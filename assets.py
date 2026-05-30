"""
Texture loading, scaling, and caching.

All textures come from the Faithful-32x Minecraft resource pack bundled in
resources/.  When a texture file is missing the module generates a procedural
pixel-art fallback so the game never crashes on a missing asset.

Usage (after pygame.init()):
    surf = load_texture("item/stick", 32)
    surf = load_texture("block/stone", 32)
    surf = get_item_texture("iron_sword", 40)
"""
import os
import sys
import math
import hashlib
import pygame
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

def _pkg_dir() -> str:
    """Return the directory that contains bundled resources.
    Works both when running from source and when frozen by PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS          # PyInstaller temp-extract dir
    return os.path.dirname(os.path.abspath(__file__))

_PKG = _pkg_dir()

_BASE = os.path.join(
    _PKG,
    "resources", "Faithful-32x-1.21.11",
    "assets", "minecraft", "textures"
)

# Custom texture directories checked after the Faithful pack lookup fails.
# resources/custom/ — user-supplied PNGs (firearms etc.), named by item_id
# generated_textures/ — AI-generated textures created by image_gen.py
_CUSTOM_DIR = os.path.join(_PKG, "resources", "custom")
_GEN_DIR    = os.path.join(_PKG, "generated_textures")

# ── Fallback colours keyed by semantic tag ────────────────────────────────────

_TAG_COLORS: dict[str, tuple] = {
    "wood":       (139, 90,  43),
    "stone":      (120, 120, 120),
    "metal":      (180, 180, 190),
    "iron":       (190, 190, 205),
    "copper":     (184, 115,  51),
    "gold":       (255, 200,   0),
    "diamond":    ( 84, 214, 238),
    "gem":        (150,  80, 200),
    "organic":    (160, 100,  50),
    "food":       (220, 140,  50),
    "fuel":       ( 50,  50,  50),
    "carbon":     ( 40,  40,  40),
    "earth":      ( 90,  60,  30),
    "tool":       (170, 170, 170),
    "weapon":     (200,  70,  70),
    "armor":      (110, 130, 170),
    "magic":      (170,  60, 220),
    "explosive":  (180,  80,  20),
}

# ── Internal cache ────────────────────────────────────────────────────────────

_cache: dict[tuple, pygame.Surface] = {}

# ── Texture aliases (for non-standard names) ─────────────────────────────────

_ALIASES: dict[str, str] = {
    "item/cooked_beef": "item/beef",      # just in case
}


# ── Private helpers ───────────────────────────────────────────────────────────

def _read(path: str) -> Optional[pygame.Surface]:
    """Load a .png and return the first square frame (handles animated sheets)."""
    if not os.path.exists(path):
        return None
    try:
        surf = pygame.image.load(path).convert_alpha()
        w, h = surf.get_size()
        if h > w:                          # animated texture: frames stacked vertically
            surf = surf.subsurface((0, 0, w, w)).copy()
        return surf
    except Exception:
        return None


def _color_for_name(name: str) -> tuple:
    """Pick a fallback colour by scanning the item name for known keywords."""
    name_lower = name.lower()
    for tag, col in _TAG_COLORS.items():
        if tag in name_lower:
            return col
    return (100, 100, 100)


_TAG_COLOR_PRIORITY = [
    "diamond", "gold", "copper", "iron", "metal",
    "magic", "gem", "weapon", "armor", "food",
    "wood", "stone", "fuel", "carbon", "earth",
]


def _color_for_tags(tags: frozenset) -> tuple:
    """Pick a fallback colour from item tags (used when name scan fails)."""
    for tag in _TAG_COLOR_PRIORITY:
        if tag in tags:
            col = _TAG_COLORS.get(tag)
            if col:
                return col
    return (100, 100, 100)


# ── 8×8 pixel-art silhouettes (row bitmaps, MSB = left) ──────────────────────

_SHAPE_PICKAXE = [
    0b00000110,
    0b00001111,
    0b11111100,
    0b11111000,
    0b00011000,
    0b00001100,
    0b00000110,
    0b00000011,
]
_SHAPE_SWORD = [
    0b00000110,
    0b00000110,
    0b00000110,
    0b00000110,
    0b00000110,
    0b00011110,
    0b00001100,
    0b00000000,
]
_SHAPE_AXE = [
    0b00111110,
    0b01111110,
    0b11110100,
    0b11100100,
    0b00000110,
    0b00000111,
    0b00000011,
    0b00000001,
]
_SHAPE_SHOVEL = [
    0b00011000,
    0b00111100,
    0b00111100,
    0b00111100,
    0b00011000,
    0b00011000,
    0b00011000,
    0b00011000,
]
_SHAPE_BOW = [
    0b01100000,
    0b11010000,
    0b10001100,
    0b10000110,
    0b10001100,
    0b11010000,
    0b01100000,
    0b00000000,
]
_SHAPE_HELMET = [
    0b00111100,
    0b01111110,
    0b11111111,
    0b11111111,
    0b11000011,
    0b10000001,
    0b00000000,
    0b00000000,
]
_SHAPE_CHESTPLATE = [
    0b11000011,
    0b11111111,
    0b01111110,
    0b01111110,
    0b01111110,
    0b01111110,
    0b01111110,
    0b01111110,
]
_SHAPE_LEGGINGS = [
    0b01111110,
    0b01111110,
    0b01111110,
    0b01100110,
    0b01100110,
    0b01100110,
    0b01100110,
    0b01100110,
]
_SHAPE_BOOTS = [
    0b00000000,
    0b00000000,
    0b01100110,
    0b01100110,
    0b01100110,
    0b11111111,
    0b11111111,
    0b11000011,
]
_SHAPE_ORB = [
    0b00111100,
    0b01111110,
    0b11111111,
    0b11111111,
    0b11111111,
    0b11111111,
    0b01111110,
    0b00111100,
]
_SHAPE_GEM = [
    0b00011000,
    0b00111100,
    0b01111110,
    0b11111111,
    0b11111111,
    0b01111110,
    0b00111100,
    0b00011000,
]
_SHAPE_INGOT = [
    0b00111100,
    0b01111110,
    0b11111111,
    0b11111111,
    0b11111111,
    0b11111111,
    0b01111110,
    0b00111100,
]
_SHAPE_FOOD = [
    0b00011000,
    0b00111100,
    0b01111110,
    0b01111110,
    0b01111110,
    0b00111100,
    0b00011000,
    0b00000000,
]
_SHAPE_STICK = [
    0b11000000,
    0b01100000,
    0b00110000,
    0b00011000,
    0b00001100,
    0b00000110,
    0b00000011,
    0b00000001,
]
_SHAPE_BLOCK = [
    0b11111111,
    0b11111111,
    0b11000011,
    0b10111101,
    0b10111101,
    0b11000011,
    0b11111111,
    0b11111111,
]
_SHAPE_PISTOL = [
    0b00111000,
    0b01111100,
    0b11111110,
    0b01111100,
    0b00110000,
    0b00011000,
    0b00011100,
    0b00001100,
]
_SHAPE_RIFLE = [
    0b00000011,
    0b00000111,
    0b11111110,
    0b11111100,
    0b00100100,
    0b00111100,
    0b00011000,
    0b00000000,
]
_SHAPE_SHOTGUN = [
    0b00011000,
    0b00111000,
    0b11111100,
    0b11111110,
    0b11111100,
    0b00111000,
    0b00011100,
    0b00001100,
]
_SHAPE_BULLET = [
    0b00111100,
    0b01111110,
    0b11111111,
    0b01111110,
    0b00111100,
    0b00011000,
    0b00001000,
    0b00000000,
]


def _shape_for_tags(tags: frozenset, name: str) -> list:
    n = name.lower()
    if "rifle"   in n:                        return _SHAPE_RIFLE
    if "shotgun" in n:                        return _SHAPE_SHOTGUN
    if "pistol"  in n or "firearm" in tags:   return _SHAPE_PISTOL
    if "bullet"  in n:                        return _SHAPE_BULLET
    if "pickaxe" in tags or "pickaxe" in n:   return _SHAPE_PICKAXE
    if "sword"   in tags or "sword"   in n:   return _SHAPE_SWORD
    if "axe"     in tags or "axe"     in n:   return _SHAPE_AXE
    if "shovel"  in tags or "shovel"  in n:   return _SHAPE_SHOVEL
    if "bow"     in n:                        return _SHAPE_BOW
    if "helmet"  in n or "cap" in n:          return _SHAPE_HELMET
    if "chestplate" in n or "tunic" in n:     return _SHAPE_CHESTPLATE
    if "leggings" in n or "pants" in n:       return _SHAPE_LEGGINGS
    if "boots"   in n or "shoes" in n:        return _SHAPE_BOOTS
    if "gem"     in tags or "diamond" in tags or "crystal" in n: return _SHAPE_GEM
    if "food"    in tags or "edible" in tags: return _SHAPE_FOOD
    if "thin"    in tags or "stick"  in n:    return _SHAPE_STICK
    if "metal"   in tags or "ingot"  in n:    return _SHAPE_INGOT
    if "magic"   in tags:                     return _SHAPE_ORB
    if "hard"    in tags or "stone"  in tags: return _SHAPE_BLOCK
    return _SHAPE_BLOCK


def _mystery_pattern(seed_str: str) -> list:
    """Generate a unique symmetric 8×8 pattern from a string seed."""
    h = hashlib.md5(seed_str.encode()).digest()
    rows = []
    for i in range(8):
        # Use one byte per row; mirror horizontally for symmetry
        byte = h[i % len(h)]
        half = byte & 0x0F           # 4 bits → left half
        mirrored = 0
        for bit in range(4):
            if half & (1 << bit):
                mirrored |= (1 << bit)
                mirrored |= (1 << (7 - bit))
        rows.append(mirrored)
    return rows


def _draw_shape(surf: pygame.Surface, shape: list,
                fg: tuple, bg: tuple, size: int):
    """Render an 8×8 shape bitmap onto surf at the given size."""
    cell = size / 8
    for row_idx, row_bits in enumerate(shape):
        for col_idx in range(8):
            bit = (row_bits >> (7 - col_idx)) & 1
            color = fg if bit else bg
            if color[3] == 0:
                continue
            x = int(col_idx * cell)
            y = int(row_idx * cell)
            w = max(1, int((col_idx + 1) * cell) - x)
            h = max(1, int((row_idx + 1) * cell) - y)
            pygame.draw.rect(surf, color, (x, y, w, h))


def _highlight(color: tuple, amount: int = 60) -> tuple:
    return tuple(min(255, c + amount) for c in color[:3]) + (color[3],)


def _shadow(color: tuple, amount: int = 60) -> tuple:
    return tuple(max(0, c - amount) for c in color[:3]) + (color[3],)


def _make_fallback(label: str, size: int, color: tuple,
                   tags: frozenset = frozenset(),
                   mystery: bool = False) -> pygame.Surface:
    """Procedural pixel-art icon — used when a texture file is missing."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)

    bg_color  = (0, 0, 0, 0)        # transparent background
    fg_color  = (*color[:3], 230)
    hi_color  = _highlight(fg_color, 70)
    sh_color  = _shadow(fg_color, 60)

    # Slightly lit background square
    bg_fill = (*tuple(max(0, c - 80) for c in color[:3]), 80)
    surf.fill(bg_fill)
    pygame.draw.rect(surf, (*tuple(max(0, c - 40) for c in color[:3]), 160),
                     surf.get_rect(), 1)

    if mystery:
        shape = _mystery_pattern(label)
        # Use a highlight pass for a glowing look
        _draw_shape(surf, shape, hi_color, bg_color, size)
        # Offset shadow pass
        sh_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        _draw_shape(sh_surf, shape, sh_color, bg_color, size)
        surf.blit(sh_surf, (1, 1), special_flags=pygame.BLEND_RGBA_MIN)
        _draw_shape(surf, shape, fg_color, bg_color, size)
    else:
        shape = _shape_for_tags(tags, label)
        # Shadow first
        sh_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        _draw_shape(sh_surf, shape, sh_color, bg_color, size)
        surf.blit(sh_surf, (1, 1))
        # Main colour
        _draw_shape(surf, shape, fg_color, bg_color, size)
        # Highlight (top-left pixels)
        hi_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        hi_shape = [r & (r >> 1) for r in shape]   # only pixels with a neighbour above
        _draw_shape(hi_surf, hi_shape, hi_color, bg_color, size)
        surf.blit(hi_surf, (0, 0))

    return surf


# ── Public API ────────────────────────────────────────────────────────────────

def _make_chest_texture(size: int) -> pygame.Surface:
    """Draw a 2D chest face: wood body with lid line and gold latch."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    wood      = (160, 100, 40, 255)
    wood_dark = (110,  65, 20, 255)
    wood_hi   = (195, 135, 65, 255)
    latch_col = (220, 175, 40, 255)

    surf.fill(wood)

    # Lid area (top ~35%)
    lid_h = max(1, size * 9 // 32)
    pygame.draw.rect(surf, wood_hi, (0, 0, size, lid_h))

    # Lid separator line
    sep_y = lid_h
    pygame.draw.rect(surf, wood_dark, (0, sep_y, size, max(1, size // 16)))

    # Body wood grain lines
    grain_y = sep_y + max(1, size // 8)
    while grain_y < size - size // 8:
        pygame.draw.rect(surf, wood_dark, (0, grain_y, size, max(1, size // 20)))
        grain_y += max(2, size // 7)

    # Gold latch (small rectangle centered on separator)
    lw = max(2, size // 6)
    lh = max(2, size // 5)
    lx = size // 2 - lw // 2
    ly = sep_y - lh // 2
    pygame.draw.rect(surf, latch_col, (lx, ly, lw, lh))
    pygame.draw.rect(surf, (180, 140, 20, 255), (lx, ly, lw, lh), max(1, size // 20))

    # Border
    pygame.draw.rect(surf, wood_dark, (0, 0, size, size), max(1, size // 20))
    return surf


def _make_end_portal_texture(size: int) -> pygame.Surface:
    """Procedural End Portal block — swirling void with coloured star specks."""
    import random as _rnd
    rng = _rnd.Random(0xE0D_4042)

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    # Void gradient background: very dark blue-purple to near-black
    for y in range(size):
        for x in range(size):
            t = (x + y) / (size * 2)
            r = int(4  + 10 * t)
            g = int(0  +  4 * t)
            b = int(18 + 22 * t)
            surf.set_at((x, y), (r, g, b, 255))

    # Star specks in Minecraft's signature green/purple/cyan/white palette
    _STAR_COLORS = [
        (100, 255, 100, 255),  # bright green
        ( 60, 220,  60, 220),  # green mid
        (180,  80, 255, 255),  # purple
        ( 80, 200, 255, 240),  # cyan
        (255, 255, 255, 255),  # white
        (200, 100, 255, 200),  # violet
        ( 40, 180,  40, 180),  # dark green
    ]
    n_stars = max(20, size * size // 20)
    for _ in range(n_stars):
        sx2 = rng.randint(0, size - 1)
        sy2 = rng.randint(0, size - 1)
        col = rng.choice(_STAR_COLORS)
        surf.set_at((sx2, sy2), col)
        # Occasional 2×2 bright pixel cluster for larger stars
        if rng.random() < 0.18 and sx2 + 1 < size and sy2 + 1 < size:
            dimmed = (col[0] * 2 // 3, col[1] * 2 // 3, col[2] * 2 // 3, col[3] // 2)
            surf.set_at((sx2 + 1, sy2),     dimmed)
            surf.set_at((sx2,     sy2 + 1), dimmed)

    # Subtle swirl: a few concentric ellipse-arc highlights in dark purple
    cx2, cy2 = size // 2, size // 2
    for r in range(size // 6, size // 2, max(1, size // 8)):
        n_pts = max(12, r * 6)
        for i in range(n_pts):
            angle = 2 * 3.14159 * i / n_pts + r * 0.3
            px2 = int(cx2 + math.cos(angle) * r * 0.9)
            py2 = int(cy2 + math.sin(angle) * r * 0.55)
            if 0 <= px2 < size and 0 <= py2 < size:
                old = surf.get_at((px2, py2))
                blended = (
                    min(255, old[0] + 15),
                    min(255, old[1] +  5),
                    min(255, old[2] + 35),
                    255,
                )
                surf.set_at((px2, py2), blended)

    return surf


def load_texture(texture_key: str, size: int = 32) -> pygame.Surface:
    """
    Load, scale, and cache a texture by key ("item/stick", "block/stone").
    Returns a size×size Surface — never raises.
    """
    key = (texture_key, size)
    if key in _cache:
        return _cache[key]

    # Special procedural textures
    if texture_key == "block/chest":
        surf = _make_chest_texture(size)
        _cache[key] = surf
        return surf
    if texture_key == "block/end_portal":
        surf = _make_end_portal_texture(size)
        _cache[key] = surf
        return surf

    parts = texture_key.split("/", 1)
    folder, name = parts[0], parts[1] if len(parts) > 1 else parts[0]
    path = os.path.join(_BASE, folder, name + ".png")

    surf = _read(path)

    # Try alias if primary path failed
    if surf is None:
        alt_key = _ALIASES.get(texture_key)
        if alt_key:
            a_parts = alt_key.split("/", 1)
            a_path = os.path.join(_BASE, a_parts[0], a_parts[1] + ".png")
            surf = _read(a_path)

    if surf is None:
        color = _color_for_name(name)
        surf = _make_fallback(name, size, color)
    else:
        surf = pygame.transform.scale(surf, (size, size))

    _cache[key] = surf
    return surf


def _try_custom(item_id: str, tex_path: str = None) -> Optional[pygame.Surface]:
    """Check resources/custom/ and generated_textures/ for a texture.

    tex_path is the item's .texture field (e.g. "item/deagle") — used to
    check resources/custom/item/deagle.png in addition to the flat lookup.
    """
    names = [item_id]
    if tex_path and tex_path != item_id:
        names.append(tex_path)
    for directory in (_CUSTOM_DIR, _GEN_DIR):
        for name in names:
            for ext in (".png", ".jpg", ".jpeg"):
                path = os.path.join(directory, name + ext)
                surf = _read(path)
                if surf is not None:
                    return surf
    return None


_POTION_COLORS: dict = {
    "water_bottle":              ( 80, 150, 220),
    "awkward_potion":            ( 50,  50,  90),
    "speed_potion":              (120, 215, 255),
    "strength_potion":           (220,  55,  55),
    "regen_potion":              (255, 100, 180),
    "fire_resistance_potion":    (255, 130,  20),
    "night_vision_potion":       ( 60,  30, 200),
    "healing_potion":            (255,  70, 110),
    "poison_potion":             ( 90, 185,  30),
    "harming_potion":            (140,  30, 180),
    "splash_poison":             ( 70, 155,  20),
    "splash_harming":            (120,  20, 150),
    "splash_strength":           (200,  35,  35),
}


def _make_potion_texture(item_id: str, size: int, splash: bool = False) -> pygame.Surface:
    """Render a coloured potion bottle procedurally."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    col  = _POTION_COLORS.get(item_id, (100, 100, 200))
    s    = size

    # Geometry
    bw = max(4, int(s * 0.46))
    bh = max(5, int(s * 0.52))
    bx = (s - bw) // 2
    by = s - bh - max(1, s // 16)

    nw = max(2, int(s * 0.22))
    nh = max(2, int(s * 0.26))
    nx = (s - nw) // 2
    ny = by - nh

    cork_h = max(2, int(s * 0.11))
    cork_y = ny - cork_h

    # Body
    body_ov = pygame.Surface((bw, bh), pygame.SRCALPHA)
    body_ov.fill((*col, 210))
    surf.blit(body_ov, (bx, by))
    pygame.draw.rect(surf, (20, 15, 10, 240), (bx, by, bw, bh), 1)

    # Neck
    neck_ov = pygame.Surface((nw, nh), pygame.SRCALPHA)
    neck_ov.fill((*col, 185))
    surf.blit(neck_ov, (nx, ny))
    pygame.draw.rect(surf, (20, 15, 10, 240), (nx, ny, nw, nh), 1)

    # Cork
    pygame.draw.rect(surf, (160, 115, 55), (nx, cork_y, nw, cork_h))
    pygame.draw.rect(surf, ( 90,  65, 30), (nx, cork_y, nw, cork_h), 1)

    # Shine strip — lighter left edge of body
    shine_w = max(1, bw // 4)
    shine_h = max(2, bh * 2 // 3)
    shine   = pygame.Surface((shine_w, shine_h), pygame.SRCALPHA)
    shine.fill((255, 255, 255, 55))
    surf.blit(shine, (bx + 2, by + 3))

    # Bubble
    br  = max(1, s // 12)
    bc  = (min(255, col[0] + 90), min(255, col[1] + 90), min(255, col[2] + 90), 130)
    pygame.draw.circle(surf, bc, (bx + bw // 3, by + bh // 2), br)

    # Splash drips at the bottom
    if splash:
        drip_pts = [
            (bx,          by + bh),
            (bx + bw // 2, by + bh + max(3, s // 7)),
            (bx + bw,     by + bh),
        ]
        drip_ov = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.polygon(drip_ov, (*col, 180), drip_pts)
        surf.blit(drip_ov, (0, 0))

    return surf


def get_item_texture(item_id: str, size: int = 32) -> pygame.Surface:
    """Convenience: look up the item's texture key and load it.

    Priority:
      1. generated_textures/{item_id}  (AI-generated — checked first for mystery items
         so the downloaded image overrides the placeholder Faithful texture)
      2. Faithful 32x resource pack texture
      3. resources/custom/{item_id}.png  (user-supplied, e.g. firearms)
      4. generated_textures/{item_id}  (also checked here for non-mystery items)
      5. Procedural pixel-art fallback (always works, no external files)
    """
    from items import ITEMS
    item = ITEMS.get(item_id)
    if item is None:
        return _make_fallback(item_id, size, (100, 100, 100))

    cache_key = (item_id, size)
    if cache_key in _cache:
        return _cache[cache_key]

    # Potion items — procedural coloured bottle (overrides Faithful texture)
    if item is not None and "potion" in item.tags:
        splash = "throwable" in item.tags
        surf   = _make_potion_texture(item_id, size, splash)
        _cache[cache_key] = surf
        return surf

    # Always compute parts first (needed for fallback name/color even if unused)
    parts = item.texture.split("/", 1)

    surf = None

    # Mystery items: always prefer generated_textures/ over the placeholder texture
    # stored in item.texture (which points to an existing Faithful item and would
    # otherwise shadow the AI-generated image permanently).
    if "mystery" in item.tags:
        surf = _try_custom(item_id)

    # Faithful pack
    if surf is None:
        if len(parts) == 2:
            tex_path = os.path.join(_BASE, parts[0], parts[1] + ".png")
        else:
            tex_path = os.path.join(_BASE, parts[0] + ".png")
        surf = _read(tex_path)

    # Custom / generated directories (for normal items whose Faithful texture is missing).
    # Pass item.texture so resources/custom/item/<name>.png is also checked.
    if surf is None:
        surf = _try_custom(item_id, item.texture)

    if surf is not None:
        surf = pygame.transform.scale(surf, (size, size))
    else:
        name    = parts[-1]
        color   = _color_for_name(name)
        if color == (100, 100, 100):        # name scan found nothing — try tags
            color = _color_for_tags(item.tags)
        mystery = "mystery" in item.tags
        surf    = _make_fallback(item_id, size, color, item.tags, mystery)

    _cache[cache_key] = surf
    return surf


def get_block_texture(block_id: str, size: int = 32) -> pygame.Surface:
    """Load a block face texture.  block_id may include a variant suffix."""
    # Prefer side variant for soil blocks (looks nicer in a side-scroller)
    side_variants = {
        "grass_block": "block/grass_block_side",
        "oak_log":     "block/oak_log",
    }
    key = side_variants.get(block_id, f"block/{block_id}")
    return load_texture(key, size)


def clear_cache() -> None:
    _cache.clear()


def preload(keys: list[str], size: int = 32) -> None:
    """Optional: warm up the cache for a list of texture keys."""
    for k in keys:
        load_texture(k, size)
