"""
launcher/github_api.py — GitHub Releases API wrapper.

Uses only stdlib (urllib) — no extra dependencies.
"""
from __future__ import annotations
import json, time, urllib.request, urllib.error
from dataclasses import dataclass, field
from typing import Optional

API_BASE  = "https://api.github.com"
TIMEOUT   = 8    # seconds
_CACHE_TTL = 300  # 5 minutes

@dataclass
class ReleaseAsset:
    name:         str
    download_url: str
    size:         int     # bytes


@dataclass
class Release:
    tag:        str
    name:       str
    body:       str       # changelog markdown
    published:  str       # ISO date string
    prerelease: bool
    assets:     list[ReleaseAsset] = field(default_factory=list)

    @property
    def zip_asset(self) -> Optional[ReleaseAsset]:
        """First .zip asset, or None if no assets (use source zip)."""
        for a in self.assets:
            if a.name.endswith(".zip"):
                return a
        return None

    @property
    def source_zip_url(self) -> str:
        """GitHub auto-generated source code zip URL."""
        # Derived from API URL pattern when no explicit asset exists
        return ""   # filled by GitHubClient when constructing


class _Cache:
    def __init__(self):
        self._data: Optional[list[Release]] = None
        self._ts: float = 0.0

    def get(self) -> Optional[list[Release]]:
        if self._data is not None and time.time() - self._ts < _CACHE_TTL:
            return self._data
        return None

    def set(self, data: list[Release]):
        self._data = data
        self._ts   = time.time()

    def invalidate(self):
        self._data = None


class GitHubClient:
    def __init__(self, repo: str):
        """repo: 'owner/repo'"""
        self.repo  = repo.strip()
        self._cache = _Cache()

    def _get(self, path: str) -> object:
        url = f"{API_BASE}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "minacraft-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())

    def list_releases(self, force: bool = False) -> list[Release]:
        if not force:
            cached = self._cache.get()
            if cached is not None:
                return cached

        try:
            raw = self._get(f"repos/{self.repo}/releases")
        except Exception as e:
            raise ConnectionError(f"GitHub API недоступен: {e}") from e

        releases: list[Release] = []
        for r in raw:
            assets = [
                ReleaseAsset(
                    name=a["name"],
                    download_url=a["browser_download_url"],
                    size=a["size"],
                )
                for a in r.get("assets", [])
            ]
            rel = Release(
                tag=r["tag_name"],
                name=r.get("name") or r["tag_name"],
                body=r.get("body") or "",
                published=r.get("published_at", "")[:10],
                prerelease=r.get("prerelease", False),
                assets=assets,
            )
            # Fallback: GitHub source code zip
            if rel.zip_asset is None:
                rel.source_zip_url = (
                    f"https://github.com/{self.repo}/archive/refs/tags/{rel.tag}.zip"
                )
            releases.append(rel)

        self._cache.set(releases)
        return releases

    def download(
        self,
        url: str,
        dest_path,
        progress_cb=None,
    ):
        """
        Download url → dest_path.
        progress_cb(downloaded_bytes, total_bytes) called periodically.
        """
        req  = urllib.request.Request(url, headers={"User-Agent": "minacraft-launcher/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            chunk = 65536
            with open(dest_path, "wb") as fh:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    fh.write(data)
                    done += len(data)
                    if progress_cb:
                        progress_cb(done, total)
