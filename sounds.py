"""Sound system: load OGG files from Minecraft resources, procedural fallback for missing."""
from __future__ import annotations
import os
import sys
import random
import numpy as np
import pygame
from pathlib import Path
from typing import Dict, List

_RATE  = 44100
_sounds: Dict[str, List[pygame.mixer.Sound]] = {}
_ready = False
_music_vol = 0.25

def _pkg_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.resolve()

_RES  = _pkg_dir() / "resources" / "Faithful-32x-1.21.11" / "assets" / "minecraft" / "resources copy"

# game name → list of relative paths (random choice on play)
# dig/break sounds: sound3/dig/ (actual block-breaking sounds, NOT footsteps)
# footstep sounds:  sound3/step/
# misc sounds:      sound3/random/
# damage sounds:    sound3/damage/ (classic ow) + newsound/damage/ (fleshy)
_FILE_MAP: Dict[str, List[str]] = {
    # ── Block digging (sound3/dig/ — these are the actual Minecraft dig sounds) ──
    "dig_grass":    ["sound3/dig/grass1.ogg",  "sound3/dig/grass2.ogg",
                     "sound3/dig/grass3.ogg",  "sound3/dig/grass4.ogg"],
    "dig_stone":    ["sound3/dig/stone1.ogg",  "sound3/dig/stone2.ogg",
                     "sound3/dig/stone3.ogg",  "sound3/dig/stone4.ogg"],
    "dig_wood":     ["sound3/dig/wood1.ogg",   "sound3/dig/wood2.ogg",
                     "sound3/dig/wood3.ogg",   "sound3/dig/wood4.ogg"],
    "dig_sand":     ["sound3/dig/sand1.ogg",   "sound3/dig/sand2.ogg",
                     "sound3/dig/sand3.ogg",   "sound3/dig/sand4.ogg"],
    "dig_gravel":   ["sound3/dig/gravel1.ogg", "sound3/dig/gravel2.ogg",
                     "sound3/dig/gravel3.ogg", "sound3/dig/gravel4.ogg"],
    "dig_snow":     ["sound3/dig/snow1.ogg",   "sound3/dig/snow2.ogg",
                     "sound3/dig/snow3.ogg",   "sound3/dig/snow4.ogg"],
    "dig_cloth":    ["sound3/dig/cloth1.ogg",  "sound3/dig/cloth2.ogg",
                     "sound3/dig/cloth3.ogg",  "sound3/dig/cloth4.ogg"],
    # ── Footsteps (sound3/step/) ──────────────────────────────────────────────
    "step_grass":   ["sound3/step/grass1.ogg", "sound3/step/grass2.ogg",
                     "sound3/step/grass3.ogg", "sound3/step/grass4.ogg",
                     "sound3/step/grass5.ogg", "sound3/step/grass6.ogg"],
    "step_stone":   ["sound3/step/stone1.ogg", "sound3/step/stone2.ogg",
                     "sound3/step/stone3.ogg", "sound3/step/stone4.ogg",
                     "sound3/step/stone5.ogg", "sound3/step/stone6.ogg"],
    "step_wood":    ["sound3/step/wood1.ogg",  "sound3/step/wood2.ogg",
                     "sound3/step/wood3.ogg",  "sound3/step/wood4.ogg",
                     "sound3/step/wood5.ogg",  "sound3/step/wood6.ogg"],
    "step_sand":    ["sound3/step/sand1.ogg",  "sound3/step/sand2.ogg",
                     "sound3/step/sand3.ogg",  "sound3/step/sand4.ogg",
                     "sound3/step/sand5.ogg"],
    "step_gravel":  ["sound3/step/gravel1.ogg","sound3/step/gravel2.ogg",
                     "sound3/step/gravel3.ogg","sound3/step/gravel4.ogg"],
    "step_snow":    ["sound3/step/snow1.ogg",  "sound3/step/snow2.ogg",
                     "sound3/step/snow3.ogg",  "sound3/step/snow4.ogg"],
    # ── Block interact / UI ───────────────────────────────────────────────────
    "break_block":  ["sound3/random/break.ogg"],
    "place_block":  ["sound3/random/click.ogg"],
    "pickup":       ["sound3/random/orb.ogg"],
    "craft":        ["sound3/random/pop.ogg"],
    "cant_mine":    ["sound3/random/click.ogg"],
    "click_button": ["sound3/random/click.ogg"],
    "door_open":    ["sound3/random/door_open.ogg"],
    "door_close":   ["sound3/random/door_close.ogg"],
    "chest_open":   ["sound3/random/chestopen.ogg"],
    "chest_close":  ["sound3/random/chestclosed.ogg"],
    "ignite":       ["sound3/fire/ignite.ogg"],
    "fuse":         ["sound3/random/fuse.ogg"],
    "fizz":         ["sound3/random/fizz.ogg"],
    "orb":          ["sound3/random/orb.ogg"],
    "levelup":      ["sound3/random/levelup.ogg"],
    "portal":       ["sound3/portal/portal.ogg"],
    # ── Food / drink ─────────────────────────────────────────────────────────
    "eat":          ["sound3/random/eat1.ogg", "sound3/random/eat2.ogg",
                     "sound3/random/eat3.ogg"],
    "drink":        ["sound3/random/drink.ogg"],
    "burp":         ["sound3/random/burp.ogg"],
    # ── Combat / damage ───────────────────────────────────────────────────────
    "hurt":         ["sound3/damage/hit1.ogg",          "sound3/damage/hit2.ogg",
                     "sound3/damage/hit3.ogg",
                     "newsound/damage/hurtflesh1.ogg",  "newsound/damage/hurtflesh2.ogg",
                     "newsound/damage/hurtflesh3.ogg"],
    "fall_big":     ["newsound/damage/fallbig1.ogg", "newsound/damage/fallbig2.ogg"],
    "fall_small":   ["newsound/damage/fallsmall.ogg"],
    "explode":      ["sound3/random/explode1.ogg", "sound3/random/explode2.ogg",
                     "sound3/random/explode3.ogg", "sound3/random/explode4.ogg"],
    "glass_break":  ["sound3/random/glass1.ogg",   "sound3/random/glass2.ogg",
                     "sound3/random/glass3.ogg"],
    "successful_hit": ["sound3/random/successful_hit.ogg"],
    # ── Liquid ────────────────────────────────────────────────────────────────
    "splash":       ["sound3/liquid/splash.ogg", "sound3/liquid/splash2.ogg"],
    "swim":         ["sound3/liquid/swim1.ogg",  "sound3/liquid/swim2.ogg",
                     "sound3/liquid/swim3.ogg",  "sound3/liquid/swim4.ogg"],
    "lava_ambient": ["sound3/liquid/lava.ogg"],
    "lava_pop":     ["sound3/liquid/lavapop.ogg"],
    # ── Ambient ───────────────────────────────────────────────────────────────
    "thunder":      ["newsound/ambient/weather/thunder1.ogg",
                     "newsound/ambient/weather/thunder2.ogg",
                     "newsound/ambient/weather/thunder3.ogg"],
    "rain":         ["newsound/ambient/weather/rain1.ogg", "newsound/ambient/weather/rain2.ogg",
                     "newsound/ambient/weather/rain3.ogg", "newsound/ambient/weather/rain4.ogg"],
    "cave_ambient": ["newsound/ambient/cave/cave1.ogg",  "newsound/ambient/cave/cave2.ogg",
                     "newsound/ambient/cave/cave3.ogg",  "newsound/ambient/cave/cave4.ogg",
                     "newsound/ambient/cave/cave5.ogg",  "newsound/ambient/cave/cave6.ogg",
                     "newsound/ambient/cave/cave7.ogg",  "newsound/ambient/cave/cave8.ogg",
                     "newsound/ambient/cave/cave9.ogg",  "newsound/ambient/cave/cave10.ogg",
                     "newsound/ambient/cave/cave11.ogg", "newsound/ambient/cave/cave12.ogg",
                     "newsound/ambient/cave/cave13.ogg"],
}

_MUSIC_FILES = [
    "music/calm1.ogg", "music/calm2.ogg", "music/calm3.ogg",
    "newmusic/hal1.ogg", "newmusic/hal2.ogg", "newmusic/hal3.ogg", "newmusic/hal4.ogg",
    "newmusic/nuance1.ogg", "newmusic/nuance2.ogg",
    "newmusic/piano1.ogg",  "newmusic/piano2.ogg",  "newmusic/piano3.ogg",
]

_music_playlist: List[str] = []
_music_idx = 0
_MUSIC_EVENT = pygame.USEREVENT + 1


# ── Synthesis primitives ──────────────────────────────────────────────────────

_rng = np.random.default_rng(42)


def _make(arr: np.ndarray) -> pygame.mixer.Sound:
    arr = np.clip(arr, -1.0, 1.0)
    i16 = (arr * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([i16, i16]))


def _adsr(n: int, a: float, d: float, s_lvl: float, r: float) -> np.ndarray:
    e = np.empty(n, dtype=np.float32)
    ia  = max(1, int(a * n));  id_ = max(1, int(d * n))
    ir  = max(1, int(r * n));  is_ = max(0, n - ia - id_ - ir)
    p = 0
    e[p:p+ia]  = np.linspace(0.0, 1.0, ia);      p += ia
    e[p:p+id_] = np.linspace(1.0, s_lvl, id_);   p += id_
    if is_: e[p:p+is_] = s_lvl;                   p += is_
    e[p:n]     = np.linspace(s_lvl, 0.0, n - p)
    return e


def _chirp(dur: float, f0: float, f1: float, vol: float,
           a=0.005, d=0.5, s=0.0, r=0.1) -> np.ndarray:
    n = int(_RATE * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    phase = np.cumsum(np.linspace(f0, f1, n) / _RATE)
    return np.sin(2 * np.pi * phase) * _adsr(n, a, d, s, r) * vol


def _sine(dur: float, freq: float, vol: float,
          a=0.01, d=0.15, s=0.5, r=0.3) -> np.ndarray:
    n = int(_RATE * dur)
    t = np.linspace(0.0, dur, n, dtype=np.float32)
    return np.sin(2 * np.pi * freq * t) * _adsr(n, a, d, s, r) * vol


# ── Init ─────────────────────────────────────────────────────────────────────

def init():
    global _ready, _music_playlist, _music_idx
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=_RATE, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(32)
        # Load OGG files
        for name, paths in _FILE_MAP.items():
            loaded = []
            for rel in paths:
                p = _RES / rel
                if p.exists():
                    try:
                        loaded.append(pygame.mixer.Sound(str(p)))
                    except Exception:
                        pass
            if loaded:
                _sounds[name] = loaded

        # Procedural fallback for jump (no good OGG exists)
        if "jump" not in _sounds:
            s = _chirp(0.09, 220, 70, 0.30, a=0.005, d=0.55, s=0.0, r=0.1)
            _sounds["jump"] = [_make(s)]

        # Music playlist
        _music_playlist = [str(_RES / f) for f in _MUSIC_FILES
                           if (_RES / f).exists()]
        if _music_playlist:
            random.shuffle(_music_playlist)
            _music_idx = 0
            _start_next_track()

        _ready = True
    except Exception as e:
        _ready = False


def _start_next_track():
    global _music_idx
    if not _music_playlist:
        return
    path = _music_playlist[_music_idx % len(_music_playlist)]
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(_music_vol)
        pygame.mixer.music.play()
        pygame.mixer.music.set_endevent(_MUSIC_EVENT)
    except Exception:
        pass


def on_event(event: pygame.event.Event):
    """Call from main event loop to advance music playlist."""
    if event.type == _MUSIC_EVENT:
        global _music_idx
        _music_idx += 1
        _start_next_track()


def play(name: str, volume: float = 1.0):
    if not _ready:
        return
    variants = _sounds.get(name)
    if not variants:
        return
    s = random.choice(variants)
    s.set_volume(max(0.0, min(1.0, volume)))
    s.play()


def set_music_volume(vol: float):
    global _music_vol
    _music_vol = max(0.0, min(1.0, vol))
    try:
        pygame.mixer.music.set_volume(_music_vol)
    except Exception:
        pass
