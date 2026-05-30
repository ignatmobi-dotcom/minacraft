"""
Item definitions and inventory stack model.

Tags drive the semantic crafting system — every item has a set of string
tags that describe its material, shape, and function.  The crafting engine
(crafting.py) reads these tags; no positions or fixed recipes needed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict


# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class ItemDef:
    """Static (immutable) description of one item type."""
    id: str
    name: str
    texture: str          # "item/stick"  or  "block/stone"
    tags: frozenset
    max_stack: int = 64
    max_durability: int = 0   # 0 = no durability (stackable consumables)
    properties: dict = field(default_factory=dict)

    def __post_init__(self):
        self.tags = frozenset(self.tags)

    def has(self, tag: str) -> bool:
        return tag in self.tags

    def get(self, prop: str, default=0):
        return self.properties.get(prop, default)


@dataclass
class ItemStack:
    """One inventory slot: an item type + count + current durability."""
    item_id: str
    count: int = 1
    durability: int = -1   # -1 → will be initialised to max_durability
    enchantments: dict = field(default_factory=dict)   # {"sharpness": 3, ...}

    def __post_init__(self):
        if self.durability == -1:
            item = ITEMS.get(self.item_id)
            self.durability = item.max_durability if item else 0

    # ── properties ───────────────────────────────────────────────────────

    @property
    def item(self) -> Optional[ItemDef]:
        return ITEMS.get(self.item_id)

    @property
    def max_stack(self) -> int:
        it = self.item
        return it.max_stack if it else 64

    # ── helpers ──────────────────────────────────────────────────────────

    def is_empty(self) -> bool:
        return self.count <= 0

    def copy(self) -> "ItemStack":
        s = ItemStack(self.item_id, self.count, self.durability)
        s.enchantments = dict(self.enchantments)
        return s

    def can_merge(self, other: "ItemStack") -> bool:
        return (other is not None
                and self.item_id == other.item_id
                and self.max_stack > 1
                and self.count < self.max_stack
                and not self.enchantments
                and not other.enchantments)

    def split_half(self) -> "ItemStack":
        half = max(1, self.count // 2)
        self.count -= half
        return ItemStack(self.item_id, half, self.durability)

    # ── serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d: dict = {"id": self.item_id, "count": self.count, "dur": self.durability}
        if self.enchantments:
            d["ench"] = self.enchantments
        return d

    @staticmethod
    def from_dict(d: dict) -> "ItemStack":
        s = ItemStack(d["id"], d["count"], d.get("dur", -1))
        s.enchantments = d.get("ench", {})
        return s


# ── Item registry ─────────────────────────────────────────────────────────────

ITEMS: Dict[str, ItemDef] = {}


def _i(id, name, texture, tags, stack=64, dur=0, **props) -> ItemDef:
    return ItemDef(id=id, name=name, texture=texture,
                   tags=frozenset(tags), max_stack=stack,
                   max_durability=dur, properties=props)


_defs = [

    # ── World blocks (mineable tiles → dropped items) ─────────────────────

    _i("oak_log",    "Дубовое бревно",  "block/oak_log",
       {"wood", "log", "fuel", "hard", "material"}),
    _i("oak_planks", "Дубовые доски",   "block/oak_planks",
       {"wood", "plank", "fuel", "material", "head_material", "tier_wood"}),
    _i("oak_leaves", "Листья дуба",     "block/oak_leaves",
       {"organic", "light", "material"}),
    _i("dirt",       "Земля",           "block/dirt",
       {"earth", "soft", "material"}),

    # ── Biome wood types ───────────────────────────────────────────────────
    _i("jungle_log",    "Тропическое бревно", "block/jungle_log",
       {"wood", "log", "fuel", "hard", "material"}),
    _i("jungle_leaves", "Листья джунглей",    "block/jungle_leaves",
       {"organic", "light", "material"}),
    _i("bamboo",        "Бамбук",             "block/bamboo_stalk",
       {"wood", "thin", "material", "fuel"}),
    _i("acacia_log",    "Акациевое бревно",   "block/acacia_log",
       {"wood", "log", "fuel", "hard", "material"}),
    _i("acacia_leaves", "Листья акации",      "block/acacia_leaves",
       {"organic", "light", "material"}),
    _i("spruce_log",    "Еловое бревно",      "block/spruce_log",
       {"wood", "log", "fuel", "hard", "material"}),
    _i("spruce_leaves", "Листья ели",         "block/spruce_leaves",
       {"organic", "light", "material"}),
    _i("mangrove_log",  "Мангровое бревно",   "block/mangrove_log",
       {"wood", "log", "fuel", "hard", "material"}),

    # ── Biome surface & decor ──────────────────────────────────────────────
    _i("podzol",              "Подзол",            "block/podzol_side",
       {"earth", "soft", "material"}),
    _i("mud",                 "Грязь",             "block/mud",
       {"earth", "soft", "material"}),
    _i("lily_pad",            "Кувшинка",          "block/lily_pad",
       {"organic", "light", "material"}),
    _i("mycelium",            "Мицелий",           "block/mycelium_side",
       {"earth", "soft", "material"}),
    _i("red_mushroom_block",  "Красный гриб",      "block/red_mushroom_block",
       {"organic", "material"}),
    _i("brown_mushroom_block","Коричневый гриб",   "block/brown_mushroom_block",
       {"organic", "material"}),
    _i("cobblestone","Булыжник",        "block/cobblestone",
       {"stone", "hard", "material", "head_material", "tier_stone"}),
    _i("stone",      "Камень",          "block/stone",
       {"stone", "hard", "material"}),
    _i("sand",       "Песок",           "block/sand",
       {"earth", "soft", "material"}),
    _i("gravel",     "Гравий",          "block/gravel",
       {"earth", "material"}),

    # ── Ores ──────────────────────────────────────────────────────────────

    _i("coal_ore",    "Угольная руда",   "block/coal_ore",
       {"stone", "ore", "material"}),
    _i("iron_ore",    "Железная руда",   "block/iron_ore",
       {"stone", "ore", "metal", "material"}),
    _i("copper_ore",  "Медная руда",     "block/copper_ore",
       {"stone", "ore", "metal", "material"}),
    _i("gold_ore",    "Золотая руда",    "block/gold_ore",
       {"stone", "ore", "metal", "material"}),
    _i("diamond_ore", "Алмазная руда",   "block/diamond_ore",
       {"stone", "ore", "gem", "material"}),

    # ── Basic raw materials ────────────────────────────────────────────────

    _i("stick",       "Палка",           "item/stick",
       {"wood", "stick", "handle", "thin", "material", "fuel"}),
    _i("flint",       "Кремень",         "item/flint",
       {"stone", "shard", "sharp", "material", "head_material", "tier_stone"}),
    _i("coal",        "Уголь",           "item/coal",
       {"carbon", "fuel", "material"}),
    _i("charcoal",    "Уголь древесный", "item/charcoal",
       {"carbon", "fuel", "wood", "material"}),
    _i("raw_iron",    "Сырое железо",    "item/raw_iron",
       {"metal", "iron", "raw", "material"}),
    _i("raw_copper",  "Сырая медь",      "item/raw_copper",
       {"metal", "copper", "raw", "material"}),
    _i("raw_gold",    "Сырое золото",    "item/raw_gold",
       {"metal", "gold", "raw", "material"}),
    _i("iron_ingot",  "Железный слиток", "item/iron_ingot",
       {"metal", "iron", "ingot", "hard", "material",
        "head_material", "armor_material", "tier_iron"}),
    _i("copper_ingot","Медный слиток",   "item/copper_ingot",
       {"metal", "copper", "ingot", "material",
        "head_material", "armor_material", "tier_copper"}),
    _i("gold_ingot",  "Золотой слиток",  "item/gold_ingot",
       {"metal", "gold", "ingot", "material",
        "head_material", "armor_material", "tier_gold"}),
    _i("diamond",     "Алмаз",           "item/diamond",
       {"gem", "diamond", "shard", "sharp", "hard", "material",
        "head_material", "armor_material", "tier_diamond"}),
    _i("netherite_ingot", "Слиток незерита", "item/netherite_ingot",
       {"metal", "netherite", "ingot", "hard", "material",
        "head_material", "armor_material", "tier_netherite"}),
    _i("leather",     "Кожа",            "item/leather",
       {"organic", "flexible", "material", "armor_material", "tier_leather"}),
    _i("bone",        "Кость",           "item/bone",
       {"organic", "hard", "material"}),
    _i("feather",     "Перо",            "item/feather",
       {"organic", "flexible", "light", "material"}),
    _i("string",      "Нить",            "item/string",
       {"organic", "flexible", "binding", "thin", "material"}),
    _i("iron_nugget", "Железный самородок","item/iron_nugget",
       {"metal", "iron", "nugget", "material"}),
    _i("gold_nugget", "Золотой самородок","item/gold_nugget",
       {"metal", "gold", "nugget", "material"}),
    _i("blaze_rod",   "Жезл Жара",       "item/blaze_rod",
       {"organic", "fuel", "handle", "magic", "material"}),
    _i("blaze_powder","Порошок Жара",    "item/blaze_powder",
       {"organic", "dust", "fuel", "magic", "material"}),
    _i("gunpowder",   "Порох",           "item/gunpowder",
       {"dust", "explosive", "material"}),
    _i("amethyst_shard","Аметистовый осколок","item/amethyst_shard",
       {"gem", "shard", "sharp", "magic", "material"}),
    _i("flint_and_steel","Огниво",       "item/flint_and_steel",
       {"metal", "stone", "tool"}, stack=1, dur=64),

    # ── Food ──────────────────────────────────────────────────────────────

    _i("apple",        "Яблоко",          "item/apple",
       {"food", "organic", "edible"}, food_value=4),
    _i("bread",        "Хлеб",            "item/bread",
       {"food", "organic", "edible"}, food_value=5),
    _i("beef",         "Сырое мясо",      "item/beef",
       {"food", "organic", "raw"}, food_value=2),
    _i("cooked_beef",  "Стейк",           "item/cooked_beef",
       {"food", "organic", "edible"}, food_value=8),
    _i("baked_potato", "Печёная картошка","item/baked_potato",
       {"food", "organic", "edible"}, food_value=5),
    _i("golden_apple", "Золотое яблоко",  "item/golden_apple",
       {"food", "organic", "edible", "magic", "gold"}, food_value=4),

    # ── Misc / craftable ──────────────────────────────────────────────────

    _i("bowl",         "Миска",           "item/bowl",
       {"wood", "hollow", "material"}),
    _i("bucket",       "Ведро",           "item/bucket",
       {"metal", "hollow", "iron", "material"}, stack=16),
    _i("book",         "Книга",           "item/book",
       {"organic", "material"}),
    _i("arrow",        "Стрела",          "item/arrow",
       {"wood", "stone", "organic", "weapon", "thin"}),
    _i("torch",        "Факел",           "block/torch",
       {"fuel", "light", "material"}),
    _i("crystal",      "Кристалл",        "item/amethyst_shard",
       {"gem", "magic", "material"}),
    _i("glowstone",    "Светящийся камень","block/glowstone",
       {"light", "stone", "material"}),
    _i("magma_block",  "Магматический блок","block/magma",
       {"stone", "hot", "material"}),

    # ── Wooden tools ──────────────────────────────────────────────────────

    _i("wooden_pickaxe","Деревянная кирка","item/wooden_pickaxe",
       {"tool", "pickaxe", "tier_wood", "wood"}, stack=1, dur=59,
       damage=2, mining_level=1),
    _i("wooden_axe",   "Деревянный топор","item/wooden_axe",
       {"tool", "axe", "tier_wood", "wood"}, stack=1, dur=59,
       damage=3, mining_level=1),
    _i("wooden_sword", "Деревянный меч",  "item/wooden_sword",
       {"weapon", "sword", "tier_wood", "wood"}, stack=1, dur=59, damage=4),
    _i("wooden_shovel","Деревянная лопата","item/wooden_shovel",
       {"tool", "shovel", "tier_wood", "wood"}, stack=1, dur=59,
       damage=2, mining_level=1),

    # ── Stone tools ───────────────────────────────────────────────────────

    _i("stone_pickaxe","Каменная кирка",  "item/stone_pickaxe",
       {"tool", "pickaxe", "tier_stone", "stone"}, stack=1, dur=131,
       damage=3, mining_level=2),
    _i("stone_axe",   "Каменный топор",  "item/stone_axe",
       {"tool", "axe", "tier_stone", "stone"}, stack=1, dur=131,
       damage=4, mining_level=2),
    _i("stone_sword", "Каменный меч",    "item/stone_sword",
       {"weapon", "sword", "tier_stone", "stone"}, stack=1, dur=131, damage=5),
    _i("stone_shovel","Каменная лопата", "item/stone_shovel",
       {"tool", "shovel", "tier_stone", "stone"}, stack=1, dur=131,
       damage=3, mining_level=2),
    _i("stone_hoe",   "Каменная мотыга", "item/stone_hoe",
       {"tool", "hoe", "tier_stone", "stone"}, stack=1, dur=131,
       damage=2, mining_level=2),

    # ── Copper tools ──────────────────────────────────────────────────────

    _i("copper_pickaxe","Медная кирка",  "item/copper_pickaxe",
       {"tool", "pickaxe", "tier_copper", "metal"}, stack=1, dur=200,
       damage=3, mining_level=2),
    _i("copper_axe",  "Медный топор",    "item/copper_axe",
       {"tool", "axe", "tier_copper", "metal"}, stack=1, dur=200,
       damage=4, mining_level=2),
    _i("copper_sword","Медный меч",      "item/copper_sword",
       {"weapon", "sword", "tier_copper", "metal"}, stack=1, dur=200, damage=5),
    _i("copper_shovel","Медная лопата",  "item/copper_shovel",
       {"tool", "shovel", "tier_copper", "metal"}, stack=1, dur=200,
       damage=3, mining_level=2),
    _i("copper_hoe",  "Медная мотыга",   "item/copper_hoe",
       {"tool", "hoe", "tier_copper", "metal"}, stack=1, dur=200,
       damage=2, mining_level=2),

    # ── Iron tools ────────────────────────────────────────────────────────

    _i("iron_pickaxe","Железная кирка",  "item/iron_pickaxe",
       {"tool", "pickaxe", "tier_iron", "metal", "iron"}, stack=1, dur=250,
       damage=4, mining_level=3),
    _i("iron_axe",    "Железный топор",  "item/iron_axe",
       {"tool", "axe", "tier_iron", "metal", "iron"}, stack=1, dur=250,
       damage=5, mining_level=3),
    _i("iron_sword",  "Железный меч",    "item/iron_sword",
       {"weapon", "sword", "tier_iron", "metal", "iron"}, stack=1, dur=250,
       damage=6),
    _i("iron_shovel", "Железная лопата", "item/iron_shovel",
       {"tool", "shovel", "tier_iron", "metal", "iron"}, stack=1, dur=250,
       damage=4, mining_level=3),
    _i("iron_hoe",    "Железная мотыга", "item/iron_hoe",
       {"tool", "hoe", "tier_iron", "metal", "iron"}, stack=1, dur=250,
       damage=3, mining_level=3),

    # ── Golden tools ──────────────────────────────────────────────────────

    _i("golden_pickaxe","Золотая кирка", "item/golden_pickaxe",
       {"tool", "pickaxe", "tier_gold", "metal", "gold"}, stack=1, dur=32,
       damage=2, mining_level=3),
    _i("golden_axe",  "Золотой топор",   "item/golden_axe",
       {"tool", "axe", "tier_gold", "metal", "gold"}, stack=1, dur=32,
       damage=3, mining_level=3),
    _i("golden_sword","Золотой меч",     "item/golden_sword",
       {"weapon", "sword", "tier_gold", "metal", "gold"}, stack=1, dur=32,
       damage=4),
    _i("golden_shovel","Золотая лопата", "item/golden_shovel",
       {"tool", "shovel", "tier_gold", "metal", "gold"}, stack=1, dur=32,
       damage=2, mining_level=3),

    # ── Diamond tools ─────────────────────────────────────────────────────

    _i("diamond_pickaxe","Алмазная кирка","item/diamond_pickaxe",
       {"tool", "pickaxe", "tier_diamond", "gem", "diamond"}, stack=1,
       dur=1561, damage=5, mining_level=4),
    _i("diamond_axe", "Алмазный топор",  "item/diamond_axe",
       {"tool", "axe", "tier_diamond", "gem", "diamond"}, stack=1,
       dur=1561, damage=6, mining_level=4),
    _i("diamond_sword","Алмазный меч",   "item/diamond_sword",
       {"weapon", "sword", "tier_diamond", "gem", "diamond"}, stack=1,
       dur=1561, damage=7),
    _i("diamond_shovel","Алмазная лопата","item/diamond_shovel",
       {"tool", "shovel", "tier_diamond", "gem", "diamond"}, stack=1,
       dur=1561, damage=5, mining_level=4),
    _i("diamond_hoe", "Алмазная мотыга", "item/diamond_hoe",
       {"tool", "hoe", "tier_diamond", "gem", "diamond"}, stack=1,
       dur=1561, damage=4, mining_level=4),

    # ── Bow ───────────────────────────────────────────────────────────────

    _i("bow",          "Лук",             "item/bow",
       {"weapon", "ranged", "organic", "wood"}, stack=1, dur=384, damage=6),

    # ── Firearms (textures: resources/custom/{id}.png) ────────────────────

    _i("bullet",   "Пуля",        "item/gunpowder",
       {"weapon", "thin", "metal", "iron", "explosive", "ammo"}, stack=9999),
    _i("shotgun",  "Дробовик",    "item/shotgun",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=240, damage=12),
    _i("deagle",       "Дигл",               "item/deagle",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=400, damage=12),
    _i("revolver",     "Револьвер",          "item/revolver",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=320, damage=10),
    _i("ak47",         "АК-47",              "item/ak47",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=600, damage=9),
    _i("uzi",          "Узи",                "item/uzi",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=440, damage=7),
    _i("mp5",          "МП-5",               "item/mp5",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=400, damage=8),
    _i("sniper_rifle", "Снайперская винтовка","item/sniper_rifle",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=360, damage=25),
    _i("flamethrower", "Огнемёт",            "item/flamethrower",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=4800, damage=6),
    _i("rpg",          "РПГ-7",              "item/rpg",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron"},
       stack=1, dur=160, damage=30),
    _i("rifle_ammo",     "Патрон",            "item/rifle_ammo",
       {"ammo", "metal", "explosive"}),
    _i("shotgun_shell",  "Дробовой патрон",   "item/shotgun_shell",
       {"ammo", "metal", "explosive"}),
    _i("rocket",         "Ракета",            "item/rocket",
       {"ammo", "explosive"}),
    _i("napalm_canister","Баллон с напалмом", "item/napalm_canister",
       {"ammo", "explosive"}),
    # Extended firearms — textures in resources/custom/item/
    _i("glock",        "Глок",               "item/glock",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron", "fast_fire"},
       stack=1, dur=360, damage=9, fire_rate=8),
    _i("gold_deagle",  "Золотой Дигл",       "item/gold_deagle",
       {"weapon", "ranged", "firearm", "metal", "gold", "tier_gold", "fire_effect"},
       stack=1, dur=300, damage=18, fire_rate=2),
    _i("minigun",      "Миниган",            "item/minigun",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron", "spinup"},
       stack=1, dur=4000, damage=6, fire_rate=60, spinup_ticks=60),
    _i("gold_minigun", "Золотой Миниган",    "item/gold_minigun",
       {"weapon", "ranged", "firearm", "metal", "gold", "tier_gold", "spinup", "fire_effect"},
       stack=1, dur=3500, damage=8, fire_rate=80, spinup_ticks=60),
    _i("diamond_minigun", "Алмазный Миниган", "item/diamond_minigun",
       {"weapon", "ranged", "firearm", "metal", "diamond", "tier_diamond", "spinup"},
       stack=1, dur=6000, damage=10, fire_rate=100, spinup_ticks=40),
    _i("m249_saw",     "Пулемёт M249 SAW",  "item/M249_SAW",
       {"weapon", "ranged", "firearm", "metal", "iron", "tier_iron", "burst"},
       stack=1, dur=1000, damage=7, fire_rate=15, burst_size=5),

    # ── Leather armor ─────────────────────────────────────────────────────

    _i("leather_helmet",    "Кожаный шлем",      "item/leather_helmet",
       {"armor", "helmet",    "tier_leather", "organic"}, stack=1, dur=55,  defense=1),
    _i("leather_chestplate","Кожаный нагрудник",  "item/leather_chestplate",
       {"armor", "chestplate","tier_leather", "organic"}, stack=1, dur=80,  defense=3),
    _i("leather_leggings",  "Кожаные штаны",      "item/leather_leggings",
       {"armor", "leggings",  "tier_leather", "organic"}, stack=1, dur=75,  defense=2),
    _i("leather_boots",     "Кожаные ботинки",    "item/leather_boots",
       {"armor", "boots",     "tier_leather", "organic"}, stack=1, dur=65,  defense=1),

    # ── Iron armor ────────────────────────────────────────────────────────

    _i("iron_helmet",     "Железный шлем",      "item/iron_helmet",
       {"armor", "helmet",    "tier_iron", "metal", "iron"}, stack=1, dur=165, defense=2),
    _i("iron_chestplate", "Железный нагрудник",  "item/iron_chestplate",
       {"armor", "chestplate","tier_iron", "metal", "iron"}, stack=1, dur=240, defense=6),
    _i("iron_leggings",   "Железные штаны",      "item/iron_leggings",
       {"armor", "leggings",  "tier_iron", "metal", "iron"}, stack=1, dur=225, defense=5),
    _i("iron_boots",      "Железные ботинки",    "item/iron_boots",
       {"armor", "boots",     "tier_iron", "metal", "iron"}, stack=1, dur=195, defense=2),

    # ── Copper armor ──────────────────────────────────────────────────────

    _i("copper_helmet",     "Медный шлем",      "item/copper_helmet",
       {"armor", "helmet",    "tier_copper", "metal", "copper"}, stack=1, dur=120, defense=2),
    _i("copper_chestplate", "Медный нагрудник",  "item/copper_chestplate",
       {"armor", "chestplate","tier_copper", "metal", "copper"}, stack=1, dur=160, defense=4),
    _i("copper_leggings",   "Медные штаны",      "item/copper_leggings",
       {"armor", "leggings",  "tier_copper", "metal", "copper"}, stack=1, dur=150, defense=3),
    _i("copper_boots",      "Медные ботинки",    "item/copper_boots",
       {"armor", "boots",     "tier_copper", "metal", "copper"}, stack=1, dur=130, defense=2),

    # ── Golden armor ──────────────────────────────────────────────────────

    _i("golden_helmet",     "Золотой шлем",      "item/golden_helmet",
       {"armor", "helmet",    "tier_gold", "metal", "gold"}, stack=1, dur=77,  defense=2),
    _i("golden_chestplate", "Золотой нагрудник",  "item/golden_chestplate",
       {"armor", "chestplate","tier_gold", "metal", "gold"}, stack=1, dur=112, defense=5),
    _i("golden_leggings",   "Золотые штаны",      "item/golden_leggings",
       {"armor", "leggings",  "tier_gold", "metal", "gold"}, stack=1, dur=105, defense=3),
    _i("golden_boots",      "Золотые ботинки",    "item/golden_boots",
       {"armor", "boots",     "tier_gold", "metal", "gold"}, stack=1, dur=91,  defense=1),

    # ── Diamond armor ─────────────────────────────────────────────────────

    _i("diamond_helmet",     "Алмазный шлем",      "item/diamond_helmet",
       {"armor", "helmet",    "tier_diamond", "gem", "diamond"}, stack=1, dur=363, defense=3),
    _i("diamond_chestplate", "Алмазный нагрудник",  "item/diamond_chestplate",
       {"armor", "chestplate","tier_diamond", "gem", "diamond"}, stack=1, dur=528, defense=8),
    _i("diamond_leggings",   "Алмазные штаны",      "item/diamond_leggings",
       {"armor", "leggings",  "tier_diamond", "gem", "diamond"}, stack=1, dur=495, defense=6),
    _i("diamond_boots",      "Алмазные ботинки",    "item/diamond_boots",
       {"armor", "boots",     "tier_diamond", "gem", "diamond"}, stack=1, dur=429, defense=3),

    # ── Craftable blocks ──────────────────────────────────────────────────

    _i("workbench", "Верстак", "block/crafting_table_front",
       {"wood", "tool", "material"}),
    _i("furnace",   "Печь",    "block/furnace_front",
       {"stone", "tool", "material"}),
    _i("chest",     "Сундук",  "block/oak_planks",
       {"wood", "material", "container"}),
    _i("barrel",    "Бочка",   "block/barrel_side",
       {"wood", "material", "container"}),
    _i("oak_door",  "Дубовая дверь", "item/oak_door",
       {"wood", "material"}),
    _i("anvil",          "Наковальня",         "block/anvil",
       {"metal", "iron", "hard", "heavy", "material"}, stack=1),
    _i("gunsmith_table", "Стол кузница",        "block/smithing_table_front",
       {"wood", "metal", "tool", "material"}),
    _i("tnt",            "TNT",                 "block/tnt_side",
       {"explosive", "material"}, stack=64),
    _i("sponge",    "Губка",   "block/sponge",
       {"organic", "soft", "material"}),
    _i("glass",     "Стекло",  "block/glass",
       {"stone", "material"}, stack=64),

    # ── Stone & world blocks (item forms) ────────────────────────────────

    _i("granite",         "Гранит",          "block/granite",
       {"stone", "hard", "material", "head_material", "tier_stone"}),
    _i("andesite",        "Андезит",         "block/andesite",
       {"stone", "hard", "material"}),
    _i("diorite",         "Диорит",          "block/diorite",
       {"stone", "hard", "material"}),
    _i("mossy_cobblestone","Замшелый булыжник","block/mossy_cobblestone",
       {"stone", "hard", "material"}),
    _i("clay_ball",       "Ком глины",       "block/clay",
       {"earth", "soft", "material"}),
    _i("sandstone",       "Песчаник",        "block/sandstone",
       {"stone", "material"}),
    _i("snowball",        "Снежок",          "block/snow",
       {"organic", "soft", "material"}),
    _i("ice",             "Лёд",             "block/ice",
       {"stone", "material"}),
    _i("cactus",          "Кактус",          "block/cactus_side",
       {"organic", "material"}),
    _i("obsidian",        "Обсидиан",        "block/obsidian",
       {"stone", "hard", "material"}),
    _i("emerald",         "Изумруд",         "item/emerald",
       {"gem", "trade", "material"}),

    # ── Nether materials ──────────────────────────────────────────────────

    _i("nether_quartz",     "Незерский кварц",           "item/quartz",
       {"gem", "material"}),
    _i("nether_scrap",      "Незеритовый скрап",         "item/netherite_scrap",
       {"metal", "netherite", "raw", "material"}),
    _i("nether_star",       "Звезда Незера",             "item/nether_star",
       {"gem", "magic", "rare", "material"}),
    _i("ghast_tear",        "Слеза гаста",               "item/ghast_tear",
       {"organic", "magic", "material"}),
    _i("netherrack",        "Незеррак",                  "block/netherrack",
       {"stone", "material"}),
    _i("nether_brick",      "Незерский кирпич",          "item/nether_brick",
       {"stone", "material"}),
    _i("soul_sand",         "Песок душ",                 "block/soul_sand",
       {"earth", "soft", "material"}),
    _i("basalt",            "Базальт",                   "block/basalt_side",
       {"stone", "hard", "material"}),
    _i("nether_wart_block", "Бородавочный блок",         "block/nether_wart_block",
       {"organic", "material"}),

    # ── Netherite tools ───────────────────────────────────────────────────

    _i("netherite_pickaxe", "Незеритовая кирка",  "item/netherite_pickaxe",
       {"tool", "pickaxe", "tier_netherite", "metal"}, stack=1, dur=2031,
       damage=6, mining_level=5),
    _i("netherite_axe",     "Незеритовый топор",  "item/netherite_axe",
       {"tool", "axe", "tier_netherite", "metal"}, stack=1, dur=2031,
       damage=10, mining_level=5),
    _i("netherite_sword",   "Незеритовый меч",    "item/netherite_sword",
       {"weapon", "sword", "tier_netherite", "metal"}, stack=1, dur=2031, damage=8),
    _i("netherite_shovel",  "Незеритовая лопата", "item/netherite_shovel",
       {"tool", "shovel", "tier_netherite", "metal"}, stack=1, dur=2031,
       damage=6, mining_level=5),
    _i("netherite_hoe",     "Незеритовая мотыга", "item/netherite_hoe",
       {"tool", "hoe", "tier_netherite", "metal"}, stack=1, dur=2031,
       damage=5, mining_level=5),

    # ── Netherite armor ───────────────────────────────────────────────────

    _i("netherite_helmet",     "Незеритовый шлем",      "item/netherite_helmet",
       {"armor", "helmet",     "tier_netherite", "metal"}, stack=1, dur=407, defense=3),
    _i("netherite_chestplate", "Незеритовый нагрудник",  "item/netherite_chestplate",
       {"armor", "chestplate", "tier_netherite", "metal"}, stack=1, dur=592, defense=8),
    _i("netherite_leggings",   "Незеритовые штаны",      "item/netherite_leggings",
       {"armor", "leggings",   "tier_netherite", "metal"}, stack=1, dur=555, defense=6),
    _i("netherite_boots",      "Незеритовые ботинки",    "item/netherite_boots",
       {"armor", "boots",      "tier_netherite", "metal"}, stack=1, dur=481, defense=3),

    # ── Alloy ingots ─────────────────────────────────────────────────────

    _i("bronze_ingot", "Бронзовый слиток", "item/copper_ingot",
       {"metal", "bronze", "ingot", "hard", "material",
        "head_material", "armor_material", "tier_bronze"}),
    _i("steel_ingot",  "Стальной слиток",  "item/iron_ingot",
       {"metal", "steel", "ingot", "hard", "material",
        "head_material", "armor_material", "tier_steel"}),

    # ── Bronze tools ─────────────────────────────────────────────────────

    _i("bronze_pickaxe","Бронзовая кирка",  "item/copper_pickaxe",
       {"tool", "pickaxe", "tier_bronze", "metal"}, stack=1, dur=180,
       damage=3, mining_level=2),
    _i("bronze_axe",   "Бронзовый топор",  "item/copper_axe",
       {"tool", "axe",     "tier_bronze", "metal"}, stack=1, dur=180,
       damage=4, mining_level=2),
    _i("bronze_sword", "Бронзовый меч",    "item/copper_sword",
       {"weapon", "sword", "tier_bronze", "metal"}, stack=1, dur=180, damage=5),
    _i("bronze_shovel","Бронзовая лопата", "item/copper_shovel",
       {"tool", "shovel",  "tier_bronze", "metal"}, stack=1, dur=180,
       damage=3, mining_level=2),

    # ── Steel tools ──────────────────────────────────────────────────────

    _i("steel_pickaxe","Стальная кирка",   "item/iron_pickaxe",
       {"tool", "pickaxe", "tier_steel", "metal"}, stack=1, dur=400,
       damage=5, mining_level=3),
    _i("steel_axe",   "Стальной топор",   "item/iron_axe",
       {"tool", "axe",     "tier_steel", "metal"}, stack=1, dur=400,
       damage=6, mining_level=3),
    _i("steel_sword", "Стальной меч",     "item/iron_sword",
       {"weapon", "sword", "tier_steel", "metal"}, stack=1, dur=400, damage=7),
    _i("steel_shovel","Стальная лопата",  "item/iron_shovel",
       {"tool", "shovel",  "tier_steel", "metal"}, stack=1, dur=400,
       damage=5, mining_level=3),

    # ── Bronze armor ─────────────────────────────────────────────────────

    _i("bronze_helmet",     "Бронзовый шлем",      "item/copper_helmet",
       {"armor", "helmet",     "tier_bronze", "metal"}, stack=1, dur=140, defense=2),
    _i("bronze_chestplate", "Бронзовый нагрудник",  "item/copper_chestplate",
       {"armor", "chestplate", "tier_bronze", "metal"}, stack=1, dur=190, defense=5),
    _i("bronze_leggings",   "Бронзовые штаны",      "item/copper_leggings",
       {"armor", "leggings",   "tier_bronze", "metal"}, stack=1, dur=175, defense=4),
    _i("bronze_boots",      "Бронзовые ботинки",    "item/copper_boots",
       {"armor", "boots",      "tier_bronze", "metal"}, stack=1, dur=155, defense=2),

    # ── Steel armor ──────────────────────────────────────────────────────

    _i("steel_helmet",     "Стальной шлем",      "item/iron_helmet",
       {"armor", "helmet",     "tier_steel", "metal"}, stack=1, dur=330, defense=3),
    _i("steel_chestplate", "Стальной нагрудник",  "item/iron_chestplate",
       {"armor", "chestplate", "tier_steel", "metal"}, stack=1, dur=480, defense=7),
    _i("steel_leggings",   "Стальные штаны",      "item/iron_leggings",
       {"armor", "leggings",   "tier_steel", "metal"}, stack=1, dur=450, defense=6),
    _i("steel_boots",      "Стальные ботинки",    "item/iron_boots",
       {"armor", "boots",      "tier_steel", "metal"}, stack=1, dur=390, defense=3),

    # ── Enchanting / Brewing blocks ───────────────────────────────────────

    _i("enchanting_table", "Стол зачарований", "block/enchanting_table_top",
       {"wood", "magic", "furniture"}),
    _i("brewing_stand", "Стойка варки", "block/brewing_stand",
       {"metal", "magic", "furniture"}),
    _i("lapis_lazuli", "Лазурит", "item/lapis_lazuli",
       {"gem", "magic", "material"}),

    # ── Potion ingredients ────────────────────────────────────────────────

    _i("nether_wart",    "Адский нарост",      "item/nether_wart",
       {"organic", "magic", "material"}),
    _i("spider_eye",     "Паучий глаз",        "item/spider_eye",
       {"organic", "poison", "material"}),
    _i("fermented_spider_eye", "Сброженный глаз", "item/fermented_spider_eye",
       {"organic", "poison", "magic", "material"}),
    _i("sugar",          "Сахар",              "item/sugar",
       {"organic", "material"}),
    _i("glistering_melon_slice", "Блестящий ломтик дыни", "item/glistering_melon_slice",
       {"organic", "gold", "magic", "material"}),
    _i("golden_carrot",  "Золотая морковь",    "item/golden_carrot",
       {"food", "organic", "gold", "magic", "material"}, food_value=6),
    _i("magma_cream",    "Магмовый крем",      "item/magma_cream",
       {"organic", "hot", "magic", "material"}),

    # ── Bottles & Potions ─────────────────────────────────────────────────

    _i("glass_bottle",   "Стеклянная бутылочка", "item/glass_bottle",
       {"glass", "hollow", "material"}, stack=16),
    _i("water_bottle",   "Водяная бутылка",    "item/potion",
       {"liquid", "material"}, stack=16),
    _i("awkward_potion", "Неловкое зелье",     "item/potion",
       {"liquid", "potion", "material"}, stack=16),

    _i("speed_potion",   "Зелье скорости",          "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="speed",           effect_dur=30,  effect_lvl=1),
    _i("strength_potion","Зелье силы",              "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="strength",        effect_dur=30,  effect_lvl=1),
    _i("regen_potion",   "Зелье регенерации",       "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="regen",           effect_dur=45,  effect_lvl=1),
    _i("fire_resistance_potion","Зелье огнестойкости","item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="fire_resistance", effect_dur=180, effect_lvl=1),
    _i("night_vision_potion","Зелье ночного зрения","item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="night_vision",    effect_dur=180, effect_lvl=1),
    _i("healing_potion", "Зелье лечения",           "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="healing",         effect_dur=0,   effect_lvl=4),
    _i("poison_potion",  "Зелье яда",               "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="poison",          effect_dur=45,  effect_lvl=1),
    _i("harming_potion", "Зелье вреда",             "item/potion",
       {"liquid", "potion", "consumable"}, stack=16,
       effect="harming",         effect_dur=0,   effect_lvl=3),

    _i("splash_poison",  "Плескат. зелье яда",      "item/splash_potion",
       {"liquid", "potion", "throwable"}, stack=16,
       effect="poison",   effect_dur=20, effect_lvl=1),
    _i("splash_harming", "Плескат. зелье вреда",    "item/splash_potion",
       {"liquid", "potion", "throwable"}, stack=16,
       effect="harming",  effect_dur=0,  effect_lvl=3),
    _i("splash_strength","Плескат. зелье силы",     "item/splash_potion",
       {"liquid", "potion", "throwable"}, stack=16,
       effect="strength", effect_dur=30, effect_lvl=1),

    # ── Redstone ─────────────────────────────────────────────────────────────
    _i("redstone",       "Красный камень",       "item/redstone",
       {"material", "redstone"}, stack=64),
    _i("redstone_torch", "Факел из красного камня", "block/redstone_torch",
       {"functional", "redstone"}, stack=64),
    _i("lever",          "Рычаг",                 "block/lever",
       {"functional", "redstone"}, stack=64),
    _i("stone_button",   "Каменная кнопка",       "block/stone_button",
       {"functional", "redstone"}, stack=64),
    _i("wooden_button",  "Деревянная кнопка",     "block/oak_planks",
       {"functional", "redstone"}, stack=64),
    _i("pressure_plate",        "Каменная плита давления",  "block/stone",
       {"functional", "redstone"}, stack=64),
    _i("wooden_pressure_plate", "Деревянная плита давления","block/oak_planks",
       {"functional", "redstone"}, stack=64),

    # ── Boss items ────────────────────────────────────────────────────────────
    _i("crown_fragment", "Фрагмент Короны",  "item/gold_ingot",
       {"boss_summon", "rare"}, stack=1),
    _i("earth_rune",     "Земная Руна",      "item/amethyst_shard",
       {"boss_summon", "rare"}, stack=1),
    _i("king_blade",     "Клинок Короля",    "item/diamond_sword",
       {"sword", "sharp", "tool", "weapon", "tier_diamond"}, stack=1, dur=800,
       damage=8),
    _i("golem_heart",    "Сердце Голема",    "item/amethyst_shard",
       {"material", "rare", "magic"}, stack=1),

    # ── End items ─────────────────────────────────────────────────────────────
    _i("ender_pearl",   "Жемчуг Края",       "item/ender_pearl",
       {"material", "rare", "magic"}, stack=16),
    _i("blaze_powder",  "Пыль Огня",         "item/blaze_powder",
       {"material", "fuel"}, stack=64),
    _i("eye_of_ender",  "Глаз Края",         "item/ender_eye",
       {"material", "rare", "magic"}, stack=16),
    _i("dragon_egg",    "Яйцо Дракона",      "item/dragon_egg",
       {"rare", "trophy"}, stack=1),
    _i("end_stone",     "Камень Края",       "block/end_stone",
       {"stone", "material"}, stack=64),
    _i("purpur_block",  "Пурпурный блок",    "block/purpur_block",
       {"stone", "material"}, stack=64),

]

for _item in _defs:
    ITEMS[_item.id] = _item


def register_discovered(item_def: "ItemDef"):
    """Register a mystery item generated by the crafting engine."""
    ITEMS[item_def.id] = item_def


# ── Tier metadata (used by crafting.py) ──────────────────────────────────────

# tag → (display_name, item_prefix, tool_dur, armor_scale, damage_bonus)
TIERS: Dict[str, tuple] = {
    "tier_leather":   ("кожаный",    "leather",  80,    1.0,  0),
    "tier_wood":      ("деревянный", "wooden",   59,    0.8,  0),
    "tier_stone":     ("каменный",   "stone",    131,   1.2,  1),
    "tier_copper":    ("медный",     "copper",   200,   1.5,  1),
    "tier_bronze":    ("бронзовый",  "bronze",   180,   1.6,  1),
    "tier_iron":      ("железный",   "iron",     250,   2.0,  2),
    "tier_steel":     ("стальной",   "steel",    400,   2.8,  3),
    "tier_gold":      ("золотой",    "golden",   32,    1.4,  0),
    "tier_diamond":   ("алмазный",   "diamond",  1561,  4.0,  3),
    "tier_netherite": ("незеритовый","netherite", 2031, 5.0,  4),
}
