import json
from dataclasses import dataclass, asdict, field, fields
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class ConversionConfig:
    """Configuration for firmware conversion settings."""
    # Identity
    name: str
    description: str = ""
    
    # Protocol
    protocol: str = "can"  # "can" or "kwp"
    kwp_format: str = "0x80"  # Only used if protocol == "kwp"; "" = omit from output
    kwp_target: str = "0x12"  # "" = omit
    kwp_source: str = "0xF1"  # "" = omit
    
    # Address Range Filter
    use_filter: bool = False
    address_ranges: List[Tuple[str, str, str]] = field(default_factory=list)  # List of (start_str, end_str, len_str); end or len can be ""
    
    # Frame Format
    max_line_len: str = "0xE0"
    sid: str = "0x36"
    use_counter: bool = True
    counter_start: str = "1"
    crc_type: str = "(none)"  # "(none)", "CRC8", "CRC16", "CRC32", "Checksum"
    crc_reverse: bool = False

    # CAN34 Format (only used when protocol == "can34")
    can34_byte1: str = "0x34"
    can34_byte2: str = "0x82"
    can34_frame_len: str = "0xF0"
    can34_crc_type: str = "NCCITT"
    can34_crc_reverse: bool = False

    # Options
    split: bool = True
    out_dir: str = ""  # Relative path only (absolute paths not stored - user-specific)
    out_prefix: str = "block"
    cont_counter: bool = False
    
    # Advanced
    bin_start: str = "0x0"
    fill: str = "0xFF"
    fill_gaps: bool = False
    validate_srec: bool = False
    
    # Metadata (for sync)
    author: str = ""
    remote_id: Optional[str] = None
    is_local: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert address_ranges from list of tuples to list of lists for JSON
        data['address_ranges'] = [list(r) for r in data['address_ranges']]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversionConfig':
        """Create config from dictionary (from JSON)."""
        data = dict(data)  # copy to avoid mutating caller's dict
        # Convert address_ranges from list of lists back to list of 3-tuples (start, end, len)
        if 'address_ranges' in data:
            normalized = []
            for r in data['address_ranges']:
                r = list(r)
                if len(r) == 2:
                    normalized.append((r[0], r[1], ""))
                else:
                    normalized.append((r[0], r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else ""))
            data['address_ranges'] = normalized
        # Migrate legacy use_checksum: if use_checksum was True and no CRC type, set crc_type to "Checksum"
        if data.get('use_checksum') and (data.get('crc_type') or '(none)').strip() in ('', '(none)'):
            data['crc_type'] = 'Checksum'
        data.pop('use_checksum', None)
        # Only pass known fields (ignore unknown keys from old configs) (ignore extra keys from API or future fields)
        valid = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return cls(**filtered)


class ConfigManager:
    """Manages conversion configs in local cache."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize config manager.
        
        Args:
            cache_dir: Directory for cache files. Defaults to ./cache/configs/
        """
        if cache_dir is None:
            cache_dir = Path.cwd() / "cache" / "configs"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def list_configs(self) -> List[str]:
        """
        List all available config names.
        
        Returns:
            List of config names (without .json extension)
        """
        if not self.cache_dir.exists():
            return []
        
        configs = []
        for file_path in self.cache_dir.glob("*.json"):
            try:
                # Validate it's a valid config by trying to load it
                with file_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'name' in data:
                        configs.append(data['name'])
            except (json.JSONDecodeError, IOError, KeyError):
                # Skip invalid files
                continue
        
        return sorted(configs)
    
    def load_config(self, name: str) -> Optional[ConversionConfig]:
        """
        Load a config by name.
        
        Args:
            name: Config name
            
        Returns:
            ConversionConfig if found, None otherwise
        """
        # Find file by name (config name might not match filename)
        for file_path in self.cache_dir.glob("*.json"):
            try:
                with file_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('name') == name:
                        return ConversionConfig.from_dict(data)
            except (json.JSONDecodeError, IOError, KeyError):
                continue
        
        return None
    
    def save_config(self, config: ConversionConfig) -> bool:
        """
        Save a config to local cache.
        
        Args:
            config: ConversionConfig to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use sanitized name as filename
            safe_name = self._sanitize_filename(config.name)
            file_path = self.cache_dir / f"{safe_name}.json"
            
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            
            return True
        except (IOError, OSError) as e:
            print(f"Error saving config: {e}")
            return False
    
    def delete_config(self, name: str) -> bool:
        """
        Delete a config by name.
        
        Args:
            name: Config name to delete
            
        Returns:
            True if deleted, False if not found
        """
        for file_path in self.cache_dir.glob("*.json"):
            try:
                with file_path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('name') == name:
                        file_path.unlink()
                        return True
            except (json.JSONDecodeError, IOError, OSError):
                continue
        
        return False
    
    def config_exists(self, name: str) -> bool:
        """
        Check if a config with given name exists.
        
        Args:
            name: Config name to check
            
        Returns:
            True if exists, False otherwise
        """
        return self.load_config(name) is not None
    
    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize config name for use as filename.
        
        Args:
            name: Original config name
            
        Returns:
            Sanitized filename-safe string
        """
        # Replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        safe = name
        for char in invalid_chars:
            safe = safe.replace(char, '_')
        # Remove leading/trailing spaces and dots
        safe = safe.strip(' .')
        # If empty after sanitization, use default
        if not safe:
            safe = "config"
        return safe
