"""
Crafting workbench — shaped + unordered recipe engine + UI.

Shaped recipes: items placed in a specific pattern (bounding-box match).
Unordered recipes: any arrangement, exact total counts (smelting, alloys, firearms).

UI layout (full overlay while open):
  3×3 craft grid | → | output slot
  ─────── Инвентарь ────────────────
  grid 3×9 rows
  hotbar row
"""
from __future__ import annotations
import logging, random, pygame
from typing import Optional, List, Dict, Set

import keys as _keys

_log = logging.getLogger("minacraft")
from items import ItemStack, ItemDef, ITEMS, TIERS, register_discovered
from assets import get_item_texture
from inventory import Inventory, SLOT_SIZE, SLOT_STEP, HOTBAR_N, GRID_N, GRID_ROWS, TOTAL_N
import sounds


# ── Recipe discovery tracking ─────────────────────────────────────────────────

_discovered: Set[str] = set()

def mark_discovered(result_id: str):
    _discovered.add(result_id)

def get_discovered() -> Set[str]:
    return _discovered

def set_discovered(ids):
    global _discovered
    _discovered = set(ids)


# ── Recipe tables ─────────────────────────────────────────────────────────────

_TOOL_MATS = [
    ("oak_planks",   "wooden"),
    ("cobblestone",  "stone"),
    ("iron_ingot",   "iron"),
    ("gold_ingot",   "golden"),
    ("diamond",      "diamond"),
    ("copper_ingot", "copper"),
    ("bronze_ingot", "bronze"),
    ("steel_ingot",  "steel"),
]

_ARMOR_MATS = [
    ("leather",      "leather"),
    ("iron_ingot",   "iron"),
    ("gold_ingot",   "golden"),
    ("diamond",      "diamond"),
    ("copper_ingot", "copper"),
    ("bronze_ingot", "bronze"),
    ("steel_ingot",  "steel"),
]


def _build_shaped() -> List[tuple]:
    """Generate all shaped (positional) recipes."""
    r: List[tuple] = []

    I = "iron_ingot"

    # ── Utility ───────────────────────────────────────────────────────────
    r += [
        # Log → 4 planks (any single oak log)
        ([["oak_log"]], "oak_planks", 4),
        # 2 planks in a column → 4 sticks  (matches any plank via "plank" tag)
        ([["plank"], ["plank"]], "stick", 4),
        # Torches
        ([["coal"],     ["stick"]], "torch", 4),
        ([["charcoal"], ["stick"]], "torch", 4),
        # Flint and steel — both orientations
        ([["flint", "iron_ingot"]], "flint_and_steel", 1),
        ([["iron_ingot", "flint"]], "flint_and_steel", 1),
        ([["flint"], ["iron_ingot"]], "flint_and_steel", 1),
        ([["iron_ingot"], ["flint"]], "flint_and_steel", 1),
        # TNT — 5× gunpowder + 4× sand, checkerboard
        ([["gunpowder", "sand",      "gunpowder"],
          ["sand",      "gunpowder", "sand"     ],
          ["gunpowder", "sand",      "gunpowder"]], "tnt", 1),
        # Anvil — 8× iron_ingot
        ([[I,    I,    I   ],
          [None, I,    None],
          [I,    I,    I   ]], "anvil", 1),
        # Gunsmith table — workbench + anvil + 7× iron_ingot
        ([[I,       I,           I   ],
          [I,       "workbench", I   ],
          ["anvil", I,           "anvil"]], "gunsmith_table", 1),
        # Arrow: flint → stick → feather (column)
        ([["flint"], ["stick"], ["feather"]], "arrow", 4),
        # Bow — left and right orientations
        ([[None, "stick", "string"], ["stick", None, "string"], [None, "stick", "string"]], "bow", 1),
        ([["string", "stick", None], ["string", None, "stick"], ["string", "stick", None]], "bow", 1),
        # Crafting blocks
        ([["plank", "plank"], ["plank", "plank"]], "workbench", 1),
        ([["stone", "stone", "stone"], ["stone", None, "stone"], ["stone", "stone", "stone"]], "furnace", 1),
        ([["plank", "plank", "plank"], ["plank", None, "plank"], ["plank", "plank", "plank"]], "chest", 1),
        ([["plank", "stick", "plank"], ["plank", None, "plank"], ["plank", "stick", "plank"]], "barrel", 1),
        ([["plank", "plank"], ["plank", "plank"], ["plank", "plank"]], "oak_door", 3),
        ([["sand"]], "glass", 1),
        # Enchanting table: diamond+book+diamond / obsidian×4 bottom row
        ([["diamond", "book",   "diamond"],
          ["obsidian", "obsidian", "obsidian"]], "enchanting_table", 1),
        # Brewing stand: blaze_rod center + cobblestone row
        ([[None, "blaze_rod", None],
          ["cobblestone", "cobblestone", "cobblestone"]], "brewing_stand", 1),
        # Glass bottle (V shape)
        ([[None, "glass", None],
          ["glass", None, "glass"]], "glass_bottle", 3),
        # Glistering melon: gold nuggets around apple
        ([["gold_nugget", "gold_nugget", "gold_nugget"],
          ["gold_nugget", "apple",       "gold_nugget"],
          ["gold_nugget", "gold_nugget", "gold_nugget"]], "glistering_melon_slice", 1),
        # Magma cream: blaze_powder + magma_block (both orientations)
        ([[None, "blaze_powder", None],
          [None, "magma_block",  None]], "magma_cream", 2),
        ([[None, "magma_block",  None],
          [None, "blaze_powder", None]], "magma_cream", 2),
        # Fermented spider eye
        ([[None, "sugar",      None],
          [None, "spider_eye", None]], "fermented_spider_eye", 1),
        ([[None, "spider_eye", None],
          [None, "sugar",      None]], "fermented_spider_eye", 1),
        # Golden carrot: gold nuggets around golden_apple
        ([["gold_nugget", "gold_nugget", "gold_nugget"],
          ["gold_nugget", "golden_apple","gold_nugget"],
          ["gold_nugget", "gold_nugget", "gold_nugget"]], "golden_carrot", 4),
        # ── Redstone ─────────────────────────────────────────────────────────
        # Redstone torch: redstone + stick (column)
        ([["redstone"], ["stick"]], "redstone_torch", 1),
        ([["stick"], ["redstone"]], "redstone_torch", 1),
        # Lever: stick on cobblestone
        ([["stick"], ["cobblestone"]], "lever", 1),
        # Stone button: single cobblestone (compact)
        ([["cobblestone"]], "stone_button", 1),
        # Wooden button: single plank
        ([["plank"]], "wooden_button", 1),
        # Pressure plate: 2 stone side by side
        ([["cobblestone", "cobblestone"]], "pressure_plate", 1),
        # Wooden pressure plate: 2 planks side by side
        ([["plank", "plank"]], "wooden_pressure_plate", 1),
        # Netherite ingot: 4 nether_scrap + 4 gold_ingot
        ([["nether_scrap", "nether_scrap", "gold_ingot"],
          ["nether_scrap", "nether_scrap", "gold_ingot"],
          ["gold_ingot",   "gold_ingot",   None]], "netherite_ingot", 1),
    ]

    # ── Tools per material ────────────────────────────────────────────────
    for mat, pfx in _TOOL_MATS:
        M, S = mat, "stick"
        # Pickaxe: T-shape top row
        r.append(([[M, M, M], [None, S, None], [None, S, None]], f"{pfx}_pickaxe", 1))
        # Sword: 1-wide column (M, M, S)
        r.append(([[M], [M], [S]], f"{pfx}_sword", 1))
        # Shovel: 1-wide column (M, S, S)
        r.append(([[M], [S], [S]], f"{pfx}_shovel", 1))
        # Axe — both left/right mirror
        r.append(([[M, M], [M, S], [None, S]], f"{pfx}_axe", 1))
        r.append(([[M, M], [S, M], [S, None]], f"{pfx}_axe", 1))
        # Hoe — both left/right mirror
        r.append(([[M, M], [None, S], [None, S]], f"{pfx}_hoe", 1))
        r.append(([[M, M], [S, None], [S, None]], f"{pfx}_hoe", 1))

    # ── Armor per material ────────────────────────────────────────────────
    for mat, pfx in _ARMOR_MATS:
        M = mat
        # Helmet:     M M M / M . M
        r.append(([[M, M, M], [M, None, M]], f"{pfx}_helmet", 1))
        # Chestplate: M . M / M M M / M M M
        r.append(([[M, None, M], [M, M, M], [M, M, M]], f"{pfx}_chestplate", 1))
        # Leggings:   M M M / M . M / M . M
        r.append(([[M, M, M], [M, None, M], [M, None, M]], f"{pfx}_leggings", 1))
        # Boots:      M . M / M . M
        r.append(([[M, None, M], [M, None, M]], f"{pfx}_boots", 1))

    # Keep only recipes whose result item actually exists
    return [(pat, rid, cnt) for pat, rid, cnt in r if rid in ITEMS]


_SHAPED: List[tuple] = _build_shaped()

# Unordered: just check total counts, position doesn't matter.
# Place items one per slot so _consume_inputs works correctly.
_UNORDERED: List[tuple] = [
    # Smelting (raw ore + fuel → ingot×2)
    ({"raw_iron":   1, "coal":     1}, "iron_ingot",   2),
    ({"raw_iron":   1, "charcoal": 1}, "iron_ingot",   2),
    ({"raw_copper": 1, "coal":     1}, "copper_ingot", 2),
    ({"raw_copper": 1, "charcoal": 1}, "copper_ingot", 2),
    ({"raw_gold":   1, "coal":     1}, "gold_ingot",   2),
    ({"raw_gold":   1, "charcoal": 1}, "gold_ingot",   2),
    # Cooking (raw food + fuel → cooked)
    ({"beef":    1, "coal":     1}, "cooked_beef", 1),
    ({"beef":    1, "charcoal": 1}, "cooked_beef", 1),
    # Alloys
    ({"copper_ingot": 2, "iron_ingot": 1}, "bronze_ingot", 2),
    ({"iron_ingot":   2, "coal":       1}, "steel_ingot",  1),
    # Boss summon items
    ({"amethyst_shard": 2, "emerald": 1},  "earth_rune",    1),
    # End items
    ({"ender_pearl": 1, "blaze_powder": 1}, "eye_of_ender", 1),
    # Decompose ingot → nuggets
    ({"iron_ingot": 1},                                   "iron_nugget",     9),
    # Ammo (crafted at workbench)
    ({"iron_nugget": 1, "gunpowder": 1},                  "bullet",          4),
    ({"iron_ingot": 1, "gunpowder": 1},                   "rifle_ammo",      6),
    ({"iron_ingot": 1, "gunpowder": 2},                   "shotgun_shell",   4),
    ({"iron_ingot": 1, "coal": 1, "gunpowder": 1},        "napalm_canister", 3),
]


# ── Gunsmith table recipes (5×5 grid) ────────────────────────────────────────

def _build_gunsmith_shaped() -> List[tuple]:
    I, G, S, C = "iron_ingot", "gunpowder", "stick", "copper_ingot"
    Au, St, T  = "gold_ingot", "steel_ingot", "tnt"
    D          = "diamond"
    r: List[tuple] = [
        # Glock — compact pistol (3×3)
        ([[I,    I,    None],
          [G,    I,    None],
          [None, I,    None]], "glock",       1),
        # Deagle (4 rows × 3 cols)
        ([[I,    I,    None],
          [None, G,    I   ],
          [None, I,    I   ],
          [None, None, I   ]], "deagle",      1),
        # Gold Deagle
        ([[Au,   Au,   None],
          [None, G,    Au  ],
          [None, Au,   Au  ],
          [None, None, Au  ]], "gold_deagle", 1),
        # Revolver (4×3)
        ([[I,    I,    I   ],
          [I,    G,    None],
          [None, I,    None],
          [None, I,    None]], "revolver",    1),
        # Uzi (3×3)
        ([[I,    I,    None],
          [I,    G,    G   ],
          [None, I,    None]], "uzi",         1),
        # MP5 (3×3)
        ([[I,    I,    S   ],
          [I,    G,    None],
          [I,    None, None]], "mp5",         1),
        # AK-47 (3×4)
        ([[I,    None, I,    None],
          [I,    G,    G,    I   ],
          [I,    I,    None, None]], "ak47",  1),
        # Sniper rifle (3×5)
        ([[I, I, I, I, I],
          [I, G, S, I, None],
          [None, I, None, None, None]], "sniper_rifle", 1),
        # M249 SAW (4×4)
        ([[I,    None, I,    I   ],
          [I,    G,    G,    G   ],
          [I,    I,    I,    None],
          [None, I,    S,    None]], "m249_saw",     1),
        # Flamethrower (3×4)
        ([[I,    I,    C,    I   ],
          [I,    G,    G,    None],
          [I,    None, I,    None]], "flamethrower", 1),
        # RPG-7 (3×4)
        ([[I,    I,    I,    None],
          [S,    G,    I,    I   ],
          [None, G,    I,    None]], "rpg",          1),
        # Minigun — needs steel (4×4)
        ([[St,   I,    I,    None],
          [St,   G,    G,    I   ],
          [St,   I,    I,    None],
          [None, I,    I,    None]], "minigun",         1),
        # Gold Minigun (4×4)
        ([[Au,   Au,   Au,   None],
          [Au,   G,    G,    Au  ],
          [Au,   Au,   Au,   None],
          [None, Au,   Au,   None]], "gold_minigun",    1),
        # Diamond Minigun (4×4)
        ([[D,    D,    D,    None],
          [D,    G,    G,    D   ],
          [D,    D,    D,    None],
          [None, D,    D,    None]], "diamond_minigun", 1),
        # Rocket for RPG — uses TNT (3×2)
        ([[I,    T   ],
          [G,    T   ],
          [I,    None]], "rocket",           2),
        # Shotgun (3×3)
        ([[I,    I   ],
          [G,    None],
          [I,    S   ]], "shotgun",          1),
    ]
    return [(p, rid, cnt) for p, rid, cnt in r if rid in ITEMS]


_GUNSMITH_SHAPED: List[tuple] = _build_gunsmith_shaped()

_GUNSMITH_UNORDERED: List[tuple] = [
    # Extra ammo recipes
    ({"iron_ingot": 2, "gunpowder": 3},    "rocket",           1),
]

# Minimum player level required to craft each firearm at the gunsmith table
_GUNSMITH_LEVEL_REQ: Dict[str, int] = {
    "glock":           2,
    "shotgun":         3,
    "revolver":        3,
    "deagle":          4,
    "uzi":             4,
    "mp5":             5,
    "ak47":            6,
    "gold_deagle":     7,
    "flamethrower":    7,
    "sniper_rifle":    8,
    "m249_saw":        9,
    "rpg":            11,
    "rocket":          5,
    "minigun":        13,
    "gold_minigun":   16,
    "diamond_minigun": 20,
}

# XP gained when crafting each firearm at the gunsmith table
_GUNSMITH_XP_REWARD: Dict[str, int] = {
    "glock":           20,
    "shotgun":         25,
    "revolver":        30,
    "deagle":          40,
    "uzi":             35,
    "mp5":             35,
    "ak47":            50,
    "gold_deagle":     65,
    "flamethrower":    55,
    "sniper_rifle":    60,
    "m249_saw":        70,
    "rpg":             80,
    "rocket":          10,
    "minigun":         90,
    "gold_minigun":   130,
    "diamond_minigun": 200,
}


def get_gunsmith_level_req(item_id: str) -> int:
    return _GUNSMITH_LEVEL_REQ.get(item_id, 1)


def determine_gunsmith_result(grid: List[Optional[ItemStack]], player_level: int = 99) -> Optional[ItemStack]:
    """Recipes for the 5×5 gunsmith table — shaped only (no mystery fallback).
    Returns None if the matched weapon requires a higher player level."""
    result = _match_shaped_grid(grid, 5, _GUNSMITH_SHAPED)
    if result is None:
        result = _match_unordered_table(grid, _GUNSMITH_UNORDERED)
    if result is not None:
        req = _GUNSMITH_LEVEL_REQ.get(result.item_id, 1)
        if player_level < req:
            return None  # locked — insufficient level
    return result


# ── Furnace smelting ──────────────────────────────────────────────────────────

_SMELT: Dict[str, tuple] = {
    "raw_iron":    ("iron_ingot",   2),
    "raw_copper":  ("copper_ingot", 2),
    "raw_gold":    ("gold_ingot",   2),
    "iron_ore":    ("iron_ingot",   1),
    "copper_ore":  ("copper_ingot", 1),
    "gold_ore":    ("gold_ingot",   1),
    "beef":        ("cooked_beef",  1),
    "cobblestone": ("stone",        1),
    "sand":        ("glass",        1),
}

_FUEL_ITEMS: frozenset = frozenset({
    "coal", "charcoal", "oak_log", "oak_planks", "stick", "blaze_rod", "torch",
})


def get_smelt_result(input_id: str) -> Optional[tuple]:
    """Return (result_id, count) or None for a furnace input item."""
    return _SMELT.get(input_id)


# ── Enchantment definitions ───────────────────────────────────────────────────

_ENCHANTS: Dict[str, Dict] = {
    "sharpness":      {"name": "Острота",         "max_lvl": 5,
                       "applicable": {"sword", "axe"},
                       "desc": "+0.5 урона/ур."},
    "efficiency":     {"name": "Эффективность",   "max_lvl": 5,
                       "applicable": {"pickaxe", "axe", "shovel"},
                       "desc": "+20% скор. добычи/ур."},
    "unbreaking":     {"name": "Неломкость",       "max_lvl": 3,
                       "applicable": None,
                       "desc": "~33%/ур. шанс сохр. прочность"},
    "protection":     {"name": "Защита",           "max_lvl": 4,
                       "applicable": {"armor"},
                       "desc": "+5% снижение урона/ур."},
    "fire_protection":{"name": "Огнезащита",       "max_lvl": 4,
                       "applicable": {"armor"},
                       "desc": "защита от огня и лавы"},
    "feather_falling":{"name": "Мягкое падение",   "max_lvl": 4,
                       "applicable": {"boots"},
                       "desc": "меньше урона от падения"},
    "fortune":        {"name": "Удача",             "max_lvl": 3,
                       "applicable": {"pickaxe"},
                       "desc": "доп. выпадение с руд"},
    "silk_touch":     {"name": "Шёлковое касание", "max_lvl": 1,
                       "applicable": {"pickaxe", "shovel"},
                       "desc": "блок выпадает целиком"},
    "looting":        {"name": "Добыча",            "max_lvl": 3,
                       "applicable": {"sword"},
                       "desc": "+шанс доп. дропа с моба"},
    "fire_aspect":    {"name": "Огненный аспект",  "max_lvl": 2,
                       "applicable": {"sword"},
                       "desc": "+урон от огня"},
    "knockback":      {"name": "Отбрасывание",     "max_lvl": 2,
                       "applicable": {"sword"},
                       "desc": "отталкивает врагов"},
    "mending":        {"name": "Починка",           "max_lvl": 1,
                       "applicable": None,
                       "desc": "XP восстанавливает прочность"},
    "thorns":         {"name": "Шипы",              "max_lvl": 3,
                       "applicable": {"chestplate"},
                       "desc": "отражает часть урона"},
    "respiration":    {"name": "Дыхание",           "max_lvl": 3,
                       "applicable": {"helmet"},
                       "desc": "+15 с запаса воздуха/ур."},
    "aqua_affinity":  {"name": "Водное сродство",  "max_lvl": 1,
                       "applicable": {"helmet"},
                       "desc": "нормальная добыча под водой"},
    "night_vision_ench": {"name": "Ночное зрение", "max_lvl": 1,
                       "applicable": {"helmet"},
                       "desc": "постоянная видимость в темноте"},
}

# ── Brewing recipes ───────────────────────────────────────────────────────────
# ingredient_id → {input_potion_id: result_potion_id}

_BREWING_RECIPES: Dict[str, Dict[str, str]] = {
    "nether_wart":             {"water_bottle":           "awkward_potion"},
    "sugar":                   {"awkward_potion":          "speed_potion"},
    "blaze_powder":            {"awkward_potion":          "strength_potion"},
    "ghast_tear":              {"awkward_potion":          "regen_potion"},
    "magma_cream":             {"awkward_potion":          "fire_resistance_potion"},
    "golden_carrot":           {"awkward_potion":          "night_vision_potion"},
    "glistering_melon_slice":  {"awkward_potion":          "healing_potion"},
    "spider_eye":              {"awkward_potion":          "poison_potion"},
    "fermented_spider_eye":    {
        "healing_potion":      "harming_potion",
        "poison_potion":       "harming_potion",
        "night_vision_potion": "harming_potion",
        "speed_potion":        "harming_potion",
    },
    "gunpowder":               {
        "poison_potion":       "splash_poison",
        "harming_potion":      "splash_harming",
        "strength_potion":     "splash_strength",
    },
}


# ── Mystery item fallback ─────────────────────────────────────────────────────

_TAG_ADJ: Dict[str, str] = {
    "iron": "Железный", "gold": "Золотой", "diamond": "Алмазный",
    "copper": "Медный", "stone": "Каменный", "wood": "Деревянный",
    "magic": "Зачарованный", "sharp": "Острый", "hard": "Прочный",
    "explosive": "Взрывной", "organic": "Костяной", "gem": "Драгоценный",
    "metal": "Металлический", "carbon": "Угольный", "earth": "Земляной",
    "fuel": "Пылающий", "flexible": "Гибкий", "light": "Светящийся",
}

_TAG_NOUN: Dict[str, str] = {
    "weapon": "клинок", "tool": "инструмент", "armor": "пластина",
    "magic": "кристалл", "explosive": "бомба", "organic": "амулет",
    "gem": "самоцвет", "food": "деликатес", "fuel": "горелка",
    "stone": "глыба", "metal": "слиток", "wood": "жезл",
    "light": "светильник", "binding": "путы", "material": "артефакт",
}

_TIER_PRIORITY = [
    "tier_netherite", "tier_diamond", "tier_gold",
    "tier_steel", "tier_iron", "tier_bronze", "tier_copper",
    "tier_stone", "tier_wood", "tier_leather",
]


def _get_best_tier(item_defs: List) -> str:
    all_tags: set = set()
    for d in item_defs:
        all_tags |= set(d.tags)
    for t in _TIER_PRIORITY:
        if t in all_tags:
            return t
    return "tier_wood"


def _pick_best(tc: Dict[str, int], lookup: Dict[str, str],
               exclude: frozenset = frozenset()) -> str:
    best, best_n = "material", 0
    for tag, n in tc.items():
        if tag in lookup and tag not in exclude and n > best_n:
            best, best_n = tag, n
    return best


def _mystery_item(counts: Dict[str, int], tc: Dict[str, int],
                  total: int) -> Optional[ItemStack]:
    mystery_id = ("mystery_" + "_".join(sorted(counts.keys())))[:60]

    if mystery_id in ITEMS:
        try:
            import image_gen
            ex = ITEMS[mystery_id]
            image_gen.start(mystery_id, ex.name, ex.tags)
        except Exception:
            pass
        return ItemStack(mystery_id, 1)

    adj_tag  = _pick_best(tc, _TAG_ADJ)
    noun_tag = _pick_best(tc, _TAG_NOUN, exclude=frozenset({adj_tag}))
    name     = f"{_TAG_ADJ.get(adj_tag, 'Неизвестный')} {_TAG_NOUN.get(noun_tag, 'артефакт')}"

    all_defs  = [ITEMS[iid] for iid in counts if iid in ITEMS]
    best_tier = _get_best_tier(all_defs)
    tex_item  = next((d for d in all_defs if best_tier in d.tags),
                     all_defs[0] if all_defs else None)
    texture   = tex_item.texture if tex_item else "item/diamond"

    tier_data = TIERS.get(best_tier, ("", "", 100, 1.0, 0))
    dur       = int(tier_data[2] * 0.6) or 50
    props: dict = {}
    if tc.get("weapon") or tc.get("sharp"):
        props["damage"]  = 3 + tier_data[4]
    if tc.get("armor") or tc.get("hard"):
        props["defense"] = max(1, int(tier_data[3]))
    if tc.get("fuel"):
        props["fuel_value"] = total * 10
    if tc.get("food") or tc.get("edible"):
        props["food_value"] = total * 2

    has_dur   = bool(props.get("damage") or props.get("defense"))
    max_stack = 1 if has_dur else 16
    combined  = frozenset(tc.keys()) | {"mystery"}

    item_def = ItemDef(
        id=mystery_id, name=name, texture=texture,
        tags=combined, max_stack=max_stack,
        max_durability=dur if has_dur else 0,
        properties=props,
    )
    register_discovered(item_def)

    try:
        import image_gen
        image_gen.start(mystery_id, name, combined)
    except Exception:
        pass

    return ItemStack(mystery_id, 1)


# ── Recipe engine ─────────────────────────────────────────────────────────────

def determine_result(grid: List[Optional[ItemStack]]) -> Optional[ItemStack]:
    """Shaped → unordered → mystery item fallback."""
    result = _match_shaped(grid)
    if result is not None:
        return result
    result = _match_unordered(grid)
    if result is not None:
        return result

    # Mystery item: generate from whatever was placed
    placed = [(i, s) for i, s in enumerate(grid) if s and not s.is_empty()]
    if not placed:
        return None
    counts: Dict[str, int] = {}
    for _, s in placed:
        counts[s.item_id] = counts.get(s.item_id, 0) + s.count
    all_defs = [ITEMS[iid] for iid in counts if iid in ITEMS]
    tc: Dict[str, int] = {}
    for d in all_defs:
        for t in d.tags:
            tc[t] = tc.get(t, 0) + 1
    total = sum(counts.values())
    return _mystery_item(counts, tc, total)


def _match_shaped_grid(grid: List[Optional[ItemStack]], width: int,
                       recipe_table: List[tuple]) -> Optional[ItemStack]:
    """Bounding-box shaped match for an arbitrary (width × height) grid.
    Both the player grid and the recipe pattern are trimmed to their
    bounding box before comparison, so trailing/leading None rows/cols
    in pattern definitions are ignored."""
    height = len(grid) // width
    g = [[None] * width for _ in range(height)]
    for i, s in enumerate(grid):
        if s and not s.is_empty():
            g[i // width][i % width] = s.item_id

    rows_used = [r for r in range(height) if any(g[r][c] is not None for c in range(width))]
    cols_used = [c for c in range(width)  if any(g[r][c] is not None for r in range(height))]
    if not rows_used or not cols_used:
        return None

    r0, r1 = min(rows_used), max(rows_used)
    c0, c1 = min(cols_used), max(cols_used)
    gh = r1 - r0 + 1
    gw = c1 - c0 + 1

    for pattern, result_id, result_count in recipe_table:
        ph = len(pattern)
        if ph == 0:
            continue
        # Compute bounding box of the pattern's non-None cells
        p_row_used = [r for r in range(ph)
                      if any(c < len(pattern[r]) and pattern[r][c] is not None
                             for c in range(max(len(row) for row in pattern)))]
        p_col_used = [c for r in range(ph) for c in range(len(pattern[r]))
                      if pattern[r][c] is not None]
        if not p_row_used or not p_col_used:
            continue
        pr0, pr1 = min(p_row_used), max(p_row_used)
        pc0, pc1 = min(p_col_used), max(p_col_used)
        pgh = pr1 - pr0 + 1
        pgw = pc1 - pc0 + 1
        if pgh != gh or pgw != gw:
            continue
        match = True
        for pr in range(pgh):
            for pc in range(pgw):
                gcell = g[r0 + pr][c0 + pc]
                prow  = pattern[pr0 + pr]
                pcell = prow[pc0 + pc] if pc0 + pc < len(prow) else None
                if not _cell_matches(gcell, pcell):
                    match = False
                    break
            if not match:
                break
        if match and result_id in ITEMS:
            return ItemStack(result_id, result_count)
    return None


def _match_unordered_table(grid: List[Optional[ItemStack]],
                           recipe_table: List[tuple]) -> Optional[ItemStack]:
    counts: Dict[str, int] = {}
    for s in grid:
        if s and not s.is_empty():
            counts[s.item_id] = counts.get(s.item_id, 0) + s.count
    if not counts:
        return None
    for required, result_id, count in recipe_table:
        if counts.keys() != required.keys():
            continue
        # Accept exact multiples: 3× ingredients → 3× output
        ratios = []
        ok = True
        for k, need in required.items():
            have = counts.get(k, 0)
            if need == 0 or have % need != 0:
                ok = False
                break
            ratios.append(have // need)
        if ok and ratios and len(set(ratios)) == 1 and result_id in ITEMS:
            return ItemStack(result_id, count * ratios[0])
    return None


def _match_shaped(grid: List[Optional[ItemStack]]) -> Optional[ItemStack]:
    return _match_shaped_grid(grid, 3, _SHAPED)


def _match_unordered(grid: List[Optional[ItemStack]]) -> Optional[ItemStack]:
    return _match_unordered_table(grid, _UNORDERED)


def _cell_matches(item_id: Optional[str], pattern_cell: Optional[str]) -> bool:
    if pattern_cell is None:
        return item_id is None
    if item_id is None:
        return False
    if item_id == pattern_cell:
        return True
    item = ITEMS.get(item_id)
    return item is not None and pattern_cell in item.tags


def describe_result(result: ItemStack) -> str:
    it = result.item
    if it is None:
        return ""
    if "mystery" in it.tags:
        tags = sorted(t for t in it.tags if t not in ("mystery", "material"))[:5]
        return "✦ Новый предмет!  " + ", ".join(tags)
    p = it.properties
    parts = []
    if p.get("damage"):     parts.append(f"Урон: {p['damage']}")
    if p.get("defense"):    parts.append(f"Защита: {p['defense']}")
    if p.get("food_value"): parts.append(f"Еда: +{p['food_value']}")
    if it.max_durability:   parts.append(f"Прочность: {it.max_durability}")
    return "  |  ".join(parts)


# ── Crafting UI ───────────────────────────────────────────────────────────────

_CS = 46   # craft slot size


class CraftingUI:
    """Full-screen crafting overlay: 3×3 grid + output + player inventory."""

    def __init__(self, sw: int, sh: int):
        self.grid:    List[Optional[ItemStack]] = [None] * 9
        self.result:  Optional[ItemStack] = None
        self.cursor:  Optional[ItemStack] = None
        self.is_open: bool = False
        self.sw = sw
        self.sh = sh

        self._craft_rects: List[pygame.Rect] = []
        self._output_rect: Optional[pygame.Rect] = None
        self._inv_rects:   List[pygame.Rect] = []
        self._hb_rects:    List[pygame.Rect] = []
        self._arrow_pos:   tuple = (0, 0)
        self._panel_rect:  pygame.Rect = pygame.Rect(0, 0, 10, 10)

        self._font_m: Optional[pygame.font.Font] = None
        self._font_s: Optional[pygame.font.Font] = None
        self._font_t: Optional[pygame.font.Font] = None
        self._panel_surf: Optional[pygame.Surface] = None

        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._panel_surf = None
        self._rebuild()

    def _rebuild(self):
        sw, sh, CS, SS = self.sw, self.sh, _CS, SLOT_STEP
        top_y = 55
        ox    = sw // 2 - (3 * CS + 54 + CS + 10) // 2

        self._craft_rects = [
            pygame.Rect(ox + (i % 3) * CS, top_y + (i // 3) * CS, CS-4, CS-4)
            for i in range(9)
        ]
        out_x = ox + 3*CS + 54
        out_y = top_y + CS
        self._output_rect = pygame.Rect(out_x, out_y, CS+8, CS+8)
        self._arrow_pos   = (ox + 3*CS + 22, top_y + CS + CS//2)

        inv_top = top_y + 3*CS + 24
        inv_ox  = sw // 2 - 9*SS // 2
        self._inv_rects = [
            pygame.Rect(inv_ox + (i%9)*SS, inv_top + (i//9)*SS, SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_top + GRID_ROWS * SS + 6
        self._hb_rects = [
            pygame.Rect(inv_ox + i*SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        pan_bot  = max(r.bottom for r in self._hb_rects) + 12
        pan_left = min(r.x for r in self._craft_rects) - 14
        self._panel_rect = pygame.Rect(pan_left, top_y - 28,
                                       sw - pan_left*2, pan_bot - top_y + 28 + 12)

    def _fonts(self):
        if self._font_m is None:
            self._font_m = pygame.font.SysFont(None, 22)
            self._font_s = pygame.font.SysFont(None, 18)
            self._font_t = pygame.font.SysFont(None, 14)

    # ── Open / close ──────────────────────────────────────────────────────

    def open(self):
        self.is_open = True

    def close(self, inv: Inventory):
        self.is_open = False
        for i in range(9):
            s = self.grid[i]
            if s and not s.is_empty():
                inv.add(s)
            self.grid[i] = None
        if self.cursor:
            inv.add(self.cursor)
            self.cursor = None
        self.result = None

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event, inv: Inventory) -> bool:
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_e, pygame.K_ESCAPE):
                self.close(inv)
                return True
            num = norm - pygame.K_1
            if 0 <= num <= 8:
                inv.selected = num
                return True
        if event.type == pygame.MOUSEWHEEL:
            inv.selected = (inv.selected - event.y) % HOTBAR_N
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            mods = pygame.key.get_mods()
            self._click(event.pos, event.button, bool(mods & pygame.KMOD_SHIFT), inv)
        return True

    def _click(self, pos, btn, shift, inv):
        # Output slot
        if self._output_rect and self._output_rect.collidepoint(pos):
            if self.result and not self.result.is_empty():
                if shift or self.cursor is None:
                    _log.info("КРАФТ: %s ×%d (верстак)",
                              self.result.item_id, self.result.count)
                    mark_discovered(self.result.item_id)
                    self._consume_inputs()
                    sounds.play("craft", 0.55)
                    if shift:
                        inv.add(self.result)
                    else:
                        self.cursor = self.result
                    self._update_result()
                elif (self.cursor.item_id == self.result.item_id
                      and self.cursor.can_merge(self.result)):
                    _log.info("КРАФТ: %s ×%d (верстак)",
                              self.result.item_id, self.result.count)
                    mark_discovered(self.result.item_id)
                    self._consume_inputs()
                    sounds.play("craft", 0.55)
                    self.cursor.count += min(
                        self.cursor.max_stack - self.cursor.count, self.result.count)
                    self._update_result()
            return

        # Craft grid
        for i, r in enumerate(self._craft_rects):
            if r.collidepoint(pos):
                if shift and btn == 1 and self.grid[i]:
                    inv.add(self.grid[i]); self.grid[i] = None
                elif btn == 1:  self._lmb(self.grid, i)
                elif btn == 3:  self._rmb(self.grid, i)
                self._update_result()
                return

        # Inventory grid + hotbar
        for i, r in enumerate(self._inv_rects):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if shift and btn == 1: self._shift_to_craft(idx, inv)
                elif btn == 1: self._lmb(inv.slots, idx)
                elif btn == 3: self._rmb(inv.slots, idx)
                return
        for i, r in enumerate(self._hb_rects):
            if r.collidepoint(pos):
                if shift and btn == 1: self._shift_to_craft(i, inv)
                elif btn == 1: self._lmb(inv.slots, i)
                elif btn == 3: self._rmb(inv.slots, i)
                return

        if self.cursor:
            inv.add(self.cursor); self.cursor = None

    def _lmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot; slots[i] = None
        else:
            if slot is None or slot.is_empty():
                slots[i] = self.cursor; self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                move = min(slot.max_stack - slot.count, self.cursor.count)
                slot.count += move; self.cursor.count -= move
                if self.cursor.count <= 0: self.cursor = None
            else:
                slots[i] = self.cursor
                self.cursor = slot if not slot.is_empty() else None

    def _rmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot.split_half()
                if slot.is_empty(): slots[i] = None
        else:
            if slot is None or slot.is_empty():
                slots[i] = ItemStack(self.cursor.item_id, 1, self.cursor.durability)
                self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                slot.count += 1; self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None

    def _shift_to_craft(self, idx, inv):
        s = inv.slots[idx]
        if not s or s.is_empty(): return
        for j in range(9):
            if self.grid[j] is None:
                self.grid[j] = s; inv.slots[idx] = None
                self._update_result(); return
        targets = range(HOTBAR_N, TOTAL_N) if idx < HOTBAR_N else range(HOTBAR_N)
        for i in targets:
            if inv.slots[i] is None:
                inv.slots[i] = s; inv.slots[idx] = None; return

    def _update_result(self):
        self.result = determine_result(self.grid)

    def _consume_inputs(self):
        for i in range(9):
            s = self.grid[i]
            if s and not s.is_empty():
                s.count -= 1
                if s.count <= 0: self.grid[i] = None

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: Inventory, mouse_pos: tuple):
        if not self.is_open:
            return
        self._fonts()
        sw, sh = screen.get_size()

        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 145))
        screen.blit(dim, (0, 0))

        pr = self._panel_rect
        if self._panel_surf is None or self._panel_surf.get_size() != (pr.w, pr.h):
            self._panel_surf = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
            self._panel_surf.fill((28, 22, 18, 235))
        screen.blit(self._panel_surf, pr.topleft)
        pygame.draw.rect(screen, (90, 75, 55), pr, 2)

        title = self._font_m.render("ВЕРСТАК", True, (220, 200, 140))
        screen.blit(title, (pr.x + 8, pr.y + 6))
        hint = self._font_s.render("[E/Esc]", True, (110, 100, 80))
        screen.blit(hint, (pr.right - hint.get_width() - 8, pr.y + 6))

        for i, rect in enumerate(self._craft_rects):
            self._draw_slot(screen, rect, self.grid[i], big=True)

        ax, ay = self._arrow_pos
        pygame.draw.polygon(screen, (180, 160, 80), [
            (ax-14, ay-9), (ax+8, ay), (ax-14, ay+9)
        ])

        r   = self._output_rect
        has = self.result and not self.result.is_empty()
        pygame.draw.rect(screen, (35, 30, 20), r)
        pygame.draw.rect(screen, (255,215,50) if has else (80,75,60), r, 2)
        if has:
            self._draw_item(screen, self.result, r.x+5, r.y+5, r.w-10)
            desc = describe_result(self.result)
            if desc:
                ds = self._font_s.render(desc, True, (170, 165, 130))
                screen.blit(ds, (r.x, r.bottom + 4))

        sep_y = self._inv_rects[0].y - 14
        lbl   = self._font_s.render("── Инвентарь ──", True, (100, 90, 70))
        screen.blit(lbl, (sw//2 - lbl.get_width()//2, sep_y))

        for i, rect in enumerate(self._inv_rects):
            self._draw_slot(screen, rect, inv.slots[HOTBAR_N + i])
        for i, rect in enumerate(self._hb_rects):
            self._draw_slot(screen, rect, inv.slots[i], selected=(i == inv.selected))

        if self.cursor and not self.cursor.is_empty():
            sz = SLOT_SIZE - 8
            self._draw_item(screen, self.cursor,
                            mouse_pos[0]-sz//2, mouse_pos[1]-sz//2, sz)

        self._draw_tooltip(screen, mouse_pos, inv)

    def _draw_slot(self, screen, rect, stack, selected=False, big=False):
        bg  = (72,60,44) if selected else (42,38,32)
        bdr = (255,215,50) if selected else (72,65,52)
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, bdr, rect, 2 if selected else 1)
        if stack and not stack.is_empty():
            pad  = 6 if big else 4
            self._draw_item(screen, stack, rect.x+pad, rect.y+pad, rect.w-pad*2)

    def _draw_item(self, screen, stack, x, y, size):
        tex = get_item_texture(stack.item_id, size)
        screen.blit(tex, (x, y))
        if stack.count > 1:
            num = str(stack.count)
            s   = self._font_t.render(num, True, (0,0,0))
            t   = self._font_t.render(num, True, (255,255,255))
            nx, ny = x+size-t.get_width()+1, y+size-t.get_height()+1
            screen.blit(s, (nx+1, ny+1)); screen.blit(t, (nx, ny))
        it = stack.item
        if it and it.max_durability > 0 and stack.durability < it.max_durability:
            ratio = max(0.0, stack.durability / it.max_durability)
            col   = (70,210,40) if ratio>0.6 else (220,200,30) if ratio>0.3 else (210,50,30)
            by    = y + size + 1
            pygame.draw.rect(screen, (20,12,12), (x, by, size, 2))
            pygame.draw.rect(screen, col, (x, by, max(1,int(size*ratio)), 2))

    def _draw_tooltip(self, screen, mouse_pos, inv):
        stack: Optional[ItemStack] = None
        for i, r in enumerate(self._craft_rects):
            if r.collidepoint(mouse_pos): stack = self.grid[i]; break
        if stack is None and self._output_rect and self._output_rect.collidepoint(mouse_pos):
            stack = self.result
        if stack is None:
            for i, r in enumerate(self._inv_rects):
                if r.collidepoint(mouse_pos): stack = inv.slots[HOTBAR_N+i]; break
        if stack is None:
            for i, r in enumerate(self._hb_rects):
                if r.collidepoint(mouse_pos): stack = inv.slots[i]; break
        if not stack or stack.is_empty(): return
        it = stack.item
        if it is None: return
        lines = [it.name]
        p = it.properties
        if it.max_durability > 0:
            lines.append(f"Прочность: {stack.durability}/{it.max_durability}")
        if p.get("damage"):     lines.append(f"Урон: {p['damage']}")
        if p.get("defense"):    lines.append(f"Защита: {p['defense']}")
        if p.get("food_value"): lines.append(f"Еда: +{p['food_value']}")
        surfs  = [self._font_s.render(l, True, (255,240,180)) for l in lines]
        surfs[0] = self._font_s.render(lines[0], True, (255,255,100))
        tw = max(s.get_width() for s in surfs) + 14
        th = sum(s.get_height()+2 for s in surfs) + 8
        tx = min(mouse_pos[0]+16, self.sw - tw - 4)
        ty = max(mouse_pos[1]-th-6, 4)
        bg = pygame.Surface((tw, th), pygame.SRCALPHA)
        bg.fill((12, 8, 6, 215))
        screen.blit(bg, (tx, ty))
        pygame.draw.rect(screen, (110,90,50), (tx, ty, tw, th), 1)
        cy = ty + 5
        for surf in surfs:
            screen.blit(surf, (tx+7, cy)); cy += surf.get_height() + 2


# ── Recipe helpers ────────────────────────────────────────────────────────────

def get_recipe_info(result_id: str) -> Optional[dict]:
    """Return recipe data for a result item, or None if not found.
    Checks workbench recipes first, then gunsmith."""
    for pat, rid, cnt in _SHAPED:
        if rid == result_id:
            return {"type": "shaped", "pattern": pat, "count": cnt,
                    "table": "workbench"}
    for req, rid, cnt in _UNORDERED:
        if rid == result_id:
            return {"type": "unordered", "ingredients": req, "count": cnt,
                    "table": "workbench"}
    for pat, rid, cnt in _GUNSMITH_SHAPED:
        if rid == result_id:
            return {"type": "shaped", "pattern": pat, "count": cnt,
                    "table": "gunsmith",
                    "level_req": _GUNSMITH_LEVEL_REQ.get(rid, 1),
                    "xp_reward": _GUNSMITH_XP_REWARD.get(rid, 0)}
    for req, rid, cnt in _GUNSMITH_UNORDERED:
        if rid == result_id:
            return {"type": "unordered", "ingredients": req, "count": cnt,
                    "table": "gunsmith",
                    "level_req": _GUNSMITH_LEVEL_REQ.get(rid, 1),
                    "xp_reward": _GUNSMITH_XP_REWARD.get(rid, 0)}
    return None


def get_weapon_recipe_ids() -> List[str]:
    """Workbench weapon recipes (no level gating — bow/arrow etc.)."""
    seen: set = set()
    result: List[str] = []
    for pat, rid, cnt in _SHAPED:
        if rid in ITEMS and "weapon" in ITEMS[rid].tags and rid not in seen:
            seen.add(rid); result.append(rid)
    for req, rid, cnt in _UNORDERED:
        if rid in ITEMS and "weapon" in ITEMS[rid].tags and rid not in seen:
            seen.add(rid); result.append(rid)
    return result


def get_gunsmith_recipe_ids(player_level: int = 1) -> List[str]:
    """Gunsmith firearm recipes visible to the player (level-gated)."""
    seen: set = set()
    result: List[str] = []
    for pat, rid, cnt in _GUNSMITH_SHAPED:
        req = _GUNSMITH_LEVEL_REQ.get(rid, 1)
        if rid in ITEMS and rid not in seen and player_level >= req:
            seen.add(rid); result.append(rid)
    for req_dict, rid, cnt in _GUNSMITH_UNORDERED:
        req = _GUNSMITH_LEVEL_REQ.get(rid, 1)
        if rid in ITEMS and rid not in seen and player_level >= req:
            seen.add(rid); result.append(rid)
    return result


# ── Recipe Book ───────────────────────────────────────────────────────────────

class RecipeBook:
    """Split-panel recipe browser: left = item list, right = pattern detail."""

    ICON   = 40
    PAD    = 10
    TAB_H  = 26
    SLOT   = 44   # grid slot size in detail panel

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open    = False
        self._tab       = 0       # 0 = Оружие, 1 = Открытые
        self._scroll    = 0
        self._selected  = -1      # index into current tab's list
        self._list_rects: List[Optional[pygame.Rect]] = []
        self._tab_rects:  List[pygame.Rect] = []
        self._panel:  pygame.Rect = pygame.Rect(0, 0, 10, 10)
        self._list_r: pygame.Rect = pygame.Rect(0, 0, 10, 10)
        self._detail_r: pygame.Rect = pygame.Rect(0, 0, 10, 10)
        self._font_m: Optional[pygame.font.Font] = None
        self._font_s: Optional[pygame.font.Font] = None
        self._font_t: Optional[pygame.font.Font] = None
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        pw = min(self.sw - 40, 720)
        ph = min(self.sh - 60, 500)
        px = (self.sw - pw) // 2
        py = (self.sh - ph) // 2
        self._panel   = pygame.Rect(px, py, pw, ph)
        lw = 190
        self._list_r  = pygame.Rect(px + self.PAD, py + 30 + self.TAB_H + self.PAD,
                                    lw, ph - 30 - self.TAB_H - self.PAD * 2)
        self._detail_r = pygame.Rect(px + lw + self.PAD * 2, py + 30 + self.TAB_H,
                                     pw - lw - self.PAD * 3, ph - 30 - self.TAB_H - self.PAD)

    def _fonts(self):
        if self._font_m is None:
            self._font_m = pygame.font.SysFont(None, 22)
            self._font_s = pygame.font.SysFont(None, 18)
            self._font_t = pygame.font.SysFont(None, 14)

    def _get_list(self, player_level: int = 1) -> List[str]:
        if self._tab == 0:
            # Combine workbench weapons + level-unlocked gunsmith weapons
            wb = get_weapon_recipe_ids()
            gs = get_gunsmith_recipe_ids(player_level)
            seen: set = set()
            result: List[str] = []
            for rid in wb + gs:
                if rid not in seen:
                    seen.add(rid); result.append(rid)
            return result
        return sorted(_discovered)

    def open(self):
        self.is_open   = True
        self._scroll   = 0
        self._selected = -1
        self._tab      = 0

    def close(self):
        self.is_open = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_ESCAPE, pygame.K_r):
                self.close(); return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Tab clicks
            for i, tr in enumerate(self._tab_rects):
                if tr.collidepoint(event.pos):
                    self._tab = i; self._scroll = 0; self._selected = -1; return True
            # List item clicks
            for i, r in enumerate(self._list_rects):
                if r and r.collidepoint(event.pos):
                    self._selected = i; return True
        return True

    def draw(self, screen: pygame.Surface, mouse_pos: tuple, player_level: int = 1):
        if not self.is_open:
            return
        self._fonts()

        # Dim background
        dim = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        screen.blit(dim, (0, 0))

        pr = self._panel
        ps = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        ps.fill((20, 16, 12, 245))
        screen.blit(ps, pr.topleft)
        pygame.draw.rect(screen, (90, 75, 55), pr, 2)

        # Title
        title = self._font_m.render("КНИГА РЕЦЕПТОВ", True, (220, 200, 140))
        screen.blit(title, (pr.x + self.PAD, pr.y + 6))
        hint  = self._font_t.render("[R / Esc]", True, (110, 100, 80))
        screen.blit(hint, (pr.right - hint.get_width() - 8, pr.y + 8))

        # Tabs
        tab_labels = ["Оружие", "Открытые"]
        tab_x = pr.x + self.PAD
        tab_y = pr.y + 28
        self._tab_rects = []
        for i, lbl in enumerate(tab_labels):
            ts   = self._font_s.render(lbl, True, (255, 255, 255))
            tw   = ts.get_width() + 18
            rect = pygame.Rect(tab_x, tab_y, tw, self.TAB_H)
            self._tab_rects.append(rect)
            active = (i == self._tab)
            bg_col = (65, 52, 36) if active else (30, 24, 18)
            bd_col = (200, 170, 80) if active else (70, 62, 48)
            pygame.draw.rect(screen, bg_col, rect, border_radius=4)
            pygame.draw.rect(screen, bd_col, rect, 1, border_radius=4)
            tc = (240, 220, 140) if active else (160, 145, 120)
            ts2 = self._font_s.render(lbl, True, tc)
            screen.blit(ts2, (rect.x + 9, rect.y + (self.TAB_H - ts2.get_height()) // 2))
            tab_x += tw + 4

        # Divider between list and detail
        div_x = self._detail_r.x - self.PAD
        pygame.draw.line(screen, (70, 62, 48),
                         (div_x, pr.y + 30 + self.TAB_H),
                         (div_x, pr.bottom - self.PAD))

        # ── Left: item list ───────────────────────────────────────────────
        items_list = self._get_list(player_level)
        lr = self._list_r
        step  = self.ICON + 4
        cols  = max(1, lr.w // step)
        clip  = pygame.Rect(lr.x, lr.y, lr.w, lr.h)
        screen.set_clip(clip)

        self._list_rects = []
        for idx, rid in enumerate(items_list):
            col = idx % cols
            row = idx // cols - self._scroll
            ry  = lr.y + row * step
            if ry + step < lr.y or ry > lr.bottom:
                self._list_rects.append(None)
                continue
            rx   = lr.x + col * step
            rect = pygame.Rect(rx, ry, self.ICON, self.ICON)
            self._list_rects.append(rect)
            selected = (idx == self._selected)
            hover    = rect.collidepoint(mouse_pos)
            if selected:
                bg = (75, 62, 42)
            elif hover:
                bg = (55, 46, 34)
            else:
                bg = (38, 32, 24)
            pygame.draw.rect(screen, bg, rect)
            bd = (220, 190, 90) if selected else (72, 65, 52)
            pygame.draw.rect(screen, bd, rect, 2 if selected else 1)
            tex = get_item_texture(rid, self.ICON - 6)
            screen.blit(tex, (rx + 3, ry + 3))

        screen.set_clip(None)

        # Scroll hints
        if self._scroll > 0:
            arr = self._font_t.render("▲", True, (160, 150, 120))
            screen.blit(arr, (lr.x + lr.w // 2 - arr.get_width() // 2, lr.y - 2))
        max_rows = max(1, (len(items_list) + cols - 1) // cols)
        visible_rows = lr.h // step
        if self._scroll < max_rows - visible_rows:
            arr = self._font_t.render("▼", True, (160, 150, 120))
            screen.blit(arr, (lr.x + lr.w // 2 - arr.get_width() // 2, lr.bottom + 2))

        # Item name on hover (left panel)
        if not self._list_rects:
            if not items_list:
                msg = self._font_s.render(
                    "Нет рецептов — открой что-нибудь!" if self._tab == 1
                    else "Рецепты недоступны",
                    True, (120, 110, 90))
                screen.blit(msg, (lr.x, lr.y + 4))

        # ── Right: recipe detail ──────────────────────────────────────────
        dr = self._detail_r
        if 0 <= self._selected < len(items_list):
            rid  = items_list[self._selected]
            info = get_recipe_info(rid)
            item = ITEMS.get(rid)
            if info and item:
                self._draw_recipe_detail(screen, dr, rid, item, info)
        else:
            hint2 = self._font_s.render("← Выбери рецепт", True, (100, 90, 70))
            screen.blit(hint2, (dr.x + 8, dr.y + dr.h // 2))

        # Name tooltip on hover
        for idx, r in enumerate(self._list_rects):
            if r and r.collidepoint(mouse_pos) and idx < len(items_list):
                it = ITEMS.get(items_list[idx])
                name = it.name if it else items_list[idx]
                ns = self._font_t.render(name, True, (255, 255, 100))
                tx = min(mouse_pos[0] + 12, self.sw - ns.get_width() - 6)
                ty = max(mouse_pos[1] - ns.get_height() - 4, 4)
                bg = pygame.Surface((ns.get_width() + 8, ns.get_height() + 4), pygame.SRCALPHA)
                bg.fill((12, 8, 6, 210))
                screen.blit(bg, (tx - 4, ty - 2))
                screen.blit(ns, (tx, ty))
                break

    def _draw_recipe_detail(self, screen, dr, rid, item, info):
        """Draw the recipe pattern in the right panel."""
        x, y = dr.x + 8, dr.y + 8

        # Item name + result count
        name_s = self._font_m.render(item.name, True, (240, 220, 150))
        screen.blit(name_s, (x, y)); y += name_s.get_height() + 4

        # Table / level requirement badge
        table = info.get("table", "workbench")
        level_req = info.get("level_req", 0)
        xp_reward = info.get("xp_reward", 0)
        if table == "gunsmith":
            tbl_col = (255, 190, 80)
            tbl_s = self._font_t.render(f"Стол кузница  |  LVL {level_req}+  |  +{xp_reward} XP",
                                        True, tbl_col)
        else:
            tbl_s = self._font_t.render("Верстак", True, (130, 190, 130))
        screen.blit(tbl_s, (x, y)); y += tbl_s.get_height() + 4

        # Tags / properties summary
        props = []
        p = item.properties
        if p.get("damage"):   props.append(f"Урон: {p['damage']}")
        if p.get("defense"):  props.append(f"Защита: {p['defense']}")
        if item.max_durability: props.append(f"Прочность: {item.max_durability}")
        if props:
            ps = self._font_t.render("  ".join(props), True, (160, 150, 120))
            screen.blit(ps, (x, y)); y += ps.get_height() + 6

        if info["type"] == "shaped":
            y = self._draw_shaped(screen, x, y, dr, info["pattern"], rid, info["count"])
        else:
            y = self._draw_unordered(screen, x, y, dr, info["ingredients"], rid, info["count"])

    def _draw_shaped(self, screen, x, y, dr, pattern, rid, count):
        """Draw 3×3 (or smaller) shaped recipe grid."""
        SZ = self.SLOT
        # Normalise pattern to full 3×3
        rows = len(pattern)
        cols = max(len(r) for r in pattern) if pattern else 0
        label = self._font_t.render("Рецепт (строгий):", True, (140, 130, 110))
        screen.blit(label, (x, y)); y += label.get_height() + 4

        grid_x, grid_y = x, y
        for ri in range(rows):
            for ci in range(cols):
                cell = pattern[ri][ci] if ci < len(pattern[ri]) else None
                rx, ry = grid_x + ci * (SZ + 2), grid_y + ri * (SZ + 2)
                rect = pygame.Rect(rx, ry, SZ, SZ)
                if rect.right > dr.right - 4:
                    continue
                pygame.draw.rect(screen, (38, 32, 24), rect)
                pygame.draw.rect(screen, (72, 65, 52), rect, 1)
                if cell:
                    item_obj = ITEMS.get(cell)
                    if item_obj:
                        tex = get_item_texture(cell, SZ - 8)
                        screen.blit(tex, (rx + 4, ry + 4))
                        # Show count if needed (always 1 in patterns)
                        n = self._font_t.render("1", True, (200, 200, 200))
                        screen.blit(n, (rx + SZ - n.get_width() - 2, ry + SZ - n.get_height() - 1))
                    else:
                        # It's a tag — show tag name
                        tag_s = self._font_t.render(cell[:6], True, (180, 160, 100))
                        screen.blit(tag_s, (rx + 2, ry + SZ // 2 - tag_s.get_height() // 2))

        # Arrow + result
        ax = grid_x + cols * (SZ + 2) + 8
        ay = grid_y + (rows * (SZ + 2)) // 2
        if ax + 60 < dr.right:
            pygame.draw.polygon(screen, (200, 170, 60), [
                (ax, ay - 8), (ax + 18, ay), (ax, ay + 8)
            ])
            tex = get_item_texture(rid, SZ)
            screen.blit(tex, (ax + 24, ay - SZ // 2))
            cnt_s = self._font_s.render(f"×{count}", True, (220, 210, 170))
            screen.blit(cnt_s, (ax + 26, ay + SZ // 2 + 2))

        y = grid_y + rows * (SZ + 2) + 14

        # Ingredient legend below grid
        seen: dict = {}
        for row in pattern:
            for cell in row:
                if cell:
                    seen[cell] = seen.get(cell, 0) + 1
        for cell, n in seen.items():
            item_obj = ITEMS.get(cell)
            name = item_obj.name if item_obj else cell
            icon = get_item_texture(cell, 18)
            screen.blit(icon, (x, y))
            ls = self._font_t.render(f"×{n}  {name}", True, (190, 180, 155))
            screen.blit(ls, (x + 22, y + 1))
            y += 22
        return y

    def _draw_unordered(self, screen, x, y, dr, ingredients, rid, count):
        """Draw unordered (any arrangement) recipe."""
        label = self._font_t.render("Рецепт (любой порядок):", True, (140, 130, 110))
        screen.blit(label, (x, y)); y += label.get_height() + 6

        for iid, n in ingredients.items():
            item_obj = ITEMS.get(iid)
            name = item_obj.name if item_obj else iid
            icon = get_item_texture(iid, 26)
            screen.blit(icon, (x, y))
            ls = self._font_s.render(f"×{n}  {name}", True, (210, 200, 170))
            screen.blit(ls, (x + 30, y + 4))
            y += 32

        y += 8
        # Arrow + result
        pygame.draw.polygon(screen, (200, 170, 60), [(x, y+8), (x+16, y+16), (x, y+24)])
        tex = get_item_texture(rid, 36)
        screen.blit(tex, (x + 24, y))
        cnt_s = self._font_s.render(f"×{count}  {ITEMS[rid].name if rid in ITEMS else rid}",
                                    True, (220, 210, 170))
        screen.blit(cnt_s, (x + 64, y + 10))
        return y + 44


# ── Gunsmith Recipe Book ──────────────────────────────────────────────────────

class GunsmithRecipeBook:
    """Overlay showing all gunsmith recipes; click to auto-fill grid if possible."""

    _COLS = 4
    _CELL = 56   # icon cell size

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open = False
        self._font_m = self._font_s = None
        self._scroll = 0
        self._recipes: List[tuple] = []   # [(result_id, count, ingredients)]

    def _fonts(self):
        if self._font_m is None:
            self._font_m = pygame.font.SysFont(None, 22)
            self._font_s = pygame.font.SysFont(None, 17)

    def open(self, player_level: int = 1):
        self.is_open = True
        self._scroll = 0
        seen: set = set()
        result: List[tuple] = []
        for pat, rid, cnt in _GUNSMITH_SHAPED:
            req = _GUNSMITH_LEVEL_REQ.get(rid, 1)
            if rid in ITEMS and rid not in seen and player_level >= req:
                # Count required ingredients from pattern
                ingr: Dict[str, int] = {}
                for row in pat:
                    for cell in row:
                        if cell:
                            ingr[cell] = ingr.get(cell, 0) + 1
                seen.add(rid)
                result.append((rid, cnt, ingr))
        for ingr_d, rid, cnt in _GUNSMITH_UNORDERED:
            req = _GUNSMITH_LEVEL_REQ.get(rid, 1)
            if rid in ITEMS and rid not in seen and player_level >= req:
                seen.add(rid)
                result.append((rid, cnt, dict(ingr_d)))
        self._recipes = result

    def _panel_rect(self) -> pygame.Rect:
        pw = min(self.sw - 40, self._COLS * (self._CELL + 8) + 60)
        ph = min(self.sh - 60, 500)
        return pygame.Rect(self.sw // 2 - pw // 2, self.sh // 2 - ph // 2, pw, ph)

    def _item_rects(self) -> List[pygame.Rect]:
        pr = self._panel_rect()
        C, CS = self._COLS, self._CELL + 8
        rects = []
        for i, (rid, cnt, ingr) in enumerate(self._recipes):
            col = i % C
            row = i // C
            x = pr.x + 14 + col * CS
            y = pr.y + 44 + row * CS - self._scroll
            rects.append(pygame.Rect(x, y, self._CELL, self._CELL))
        return rects

    def _can_craft(self, ingr: Dict[str, int], inv: Inventory) -> bool:
        counts: Dict[str, int] = {}
        for s in inv.slots:
            if s and not s.is_empty():
                counts[s.item_id] = counts.get(s.item_id, 0) + s.count
        return all(counts.get(k, 0) >= v for k, v in ingr.items())

    def handle_event(self, event, grid: list, inv: Inventory) -> bool:
        """Returns True if event consumed. Fills grid on recipe click."""
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            k = _keys.normalize(event)
            if k in (pygame.K_ESCAPE, pygame.K_r):
                self.is_open = False
                return True
        if event.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - event.y * 30)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pr = self._panel_rect()
            if not pr.collidepoint(event.pos):
                self.is_open = False
                return True
            rects = self._item_rects()
            for i, r in enumerate(rects):
                if r.collidepoint(event.pos) and i < len(self._recipes):
                    rid, cnt, ingr = self._recipes[i]
                    if self._can_craft(ingr, inv):
                        self._fill_grid(rid, ingr, grid, inv)
                    self.is_open = False
                    return True
        return True

    def _fill_grid(self, rid: str, ingr: Dict[str, int], grid: list, inv: Inventory):
        """Move required items from inventory into the 5×5 grid."""
        # Return existing grid contents to inventory
        for i in range(25):
            if grid[i] and not grid[i].is_empty():
                inv.add(grid[i])
            grid[i] = None
        # Place ingredients starting from top-left
        slot_idx = 0
        for item_id, need in ingr.items():
            remaining = need
            while remaining > 0 and slot_idx < 25:
                take = min(remaining, 64)
                # Find in inventory
                for si, s in enumerate(inv.slots):
                    if s and s.item_id == item_id and not s.is_empty():
                        moved = min(s.count, take)
                        grid[slot_idx] = ItemStack(item_id, moved)
                        s.count -= moved
                        if s.is_empty():
                            inv.slots[si] = None
                        remaining -= moved
                        slot_idx += 1
                        break
                else:
                    break

    def draw(self, screen: pygame.Surface, inv: Inventory):
        if not self.is_open:
            return
        self._fonts()
        from assets import get_item_texture

        sw, sh = screen.get_size()
        pr = self._panel_rect()

        # Dim background
        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        screen.blit(dim, (0, 0))

        pygame.draw.rect(screen, (28, 22, 14), pr, border_radius=8)
        pygame.draw.rect(screen, (200, 170, 60), pr, 2, border_radius=8)

        title = self._font_m.render("РЕЦЕПТЫ КУЗНИЦЫ  (R / ESC — закрыть)",
                                    True, (240, 210, 120))
        screen.blit(title, (pr.x + 10, pr.y + 12))

        mouse = pygame.mouse.get_pos()
        rects = self._item_rects()
        clip = pygame.Rect(pr.x, pr.y + 40, pr.w, pr.h - 44)
        screen.set_clip(clip)

        for i, (r, (rid, cnt, ingr)) in enumerate(zip(rects, self._recipes)):
            if r.bottom < pr.y + 40 or r.top > pr.bottom:
                continue
            craftable = self._can_craft(ingr, inv)
            hov = r.collidepoint(mouse)
            bg = (55, 45, 30) if hov else (38, 30, 18)
            bd = (220, 180, 60) if craftable else (80, 70, 50)
            pygame.draw.rect(screen, bg, r, border_radius=4)
            pygame.draw.rect(screen, bd, r, 2 if craftable else 1, border_radius=4)
            tex = get_item_texture(rid, self._CELL - 12)
            screen.blit(tex, (r.x + 6, r.y + 4))
            # Item name
            name = ITEMS[rid].name if rid in ITEMS else rid
            nm = self._font_s.render(name[:12], True,
                                     (240, 220, 140) if craftable else (120, 110, 80))
            screen.blit(nm, (r.x + 2, r.y + self._CELL - 14))
            # Tooltip on hover: show required ingredients
            if hov:
                lines = [f"{v}× {k}" for k, v in ingr.items()]
                tw = max(len(l) for l in lines) * 7 + 10
                ty0 = r.bottom + 4
                pygame.draw.rect(screen, (20, 16, 10),
                                 (r.x, ty0, tw, len(lines) * 16 + 6), border_radius=3)
                for li, ln in enumerate(lines):
                    lc = (180, 240, 160) if self._can_craft({v: int(k) for k, v in [ln.split("× ")]
                                                             if len(ln.split("× ")) == 2},
                                                            inv) else (200, 170, 130)
                    lt = self._font_s.render(ln, True, lc)
                    screen.blit(lt, (r.x + 4, ty0 + 3 + li * 16))

        screen.set_clip(None)


# ── Gunsmith Table UI ─────────────────────────────────────────────────────────

class GunsmithUI:
    """5×5 gunsmith-table overlay — shaped recipes for all firearms."""

    _GS = 40  # craft-slot size (slightly smaller than CraftingUI to fit 5×5)

    def __init__(self, sw: int, sh: int):
        self.grid:   List[Optional[ItemStack]] = [None] * 25
        self.result: Optional[ItemStack] = None
        self._result_locked: Optional[ItemStack] = None  # recipe exists but level too low
        self.cursor: Optional[ItemStack] = None
        self.is_open = False
        self.sw = sw
        self.sh = sh
        self._craft_rects: List[pygame.Rect] = []
        self._output_rect: Optional[pygame.Rect] = None
        self._inv_rects:   List[pygame.Rect] = []
        self._hb_rects:    List[pygame.Rect] = []
        self._panel_rect   = pygame.Rect(0, 0, 10, 10)
        self._font_m = self._font_s = self._font_t = None
        self._panel_surf = None
        self.recipe_book = GunsmithRecipeBook(sw, sh)
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._panel_surf = None
        self.recipe_book.sw, self.recipe_book.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        sw, sh, GS, SS = self.sw, self.sh, self._GS, SLOT_STEP
        top_y  = 40
        grid_w = 5 * GS
        ox     = sw // 2 - (grid_w + 50 + GS + 8) // 2

        self._craft_rects = [
            pygame.Rect(ox + (i % 5) * GS, top_y + (i // 5) * GS, GS - 4, GS - 4)
            for i in range(25)
        ]
        out_x = ox + grid_w + 50
        out_y = top_y + 2 * GS
        self._output_rect = pygame.Rect(out_x, out_y, GS + 8, GS + 8)
        self._arrow_pos   = (ox + grid_w + 14, top_y + 2 * GS + GS // 2)

        inv_top = top_y + 5 * GS + 20
        inv_ox  = sw // 2 - 9 * SS // 2
        self._inv_rects = [
            pygame.Rect(inv_ox + (i % 9) * SS, inv_top + (i // 9) * SS, SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_top + GRID_ROWS * SS + 6
        self._hb_rects = [
            pygame.Rect(inv_ox + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        pan_bot = max(r.bottom for r in self._hb_rects) + 12
        all_rects = self._craft_rects + [self._output_rect] + self._inv_rects + self._hb_rects
        raw_left  = min(r.x     for r in all_rects) - 14
        raw_right = max(r.right for r in all_rects) + 14
        # Symmetrize around screen center so the panel looks centred
        half_w    = max(sw // 2 - raw_left, raw_right - sw // 2)
        pan_left  = sw // 2 - half_w
        self._panel_rect = pygame.Rect(pan_left, top_y - 28,
                                       half_w * 2,
                                       pan_bot - top_y + 28 + 12)

    def _fonts(self):
        if self._font_m is None:
            self._font_m = pygame.font.SysFont(None, 22)
            self._font_s = pygame.font.SysFont(None, 18)
            self._font_t = pygame.font.SysFont(None, 14)

    # ── open / close ──────────────────────────────────────────────────────

    def open(self):
        self.is_open = True

    def close(self, inv: Inventory):
        self.is_open = False
        for i in range(25):
            s = self.grid[i]
            if s and not s.is_empty():
                inv.add(s)
            self.grid[i] = None
        if self.cursor:
            inv.add(self.cursor)
            self.cursor = None
        self.result = None

    # ── events ────────────────────────────────────────────────────────────

    def handle_event(self, event, inv: Inventory, player=None) -> bool:
        if not self.is_open:
            return False
        # Recipe book takes priority when open
        if self.recipe_book.is_open:
            self.recipe_book.handle_event(event, self.grid, inv)
            return True
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_e, pygame.K_ESCAPE):
                self.close(inv)
                return True
            if norm == pygame.K_r:
                lvl = player.level if player is not None else 1
                self.recipe_book.open(lvl)
                _log.info("Рецепты кузницы открыты")
                return True
            num = norm - pygame.K_1
            if 0 <= num <= 8:
                inv.selected = num
                return True
        if event.type == pygame.MOUSEWHEEL:
            inv.selected = (inv.selected - event.y) % HOTBAR_N
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            mods = pygame.key.get_mods()
            self._click(event.pos, event.button, bool(mods & pygame.KMOD_SHIFT), inv, player)
        return True

    def _click(self, pos, btn, shift, inv, player=None):
        if self._output_rect and self._output_rect.collidepoint(pos):
            if self.result and not self.result.is_empty():
                def _do_craft():
                    _log.info("КРАФТ: %s ×%d (стол кузница)",
                              self.result.item_id, self.result.count)
                    mark_discovered(self.result.item_id)
                    xp = _GUNSMITH_XP_REWARD.get(self.result.item_id, 0)
                    if player is not None and xp > 0:
                        player.add_xp(xp)
                    self._consume_inputs()
                    sounds.play("craft", 0.55)

                if shift or self.cursor is None:
                    _do_craft()
                    if shift:
                        inv.add(self.result)
                    else:
                        self.cursor = self.result
                    self._update_result(player)
                elif (self.cursor.item_id == self.result.item_id
                      and self.cursor.can_merge(self.result)):
                    _do_craft()
                    self.cursor.count += min(
                        self.cursor.max_stack - self.cursor.count, self.result.count)
                    self._update_result(player)
            return

        for i, r in enumerate(self._craft_rects):
            if r.collidepoint(pos):
                if shift and btn == 1 and self.grid[i]:
                    inv.add(self.grid[i]); self.grid[i] = None
                elif btn == 1: self._lmb(self.grid, i)
                elif btn == 3: self._rmb(self.grid, i)
                self._update_result(player)
                return

        for i, r in enumerate(self._inv_rects):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if shift and btn == 1: self._shift_to_craft(idx, inv, player)
                elif btn == 1: self._lmb(inv.slots, idx)
                elif btn == 3: self._rmb(inv.slots, idx)
                return
        for i, r in enumerate(self._hb_rects):
            if r.collidepoint(pos):
                if shift and btn == 1: self._shift_to_craft(i, inv, player)
                elif btn == 1: self._lmb(inv.slots, i)
                elif btn == 3: self._rmb(inv.slots, i)
                return
        if self.cursor:
            inv.add(self.cursor); self.cursor = None

    def _lmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot; slots[i] = None
        else:
            if slot is None or slot.is_empty():
                slots[i] = self.cursor; self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                move = min(slot.max_stack - slot.count, self.cursor.count)
                slot.count += move; self.cursor.count -= move
                if self.cursor.count <= 0: self.cursor = None
            else:
                slots[i] = self.cursor
                self.cursor = slot if not slot.is_empty() else None

    def _rmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot.split_half()
                if slot.is_empty(): slots[i] = None
        else:
            if slot is None or slot.is_empty():
                slots[i] = ItemStack(self.cursor.item_id, 1, self.cursor.durability)
                self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                slot.count += 1; self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None

    def _shift_to_craft(self, idx, inv, player=None):
        s = inv.slots[idx]
        if not s or s.is_empty(): return
        for j in range(25):
            if self.grid[j] is None:
                self.grid[j] = s; inv.slots[idx] = None
                self._update_result(player); return
        targets = range(HOTBAR_N, TOTAL_N) if idx < HOTBAR_N else range(HOTBAR_N)
        for i in targets:
            if inv.slots[i] is None:
                inv.slots[i] = s; inv.slots[idx] = None; return

    def _update_result(self, player=None):
        lvl = player.level if player is not None else 99
        self.result = determine_gunsmith_result(self.grid, lvl)
        # Also store what would be crafted at max level (for lock display)
        self._result_locked = determine_gunsmith_result(self.grid, 99) \
            if self.result is None else None

    def _consume_inputs(self):
        for i in range(25):
            s = self.grid[i]
            if s and not s.is_empty():
                s.count -= 1
                if s.count <= 0: self.grid[i] = None

    # ── drawing ───────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: Inventory, mouse_pos: tuple, player=None):
        if not self.is_open:
            return
        self._fonts()
        sw, sh = screen.get_size()
        GS = self._GS

        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 145))
        screen.blit(dim, (0, 0))

        pr = self._panel_rect
        if self._panel_surf is None or self._panel_surf.get_size() != (pr.w, pr.h):
            self._panel_surf = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
            self._panel_surf.fill((22, 18, 28, 235))
        screen.blit(self._panel_surf, pr.topleft)
        pygame.draw.rect(screen, (130, 95, 55), pr, 2)

        title = self._font_m.render("СТОЛ КУЗНИЦА", True, (255, 190, 80))
        screen.blit(title, (pr.x + 8, pr.y + 6))

        for i, r in enumerate(self._craft_rects):
            pygame.draw.rect(screen, (50, 42, 32), r)
            pygame.draw.rect(screen, (80, 65, 48), r, 1)
            s = self.grid[i]
            if s and not s.is_empty():
                tex = get_item_texture(s.item_id, GS - 6)
                screen.blit(tex, (r.x + 3, r.y + 3))
                if s.count > 1:
                    c = self._font_s.render(str(s.count), True, (255, 255, 255))
                    screen.blit(c, (r.right - c.get_width() - 2, r.bottom - c.get_height()))

        ax, ay = self._arrow_pos
        pygame.draw.polygon(screen, (200, 165, 55),
                            [(ax, ay - 10), (ax + 22, ay), (ax, ay + 10)])

        if self._output_rect:
            or_ = self._output_rect
            pygame.draw.rect(screen, (40, 32, 22), or_)
            pygame.draw.rect(screen, (200, 150, 60), or_, 2)
            if self.result and not self.result.is_empty():
                tex = get_item_texture(self.result.item_id, GS + 4)
                screen.blit(tex, (or_.x + 2, or_.y + 2))
                if self.result.count > 1:
                    c = self._font_s.render(str(self.result.count), True, (255, 255, 200))
                    screen.blit(c, (or_.right - c.get_width() - 2, or_.bottom - 16))
            elif self._result_locked and not self._result_locked.is_empty():
                # Recipe exists but level is too low — show dimmed item + lock
                tex = get_item_texture(self._result_locked.item_id, GS + 4)
                dim_surf = tex.copy()
                dim_surf.set_alpha(80)
                screen.blit(dim_surf, (or_.x + 2, or_.y + 2))
                req = _GUNSMITH_LEVEL_REQ.get(self._result_locked.item_id, 1)
                lock_s = self._font_t.render(f"LVL {req}", True, (255, 80, 80))
                screen.blit(lock_s, (or_.x + (or_.w - lock_s.get_width()) // 2,
                                     or_.y + or_.h - lock_s.get_height() - 2))

        for i, r in enumerate(self._inv_rects):
            pygame.draw.rect(screen, (50, 42, 35), r)
            pygame.draw.rect(screen, (75, 62, 48), r, 1)
            s = inv.slots[HOTBAR_N + i]
            if s and not s.is_empty():
                tex = get_item_texture(s.item_id, SLOT_SIZE - 4)
                screen.blit(tex, (r.x + 2, r.y + 2))
                if s.count > 1:
                    c = self._font_s.render(str(s.count), True, (255, 255, 255))
                    screen.blit(c, (r.right - c.get_width() - 2, r.bottom - 14))

        for i, r in enumerate(self._hb_rects):
            sel = i == inv.selected
            pygame.draw.rect(screen, (50, 42, 35), r)
            pygame.draw.rect(screen, (130, 105, 60) if sel else (75, 62, 48), r, 2 if sel else 1)
            s = inv.slots[i]
            if s and not s.is_empty():
                tex = get_item_texture(s.item_id, SLOT_SIZE - 4)
                screen.blit(tex, (r.x + 2, r.y + 2))
                if s.count > 1:
                    c = self._font_s.render(str(s.count), True, (255, 255, 255))
                    screen.blit(c, (r.right - c.get_width() - 2, r.bottom - 14))

        if self.cursor and not self.cursor.is_empty():
            cx, cy = mouse_pos
            tex = get_item_texture(self.cursor.item_id, GS)
            screen.blit(tex, (cx - GS // 2, cy - GS // 2))

        for i, r in enumerate(self._craft_rects):
            if r.collidepoint(mouse_pos):
                s = self.grid[i]
                if s and not s.is_empty() and s.item:
                    tt = self._font_s.render(s.item.name, True, (230, 220, 180))
                    tx = min(mouse_pos[0] + 12, sw - tt.get_width() - 4)
                    screen.blit(tt, (tx, mouse_pos[1] - 20))

        # Recipe book overlay (drawn on top of everything)
        self.recipe_book.draw(screen, inv)


# ── Villager Trade UI ─────────────────────────────────────────────────────────

class VillagerTradeUI:
    """Split-panel trade UI with trust tiers, keyboard nav, and item counts."""

    PW = 710
    PH = 490
    LW = 290    # left list panel width
    ROW_H = 42
    HDR_H = 22
    TRUST_PER_TRADE = 8

    _TIER_NAMES  = ["Новичок", "Ученик", "Подмастерье", "Мастер"]
    _TIER_TRUST  = [0, 25, 50, 75]

    _PROF_NAMES = {
        "farmer":      "Фермер",
        "smith":       "Кузнец",
        "librarian":   "Библиотекарь",
        "weaponsmith": "Оружейник",
        "mason":       "Каменщик",
        "cleric":      "Жрец",
        "butcher":     "Мясник",
        "fletcher":    "Лучник",
        "piglin":      "Пиглин",
    }
    _GREETINGS = {
        "farmer":      "Куплю продукты, продам еду!",
        "smith":       "Металл и инструменты — лучшие цены!",
        "librarian":   "Знания — сила. Торгуем?",
        "weaponsmith": "Оружие любого типа, спрашивай!",
        "mason":       "Камень — основа всего!",
        "cleric":      "Зелья и магия — мой хлеб!",
        "butcher":     "Лучшее мясо — у меня!",
        "fletcher":    "Лук и стрелы — быстро и метко!",
        "piglin":      "Золото! Давай золото, я давать хорошее.",
    }

    # (give_dict, get_dict, tier 0-3)
    _TRADES: Dict[str, List[tuple]] = {
        "farmer": [
            ({"coal":          2}, {"bread":          2}, 0),
            ({"apple":         5}, {"emerald":        1}, 0),
            ({"baked_potato":  6}, {"emerald":        1}, 0),
            ({"emerald":       1}, {"bread":          6}, 1),
            ({"beef":          4}, {"emerald":        1}, 1),
            ({"emerald":       2}, {"cooked_beef":    4}, 1),
            ({"emerald":       3}, {"apple":         16}, 2),
            ({"cooked_beef":   4}, {"emerald":        2}, 2),
            ({"emerald":       5}, {"golden_apple":   1}, 3),
            ({"bread":        24}, {"golden_apple":   1}, 3),
        ],
        "smith": [
            ({"coal":          3}, {"iron_ingot":     1}, 0),
            ({"iron_ingot":    4}, {"emerald":        1}, 0),
            ({"coal": 4, "iron_ingot": 1}, {"steel_ingot": 1}, 1),
            ({"emerald":       3}, {"iron_pickaxe":   1}, 1),
            ({"diamond":       2}, {"emerald":        3}, 2),
            ({"emerald":       5}, {"iron_chestplate":1}, 2),
            ({"emerald":       8}, {"diamond_pickaxe":1}, 3),
            ({"emerald":       6}, {"diamond_sword":  1}, 3),
        ],
        "librarian": [
            ({"stick":         4}, {"torch":          8}, 0),
            ({"coal":          2}, {"glass":          6}, 0),
            ({"bone":          2}, {"arrow":          8}, 0),
            ({"emerald":       1}, {"book":           3}, 1),
            ({"lapis_lazuli": 10}, {"emerald":        1}, 1),
            ({"emerald":       3}, {"lapis_lazuli":   8}, 2),
            ({"blaze_rod":     1}, {"emerald":        2}, 2),
            ({"emerald":       5}, {"enchanting_table":1}, 3),
            ({"emerald":       3}, {"brewing_stand":  1}, 3),
        ],
        "weaponsmith": [
            ({"iron_ingot":    4}, {"iron_sword":     1}, 0),
            ({"steel_ingot":   2}, {"emerald":        2}, 0),
            ({"emerald":       2}, {"iron_axe":       1}, 1),
            ({"diamond":       2}, {"emerald":        3}, 1),
            ({"emerald":       5}, {"diamond_sword":  1}, 2),
            ({"emerald":       4}, {"diamond_axe":    1}, 2),
            ({"emerald":      10}, {"netherite_sword":1}, 3),
        ],
        "mason": [
            ({"stone":        10}, {"cobblestone":   10}, 0),
            ({"cobblestone":  12}, {"emerald":        1}, 0),
            ({"emerald":       1}, {"granite":        4}, 1),
            ({"emerald":       1}, {"diorite":        4}, 1),
            ({"obsidian":      2}, {"emerald":        1}, 2),
            ({"emerald":       3}, {"glass":          8}, 2),
            ({"emerald":       4}, {"obsidian":       4}, 3),
        ],
        "cleric": [
            ({"gunpowder":     3}, {"emerald":        1}, 0),
            ({"spider_eye":    1}, {"emerald":        1}, 0),
            ({"emerald":       2}, {"healing_potion": 1}, 1),
            ({"emerald":       2}, {"speed_potion":   1}, 1),
            ({"blaze_powder":  2}, {"emerald":        1}, 2),
            ({"emerald":       3}, {"strength_potion":1}, 2),
            ({"ghast_tear":    1}, {"emerald":        3}, 3),
            ({"emerald":       5}, {"fire_resistance_potion":1}, 3),
        ],
        "butcher": [
            ({"beef":          4}, {"cooked_beef":    4}, 0),
            ({"leather":       3}, {"emerald":        1}, 0),
            ({"emerald":       2}, {"cooked_beef":    8}, 1),
            ({"coal":          2}, {"cooked_beef":    6}, 1),
            ({"bone":          5}, {"emerald":        1}, 2),
            ({"emerald":       3}, {"golden_apple":   1}, 2),
            ({"emerald":       6}, {"golden_apple":   3}, 3),
        ],
        "fletcher": [
            ({"stick":         4}, {"arrow":          8}, 0),
            ({"feather":       3}, {"emerald":        1}, 0),
            ({"string":        2}, {"emerald":        1}, 1),
            ({"emerald":       2}, {"bow":            1}, 1),
            ({"flint":         8}, {"emerald":        1}, 2),
            ({"emerald":       3}, {"arrow":         32}, 2),
            ({"emerald":       6}, {"bow":            1}, 3),
        ],
        # Пиглины торгуют за золото — дают незерские товары
        "piglin": [
            ({"gold_ingot":    1}, {"bullet":        32}, 0),
            ({"gold_ingot":    2}, {"nether_brick":   8}, 0),
            ({"gold_ingot":    3}, {"flint_and_steel":1}, 0),
            ({"gold_ingot":    2}, {"obsidian":       2}, 1),
            ({"gold_ingot":    4}, {"blaze_rod":      2}, 1),
            ({"gold_ingot":    5}, {"fire_resistance_potion": 1}, 1),
            ({"gold_ingot":    6}, {"blaze_powder":   4}, 2),
            ({"gold_ingot":    8}, {"netherite_scrap":1}, 2),
            ({"gold_ingot":   12}, {"ancient_debris": 1}, 3),
            ({"gold_ingot":   16}, {"netherite_ingot":1}, 3),
        ],
    }

    _ROW_H  = 72   # height of one trade card
    _ICO_SZ = 40   # icon size inside card
    _STOCK_PER_TRADE = (3, 6)   # random stock range when opening

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open     = False
        self._mob        = None
        self._selected   = 0
        self._scroll_px  = 0
        self._btn_rect: Optional[pygame.Rect] = None
        self._stock: Dict[int, int] = {}   # trade_index → remaining stock
        self._fa: Optional[pygame.font.Font] = None
        self._fb: Optional[pygame.font.Font] = None
        self._fc: Optional[pygame.font.Font] = None
        self._fd: Optional[pygame.font.Font] = None

    def _fonts(self):
        if self._fa is None:
            self._fa = pygame.font.SysFont(None, 28)
            self._fb = pygame.font.SysFont(None, 21)
            self._fc = pygame.font.SysFont(None, 16)
            self._fd = pygame.font.SysFont(None, 14)

    def open(self, mob) -> None:
        self.is_open   = True
        self._mob      = mob
        if "trust" not in mob.extra:
            mob.extra["trust"] = 0
        self._selected = 0
        self._scroll_px = 0
        # Assign fresh stock for each trade this session
        trades = self._prof_trades()
        self._stock = {i: random.randint(*self._STOCK_PER_TRADE)
                       for i in range(len(trades))}

    def close(self) -> None:
        self.is_open = False
        self._mob    = None

    def _prof_trades(self) -> List[tuple]:
        if not self._mob:
            return []
        prof = self._mob.extra.get("profession", "farmer")
        return self._TRADES.get(prof, [])

    def _tier_level(self) -> int:
        trust = self._mob.extra.get("trust", 0) if self._mob else 0
        return sum(1 for t in self._TIER_TRUST if trust >= t) - 1

    def _build_flat(self, trades: List[tuple], tier_lv: int):
        """Returns list of (kind, payload, height):
           kind='header' payload=tier_int
           kind='trade'  payload=trade_index
           kind='locked' payload=tier_int
        """
        flat = []
        for tier in range(4):
            flat.append(("header", tier, self.HDR_H))
            tier_trades = [(i, t) for i, t in enumerate(trades) if t[2] == tier]
            if tier > tier_lv:
                flat.append(("locked", tier, self.ROW_H))
            else:
                for idx, _ in tier_trades:
                    flat.append(("trade", idx, self.ROW_H))
        return flat

    def _selectable_indices(self, trades, tier_lv) -> List[int]:
        return [i for i, t in enumerate(trades) if t[2] <= tier_lv]

    def handle_event(self, event: pygame.event.Event, inv) -> bool:
        if not self.is_open:
            return False
        trades   = self._prof_trades()
        tier_lv  = self._tier_level()
        sel_idx  = self._selectable_indices(trades, tier_lv)

        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_ESCAPE, pygame.K_e):
                self.close(); return True
            if norm == pygame.K_RETURN and self._selected in sel_idx:
                self._execute(inv, trades); return True
            if norm == pygame.K_UP:
                pos = sel_idx.index(self._selected) if self._selected in sel_idx else 0
                self._selected = sel_idx[max(0, pos - 1)]
                return True
            if norm == pygame.K_DOWN:
                pos = sel_idx.index(self._selected) if self._selected in sel_idx else -1
                self._selected = sel_idx[min(len(sel_idx) - 1, pos + 1)]
                return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button in (4, 5):   # scroll wheel
                self._scroll_px += -30 if event.button == 4 else 30
                return True
            if event.button == 1:
                if self._btn_rect and self._btn_rect.collidepoint(event.pos):
                    self._execute(inv, trades); return True
                # Check trade row clicks — handled in draw via _click_map
                for (y0, y1, idx) in getattr(self, "_click_map", []):
                    if y0 <= event.pos[1] < y1 and idx in sel_idx:
                        self._selected = idx; return True
        return True

    def _execute(self, inv, trades: List[tuple]) -> None:
        if not (0 <= self._selected < len(trades)):
            return
        if self._stock.get(self._selected, 0) <= 0:
            return   # out of stock
        give_d, get_d, _ = trades[self._selected]
        if not all(inv.count(iid) >= n for iid, n in give_d.items()):
            return
        for iid, n in give_d.items():
            inv.remove(iid, n)
        for iid, n in get_d.items():
            if iid in ITEMS:
                inv.add(ItemStack(iid, n))
        self._stock[self._selected] = max(0, self._stock.get(self._selected, 0) - 1)
        if self._mob:
            self._mob.extra["trust"] = min(100, self._mob.extra.get("trust", 0)
                                           + self.TRUST_PER_TRADE)
        sounds.play("craft", 0.7)

    # ── Drawing helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _draw_stars(screen, x, y, filled: int, total: int = 4,
                    size: int = 14, gap: int = 3):
        for i in range(total):
            cx = x + i * (size + gap) + size // 2
            cy = y + size // 2
            col = (255, 210, 40) if i < filled else (55, 48, 32)
            bdr = (200, 160, 20) if i < filled else (80, 70, 50)
            pts = []
            import math as _m
            for k in range(5):
                a_out = _m.pi / 2 + k * 2 * _m.pi / 5
                a_in  = a_out + _m.pi / 5
                pts.append((cx + _m.cos(a_out) * size // 2,
                             cy - _m.sin(a_out) * size // 2))
                pts.append((cx + _m.cos(a_in)  * size // 4,
                             cy - _m.sin(a_in)  * size // 4))
            pygame.draw.polygon(screen, col, pts)
            pygame.draw.polygon(screen, bdr, pts, 1)

    def draw(self, screen: pygame.Surface, mouse_pos: tuple, inv) -> None:
        if not self.is_open or not self._mob:
            return
        self._fonts()

        PW = min(self.sw - 60, 600)
        PH = min(self.sh - 60, 520)
        px = (self.sw - PW) // 2
        py = (self.sh - PH) // 2

        # ── Panel shadow ──────────────────────────────────────────────────────
        shad = pygame.Surface((PW + 8, PH + 8), pygame.SRCALPHA)
        shad.fill((0, 0, 0, 80))
        screen.blit(shad, (px + 4, py + 4))

        # ── Panel background ──────────────────────────────────────────────────
        bg = pygame.Surface((PW, PH), pygame.SRCALPHA)
        bg.fill((12, 8, 4, 250))
        screen.blit(bg, (px, py))
        pygame.draw.rect(screen, (140, 110, 60), (px, py, PW, PH), 2, border_radius=8)
        pygame.draw.rect(screen, (80, 60, 30), (px + 1, py + 1, PW - 2, PH - 2), 1, border_radius=7)

        prof      = self._mob.extra.get("profession", "farmer")
        trust     = self._mob.extra.get("trust", 0)
        trades    = self._prof_trades()
        tier_lv   = self._tier_level()
        sel_idx   = self._selectable_indices(trades, tier_lv)
        prof_name = self._PROF_NAMES.get(prof, prof)
        greeting  = self._GREETINGS.get(prof, "")

        # ── Header block ──────────────────────────────────────────────────────
        hdr_h = 72
        hdr_bg = pygame.Surface((PW - 4, hdr_h - 2), pygame.SRCALPHA)
        hdr_bg.fill((30, 22, 10, 220))
        screen.blit(hdr_bg, (px + 2, py + 2))
        pygame.draw.line(screen, (110, 88, 48), (px + 8, py + hdr_h),
                         (px + PW - 8, py + hdr_h), 2)

        # Profession name + tier stars
        title_s = self._fa.render(f"Торговля  —  {prof_name}", True, (245, 215, 130))
        screen.blit(title_s, (px + 14, py + 8))
        self._draw_stars(screen, px + PW - 14 - (tier_lv + 1) * 17,
                         py + 8, tier_lv + 1)

        # Greeting in italics (using regular font, different color)
        greet_s = self._fb.render(f"«{greeting}»", True, (145, 175, 120))
        screen.blit(greet_s, (px + 16, py + 34))

        # Trust bar
        bar_x = px + 14
        bar_w = PW - 28
        bar_h = 10
        bar_y = py + 56
        pygame.draw.rect(screen, (28, 22, 12), (bar_x, bar_y, bar_w, bar_h), border_radius=5)
        fw = int(trust / 100 * bar_w)
        if fw > 0:
            bar_col = (50, 160, 70) if trust >= 75 else (160, 120, 40)
            pygame.draw.rect(screen, bar_col, (bar_x, bar_y, fw, bar_h), border_radius=5)
        pygame.draw.rect(screen, (180, 145, 65), (bar_x, bar_y, bar_w, bar_h), 1, border_radius=5)
        for thr in self._TIER_TRUST[1:]:
            mx = bar_x + int(thr / 100 * bar_w)
            pygame.draw.line(screen, (255, 210, 80), (mx, bar_y + 1), (mx, bar_y + bar_h - 2))
        if tier_lv < 3:
            nxt = self._TIER_TRUST[tier_lv + 1]
            bar_txt = f"{self._TIER_NAMES[tier_lv]}  {trust}/100  →  {self._TIER_NAMES[tier_lv+1]} +{nxt - trust}"
        else:
            bar_txt = f"{self._TIER_NAMES[tier_lv]}  {trust}/100  •  Максимальный уровень"
        bt_s = self._fd.render(bar_txt, True, (185, 160, 90))
        screen.blit(bt_s, (bar_x + bar_w // 2 - bt_s.get_width() // 2, bar_y - 13))

        # ── Trade cards (scrollable single-column) ────────────────────────────
        list_x  = px + 8
        list_w  = PW - 16
        list_y0 = py + hdr_h + 6
        list_h  = PH - hdr_h - 44   # leave room for bottom hint

        RH  = self._ROW_H
        ISO = self._ICO_SZ

        # Build flat list: headers + trade rows
        flat = []
        for tier in range(4):
            flat.append(("hdr", tier))
            tier_trades = [(i, t) for i, t in enumerate(trades) if t[2] == tier]
            if tier > tier_lv:
                flat.append(("locked", tier))
            else:
                for idx, _ in tier_trades:
                    flat.append(("trade", idx))

        HDR_H = 22
        heights = [HDR_H if k in ("hdr", "locked") else RH for k, _ in flat]
        content_h = sum(heights)
        max_sc = max(0, content_h - list_h + 4)
        self._scroll_px = max(0, min(self._scroll_px, max_sc))

        old_clip = screen.get_clip()
        screen.set_clip(pygame.Rect(list_x, list_y0, list_w, list_h))

        y_cur     = list_y0 - self._scroll_px
        click_map = []

        for (kind, payload), row_h in zip(flat, heights):
            ys, ye = y_cur, y_cur + row_h
            if ye > list_y0 - 2 and ys < list_y0 + list_h + 2:

                if kind == "hdr":
                    tier   = payload
                    locked = tier > tier_lv
                    hc = (48, 38, 20) if not locked else (28, 22, 14)
                    lc = (210, 170, 80) if not locked else (80, 68, 48)
                    tier_label = self._TIER_NAMES[tier]
                    if locked:
                        tier_label += f"   🔒  нужно {self._TIER_TRUST[tier]} доверия"
                    pygame.draw.rect(screen, hc, (list_x, ys, list_w, row_h - 1))
                    pygame.draw.line(screen, (75, 58, 30),
                                     (list_x, ys + row_h - 1),
                                     (list_x + list_w, ys + row_h - 1))
                    hl = self._fc.render(tier_label, True, lc)
                    screen.blit(hl, (list_x + 10, ys + (row_h - hl.get_height()) // 2))

                elif kind == "locked":
                    ls = self._fd.render("  — сделок нет —", True, (65, 55, 38))
                    screen.blit(ls, (list_x + 14, ys + (row_h - ls.get_height()) // 2))

                elif kind == "trade":
                    idx = payload
                    give_d, get_d, _ = trades[idx]
                    stock = self._stock.get(idx, 0)
                    can   = (stock > 0
                             and all(inv.count(iid) >= n for iid, n in give_d.items()))
                    out   = stock <= 0
                    sel   = (idx == self._selected)
                    hov   = pygame.Rect(list_x, ys, list_w, row_h).collidepoint(mouse_pos)

                    # Card background
                    if out:
                        bg_c = (22, 16, 10)
                        bd_c = (55, 42, 28)
                    elif sel:
                        bg_c = (58, 46, 22)
                        bd_c = (230, 185, 60)
                    elif hov:
                        bg_c = (40, 32, 16)
                        bd_c = (130, 100, 50)
                    else:
                        bg_c = (24, 18, 10)
                        bd_c = (68, 54, 32)
                    card = pygame.Rect(list_x + 3, ys + 3, list_w - 6, row_h - 6)
                    pygame.draw.rect(screen, bg_c, card, border_radius=5)
                    pygame.draw.rect(screen, bd_c, card, 1, border_radius=5)

                    # — GIVE items (left side) —
                    ix = card.x + 8
                    cy_icon = ys + (row_h - ISO) // 2
                    for iid, n in give_d.items():
                        tex = get_item_texture(iid, ISO)
                        if out:
                            tex = tex.copy()
                            tex.set_alpha(80)
                        screen.blit(tex, (ix, cy_icon))
                        item_name = ITEMS[iid].name if iid in ITEMS else iid
                        nl = self._fc.render(item_name, True,
                                             (170, 145, 95) if not out else (80, 65, 45))
                        screen.blit(nl, (ix, cy_icon + ISO + 1))
                        # Count badge
                        nc = self._fb.render(f"×{n}", True,
                                             (235, 200, 100) if not out else (90, 75, 50))
                        screen.blit(nc, (ix + ISO - nc.get_width(), cy_icon - nc.get_height() + 1))
                        # In-inventory amount
                        have = inv.count(iid)
                        hcol = (80, 200, 80) if have >= n else (200, 75, 75)
                        if out:
                            hcol = (55, 45, 35)
                        hs = self._fd.render(f"есть {have}", True, hcol)
                        screen.blit(hs, (ix, cy_icon + ISO + 12))
                        ix += ISO + 10

                    # — Arrow —
                    mid_x = card.x + card.w // 2
                    arr_s = self._fa.render("→", True,
                                            (200, 170, 50) if not out else (55, 45, 28))
                    screen.blit(arr_s, (mid_x - arr_s.get_width() // 2,
                                        ys + (row_h - arr_s.get_height()) // 2))

                    # — GET items (right side) —
                    ix = card.right - 8
                    for iid, n in reversed(list(get_d.items())):
                        ix -= ISO
                        tex = get_item_texture(iid, ISO)
                        if out:
                            tex = tex.copy()
                            tex.set_alpha(80)
                        screen.blit(tex, (ix, cy_icon))
                        item_name = ITEMS[iid].name if iid in ITEMS else iid
                        nl = self._fc.render(item_name, True,
                                             (140, 210, 140) if not out else (60, 80, 60))
                        screen.blit(nl, (ix, cy_icon + ISO + 1))
                        nc = self._fb.render(f"×{n}", True,
                                             (140, 235, 140) if not out else (60, 90, 60))
                        screen.blit(nc, (ix + ISO - nc.get_width(), cy_icon - nc.get_height() + 1))
                        ix -= 10

                    # — Stock dots —
                    dot_x = card.right - 10
                    dot_y = card.y + 6
                    for si in range(self._STOCK_PER_TRADE[1]):
                        dc = (70, 200, 70) if si < stock else (45, 35, 20)
                        pygame.draw.circle(screen, dc, (dot_x, dot_y + si * 8), 3)

                    # — Availability dot (left edge) —
                    av_col = (60, 220, 60) if can else (200, 60, 60) if not out else (55, 45, 30)
                    pygame.draw.circle(screen, av_col, (card.x + 5, ys + row_h // 2), 4)

                    if not out:
                        click_map.append((ys, ye, idx))

            y_cur += row_h

        screen.set_clip(old_clip)
        self._click_map = click_map

        # Scrollbar
        if max_sc > 0:
            ft = self._scroll_px / (content_h or 1)
            fb = (self._scroll_px + list_h) / (content_h or 1)
            sb_x  = list_x + list_w - 5
            sb_y0 = list_y0 + int(ft * list_h)
            sb_y1 = list_y0 + int(fb * list_h)
            pygame.draw.rect(screen, (45, 36, 20), (sb_x, list_y0, 4, list_h), border_radius=2)
            pygame.draw.rect(screen, (185, 150, 70), (sb_x, sb_y0, 4, max(10, sb_y1 - sb_y0)),
                             border_radius=2)

        # ── Action button for selected trade ──────────────────────────────────
        if 0 <= self._selected < len(trades) and self._selected in sel_idx:
            give_d, get_d, _ = trades[self._selected]
            stock_left = self._stock.get(self._selected, 0)
            can = (stock_left > 0
                   and all(inv.count(iid) >= n for iid, n in give_d.items()))
            btn_w = 220
            btn_h = 34
            bx = px + (PW - btn_w) // 2
            by = py + PH - btn_h - 6
            self._btn_rect = pygame.Rect(bx, by, btn_w, btn_h)
            hov_btn = self._btn_rect.collidepoint(mouse_pos)
            if can:
                btn_bg = (50, 100, 40) if hov_btn else (34, 70, 26)
                btn_bd = (100, 195, 75)
                btn_tc = (205, 245, 180)
                label  = f"Обменять  [Enter]  (+{self.TRUST_PER_TRADE} дов.)"
            elif stock_left <= 0:
                btn_bg = (35, 25, 15)
                btn_bd = (80, 60, 40)
                btn_tc = (120, 95, 70)
                label  = "Товар закончился"
            else:
                btn_bg = (50, 30, 20)
                btn_bd = (110, 70, 50)
                btn_tc = (150, 105, 80)
                label  = "Не хватает предметов"
            pygame.draw.rect(screen, btn_bg, self._btn_rect, border_radius=7)
            pygame.draw.rect(screen, btn_bd, self._btn_rect, 1, border_radius=7)
            lbl = self._fb.render(label, True, btn_tc)
            screen.blit(lbl, (self._btn_rect.centerx - lbl.get_width() // 2,
                               self._btn_rect.centery - lbl.get_height() // 2))
        else:
            self._btn_rect = None

        # Bottom hint
        hint = self._fd.render(
            "[E / Esc] закрыть   ·   ↑ ↓ навигация   ·   колесо — прокрутка",
            True, (75, 62, 42))
        screen.blit(hint, (px + PW // 2 - hint.get_width() // 2, py + PH - 18))


# ── Enchanting UI ─────────────────────────────────────────────────────────────

def _roman(n: int) -> str:
    return ["I", "II", "III", "IV", "V"][max(0, min(4, n - 1))]


class EnchantingUI:
    """Enchanting table overlay: place item + lapis → pick one of 3 enchantments."""

    SZ  = 46
    PAD = 14

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open = False

        self.item_slot:  Optional[ItemStack] = None
        self.lapis_slot: Optional[ItemStack] = None
        self.cursor:     Optional[ItemStack] = None

        # (ench_id, level, lapis_cost, xp_cost)
        self._options: List[tuple] = []

        self._item_r:   Optional[pygame.Rect] = None
        self._lapis_r:  Optional[pygame.Rect] = None
        self._opt_rects: List[pygame.Rect] = []
        self._inv_rects: List[pygame.Rect] = []
        self._hb_rects:  List[pygame.Rect] = []
        self._panel:    Optional[pygame.Rect] = None
        self._fs: Optional[pygame.font.Font] = None
        self._fm: Optional[pygame.font.Font] = None
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        SS = SLOT_STEP
        SZ = self.SZ
        cx = self.sw // 2
        cy = self.sh // 2 - 100

        self._item_r  = pygame.Rect(cx - 220, cy,          SZ, SZ)
        self._lapis_r = pygame.Rect(cx - 220, cy + SZ + 8, SZ, SZ)

        self._opt_rects = [
            pygame.Rect(cx - 160, cy + i * 48, 340, 42)
            for i in range(3)
        ]

        inv_top = cy + 3 * 48 + 20
        inv_ox  = self.sw // 2 - 9 * SS // 2
        self._inv_rects = [
            pygame.Rect(inv_ox + (i % 9) * SS, inv_top + (i // 9) * SS,
                        SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_top + GRID_ROWS * SS + 6
        self._hb_rects = [
            pygame.Rect(inv_ox + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        all_r = ([self._item_r, self._lapis_r]
                 + self._opt_rects + self._inv_rects + self._hb_rects)
        p = self.PAD
        self._panel = pygame.Rect(
            min(r.x for r in all_r) - p,
            min(r.y for r in all_r) - p - 26,
            max(r.right for r in all_r) - min(r.x for r in all_r) + p * 2,
            max(r.bottom for r in all_r) - min(r.y for r in all_r) + p * 2 + 26,
        )

    def _fonts(self):
        if self._fs is None:
            self._fs = pygame.font.SysFont(None, 18)
            self._fm = pygame.font.SysFont(None, 22)

    # ── Open / close ──────────────────────────────────────────────────────

    def open(self):
        self.is_open = True
        self._refresh_options()

    def close(self, inv: "Inventory"):
        if self.cursor:
            inv.add(self.cursor); self.cursor = None
        for attr in ("item_slot", "lapis_slot"):
            s = getattr(self, attr)
            if s:
                inv.add(s); setattr(self, attr, None)
        self.is_open = False
        self._options = []

    # ── Options generation ────────────────────────────────────────────────

    def _refresh_options(self):
        self._options = []
        if not self.item_slot:
            return
        item = self.item_slot.item
        if not item or not item.max_durability:
            return
        applicable = []
        for eid, edata in _ENCHANTS.items():
            req = edata["applicable"]
            if req is None or any(t in item.tags for t in req):
                applicable.append(eid)
        if not applicable:
            return
        import random as _rng
        rng = _rng.Random(hash(self.item_slot.item_id) ^ (self.lapis_slot.count if self.lapis_slot else 0))
        rng.shuffle(applicable)
        for tier in range(1, 4):
            eid = applicable[(tier - 1) % len(applicable)]
            lvl = min(tier, _ENCHANTS[eid]["max_lvl"])
            self._options.append((eid, lvl, tier, tier))   # lapis_cost=tier, xp_cost=tier

    # ── Apply enchantment ─────────────────────────────────────────────────

    def apply(self, idx: int, inv: "Inventory", player) -> bool:
        if idx >= len(self._options) or not self.item_slot:
            return False
        eid, lvl, lapis_cost, xp_cost = self._options[idx]
        lapis_avail = self.lapis_slot.count if self.lapis_slot else 0
        if lapis_avail < lapis_cost or player.level < xp_cost:
            return False
        # Apply
        cur = self.item_slot.enchantments.get(eid, 0)
        self.item_slot.enchantments[eid] = min(_ENCHANTS[eid]["max_lvl"], cur + lvl)
        # Consume lapis
        self.lapis_slot.count -= lapis_cost
        if self.lapis_slot.count <= 0:
            self.lapis_slot = None
        # Consume XP levels (reduce level, not raw XP)
        from world import XP_THRESHOLDS
        new_lvl = max(1, player.level - xp_cost)
        player.level = new_lvl
        player.xp = XP_THRESHOLDS[new_lvl - 1]
        import sounds as _snd
        _snd.play("craft", 0.7)
        self._refresh_options()
        return True

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event, inv: "Inventory", player) -> bool:
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_e, pygame.K_ESCAPE):
                self.close(inv); return True
            num = norm - pygame.K_1
            if 0 <= num <= 8:
                inv.selected = num; return True
        if event.type == pygame.MOUSEWHEEL:
            inv.selected = (inv.selected - event.y) % HOTBAR_N; return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            mods = pygame.key.get_mods()
            self._click(event.pos, event.button, bool(mods & pygame.KMOD_SHIFT), inv, player)
        return True

    def _click(self, pos, btn, shift, inv, player):
        if self._item_r and self._item_r.collidepoint(pos):
            self._slot_click("item", btn); self._refresh_options(); return
        if self._lapis_r and self._lapis_r.collidepoint(pos):
            if self.cursor and self.cursor.item_id != "lapis_lazuli":
                return
            self._slot_click("lapis", btn); self._refresh_options(); return
        for i, r in enumerate(self._opt_rects):
            if r.collidepoint(pos) and btn == 1:
                self.apply(i, inv, player); return
        for i, r in enumerate(self._inv_rects):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if btn == 1: self._inv_lmb(inv.slots, idx)
                elif btn == 3: self._inv_rmb(inv.slots, idx)
                return
        for i, r in enumerate(self._hb_rects):
            if r.collidepoint(pos):
                if btn == 1: self._inv_lmb(inv.slots, i)
                elif btn == 3: self._inv_rmb(inv.slots, i)
                return
        if self.cursor:
            inv.add(self.cursor); self.cursor = None

    def _get_slot(self, name):
        return self.item_slot if name == "item" else self.lapis_slot

    def _set_slot(self, name, val):
        if name == "item":  self.item_slot  = val
        else:               self.lapis_slot = val

    def _slot_click(self, name, btn):
        slot = self._get_slot(name)
        if btn == 1:
            if self.cursor is None:
                if slot and not slot.is_empty():
                    self.cursor = slot; self._set_slot(name, None)
            else:
                if slot is None or slot.is_empty():
                    self._set_slot(name, self.cursor); self.cursor = None
                elif (slot.item_id == self.cursor.item_id
                      and slot.can_merge(self.cursor)):
                    move = min(slot.max_stack - slot.count, self.cursor.count)
                    slot.count += move; self.cursor.count -= move
                    if self.cursor.count <= 0: self.cursor = None
                else:
                    self._set_slot(name, self.cursor)
                    self.cursor = slot if not slot.is_empty() else None
        elif btn == 3:
            if self.cursor is None:
                if slot and not slot.is_empty():
                    self.cursor = slot.split_half()
                    if slot.is_empty(): self._set_slot(name, None)
            else:
                if slot is None or slot.is_empty():
                    one = ItemStack(self.cursor.item_id, 1, self.cursor.durability)
                    one.enchantments = dict(self.cursor.enchantments)
                    self._set_slot(name, one)
                    self.cursor.count -= 1
                    if self.cursor.count <= 0: self.cursor = None
                elif (slot.item_id == self.cursor.item_id
                      and slot.count < slot.max_stack):
                    slot.count += 1
                    self.cursor.count -= 1
                    if self.cursor.count <= 0: self.cursor = None

    def _inv_lmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot; slots[i] = None
        else:
            if slot is None or slot.is_empty():
                slots[i] = self.cursor; self.cursor = None
            elif (slot.item_id == self.cursor.item_id
                  and slot.can_merge(self.cursor)):
                move = min(slot.max_stack - slot.count, self.cursor.count)
                slot.count += move; self.cursor.count -= move
                if self.cursor.count <= 0: self.cursor = None
            else:
                slots[i], self.cursor = self.cursor, slot

    def _inv_rmb(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot.split_half()
                if slot.is_empty(): slots[i] = None
        else:
            if slot is None or slot.is_empty():
                one = ItemStack(self.cursor.item_id, 1, self.cursor.durability)
                one.enchantments = dict(self.cursor.enchantments)
                slots[i] = one
                self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None
            elif (slot.item_id == self.cursor.item_id
                  and slot.count < slot.max_stack):
                slot.count += 1
                self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: "Inventory", mouse_pos: tuple, player):
        if not self.is_open:
            return
        self._fonts()

        # Dim
        dim = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        screen.blit(dim, (0, 0))

        # Panel
        pr = self._panel
        ps = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        ps.fill((12, 6, 22, 248))
        screen.blit(ps, pr.topleft)
        pygame.draw.rect(screen, (80, 40, 130), pr, 2)

        # Title
        title = self._fm.render("СТОЛ ЗАЧАРОВАНИЙ", True, (190, 140, 255))
        screen.blit(title, (pr.x + self.PAD, pr.y + 6))
        hint_t = self._fs.render("[E / Esc]", True, (100, 70, 160))
        screen.blit(hint_t, (pr.right - hint_t.get_width() - 8, pr.y + 8))

        # Item slot
        _draw_ui_slot(screen, self._item_r, self.item_slot, mouse_pos,
                      (50, 30, 80), (130, 70, 220))

        # Lapis slot
        _draw_ui_slot(screen, self._lapis_r, self.lapis_slot, mouse_pos,
                      (20, 30, 80), (60, 90, 220))

        lapis_n = self.lapis_slot.count if self.lapis_slot else 0
        info = self._fs.render(
            f"⬩ {lapis_n} лазурит   ✦ {player.level} LVL",
            True, (140, 170, 255),
        )
        screen.blit(info, (self._item_r.right + 8, self._item_r.y + 4))

        # Enchantment options
        for i, data in enumerate(self._options):
            eid, lvl, lap, xp = data
            r = self._opt_rects[i]
            edata = _ENCHANTS[eid]
            can = (lapis_n >= lap) and (player.level >= xp)
            bg = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            bg.fill((28, 16, 50, 220) if can else (16, 10, 30, 200))
            screen.blit(bg, r.topleft)
            bd = (150, 80, 255) if can else (70, 45, 110)
            pygame.draw.rect(screen, bd, r, 1)

            nm = f"{edata['name']} {_roman(lvl)}"
            nc = (210, 170, 255) if can else (120, 90, 160)
            ns = self._fs.render(nm, True, nc)
            ds = self._fs.render(edata["desc"], True,
                                 (145, 130, 175) if can else (90, 75, 110))
            cs = self._fs.render(f"⬩{lap}  ✦{xp}", True,
                                 (140, 220, 140) if can else (90, 130, 90))
            screen.blit(ns, (r.x + 8, r.y + 6))
            screen.blit(ds, (r.x + 8, r.y + 22))
            screen.blit(cs, (r.right - cs.get_width() - 8, r.y + (r.h - cs.get_height()) // 2))

        if not self._options:
            msg = self._fs.render(
                "Положи предмет с прочностью и лазурит", True, (130, 100, 180))
            if self._opt_rects:
                screen.blit(msg, (self._opt_rects[0].x + 8, self._opt_rects[0].y + 12))

        # Inventory grid
        _draw_enchbrew_inv(screen, self._inv_rects, self._hb_rects, inv,
                           mouse_pos, self._fs, inv.selected)

        # Cursor
        if self.cursor:
            tex = get_item_texture(self.cursor.item_id, SLOT_SIZE - 4)
            screen.blit(tex, (mouse_pos[0] - SLOT_SIZE // 2, mouse_pos[1] - SLOT_SIZE // 2))


# ── Brewing UI ────────────────────────────────────────────────────────────────

class BrewingUI:
    """Brewing stand overlay: ingredient + fuel + 3 bottle slots."""

    SZ  = 46
    PAD = 14

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open = False
        self.pos: Optional[tuple] = None

        self.fuel_slot:       Optional[ItemStack] = None
        self.ingredient_slot: Optional[ItemStack] = None
        self.bottle_slots:    List[Optional[ItemStack]] = [None, None, None]
        self.cursor:          Optional[ItemStack] = None

        self._fuel_r:    Optional[pygame.Rect] = None
        self._ingr_r:    Optional[pygame.Rect] = None
        self._bottle_rs: List[pygame.Rect] = []
        self._brew_r:    Optional[pygame.Rect] = None
        self._inv_rects: List[pygame.Rect] = []
        self._hb_rects:  List[pygame.Rect] = []
        self._panel:     Optional[pygame.Rect] = None
        self._fs: Optional[pygame.font.Font] = None
        self._fm: Optional[pygame.font.Font] = None
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        SS = SLOT_STEP
        SZ = self.SZ
        cx = self.sw // 2
        cy = self.sh // 2 - 90

        # Fuel (top-left), ingredient (top-center)
        self._fuel_r = pygame.Rect(cx - 140, cy,         SZ, SZ)
        self._ingr_r = pygame.Rect(cx - SZ // 2, cy,     SZ, SZ)

        # Brew button (arrow, center below ingredient)
        self._brew_r = pygame.Rect(cx - 18, cy + SZ + 8, 36, 28)

        # 3 bottle slots (bottom row)
        gap = 10
        total_w = 3 * SZ + 2 * gap
        x0 = cx - total_w // 2
        self._bottle_rs = [
            pygame.Rect(x0 + i * (SZ + gap), cy + SZ + 48, SZ, SZ)
            for i in range(3)
        ]

        inv_top = cy + SZ + 48 + SZ + 18
        inv_ox  = self.sw // 2 - 9 * SS // 2
        self._inv_rects = [
            pygame.Rect(inv_ox + (i % 9) * SS, inv_top + (i // 9) * SS,
                        SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_top + GRID_ROWS * SS + 6
        self._hb_rects = [
            pygame.Rect(inv_ox + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        all_r = ([self._fuel_r, self._ingr_r, self._brew_r]
                 + self._bottle_rs + self._inv_rects + self._hb_rects)
        p = self.PAD
        self._panel = pygame.Rect(
            min(r.x for r in all_r) - p,
            min(r.y for r in all_r) - p - 26,
            max(r.right for r in all_r) - min(r.x for r in all_r) + p * 2,
            max(r.bottom for r in all_r) - min(r.y for r in all_r) + p * 2 + 26,
        )

    def _fonts(self):
        if self._fs is None:
            self._fs = pygame.font.SysFont(None, 18)
            self._fm = pygame.font.SysFont(None, 22)

    # ── Open / close ──────────────────────────────────────────────────────

    def open(self, tx: int, ty: int, world):
        self.is_open = True
        self.pos = (tx, ty)
        raw = world.get_container(tx, ty)
        def _ld(d):
            if d is None: return None
            try: return ItemStack.from_dict(d)
            except Exception: return None
        self.fuel_slot       = _ld(raw[0] if len(raw) > 0 else None)
        self.ingredient_slot = _ld(raw[1] if len(raw) > 1 else None)
        for i in range(3):
            self.bottle_slots[i] = _ld(raw[2 + i] if len(raw) > 2 + i else None)

    def close(self, world, inv: "Inventory"):
        if self.cursor:
            inv.add(self.cursor); self.cursor = None
        if self.pos:
            world.save_container(self.pos[0], self.pos[1], [
                self.fuel_slot.to_dict()       if self.fuel_slot       else None,
                self.ingredient_slot.to_dict() if self.ingredient_slot else None,
            ] + [
                self.bottle_slots[i].to_dict() if self.bottle_slots[i] else None
                for i in range(3)
            ] + [None] * 22)
        self.is_open = False
        self.pos = None

    # ── Brew logic ────────────────────────────────────────────────────────

    def _can_brew(self) -> bool:
        if not self.fuel_slot or self.fuel_slot.item_id != "blaze_powder":
            return False
        if not self.ingredient_slot:
            return False
        recipe = _BREWING_RECIPES.get(self.ingredient_slot.item_id, {})
        return any(
            b and b.item_id in recipe
            for b in self.bottle_slots
        )

    def _do_brew(self):
        if not self._can_brew():
            return False
        ing_id = self.ingredient_slot.item_id
        recipe = _BREWING_RECIPES[ing_id]
        brewed = False
        for i, b in enumerate(self.bottle_slots):
            if b and b.item_id in recipe:
                rid = recipe[b.item_id]
                if rid in ITEMS:
                    self.bottle_slots[i] = ItemStack(rid, 1)
                    brewed = True
        if brewed:
            self.ingredient_slot.count -= 1
            if self.ingredient_slot.count <= 0:
                self.ingredient_slot = None
            self.fuel_slot.count -= 1
            if self.fuel_slot.count <= 0:
                self.fuel_slot = None
            import sounds as _snd
            _snd.play("craft", 0.6)
        return brewed

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event,
                     inv: "Inventory", world) -> bool:
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_e, pygame.K_ESCAPE):
                self.close(world, inv); return True
            num = norm - pygame.K_1
            if 0 <= num <= 8:
                inv.selected = num; return True
        if event.type == pygame.MOUSEWHEEL:
            inv.selected = (inv.selected - event.y) % HOTBAR_N; return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            mods = pygame.key.get_mods()
            self._click(event.pos, event.button,
                        bool(mods & pygame.KMOD_SHIFT), inv, world)
        return True

    def _click(self, pos, btn, shift, inv, world):
        # Brew button
        if self._brew_r and self._brew_r.collidepoint(pos) and btn == 1:
            self._do_brew(); return
        # Fuel slot
        if self._fuel_r and self._fuel_r.collidepoint(pos):
            if self.cursor and self.cursor.item_id != "blaze_powder":
                return
            _brewing_slot_lmb(self, "fuel", btn); return
        # Ingredient slot
        if self._ingr_r and self._ingr_r.collidepoint(pos):
            _brewing_slot_lmb(self, "ingredient", btn); return
        # Bottle slots
        for i, r in enumerate(self._bottle_rs):
            if r.collidepoint(pos):
                _brewing_bottle_lmb(self, i, btn); return
        # Inventory
        for i, r in enumerate(self._inv_rects):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if btn == 1: _brewing_inv_lmb(self, inv.slots, idx)
                elif btn == 3: _brewing_inv_rmb(self, inv.slots, idx)
                return
        for i, r in enumerate(self._hb_rects):
            if r.collidepoint(pos):
                if btn == 1: _brewing_inv_lmb(self, inv.slots, i)
                elif btn == 3: _brewing_inv_rmb(self, inv.slots, i)
                return
        if self.cursor:
            inv.add(self.cursor); self.cursor = None

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: "Inventory",
             mouse_pos: tuple, world):
        if not self.is_open:
            return
        self._fonts()

        dim = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        screen.blit(dim, (0, 0))

        pr = self._panel
        ps = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        ps.fill((10, 10, 20, 248))
        screen.blit(ps, pr.topleft)
        pygame.draw.rect(screen, (60, 55, 90), pr, 2)

        title = self._fm.render("СТОЙКА ВАРКИ", True, (170, 165, 220))
        screen.blit(title, (pr.x + self.PAD, pr.y + 6))
        hint_t = self._fs.render("[E / Esc]", True, (90, 85, 130))
        screen.blit(hint_t, (pr.right - hint_t.get_width() - 8, pr.y + 8))

        # Fuel slot
        _draw_ui_slot(screen, self._fuel_r, self.fuel_slot, mouse_pos,
                      (30, 20, 10), (180, 120, 40))
        fuel_lbl = self._fs.render("Топливо", True, (160, 120, 60))
        screen.blit(fuel_lbl, (self._fuel_r.x, self._fuel_r.bottom + 2))

        # Ingredient slot
        _draw_ui_slot(screen, self._ingr_r, self.ingredient_slot, mouse_pos,
                      (20, 25, 35), (80, 90, 160))
        ing_lbl = self._fs.render("Ингредиент", True, (130, 135, 190))
        screen.blit(ing_lbl, (self._ingr_r.x, self._ingr_r.bottom + 2))

        # Brew button
        can = self._can_brew()
        btn_col = (70, 140, 200) if can else (45, 55, 80)
        btn_bd  = (120, 200, 255) if can else (70, 80, 120)
        pygame.draw.rect(screen, btn_col, self._brew_r, border_radius=5)
        pygame.draw.rect(screen, btn_bd,  self._brew_r, 1, border_radius=5)
        # Arrow ↓
        bx, by = self._brew_r.centerx, self._brew_r.centery
        ac = (220, 240, 255) if can else (100, 110, 140)
        pygame.draw.polygon(screen, ac,
                            [(bx - 7, by - 5), (bx + 7, by - 5), (bx, by + 6)])

        # Bottle slots
        for i, r in enumerate(self._bottle_rs):
            _draw_ui_slot(screen, r, self.bottle_slots[i], mouse_pos,
                          (20, 30, 40), (60, 120, 160))

        # Brewing labels
        ing = self.ingredient_slot
        if ing and ing.item_id in _BREWING_RECIPES:
            recipe = _BREWING_RECIPES[ing.item_id]
            results = {v: True for v in recipe.values() if v in ITEMS}
            res_item = ITEMS.get(next(iter(results), ""))
            if res_item:
                res_lbl = self._fs.render(f"→ {res_item.name}", True, (180, 220, 180))
                screen.blit(res_lbl, (self._ingr_r.right + 6, self._ingr_r.y + 14))

        # Inventory
        _draw_enchbrew_inv(screen, self._inv_rects, self._hb_rects, inv,
                           mouse_pos, self._fs, inv.selected)

        # Cursor
        if self.cursor:
            tex = get_item_texture(self.cursor.item_id, SLOT_SIZE - 4)
            screen.blit(tex, (mouse_pos[0] - SLOT_SIZE // 2,
                               mouse_pos[1] - SLOT_SIZE // 2))


# ── Shared draw helpers ───────────────────────────────────────────────────────

def _draw_ui_slot(screen: pygame.Surface, r: pygame.Rect,
                  stack: Optional["ItemStack"], mouse_pos: tuple,
                  bg_col, bd_col):
    hov = r.collidepoint(mouse_pos)
    bg = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    bg.fill((*bg_col, 220) if not hov else
            (min(255, bg_col[0] + 20), min(255, bg_col[1] + 20),
             min(255, bg_col[2] + 20), 240))
    screen.blit(bg, r.topleft)
    pygame.draw.rect(screen, bd_col, r, 2 if hov else 1)
    if stack and not stack.is_empty():
        tex = get_item_texture(stack.item_id, r.w - 8)
        screen.blit(tex, (r.x + 4, r.y + 4))
        if stack.count > 1:
            fn = pygame.font.SysFont(None, 16)
            lbl = fn.render(str(stack.count), True, (255, 255, 255))
            screen.blit(lbl, (r.right - lbl.get_width() - 2, r.bottom - lbl.get_height() - 1))


def _draw_enchbrew_inv(screen: pygame.Surface,
                       inv_rects: list, hb_rects: list,
                       inv: "Inventory", mouse_pos: tuple,
                       font: pygame.font.Font, selected: int):
    """Draw player inventory grid + hotbar inside enchanting/brewing UIs."""
    for i, r in enumerate(inv_rects):
        idx = HOTBAR_N + i
        s = inv.slots[idx]
        hov = r.collidepoint(mouse_pos)
        bg = (60, 52, 40) if hov else (38, 32, 24)
        pygame.draw.rect(screen, bg, r)
        pygame.draw.rect(screen, (80, 70, 55), r, 1)
        if s and not s.is_empty():
            tex = get_item_texture(s.item_id, SLOT_SIZE - 6)
            screen.blit(tex, (r.x + 3, r.y + 3))
            if s.count > 1:
                fn = pygame.font.SysFont(None, 16)
                lbl = fn.render(str(s.count), True, (255, 255, 255))
                screen.blit(lbl, (r.right - lbl.get_width() - 2, r.bottom - lbl.get_height() - 1))
    for i, r in enumerate(hb_rects):
        s = inv.slots[i]
        sel = (i == selected)
        bg = (75, 62, 42) if sel else (38, 32, 24)
        bd = (230, 200, 100) if sel else (80, 70, 55)
        pygame.draw.rect(screen, bg, r)
        pygame.draw.rect(screen, bd, r, 2 if sel else 1)
        if s and not s.is_empty():
            tex = get_item_texture(s.item_id, SLOT_SIZE - 6)
            screen.blit(tex, (r.x + 3, r.y + 3))
            if s.count > 1:
                fn = pygame.font.SysFont(None, 16)
                lbl = fn.render(str(s.count), True, (255, 255, 255))
                screen.blit(lbl, (r.right - lbl.get_width() - 2, r.bottom - lbl.get_height() - 1))


def _brewing_slot_lmb(ui: "BrewingUI", name: str, btn: int):
    slot = ui.fuel_slot if name == "fuel" else ui.ingredient_slot
    if btn == 1:
        if ui.cursor is None:
            if slot and not slot.is_empty():
                ui.cursor = slot
                if name == "fuel":  ui.fuel_slot       = None
                else:               ui.ingredient_slot = None
        else:
            if slot is None or slot.is_empty():
                if name == "fuel":  ui.fuel_slot       = ui.cursor
                else:               ui.ingredient_slot = ui.cursor
                ui.cursor = None
            elif (slot.item_id == ui.cursor.item_id
                  and slot.can_merge(ui.cursor)):
                move = min(slot.max_stack - slot.count, ui.cursor.count)
                slot.count += move; ui.cursor.count -= move
                if ui.cursor.count <= 0: ui.cursor = None
            else:
                if name == "fuel":  ui.fuel_slot,       ui.cursor = ui.cursor, slot
                else:               ui.ingredient_slot, ui.cursor = ui.cursor, slot
    elif btn == 3:
        if ui.cursor is None:
            if slot and not slot.is_empty():
                ui.cursor = slot.split_half()
                if slot.is_empty():
                    if name == "fuel":  ui.fuel_slot       = None
                    else:               ui.ingredient_slot = None
        else:
            if slot is None or slot.is_empty():
                one = ItemStack(ui.cursor.item_id, 1, ui.cursor.durability)
                if name == "fuel":  ui.fuel_slot       = one
                else:               ui.ingredient_slot = one
                ui.cursor.count -= 1
                if ui.cursor.count <= 0: ui.cursor = None
            elif (slot.item_id == ui.cursor.item_id
                  and slot.count < slot.max_stack):
                slot.count += 1; ui.cursor.count -= 1
                if ui.cursor.count <= 0: ui.cursor = None


def _brewing_bottle_lmb(ui: "BrewingUI", i: int, btn: int):
    slot = ui.bottle_slots[i]
    if btn == 1:
        if ui.cursor is None:
            if slot and not slot.is_empty():
                ui.cursor = slot; ui.bottle_slots[i] = None
        else:
            if slot is None or slot.is_empty():
                ui.bottle_slots[i] = ui.cursor; ui.cursor = None
            elif (slot.item_id == ui.cursor.item_id
                  and slot.can_merge(ui.cursor)):
                move = min(slot.max_stack - slot.count, ui.cursor.count)
                slot.count += move; ui.cursor.count -= move
                if ui.cursor.count <= 0: ui.cursor = None
            else:
                ui.bottle_slots[i], ui.cursor = ui.cursor, slot
    elif btn == 3:
        if ui.cursor is None:
            if slot and not slot.is_empty():
                ui.cursor = slot.split_half()
                if slot.is_empty(): ui.bottle_slots[i] = None
        else:
            if slot is None or slot.is_empty():
                one = ItemStack(ui.cursor.item_id, 1, ui.cursor.durability)
                ui.bottle_slots[i] = one
                ui.cursor.count -= 1
                if ui.cursor.count <= 0: ui.cursor = None
            elif (slot.item_id == ui.cursor.item_id
                  and slot.count < slot.max_stack):
                slot.count += 1; ui.cursor.count -= 1
                if ui.cursor.count <= 0: ui.cursor = None


def _brewing_inv_lmb(ui: "BrewingUI", slots, i):
    slot = slots[i]
    if ui.cursor is None:
        if slot and not slot.is_empty():
            ui.cursor = slot; slots[i] = None
    else:
        if slot is None or slot.is_empty():
            slots[i] = ui.cursor; ui.cursor = None
        elif (slot.item_id == ui.cursor.item_id
              and slot.can_merge(ui.cursor)):
            move = min(slot.max_stack - slot.count, ui.cursor.count)
            slot.count += move; ui.cursor.count -= move
            if ui.cursor.count <= 0: ui.cursor = None
        else:
            slots[i], ui.cursor = ui.cursor, slot


def _brewing_inv_rmb(ui: "BrewingUI", slots, i):
    slot = slots[i]
    if ui.cursor is None:
        if slot and not slot.is_empty():
            ui.cursor = slot.split_half()
            if slot.is_empty(): slots[i] = None
    else:
        if slot is None or slot.is_empty():
            one = ItemStack(ui.cursor.item_id, 1, ui.cursor.durability)
            slots[i] = one
            ui.cursor.count -= 1
            if ui.cursor.count <= 0: ui.cursor = None
        elif (slot.item_id == ui.cursor.item_id
              and slot.count < slot.max_stack):
            slot.count += 1; ui.cursor.count -= 1
            if ui.cursor.count <= 0: ui.cursor = None


def get_enchants() -> Dict[str, Dict]:
    """Expose enchantment definitions to other modules."""
    return _ENCHANTS
