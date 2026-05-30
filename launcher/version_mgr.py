"""
launcher/version_mgr.py — local version installation / listing.

Installed versions live in  versions/<tag>/
  versions/<tag>/main.py   ← game entry point
  versions/<tag>/...

Special pseudo-version "dev" always points to the project root.
"""
from __future__ import annotations
import json, shutil, tempfile, zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from .config import Config
from .github_api import GitHubClient, Release


@dataclass
class VersionInfo:
    tag:        str            # "dev", "0.9-alfa", …
    label:      str            # human-readable display name
    installed:  bool
    path:       Optional[Path] # None if not installed
    release:    Optional[Release] = None   # None for "dev"
    is_dev:     bool = False


DEV_TAG = "dev"


class VersionManager:
    def __init__(self, cfg: Config):
        self.cfg  = cfg
        self._gh: Optional[GitHubClient] = None
        if cfg.github_repo:
            self._gh = GitHubClient(cfg.github_repo)

    # ── Listing ───────────────────────────────────────────────────────────

    def set_repo(self, repo: str):
        self.cfg.github_repo = repo
        self._gh = GitHubClient(repo) if repo else None

    def list_versions(self, force_refresh: bool = False) -> list[VersionInfo]:
        """
        Returns merged list:
          1) "dev" entry (always first)
          2) GitHub releases, marked installed/not
        Offline-safe: returns only local if GitHub unreachable.
        """
        versions: list[VersionInfo] = []

        # Dev pseudo-entry
        root = Path(__file__).parent.parent
        versions.append(VersionInfo(
            tag=DEV_TAG,
            label="Dev (текущая разработка)",
            installed=True,
            path=root,
            is_dev=True,
        ))

        # Installed local versions (may have no matching GitHub release)
        installed_tags = self._installed_tags()

        remote: list[Release] = []
        if self._gh:
            try:
                remote = self._gh.list_releases(force=force_refresh)
            except Exception:
                pass   # offline — show only local

        # Build from remote list
        remote_tags = set()
        for rel in remote:
            remote_tags.add(rel.tag)
            path = self.cfg.versions_dir / rel.tag
            versions.append(VersionInfo(
                tag=rel.tag,
                label=f"{rel.name}  ({rel.published})",
                installed=rel.tag in installed_tags,
                path=path if rel.tag in installed_tags else None,
                release=rel,
            ))

        # Local-only installs (not on GitHub or stale cache)
        for tag in installed_tags:
            if tag not in remote_tags:
                path = self.cfg.versions_dir / tag
                versions.append(VersionInfo(
                    tag=tag,
                    label=f"{tag}  (локальная)",
                    installed=True,
                    path=path,
                ))

        return versions

    def _installed_tags(self) -> set[str]:
        vd = self.cfg.versions_dir
        if not vd.exists():
            return set()
        return {
            d.name for d in vd.iterdir()
            if d.is_dir() and (d / "main.py").exists()
        }

    # ── Install ───────────────────────────────────────────────────────────

    def install(
        self,
        info: VersionInfo,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ):
        """
        Download and install info.release.
        Raises RuntimeError on failure.
        """
        if info.is_dev or info.installed:
            return
        rel = info.release
        if rel is None:
            raise RuntimeError("Нет информации о релизе")
        if self._gh is None:
            raise RuntimeError("GitHub-репозиторий не настроен")

        # Choose download URL
        asset = rel.zip_asset
        url   = asset.download_url if asset else getattr(rel, "source_zip_url", "")
        if not url:
            raise RuntimeError("Нет ссылки для скачивания")

        dest_dir = self.cfg.versions_dir / rel.tag
        dest_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self._gh.download(url, tmp_path, progress_cb)
            self._extract(tmp_path, dest_dir)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _extract(self, zip_path: Path, dest: Path):
        """
        Extract zip to dest, stripping the top-level folder if present
        (GitHub source zips have owner-repo-tag/ prefix).
        """
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            # Detect common prefix
            prefix = ""
            if names:
                top = names[0].split("/")[0]
                if all(n.startswith(top + "/") for n in names):
                    prefix = top + "/"

            for member in zf.infolist():
                rel = member.filename
                if prefix:
                    rel = rel[len(prefix):]
                if not rel:
                    continue
                target = dest / rel
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

    # ── Uninstall ─────────────────────────────────────────────────────────

    def uninstall(self, info: VersionInfo):
        if info.is_dev or not info.installed or info.path is None:
            return
        shutil.rmtree(info.path, ignore_errors=True)

    # ── Worlds ────────────────────────────────────────────────────────────

    def list_worlds(self) -> list[dict]:
        """
        Return list of worlds found in saves_dir.
        Each dict: {"name": str, "path": Path, "slot": int}.
        """
        sd = self.cfg.saves_dir
        if not sd.exists():
            return []
        worlds = []
        for p in sorted(sd.glob("world_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                name = data.get("name") or p.stem
                slot = int(p.stem.split("_")[1])
                worlds.append({"name": name, "path": p, "slot": slot})
            except Exception:
                pass
        return worlds

    def delete_world(self, world: dict):
        Path(world["path"]).unlink(missing_ok=True)
