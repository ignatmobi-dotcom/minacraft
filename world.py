"""
2D side-scrolling world: tile generation, player physics, mining/placing.

v0.9-alfa: world expanded ×10, sparse save (mods only), new blocks,
           water + lakes, structures (houses + ruins), containers.
"""
from __future__ import annotations
import pygame
import random
import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, List

from items import ItemStack

# ── Version ────────────────────────────────────────────────────────────────────

GAME_VERSION = "1.0-beta"

# ── Global constants ───────────────────────────────────────────────────────────

TILE_SIZE   = 32
WORLD_W     = 5000      # wide open world — saved sparsely (mods only)
WORLD_H     = 280       # 2× deeper — extra cavern + deep layers

GRAVITY     = 0.45
MAX_FALL    = 20.0
JUMP_VEL    = -10.0
MOVE_SPEED  = 3.5
MINE_REACH  = 5
EPS         = 0.05

PLAYER_W    = 26
PLAYER_H    = 52

SKY_TOP     = (100, 160, 240)
SKY_BOT     = ( 50,  90, 180)
CAVE_COLOR  = ( 15,   8,   4)

FPS         = 60

# ── Tile definitions ──────────────────────────────────────────────────────────
# key → (texture_key, drop_item_id | None, hardness, solid)

TILE_DATA: Dict[str, Tuple[str, Optional[str], float, bool]] = {
    # ── Original blocks ──────────────────────────────────────────────────────
    "grass":       ("block/grass_block_side", "dirt",        0.6,  True ),
    "dirt":        ("block/dirt",             "dirt",        0.5,  True ),
    "sand":        ("block/sand",             "sand",        0.5,  True ),
    "gravel":      ("block/gravel",           "gravel",      0.6,  True ),
    "stone":       ("block/stone",            "cobblestone", 1.5,  True ),
    "cobblestone": ("block/cobblestone",      "cobblestone", 2.0,  True ),
    "oak_log":     ("block/oak_log",          "oak_log",     2.0,  True ),
    "oak_leaves":  ("block/oak_leaves",       None,          0.2,  False),
    "oak_planks":  ("block/oak_planks",       "oak_planks",  2.0,  True ),
    "coal_ore":    ("block/coal_ore",         "coal",        3.0,  True ),
    "iron_ore":    ("block/iron_ore",         "raw_iron",    3.0,  True ),
    "copper_ore":  ("block/copper_ore",       "raw_copper",  3.0,  True ),
    "gold_ore":    ("block/gold_ore",         "raw_gold",    3.5,  True ),
    "diamond_ore": ("block/diamond_ore",      "diamond",     5.0,  True ),
    "bedrock":     ("block/bedrock",          None,         -1.0,  True ),
    "torch":       ("block/torch",            "torch",       0.0,  False),
    "workbench":   ("block/crafting_table_front", "workbench", 2.5, True ),
    # ── New stone variants ───────────────────────────────────────────────────
    "granite":         ("block/granite",           "granite",           1.5, True ),
    "andesite":        ("block/andesite",          "andesite",          1.5, True ),
    "diorite":         ("block/diorite",           "diorite",           1.5, True ),
    "mossy_cobblestone":("block/mossy_cobblestone","mossy_cobblestone", 2.0, True ),
    "stone_bricks":    ("block/stone_bricks",      "stone_bricks",      2.0, True ),
    "obsidian":        ("block/obsidian",          "obsidian",         50.0, True ),
    # ── Surface & sediment ───────────────────────────────────────────────────
    "clay":            ("block/clay",              "clay_ball",         0.6, True ),
    "sandstone":       ("block/sandstone",         "sandstone",         0.8, True ),
    "snow":            ("block/snow",              "snowball",          0.2, True ),
    "ice":             ("block/ice",               "ice",               0.5, True ),
    "cactus":          ("block/cactus_side",       "cactus",            0.0, True ),
    "glass":           ("block/glass",             None,                0.3, False),
    # ── Deep layer ──────────────────────────────────────────────────────────
    "deepstone":       ("block/deepslate",         "cobblestone",       2.0, True ),
    "glowstone":       ("block/glowstone",         "glowstone",         1.0, False),
    "crystal_ore":     ("block/amethyst_cluster",  "crystal",           4.0, True ),
    "magma_block":     ("block/magma",             "magma_block",       1.5, True ),
    "lava":            ("block/lava_flow",         None,                0.0, False),
    # ── Liquids ──────────────────────────────────────────────────────────────
    "water":           ("block/water_flow",        None,                0.0, False),
    # ── Functional blocks ────────────────────────────────────────────────────
    "anvil":           ("block/anvil",               "anvil",             5.0, True ),
    "gunsmith_table":  ("block/smithing_table_front","gunsmith_table",   3.0, True ),
    "tnt":             ("block/tnt_side",           "tnt",               0.5, True ),
    "sponge":          ("block/sponge",            "sponge",            0.6, True ),
    "furnace":         ("block/furnace_front",     "furnace",           3.5, True ),
    "chest":           ("block/chest",              "chest",             2.5, True ),
    "barrel":          ("block/barrel_side",       "barrel",            2.5, True ),
    "oak_door":          ("block/oak_door_bottom",   "oak_door",          3.0, True ),
    "oak_door_top":      ("block/oak_door_top",     None,                3.0, True ),
    "oak_door_open":     ("block/oak_door_bottom",  "oak_door",          3.0, False),
    "oak_door_top_open": ("block/oak_door_top",     None,                3.0, False),
    # ── Nether blocks ────────────────────────────────────────────────────
    "netherrack":        ("block/netherrack",         "netherrack",        0.4, True ),
    "nether_quartz_ore": ("block/nether_quartz_ore",  "nether_quartz",     3.0, True ),
    "nether_gold_ore":   ("block/nether_gold_ore",    "gold_nugget",       3.0, True ),
    "soul_sand":         ("block/soul_sand",           "soul_sand",         0.5, True ),
    "basalt":            ("block/basalt_side",         "basalt",            1.5, True ),
    "nether_brick":      ("block/nether_bricks",      "nether_brick",      2.0, True ),
    "nether_portal":     ("block/nether_portal",      None,               -1.0, False),
    "nether_wart_block": ("block/nether_wart_block",  "nether_wart_block", 0.3, True ),
    "ancient_debris":    ("block/ancient_debris_side","nether_scrap",      8.0, True ),
    # ── End blocks ───────────────────────────────────────────────────────────
    "end_stone":         ("block/end_stone",           "end_stone",          3.0, True ),
    "end_portal_frame":       ("block/end_portal_frame_eye", "None",         -1.0, True ),
    "end_portal_frame_empty": ("block/end_portal_frame_side","None",         -1.0, True ),
    "end_portal":        ("block/end_portal",           None,               -1.0, False),
    "purpur_block":      ("block/purpur_block",         "purpur_block",       1.5, True ),
    "chorus_plant":      ("block/chorus_plant",         None,                 0.0, False),
    "end_crystal":       ("block/beacon",               "end_stone",          0.0, False),
    # ── Biome-specific blocks ────────────────────────────────────────────────
    "jungle_log":     ("block/jungle_log",         "jungle_log",         2.0, True ),
    "jungle_leaves":  ("block/jungle_leaves",       None,                 0.2, False),
    "bamboo":         ("block/bamboo_stalk",        "bamboo",             0.0, True ),
    "podzol":         ("block/podzol_side",         "dirt",               0.5, True ),
    "mud":            ("block/mud",                 "mud",                0.7, True ),
    "mangrove_log":   ("block/mangrove_log",        "mangrove_log",       2.0, True ),
    "lily_pad":       ("block/lily_pad",            "lily_pad",           0.0, False),
    "acacia_log":     ("block/acacia_log",          "acacia_log",         2.0, True ),
    "acacia_leaves":  ("block/acacia_leaves",       None,                 0.2, False),
    "spruce_log":     ("block/spruce_log",          "spruce_log",         2.0, True ),
    "spruce_leaves":  ("block/spruce_leaves",       None,                 0.2, False),
    "mycelium":       ("block/mycelium_side",       "dirt",               0.6, True ),
    "red_mushroom_block":   ("block/red_mushroom_block",   "red_mushroom_block",   0.2, True ),
    "brown_mushroom_block": ("block/brown_mushroom_block", "brown_mushroom_block", 0.2, True ),
    # ── Enchanting / Brewing ─────────────────────────────────────────────────
    "enchanting_table": ("block/enchanting_table_top", "enchanting_table", 2.5, True ),
    "brewing_stand":    ("block/brewing_stand",         "brewing_stand",    3.0, True ),
    "lapis_ore":        ("block/lapis_ore",             "lapis_lazuli",     3.0, True ),
    # ── Redstone ─────────────────────────────────────────────────────────────
    "redstone_wire":        ("block/redstone_dust_dot",   "redstone",      0.0, False),
    "redstone_torch_on":    ("block/redstone_torch",      "redstone_torch",0.0, False),
    "redstone_torch_off":   ("block/redstone_torch",      "redstone_torch",0.0, False),
    "lever_off":            ("block/lever",               "lever",         0.5, False),
    "lever_on":             ("block/lever",               "lever",         0.5, False),
    "stone_button_off":     ("block/stone_button",        "stone_button",  0.5, False),
    "stone_button_on":      ("block/stone_button",        "stone_button",  0.5, False),
    "wooden_button_off":    ("block/oak_planks",          "wooden_button", 0.5, False),
    "wooden_button_on":     ("block/oak_planks",          "wooden_button", 0.5, False),
    "pressure_plate_off":   ("block/stone",               "pressure_plate",0.5, False),
    "pressure_plate_on":    ("block/stone",               "pressure_plate",0.5, False),
    "wooden_pressure_plate_off": ("block/oak_planks",     "wooden_pressure_plate", 0.5, False),
    "wooden_pressure_plate_on":  ("block/oak_planks",     "wooden_pressure_plate", 0.5, False),
}

# Minimum tool tier required to break the block (0 = bare hands ok)
TILE_MIN_TIER: Dict[str, int] = {
    "stone":       1, "cobblestone": 1,
    "coal_ore":    1, "iron_ore":    1, "copper_ore": 1,
    "gold_ore":    2, "diamond_ore": 2,
    "workbench":   1,
    "granite":     1, "andesite":   1, "diorite":    1,
    "mossy_cobblestone": 1, "stone_bricks": 1,
    "obsidian":    4,
    "sandstone":   1, "ice":        1,
    "anvil":       2, "gunsmith_table": 1,
    "furnace":     1, "chest":      0, "barrel":     0,
    "deepstone":   2, "crystal_ore": 3, "magma_block": 2, "glowstone": 1,
    "nether_quartz_ore": 2, "nether_gold_ore": 2, "ancient_debris": 4,
    "basalt": 1, "nether_brick": 1, "soul_sand": 0, "netherrack": 0,
    "lapis_ore": 1, "enchanting_table": 2, "brewing_stand": 1,
    "redstone_wire": 0, "redstone_torch_on": 0, "redstone_torch_off": 0,
    "lever_off": 0, "lever_on": 0,
    "stone_button_off": 0, "stone_button_on": 0,
    "wooden_button_off": 0, "wooden_button_on": 0,
    "pressure_plate_off": 0, "pressure_plate_on": 0,
    "wooden_pressure_plate_off": 0, "wooden_pressure_plate_on": 0,
}

TILE_SOUND: Dict[str, str] = {
    "grass":       "dig_grass", "dirt":        "dig_grass",
    "oak_leaves":  "dig_grass", "torch":       "dig_grass",
    "snow":        "dig_snow",  "clay":        "dig_grass",
    "sand":        "dig_sand",  "gravel":      "dig_gravel",
    "stone":       "dig_stone", "cobblestone": "dig_stone",
    "coal_ore":    "dig_stone", "iron_ore":    "dig_stone",
    "copper_ore":  "dig_stone", "gold_ore":    "dig_stone",
    "diamond_ore": "dig_stone", "bedrock":     "dig_stone",
    "granite":     "dig_stone", "andesite":    "dig_stone",
    "diorite":     "dig_stone", "mossy_cobblestone": "dig_stone",
    "obsidian":    "dig_stone", "sandstone":   "dig_stone",
    "ice":         "dig_stone",
    "oak_log":     "dig_wood",  "oak_planks":  "dig_wood",
    "workbench":   "dig_wood",  "chest":       "dig_wood",
    "barrel":          "dig_wood",  "oak_door":         "dig_wood",
    "oak_door_open":   "dig_wood",  "oak_door_top":     "dig_wood",
    "oak_door_top_open":"dig_wood", "sponge":           "dig_grass",
    "anvil":       "dig_stone", "gunsmith_table": "dig_wood", "tnt": "dig_grass",
    "furnace":     "dig_stone", "cactus":      "dig_grass",
    "glass":       "dig_stone",
    "deepstone":   "dig_stone", "crystal_ore": "dig_stone",
    "magma_block": "dig_stone", "glowstone":   "dig_stone",
    "netherrack":  "dig_stone", "nether_quartz_ore": "dig_stone",
    "nether_gold_ore": "dig_stone", "basalt": "dig_stone",
    "nether_brick": "dig_stone", "ancient_debris": "dig_stone",
    "soul_sand":   "dig_sand",  "nether_wart_block": "dig_grass",
    "lapis_ore": "dig_stone", "enchanting_table": "dig_wood", "brewing_stand": "dig_stone",
    "jungle_log": "dig_wood",  "jungle_leaves": "dig_grass",
    "bamboo":     "dig_wood",  "podzol":        "dig_grass",
    "mud":        "dig_grass", "mangrove_log":  "dig_wood",
    "lily_pad":   "dig_grass", "acacia_log":    "dig_wood",
    "acacia_leaves": "dig_grass", "spruce_log": "dig_wood",
    "spruce_leaves": "dig_grass", "mycelium":   "dig_grass",
    "red_mushroom_block": "dig_grass", "brown_mushroom_block": "dig_grass",
    "redstone_wire": "dig_stone", "redstone_torch_on": "dig_grass",
    "redstone_torch_off": "dig_grass",
    "lever_off": "dig_stone", "lever_on": "dig_stone",
    "stone_button_off": "dig_stone", "stone_button_on": "dig_stone",
    "wooden_button_off": "dig_wood",  "wooden_button_on": "dig_wood",
    "pressure_plate_off": "dig_stone", "pressure_plate_on": "dig_stone",
    "wooden_pressure_plate_off": "dig_wood", "wooden_pressure_plate_on": "dig_wood",
}

TILE_COLOR: Dict[str, Tuple[int, int, int]] = {
    "grass":       (80,  145,  55), "dirt":        (130,  90,  55),
    "sand":        (220, 200, 120), "gravel":      (145, 135, 125),
    "stone":       (155, 150, 145), "cobblestone": (130, 125, 118),
    "coal_ore":    ( 55,  55,  60), "iron_ore":    (200, 155, 120),
    "copper_ore":  (195, 120,  75), "gold_ore":    (255, 210,  45),
    "diamond_ore": ( 70, 225, 225), "bedrock":     ( 60,  58,  58),
    "oak_log":     (145, 105,  60), "oak_leaves":  ( 50, 145,  50),
    "oak_planks":  (195, 155,  80), "workbench":   (140, 100,  60),
    "torch":       (255, 185,  50),
    "granite":     (175, 135, 120), "andesite":    (110, 110, 110),
    "diorite":     (220, 218, 215), "mossy_cobblestone": (100, 120,  80),
    "obsidian":    ( 25,  15,  35), "clay":        (155, 155, 170),
    "sandstone":   (220, 205, 150), "snow":        (230, 240, 255),
    "ice":         (150, 200, 235), "cactus":      ( 70, 150,  50),
    "glass":       (200, 230, 255), "water":       ( 40, 100, 200),
    "deepstone":   ( 45,  42,  55), "crystal_ore": (155,  80, 220),
    "magma_block": (200,  65,  20), "glowstone":   (255, 220,  70),
    "lava":        (230,  80,  20),
    "anvil":       ( 65,  65,  75), "gunsmith_table": (105,  80,  60),
    "tnt":         (185,  45,  35),
    "sponge":      (220, 210,  80), "furnace":     (130, 120, 115),
    "netherrack":  (140,  45,  35), "nether_quartz_ore": (200, 185, 175),
    "nether_gold_ore": (220, 165,  35), "soul_sand": (100,  80,  60),
    "basalt":      ( 60,  58,  70), "nether_brick": (110,  40,  30),
    "nether_portal":(100,  30, 200), "nether_wart_block": (150,  30,  30),
    "ancient_debris":( 80,  55,  50),
    "end_stone":     (220, 220, 175), "end_portal_frame": ( 80, 140,  90),
    "end_portal_frame_empty": (60, 110, 70),
    "end_portal":    ( 10,   5,  35), "purpur_block":  (160,  90, 160),
    "chorus_plant":  (110,  60, 120), "end_crystal":   (  0, 230, 230),
    "chest":            (175, 130,  70), "barrel":           (150, 110,  60),
    "oak_door":         (160, 115,  55), "oak_door_open":     (160, 115,  55),
    "oak_door_top":     (160, 115,  55), "oak_door_top_open": (160, 115,  55),
    "jungle_log":    ( 90,  65,  40), "jungle_leaves":  ( 35, 110,  25),
    "bamboo":        (110, 140,  55), "podzol":         (105,  72,  50),
    "mud":           ( 82,  60,  50), "mangrove_log":   ( 85,  60,  40),
    "lily_pad":      ( 45, 125,  45), "acacia_log":     (155, 105,  50),
    "acacia_leaves": ( 95, 135,  50), "spruce_log":     ( 80,  60,  45),
    "spruce_leaves": ( 45, 105,  55), "mycelium":       (120,  85, 110),
    "red_mushroom_block":   (210,  50,  50),
    "brown_mushroom_block": (155, 100,  55),
    "enchanting_table": ( 55,  28,  75), "brewing_stand": ( 68,  62,  72),
    "lapis_ore":        ( 28,  68, 185),
    "redstone_wire":     (200,  40,  40), "redstone_torch_on":  (220,  60,  40),
    "redstone_torch_off":(100,  30,  20),
    "lever_off":         (140, 110,  70), "lever_on":           (200, 160,  60),
    "stone_button_off":  (155, 150, 145), "stone_button_on":    (210, 180, 100),
    "wooden_button_off": (195, 155,  80), "wooden_button_on":   (235, 195, 100),
    "pressure_plate_off":(155, 150, 145), "pressure_plate_on":  (210, 180, 100),
    "wooden_pressure_plate_off": (195, 155, 80),
    "wooden_pressure_plate_on":  (235, 195, 100),
}


# ── Camera ────────────────────────────────────────────────────────────────────

class Camera:
    def __init__(self, sw: int, sh: int):
        self.x = 0.0
        self.y = 0.0
        self.sw = sw
        self.sh = sh

    def follow(self, player: "Player", world: "World", smooth: float = 0.12):
        tx = player.x + PLAYER_W / 2 - self.sw / 2
        ty = player.y + PLAYER_H / 2 - self.sh / 2
        self.x += (tx - self.x) * smooth
        self.y += (ty - self.y) * smooth
        self.x = max(0.0, min(self.x, world.width  * TILE_SIZE - self.sw))
        self.y = max(0.0, min(self.y, world.height * TILE_SIZE - self.sh))

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        return int(wx - self.x), int(wy - self.y)

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        return sx + self.x, sy + self.y

    def snap(self, player: "Player", world: "World"):
        self.x = player.x + PLAYER_W / 2 - self.sw / 2
        self.y = player.y + PLAYER_H / 2 - self.sh / 2
        self.x = max(0.0, min(self.x, world.width  * TILE_SIZE - self.sw))
        self.y = max(0.0, min(self.y, world.height * TILE_SIZE - self.sh))


# ── Player ────────────────────────────────────────────────────────────────────

MAX_OXYGEN   = 15.0   # seconds of air supply
SWIM_SPEED   = 2.5    # horizontal speed in water
WATER_GRAV   = 0.08   # gravity while swimming
SWIM_UP_VEL  = -4.5   # upward push when pressing jump in water
DROWN_DAMAGE_INTERVAL = 1.0  # seconds between drowning damage ticks

LAVA_SPEED   = 1.2    # horizontal speed in lava (very viscous)
LAVA_GRAV    = 0.04   # gravity in lava (very slow sink)
LAVA_UP_VEL  = -2.5   # upward push when pressing jump in lava

SPRINT_SPEED        = 5.5    # horizontal speed while sprinting
MAX_HUNGER          = 20.0
HUNGER_DRAIN_RATE   = 0.025  # food units per second (full bar ~13 min)
SPRINT_HUNGER_MULT  = 3.0    # sprint drains this many times faster
HUNGER_DMG_INTERVAL = 2.0    # seconds between HP loss when starving
HUNGER_REGEN_INTERVAL = 4.0  # seconds between HP regen when well-fed (≥18)

DAY_CYCLE_LEN = 600.0   # seconds per full day (10 real minutes)

# ── XP / Level ────────────────────────────────────────────────────────────────

MAX_LEVEL = 20
# XP required to reach each level (index = level - 1)
XP_THRESHOLDS = [0, 50, 150, 300, 500, 750, 1050, 1400, 1800, 2250,
                 2750, 3300, 3900, 4550, 5250, 6000, 6800, 7650, 8550, 9500]

# XP gained when fully mining these tiles
_ORE_XP: Dict[str, int] = {
    "coal_ore":    5,
    "copper_ore":  8,
    "iron_ore":    10,
    "gold_ore":    20,
    "diamond_ore": 35,
    "crystal_ore": 50,
    "lapis_ore":          15,
    "nether_quartz_ore":  12,
    "nether_gold_ore":    18,
    "ancient_debris":     60,
}

@dataclass
class Player:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    on_ground: bool = False
    facing: int = 1

    hp: int = 20
    max_hp: int = 20

    mining_target: Optional[Tuple[int, int]] = None
    mining_progress: float = 0.0

    walk_frame:  float = 0.0
    just_jumped: bool  = False

    in_water:     bool  = False
    in_lava:      bool  = False
    oxygen:       float = MAX_OXYGEN
    _drown_t:     float = field(default=0.0, repr=False)

    hunger:       float = 20.0   # MAX_HUNGER
    is_sprinting: bool  = False
    _hunger_t:    float = field(default=0.0, repr=False)

    xp:    int = 0
    level: int = 1

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), PLAYER_W, PLAYER_H)

    @property
    def center(self) -> Tuple[float, float]:
        return self.x + PLAYER_W / 2, self.y + PLAYER_H / 2

    def add_xp(self, amount: int) -> bool:
        """Add XP and level up if threshold crossed. Returns True if leveled up."""
        if self.level >= MAX_LEVEL or amount <= 0:
            return False
        self.xp += amount
        leveled = False
        while self.level < MAX_LEVEL and self.xp >= XP_THRESHOLDS[self.level]:
            self.level += 1
            leveled = True
        return leveled

    def xp_to_next(self) -> int:
        """XP needed to reach next level (0 if at max)."""
        if self.level >= MAX_LEVEL:
            return 0
        return XP_THRESHOLDS[self.level] - self.xp

    def xp_progress(self) -> float:
        """0.0-1.0 progress within current level."""
        if self.level >= MAX_LEVEL:
            return 1.0
        prev = XP_THRESHOLDS[self.level - 1]
        nxt  = XP_THRESHOLDS[self.level]
        return max(0.0, min(1.0, (self.xp - prev) / (nxt - prev)))

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "hp": self.hp, "max_hp": self.max_hp,
                "oxygen": self.oxygen, "hunger": self.hunger,
                "xp": self.xp, "level": self.level}

    @staticmethod
    def from_dict(d: dict) -> "Player":
        p = Player(d["x"], d["y"], hp=d["hp"], max_hp=d["max_hp"])
        p.oxygen = float(d.get("oxygen", MAX_OXYGEN))
        p.hunger = float(d.get("hunger", MAX_HUNGER))
        p.xp    = int(d.get("xp", 0))
        p.level = int(d.get("level", 1))
        return p


# ── World ─────────────────────────────────────────────────────────────────────

class World:
    """
    Tile world with sparse save: _base holds generated terrain (never saved),
    _mods holds player changes.  get() checks _mods first, then _base.
    """

    def __init__(self, seed: int, width: int = WORLD_W, height: int = WORLD_H,
                 dimension: str = "overworld"):
        self.seed      = seed
        self.width     = width
        self.height    = height
        self.dimension = dimension

        # Foreground layer — generated terrain (never saved)
        self._base: List[List[Optional[str]]] = [
            [None] * width for _ in range(height)
        ]
        # Foreground player modifications
        self._mods: Dict[str, Optional[str]] = {}
        # Background layer — stone/dirt fill (never saved, separate from fg)
        self._bg_base: List[List[Optional[str]]] = [
            [None] * width for _ in range(height)
        ]
        # Background player modifications
        self._bg_mods: Dict[str, Optional[str]] = {}
        # Container inventories
        self._containers: Dict[str, List] = {}
        # TNT timers: key="x,y", value=ticks remaining until explosion
        self._tnt_timers: Dict[str, int] = {}
        # Achievements unlocked
        self._achievements: set = set()
        # Redstone button/plate auto-off timers: key="x,y", value=ticks
        self._button_timers: Dict[str, int] = {}

        self._tex: Dict[str, pygame.Surface] = {}
        self._dim_tex: Dict[str, pygame.Surface] = {}   # dimmed bg versions
        self._surface_heights: Optional[List[int]] = None
        self._generate(seed)

    # ── Tile access ──────────────────────────────────────────────────────────

    def get(self, x: int, y: int) -> Optional[str]:
        key = f"{x},{y}"
        if key in self._mods:
            return self._mods[key]
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._base[y][x]
        return None

    # ── Background layer ─────────────────────────────────────────────────────────

    def get_bg(self, x: int, y: int) -> Optional[str]:
        key = f"{x},{y}"
        if key in self._bg_mods:
            return self._bg_mods[key]
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._bg_base[y][x]
        return None

    def set_bg(self, x: int, y: int, tile: Optional[str]):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        key = f"{x},{y}"
        if tile == self._bg_base[y][x]:
            self._bg_mods.pop(key, None)
        else:
            self._bg_mods[key] = tile

    def surface_height_at(self, x: int) -> int:
        """Return the y-tile of the surface at column x."""
        if self._surface_heights is None:
            return self.height // 3
        x = max(0, min(self.width - 1, x))
        return self._surface_heights[x]

    def _set_raw(self, x: int, y: int, tile: Optional[str]):
        """Set a tile without triggering cascade effects."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        key = f"{x},{y}"
        if tile == self._base[y][x]:
            self._mods.pop(key, None)
        else:
            self._mods[key] = tile

    def set(self, x: int, y: int, tile: Optional[str]):
        current = self.get(x, y)
        self._set_raw(x, y, tile)
        # Sponge absorbs water when placed
        if tile == "sponge":
            self._absorb_water(x, y, radius=4)
        # Door: auto-sync the other half
        if tile in ("oak_door", "oak_door_open"):
            top = "oak_door_top" if tile == "oak_door" else "oak_door_top_open"
            self._set_raw(x, y - 1, top)
        elif tile is None:
            if current in ("oak_door", "oak_door_open"):
                above = self.get(x, y - 1)
                if above in ("oak_door_top", "oak_door_top_open"):
                    self._set_raw(x, y - 1, None)
            elif current in ("oak_door_top", "oak_door_top_open"):
                below = self.get(x, y + 1)
                if below in ("oak_door", "oak_door_open"):
                    self._set_raw(x, y + 1, None)

    def is_solid(self, x: int, y: int) -> bool:
        t = self.get(x, y)
        if t is None:
            return False
        # Active portal: side obsidian columns become passable so player can walk out
        if t == "obsidian" and (
                self.get(x - 1, y) == "nether_portal" or
                self.get(x + 1, y) == "nether_portal"):
            return False
        # End portal: side frame blocks become passable once portal is active
        if t in ("end_portal_frame", "end_portal_frame_empty") and (
                self.get(x - 1, y) == "end_portal" or
                self.get(x + 1, y) == "end_portal"):
            return False
        data = TILE_DATA.get(t)
        return data[3] if data else False

    # ── Container helpers ────────────────────────────────────────────────────

    def get_container(self, x: int, y: int) -> List:
        key = f"{x},{y}"
        if key not in self._containers:
            self._containers[key] = [None] * 27
        return self._containers[key]

    def save_container(self, x: int, y: int, slots: List):
        self._containers[f"{x},{y}"] = slots

    def pop_container(self, x: int, y: int) -> List[ItemStack]:
        key = f"{x},{y}"
        raw = self._containers.pop(key, [])
        result = []
        for s in raw:
            if s:
                try:
                    result.append(ItemStack.from_dict(s))
                except Exception:
                    pass
        return result

    # ── Water helpers ────────────────────────────────────────────────────────

    def tick_water(self, px: int, py: int, radius: int = 24):
        """Flow water downward in an area around the player tile (px, py)."""
        x0 = max(0, px - radius)
        x1 = min(self.width, px + radius)
        y0 = max(0, py - radius)
        y1 = min(self.height, py + radius)

        to_add: List[Tuple[int, int]] = []
        for ty in range(y1 - 1, y0 - 1, -1):
            for tx in range(x0, x1):
                if self.get(tx, ty) != "water":
                    continue
                below = self.get(tx, ty + 1) if ty + 1 < self.height else "bedrock"
                if below is None:
                    to_add.append((tx, ty + 1))

        for tx, ty in to_add:
            self.set(tx, ty, "water")

    def _absorb_water(self, x: int, y: int, radius: int = 4):
        for tx in range(max(0, x - radius), min(self.width, x + radius + 1)):
            for ty in range(max(0, y - radius), min(self.height, y + radius + 1)):
                if math.hypot(tx - x, ty - y) <= radius:
                    if self.get(tx, ty) == "water":
                        self.set(tx, ty, None)

    # ── TNT helpers ──────────────────────────────────────────────────────────

    def light_tnt(self, x: int, y: int, ticks: int = 300):
        """Start 5-second TNT timer (300 ticks at 60 fps)."""
        if self.get(x, y) == "tnt":
            self._tnt_timers[f"{x},{y}"] = ticks

    def tick_tnt(self) -> List[Tuple[int, int]]:
        """Decrement timers, explode ready TNT.
        Returns list of (x, y) explosion centres for particle effects.
        """
        events: List[Tuple[int, int]] = []
        expired = [k for k, t in self._tnt_timers.items() if t <= 0]
        for key in expired:
            self._tnt_timers.pop(key, None)
            x, y = map(int, key.split(","))
            if self.get(x, y) == "tnt":
                self.set(x, y, None)
            self._explode(x, y, power=5)
            events.append((x, y))
        for key in list(self._tnt_timers):
            self._tnt_timers[key] -= 1
        return events

    def _explode(self, x: int, y: int, power: int = 5):
        """Break tiles in circle, chain-react adjacent TNT."""
        for dy in range(-power, power + 1):
            for dx in range(-power, power + 1):
                if dx * dx + dy * dy > power * power:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                t = self.get(nx, ny)
                if t is None or t in ("water", "bedrock", "lava", "nether_portal"):
                    continue
                if t == "tnt":
                    # Chain reaction with shorter fuse (40 ticks ≈ 0.67 s)
                    self.light_tnt(nx, ny, ticks=40)
                else:
                    self.set(nx, ny, None)

    # ── Portal helpers ───────────────────────────────────────────────────────

    def check_portal_frame(self, tx: int, ty: int) -> Optional[Tuple[int,int,int,int]]:
        """Scan 5-tile radius for a 4-wide×5-tall obsidian frame.
        Returns (ix0, iy0, ix1, iy1) interior corners, or None."""
        for fx in range(tx - 5, tx + 5):
            for fy in range(ty - 6, ty + 5):
                if self._is_portal_frame(fx, fy):
                    return (fx + 1, fy + 1, fx + 2, fy + 3)
        return None

    def _is_portal_frame(self, fx: int, fy: int) -> bool:
        """Check 4×5 obsidian frame with bottom-left at (fx, fy+4)."""
        # Frame corners: 4 wide × 5 tall (fy = top, fy+4 = bottom)
        for x in range(fx, fx + 4):
            if self.get(x, fy) != "obsidian":      return False
            if self.get(x, fy + 4) != "obsidian":  return False
        for y in range(fy, fy + 5):
            if self.get(fx, y) != "obsidian":       return False
            if self.get(fx + 3, y) != "obsidian":   return False
        # Interior must be empty (or already nether_portal)
        for y in range(fy + 1, fy + 4):
            for x in range(fx + 1, fx + 3):
                t = self.get(x, y)
                if t is not None and t != "nether_portal":
                    return False
        return True

    def activate_portal(self, tx: int, ty: int) -> Optional[Tuple[int,int]]:
        """Activate a portal frame containing (tx, ty). Returns interior top-left."""
        result = self.check_portal_frame(tx, ty)
        if result is None:
            return None
        ix0, iy0, ix1, iy1 = result
        for y in range(iy0, iy1 + 1):
            for x in range(ix0, ix1 + 1):
                self._set_raw(x, y, "nether_portal")
        return (ix0, iy0)

    def place_portal_frame(self, cx: int, y_surface: int):
        """Place a 4×5 obsidian portal frame + lit interior at column cx.
        y_surface must be the solid floor tile (player stands on top of it)."""
        fx = cx - 2
        fy = y_surface - 4  # bottom obsidian at floor level, interior at floor-1..floor-3
        for x in range(fx, fx + 4):
            self.set(x, fy, "obsidian")
            self.set(x, fy + 4, "obsidian")
        for y in range(fy, fy + 5):
            self.set(fx, y, "obsidian")
            self.set(fx + 3, y, "obsidian")
        for y in range(fy + 1, fy + 4):
            for x in range(fx + 1, fx + 3):
                self._set_raw(x, y, "nether_portal")

    # ── Generation ───────────────────────────────────────────────────────────

    def _generate(self, seed: int):
        if self.dimension == "nether":
            self._generate_nether(seed)
            return
        if self.dimension == "end":
            self._generate_end(seed)
            return
        rng = random.Random(seed)
        heights, biome_tbl = self._heightmap(rng)
        self._surface_heights = heights

        scale = self.width / 280  # scaling factor vs original 280-wide world

        # Re-compute biome vals from the same noise table + assign with percentile method
        TABLE_SIZE = max(512, self.width)
        biome_vals = [
            self._value_noise1d(biome_tbl, x / self.width * 5.0, TABLE_SIZE)
            for x in range(self.width)
        ]
        biomes = self._assign_biomes(biome_vals)  # List[str], one per column
        base_y = int(self.height * 0.37)

        for x in range(self.width):
            h     = heights[x]
            biome = biomes[x]
            for y in range(self.height - 4, self.height):
                self._base[y][x] = "bedrock"
            for y in range(h + 4, self.height - 4):
                self._base[y][x] = "stone"
            for y in range(h + 1, h + 4):
                self._base[y][x] = "dirt"

            # Biome-driven surface tile
            if biome == "desert":
                self._base[h][x] = "sand"
                for dy in range(1, 4):
                    if 0 <= h + dy < self.height:
                        self._base[h + dy][x] = "sandstone"
            elif biome in ("tundra", "taiga"):
                self._base[h][x] = "snow"
            elif biome == "swamp":
                self._base[h][x] = "mud"
                for dy in range(1, 4):
                    if 0 <= h + dy < self.height:
                        self._base[h + dy][x] = "mud"
            elif biome == "jungle":
                self._base[h][x] = "podzol"
            elif biome == "mushroom_fields":
                self._base[h][x] = "mycelium"
            elif biome == "mountains" and h < base_y - 12:
                self._base[h][x] = "stone"   # bare rock on peaks
            else:
                self._base[h][x] = "grass"

        self._make_caves(rng, heights, scale)
        self._place_ores(rng, heights, scale)
        self._place_stone_variants(rng, heights, scale)
        self._place_clay_patches(rng, heights)
        self._place_trees(rng, heights, biomes)
        self._place_cactus(rng, heights, biomes)
        self._place_jungle_features(rng, heights, biomes)
        self._place_swamp_features(rng, heights, biomes)
        self._place_savanna_trees(rng, heights, biomes)
        self._place_taiga_trees(rng, heights, biomes)
        self._place_mushroom_features(rng, heights, biomes)
        self._place_lakes(rng, heights, biomes)
        self._place_obsidian(rng)
        self._place_snow_ice(rng, heights, biomes)
        self._place_structures(rng, heights, scale)
        # Deep layer generation (below ~70% depth)
        self._fill_deep_stone(heights)
        self._make_deep_caverns(rng, heights, scale)
        self._place_deep_ores(rng, heights, scale)
        self._place_crystal_clusters(rng, heights, scale)
        self._place_lava_pools(rng, heights, scale)
        self._generate_background(heights)

    # ── Noise helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _smoothstep(t: float) -> float:
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    def _value_noise1d(self, rng_table: List[float], x: float, period: int) -> float:
        """1D value noise: smooth interpolation between random values at integers."""
        xi  = int(x) % period
        xi1 = (xi + 1) % period
        frac = x - math.floor(x)
        t = self._smoothstep(frac)
        return self._lerp(rng_table[xi], rng_table[xi1], t)

    def _fbm1d(self, rng_table: List[float], x: float, period: int,
               octaves: int = 5, lacunarity: float = 2.0, gain: float = 0.5) -> float:
        """Fractional Brownian motion (multi-octave value noise)."""
        v, amp, freq = 0.0, 0.5, 1.0
        for _ in range(octaves):
            p = max(1, int(period / freq))
            tbl = rng_table  # period adjusts automatically via modulo
            v    += amp * self._value_noise1d(tbl, x * freq, p)
            amp  *= gain
            freq *= lacunarity
        return v

    def _value_noise2d(self, tbl_x: List[float], tbl_y: List[float],
                       x: float, y: float, period_x: int, period_y: int) -> float:
        """2D value noise via bilinear interpolation of random grid."""
        xi  = int(x) % period_x; xi1 = (xi + 1) % period_x
        yi  = int(y) % period_y; yi1 = (yi + 1) % period_y
        fx = x - math.floor(x);  fy = y - math.floor(y)
        tx = self._smoothstep(fx); ty = self._smoothstep(fy)
        # 4-corner hash
        h00 = (tbl_x[xi]  * 0.5 + tbl_y[yi])  % 1.0
        h10 = (tbl_x[xi1] * 0.5 + tbl_y[yi])  % 1.0
        h01 = (tbl_x[xi]  * 0.5 + tbl_y[yi1]) % 1.0
        h11 = (tbl_x[xi1] * 0.5 + tbl_y[yi1]) % 1.0
        return self._lerp(self._lerp(h00, h10, tx), self._lerp(h01, h11, tx), ty)

    def _make_noise_table(self, rng: random.Random, size: int) -> List[float]:
        return [rng.random() for _ in range(size)]

    def _heightmap(self, rng: random.Random) -> Tuple[List[int], List[float]]:
        """Returns (heights, biome_tbl) so _generate can reuse the noise table."""
        W = self.width
        TABLE_SIZE = max(512, W)

        tbl_biome  = self._make_noise_table(rng, TABLE_SIZE)
        tbl_height = self._make_noise_table(rng, TABLE_SIZE)

        biome_vals = [self._value_noise1d(tbl_biome, x / W * 5.0, TABLE_SIZE)
                      for x in range(W)]
        biomes = self._assign_biomes(biome_vals)

        base_y = int(self.height * 0.37)

        # Per-column biome parameters (before smoothing)
        _BIOME_PARAMS = {
            "tundra":          (base_y + 3,   4),
            "taiga":           (base_y + 1,   8),
            "mountains":       (base_y - 18, 32),
            "forest":          (base_y,      10),
            "swamp":           (base_y + 5,   3),
            "plains":          (base_y + 4,   7),
            "savanna":         (base_y + 2,   6),
            "jungle":          (base_y - 2,  12),
            "mushroom_fields": (base_y + 3,   5),
            "desert":          (base_y + 6,   5),
        }
        raw_base = [float(_BIOME_PARAMS[b][0]) for b in biomes]
        raw_amp  = [float(_BIOME_PARAMS[b][1]) for b in biomes]

        # Gaussian smooth the base array to eliminate sharp biome-border cliffs
        sigma = 22
        half_k = sigma * 3
        smooth_base = []
        smooth_amp  = []
        for x in range(W):
            tb = ta = tw = 0.0
            for dx in range(-half_k, half_k + 1):
                xi = max(0, min(W - 1, x + dx))
                w = math.exp(-0.5 * (dx / sigma) ** 2)
                tb += raw_base[xi] * w
                ta += raw_amp[xi]  * w
                tw += w
            smooth_base.append(tb / tw)
            smooth_amp.append(ta / tw)

        result = []
        for x in range(W):
            hv = self._fbm1d(tbl_height, x / W * 8.0, TABLE_SIZE,
                             octaves=6, gain=0.45)
            height = int(smooth_base[x] + (hv - 0.5) * smooth_amp[x] * 2)
            result.append(max(8, min(self.height - 25, height)))

        return result, tbl_biome

    @staticmethod
    def _classify_biome(bv: float) -> str:
        """Map a noise value [0,1] to a biome name (fixed thresholds, for rough lookups)."""
        if bv < 0.10: return "tundra"
        if bv < 0.20: return "taiga"
        if bv < 0.32: return "mountains"
        if bv < 0.44: return "forest"
        if bv < 0.54: return "swamp"
        if bv < 0.64: return "plains"
        if bv < 0.74: return "savanna"
        if bv < 0.84: return "jungle"
        if bv < 0.92: return "mushroom_fields"
        return "desert"

    @staticmethod
    def _assign_biomes(biome_vals: List[float]) -> List[str]:
        """Assign biomes using percentile thresholds for controlled world distribution.

        Each biome gets exactly its target fraction of the world columns, regardless
        of how the underlying noise distributes.
        """
        _NAMES  = ["tundra","taiga","mountains","forest","swamp",
                   "plains","savanna","jungle","mushroom_fields","desert"]
        _FRACS  = [0.08,   0.10,    0.12,       0.15,   0.08,
                   0.12,   0.10,    0.10,        0.07,   0.08]

        W = len(biome_vals)
        sorted_idxs = sorted(range(W), key=lambda i: biome_vals[i])
        result = ["plains"] * W
        start = 0
        for name, frac in zip(_NAMES, _FRACS):
            end = min(W, start + max(1, round(frac * W)))
            for i in range(start, end):
                result[sorted_idxs[i]] = name
            start = end
        for i in range(start, W):
            result[sorted_idxs[i]] = _NAMES[-1]
        return result

    def _biome_at(self, tbl_biome: List[float], x: int) -> str:
        """Return approximate biome at x (fixed thresholds, used for structure checks)."""
        TABLE_SIZE = len(tbl_biome)
        bv = self._value_noise1d(tbl_biome, x / self.width * 5.0, TABLE_SIZE)
        return self._classify_biome(bv)

    def _make_caves(self, rng: random.Random, heights: List[int], scale: float):
        """Perlin-style 2D cave network using noise threshold + worm tunnels."""
        TABLE_SIZE = max(256, self.width)
        tbl_x = self._make_noise_table(rng, TABLE_SIZE)
        tbl_y = self._make_noise_table(rng, TABLE_SIZE)

        # Pass 1: 2D noise threshold caves (natural cave shapes)
        cave_period_x = max(32, self.width // 20)
        cave_period_y = max(16, self.height // 8)
        for ty in range(self.height - 5):
            for tx in range(self.width):
                if ty <= heights[tx] + 3:
                    continue  # Don't carve near surface
                nv = self._value_noise2d(
                    tbl_x, tbl_y,
                    tx / cave_period_x, ty / cave_period_y,
                    TABLE_SIZE, TABLE_SIZE
                )
                if abs(nv - 0.5) < 0.12:  # threshold for tunnel shape
                    if self._base[ty][tx] not in (None, "bedrock"):
                        self._base[ty][tx] = None

        # Pass 2: worm tunnels for connectivity
        count = int(40 * scale)
        for _ in range(count):
            cx = rng.randint(10, self.width - 10)
            depth = rng.randint(10, self.height - heights[cx] - 15)
            cy = heights[cx] + depth
            if cy >= self.height - 5:
                continue
            dx = rng.choice([-1, -1, 0, 1, 1])
            dy = rng.choice([-1, 0, 0, 0, 1])
            steps = rng.randint(20, 60)
            for _ in range(steps):
                if rng.random() < 0.22:
                    dx = rng.choice([-1, 0, 0, 1])
                if rng.random() < 0.18:
                    dy = rng.choice([-1, 0, 0, 1])
                cx = max(2, min(self.width - 3, cx + dx))
                cy = max(heights[cx] + 4, min(self.height - 6, cy + dy))
                r = rng.randint(1, 2)
                for oy in range(-r, r + 1):
                    for ox in range(-r, r + 1):
                        nx, ny = cx + ox, cy + oy
                        if (0 <= nx < self.width and 0 <= ny < self.height
                                and self._base[ny][nx] not in (None, "bedrock")):
                            self._base[ny][nx] = None

    def _place_ores(self, rng: random.Random, heights: List[int], scale: float):
        specs = [
            ("coal_ore",    4,   70,  int(90*scale),  5),
            ("iron_ore",    8,  100,  int(60*scale),  4),
            ("copper_ore",  6,   85,  int(70*scale),  4),
            ("lapis_ore",  12,  110,  int(22*scale),  3),
            ("gold_ore",   28,  140,  int(35*scale),  3),
            ("diamond_ore",38,  170,  int(20*scale),  2),
        ]
        for tile_id, dmin, dmax, veins, vsize in specs:
            placed = 0
            attempts = 0
            while placed < veins and attempts < veins * 60:
                attempts += 1
                x  = rng.randint(5, self.width - 6)
                d  = rng.randint(dmin, min(dmax, self.height - heights[x] - 6))
                y  = heights[x] + d
                if y >= self.height - 5 or self._base[y][x] != "stone":
                    continue
                for _ in range(vsize):
                    nx = x + rng.randint(-2, 2)
                    ny = y + rng.randint(-1, 1)
                    if (0 <= nx < self.width and 0 <= ny < self.height
                            and self._base[ny][nx] == "stone"):
                        self._base[ny][nx] = tile_id
                placed += 1

    def _place_stone_variants(self, rng: random.Random, heights: List[int], scale: float):
        variants = [
            ("granite",    10, 100, int(80*scale), 4),
            ("andesite",   10, 100, int(80*scale), 4),
            ("diorite",    10, 100, int(60*scale), 3),
        ]
        for tile_id, dmin, dmax, veins, vsize in variants:
            placed = 0
            attempts = 0
            while placed < veins and attempts < veins * 40:
                attempts += 1
                x = rng.randint(5, self.width - 6)
                d = rng.randint(dmin, min(dmax, self.height - heights[x] - 6))
                y = heights[x] + d
                if y >= self.height - 5 or self._base[y][x] != "stone":
                    continue
                for _ in range(vsize + rng.randint(0, 4)):
                    nx = x + rng.randint(-2, 2)
                    ny = y + rng.randint(-2, 2)
                    if (0 <= nx < self.width and 0 <= ny < self.height
                            and self._base[ny][nx] == "stone"):
                        self._base[ny][nx] = tile_id
                placed += 1

    def _place_clay_patches(self, rng: random.Random, heights: List[int]):
        count = self.width // 60
        for _ in range(count):
            cx = rng.randint(10, self.width - 10)
            for dx in range(rng.randint(3, 6)):
                x = cx + dx - 3
                if not (0 <= x < self.width):
                    continue
                for dy in range(rng.randint(1, 4)):
                    y = heights[x] + dy
                    if (0 <= y < self.height
                            and self._base[y][x] in ("dirt", "grass")):
                        self._base[y][x] = "clay"

    def _place_trees(self, rng: random.Random, heights: List[int],
                     biomes: List[str]):
        """Oak trees — forest/plains/mountains only."""
        _NO_OAK = frozenset({"jungle", "swamp", "savanna", "taiga",
                              "mushroom_fields", "desert", "tundra"})
        x = rng.randint(3, 7)
        while x < self.width - 5:
            h     = heights[x]
            biome = biomes[x]
            # Plains: sparse oaks; forest: dense; mountains: sparse in valleys
            if biome in _NO_OAK or self._base[h][x] != "grass":
                x += rng.randint(2, 5)
                continue
            density = 0.45 if biome == "forest" else 0.18
            if rng.random() < density:
                trunk = rng.randint(4, 6)
                for ty in range(h - trunk, h):
                    if self._base[ty][x] is None:
                        self._base[ty][x] = "oak_log"
                top = h - trunk
                for lx in range(x - 2, x + 3):
                    for ly in range(top - 1, top + 2):
                        if (0 <= lx < self.width and 0 <= ly < self.height
                                and self._base[ly][lx] is None):
                            self._base[ly][lx] = "oak_leaves"
                for lx in range(x - 1, x + 2):
                    ly = top + 2
                    if (0 <= lx < self.width and 0 <= ly < self.height
                            and self._base[ly][lx] is None):
                        self._base[ly][lx] = "oak_leaves"
                x += rng.randint(5, 12)
            else:
                x += rng.randint(2, 5)

    def _place_cactus(self, rng: random.Random, heights: List[int],
                      biomes: List[str]):
        count = self.width // 80
        for _ in range(count):
            x = rng.randint(2, self.width - 3)
            if biomes[x] != "desert":
                continue
            h = heights[x]
            if self._base[h][x] != "sand":
                continue
            tall = rng.randint(1, 3)
            clear = True
            for dy in range(1, tall + 1):
                ny = h - dy
                if ny < 0 or self._base[ny][x] is not None:
                    clear = False
                    break
                for nx in (x - 1, x + 1):
                    if (0 <= nx < self.width
                            and self._base[ny][nx] is not None
                            and self._base[ny][nx] != "air"):
                        clear = False
                        break
            if clear:
                for dy in range(1, tall + 1):
                    self._base[h - dy][x] = "cactus"

    def _place_lakes(self, rng: random.Random, heights: List[int],
                     biomes: Optional[List[str]] = None):
        count = self.width // 90
        extras = 0
        if biomes:
            extras = sum(1 for b in biomes if b in ("swamp", "jungle")) // 150
        for _ in range(count + extras):
            cx = rng.randint(20, self.width - 20)
            if biomes is not None:
                if biomes[cx] in ("desert", "mushroom_fields"):
                    continue
            h  = heights[cx]
            w  = rng.randint(8, 20)
            depth = rng.randint(4, 8)

            # Carve the lake basin
            for dx in range(-w // 2, w // 2 + 1):
                x = cx + dx
                if not (0 <= x < self.width):
                    continue
                d = int(depth * (1 - (2 * abs(dx) / w) ** 2))
                if d <= 0:
                    continue
                lake_y = h + 1
                for dy in range(d):
                    ny = lake_y + dy
                    if 0 <= ny < self.height:
                        self._base[ny][x] = None
                # Clay at bottom
                ny = lake_y + d
                if 0 <= ny < self.height and self._base[ny][x] in ("dirt", "grass", "stone"):
                    self._base[ny][x] = "clay"

            # Fill with water
            water_level = h + 1
            for dx in range(-w // 2, w // 2 + 1):
                x = cx + dx
                if not (0 <= x < self.width):
                    continue
                d = int(depth * (1 - (2 * abs(dx) / w) ** 2))
                for dy in range(d):
                    ny = water_level + dy
                    if 0 <= ny < self.height and self._base[ny][x] is None:
                        self._base[ny][x] = "water"

    def _place_obsidian(self, rng: random.Random):
        count = self.width // 200
        for _ in range(count):
            x = rng.randint(5, self.width - 6)
            y = rng.randint(self.height - 30, self.height - 6)
            if self._base[y][x] == "stone":
                for _ in range(rng.randint(3, 8)):
                    nx = x + rng.randint(-2, 2)
                    ny = y + rng.randint(-1, 1)
                    if (0 <= nx < self.width and 0 <= ny < self.height
                            and self._base[ny][nx] == "stone"):
                        self._base[ny][nx] = "obsidian"

    def _place_snow_ice(self, rng: random.Random, heights: List[int],
                        biomes: Optional[List[str]] = None):
        """Freeze water to ice in tundra/taiga columns."""
        for x in range(self.width):
            if biomes:
                if biomes[x] not in ("tundra", "taiga"):
                    continue
            h = heights[x]
            # Ice over water
            if h + 1 < self.height and self._base[h + 1][x] == "water":
                self._base[h + 1][x] = "ice"
            if self._base[h][x] == "water":
                self._base[h][x] = "ice"

    # ── Biome-specific feature placement ────────────────────────────────────────

    def _place_jungle_features(self, rng: random.Random, heights: List[int],
                                biomes: List[str]):
        """Giant jungle trees and bamboo clusters in jungle biome."""
        x = rng.randint(3, 8)
        while x < self.width - 6:
            h = heights[x]
            if biomes[x] != "jungle":
                x += rng.randint(2, 5)
                continue
            surf = self._base[h][x]
            if surf in ("podzol", "grass") and rng.random() < 0.50:
                # Very tall jungle tree (8–14 trunk)
                trunk = rng.randint(8, 14)
                for ty in range(h - trunk, h):
                    if 0 <= ty < self.height and self._base[ty][x] is None:
                        self._base[ty][x] = "jungle_log"
                top = h - trunk
                # Wide, bushy canopy
                for lx in range(x - 3, x + 4):
                    for ly in range(top - 2, top + 3):
                        if (0 <= lx < self.width and 0 <= ly < self.height
                                and self._base[ly][lx] is None
                                and (abs(lx - x) + abs(ly - top) < 5)):
                            self._base[ly][lx] = "jungle_leaves"
                x += rng.randint(4, 8)
            else:
                x += rng.randint(2, 4)
        # Bamboo clusters
        count = self.width // 100
        for _ in range(count):
            bx = rng.randint(5, self.width - 5)
            if biomes[bx] != "jungle":
                continue
            h = heights[bx]
            if self._base[h][bx] not in ("podzol", "grass"):
                continue
            w = rng.randint(2, 5)
            for dx in range(-w, w + 1):
                cx = bx + dx
                if not (0 <= cx < self.width):
                    continue
                tall = rng.randint(4, 8)
                for ty in range(1, tall + 1):
                    ny = h - ty
                    if 0 <= ny < self.height and self._base[ny][cx] is None:
                        self._base[ny][cx] = "bamboo"

    def _place_swamp_features(self, rng: random.Random, heights: List[int],
                               biomes: List[str]):
        """Mangrove trees and lily pads in swamp biome."""
        x = rng.randint(3, 7)
        while x < self.width - 5:
            h = heights[x]
            if biomes[x] != "swamp":
                x += rng.randint(2, 5)
                continue
            surf = self._base[h][x]
            if surf in ("mud", "grass") and rng.random() < 0.30:
                # Short mangrove tree (3–5 trunk)
                trunk = rng.randint(3, 5)
                for ty in range(h - trunk, h):
                    if 0 <= ty < self.height and self._base[ty][x] is None:
                        self._base[ty][x] = "mangrove_log"
                top = h - trunk
                for lx in range(x - 2, x + 3):
                    for ly in range(top - 1, top + 2):
                        if (0 <= lx < self.width and 0 <= ly < self.height
                                and self._base[ly][lx] is None):
                            self._base[ly][lx] = "jungle_leaves"
                x += rng.randint(5, 10)
            else:
                x += rng.randint(2, 4)
        # Lily pads on water surfaces in swamp
        for x2 in range(self.width):
            if biomes[x2] != "swamp":
                continue
            h = heights[x2]
            if (self._base[h][x2] == "water"
                    and rng.random() < 0.25
                    and h - 1 >= 0 and self._base[h - 1][x2] is None):
                self._base[h - 1][x2] = "lily_pad"

    def _place_savanna_trees(self, rng: random.Random, heights: List[int],
                              biomes: List[str]):
        """Acacia trees with flat canopy in savanna biome."""
        x = rng.randint(3, 8)
        while x < self.width - 6:
            h = heights[x]
            if biomes[x] != "savanna":
                x += rng.randint(2, 6)
                continue
            if self._base[h][x] == "grass" and rng.random() < 0.20:
                # Angled acacia trunk (4–6 tiles)
                trunk = rng.randint(4, 6)
                lean  = rng.choice([-1, 1])
                cx    = x
                for ty in range(h - trunk, h):
                    if 0 <= ty < self.height and 0 <= cx < self.width:
                        if self._base[ty][cx] is None:
                            self._base[ty][cx] = "acacia_log"
                    if ty == h - trunk // 2:
                        cx += lean
                top = h - trunk
                # Very flat, wide canopy
                for lx in range(cx - 3, cx + 4):
                    for ly in range(top - 1, top + 2):
                        if (0 <= lx < self.width and 0 <= ly < self.height
                                and self._base[ly][lx] is None
                                and abs(ly - top) < 2):
                            self._base[ly][lx] = "acacia_leaves"
                x += rng.randint(10, 18)
            else:
                x += rng.randint(3, 7)

    def _place_taiga_trees(self, rng: random.Random, heights: List[int],
                            biomes: List[str]):
        """Conical spruce trees in taiga biome."""
        x = rng.randint(3, 7)
        while x < self.width - 5:
            h = heights[x]
            if biomes[x] != "taiga":
                x += rng.randint(2, 5)
                continue
            if self._base[h][x] in ("snow", "grass") and rng.random() < 0.40:
                trunk = rng.randint(6, 10)
                for ty in range(h - trunk, h):
                    if 0 <= ty < self.height and self._base[ty][x] is None:
                        self._base[ty][x] = "spruce_log"
                    # Podzol patch under tree
                    if 0 <= h < self.height:
                        self._base[h][x] = "podzol"
                top = h - trunk
                # Conical canopy: wide at bottom, narrow at top
                for layer, ly in enumerate(range(top, h)):
                    radius = min(3, (ly - top) // 2 + 1)
                    for lx in range(x - radius, x + radius + 1):
                        if (0 <= lx < self.width and 0 <= ly < self.height
                                and self._base[ly][lx] is None):
                            self._base[ly][lx] = "spruce_leaves"
                x += rng.randint(5, 10)
            else:
                x += rng.randint(2, 5)

    def _place_mushroom_features(self, rng: random.Random, heights: List[int],
                                  biomes: List[str]):
        """Giant red and brown mushrooms in mushroom fields biome."""
        x = rng.randint(3, 7)
        while x < self.width - 5:
            h = heights[x]
            if biomes[x] != "mushroom_fields":
                x += rng.randint(2, 5)
                continue
            if self._base[h][x] == "mycelium" and rng.random() < 0.35:
                mtype = rng.choice(["red", "brown"])
                cap   = "red_mushroom_block" if mtype == "red" else "brown_mushroom_block"
                stem_h = rng.randint(3, 8)
                for ty in range(h - stem_h, h):
                    if 0 <= ty < self.height and self._base[ty][x] is None:
                        self._base[ty][x] = "oak_log"   # mushroom stem (log texture)
                top = h - stem_h
                if mtype == "red":
                    # Dome cap
                    for lx in range(x - 2, x + 3):
                        for ly in range(top - 2, top + 1):
                            if (0 <= lx < self.width and 0 <= ly < self.height
                                    and self._base[ly][lx] is None
                                    and abs(lx - x) + abs(ly - top) < 4):
                                self._base[ly][lx] = cap
                else:
                    # Flat wide cap
                    for lx in range(x - 3, x + 4):
                        if 0 <= lx < self.width and 0 <= top < self.height:
                            if self._base[top][lx] is None:
                                self._base[top][lx] = cap
                        if (0 <= lx < self.width and 0 <= top + 1 < self.height
                                and abs(lx - x) <= 1):
                            if self._base[top + 1][lx] is None:
                                self._base[top + 1][lx] = cap
                x += rng.randint(8, 16)
            else:
                x += rng.randint(2, 5)

    def _place_structures(self, rng: random.Random, heights: List[int], scale: float):
        # Villages — absolute count (not scaled), evenly distributed
        village_count = rng.randint(3, 5)
        village_step  = self.width // max(village_count, 1)
        village_xs: List[int] = []
        for i in range(village_count):
            lo = i * village_step + 50
            hi = min((i + 1) * village_step - 50, self.width - 60)
            if lo >= hi:
                continue
            vx = rng.randint(lo, hi)
            if self._try_village(rng, vx, heights):
                village_xs.append(vx)

        # Rare isolated houses (sparse, away from villages)
        house_count = rng.randint(4, 8)
        step = self.width // max(house_count, 1)
        for i in range(house_count):
            lo = i * step + 5
            hi = min((i + 1) * step - 5, self.width - 15)
            if lo >= hi:
                continue
            x = rng.randint(lo, hi)
            # Skip if too close to a village
            if any(abs(x - vx) < 100 for vx in village_xs):
                continue
            self._try_house(rng, x, heights)

        # Underground ruins
        ruin_count = int(30 * scale)
        for _ in range(ruin_count):
            x  = rng.randint(10, self.width - 10)
            h  = heights[x]
            depth = rng.randint(15, min(50, self.height - h - 20))
            y  = h + depth
            self._try_ruin(rng, x, y)

        # Abandoned portals (surface)
        portal_count = rng.randint(2, 4)
        portal_step  = self.width // max(portal_count, 1)
        for i in range(portal_count):
            lo = i * portal_step + 30
            hi = min((i + 1) * portal_step - 30, self.width - 20)
            if lo >= hi:
                continue
            px = rng.randint(lo, hi)
            self._try_abandoned_portal(rng, px, heights)

        # Stronghold — exactly one, underground, with End portal frames
        self._place_stronghold(rng, heights)

    def _place_stronghold(self, rng: random.Random, heights: List[int]):
        """Carve a stronghold chamber underground with a 3×3 ring of End portal frames."""
        cx = rng.randint(self.width * 3 // 8, self.width * 5 // 8)
        surf_y = heights[min(cx, self.width - 1)]
        # Keep above the deep layer so cave passes can't wipe the frames
        safe_max = max(25, self._deep_start() - surf_y - 15)
        depth = rng.randint(20, min(45, safe_max))
        cy    = min(surf_y + depth, self.height - 16)

        RW, RH = 22, 12
        rx = cx - RW // 2
        ry = cy - RH // 2

        # Walls + floor + ceiling
        wall_tiles = ["mossy_cobblestone", "stone", "stone", "stone_bricks"]
        for y in range(max(0, ry - 1), min(self.height, ry + RH + 2)):
            for x in range(max(0, rx - 1), min(self.width, rx + RW + 2)):
                edge = (y <= ry or y >= ry + RH + 1
                        or x <= rx or x >= rx + RW + 1)
                if edge:
                    self._base[y][x] = rng.choice(wall_tiles)
                else:
                    self._base[y][x] = None   # hollow interior

        # Entrance tunnel up to surface
        for y in range(ry, surf_y, -1):
            if 0 <= y < self.height:
                for tx in range(cx - 1, cx + 2):
                    if 0 <= tx < self.width:
                        self._base[y][tx] = None

        # Torches along tunnel every 8 tiles
        for y in range(surf_y + 4, ry, -8):
            if 0 <= y < self.height and 0 <= cx < self.width:
                self._base[y][cx - 2] = "torch"

        # Gate-style portal: 2-tile-high opening so the player (52 px) can walk through.
        #   [F][F][F]   cy-1  ← top arch (solid frames)
        #   [.][.][.]   cy    ← open (becomes end_portal when activated)
        #   [.][.][.]   cy+1  ← open (becomes end_portal when activated)
        #   [F][F][F]   cy+2  ← bottom arch / floor under portal (solid frames)
        frame_positions = [
            (cx - 1, cy - 1), (cx, cy - 1), (cx + 1, cy - 1),   # top arch
            (cx - 1, cy + 2), (cx, cy + 2), (cx + 1, cy + 2),   # bottom arch (moved down)
        ]
        self._end_portal_frames: Dict[str, bool] = {}
        for fx, ffy in frame_positions:
            if 0 <= fx < self.width and 0 <= ffy < self.height:
                self._base[ffy][fx] = "end_portal_frame_empty"
                self._end_portal_frames[f"{fx},{ffy}"] = False
        # Both middle rows stay clear (future end_portal tiles)
        for row in (cy, cy + 1):
            for dx in (-1, 0, 1):
                if 0 <= cx + dx < self.width and 0 <= row < self.height:
                    self._base[row][cx + dx] = None

        # Glowstone flanking the gate — above top arch (cy-2) and below bottom arch (cy+3)
        for gx in (cx - 2, cx + 2):
            for gy in (cy - 2, cy + 3):
                if 0 <= gx < self.width and 0 <= gy < self.height:
                    self._base[gy][gx] = "glowstone"

        self._end_portal_cx  = cx
        self._end_portal_fy  = cy
        self._stronghold_cx  = cx
        self._stronghold_cy  = cy
        self._end_portal_active = False

        # Loot chest
        chx, chy = cx + 6, ry + RH - 1
        if 0 <= chx < self.width and 0 <= chy < self.height:
            self._base[chy][chx] = "chest"
            loot = []
            for item_id, mn, mx in [
                ("eye_of_ender", 2, 4), ("golden_apple", 1, 2),
                ("diamond", 1, 3), ("iron_ingot", 4, 8), ("obsidian", 2, 4),
            ]:
                n = rng.randint(mn, mx)
                loot.append(ItemStack(item_id, n).to_dict())
            self._containers[f"{chx},{chy}"] = loot + [None] * (27 - len(loot))

    # ── Deep layer generation ─────────────────────────────────────────────────

    def _deep_start(self) -> int:
        """Y coordinate where deepstone/cavern layer begins."""
        return int(self.height * 0.62)

    def _fill_deep_stone(self, heights: List[int]):
        """Replace stone with deepstone below the cavern threshold."""
        ds = self._deep_start()
        for y in range(ds, self.height - 4):
            for x in range(self.width):
                if self._base[y][x] == "stone":
                    self._base[y][x] = "deepstone"

    def _make_deep_caverns(self, rng: random.Random, heights: List[int], scale: float):
        """Large open cavern system in the deep layer."""
        ds = self._deep_start()
        TABLE_SIZE = max(256, self.width)
        tbl_x = self._make_noise_table(rng, TABLE_SIZE)
        tbl_y = self._make_noise_table(rng, TABLE_SIZE)

        # Tiles that must never be wiped by cave generation
        _CAVE_PROTECTED = frozenset({
            None, "bedrock",
            "end_portal_frame_empty", "end_portal_frame", "end_portal",
            "chest", "mossy_cobblestone",
        })

        # Noise-based large voids
        cpx = max(24, self.width // 14)
        cpy = max(12, (self.height - ds) // 5)
        for ty in range(ds, self.height - 6):
            for tx in range(self.width):
                nv = self._value_noise2d(tbl_x, tbl_y,
                                         tx / cpx, ty / cpy,
                                         TABLE_SIZE, TABLE_SIZE)
                if abs(nv - 0.5) < 0.16:
                    if self._base[ty][tx] not in _CAVE_PROTECTED:
                        self._base[ty][tx] = None

        # Extra worm tunnels for connectivity
        count = int(25 * scale)
        for _ in range(count):
            cx = rng.randint(10, self.width - 10)
            cy = rng.randint(ds + 5, self.height - 8)
            dx = rng.choice([-1, 0, 0, 1])
            dy = rng.choice([-1, 0, 0, 1])
            for _ in range(rng.randint(30, 80)):
                if rng.random() < 0.2:
                    dx = rng.choice([-1, 0, 0, 1])
                if rng.random() < 0.15:
                    dy = rng.choice([-1, 0, 0, 1])
                cx = max(2, min(self.width - 3, cx + dx))
                cy = max(ds, min(self.height - 6, cy + dy))
                r = rng.randint(2, 4)   # bigger radius than surface caves
                for oy in range(-r, r + 1):
                    for ox in range(-r, r + 1):
                        if ox * ox + oy * oy <= r * r:
                            nx, ny = cx + ox, cy + oy
                            if (0 <= nx < self.width and 0 <= ny < self.height
                                    and self._base[ny][nx] not in _CAVE_PROTECTED):
                                self._base[ny][nx] = None

    def _place_deep_ores(self, rng: random.Random, heights: List[int], scale: float):
        """Rare ores exclusive to the deep layer."""
        ds = self._deep_start()
        max_d = self.height - 6 - ds
        specs = [
            ("crystal_ore", 10, max_d, int(18 * scale), 3),
            ("diamond_ore", 15, max_d, int(12 * scale), 2),  # extra deep diamonds
            ("glowstone",    5, max_d, int(22 * scale), 2),
            ("magma_block",  8, max_d, int(30 * scale), 3),
        ]
        for tile_id, dmin, dmax, veins, vsize in specs:
            for _ in range(veins * 15):
                x = rng.randint(5, self.width - 6)
                d = rng.randint(dmin, max(dmin + 1, dmax))
                y = ds + d
                if y >= self.height - 5:
                    continue
                for _ in range(vsize + rng.randint(0, vsize)):
                    nx = max(1, min(self.width - 2, x + rng.randint(-2, 2)))
                    ny = max(ds, min(self.height - 6, y + rng.randint(-1, 1)))
                    if self._base[ny][nx] in ("deepstone", "stone", "obsidian"):
                        self._base[ny][nx] = tile_id

    def _place_crystal_clusters(self, rng: random.Random, heights: List[int], scale: float):
        """Place crystal_ore clusters on cave ceilings and walls in deep layer."""
        ds = self._deep_start()
        count = int(40 * scale)
        for _ in range(count):
            cx = rng.randint(5, self.width - 6)
            cy = rng.randint(ds + 3, self.height - 8)
            if self._base[cy][cx] is not None:
                continue  # only in open space
            # Check for solid block above/beside to attach to
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + ox, cy + oy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    if self._base[ny][nx] in ("deepstone", "stone"):
                        self._base[ny][nx] = "crystal_ore"

    def _place_lava_pools(self, rng: random.Random, heights: List[int], scale: float):
        """Pools of lava in the deepest part of the world."""
        lava_start = int(self.height * 0.82)
        count = int(30 * scale)
        for _ in range(count):
            cx = rng.randint(10, self.width - 10)
            cy = rng.randint(lava_start, self.height - 6)
            if self._base[cy][cx] is not None:
                continue  # only carve into empty space first
            for oy in range(-1, 2):
                for ox in range(-2, 3):
                    nx, ny = cx + ox, cy + oy
                    if (0 <= nx < self.width and 0 <= ny < self.height
                            and self._base[ny][nx] is None):
                        self._base[ny][nx] = "lava"

    # ── Nether generation ────────────────────────────────────────────────────

    def _generate_nether(self, seed: int):
        rng = random.Random(seed ^ 0xDEAD_BEEF)
        W, H = self.width, self.height

        # Fill solid netherrack
        for y in range(H):
            for x in range(W):
                self._base[y][x] = "netherrack"

        # Bedrock ceiling (y=0..3) and floor (y=H-4..H)
        for x in range(W):
            for y in range(4):
                self._base[y][x] = "bedrock"
            for y in range(H - 4, H):
                self._base[y][x] = "bedrock"

        # Carve large caverns (much bigger than overworld)
        TABLE_SIZE = max(512, W)
        tbl_x = self._make_noise_table(rng, TABLE_SIZE)
        tbl_y = self._make_noise_table(rng, TABLE_SIZE)

        cave_px = max(20, W // 14)
        cave_py = max(10, H // 6)
        for ty in range(4, H - 4):
            for tx in range(W):
                nv = self._value_noise2d(tbl_x, tbl_y,
                                         tx / cave_px, ty / cave_py,
                                         TABLE_SIZE, TABLE_SIZE)
                if abs(nv - 0.5) < 0.16:
                    self._base[ty][tx] = None

        # Worm tunnels for connectivity
        for _ in range(int(60 * (W / WORLD_W))):
            cx = rng.randint(10, W - 10)
            cy = rng.randint(8, H - 10)
            dx = rng.choice([-1, 0, 1])
            dy = rng.choice([-1, 0, 0, 1])
            steps = rng.randint(30, 80)
            for _ in range(steps):
                if rng.random() < 0.2: dx = rng.choice([-1, 0, 1])
                if rng.random() < 0.2: dy = rng.choice([-1, 0, 0, 1])
                cx = max(2, min(W - 3, cx + dx))
                cy = max(5, min(H - 6, cy + dy))
                r = rng.randint(1, 3)
                for oy in range(-r, r + 1):
                    for ox in range(-r, r + 1):
                        if ox*ox + oy*oy <= r*r:
                            nx2, ny2 = cx + ox, cy + oy
                            if (4 <= ny2 < H - 4 and 0 <= nx2 < W
                                    and self._base[ny2][nx2] != "bedrock"):
                                self._base[ny2][nx2] = None

        # Lava sea at bottom (~y = H*0.72 to H-4)
        lava_y = int(H * 0.72)
        for ty in range(lava_y, H - 4):
            for tx in range(W):
                if self._base[ty][tx] is None:
                    self._base[ty][tx] = "lava"

        # Nether quartz ore veins
        for _ in range(int(280 * (W / WORLD_W))):
            ox = rng.randint(1, W - 2)
            oy = rng.randint(5, H - 6)
            vsize = rng.randint(3, 9)
            for _ in range(vsize):
                nx2 = max(1, min(W - 2, ox + rng.randint(-2, 2)))
                ny2 = max(5, min(H - 6, oy + rng.randint(-1, 1)))
                if self._base[ny2][nx2] == "netherrack":
                    self._base[ny2][nx2] = "nether_quartz_ore"

        # Nether gold ore
        for _ in range(int(120 * (W / WORLD_W))):
            ox = rng.randint(1, W - 2)
            oy = rng.randint(5, H - 6)
            for _ in range(rng.randint(2, 6)):
                nx2 = max(1, min(W - 2, ox + rng.randint(-1, 1)))
                ny2 = max(5, min(H - 6, oy + rng.randint(-1, 1)))
                if self._base[ny2][nx2] == "netherrack":
                    self._base[ny2][nx2] = "nether_gold_ore"

        # Ancient debris (rare, deep)
        deep_y = int(H * 0.55)
        for _ in range(int(12 * (W / WORLD_W))):
            ox = rng.randint(1, W - 2)
            oy = rng.randint(deep_y, H - 6)
            if self._base[oy][ox] == "netherrack":
                self._base[oy][ox] = "ancient_debris"

        # Soul sand patches at floor of caverns
        for _ in range(int(40 * (W / WORLD_W))):
            ox = rng.randint(5, W - 6)
            for oy2 in range(5, lava_y):
                if self._base[oy2][ox] is None:
                    # Find floor
                    if oy2 + 1 < H and self._base[oy2 + 1][ox] not in (None, "lava", "bedrock"):
                        patch_w = rng.randint(2, 5)
                        for dp in range(patch_w):
                            px2 = ox + dp
                            if 0 < px2 < W:
                                self._base[oy2 + 1][px2] = "soul_sand"
                    break

        # Basalt spires
        for _ in range(int(25 * (W / WORLD_W))):
            bx = rng.randint(5, W - 6)
            # Find floor in a cavern
            for by in range(H - 6, 4, -1):
                if self._base[by][bx] is None and (by + 1 >= H - 4 or
                        self._base[by + 1][bx] in ("netherrack", "bedrock")):
                    h_spire = rng.randint(3, 7)
                    for sy2 in range(h_spire):
                        ny2 = by - sy2
                        if 4 <= ny2 < H - 4 and self._base[ny2][bx] is None:
                            self._base[ny2][bx] = "basalt"
                    break

        # Nether fortress — track X centers for blaze spawn zones
        self._blaze_zone_xs: list = []
        for _ in range(max(1, int(3 * (W / WORLD_W)))):
            fx = rng.randint(W // 10, W - W // 10)
            self._place_nether_fortress(rng, fx)
            self._blaze_zone_xs.append(fx)

        # Background layer = solid netherrack
        for y in range(H):
            for x in range(W):
                bg = "bedrock" if (y < 4 or y >= H - 4) else "netherrack"
                self._bg_base[y][x] = bg

        # Compute surface heights for lighting (use lava_y as "surface")
        self._surface_heights = [lava_y] * W

    def _place_nether_fortress(self, rng: random.Random, cx: int):
        """Place a simple nether brick fortress structure."""
        W, H = self.width, self.height
        # Find a mid-height cavern location
        mid_y = H // 2
        base_y = mid_y
        for dy in range(0, H // 4):
            ty2 = mid_y + dy
            if ty2 < H - 6 and self._base[ty2][cx] is None:
                base_y = ty2 + 1
                break

        if base_y >= H - 6:
            return

        # Main platform
        plat_w = rng.randint(30, 50)
        plat_x0 = max(2, cx - plat_w // 2)
        plat_x1 = min(W - 2, cx + plat_w // 2)
        plat_y  = base_y

        for x in range(plat_x0, plat_x1):
            if 0 <= x < W and 0 <= plat_y < H:
                self._base[plat_y][x] = "nether_brick"
            # Pillars down
            for dy in range(1, rng.randint(3, 8)):
                ny2 = plat_y + dy
                if ny2 < H - 4:
                    self._base[ny2][x] = "nether_brick" if x == plat_x0 or x == plat_x1 - 1 else None

        # 2-3 rooms on the platform
        n_rooms = rng.randint(2, 3)
        rx = plat_x0 + 2
        for _ in range(n_rooms):
            rw = rng.randint(6, 10)
            rh = rng.randint(4, 6)
            if rx + rw >= plat_x1 - 2:
                break
            # Walls
            for dy in range(1, rh + 1):
                ny2 = plat_y - dy
                if ny2 < 4:
                    break
                for dx in range(rw):
                    nx2 = rx + dx
                    if 0 <= nx2 < W:
                        if dx == 0 or dx == rw - 1 or dy == rh:
                            self._base[ny2][nx2] = "nether_brick"
            # Door opening
            door_x = rx + rw // 2
            if 0 <= door_x < W:
                self._base[plat_y - 1][door_x] = None
                self._base[plat_y - 2][door_x] = None
            # Nether wart decoration on roof
            roof_y = plat_y - rh
            if roof_y > 4:
                for dx in range(1, rw - 1, 2):
                    nx2 = rx + dx
                    if 0 <= nx2 < W:
                        self._base[roof_y][nx2] = "nether_wart_block"
            # Chest with loot inside
            chest_x = rx + rw // 2
            chest_y = plat_y - 2
            if (0 <= chest_x < W and 0 <= chest_y < H
                    and self._base[chest_y][chest_x] is None):
                self._base[chest_y][chest_x] = "chest"
                loot = []
                for _ in range(rng.randint(2, 5)):
                    choice = rng.choice([
                        ("nether_quartz", 2, 8),
                        ("gold_ingot", 1, 3),
                        ("blaze_rod", 1, 2),
                        ("nether_brick", 4, 12),
                        ("ghast_tear", 1, 1),
                        ("diamond", 1, 1),
                    ])
                    item_id, lo, hi = choice
                    loot.append(ItemStack(item_id, rng.randint(lo, hi)).to_dict())
                self._containers[f"{chest_x},{chest_y}"] = loot + [None] * (27 - len(loot))
            rx += rw + 3

        # Blaze tower — a dedicated open-air shaft above the fortress center
        # where blazes naturally congregate.  16 wide, 25 tall, nether_brick walls,
        # glowstone ceiling, open interior so blazes can fly freely.
        tower_w  = 16
        tower_h  = 25
        tx0 = max(2, cx - tower_w // 2)
        tx1 = min(W - 2, cx + tower_w // 2)
        top_y = plat_y - tower_h
        if top_y >= 4:
            for ty2 in range(top_y, plat_y):
                for bx2 in range(tx0, tx1 + 1):
                    if 0 <= bx2 < W:
                        on_wall = (bx2 == tx0 or bx2 == tx1)
                        on_roof = (ty2 == top_y)
                        if on_wall or on_roof:
                            self._base[ty2][bx2] = "nether_brick"
                        elif self._base[ty2][bx2] is not None:
                            self._base[ty2][bx2] = None   # clear interior
            # Glowstone lanterns at the top corners
            for bx2 in (tx0 + 2, tx1 - 2):
                if 0 <= bx2 < W and 0 <= top_y < H:
                    self._base[top_y][bx2] = "glowstone"

    # ── End generation ───────────────────────────────────────────────────────

    def _generate_end(self, seed: int):
        """Floating islands of end_stone in the void, central arena, obsidian pillars."""
        rng = random.Random(seed ^ 0xE4D_B055)
        W, H = self.width, self.height
        cx   = W // 2

        # Helper: fill rectangle with end_stone
        def _rect(x0, y0, x1, y1, tile="end_stone"):
            for yy in range(max(0, y0), min(H, y1 + 1)):
                for xx in range(max(0, x0), min(W, x1 + 1)):
                    self._base[yy][xx] = tile

        # ── Central arena island ──────────────────────────────────────────
        arena_w = 60
        arena_h = 6
        arena_y = H // 2
        _rect(cx - arena_w // 2, arena_y, cx + arena_w // 2, arena_y + arena_h)
        # Smooth underside (taper edges)
        for edge in range(1, 8):
            _rect(cx - arena_w // 2 + edge, arena_y + arena_h + edge // 2,
                  cx + arena_w // 2 - edge, arena_y + arena_h + edge // 2)

        # ── Obsidian pillars with end crystals ───────────────────────────
        pillar_xs = [cx - 22, cx - 10, cx + 10, cx + 22]
        for px in pillar_xs:
            ph = rng.randint(8, 14)
            # Build pillar from arena top upward
            for py in range(arena_y - ph, arena_y):
                if 0 <= py < H:
                    self._base[py][px] = "obsidian"
            # End crystal on top
            top_y = arena_y - ph - 1
            if 0 <= top_y < H:
                self._base[top_y][px] = "end_crystal"

        # ── Floating side islands ─────────────────────────────────────────
        side_offsets = [(-90, -8), (90, -6), (-140, 4), (140, 2), (-60, 12), (65, 10)]
        for ox, oy in side_offsets:
            iw = rng.randint(18, 32)
            ih = rng.randint(3, 6)
            ix = cx + ox
            iy = arena_y + oy
            _rect(ix - iw // 2, iy, ix + iw // 2, iy + ih)
            # Chorus plants on top
            for _ in range(rng.randint(1, 4)):
                cpx = rng.randint(ix - iw // 2 + 1, ix + iw // 2 - 1)
                cpy = iy - 1
                if 0 <= cpy < H:
                    self._base[cpy][cpx] = "chorus_plant"

        # ── End portal frame at center of arena ───────────────────────────
        # 4 frame blocks in a + pattern; each has 10% chance of spawning
        # with an Eye of Ender already inserted (independent per cell).
        fy = arena_y - 1
        frame_positions = [
            (cx - 2, fy), (cx + 2, fy), (cx, fy - 2), (cx, fy + 2),
        ]
        self._end_portal_frames: Dict[str, bool] = {}
        for fx, fffy in frame_positions:
            has_eye = rng.random() < 0.10
            self._end_portal_frames[f"{fx},{fffy}"] = has_eye
            if 0 <= fffy < H and 0 <= fx < W:
                tile = "end_portal_frame" if has_eye else "end_portal_frame_empty"
                self._base[fffy][fx] = tile

        self._end_portal_cx  = cx
        self._end_portal_fy  = fy

        # If all frames happened to spawn pre-filled, open immediately
        if all(self._end_portal_frames.values()):
            for py in range(fy - 1, fy + 2):
                for px in range(cx - 1, cx + 2):
                    if self.get(px, py) is None:
                        self._set_raw(px, py, "end_portal")
            self._end_portal_active = True
        else:
            self._end_portal_active = False

        # Surface heights dummy (used by camera clamp)
        self._surface_heights = [arena_y] * W

    def activate_end_frame(self, tx: int, ty: int) -> bool:
        """Insert an Eye of Ender into one frame block.
        Returns True when all frames are activated and the portal opens."""
        if not hasattr(self, "_end_portal_frames"):
            return False
        key = f"{tx},{ty}"
        if key not in self._end_portal_frames or self._end_portal_frames[key]:
            return False
        self._end_portal_frames[key] = True
        # Swap tile to show the eye visually
        self._set_raw(tx, ty, "end_portal_frame")
        if all(self._end_portal_frames.values()):
            # Open the portal — fill inner tiles (2-row opening) with end_portal
            cx = self._end_portal_cx
            fy = self._end_portal_fy
            for py in range(fy - 1, fy + 3):   # cy-1..cy+2; frames skip non-None
                for px in range(cx - 1, cx + 2):
                    if self.get(px, py) is None:
                        self._set_raw(px, py, "end_portal")
            self._end_portal_active = True
            return True
        return False

    # ── Background layer ─────────────────────────────────────────────────────

    def _generate_background(self, heights: List[int]):
        """Fill background layer with stone/dirt mirroring surface, deepstone below threshold."""
        ds = self._deep_start()
        for x in range(self.width):
            h = heights[x]
            for y in range(self.height - 4, self.height):
                self._bg_base[y][x] = "bedrock"
            for y in range(ds, self.height - 4):
                self._bg_base[y][x] = "deepstone"
            for y in range(h + 1, ds):
                self._bg_base[y][x] = "stone"
            for y in range(h - 2, h + 1):
                if 0 <= y < self.height:
                    self._bg_base[y][x] = "dirt"

    def _try_house(self, rng: random.Random, cx: int, heights: List[int]) -> bool:
        W = rng.randint(7, 11)
        H = rng.randint(4, 6)
        if cx + W + 3 >= self.width or cx < 3:
            return False

        hs = heights[cx:cx + W]
        if not hs:
            return False
        base_y = max(hs)
        if max(hs) - min(hs) > 3:
            return False
        if base_y + 2 >= self.height:
            return False

        # Conflict check
        for dx in range(-1, W + 1):
            for dy in range(-H - 2, 2):
                ny = base_y + dy
                nx = cx + dx
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    t = self._base[ny][nx]
                    if t in ("oak_log", "workbench", "chest", "water"):
                        return False

        # Floor
        for dx in range(W):
            if 0 <= base_y < self.height:
                self._base[base_y][cx + dx] = "cobblestone"

        # Walls and interior
        for dy in range(1, H):
            ny = base_y - dy
            if not 0 <= ny < self.height:
                continue
            for dx in range(W):
                nx = cx + dx
                if not 0 <= nx < self.width:
                    continue
                if dx == 0 or dx == W - 1:
                    self._base[ny][nx] = "oak_planks"
                else:
                    self._base[ny][nx] = None

        # Roof
        roof_y = base_y - H
        if 0 < roof_y < self.height:
            for dx in range(-1, W + 1):
                nx = cx + dx
                if 0 <= nx < self.width:
                    self._base[roof_y][nx] = "oak_log"

        # Door opening (left side) — 2-block tall door
        door_nx = cx + 1
        if 0 <= door_nx < self.width:
            if 0 <= base_y - 1 < self.height:
                self._base[base_y - 1][door_nx] = "oak_door"
            if 0 <= base_y - 2 < self.height:
                self._base[base_y - 2][door_nx] = "oak_door_top"

        # Window (right side)
        win_nx = cx + W - 2
        win_ny = base_y - H // 2
        if 0 <= win_nx < self.width and 0 <= win_ny < self.height:
            self._base[win_ny][win_nx] = "glass"

        # Chest inside (40% chance)
        if rng.random() < 0.4:
            chest_nx = cx + W // 2
            chest_ny = base_y - 1
            if 0 <= chest_nx < self.width and 0 <= chest_ny < self.height:
                self._base[chest_ny][chest_nx] = "chest"
                loot = []
                if rng.random() < 0.8:
                    loot.append(ItemStack("oak_planks", rng.randint(4, 12)).to_dict())
                if rng.random() < 0.6:
                    loot.append(ItemStack("coal", rng.randint(2, 6)).to_dict())
                if rng.random() < 0.3:
                    loot.append(ItemStack("iron_ingot", rng.randint(1, 3)).to_dict())
                if rng.random() < 0.5:
                    loot.append(ItemStack("bread", rng.randint(1, 3)).to_dict())
                if rng.random() < 0.35:
                    loot.append(ItemStack("apple", rng.randint(1, 4)).to_dict())
                if rng.random() < 0.2:
                    loot.append(ItemStack("gunpowder", rng.randint(1, 3)).to_dict())
                if rng.random() < 0.15:
                    loot.append(ItemStack("string", rng.randint(2, 6)).to_dict())
                key = f"{chest_nx},{chest_ny}"
                self._containers[key] = loot + [None] * (27 - len(loot))

        return True

    def _try_village(self, rng: random.Random, cx: int, heights: List[int]) -> bool:
        """Place an organized village: 3-6 houses on a flat stretch, with a stone path."""
        # Find a flat-enough stretch around cx
        half = 60
        x0 = max(5, cx - half)
        x1 = min(self.width - 5, cx + half)
        hs = [heights[x] for x in range(x0, x1)]
        if not hs or max(hs) - min(hs) > 5:
            return False  # terrain too rough for a village

        base_y = max(hs)   # village ground level (stone path)
        house_n = rng.randint(3, 6)
        spacing = (x1 - x0) // max(house_n, 1)

        # Stone path along village width
        for x in range(x0, x1):
            if 0 <= base_y < self.height and self._base[base_y][x] in ("grass", "snow", "sand", "dirt"):
                self._base[base_y][x] = "cobblestone"

        # Place houses at regular intervals
        placed = 0
        for i in range(house_n):
            hx = x0 + i * spacing + rng.randint(2, max(2, spacing - 12))
            if hx + 12 >= self.width:
                continue
            if self._try_house(rng, hx, heights):
                placed += 1

        # Simple well in the center: 2×2 hole with cobblestone rim
        wx = cx
        wy = base_y
        if 2 <= wx < self.width - 2 and wy > 3:
            for dxx in range(-1, 2):
                for dyy in range(-1, 3):
                    nx = wx + dxx
                    ny = wy + dyy
                    if 0 <= nx < self.width and 0 <= ny < self.height:
                        if dxx == -1 or dxx == 1 or dyy < 0 or dyy == 2:
                            self._base[ny][nx] = "cobblestone"
                        else:
                            self._base[ny][nx] = None  # well interior
            # Water at bottom of well
            for dxx in (0,):
                ny = wy + 3
                if 0 <= ny < self.height:
                    self._base[ny][wx] = "water"

        return placed > 0

    def _try_ruin(self, rng: random.Random, cx: int, cy: int):
        W = rng.randint(4, 7)
        H = rng.randint(3, 5)
        if cx + W + 1 >= self.width or cx < 1:
            return
        if cy + 2 >= self.height or cy - H < 0:
            return

        # Check area is stone
        stone_count = 0
        for dx in range(W):
            for dy in range(H):
                t = self._base[cy - dy][cx + dx]
                if t == "stone":
                    stone_count += 1
        if stone_count < W * H * 0.6:
            return

        # Carve interior
        for dy in range(H):
            for dx in range(W):
                ny = cy - dy
                nx = cx + dx
                if 0 <= ny < self.height and 0 <= nx < self.width:
                    self._base[ny][nx] = None

        # Mossy cobblestone walls (some missing for ruined look)
        for side_x in range(cx - 1, cx + W + 1):
            for side_y in [cy + 1, cy - H]:
                if 0 <= side_x < self.width and 0 <= side_y < self.height:
                    if rng.random() < 0.75:
                        self._base[side_y][side_x] = "mossy_cobblestone"
        for dy in range(-H, 2):
            for side_x in [cx - 1, cx + W]:
                ny = cy + dy
                if 0 <= side_x < self.width and 0 <= ny < self.height:
                    if rng.random() < 0.75:
                        self._base[ny][side_x] = "mossy_cobblestone"

        # Treasure chest (50% chance)
        if rng.random() < 0.5:
            chest_nx = cx + W // 2
            chest_ny = cy - 1
            if 0 <= chest_nx < self.width and 0 <= chest_ny < self.height:
                self._base[chest_ny][chest_nx] = "chest"
                loot = []
                if rng.random() < 0.9:
                    loot.append(ItemStack("coal", rng.randint(3, 8)).to_dict())
                if rng.random() < 0.6:
                    loot.append(ItemStack("iron_ingot", rng.randint(1, 4)).to_dict())
                if rng.random() < 0.25:
                    loot.append(ItemStack("gold_ingot", rng.randint(1, 2)).to_dict())
                if rng.random() < 0.1:
                    loot.append(ItemStack("diamond", 1).to_dict())
                if rng.random() < 0.4:
                    loot.append(ItemStack("torch", rng.randint(2, 6)).to_dict())
                if rng.random() < 0.5:
                    loot.append(ItemStack("gunpowder", rng.randint(1, 4)).to_dict())
                if rng.random() < 0.4:
                    loot.append(ItemStack("bread", rng.randint(1, 3)).to_dict())
                if rng.random() < 0.3:
                    loot.append(ItemStack("cooked_beef", rng.randint(1, 2)).to_dict())
                if rng.random() < 0.2:
                    loot.append(ItemStack("iron_nugget", rng.randint(2, 6)).to_dict())
                if rng.random() < 0.15:
                    loot.append(ItemStack("string", rng.randint(2, 4)).to_dict())
                key = f"{chest_nx},{chest_ny}"
                self._containers[key] = loot + [None] * (27 - len(loot))

    def _try_abandoned_portal(self, rng: random.Random,
                              cx: int, heights: List[int]) -> bool:
        """Place a ruined Nether-portal frame on the surface with a loot chest."""
        if cx < 5 or cx + 10 >= self.width:
            return False

        # Portal frame: 6 wide, 5 tall pillar cross-section
        #   col offsets 0 and 5 = obsidian pillars (4 high)
        #   row at top = connecting obsidian arch
        hs = heights[cx: cx + 6]
        if not hs:
            return False
        base_y = max(hs)
        if max(hs) - min(hs) > 4:
            return False
        if base_y + 2 >= self.height or base_y - 6 < 0:
            return False

        # Blocks for the ruined frame: list of (dx, dy_from_base, tile, chance_to_place)
        # dy < 0 = above ground, dy == 0 = at surface
        frame_blocks = [
            # Left pillar (x=0)
            (0, 0, "obsidian", 1.00),
            (0, -1, "obsidian", 1.00),
            (0, -2, "obsidian", 0.85),
            (0, -3, "obsidian", 0.75),
            (0, -4, "obsidian", 0.60),
            # Right pillar (x=5)
            (5, 0, "obsidian", 1.00),
            (5, -1, "obsidian", 1.00),
            (5, -2, "obsidian", 0.85),
            (5, -3, "obsidian", 0.75),
            (5, -4, "obsidian", 0.55),
            # Top arch
            (1, -4, "obsidian", 0.70),
            (2, -4, "obsidian", 0.80),
            (3, -4, "obsidian", 0.80),
            (4, -4, "obsidian", 0.70),
            # Corner crying obsidian decoration
            (0, -5, "obsidian", 0.45),
            (5, -5, "obsidian", 0.45),
            # Netherrack patches at base (portal rubble)
            (-1, 0, "netherrack", 0.65),
            (6, 0, "netherrack", 0.65),
            (-1, -1, "netherrack", 0.40),
            (6, -1, "netherrack", 0.40),
            (1, 0, "netherrack", 0.35),
            (4, 0, "netherrack", 0.35),
        ]

        # Check no existing structures conflict
        for dx, dy, _, _ in frame_blocks:
            nx, ny = cx + dx, base_y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                t = self._base[ny][nx]
                if t in ("oak_log", "workbench", "chest", "obsidian"):
                    return False

        # Place frame blocks
        for dx, dy, tile, chance in frame_blocks:
            if rng.random() > chance:
                continue
            nx, ny = cx + dx, base_y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                self._base[ny][nx] = tile

        # Loot chest — always placed, at the base interior centre
        chest_nx = cx + 2
        chest_ny = base_y - 1
        if 0 <= chest_nx < self.width and 0 <= chest_ny < self.height:
            self._base[chest_ny][chest_nx] = "chest"
            loot: list = []

            if rng.random() < 0.70:
                loot.append(ItemStack("obsidian", rng.randint(1, 5)).to_dict())
            if rng.random() < 0.40:
                loot.append(ItemStack("flint_and_steel", 1).to_dict())
            if rng.random() < 0.20:
                loot.append(ItemStack("golden_apple", rng.randint(1, 4)).to_dict())
            if rng.random() < 0.15:
                loot.append(ItemStack("golden_carrot", rng.randint(1, 5)).to_dict())
            if rng.random() < 0.05:
                loot.append(ItemStack("gold_deagle", 1).to_dict())
            if rng.random() < 0.01:
                loot.append(ItemStack("gold_minigun", 1).to_dict())
            if rng.random() < 0.10:
                loot.append(ItemStack("eye_of_ender", rng.randint(2, 6)).to_dict())

            # 30%: one random golden armor piece with a protection enchant
            if rng.random() < 0.30:
                armor_piece = rng.choice([
                    "golden_helmet", "golden_chestplate",
                    "golden_leggings", "golden_boots",
                ])
                ench_id = rng.choice(["protection", "fire_protection"])
                ench_lvl = rng.randint(1, 2)
                stack = ItemStack(armor_piece, 1)
                stack.enchantments = {ench_id: ench_lvl}
                loot.append(stack.to_dict())

            key = f"{chest_nx},{chest_ny}"
            self._containers[key] = loot + [None] * (27 - len(loot))

        return True

    # ── Rendering ────────────────────────────────────────────────────────────

    def _tex_for(self, key: str) -> pygame.Surface:
        if key not in self._tex:
            from assets import load_texture
            self._tex[key] = load_texture(key, TILE_SIZE)
        return self._tex[key]

    def _dim_tex_for(self, key: str) -> pygame.Surface:
        """Dimmed (60% brightness) texture for background layer."""
        if key not in self._dim_tex:
            from assets import load_texture
            src = load_texture(key, TILE_SIZE)
            dim = src.copy()
            dim.fill((0, 0, 0, 100), special_flags=pygame.BLEND_RGBA_MULT)
            # Actually darken RGB while keeping alpha
            dim = src.copy()
            arr = pygame.surfarray.pixels3d(dim)
            arr[:] = (arr * 0.5).astype(arr.dtype)
            del arr
            self._dim_tex[key] = dim
        return self._dim_tex[key]

    def draw(self, screen: pygame.Surface, camera: Camera,
             mining_target: Optional[Tuple[int, int]] = None,
             mining_progress: float = 0.0,
             active_layer: str = "fg"):
        sw, sh = screen.get_size()
        TS = TILE_SIZE

        if self.dimension == "nether":
            _draw_nether_sky(screen)
        else:
            _draw_sky(screen)

        x0 = max(0, int(camera.x) // TS)
        y0 = max(0, int(camera.y) // TS)
        x1 = min(self.width,  x0 + sw // TS + 2)
        y1 = min(self.height, y0 + sh // TS + 2)

        water_tiles: List[Tuple[int, int]] = []
        lava_tiles:  List[Tuple[int, int]] = []

        for ty in range(y0, y1):
            for tx in range(x0, x1):
                # Background layer: render where foreground is empty
                fg_tile = self.get(tx, ty)
                if fg_tile is None or fg_tile in ("water", "lava"):
                    bg_tile = self.get_bg(tx, ty)
                    if bg_tile and bg_tile not in ("bedrock",):
                        bg_data = TILE_DATA.get(bg_tile)
                        if bg_data:
                            sx = tx * TS - int(camera.x)
                            sy = ty * TS - int(camera.y)
                            screen.blit(self._dim_tex_for(bg_data[0]), (sx, sy))
                            if mining_target == (tx, ty) and mining_progress > 0:
                                ov = pygame.Surface((TS, TS), pygame.SRCALPHA)
                                ov.fill((0, 0, 0, int(180 * mining_progress)))
                                screen.blit(ov, (sx, sy))
                    if fg_tile == "water":
                        water_tiles.append((tx, ty))
                    elif fg_tile == "lava":
                        lava_tiles.append((tx, ty))
                    continue

                tile = fg_tile
                data = TILE_DATA.get(tile)
                if data is None:
                    continue
                sx = tx * TS - int(camera.x)
                sy = ty * TS - int(camera.y)
                tex = self._tex_for(data[0])
                if tile in ("oak_door_open", "oak_door_top_open"):
                    # Render open door semi-transparent
                    faded = tex.copy()
                    faded.set_alpha(80)
                    screen.blit(faded, (sx, sy))
                else:
                    screen.blit(tex, (sx, sy))

                if mining_target == (tx, ty) and mining_progress > 0:
                    ov = pygame.Surface((TS, TS), pygame.SRCALPHA)
                    ov.fill((0, 0, 0, int(180 * mining_progress)))
                    screen.blit(ov, (sx, sy))

        # Water rendered last (semi-transparent blue overlay)
        if water_tiles:
            ws = pygame.Surface((TS, TS), pygame.SRCALPHA)
            ws.fill((30, 90, 200, 150))
            pygame.draw.line(ws, (80, 150, 255, 60), (2, TS // 3), (TS - 2, TS // 3), 1)
            pygame.draw.line(ws, (80, 150, 255, 40), (2, TS * 2 // 3), (TS - 2, TS * 2 // 3), 1)
            for tx, ty in water_tiles:
                sx = tx * TS - int(camera.x)
                sy = ty * TS - int(camera.y)
                screen.blit(ws, (sx, sy))

        # Lava: semi-transparent orange-red overlay with shimmer
        if lava_tiles:
            ls = pygame.Surface((TS, TS), pygame.SRCALPHA)
            ls.fill((210, 60, 10, 200))
            pygame.draw.line(ls, (255, 120, 30, 80), (2, TS // 3), (TS - 2, TS // 3), 2)
            pygame.draw.line(ls, (255, 90, 10, 50), (2, TS * 2 // 3), (TS - 2, TS * 2 // 3), 1)
            for tx, ty in lava_tiles:
                sx = tx * TS - int(camera.x)
                sy = ty * TS - int(camera.y)
                screen.blit(ls, (sx, sy))

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "version":            GAME_VERSION,
            "seed":               self.seed,
            "width":              self.width,
            "height":             self.height,
            "dimension":          self.dimension,
            "mods":               self._mods,
            "bg_mods":            self._bg_mods,
            "containers":         self._containers,
            "achievements":       list(self._achievements),
            "end_portal_frames":  getattr(self, "_end_portal_frames", {}),
            "end_portal_active":  getattr(self, "_end_portal_active", False),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "World":
        width  = d.get("width",  WORLD_W)
        height = d.get("height", WORLD_H)
        dim    = d.get("dimension", "overworld")
        obj = cls(d["seed"], width, height, dim)   # generates _base

        if "mods" in d:
            obj._mods = d["mods"]
        elif "tiles" in d:
            # Legacy: full tile array — diff against freshly generated _base
            old_tiles = d["tiles"]
            for y in range(min(height, len(old_tiles))):
                row = old_tiles[y]
                for x in range(min(width, len(row))):
                    old_val = row[x]
                    gen_val = obj._base[y][x]
                    if old_val != gen_val:
                        obj._mods[f"{x},{y}"] = old_val

        obj._bg_mods      = d.get("bg_mods", {})
        obj._containers   = d.get("containers", {})
        obj._achievements = set(d.get("achievements", []))
        # Restore End portal activation state (overrides values set by _place_stronghold)
        if "end_portal_frames" in d:
            obj._end_portal_frames = d["end_portal_frames"]
        if "end_portal_active" in d:
            obj._end_portal_active = d["end_portal_active"]
        # Force portal frames into _mods so they render even if _base was regenerated
        # differently. Only applies to positions the player has not explicitly modified.
        if hasattr(obj, "_end_portal_frames"):
            for key, has_eye in obj._end_portal_frames.items():
                if key not in obj._mods:
                    obj._mods[key] = "end_portal_frame" if has_eye else "end_portal_frame_empty"
        return obj

    # ── Redstone ──────────────────────────────────────────────────────────────

    _RS_SOURCES = frozenset({"lever_on", "redstone_torch_on",
                              "stone_button_on", "wooden_button_on",
                              "pressure_plate_on", "wooden_pressure_plate_on"})
    _RS_WIRE    = frozenset({"redstone_wire"})
    _RS_DOORS   = frozenset({"oak_door", "oak_door_open"})

    def _is_powered(self, x: int, y: int, depth: int = 0) -> bool:
        """BFS: returns True if (x,y) is connected to a power source within 15 tiles."""
        if depth > 15:
            return False
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            t = self.get(x + dx, y + dy)
            if t in self._RS_SOURCES:
                return True
            if t in self._RS_WIRE and depth < 14:
                if self._is_powered(x + dx, y + dy, depth + 1):
                    return True
        return False

    def toggle_lever(self, x: int, y: int):
        t = self.get(x, y)
        if t == "lever_off":
            self.set(x, y, "lever_on")
        elif t == "lever_on":
            self.set(x, y, "lever_off")
        self._update_powered_doors_near(x, y)

    def activate_button(self, x: int, y: int):
        t = self.get(x, y)
        if t in ("stone_button_off", "wooden_button_off"):
            on = "stone_button_on" if t.startswith("stone") else "wooden_button_on"
            self.set(x, y, on)
            self._button_timers[f"{x},{y}"] = 20   # 20 ticks (~0.33s at 60fps)
            self._update_powered_doors_near(x, y)

    def tick_redstone(self) -> None:
        expired = []
        for key, ticks in self._button_timers.items():
            self._button_timers[key] = ticks - 1
            if self._button_timers[key] <= 0:
                expired.append(key)
        for key in expired:
            del self._button_timers[key]
            x, y = map(int, key.split(","))
            t = self.get(x, y)
            if t in ("stone_button_on", "wooden_button_on"):
                off = "stone_button_off" if t.startswith("stone") else "wooden_button_off"
                self.set(x, y, off)
                self._update_powered_doors_near(x, y)

    def update_pressure_plates(self, px: int, py: int) -> None:
        """Activate pressure plates the player stands on, deactivate others near them."""
        check_r = 3
        for dy in range(-check_r, check_r + 1):
            for dx in range(-check_r, check_r + 1):
                tx, ty = px + dx, py + dy
                t = self.get(tx, ty)
                if t in ("pressure_plate_off", "wooden_pressure_plate_off",
                         "pressure_plate_on", "wooden_pressure_plate_on"):
                    on_tile = (abs(dx) <= 1 and abs(dy) <= 1
                               and abs(tx - px) <= 1 and abs(ty - py) <= 1)
                    player_on = (px == tx and (py == ty or py == ty - 1))
                    want_on = player_on
                    is_on   = t.endswith("_on")
                    if want_on and not is_on:
                        new_t = t.replace("_off", "_on")
                        self.set(tx, ty, new_t)
                        self._update_powered_doors_near(tx, ty)
                    elif not want_on and is_on:
                        new_t = t.replace("_on", "_off")
                        self.set(tx, ty, new_t)
                        self._update_powered_doors_near(tx, ty)

    def _update_powered_doors_near(self, cx: int, cy: int, radius: int = 16):
        """Open/close doors that are powered/unpowered near (cx,cy)."""
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx, ty = cx + dx, cy + dy
                t = self.get(tx, ty)
                if t in ("oak_door", "oak_door_open"):
                    powered = self._is_powered(tx, ty)
                    if powered and t == "oak_door":
                        self._set_raw(tx, ty, "oak_door_open")
                        top = self.get(tx, ty - 1)
                        if top in ("oak_door_top", "oak_door_top_open"):
                            self._set_raw(tx, ty - 1, "oak_door_top_open")
                    elif not powered and t == "oak_door_open":
                        self._set_raw(tx, ty, "oak_door")
                        top = self.get(tx, ty - 1)
                        if top in ("oak_door_top", "oak_door_top_open"):
                            self._set_raw(tx, ty - 1, "oak_door_top")


# ── Physics ───────────────────────────────────────────────────────────────────

def _player_in_water(player: Player, world: World) -> bool:
    """Return True if the player's body center is inside a water tile."""
    cx = int((player.x + PLAYER_W / 2) // TILE_SIZE)
    cy = int((player.y + PLAYER_H * 0.6) // TILE_SIZE)
    return world.get(cx, cy) == "water"


def _player_head_in_water(player: Player, world: World) -> bool:
    """Return True if the player's head is submerged."""
    cx = int((player.x + PLAYER_W / 2) // TILE_SIZE)
    cy = int((player.y + PLAYER_H * 0.2) // TILE_SIZE)
    return world.get(cx, cy) == "water"


def _player_in_lava(player: Player, world: World) -> bool:
    """Return True if the player's body center is inside a lava tile."""
    cx = int((player.x + PLAYER_W / 2) // TILE_SIZE)
    cy = int((player.y + PLAYER_H * 0.6) // TILE_SIZE)
    return world.get(cx, cy) == "lava"


def update_player(player: Player, world: World, keys: set, defense: int = 0):
    player.just_jumped = False
    dt = 1.0 / FPS

    def _k(*ks):
        return any(keys.get(k, False) for k in ks)

    player.in_water = _player_in_water(player, world)
    player.in_lava  = _player_in_lava(player, world)
    head_submerged  = _player_head_in_water(player, world)

    # Oxygen / drowning
    if head_submerged:
        player.oxygen = max(0.0, player.oxygen - dt)
        if player.oxygen <= 0.0:
            player._drown_t += dt
            if player._drown_t >= DROWN_DAMAGE_INTERVAL:
                player._drown_t = 0.0
                dmg = max(1, 2 - defense // 4)
                player.hp = max(0, player.hp - dmg)
    else:
        player.oxygen = min(MAX_OXYGEN, player.oxygen + dt * 3.0)
        player._drown_t = 0.0

    # Sprint: Shift held + moving on ground + enough hunger
    shift_held = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
    moving_h   = _k(pygame.K_a, pygame.K_LEFT) or _k(pygame.K_d, pygame.K_RIGHT)
    player.is_sprinting = (
        shift_held and moving_h and not player.in_water
        and not player.in_lava and player.hunger > 3.0
    )

    # Hunger drain
    drain = HUNGER_DRAIN_RATE * (SPRINT_HUNGER_MULT if player.is_sprinting else 1.0)
    player.hunger = max(0.0, player.hunger - drain * dt)

    # Starvation / regen HP (shared timer to avoid tick conflicts)
    if player.hunger <= 0.0:
        player._hunger_t += dt
        if player._hunger_t >= HUNGER_DMG_INTERVAL:
            player._hunger_t = 0.0
            player.hp = max(0, player.hp - 1)
    elif player.hunger >= 18.0 and player.hp < player.max_hp:
        player._hunger_t += dt
        if player._hunger_t >= HUNGER_REGEN_INTERVAL:
            player._hunger_t = 0.0
            player.hp = min(player.max_hp, player.hp + 1)
    else:
        player._hunger_t = 0.0

    # Soul sand slowness
    foot_tx = int((player.x + PLAYER_W / 2) // TILE_SIZE)
    foot_ty = int((player.y + PLAYER_H - 2) // TILE_SIZE)
    on_soul_sand = world.get(foot_tx, foot_ty) == "soul_sand"

    # Horizontal movement
    if player.in_lava:
        speed = LAVA_SPEED
    elif player.in_water:
        speed = SWIM_SPEED
    elif player.is_sprinting and not on_soul_sand:
        speed = SPRINT_SPEED
    elif on_soul_sand:
        speed = MOVE_SPEED * 0.4
    else:
        speed = MOVE_SPEED
    player.vx = 0.0
    if _k(pygame.K_a, pygame.K_LEFT):
        player.vx = -speed
        player.facing = -1
    if _k(pygame.K_d, pygame.K_RIGHT):
        player.vx = speed
        player.facing = 1

    if player.vx != 0 and player.on_ground:
        player.walk_frame += 0.28 if player.is_sprinting else 0.18
    elif player.vx == 0:
        player.walk_frame = round(player.walk_frame / math.pi) * math.pi

    if player.in_lava:
        # Lava: very viscous — slow buoyancy, sluggish upward push
        if _k(pygame.K_w, pygame.K_SPACE, pygame.K_UP):
            player.vy = max(player.vy + LAVA_UP_VEL * dt * FPS * 0.25, LAVA_UP_VEL)
            player.just_jumped = True
        player.vy *= 0.75
        player.vy = min(player.vy + LAVA_GRAV, MAX_FALL * 0.15)
    elif player.in_water:
        # Water: W/Space push upward; natural buoyancy slows fall
        if _k(pygame.K_w, pygame.K_SPACE, pygame.K_UP):
            player.vy = max(player.vy + SWIM_UP_VEL * dt * FPS * 0.35, SWIM_UP_VEL)
            player.just_jumped = True
        # Drag: dampen vertical velocity
        player.vy *= 0.82
        player.vy = min(player.vy + WATER_GRAV, MAX_FALL * 0.3)
    else:
        if player.on_ground and _k(pygame.K_w, pygame.K_SPACE, pygame.K_UP):
            player.vy = JUMP_VEL
            player.on_ground  = False
            player.just_jumped = True

        # Zero downward velocity when standing on ground to prevent shaking
        if player.on_ground and player.vy > 0:
            player.vy = 0.0

        player.vy = min(player.vy + GRAVITY, MAX_FALL)

    player.x += player.vx
    _collide_x(player, world)

    player.on_ground = False
    player.y += player.vy
    _collide_y(player, world)

    player.x = max(0.0, min(player.x, world.width  * TILE_SIZE - PLAYER_W))
    player.y = max(0.0, min(player.y, world.height * TILE_SIZE - PLAYER_H))


def _collide_x(player: Player, world: World):
    r  = player.rect
    TS = TILE_SIZE
    ty0 = r.top    // TS
    ty1 = (r.bottom - 1) // TS
    for ty in range(ty0, ty1 + 1):
        if player.vx > 0:
            tx = r.right // TS
            if world.is_solid(tx, ty):
                tile_r = pygame.Rect(tx * TS, ty * TS, TS, TS)
                if r.colliderect(tile_r):
                    player.x = tx * TS - PLAYER_W - EPS
                    player.vx = 0.0
                    r = player.rect
        elif player.vx < 0:
            tx = (r.left - 1) // TS
            if world.is_solid(tx, ty):
                tile_r = pygame.Rect(tx * TS, ty * TS, TS, TS)
                if r.colliderect(tile_r):
                    player.x = (tx + 1) * TS + EPS
                    player.vx = 0.0
                    r = player.rect


def _collide_y(player: Player, world: World):
    r  = player.rect
    TS = TILE_SIZE
    tx0 = r.left  // TS
    tx1 = (r.right - 1) // TS
    for tx in range(tx0, tx1 + 1):
        if player.vy > 0:
            ty = r.bottom // TS
            if world.is_solid(tx, ty):
                # Use horizontal-only check: vertical overlap guaranteed by ty = r.bottom // TS.
                # Snap to exact integer (no EPS offset) so r.bottom == ty*TS every frame,
                # which retriggers this check and prevents the 2-pixel jitter cycle.
                if r.right > tx * TS and r.left < (tx + 1) * TS:
                    player.y = float(ty * TS - PLAYER_H)
                    player.vy = 0.0
                    player.on_ground = True
                    r = player.rect
        elif player.vy < 0:
            ty = (r.top - 1) // TS
            if world.is_solid(tx, ty):
                tile_r = pygame.Rect(tx * TS, ty * TS, TS, TS)
                if r.colliderect(tile_r):
                    player.y = (ty + 1) * TS + EPS
                    player.vy = 0.0
                    r = player.rect


# ── Mining / placing ──────────────────────────────────────────────────────────

def try_mine(player: Player, world: World,
             mouse_screen: Tuple[int, int], camera: Camera,
             held_item: Optional[ItemStack],
             layer: str = "fg",
             extra_speed: float = 1.0,
             ) -> Tuple[Optional[ItemStack], Optional[str]]:
    wx, wy = camera.screen_to_world(*mouse_screen)
    tx, ty = int(wx // TILE_SIZE), int(wy // TILE_SIZE)

    pcx, pcy = player.center
    tile_cx  = tx * TILE_SIZE + TILE_SIZE / 2
    tile_cy  = ty * TILE_SIZE + TILE_SIZE / 2
    dist = math.hypot(tile_cx - pcx, tile_cy - pcy)
    if dist > MINE_REACH * TILE_SIZE:
        _reset_mining(player)
        return None, None, 0

    if layer == "bg":
        # Background layer: only mine if foreground is empty at this cell
        if world.get(tx, ty) is not None:
            _reset_mining(player)
            return None, None, 0
        tile = world.get_bg(tx, ty)
        if tile is None or tile == "bedrock":
            _reset_mining(player)
            return None, None, 0
        data = TILE_DATA.get(tile)
        if data is None or data[2] < 0:
            _reset_mining(player)
            return None, None, 0
        speed_mult = _tool_speed(held_item, tile) * extra_speed
        if speed_mult <= 0.0:
            _reset_mining(player)
            return None, "cant_mine", 0
        if player.mining_target != (tx, ty):
            player.mining_target   = (tx, ty)
            player.mining_progress = 0.0
        hardness     = max(0.05, data[2])
        old_progress = player.mining_progress
        player.mining_progress += speed_mult / (hardness * FPS)
        if player.mining_progress >= 1.0:
            drop_id = data[1]
            world.set_bg(tx, ty, None)
            _reset_mining(player)
            return (ItemStack(drop_id, 1) if drop_id else None), "break_block", 0
        sound_event = None
        if int(player.mining_progress * 4) > int(old_progress * 4):
            sound_event = TILE_SOUND.get(tile, "dig_stone")
        return None, sound_event, 0

    tile = world.get(tx, ty)
    if tile is None:
        _reset_mining(player)
        return None, None, 0

    # Fluids cannot be broken
    if tile in ("water", "lava"):
        _reset_mining(player)
        return None, None, 0

    data = TILE_DATA.get(tile)
    if data is None or data[2] < 0:
        _reset_mining(player)
        return None, None, 0

    speed_mult = _tool_speed(held_item, tile) * extra_speed
    if speed_mult <= 0.0:
        _reset_mining(player)
        return None, "cant_mine", 0

    if player.mining_target != (tx, ty):
        player.mining_target   = (tx, ty)
        player.mining_progress = 0.0

    hardness     = max(0.05, data[2])
    old_progress = player.mining_progress
    player.mining_progress += speed_mult / (hardness * FPS)

    if player.mining_progress >= 1.0:
        drop_id = data[1]
        if tile == "gravel" and random.random() < 0.12:
            drop_id = "flint"
        if tile == "oak_leaves" and random.random() < 0.06:
            drop_id = "apple"
        world.set(tx, ty, None)
        # Cactus: cascade-break all cactus blocks above
        if tile == "cactus":
            cy = ty - 1
            while cy >= 0 and world.get(tx, cy) == "cactus":
                world.set(tx, cy, None)
                cy -= 1
        _reset_mining(player)
        drop = ItemStack(drop_id, 1) if drop_id else None
        xp_gain = _ORE_XP.get(tile, 0)
        return drop, "break_block", xp_gain

    sound_event = None
    if int(player.mining_progress * 4) > int(old_progress * 4):
        sound_event = TILE_SOUND.get(tile, "dig_stone")

    return None, sound_event, 0


# Item ID → placed tile ID (for items that place a different tile name)
_ITEM_TO_TILE: Dict[str, str] = {
    "lever":                    "lever_off",
    "stone_button":             "stone_button_off",
    "wooden_button":            "wooden_button_off",
    "pressure_plate":           "pressure_plate_off",
    "wooden_pressure_plate":    "wooden_pressure_plate_off",
    "redstone_torch":           "redstone_torch_on",
}


def try_place(player: Player, world: World,
              mouse_screen: Tuple[int, int], camera: Camera,
              item: Optional[ItemStack],
              layer: str = "fg") -> bool:
    tile_to_place = _ITEM_TO_TILE.get(item.item_id if item else "", "") or (item.item_id if item else "")
    if item is None or item.is_empty() or tile_to_place not in TILE_DATA:
        return False

    wx, wy = camera.screen_to_world(*mouse_screen)
    tx, ty = int(wx // TILE_SIZE), int(wy // TILE_SIZE)

    pcx, pcy = player.center
    dist = math.hypot(tx * TILE_SIZE + TILE_SIZE/2 - pcx,
                      ty * TILE_SIZE + TILE_SIZE/2 - pcy)
    if dist > MINE_REACH * TILE_SIZE:
        return False

    if layer == "bg":
        # Background: only place if foreground is empty here
        if world.get(tx, ty) is not None:
            return False
        if world.get_bg(tx, ty) is not None:
            return False
        world.set_bg(tx, ty, tile_to_place)
        item.count -= 1
        return True

    if world.get(tx, ty) is not None:
        return False

    # Door needs an empty block above it
    if item.item_id == "oak_door" and world.get(tx, ty - 1) is not None:
        return False

    tile_rect = pygame.Rect(tx * TILE_SIZE, ty * TILE_SIZE, TILE_SIZE, TILE_SIZE)
    if tile_rect.colliderect(player.rect):
        return False

    world.set(tx, ty, tile_to_place)
    item.count -= 1
    return True


def hover_tile(camera: Camera, mouse_screen: Tuple[int, int]) -> Tuple[int, int]:
    wx, wy = camera.screen_to_world(*mouse_screen)
    return int(wx // TILE_SIZE), int(wy // TILE_SIZE)


def draw_tile_cursor(screen: pygame.Surface, camera: Camera,
                     tx: int, ty: int, player: Player,
                     mining_progress: float = 0.0,
                     active_layer: str = "fg",
                     world: Optional["World"] = None):
    pcx, pcy = player.center
    dist = math.hypot(tx * TILE_SIZE + TILE_SIZE/2 - pcx,
                      ty * TILE_SIZE + TILE_SIZE/2 - pcy)
    if dist > MINE_REACH * TILE_SIZE:
        return

    if world is not None:
        if active_layer == "fg":
            tile = world.get(tx, ty)
            if tile is None or tile == "water":
                return
            color = (255, 255, 255)
        else:
            if world.get(tx, ty) is not None:
                return
            if world.get_bg(tx, ty) is None:
                return
            color = (255, 215, 0)  # gold for bg layer
    else:
        color = (255, 255, 255)

    sx = tx * TILE_SIZE - int(camera.x)
    sy = ty * TILE_SIZE - int(camera.y)
    pygame.draw.rect(screen, color, (sx, sy, TILE_SIZE, TILE_SIZE), 2)


# ── Day / night lighting ──────────────────────────────────────────────────────

_glow_cache: Dict[tuple, pygame.Surface] = {}


def _make_glow(radius: int, tint_r: int, tint_g: int, tint_b: int) -> pygame.Surface:
    """Generate a radial glow surface (black bg → tinted center)."""
    key = (radius, tint_r, tint_g, tint_b)
    if key in _glow_cache:
        return _glow_cache[key]
    size = radius * 2 + 2
    surf = pygame.Surface((size, size))
    surf.fill((0, 0, 0))
    cx = cy = radius + 1
    for r in range(radius, 0, -1):
        frac = (radius - r) / radius
        bright = int(255 * frac ** 0.55)
        cr = min(255, bright * tint_r // 255)
        cg = min(255, bright * tint_g // 255)
        cb = min(255, bright * tint_b // 255)
        pygame.draw.circle(surf, (cr, cg, cb), (cx, cy), r)
    _glow_cache[key] = surf
    return surf


def draw_lighting_overlay(screen: pygame.Surface, day_time: float,
                          underground_frac: float,
                          torch_positions: List[Tuple[int, int]],
                          glowstone_positions: List[Tuple[int, int]],
                          player_sx: int, player_sy: int,
                          lava_positions: Optional[List[Tuple[int, int]]] = None) -> None:
    """Apply darkness + light sources via BLEND_RGB_MULT.

    underground_frac: 0.0 = fully on surface, 1.0 = deep underground.
    day_time: in-game clock (only affects surface darkness level).
    Glowstone tiles emit a warm yellow glow; lava tiles emit wide orange glow.
    """
    t_angle = 2.0 * math.pi * day_time / DAY_CYCLE_LEN
    night_frac = max(0.0, -math.sin(t_angle))  # 0 at noon, 1 at midnight

    # Underground is always dark regardless of time
    surface_dark    = int(night_frac * 195)
    underground_dark = int(underground_frac * 220)
    base_dark = max(surface_dark, underground_dark)

    if base_dark < 4:
        return

    sw, sh = screen.get_size()
    ambient = max(22, 255 - base_dark)
    # Deeper underground: slight purple tint
    ug = underground_frac * 0.14
    amb_r = min(255, int(ambient * (0.79 - ug)))
    amb_g = min(255, int(ambient * (0.85 - ug * 0.5)))
    amb_b = min(255, int(ambient * 1.00))

    light_map = pygame.Surface((sw, sh))
    light_map.fill((amb_r, amb_g, amb_b))

    # Torch: warm orange, radius grows with darkness
    t_r = min(148, 80 + int(base_dark * 0.30))
    glow_t = _make_glow(t_r, 255, 185, 75)
    for (sx, sy) in torch_positions:
        cx = sx + TILE_SIZE // 2 - t_r - 1
        cy = sy + TILE_SIZE // 2 - t_r - 1
        light_map.blit(glow_t, (cx, cy), special_flags=pygame.BLEND_RGB_ADD)

    # Glowstone: warm yellow glow
    g_r = min(96, 48 + int(base_dark * 0.18))
    glow_g = _make_glow(g_r, 255, 230, 110)
    for (sx, sy) in glowstone_positions:
        cx = sx + TILE_SIZE // 2 - g_r - 1
        cy = sy + TILE_SIZE // 2 - g_r - 1
        light_map.blit(glow_g, (cx, cy), special_flags=pygame.BLEND_RGB_ADD)

    # Lava: wide orange glow (like a large torch)
    if lava_positions:
        lv_r = min(80, 40 + int(base_dark * 0.16))
        glow_lv = _make_glow(lv_r, 255, 120, 30)
        for (sx, sy) in lava_positions:
            cx = sx + TILE_SIZE // 2 - lv_r - 1
            cy = sy + TILE_SIZE // 2 - lv_r - 1
            light_map.blit(glow_lv, (cx, cy), special_flags=pygame.BLEND_RGB_ADD)

    # Player ambient light
    p_r = min(88, 44 + int(base_dark * 0.18))
    glow_p = _make_glow(p_r, 210, 220, 255)
    px = player_sx + PLAYER_W // 2 - p_r - 1
    py = player_sy + PLAYER_H // 2 - p_r - 1
    light_map.blit(glow_p, (px, py), special_flags=pygame.BLEND_RGB_ADD)

    screen.blit(light_map, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


def draw_night_overlay(screen, day_time, torch_positions, player_sx, player_sy):
    """Backward-compat shim."""
    draw_lighting_overlay(screen, day_time, 0.0, torch_positions, [], player_sx, player_sy)


def find_spawn(world: World) -> Tuple[float, float]:
    cx = world.width // 2
    for y in range(world.height):
        if world.get(cx, y) is not None and world.get(cx, y) != "water":
            px = cx * TILE_SIZE + TILE_SIZE // 2 - PLAYER_W // 2
            py = y * TILE_SIZE - PLAYER_H - 1
            return float(px), float(py)
    return float(cx * TILE_SIZE), 0.0


# ── Drawing helpers ───────────────────────────────────────────────────────────

_sky_surf: Optional[pygame.Surface] = None


def _draw_sky(screen: pygame.Surface):
    global _sky_surf
    sw, sh = screen.get_size()
    if _sky_surf is None or _sky_surf.get_size() != (sw, sh):
        _sky_surf = pygame.Surface((sw, sh))
        for y in range(sh):
            t = y / sh
            r = int(SKY_TOP[0] * (1-t) + SKY_BOT[0] * t)
            g = int(SKY_TOP[1] * (1-t) + SKY_BOT[1] * t)
            b = int(SKY_TOP[2] * (1-t) + SKY_BOT[2] * t)
            pygame.draw.line(_sky_surf, (r, g, b), (0, y), (sw - 1, y))
    screen.blit(_sky_surf, (0, 0))


_nether_sky_surf: Optional[pygame.Surface] = None
_end_sky_surf:    Optional[pygame.Surface] = None


def _draw_end_sky(screen: pygame.Surface):
    global _end_sky_surf
    sw, sh = screen.get_size()
    if _end_sky_surf is None or _end_sky_surf.get_size() != (sw, sh):
        _end_sky_surf = pygame.Surface((sw, sh))
        for y in range(sh):
            t = y / sh
            r = int(5  * (1-t) + 2  * t)
            g = int(3  * (1-t) + 1  * t)
            b = int(12 * (1-t) + 5  * t)
            pygame.draw.line(_end_sky_surf, (r, g, b), (0, y), (sw - 1, y))
        # Stars
        import random as _r
        rng = _r.Random(777)
        for _ in range(200):
            sx2 = rng.randint(0, sw - 1)
            sy2 = rng.randint(0, sh - 1)
            br  = rng.randint(60, 180)
            _end_sky_surf.set_at((sx2, sy2), (br, br, br + 40))
    screen.blit(_end_sky_surf, (0, 0))


def _draw_nether_sky(screen: pygame.Surface):
    global _nether_sky_surf
    sw, sh = screen.get_size()
    if _nether_sky_surf is None or _nether_sky_surf.get_size() != (sw, sh):
        _nether_sky_surf = pygame.Surface((sw, sh))
        for y in range(sh):
            t = y / sh
            r = int(30 * (1-t) + 8 * t)
            g = int(6  * (1-t) + 2 * t)
            b = int(4  * (1-t) + 1 * t)
            pygame.draw.line(_nether_sky_surf, (r, g, b), (0, y), (sw - 1, y))
    screen.blit(_nether_sky_surf, (0, 0))


_SKIN   = (237, 197, 140)
_SKIN2  = (200, 160, 105)   # shadow skin
_HAIR   = ( 80,  50,  20)
_HAIR2  = (105,  70,  30)   # hair highlight
_SHIRT  = ( 60, 110, 200)
_SHIRT2 = ( 45,  85, 165)   # shirt shadow
_PANTS  = ( 55,  70, 160)
_PANTS2 = ( 38,  50, 115)   # pants shadow
_EYE    = ( 50,  55, 200)
_OUT    = ( 22,  14,   8)
_BOOT   = ( 42,  30,  18)

# ── Minecraft skin sheet UV (in 64×64 space; scaled by skin resolution) ──────

class SkinParts:
    """Pre-extracted + scaled surfaces from a Minecraft player skin sheet.

    Supports both 64×64 (standard) and 128×128 (Faithful 2× pack) skin files.
    """

    # Minecraft UV regions in 64×64 coordinate space
    _UV = {
        "head": (8,  8,  8, 8),
        "hat":  (40, 8,  8, 8),   # hat/hair overlay layer
        "body": (20, 20, 8, 12),
        "r_arm":(44, 20, 4, 12),  # wide-format right arm front
        "l_arm":(36, 52, 4, 12),  # wide-format left arm front
        "r_leg":(4,  20, 4, 12),
        "l_leg":(20, 52, 4, 12),
    }

    def __init__(self, path: str):
        raw = pygame.image.load(path).convert_alpha()
        sc  = raw.get_width() // 64   # 1 for 64px skin, 2 for 128px Faithful

        def _crop(key):
            u, v, w, h = self._UV[key]
            return raw.subsurface(pygame.Rect(u * sc, v * sc, w * sc, h * sc))

        HEAD_W, HEAD_H = 22, 22
        BODY_W, BODY_H = 16, 10
        ARM_W,  ARM_H  =  5, 15
        LEG_W,  LEG_H  =  8, 20

        head_base = pygame.transform.scale(_crop("head"), (HEAD_W, HEAD_H))
        hat_layer = pygame.transform.scale(_crop("hat"),  (HEAD_W, HEAD_H))
        # Composite hat onto head (the hat layer uses alpha for empty areas)
        head_comp = head_base.copy()
        head_comp.blit(hat_layer, (0, 0))
        self.head = head_comp

        self.body = pygame.transform.scale(_crop("body"), (BODY_W, BODY_H))

        # Store raw crops for per-frame dynamic scaling (animation squishes limbs)
        self._r_arm_raw = _crop("r_arm")
        self._l_arm_raw = _crop("l_arm")
        self._r_leg_raw = _crop("r_leg")
        self._l_leg_raw = _crop("l_leg")
        self.arm_w, self.arm_h = ARM_W, ARM_H
        self.leg_w, self.leg_h = LEG_W, LEG_H

        # Face preview (8×8 head face → 48×48) for skin select UI
        self.preview = pygame.transform.scale(_crop("head"), (48, 48))

    def arm_surf(self, is_front: bool, animated_h: int,
                 flip: bool = False) -> pygame.Surface:
        raw = self._l_arm_raw if is_front else self._r_arm_raw
        s = pygame.transform.scale(raw, (self.arm_w, max(2, animated_h)))
        return pygame.transform.flip(s, flip, False) if flip else s

    def leg_surf(self, is_right: bool, animated_h: int,
                 flip: bool = False) -> pygame.Surface:
        raw = self._r_leg_raw if is_right else self._l_leg_raw
        s = pygame.transform.scale(raw, (self.leg_w, max(2, animated_h)))
        return pygame.transform.flip(s, flip, False) if flip else s


def _draw_limb(screen: pygame.Surface,
               x: int, y: int, w: int, h: int, off: int,
               col_hi: tuple, col_lo: tuple) -> None:
    """Limb with swing offset and two-tone shading."""
    yy = y + max(0, off)
    hh = max(2, h - abs(off))
    split = hh * 2 // 3
    pygame.draw.rect(screen, col_hi, (x, yy,        w, split))
    pygame.draw.rect(screen, col_lo, (x, yy + split, w, hh - split))
    pygame.draw.rect(screen, _OUT,   (x, yy,        w, hh), 1)


def draw_player(screen: pygame.Surface, player: Player, camera: Camera,
                held_item=None, off_hand=None,
                skin: "Optional[SkinParts]" = None,
                attack_swing: float = 0.0, armor: "Optional[list]" = None):
    sx, sy = camera.world_to_screen(player.x, player.y)
    W = PLAYER_W   # 26 px hitbox width

    # ── Proportions ───────────────────────────────────────────────────────
    head_w = 22;  head_h = 22
    body_w = 16;  body_h = 10
    leg_w  =  8;  leg_h  = 20
    arm_w  =  5;  arm_h  = 15

    hx = sx + (W - head_w) // 2
    hy = sy
    bx = sx + (W - body_w) // 2
    by = hy + head_h

    gap    = 2
    ll_x   = sx + (W - leg_w * 2 - gap) // 2
    rl_x   = ll_x + leg_w + gap
    leg_y  = by + body_h

    la_x   = bx - arm_w - 1
    ra_x   = bx + body_w + 1
    arm_y  = by + 1

    # Sprint leans the whole upper body forward
    lean = int(player.facing * (2 if player.is_sprinting else 0))

    # Walk swing — arms/legs alternate
    sw     = math.sin(player.walk_frame) * 6.0
    ll_off = int( sw);  rl_off = int(-sw)
    la_off = int(-sw);  ra_off = int( sw)

    # ── Determine which side is "back" (rendered first) ────────────────
    f = player.facing  # 1 = right, -1 = left
    back_leg_x  = ll_x if f > 0 else rl_x
    front_leg_x = rl_x if f > 0 else ll_x
    back_leg_o  = ll_off if f > 0 else rl_off
    front_leg_o = rl_off if f > 0 else ll_off
    back_arm_x  = la_x if f > 0 else ra_x
    front_arm_x = ra_x if f > 0 else la_x
    back_arm_o  = la_off if f > 0 else ra_off
    front_arm_o = ra_off if f > 0 else la_off

    flip_h = (f < 0)  # flip textures when facing left

    # ── Draw order: back-leg → back-arm → body → front-leg → front-arm → head
    if skin:
        bk_leg_h = max(2, leg_h - abs(back_leg_o))
        bk_leg_y = leg_y + max(0, back_leg_o)
        screen.blit(skin.leg_surf(False, bk_leg_h, flip_h), (back_leg_x + lean, bk_leg_y))
    else:
        _draw_limb(screen, back_leg_x + lean, leg_y, leg_w, leg_h, back_leg_o,
                   _PANTS2, _BOOT)
        bl_yy = leg_y + leg_h + min(0, back_leg_o) - 4
        pygame.draw.rect(screen, _BOOT, (back_leg_x + lean, bl_yy, leg_w, 4))

    if skin:
        bk_arm_h = max(2, arm_h - abs(back_arm_o))
        bk_arm_y = arm_y + max(0, back_arm_o)
        screen.blit(skin.arm_surf(False, bk_arm_h, flip_h), (back_arm_x + lean, bk_arm_y))
    else:
        _draw_limb(screen, back_arm_x + lean, arm_y, arm_w, arm_h, back_arm_o,
                   _SHIRT2, _SKIN2)

    # Body
    if skin:
        body_surf = pygame.transform.flip(skin.body, flip_h, False) if flip_h else skin.body
        screen.blit(body_surf, (bx + lean, by))
    else:
        pygame.draw.rect(screen, _SHIRT,  (bx + lean, by, body_w, body_h))
        pygame.draw.rect(screen, _SHIRT2, (bx + lean + body_w // 2, by, body_w // 2, body_h))
        pygame.draw.rect(screen, _OUT,    (bx + lean, by, body_w, body_h), 1)
        seam_x = bx + lean + body_w // 2
        pygame.draw.line(screen, _SHIRT2, (seam_x, by + 2), (seam_x, by + body_h - 2), 1)

    # Front leg
    if skin:
        fr_leg_h = max(2, leg_h - abs(front_leg_o))
        fr_leg_y = leg_y + max(0, front_leg_o)
        screen.blit(skin.leg_surf(True, fr_leg_h, flip_h), (front_leg_x + lean, fr_leg_y))
    else:
        _draw_limb(screen, front_leg_x + lean, leg_y, leg_w, leg_h, front_leg_o,
                   _PANTS, _BOOT)
        fl_yy = leg_y + leg_h + min(0, front_leg_o) - 4
        pygame.draw.rect(screen, _BOOT, (front_leg_x + lean, fl_yy, leg_w, 4))

    # Front arm — swings during attack or mining
    if attack_swing > 0.0:
        # Attack: fast full-arc swing (elbow forward + down, then snap back)
        phase = 1.0 - (attack_swing / 0.30)   # 0→1 as animation plays out
        arc   = math.sin(phase * math.pi)      # 0→peak→0
        mx    = int(player.facing * arc * 14)
        my    = int(arc * 11)
    elif player.mining_target:
        swing = math.sin(player.mining_progress * math.pi)   # 0→1→0 arc
        mx = int(player.facing * swing * 9)   # push arm forward
        my = int(swing * 8)                   # push arm down
    else:
        mx = my = 0

    fa_x = front_arm_x + lean + mx
    fa_o = int(front_arm_o) + my

    if skin:
        fr_arm_h = max(2, arm_h - abs(fa_o))
        fr_arm_y = arm_y + max(0, fa_o)
        screen.blit(skin.arm_surf(True, fr_arm_h, flip_h), (fa_x, fr_arm_y))
    else:
        _draw_limb(screen, fa_x, arm_y, arm_w, arm_h, fa_o, _SHIRT, _SKIN)

    # Held item in front hand — 1.5× size (32 px)
    from assets import get_item_texture
    item_size = 32
    if held_item and not held_item.is_empty():
        tip_x = fa_x + arm_w // 2 + player.facing * (arm_w // 2 + 3)
        tip_y = arm_y + arm_h + fa_o - item_size // 2
        tex = get_item_texture(held_item.item_id, item_size)
        screen.blit(tex, (tip_x - item_size // 2, tip_y))

    # Off-hand item on the back arm (smaller: 22 px)
    if off_hand and not off_hand.is_empty():
        off_size = 22
        ba_x = back_arm_x + lean
        ba_o = int(back_arm_o)
        ba_tip_x = ba_x + arm_w // 2 - player.facing * (arm_w // 2 + 3)
        ba_tip_y = arm_y + arm_h + ba_o - off_size // 2
        off_tex = get_item_texture(off_hand.item_id, off_size)
        screen.blit(off_tex, (ba_tip_x - off_size // 2, ba_tip_y))

    # Head
    if skin:
        head_surf = pygame.transform.flip(skin.head, flip_h, False) if flip_h else skin.head
        screen.blit(head_surf, (hx + lean, hy))
    else:
        pygame.draw.rect(screen, _SKIN,  (hx + lean, hy, head_w, head_h))
        shade_x = (hx + lean + head_w * 3 // 4) if f > 0 else (hx + lean)
        pygame.draw.rect(screen, _SKIN2, (shade_x, hy, head_w // 4, head_h))
        pygame.draw.rect(screen, _OUT,   (hx + lean, hy, head_w, head_h), 1)
        pygame.draw.rect(screen, _HAIR,  (hx + lean, hy, head_w, 8))
        pygame.draw.rect(screen, _HAIR,  (hx + lean, hy, 3, head_h))
        pygame.draw.rect(screen, _HAIR,  (hx + lean + head_w - 3, hy, 3, head_h))
        pygame.draw.rect(screen, _HAIR2, (hx + lean, hy, head_w, 4))
        ey = hy + head_h // 3 + 1
        if f > 0:
            ex = hx + lean + head_w * 3 // 4 - 1
            pygame.draw.rect(screen, (240, 228, 208), (ex,     ey,     6, 5))
            pygame.draw.rect(screen, _EYE,             (ex + 1, ey + 1, 4, 4))
            pygame.draw.rect(screen, _OUT,             (ex + 3, ey + 1, 2, 2))
        else:
            ex = hx + lean + head_w // 4 - 3
            pygame.draw.rect(screen, (240, 228, 208), (ex,     ey,     6, 5))
            pygame.draw.rect(screen, _EYE,             (ex + 1, ey + 1, 4, 4))
            pygame.draw.rect(screen, _OUT,             (ex + 1, ey + 1, 2, 2))
        mouth_x = hx + lean + (head_w * 3 // 4 - 3 if f > 0 else head_w // 4 - 1)
        pygame.draw.rect(screen, (155, 95, 75), (mouth_x, hy + head_h * 2 // 3, 5, 2))
        pygame.draw.rect(screen, _OUT, (mouth_x, hy + head_h * 2 // 3, 5, 2), 1)

    # ── Armor overlays ────────────────────────────────────────────────────
    if armor:
        def _armor_color(item_id: str) -> Optional[tuple]:
            """Return (fill, border) color pair for a piece of armor."""
            _COLORS = {
                "leather":  ((139, 90,  43,  140), (100, 60, 20)),
                "iron":     ((192, 192, 192, 150), (120, 120, 140)),
                "gold":     ((255, 215,  0,  150), (200, 165, 0)),
                "diamond":  ((0,   206, 209, 150), (0, 150, 160)),
                "steel":    ((100, 140, 180, 150), (70, 100, 140)),
                "bronze":   ((176, 125,  62, 150), (130, 90, 40)),
                "emerald":  ((80,  200,  90, 150), (40, 150, 60)),
                "netherite":((80,   70,  80, 150), (50, 45, 55)),
            }
            if item_id is None:
                return None
            for mat, cols in _COLORS.items():
                if mat in item_id:
                    return cols
            return None

        def _alpha_rect(surf, col_alpha, rect):
            if len(col_alpha) == 4:
                ov = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
                ov.fill(col_alpha)
                surf.blit(ov, (rect[0], rect[1]))
            else:
                pygame.draw.rect(surf, col_alpha, rect)

        # armor = [helmet, chestplate, leggings, boots]
        helmet, chest, legs, boots = (
            armor[i] if i < len(armor) else None for i in range(4))

        # Boots (full boot with toe cap)
        if boots and not boots.is_empty():
            ac = _armor_color(boots.item_id)
            if ac:
                bh = 6
                boot_y = leg_y + leg_h - bh
                for bx2 in (ll_x, rl_x):
                    _alpha_rect(screen, ac[0], (bx2 + lean, boot_y, leg_w, bh))
                    pygame.draw.rect(screen, ac[1], (bx2 + lean, boot_y, leg_w, bh), 1)
                    # toe cap highlight
                    pygame.draw.line(screen, ac[1],
                                     (bx2 + lean + 1, boot_y + 1),
                                     (bx2 + lean + leg_w - 2, boot_y + 1), 1)

        # Leggings (2 separate leg panels with a seam line)
        if legs and not legs.is_empty():
            ac = _armor_color(legs.item_id)
            if ac:
                lh2 = leg_h * 3 // 4
                for lx2 in (ll_x, rl_x):
                    _alpha_rect(screen, ac[0], (lx2 + lean, leg_y, leg_w, lh2))
                    pygame.draw.rect(screen, ac[1], (lx2 + lean, leg_y, leg_w, lh2), 1)
                    # horizontal knee line
                    ky = leg_y + lh2 // 2
                    pygame.draw.line(screen, ac[1],
                                     (lx2 + lean + 1, ky), (lx2 + lean + leg_w - 2, ky), 1)
                # crotch plate connecting both legs
                _alpha_rect(screen, ac[0],
                            (ll_x + lean, leg_y, rl_x - ll_x + leg_w, 5))
                pygame.draw.rect(screen, ac[1],
                                 (ll_x + lean, leg_y, rl_x - ll_x + leg_w, 5), 1)

        # Chestplate (body + wide pauldrons)
        if chest and not chest.is_empty():
            ac = _armor_color(chest.item_id)
            if ac:
                # Main torso plate
                _alpha_rect(screen, ac[0], (bx + lean - 1, by, body_w + 2, body_h))
                pygame.draw.rect(screen, ac[1], (bx + lean - 1, by, body_w + 2, body_h), 1)
                # Vertical ridge down the center
                mx = bx + lean + body_w // 2 - 1
                pygame.draw.line(screen, ac[1],
                                 (mx, by + 2), (mx, by + body_h - 2), 1)
                # Pauldrons — wider shoulder guards
                for ax2 in (la_x - 1, ra_x):
                    _alpha_rect(screen, ac[0], (ax2 + lean, arm_y, arm_w + 2, arm_h // 2 + 2))
                    pygame.draw.rect(screen, ac[1], (ax2 + lean, arm_y, arm_w + 2, arm_h // 2 + 2), 1)
                # Rivet dots on chest
                for rx2, ry2 in ((bx + lean + 2, by + 2), (bx + lean + body_w - 3, by + 2),
                                 (bx + lean + 2, by + body_h - 4), (bx + lean + body_w - 3, by + body_h - 4)):
                    pygame.draw.circle(screen, ac[1], (rx2, ry2), 1)

        # Helmet — brow band + side guards + nasal, face mostly open
        if helmet and not helmet.is_empty():
            ac = _armor_color(helmet.item_id)
            if ac:
                hm_x = hx + lean
                hm_y = hy
                bw   = head_h * 5 // 22   # brow band height (~5px for 22px head)
                bw   = max(4, bw)

                # Cap on top of head — extends 1px each side and 2px above
                _alpha_rect(screen, ac[0], (hm_x - 1, hm_y - 2, head_w + 2, bw + 2))
                pygame.draw.rect(screen, ac[1], (hm_x - 1, hm_y - 2, head_w + 2, bw + 2), 1)

                # Side cheek guards — full height of head, 3px wide
                side_w = 3
                side_h = head_h
                for sx2 in (hm_x - side_w, hm_x + head_w):
                    _alpha_rect(screen, ac[0], (sx2, hm_y, side_w, side_h))
                    pygame.draw.rect(screen, ac[1], (sx2, hm_y, side_w, side_h), 1)

                # Nasal guard — narrow strip from brow cap down to midface
                nasal_w = 2
                nasal_h = head_h * 9 // 16
                nasal_x = hm_x + (head_w - nasal_w) // 2
                nasal_y = hm_y + bw
                _alpha_rect(screen, ac[0], (nasal_x, nasal_y, nasal_w, nasal_h))
                pygame.draw.rect(screen, ac[1], (nasal_x, nasal_y, nasal_w, nasal_h), 1)

                # Decorative rivets on the cap
                for riv_x in (hm_x + 3, hm_x + head_w - 4):
                    pygame.draw.circle(screen, ac[1], (riv_x, hm_y + bw // 2), 1)

    # Mining progress bar
    if player.mining_target and player.mining_progress > 0:
        bar_y = sy + PLAYER_H + 4
        bar_w = PLAYER_W
        pygame.draw.rect(screen, (60, 60, 60), (sx, bar_y, bar_w, 4))
        pygame.draw.rect(screen, (255, 140, 0),
                         (sx, bar_y, int(bar_w * player.mining_progress), 4))


def draw_hp_bar(screen: pygame.Surface, player: Player, defense: int = 0):
    x, y = 10, 10
    for i in range(player.max_hp // 2):
        filled = i < player.hp // 2
        col = (200, 30, 30) if filled else (80, 30, 30)
        pygame.draw.rect(screen, col, (x + i * 18, y, 14, 14))
        pygame.draw.rect(screen, (255, 100, 100), (x + i * 18, y, 14, 14), 1)

    # Armor shield icons — one per 2 defense points
    if defense > 0:
        ay = y + 18
        shields = min(defense // 2, 10)
        for i in range(shields):
            pts = [
                (x + i * 18 + 7, ay),
                (x + i * 18 + 14, ay + 4),
                (x + i * 18 + 14, ay + 10),
                (x + i * 18 + 7, ay + 14),
                (x + i * 18,     ay + 10),
                (x + i * 18,     ay + 4),
            ]
            pygame.draw.polygon(screen, (60, 100, 200), pts)
            pygame.draw.polygon(screen, (140, 180, 255), pts, 1)
        ay += 18
    else:
        ay = y + 18

    # Oxygen bubbles — shown only when not at full oxygen
    if player.oxygen < MAX_OXYGEN - 0.1:
        bubbles = int(MAX_OXYGEN)
        filled_b = int(player.oxygen)
        for i in range(bubbles):
            bx = x + i * 18
            if i < filled_b:
                pygame.draw.circle(screen, (80, 160, 255), (bx + 7, ay + 7), 6)
                pygame.draw.circle(screen, (180, 220, 255), (bx + 7, ay + 7), 6, 1)
            else:
                pygame.draw.circle(screen, (30, 60, 100), (bx + 7, ay + 7), 6)
                pygame.draw.circle(screen, (60, 100, 150), (bx + 7, ay + 7), 6, 1)


def draw_hunger_bar(screen: pygame.Surface, player: Player):
    """Draw 10 drumstick icons (right-aligned) representing hunger 0-20."""
    sw = screen.get_width()
    x0 = sw - 184   # 10 icons × 18 px = 180 + 4 margin
    y  = 10
    for i in range(10):
        bx        = x0 + i * 18
        threshold = (i + 1) * 2
        filled    = player.hunger >= threshold
        half      = not filled and player.hunger >= threshold - 1
        col  = (200, 140, 40) if filled else (110, 75, 25) if half else (60, 40, 14)
        dark = (100,  65, 18) if filled else ( 55, 35, 10) if half else (32, 20,  7)
        # Drum head
        pygame.draw.circle(screen, col,  (bx + 9, y + 7), 6)
        pygame.draw.circle(screen, dark, (bx + 9, y + 7), 6, 1)
        # Handle
        pygame.draw.rect(screen, col,  (bx + 7, y + 12, 3, 5))
        pygame.draw.rect(screen, dark, (bx + 7, y + 12, 3, 5), 1)


_xp_font: Optional[pygame.font.Font] = None

def draw_xp_bar(screen: pygame.Surface, player: Player):
    """Green XP bar under HP area + level number."""
    global _xp_font
    if _xp_font is None:
        _xp_font = pygame.font.SysFont(None, 18)
    bar_w = 180
    bar_h = 8
    x, y  = 10, 56  # below HP icons row
    # shift down if armor shields are showing
    if player.hp < player.max_hp or True:   # always consistent position
        pass
    pygame.draw.rect(screen, (20, 50, 20), (x, y, bar_w, bar_h))
    fill_w = int(bar_w * player.xp_progress())
    if fill_w > 0:
        pygame.draw.rect(screen, (60, 200, 60), (x, y, fill_w, bar_h))
    pygame.draw.rect(screen, (40, 120, 40), (x, y, bar_w, bar_h), 1)
    lbl = _xp_font.render(f"LVL {player.level}", True, (100, 240, 100))
    screen.blit(lbl, (x + bar_w + 6, y - 1))


# ── Private helpers ───────────────────────────────────────────────────────────

def _reset_mining(player: Player):
    player.mining_target   = None
    player.mining_progress = 0.0


_TIER_LEVEL: Dict[str, int] = {
    "tier_wood": 1, "tier_stone": 2, "tier_copper": 2, "tier_bronze": 2,
    "tier_iron": 3, "tier_steel": 3, "tier_gold":  1,
    "tier_diamond": 4, "tier_netherite": 5,
}
_TIER_MULT: Dict[str, float] = {
    "tier_wood": 1.5, "tier_stone": 2.0, "tier_copper": 2.5, "tier_bronze": 2.5,
    "tier_iron": 3.0, "tier_steel": 3.5, "tier_gold":  4.0,
    "tier_diamond": 6.0, "tier_netherite": 8.0,
}

_STONE_TILES = frozenset({
    "stone", "cobblestone", "coal_ore", "iron_ore",
    "copper_ore", "gold_ore", "diamond_ore", "bedrock",
    "granite", "andesite", "diorite", "mossy_cobblestone",
    "obsidian", "sandstone", "ice", "glass", "furnace",
})
_WOOD_TILES  = frozenset({"oak_log", "oak_planks", "workbench",
                           "chest", "barrel", "oak_door", "oak_door_open",
                           "gunsmith_table"})
_EARTH_TILES = frozenset({"dirt", "sand", "gravel", "clay", "snow", "sponge"})


def _tool_speed(item: Optional[ItemStack], tile: str) -> float:
    min_tier = TILE_MIN_TIER.get(tile, 0)

    if item is None:
        return 0.0 if min_tier > 0 else 1.0
    it = item.item
    if it is None:
        return 0.0 if min_tier > 0 else 1.0

    tags = it.tags

    tool_level = 0
    tool_mult  = 1.0
    for tier, lvl in _TIER_LEVEL.items():
        if tier in tags and lvl > tool_level:
            tool_level = lvl
            tool_mult  = _TIER_MULT[tier]

    def _check(tool_tag: str, default_mult: float = 1.5) -> float:
        if tool_tag not in tags:
            return 0.0 if min_tier > 0 else 1.0
        if tool_level < min_tier:
            return 0.0
        return max(tool_mult, default_mult)

    if tile in _STONE_TILES:
        return _check("pickaxe", 1.5)
    if tile in _WOOD_TILES:
        return _check("axe", 1.5)
    if tile in _EARTH_TILES:
        return _check("shovel", 1.5) if "shovel" in tags else 1.0

    return 1.0
