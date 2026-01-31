import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple


@dataclass
class GuiConfig:
    app_title: str = "Firmware Converter"


class ConverterGui(tk.Tk):
    def __init__(self, cfg: Optional[GuiConfig] = None):
        super().__init__()
        self.cfg = cfg or GuiConfig()

        self.title(self.cfg.app_title)
        self.geometry("860x600")
        self.minsize(820, 520)

        self._init_theme()
        self._build_ui()

        self._worker: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

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

        # -------- Input/Output panel
        io_group = ttk.Labelframe(left, text="Input / Output")
        io_group.pack(fill="x", pady=(0, 12))

        self.var_input = tk.StringVar(value="")
        self.var_type = tk.StringVar(value="(auto)")
        self.var_out = tk.StringVar(value=str(Path.cwd() / "output_can.txt"))

        self._row_filepicker(io_group, 0, "Input file", self.var_input, self._pick_input, icon="📄")
        self._row_type(io_group, 1)
        self._row_filepicker(io_group, 2, "Output file", self.var_out, self._pick_output, icon="💾")

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
    
    def _clear_address_ranges(self) -> None:
        """Clear all address range entries and add one default."""
        for start_var, end_var, row_frame in self.address_ranges:
            try:
                row_frame.destroy()
            except tk.TclError:
                pass
        self.address_ranges.clear()
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

            fmt = core.OutputFormat(
                max_line_len=max_line_len,
                service_byte=sid,
                use_counter=use_counter,
                counter_start=counter_start,
                crc_type=crc_type,
                crc_bytes=crc_bytes,
                crc_reverse_bytes=bool(self.var_crc_reverse.get()),
                use_checksum=bool(self.var_use_checksum.get()),
            )

            self._log(f"Input: {in_path}", level="info")
            self._log(f"Type: {ftype}", level="info")
            checksum_info = "yes" if self.var_use_checksum.get() else "no"
            self._log(f"Max line len: 0x{max_line_len:X}, SID: 0x{sid:02X}, Counter: {use_counter}, Start: {counter_start}, CRC: {crc_type or 'none'}, Checksum: {checksum_info}", level="info")

            if ftype in {"s19", "s28", "s37"}:
                mem = core.parse_srecord_to_mem(in_path, validate_checksum=bool(self.var_validate_srec.get()))
            elif ftype == "hex":
                mem = core.parse_hex_to_mem(in_path)
            elif ftype == "bin":
                mem = core.parse_bin_to_mem(in_path, start_addr=int(self.var_bin_start.get(), 0))
            else:
                raise ValueError(f"Unsupported type: {ftype}")

            # Apply address range filtering if enabled
            if self.var_use_filter.get():
                ranges = self._parse_address_ranges()
                if ranges:
                    original_size = len(mem)
                    mem = core.filter_mem_by_ranges(mem, ranges)
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

