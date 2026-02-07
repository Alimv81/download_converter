import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import re
from intelhex import IntelHex


class ProtocolType(Enum):
    CAN = "can"
    KWP = "kwp"


@dataclass(frozen=True)
class OutputFormat:
    """
    Output line format (configurable):

    CAN format:
    - 2 bytes: big-endian length
    - then exactly `line_len` bytes follow, structured as:
        - 1 byte: service byte (SID, configurable, default 0x36)
        - 0 or 1 byte: counter (optional, wraps mod 256)
        - remaining bytes: firmware data
        - 0, 1, 2, or 4 bytes: CRC (optional)
        - 0 or 1 byte: checksum (optional)

    KWP format:
    - 1 byte: format byte (0x80=physical, 0x81=functional, 0xC2=extended)
    - 1 byte: length (target + source + service + counter? + data + CRC? + checksum)
    - 1 byte: target address
    - 1 byte: source address
    - 1 byte: service byte (SID)
    - 0 or 1 byte: counter (optional)
    - remaining bytes: firmware data
    - 0, 1, 2, or 4 bytes: CRC (optional)
    - 1 byte: checksum (XOR or sum, typically always present)
    """

    protocol: ProtocolType = ProtocolType.CAN
    max_line_len: int = 0xE0
    service_byte: int = 0x36
    use_counter: bool = True
    counter_start: int = 1
    crc_type: Optional[str] = None  # None, "CRC8", "CRC16", "CRC32", "Checksum"
    crc_bytes: int = 0  # 0, 1, 2, or 4 (1 for Checksum)
    crc_reverse_bytes: bool = False  # Reverse byte order for multi-byte CRCs (not used for Checksum)
    # KWP-specific fields (None = omit from output frame)
    kwp_format_byte: Optional[int] = 0x80  # 0x80=physical, etc.; None = omit, frame starts with length
    kwp_target_addr: Optional[int] = 0x12  # Target ECU address; None = omit
    kwp_source_addr: Optional[int] = 0xF1  # Tester address; None = omit

    @property
    def data_bytes_per_line(self) -> int:
        """Calculate how many data bytes fit in each line after header and trailer (CRC or Checksum)."""
        if self.protocol == ProtocolType.CAN:
            header_bytes = 1  # service_byte
            if self.use_counter:
                header_bytes += 1
            return self.max_line_len - header_bytes - self.crc_bytes
        else:  # KWP
            header_bytes = 1  # service_byte
            if self.use_counter:
                header_bytes += 1
            fixed_kwp_header = (1 if self.kwp_target_addr is not None else 0) + (1 if self.kwp_source_addr is not None else 0)
            return self.max_line_len - fixed_kwp_header - header_bytes - self.crc_bytes


def calculate_crc8(data: List[int], polynomial: int = 0x07, init_value: int = 0x00) -> int:
    """
    Calculate CRC-8 using polynomial 0x07 (common in automotive/CAN).
    Other common polynomials: 0x31 (Dallas/Maxim), 0x9B (DARC).
    """
    crc = init_value
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ polynomial) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc & 0xFF


def calculate_crc16(data: List[int], polynomial: int = 0x1021, init_value: int = 0xFFFF) -> int:
    """
    Calculate CRC-16-CCITT (polynomial 0x1021, init 0xFFFF).
    Other common variants: CRC-16-IBM (0x8005, init 0xFFFF), CRC-16-MODBUS (0x8005, init 0xFFFF, reflected).
    """
    crc = init_value
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ polynomial) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def calculate_crc32(
    data: List[int],
    polynomial: int = 0xEDB88320,  # Reflected form of 0x04C11DB7 (IEEE 802.3)
    init_value: int = 0xFFFFFFFF,
    final_xor: int = 0xFFFFFFFF,
) -> int:
    """
    Calculate CRC-32 using reflected algorithm (matches IEEE 802.3 / zlib with defaults).
    Default polynomial 0xEDB88320, init 0xFFFFFFFF, final XOR 0xFFFFFFFF equals zlib.crc32.
    CRC-32C (Castagnoli) uses polynomial 0x82F63B78.
    """
    crc = init_value & 0xFFFFFFFF
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            if crc & 1:
                crc = ((crc >> 1) ^ polynomial) & 0xFFFFFFFF
            else:
                crc = (crc >> 1) & 0xFFFFFFFF
    return (crc ^ final_xor) & 0xFFFFFFFF


def calculate_checksum(data: List[int]) -> int:
    """
    Calculate simple byte sum checksum (1 byte).
    Returns the sum of all bytes modulo 256.
    """
    return sum(data) & 0xFF


def calculate_kwp_checksum(data: List[int]) -> int:
    """
    Calculate KWP2000 checksum (XOR of all bytes).
    This is the standard KWP checksum method.
    """
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum & 0xFF


def calculate_crc(data: List[int], crc_type: str, reverse_bytes: bool = False) -> List[int]:
    """
    Calculate CRC and return as list of bytes.
    
    For multi-byte CRCs:
    - If reverse_bytes=False: little-endian (LSB first)
    - If reverse_bytes=True: big-endian (MSB first, bytes reversed)
    
    For CRC8 (single byte), reverse_bytes has no effect.
    """
    if crc_type == "CRC8":
        crc_val = calculate_crc8(data)
        return [crc_val]
    elif crc_type == "CRC16":
        crc_val = calculate_crc16(data)
        if reverse_bytes:
            # Big-endian: MSB first
            return [(crc_val >> 8) & 0xFF, crc_val & 0xFF]
        else:
            # Little-endian: LSB first
            return [crc_val & 0xFF, (crc_val >> 8) & 0xFF]
    elif crc_type == "CRC32":
        crc_val = calculate_crc32(data)
        if reverse_bytes:
            # Big-endian: MSB first
            return [
                (crc_val >> 24) & 0xFF,
                (crc_val >> 16) & 0xFF,
                (crc_val >> 8) & 0xFF,
                crc_val & 0xFF,
            ]
        else:
            # Little-endian: LSB first
            return [
                crc_val & 0xFF,
                (crc_val >> 8) & 0xFF,
                (crc_val >> 16) & 0xFF,
                (crc_val >> 24) & 0xFF,
            ]
    else:
        raise ValueError(f"Unknown CRC type: {crc_type}")


def parse_srecord_to_mem(path: Path, *, validate_checksum: bool = False) -> Dict[int, int]:
    """
    Parse Motorola S-record file into address->byte map.
    Supports S1/S2/S3 data records. Ignores non-data records.
    """
    mem: Dict[int, int] = {}
    with path.open("r", encoding="ascii", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line.startswith("S") or len(line) < 4:
                continue

            rtype = line[1]
            if rtype not in {"1", "2", "3"}:
                continue

            try:
                count = int(line[2:4], 16)
            except ValueError:
                continue

            addr_len_bytes = {"1": 2, "2": 3, "3": 4}[rtype]
            addr_len_chars = addr_len_bytes * 2

            # After 'S' + type + count(2 hex chars), we have:
            # address(addr_len_bytes) + data(N) + checksum(1 byte)
            addr_start = 4
            addr_end = addr_start + addr_len_chars
            if len(line) < addr_end + 2:  # must at least have checksum byte
                continue

            try:
                addr = int(line[addr_start:addr_end], 16)
            except ValueError:
                continue

            data_len_bytes = count - addr_len_bytes - 1
            if data_len_bytes < 0:
                continue

            data_start = addr_end
            data_end = data_start + data_len_bytes * 2
            checksum_start = data_end
            checksum_end = checksum_start + 2
            if len(line) < checksum_end:
                continue

            # Optional checksum validation:
            # checksum is ones-complement of the least significant byte of the sum of
            # count + address bytes + data bytes.
            if validate_checksum:
                try:
                    checksum = int(line[checksum_start:checksum_end], 16)
                except ValueError:
                    continue
                total = count
                for i in range(0, addr_len_chars, 2):
                    total += int(line[addr_start + i : addr_start + i + 2], 16)
                for i in range(0, data_len_bytes * 2, 2):
                    total += int(line[data_start + i : data_start + i + 2], 16)
                total &= 0xFF
                expected = (~total) & 0xFF
                if checksum != expected:
                    raise ValueError(
                        f"S-record checksum mismatch at address 0x{addr:X}: "
                        f"got 0x{checksum:02X}, expected 0x{expected:02X}"
                    )

            for i in range(data_len_bytes):
                byte_hex = line[data_start + 2 * i : data_start + 2 * i + 2]
                try:
                    b = int(byte_hex, 16)
                except ValueError:
                    b = 0xFF
                mem[addr + i] = b

    return mem


def parse_hex_to_mem(path: Path) -> Dict[int, int]:
    """
    Parse Intel HEX into address->byte map.

    Notes:
    - Supports record types: 00 (data), 01 (EOF), 02 (extended segment address),
      04 (extended linear address).
    - Tolerates "pretty" hex lines that include ANSI color codes and/or trailing
      annotations (keeps only the ':' record).
    - If input contains overlapping data, later bytes overwrite earlier bytes.
    """

    # Fast path: normal Intel HEX files.
    try:
        ih = IntelHex(str(path))
        return {addr: int(ih[addr]) for addr in ih.addresses()}
    except Exception:
        pass

    # ANSI escape sequences (e.g. pretty-printed HEX fixtures with colors)
    ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def clean_record_line(line: str) -> Optional[str]:
        # Strip ANSI escape codes
        line = ansi_re.sub("", line).strip()
        if not line:
            return None
        # Keep only the part starting at the first ':'
        if ":" not in line:
            return None
        line = line[line.index(":") :].strip()
        # Drop trailing annotations like " (data)"
        if " " in line:
            line = line.split(" ", 1)[0]
        if "\t" in line:
            line = line.split("\t", 1)[0]
        if "(" in line:
            line = line.split("(", 1)[0].strip()
        return line if line.startswith(":") and len(line) >= 11 else None

    mem: Dict[int, int] = {}
    base = 0  # upper address base

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = clean_record_line(raw)
            if not line:
                continue

            try:
                count = int(line[1:3], 16)
                addr = int(line[3:7], 16)
                rtype = int(line[7:9], 16)
                data_hex = line[9 : 9 + count * 2]
                checksum = int(line[9 + count * 2 : 11 + count * 2], 16)
            except Exception:
                continue

            # Verify checksum (best-effort; if line is malformed we already skipped)
            try:
                total = count + ((addr >> 8) & 0xFF) + (addr & 0xFF) + rtype
                for i in range(0, len(data_hex), 2):
                    total += int(data_hex[i : i + 2], 16)
                total &= 0xFF
                expected = ((~total) + 1) & 0xFF
                if checksum != expected:
                    # Ignore checksum mismatch rather than failing hard (some fixtures are non-strict).
                    pass
            except Exception:
                pass

            if rtype == 0x00:  # data
                abs_addr = base + addr
                for i in range(count):
                    b = int(data_hex[2 * i : 2 * i + 2], 16)
                    mem[abs_addr + i] = b
            elif rtype == 0x01:  # EOF
                break
            elif rtype == 0x02:  # extended segment address (base = value << 4)
                if count == 2:
                    seg = int(data_hex, 16)
                    base = (seg << 4) & 0xFFFFFFFF
            elif rtype == 0x04:  # extended linear address (base = value << 16)
                if count == 2:
                    upper = int(data_hex, 16)
                    base = (upper << 16) & 0xFFFFFFFF
            else:
                # Ignore other record types
                continue

    return mem


def parse_bin_to_mem(path: Path, *, start_addr: int = 0) -> Dict[int, int]:
    b = path.read_bytes()
    return {start_addr + i: byte for i, byte in enumerate(b)}


def filter_mem_by_ranges(mem: Dict[int, int], ranges: List[Tuple[int, int]]) -> Dict[int, int]:
    """
    Filter memory map to only include addresses within the specified ranges.
    
    Args:
        mem: Original memory map (address -> byte)
        ranges: List of (start_addr, end_addr) tuples (inclusive on both ends)
    
    Returns:
        Filtered memory map containing only addresses within the specified ranges
    """
    if not ranges:
        return mem
    
    filtered: Dict[int, int] = {}
    for addr, byte_val in mem.items():
        for start, end in ranges:
            if start <= addr <= end:
                filtered[addr] = byte_val
                break
    
    return filtered


def mem_to_segments_by_ranges(mem: Dict[int, int], ranges: List[Tuple[int, int]], *, fill: int = 0xFF, fill_gaps: bool = False) -> List[Tuple[int, int, List[int]]]:
    """
    Convert memory map into segments based on specified address ranges.
    Each range produces one segment, even if they overlap or are contiguous.
    
    Args:
        mem: Memory map (address -> byte)
        ranges: List of (start_addr, end_addr) tuples (inclusive on both ends)
        fill: Fill byte for gaps within a range
        fill_gaps: If True, fill gaps within each range with fill byte
    
    Returns:
        List of (start_addr, end_addr, bytes) segments, one per range
    """
    if not ranges:
        return []
    
    segments: List[Tuple[int, int, List[int]]] = []
    
    for start, end in ranges:
        if start > end:
            continue
        
        # Collect bytes for this range
        range_bytes: List[int] = []
        range_addrs: List[int] = []
        
        for addr in range(start, end + 1):
            if addr in mem:
                range_bytes.append(mem[addr] & 0xFF)
                range_addrs.append(addr)
            elif fill_gaps:
                range_bytes.append(fill & 0xFF)
                range_addrs.append(addr)
        
        # Only create segment if there's data or if fill_gaps is enabled
        if range_bytes:
            # Determine actual start/end based on data present
            if range_addrs:
                actual_start = min(range_addrs)
                actual_end = max(range_addrs)
            else:
                actual_start = start
                actual_end = end
            
            segments.append((actual_start, actual_end, range_bytes))
    
    return segments


def mem_to_segments(mem: Dict[int, int], *, fill: int = 0xFF, fill_gaps: bool = False) -> List[Tuple[int, int, List[int]]]:
    """
    Convert address->byte map into a list of (start_addr, end_addr, bytes) segments.

    - If fill_gaps=False (default): produce one segment per contiguous address range.
    - If fill_gaps=True: produce a single dense segment spanning [min_addr, max_addr],
      filling gaps with `fill`.
    """
    if not mem:
        return []

    addrs = sorted(mem.keys())
    if fill_gaps:
        start = addrs[0]
        end = addrs[-1]
        out = [fill] * (end - start + 1)
        for a, v in mem.items():
            out[a - start] = v & 0xFF
        return [(start, end, out)]

    segments: List[Tuple[int, int, List[int]]] = []
    seg_start = addrs[0]
    seg_bytes: List[int] = [mem[seg_start] & 0xFF]
    prev = seg_start

    for a in addrs[1:]:
        if a != prev + 1:
            segments.append((seg_start, prev, seg_bytes))
            seg_start = a
            seg_bytes = [mem[a] & 0xFF]
        else:
            seg_bytes.append(mem[a] & 0xFF)
        prev = a

    segments.append((seg_start, prev, seg_bytes))
    return segments


def mem_to_bytes(mem: Dict[int, int], *, fill: int = 0xFF, fill_gaps: bool = False) -> List[int]:
    """
    Convert address->byte map into a byte stream.

    - If fill_gaps=False (default): concatenate contiguous address ranges and
      *skip* gaps between ranges (matches existing output_can.txt behavior).
    - If fill_gaps=True: produce a dense byte array spanning [min_addr, max_addr],
      filling gaps with `fill`.
    """
    if not mem:
        return []

    addrs = sorted(mem.keys())
    if fill_gaps:
        start = addrs[0]
        end = addrs[-1]
        out = [fill] * (end - start + 1)
        for a, v in mem.items():
            out[a - start] = v & 0xFF
        return out

    out: List[int] = []
    prev: Optional[int] = None
    for a in addrs:
        if prev is not None and a != prev + 1:
            # start a new segment; do not emit any filler for gaps
            pass
        out.append(mem[a] & 0xFF)
        prev = a
    return out


def chunk_iter(data: List[int], n: int) -> Iterator[List[int]]:
    for i in range(0, len(data), n):
        yield data[i : i + n]


def format_frames_can(data: List[int], fmt: OutputFormat, *, counter_start: Optional[int] = None) -> Iterator[List[int]]:
    """
    Turn firmware bytes into CAN output frames following `OutputFormat`.
    Uses fixed length (=max_line_len) for full frames, and a short final frame
    with the real remaining byte count (no padding).
    
    Frame structure: [length_hi, length_lo, service_byte, (counter?), ...data..., (crc?), (checksum?)]
    The length field includes everything after the 2-byte length header.
    
    Important: max_line_len is the TOTAL payload length (service + counter + data + CRC + checksum).
    Data bytes are calculated to fit within this limit.
    """
    counter = (fmt.counter_start if counter_start is None else counter_start) & 0xFF
    
    # Calculate fixed header size (service + optional counter)
    fixed_header_size = 1  # service_byte
    if fmt.use_counter:
        fixed_header_size += 1
    
    # Calculate how many data bytes we can fit per frame (trailer = CRC or Checksum, one of them only)
    data_bytes_per_frame = fmt.max_line_len - fixed_header_size - fmt.crc_bytes
    
    if data_bytes_per_frame <= 0:
        raise ValueError(
            f"max_line_len ({fmt.max_line_len}) is too small to fit header ({fixed_header_size} bytes) "
            f"and trailer ({fmt.crc_bytes} bytes). Need at least {fixed_header_size + fmt.crc_bytes + 1} bytes."
        )
    
    for chunk in chunk_iter(data, data_bytes_per_frame):
        # Build frame payload (service_byte + optional counter + data)
        payload: List[int] = []
        payload.append(fmt.service_byte & 0xFF)
        if fmt.use_counter:
            payload.append(counter)
        payload.extend(chunk)
        
        # Append trailer: either CRC or Checksum (only one)
        if fmt.crc_type == "Checksum":
            payload.append(calculate_checksum(payload))
        elif fmt.crc_type:
            crc_bytes = calculate_crc(payload, fmt.crc_type, reverse_bytes=fmt.crc_reverse_bytes)
            payload.extend(crc_bytes)
        
        # Verify payload length matches max_line_len for full frames
        payload_len = len(payload)
        is_last = len(chunk) < data_bytes_per_frame
        
        if not is_last:
            # For full frames, payload must equal max_line_len
            if payload_len != fmt.max_line_len:
                raise ValueError(
                    f"Payload length mismatch: expected {fmt.max_line_len}, got {payload_len}. "
                    f"Header: {fixed_header_size}, Data: {len(chunk)}, Trailer: {fmt.crc_bytes}"
                )
        
        # The length field represents the payload length (not including the 2-byte length header itself)
        frame: List[int] = []
        frame.append((payload_len >> 8) & 0xFF)
        frame.append(payload_len & 0xFF)
        frame.extend(payload)
        
        yield frame
        
        if fmt.use_counter:
            counter = (counter + 1) & 0xFF


def format_frames_kwp(data: List[int], fmt: OutputFormat, *, counter_start: Optional[int] = None) -> Iterator[List[int]]:
    """
    Format frames in KWP2000 format.
    
    Optional bytes (when None are omitted):
    [format_byte?] + [length] + [target?] + [source?] + [service] + [counter?] + [data] + [CRC?] + [checksum]
    Length = size of everything after the length byte (target? + source? + service + ...).
    """
    counter = (fmt.counter_start if counter_start is None else counter_start) & 0xFF
    
    fixed_header_size = 1  # service_byte
    if fmt.use_counter:
        fixed_header_size += 1
    fixed_kwp_header = (1 if fmt.kwp_target_addr is not None else 0) + (1 if fmt.kwp_source_addr is not None else 0)
    data_bytes_per_frame = fmt.max_line_len - fixed_kwp_header - fixed_header_size - fmt.crc_bytes
    
    if data_bytes_per_frame <= 0:
        raise ValueError(
            f"max_line_len ({fmt.max_line_len}) is too small for KWP format. "
            f"Need at least {fixed_kwp_header + fixed_header_size + fmt.crc_bytes + 1} bytes."
        )
    
    for chunk in chunk_iter(data, data_bytes_per_frame):
        payload: List[int] = []
        if fmt.kwp_target_addr is not None:
            payload.append(fmt.kwp_target_addr & 0xFF)
        if fmt.kwp_source_addr is not None:
            payload.append(fmt.kwp_source_addr & 0xFF)
        payload.append(fmt.service_byte & 0xFF)
        if fmt.use_counter:
            payload.append(counter)
        payload.extend(chunk)
        
        # Append trailer: either CRC or Checksum (only one); KWP has no default trailer when none selected
        if fmt.crc_type == "Checksum":
            payload.append(calculate_checksum(payload))
        elif fmt.crc_type:
            crc_bytes = calculate_crc(payload, fmt.crc_type, reverse_bytes=fmt.crc_reverse_bytes)
            payload.extend(crc_bytes)
        
        length_byte = len(payload) & 0xFF
        
        frame: List[int] = []
        if fmt.kwp_format_byte is not None:
            frame.append(fmt.kwp_format_byte & 0xFF)
        frame.append(length_byte)
        frame.extend(payload)
        
        yield frame
        
        if fmt.use_counter:
            counter = (counter + 1) & 0xFF


def format_frames(data: List[int], fmt: OutputFormat, *, counter_start: Optional[int] = None) -> Iterator[List[int]]:
    """
    Dispatch to appropriate formatter based on protocol type.
    """
    if fmt.protocol == ProtocolType.KWP:
        return format_frames_kwp(data, fmt, counter_start=counter_start)
    else:  # CAN (default)
        return format_frames_can(data, fmt, counter_start=counter_start)


def frame_count_for_data_len(data_len: int, fmt: OutputFormat) -> int:
    if data_len <= 0:
        return 0
    n = fmt.data_bytes_per_line
    return (data_len + n - 1) // n


def write_frames(frames: Iterable[List[int]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use CRLF to match existing reference outputs (Windows-style line endings).
    with out_path.open("w", encoding="ascii", newline="") as f:
        for frame in frames:
            f.write(" ".join(f"{b:02X}" for b in frame) + "\r\n")


def infer_type_from_suffix(p: Path) -> str:
    s = p.suffix.lower().lstrip(".")
    if s in {"s19", "s28", "s37"}:
        return s
    if s in {"hex"}:
        return "hex"
    if s in {"bin"}:
        return "bin"
    raise ValueError(f"Cannot infer file type from extension: {p.name}")


def main() -> None:
    # If launched with no CLI parameters, open the GUI.
    # (Keeps existing CLI behavior unchanged when arguments are provided.)
    if len(sys.argv) == 1:
        from gui import run_gui

        run_gui()
        return

    ap = argparse.ArgumentParser(description="Convert s19/s28/s37/hex/bin to CAN/KWP text output format.")
    ap.add_argument("input", type=str, help="Input firmware file path")
    ap.add_argument("--type", type=str, default=None, help="Input type: s19|s28|s37|hex|bin (default: infer from extension)")
    ap.add_argument("--protocol", type=str, choices=["can", "kwp"], default="can", help="Output protocol: can or kwp (default: can)")
    ap.add_argument("--out", type=str, default="output_can.txt", help="Output text file path")
    ap.add_argument("--split-by-address", action="store_true", help="Write one output file per contiguous address range", default=True)
    ap.add_argument("--out-dir", type=str, default="output_segments", help="Output directory when using --split-by-address")
    ap.add_argument("--out-prefix", type=str, default="seg", help="Filename prefix when using --split-by-address")
    ap.add_argument("--continuous-counter", action="store_true", help="When splitting, continue counter across segments (instead of resetting per file)")
    ap.add_argument("--bin-start-addr", type=lambda x: int(x, 0), default=0, help="Start address for BIN (default 0)")
    ap.add_argument("--fill", type=lambda x: int(x, 0), default=0xFF, help="Fill byte for address gaps (default 0xFF)")
    ap.add_argument("--fill-gaps", action="store_true", help="Fill address gaps with --fill instead of skipping them")
    ap.add_argument("--validate-srec-checksum", action="store_true", help="Validate S-record checksums (slower)")
    ap.add_argument("--sid", type=lambda x: int(x, 0), default=0x36, help="Service ID byte (default 0x36)")
    ap.add_argument("--no-counter", action="store_true", help="Omit counter byte from output frames")
    ap.add_argument("--counter-start", type=int, default=1, help="Starting counter value (default 1)")
    ap.add_argument("--crc", type=str, choices=["CRC8", "CRC16", "CRC32", "Checksum"], default=None, help="CRC or checksum type to append to frames (default: none)")
    ap.add_argument("--crc-reverse", action="store_true", help="Reverse CRC byte order (big-endian for multi-byte CRCs; not used for Checksum)")
    ap.add_argument("--max-line-len", type=lambda x: int(x, 0), default=0xE0, help="Maximum line length (payload after 2-byte length header for CAN, or after format+length for KWP, default 0xE0)")
    ap.add_argument("--kwp-format", type=lambda x: int(x, 0), default=0x80, help="KWP format byte: 0x80=physical, 0x81=functional, 0xC2=extended (default: 0x80)")
    ap.add_argument("--kwp-target", type=lambda x: int(x, 0), default=0x12, help="KWP target address (default: 0x12)")
    ap.add_argument("--kwp-source", type=lambda x: int(x, 0), default=0xF1, help="KWP source address (default: 0xF1)")
    ap.add_argument("--address-ranges", type=str, nargs="+", metavar="START:END", 
                    help="Filter by address ranges (format: START:END, can specify multiple, e.g., --address-ranges 0x1000:0x1FFF 0x5000:0x5FFF)")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise FileNotFoundError(str(in_path))

    ftype = (args.type or infer_type_from_suffix(in_path)).lower()

    if ftype in {"s19", "s28", "s37"}:
        mem = parse_srecord_to_mem(in_path, validate_checksum=bool(args.validate_srec_checksum))
    elif ftype == "hex":
        mem = parse_hex_to_mem(in_path)
    elif ftype == "bin":
        mem = parse_bin_to_mem(in_path, start_addr=int(args.bin_start_addr))
    else:
        raise ValueError(f"Unsupported type: {ftype}")

    # Parse address ranges if specified
    parsed_ranges: Optional[List[Tuple[int, int]]] = None
    if args.address_ranges:
        parsed_ranges = []
        for range_str in args.address_ranges:
            try:
                if ":" not in range_str:
                    raise ValueError(f"Invalid range format: {range_str}. Expected START:END")
                start_str, end_str = range_str.split(":", 1)
                start = int(start_str.strip(), 0)
                end = int(end_str.strip(), 0)
                if start > end:
                    raise ValueError(f"Start address ({start_str}) must be <= end address ({end_str})")
                parsed_ranges.append((start, end))
            except ValueError as e:
                raise ValueError(f"Invalid address range '{range_str}': {e}")
        
        if parsed_ranges:
            # Only filter if NOT splitting by address (when splitting, we'll use ranges directly)
            if not args.split_by_address:
                original_size = len(mem)
                mem = filter_mem_by_ranges(mem, parsed_ranges)
                filtered_size = len(mem)
                print(f"Filtered: {original_size} → {filtered_size} addresses")
                if filtered_size == 0:
                    raise ValueError("No data found in specified address ranges")

    # Determine protocol type
    protocol = ProtocolType.CAN if args.protocol == "can" else ProtocolType.KWP
    
    # Determine trailer bytes based on type (CRC or Checksum)
    crc_bytes = 0
    if args.crc == "CRC8":
        crc_bytes = 1
    elif args.crc == "CRC16":
        crc_bytes = 2
    elif args.crc == "CRC32":
        crc_bytes = 4
    elif args.crc == "Checksum":
        crc_bytes = 1
    
    fmt = OutputFormat(
        protocol=protocol,
        max_line_len=int(args.max_line_len) & 0xFFFF,
        service_byte=int(args.sid) & 0xFF,
        use_counter=not args.no_counter,
        counter_start=int(args.counter_start) & 0xFF,
        crc_type=args.crc,
        crc_bytes=crc_bytes,
        crc_reverse_bytes=bool(args.crc_reverse),
        kwp_format_byte=int(args.kwp_format) & 0xFF if protocol == ProtocolType.KWP else 0x80,
        kwp_target_addr=int(args.kwp_target) & 0xFF if protocol == ProtocolType.KWP else 0x12,
        kwp_source_addr=int(args.kwp_source) & 0xFF if protocol == ProtocolType.KWP else 0xF1,
    )

    if args.split_by_address:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # If address ranges are specified, create one segment per range (no merging)
        if parsed_ranges:
            segments = mem_to_segments_by_ranges(mem, parsed_ranges, fill=int(args.fill) & 0xFF, fill_gaps=bool(args.fill_gaps))
        else:
            # No ranges specified, use normal contiguous block splitting
            segments = mem_to_segments(mem, fill=int(args.fill) & 0xFF, fill_gaps=bool(args.fill_gaps))
        
        next_counter = fmt.counter_start
        for idx, (start, end, seg_bytes) in enumerate(segments, start=1):
            cstart = next_counter if args.continuous_counter else fmt.counter_start
            frames = format_frames(seg_bytes, fmt, counter_start=cstart)
            out_path = out_dir / f"{args.out_prefix}_{idx:03d}_0x{start:08X}_0x{end:08X}.txt"
            write_frames(frames, out_path)
            if args.continuous_counter:
                next_counter = (cstart + frame_count_for_data_len(len(seg_bytes), fmt)) & 0xFF
    else:
        data = mem_to_bytes(mem, fill=int(args.fill) & 0xFF, fill_gaps=bool(args.fill_gaps))
        frames = format_frames(data, fmt)
        write_frames(frames, Path(args.out))


if __name__ == "__main__":
    main()

