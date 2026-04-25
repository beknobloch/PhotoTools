from __future__ import annotations

import re
import webbrowser
from copy import deepcopy
from pathlib import Path
from tkinter import StringVar, filedialog, messagebox, ttk
import tkinter as tk

from lr2rt.config import load_config
from lr2rt.mapper import MappingEngine
from lr2rt.models import ConversionResult
from lr2rt.parsers import parse_lightroom_file
from lr2rt.pp3_template import merge_pp3_sections, parse_pp3_file
from lr2rt.pp3_writer import write_pp3
from lr2rt.reporting import write_html_preview

SUPPORTED_EXTENSIONS = {".xmp", ".dng"}
_DROP_TOKEN_RE = re.compile(r"\{[^}]*\}|[^\s]+")
_DEFAULT_PREVIEW_PATH = Path.home() / ".lr2rt" / "gui_preview.html"


def parse_drop_paths(drop_data: str) -> list[Path]:
    tokens = _DROP_TOKEN_RE.findall(drop_data.strip())
    paths: list[Path] = []
    for token in tokens:
        normalized = token[1:-1] if token.startswith("{") and token.endswith("}") else token
        normalized = normalized.strip()
        if normalized:
            paths.append(Path(normalized).expanduser().resolve())
    return paths


def is_supported_input(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def build_output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}.pp3"


def build_preview_path() -> Path:
    return _DEFAULT_PREVIEW_PATH


def _apply_base_profile(result: ConversionResult, base_pp3: Path | None, base_pp3_mode: str = "safe") -> ConversionResult:
    if base_pp3 is None:
        return result
    template_path = base_pp3.expanduser().resolve()
    base_sections = parse_pp3_file(template_path)

    if base_pp3_mode == "preserve":
        mapped_overrides: dict[str, dict[str, str]] = {}
        for mapped in result.mapped_values:
            mapped_overrides.setdefault(mapped.section, {})[mapped.key] = mapped.value
        result.pp3_sections = merge_pp3_sections(base_sections, mapped_overrides)
        return result

    merged = deepcopy(base_sections)
    converter_sections = result.pp3_sections
    for section, kv_pairs in converter_sections.items():
        merged[section] = deepcopy(kv_pairs)

    converter_section_names = set(converter_sections.keys())
    for section, kv_pairs in list(merged.items()):
        if section in converter_section_names:
            continue
        if "Enabled" in kv_pairs:
            merged[section] = {"Enabled": "false"}

    result.pp3_sections = merged
    return result


def _run_gui_pipeline(
    input_path: Path,
    profile: str = "balanced",
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str = "safe",
) -> ConversionResult:
    input_path = input_path.expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if not is_supported_input(input_path):
        raise ValueError("Input must be a Lightroom preset (.xmp or .dng).")

    override_path = Path(mapping_file).expanduser().resolve() if mapping_file else None
    config = load_config(override_path)
    namespace = config.get("metadata_namespaces", {}).get("crs", "http://ns.adobe.com/camera-raw-settings/1.0/")
    engine = MappingEngine(config, profile_name=profile)

    settings = parse_lightroom_file(input_path, namespace)
    result = engine.convert(settings)
    return _apply_base_profile(result, base_pp3, base_pp3_mode=base_pp3_mode)


def run_gui_conversion(
    input_path: Path,
    output_dir: Path,
    profile: str = "balanced",
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str = "safe",
) -> tuple[Path, ConversionResult]:
    output_dir = output_dir.expanduser().resolve()
    result = _run_gui_pipeline(
        input_path=input_path,
        profile=profile,
        mapping_file=mapping_file,
        base_pp3=base_pp3,
        base_pp3_mode=base_pp3_mode,
    )

    output_path = build_output_path(input_path, output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_pp3(output_path, result.pp3_sections)
    return output_path, result


def run_gui_preview(
    input_path: Path,
    profile: str = "balanced",
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str = "safe",
    preview_path: Path | None = None,
) -> tuple[Path, ConversionResult]:
    result = _run_gui_pipeline(
        input_path=input_path,
        profile=profile,
        mapping_file=mapping_file,
        base_pp3=base_pp3,
        base_pp3_mode=base_pp3_mode,
    )
    output_path = (preview_path or build_preview_path()).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_html_preview(result, output_path)
    return output_path, result


class ConverterWindow:
    def __init__(
        self,
        root: tk.Tk,
        dnd_available: bool,
        available_profiles: list[str],
        profile: str,
        mapping_file: str | None,
        base_pp3: Path | None,
        base_pp3_mode: str,
    ) -> None:
        self.root = root
        self.dnd_available = dnd_available
        self.available_profiles = available_profiles
        self.profile_var = StringVar(value=profile)
        self.mapping_file = mapping_file
        self.base_pp3 = base_pp3
        self.base_pp3_mode = base_pp3_mode
        self.input_var = StringVar(value="")
        self.output_dir_var = StringVar(value=str(Path.home() / "Downloads"))
        self.status_var = StringVar(value="Drop a preset or click Browse, then preview or convert.")

        self.root.title("lr2rt Converter")
        self.root.geometry("860x520")
        self.root.minsize(820, 480)
        self._configure_style()
        self._build()

    def _configure_style(self) -> None:
        self.root.configure(background="#090a0c")
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("App.TFrame", background="#090a0c")
        style.configure(
            "Card.TFrame",
            background="#171a20",
            borderwidth=1,
            relief="solid",
            bordercolor="#3b3225",
        )
        style.configure("ActionRow.TFrame", background="#171a20", borderwidth=0, relief="flat")
        style.configure("Title.TLabel", background="#171a20", foreground="#f5efe2", font=("Times", 19, "bold"))
        style.configure("Subtitle.TLabel", background="#171a20", foreground="#b2ab9e", font=("Times", 11))
        style.configure("Field.TLabel", background="#171a20", foreground="#d7cfbf", font=("TkDefaultFont", 10, "bold"))
        style.configure("Hint.TLabel", background="#171a20", foreground="#9f9789", font=("TkDefaultFont", 9))
        style.configure(
            "Status.TLabel",
            background="#111318",
            foreground="#e6dfd2",
            font=("TkDefaultFont", 10),
            padding=(10, 8),
        )

        style.configure(
            "Input.TEntry",
            fieldbackground="#12151a",
            foreground="#f3ecdd",
            bordercolor="#3b3225",
            insertcolor="#f3ecdd",
            padding=(8, 6),
        )
        style.map(
            "Input.TEntry",
            fieldbackground=[("focus", "#181c23")],
            bordercolor=[("focus", "#d3b173")],
        )

        style.configure(
            "Input.TCombobox",
            fieldbackground="#12151a",
            foreground="#f3ecdd",
            bordercolor="#3b3225",
            arrowcolor="#d3b173",
            padding=(8, 6),
        )
        style.map(
            "Input.TCombobox",
            fieldbackground=[("readonly", "#12151a"), ("focus", "#181c23")],
            bordercolor=[("focus", "#d3b173")],
        )

        style.configure(
            "Utility.TButton",
            background="#21262f",
            foreground="#ece3d2",
            bordercolor="#4a4030",
            lightcolor="#21262f",
            darkcolor="#21262f",
            focuscolor="#21262f",
            padding=(12, 8),
            relief="flat",
        )
        style.map(
            "Utility.TButton",
            background=[("active", "#2a313c"), ("pressed", "#1d232c")],
            foreground=[("disabled", "#7d776d")],
        )
        style.configure(
            "UtilityHover.TButton",
            background="#2f3744",
            foreground="#f6eddd",
            bordercolor="#5a503d",
            lightcolor="#2f3744",
            darkcolor="#2f3744",
            focuscolor="#2f3744",
            padding=(12, 8),
            relief="flat",
        )
        style.map(
            "UtilityHover.TButton",
            background=[("pressed", "#232a33")],
            foreground=[("disabled", "#7d776d")],
        )

        style.configure(
            "Secondary.TButton",
            background="#3b2f1f",
            foreground="#f4e5c9",
            bordercolor="#5a462d",
            lightcolor="#3b2f1f",
            darkcolor="#3b2f1f",
            focuscolor="#3b2f1f",
            padding=(14, 8),
            relief="flat",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#4a3a26"), ("pressed", "#332818")],
            foreground=[("disabled", "#8d7f6b")],
        )
        style.configure(
            "SecondaryHover.TButton",
            background="#5a462d",
            foreground="#fff3dc",
            bordercolor="#7a613f",
            lightcolor="#5a462d",
            darkcolor="#5a462d",
            focuscolor="#5a462d",
            padding=(14, 8),
            relief="flat",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "SecondaryHover.TButton",
            background=[("pressed", "#473720")],
            foreground=[("disabled", "#8d7f6b")],
        )

        style.configure(
            "Primary.TButton",
            background="#d3b173",
            foreground="#090a0c",
            bordercolor="#d3b173",
            lightcolor="#d3b173",
            darkcolor="#d3b173",
            focuscolor="#d3b173",
            padding=(16, 8),
            relief="flat",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#e0c089"), ("pressed", "#be9b5e")],
            foreground=[("disabled", "#3c3b38")],
        )
        style.configure(
            "PrimaryHover.TButton",
            background="#e7cb95",
            foreground="#090a0c",
            bordercolor="#e7cb95",
            lightcolor="#e7cb95",
            darkcolor="#e7cb95",
            focuscolor="#e7cb95",
            padding=(16, 8),
            relief="flat",
            font=("TkDefaultFont", 10, "bold"),
        )
        style.map(
            "PrimaryHover.TButton",
            background=[("pressed", "#c8a86b")],
            foreground=[("disabled", "#3c3b38")],
        )

    def _wire_hover_style(self, button: ttk.Button, normal_style: str, hover_style: str) -> None:
        def on_enter(_event: object) -> None:
            if "disabled" in button.state():
                return
            button.configure(style=hover_style)

        def on_leave(_event: object) -> None:
            button.configure(style=normal_style)

        button.bind("<Enter>", on_enter, add="+")
        button.bind("<Leave>", on_leave, add="+")

    def _build(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=22)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header_card = ttk.Frame(outer, style="Card.TFrame", padding=(16, 14))
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header_card.columnconfigure(0, weight=1)
        ttk.Label(header_card, text="Lightroom Preset to RawTherapee", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        subtitle_text = (
            "Custom mapping loaded. Choose a profile, preview the look, then convert."
            if self.mapping_file
            else "Balanced profile selected. Preview first for a quick visual quality check."
        )
        ttk.Label(header_card, text=subtitle_text, style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        form_card = ttk.Frame(outer, style="Card.TFrame", padding=(16, 14))
        form_card.grid(row=1, column=0, sticky="nsew")
        for idx, weight in enumerate((0, 1, 0)):
            form_card.columnconfigure(idx, weight=weight)
        form_card.rowconfigure(4, weight=1)

        ttk.Label(form_card, text="Profile", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            form_card,
            textvariable=self.profile_var,
            values=self.available_profiles,
            state="readonly",
            style="Input.TCombobox",
        ).grid(row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Label(form_card, text="Translation profile", style="Hint.TLabel").grid(
            row=0, column=2, sticky="e"
        )

        ttk.Label(form_card, text="Preset (.xmp/.dng)", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(form_card, textvariable=self.input_var, style="Input.TEntry").grid(
            row=1, column=1, sticky="ew", padx=(10, 10), pady=(10, 0)
        )
        browse_input_btn = ttk.Button(form_card, text="Browse...", command=self._browse_input, style="Utility.TButton")
        self._wire_hover_style(browse_input_btn, "Utility.TButton", "UtilityHover.TButton")
        browse_input_btn.grid(row=1, column=2, sticky="ew", pady=(10, 0))

        self.drop_target = tk.Label(
            form_card,
            text="Drag and drop a .xmp or .dng file here",
            relief=tk.SOLID,
            borderwidth=1,
            padx=14,
            pady=18,
            anchor="center",
            bg="#101318",
            fg="#d6cdbd",
            highlightthickness=1,
            highlightbackground="#3b3225",
            font=("TkDefaultFont", 10),
        )
        self.drop_target.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 12))
        if self.dnd_available:
            self.drop_target.configure(text="Drag and drop a .xmp or .dng file here")
        else:
            self.drop_target.configure(text="Drag-and-drop unavailable (install tkinterdnd2). Use Browse instead.")

        ttk.Label(form_card, text="Output folder", style="Field.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Entry(form_card, textvariable=self.output_dir_var, style="Input.TEntry").grid(
            row=3, column=1, sticky="ew", padx=(10, 10)
        )
        browse_output_btn = ttk.Button(
            form_card, text="Choose...", command=self._browse_output_dir, style="Utility.TButton"
        )
        self._wire_hover_style(browse_output_btn, "Utility.TButton", "UtilityHover.TButton")
        browse_output_btn.grid(row=3, column=2, sticky="ew")

        action_row = ttk.Frame(form_card, style="ActionRow.TFrame")
        action_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=0)
        action_row.columnconfigure(2, weight=0)
        action_row.columnconfigure(3, weight=1)
        preview_btn = ttk.Button(
            action_row,
            text="Preview HTML",
            width=16,
            command=self._preview,
            style="Secondary.TButton",
        )
        self._wire_hover_style(preview_btn, "Secondary.TButton", "SecondaryHover.TButton")
        preview_btn.grid(row=0, column=1, padx=(0, 10))
        convert_btn = ttk.Button(
            action_row,
            text="Convert Preset",
            width=16,
            command=self._convert,
            style="Primary.TButton",
        )
        self._wire_hover_style(convert_btn, "Primary.TButton", "PrimaryHover.TButton")
        convert_btn.grid(row=0, column=2, padx=(10, 0))

        ttk.Label(form_card, textvariable=self.status_var, wraplength=760, style="Status.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0)
        )

    def bind_drop(self, dnd_files_symbol: object) -> None:
        self.drop_target.drop_target_register(dnd_files_symbol)
        self.drop_target.dnd_bind("<<Drop>>", self._on_drop)

    def _browse_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select Lightroom preset",
            filetypes=[("Lightroom Presets", "*.xmp *.dng"), ("All files", "*.*")],
        )
        if selected:
            self._set_input(Path(selected))

    def _browse_output_dir(self) -> None:
        initial_dir = self.output_dir_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(title="Select output folder", initialdir=initial_dir)
        if selected:
            self.output_dir_var.set(str(Path(selected).expanduser().resolve()))

    def _on_drop(self, event: object) -> None:
        drop_data = getattr(event, "data", "")
        for path in parse_drop_paths(str(drop_data)):
            if path.exists() and is_supported_input(path):
                self._set_input(path)
                return
        self.status_var.set("Dropped file is not a supported .xmp or .dng preset.")

    def _set_input(self, path: Path) -> None:
        if not is_supported_input(path):
            self.status_var.set("Input must be .xmp or .dng.")
            return
        resolved = path.expanduser().resolve()
        self.input_var.set(str(resolved))
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(resolved.parent))
        self.status_var.set("Ready to preview or convert.")

    def _preview(self) -> None:
        input_value = self.input_var.get().strip()
        if not input_value:
            messagebox.showerror("Missing input", "Select a .xmp or .dng file first.")
            return

        input_path = Path(input_value)
        try:
            preview_path, result = run_gui_preview(
                input_path=input_path,
                profile=self.profile_var.get().strip() or "balanced",
                mapping_file=self.mapping_file,
                base_pp3=self.base_pp3,
                base_pp3_mode=self.base_pp3_mode,
            )
            webbrowser.open_new(preview_path.as_uri())
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))
            return

        warning_text = f" | warnings: {len(result.warnings)}" if result.warnings else ""
        self.status_var.set(f"Preview opened: {preview_path}{warning_text}")

    def _convert(self) -> None:
        input_value = self.input_var.get().strip()
        output_value = self.output_dir_var.get().strip()
        if not input_value:
            messagebox.showerror("Missing input", "Select a .xmp or .dng file first.")
            return
        if not output_value:
            messagebox.showerror("Missing output folder", "Choose an output folder.")
            return

        input_path = Path(input_value)
        output_dir = Path(output_value)
        try:
            output_path, result = run_gui_conversion(
                input_path=input_path,
                output_dir=output_dir,
                profile=self.profile_var.get().strip() or "balanced",
                mapping_file=self.mapping_file,
                base_pp3=self.base_pp3,
                base_pp3_mode=self.base_pp3_mode,
            )
        except Exception as exc:
            messagebox.showerror("Conversion failed", str(exc))
            return

        warning_text = f" | warnings: {len(result.warnings)}" if result.warnings else ""
        self.status_var.set(f"Saved {output_path.name} to {output_path.parent}{warning_text}")
        messagebox.showinfo("Conversion complete", f"Created:\n{output_path}")


def launch_gui(
    profile: str = "balanced",
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str = "safe",
) -> None:
    override_path = Path(mapping_file).expanduser().resolve() if mapping_file else None
    config = load_config(override_path)
    available_profiles = list(config.get("profiles", {}).keys())
    if not available_profiles:
        raise ValueError("No mapping profiles found in configuration.")

    selected_profile = "balanced" if "balanced" in available_profiles else available_profiles[0]
    if profile in available_profiles:
        selected_profile = profile

    dnd_available = False
    dnd_files_symbol: object | None = None

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

        root = TkinterDnD.Tk()
        dnd_available = True
        dnd_files_symbol = DND_FILES
    except Exception:
        root = tk.Tk()

    app = ConverterWindow(
        root=root,
        dnd_available=dnd_available,
        available_profiles=available_profiles,
        profile=selected_profile,
        mapping_file=mapping_file,
        base_pp3=base_pp3,
        base_pp3_mode=base_pp3_mode,
    )
    if dnd_available and dnd_files_symbol is not None:
        app.bind_drop(dnd_files_symbol)

    root.mainloop()


def main() -> int:
    launch_gui()
    return 0
