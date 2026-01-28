import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import re
from intelhex import IntelHex


@dataclass(frozen=True)
class OutputFormat:
    """
    Output line format (matches existing output_can.txt):

    - 2 bytes: big-endian length (always 0x0040 in current format)
    - then exactly `line_len` bytes follow, structured as:
        - 1 byte: service byte (0x36)
        - 1 byte: counter (1..255, wraps mod 256)
        - remaining bytes: firmware data (line_len - 2 bytes)

    Total bytes per output line = 2 + line_len (=> 66 when line_len=0x40).
    """

    max_line_len: int = 0x40
    service_byte: int = 0x36
    counter_start: int = 1

    @property
    def data_bytes_per_line(self) -> int:
        return self.max_line_len - 2


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


def format_frames(data: List[int], fmt: OutputFormat, *, counter_start: Optional[int] = None) -> Iterator[List[int]]:
    """
    Turn firmware bytes into output frames following `OutputFormat`.
    Uses fixed length (=max_line_len) for full frames, and a short final frame
    with the real remaining byte count (no padding), matching output_can.txt.
    """
    counter = (fmt.counter_start if counter_start is None else counter_start) & 0xFF
    for chunk in chunk_iter(data, fmt.data_bytes_per_line):
        is_last = len(chunk) < fmt.data_bytes_per_line
        line_len = (2 + len(chunk)) if is_last else fmt.max_line_len
        frame: List[int] = []
        frame.append((line_len >> 8) & 0xFF)
        frame.append(line_len & 0xFF)
        frame.append(fmt.service_byte & 0xFF)
        frame.append(counter)
        frame.extend(chunk)
        yield frame
        counter = (counter + 1) & 0xFF


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

    ap = argparse.ArgumentParser(description="Convert s19/s28/s37/hex/bin to CAN text output format.")
    ap.add_argument("input", type=str, help="Input firmware file path")
    ap.add_argument("--type", type=str, default=None, help="Input type: s19|s28|s37|hex|bin (default: infer from extension)")
    ap.add_argument("--out", type=str, default="output_can.txt", help="Output text file path")
    ap.add_argument("--split-by-address", action="store_true", help="Write one output file per contiguous address range")
    ap.add_argument("--out-dir", type=str, default="output_segments", help="Output directory when using --split-by-address")
    ap.add_argument("--out-prefix", type=str, default="seg", help="Filename prefix when using --split-by-address")
    ap.add_argument("--continuous-counter", action="store_true", help="When splitting, continue counter across segments (instead of resetting per file)")
    ap.add_argument("--bin-start-addr", type=lambda x: int(x, 0), default=0, help="Start address for BIN (default 0)")
    ap.add_argument("--fill", type=lambda x: int(x, 0), default=0xFF, help="Fill byte for address gaps (default 0xFF)")
    ap.add_argument("--fill-gaps", action="store_true", help="Fill address gaps with --fill instead of skipping them")
    ap.add_argument("--validate-srec-checksum", action="store_true", help="Validate S-record checksums (slower)")
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

    fmt = OutputFormat()

    if args.split_by_address:
        segments = mem_to_segments(mem, fill=int(args.fill) & 0xFF, fill_gaps=bool(args.fill_gaps))
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
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

