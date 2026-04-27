from __future__ import annotations

import json
import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk

from lr2rt.config import load_config
from lr2rt.mapper import MappingEngine
from lr2rt.models import ConversionResult
from lr2rt.parsers import parse_lightroom_file
from lr2rt.pp3_template import apply_base_profile_mode, parse_pp3_file
from lr2rt.pp3_writer import write_pp3
from lr2rt.quality import StrictEvaluation, evaluate_strict_mode
from lr2rt.reporting import write_html_preview

SUPPORTED_EXTENSIONS = {".xmp", ".dng"}
_DROP_TOKEN_RE = re.compile(r"\{[^}]*\}|[^\s]+")
_DEFAULT_PREVIEW_PATH = Path.home() / ".lr2rt" / "gui_preview.html"
_DEFAULT_GUI_PREFS_PATH = Path.home() / ".lr2rt" / "gui_prefs.json"
_BASE_PP3_MODES = ("safe", "preserve")

STATUS_QUEUED = "Queued"
STATUS_PREVIEWED = "Previewed"
STATUS_CONVERTED = "Converted"
STATUS_CONVERTED_WARN = "Converted (Warnings)"
STATUS_FAILED_STRICT = "Failed (Strict)"
STATUS_ERROR = "Error"


@dataclass(slots=True, frozen=True)
class GuiPreferences:
    input_dir: str
    output_dir: str
    profile: str
    base_pp3: str
    base_pp3_mode: str
    strict: bool


def _default_gui_preferences() -> GuiPreferences:
    home = str(Path.home())
    return GuiPreferences(
        input_dir=home,
        output_dir=str(Path.home() / "Downloads"),
        profile="balanced",
        base_pp3="",
        base_pp3_mode="safe",
        strict=False,
    )


def load_gui_preferences(path: Path | None = None) -> GuiPreferences:
    prefs_path = (path or _DEFAULT_GUI_PREFS_PATH).expanduser().resolve()
    defaults = _default_gui_preferences()
    if not prefs_path.exists():
        return defaults

    try:
        raw = json.loads(prefs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults

    input_dir = str(raw.get("input_dir", defaults.input_dir)).strip() or defaults.input_dir
    output_dir = str(raw.get("output_dir", defaults.output_dir)).strip() or defaults.output_dir
    profile = str(raw.get("profile", defaults.profile)).strip() or defaults.profile
    base_pp3 = str(raw.get("base_pp3", defaults.base_pp3)).strip()
    base_pp3_mode = str(raw.get("base_pp3_mode", defaults.base_pp3_mode)).strip()
    if base_pp3_mode not in _BASE_PP3_MODES:
        base_pp3_mode = defaults.base_pp3_mode
    strict = bool(raw.get("strict", defaults.strict))

    return GuiPreferences(
        input_dir=input_dir,
        output_dir=output_dir,
        profile=profile,
        base_pp3=base_pp3,
        base_pp3_mode=base_pp3_mode,
        strict=strict,
    )


def save_gui_preferences(preferences: GuiPreferences, path: Path | None = None) -> None:
    prefs_path = (path or _DEFAULT_GUI_PREFS_PATH).expanduser().resolve()
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "input_dir": preferences.input_dir,
        "output_dir": preferences.output_dir,
        "profile": preferences.profile,
        "base_pp3": preferences.base_pp3,
        "base_pp3_mode": preferences.base_pp3_mode,
        "strict": preferences.strict,
    }
    prefs_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass(slots=True, frozen=True)
class QueueAddSummary:
    added: int = 0
    skipped_missing: int = 0
    skipped_unsupported: int = 0
    skipped_duplicate: int = 0


@dataclass(slots=True)
class QueueEntry:
    input_path: Path
    status: str = STATUS_QUEUED
    warning_count: int = 0
    output_path: Path | None = None
    message: str = ""


class ConversionQueueModel:
    def __init__(self) -> None:
        self._entries: list[QueueEntry] = []

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[QueueEntry]:
        return self._entries

    def get(self, index: int) -> QueueEntry | None:
        if index < 0 or index >= len(self._entries):
            return None
        return self._entries[index]

    def add_paths(self, paths: list[Path]) -> QueueAddSummary:
        added = skipped_missing = skipped_unsupported = skipped_duplicate = 0

        existing = {entry.input_path for entry in self._entries}
        for raw_path in paths:
            path = raw_path.expanduser().resolve()
            if not path.exists():
                skipped_missing += 1
                continue
            if not is_supported_input(path):
                skipped_unsupported += 1
                continue
            if path in existing:
                skipped_duplicate += 1
                continue

            self._entries.append(QueueEntry(input_path=path))
            existing.add(path)
            added += 1

        return QueueAddSummary(
            added=added,
            skipped_missing=skipped_missing,
            skipped_unsupported=skipped_unsupported,
            skipped_duplicate=skipped_duplicate,
        )

    def remove_indices(self, indices: list[int]) -> int:
        removed = 0
        for idx in sorted(set(indices), reverse=True):
            if idx < 0 or idx >= len(self._entries):
                continue
            del self._entries[idx]
            removed += 1
        return removed

    def clear(self) -> None:
        self._entries.clear()


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
    result.pp3_sections = apply_base_profile_mode(
        base_sections=base_sections,
        converter_sections=result.pp3_sections,
        mapped_values=result.mapped_values,
        base_pp3_mode=base_pp3_mode,
    )
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


def run_gui_conversion_checked(
    input_path: Path,
    output_dir: Path,
    profile: str = "balanced",
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str = "safe",
    strict: bool = False,
) -> tuple[Path | None, ConversionResult, StrictEvaluation]:
    output_dir = output_dir.expanduser().resolve()
    result = _run_gui_pipeline(
        input_path=input_path,
        profile=profile,
        mapping_file=mapping_file,
        base_pp3=base_pp3,
        base_pp3_mode=base_pp3_mode,
    )
    strict_eval = evaluate_strict_mode(result, strict=strict)
    if strict_eval.failed:
        return None, result, strict_eval

    output_path = build_output_path(Path(input_path).expanduser().resolve(), output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_pp3(output_path, result.pp3_sections)
    return output_path, result, strict_eval


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
        strict: bool,
        input_dir: str,
        output_dir: str,
        preferences_path: Path | None = None,
    ) -> None:
        self.root = root
        self.dnd_available = dnd_available
        self.available_profiles = available_profiles
        self.profile_var = StringVar(value=profile)
        self.strict_var = BooleanVar(value=strict)
        self.mapping_file = mapping_file
        self.base_pp3_var = StringVar(value=str(base_pp3) if base_pp3 else "")
        self.base_pp3_mode_var = StringVar(value=base_pp3_mode if base_pp3_mode in _BASE_PP3_MODES else "safe")
        self.input_dir_var = StringVar(value=input_dir)
        self.output_dir_var = StringVar(value=output_dir)
        self.preferences_path = preferences_path
        self.status_var = StringVar(value="Add presets to the queue, then preview or convert all.")
        self.queue = ConversionQueueModel()

        self.root.title("Lightroom Preset to RawTherapee Profile Converter")
        self.root.geometry("980x620")
        self.root.minsize(900, 520)
        self._configure_style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        self.root.configure(background="#090a0c")
        # Ensure Combobox dropdown listbox keeps the same high-contrast palette.
        self.root.option_add("*TCombobox*Listbox.background", "#12151a")
        self.root.option_add("*TCombobox*Listbox.foreground", "#f3ecdd")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#d3b173")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#090a0c")
        self.root.option_add("*TButton*cursor", "hand2")
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("App.TFrame", background="#090a0c")
        style.configure("Card.TFrame", background="#171a20", borderwidth=1, relief="solid", bordercolor="#3b3225")
        style.configure("ActionRow.TFrame", background="#171a20", borderwidth=0, relief="flat")
        style.configure("Title.TLabel", background="#171a20", foreground="#f5efe2", font=("Times", 19, "bold"))
        style.configure("Subtitle.TLabel", background="#171a20", foreground="#b2ab9e", font=("Times", 11))
        style.configure("Field.TLabel", background="#171a20", foreground="#d7cfbf", font=("TkDefaultFont", 10, "bold"))
        style.configure("Hint.TLabel", background="#171a20", foreground="#9f9789", font=("TkDefaultFont", 9))
        style.configure("Status.TLabel", background="#111318", foreground="#e6dfd2", font=("TkDefaultFont", 10), padding=(10, 8))
        style.configure("Input.TEntry", fieldbackground="#12151a", foreground="#f3ecdd", bordercolor="#3b3225", insertcolor="#f3ecdd", padding=(8, 6))
        style.configure("Input.TCombobox", fieldbackground="#12151a", foreground="#f3ecdd", bordercolor="#3b3225", arrowcolor="#d3b173", padding=(8, 6))
        style.map(
            "Input.TCombobox",
            fieldbackground=[("readonly", "#12151a"), ("focus", "#181c23"), ("active", "#181c23")],
            foreground=[("readonly", "#f3ecdd"), ("focus", "#f3ecdd"), ("active", "#f3ecdd")],
            selectbackground=[("readonly", "#d3b173"), ("focus", "#d3b173")],
            selectforeground=[("readonly", "#090a0c"), ("focus", "#090a0c")],
            bordercolor=[("focus", "#d3b173"), ("active", "#d3b173")],
            arrowcolor=[("active", "#e2c28b"), ("focus", "#e2c28b")],
        )

        style.configure("Utility.TButton", background="#21262f", foreground="#ece3d2", bordercolor="#4a4030", lightcolor="#21262f", darkcolor="#21262f", focuscolor="#21262f", padding=(10, 7), relief="flat")
        style.configure("Secondary.TButton", background="#3b2f1f", foreground="#f4e5c9", bordercolor="#5a462d", lightcolor="#3b2f1f", darkcolor="#3b2f1f", focuscolor="#3b2f1f", padding=(12, 8), relief="flat", font=("TkDefaultFont", 10, "bold"))
        style.configure("Primary.TButton", background="#d3b173", foreground="#090a0c", bordercolor="#d3b173", lightcolor="#d3b173", darkcolor="#d3b173", focuscolor="#d3b173", padding=(12, 8), relief="flat", font=("TkDefaultFont", 10, "bold"))
        style.map(
            "Utility.TButton",
            background=[("active", "#2a313c"), ("pressed", "#1d232c")],
            foreground=[("active", "#f7efde"), ("pressed", "#f7efde"), ("focus", "#f7efde")],
            bordercolor=[("active", "#5a503d"), ("focus", "#5a503d")],
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#4a3a26"), ("pressed", "#332818")],
            foreground=[("active", "#fff3dc"), ("pressed", "#fff3dc"), ("focus", "#fff3dc")],
            bordercolor=[("active", "#7a613f"), ("focus", "#7a613f")],
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#e0c089"), ("pressed", "#be9b5e")],
            foreground=[("active", "#090a0c"), ("pressed", "#090a0c"), ("focus", "#090a0c")],
        )

    def _build(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=22)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header_card = ttk.Frame(outer, style="Card.TFrame", padding=(16, 14))
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header_card.columnconfigure(0, weight=1)

        ttk.Label(
            header_card,
            text="Lightroom Preset to RawTherapee Profile Converter",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")

        form_card = ttk.Frame(outer, style="Card.TFrame", padding=(16, 14))
        form_card.grid(row=1, column=0, sticky="nsew")
        form_card.columnconfigure(1, weight=1)
        form_card.rowconfigure(5, weight=1)

        ttk.Label(form_card, text="Profile", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            form_card,
            textvariable=self.profile_var,
            values=self.available_profiles,
            state="readonly",
            style="Input.TCombobox",
        ).grid(row=0, column=1, sticky="ew", padx=(10, 10))
        ttk.Label(form_card, text="Translation profile", style="Hint.TLabel").grid(row=0, column=2, sticky="e")

        tk.Checkbutton(
            form_card,
            text="Strict mode (fail conversion on warnings)",
            variable=self.strict_var,
            bg="#171a20",
            fg="#f3ecdd",
            activebackground="#171a20",
            activeforeground="#f3ecdd",
            selectcolor="#d3b173",
            highlightthickness=0,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        input_actions = ttk.Frame(form_card, style="ActionRow.TFrame")
        input_actions.grid(row=1, column=2, sticky="e", pady=(10, 0))
        ttk.Button(input_actions, text="Add Files...", command=self._browse_input_files, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(input_actions, text="Remove Selected", command=self._remove_selected, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(input_actions, text="Clear Queue", command=self._clear_queue, style="Utility.TButton", cursor="hand2").grid(row=0, column=2)

        self.drop_target = tk.Label(
            form_card,
            text="Drag and drop .xmp/.dng files to add them to the queue",
            relief=tk.SOLID,
            borderwidth=1,
            padx=14,
            pady=12,
            anchor="center",
            bg="#101318",
            fg="#d6cdbd",
            highlightthickness=1,
            highlightbackground="#3b3225",
            font=("TkDefaultFont", 10),
        )
        self.drop_target.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 10))
        if not self.dnd_available:
            self.drop_target.configure(text="Drag-and-drop unavailable (install tkinterdnd2). Use Add Files instead.")

        ttk.Label(form_card, text="Output folder", style="Field.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Entry(form_card, textvariable=self.output_dir_var, style="Input.TEntry").grid(
            row=3, column=1, sticky="ew", padx=(10, 10)
        )
        output_actions = ttk.Frame(form_card, style="ActionRow.TFrame")
        output_actions.grid(row=3, column=2, sticky="e")
        ttk.Button(output_actions, text="Choose...", command=self._browse_output_dir, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(output_actions, text="Open Folder", command=self._open_output_folder, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=1
        )

        ttk.Label(form_card, text="Base .pp3 (optional)", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(10, 0))
        base_frame = ttk.Frame(form_card, style="ActionRow.TFrame")
        base_frame.grid(row=4, column=1, sticky="ew", padx=(10, 10), pady=(10, 0))
        base_frame.columnconfigure(0, weight=1)
        self.base_frame = base_frame
        ttk.Entry(base_frame, textvariable=self.base_pp3_var, style="Input.TEntry").grid(row=0, column=0, sticky="ew")
        ttk.Combobox(
            base_frame,
            textvariable=self.base_pp3_mode_var,
            values=list(_BASE_PP3_MODES),
            state="readonly",
            width=11,
            style="Input.TCombobox",
        ).grid(row=0, column=1, padx=(8, 0), sticky="e")
        self.base_hint_label = ttk.Label(
            base_frame,
            text=(
                "Template RawTherapee profile used as a starting point before mapped values are merged."
            ),
            style="Hint.TLabel",
            wraplength=320,
            justify="left",
        )
        self.base_hint_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.base_frame.bind("<Configure>", self._on_base_frame_configure, add="+")
        base_actions = ttk.Frame(form_card, style="ActionRow.TFrame")
        base_actions.grid(row=4, column=2, sticky="e", pady=(10, 0))
        ttk.Button(base_actions, text="Choose...", command=self._browse_base_pp3, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(base_actions, text="Clear", command=self._clear_base_pp3, style="Utility.TButton", cursor="hand2").grid(
            row=0, column=1
        )

        table_frame = ttk.Frame(form_card, style="ActionRow.TFrame")
        table_frame.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(14, 0))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.queue_table = ttk.Treeview(
            table_frame,
            columns=("preset", "status", "warnings", "output"),
            show="headings",
            selectmode="extended",
        )
        self.queue_table.heading("preset", text="Preset")
        self.queue_table.heading("status", text="Status")
        self.queue_table.heading("warnings", text="Warnings")
        self.queue_table.heading("output", text="Output")
        self.queue_table.column("preset", width=300, anchor="w")
        self.queue_table.column("status", width=150, anchor="w")
        self.queue_table.column("warnings", width=85, anchor="center")
        self.queue_table.column("output", width=300, anchor="w")
        self.queue_table.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.queue_table.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.queue_table.configure(yscrollcommand=y_scroll.set)

        action_row = ttk.Frame(form_card, style="ActionRow.TFrame")
        action_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=0)
        action_row.columnconfigure(2, weight=0)
        action_row.columnconfigure(3, weight=1)

        ttk.Button(action_row, text="Preview Selected", command=self._preview_selected, style="Secondary.TButton", cursor="hand2").grid(
            row=0, column=1, padx=(0, 10)
        )
        ttk.Button(action_row, text="Convert All", command=self._convert_all, style="Primary.TButton", cursor="hand2").grid(
            row=0, column=2, padx=(10, 0)
        )

        ttk.Label(form_card, textvariable=self.status_var, wraplength=880, style="Status.TLabel").grid(
            row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0)
        )

        self._bind_preference_events()
        self.root.after_idle(self._update_base_hint_wraplength)

    def bind_drop(self, dnd_files_symbol: object) -> None:
        self.drop_target.drop_target_register(dnd_files_symbol)
        self.drop_target.dnd_bind("<<Drop>>", self._on_drop)

    def _bind_preference_events(self) -> None:
        self.profile_var.trace_add("write", lambda *_: self._persist_preferences())
        self.strict_var.trace_add("write", lambda *_: self._persist_preferences())
        self.output_dir_var.trace_add("write", lambda *_: self._persist_preferences())
        self.base_pp3_var.trace_add("write", lambda *_: self._persist_preferences())
        self.base_pp3_mode_var.trace_add("write", lambda *_: self._persist_preferences())

    def _on_base_frame_configure(self, _event: object) -> None:
        self._update_base_hint_wraplength()

    def _update_base_hint_wraplength(self) -> None:
        try:
            width = self.base_frame.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        self.base_hint_label.configure(wraplength=max(180, width - 12))

    def _current_base_pp3(self) -> Path | None:
        base_value = self.base_pp3_var.get().strip()
        if not base_value:
            return None
        return Path(base_value).expanduser().resolve()

    def _collect_preferences(self) -> GuiPreferences:
        input_dir = self.input_dir_var.get().strip() or str(Path.home())
        output_dir = self.output_dir_var.get().strip() or str(Path.home() / "Downloads")
        profile = self.profile_var.get().strip() or "balanced"
        base_pp3 = self.base_pp3_var.get().strip()
        base_mode = self.base_pp3_mode_var.get().strip()
        if base_mode not in _BASE_PP3_MODES:
            base_mode = "safe"
        strict = bool(self.strict_var.get())
        return GuiPreferences(
            input_dir=input_dir,
            output_dir=output_dir,
            profile=profile,
            base_pp3=base_pp3,
            base_pp3_mode=base_mode,
            strict=strict,
        )

    def _persist_preferences(self) -> None:
        try:
            save_gui_preferences(self._collect_preferences(), path=self.preferences_path)
        except OSError:
            pass

    def _on_close(self) -> None:
        self._persist_preferences()
        self.root.destroy()

    def _selected_indices(self) -> list[int]:
        indices: list[int] = []
        for item_id in self.queue_table.selection():
            try:
                indices.append(int(item_id))
            except ValueError:
                continue
        return sorted(set(indices))

    def _refresh_queue_table(self) -> None:
        for item_id in self.queue_table.get_children():
            self.queue_table.delete(item_id)

        for idx, entry in enumerate(self.queue.entries()):
            output_text = str(entry.output_path) if entry.output_path else ""
            self.queue_table.insert(
                "",
                "end",
                iid=str(idx),
                values=(str(entry.input_path), entry.status, str(entry.warning_count), output_text),
            )

    def _add_paths(self, paths: list[Path]) -> None:
        resolved_paths = [path.expanduser().resolve() for path in paths]
        if resolved_paths:
            self.input_dir_var.set(str(resolved_paths[0].parent))
        summary = self.queue.add_paths(paths)
        self._refresh_queue_table()

        fragments: list[str] = [f"Added {summary.added}"]
        if summary.skipped_duplicate:
            fragments.append(f"duplicates {summary.skipped_duplicate}")
        if summary.skipped_missing:
            fragments.append(f"missing {summary.skipped_missing}")
        if summary.skipped_unsupported:
            fragments.append(f"unsupported {summary.skipped_unsupported}")

        self.status_var.set("Queue update: " + " | ".join(fragments))
        self._persist_preferences()

    def _browse_input_files(self) -> None:
        initial_dir = self.input_dir_var.get().strip() or str(Path.home())
        selected = filedialog.askopenfilenames(
            title="Select Lightroom presets",
            initialdir=initial_dir,
            filetypes=[("Lightroom Presets", "*.xmp *.dng"), ("All files", "*.*")],
        )
        if selected:
            self._add_paths([Path(path) for path in selected])

    def _browse_output_dir(self) -> None:
        initial_dir = self.output_dir_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(title="Select output folder", initialdir=initial_dir)
        if selected:
            self.output_dir_var.set(str(Path(selected).expanduser().resolve()))

    def _browse_base_pp3(self) -> None:
        initial_dir = str(Path.home())
        current = self.base_pp3_var.get().strip()
        if current:
            initial_dir = str(Path(current).expanduser().resolve().parent)
        selected = filedialog.askopenfilename(
            title="Select base RawTherapee profile",
            initialdir=initial_dir,
            filetypes=[("RawTherapee Profile", "*.pp3"), ("All files", "*.*")],
        )
        if selected:
            self.base_pp3_var.set(str(Path(selected).expanduser().resolve()))

    def _clear_base_pp3(self) -> None:
        self.base_pp3_var.set("")

    def _open_output_folder(self) -> None:
        output_dir = Path(self.output_dir_var.get().strip()).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        webbrowser.open_new(output_dir.as_uri())

    def _remove_selected(self) -> None:
        indices = self._selected_indices()
        if not indices:
            self.status_var.set("No queue rows selected.")
            return

        removed = self.queue.remove_indices(indices)
        self._refresh_queue_table()
        self.status_var.set(f"Removed {removed} item(s) from queue.")

    def _clear_queue(self) -> None:
        if len(self.queue) == 0:
            self.status_var.set("Queue already empty.")
            return
        self.queue.clear()
        self._refresh_queue_table()
        self.status_var.set("Queue cleared.")

    def _on_drop(self, event: object) -> None:
        drop_data = getattr(event, "data", "")
        paths = parse_drop_paths(str(drop_data))
        if not paths:
            self.status_var.set("No files found in drop payload.")
            return
        self._add_paths(paths)

    def _preview_selected(self) -> None:
        indices = self._selected_indices()
        if not indices:
            messagebox.showerror("Missing selection", "Select a queued file to preview.")
            return

        entry = self.queue.get(indices[0])
        if entry is None:
            messagebox.showerror("Missing selection", "Selected queue item is unavailable.")
            return

        try:
            preview_path, result = run_gui_preview(
                input_path=entry.input_path,
                profile=self.profile_var.get().strip() or "balanced",
                mapping_file=self.mapping_file,
                base_pp3=self._current_base_pp3(),
                base_pp3_mode=self.base_pp3_mode_var.get().strip() or "safe",
            )
            webbrowser.open_new(preview_path.as_uri())
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc))
            return

        entry.status = STATUS_PREVIEWED
        entry.warning_count = len(result.warnings)
        entry.message = f"Preview opened at {preview_path}"
        self._refresh_queue_table()
        self.status_var.set(f"Preview opened: {preview_path} | warnings: {len(result.warnings)}")
        self._persist_preferences()

    def _convert_all(self) -> None:
        if len(self.queue) == 0:
            messagebox.showerror("Missing queue", "Add one or more presets to the queue first.")
            return

        output_value = self.output_dir_var.get().strip()
        if not output_value:
            messagebox.showerror("Missing output folder", "Choose an output folder.")
            return

        output_dir = Path(output_value)
        profile = self.profile_var.get().strip() or "balanced"
        strict = bool(self.strict_var.get())

        converted = failed = errors = 0
        for entry in self.queue.entries():
            try:
                output_path, result, strict_eval = run_gui_conversion_checked(
                    input_path=entry.input_path,
                    output_dir=output_dir,
                    profile=profile,
                    mapping_file=self.mapping_file,
                    base_pp3=self._current_base_pp3(),
                    base_pp3_mode=self.base_pp3_mode_var.get().strip() or "safe",
                    strict=strict,
                )
                entry.warning_count = len(result.warnings)
                entry.output_path = output_path

                if strict_eval.failed:
                    entry.message = strict_eval.message or "Strict mode failed."
                    entry.output_path = None
                    entry.status = STATUS_FAILED_STRICT
                    failed += 1
                    continue

                entry.message = ""
                entry.status = STATUS_CONVERTED_WARN if result.warnings else STATUS_CONVERTED
                converted += 1
            except Exception as exc:
                entry.warning_count = 0
                entry.output_path = None
                entry.message = str(exc)
                entry.status = STATUS_ERROR
                errors += 1

        self._refresh_queue_table()
        self.status_var.set(
            "Batch complete. "
            f"Converted: {converted} | Failed: {failed} | Errors: {errors} | Skipped: 0"
        )
        self._persist_preferences()


def launch_gui(
    profile: str | None = None,
    mapping_file: str | None = None,
    base_pp3: Path | None = None,
    base_pp3_mode: str | None = None,
    strict: bool | None = None,
    preferences_path: Path | None = None,
) -> None:
    preferences = load_gui_preferences(path=preferences_path)
    override_path = Path(mapping_file).expanduser().resolve() if mapping_file else None
    config = load_config(override_path)
    available_profiles = list(config.get("profiles", {}).keys())
    if not available_profiles:
        raise ValueError("No mapping profiles found in configuration.")

    preferred_profile = profile or preferences.profile
    selected_profile = "balanced" if "balanced" in available_profiles else available_profiles[0]
    if preferred_profile in available_profiles:
        selected_profile = preferred_profile

    selected_base_pp3_mode = (base_pp3_mode or preferences.base_pp3_mode).strip()
    if selected_base_pp3_mode not in _BASE_PP3_MODES:
        selected_base_pp3_mode = "safe"

    selected_base_pp3 = base_pp3
    if selected_base_pp3 is None and preferences.base_pp3:
        selected_base_pp3 = Path(preferences.base_pp3).expanduser().resolve()

    selected_output_dir = preferences.output_dir
    selected_input_dir = preferences.input_dir
    selected_strict = preferences.strict if strict is None else strict

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
        base_pp3=selected_base_pp3,
        base_pp3_mode=selected_base_pp3_mode,
        strict=selected_strict,
        input_dir=selected_input_dir,
        output_dir=selected_output_dir,
        preferences_path=preferences_path,
    )
    if dnd_available and dnd_files_symbol is not None:
        app.bind_drop(dnd_files_symbol)

    root.mainloop()


def main() -> int:
    launch_gui()
    return 0
