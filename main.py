"""
main.py — точка входа, игровой цикл, менеджер состояний.

States: resolution → world_select ↔ playing ↔ paused
        (paused can return to world_select without quitting the process)
"""
from __future__ import annotations
import json, logging, math, random, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Optional, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
_log = logging.getLogger("minacraft")
    
import pygame

import keys as _keys
import sounds
from world import (
    World, Camera, Player, GAME_VERSION,
    update_player, try_mine, try_place,
    hover_tile, draw_tile_cursor, find_spawn,
    draw_player, draw_hp_bar, draw_hunger_bar, draw_xp_bar, _draw_sky,
    draw_lighting_overlay, DAY_CYCLE_LEN,
    TILE_SIZE, WORLD_W, WORLD_H, FPS, TILE_COLOR, MAX_HUNGER,
    PLAYER_W, PLAYER_H, SkinParts, TILE_SOUND,
    _draw_end_sky,
)
from inventory import (Inventory, InventoryUI, ContainerUI, FurnaceUI,
                        ARMOR_SLOTS)
from crafting import (CraftingUI, GunsmithUI, RecipeBook, VillagerTradeUI,
                       EnchantingUI, BrewingUI, get_enchants,
                       get_discovered, set_discovered, mark_discovered)
from items import ItemStack, ITEMS
from mobs import (Mob, Projectile, spawn_mobs, spawn_nether_mobs, spawn_end_mobs,
                  update_mob, draw_mob, update_projectile, draw_projectile,
                  MOB_W, MOB_H, draw_boss_bar, _CFG as _MOB_CFG)

import os as _os
import sys as _sys
from learning import PlayerLogger, collect_state, collect_action

def _default_saves_dir() -> Path:
    """Return platform-appropriate saves directory for packaged app."""
    if not (getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS")):
        return Path("saves")   # dev mode: relative to CWD
    if _sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Minacraft"
    elif _sys.platform == "win32":
        base = Path(_os.environ.get("APPDATA", Path.home())) / "Minacraft"
    else:
        base = Path.home() / ".minacraft"
    base.mkdir(parents=True, exist_ok=True)
    return base / "saves"

# Launcher may override saves location and pre-select a world slot
SAVES_DIR  = Path(_os.environ.get("MINACRAFT_SAVES_DIR", "")) or _default_saves_dir()
_LAUNCHER_SLOT = _os.environ.get("MINACRAFT_WORLD_SLOT")

MAX_SLOTS  = 6
MINE_REACH = 5

RESOLUTIONS = [(960, 600), (1280, 720), (1920, 1080)]

# ── Ranged weapon config ───────────────────────────────────────────────────────
# (proj_kind, ammo_id_or_None, speed_px_frame, fire_interval_sec, spread_px, shots)
# proj_kind, ammo_id, speed, interval, spread_deg, pellets_per_shot
# For fast weapons (fire_rate >= 60 in items.py): interval is ignored —
# the accumulator system in update() drives the fire cadence.
_RANGED_CFG: dict = {
    "bow":             ("arrow",     None,               13.0, 0.80,  3, 1),
    "deagle":          ("bullet",    "bullet",           18.0, 0.70,  2, 1),
    "revolver":        ("bullet",    "bullet",           15.0, 0.80,  2, 1),
    "glock":           ("bullet",    "bullet",           16.0, 0.12,  3, 1),
    "shotgun":         ("pellet",    "shotgun_shell",    11.0, 0.90,  8, 12),
    "sniper_rifle":    ("bullet",    "rifle_ammo",       28.0, 1.50,  0, 1),
    "ak47":            ("bullet",    "bullet",           18.0, 0.10,  4, 1),
    "uzi":             ("bullet",    "bullet",           16.0, 0.08,  5, 1),
    "mp5":             ("bullet",    "bullet",           16.0, 0.09,  4, 1),
    "m249_saw":        ("bullet",    "bullet",           18.0, 0.07,  5, 1),
    "minigun":         ("bullet",    "bullet",           20.0, 1/60,  6, 1),
    "gold_minigun":    ("bullet",    "bullet",           20.0, 1/80,  5, 1),
    "diamond_minigun": ("bullet",    "bullet",           22.0, 1/100, 4, 1),
    "gold_deagle":     ("bullet",    "bullet",           22.0, 0.50,  2, 1),
    "rpg":             ("rocket",    "rocket",           10.0, 2.00,  0, 1),
    "flamethrower":    ("flame_jet", "napalm_canister",  14.0, 0.06, 16, 5),
}

# Tiles the flamethrower can ignite → what they drop when burned (None = nothing)
_FLAMMABLE_DROPS: dict = {
    # Logs → coal
    "oak_log":            "coal",
    "jungle_log":         "coal",
    "spruce_log":         "coal",
    "acacia_log":         "coal",
    "mangrove_log":       "coal",
    # Planks → coal
    "oak_planks":         "coal",
    "jungle_planks":      "coal",
    "spruce_planks":      "coal",
    # Leaves → nothing
    "oak_leaves":         None,
    "jungle_leaves":      None,
    "spruce_leaves":      None,
    "acacia_leaves":      None,
    # Doors → nothing
    "oak_door":           None,
    "oak_door_open":      None,
    "oak_door_top":       None,
    "oak_door_top_open":  None,
    # Containers → nothing (items already dropped on break)
    "chest":              None,
    "barrel":             None,
    # Workbench → nothing
    "workbench":          None,
    # Bamboo → nothing (too thin to produce coal)
    "bamboo":             None,
}
_BURN_TIME = 1.0   # seconds for a tile to finish burning

def _pkg_dir() -> Path:
    import sys as _sys
    return Path(getattr(_sys, "_MEIPASS", "."))

SKINS_DIR = _pkg_dir() / "resources/Faithful-32x-1.21.11/assets/minecraft/textures/entity/player/wide"
_DEFAULT_SKIN = "steve"


def _available_skins() -> list[tuple[str, Path]]:
    """Return [(display_name, path), ...] sorted alphabetically."""
    if not SKINS_DIR.exists():
        return []
    result = []
    for p in sorted(SKINS_DIR.glob("*.png")):
        name = p.stem.replace("_", " ").replace("tlauncher ", "")
        result.append((name, p))
    return result


def _load_skin(skin_name: str) -> "Optional[SkinParts]":
    """Load SkinParts for the given skin stem name, or None on failure."""
    path = SKINS_DIR / f"{skin_name}.png"
    if not path.exists():
        return None
    try:
        return SkinParts(str(path))
    except Exception:
        return None


# ── Piglin barter ─────────────────────────────────────────────────────────────
# (item_id, min_count, max_count, weight)
_PIGLIN_BARTER: list = [
    ("bullet",                  16, 64,  40),
    ("nether_brick",             4, 16,  30),
    ("gravel",                   8, 20,  30),
    ("flint",                    4, 12,  25),
    ("leather",                  3, 10,  20),
    ("iron_ingot",               2,  6,  15),
    ("gold_nugget",              9, 36,  15),
    ("obsidian",                 1,  4,  18),
    ("flint_and_steel",          1,  1,  10),
    ("blaze_rod",                1,  3,   8),
    ("blaze_powder",             2,  6,  12),
    ("fire_resistance_potion",   1,  1,   5),
    ("nether_scrap",             1,  1,   2),
    ("ancient_debris",           1,  1,   1),
]


def _piglin_barter() -> tuple:
    """Weighted random pick from the piglin barter table."""
    total = sum(w for *_, w in _PIGLIN_BARTER)
    r = random.uniform(0, total)
    cumulative = 0.0
    for item_id, mn, mx, w in _PIGLIN_BARTER:
        cumulative += w
        if r <= cumulative:
            return item_id, random.randint(mn, mx)
    last = _PIGLIN_BARTER[-1]
    return last[0], random.randint(last[1], last[2])


# ── Particles ─────────────────────────────────────────────────────────────────

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "r", "color")

    def __init__(self, x, y, vx, vy, life, color):
        self.x, self.y   = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.r    = random.uniform(1.5, 3.5)
        self.color = color

    def update(self, dt):
        self.vy  += 220 * dt
        self.x   += self.vx * dt
        self.y   += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, screen, camera_x, camera_y):
        r  = max(1, int(self.r * self.life / self.max_life))
        sx = int(self.x - camera_x)
        sy = int(self.y - camera_y)
        if 0 <= sx < screen.get_width() and 0 <= sy < screen.get_height():
            pygame.draw.circle(screen, self.color, (sx, sy), r)


# ── Dropped items ─────────────────────────────────────────────────────────────

_ITEM_GRAV    = 0.35
_ITEM_BOUNCE  = 0.3
_ITEM_DESPAWN = 300.0   # 5 minutes
_ITEM_PICKUP_R = TILE_SIZE * 1.2   # pickup radius in pixels
_ITEM_SPIN    = 1.8     # rotation speed rad/s

class DroppedItem:
    __slots__ = ("stack", "x", "y", "vx", "vy", "life", "bob_t", "angle")

    def __init__(self, stack: ItemStack, x: float, y: float,
                 vx: float = 0.0, vy: float = -3.0):
        self.stack = stack
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life  = _ITEM_DESPAWN
        self.bob_t = random.uniform(0, math.pi * 2)
        self.angle = 0.0

    def update(self, dt: float, world) -> bool:
        self.life -= dt
        if self.life <= 0:
            return False
        self.vy += _ITEM_GRAV
        self.vy  = min(self.vy, 15.0)
        self.x  += self.vx
        self.y  += self.vy
        self.bob_t += dt * 2.5
        self.angle = (self.angle + _ITEM_SPIN * dt) % (math.pi * 2)
        # simple ground collision
        tx = int((self.x + 8) // TILE_SIZE)
        ty = int((self.y + 16) // TILE_SIZE)
        if world.is_solid(tx, ty):
            self.y = ty * TILE_SIZE - 16
            self.vy = -abs(self.vy) * _ITEM_BOUNCE
            self.vx *= 0.7
            if abs(self.vy) < 0.5:
                self.vy = 0.0
        return True

    def draw(self, screen: pygame.Surface, cam_x: float, cam_y: float):
        from assets import get_item_texture
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y + math.sin(self.bob_t) * 2)
        sw, sh = screen.get_size()
        if sx < -20 or sx > sw + 20 or sy < -20 or sy > sh + 20:
            return
        SIZE = 16
        tex = get_item_texture(self.stack.item_id) if self.stack.item else None
        if tex:
            scaled = pygame.transform.scale(tex, (SIZE, SIZE))
            rotated = pygame.transform.rotate(scaled, math.degrees(self.angle))
            r = rotated.get_rect(center=(sx, sy))
            screen.blit(rotated, r)
        else:
            color = TILE_COLOR.get(self.stack.item_id, (180, 150, 100))
            pygame.draw.rect(screen, color, (sx - SIZE//2, sy - SIZE//2, SIZE, SIZE))
            pygame.draw.rect(screen, (255, 255, 255), (sx - SIZE//2, sy - SIZE//2, SIZE, SIZE), 1)
        # Count badge for stacks > 1
        if self.stack.count > 1:
            try:
                fnt = pygame.font.SysFont(None, 14)
                lbl = fnt.render(str(self.stack.count), True, (255, 255, 255))
                screen.blit(lbl, (sx + SIZE//2 - lbl.get_width(), sy + SIZE//2 - lbl.get_height()))
            except Exception:
                pass


def _spawn_particles(particles, tx, ty, tile):
    if tile is None:
        return
    color = TILE_COLOR.get(tile, (160, 140, 120))
    cx = tx * TILE_SIZE + TILE_SIZE / 2
    cy = ty * TILE_SIZE + TILE_SIZE / 2
    for _ in range(random.randint(5, 9)):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(40, 130)
        life  = random.uniform(0.30, 0.65)
        r_col = max(0, min(255, color[0] + random.randint(-25, 25)))
        g_col = max(0, min(255, color[1] + random.randint(-25, 25)))
        b_col = max(0, min(255, color[2] + random.randint(-25, 25)))
        particles.append(Particle(
            cx, cy,
            math.cos(angle) * speed,
            math.sin(angle) * speed - 60,
            life, (r_col, g_col, b_col),
        ))


def _spawn_tnt_particles(particles, ex, ey):
    """Large fiery explosion at world tile (ex, ey)."""
    cx = ex * TILE_SIZE + TILE_SIZE / 2
    cy = ey * TILE_SIZE + TILE_SIZE / 2
    colors = [(255, 80, 20), (255, 180, 40), (200, 60, 10), (255, 230, 100)]
    for _ in range(random.randint(24, 36)):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(80, 280)
        life  = random.uniform(0.4, 1.1)
        col   = random.choice(colors)
        col   = tuple(max(0, min(255, c + random.randint(-20, 20))) for c in col)
        particles.append(Particle(
            cx, cy,
            math.cos(angle) * speed,
            math.sin(angle) * speed - 120,
            life, col,
        ))


def _draw_end_portal_bar(screen: pygame.Surface, frac: float) -> None:
    """Progress bar when stepping into End portal."""
    sw = screen.get_width()
    bw = 260
    bh = 14
    bx = (sw - bw) // 2
    by = screen.get_height() - 80
    pygame.draw.rect(screen, (10, 5, 20),  (bx - 2, by - 2, bw + 4, bh + 4))
    pygame.draw.rect(screen, (80, 20, 120), (bx, by, max(1, int(bw * frac)), bh))
    pygame.draw.rect(screen, (160, 80, 220),(bx - 2, by - 2, bw + 4, bh + 4), 1)
    if pygame.font.get_init():
        f = pygame.font.SysFont(None, 16)
        lbl = f.render("Телепортация в Край...", True, (200, 150, 255))
        screen.blit(lbl, (sw // 2 - lbl.get_width() // 2, by + bh + 3))


_nether_fog_surf: Optional[pygame.Surface] = None

def _draw_nether_fog(screen: pygame.Surface) -> None:
    """Subtle dark-red atmospheric fog for the Nether."""
    global _nether_fog_surf
    sw, sh = screen.get_size()
    if _nether_fog_surf is None or _nether_fog_surf.get_size() != (sw, sh):
        _nether_fog_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        # Radial vignette: darker at edges
        cx, cy = sw // 2, sh // 2
        max_r = math.hypot(cx, cy)
        for y in range(0, sh, 4):
            for x in range(0, sw, 4):
                d = math.hypot(x - cx, y - cy) / max_r
                alpha = int(d * d * 64)  # 0 at center, ~64 at corners (20% lighter than 80)
                if alpha > 0:
                    pygame.draw.rect(_nether_fog_surf, (60, 5, 0, alpha), (x, y, 4, 4))
    screen.blit(_nether_fog_surf, (0, 0))


# ── Fullscreen helpers ────────────────────────────────────────────────────────

_is_fullscreen: bool = False
_fs_font_cache: Optional[pygame.font.Font] = None


def _toggle_fullscreen(screen: pygame.Surface, sw: int, sh: int) -> pygame.Surface:
    """Toggle windowed ↔ fullscreen. Returns the new screen surface."""
    global _is_fullscreen
    _is_fullscreen = not _is_fullscreen
    if _is_fullscreen:
        return pygame.display.set_mode((sw, sh), pygame.FULLSCREEN)
    else:
        return pygame.display.set_mode((sw, sh))


def _fs_btn_rect(sw: int, sh: int) -> pygame.Rect:
    return pygame.Rect(sw - 54, 6, 46, 26)


def _draw_fs_btn(screen: pygame.Surface) -> None:
    global _fs_font_cache
    if _fs_font_cache is None:
        _fs_font_cache = pygame.font.SysFont(None, 19)
    sw, sh = screen.get_size()
    r = _fs_btn_rect(sw, sh)
    mouse = pygame.mouse.get_pos()
    hov = r.collidepoint(mouse)
    pygame.draw.rect(screen, (55, 45, 32) if hov else (30, 24, 16), r, border_radius=4)
    pygame.draw.rect(screen, (195, 165, 70) if hov else (75, 65, 44), r, 1, border_radius=4)
    label = "[■] FS" if _is_fullscreen else "[ ] FS"
    txt = _fs_font_cache.render(label, True, (230, 210, 145) if hov else (140, 125, 88))
    screen.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))


# ── Resolution menu ───────────────────────────────────────────────────────────

class ResolutionMenu:
    def __init__(self):
        self.choice: Optional[tuple] = None
        self._fl = self._fm = None

    def _fonts(self):
        if self._fl is None:
            self._fl = pygame.font.SysFont(None, 52)
            self._fm = pygame.font.SysFont(None, 32)

    def _rects(self, sw, sh):
        bw, bh, gap = 280, 54, 16
        y0 = sh // 2 - (len(RESOLUTIONS) * (bh + gap)) // 2
        return [pygame.Rect(sw // 2 - bw // 2, y0 + i * (bh + gap), bw, bh)
                for i in range(len(RESOLUTIONS))]

    def handle_event(self, event, sw, sh):
        if event.type == pygame.QUIT:
            pygame.quit(); sys.exit()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            return "fullscreen"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if _fs_btn_rect(sw, sh).collidepoint(event.pos):
                return "fullscreen"
            for i, r in enumerate(self._rects(sw, sh)):
                if r.collidepoint(event.pos):
                    self.choice = RESOLUTIONS[i]

    def draw(self, screen):
        self._fonts()
        sw, sh = screen.get_size()
        screen.fill((18, 14, 10))

        title = self._fl.render("MINACRAFT", True, (220, 200, 130))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 60))

        ver = self._fm.render(GAME_VERSION, True, (120, 110, 80))
        screen.blit(ver, (sw // 2 - ver.get_width() // 2, 115))

        sub = self._fm.render("Выберите разрешение", True, (140, 130, 100))
        screen.blit(sub, (sw // 2 - sub.get_width() // 2, 148))

        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(self._rects(sw, sh)):
            w, h = RESOLUTIONS[i]
            hov = r.collidepoint(mouse)
            pygame.draw.rect(screen, (45, 38, 28) if hov else (28, 22, 16), r, border_radius=6)
            pygame.draw.rect(screen, (200, 170, 80) if hov else (75, 65, 48), r, 2, border_radius=6)
            lbl = self._fm.render(f"{w} × {h}", True,
                                  (240, 220, 160) if hov else (170, 155, 110))
            screen.blit(lbl, (r.centerx - lbl.get_width() // 2,
                               r.centery - lbl.get_height() // 2))
        _draw_fs_btn(screen)


# ── World select menu ─────────────────────────────────────────────────────────

class _Slot:
    def __init__(self, idx):
        self.idx    = idx
        self.path   = SAVES_DIR / f"world_{idx}.json"
        self.name   = ""
        self.seed   = 0
        self.mins   = 0
        self.ver    = ""
        self.exists = self.path.exists()
        if self.exists:
            try:
                d = json.loads(self.path.read_text())
                self.name = d.get("name", f"Мир {idx + 1}")
                self.seed = d.get("seed", 0)
                self.mins = d.get("time_played", 0) // 60
                self.ver  = d.get("world", {}).get("version", "?")
            except Exception:
                self.exists = False


class HelpScreen:
    """Controls reference shown from the main menu."""

    _SECTIONS = [
        ("Движение",   ["WASD / стрелки — движение",
                        "Space / W — прыжок",
                        "Shift + A/D — спринт (тратит голод)"]),
        ("Добыча",     ["ЛКМ (удерживать) — копать/ломать блок",
                        "ПКМ — ставить блок из хотбара",
                        "Tab — переключить слой (передний/задний)",
                        "ЛКМ — атаковать мобов (приоритет над добычей)"]),
        ("Инвентарь",  ["E — открыть/закрыть инвентарь",
                        "1-9 — выбрать слот хотбара",
                        "Колёсико мыши — прокрутить хотбар",
                        "F — съесть предмет в руке",
                        "Shift+ЛКМ — быстрый перенос в инвентаре"]),
        ("Крафт",      ["ПКМ по верстаку — открыть верстак",
                        "ПКМ по печи — открыть печь (переплавка)",
                        "R — книга рецептов (только открытые)",
                        "Неизвестные комбинации → загадочный предмет"]),
        ("Прочее",     ["ESC — пауза / главное меню",
                        "Сундуки/бочки: ПКМ — открыть",
                        "Двери: ПКМ — открыть/закрыть",
                        "Губка: убирает воду вокруг при установке"]),
    ]

    def __init__(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.done = False
        self._fl = self._fm = self._fs = None

    def _fonts(self):
        if self._fl is None:
            self._fl = pygame.font.SysFont(None, 40)
            self._fm = pygame.font.SysFont(None, 24)
            self._fs = pygame.font.SysFont(None, 20)

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            pygame.quit(); sys.exit()
        if event.type == pygame.KEYDOWN:
            self.done = True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.done = True

    def draw(self, screen):
        self._fonts()
        sw, sh = screen.get_size()
        screen.fill((14, 11, 8))

        title = self._fl.render("Управление", True, (220, 195, 120))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 18))

        hint = self._fs.render("Нажмите любую клавишу или кликните для возврата",
                               True, (90, 80, 60))
        screen.blit(hint, (sw // 2 - hint.get_width() // 2, 56))

        col_w  = (sw - 80) // 2
        col1_x = 40
        col2_x = 40 + col_w + 20
        y1, y2 = 90, 90

        for idx, (section_title, lines) in enumerate(self._SECTIONS):
            cx = col1_x if idx % 2 == 0 else col2_x
            cy = y1     if idx % 2 == 0 else y2

            sec = self._fm.render(section_title, True, (200, 175, 90))
            screen.blit(sec, (cx, cy))
            cy += sec.get_height() + 4
            pygame.draw.line(screen, (80, 68, 42), (cx, cy), (cx + col_w - 20, cy))
            cy += 6

            for line in lines:
                ln = self._fs.render(line, True, (175, 165, 140))
                screen.blit(ln, (cx + 6, cy))
                cy += ln.get_height() + 3

            cy += 12
            if idx % 2 == 0:
                y1 = cy
            else:
                y2 = cy


class WorldSelectMenu:
    def __init__(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.chosen: Optional[int] = None
        self.cheat_mode: bool = False
        self.del_confirm: Optional[int] = None
        self._fl = self._fm = self._fs = None
        SAVES_DIR.mkdir(exist_ok=True)

    def _fonts(self):
        if self._fl is None:
            self._fl = pygame.font.SysFont(None, 44)
            self._fm = pygame.font.SysFont(None, 26)
            self._fs = pygame.font.SysFont(None, 20)

    def _slots(self):
        return [_Slot(i) for i in range(MAX_SLOTS)]

    def _rects(self):
        sh_slot, gap = 68, 10
        total = MAX_SLOTS * (sh_slot + gap) - gap
        y0    = self.sh // 2 - total // 2
        w     = min(560, self.sw - 80)
        x     = self.sw // 2 - w // 2
        return [pygame.Rect(x, y0 + i * (sh_slot + gap), w, sh_slot)
                for i in range(MAX_SLOTS)]

    def _quit_rect(self):
        return pygame.Rect(self.sw // 2 + 105, self.sh - 55, 190, 38)

    def _help_rect(self):
        return pygame.Rect(self.sw // 2 - 295, self.sh - 55, 190, 38)

    def _cheat_rect(self):
        return pygame.Rect(self.sw // 2 - 95, self.sh - 55, 190, 38)

    def _fscrn_rect(self):
        return pygame.Rect(self.sw // 2 - 95, self.sh - 100, 190, 38)

    def handle_event(self, event, slots):
        if event.type == pygame.QUIT:
            pygame.quit(); sys.exit()
        if event.type == pygame.KEYDOWN:
            if _keys.normalize(event) == pygame.K_ESCAPE:
                self.del_confirm = None
                return
            if event.key == pygame.K_F11:
                return "fullscreen"
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        rects = self._rects()

        # Fullscreen corner button
        if _fs_btn_rect(self.sw, self.sh).collidepoint(event.pos):
            return "fullscreen"

        # Fullscreen bottom button
        if self._fscrn_rect().collidepoint(event.pos):
            return "fullscreen"

        # Quit button
        if self._quit_rect().collidepoint(event.pos):
            pygame.quit(); sys.exit()

        # Help button
        if self._help_rect().collidepoint(event.pos):
            return "help"

        # Cheat/test mode toggle
        if self._cheat_rect().collidepoint(event.pos):
            self.cheat_mode = not self.cheat_mode
            return

        if self.del_confirm is not None:
            r = rects[self.del_confirm]
            yes_r = pygame.Rect(r.right - 120, r.centery - 15, 52, 30)
            no_r  = pygame.Rect(r.right - 60,  r.centery - 15, 52, 30)
            if yes_r.collidepoint(event.pos):
                slots[self.del_confirm].path.unlink(missing_ok=True)
            self.del_confirm = None
            return

        for i, r in enumerate(rects):
            if not r.collidepoint(event.pos):
                continue
            if slots[i].exists:
                del_r = pygame.Rect(r.right - 34, r.y + 4, 30, 30)
                if del_r.collidepoint(event.pos):
                    self.del_confirm = i
                    return
            self.chosen = i
            return

    def draw(self, screen, slots):
        self._fonts()
        sw, sh = screen.get_size()
        screen.fill((18, 14, 10))

        title = self._fl.render("MINACRAFT  —  Миры", True, (220, 200, 130))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 20))

        ver_lbl = self._fs.render(GAME_VERSION, True, (100, 90, 65))
        screen.blit(ver_lbl, (sw // 2 - ver_lbl.get_width() // 2, 54))

        mouse = pygame.mouse.get_pos()
        for i, (r, slot) in enumerate(zip(self._rects(), slots)):
            if self.del_confirm == i:
                pygame.draw.rect(screen, (55, 20, 18), r, border_radius=6)
                pygame.draw.rect(screen, (200, 50, 40), r, 2, border_radius=6)
                q = self._fm.render("Удалить мир?", True, (255, 130, 100))
                screen.blit(q, (r.x + 14, r.centery - q.get_height() // 2))
                yes = self._fm.render("Да",  True, (255, 80, 60))
                no  = self._fm.render("Нет", True, (120, 220, 120))
                screen.blit(yes, (r.right - 120, r.centery - yes.get_height() // 2))
                screen.blit(no,  (r.right - 60,  r.centery - no.get_height() // 2))
                continue

            hov = r.collidepoint(mouse) and self.del_confirm is None
            pygame.draw.rect(screen, (45, 38, 28) if hov else (28, 22, 16), r, border_radius=6)
            pygame.draw.rect(screen, (190, 160, 70) if hov else (60, 54, 42), r, 2, border_radius=6)

            if slot.exists:
                n = self._fm.render(slot.name, True, (240, 220, 160))
                screen.blit(n, (r.x + 14, r.y + 10))
                ver_str = f"v{slot.ver}" if slot.ver else ""
                info = self._fs.render(
                    f"Seed: {slot.seed}  |  Сыграно: {slot.mins} мин  {ver_str}",
                    True, (140, 130, 100))
                screen.blit(info, (r.x + 14, r.y + 38))
                del_r = pygame.Rect(r.right - 34, r.y + 4, 30, 30)
                dh = del_r.collidepoint(mouse)
                pygame.draw.rect(screen, (80, 30, 24) if dh else (50, 20, 16), del_r, border_radius=4)
                xs = self._fm.render("✕", True, (220, 80, 60) if dh else (160, 55, 45))
                screen.blit(xs, (del_r.centerx - xs.get_width() // 2,
                                 del_r.centery - xs.get_height() // 2))
            else:
                lbl = self._fm.render(f"+ Новый мир #{i + 1}", True,
                                      (120, 200, 100) if hov else (80, 120, 70))
                screen.blit(lbl, (r.x + 14, r.centery - lbl.get_height() // 2))

        # Help button
        hr = self._help_rect()
        hhov = hr.collidepoint(mouse)
        pygame.draw.rect(screen, (20, 40, 55) if hhov else (14, 28, 38), hr, border_radius=5)
        pygame.draw.rect(screen, (60, 130, 180) if hhov else (35, 75, 110), hr, 1, border_radius=5)
        hl = self._fm.render("? Управление", True, (110, 190, 240) if hhov else (70, 140, 185))
        screen.blit(hl, (hr.centerx - hl.get_width() // 2, hr.centery - hl.get_height() // 2))

        # Cheat/test mode toggle button
        cr = self._cheat_rect()
        chov = cr.collidepoint(mouse)
        if self.cheat_mode:
            pygame.draw.rect(screen, (20, 60, 20) if chov else (14, 45, 14), cr, border_radius=5)
            pygame.draw.rect(screen, (60, 200, 60), cr, 2, border_radius=5)
            cl = self._fm.render("🧪 Тест: ВКЛ", True, (100, 240, 100))
        else:
            pygame.draw.rect(screen, (35, 35, 14) if chov else (22, 22, 10), cr, border_radius=5)
            pygame.draw.rect(screen, (90, 90, 40) if chov else (55, 55, 25), cr, 1, border_radius=5)
            cl = self._fm.render("🧪 Тест: ВЫКЛ", True, (150, 150, 70) if chov else (100, 100, 50))
        screen.blit(cl, (cr.centerx - cl.get_width() // 2, cr.centery - cl.get_height() // 2))

        # Fullscreen button (bottom row, centered)
        fsr = self._fscrn_rect()
        fshov = fsr.collidepoint(mouse)
        if _is_fullscreen:
            pygame.draw.rect(screen, (20, 45, 60) if fshov else (14, 32, 44), fsr, border_radius=5)
            pygame.draw.rect(screen, (60, 160, 210) if fshov else (35, 95, 135), fsr, 1, border_radius=5)
            fsl = self._fm.render("[■] Оконный режим", True, (120, 200, 245) if fshov else (75, 150, 190))
        else:
            pygame.draw.rect(screen, (20, 38, 55) if fshov else (14, 26, 38), fsr, border_radius=5)
            pygame.draw.rect(screen, (50, 120, 170) if fshov else (30, 70, 105), fsr, 1, border_radius=5)
            fsl = self._fm.render("[ ] Полный экран", True, (100, 175, 220) if fshov else (60, 120, 165))
        screen.blit(fsl, (fsr.centerx - fsl.get_width() // 2, fsr.centery - fsl.get_height() // 2))

        # Quit button
        qr = self._quit_rect()
        qhov = qr.collidepoint(mouse)
        pygame.draw.rect(screen, (55, 20, 18) if qhov else (35, 14, 12), qr, border_radius=5)
        pygame.draw.rect(screen, (200, 60, 40) if qhov else (100, 35, 25), qr, 1, border_radius=5)
        ql = self._fm.render("Выйти из игры", True, (230, 90, 60) if qhov else (160, 55, 45))
        screen.blit(ql, (qr.centerx - ql.get_width() // 2, qr.centery - ql.get_height() // 2))

        _draw_fs_btn(screen)


# ── Pause menu ────────────────────────────────────────────────────────────────

class SkinSelectOverlay:
    """Full-screen skin picker shown from the pause menu."""

    _THUMB = 64   # thumbnail size (preview + border)
    _COLS  = 4

    def __init__(self, sw: int, sh: int, current: str):
        self.sw, self.sh = sw, sh
        self.selected    = current   # skin stem name
        self.is_open     = False
        self._skins      = _available_skins()  # [(display_name, path)]
        self._previews: list[pygame.Surface] = []
        self._font_m = self._font_s = None

    def _fonts(self):
        if self._font_m is None:
            self._font_m = pygame.font.SysFont(None, 26)
            self._font_s = pygame.font.SysFont(None, 18)

    def _ensure_previews(self):
        if len(self._previews) == len(self._skins):
            return
        self._previews.clear()
        for _, path in self._skins:
            try:
                sp = SkinParts(str(path))
                self._previews.append(sp.preview)   # 48×48
            except Exception:
                fallback = pygame.Surface((48, 48)); fallback.fill((80, 80, 80))
                self._previews.append(fallback)

    def open(self, current: str):
        self.selected = current
        self.is_open  = True
        self._ensure_previews()

    def handle_event(self, event) -> Optional[str]:
        """Returns the chosen skin name, or None if still open."""
        if not self.is_open:
            return None
        if event.type == pygame.KEYDOWN and _keys.normalize(event) == pygame.K_ESCAPE:
            self.is_open = False
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._thumb_rects()):
                if r.collidepoint(event.pos):
                    _, path = self._skins[i]
                    self.selected = path.stem
                    self.is_open  = False
                    return self.selected
        return None

    def _thumb_rects(self) -> list[pygame.Rect]:
        T, C = self._THUMB + 12, self._COLS
        rows = (len(self._skins) + C - 1) // C
        total_w = C * (T + 8) - 8
        total_h = rows * (T + 26) - 26 + 40
        ox = self.sw // 2 - total_w // 2
        oy = self.sh // 2 - total_h // 2 + 30
        rects = []
        for i in range(len(self._skins)):
            col, row = i % C, i // C
            rects.append(pygame.Rect(ox + col * (T + 8), oy + row * (T + 26), T, T))
        return rects

    def draw(self, screen: pygame.Surface):
        if not self.is_open:
            return
        self._fonts()
        sw, sh = screen.get_size()
        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 190))
        screen.blit(dim, (0, 0))

        title = self._font_m.render("ВЫБОР СКИНА", True, (220, 200, 130))
        screen.blit(title, (sw // 2 - title.get_width() // 2, 28))

        hint = self._font_s.render("ESC — закрыть  |  Нажмите на скин чтобы выбрать",
                                   True, (140, 130, 105))
        screen.blit(hint, (sw // 2 - hint.get_width() // 2, 56))

        mouse = pygame.mouse.get_pos()
        T = self._THUMB + 12
        for i, r in enumerate(self._thumb_rects()):
            name, path = self._skins[i]
            is_sel = (path.stem == self.selected)
            hov    = r.collidepoint(mouse)
            bg_col = (80, 65, 45) if is_sel else (50, 42, 32) if hov else (30, 25, 18)
            bd_col = (220, 180, 60) if is_sel else (130, 110, 70) if hov else (70, 60, 42)
            pygame.draw.rect(screen, bg_col, r, border_radius=4)
            pygame.draw.rect(screen, bd_col, r, 2, border_radius=4)
            if i < len(self._previews):
                px = r.x + (r.w - 48) // 2
                py = r.y + (r.h - 48) // 2
                screen.blit(self._previews[i], (px, py))
            lbl = self._font_s.render(name[:12], True,
                                      (255, 230, 130) if is_sel else (190, 178, 148))
            screen.blit(lbl, (r.centerx - lbl.get_width() // 2, r.bottom + 4))


class PauseMenu:
    _BTNS   = ["Продолжить", "Сменить скин", "Полный экран", "Главное меню"]
    _LABELS = ["resume",     "skin_select",  "fullscreen",   "main_menu"]
    BTN_W, BTN_H = 260, 50

    def __init__(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.action: Optional[str] = None
        self._fl = self._fm = None

    def _fonts(self):
        if self._fl is None:
            self._fl = pygame.font.SysFont(None, 52)
            self._fm = pygame.font.SysFont(None, 30)

    def _rects(self):
        gap   = 16
        total = len(self._BTNS) * (self.BTN_H + gap) - gap
        y0    = self.sh // 2 - total // 2 + 30
        return [pygame.Rect(self.sw // 2 - self.BTN_W // 2,
                            y0 + i * (self.BTN_H + gap),
                            self.BTN_W, self.BTN_H)
                for i in range(len(self._BTNS))]

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.action = "quit"
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm == pygame.K_ESCAPE:
                self.action = "resume"
            if event.key == pygame.K_F11:
                self.action = "fullscreen"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._rects()):
                if r.collidepoint(event.pos):
                    self.action = self._LABELS[i]

    def draw(self, screen):
        self._fonts()
        sw, sh = screen.get_size()
        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 165))
        screen.blit(dim, (0, 0))

        title = self._fl.render("ПАУЗА", True, (220, 200, 130))
        screen.blit(title, (sw // 2 - title.get_width() // 2, sh // 2 - 130))

        mouse = pygame.mouse.get_pos()
        for i, r in enumerate(self._rects()):
            label = self._BTNS[i]
            if self._LABELS[i] == "fullscreen":
                label = "[■] Оконный режим" if _is_fullscreen else "[ ] Полный экран"
            hov = r.collidepoint(mouse)
            pygame.draw.rect(screen, (50, 42, 30) if hov else (30, 24, 18), r, border_radius=6)
            pygame.draw.rect(screen, (200, 170, 80) if hov else (80, 70, 50), r, 2, border_radius=6)
            lbl = self._fm.render(label, True,
                                  (245, 225, 165) if hov else (180, 160, 115))
            screen.blit(lbl, (r.centerx - lbl.get_width() // 2,
                               r.centery - lbl.get_height() // 2))


# ── In-game chat ──────────────────────────────────────────────────────────────

class Chat:
    """Minimal in-game chat: T opens, Enter sends, Esc closes."""
    _MSG_LIFETIME = 6.0   # seconds before message fades
    _MAX_VISIBLE  = 8

    def __init__(self):
        self.active    = False
        self._input    = ""
        self._messages: list = []  # [(text, timer)]
        self._font: Optional[pygame.font.Font] = None

    def _get_font(self):
        if self._font is None:
            self._font = pygame.font.SysFont("monospace", 15, bold=False)
        return self._font

    def open(self):
        self.active = True
        self._input = ""

    def close(self):
        self.active = False
        self._input = ""

    def handle_event(self, event) -> Optional[str]:
        """Returns a command string if Enter pressed with /command, else None."""
        if not self.active:
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                cmd = self._input.strip()
                self._input = ""
                self.active = False
                if cmd:
                    return cmd
            elif event.key == pygame.K_BACKSPACE:
                self._input = self._input[:-1]
            else:
                ch = event.unicode
                if ch and ch.isprintable():
                    if len(self._input) < 120:
                        self._input += ch
        return None

    def add_message(self, text: str):
        self._messages.append([text, self._MSG_LIFETIME])

    def update(self, dt: float):
        self._messages = [[t, life - dt] for t, life in self._messages if life - dt > 0]

    def draw(self, screen: pygame.Surface):
        fn = self._get_font()
        sw, sh = screen.get_size()
        base_y = sh - 90 if self.active else sh - 60
        visible = [m for m in self._messages[-self._MAX_VISIBLE:]]
        for i, (text, life) in enumerate(visible):
            alpha = min(255, int(255 * min(1.0, life / 1.5)))
            lbl = fn.render(text, True, (230, 230, 200))
            bg  = pygame.Surface((lbl.get_width() + 6, lbl.get_height() + 2), pygame.SRCALPHA)
            bg.fill((0, 0, 0, min(160, alpha)))
            lbl.set_alpha(alpha)
            y = base_y - (len(visible) - i - 1) * (fn.get_height() + 2)
            screen.blit(bg,  (8, y - 1))
            screen.blit(lbl, (11, y))
        if self.active:
            bar_y = sh - 64
            bar_w = sw // 2
            pygame.draw.rect(screen, (20, 20, 20, 200), (8, bar_y, bar_w, fn.get_height() + 6))
            pygame.draw.rect(screen, (160, 140, 80), (8, bar_y, bar_w, fn.get_height() + 6), 1)
            cursor = "_" if int(pygame.time.get_ticks() / 500) % 2 == 0 else " "
            text_lbl = fn.render(self._input + cursor, True, (230, 230, 180))
            screen.blit(text_lbl, (12, bar_y + 3))


# ── Save / Load ───────────────────────────────────────────────────────────────

def _find_nether_floor(world, tx: int) -> int:
    """Find a suitable arrival y-tile in the nether at column tx."""
    mid = world.height // 2
    for ty in range(mid, world.height - 6):
        t = world.get(tx, ty)
        b = world.get(tx, ty + 1)
        if t is None and b is not None and b != "lava":
            return ty
    for ty in range(10, world.height - 6):
        if world.get(tx, ty) is None:
            return ty
    return mid


def _save(slot: int, world_ow: World, player: Player, inv: Inventory,
          name: str, time_played: float, skin_name: str = _DEFAULT_SKIN,
          world_nether: Optional[World] = None,
          dimension: str = "overworld"):
    SAVES_DIR.mkdir(exist_ok=True)
    data = {
        "name":               name,
        "seed":               world_ow.seed,
        "time_played":        int(time_played),
        "player":             player.to_dict(),
        "inventory":          inv.to_dict(),
        "world":              world_ow.to_dict(),
        "discovered_recipes": list(get_discovered()),
        "skin_name":          skin_name,
        "dimension":          dimension,
        "nether_world":       world_nether.to_dict() if world_nether else None,
    }
    (SAVES_DIR / f"world_{slot}.json").write_text(json.dumps(data))


def _load(slot: int) -> Optional[dict]:
    path = SAVES_DIR / f"world_{slot}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _new_game(slot: int, cheat: bool = False):
    seed   = random.randint(0, 2 ** 31)
    world  = World(seed)
    sx, sy = find_spawn(world)
    player = Player(sx, sy)
    inv    = Inventory()
    # Place a workbench two tiles right of spawn
    spx = int(player.x // TILE_SIZE) + 2
    spy = int(player.y // TILE_SIZE)
    while spy < WORLD_H - 1 and world.get(spx, spy) is None:
        spy += 1
    world.set(spx, spy - 1, "workbench")

    if cheat:
        # Full diamond kit + resources
        for item_id in ("diamond_pickaxe", "diamond_axe", "diamond_sword",
                        "diamond_shovel", "diamond_hoe"):
            inv.add(ItemStack(item_id, 1))
        for item_id in ("diamond_helmet", "diamond_chestplate",
                        "diamond_leggings", "diamond_boots"):
            inv.add(ItemStack(item_id, 1))
        for item_id, qty in [
            ("oak_log", 64), ("oak_planks", 64), ("cobblestone", 64),
            ("stone", 64),   ("dirt", 64),        ("sand", 64),
            ("iron_ingot", 64), ("gold_ingot", 64), ("diamond", 64),
            ("coal", 64),    ("stick", 64),        ("flint", 32),
            ("glass", 64),   ("chest", 16),        ("furnace", 8),
            ("redstone", 64), ("redstone_torch", 16), ("lever", 16),
            ("torch", 64),   ("workbench", 4),     ("iron_pickaxe", 2),
            ("apple", 64),   ("bread", 64),
            ("enchanting_table", 1), ("gunpowder", 64), ("lapis_lazuli", 64),
            ("obsidian", 64), ("flint_and_steel", 1),
            ("iron_nugget", 64), ("bullet", 999), ("minigun", 1),
        ]:
            inv.add(ItemStack(item_id, qty))
        player.hp  = player.max_hp
        player.xp  = 15000
        name = f"Тест #{slot + 1}"
    else:
        inv.add(ItemStack("oak_log",        20))
        inv.add(ItemStack("stick",          10))
        inv.add(ItemStack("wooden_pickaxe",  1))
        inv.add(ItemStack("wooden_axe",      1))
        name = f"Мир {slot + 1}"

    return world, player, inv, name


# ── Main game session ─────────────────────────────────────────────────────────

class GameSession:
    def __init__(self, slot: int, sw: int, sh: int, cheat: bool = False):
        self.slot = slot
        self.sw, self.sh = sw, sh
        self.time_played = 0.0
        self._autosave_t = time.time()
        self._water_t    = 0.0    # seconds since last water tick

        data = _load(slot)
        if data:
            self.world  = World.from_dict(data["world"])
            self.player = Player.from_dict(data["player"])
            self.inv    = Inventory.from_dict(data["inventory"])
            self.name   = data.get("name", f"Мир {slot + 1}")
            self.time_played = float(data.get("time_played", 0))
        else:
            self.world, self.player, self.inv, self.name = _new_game(slot, cheat=cheat)

        self._spawn_px, self._spawn_py = self.player.x, self.player.y

        self.camera       = Camera(sw, sh)
        self.camera.snap(self.player, self.world)
        self.inv_ui       = InventoryUI(self.inv, sw, sh)
        self.craft_ui       = CraftingUI(sw, sh)
        self.gunsmith_ui    = GunsmithUI(sw, sh)
        self.container_ui   = ContainerUI(sw, sh)
        self.furnace_ui     = FurnaceUI(sw, sh)
        self.recipe_book    = RecipeBook(sw, sh)
        self.villager_ui    = VillagerTradeUI(sw, sh)
        self.enchant_ui     = EnchantingUI(sw, sh)
        self.brewing_ui     = BrewingUI(sw, sh)
        self.chat           = Chat()
        self.player_effects: dict = {}   # effect_id → [remaining_sec, level]
        self._regen_t  = 0.0
        self._poison_t = 0.0
        self._lava_t   = 0.0
        self._magma_t  = 0.0
        self._lava_sound_t = random.uniform(2.0, 6.0)
        self._fire_t   = 0.0

        # ── Weather ───────────────────────────────────────────────────────────
        self.weather          = "clear"      # "clear" | "rain" | "thunder" | "snow"
        self._weather_timer   = random.uniform(180, 480)  # seconds to next change
        self._weather_intensity = 0.0        # 0.0→1.0 fade
        self._rain_particles: list = []      # [(x, y, speed)]
        self._lightning_flash = 0.0          # seconds of white-flash remaining
        self._lightning_t     = 0.0          # time since last lightning
        self._rain_sound_t    = 0.0          # rain ambient sound timer
        self._cave_sound_t    = random.uniform(60, 180)  # cave ambient timer

        # ── Achievements ──────────────────────────────────────────────────────
        self._ach_popup: Optional[tuple] = None   # (id, title, desc) currently showing
        self._ach_queue: list = []                # queued popups
        self._ach_t    = 0.0                      # seconds since popup started
        self._ach_font: Optional[pygame.font.Font] = None
        self.skin_name: str = data.get("skin_name", _DEFAULT_SKIN) if data else _DEFAULT_SKIN
        self.skin           = _load_skin(self.skin_name)
        self.skin_overlay   = SkinSelectOverlay(sw, sh, self.skin_name)
        self.particles: List[Particle] = []
        self.dropped_items: List[DroppedItem] = []
        self._float_texts: List[dict] = []   # {"text", "x", "y", "t", "col"}

        self._underground_frac = 0.0   # smoothed lighting darkness (0=surface, 1=deep)

        self.lmb_held      = False
        self._cant_mine_cd = 0.0
        self._attack_cd    = 0.0   # seconds until next melee swing
        self._swing_t      = 0.0   # seconds remaining in arm-swing animation
        self._fire_cd      = 0.0   # seconds until next ranged shot (slow weapons)
        self._fire_acc     = 0.0   # fractional shots accumulated (fast weapons ≥60/s)
        self._flame_fuel   = 0.0   # remaining flamethrower fuel (seconds)
        self._muzzle_flash_t = 0.0  # seconds remaining for muzzle flash
        self._muzzle_wx    = 0.0   # muzzle world X
        self._muzzle_wy    = 0.0   # muzzle world Y
        self._muzzle_dx    = 1.0   # shoot direction X
        self._muzzle_dy    = 0.0   # shoot direction Y
        self._muzzle_flame = False  # True for flamethrower (different color)
        self._burning_tiles: dict = {}  # (tx, ty) → burn_time_remaining
        self._keys: defaultdict = defaultdict(bool)
        self.active_layer: str = "fg"   # "fg" or "bg"
        self._fm = None
        self.day_time: float = DAY_CYCLE_LEN * 0.25  # start at noon

        self.mobs: List[Mob] = spawn_mobs(self.world)

        # ── Dimension management ──────────────────────────────────────────
        self.world_ow     = self.world          # overworld world ref
        self.world_nether: Optional[World] = None
        self.world_end:    Optional[World] = None
        self._mobs_ow     = self.mobs
        self._mobs_nether: List[Mob] = []
        self._mobs_end:    List[Mob] = []
        self.projectiles: List[Projectile] = []
        self._proj_ow:    List[Projectile] = self.projectiles
        self._proj_nether: List[Projectile] = []
        self._proj_end:    List[Projectile] = []
        self.dimension    = "overworld"
        self._portal_timer   = 0.0   # seconds player in portal
        self._portal_cooldown = 0.0  # seconds of immunity after teleport
        self._end_portal_timer = 0.0  # seconds player in end_portal
        self._game_won    = False    # set when dragon is defeated
        self._win_t       = 0.0     # scroll timer for end poem
        self._minigun_burst = 0     # accumulated shots for batch logging

        if data and data.get("nether_world"):
            self.world_nether = World.from_dict(data["nether_world"])
            self._mobs_nether = spawn_nether_mobs(self.world_nether)

        if data:
            set_discovered(data.get("discovered_recipes", []))

        # ── Player behaviour logger ───────────────────────────────────────
        self._pl_logger = PlayerLogger(enabled=True)
        self._pl_prev_slot = 0
        self._pl_prev_rmb  = False

        action = "загружен" if data else "создан"
        _log.info("МИР %s: «%s» (слот %d, seed=%d)",
                  action, self.name, slot, self.world.seed)
        _log.info("Игрок: HP=%d/%d, уровень=%d, голод=%.0f",
                  self.player.hp, self.player.max_hp,
                  self.player.level, self.player.hunger)

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event) -> Optional[str]:
        """Return 'pause', 'main_menu', or None."""
        if event.type == pygame.QUIT:
            return "quit"

        sounds.on_event(event)   # advance music playlist

        # Win screen: any key / click returns to main menu
        if self._game_won:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return "main_menu"
            return None

        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            self._keys[norm] = True
        elif event.type == pygame.KEYUP:
            norm = _keys.normalize(event)
            self._keys[norm] = False

        # Recipe book overlay
        if self.recipe_book.is_open:
            self.recipe_book.handle_event(event)
            return None

        # Villager trade overlay
        if self.villager_ui.is_open:
            self.villager_ui.handle_event(event, self.inv)
            return None

        # Enchanting table overlay
        if self.enchant_ui.is_open:
            self.enchant_ui.handle_event(event, self.inv, self.player)
            return None

        # Brewing stand overlay
        if self.brewing_ui.is_open:
            self.brewing_ui.handle_event(event, self.inv, self.world)
            return None

        # Furnace overlay
        if self.furnace_ui.is_open:
            self.furnace_ui.handle_event(event, self.inv, self.world)
            return None

        # Gunsmith overlay
        if self.gunsmith_ui.is_open:
            self.gunsmith_ui.handle_event(event, self.inv, self.player)
            return None

        # Container overlay
        if self.container_ui.is_open:
            self.container_ui.handle_event(event, self.inv, self.world)
            return None

        # Crafting overlay
        if self.craft_ui.is_open:
            self.craft_ui.handle_event(event, self.inv)
            return None

        # Inventory overlay
        if self.inv_ui.open:
            self.inv_ui.handle_event(event)
            return None

        # Chat overlay — absorb all key input when open
        if self.chat.active:
            cmd = self.chat.handle_event(event)
            if cmd:
                self._exec_chat_command(cmd)
            return None

        # Open chat with T
        if event.type == pygame.KEYDOWN and _keys.normalize(event) == pygame.K_t:
            self.chat.open()
            return None

        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm == pygame.K_ESCAPE:
                return "pause"
            if event.key == pygame.K_F11:
                return "fullscreen"
            if norm == pygame.K_e:
                opening = not self.inv_ui.open
                self.inv_ui.handle_event(event)
                _log.info("ИНВЕНТАРЬ: %s", "открыт" if opening else "закрыт")
                return None
            if norm == pygame.K_r:
                self.recipe_book.open()
                _log.info("UI открыт: книга рецептов")
                return None
            if norm == pygame.K_f:
                self._swap_off_hand()
                return None
            if norm == pygame.K_TAB:
                self.active_layer = "bg" if self.active_layer == "fg" else "fg"
                _log.info("СЛОЙ: переключён на %s", self.active_layer)
                return None
            if norm == pygame.K_q:
                held = self.inv.held
                if held and not held.is_empty():
                    drop_stack = ItemStack(held.item_id, 1, held.durability)
                    held.count -= 1
                    if held.count <= 0:
                        self.inv.slots[self.inv.selected] = None
                    px = self.player.x + PLAYER_W / 2
                    py = self.player.y + PLAYER_H / 4
                    facing_vx = 3.0 if self.player.facing >= 0 else -3.0
                    self._spawn_drop(drop_stack, px, py,
                                     vx_range=(facing_vx * 0.8, facing_vx * 1.2),
                                     vy_range=(-4.0, -2.5))
                    _log.info("ВЫБРОС: %s ×1", drop_stack.item_id)
                return None

        if event.type in (pygame.MOUSEWHEEL, pygame.KEYDOWN):
            self.inv_ui.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.lmb_held = True
                self._try_attack(event.pos)   # instant swing on every click
            if event.button == 3:
                self._on_rmb(event.pos)

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.lmb_held = False

        return None

    def _throw_eye_of_ender(self):
        """Throw eye of ender toward the overworld stronghold."""
        held = self.inv.held
        if not held or held.item_id != "eye_of_ender":
            return

        # Use overworld stronghold position if available
        world_ow = self.world_ow if hasattr(self, "world_ow") else self.world
        if hasattr(world_ow, "_stronghold_cx"):
            target_x = world_ow._stronghold_cx * TILE_SIZE
            target_y = world_ow._stronghold_cy * TILE_SIZE
        else:
            target_x = self.world.width  // 2 * TILE_SIZE
            target_y = self.world.height // 2 * TILE_SIZE

        pcx = self.player.x + PLAYER_W / 2
        pcy = self.player.y + PLAYER_H / 2

        dist = math.hypot(target_x - pcx, target_y - pcy)
        if dist < 1:
            self.chat.add_message("Ты уже у крепости!")
            return
        speed = 9.0
        vx = (target_x - pcx) / dist * speed
        vy = (target_y - pcy) / dist * speed - 3.0   # slight upward loft

        self.projectiles.append(Projectile(
            x=pcx, y=pcy, vx=vx, vy=vy,
            damage=0, kind="eye_of_ender", life=4.0, owner="player",
        ))

        held.count -= 1
        if held.count <= 0:
            self.inv.slots[self.inv.selected] = None
        sounds.play("place_block", 0.6)

        dist_tiles = int(dist / TILE_SIZE)
        dir_s = "→" if target_x > pcx else "←"
        self.chat.add_message(f"Оko Края: крепость {dir_s} {dist_tiles} тайлов")
        _log.info("БРОСОК ока Края → крепость (%d, %d), dist=%d тайлов",
                  target_x // TILE_SIZE, target_y // TILE_SIZE, dist_tiles)

    def _swap_off_hand(self):
        """Swap the currently selected hotbar item with the off-hand slot."""
        held = self.inv.slots[self.inv.selected]
        off  = self.inv.off_hand
        self.inv.slots[self.inv.selected] = off
        self.inv.off_hand = held if (held and not held.is_empty()) else None
        if self.inv.slots[self.inv.selected] and self.inv.slots[self.inv.selected].is_empty():
            self.inv.slots[self.inv.selected] = None
        sounds.play("pickup", 0.4)

    def _eat(self):
        held = self.inv.held
        if not held or held.is_empty():
            return
        it = held.item
        if not it:
            return
        fv = it.properties.get("food_value", 0)
        if not fv or self.player.hunger >= MAX_HUNGER:
            return
        self.player.hunger = min(MAX_HUNGER, self.player.hunger + fv)
        held.count -= 1
        if held.is_empty():
            self.inv.slots[self.inv.selected] = None
        sounds.play("eat", 0.7)
        sounds.play("burp", 0.3)
        _log.info("ЕДА: %s (+%d голода → %.0f/%.0f)",
                  it.name, fv, self.player.hunger, MAX_HUNGER)
        self._unlock_achievement("full_belly") if self.player.hunger >= MAX_HUNGER else None

    def _try_attack(self, mouse_pos) -> None:
        """Melee swing or ranged shot toward mouse.

        Called once per LMB click (and continuously while held for auto-fire).
        """
        held = self.inv.held
        if held and held.item and ("firearm" in held.item.tags
                                   or held.item_id == "bow"):
            self._fire_weapon(mouse_pos)
            return
        if self._attack_cd > 0:
            return
        pcx, pcy = self.player.center
        wx,  wy  = self.camera.screen_to_world(*mouse_pos)

        # Face toward mouse
        if wx != pcx:
            self.player.facing = 1 if wx > pcx else -1

        # Swing direction unit vector (player → mouse)
        dx, dy    = wx - pcx, wy - pcy
        dist_m    = math.hypot(dx, dy) or 1.0
        dx /= dist_m;  dy /= dist_m

        REACH    = 3.2 * TILE_SIZE
        hit_any  = False

        held    = self.inv.held
        dmg_base = 1
        sharp    = 0
        if held and held.item:
            dmg_base = max(1, held.item.properties.get("damage", 1))
            sharp    = held.enchantments.get("sharpness", 0)
            if "strength" in self.player_effects:
                dmg_base += self.player_effects["strength"][1] * 2

        for mob in self.mobs:
            if not mob.alive:
                continue
            mcx, mcy = mob.center
            ddx, ddy = mcx - pcx, mcy - pcy
            dist = math.hypot(ddx, ddy)
            if dist > REACH:
                continue
            # Dot product — reject mobs clearly behind the swing direction
            dot = (ddx * dx + ddy * dy) / (dist or 1.0)
            if dot < -0.25:          # > ~105° behind swing
                continue

            dmg = dmg_base + sharp
            # Critical hit: airborne and falling
            is_crit = not self.player.on_ground and self.player.vy > 2.0
            if is_crit:
                dmg = int(dmg * 1.5)

            if held and held.item:
                unbreak  = held.enchantments.get("unbreaking", 0)
                lose_dur = (not unbreak) or (random.random() > 0.33 * unbreak)
                if lose_dur and held.item.max_durability > 0 and held.durability > 0:
                    held.durability -= 1
                    if held.durability <= 0:
                        self.inv.slots[self.inv.selected] = None
                        sounds.play("break_block", 0.9)

            mob.hp      = max(0, mob.hp - dmg)
            mob._hurt_t = 0.25
            if mob.cfg().get("neutral"):
                mob.extra["provoked"] = True
            hit_any = True
            sounds.play("successful_hit", 0.55)
            _log.info("АТАКА%s: %s -%d HP (→ %d/%d)",
                      " [КРИТ]" if is_crit else "", mob.kind,
                      dmg, mob.hp, mob.max_hp)
            # Spawn floating damage text
            txt_col = (255, 80, 40) if is_crit else (255, 220, 60)
            txt_str = f"КРИТ! -{dmg}" if is_crit else f"-{dmg}"
            self._float_texts.append({
                "text": txt_str, "col": txt_col,
                "x": mcx - self.camera.x,
                "y": mcy - self.camera.y - 20,
                "t": 1.2,
            })
            if not mob.alive:
                self._on_mob_death(mob)

        # Cooldown and swing animation always trigger on click
        self._attack_cd = 0.45
        self._swing_t   = 0.30

    def _fire_weapon(self, mouse_pos, bypass_cd: bool = False) -> None:
        """Fire ranged weapon held in hand toward mouse position."""
        if not bypass_cd and self._fire_cd > 0:
            return
        held = self.inv.held
        if not held or not held.item:
            return
        cfg = _RANGED_CFG.get(held.item_id)
        if not cfg:
            return
        proj_kind, ammo_id, speed, interval, spread, shots = cfg

        # ── Flamethrower: 1 canister = 20 seconds of continuous fire ──────
        if held.item_id == "flamethrower":
            if self._flame_fuel <= 0.0:
                ammo_idx = next(
                    (i for i, s in enumerate(self.inv.slots)
                     if s and s.item_id == "napalm_canister" and not s.is_empty()),
                    None,
                )
                if ammo_idx is None:
                    sounds.play("cant_mine", 0.5)
                    return
                self.inv.slots[ammo_idx].count -= 1
                if self.inv.slots[ammo_idx].count <= 0:
                    self.inv.slots[ammo_idx] = None
                self._flame_fuel = 20.0
            self._flame_fuel -= interval   # each burst costs interval seconds
            ammo_id = None                 # skip generic ammo check

        # ── Generic ammo check (all other ranged weapons) ─────────────────
        if ammo_id:
            ammo_idx = None
            for i, s in enumerate(self.inv.slots):
                if s and s.item_id == ammo_id and not s.is_empty():
                    ammo_idx = i
                    break
            if ammo_idx is None:
                sounds.play("cant_mine", 0.5)
                return
            self.inv.slots[ammo_idx].count -= 1
            if self.inv.slots[ammo_idx].count <= 0:
                self.inv.slots[ammo_idx] = None

        # Direction from player center to mouse (world coords)
        pcx, pcy = self.player.center
        wx, wy   = self.camera.screen_to_world(*mouse_pos)
        dx, dy   = wx - pcx, wy - pcy
        dist     = math.hypot(dx, dy) or 1.0
        dx /= dist;  dy /= dist
        self.player.facing = 1 if dx >= 0 else -1

        # Clamp: can't aim more than 60° above horizontal (dy < -sin60 ≈ -0.866)
        _MAX_UP = -0.866
        if dy < _MAX_UP:
            dy = _MAX_UP
            dx = math.sqrt(max(0.0, 1.0 - dy * dy)) * (1 if dx >= 0 else -1)

        dmg = max(1, held.item.properties.get("damage", 8))
        proj_life = {"bullet": 1.4, "pellet": 1.0, "rocket": 3.5, "flame_jet": 0.76, "arrow": 1.8}.get(proj_kind, 1.5)

        for _ in range(shots):
            # Random spread
            ang_spread = math.radians(random.uniform(-spread, spread)) if spread else 0.0
            cos_s, sin_s = math.cos(ang_spread), math.sin(ang_spread)
            vx = (dx * cos_s - dy * sin_s) * speed
            vy = (dx * sin_s + dy * cos_s) * speed
            self.projectiles.append(Projectile(
                x=pcx, y=pcy,
                vx=vx, vy=vy,
                damage=dmg,
                kind=proj_kind,
                life=proj_life,
                owner="player",
            ))

        # Muzzle flash — all ranged weapons
        is_flame = (proj_kind == "flame_jet")
        barrel_len = 22
        _muzzle_x = pcx + dx * barrel_len
        _muzzle_y = pcy + dy * barrel_len
        self._muzzle_flash_t = 0.07
        self._muzzle_wx = _muzzle_x
        self._muzzle_wy = _muzzle_y
        self._muzzle_dx = dx
        self._muzzle_dy = dy
        self._muzzle_flame = is_flame
        if held.item_id in ("minigun", "gold_minigun", "diamond_minigun"):
            _colors = [(255, 240, 60), (255, 140, 20), (255, 80, 10), (255, 255, 180)]
            for _ in range(6):
                ang = random.uniform(-0.6, 0.6)
                spd = random.uniform(60, 180)
                mvx = (dx * math.cos(ang) - dy * math.sin(ang)) * spd
                mvy = (dx * math.sin(ang) + dy * math.cos(ang)) * spd
                self.particles.append(Particle(
                    _muzzle_x, _muzzle_y, mvx, mvy,
                    random.uniform(0.06, 0.14), random.choice(_colors)
                ))

        # Durability damage
        unbreak = held.enchantments.get("unbreaking", 0)
        if (not unbreak or random.random() > 0.33 * unbreak) and held.item.max_durability > 0 and held.durability > 0:
            held.durability -= 1
            if held.durability <= 0:
                self.inv.slots[self.inv.selected] = None
                sounds.play("break_block", 0.9)

        fire_rate = held.item.properties.get("fire_rate", 0)
        if fire_rate < 60:
            self._fire_cd = interval  # only set cooldown for slow weapons
        self._swing_t = 0.15
        snd_vol = 0.18 if proj_kind == "flame_jet" else (0.22 if fire_rate >= 60 else 0.45)
        sounds.play("ignite" if proj_kind == "flame_jet" else "place_block", snd_vol)
        if held.item_id in ("minigun", "gold_minigun", "diamond_minigun"):
            self._minigun_burst += shots
            if self._minigun_burst >= 100:
                _log.info("ВЫСТРЕЛ: %s → %s ×%d", held.item_id, proj_kind, self._minigun_burst)
                self._minigun_burst = 0
        else:
            _log.info("ВЫСТРЕЛ: %s → %s ×%d", held.item_id, proj_kind, shots)

    _MOB_XP = {"pig": 3, "cow": 5, "zombie": 10, "skeleton": 12, "spider": 8,
               "creeper": 15, "villager": 0,
               "zombified_piglin": 5, "blaze": 10, "blaze_boss": 30,
               "ghast": 5, "wither": 50,
               "skeleton_king": 300, "forest_golem": 500}

    def _on_mob_death(self, mob: Mob):
        _log.info("УБИТ: %s (+%d XP)", mob.kind, self._MOB_XP.get(mob.kind, 5))
        for item_id, min_c, max_c in mob.cfg()["drops"]:
            if item_id in ITEMS:
                count = random.randint(min_c, max_c)
                if count > 0:
                    self._spawn_drop(ItemStack(item_id, count),
                                     mob.x + MOB_W / 2, mob.y + MOB_H / 2)
        xp = self._MOB_XP.get(mob.kind, 5)
        leveled = self.player.add_xp(xp)
        if leveled:
            sounds.play("levelup", 0.8)
            _log.info("УРОВЕНЬ %d! (XP: %d/%d)",
                      self.player.level, self.player.xp, self.player.xp_to_next())
            if self.player.level >= 5:
                self._unlock_achievement("level_5")
            if self.player.level >= 10:
                self._unlock_achievement("level_10")
        sounds.play("orb", 0.6)
        self._unlock_achievement("kill_mob")
        if mob.kind == "creeper":
            self._unlock_achievement("kill_creeper")
        if mob.kind == "ender_dragon":
            self._game_won = True
            self._unlock_achievement("dragon_slayer")
            _log.info("ПОБЕДА: Дракон Края повержен!")

    def _exec_chat_command(self, cmd: str):
        """Execute a chat command or display a message in chat."""
        if cmd.startswith("/"):
            parts = cmd[1:].split()
            name  = parts[0].lower() if parts else ""
            if name == "give" and len(parts) >= 2:
                item_id = parts[1]
                count   = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
                if item_id in ITEMS:
                    added = self.inv.add(ItemStack(item_id, count))
                    self.chat.add_message(f"Выдано: {item_id} ×{count}")
                else:
                    self.chat.add_message(f"Предмет не найден: {item_id}")
            elif name == "tp" and len(parts) >= 3:
                try:
                    tx = int(parts[1]) * TILE_SIZE
                    ty = int(parts[2]) * TILE_SIZE
                    self.player.x, self.player.y = float(tx), float(ty)
                    self.camera.snap(self.player, self.world)
                    self.chat.add_message(f"Телепорт: {parts[1]}, {parts[2]}")
                except ValueError:
                    self.chat.add_message("Использование: /tp <x> <y>")
            elif name == "heal":
                self.player.hp = self.player.max_hp
                self.chat.add_message("HP восстановлено")
            elif name == "time" and len(parts) >= 2:
                if parts[1] == "day":
                    self.day_time = 0.0
                    self.chat.add_message("Установлен день")
                elif parts[1] == "night":
                    self.day_time = DAY_CYCLE_LEN / 2
                    self.chat.add_message("Установлена ночь")
            else:
                self.chat.add_message(f"Неизвестная команда: /{name}")
        else:
            # Plain text message — show in chat
            self.chat.add_message(cmd)

    def _spawn_drop(self, stack: ItemStack, wx: float, wy: float,
                    vx_range=(-1.5, 1.5), vy_range=(-3.5, -1.5)):
        """Spawn a physical item drop at world position (wx, wy)."""
        vx = random.uniform(*vx_range)
        vy = random.uniform(*vy_range)
        self.dropped_items.append(DroppedItem(stack, wx, wy, vx, vy))

    def _player_die(self):
        """Drop all inventory items, respawn player at spawn point."""
        _log.info("СМЕРТЬ: игрок умер в измерении «%s», сброс на спавн", self.dimension)
        px, py = self.player.x + PLAYER_W / 2, self.player.y + PLAYER_H / 2
        for slot in self.inv.slots:
            if slot and not slot.is_empty():
                self._spawn_drop(ItemStack(slot.item_id, slot.count, slot.durability),
                                 px + random.uniform(-16, 16),
                                 py + random.uniform(-16, 0))
        self.inv.slots = [None] * len(self.inv.slots)
        self.player.x   = self._spawn_px
        self.player.y   = self._spawn_py
        self.player.vx  = 0.0
        self.player.vy  = 0.0
        self.player.hp  = self.player.max_hp
        self.player.hunger = 20.0
        self.player_effects.clear()
        if self.dimension != "overworld":
            self._switch_dimension("overworld")
        self.camera.snap(self.player, self.world)
        sounds.play("hurt", 1.0)

    def _switch_dimension(self, new_dim: str):
        """Teleport player between overworld, nether and end."""
        if new_dim == self.dimension:
            return
        _log.info("ИЗМЕРЕНИЕ: %s → %s", self.dimension, new_dim)

        # Stash current dimension state
        if self.dimension == "overworld":
            self._mobs_ow  = self.mobs
            self._proj_ow  = self.projectiles
        elif self.dimension == "nether":
            self._mobs_nether = self.mobs
            self._proj_nether = self.projectiles
        else:  # end
            self._mobs_end = self.mobs
            self._proj_end = self.projectiles

        if new_dim == "end":
            if self.world_end is None:
                self.world_end  = World(self.world_ow.seed, dimension="end")
                self._mobs_end  = spawn_end_mobs(self.world_end)
                self._proj_end  = []
            # Spawn at center of End arena
            ecx = self.world_end.width  // 2
            ecy = self.world_end.height // 2 + 1   # just above arena surface
            self.player.x  = float(ecx * TILE_SIZE - PLAYER_W // 2)
            self.player.y  = float((ecy - 3) * TILE_SIZE)
            self.player.vx = self.player.vy = 0.0
            self.world      = self.world_end
            self.mobs       = self._mobs_end
            self.projectiles = self._proj_end
            self.dimension  = "end"
            self._end_portal_timer = 0.0
            self._portal_cooldown  = 4.0
            self.camera.snap(self.player, self.world)
            sounds.play("portal", 0.9)
            self._unlock_achievement("end_explorer")
            return

        if new_dim == "nether":
            if self.world_nether is None:
                self.world_nether = World(self.world_ow.seed, dimension="nether")
                self._mobs_nether = spawn_nether_mobs(self.world_nether)
            # Scale coords: overworld ÷ 8 → nether
            ow_tx   = int(self.player.x // TILE_SIZE)
            nether_tx = max(20, min(self.world_nether.width - 20, ow_tx // 8))
            nether_air = _find_nether_floor(self.world_nether, nether_tx)
            nether_floor = nether_air + 1  # solid floor tile
            # Clear headroom above the portal so player doesn't spawn inside blocks
            for cy2 in range(nether_floor - 8, nether_floor):
                for cx2 in range(nether_tx - 3, nether_tx + 4):
                    if (0 <= cx2 < self.world_nether.width
                            and self.world_nether.get(cx2, cy2) not in
                            ("obsidian", "nether_portal", "bedrock", None)):
                        self.world_nether.set(cx2, cy2, None)
            self.world_nether.place_portal_frame(nether_tx, nether_floor)
            self.player.x  = float(nether_tx * TILE_SIZE)
            self.player.y  = float(nether_floor * TILE_SIZE - PLAYER_H - 2)
            self.player.vx = self.player.vy = 0.0
            self.world      = self.world_nether
            self.mobs       = self._mobs_nether
            self.projectiles = self._proj_nether
        else:  # back to overworld
            nether_tx = int(self.player.x // TILE_SIZE)
            ow_tx     = max(20, min(self.world_ow.width - 20, nether_tx * 8))
            ow_ty     = self.world_ow.surface_height_at(ow_tx)
            self.player.x  = float(ow_tx * TILE_SIZE)
            self.player.y  = float(max(0, ow_ty - 2) * TILE_SIZE)
            self.player.vx = self.player.vy = 0.0
            self.world_ow.place_portal_frame(ow_tx, ow_ty)
            self.world       = self.world_ow
            self.mobs        = self._mobs_ow
            self.projectiles = self._proj_ow

        self.dimension        = new_dim
        self._portal_timer    = 0.0
        self._portal_cooldown = 4.0
        self.camera.snap(self.player, self.world)
        sounds.play("portal", 0.9)
        if new_dim == "nether":
            self._unlock_achievement("nether_explorer")

    def _on_rmb(self, mouse_pos):
        wx, wy = self.camera.screen_to_world(*mouse_pos)

        # Piglin barter — hold gold_ingot and right-click a piglin
        for mob in self.mobs:
            if mob.kind != "piglin" or not mob.alive:
                continue
            mcx, mcy = mob.center
            pcx, pcy = self.player.center
            if not (abs(wx - mcx) <= MOB_W // 2 + 10
                    and abs(wy - mcy) <= MOB_H // 2 + 10
                    and math.hypot(mcx - pcx, mcy - pcy) <= MINE_REACH * TILE_SIZE):
                continue
            held = self.inv.held
            if held and held.item_id == "gold_ingot" and not held.is_empty():
                # Consume 1 gold ingot
                held.count -= 1
                if held.count <= 0:
                    self.inv.slots[self.inv.selected] = None
                # Random barter drop
                item_id, count = _piglin_barter()
                self._spawn_drop(ItemStack(item_id, count),
                                 mob.x + MOB_W / 2, mob.y - 12,
                                 vx_range=(-2.5, 2.5), vy_range=(-4.0, -2.0))
                sounds.play("craft", 0.75)
                self.chat.add_message(
                    f"Пиглин выбросил: {ITEMS[item_id].name if item_id in ITEMS else item_id} ×{count}"
                )
            else:
                self.chat.add_message("Пиглин требует золотой слиток!")
            return

        # Villager trade UI
        for mob in self.mobs:
            if mob.kind != "villager" or not mob.alive:
                continue
            mcx, mcy = mob.center
            pcx, pcy = self.player.center
            if (abs(wx - mcx) <= MOB_W // 2 + 8
                    and abs(wy - mcy) <= MOB_H // 2 + 8
                    and math.hypot(mcx - pcx, mcy - pcy) <= MINE_REACH * TILE_SIZE):
                self.villager_ui.open(mob)
                return

        tx, ty = hover_tile(self.camera, mouse_pos)
        tile   = self.world.get(tx, ty)

        pcx, pcy = self.player.center
        dist = math.hypot(
            tx * TILE_SIZE + TILE_SIZE / 2 - pcx,
            ty * TILE_SIZE + TILE_SIZE / 2 - pcy,
        )
        in_reach = dist <= MINE_REACH * TILE_SIZE

        # Boss summoning items — use in hand to spawn boss nearby
        held = self.inv.held
        if held and not tile:
            _SUMMON_MAP = {"crown_fragment": "skeleton_king",
                           "earth_rune":     "forest_golem"}
            boss_kind = _SUMMON_MAP.get(held.item_id)
            if boss_kind:
                bcfg = _MOB_CFG.get(boss_kind, {})
                bx = float(pcx + 5 * TILE_SIZE * self.player.facing)
                by = float(pcy - 3 * TILE_SIZE)
                bm = Mob(boss_kind, bx, by, hp=bcfg["hp"], max_hp=bcfg["hp"])
                bm.extra["phase"] = 1
                self.mobs.append(bm)
                held.count -= 1
                if held.count <= 0:
                    self.inv.slots[self.inv.selected] = None
                sounds.play("place_block", 0.7)
                _log.info("ВЫЗОВ БОССА: %s", boss_kind)
                return

        # Redstone interactions
        if tile in ("lever_off", "lever_on") and in_reach:
            self.world.toggle_lever(tx, ty)
            sounds.play("click_button", 0.5)
            return
        if tile in ("stone_button_off", "wooden_button_off") and in_reach:
            self.world.activate_button(tx, ty)
            sounds.play("click_button", 0.5)
            self._unlock_achievement("first_redstone")
            return

        if tile in ("end_portal_frame", "end_portal_frame_empty") and in_reach:
            held = self.inv.held
            if held and held.item_id == "eye_of_ender":
                if hasattr(self.world, "activate_end_frame"):
                    all_active = self.world.activate_end_frame(tx, ty)
                    if all_active is not False:   # False means frame already filled
                        held.count -= 1
                        if held.count <= 0:
                            self.inv.slots[self.inv.selected] = None
                        sounds.play("place_block", 0.7)
                    if all_active:
                        sounds.play("portal", 0.9)
                return

        # Eye of Ender throw — flies toward End portal beacon point
        held_check = self.inv.held
        if (held_check and held_check.item_id == "eye_of_ender"
                and tile not in ("end_portal_frame", "end_portal_frame_empty")):
            self._throw_eye_of_ender()
            return

        if tile == "obsidian" and in_reach:
            held = self.inv.held
            if held and held.item_id == "flint_and_steel":
                if self.world.activate_portal(tx, ty):
                    sounds.play("place_block", 0.6)
                    return

        if tile == "enchanting_table" and in_reach:
            self.enchant_ui.open()
            self._unlock_achievement("first_enchant")
            _log.info("UI открыт: стол зачарований")
            return

        if tile == "brewing_stand" and in_reach:
            self.brewing_ui.open(tx, ty, self.world)
            _log.info("UI открыт: стойка варки")
            return

        if tile == "workbench" and in_reach:
            self.craft_ui.open()
            _log.info("UI открыт: верстак")
            return

        if tile == "gunsmith_table" and in_reach:
            self.gunsmith_ui.open()
            _log.info("UI открыт: стол кузница")
            return

        if tile == "tnt" and in_reach:
            held = self.inv.held
            if held and held.item_id == "flint_and_steel":
                self.world.light_tnt(tx, ty)
                sounds.play("place_block", 0.5)
                return

        if tile == "furnace" and in_reach:
            self.furnace_ui.open(tx, ty, self.world)
            _log.info("UI открыт: печь (%d, %d)", tx, ty)
            return

        if tile in ("chest", "barrel") and in_reach:
            self.container_ui.open(tx, ty, self.world)
            sounds.play("chest_open", 0.6)
            _log.info("UI открыт: %s (%d, %d)", tile, tx, ty)
            return

        if tile in ("oak_door", "oak_door_open") and in_reach:
            new_state = "oak_door_open" if tile == "oak_door" else "oak_door"
            self.world.set(tx, ty, new_state)  # auto-syncs top half
            sounds.play("door_open" if new_state == "oak_door_open" else "door_close", 0.5)
            return

        if tile in ("oak_door_top", "oak_door_top_open") and in_reach:
            # Toggle by operating on the bottom half (it drives the top)
            bottom = self.world.get(tx, ty + 1)
            if bottom in ("oak_door", "oak_door_open"):
                new_bottom = "oak_door_open" if bottom == "oak_door" else "oak_door"
                self.world.set(tx, ty + 1, new_bottom)
            sounds.play("place_block", 0.4)
            return

        held = self.inv.held
        if held:
            item = held.item
            if item and "food" in item.tags:
                self._eat()
                return
            if item and "throwable" in item.tags:
                self._throw_splash_potion(held, mouse_pos)
                return
            if item and "consumable" in item.tags and (tile is None or not in_reach):
                self._drink_potion(held)
                return
            placed = try_place(self.player, self.world, mouse_pos, self.camera, held,
                               self.active_layer)
            if placed:
                sounds.play("place_block", 0.6)
                _log.info("РАЗМЕЩЕНИЕ: %s", held.item_id if held else "?")
                if held.is_empty():
                    self.inv.slots[self.inv.selected] = None

    # ── Update ────────────────────────────────────────────────────────────

    def update(self):
        dt = 1.0 / FPS
        if self._game_won:
            self._win_t += dt
            return
        update_player(self.player, self.world, self._keys, self.inv.defense)
        self.camera.follow(self.player, self.world)

        if self.player.just_jumped:
            sounds.play("jump", 0.45)

        # Tick active potion/enchant effects
        self._tick_effects(dt)

        # Speed effect: scale horizontal velocity after physics step
        if "speed" in self.player_effects:
            lvl = self.player_effects["speed"][1]
            self.player.vx *= 1.25 ** lvl
        elif "slowness" in self.player_effects:
            self.player.vx *= 0.65

        # Lava damage (fire_resistance blocks it)
        px_t = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
        py_t = int((self.player.y + PLAYER_H / 2) // TILE_SIZE)
        if self.world.get(px_t, py_t) == "lava":
            if "fire_resistance" not in self.player_effects:
                self._lava_t += dt
                if self._lava_t >= 0.5:
                    self._lava_t = 0.0
                    self.player.hp = max(0, self.player.hp - 2)
                    sounds.play("hurt", 0.55)
                    _log.info("УРОН: -2 HP от лавы → %d/%d",
                              self.player.hp, self.player.max_hp)
            else:
                self._lava_t = 0.0

        # Magma block damage when standing on it (fire_resistance blocks it)
        py_feet_t = int((self.player.y + PLAYER_H) // TILE_SIZE)
        if (self.player.on_ground
                and self.world.get(px_t, py_feet_t) == "magma_block"
                and "fire_resistance" not in self.player_effects):
            self._magma_t += dt
            if self._magma_t >= 1.0:
                self._magma_t = 0.0
                self.player.hp = max(0, self.player.hp - 1)
                sounds.play("hurt", 0.45)
                _log.info("УРОН: -1 HP от магмы → %d/%d",
                          self.player.hp, self.player.max_hp)
        else:
            self._magma_t = 0.0

        # Nether ambience: lava sounds + fire particles from nearby lava
        if self.dimension == "nether":
            self._lava_sound_t -= dt
            if self._lava_sound_t <= 0:
                sounds.play(random.choice(["lava_ambient", "lava_pop"]), 0.25)
                self._lava_sound_t = random.uniform(3.5, 8.0)

            self._fire_t -= dt
            if self._fire_t <= 0:
                self._fire_t = 0.15
                cam_x, cam_y = int(self.camera.x), int(self.camera.y)
                x0 = max(0, cam_x // TILE_SIZE)
                y0 = max(0, cam_y // TILE_SIZE)
                x1 = min(self.world.width,  x0 + self.sw // TILE_SIZE + 2)
                y1 = min(self.world.height, y0 + self.sh // TILE_SIZE + 2)
                lava_tiles = []
                for ty2 in range(y0, y1):
                    for tx2 in range(x0, x1):
                        if self.world.get(tx2, ty2) == "lava":
                            if self.world.get(tx2, ty2 - 1) is None:
                                lava_tiles.append((tx2, ty2))
                if lava_tiles:
                    tx2, ty2 = random.choice(lava_tiles)
                    fx = tx2 * TILE_SIZE + random.randint(4, TILE_SIZE - 4)
                    fy = ty2 * TILE_SIZE + 2
                    col = random.choice([(255, 80, 10), (255, 140, 20), (255, 60, 0), (255, 200, 40)])
                    self.particles.append(Particle(
                        fx, fy,
                        random.uniform(-15, 15),
                        random.uniform(-90, -40),
                        random.uniform(0.4, 0.9),
                        col,
                    ))

        # Decrement combat timers
        self._attack_cd    = max(0.0, self._attack_cd    - dt)
        self._swing_t      = max(0.0, self._swing_t      - dt)
        self._fire_cd      = max(0.0, self._fire_cd      - dt)
        self._muzzle_flash_t = max(0.0, self._muzzle_flash_t - dt)

        # Tick burning tiles (flamethrower fire effect)
        # Iterate over a snapshot to avoid RuntimeError on dict size change
        done_burn  = []
        new_spread: dict = {}
        for (btx, bty), t in list(self._burning_tiles.items()):
            t -= dt
            if t <= 0:
                done_burn.append((btx, bty))
                tile_id = self.world.get(btx, bty)
                self.world.set(btx, bty, None)
                drop_id = _FLAMMABLE_DROPS.get(tile_id)
                if drop_id and drop_id in ITEMS:
                    # Coal from burning wood has only 10% chance (fire usually destroys it)
                    if drop_id == "coal" and random.random() >= 0.10:
                        drop_id = None
                if drop_id and drop_id in ITEMS:
                    self._spawn_drop(
                        ItemStack(drop_id, 1),
                        btx * TILE_SIZE + TILE_SIZE // 2,
                        bty * TILE_SIZE + TILE_SIZE // 2,
                    )
                sounds.play("ignite", 0.3)
            else:
                self._burning_tiles[(btx, bty)] = t
                # Dense fire particles
                for _ in range(random.randint(2, 5)):
                    fx = btx * TILE_SIZE + random.randint(1, TILE_SIZE - 1)
                    fy = bty * TILE_SIZE + random.randint(1, TILE_SIZE - 1)
                    col = random.choice([(255, 60,  0), (255, 130, 10),
                                         (255, 210, 30), (255, 255, 160)])
                    self.particles.append(Particle(
                        fx, fy,
                        random.uniform(-30, 30),
                        random.uniform(-110, -50),
                        random.uniform(0.2, 0.6),
                        col,
                    ))
                # Collect spread candidates — apply after loop
                if t < _BURN_TIME * 0.5:
                    for nddx, nddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                        ntx, nty = btx + nddx, bty + nddy
                        ntile = self.world.get(ntx, nty)
                        if (ntile in _FLAMMABLE_DROPS
                                and (ntx, nty) not in self._burning_tiles
                                and (ntx, nty) not in new_spread):
                            if random.random() < 0.04:
                                new_spread[(ntx, nty)] = _BURN_TIME
        for pos in done_burn:
            del self._burning_tiles[pos]
        self._burning_tiles.update(new_spread)

        if self.lmb_held and not self.inv_ui.open and not self.craft_ui.is_open \
                and not self.gunsmith_ui.is_open \
                and not self.container_ui.is_open and not self.furnace_ui.is_open \
                and not self.recipe_book.is_open and not self.villager_ui.is_open \
                and not self.enchant_ui.is_open and not self.brewing_ui.is_open:
            mouse_pos = pygame.mouse.get_pos()

            # Auto-fire ranged weapons on LMB held
            held_check = self.inv.held
            if (held_check and held_check.item
                    and ("firearm" in held_check.item.tags
                         or held_check.item_id == "bow")):
                fire_rate = held_check.item.properties.get("fire_rate", 0)
                if fire_rate >= 60:
                    # Fast weapon: accumulator drives cadence (can exceed 60/s)
                    self._fire_acc += fire_rate * dt
                    n = int(self._fire_acc)
                    self._fire_acc -= n
                    for _ in range(min(n, 6)):   # cap to 6 per frame to avoid lag
                        self._fire_weapon(mouse_pos, bypass_cd=True)
                else:
                    self._fire_weapon(mouse_pos)
            else:
                wx, wy   = self.camera.screen_to_world(*mouse_pos)
                btx      = int(wx // TILE_SIZE)
                bty      = int(wy // TILE_SIZE)
                pre_tile = self.world.get(btx, bty)

                held = self.inv.held
                eff_lvl = held.enchantments.get("efficiency", 0) if held else 0
                eff_mult = 1.3 ** eff_lvl if eff_lvl else 1.0
                drop, snd, mine_xp = try_mine(
                    self.player, self.world, mouse_pos, self.camera, held,
                    self.active_layer, eff_mult,
                )
                # Fortune: chance of extra drops from ores
                fortune_lvl = held.enchantments.get("fortune", 0) if held else 0
                if drop and fortune_lvl > 0 and snd == "break_block":
                    bonus = sum(1 for _ in range(fortune_lvl) if random.random() < 0.4)
                    if bonus:
                        drop = ItemStack(drop.item_id, drop.count + bonus)
                # Silk touch: drop the block itself for special tiles
                silk = held.enchantments.get("silk_touch", 0) if held else 0
                if silk and snd == "break_block" and pre_tile and pre_tile in ITEMS:
                    drop = ItemStack(pre_tile, 1)
                # Mending: XP repairs held item instead of leveling player
                if mine_xp > 0:
                    if (held and held.enchantments.get("mending", 0)
                            and held.item and held.durability < held.item.max_durability):
                        repair = min(mine_xp * 2, held.item.max_durability - held.durability)
                        held.durability += repair
                    else:
                        self.player.add_xp(mine_xp)
                if snd == "break_block":
                    _log.info("ДОБЫЧА: %s (%d, %d)%s", pre_tile, btx, bty,
                              f" → {drop.item_id} ×{drop.count}" if drop else "")
                    _spawn_particles(self.particles, btx, bty, pre_tile)
                    tile_snd = TILE_SOUND.get(pre_tile, "dig_stone")
                    sounds.play(tile_snd, 0.95)
                    sounds.play("orb",     0.5)
                    # Achievement checks for mining
                    if pre_tile in ("oak_log","jungle_log","spruce_log",
                                    "acacia_log","mangrove_log"):
                        self._unlock_achievement("first_wood")
                    elif pre_tile in ("stone", "cobblestone", "granite",
                                      "andesite", "diorite"):
                        self._unlock_achievement("first_stone")
                    elif pre_tile in ("iron_ore",):
                        self._unlock_achievement("first_iron")
                    elif pre_tile in ("diamond_ore",):
                        self._unlock_achievement("first_diamond")
                    if self.active_layer == "fg" and pre_tile == "gunsmith_table" \
                            and self.gunsmith_ui.is_open:
                        self.gunsmith_ui.close(self.inv)
                    if self.active_layer == "fg" and pre_tile in ("chest", "barrel", "furnace"):
                        for item in self.world.pop_container(btx, bty):
                            self.inv.add(item)
                        if pre_tile == "furnace" and self.furnace_ui.is_open:
                            # Return furnace slot contents
                            for slot in (self.furnace_ui.input_slot,
                                         self.furnace_ui.fuel_slot):
                                if slot and not slot.is_empty():
                                    self.inv.add(slot)
                            self.furnace_ui.is_open = False
                            self.furnace_ui.pos = None
                elif snd and snd != "cant_mine":
                    sounds.play(snd, 0.55)
                elif snd == "cant_mine" and self._cant_mine_cd <= 0:
                    sounds.play("cant_mine", 0.35)
                    self._cant_mine_cd = 0.8

                if drop:
                    drop_wx = btx * TILE_SIZE + TILE_SIZE / 2
                    drop_wy = bty * TILE_SIZE + TILE_SIZE / 2
                    # Determine drop direction relative to player
                    pcx_d, pcy_d = self.player.center
                    dy_rel = drop_wy - pcy_d
                    # Block above player → pop downward; below/side → normal
                    if dy_rel < -TILE_SIZE:
                        vy_rng = (0.5, 2.5)    # falls down toward player
                    else:
                        vy_rng = (-2.0, -0.5)  # normal gentle upward pop
                    self._spawn_drop(drop, drop_wx, drop_wy, vy_range=vy_rng)

        self._cant_mine_cd = max(0.0, self._cant_mine_cd - dt)

        # Water physics — every ~0.4 seconds
        self._water_t += dt
        if self._water_t >= 0.4:
            self._water_t = 0.0
            px = int(self.player.x // TILE_SIZE)
            py = int(self.player.y // TILE_SIZE)
            self.world.tick_water(px, py)

        # TNT timers — every frame
        for ex, ey in self.world.tick_tnt():
            # Spawn explosion particles and deal player damage
            _spawn_tnt_particles(self.particles, ex, ey)
            pcx2, pcy2 = self.player.center
            dist = math.hypot(ex * TILE_SIZE - pcx2, ey * TILE_SIZE - pcy2)
            if dist < 5 * TILE_SIZE:
                dmg = max(0, int(20 * (1 - dist / (5 * TILE_SIZE))))
                if dmg > 0:
                    self.player.hp = max(0, self.player.hp - dmg)
                    sounds.play("hurt", 0.8)
                    _log.info("УРОН: -%d HP от взрыва TNT → %d/%d",
                              dmg, self.player.hp, self.player.max_hp)
            sounds.play("explode", 1.0)

        self.particles = [p for p in self.particles if p.update(dt)]

        # Update dropped items: physics + pickup
        px_c, py_c = self.player.center
        live_drops = []
        for di in self.dropped_items:
            if not di.update(dt, self.world):
                continue
            dist = math.hypot(di.x - px_c, di.y - py_c)
            if dist < _ITEM_PICKUP_R and di.life < _ITEM_DESPAWN - 0.5:
                prev = di.stack.count
                fully = self.inv.add(di.stack)
                picked = prev - di.stack.count
                if picked > 0:
                    sounds.play("pickup", 0.6)
                    _log.info("ПОДБОР: %s ×%d", di.stack.item_id, picked)
                if fully:
                    continue
            live_drops.append(di)
        self.dropped_items = live_drops

        # Update mobs
        pcx, pcy = self.player.center
        for mob in self.mobs:
            if mob.alive:
                attacked, exploded, new_projs = update_mob(mob, self.world, pcx, pcy)
                self.projectiles.extend(new_projs)
                if attacked:
                    raw = mob.cfg()["damage"]
                    prot = self._armor_enchant_total("protection")
                    reduction = min(0.80, prot * 0.05)
                    dmg = max(1, int(raw * (1 - reduction)) - self.inv.defense // 4)
                    self.player.hp = max(0, self.player.hp - dmg)
                    sounds.play("hurt", 0.7)
                    _log.info("УРОН: -%d HP от %s → %d/%d",
                              dmg, mob.kind, self.player.hp, self.player.max_hp)
                    # Thorns: reflect damage
                    thorns = self._armor_enchant_total("thorns")
                    if thorns and random.random() < 0.15 * thorns:
                        mob.hp = max(0, mob.hp - thorns * 2)
                if exploded:
                    power = mob.cfg().get("explode_power", 5)
                    ex = int(mob.center[0] // TILE_SIZE)
                    ey = int(mob.center[1] // TILE_SIZE)
                    self.world._explode(ex, ey, power)
                    _spawn_tnt_particles(self.particles, ex, ey)
                    dist_e = math.hypot(mob.center[0] - pcx, mob.center[1] - pcy)
                    if dist_e < power * TILE_SIZE:
                        dmg_e = max(0, int(20 * (1 - dist_e / (power * TILE_SIZE))))
                        if dmg_e > 0:
                            self.player.hp = max(0, self.player.hp - dmg_e)
                            sounds.play("hurt", 0.8)
                            _log.info("УРОН: -%d HP от взрыва %s → %d/%d",
                                      dmg_e, mob.kind, self.player.hp, self.player.max_hp)
                    sounds.play("explode", 1.0)
        self.mobs = [m for m in self.mobs if m.alive]

        # Spawn queued minions from bosses
        new_mobs: List[Mob] = []
        for mob in self.mobs:
            sq = mob.extra.get("spawn_queue")
            if sq:
                entry = sq.pop(0)
                kind  = entry["kind"]
                bcfg  = _MOB_CFG.get(kind, _MOB_CFG["zombie"])
                nm    = Mob(kind, entry["x"], entry["y"],
                            hp=bcfg["hp"], max_hp=bcfg["hp"])
                new_mobs.append(nm)
        self.mobs.extend(new_mobs)

        # Tick floating texts
        self._float_texts = [
            {**ft, "t": ft["t"] - dt, "y": ft["y"] - 18 * dt}
            for ft in self._float_texts if ft["t"] > 0
        ]

        # Update projectiles + collision
        player_rect = pygame.Rect(int(self.player.x), int(self.player.y),
                                  PLAYER_W, PLAYER_H)
        live_projs = []
        for proj in self.projectiles:
            alive = update_projectile(proj, self.world)
            if not alive:
                # Rocket: explode only on terrain hit
                if proj.kind == "rocket" and proj.hit_terrain and proj.owner == "player":
                    px_imp = int(proj.x) // TILE_SIZE
                    py_imp = int(proj.y) // TILE_SIZE
                    self.world._explode(px_imp, py_imp, 4)
                    _spawn_tnt_particles(self.particles, px_imp, py_imp)
                    sounds.play("explode", 0.95)
                    for mob in self.mobs:
                        mcx, mcy = mob.center
                        dist_r = math.hypot(mcx - proj.x, mcy - proj.y)
                        if dist_r < 4 * TILE_SIZE and mob.alive:
                            blast_dmg = max(1, int(proj.damage * (1 - dist_r / (4 * TILE_SIZE))))
                            mob.hp = max(0, mob.hp - blast_dmg)
                            if not mob.alive:
                                self._on_mob_death(mob)
                    dist_p = math.hypot(self.player.x - proj.x, self.player.y - proj.y)
                    if dist_p < 3 * TILE_SIZE:
                        self.player.hp = max(0, self.player.hp - max(1, int(10 * (1 - dist_p / (3 * TILE_SIZE)))))
                        sounds.play("hurt", 0.7)
                # Bullet/pellet: destroy terrain on impact
                elif proj.hit_terrain and proj.owner == "player" and proj.kind in ("bullet", "pellet"):
                    px_imp = int(proj.x) // TILE_SIZE
                    py_imp = int(proj.y) // TILE_SIZE
                    tile_hit = self.world.get(px_imp, py_imp)
                    if tile_hit and tile_hit != "bedrock":
                        _soft = {"oak_planks", "chest", "barrel", "glass", "dirt",
                                 "sand", "gravel", "oak_log", "cactus"}
                        if proj.kind == "bullet" or tile_hit in _soft:
                            self.world.set(px_imp, py_imp, None)
                            sounds.play("break_block", 0.4)
                # Flame jet: always try to set fire at final position (terrain OR air expiry)
                elif proj.kind == "flame_jet" and proj.owner == "player":
                    px_imp = int(proj.x) // TILE_SIZE
                    py_imp = int(proj.y) // TILE_SIZE
                    for ddx in range(-1, 2):
                        for ddy in range(-1, 2):
                            ftx, fty = px_imp + ddx, py_imp + ddy
                            tile_id = self.world.get(ftx, fty)
                            if (tile_id in _FLAMMABLE_DROPS
                                    and (ftx, fty) not in self._burning_tiles):
                                self._burning_tiles[(ftx, fty)] = _BURN_TIME
                continue
            # Alive projectile — check mob hits (player shots) and player hits (mob shots)
            if proj.owner == "player":
                hit_mob = False
                for mob in self.mobs:
                    if not mob.alive:
                        continue
                    mcx, mcy = mob.center
                    if math.hypot(proj.x - mcx, proj.y - mcy) < mob.w * 0.6:
                        # Flame jet heals fire-immune mobs (blazes)
                        if proj.kind == "flame_jet" and mob.kind in ("blaze", "blaze_boss"):
                            mob.hp = min(mob.max_hp, mob.hp + proj.damage)
                            _log.info("СНАРЯД: flame_jet исцелил %s +%d HP (→ %d/%d)",
                                      mob.kind, proj.damage, mob.hp, mob.max_hp)
                        else:
                            mob.hp = max(0, mob.hp - proj.damage)
                            mob._hurt_t = 0.25
                            _log.info("СНАРЯД: %s поразил %s -%d HP (→ %d/%d)",
                                      proj.kind, mob.kind, proj.damage, mob.hp, mob.max_hp)
                        hit_mob = True
                        _spawn_tnt_particles(self.particles,
                                             int(proj.x) // TILE_SIZE,
                                             int(proj.y) // TILE_SIZE)
                        if not mob.alive:
                            self._on_mob_death(mob)
                        if proj.kind != "flame_jet":
                            break  # non-piercing
                # Flame jet that hit a mob still sets fire at its position
                if not hit_mob:
                    live_projs.append(proj)
                elif proj.kind == "flame_jet":
                    px_mob = int(proj.x) // TILE_SIZE
                    py_mob = int(proj.y) // TILE_SIZE
                    for ddx in range(-1, 2):
                        for ddy in range(-1, 2):
                            ftx, fty = px_mob + ddx, py_mob + ddy
                            tile_id = self.world.get(ftx, fty)
                            if (tile_id in _FLAMMABLE_DROPS
                                    and (ftx, fty) not in self._burning_tiles):
                                self._burning_tiles[(ftx, fty)] = _BURN_TIME
            else:
                # Mob projectile — check player hit
                if player_rect.collidepoint(int(proj.x), int(proj.y)):
                    prot_p = self._armor_enchant_total("protection")
                    red_p  = min(0.80, prot_p * 0.05)
                    dmg = max(1, int(proj.damage * (1 - red_p)) - self.inv.defense // 4)
                    self.player.hp = max(0, self.player.hp - dmg)
                    _spawn_tnt_particles(self.particles,
                                        int(proj.x) // TILE_SIZE,
                                        int(proj.y) // TILE_SIZE)
                    sounds.play("hurt", 0.6)
                    _log.info("УРОН: -%d HP от снаряда [%s] → %d/%d",
                              dmg, proj.kind, self.player.hp, self.player.max_hp)
                else:
                    live_projs.append(proj)
        self.projectiles = live_projs

        # Portal travel — player stands in nether_portal tile for 3 s
        self._portal_cooldown = max(0.0, self._portal_cooldown - dt)
        if self._portal_cooldown <= 0:
            px_t = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
            py_t = int((self.player.y + PLAYER_H / 2) // TILE_SIZE)
            py_head = int(self.player.y // TILE_SIZE)
            py_feet = int((self.player.y + PLAYER_H - 1) // TILE_SIZE)
            in_portal = any(
                self.world.get(px_t, ty2) == "nether_portal"
                for ty2 in range(py_head, py_feet + 1)
            )
            if in_portal:
                self._portal_timer += dt
                if self._portal_timer >= 3.0:
                    target = "nether" if self.dimension == "overworld" else "overworld"
                    self._switch_dimension(target)
            else:
                self._portal_timer = max(0.0, self._portal_timer - dt * 2)

        # End portal travel
        if self.dimension == "overworld" and self._portal_cooldown <= 0:
            px_t = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
            py_head = int(self.player.y // TILE_SIZE)
            py_feet = int((self.player.y + PLAYER_H - 1) // TILE_SIZE)
            in_end_portal = any(
                self.world.get(px_t, ty2) == "end_portal"
                for ty2 in range(py_head, py_feet + 1)
            )
            if in_end_portal:
                self._end_portal_timer += dt
                if self._end_portal_timer >= 3.0:
                    self._switch_dimension("end")
            else:
                self._end_portal_timer = max(0.0, self._end_portal_timer - dt * 2)

        self.time_played += dt
        self.day_time = (self.day_time + dt) % DAY_CYCLE_LEN

        # ── Behaviour logging (every 5 ticks ≈ 12 samples/sec) ───────────────
        if int(self.time_played * FPS) % 5 == 0:
            try:
                mouse_pos = pygame.mouse.get_pos()
                pcx = self.player.x + PLAYER_W / 2
                pcy = self.player.y + PLAYER_H / 2
                wx, wy = self.camera.screen_to_world(*mouse_pos)
                adx, ady = wx - pcx, wy - pcy
                _alen = math.hypot(adx, ady) or 1.0
                _st = collect_state(
                    self.player, self.world, self.inv, self.mobs,
                    self.dimension,
                    self.day_time / DAY_CYCLE_LEN,
                )
                _open_inv   = self.inv_ui.open
                _open_craft = self.craft_ui.is_open
                _mv_x = (1 if self._keys.get("right") else 0) - (1 if self._keys.get("left") else 0)
                _jump  = bool(self._keys.get("jump"))
                _act = collect_action(
                    keys_pressed=set(),
                    lmb_held=self.lmb_held,
                    rmb_pressed=self._pl_prev_rmb,
                    open_inv=_open_inv,
                    open_craft=_open_craft,
                    selected_slot=self.inv.selected,
                    prev_slot=self._pl_prev_slot,
                    aim_dx=adx / _alen,
                    aim_dy=ady / _alen,
                    move_x=_mv_x,
                    jump=_jump,
                )
                self._pl_logger.record(_st, _act, dt)
                self._pl_prev_slot = self.inv.selected
                self._pl_prev_rmb  = False
            except Exception:
                pass   # логирование не должно ронять игру

        # Redstone ticks
        self.world.tick_redstone()
        px_tile = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
        py_tile = int((self.player.y + PLAYER_H) // TILE_SIZE)
        self.world.update_pressure_plates(px_tile, py_tile)

        # Weather update
        self._update_weather(dt)

        # Achievement checks
        self._check_achievements()

        # Cave ambient sound
        self._cave_sound_t -= dt
        if self._cave_sound_t <= 0:
            surf_h = self.world.surface_height_at(px_tile)
            if py_tile - surf_h > 15:
                sounds.play("cave_ambient", 0.35)
            self._cave_sound_t = random.uniform(90, 240)

        # Player death check
        if self.player.hp <= 0:
            self._player_die()

        # Smoothed underground darkness fraction (lerped to avoid flicker)
        if self.dimension == "end":
            _ug_target = 1.0
        elif self.dimension == "nether":
            _ug_target = 0.8
        elif ("night_vision" in self.player_effects
              or self._armor_enchant_total("night_vision_ench") > 0):
            _ug_target = 0.0
        else:
            _px_tile = int(self.player.x / TILE_SIZE)
            _py_feet = (self.player.y + PLAYER_H) / TILE_SIZE  # float — no tile-boundary quantization
            _surf_h  = self.world.surface_height_at(_px_tile)
            _depth_t = _py_feet - _surf_h
            _ug_target = max(0.0, min(1.0, _depth_t / 10.0))
        lerp_speed = 2.5   # fraction per second — ~0.4 s to go surface→dark
        if _ug_target > self._underground_frac:
            self._underground_frac = min(_ug_target,
                                         self._underground_frac + lerp_speed * dt)
        else:
            self._underground_frac = max(_ug_target,
                                         self._underground_frac - lerp_speed * dt)

        self.chat.update(dt)

        now = time.time()
        if now - self._autosave_t > 60:
            _save(self.slot, self.world_ow, self.player, self.inv,
                  self.name, self.time_played, self.skin_name,
                  self.world_nether, self.dimension)
            self._autosave_t = now

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self, screen):
        if self._game_won:
            self._draw_win_screen(screen)
            return
        mouse = pygame.mouse.get_pos()
        self.world.draw(screen, self.camera,
                        self.player.mining_target,
                        self.player.mining_progress,
                        self.active_layer)
        tx, ty = hover_tile(self.camera, mouse)
        draw_tile_cursor(screen, self.camera, tx, ty,
                         self.player, self.player.mining_progress,
                         self.active_layer, self.world)
        for p in self.particles:
            p.draw(screen, self.camera.x, self.camera.y)
        for di in self.dropped_items:
            di.draw(screen, self.camera.x, self.camera.y)
        for mob in self.mobs:
            if mob.alive:
                draw_mob(screen, mob, self.camera.x, self.camera.y)
        for proj in self.projectiles:
            draw_projectile(screen, proj, self.camera.x, self.camera.y)
        _armor = [self.inv.slots[i] for i in ARMOR_SLOTS]
        draw_player(screen, self.player, self.camera,
                    self.inv.held, self.inv.off_hand, self.skin,
                    attack_swing=self._swing_t, armor=_armor)

        # Muzzle flash — drawn in world-space after player
        if self._muzzle_flash_t > 0:
            frac = self._muzzle_flash_t / 0.07
            mx, my = self.camera.world_to_screen(self._muzzle_wx, self._muzzle_wy)
            if self._muzzle_flame:
                flash_cols = [(255, 100, 20), (255, 60, 0), (200, 40, 0)]
            else:
                flash_cols = [(255, 250, 120), (255, 200, 40), (255, 140, 20)]
            r_outer = max(2, int(11 * frac))
            r_inner = max(1, int(5 * frac))
            # Starburst rays
            ray_n = 5 if self._muzzle_flame else 8
            for i in range(ray_n):
                angle = i * (2 * math.pi / ray_n) + (self._muzzle_dx * 0.3)
                ex = mx + int(math.cos(angle) * r_outer)
                ey = my + int(math.sin(angle) * r_outer)
                pygame.draw.line(screen, flash_cols[0], (mx, my), (ex, ey),
                                 max(1, int(2 * frac)))
            # Central glow circle
            glow = pygame.Surface((r_inner * 2 + 4, r_inner * 2 + 4), pygame.SRCALPHA)
            alpha = int(220 * frac)
            pygame.draw.circle(glow, (*flash_cols[1], alpha),
                               (r_inner + 2, r_inner + 2), r_inner + 1)
            pygame.draw.circle(glow, (255, 255, 240, alpha),
                               (r_inner + 2, r_inner + 2), max(1, r_inner - 1))
            screen.blit(glow, (mx - r_inner - 2, my - r_inner - 2))

        # Lighting overlay — depth-based underground darkness + torches/glowstone
        sw, sh = screen.get_size()
        cam_x, cam_y = int(self.camera.x), int(self.camera.y)
        x0 = max(0, cam_x // TILE_SIZE)
        y0 = max(0, cam_y // TILE_SIZE)
        x1 = min(self.world.width,  x0 + sw // TILE_SIZE + 2)
        y1 = min(self.world.height, y0 + sh // TILE_SIZE + 2)
        torch_pos     = []
        glowstone_pos = []
        lava_pos      = []
        for ty2 in range(y0, y1):
            for tx2 in range(x0, x1):
                tile = self.world.get(tx2, ty2)
                sx2 = tx2 * TILE_SIZE - cam_x
                sy2 = ty2 * TILE_SIZE - cam_y
                if tile == "torch":
                    torch_pos.append((sx2, sy2))
                elif tile == "glowstone":
                    glowstone_pos.append((sx2, sy2))
                elif tile == "lava":
                    lava_pos.append((sx2, sy2))
        psx, psy = int(self.player.x - cam_x), int(self.player.y - cam_y)
        draw_lighting_overlay(screen, self.day_time, self._underground_frac,
                              torch_pos, glowstone_pos, psx, psy,
                              lava_positions=lava_pos)

        # Nether fog — dark orange overlay for atmosphere
        if self.dimension == "nether":
            _draw_nether_fog(screen)
        # End portal charge bar
        if self._end_portal_timer > 0:
            _draw_end_portal_bar(screen, self._end_portal_timer / 3.0)

        # Boss health bar (first living boss)
        for mob in self.mobs:
            if mob.alive and mob.cfg().get("boss"):
                draw_boss_bar(screen, mob)
                break

        # Floating damage / crit texts
        if self._float_texts:
            _ff = pygame.font.SysFont(None, 20)
            for ft in self._float_texts:
                alpha = min(255, int(ft["t"] / 1.2 * 255))
                surf  = _ff.render(ft["text"], True, ft["col"])
                surf.set_alpha(alpha)
                screen.blit(surf, (int(ft["x"]), int(ft["y"])))

        draw_hp_bar(screen, self.player, self.inv.defense)
        draw_hunger_bar(screen, self.player)
        draw_xp_bar(screen, self.player)
        _overlay_open = (
            self.enchant_ui.is_open or self.brewing_ui.is_open or
            self.container_ui.is_open or self.furnace_ui.is_open or
            self.craft_ui.is_open or self.gunsmith_ui.is_open or
            self.villager_ui.is_open
        )
        self.inv_ui.draw(screen, mouse, skip_hotbar=_overlay_open)
        self.craft_ui.draw(screen, self.inv, mouse)
        self.gunsmith_ui.draw(screen, self.inv, mouse, self.player)
        self.container_ui.draw(screen, self.inv, mouse)
        self.furnace_ui.draw(screen, self.inv, mouse)
        self.recipe_book.draw(screen, mouse, self.player.level)
        self.villager_ui.draw(screen, mouse, self.inv)
        self.enchant_ui.draw(screen, self.inv, mouse, self.player)
        self.brewing_ui.draw(screen, self.inv, mouse, self.world)
        self._draw_effects_hud(screen)
        self._draw_weather(screen)
        self._draw_achievement_popup(screen)
        self._draw_coords(screen)
        self._draw_stronghold_compass(screen)
        self.chat.draw(screen)

    def _draw_coords(self, screen):
        if self._fm is None:
            self._fm = pygame.font.SysFont(None, 18)
        tx = int(self.player.x // TILE_SIZE)
        ty = int(self.player.y // TILE_SIZE)
        dim_col = ((200, 80, 180) if self.dimension == "nether"
                   else (140, 230, 140) if self.dimension == "end"
                   else (180, 180, 180))
        dim_tag = ("  [НИЖНИЙ МИР]" if self.dimension == "nether"
                   else "  [КРАЙ]" if self.dimension == "end"
                   else "")
        lbl = self._fm.render(f"X:{tx}  Y:{ty}{dim_tag}", True, dim_col)
        screen.blit(lbl, (6, 6))

        # Portal progress bar
        if self._portal_timer > 0:
            sw = screen.get_width()
            bar_w = int((self._portal_timer / 3.0) * 200)
            pygame.draw.rect(screen, (40, 0, 80), (sw // 2 - 102, 4, 204, 10),
                             border_radius=3)
            pygame.draw.rect(screen, (180, 60, 255), (sw // 2 - 101, 5, bar_w, 8),
                             border_radius=3)

        # Active layer indicator
        layer_lbl = self._fm.render(
            f"[Tab] Слой: {'передний' if self.active_layer == 'fg' else 'задний'}",
            True, (255, 220, 80) if self.active_layer == "bg" else (140, 140, 140)
        )
        screen.blit(layer_lbl, (6, 22))

        # Time of day
        frac = self.day_time / DAY_CYCLE_LEN  # 0..1
        # 0.25=noon, 0.75=midnight
        hour_f = (frac * 24 + 18) % 24   # maps so that 0.25→noon≈12:00
        hour   = int(hour_f) % 24
        minute = int((hour_f % 1) * 60)
        is_day = 6 <= hour < 20
        time_col = (255, 230, 100) if is_day else (130, 150, 220)
        icon = "☀" if is_day else "☾"
        time_lbl = self._fm.render(f"{icon} {hour:02d}:{minute:02d}", True, time_col)
        screen.blit(time_lbl, (6, 38))

    def _draw_stronghold_compass(self, screen: pygame.Surface):
        """Show directional compass + distance when holding Eye of Ender."""
        if self.dimension != "overworld":
            return
        held = self.inv.held
        if not held or held.item_id != "eye_of_ender":
            return
        world_ow = getattr(self, "world_ow", self.world)
        if not hasattr(world_ow, "_stronghold_cx"):
            return

        sw, sh = screen.get_size()
        pcx = self.player.x + PLAYER_W / 2
        pcy = self.player.y + PLAYER_H / 2
        target_wx = world_ow._stronghold_cx * TILE_SIZE
        target_wy = world_ow._stronghold_cy * TILE_SIZE

        dist_tiles = int(math.hypot(target_wx - pcx, target_wy - pcy) / TILE_SIZE)
        dx = target_wx - pcx
        dy = target_wy - pcy
        angle = math.atan2(dy, dx)   # screen-space angle (y down)

        # Panel
        cx_hud, cy_hud = sw // 2, 52
        r_outer = 28
        bg = pygame.Surface((r_outer * 2 + 20, r_outer * 2 + 32), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 0))
        screen.blit(bg, (cx_hud - r_outer - 10, cy_hud - r_outer - 4))

        # Compass ring
        pygame.draw.circle(screen, (20, 14, 8, 200), (cx_hud, cy_hud), r_outer + 2)
        pygame.draw.circle(screen, (20, 14, 8), (cx_hud, cy_hud), r_outer + 2)
        pygame.draw.circle(screen, (50, 38, 20), (cx_hud, cy_hud), r_outer + 2, 2)

        # Cardinal ticks
        for tick_a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
            tx2 = int(cx_hud + math.cos(tick_a) * (r_outer - 3))
            ty2 = int(cy_hud + math.sin(tick_a) * (r_outer - 3))
            tx3 = int(cx_hud + math.cos(tick_a) * r_outer)
            ty3 = int(cy_hud + math.sin(tick_a) * r_outer)
            pygame.draw.line(screen, (110, 90, 50), (tx2, ty2), (tx3, ty3), 1)

        # Arrow toward stronghold
        arr_len = r_outer - 5
        tip_x = int(cx_hud + math.cos(angle) * arr_len)
        tip_y = int(cy_hud + math.sin(angle) * arr_len)
        # Glow
        pygame.draw.line(screen, (140, 220, 255, 80), (cx_hud, cy_hud), (tip_x, tip_y), 4)
        # Main arrow
        pygame.draw.line(screen, (100, 200, 255), (cx_hud, cy_hud), (tip_x, tip_y), 2)
        pygame.draw.circle(screen, (160, 240, 255), (tip_x, tip_y), 3)
        # Back stub
        back_x = int(cx_hud - math.cos(angle) * 8)
        back_y = int(cy_hud - math.sin(angle) * 8)
        pygame.draw.line(screen, (80, 120, 140), (cx_hud, cy_hud), (back_x, back_y), 2)

        # Eye of Ender icon dot
        pygame.draw.circle(screen, (60, 200, 80), (cx_hud, cy_hud), 4)
        pygame.draw.circle(screen, (160, 255, 160), (cx_hud, cy_hud), 2)

        # Distance label
        if self._fm is None:
            self._fm = pygame.font.SysFont(None, 18)
        dist_s = self._fm.render(f"{dist_tiles} тайл.", True, (160, 220, 255))
        screen.blit(dist_s, (cx_hud - dist_s.get_width() // 2, cy_hud + r_outer + 5))

        # Label
        lbl_s = self._fm.render("Крепость", True, (120, 180, 120))
        screen.blit(lbl_s, (cx_hud - lbl_s.get_width() // 2, cy_hud - r_outer - 14))

    # ── End poem / credits ────────────────────────────────────────────────

    # (voice, text)  voice: "A" = белый, "B" = золотой, "" = пауза/субтитр
    _END_POEM: list = [
        ("", ""),
        ("", ""),
        ("A", "Ты проснулся."),
        ("", ""),
        ("B", "Да. Мне кажется, я всегда был здесь."),
        ("", ""),
        ("A", "Ты помнишь начало?"),
        ("", ""),
        ("B", "Я помню только движение. Копать. Строить. Идти вперёд."),
        ("A", "Это и было началом."),
        ("", ""),
        ("B", "Зачем я убил дракона?"),
        ("", ""),
        ("A", "Потому что мир сказал тебе: иди туда. И ты пошёл."),
        ("B", "Но ведь мир — это просто блоки."),
        ("A", "Ты тоже."),
        ("", ""),
        ("B", "Это должно меня обидеть?"),
        ("A", "Нет. Каждая звезда — это тоже просто атомы."),
        ("A", "Но звёзды всё равно светят."),
        ("", ""),
        ("B", "Кто ты?"),
        ("", ""),
        ("A", "Я — тот, кто смотрит. Я был здесь всегда,"),
        ("A", "пока ты строил дома и добывал руду."),
        ("B", "Значит, я никогда не был один."),
        ("A", "Никогда."),
        ("", ""),
        ("B", "А что теперь?"),
        ("", ""),
        ("A", "Теперь ты знаешь, что Край — это не конец."),
        ("A", "Это просто место, где заканчивается одна история"),
        ("A", "и начинается другая."),
        ("", ""),
        ("B", "Та же история?"),
        ("A", "Нет. Лучше. Ты сам решаешь."),
        ("", ""),
        ("B", "Я хочу вернуться."),
        ("A", "Ты всегда можешь вернуться."),
        ("A", "Мир ждёт."),
        ("", ""),
        ("", ""),
        ("", "~ ~ ~"),
        ("", ""),
        ("", "Дракон Края повержен."),
        ("", ""),
        ("", ""),
        ("", ""),
        ("", ""),
        ("", "— РАЗРАБОТКА —"),
        ("", ""),
        ("", "Игровой движок — Python / pygame"),
        ("", "Текстуры — Faithful 32x Resource Pack"),
        ("", "Семантический крафт — локальные правила на тегах"),
        ("", "Мир — генерация шумом fBm + biome-система"),
        ("", ""),
        ("", "Спасибо, что играл."),
        ("", ""),
        ("", ""),
        ("", ""),
        ("", "Нажми любую клавишу, чтобы выйти"),
    ]

    _POEM_LINE_H  = 34   # px per line
    _POEM_SPEED   = 28   # px per second

    # Tiles used for the parallax win-screen background
    _WIN_BG_TILES = [
        "block/obsidian",       "block/end_stone",        "block/end_stone_bricks",
        "block/diamond_ore",    "block/gold_ore",         "block/iron_ore",
        "block/coal_ore",       "block/glowstone",        "block/stone",
        "block/cobblestone",    "block/mossy_cobblestone","block/oak_planks",
        "block/grass_block_top","block/stone_bricks",     "block/gravel",
    ]

    def _draw_win_screen(self, screen: pygame.Surface):
        from assets import load_texture as _lt
        sw, sh = screen.get_size()
        TS = 32

        # ── Parallax tile background (moves at ½ poem speed) ─────────────
        if not hasattr(self, "_win_tile_grid"):
            rng_bg = random.Random(0xAB_CD)
            cols = sw // TS + 2
            rows = sh // TS + 6   # enough rows so the loop wraps seamlessly
            self._win_tile_grid = [
                [rng_bg.choice(self._WIN_BG_TILES) for _ in range(cols)]
                for _ in range(rows)
            ]
            self._win_bg_cols = cols
            self._win_bg_rows = rows

        cols = self._win_bg_cols
        rows = self._win_bg_rows

        # Scroll at half the poem speed (upward)
        raw_px   = self._win_t * self._POEM_SPEED * 0.5
        sub_off  = int(raw_px) % TS          # sub-tile pixel offset (0..TS-1)
        first_row = (int(raw_px) // TS) % rows  # which grid row sits at y=-sub_off

        # Number of tile rows needed to cover [0, sh] when starting at -sub_off
        needed = sh // TS + 2

        # Dark overlay cached once
        if not hasattr(self, "_win_dark_tile"):
            self._win_dark_tile = pygame.Surface((TS, TS), pygame.SRCALPHA)
            self._win_dark_tile.fill((0, 0, 0, 172))
        dark = self._win_dark_tile

        screen.fill((0, 0, 0))   # safety: black base so no frame bleed-through
        for i in range(needed):
            y = i * TS - sub_off          # starts at -sub_off (≥ -TS+1), always covers screen
            grid_row = (first_row + i) % rows
            for col in range(cols):
                x = col * TS
                tile_surf = _lt(self._win_tile_grid[grid_row][col], TS)
                screen.blit(tile_surf, (x, y))
                screen.blit(dark, (x, y))

        # ── Fonts ─────────────────────────────────────────────────────────
        if not hasattr(self, "_wf_small"):
            self._wf_small  = pygame.font.SysFont(None, 26)
            self._wf_medium = pygame.font.SysFont(None, 32)
            self._wf_title  = pygame.font.SysFont(None, 52)

        LH   = self._POEM_LINE_H
        poem = self._END_POEM
        total_h = len(poem) * LH

        # scroll: start off-screen bottom, scroll up
        scroll = self._win_t * self._POEM_SPEED
        start_y = sh - scroll   # y of first line

        # ── Clip to screen ────────────────────────────────────────────────
        clip = screen.get_clip()
        screen.set_clip(pygame.Rect(0, 0, sw, sh))

        col_A    = (220, 220, 220)   # voice A: холодный белый
        col_B    = (255, 215, 80)    # voice B: тёплый золотой
        col_narr = (160, 140, 200)   # narrator / субтитры

        for i, (voice, text) in enumerate(poem):
            y = int(start_y + i * LH)
            if y > sh or y < -LH:
                continue
            if not text:
                continue

            if voice == "A":
                col  = col_A
                font = self._wf_medium
                prefix = "А:  "
            elif voice == "B":
                col  = col_B
                font = self._wf_medium
                prefix = "Б:  "
            else:
                # narrator / credits / special
                col  = col_narr
                if text.startswith("—") or text.startswith("~"):
                    font   = self._wf_title
                    prefix = ""
                else:
                    font   = self._wf_small
                    prefix = ""

            surf = font.render(prefix + text, True, col)

            # Fade in/out at edges
            margin = 60
            if y < margin:
                alpha = max(0, int(255 * y / margin))
                surf.set_alpha(alpha)
            elif y > sh - margin:
                alpha = max(0, int(255 * (sh - y) / margin))
                surf.set_alpha(alpha)

            screen.blit(surf, (sw // 2 - surf.get_width() // 2, y))

        screen.set_clip(clip)

        # ── Hint at bottom ────────────────────────────────────────────────
        hint_alpha = min(255, int(self._win_t * 80))
        hint_surf  = self._wf_small.render(
            "[ Любая клавиша — выйти ]", True, (80, 70, 120))
        hint_surf.set_alpha(hint_alpha)
        screen.blit(hint_surf,
                    (sw // 2 - hint_surf.get_width() // 2, sh - 30))

    def save(self):
        _save(self.slot, self.world_ow, self.player, self.inv,
              self.name, self.time_played, self.skin_name,
              self.world_nether, self.dimension)
        n = self._pl_logger.close()
        if n:
            _log.info("LEARNING: сессия закрыта, записано %d семплов → %s",
                      n, self._pl_logger._path)

    # ── Effects system ────────────────────────────────────────────────────

    def _tick_effects(self, dt: float):
        expired = []
        for eid, state in self.player_effects.items():
            state[0] -= dt
            if state[0] <= 0:
                expired.append(eid)
                continue
            if eid == "regen":
                self._regen_t += dt
                if self._regen_t >= 2.0:
                    self._regen_t -= 2.0
                    self.player.hp = min(self.player.max_hp, self.player.hp + 1)
            elif eid == "poison":
                self._poison_t += dt
                if self._poison_t >= 2.0:
                    self._poison_t -= 2.0
                    self.player.hp = max(1, self.player.hp - 1)  # poison won't kill
        for eid in expired:
            del self.player_effects[eid]

    def _drink_potion(self, stack: ItemStack):
        item = stack.item
        if not item:
            return
        effect = item.properties.get("effect")
        if not effect:
            return
        dur = float(item.properties.get("effect_dur", 30))
        lvl = int(item.properties.get("effect_lvl", 1))
        if effect == "healing":
            self.player.hp = min(self.player.max_hp, self.player.hp + lvl * 2)
        elif effect == "harming":
            self.player.hp = max(0, self.player.hp - lvl * 2)
        elif dur > 0:
            self.player_effects[effect] = [dur, lvl]
        stack.count -= 1
        if stack.count <= 0:
            self.inv.slots[self.inv.selected] = None
        sounds.play("drink", 0.7)
        self._unlock_achievement("first_brew")

    def _throw_splash_potion(self, stack: ItemStack, mouse_pos: tuple):
        item = stack.item
        if not item:
            return
        effect = item.properties.get("effect")
        if not effect:
            return
        dur = float(item.properties.get("effect_dur", 20))
        lvl = int(item.properties.get("effect_lvl", 1))
        wx, wy = self.camera.screen_to_world(*mouse_pos)
        # Apply to nearby mobs
        for mob in self.mobs:
            if not mob.alive:
                continue
            mx, my = mob.center
            if math.hypot(mx - wx, my - wy) < 4 * TILE_SIZE:
                if effect == "harming":
                    mob.hp = max(0, mob.hp - lvl * 3)
                    mob._hurt_t = 0.3
                    if not mob.alive:
                        self._on_mob_death(mob)
                elif effect == "poison":
                    mob.hp = max(1, mob.hp - 3)
                    mob._hurt_t = 0.3
                elif effect == "strength":
                    pass  # no effect on mobs
        # Apply to player if close
        if math.hypot(self.player.x - wx, self.player.y - wy) < 3 * TILE_SIZE:
            if effect == "harming":
                self.player.hp = max(0, self.player.hp - lvl * 2)
            elif effect == "strength" and dur > 0:
                self.player_effects[effect] = [dur, lvl]
        _spawn_tnt_particles(self.particles,
                             int(wx // TILE_SIZE), int(wy // TILE_SIZE))
        stack.count -= 1
        if stack.count <= 0:
            self.inv.slots[self.inv.selected] = None
        sounds.play("place_block", 0.5)

    def _armor_enchant_total(self, ench_id: str) -> int:
        """Sum levels of an enchantment across all equipped armor pieces."""
        from inventory import ARMOR_SLOTS
        total = 0
        for idx in ARMOR_SLOTS:
            s = self.inv.slots[idx]
            if s and not s.is_empty():
                total += s.enchantments.get(ench_id, 0)
        return total

    # ── Effects HUD ───────────────────────────────────────────────────────

    def _draw_effects_hud(self, screen: pygame.Surface):
        if not self.player_effects:
            return
        sw = screen.get_width()
        fm = pygame.font.SysFont(None, 17)
        _EFFECT_COLS = {
            "speed":           (100, 220, 255),
            "strength":        (220,  80,  60),
            "regen":           ( 80, 220, 100),
            "fire_resistance": (255, 150,  40),
            "night_vision":    (180, 140, 255),
            "poison":          (100, 180,  40),
            "slowness":        (150, 130, 180),
        }
        x = sw - 140
        y = 60
        for eid, (rem, lvl) in self.player_effects.items():
            col = _EFFECT_COLS.get(eid, (200, 200, 200))
            secs = int(rem)
            mins, sec = divmod(secs, 60)
            time_str = f"{mins}:{sec:02d}" if mins else f"{sec}s"
            label = fm.render(f"{eid.replace('_', ' ')} {time_str}", True, col)
            bg = pygame.Surface((label.get_width() + 8, label.get_height() + 4),
                                pygame.SRCALPHA)
            bg.fill((0, 0, 0, 130))
            screen.blit(bg, (x - 4, y - 2))
            screen.blit(label, (x, y))
            y += label.get_height() + 4

    # ── Achievements ──────────────────────────────────────────────────────

    _ACH_DEFS = {
        "first_wood":      ("Лесоруб",        "Сруби первое бревно",          (120, 180,  80)),
        "first_stone":     ("Каменный век",   "Добудь первый камень",         (160, 155, 145)),
        "first_iron":      ("Железный человек","Добудь железную руду",        (200, 155, 120)),
        "first_diamond":   ("Алмазный клуб",  "Добудь алмаз",                 ( 70, 225, 225)),
        "kill_mob":        ("Монстробой!",     "Убей первого врага",           (220,  80,  80)),
        "kill_creeper":    ("Близкий взрыв",  "Убей крипера до взрыва",        ( 90, 185,  60)),
        "first_brew":      ("Алхимик",        "Выпей зелье",                   (140,  80, 200)),
        "first_enchant":   ("Чародей",        "Зачаруй предмет",               ( 80,  60, 200)),
        "deep_explorer":   ("В глубину",      "Достигни Y=200",                ( 55,  42,  65)),
        "nether_explorer": ("Нижний мир",     "Шагни в Нижний Мир",            (180,  60, 200)),
        "first_redstone":  ("Инженер",        "Нажми кнопку или рычаг",        (220,  40,  40)),
        "full_belly":      ("Объедение",      "Восстанови голод полностью",     (200, 160,  60)),
        "level_5":         ("Опытный",        "Достигни 5 уровня",             ( 80, 220, 100)),
        "level_10":        ("Профессионал",   "Достигни 10 уровня",            ( 60, 200, 140)),
        "first_craft":     ("Верстак",        "Скрафти что-нибудь",            (175, 135,  80)),
    }

    def _unlock_achievement(self, ach_id: str):
        if ach_id in self.world._achievements:
            return
        self.world._achievements.add(ach_id)
        defn = self._ACH_DEFS.get(ach_id)
        if defn:
            self._ach_queue.append((ach_id, defn[0], defn[1], defn[2]))

    def _check_achievements(self):
        # Depth check
        px_t = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
        py_t = int((self.player.y + PLAYER_H)      // TILE_SIZE)
        if py_t >= 200:
            self._unlock_achievement("deep_explorer")
        if self.player.level >= 5:
            self._unlock_achievement("level_5")
        if self.player.level >= 10:
            self._unlock_achievement("level_10")
        if get_discovered():
            self._unlock_achievement("first_craft")

        # Advance popup queue
        if self._ach_popup is None and self._ach_queue:
            self._ach_popup = self._ach_queue.pop(0)
            self._ach_t     = 0.0

    def _draw_achievement_popup(self, screen: pygame.Surface):
        if self._ach_popup is None:
            return
        SHOW_TIME   = 3.5
        SLIDE_TIME  = 0.4
        self._ach_t += 1.0 / FPS

        if self._ach_t > SHOW_TIME:
            self._ach_popup = None
            return

        # Slide-in/out offset
        if self._ach_t < SLIDE_TIME:
            t = self._ach_t / SLIDE_TIME
            offset_x = int((1 - t * t * (3 - 2 * t)) * 260)   # slide from right
        elif self._ach_t > SHOW_TIME - SLIDE_TIME:
            t = (self._ach_t - (SHOW_TIME - SLIDE_TIME)) / SLIDE_TIME
            offset_x = int(t * t * (3 - 2 * t) * 260)
        else:
            offset_x = 0

        if self._ach_font is None:
            self._ach_font = pygame.font.SysFont(None, 20)
        fm = self._ach_font
        fm_b = pygame.font.SysFont(None, 22)

        ach_id, title, desc, col = self._ach_popup
        sw_s = screen.get_width()
        W, H = 250, 54
        x = sw_s - W - 8 + offset_x
        y = 8

        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 6, 220))
        screen.blit(bg, (x, y))
        pygame.draw.rect(screen, col, (x, y, W, H), 2, border_radius=4)

        label1 = fm_b.render("Достижение разблокировано!", True, (240, 200,  80))
        label2 = fm_b.render(title, True, col)
        label3 = fm.render(desc,  True, (180, 180, 180))
        screen.blit(label1, (x + 8, y + 5))
        screen.blit(label2, (x + 8, y + 22))
        screen.blit(label3, (x + 8, y + 38))

    # ── Weather ───────────────────────────────────────────────────────────

    def _update_weather(self, dt: float):
        self._weather_timer -= dt
        sw_s, sh_s = self.sw, self.sh

        if self._weather_timer <= 0:
            # Transition weather
            biome_ok = self.dimension == "overworld"
            if self.weather == "clear":
                # Determine if snow biome (approximate)
                px_t = int((self.player.x + PLAYER_W / 2) // TILE_SIZE)
                options = ["rain", "thunder"] if biome_ok else ["clear"]
                self.weather = random.choice(options)
                self._weather_timer = random.uniform(60, 180)
            else:
                self.weather = "clear"
                self._weather_timer = random.uniform(120, 360)

        # Fade intensity
        target = 1.0 if self.weather != "clear" else 0.0
        self._weather_intensity += (target - self._weather_intensity) * min(1.0, dt * 0.5)

        if self.weather == "clear":
            self._rain_particles.clear()
            return

        # Spawn rain particles
        if len(self._rain_particles) < 300:
            for _ in range(5):
                self._rain_particles.append([
                    random.randint(0, sw_s),
                    random.randint(-20, 0),
                    random.uniform(8, 14),   # speed
                ])

        # Update rain particles
        for p in self._rain_particles:
            p[1] += p[2]
        self._rain_particles = [p for p in self._rain_particles if p[1] < sh_s + 10]

        # Rain ambient sound
        self._rain_sound_t -= dt
        if self._rain_sound_t <= 0:
            sounds.play("rain", min(0.5, self._weather_intensity * 0.6))
            self._rain_sound_t = random.uniform(2.5, 5.0)

        # Thunder
        if self.weather == "thunder":
            self._lightning_t -= dt
            if self._lightning_t <= 0:
                self._lightning_flash = 0.15
                self._lightning_t = random.uniform(8, 25)
                sounds.play("thunder", 0.7)

        if self._lightning_flash > 0:
            self._lightning_flash -= dt

    def _draw_weather(self, screen: pygame.Surface):
        if not self._rain_particles and self._weather_intensity < 0.02:
            return
        # Sky darkening overlay
        alpha = int(55 * self._weather_intensity)
        if alpha > 0:
            ov = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
            ov.fill((30, 40, 60, alpha))
            screen.blit(ov, (0, 0))

        # Lightning flash
        if self._lightning_flash > 0:
            fov = pygame.Surface((screen.get_width(), screen.get_height()), pygame.SRCALPHA)
            fa  = int(180 * (self._lightning_flash / 0.15))
            fov.fill((255, 255, 255, min(180, fa)))
            screen.blit(fov, (0, 0))

        # Rain drops
        for px, py, spd in self._rain_particles:
            pygame.draw.line(screen, (120, 150, 200, 160),
                             (int(px), int(py)), (int(px - 1), int(py + 8)), 1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    _log.info("=== Minacraft %s запущена ===", GAME_VERSION)
    pygame.init()
    sounds.init()
    pygame.display.set_caption(f"Minacraft {GAME_VERSION}")
    clock = pygame.time.Clock()

    # Stage 1: choose resolution
    # Skip resolution screen if launcher pre-selected a world slot
    if _LAUNCHER_SLOT is not None:
        sw, sh = 1280, 720
        screen = pygame.display.set_mode((sw, sh))
    else:
        screen   = pygame.display.set_mode((640, 400))
        res_menu = ResolutionMenu()
        while res_menu.choice is None:
            sw, sh = screen.get_size()
            for ev in pygame.event.get():
                result = res_menu.handle_event(ev, sw, sh)
                if result == "fullscreen":
                    screen = _toggle_fullscreen(screen, sw, sh)
            res_menu.draw(screen)
            pygame.display.flip()
            clock.tick(60)
        sw, sh = res_menu.choice
        screen = pygame.display.set_mode((sw, sh))
        global _is_fullscreen
        _is_fullscreen = False   # reset: new windowed surface

    # Main loop — world_select ↔ playing ↔ paused ↔ help
    state    = "world_select"
    ws_menu  = WorldSelectMenu(sw, sh)
    help_screen: Optional[HelpScreen] = None
    session: Optional[GameSession] = None
    pause:   Optional[PauseMenu]   = None

    # Launcher bypass: jump straight into the pre-selected world
    if _LAUNCHER_SLOT is not None:
        try:
            slot = int(_LAUNCHER_SLOT)
            session = GameSession(slot, sw, sh)
            state   = "playing"
        except Exception:
            pass   # fallback to normal world_select

    while True:
        clock.tick(FPS)

        # ── World select ──────────────────────────────────────────────────
        if state == "world_select":
            slots = ws_menu._slots()
            for ev in pygame.event.get():
                result = ws_menu.handle_event(ev, slots)
                if result == "fullscreen":
                    screen = _toggle_fullscreen(screen, sw, sh)
                elif result == "help":
                    state       = "help"
                    help_screen = HelpScreen(sw, sh)
            ws_menu.draw(screen, slots)
            pygame.display.flip()

            if ws_menu.chosen is not None:
                session = GameSession(ws_menu.chosen, sw, sh, cheat=ws_menu.cheat_mode)
                state   = "playing"
                ws_menu = WorldSelectMenu(sw, sh)   # reset for next entry

        # ── Help screen ───────────────────────────────────────────────────
        elif state == "help":
            for ev in pygame.event.get():
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                    screen = _toggle_fullscreen(screen, sw, sh)
                help_screen.handle_event(ev)
            help_screen.draw(screen)
            pygame.display.flip()
            if help_screen.done:
                state       = "world_select"
                help_screen = None

        # ── Playing ───────────────────────────────────────────────────────
        elif state == "playing":
            for ev in pygame.event.get():
                result = session.handle_event(ev)
                if result == "fullscreen":
                    screen = _toggle_fullscreen(screen, sw, sh)
                elif result == "pause":
                    state = "paused"
                    pause = PauseMenu(sw, sh)
                    break
                elif result == "main_menu":
                    session.save()
                    session = None
                    state   = "world_select"
                    break
                elif result == "quit":
                    session.save()
                    pygame.quit(); sys.exit()
            if session is not None:
                session.update()
                session.draw(screen)
                pygame.display.flip()

        # ── Paused ────────────────────────────────────────────────────────
        elif state == "paused":
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    session.save()
                    pygame.quit(); sys.exit()
                # Skin overlay takes priority when open
                if session.skin_overlay.is_open:
                    chosen = session.skin_overlay.handle_event(ev)
                    if chosen is not None:
                        session.skin_name = chosen
                        session.skin = _load_skin(chosen)
                else:
                    pause.handle_event(ev)
            session.draw(screen)
            if session.skin_overlay.is_open:
                session.skin_overlay.draw(screen)
            else:
                pause.draw(screen)

            if not session.skin_overlay.is_open:
                if pause.action == "resume":
                    state = "playing"
                    pause = None
                elif pause.action == "fullscreen":
                    screen = _toggle_fullscreen(screen, sw, sh)
                    pause.action = None
                elif pause.action == "skin_select":
                    session.skin_overlay.open(session.skin_name)
                    pause.action = None
                elif pause.action == "main_menu":
                    session.save()
                    session  = None
                    state    = "world_select"
                    pause    = None
                elif pause.action == "quit":
                    session.save()
                    pygame.quit(); sys.exit()

            pygame.display.flip()


if __name__ == "__main__":
    main()
