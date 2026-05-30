"""
launcher.py — Minacraft Launcher (tkinter, тёмная тема).

Запускать этот файл вместо main.py для управления версиями и мирами.
"""
from __future__ import annotations
import subprocess, sys, threading, time, os
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from launcher.config   import Config
from launcher.version_mgr import VersionManager, VersionInfo, DEV_TAG

# ── Цвета ─────────────────────────────────────────────────────────────────────

BG       = "#0f0f1a"
BG2      = "#1a1a2e"
BG3      = "#16213e"
ACCENT   = "#4a9eff"
ACCENT2  = "#2d6abf"
FG       = "#e0e0f0"
FG_DIM   = "#7080a0"
FG_HEAD  = "#ffffff"
GREEN    = "#3dd68c"
RED      = "#e05252"
YELLOW   = "#f0c040"
BORDER   = "#2a2a4a"

FONT_N   = ("Segoe UI", 10)
FONT_B   = ("Segoe UI", 10, "bold")
FONT_S   = ("Segoe UI", 9)
FONT_H   = ("Segoe UI", 13, "bold")
FONT_T   = ("Segoe UI", 18, "bold")

ROOT_DIR = Path(__file__).parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _configure_ttk_style():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("TScrollbar",
                 background=BG3, troughcolor=BG2, arrowcolor=FG_DIM,
                 bordercolor=BG2, darkcolor=BG3, lightcolor=BG3)
    s.configure("Vertical.TScrollbar",
                 background=BG3, troughcolor=BG2, arrowcolor=FG_DIM)
    s.configure("Horizontal.TProgressbar",
                 background=ACCENT, troughcolor=BG2,
                 bordercolor=BG2, lightcolor=ACCENT, darkcolor=ACCENT2)


# ── Panels ────────────────────────────────────────────────────────────────────

class VersionPanel(tk.Frame):
    """Left panel: list of versions."""

    def __init__(self, parent, on_select):
        super().__init__(parent, bg=BG2, width=220)
        self.pack_propagate(False)
        self._on_select = on_select
        self._items: list[VersionInfo] = []
        self._sel_idx: int = -1
        self._btns: list[tk.Frame] = []
        self._build()

    def _build(self):
        tk.Label(self, text="ВЕРСИИ", bg=BG2, fg=FG_DIM,
                 font=FONT_S).pack(anchor="w", padx=10, pady=(10, 4))

        frame = tk.Frame(self, bg=BG2)
        frame.pack(fill="both", expand=True, padx=4)

        self._scroll_canvas = tk.Canvas(frame, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical",
                           command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(self._scroll_canvas, bg=BG2)
        self._win_id = self._scroll_canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw")
        self._list_frame.bind("<Configure>", self._on_frame_configure)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel
        self._scroll_canvas.bind("<MouseWheel>", self._on_wheel)
        self._list_frame.bind("<MouseWheel>", self._on_wheel)

        # Refresh button
        tk.Label(self, text="", bg=BG2).pack(pady=2)

    def _on_frame_configure(self, _e):
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._scroll_canvas.itemconfig(self._win_id, width=e.width)

    def _on_wheel(self, e):
        self._scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def populate(self, items: list[VersionInfo], active_tag: str):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._btns.clear()
        self._items = items

        for i, vi in enumerate(items):
            if vi.installed:
                dot_col  = GREEN if vi.is_dev else ACCENT
                dot_text = "●"
            else:
                dot_col  = FG_DIM
                dot_text = "○"

            is_active = (vi.tag == active_tag)
            row_bg    = BG3 if is_active else BG2

            row = tk.Frame(self._list_frame, bg=row_bg,
                           cursor="hand2", pady=4)
            row.pack(fill="x", padx=2, pady=1)
            self._btns.append(row)

            tk.Label(row, text=dot_text, bg=row_bg,
                     fg=dot_col, font=FONT_N, width=2).pack(side="left")

            label = vi.label
            if len(label) > 26:
                label = label[:24] + "…"
            lbl = tk.Label(row, text=label, bg=row_bg,
                           fg=FG_HEAD if is_active else FG,
                           font=FONT_B if is_active else FONT_N,
                           anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

            for widget in (row, lbl):
                widget.bind("<Button-1>", lambda e, idx=i: self._select(idx))
                widget.bind("<MouseWheel>", self._on_wheel)

        if items:
            # auto-select active
            for i, vi in enumerate(items):
                if vi.tag == active_tag:
                    self._select(i)
                    break
            else:
                self._select(0)

    def _select(self, idx: int):
        # Reset previous highlight
        for i, row in enumerate(self._btns):
            vi  = self._items[i]
            bg  = BG3 if i == idx else BG2
            fg  = FG_HEAD if i == idx else FG
            fn  = FONT_B if i == idx else FONT_N
            row.configure(bg=bg)
            for child in row.winfo_children():
                try:
                    child.configure(bg=bg, fg=fg, font=fn)
                except tk.TclError:
                    pass
        self._sel_idx = idx
        self._on_select(self._items[idx])

    @property
    def selected(self) -> Optional[VersionInfo]:
        if 0 <= self._sel_idx < len(self._items):
            return self._items[self._sel_idx]
        return None


class ChangelogPanel(tk.Frame):
    """Center panel: version info + changelog."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._build()

    def _build(self):
        self._title = tk.Label(self, text="", bg=BG, fg=FG_HEAD, font=FONT_H)
        self._title.pack(anchor="w", padx=16, pady=(14, 2))

        self._meta = tk.Label(self, text="", bg=BG, fg=FG_DIM, font=FONT_S)
        self._meta.pack(anchor="w", padx=16)

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=8)

        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True, padx=16)

        self._text = tk.Text(
            frame, wrap="word", bg=BG, fg=FG,
            font=("Consolas", 10), relief="flat",
            insertbackground=FG, selectbackground=ACCENT2,
            padx=4, pady=4, state="disabled",
            highlightthickness=0, borderwidth=0,
        )
        sb = ttk.Scrollbar(frame, orient="vertical",
                           command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

    def show(self, vi: VersionInfo):
        self._title.configure(text=vi.label)
        if vi.is_dev:
            meta = "Текущая версия в разработке  •  всегда актуальна"
        elif vi.release:
            pre  = "  •  pre-release" if vi.release.prerelease else ""
            meta = f"{vi.release.published}{pre}"
        else:
            meta = "Локальная установка"
        self._meta.configure(text=meta)

        body = ""
        if vi.is_dev:
            body = (
                "Это текущая рабочая версия из папки проекта.\n\n"
                "Все изменения здесь — самые свежие.\n"
                "Может быть нестабильной."
            )
        elif vi.release and vi.release.body:
            body = vi.release.body
        else:
            body = "(Описание недоступно)"

        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("end", body)
        self._text.configure(state="disabled")


class WorldPanel(tk.Frame):
    """Right panel: world list."""

    def __init__(self, parent, on_select, on_new, on_delete):
        super().__init__(parent, bg=BG2, width=200)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_new    = on_new
        self._on_delete = on_delete
        self._worlds: list[dict] = []
        self._sel_idx = -1
        self._btns: list[tk.Frame] = []
        self._build()

    def _build(self):
        tk.Label(self, text="МИРЫ", bg=BG2, fg=FG_DIM,
                 font=FONT_S).pack(anchor="w", padx=10, pady=(10, 4))

        list_frame = tk.Frame(self, bg=BG2)
        list_frame.pack(fill="both", expand=True, padx=4)

        self._canvas = tk.Canvas(list_frame, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(list_frame, orient="vertical",
                           command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._lf = tk.Frame(self._canvas, bg=BG2)
        self._wid = self._canvas.create_window((0, 0), window=self._lf, anchor="nw")
        self._lf.bind("<Configure>",
                      lambda e: self._canvas.configure(
                          scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(self._wid, width=e.width))
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._lf.bind("<MouseWheel>", self._on_wheel)

        btn_frame = tk.Frame(self, bg=BG2)
        btn_frame.pack(fill="x", padx=6, pady=6)
        self._btn_new = _flat_btn(btn_frame, "+ Новый мир", self._on_new,
                                   bg=BG3, fg=GREEN)
        self._btn_new.pack(fill="x", pady=(0, 4))
        self._btn_del = _flat_btn(btn_frame, "🗑 Удалить", self._do_delete,
                                   bg=BG3, fg=RED)
        self._btn_del.pack(fill="x")

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def populate(self, worlds: list[dict]):
        for w in self._lf.winfo_children():
            w.destroy()
        self._btns.clear()
        self._worlds = worlds
        self._sel_idx = -1

        for i, wd in enumerate(worlds):
            row = tk.Frame(self._lf, bg=BG2, cursor="hand2", pady=5)
            row.pack(fill="x", padx=2, pady=1)
            self._btns.append(row)

            tk.Label(row, text="🌍", bg=BG2, fg=ACCENT,
                     font=("Segoe UI", 12)).pack(side="left", padx=(4, 2))
            name = wd["name"]
            if len(name) > 20:
                name = name[:18] + "…"
            lbl = tk.Label(row, text=name, bg=BG2, fg=FG,
                           font=FONT_N, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)

            for widget in (row, lbl):
                widget.bind("<Button-1>", lambda e, idx=i: self._select(idx))
                widget.bind("<MouseWheel>", self._on_wheel)

        if worlds:
            self._select(0)
        else:
            self._on_select(None)

    def _select(self, idx: int):
        for i, row in enumerate(self._btns):
            bg = BG3 if i == idx else BG2
            row.configure(bg=bg)
            for c in row.winfo_children():
                try:
                    c.configure(bg=bg)
                except tk.TclError:
                    pass
        self._sel_idx = idx
        self._on_select(self._worlds[idx] if 0 <= idx < len(self._worlds) else None)

    def _do_delete(self):
        if 0 <= self._sel_idx < len(self._worlds):
            self._on_delete(self._worlds[self._sel_idx])

    @property
    def selected(self) -> Optional[dict]:
        if 0 <= self._sel_idx < len(self._worlds):
            return self._worlds[self._sel_idx]
        return None


class BottomBar(tk.Frame):
    """Bottom bar: action buttons + progress bar."""

    def __init__(self, parent, on_install, on_uninstall, on_play, on_settings):
        super().__init__(parent, bg=BG3, height=72)
        self.pack_propagate(False)
        self._on_install   = on_install
        self._on_uninstall = on_uninstall
        self._on_play      = on_play
        self._on_settings  = on_settings
        self._build()

    def _build(self):
        left = tk.Frame(self, bg=BG3)
        left.pack(side="left", padx=10, pady=10)

        self._btn_install = _flat_btn(left, "↓ Установить", self._on_install,
                                       bg=BG2, fg=ACCENT)
        self._btn_install.pack(side="left", padx=(0, 6))

        self._btn_uninstall = _flat_btn(left, "✕ Удалить", self._on_uninstall,
                                         bg=BG2, fg=RED)
        self._btn_uninstall.pack(side="left", padx=(0, 6))

        _flat_btn(left, "⚙ Настройки", on_settings, bg=BG2,
                  fg=FG_DIM).pack(side="left")

        right = tk.Frame(self, bg=BG3)
        right.pack(side="right", padx=10, pady=10)

        self._btn_play = _flat_btn(right, "▶  ИГРАТЬ", self._on_play,
                                    bg=ACCENT2, fg=FG_HEAD,
                                    font=("Segoe UI", 11, "bold"),
                                    padx=22, pady=8)
        self._btn_play.pack()

        # Progress area (hidden until downloading)
        self._prog_frame = tk.Frame(self, bg=BG3)
        self._prog_lbl   = tk.Label(self._prog_frame, text="", bg=BG3,
                                    fg=FG_DIM, font=FONT_S)
        self._prog_lbl.pack(anchor="w")
        self._progbar = ttk.Progressbar(self._prog_frame, mode="determinate",
                                         length=260, style="Horizontal.TProgressbar")
        self._progbar.pack(fill="x", pady=(2, 0))

    def set_version_state(self, vi: Optional[VersionInfo]):
        if vi is None:
            self._btn_install.configure(state="disabled")
            self._btn_uninstall.configure(state="disabled")
            return
        if vi.is_dev:
            self._btn_install.configure(state="disabled")
            self._btn_uninstall.configure(state="disabled")
        elif vi.installed:
            self._btn_install.configure(state="disabled")
            self._btn_uninstall.configure(state="normal")
        else:
            self._btn_install.configure(state="normal")
            self._btn_uninstall.configure(state="disabled")

    def show_progress(self, text: str, value: float):
        """value: 0.0–1.0, or -1 to hide."""
        if value < 0:
            self._prog_frame.place_forget()
            return
        self._prog_frame.place(relx=0.35, rely=0.1, relwidth=0.3)
        self._prog_lbl.configure(text=text)
        self._progbar["value"] = value * 100

    def set_play_state(self, enabled: bool):
        self._btn_play.configure(
            state="normal" if enabled else "disabled",
            bg=ACCENT2 if enabled else BG2,
        )


def on_settings():
    pass   # placeholder — overridden by App


def _flat_btn(parent, text, command, bg=BG2, fg=FG,
              font=FONT_N, padx=14, pady=6, **kw) -> tk.Button:
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, font=font,
        relief="flat", cursor="hand2",
        padx=padx, pady=pady,
        activebackground=ACCENT2, activeforeground=FG_HEAD,
        borderwidth=0, highlightthickness=0,
        **kw,
    )
    return btn


# ── Header ────────────────────────────────────────────────────────────────────

class Header(tk.Frame):
    def __init__(self, parent, version_label: str):
        super().__init__(parent, bg=BG3, height=54)
        self.pack_propagate(False)

        # Logo canvas
        logo = tk.Canvas(self, bg=BG3, width=44, height=44,
                         highlightthickness=0)
        logo.pack(side="left", padx=(12, 6), pady=5)
        self._draw_logo(logo)

        tk.Label(self, text="MINACRAFT", bg=BG3, fg=FG_HEAD,
                 font=FONT_T).pack(side="left")
        tk.Label(self, text="LAUNCHER", bg=BG3, fg=ACCENT,
                 font=("Segoe UI", 11)).pack(side="left", padx=(6, 0))

        tk.Label(self, text=version_label, bg=BG3, fg=FG_DIM,
                 font=FONT_S).pack(side="right", padx=16)

    def _draw_logo(self, c: tk.Canvas):
        # Grass block top
        c.create_rectangle(2, 2, 42, 22, fill="#5d8a3c", outline="")
        c.create_rectangle(2, 22, 42, 42, fill="#8b6340", outline="")
        # Highlight
        c.create_rectangle(4, 4, 18, 10, fill="#7ab84c", outline="")
        c.create_rectangle(22, 6, 38, 10, fill="#7ab84c", outline="")


# ── Settings dialog ───────────────────────────────────────────────────────────

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, cfg: Config, on_save):
        super().__init__(parent)
        self.title("Настройки лаунчера")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._cfg    = cfg
        self._on_save = on_save
        self._build()
        self.geometry("420x180")

    def _build(self):
        pad = dict(padx=14, pady=6)

        tk.Label(self, text="GitHub репозиторий", bg=BG, fg=FG,
                 font=FONT_N).grid(row=0, column=0, sticky="w", **pad)
        self._repo_var = tk.StringVar(value=self._cfg.github_repo)
        tk.Entry(self, textvariable=self._repo_var,
                 bg=BG2, fg=FG, insertbackground=FG,
                 font=FONT_N, width=28,
                 relief="flat", highlightthickness=1,
                 highlightcolor=ACCENT,
                 highlightbackground=BORDER).grid(row=0, column=1, **pad)
        tk.Label(self, text='Пример: username/minacraft', bg=BG,
                 fg=FG_DIM, font=FONT_S).grid(row=1, column=1, sticky="w", padx=14)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.grid(row=3, column=0, columnspan=2, pady=16)
        _flat_btn(btn_row, "Сохранить", self._save,
                  bg=ACCENT2, fg=FG_HEAD).pack(side="left", padx=6)
        _flat_btn(btn_row, "Отмена", self.destroy,
                  bg=BG2, fg=FG).pack(side="left")

        self.columnconfigure(1, weight=1)

    def _save(self):
        self._cfg.github_repo = self._repo_var.get()
        self._cfg.save()
        self._on_save()
        self.destroy()


# ── Main App ──────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.cfg  = Config()
        self.vmgr = VersionManager(self.cfg)

        self._sel_version: Optional[VersionInfo] = None
        self._sel_world:   Optional[dict]         = None
        self._game_proc:   Optional[subprocess.Popen] = None

        self._root = tk.Tk()
        self._root.title("Minacraft Launcher")
        self._root.configure(bg=BG)
        self._root.geometry("900x560")
        self._root.minsize(820, 500)

        _configure_ttk_style()
        self._build()
        self._refresh_versions()
        self._refresh_worlds()

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _build(self):
        # Header
        hdr = Header(self._root, "v1.0")
        hdr.pack(fill="x")

        # Separator
        tk.Frame(self._root, bg=BORDER, height=1).pack(fill="x")

        # Main content row
        content = tk.Frame(self._root, bg=BG)
        content.pack(fill="both", expand=True)

        self._ver_panel = VersionPanel(content, self._on_version_select)
        self._ver_panel.pack(side="left", fill="y")

        tk.Frame(content, bg=BORDER, width=1).pack(side="left", fill="y")

        self._chg_panel = ChangelogPanel(content)
        self._chg_panel.pack(side="left", fill="both", expand=True)

        tk.Frame(content, bg=BORDER, width=1).pack(side="right", fill="y")

        self._world_panel = WorldPanel(
            content,
            on_select=self._on_world_select,
            on_new=self._new_world,
            on_delete=self._delete_world,
        )
        self._world_panel.pack(side="right", fill="y")

        # Bottom
        tk.Frame(self._root, bg=BORDER, height=1).pack(fill="x")

        self._bottom = BottomBar(
            self._root,
            on_install=self._install,
            on_uninstall=self._uninstall,
            on_play=self._play,
            on_settings=self._open_settings,
        )
        self._bottom.pack(fill="x")

        # Status bar
        self._status_var = tk.StringVar(value="Готов")
        tk.Label(self._root, textvariable=self._status_var,
                 bg=BG3, fg=FG_DIM, font=FONT_S, anchor="w",
                 padx=10).pack(fill="x")

    # ── Version actions ───────────────────────────────────────────────────

    def _refresh_versions(self, force: bool = False):
        self._status("Загрузка списка версий…")
        versions = self.vmgr.list_versions(force_refresh=force)
        self._ver_panel.populate(versions, self.cfg.active_version)
        self._status("Готов")

    def _on_version_select(self, vi: VersionInfo):
        self._sel_version = vi
        self._chg_panel.show(vi)
        self._bottom.set_version_state(vi)
        can_play = vi.installed
        self._bottom.set_play_state(can_play)

    def _install(self):
        vi = self._sel_version
        if vi is None or vi.installed:
            return
        if not self.cfg.github_repo:
            messagebox.showwarning("Нет репозитория",
                                   "Укажите GitHub-репозиторий в Настройках.")
            return

        self._bottom.show_progress("Подключение…", 0.0)
        self._status(f"Устанавливаю {vi.tag}…")

        def _worker():
            def _prog(done, total):
                if total > 0:
                    frac = done / total
                    mb   = done / 1_048_576
                    tot  = total / 1_048_576
                    self._root.after(0, self._bottom.show_progress,
                                     f"{mb:.1f} / {tot:.1f} МБ", frac)
            try:
                self.vmgr.install(vi, progress_cb=_prog)
                self._root.after(0, self._install_done, vi.tag, None)
            except Exception as e:
                self._root.after(0, self._install_done, vi.tag, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _install_done(self, tag: str, error: Optional[str]):
        self._bottom.show_progress("", -1)
        if error:
            messagebox.showerror("Ошибка установки", error)
            self._status("Ошибка")
        else:
            self._status(f"{tag} установлена")
        self._refresh_versions()

    def _uninstall(self):
        vi = self._sel_version
        if vi is None or not vi.installed or vi.is_dev:
            return
        if not messagebox.askyesno("Удалить версию",
                                   f"Удалить {vi.tag}?\nИгровые миры не будут удалены."):
            return
        self.vmgr.uninstall(vi)
        self._status(f"{vi.tag} удалена")
        self._refresh_versions()

    # ── World actions ─────────────────────────────────────────────────────

    def _refresh_worlds(self):
        worlds = self.vmgr.list_worlds()
        self._world_panel.populate(worlds)

    def _on_world_select(self, world: Optional[dict]):
        self._sel_world = world

    def _new_world(self):
        name = simpledialog.askstring(
            "Новый мир", "Имя мира:", parent=self._root)
        if not name:
            return
        # Find a free slot
        existing_slots = {w["slot"] for w in self.vmgr.list_worlds()}
        slot = next(i for i in range(10) if i not in existing_slots)
        import json
        path = self.cfg.saves_dir / f"world_{slot}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name, "seed": None, "new": True},
                                   ensure_ascii=False), encoding="utf-8")
        self._refresh_worlds()

    def _delete_world(self, world: dict):
        if not messagebox.askyesno("Удалить мир",
                                   f"Удалить мир «{world['name']}»?\nОтменить нельзя."):
            return
        self.vmgr.delete_world(world)
        self._refresh_worlds()

    # ── Play ──────────────────────────────────────────────────────────────

    def _play(self):
        vi    = self._sel_version
        world = self._sel_world

        if vi is None or not vi.installed:
            messagebox.showwarning("Нет версии", "Выберите установленную версию.")
            return

        game_dir = vi.path
        main_py  = game_dir / "main.py"
        if not main_py.exists():
            messagebox.showerror("Ошибка",
                                 f"main.py не найден в:\n{game_dir}")
            return

        args = [sys.executable, str(main_py)]

        # Pass world slot if selected (game reads saves/ from its cwd)
        # We launch from the game directory so saves/ resolve correctly.
        # If game_dir != ROOT_DIR, saves_dir is different — copy saves link.
        env = os.environ.copy()
        if world:
            env["MINACRAFT_WORLD_SLOT"] = str(world["slot"])
            env["MINACRAFT_SAVES_DIR"]  = str(self.cfg.saves_dir.resolve())

        self.cfg.active_version = vi.tag
        self.cfg.save()

        try:
            self._game_proc = subprocess.Popen(
                args, cwd=str(game_dir), env=env,
            )
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))
            return

        self._root.withdraw()   # hide launcher while game runs
        self._monitor_game()

    def _monitor_game(self):
        if self._game_proc and self._game_proc.poll() is None:
            self._root.after(1000, self._monitor_game)
        else:
            self._game_proc = None
            self._root.deiconify()   # show launcher again
            self._refresh_worlds()

    # ── Settings ──────────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self._root, self.cfg,
                       on_save=lambda: (self.vmgr.set_repo(self.cfg.github_repo),
                                        self._refresh_versions(force=True)))

    # ── Misc ──────────────────────────────────────────────────────────────

    def _status(self, msg: str):
        self._status_var.set(msg)
        self._root.update_idletasks()

    def _on_close(self):
        if self._game_proc and self._game_proc.poll() is None:
            if not messagebox.askyesno("Игра запущена",
                                       "Игра ещё запущена. Всё равно закрыть?"):
                return
            self._game_proc.terminate()
        self._root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App()
