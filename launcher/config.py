"""
launcher/config.py — persistent launcher settings (launcher_config.json).
"""
from __future__ import annotations
import json
from pathlib import Path

_ROOT        = Path(__file__).parent.parent   # project root
CONFIG_PATH  = _ROOT / "launcher_config.json"
VERSIONS_DIR = _ROOT / "versions"
SAVES_DIR    = _ROOT / "saves"

_DEFAULTS: dict = {
    "github_repo":      "",           # "owner/repo" or empty
    "active_version":   "dev",
    "saves_dir":        str(SAVES_DIR),
    "versions_dir":     str(VERSIONS_DIR),
    "window_geometry":  "900x550",
}


class Config:
    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._load()

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        CONFIG_PATH.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Accessors ─────────────────────────────────────────────────────────

    @property
    def github_repo(self) -> str:
        return self._data.get("github_repo", "")

    @github_repo.setter
    def github_repo(self, v: str):
        self._data["github_repo"] = v.strip()

    @property
    def active_version(self) -> str:
        return self._data.get("active_version", "dev")

    @active_version.setter
    def active_version(self, v: str):
        self._data["active_version"] = v

    @property
    def saves_dir(self) -> Path:
        return Path(self._data.get("saves_dir", str(SAVES_DIR)))

    @property
    def versions_dir(self) -> Path:
        return Path(self._data.get("versions_dir", str(VERSIONS_DIR)))
