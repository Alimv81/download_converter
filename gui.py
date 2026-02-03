import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, simpledialog
from typing import List, Optional, Tuple, Dict

from config_manager import ConfigManager, ConversionConfig
from api_client import APIClient, ConfigSync, APIError


@dataclass
class GuiConfig:
    app_title: str = "Firmware Converter"


class ConverterGui(tk.Tk):
    def __init__(self, cfg: Optional[GuiConfig] = None):
        super().__init__()
        self.cfg = cfg or GuiConfig()

        self.title(self.cfg.app_title)
        # Make fullscreen by default (cross-platform)
        try:
            # Windows
            self.state("zoomed")
        except tk.TclError:
            try:
                # Linux (X11)
                self.attributes("-zoomed", True)
            except tk.TclError:
                try:
                    # macOS or fallback: maximize window
                    self.update_idletasks()
                    width = self.winfo_screenwidth()
                    height = self.winfo_screenheight()
                    self.geometry(f"{width}x{height}+0+0")
                except Exception:
                    # Final fallback: use default size
                    self.geometry("860x600")
        self.minsize(820, 520)

        self._init_theme()
        
        # Initialize config manager
        self.config_manager = ConfigManager()
        
        # Initialize API client (optional - can be None if offline)
        # TODO: Make API URL configurable (env var, settings file, etc.)
        self.api_client: Optional[APIClient] = None
        self.config_sync: Optional[ConfigSync] = None
        self._init_api_client()
        
        self._build_ui()

        self._worker: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._api_worker: Optional[threading.Thread] = None

    # ------------------ Theme ------------------
    def _init_theme(self) -> None:
        # Colors
        self.c_bg = "#0B1220"
        self.c_panel = "#0F1A2E"
        self.c_text = "#E6EEF8"
        self.c_muted = "#A7B6C8"
        self.c_accent = "#5CC8FF"
        self.c_good = "#3CCB7F"
        self.c_warn = "#FFCC66"
        self.c_bad = "#FF5C7A"
        self.c_button = "#152544"
        self.c_button_hover = "#1B2F57"

        self.configure(bg=self.c_bg)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.c_bg)
        style.configure("Panel.TFrame", background=self.c_panel)
        style.configure("TLabel", background=self.c_bg, foreground=self.c_text)
        style.configure("Muted.TLabel", background=self.c_bg, foreground=self.c_muted)
        style.configure("Panel.TLabel", background=self.c_panel, foreground=self.c_text)
        style.configure("Header.TLabel", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 14, "bold"))

        style.configure("TEntry", fieldbackground="#0C1528", foreground=self.c_text)
        style.configure("TCombobox", fieldbackground="#0C1528", foreground=self.c_text, background="#0C1528")
        style.map("TCombobox", fieldbackground=[("readonly", "#0C1528")])

        style.configure("TCheckbutton", background=self.c_bg, foreground=self.c_text)

        style.configure(
            "Accent.TButton",
            background=self.c_accent,
            foreground="#001018",
            borderwidth=0,
            padding=(12, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#79D7FF"), ("disabled", "#2D5261")],
            foreground=[("disabled", "#0B1220")],
        )

        style.configure(
            "Ghost.TButton",
            background=self.c_button,
            foreground=self.c_text,
            borderwidth=0,
            padding=(10, 7),
            font=("Segoe UI", 10),
        )
        style.map("Ghost.TButton", background=[("active", self.c_button_hover)])

        style.configure("TLabelframe", background=self.c_bg, foreground=self.c_text)
        style.configure("TLabelframe.Label", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 10, "bold"))

    def _init_api_client(self) -> None:
        """Initialize API client (can be None if offline)."""
        try:
            # TODO: Make this configurable (env var, config file, etc.)
            # For now, default to localhost:8000 (common FastAPI default)
            api_url = "http://localhost:8000"
            self.api_client = APIClient(base_url=api_url)
            self.config_sync = ConfigSync(self.config_manager, self.api_client)
        except Exception as e:
            # If API client fails to initialize, continue in offline mode
            self.api_client = None
            self.config_sync = ConfigSync(self.config_manager, None)
            print(f"API client not available (offline mode): {e}")

    # ------------------ UI ------------------
    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=18, pady=16)

        header = ttk.Frame(root)
        header.pack(fill="x")

        title = ttk.Label(header, text="Firmware → CAN Text Converter", style="Header.TLabel")
        title.pack(side="left")

        subtitle = ttk.Label(
            header,
            text="S19/S28/S37 • Intel HEX • BIN  → 00 40 36 .. frames",
            style="Muted.TLabel",
        )
        subtitle.pack(side="left", padx=14, pady=4)

        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, pady=(14, 0))

        # Create scrollable frame for left side
        left_container = ttk.Frame(body)
        left_container.pack(side="left", fill="both", expand=True, padx=(0, 12))
        
        # Canvas and scrollbar for scrolling
        left_canvas = tk.Canvas(left_container, bg=self.c_bg, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=left_canvas.yview)
        left = ttk.Frame(left_canvas)
        
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_canvas_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        
        def configure_scroll_region(event):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))
            # Keep canvas width same as scrollable frame
            canvas_width = event.width
            left_canvas.itemconfig(left_canvas_window, width=canvas_width)
        
        def on_canvas_configure(event):
            canvas_width = event.width
            left_canvas.itemconfig(left_canvas_window, width=canvas_width)
        
        left.bind("<Configure>", configure_scroll_region)
        left_canvas.bind("<Configure>", on_canvas_configure)
        
        # Mouse wheel scrolling (Windows/Mac)
        def on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Linux mouse wheel scrolling
        def on_button4(event):
            left_canvas.yview_scroll(-1, "units")
        
        def on_button5(event):
            left_canvas.yview_scroll(1, "units")
        
        left_canvas.bind_all("<MouseWheel>", on_mousewheel)
        left_canvas.bind_all("<Button-4>", on_button4)
        left_canvas.bind_all("<Button-5>", on_button5)
        
        # Store reference for cleanup if needed
        self.left_canvas = left_canvas
        
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")

        right = ttk.Frame(body, style="Panel.TFrame")
        right.pack(side="right", fill="both", expand=False)

        # -------- Config Presets panel
        config_group = ttk.Labelframe(left, text="Config Presets")
        config_group.pack(fill="x", pady=(0, 12))
        
        # Config dropdown and buttons row
        config_row1 = ttk.Frame(config_group)
        config_row1.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        config_row1.columnconfigure(1, weight=1)
        
        ttk.Label(config_row1, text="💾  Preset:").grid(row=0, column=0, sticky="w")
        self.var_config_name = tk.StringVar(value="")
        self.cbo_config = ttk.Combobox(
            config_row1,
            textvariable=self.var_config_name,
            state="readonly",
            width=30,
        )
        self.cbo_config.grid(row=0, column=1, sticky="ew", padx=(10, 8))
        self.cbo_config.bind("<<ComboboxSelected>>", lambda e: self._on_config_selected())
        
        # Buttons row
        config_btn_row = ttk.Frame(config_group)
        config_btn_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        
        ttk.Button(config_btn_row, text="Load", style="Ghost.TButton", command=self._load_config).pack(side="left", padx=(0, 6))
        ttk.Button(config_btn_row, text="Save", style="Ghost.TButton", command=self._save_config).pack(side="left", padx=(0, 6))
        ttk.Button(config_btn_row, text="Delete", style="Ghost.TButton", command=self._delete_config).pack(side="left")
        
        config_group.columnconfigure(0, weight=1)
        
        # -------- Sync with Server panel
        sync_group = ttk.Labelframe(left, text="Sync with Server")
        sync_group.pack(fill="x", pady=(0, 12))
        
        sync_btn_row = ttk.Frame(sync_group)
        sync_btn_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        sync_btn_row.columnconfigure(0, weight=1)
        sync_btn_row.columnconfigure(1, weight=1)
        
        self.btn_download = ttk.Button(
            sync_btn_row, 
            text="↓ Get Latest Configs", 
            style="Ghost.TButton", 
            command=self._download_configs
        )
        self.btn_download.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        
        self.btn_upload = ttk.Button(
            sync_btn_row, 
            text="↑ Upload Current", 
            style="Ghost.TButton", 
            command=self._upload_current_config
        )
        self.btn_upload.grid(row=0, column=1, sticky="ew")
        
        # Status label
        self.var_api_status = tk.StringVar(value="Status: Checking...")
        self.lbl_api_status = ttk.Label(
            sync_group, 
            textvariable=self.var_api_status, 
            style="Muted.TLabel",
            font=("Segoe UI", 9)
        )
        self.lbl_api_status.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
        
        sync_group.columnconfigure(0, weight=1)
        
        # Check API status in background
        self._check_api_status()
        
        # Refresh config list
        self._refresh_config_list()

        # -------- Input/Output panel
        io_group = ttk.Labelframe(left, text="Input / Output")
        io_group.pack(fill="x", pady=(0, 12))

        self.var_input = tk.StringVar(value="")
        self.var_type = tk.StringVar(value="(auto)")
        self.var_out = tk.StringVar(value=str(Path.cwd() / "output_can.txt"))

        self._row_filepicker(io_group, 0, "Input file", self.var_input, self._pick_input, icon="📄")
        self._row_type(io_group, 1)
        self._row_filepicker(io_group, 2, "Output file", self.var_out, self._pick_output, icon="💾")

        # -------- Protocol Selection panel
        protocol_group = ttk.Labelframe(left, text="Protocol")
        protocol_group.pack(fill="x", pady=(0, 12))

        self.var_protocol = tk.StringVar(value="can")
        row_protocol = ttk.Frame(protocol_group)
        row_protocol.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        ttk.Radiobutton(row_protocol, text="CAN", variable=self.var_protocol, value="can", 
                        command=self._sync_protocol_fields).pack(side="left", padx=(0, 20))
        ttk.Radiobutton(row_protocol, text="KWP2000", variable=self.var_protocol, value="kwp",
                        command=self._sync_protocol_fields).pack(side="left")

        # KWP-specific fields (initially hidden/disabled)
        self.var_kwp_format = tk.StringVar(value="0x80")
        self.var_kwp_target = tk.StringVar(value="0x12")
        self.var_kwp_source = tk.StringVar(value="0xF1")

        self.kwp_fields_frame = ttk.Frame(protocol_group)
        self.kwp_fields_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        protocol_group.columnconfigure(0, weight=1)
        
        # Format byte
        row_kwp_format = ttk.Frame(self.kwp_fields_frame)
        row_kwp_format.grid(row=0, column=0, sticky="ew", pady=4)
        row_kwp_format.columnconfigure(1, weight=1)
        ttk.Label(row_kwp_format, text="⚙  Format byte (hex)").grid(row=0, column=0, sticky="w")
        self.ent_kwp_format = ttk.Entry(row_kwp_format, textvariable=self.var_kwp_format, width=18)
        self.ent_kwp_format.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        # Target address
        row_kwp_target = ttk.Frame(self.kwp_fields_frame)
        row_kwp_target.grid(row=1, column=0, sticky="ew", pady=4)
        row_kwp_target.columnconfigure(1, weight=1)
        ttk.Label(row_kwp_target, text="⚙  Target address (hex)").grid(row=0, column=0, sticky="w")
        self.ent_kwp_target = ttk.Entry(row_kwp_target, textvariable=self.var_kwp_target, width=18)
        self.ent_kwp_target.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        # Source address
        row_kwp_source = ttk.Frame(self.kwp_fields_frame)
        row_kwp_source.grid(row=2, column=0, sticky="ew", pady=4)
        row_kwp_source.columnconfigure(1, weight=1)
        ttk.Label(row_kwp_source, text="⚙  Source address (hex)").grid(row=0, column=0, sticky="w")
        self.ent_kwp_source = ttk.Entry(row_kwp_source, textvariable=self.var_kwp_source, width=18)
        self.ent_kwp_source.grid(row=0, column=1, sticky="w", padx=(10, 0))

        # -------- Options panel
        opt_group = ttk.Labelframe(left, text="Options")
        opt_group.pack(fill="x", pady=(0, 12))

        self.var_split = tk.BooleanVar(value=True)
        self.var_out_dir = tk.StringVar(value=str(Path.cwd() / "output_segments"))
        self.var_out_prefix = tk.StringVar(value="block")
        self.var_cont_counter = tk.BooleanVar(value=False)

        self.var_bin_start = tk.StringVar(value="0x0")
        self.var_fill = tk.StringVar(value="0xFF")
        self.var_fill_gaps = tk.BooleanVar(value=False)
        self.var_validate_srec = tk.BooleanVar(value=False)

        # Split block
        row = ttk.Frame(opt_group)
        row.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        row.columnconfigure(1, weight=1)
        ttk.Checkbutton(row, text="Split by address ranges (one file per contiguous block)", variable=self.var_split, command=self._sync_enabled).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        self._row_dirpicker(opt_group, 1, "Output directory", self.var_out_dir, self._pick_out_dir, icon="📁")
        self._row_entry(opt_group, 2, "Filename prefix", self.var_out_prefix, width=20)

        row = ttk.Frame(opt_group)
        row.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        ttk.Checkbutton(row, text="Continuous counter across blocks", variable=self.var_cont_counter).pack(side="left")

        # -------- Address Range Filter panel
        filter_group = ttk.Labelframe(left, text="Address Range Filter")
        filter_group.pack(fill="both", expand=True, pady=(0, 12))
        
        self.var_use_filter = tk.BooleanVar(value=False)
        self.address_ranges: List[Tuple[tk.StringVar, tk.StringVar, ttk.Frame]] = []
        
        row_filter = ttk.Frame(filter_group)
        row_filter.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        ttk.Checkbutton(row_filter, text="Filter by address ranges (only process data within specified ranges)", 
                       variable=self.var_use_filter, command=self._sync_filter_enabled).pack(side="left")
        
        # Container for address range entries
        self.filter_container = ttk.Frame(filter_group)
        self.filter_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        filter_group.columnconfigure(0, weight=1)
        filter_group.rowconfigure(1, weight=1)
        
        # Scrollable frame for address ranges
        filter_canvas = tk.Canvas(self.filter_container, bg=self.c_panel, highlightthickness=0)
        filter_scrollbar = ttk.Scrollbar(self.filter_container, orient="vertical", command=filter_canvas.yview)
        self.filter_scroll_frame = ttk.Frame(filter_canvas)
        
        filter_canvas.configure(yscrollcommand=filter_scrollbar.set)
        filter_canvas.create_window((0, 0), window=self.filter_scroll_frame, anchor="nw")
        
        def configure_scroll_region(event):
            filter_canvas.configure(scrollregion=filter_canvas.bbox("all"))
        
        self.filter_scroll_frame.bind("<Configure>", configure_scroll_region)
        
        filter_canvas.pack(side="left", fill="both", expand=True)
        filter_scrollbar.pack(side="right", fill="y")
        
        # Buttons for managing ranges
        btn_frame = ttk.Frame(filter_group)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        ttk.Button(btn_frame, text="+ Add Range", style="Ghost.TButton", command=self._add_address_range).pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Clear All", style="Ghost.TButton", command=self._clear_address_ranges).pack(side="left")
        
        # Add one initial range entry
        self._add_address_range()

        # -------- Frame Format panel
        frame_group = ttk.Labelframe(left, text="Frame Format")
        frame_group.pack(fill="x", pady=(0, 12))

        self.var_max_line_len = tk.StringVar(value="0xE0")
        self.var_sid = tk.StringVar(value="0x36")
        self.var_use_counter = tk.BooleanVar(value=True)
        self.var_counter_start = tk.StringVar(value="1")
        self.var_crc_type = tk.StringVar(value="(none)")
        self.var_crc_reverse = tk.BooleanVar(value=False)
        self.var_use_checksum = tk.BooleanVar(value=False)

        self._row_entry(frame_group, 0, "Max line length (hex)", self.var_max_line_len, width=22)
        self._row_entry(frame_group, 1, "Service ID (SID, hex)", self.var_sid, width=22)
        
        row = ttk.Frame(frame_group)
        row.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        ttk.Checkbutton(row, text="Include counter byte", variable=self.var_use_counter, command=self._sync_counter_enabled).pack(side="left")
        
        # Counter start entry (store reference for enabling/disabling)
        row_counter = ttk.Frame(frame_group)
        row_counter.grid(row=3, column=0, sticky="ew", padx=12, pady=6)
        row_counter.columnconfigure(1, weight=1)
        ttk.Label(row_counter, text="🔢  Counter start value").grid(row=0, column=0, sticky="w")
        self.ent_counter_start = ttk.Entry(row_counter, textvariable=self.var_counter_start, width=22)
        self.ent_counter_start.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        row = ttk.Frame(frame_group)
        row.grid(row=4, column=0, sticky="ew", padx=12, pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="🔐  CRC type").grid(row=0, column=0, sticky="w")
        self.cbo_crc = ttk.Combobox(
            row,
            textvariable=self.var_crc_type,
            values=["(none)", "CRC8", "CRC16", "CRC32"],
            state="readonly",
            width=18,
        )
        self.cbo_crc.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        row_crc_reverse = ttk.Frame(frame_group)
        row_crc_reverse.grid(row=5, column=0, sticky="ew", padx=12, pady=6)
        ttk.Checkbutton(row_crc_reverse, text="CRC byte rotation (reverse byte order)", variable=self.var_crc_reverse).pack(side="left")
        
        row_checksum = ttk.Frame(frame_group)
        row_checksum.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 8))
        ttk.Checkbutton(row_checksum, text="Add checksum byte at end of frame", variable=self.var_use_checksum).pack(side="left")

        # BIN + fill
        adv = ttk.Labelframe(left, text="Advanced")
        adv.pack(fill="x")
        self._row_entry(adv, 0, "BIN start address", self.var_bin_start, width=22)
        self._row_entry(adv, 1, "Fill byte (hex)", self.var_fill, width=22)
        row = ttk.Frame(adv)
        row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        ttk.Checkbutton(row, text="Fill address gaps (instead of skipping)", variable=self.var_fill_gaps).pack(side="left")
        ttk.Checkbutton(row, text="Validate S-record checksums (slower)", variable=self.var_validate_srec).pack(side="left", padx=16)

        # -------- Run panel (right)
        right_inner = ttk.Frame(right, style="Panel.TFrame")
        right_inner.pack(fill="both", expand=True, padx=14, pady=14)

        ttk.Label(right_inner, text="Run", style="Panel.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            right_inner,
            text="Pick a file, set options, then convert.\nOutput uses CRLF and your exact frame format.",
            style="Panel.TLabel",
            foreground=self.c_muted,
        ).pack(anchor="w", pady=(6, 12))

        btns = ttk.Frame(right_inner, style="Panel.TFrame")
        btns.pack(fill="x", pady=(0, 10))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        self.btn_run = ttk.Button(btns, text="Convert  ▶", style="Accent.TButton", command=self._on_run)
        self.btn_run.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.btn_stop = ttk.Button(btns, text="Stop  ■", style="Ghost.TButton", command=self._on_stop, state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="ew")

        ttk.Label(right_inner, text="Log", style="Panel.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(6, 4))

        self.txt = tk.Text(
            right_inner,
            height=18,
            bg="#0A1326",
            fg=self.c_text,
            insertbackground=self.c_text,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        self.txt.pack(fill="both", expand=True)

        self._log("Ready. Choose an input file to begin.", level="info")
        self._sync_enabled()
        self._sync_counter_enabled()
        self._sync_protocol_fields()

    def _row_filepicker(self, parent: ttk.Labelframe, r: int, label: str, var: tk.StringVar, cmd, *, icon: str) -> None:
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", padx=12, pady=(10 if r == 0 else 6, 6))
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=f"{icon}  {label}").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(row, textvariable=var)
        ent.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Button(row, text="Browse…", style="Ghost.TButton", command=cmd).grid(row=0, column=2, sticky="e")

    def _row_dirpicker(self, parent: ttk.Labelframe, r: int, label: str, var: tk.StringVar, cmd, *, icon: str) -> None:
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", padx=12, pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=f"{icon}  {label}").grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(row, textvariable=var)
        ent.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        self.btn_dir = ttk.Button(row, text="Browse…", style="Ghost.TButton", command=cmd)
        self.btn_dir.grid(row=0, column=2, sticky="e")

    def _row_type(self, parent: ttk.Labelframe, r: int) -> None:
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", padx=12, pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="🧩  Input type").grid(row=0, column=0, sticky="w")
        self.cbo = ttk.Combobox(
            row,
            textvariable=self.var_type,
            values=["(auto)", "s19", "s28", "s37", "hex", "bin"],
            state="readonly",
        )
        self.cbo.grid(row=0, column=1, sticky="w", padx=(10, 0))

    def _row_entry(self, parent: ttk.Labelframe, r: int, label: str, var: tk.StringVar, *, width: int = 30) -> None:
        row = ttk.Frame(parent)
        row.grid(row=r, column=0, sticky="ew", padx=12, pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=f"⚙  {label}").grid(row=0, column=0, sticky="w")
        ttk.Entry(row, textvariable=var, width=width).grid(row=0, column=1, sticky="w", padx=(10, 0))

    # ------------------ Actions ------------------
    def _pick_input(self) -> None:
        p = filedialog.askopenfilename(
            title="Select input firmware file",
            filetypes=[
                ("Firmware", "*.s19 *.s28 *.s37 *.hex *.bin"),
                ("S19", "*.s19"),
                ("S28", "*.s28"),
                ("S37", "*.s37"),
                ("HEX", "*.hex"),
                ("BIN", "*.bin"),
                ("All files", "*.*"),
            ],
        )
        if p:
            self.var_input.set(p)
            # Suggest output
            out = Path(p).with_suffix(".txt")
            self.var_out.set(str(out))

    def _pick_output(self) -> None:
        p = filedialog.asksaveasfilename(
            title="Select output text file",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if p:
            self.var_out.set(p)

    def _pick_out_dir(self) -> None:
        p = filedialog.askdirectory(title="Select output directory")
        if p:
            self.var_out_dir.set(p)

    def _sync_enabled(self) -> None:
        split = bool(self.var_split.get())
        state = "normal" if split else "disabled"
        try:
            self.btn_dir.configure(state=state)
        except Exception:
            pass
        self.cbo.configure(state="readonly")
    
    def _sync_counter_enabled(self) -> None:
        use_counter = bool(self.var_use_counter.get())
        state = "normal" if use_counter else "disabled"
        try:
            self.ent_counter_start.configure(state=state)
        except Exception:
            pass
    
    def _sync_filter_enabled(self) -> None:
        use_filter = bool(self.var_use_filter.get())
        state = "normal" if use_filter else "disabled"
        for start_var, end_var, row_frame in self.address_ranges:
            try:
                for widget in row_frame.winfo_children():
                    if isinstance(widget, (ttk.Entry, ttk.Button)):
                        widget.configure(state=state)
            except Exception:
                pass
    
    def _sync_protocol_fields(self) -> None:
        """Show/hide and enable/disable KWP-specific fields based on protocol selection."""
        is_kwp = self.var_protocol.get() == "kwp"
        state = "normal" if is_kwp else "disabled"
        try:
            self.ent_kwp_format.configure(state=state)
            self.ent_kwp_target.configure(state=state)
            self.ent_kwp_source.configure(state=state)
        except Exception:
            pass
    
    def _add_address_range(self) -> None:
        """Add a new address range entry row."""
        start_var = tk.StringVar(value="0x0")
        end_var = tk.StringVar(value="0xFFFF")
        
        row = ttk.Frame(self.filter_scroll_frame)
        row.pack(fill="x", pady=2, padx=4)
        
        ttk.Label(row, text="Start:").pack(side="left", padx=(0, 4))
        ent_start = ttk.Entry(row, textvariable=start_var, width=18)
        ent_start.pack(side="left", padx=(0, 8))
        
        ttk.Label(row, text="End:").pack(side="left", padx=(0, 4))
        ent_end = ttk.Entry(row, textvariable=end_var, width=18)
        ent_end.pack(side="left", padx=(0, 8))
        
        btn_remove = ttk.Button(row, text="✕", style="Ghost.TButton", width=3,
                               command=lambda: self._remove_address_range(start_var, end_var, row))
        btn_remove.pack(side="left")
        
        self.address_ranges.append((start_var, end_var, row))
        
        if not self.var_use_filter.get():
            ent_start.configure(state="disabled")
            ent_end.configure(state="disabled")
            btn_remove.configure(state="disabled")
    
    def _remove_address_range(self, start_var: tk.StringVar, end_var: tk.StringVar, row_frame: ttk.Frame) -> None:
        """Remove an address range entry."""
        try:
            self.address_ranges = [(s, e, r) for s, e, r in self.address_ranges if (s, e, r) != (start_var, end_var, row_frame)]
            row_frame.destroy()
        except tk.TclError:
            pass
    
    def _clear_address_ranges(self, add_default: bool = True) -> None:
        """Clear all address range entries and optionally add one default."""
        for start_var, end_var, row_frame in self.address_ranges:
            try:
                row_frame.destroy()
            except tk.TclError:
                pass
        self.address_ranges.clear()
        if add_default:
            self._add_address_range()
    
    def _parse_address_ranges(self) -> List[Tuple[int, int]]:
        """Parse address ranges from GUI variables."""
        ranges: List[Tuple[int, int]] = []
        for start_var, end_var, row_frame in self.address_ranges:
            try:
                start_str = start_var.get().strip()
                end_str = end_var.get().strip()
                if start_str and end_str:
                    start = int(start_str, 0)  # Supports hex (0x) and decimal
                    end = int(end_str, 0)
                    if start <= end:
                        ranges.append((start, end))
            except (ValueError, AttributeError):
                continue
        return ranges

    def _on_stop(self) -> None:
        self._stop_flag.set()
        self._log("Stop requested…", level="warn")

    def _on_run(self) -> None:
        if self._worker and self._worker.is_alive():
            return

        in_path = self.var_input.get().strip()
        if not in_path:
            messagebox.showerror("Missing input", "Please select an input file.")
            return

        self._stop_flag.clear()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    def _run_worker(self) -> None:
        try:
            # Import here so CLI users don't pay tkinter cost and to avoid cycles.
            import converter as core

            in_path = Path(self.var_input.get().strip())
            ftype = self.var_type.get().strip()
            if ftype == "(auto)":
                ftype = core.infer_type_from_suffix(in_path)

            # Parse protocol selection
            protocol_str = self.var_protocol.get().strip()
            protocol = core.ProtocolType.CAN if protocol_str == "can" else core.ProtocolType.KWP

            # Parse frame format options
            max_line_len = int(self.var_max_line_len.get().strip(), 0) & 0xFFFF
            sid = int(self.var_sid.get().strip(), 0) & 0xFF
            use_counter = bool(self.var_use_counter.get())
            counter_start = int(self.var_counter_start.get().strip(), 0) & 0xFF
            crc_type_str = self.var_crc_type.get().strip()
            crc_type = None if crc_type_str == "(none)" else crc_type_str
            crc_bytes = 0
            if crc_type == "CRC8":
                crc_bytes = 1
            elif crc_type == "CRC16":
                crc_bytes = 2
            elif crc_type == "CRC32":
                crc_bytes = 4

            # Parse KWP-specific fields
            kwp_format_byte = int(self.var_kwp_format.get().strip(), 0) & 0xFF if protocol == core.ProtocolType.KWP else 0x80
            kwp_target = int(self.var_kwp_target.get().strip(), 0) & 0xFF if protocol == core.ProtocolType.KWP else 0x12
            kwp_source = int(self.var_kwp_source.get().strip(), 0) & 0xFF if protocol == core.ProtocolType.KWP else 0xF1

            fmt = core.OutputFormat(
                protocol=protocol,
                max_line_len=max_line_len,
                service_byte=sid,
                use_counter=use_counter,
                counter_start=counter_start,
                crc_type=crc_type,
                crc_bytes=crc_bytes,
                crc_reverse_bytes=bool(self.var_crc_reverse.get()),
                use_checksum=bool(self.var_use_checksum.get()),
                kwp_format_byte=kwp_format_byte,
                kwp_target_addr=kwp_target,
                kwp_source_addr=kwp_source,
            )

            self._log(f"Input: {in_path}", level="info")
            self._log(f"Type: {ftype}", level="info")
            protocol_name = "KWP2000" if protocol == core.ProtocolType.KWP else "CAN"
            self._log(f"Protocol: {protocol_name}", level="info")
            checksum_info = "yes" if self.var_use_checksum.get() else "no"
            if protocol == core.ProtocolType.KWP:
                self._log(f"KWP: Format=0x{kwp_format_byte:02X}, Target=0x{kwp_target:02X}, Source=0x{kwp_source:02X}", level="info")
            self._log(f"Max line len: 0x{max_line_len:X}, SID: 0x{sid:02X}, Counter: {use_counter}, Start: {counter_start}, CRC: {crc_type or 'none'}, Checksum: {checksum_info}", level="info")

            if ftype in {"s19", "s28", "s37"}:
                mem = core.parse_srecord_to_mem(in_path, validate_checksum=bool(self.var_validate_srec.get()))
            elif ftype == "hex":
                mem = core.parse_hex_to_mem(in_path)
            elif ftype == "bin":
                mem = core.parse_bin_to_mem(in_path, start_addr=int(self.var_bin_start.get(), 0))
            else:
                raise ValueError(f"Unsupported type: {ftype}")

            # Parse address ranges if enabled
            parsed_ranges = None
            if self.var_use_filter.get():
                parsed_ranges = self._parse_address_ranges()
                if parsed_ranges:
                    # Only filter if NOT splitting by address (when splitting, we'll use ranges directly)
                    if not self.var_split.get():
                        original_size = len(mem)
                        mem = core.filter_mem_by_ranges(mem, parsed_ranges)
                        filtered_size = len(mem)
                        self._log(f"Filtered: {original_size} → {filtered_size} addresses", level="info")
                        if filtered_size == 0:
                            raise ValueError("No data found in specified address ranges")
                else:
                    self._log("Warning: Address filter enabled but no valid ranges specified", level="warn")

            fill = int(self.var_fill.get(), 0) & 0xFF
            fill_gaps = bool(self.var_fill_gaps.get())

            if self.var_split.get():
                out_dir = Path(self.var_out_dir.get().strip())
                out_dir.mkdir(parents=True, exist_ok=True)
                prefix = self.var_out_prefix.get().strip() or "seg"
                
                # If address ranges are specified, create one segment per range (no merging)
                if parsed_ranges:
                    segments = core.mem_to_segments_by_ranges(mem, parsed_ranges, fill=fill, fill_gaps=fill_gaps)
                else:
                    # No ranges specified, use normal contiguous block splitting
                    segments = core.mem_to_segments(mem, fill=fill, fill_gaps=fill_gaps)
                
                self._log(f"Segments: {len(segments)}", level="good")

                next_counter = fmt.counter_start
                for idx, (start, end, seg_bytes) in enumerate(segments, start=1):
                    if self._stop_flag.is_set():
                        raise RuntimeError("Stopped by user.")

                    cstart = next_counter if self.var_cont_counter.get() else fmt.counter_start
                    frames = core.format_frames(seg_bytes, fmt, counter_start=cstart)
                    out_path = out_dir / f"{prefix}_{idx:03d}_0x{start:08X}_0x{end:08X}.txt"
                    core.write_frames(frames, out_path)
                    self._log(f"✔ Wrote {out_path.name}", level="good")

                    if self.var_cont_counter.get():
                        next_counter = (cstart + core.frame_count_for_data_len(len(seg_bytes), fmt)) & 0xFF

                self._log("Done.", level="good")
            else:
                out_path = Path(self.var_out.get().strip())
                data = core.mem_to_bytes(mem, fill=fill, fill_gaps=fill_gaps)
                frames = core.format_frames(data, fmt)
                core.write_frames(frames, out_path)
                self._log(f"✔ Wrote {out_path}", level="good")

        except Exception as e:
            self._log(f"Error: {e}", level="bad")
            self.after(0, lambda: messagebox.showerror("Conversion failed", str(e)))
        finally:
            self.after(0, self._on_done)

    def _on_done(self) -> None:
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    # ------------------ Config Management ------------------
    def _refresh_config_list(self) -> None:
        """Refresh the config dropdown with available configs."""
        configs = self.config_manager.list_configs()
        self.cbo_config['values'] = configs
        if configs:
            self.cbo_config.current(0)
        else:
            self.var_config_name.set("")
    
    def _on_config_selected(self) -> None:
        """Called when user selects a config from dropdown (doesn't load yet)."""
        pass  # Just selection, loading happens on Load button
    
    def _load_config(self) -> None:
        """Load selected config and populate GUI fields."""
        name = self.var_config_name.get().strip()
        if not name:
            messagebox.showwarning("No config selected", "Please select a config from the dropdown.")
            return
        
        config = self.config_manager.load_config(name)
        if config is None:
            messagebox.showerror("Config not found", f"Config '{name}' could not be loaded.")
            self._refresh_config_list()
            return
        
        # Populate GUI fields from config
        self._config_to_gui(config)
        self._log(f"✓ Loaded config: {name}", level="good")
    
    def _save_config(self) -> None:
        """Save current GUI state as a config."""
        # Get config name
        current_name = self.var_config_name.get().strip()
        if current_name and self.config_manager.config_exists(current_name):
            # Update existing config
            name = current_name
            msg = f"Update existing config '{name}'?"
        else:
            # New config - ask for name
            name = simpledialog.askstring("Save Config", "Enter config name:", initialvalue=current_name)
            if not name or not name.strip():
                return
            name = name.strip()
            if self.config_manager.config_exists(name):
                if not messagebox.askyesno("Config exists", f"Config '{name}' already exists. Overwrite?"):
                    return
        
        # Create config from current GUI state
        config = self._gui_to_config(name)
        
        # Save config
        if self.config_manager.save_config(config):
            self._log(f"✓ Saved config: {name}", level="good")
            self._refresh_config_list()
            # Select the saved config
            self.var_config_name.set(name)
        else:
            messagebox.showerror("Save failed", f"Failed to save config '{name}'.")
    
    def _delete_config(self) -> None:
        """Delete selected config."""
        name = self.var_config_name.get().strip()
        if not name:
            messagebox.showwarning("No config selected", "Please select a config to delete.")
            return
        
        if not messagebox.askyesno("Delete Config", f"Are you sure you want to delete config '{name}'?"):
            return
        
        if self.config_manager.delete_config(name):
            self._log(f"✓ Deleted config: {name}", level="info")
            self._refresh_config_list()
        else:
            messagebox.showerror("Delete failed", f"Failed to delete config '{name}'.")
    
    def _gui_to_config(self, name: str) -> ConversionConfig:
        """Convert current GUI state to ConversionConfig."""
        # Collect address ranges
        address_ranges = []
        if self.var_use_filter.get():
            for start_var, end_var, row_frame in self.address_ranges:
                start_str = start_var.get().strip()
                end_str = end_var.get().strip()
                if start_str and end_str:
                    address_ranges.append((start_str, end_str))
        
        # Get output directory - don't store absolute paths (user-specific)
        # Only store relative paths or empty string
        out_dir = self.var_out_dir.get().strip()
        try:
            out_dir_path = Path(out_dir)
            if out_dir_path.is_absolute():
                # Don't store absolute paths - they're user-specific
                # Use empty string, will default to relative path on load
                out_dir = ""
            else:
                # Store relative path as-is
                out_dir = str(out_dir_path)
        except Exception:
            # If path is invalid, store empty string
            out_dir = ""
        
        return ConversionConfig(
            name=name,
            description="",  # Can be enhanced later
            protocol=self.var_protocol.get().strip(),
            kwp_format=self.var_kwp_format.get().strip(),
            kwp_target=self.var_kwp_target.get().strip(),
            kwp_source=self.var_kwp_source.get().strip(),
            input_type=self.var_type.get().strip(),
            use_filter=self.var_use_filter.get(),
            address_ranges=address_ranges,
            max_line_len=self.var_max_line_len.get().strip(),
            sid=self.var_sid.get().strip(),
            use_counter=self.var_use_counter.get(),
            counter_start=self.var_counter_start.get().strip(),
            crc_type=self.var_crc_type.get().strip(),
            crc_reverse=self.var_crc_reverse.get(),
            use_checksum=self.var_use_checksum.get(),
            split=self.var_split.get(),
            out_dir=out_dir,
            out_prefix=self.var_out_prefix.get().strip(),
            cont_counter=self.var_cont_counter.get(),
            bin_start=self.var_bin_start.get().strip(),
            fill=self.var_fill.get().strip(),
            fill_gaps=self.var_fill_gaps.get(),
            validate_srec=self.var_validate_srec.get(),
        )
    
    def _config_to_gui(self, config: ConversionConfig) -> None:
        """Populate GUI fields from ConversionConfig."""
        # Protocol
        self.var_protocol.set(config.protocol)
        self.var_kwp_format.set(config.kwp_format)
        self.var_kwp_target.set(config.kwp_target)
        self.var_kwp_source.set(config.kwp_source)
        self._sync_protocol_fields()
        
        # Input type
        self.var_type.set(config.input_type)
        
        # Address Range Filter
        self.var_use_filter.set(config.use_filter)
        # Clear existing ranges (don't add default - we'll add from config or leave empty)
        self._clear_address_ranges(add_default=False)
        # Add ranges from config
        if config.address_ranges:
            for start_str, end_str in config.address_ranges:
                self._add_address_range()
                # Set the values in the last added range
                if self.address_ranges:
                    start_var, end_var, _ = self.address_ranges[-1]
                    start_var.set(start_str)
                    end_var.set(end_str)
        # If no ranges in config, leave it empty (don't add default)
        self._sync_filter_enabled()
        
        # Frame Format
        self.var_max_line_len.set(config.max_line_len)
        self.var_sid.set(config.sid)
        self.var_use_counter.set(config.use_counter)
        self.var_counter_start.set(config.counter_start)
        self.var_crc_type.set(config.crc_type)
        self.var_crc_reverse.set(config.crc_reverse)
        self.var_use_checksum.set(config.use_checksum)
        self._sync_counter_enabled()
        
        # Options
        self.var_split.set(config.split)
        # Handle out_dir: if empty or absolute (shouldn't happen but handle it), use default relative path
        out_dir = config.out_dir.strip() if config.out_dir else ""
        if not out_dir or Path(out_dir).is_absolute():
            # Use default relative path
            out_dir = str(Path.cwd() / "output_segments")
        self.var_out_dir.set(out_dir)
        self.var_out_prefix.set(config.out_prefix)
        self.var_cont_counter.set(config.cont_counter)
        self._sync_enabled()
        
        # Advanced
        self.var_bin_start.set(config.bin_start)
        self.var_fill.set(config.fill)
        self.var_fill_gaps.set(config.fill_gaps)
        self.var_validate_srec.set(config.validate_srec)

    # ------------------ API Sync ------------------
    def _check_api_status(self) -> None:
        """Check API status in background and update UI."""
        def check():
            if self.api_client:
                try:
                    is_online = self.api_client.test_connection()
                    status = "✓ Online" if is_online else "⚠ Offline"
                    self.after(0, lambda: self.var_api_status.set(f"Status: {status}"))
                except Exception:
                    self.after(0, lambda: self.var_api_status.set("Status: ⚠ Offline"))
            else:
                self.after(0, lambda: self.var_api_status.set("Status: ⚠ Offline (No API configured)"))
        
        # Run in background thread
        threading.Thread(target=check, daemon=True).start()
    
    def _download_configs(self) -> None:
        """Download all configs from API."""
        if not self.config_sync or not self.api_client:
            messagebox.showwarning(
                "Offline Mode", 
                "API client is not configured. Cannot download configs.\n\n"
                "The app works fully offline - you can still save and load local configs."
            )
            return
        
        # Disable button during download
        self.btn_download.configure(state="disabled")
        self.var_api_status.set("Status: Downloading...")
        self._log("Downloading configs from server...", level="info")
        
        def download_worker():
            try:
                downloaded, errors = self.config_sync.download_all_configs()
                self.after(0, lambda: self._on_download_complete(downloaded, errors))
            except APIError as e:
                self.after(0, lambda: self._on_download_error(str(e)))
            except Exception as e:
                self.after(0, lambda: self._on_download_error(f"Unexpected error: {e}"))
        
        self._api_worker = threading.Thread(target=download_worker, daemon=True)
        self._api_worker.start()
    
    def _on_download_complete(self, downloaded: int, errors: int) -> None:
        """Called when download completes."""
        self.btn_download.configure(state="normal")
        self._check_api_status()
        self._refresh_config_list()
        
        if downloaded > 0:
            self._log(f"✓ Downloaded {downloaded} config(s) from server", level="good")
        if errors > 0:
            self._log(f"⚠ {errors} config(s) had errors during download", level="warn")
        if downloaded == 0 and errors == 0:
            self._log("No configs available on server", level="info")
    
    def _on_download_error(self, error_msg: str) -> None:
        """Called when download fails."""
        self.btn_download.configure(state="normal")
        self._check_api_status()
        self._log(f"✗ Download failed: {error_msg}", level="bad")
        messagebox.showerror("Download Failed", f"Failed to download configs:\n\n{error_msg}")
    
    def _upload_current_config(self) -> None:
        """Upload current GUI state as config to API."""
        if not self.config_sync or not self.api_client:
            messagebox.showwarning(
                "Offline Mode", 
                "API client is not configured. Cannot upload configs.\n\n"
                "Save the config locally first, then upload when online."
            )
            return
        
        # Get current config name or ask for one
        current_name = self.var_config_name.get().strip()
        if not current_name:
            # Ask user to save locally first or provide a name
            name = simpledialog.askstring("Upload Config", "Enter config name to upload:", initialvalue="")
            if not name or not name.strip():
                return
            current_name = name.strip()
            # Save locally first
            config = self._gui_to_config(current_name)
            if not self.config_manager.save_config(config):
                messagebox.showerror("Save Failed", "Failed to save config locally before upload.")
                return
        
        # Disable button during upload
        self.btn_upload.configure(state="disabled")
        self.var_api_status.set("Status: Uploading...")
        self._log(f"Uploading config '{current_name}' to server...", level="info")
        
        def upload_worker():
            try:
                response = self.config_sync.upload_config(current_name)
                self.after(0, lambda: self._on_upload_complete(current_name, response))
            except APIError as e:
                self.after(0, lambda: self._on_upload_error(current_name, str(e)))
            except Exception as e:
                self.after(0, lambda: self._on_upload_error(current_name, f"Unexpected error: {e}"))
        
        self._api_worker = threading.Thread(target=upload_worker, daemon=True)
        self._api_worker.start()
    
    def _on_upload_complete(self, config_name: str, response: Dict) -> None:
        """Called when upload completes."""
        self.btn_upload.configure(state="normal")
        self._check_api_status()
        self._refresh_config_list()
        
        remote_id = response.get('id', 'N/A')
        self._log(f"✓ Uploaded config '{config_name}' to server (ID: {remote_id})", level="good")
        messagebox.showinfo("Upload Successful", f"Config '{config_name}' uploaded successfully!")
    
    def _on_upload_error(self, config_name: str, error_msg: str) -> None:
        """Called when upload fails."""
        self.btn_upload.configure(state="normal")
        self._check_api_status()
        self._log(f"✗ Upload failed for '{config_name}': {error_msg}", level="bad")
        messagebox.showerror("Upload Failed", f"Failed to upload config '{config_name}':\n\n{error_msg}")

    # ------------------ Log ------------------
    def _log(self, msg: str, *, level: str = "info") -> None:
        color = {
            "info": self.c_text,
            "good": self.c_good,
            "warn": self.c_warn,
            "bad": self.c_bad,
        }.get(level, self.c_text)

        def write():
            self.txt.insert("end", msg + "\n")
            self.txt.tag_add(level, "end-2l", "end-1l")
            self.txt.tag_config(level, foreground=color)
            self.txt.see("end")

        self.after(0, write)


def run_gui() -> None:
    app = ConverterGui()
    app.mainloop()

