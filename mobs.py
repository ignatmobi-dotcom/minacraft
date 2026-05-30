"""Mob entities: zombies, pigs, spiders, skeletons, cows, creepers, villagers."""
from __future__ import annotations
import math
import random
import pygame
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from items import ItemStack, ITEMS

# Physics constants (mirror world.py to avoid circular import)
_TS       = 32
_GRAVITY  = 0.45
_MAX_FALL = 20.0
_FPS      = 60
_EPS      = 0.05

MOB_W = 24
MOB_H = 48

# Per-kind overrides  (width, height)
_MOB_SIZES: dict = {
    "enderman": (20, 96),   # 3 tiles tall, slightly narrow
}

_ENTITY_BASE = Path("resources/Faithful-32x-1.21.11/assets/minecraft/textures/entity")

_PIG_TEX_PATH    = str(_ENTITY_BASE / "pig/temperate_pig.png")
_SPIDER_TEX_PATH = str(_ENTITY_BASE / "spider/spider.png")

_misc_tex_cache: Dict[str, Optional[pygame.Surface]] = {}

def _get_misc_tex(path: str) -> Optional[pygame.Surface]:
    if path not in _misc_tex_cache:
        try:
            _misc_tex_cache[path] = pygame.image.load(path).convert_alpha()
        except Exception:
            _misc_tex_cache[path] = None
    return _misc_tex_cache[path]

def _tex_crop(tex: pygame.Surface, u: int, v: int, w: int, h: int) -> pygame.Surface:
    """Crop using 64-unit base UV; Faithful 32x textures are 2× native size."""
    sc = max(1, tex.get_width() // 64)
    s  = pygame.Surface((w * sc, h * sc), pygame.SRCALPHA)
    s.blit(tex, (0, 0), (u * sc, v * sc, w * sc, h * sc))
    return s


def _draw_pig(screen: pygame.Surface, sx: int, sy: int,
              W: int, H: int, walk_frame: float, facing: int, flash: bool) -> None:
    """Pure pygame side-view pig: rounded body, 4 stubby legs, snout, ears."""
    PINK   = (230, 160, 155)
    BELLY  = (210, 135, 128)
    DARK   = (185, 110, 105)
    SNOUT  = (205, 128, 122)
    EYE    = (25,  15,  15)
    OUT    = (55,  25,  20)

    cx   = sx + W // 2
    base = sy + H

    # Layout: wide short body centered on mob centre
    body_w = 40
    body_h = 16
    leg_h  = 11
    leg_w  = 6

    body_x = cx - body_w // 2
    body_y = base - leg_h - body_h

    # Legs — 4 positions, alternating stride
    swing = math.sin(walk_frame) * 4
    leg_xs = [body_x + 4, body_x + 12, body_x + body_w - 18, body_x + body_w - 10]
    for i, lx in enumerate(leg_xs):
        off = int(swing if i % 2 == 0 else -swing)
        lh  = max(4, leg_h - abs(off))
        ly  = base - lh + max(0, off)
        pygame.draw.rect(screen, DARK, (lx, ly, leg_w, lh))
        pygame.draw.rect(screen, OUT,  (lx, ly, leg_w, lh), 1)

    # Body — slightly rounded via polygon
    bx, by = body_x, body_y
    r = 4
    pygame.draw.rect(screen, PINK,  (bx + r, by,     body_w - 2*r, body_h))
    pygame.draw.rect(screen, PINK,  (bx,     by + r, body_w,       body_h - 2*r))
    for cx2, cy2 in [(bx+r, by+r), (bx+body_w-r-1, by+r),
                     (bx+r, by+body_h-r-1), (bx+body_w-r-1, by+body_h-r-1)]:
        pygame.draw.circle(screen, PINK, (cx2, cy2), r)
    # Belly stripe
    pygame.draw.rect(screen, BELLY, (bx + r, by + body_h//2, body_w - 2*r, body_h//2 - 1))
    # Outline
    pygame.draw.rect(screen, OUT, (bx + r, by,     body_w - 2*r, body_h),       1)
    pygame.draw.rect(screen, OUT, (bx,     by + r, body_w,       body_h - 2*r), 1)

    # Head — square-ish, offset to front
    head_w = 18
    head_h = 16
    head_y = body_y - head_h + 6
    if facing > 0:
        head_x = body_x + body_w - 6
    else:
        head_x = body_x - head_w + 6

    pygame.draw.rect(screen, PINK, (head_x, head_y, head_w, head_h))
    pygame.draw.rect(screen, OUT,  (head_x, head_y, head_w, head_h), 1)

    # Ear
    ear_x = head_x + (2 if facing > 0 else head_w - 7)
    pygame.draw.rect(screen, DARK, (ear_x, head_y - 5, 5, 6))
    pygame.draw.rect(screen, OUT,  (ear_x, head_y - 5, 5, 6), 1)

    # Eye
    eye_x = head_x + (head_w - 6 if facing > 0 else 3)
    pygame.draw.rect(screen, EYE, (eye_x, head_y + 4, 3, 3))
    pygame.draw.rect(screen, (240, 240, 240), (eye_x + 1, head_y + 4, 1, 1))

    # Snout
    sn_w, sn_h = 10, 6
    sn_x = head_x + (head_w - sn_w if facing > 0 else 0)
    sn_y = head_y + head_h - sn_h - 1
    pygame.draw.rect(screen, SNOUT, (sn_x, sn_y, sn_w, sn_h))
    pygame.draw.rect(screen, OUT,   (sn_x, sn_y, sn_w, sn_h), 1)
    # Nostrils
    for nx2 in (sn_x + 2, sn_x + sn_w - 4):
        pygame.draw.rect(screen, OUT, (nx2, sn_y + 1, 2, 2))

    if flash:
        bounds_x = min(body_x, head_x) - 2
        bounds_w = body_w + head_w + 4
        ov = pygame.Surface((bounds_w, body_h + leg_h + head_h + 8), pygame.SRCALPHA)
        ov.fill((255, 60, 60, 120))
        screen.blit(ov, (bounds_x, head_y - 2))


def _draw_spider(screen: pygame.Surface, sx: int, sy: int,
                 W: int, H: int, walk_frame: float, facing: int, flash: bool) -> None:
    """Side-view spider: wide low double-body, 8 jointed legs, red eyes."""
    tex = _get_misc_tex(_SPIDER_TEX_PATH)

    body_h  = H * 3 // 8
    body_y  = sy + H // 5
    abd_w   = W * 3 // 5           # abdomen (rear)
    ceph_w  = W * 2 // 5 + 4      # cephalothorax (front, slightly bigger)
    ceph_h  = body_h + 4

    PURPLE  = (55, 38, 65)
    DARK_P  = (35, 22, 45)
    RED     = (200, 20, 20)
    OUT     = (15, 8, 20)

    # 8 jointed legs (4 per side)
    swing = math.sin(walk_frame) * 0.45
    body_cx = sx + W // 2
    body_cy = body_y + body_h // 2
    n = 4
    for side in (1, -1):
        for i in range(n):
            frac     = i / (n - 1)
            base_ang = math.pi * (0.12 + frac * 0.55)
            ang      = base_ang + (swing if i % 2 == 0 else -swing) * side
            seg_len  = H * 3 // 8

            # First segment (shoulder → knee)
            kx = int(body_cx + math.cos(ang) * side * seg_len * 0.55)
            ky = int(body_cy + math.sin(base_ang) * seg_len * 0.55)
            pygame.draw.line(screen, DARK_P, (body_cx, body_cy), (kx, ky), 2)

            # Second segment (knee → foot), angled down
            foot_ang = ang + 0.6 * side
            fx = int(kx + math.cos(foot_ang) * side * seg_len * 0.6)
            fy = int(ky + math.sin(base_ang + 0.5) * seg_len * 0.55)
            pygame.draw.line(screen, DARK_P, (kx, ky), (fx, fy), 2)

    # Abdomen
    abd_x = (sx + W - abd_w) if facing > 0 else sx
    if tex:
        raw = _tex_crop(tex, 0, 12, 15, 11)
        bs  = pygame.transform.scale(raw, (abd_w, body_h))
        if facing < 0:
            bs = pygame.transform.flip(bs, True, False)
        screen.blit(bs, (abd_x, body_y))
    else:
        pygame.draw.ellipse(screen, PURPLE, (abd_x, body_y, abd_w, body_h))
        pygame.draw.ellipse(screen, OUT,    (abd_x, body_y, abd_w, body_h), 1)

    # Cephalothorax (head+thorax, front)
    cx = (sx - 4) if facing > 0 else (sx + W - ceph_w + 4)
    if tex:
        raw = _tex_crop(tex, 32, 4, 8, 8)
        cs  = pygame.transform.scale(raw, (ceph_w, ceph_h))
        if facing < 0:
            cs = pygame.transform.flip(cs, True, False)
        screen.blit(cs, (cx, body_y - 3))
    else:
        pygame.draw.ellipse(screen, DARK_P, (cx, body_y - 3, ceph_w, ceph_h))
        pygame.draw.ellipse(screen, OUT,    (cx, body_y - 3, ceph_w, ceph_h), 1)

    # Red eyes (4 eyes on cephalothorax)
    ex_base = cx + (ceph_w - 10 if facing > 0 else 4)
    ey      = body_y + 4
    for di in (0, 5):
        pygame.draw.rect(screen, RED, (ex_base + di, ey, 3, 3))
        pygame.draw.rect(screen, RED, (ex_base + di, ey + 5, 3, 3))

    if flash:
        ov = pygame.Surface((W + 8, H), pygame.SRCALPHA)
        ov.fill((255, 60, 60, 130))
        screen.blit(ov, (sx - 4, sy))


# kind → config
_CFG: Dict[str, dict] = {
    "zombie": {
        "hp": 20, "speed": 1.4, "damage": 2,
        "detect": 14, "attack_range": 1.6,
        "drops": [("bone", 0, 2)],
        "body":  (60, 130, 60),  "pants": (30, 65, 30), "head":  (70, 145, 70),
        "hostile": True,
        "tex_path": str(_ENTITY_BASE / "zombie/zombie.png"),
        "tex_legacy": False,
    },
    "pig": {
        "hp": 10, "speed": 1.2, "damage": 0,
        "detect": 0, "attack_range": 0,
        "drops": [("cooked_beef", 1, 2)],
        "body":  (230, 155, 155), "pants": (210, 130, 130), "head": (240, 175, 175),
        "hostile": False,
        "tex_path": None,   # custom quadruped renderer below
    },
    "spider": {
        "hp": 16, "speed": 2.3, "damage": 3,
        "detect": 12, "attack_range": 1.3,
        "drops": [("string", 0, 2)],
        "body":  (65, 48, 78),   "pants": (48, 35, 58),  "head":  (85, 65, 95),
        "hostile": True,
        "tex_path": None,   # custom arachnid renderer below
    },
    "skeleton": {
        "hp": 18, "speed": 1.6, "damage": 2,
        "detect": 18, "attack_range": 1.5,
        "shoot_range": 12.0, "shoot_cd": 2.5, "projectile": "arrow",
        "drops": [("bone", 1, 2), ("arrow", 0, 3)],
        "body":  (210, 210, 210), "pants": (190, 190, 190), "head": (220, 220, 220),
        "hostile": True,
        "tex_path": str(_ENTITY_BASE / "skeleton/skeleton.png"),
        "tex_legacy": True,
    },
    "cow": {
        "hp": 14, "speed": 1.0, "damage": 0,
        "detect": 0, "attack_range": 0,
        "drops": [("beef", 1, 2), ("leather", 0, 1)],
        "body":  (110, 90, 70), "pants": (85, 70, 55), "head": (120, 100, 80),
        "hostile": False,
        "tex_path": None,
    },
    "creeper": {
        "hp": 20, "speed": 1.5, "damage": 0,
        "detect": 10, "attack_range": 0,
        "drops": [("gunpowder", 0, 2)],
        "body":  (55, 100, 55), "pants": (40, 80, 40), "head": (60, 110, 60),
        "hostile": True,
        "tex_path": str(_ENTITY_BASE / "creeper/creeper.png"),
        "tex_legacy": True,
        "fuse_range": 2.5,   # tiles before fusing starts
        "fuse_time":  1.5,   # seconds until explosion
        "explode_power": 5,
    },
    "villager": {
        "hp": 20, "speed": 0.8, "damage": 0,
        "detect": 0, "attack_range": 0,
        "drops": [],
        "body":  (80, 120, 180), "pants": (60, 80, 140), "head": (220, 190, 155),
        "hostile": False,
        "tex_path": str(_ENTITY_BASE / "villager/villager.png"),
        "tex_legacy": False,
    },
    # ── Nether mobs ──────────────────────────────────────────────────────────────
    "piglin": {
        "hp": 16, "speed": 1.8, "damage": 4,
        "detect": 14, "attack_range": 1.8,
        "drops": [("gold_nugget", 0, 3), ("gold_ingot", 0, 1)],
        "body":  (210, 140, 60), "pants": (160, 100, 40), "head": (230, 160, 80),
        "hostile": False,   # neutral — becomes hostile when hurt
        "neutral": True,
        "tex_path": str(_ENTITY_BASE / "piglin/piglin.png"),
        "tex_legacy": False,
    },
    "zombified_piglin": {
        "hp": 20, "speed": 1.5, "damage": 5,
        "detect": 16, "attack_range": 1.8,
        "drops": [("gold_nugget", 0, 2), ("ender_pearl", 0, 1)],
        "body":  (180, 120, 90), "pants": (120, 80, 60), "head": (200, 140, 100),
        "hostile": False,   # neutral — becomes hostile when hurt
        "neutral": True,
        "tex_path": str(_ENTITY_BASE / "piglin/zombified_piglin.png"),
        "tex_legacy": False,
    },
    "enderman": {
        "hp": 40, "speed": 2.2, "damage": 7,
        "detect": 20, "attack_range": 1.5,
        "drops": [("ender_pearl", 1, 2)],
        "body":  (25, 15, 35), "pants": (18, 10, 28), "head": (30, 18, 40),
        "hostile": False,
        "neutral": True,
        "tex_path": str(_ENTITY_BASE / "enderman/enderman.png"),
        "tex_legacy": False,
    },
    "blaze": {
        "hp": 20, "speed": 1.2, "damage": 0,   # ranged only
        "detect": 12, "attack_range": 0,
        "drops": [("blaze_rod", 0, 2), ("blaze_powder", 0, 1)],
        "body":  (220, 140, 40), "pants": (180, 110, 30), "head": (240, 160, 50),
        "hostile": True,
        "flies": True,
        "shoot_range": 10.0,
        "shoot_cd": 3.0,
        "projectile": "fire_charge",
        "tex_path": str(_ENTITY_BASE / "blaze.png"),
        "tex_legacy": True,
    },
    "blaze_boss": {
        "hp": 80, "speed": 1.5, "damage": 0,
        "detect": 18, "attack_range": 0,
        "drops": [("blaze_rod", 3, 6), ("blaze_powder", 2, 4)],
        "body":  (255, 160, 20), "pants": (200, 120, 20), "head": (255, 180, 40),
        "hostile": True,
        "flies": True,
        "shoot_range": 14.0,
        "shoot_cd": 1.5,
        "projectile": "fire_charge",
        "tex_path": str(_ENTITY_BASE / "blaze.png"),
        "tex_legacy": True,
    },
    "ghast": {
        "hp": 10, "speed": 1.0, "damage": 0,
        "detect": 24, "attack_range": 0,
        "drops": [("gunpowder", 0, 2), ("ghast_tear", 0, 1)],
        "body":  (230, 225, 220), "pants": (210, 205, 200), "head": (240, 235, 230),
        "hostile": True,
        "flies": True,
        "shoot_range": 20.0,
        "shoot_cd": 4.0,
        "projectile": "fireball",
        "tex_path": str(_ENTITY_BASE / "ghast/ghast.png"),
        "tex_legacy": False,
        "tex_scale": 4,   # 256×128 → sc=4 but draw at 2× normal size
    },
    "wither": {
        "hp": 300, "speed": 1.0, "damage": 0,
        "detect": 30, "attack_range": 0,
        "drops": [("nether_star", 1, 1)],
        "body":  (30, 30, 40), "pants": (20, 20, 30), "head": (40, 40, 55),
        "hostile": True,
        "flies": True,
        "shoot_range": 22.0,
        "shoot_cd": 2.0,
        "projectile": "wither_skull",
        "tex_path": str(_ENTITY_BASE / "wither/wither.png"),
        "tex_legacy": False,
        "boss": True,
        "boss_name": "Иссушитель",
    },
    # ── Overworld bosses ────────────────────────────────────────────────────────
    "skeleton_king": {
        "hp": 150, "speed": 2.4, "damage": 5,
        "detect": 28, "attack_range": 1.5,
        "shoot_range": 14.0, "shoot_cd": 1.6, "projectile": "arrow",
        "shoot_count": 3, "shoot_spread": 0.28,
        "drops": [("arrow", 18, 28), ("bone", 6, 10),
                  ("diamond", 1, 2),  ("crown_fragment", 0, 1),
                  ("emerald", 2, 4),  ("king_blade", 1, 1)],
        "body":  (210, 210, 215), "pants": (175, 175, 185), "head": (225, 225, 230),
        "hostile": True,
        "boss": True,
        "boss_name": "Скелет-Король",
        "tex_path": str(_ENTITY_BASE / "skeleton/skeleton.png"),
        "tex_legacy": True,
    },
    "forest_golem": {
        "hp": 280, "speed": 1.1, "damage": 12,
        "detect": 22, "attack_range": 2.4,
        "drops": [("oak_log", 16, 24), ("diamond", 1, 3),
                  ("golem_heart", 1, 1), ("emerald", 3, 6)],
        "body":  (88, 108, 72), "pants": (68, 88, 55), "head": (78, 98, 62),
        "hostile": True,
        "boss": True,
        "boss_name": "Лесной Голем",
        "tex_path": None,
    },
    "ender_dragon": {
        "hp": 400, "speed": 2.0, "damage": 10,
        "detect": 60, "attack_range": 3.0,
        "shoot_range": 20.0, "shoot_cd": 3.0, "projectile": "dragon_fireball",
        "drops": [("dragon_egg", 1, 1), ("ender_pearl", 4, 8),
                  ("diamond", 4, 6), ("emerald", 8, 12)],
        "body":  (25, 10, 40), "pants": (20, 8, 32), "head": (30, 12, 48),
        "hostile": True,
        "flies": True,
        "boss": True,
        "boss_name": "Дракон Края",
        "tex_path": None,
    },
}


# ── Entity texture renderer ───────────────────────────────────────────────────

class MobParts:
    """Pre-scaled UV slices from a Minecraft entity texture PNG.

    UV coordinates are in 64-unit base space. Textures in Faithful 32x
    are 128×128 or 128×64 (scale factor 2).

    Legacy (64×32) format: l_arm / l_leg are mirrored from r_arm / r_leg.
    Full (64×64) format  : l_arm / l_leg have their own UV region.
    """

    _CACHE: Dict[str, "MobParts"] = {}

    # UV (u, v, w, h) in 64-unit base space
    _UV_FULL = {
        "head":  (8,  8,  8, 8),
        "body":  (20, 20, 8, 12),
        "r_arm": (44, 20, 4, 12),
        "r_leg": (4,  20, 4, 12),
        "l_arm": (36, 52, 4, 12),
        "l_leg": (20, 52, 4, 12),
    }
    _UV_LEGACY = {
        "head":  (8,  8,  8, 8),
        "body":  (20, 20, 8, 12),
        "r_arm": (44, 20, 4, 12),
        "r_leg": (4,  20, 4, 12),
    }

    def __init__(self, tex: pygame.Surface, legacy: bool):
        tw = tex.get_width()
        sc = max(1, tw // 64)

        uvs = self._UV_LEGACY if legacy else self._UV_FULL

        head_h = MOB_W              # 24
        body_h = MOB_H // 3         # 16
        leg_h  = MOB_H - head_h - body_h  # 8
        lw     = (MOB_W - 6) // 2   # 9

        def crop_scale(u, v, w, h, dw, dh):
            s = pygame.Surface((w * sc, h * sc), pygame.SRCALPHA)
            s.blit(tex, (0, 0), pygame.Rect(u * sc, v * sc, w * sc, h * sc))
            return pygame.transform.scale(s, (dw, dh))

        self.head   = crop_scale(*uvs["head"],  MOB_W, head_h)
        self.body   = crop_scale(*uvs["body"],  MOB_W - 4, body_h)
        self.r_leg  = crop_scale(*uvs["r_leg"], lw, leg_h)

        if legacy:
            self.l_leg = pygame.transform.flip(self.r_leg, True, False)
            self.r_arm = crop_scale(*uvs["r_arm"], 4, body_h)
            self.l_arm = pygame.transform.flip(self.r_arm, True, False)
        else:
            self.l_leg = crop_scale(*uvs["l_leg"], lw, leg_h)
            self.r_arm = crop_scale(*uvs["r_arm"], 4, body_h)
            self.l_arm = crop_scale(*uvs["l_arm"], 4, body_h)

        # Pre-compute flipped versions (for facing left)
        self.head_L  = pygame.transform.flip(self.head,  True, False)
        self.body_L  = pygame.transform.flip(self.body,  True, False)
        self.r_leg_L = pygame.transform.flip(self.l_leg, True, False)
        self.l_leg_L = pygame.transform.flip(self.r_leg, True, False)
        self.r_arm_L = pygame.transform.flip(self.l_arm, True, False)
        self.l_arm_L = pygame.transform.flip(self.r_arm, True, False)

    @classmethod
    def load(cls, path: str, legacy: bool = False) -> Optional["MobParts"]:
        key = f"{path}:{legacy}"
        if key in cls._CACHE:
            return cls._CACHE[key]
        try:
            tex   = pygame.image.load(path).convert_alpha()
            parts = cls(tex, legacy)
            cls._CACHE[key] = parts
            return parts
        except Exception:
            return None


def _load_parts(kind: str) -> Optional[MobParts]:
    cfg = _CFG.get(kind, {})
    p   = cfg.get("tex_path")
    if not p:
        return None
    return MobParts.load(p, legacy=cfg.get("tex_legacy", False))


# ── Projectile ────────────────────────────────────────────────────────────────

@dataclass
class Projectile:
    x:      float
    y:      float
    vx:     float
    vy:     float
    damage: int
    kind:   str     # "fire_charge"|"fireball"|"wither_skull"|"arrow"|"boulder"|"bullet"|"pellet"|"rocket"|"flame_jet"|"eye_of_ender"
    life:   float   # seconds remaining
    owner:  str     # mob kind or "player" that fired it
    hit_terrain: bool = False   # set True when stopped by a solid block

    def _radius(self) -> int:
        if self.kind == "fireball":
            return 10
        if self.kind == "wither_skull":
            return 8
        if self.kind == "boulder":
            return 9
        if self.kind == "bullet":
            return 5
        if self.kind == "arrow":
            return 3
        if self.kind == "dragon_fireball":
            return 12
        if self.kind == "rocket":
            return 6
        if self.kind == "flame_jet":
            return 4
        if self.kind == "eye_of_ender":
            return 5
        if self.kind == "pellet":
            return 3
        return 5


def update_projectile(proj: Projectile, world) -> bool:
    """Move projectile one frame. Returns True while still alive."""
    dt = 1.0 / _FPS
    proj.life -= dt
    if proj.life <= 0:
        return False

    proj.x += proj.vx
    proj.y += proj.vy

    if proj.kind == "wither_skull":
        proj.vy += _GRAVITY * 0.25
    elif proj.kind == "arrow":
        proj.vy += _GRAVITY * 0.5
    elif proj.kind == "boulder":
        proj.vy += _GRAVITY * 0.8
    elif proj.kind == "rocket":
        proj.vy += _GRAVITY * 0.15
    elif proj.kind == "pellet":
        proj.vy += _GRAVITY * 0.6  # drops faster than bullet — short range
    elif proj.kind == "eye_of_ender":
        proj.vy += _GRAVITY * 0.3  # gentle arc
        return True  # passes through terrain

    r  = proj._radius()
    tx = int((proj.x + r) // _TS)
    ty = int((proj.y + r) // _TS)
    if world.is_solid(tx, ty):
        proj.hit_terrain = True
        return False
    return True


_proj_font: Optional[pygame.font.Font] = None  # unused, placeholder


def draw_projectile(screen: pygame.Surface, proj: Projectile,
                    cam_x: float, cam_y: float) -> None:
    r  = proj._radius()
    sx = int(proj.x - cam_x)
    sy = int(proj.y - cam_y)
    sw, sh = screen.get_size()
    if sx + r < 0 or sx - r > sw or sy + r < 0 or sy - r > sh:
        return

    if proj.kind == "pellet":
        # Shotgun buckshot — small orange-yellow dot with faint trail
        spd = math.hypot(proj.vx, proj.vy)
        if spd > 0.1:
            nx, ny = proj.vx / spd, proj.vy / spd
        else:
            nx, ny = 1.0, 0.0
        pygame.draw.line(screen, (200, 140, 60),
                         (int(sx - nx * 3), int(sy - ny * 3)), (sx, sy), 1)
        pygame.draw.circle(screen, (255, 210, 80), (sx, sy), 2)
    elif proj.kind == "bullet":
        # Bright white-yellow tracer — thick for minigun
        spd = math.hypot(proj.vx, proj.vy)
        if spd > 0.1:
            nx, ny = proj.vx / spd, proj.vy / spd
        else:
            nx, ny = 1.0, 0.0
        x0 = int(sx - nx * 8)
        y0 = int(sy - ny * 8)
        x1 = int(sx + nx * 4)
        y1 = int(sy + ny * 4)
        pygame.draw.line(screen, (255, 200, 60),  (x0, y0), (x1, y1), 4)
        pygame.draw.line(screen, (255, 255, 200), (x0, y0), (x1, y1), 2)
        pygame.draw.circle(screen, (255, 255, 240), (sx, sy), 3)
    elif proj.kind == "rocket":
        # Rocket body + exhaust flame
        spd = math.hypot(proj.vx, proj.vy)
        if spd > 0.1:
            nx, ny = proj.vx / spd, proj.vy / spd
        else:
            nx, ny = 1.0, 0.0
        # Tip
        tx_r = int(sx + nx * 8)
        ty_r = int(sy + ny * 8)
        # Body
        bx = int(sx - nx * 5)
        by = int(sy - ny * 5)
        pygame.draw.line(screen, (200, 180, 60),  (bx, by), (tx_r, ty_r), 4)
        pygame.draw.circle(screen, (255, 80, 20), (tx_r, ty_r), 3)
        # Exhaust
        pygame.draw.circle(screen, (255, 140, 30), (bx, by), 4)
        pygame.draw.circle(screen, (255, 240, 60), (bx, by), 2)
    elif proj.kind == "flame_jet":
        # Glowing spinning squares — outer glow → bright mid → white core
        ang = math.radians(proj.life * 720 % 360)   # full spin ~0.5 s
        ca, sa = math.cos(ang), math.sin(ang)

        def _sq(h):
            return [(int(sx + dx * ca - dy * sa), int(sy + dx * sa + dy * ca))
                    for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]

        pygame.draw.polygon(screen, (200,  30,   0), _sq(13))   # outer dark
        pygame.draw.polygon(screen, (255,  90,  10), _sq(10))   # mid orange
        pygame.draw.polygon(screen, (255, 200,  50), _sq( 7))   # inner bright
        pygame.draw.polygon(screen, (255, 255, 200), _sq( 4))   # core white
    elif proj.kind == "arrow":
        # Draw arrow as a short line in direction of travel
        spd = math.hypot(proj.vx, proj.vy)
        if spd > 0.1:
            nx, ny = proj.vx / spd, proj.vy / spd
        else:
            nx, ny = 1.0, 0.0
        x0 = int(sx - nx * 6)
        y0 = int(sy - ny * 6)
        x1 = int(sx + nx * 6)
        y1 = int(sy + ny * 6)
        pygame.draw.line(screen, (160, 120, 60), (x0, y0), (x1, y1), 2)
        pygame.draw.circle(screen, (200, 160, 80), (x1, y1), 2)
    elif proj.kind == "boulder":
        pygame.draw.circle(screen, (95, 85, 75),  (sx, sy), r)
        pygame.draw.circle(screen, (130, 118, 105),(sx, sy), r - 3)
        pygame.draw.circle(screen, (65, 55, 48),   (sx, sy), r, 2)
    elif proj.kind == "fireball":
        pygame.draw.circle(screen, (255, 100, 20), (sx, sy), r)
        pygame.draw.circle(screen, (255, 220, 80), (sx, sy), r // 2)
    elif proj.kind == "wither_skull":
        pygame.draw.circle(screen, (50, 40, 70),   (sx, sy), r)
        pygame.draw.circle(screen, (150, 110, 200),(sx, sy), r // 2)
    elif proj.kind == "dragon_fireball":
        pygame.draw.circle(screen, (80,  20, 120), (sx, sy), r)
        pygame.draw.circle(screen, (200, 60, 255), (sx, sy), r // 2)
        pygame.draw.circle(screen, (255, 200, 255),(sx, sy), max(2, r // 4))
    elif proj.kind == "eye_of_ender":
        ang = math.radians(proj.life * 540 % 360)
        ca, sa = math.cos(ang), math.sin(ang)
        # Spinning green eye orb
        pygame.draw.circle(screen, ( 10,  80,  20), (sx, sy), r + 2)
        pygame.draw.circle(screen, ( 30, 200,  60), (sx, sy), r)
        pygame.draw.circle(screen, (180, 255, 180), (sx, sy), max(2, r // 2))
        # Sparkle dots around the orb
        for i in range(4):
            da = ang + i * math.pi / 2
            ex = int(sx + math.cos(da) * (r + 4))
            ey = int(sy + math.sin(da) * (r + 4))
            pygame.draw.circle(screen, (100, 255, 100), (ex, ey), 2)
    else:  # fire_charge
        pygame.draw.circle(screen, (255, 155, 30), (sx, sy), r)
        pygame.draw.circle(screen, (255, 240, 130),(sx, sy), max(1, r // 2))


# ── Mob dataclass ─────────────────────────────────────────────────────────────

@dataclass
class Mob:
    kind:       str
    x:          float
    y:          float
    vx:         float = 0.0
    vy:         float = 0.0
    hp:         int   = 10
    max_hp:     int   = 10
    facing:     int   = 1
    on_ground:  bool  = False
    walk_frame: float = 0.0
    _ai_t:      float = field(default=0.0,   repr=False)
    _attack_cd: float = field(default=0.0,   repr=False)
    _hurt_t:    float = field(default=0.0,   repr=False)
    _jump_cd:   float = field(default=0.0,   repr=False)
    _fuse_t:    float = field(default=0.0,   repr=False)   # creeper only
    _fusing:    bool  = field(default=False,  repr=False)  # creeper only
    _shoot_cd:  float = field(default=0.0,   repr=False)   # ranged mobs
    extra:      dict  = field(default_factory=dict, repr=False)  # villager profession etc.

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def w(self) -> int:
        return _MOB_SIZES.get(self.kind, (MOB_W, MOB_H))[0]

    @property
    def h(self) -> int:
        return _MOB_SIZES.get(self.kind, (MOB_W, MOB_H))[1]

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def center(self) -> Tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def cfg(self) -> dict:
        return _CFG.get(self.kind, _CFG["zombie"])

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "x": self.x, "y": self.y, "hp": self.hp}
        if self.extra:
            d["extra"] = self.extra
        return d

    @staticmethod
    def from_dict(d: dict) -> "Mob":
        cfg = _CFG.get(d.get("kind", "zombie"), _CFG["zombie"])
        m = Mob(d["kind"], d["x"], d["y"])
        m.hp     = d.get("hp", cfg["hp"])
        m.max_hp = cfg["hp"]
        m.extra  = d.get("extra", {})
        return m


# ── Physics helpers ───────────────────────────────────────────────────────────

def _cx(mob: Mob, world) -> None:
    r = mob.rect
    for ty in range(r.top // _TS, (r.bottom - 1) // _TS + 1):
        if mob.vx > 0:
            tx = r.right // _TS
            if world.is_solid(tx, ty):
                mob.x = tx * _TS - mob.w - _EPS
                mob.vx = 0.0
                r = mob.rect
        elif mob.vx < 0:
            tx = (r.left - 1) // _TS
            if world.is_solid(tx, ty):
                mob.x = (tx + 1) * _TS + _EPS
                mob.vx = 0.0
                r = mob.rect


def _cy(mob: Mob, world) -> None:
    r = mob.rect
    for tx in range(r.left // _TS, (r.right - 1) // _TS + 1):
        if mob.vy > 0:
            ty = r.bottom // _TS
            if world.is_solid(tx, ty):
                tr = pygame.Rect(tx * _TS, ty * _TS, _TS, _TS)
                if r.colliderect(tr):
                    mob.y = ty * _TS - mob.h - _EPS
                    mob.vy = 0.0
                    mob.on_ground = True
                    r = mob.rect
        elif mob.vy < 0:
            ty = (r.top - 1) // _TS
            if world.is_solid(tx, ty):
                tr = pygame.Rect(tx * _TS, ty * _TS, _TS, _TS)
                if r.colliderect(tr):
                    mob.y = (ty + 1) * _TS + _EPS
                    mob.vy = 0.0
                    r = mob.rect


# ── Boss phase logic ──────────────────────────────────────────────────────────

def _update_boss_phase(mob: Mob, cfg: dict, dist_t: float,
                       dx: float, dy: float, dist_px: float,
                       new_projs: List[Projectile]) -> None:
    """Handle phase transitions and special attacks for boss mobs."""
    extra = mob.extra
    dt    = 1.0 / _FPS

    # Phase 1→2 at 50% HP
    if extra.get("phase", 1) == 1 and mob.hp <= mob.max_hp * 0.5:
        extra["phase"] = 2
        extra.setdefault("boss_special_cd", 0.0)

    extra["boss_special_cd"] = max(0.0, extra.get("boss_special_cd", 8.0) - dt)
    mcx, mcy = mob.center

    if mob.kind == "skeleton_king":
        # Phase 2 special: summon 3 skeleton minions every 15 s
        if extra.get("phase", 1) == 2 and extra["boss_special_cd"] <= 0:
            extra["boss_special_cd"] = 15.0
            sq = extra.setdefault("spawn_queue", [])
            for i in range(3):
                sq.append({"kind": "skeleton",
                           "x": mcx + (i - 1) * _TS * 2,
                           "y": mcy - _TS * 2})

    elif mob.kind == "forest_golem":
        if extra.get("phase", 1) == 2:
            # Slow regen
            extra["regen_acc"] = extra.get("regen_acc", 0.0) + dt
            if extra["regen_acc"] >= 1.0:
                extra["regen_acc"] -= 1.0
                mob.hp = min(mob.max_hp, mob.hp + 2)
            # Radial boulder shockwave every 12 s
            if extra["boss_special_cd"] <= 0:
                extra["boss_special_cd"] = 12.0
                for i in range(6):
                    angle = i * (math.pi / 3)
                    new_projs.append(Projectile(
                        x=mcx, y=mcy,
                        vx=math.cos(angle) * 5.0,
                        vy=math.sin(angle) * 5.0,
                        damage=8, kind="boulder", life=4.0,
                        owner="forest_golem",
                    ))

    elif mob.kind == "ender_dragon":
        # Phase 2: spiral volley every 8 s
        if extra.get("phase", 1) == 2 and extra["boss_special_cd"] <= 0:
            extra["boss_special_cd"] = 8.0
            for i in range(8):
                angle = i * (math.pi / 4) + extra.get("spiral_offset", 0.0)
                new_projs.append(Projectile(
                    x=mcx, y=mcy,
                    vx=math.cos(angle) * 6.0,
                    vy=math.sin(angle) * 6.0,
                    damage=12, kind="dragon_fireball", life=5.0,
                    owner="ender_dragon",
                ))
            extra["spiral_offset"] = extra.get("spiral_offset", 0.0) + math.pi / 8


# ── AI update ─────────────────────────────────────────────────────────────────

def update_mob(mob: Mob, world, player_cx: float, player_cy: float
               ) -> Tuple[bool, bool, List[Projectile]]:
    """Update one mob. Returns (attacked_player, did_explode, new_projectiles)."""
    dt         = 1.0 / _FPS
    cfg        = mob.cfg()
    attacked   = False
    exploded   = False
    new_projs: List[Projectile] = []

    mob._hurt_t    = max(0.0, mob._hurt_t    - dt)
    mob._attack_cd = max(0.0, mob._attack_cd - dt)
    mob._jump_cd   = max(0.0, mob._jump_cd   - dt)
    mob._shoot_cd  = max(0.0, mob._shoot_cd  - dt)

    mcx, mcy  = mob.center
    dx        = player_cx - mcx
    dy        = player_cy - mcy
    dist_px   = math.hypot(dx, dy)
    dist_t    = dist_px / _TS

    speed  = cfg["speed"]
    flies  = cfg.get("flies", False)
    # Neutral mobs become hostile when provoked (hit by player)
    is_hostile = cfg["hostile"] or (cfg.get("neutral", False) and mob.extra.get("provoked", False))

    # ── Creeper fuse logic ────────────────────────────────────────────────
    if mob.kind == "creeper":
        fuse_r = cfg.get("fuse_range", 2.5)
        fuse_t = cfg.get("fuse_time", 1.5)
        if dist_t <= fuse_r:
            mob._fusing = True
            mob._fuse_t += dt
            if mob._fuse_t >= fuse_t:
                mob.hp      = 0
                exploded    = True
                mob._fusing = False
                return attacked, exploded, new_projs
        else:
            if mob._fusing:
                mob._fuse_t = max(0.0, mob._fuse_t - dt * 2)
                if mob._fuse_t <= 0:
                    mob._fusing = False

    # ── Boss phase AI ─────────────────────────────────────────────────────
    if cfg.get("boss"):
        _update_boss_phase(mob, cfg, dist_t, dx, dy, dist_px, new_projs)

    # ── Ranged shooting ───────────────────────────────────────────────────
    shoot_range = cfg.get("shoot_range", 0)
    # Phase 2 for skeleton_king: faster, more arrows
    p2 = mob.extra.get("phase", 1) == 2
    if mob.kind == "skeleton_king" and p2:
        shoot_range = shoot_range * 1.3
    if shoot_range > 0 and dist_t <= shoot_range and mob._shoot_cd <= 0:
        mob._shoot_cd = cfg.get("shoot_cd", 3.0) * (0.6 if p2 and mob.kind == "skeleton_king" else 1.0)
        proj_kind  = cfg.get("projectile", "fire_charge")
        proj_speed = 4.0 if proj_kind == "fireball" else 5.0 if proj_kind == "wither_skull" else 7.0
        pdist = dist_px or 1.0
        dmg   = cfg["damage"] if cfg["damage"] > 0 else 4
        shoot_count  = cfg.get("shoot_count", 1) + (2 if p2 and mob.kind == "skeleton_king" else 0)
        shoot_spread = cfg.get("shoot_spread", 0.0)
        base_angle   = math.atan2(dy, dx)
        for i in range(shoot_count):
            if shoot_count > 1:
                angle = base_angle + (i - shoot_count // 2) * shoot_spread
            else:
                angle = base_angle
            new_projs.append(Projectile(
                x=mcx, y=mcy,
                vx=math.cos(angle) * proj_speed,
                vy=math.sin(angle) * proj_speed,
                damage=dmg,
                kind=proj_kind,
                life=6.0,
                owner=mob.kind,
            ))

    # ── Flying mob AI + physics ───────────────────────────────────────────
    if flies:
        if is_hostile and dist_t <= cfg["detect"]:
            if abs(dx) > 4:
                mob.vx    = speed * (1 if dx > 0 else -1)
                mob.facing = 1 if dx > 0 else -1
            else:
                mob.vx = 0.0
            mob.vy = speed * 0.6 * (1 if dy > 0 else -1) if abs(dy) > 16 else 0.0
        else:
            mob._ai_t -= dt
            if mob._ai_t <= 0:
                mob.vx    = speed * 0.4 * random.choice([-1, 0, 0, 1])
                mob.vy    = speed * 0.4 * random.choice([-1, 0, 0, 1])
                mob._ai_t = random.uniform(1.5, 3.0)
            if mob.vx != 0:
                mob.facing = 1 if mob.vx > 0 else -1

        mob.x += mob.vx
        _cx(mob, world)
        mob.y += mob.vy
        mob.x  = max(0.0, min(mob.x, world.width  * _TS - mob.w))
        mob.y  = max(0.0, min(mob.y, world.height * _TS - mob.h))
        if mob.vx != 0:
            mob.walk_frame += 0.16
        else:
            mob.walk_frame = round(mob.walk_frame / math.pi) * math.pi
        return attacked, exploded, new_projs

    # ── Ground mob AI ─────────────────────────────────────────────────────
    if is_hostile and dist_t <= cfg["detect"]:
        mob._ai_t = 0.0
        if abs(dx) > 2:
            mob.vx    = speed * (1 if dx > 0 else -1)
            mob.facing = 1 if dx > 0 else -1
        else:
            mob.vx = 0.0

        if mob.vx != 0 and mob.on_ground and mob._jump_cd <= 0:
            ahead_tx = int((mcx + mob.vx * 4) // _TS)
            ahead_ty = int((mob.y + mob.h * 0.6) // _TS)
            if world.is_solid(ahead_tx, ahead_ty):
                mob.vy        = -8.0
                mob.on_ground = False
                mob._jump_cd  = 0.6

        if cfg["attack_range"] > 0 and dist_t <= cfg["attack_range"] and mob._attack_cd <= 0:
            mob._attack_cd = 1.0
            attacked = True
    else:
        mob._ai_t -= dt
        if mob._ai_t <= 0:
            if random.random() < 0.45:
                mob.vx     = speed * random.choice([-1, 1])
                mob.facing = 1 if mob.vx > 0 else -1
                mob._ai_t  = random.uniform(1.5, 3.5)
            else:
                mob.vx    = 0.0
                mob._ai_t = random.uniform(1.0, 2.5)

        if mob.vx != 0 and mob.on_ground:
            edge_tx = int((mcx + mob.vx * 10) // _TS)
            edge_ty = int((mob.y + mob.h + 4) // _TS)
            if not world.is_solid(edge_tx, edge_ty):
                mob.vx    = -mob.vx
                mob.facing = 1 if mob.vx > 0 else -1
                mob._ai_t  = random.uniform(1.0, 2.0)

    # Ground physics
    if mob.on_ground and mob.vy > 0:
        mob.vy = 0.0
    mob.vy        = min(mob.vy + _GRAVITY, _MAX_FALL)
    mob.on_ground = False

    mob.x += mob.vx
    _cx(mob, world)
    mob.y += mob.vy
    _cy(mob, world)

    mob.x = max(0.0, min(mob.x, world.width  * _TS - mob.w))
    mob.y = max(0.0, min(mob.y, world.height * _TS - mob.h))

    if mob.vx != 0 and mob.on_ground:
        mob.walk_frame += 0.16
    else:
        mob.walk_frame = round(mob.walk_frame / math.pi) * math.pi

    return attacked, exploded, new_projs


# ── Drawing ───────────────────────────────────────────────────────────────────

def _draw_textured(screen: pygame.Surface, parts: MobParts,
                   sx: int, sy: int, W: int, H: int,
                   walk_frame: float, facing: int, flash: bool,
                   fuse_frac: float = 0.0) -> None:
    """Draw a mob using pre-scaled MobParts surfaces."""
    head_h = W
    body_h = H // 3
    leg_h  = H - head_h - body_h
    lw     = (W - 6) // 2
    arm_x_l = sx - 4
    arm_x_r = sx + W

    swing  = math.sin(walk_frame) * min(float(leg_h), 5.0)
    l_off  = int( swing)
    r_off  = int(-swing)

    if facing > 0:
        head_s  = parts.head
        body_s  = parts.body
        ll_s, rl_s = parts.l_leg, parts.r_leg
        la_s, ra_s = parts.l_arm, parts.r_arm
        ll_off, rl_off = l_off, r_off
    else:
        head_s  = parts.head_L
        body_s  = parts.body_L
        ll_s, rl_s = parts.l_leg_L, parts.r_leg_L
        la_s, ra_s = parts.l_arm_L, parts.r_arm_L
        # Swap swing when facing left so forward leg stays correct
        ll_off, rl_off = r_off, l_off

    ly = sy + head_h + body_h

    # Legs
    screen.blit(ll_s, (sx + 2,            ly + max(0, ll_off)))
    screen.blit(rl_s, (sx + 2 + lw + 2,   ly + max(0, rl_off)))

    # Arms (alongside body)
    screen.blit(la_s, (arm_x_l if facing > 0 else arm_x_r, sy + head_h))
    screen.blit(ra_s, (arm_x_r if facing > 0 else arm_x_l, sy + head_h))

    # Body
    screen.blit(body_s, (sx + 2, sy + head_h))

    # Head
    screen.blit(head_s, (sx, sy))

    # Hurt flash
    if flash:
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((255, 60, 60, 130))
        screen.blit(overlay, (sx, sy))

    # Creeper fuse flicker (blink white)
    if fuse_frac > 0.0:
        alpha = int(160 * fuse_frac * (0.5 + 0.5 * math.sin(fuse_frac * 30)))
        if alpha > 0:
            fuse_surf = pygame.Surface((W, H), pygame.SRCALPHA)
            fuse_surf.fill((255, 255, 255, alpha))
            screen.blit(fuse_surf, (sx, sy))


def _draw_skeleton_king(screen: pygame.Surface, sx: int, sy: int,
                        W: int, H: int, walk_frame: float, facing: int,
                        flash: bool, phase: int) -> None:
    """Skeleton King: 1.5× scale skeleton with gold crown and glowing red eyes."""
    BW = int(W * 1.5)
    BH = int(H * 1.5)
    bsx = sx - (BW - W) // 2
    bsy = sy - (BH - H)

    BONE  = (255, 120, 120) if flash else (230, 225, 210)
    DARK  = (160, 155, 140)
    OUT   = (60,  55,  45)
    GOLD  = (255, 200, 50)
    RED   = (220, 30,  30)

    head_h = BW
    body_h = BH // 3
    leg_h  = BH - head_h - body_h
    lw     = (BW - 6) // 2

    swing = math.sin(walk_frame) * 6.0
    ly    = bsy + head_h + body_h
    for i, x_off in enumerate([2, 2 + lw + 2]):
        off = int(swing if i == 0 else -swing)
        hh  = max(2, leg_h - abs(off))
        yy  = ly + max(0, off)
        pygame.draw.rect(screen, DARK, (bsx + x_off, yy, lw, hh))
        pygame.draw.rect(screen, OUT,  (bsx + x_off, yy, lw, hh), 1)

    # Ribcage body
    pygame.draw.rect(screen, BONE, (bsx + 2, bsy + head_h, BW - 4, body_h))
    for rib in range(3):
        ry = bsy + head_h + 3 + rib * (body_h // 3)
        pygame.draw.line(screen, DARK, (bsx + 4, ry), (bsx + BW - 5, ry), 1)
    pygame.draw.rect(screen, OUT, (bsx + 2, bsy + head_h, BW - 4, body_h), 1)

    # Skull head
    pygame.draw.rect(screen, BONE, (bsx, bsy, BW, head_h))
    pygame.draw.rect(screen, OUT,  (bsx, bsy, BW, head_h), 1)

    # Eye socket with red glow
    ey = bsy + head_h // 3
    ex = bsx + (BW * 2 // 3 - 3 if facing > 0 else BW // 6)
    pygame.draw.rect(screen, RED, (ex, ey, 5, 4))

    # Jaw line
    jaw_y = bsy + head_h * 3 // 4
    pygame.draw.line(screen, DARK, (bsx + 3, jaw_y), (bsx + BW - 4, jaw_y), 1)

    # Gold crown
    pts = [
        (bsx + 2,        bsy),
        (bsx + 2,        bsy - 6),
        (bsx + BW // 4,  bsy - 10),
        (bsx + BW // 2,  bsy - 5),
        (bsx + BW * 3 // 4, bsy - 10),
        (bsx + BW - 2,   bsy - 6),
        (bsx + BW - 2,   bsy),
    ]
    pygame.draw.polygon(screen, GOLD, pts)
    pygame.draw.polygon(screen, OUT,  pts, 1)

    # Phase 2: crimson aura
    if phase == 2:
        aura = pygame.Surface((BW + 10, BH + 10), pygame.SRCALPHA)
        aura.fill((200, 0, 0, 30))
        screen.blit(aura, (bsx - 5, bsy - 5))


def _draw_forest_golem(screen: pygame.Surface, sx: int, sy: int,
                       W: int, H: int, walk_frame: float, facing: int,
                       flash: bool, phase: int) -> None:
    """Forest Golem: 2× hulking stone body with mossy patches and glowing eyes."""
    BW = int(W * 2.0)
    BH = int(H * 2.0)
    bsx = sx - (BW - W) // 2
    bsy = sy - (BH - H)

    STONE = (200, 100, 100) if flash else (110, 110, 100)
    DARK  = (70,  70,  65)
    MOSS  = (55,  120,  45)
    OUT   = (30,  30,  25)
    GLOW  = (255, 80, 40) if phase == 2 else (80, 200, 60)

    head_h = BW
    body_h = BH // 3
    leg_h  = BH - head_h - body_h
    lw     = (BW - 8) // 2

    swing = math.sin(walk_frame) * 5.0
    ly    = bsy + head_h + body_h
    for i, x_off in enumerate([3, 3 + lw + 2]):
        off = int(swing if i == 0 else -swing)
        hh  = max(2, leg_h - abs(off))
        yy  = ly + max(0, off)
        pygame.draw.rect(screen, DARK,  (bsx + x_off, yy, lw, hh))
        pygame.draw.rect(screen, OUT,   (bsx + x_off, yy, lw, hh), 1)

    # Wide stone torso with moss patches
    pygame.draw.rect(screen, STONE, (bsx + 3, bsy + head_h, BW - 6, body_h))
    pygame.draw.rect(screen, MOSS,  (bsx + 6,        bsy + head_h + 3,  9,  6))
    pygame.draw.rect(screen, MOSS,  (bsx + BW - 16,  bsy + head_h + 8, 10,  7))
    pygame.draw.rect(screen, OUT,   (bsx + 3, bsy + head_h, BW - 6, body_h), 2)

    # Square head
    pygame.draw.rect(screen, STONE, (bsx, bsy, BW, head_h))
    pygame.draw.rect(screen, MOSS,  (bsx + 4, bsy + head_h - 7, 14, 7))  # moss cap
    pygame.draw.rect(screen, OUT,   (bsx, bsy, BW, head_h), 2)

    # Stone crack
    pygame.draw.line(screen, DARK, (bsx + 4, bsy + 4), (bsx + 12, bsy + head_h // 2), 1)

    # Glowing eyes
    ey = bsy + head_h // 3
    ex = bsx + (BW * 2 // 3 - 4 if facing > 0 else BW // 5)
    pygame.draw.rect(screen, GLOW, (ex, ey, 7, 5))

    # Phase 2: green ember aura
    if phase == 2:
        aura = pygame.Surface((BW + 14, BH + 14), pygame.SRCALPHA)
        aura.fill((0, 160, 30, 28))
        screen.blit(aura, (bsx - 7, bsy - 7))


def _draw_ender_dragon(screen: pygame.Surface, sx: int, sy: int,
                       W: int, H: int, walk_frame: float, facing: int,
                       flash: bool, phase: int) -> None:
    """Ender Dragon — large winged serpentine body, pure pygame."""
    BW = int(W * 3.5)
    BH = int(H * 2.2)
    bsx = sx - (BW - W) // 2
    bsy = sy - (BH - H)

    PURPLE = (255, 80, 80) if flash else (60, 20, 90)
    DARK   = (35, 10, 55)
    WING   = (40, 15, 65)
    WING_M = (25, 8,  45)
    EYE    = (255, 60, 0) if phase == 2 else (200, 255, 60)
    OUT    = (15, 5, 25)

    cx = bsx + BW // 2
    cy = bsy + BH // 2

    # Wings — triangular membranes
    wing_bob = math.sin(walk_frame * 2) * 12
    # Left wing
    lw_pts = [
        (cx, cy - 5),
        (bsx - 20, cy - 30 + int(wing_bob)),
        (bsx - 5,  cy + 15),
    ]
    pygame.draw.polygon(screen, WING, lw_pts)
    pygame.draw.polygon(screen, WING_M, lw_pts, 2)
    # Right wing
    rw_pts = [
        (cx, cy - 5),
        (bsx + BW + 20, cy - 30 + int(wing_bob)),
        (bsx + BW + 5,  cy + 15),
    ]
    pygame.draw.polygon(screen, WING, rw_pts)
    pygame.draw.polygon(screen, WING_M, rw_pts, 2)

    # Body — long oval
    body_rect = pygame.Rect(bsx + 10, cy - 14, BW - 20, 28)
    pygame.draw.ellipse(screen, PURPLE, body_rect)
    pygame.draw.ellipse(screen, OUT,    body_rect, 2)

    # Head
    head_x = bsx + (BW - 26) if facing > 0 else bsx
    head_y = cy - 20
    pygame.draw.rect(screen, DARK,   (head_x, head_y, 26, 20))
    pygame.draw.rect(screen, OUT,    (head_x, head_y, 26, 20), 1)
    # Snout
    snout_x = head_x + (18 if facing > 0 else -6)
    pygame.draw.rect(screen, DARK,   (snout_x, head_y + 10, 8, 10))
    # Eye
    eye_x = head_x + (14 if facing > 0 else 4)
    pygame.draw.rect(screen, EYE,    (eye_x, head_y + 5, 6, 5))

    # Tail segments
    for i in range(1, 5):
        t    = i / 5.0
        tsz  = int(14 * (1 - t * 0.6))
        tail_x = cx + int((BW * 0.3 * (-1 if facing > 0 else 1)) * t)
        tail_y = cy + int(math.sin(walk_frame + i) * 6)
        pygame.draw.circle(screen, PURPLE, (tail_x, tail_y), tsz)

    # Phase 2: crackling purple aura
    if phase == 2:
        aura = pygame.Surface((BW + 50, BH + 50), pygame.SRCALPHA)
        aura.fill((100, 0, 120, 25))
        screen.blit(aura, (bsx - 25, bsy - 25))


_boss_bar_font: Optional[pygame.font.Font] = None


def draw_boss_bar(screen: pygame.Surface, mob: Mob) -> None:
    """Draw boss HP bar at top-center of screen."""
    global _boss_bar_font
    if _boss_bar_font is None:
        _boss_bar_font = pygame.font.SysFont(None, 22)
    sw = screen.get_width()
    bw  = min(sw - 80, 500)
    bx  = (sw - bw) // 2
    by  = 18
    bh  = 18
    hp_r  = mob.hp / max(1, mob.max_hp)
    phase = mob.extra.get("phase", 1)

    pygame.draw.rect(screen, (20, 10, 10), (bx - 2, by - 2, bw + 4, bh + 4))
    fill_col = (200, 30, 180) if phase == 2 else (200, 50, 50)
    pygame.draw.rect(screen, fill_col, (bx, by, max(1, int(bw * hp_r)), bh))
    pygame.draw.rect(screen, (180, 140, 60), (bx - 2, by - 2, bw + 4, bh + 4), 2)

    name = mob.cfg().get("boss_name", mob.kind)
    lbl  = _boss_bar_font.render(name, True, (240, 220, 160))
    screen.blit(lbl, (sw // 2 - lbl.get_width() // 2, by + bh + 3))


def draw_mob(screen: pygame.Surface, mob: Mob, cam_x: float, cam_y: float) -> None:
    sx = int(mob.x - cam_x)
    sy = int(mob.y - cam_y)
    W, H = mob.w, mob.h

    # Culling
    sw, sh = screen.get_size()
    if sx + W < 0 or sx > sw or sy + H < 0 or sy > sh:
        return

    cfg   = mob.cfg()
    flash = mob._hurt_t > 0

    # Custom renderers
    phase = mob.extra.get("phase", 1)
    if mob.kind == "skeleton_king":
        _draw_skeleton_king(screen, sx, sy, MOB_W, MOB_H, mob.walk_frame, mob.facing, flash, phase)
    elif mob.kind == "forest_golem":
        _draw_forest_golem(screen, sx, sy, MOB_W, MOB_H, mob.walk_frame, mob.facing, flash, phase)
    elif mob.kind == "ender_dragon":
        _draw_ender_dragon(screen, sx, sy, MOB_W, MOB_H, mob.walk_frame, mob.facing, flash, phase)
    elif mob.kind == "pig":
        _draw_pig(screen, sx, sy, MOB_W, MOB_H, mob.walk_frame, mob.facing, flash)
    elif mob.kind == "spider":
        _draw_spider(screen, sx, sy, MOB_W, MOB_H, mob.walk_frame, mob.facing, flash)
    elif mob.kind == "enderman":
        _draw_enderman(screen, sx, sy, W, H, mob.walk_frame, mob.facing, flash)
    else:
        # Try entity texture first
        parts = _load_parts(mob.kind)
        if parts is not None:
            fuse_frac = (mob._fuse_t / cfg.get("fuse_time", 1.5)) if mob._fusing else 0.0
            _draw_textured(screen, parts, sx, sy, W, H,
                           mob.walk_frame, mob.facing, flash, fuse_frac)
        else:
            _draw_procedural(screen, mob, sx, sy, W, H, cfg, flash)

    # HP bar above mob
    bar_y = sy - 7
    hp_r  = mob.hp / max(1, mob.max_hp)
    hp_col = (50, 200, 50) if hp_r > 0.6 else (200, 200, 30) if hp_r > 0.3 else (200, 50, 30)
    pygame.draw.rect(screen, (30, 15, 15),  (sx, bar_y, W, 3))
    pygame.draw.rect(screen, hp_col, (sx, bar_y, max(1, int(W * hp_r)), 3))

    # Villager name tag
    if mob.kind == "villager":
        _draw_villager_tag(screen, mob, sx, sy, W)


def _draw_enderman(screen, sx, sy, W, H, walk_frame, facing, flash):
    """Tall, slender enderman — 3 tiles high with glowing purple eyes."""
    col_body = (255, 120, 255) if flash else (15, 8, 20)
    col_eyes = (120, 0, 200)
    col_out  = (60, 0, 100)

    # proportions: tiny head (W×W), slim body (~W×H//2), long legs
    head_w = W
    head_h = W
    body_h = H // 4
    leg_h  = H - head_h - body_h
    leg_w  = max(3, W // 4)
    gap    = 2

    swing  = math.sin(walk_frame) * 7.0
    l_off  = int( swing)
    r_off  = int(-swing)

    # Legs
    lx = sx + (W - leg_w * 2 - gap) // 2
    rx = lx + leg_w + gap
    ly = sy + head_h + body_h
    for x, off in ((lx, l_off), (rx, r_off)):
        yy = ly + max(0, off)
        hh = max(2, leg_h - abs(off))
        pygame.draw.rect(screen, col_body, (x, yy, leg_w, hh))
        pygame.draw.rect(screen, col_out,  (x, yy, leg_w, hh), 1)

    # Slim body
    bx = sx + (W - max(4, W // 2)) // 2
    bw = max(4, W // 2)
    pygame.draw.rect(screen, col_body, (bx, sy + head_h, bw, body_h))
    pygame.draw.rect(screen, col_out,  (bx, sy + head_h, bw, body_h), 1)

    # Arms (very long thin)
    arm_w = max(2, W // 5)
    arm_h = leg_h + body_h // 2
    lax = bx - arm_w - 1
    rax = bx + bw + 1
    ay  = sy + head_h + 1
    pygame.draw.rect(screen, col_body, (lax, ay, arm_w, arm_h))
    pygame.draw.rect(screen, col_out,  (lax, ay, arm_w, arm_h), 1)
    pygame.draw.rect(screen, col_body, (rax, ay, arm_w, arm_h))
    pygame.draw.rect(screen, col_out,  (rax, ay, arm_w, arm_h), 1)

    # Head
    pygame.draw.rect(screen, col_body, (sx, sy, head_w, head_h))
    pygame.draw.rect(screen, col_out,  (sx, sy, head_w, head_h), 1)

    # Glowing purple eyes
    ey = sy + head_h // 3
    if facing > 0:
        pygame.draw.rect(screen, col_eyes, (sx + head_w * 3 // 5, ey, 4, 3))
        pygame.draw.rect(screen, col_eyes, (sx + head_w * 3 // 5 + 5, ey, 4, 3))
    else:
        pygame.draw.rect(screen, col_eyes, (sx + head_w // 5 - 2, ey, 4, 3))
        pygame.draw.rect(screen, col_eyes, (sx + head_w // 5 + 3, ey, 4, 3))


def _draw_procedural(screen, mob, sx, sy, W, H, cfg, flash):
    """Fallback solid-color mob drawing for kinds without entity textures."""
    body_col  = (255, 90, 90)   if flash else cfg["body"]
    pants_col = (220, 70, 70)   if flash else cfg["pants"]
    head_col  = (255, 110, 110) if flash else cfg["head"]
    out_col   = (15, 8, 8)

    head_h = W
    body_h = H // 3
    leg_h  = H - head_h - body_h
    lw     = (W - 6) // 2

    swing = math.sin(mob.walk_frame) * 5.0
    l_off = int( swing)
    r_off = int(-swing)

    ly = sy + head_h + body_h
    for x_off, off in [(2, l_off), (2 + lw + 2, r_off)]:
        yy = ly + max(0, off)
        hh = max(2, leg_h - abs(off))
        pygame.draw.rect(screen, pants_col, (sx + x_off, yy, lw, hh))
        pygame.draw.rect(screen, out_col,   (sx + x_off, yy, lw, hh), 1)

    pygame.draw.rect(screen, body_col,  (sx + 2, sy + head_h, W - 4, body_h))
    pygame.draw.rect(screen, out_col,   (sx + 2, sy + head_h, W - 4, body_h), 1)
    pygame.draw.rect(screen, head_col, (sx, sy, W, head_h))
    pygame.draw.rect(screen, out_col,  (sx, sy, W, head_h), 1)

    ey = sy + head_h // 3
    if mob.kind == "pig":
        ex = sx + (W * 2 // 3 - 2 if mob.facing > 0 else W // 6)
        pygame.draw.rect(screen, (20, 10, 10), (ex, ey, 3, 3))
        sx2 = sx + (W * 3 // 4 - 4 if mob.facing > 0 else 2)
        pygame.draw.rect(screen, (205, 135, 135), (sx2, sy + head_h * 2 // 3, 8, 5))
        pygame.draw.rect(screen, out_col,          (sx2, sy + head_h * 2 // 3, 8, 5), 1)
    elif mob.kind == "spider":
        for ei in range(2):
            offset = ei * 5
            ex = sx + (W * 2 // 3 - 2 + offset if mob.facing > 0 else W // 6 + offset)
            pygame.draw.rect(screen, (220, 20, 20), (ex, ey, 3, 3))
    elif mob.kind == "cow":
        ex = sx + (W * 2 // 3 - 2 if mob.facing > 0 else W // 6)
        pygame.draw.rect(screen, (30, 20, 10), (ex, ey, 4, 4))
        hx = sx + (W * 2 // 3 if mob.facing > 0 else W // 6 - 3)
        pygame.draw.line(screen, (230, 215, 185), (hx, sy + 2), (hx + 2, sy - 4), 2)
        pygame.draw.ellipse(screen, (230, 185, 190),
                            (sx + W // 4, sy + head_h + body_h, W // 2, leg_h // 3))


_vtag_font: Optional[pygame.font.Font] = None

def _draw_villager_tag(screen, mob, sx, sy, W):
    global _vtag_font
    if _vtag_font is None:
        _vtag_font = pygame.font.SysFont(None, 14)
    prof = mob.extra.get("profession", "farmer")
    labels = {"farmer": "Фермер", "smith": "Кузнец", "librarian": "Библиотекарь",
              "weaponsmith": "Оружейник", "mason": "Каменщик",
              "cleric": "Жрец", "butcher": "Мясник", "fletcher": "Лучник"}
    lbl = _vtag_font.render(labels.get(prof, prof), True, (255, 255, 180))
    lx = sx + W // 2 - lbl.get_width() // 2
    ly = sy - 14
    bg = pygame.Surface((lbl.get_width() + 4, lbl.get_height() + 2), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 140))
    screen.blit(bg, (lx - 2, ly - 1))
    screen.blit(lbl, (lx, ly))


# ── Spawning ──────────────────────────────────────────────────────────────────

_PROFESSIONS = ["farmer", "smith", "librarian", "weaponsmith", "mason",
                "cleric", "butcher", "fletcher"]


def spawn_mobs(world) -> List[Mob]:
    """Place initial mobs across the world at spawn time."""
    mobs: List[Mob] = []
    targets = {
        "pig": 16, "cow": 8,
        "zombie": 10, "spider": 6, "skeleton": 6,
        "creeper": 6, "villager": 10, "enderman": 4,
    }

    for kind, count in targets.items():
        spawned  = 0
        attempts = 0
        while spawned < count and attempts < count * 30:
            attempts += 1
            tx = random.randint(15, world.width - 15)

            for ty in range(world.height):
                tile = world.get(tx, ty)
                if tile is None or tile in ("water", "oak_leaves"):
                    continue
                cx = world.width // 2
                # Hostile mobs away from spawn
                if kind in ("zombie", "spider", "skeleton", "creeper", "enderman") \
                        and abs(tx - cx) < 40:
                    break
                # Villagers near the centre (villages are near centre-ish)
                if kind == "villager" and abs(tx - cx) > world.width // 3:
                    break
                x = float(tx * _TS + (_TS - MOB_W) // 2)
                y = float(ty * _TS - MOB_H - 1)
                cfg = _CFG[kind]
                m = Mob(kind, x, y, hp=cfg["hp"], max_hp=cfg["hp"])
                m.facing = random.choice([-1, 1])
                m._ai_t  = random.uniform(0, 3)
                if kind == "villager":
                    m.extra["profession"] = random.choice(_PROFESSIONS)
                mobs.append(m)
                spawned += 1
                break

    return mobs


def spawn_nether_mobs(world) -> List[Mob]:
    """Place initial mobs in the nether dimension."""
    mobs: List[Mob] = []
    targets = {"piglin": 10, "zombified_piglin": 12, "blaze": 14, "ghast": 4, "enderman": 6}

    # Blaze zones — fortress X centers where blazes congregate (70% of spawns)
    _blaze_zones: list = getattr(world, "_blaze_zone_xs", [])
    _blaze_zone_radius = 120  # tiles around each fortress center

    for kind, count in targets.items():
        cfg     = _CFG[kind]
        flies   = cfg.get("flies", False)
        spawned = 0
        attempts = 0
        while spawned < count and attempts < count * 60:
            attempts += 1

            # Blazes: 70 % of the time pick an X near a fortress
            if kind == "blaze" and _blaze_zones and random.random() < 0.70:
                zone_cx = random.choice(_blaze_zones)
                half = min(_blaze_zone_radius, zone_cx - 10,
                           world.width - 10 - zone_cx)
                half = max(10, half)
                tx = random.randint(max(10, zone_cx - half),
                                    min(world.width - 10, zone_cx + half))
            else:
                tx = random.randint(20, world.width - 20)

            if flies:
                # Find open air in the blaze-tower height range (upper half)
                y_top = world.height // 5
                y_bot = world.height * 3 // 5   # prefer upper zone for blazes
                for ty in range(y_top, y_bot):
                    if world.get(tx, ty) is None:
                        x = float(tx * _TS + (_TS - MOB_W) // 2)
                        y = float(ty * _TS + (_TS - MOB_H) // 2)
                        m = Mob(kind, x, y, hp=cfg["hp"], max_hp=cfg["hp"])
                        m.facing = random.choice([-1, 1])
                        m._ai_t  = random.uniform(0, 3)
                        mobs.append(m)
                        spawned += 1
                        break
            else:
                # Ground mob — find netherrack/nether_brick floor
                for ty in range(world.height // 5, world.height - 5):
                    tile  = world.get(tx, ty)
                    below = world.get(tx, ty + 1)
                    if tile is None and below in ("netherrack", "nether_brick",
                                                   "basalt", "bedrock"):
                        x = float(tx * _TS + (_TS - MOB_W) // 2)
                        y = float(ty * _TS - MOB_H - 1)
                        m = Mob(kind, x, y, hp=cfg["hp"], max_hp=cfg["hp"])
                        m.facing = random.choice([-1, 1])
                        m._ai_t  = random.uniform(0, 3)
                        mobs.append(m)
                        spawned += 1
                        break

    return mobs


def spawn_end_mobs(world) -> List[Mob]:
    """Spawn Ender Dragon + endermen across the End arena."""
    mobs: List[Mob] = []
    cx = world.width  // 2
    cy = world.height // 2 - 10

    cfg = _CFG["ender_dragon"]
    dragon = Mob("ender_dragon",
                 float(cx * _TS - MOB_W // 2),
                 float(cy * _TS - MOB_H // 2),
                 hp=cfg["hp"], max_hp=cfg["hp"])
    dragon.extra["phase"] = 1
    dragon.facing = -1
    mobs.append(dragon)

    # Scatter endermen across the floating islands
    ecfg    = _CFG["enderman"]
    arena_y = world.height // 2  # approximate surface row
    spawned = 0
    attempts = 0
    while spawned < 10 and attempts < 400:
        attempts += 1
        tx = random.randint(cx - 60, cx + 60)
        if tx < 0 or tx >= world.width:
            continue
        for ty in range(max(0, arena_y - 20), min(world.height - 1, arena_y + 20)):
            tile  = world.get(tx, ty)
            below = world.get(tx, ty + 1)
            if tile is None and below in ("end_stone", "purpur_block", "obsidian"):
                x = float(tx * _TS + (_TS - MOB_W) // 2)
                y = float(ty * _TS - MOB_H - 1)
                m = Mob("enderman", x, y, hp=ecfg["hp"], max_hp=ecfg["hp"])
                m.facing = random.choice([-1, 1])
                m._ai_t  = random.uniform(0, 3)
                mobs.append(m)
                spawned += 1
                break

    return mobs
