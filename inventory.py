"""
Inventory, hotbar, and drag-and-drop UI — Minecraft-style.

Slot layout (45 total):
  [0..8]   hotbar  (always visible at bottom)
  [9..44]  4×9 grid (shown when open with E)

Controls:
  E          — toggle inventory
  1-9        — select hotbar slot
  Scroll     — cycle hotbar
  LMB slot   — pick up / put down full stack
  RMB slot   — pick up / put down single item
  Shift+LMB  — quick-transfer between hotbar ↔ grid
"""
from __future__ import annotations
import pygame
from typing import Optional, List

import keys as _keys
from items import ItemStack, ITEMS
from assets import get_item_texture

# ── Layout constants ───────────────────────────────────────────────────────────

SLOT_SIZE  = 40    # inner content area (px)
SLOT_STEP  = 44    # slot_size + 4 px gap
HOTBAR_N   = 9
GRID_ROWS  = 4
GRID_COLS  = 9
GRID_N     = GRID_ROWS * GRID_COLS   # 36
TOTAL_N    = HOTBAR_N + GRID_N       # 45

# Armor slot indices (appended after TOTAL_N)
ARMOR_HELMET     = TOTAL_N      # 36
ARMOR_CHESTPLATE = TOTAL_N + 1  # 37
ARMOR_LEGGINGS   = TOTAL_N + 2  # 38
ARMOR_BOOTS      = TOTAL_N + 3  # 39
ARMOR_SLOTS      = [ARMOR_HELMET, ARMOR_CHESTPLATE, ARMOR_LEGGINGS, ARMOR_BOOTS]
ARMOR_TAGS       = ["helmet", "chestplate", "leggings", "boots"]
ARMOR_LABELS     = ["Шлем", "Нагрудник", "Поножи", "Сапоги"]
ARMOR_TOTAL      = TOTAL_N + 4  # 40


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dur_color(ratio: float) -> tuple:
    if ratio > 0.6:
        return (70, 210, 40)
    if ratio > 0.3:
        return (220, 200, 30)
    return (210, 50, 30)


# ── Data model ─────────────────────────────────────────────────────────────────

class Inventory:
    """49 item stacks: hotbar[0:9] + grid[9:45] + armor[45:49]."""

    def __init__(self):
        self.slots: List[Optional[ItemStack]] = [None] * ARMOR_TOTAL
        self.selected: int = 0
        self.off_hand: Optional[ItemStack] = None

    # ── Accessors ─────────────────────────────────────────────────────────

    @property
    def held(self) -> Optional[ItemStack]:
        return self.slots[self.selected]

    def has_item(self, item_id: str) -> bool:
        return any(s and s.item_id == item_id for s in self.slots)

    def count(self, item_id: str) -> int:
        """Total count of item_id across all slots."""
        return sum(s.count for s in self.slots if s and s.item_id == item_id)

    def remove(self, item_id: str, amount: int) -> bool:
        """Remove up to amount of item_id. Returns True if fully removed."""
        remaining = amount
        for i in range(TOTAL_N):
            s = self.slots[i]
            if s and s.item_id == item_id and remaining > 0:
                take = min(s.count, remaining)
                s.count -= take
                remaining -= take
                if s.count <= 0:
                    self.slots[i] = None
        return remaining == 0

    @property
    def defense(self) -> int:
        """Total defense from equipped armor."""
        total = 0
        for idx in ARMOR_SLOTS:
            s = self.slots[idx]
            if s and s.item:
                total += s.item.properties.get("defense", 0)
        return total

    def _armor_slot_for(self, item_id: str) -> Optional[int]:
        """Return the armor slot index that accepts this item, or None."""
        from items import ITEMS
        item = ITEMS.get(item_id)
        if item is None:
            return None
        for slot_idx, tag in zip(ARMOR_SLOTS, ARMOR_TAGS):
            if tag in item.tags:
                return slot_idx
        return None

    def equip_armor(self, inv_idx: int) -> bool:
        """Move the item at inv_idx to its armor slot. Returns True if equipped."""
        stack = self.slots[inv_idx]
        if not stack or stack.is_empty():
            return False
        armor_slot = self._armor_slot_for(stack.item_id)
        if armor_slot is None:
            return False
        # Swap: put old armor back into inv
        old = self.slots[armor_slot]
        self.slots[armor_slot] = stack
        self.slots[inv_idx] = old
        return True

    # ── Mutation ──────────────────────────────────────────────────────────

    def add(self, stack: ItemStack) -> bool:
        """
        Insert stack into inventory (merge first, then empty slots).
        Returns True if fully placed.
        """
        remaining = stack.count

        # Pass 1: merge into matching stacks
        for i in range(TOTAL_N):
            s = self.slots[i]
            if s and s.item_id == stack.item_id and s.can_merge(stack):
                space     = s.max_stack - s.count
                move      = min(space, remaining)
                s.count  += move
                remaining -= move
                if remaining == 0:
                    return True

        # Pass 2: empty slots
        it_def = ITEMS.get(stack.item_id)
        ms     = it_def.max_stack if it_def else 64
        for i in range(TOTAL_N):
            if self.slots[i] is None and remaining > 0:
                take            = min(ms, remaining)
                self.slots[i]   = ItemStack(stack.item_id, take, stack.durability)
                remaining      -= take
                if remaining == 0:
                    return True

        stack.count = remaining
        return False

    def consume_held(self, count: int = 1):
        s = self.slots[self.selected]
        if s:
            s.count -= count
            if s.count <= 0:
                self.slots[self.selected] = None

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "selected": self.selected,
            "slots": [s.to_dict() if s else None for s in self.slots],
            "off_hand": self.off_hand.to_dict() if self.off_hand else None,
        }

    @staticmethod
    def from_dict(d: dict) -> "Inventory":
        inv = Inventory()
        inv.selected = d.get("selected", 0)
        for i, sd in enumerate(d.get("slots", [])):
            if i < ARMOR_TOTAL and sd:
                inv.slots[i] = ItemStack.from_dict(sd)
        oh = d.get("off_hand")
        if oh:
            try:
                inv.off_hand = ItemStack.from_dict(oh)
            except Exception:
                pass
        return inv


# ── UI controller ──────────────────────────────────────────────────────────────

class InventoryUI:
    """Handles rendering and mouse/keyboard interaction for the inventory."""

    def __init__(self, inventory: Inventory, sw: int, sh: int):
        self.inv    = inventory
        self.sw     = sw
        self.sh     = sh
        self.open   = False

        self.cursor: Optional[ItemStack] = None   # item being dragged on mouse

        self._fs: Optional[pygame.font.Font] = None   # small  (~18 px)
        self._ft: Optional[pygame.font.Font] = None   # tiny   (~14 px)
        self._panel_surf: Optional[pygame.Surface] = None

        self._hr: List[pygame.Rect] = []   # hotbar rects
        self._gr: List[pygame.Rect] = []   # grid   rects
        self._ar: List[pygame.Rect] = []   # armor  rects
        self._rebuild()

    # ── Layout ────────────────────────────────────────────────────────────

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._panel_surf = None
        self._rebuild()

    def _rebuild(self):
        SS   = SLOT_STEP
        ox   = self.sw // 2 - HOTBAR_N * SS // 2
        hb_y = self.sh - SS - 8
        self._hr = [
            pygame.Rect(ox + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        gr_y = hb_y - GRID_ROWS * SS - 18
        self._gr = [
            pygame.Rect(ox + (i % GRID_COLS) * SS,
                        gr_y + (i // GRID_COLS) * SS,
                        SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        # Armor slots: single column to the left of the grid
        armor_x = ox - SS - 6
        self._ar = [
            pygame.Rect(armor_x, gr_y + i * SS, SLOT_SIZE, SLOT_SIZE)
            for i in range(4)
        ]

    def _fonts(self):
        if self._fs is None:
            self._fs = pygame.font.SysFont(None, 18)
            self._ft = pygame.font.SysFont(None, 14)

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed by the inventory."""

        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm == pygame.K_e:
                self.open = not self.open
                if not self.open and self.cursor:
                    self.inv.add(self.cursor)
                    self.cursor = None
                return True
            num = norm - pygame.K_1
            if 0 <= num <= 8:
                self.inv.selected = num
                return True

        if event.type == pygame.MOUSEWHEEL:
            self.inv.selected = (self.inv.selected - event.y) % HOTBAR_N
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            mods  = pygame.key.get_mods()
            shift = bool(mods & pygame.KMOD_SHIFT)
            return self._click(event.pos, event.button, shift)

        return False

    def _click(self, pos: tuple, btn: int, shift: bool) -> bool:
        idx = self._hit(pos)

        if idx is None:
            # Outside all slots — return cursor to inventory
            if btn == 1 and self.cursor:
                self.inv.add(self.cursor)
                self.cursor = None
            return False

        if shift and btn == 1:
            self._quick_move(idx)
            return True

        slot = self.inv.slots[idx]
        if btn == 1:
            self._lmb(idx, slot)
        elif btn == 3:
            self._rmb(idx, slot)
        return True

    def _lmb(self, idx: int, slot: Optional[ItemStack]):
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor      = slot
                self.inv.slots[idx] = None
        else:
            # Armor slots only accept matching armor type
            if idx in ARMOR_SLOTS and self.inv._armor_slot_for(self.cursor.item_id) != idx:
                return
            if slot is None or slot.is_empty():
                self.inv.slots[idx] = self.cursor
                self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                space             = slot.max_stack - slot.count
                move              = min(space, self.cursor.count)
                slot.count       += move
                self.cursor.count -= move
                if self.cursor.count <= 0:
                    self.cursor = None
            else:
                self.inv.slots[idx] = self.cursor
                self.cursor = slot if not slot.is_empty() else None

    def _rmb(self, idx: int, slot: Optional[ItemStack]):
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot.split_half()
                if slot.is_empty():
                    self.inv.slots[idx] = None
        else:
            if idx in ARMOR_SLOTS and self.inv._armor_slot_for(self.cursor.item_id) != idx:
                return
            if slot is None or slot.is_empty():
                self.inv.slots[idx] = ItemStack(self.cursor.item_id, 1,
                                                self.cursor.durability)
                self.cursor.count -= 1
                if self.cursor.count <= 0:
                    self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                slot.count       += 1
                self.cursor.count -= 1
                if self.cursor.count <= 0:
                    self.cursor = None

    def _quick_move(self, idx: int):
        stack = self.inv.slots[idx]
        if not stack or stack.is_empty():
            return

        # Armor slot → unequip back to inventory/hotbar
        if idx in ARMOR_SLOTS:
            for i in list(range(HOTBAR_N, TOTAL_N)) + list(range(HOTBAR_N)):
                if self.inv.slots[i] is None:
                    self.inv.slots[i]   = stack
                    self.inv.slots[idx] = None
                    return
            return

        # Item with armor tag → equip to its armor slot
        armor_slot = self.inv._armor_slot_for(stack.item_id)
        if armor_slot is not None:
            self.inv.equip_armor(idx)
            return

        # Normal hotbar ↔ grid transfer
        targets = range(HOTBAR_N, TOTAL_N) if idx < HOTBAR_N else range(HOTBAR_N)

        # Try merging first
        for i in targets:
            s = self.inv.slots[i]
            if s and s.item_id == stack.item_id and s.can_merge(stack):
                space       = s.max_stack - s.count
                move        = min(space, stack.count)
                s.count    += move
                stack.count -= move
                if stack.count <= 0:
                    self.inv.slots[idx] = None
                    return

        # Then find an empty slot
        for i in targets:
            if self.inv.slots[i] is None:
                self.inv.slots[i]   = stack
                self.inv.slots[idx] = None
                return

    def _hit(self, pos) -> Optional[int]:
        for i, r in enumerate(self._hr):
            if r.collidepoint(pos):
                return i
        if self.open:
            for i, r in enumerate(self._ar):
                if r.collidepoint(pos):
                    return ARMOR_SLOTS[i]
            for i, r in enumerate(self._gr):
                if r.collidepoint(pos):
                    return HOTBAR_N + i
        return None

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, mouse_pos: tuple,
             skip_hotbar: bool = False):
        self._fonts()

        if self.open:
            self._draw_grid_panel(screen)
            for i, rect in enumerate(self._ar):
                self._draw_armor_slot(screen, rect,
                                      self.inv.slots[ARMOR_SLOTS[i]],
                                      ARMOR_LABELS[i])
            for i, rect in enumerate(self._gr):
                self._draw_slot(screen, rect, self.inv.slots[HOTBAR_N + i])

        if not skip_hotbar:
            self._draw_hotbar_bg(screen)
            for i, rect in enumerate(self._hr):
                self._draw_slot(screen, rect, self.inv.slots[i],
                                selected=(i == self.inv.selected))
            # Held-item display (bottom-right corner, large icon)
            self._draw_hand(screen)

        # Dragged item follows cursor
        if self.cursor and not self.cursor.is_empty():
            self._draw_item_at(screen, self.cursor,
                               mouse_pos[0] - SLOT_SIZE // 2,
                               mouse_pos[1] - SLOT_SIZE // 2,
                               shadow=True)

        # Tooltip on hovered slot
        self._draw_tooltip(screen, mouse_pos)

    # ── Draw helpers ──────────────────────────────────────────────────────

    def _draw_hotbar_bg(self, screen: pygame.Surface):
        if not self._hr:
            return
        r0, r8 = self._hr[0], self._hr[-1]
        bg = pygame.Rect(r0.x - 4, r0.y - 4, r8.right - r0.x + 8, r0.h + 8)
        ov = pygame.Surface((bg.w, bg.h), pygame.SRCALPHA)
        ov.fill((18, 18, 18, 185))
        screen.blit(ov, bg.topleft)
        pygame.draw.rect(screen, (70, 70, 70), bg, 1)

    def _draw_grid_panel(self, screen: pygame.Surface):
        if not self._gr:
            return
        all_rects = list(self._gr) + list(self._ar)
        min_x = min(r.x for r in all_rects)
        min_y = min(r.y for r in all_rects)
        max_x = max(r.right for r in all_rects)
        max_y = max(r.bottom for r in all_rects)
        pad = 10
        bg  = pygame.Rect(min_x - pad, min_y - pad - 20,
                          max_x - min_x + pad * 2,
                          max_y - min_y + pad * 2 + 20)
        if (self._panel_surf is None
                or self._panel_surf.get_size() != (bg.w, bg.h)):
            self._panel_surf = pygame.Surface((bg.w, bg.h), pygame.SRCALPHA)
            self._panel_surf.fill((18, 18, 18, 210))
        screen.blit(self._panel_surf, bg.topleft)
        pygame.draw.rect(screen, (80, 80, 80), bg, 2)
        lbl = self._fs.render("Инвентарь", True, (180, 180, 180))
        screen.blit(lbl, (bg.x + 6, bg.y + 4))
        # "Броня" label above armor column
        if self._ar:
            albl = self._fs.render("Броня", True, (140, 140, 200))
            screen.blit(albl, (self._ar[0].x + SLOT_SIZE // 2 - albl.get_width() // 2,
                                bg.y + 4))

    def _draw_slot(self, screen: pygame.Surface, rect: pygame.Rect,
                   stack: Optional[ItemStack], selected: bool = False):
        bg  = (72, 62, 48) if selected else (42, 42, 42)
        bdr = (255, 215, 50) if selected else (70, 70, 70)
        pygame.draw.rect(screen, bg,  rect)
        pygame.draw.rect(screen, bdr, rect, 2 if selected else 1)
        if stack and not stack.is_empty():
            self._draw_item_at(screen, stack, rect.x + 4, rect.y + 4)

    def _draw_armor_slot(self, screen: pygame.Surface, rect: pygame.Rect,
                         stack: Optional[ItemStack], label: str):
        pygame.draw.rect(screen, (35, 35, 55), rect)
        pygame.draw.rect(screen, (80, 80, 130), rect, 1)
        if stack and not stack.is_empty():
            self._draw_item_at(screen, stack, rect.x + 4, rect.y + 4)
        else:
            lbl = self._ft.render(label, True, (85, 85, 130))
            screen.blit(lbl, (rect.x + rect.w // 2 - lbl.get_width() // 2,
                               rect.y + rect.h // 2 - lbl.get_height() // 2))

    def _draw_item_at(self, screen: pygame.Surface, stack: ItemStack,
                      x: int, y: int, shadow: bool = False):
        size = SLOT_SIZE - 8
        tex  = get_item_texture(stack.item_id, size)

        if shadow:
            sh_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            sh_surf.fill((0, 0, 0, 55))
            screen.blit(sh_surf, (x + 2, y + 2))

        screen.blit(tex, (x, y))

        # Stack count (bottom-right, with shadow)
        if stack.count > 1:
            num = str(stack.count)
            shd = self._ft.render(num, True, (0, 0, 0))
            txt = self._ft.render(num, True, (255, 255, 255))
            nx  = x + size - txt.get_width() + 1
            ny  = y + size - txt.get_height() + 1
            screen.blit(shd, (nx + 1, ny + 1))
            screen.blit(txt, (nx, ny))

        # Durability bar (2 px, below item, colour-coded)
        item = stack.item
        if item and item.max_durability > 0 and stack.durability < item.max_durability:
            ratio = max(0.0, stack.durability / item.max_durability)
            by    = y + size + 1
            pygame.draw.rect(screen, (20, 12, 12), (x, by, size, 2))
            fill_w = max(1, int(size * ratio))
            pygame.draw.rect(screen, _dur_color(ratio), (x, by, fill_w, 2))

    def _draw_hand(self, screen: pygame.Surface):
        """Large icon in the bottom-right corner showing the held item,
        and bottom-left corner showing the off-hand item."""
        size = 52
        margin = 14
        held = self.inv.held
        if held and not held.is_empty():
            x = self.sw - size - margin
            y = self.sh - size - SLOT_STEP - margin - 10
            tex = get_item_texture(held.item_id, size)
            panel = pygame.Surface((size + 8, size + 8), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 80))
            screen.blit(panel, (x - 4, y - 4))
            screen.blit(tex, (x, y))
            name_surf = self._fs.render(held.item.name if held.item else held.item_id,
                                        True, (230, 230, 230))
            nx = x + size // 2 - name_surf.get_width() // 2
            screen.blit(name_surf, (nx, y + size + 2))

        off = self.inv.off_hand
        if off and not off.is_empty():
            x = margin
            y = self.sh - size - SLOT_STEP - margin - 10
            tex = get_item_texture(off.item_id, size)
            panel = pygame.Surface((size + 8, size + 8), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 80))
            screen.blit(panel, (x - 4, y - 4))
            screen.blit(tex, (x, y))
            lbl = self._fs.render("[вт. рука]", True, (160, 160, 160))
            screen.blit(lbl, (x + size // 2 - lbl.get_width() // 2, y + size + 2))

    def _draw_tooltip(self, screen: pygame.Surface, mouse_pos: tuple):
        idx = self._hit(mouse_pos)
        if idx is None:
            return
        stack = self.inv.slots[idx]
        if not stack or stack.is_empty():
            return
        item = stack.item
        if item is None:
            return

        lines: List[str] = [item.name]
        # Enchantments — shown in purple
        _ench_lines: List[str] = []
        if stack.enchantments:
            try:
                from crafting import get_enchants
                _ench_defs = get_enchants()
            except Exception:
                _ench_defs = {}
            for eid, elvl in stack.enchantments.items():
                edata = _ench_defs.get(eid, {})
                roman = ["I","II","III","IV","V"][max(0, min(4, elvl - 1))]
                _ench_lines.append(f"  {edata.get('name', eid)} {roman}")
        p = item.properties
        if item.max_durability > 0:
            lines.append(f"Прочность: {stack.durability}/{item.max_durability}")
        if p.get("damage"):
            lines.append(f"Урон: {p['damage']}")
        if p.get("defense"):
            lines.append(f"Защита: {p['defense']}")
        if p.get("food_value"):
            lines.append(f"Еда +{p['food_value']} ❤")
        if p.get("effect"):
            dur = p.get("effect_dur", 0)
            lines.append(f"Эффект: {p['effect']}" + (f" ({dur}с)" if dur else ""))
        if p.get("mining_level"):
            lvl = ["Ничего","Дерево","Камень","Железо","Алмаз"][p["mining_level"]]
            lines.append(f"Уровень добычи: {lvl}")
        if item.max_stack > 1:
            lines.append(f"{stack.count} / {item.max_stack}")

        surfs = [self._fs.render(l, True, (255, 240, 180)) for l in lines]
        # First line is the title — make it brighter
        surfs[0] = self._fs.render(lines[0], True, (255, 255, 100))
        ench_surfs = [self._fs.render(l, True, (190, 140, 255)) for l in _ench_lines]

        all_surfs = surfs[:1] + ench_surfs + surfs[1:]
        tw = max(s.get_width() for s in all_surfs) + 14
        th = sum(s.get_height() + 2 for s in all_surfs) + 8

        tx = min(mouse_pos[0] + 16, self.sw - tw - 4)
        ty = max(mouse_pos[1] - th - 6, 4)

        bg = pygame.Surface((tw, th), pygame.SRCALPHA)
        bg.fill((12, 8, 6, 215))
        screen.blit(bg, (tx, ty))
        pygame.draw.rect(screen, (110, 90, 50), (tx, ty, tw, th), 1)

        cy = ty + 5
        for surf in all_surfs:
            screen.blit(surf, (tx + 7, cy))
            cy += surf.get_height() + 2


# ── Container UI ───────────────────────────────────────────────────────────────

class ContainerUI:
    """27-slot chest / barrel overlay with drag-and-drop."""

    SLOTS = 27
    ROWS  = 3
    COLS  = 9

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open = False
        self.pos: Optional[tuple] = None   # (tx, ty) world tile coords
        self.slots: List[Optional[ItemStack]] = [None] * self.SLOTS
        self.cursor: Optional[ItemStack] = None
        self._cr: List[pygame.Rect] = []   # container slot rects
        self._ir: List[pygame.Rect] = []   # player inv rects
        self._hr: List[pygame.Rect] = []   # hotbar rects
        self._panel: Optional[pygame.Rect] = None
        self._fs: Optional[pygame.font.Font] = None
        self._ft: Optional[pygame.font.Font] = None
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        SS = SLOT_STEP
        cx = self.sw // 2 - self.COLS * SS // 2
        cy = self.sh // 2 - (self.ROWS * SS + 10 + GRID_ROWS * SS + SS) // 2
        self._cr = [
            pygame.Rect(cx + (i % self.COLS) * SS,
                        cy + (i // self.COLS) * SS,
                        SLOT_SIZE, SLOT_SIZE)
            for i in range(self.SLOTS)
        ]
        inv_y = cy + self.ROWS * SS + 16
        self._ir = [
            pygame.Rect(cx + (i % GRID_COLS) * SS,
                        inv_y + (i // GRID_COLS) * SS,
                        SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_y + GRID_ROWS * SS + 6
        self._hr = [
            pygame.Rect(cx + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        pad = 12
        all_rects = self._cr + self._ir + self._hr
        self._panel = pygame.Rect(
            min(r.x for r in all_rects) - pad,
            min(r.y for r in all_rects) - pad - 22,
            self.COLS * SS + pad * 2,
            max(r.bottom for r in all_rects) - min(r.y for r in all_rects) + pad * 2 + 22,
        )

    def _fonts(self):
        if self._fs is None:
            self._fs = pygame.font.SysFont(None, 20)
            self._ft = pygame.font.SysFont(None, 14)

    # ── Open / close ──────────────────────────────────────────────────────

    def open(self, tx: int, ty: int, world):
        self.is_open = True
        self.pos = (tx, ty)
        raw = world.get_container(tx, ty)
        self.slots = []
        for s in raw[:self.SLOTS]:
            if s is None:
                self.slots.append(None)
            else:
                try:
                    self.slots.append(ItemStack.from_dict(s))
                except Exception:
                    self.slots.append(None)
        while len(self.slots) < self.SLOTS:
            self.slots.append(None)

    def close(self, world, inv: "Inventory"):
        if self.cursor:
            inv.add(self.cursor)
            self.cursor = None
        if self.pos:
            world.save_container(
                self.pos[0], self.pos[1],
                [s.to_dict() if s else None for s in self.slots],
            )
        self.is_open = False
        self.pos = None

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event, inv: "Inventory", world) -> bool:
        if not self.is_open:
            return False
        if event.type == pygame.KEYDOWN:
            norm = _keys.normalize(event)
            if norm in (pygame.K_e, pygame.K_ESCAPE):
                self.close(world, inv)
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
        # Container slots
        for i, r in enumerate(self._cr):
            if r.collidepoint(pos):
                if shift and btn == 1 and self.slots[i]:
                    inv.add(self.slots[i]); self.slots[i] = None
                elif btn == 1:
                    self._lmb(self.slots, i)
                elif btn == 3:
                    self._rmb(self.slots, i)
                return
        # Player inventory grid
        for i, r in enumerate(self._ir):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if shift and btn == 1:
                    self._shift_to_container(idx, inv)
                elif btn == 1:
                    self._lmb(inv.slots, idx)
                elif btn == 3:
                    self._rmb(inv.slots, idx)
                return
        # Hotbar
        for i, r in enumerate(self._hr):
            if r.collidepoint(pos):
                if shift and btn == 1:
                    self._shift_to_container(i, inv)
                elif btn == 1:
                    self._lmb(inv.slots, i)
                elif btn == 3:
                    self._rmb(inv.slots, i)
                return
        if self.cursor:
            inv.add(self.cursor)
            self.cursor = None

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

    def _shift_to_container(self, idx: int, inv: "Inventory"):
        s = inv.slots[idx]
        if not s or s.is_empty(): return
        for j in range(self.SLOTS):
            if self.slots[j] is None:
                self.slots[j] = s; inv.slots[idx] = None; return
        # Merge
        for j in range(self.SLOTS):
            t = self.slots[j]
            if t and t.item_id == s.item_id and t.can_merge(s):
                space = t.max_stack - t.count
                move = min(space, s.count)
                t.count += move; s.count -= move
                if s.count <= 0:
                    inv.slots[idx] = None; return

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: "Inventory", mouse_pos: tuple):
        if not self.is_open:
            return
        self._fonts()
        sw, sh = screen.get_size()

        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        screen.blit(dim, (0, 0))

        pr = self._panel
        panel_surf = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        panel_surf.fill((28, 22, 18, 235))
        screen.blit(panel_surf, pr.topleft)
        pygame.draw.rect(screen, (90, 75, 55), pr, 2)

        title = self._fs.render("СУНДУК  [E/Esc]", True, (220, 200, 140))
        screen.blit(title, (pr.x + 8, pr.y + 5))

        for i, rect in enumerate(self._cr):
            self._draw_slot(screen, rect, self.slots[i])

        sep_y = self._ir[0].y - 12
        lbl = self._fs.render("── Инвентарь ──", True, (100, 90, 70))
        screen.blit(lbl, (sw // 2 - lbl.get_width() // 2, sep_y))

        for i, rect in enumerate(self._ir):
            self._draw_slot(screen, rect, inv.slots[HOTBAR_N + i])
        for i, rect in enumerate(self._hr):
            self._draw_slot(screen, rect, inv.slots[i], selected=(i == inv.selected))

        if self.cursor and not self.cursor.is_empty():
            sz = SLOT_SIZE - 8
            from assets import get_item_texture
            tex = get_item_texture(self.cursor.item_id, sz)
            screen.blit(tex, (mouse_pos[0] - sz // 2, mouse_pos[1] - sz // 2))

    def _draw_slot(self, screen, rect, stack, selected=False):
        bg  = (72, 60, 44) if selected else (42, 38, 32)
        bdr = (255, 215, 50) if selected else (72, 65, 52)
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, bdr, rect, 2 if selected else 1)
        if stack and not stack.is_empty():
            pad = 4
            from assets import get_item_texture
            sz  = rect.w - pad * 2
            tex = get_item_texture(stack.item_id, sz)
            screen.blit(tex, (rect.x + pad, rect.y + pad))
            if stack.count > 1:
                num = str(stack.count)
                s   = self._ft.render(num, True, (0, 0, 0))
                t   = self._ft.render(num, True, (255, 255, 255))
                nx  = rect.right - t.get_width() + 1
                ny  = rect.bottom - t.get_height() + 1
                screen.blit(s, (nx + 1, ny + 1))
                screen.blit(t, (nx, ny))


# ── Furnace UI ─────────────────────────────────────────────────────────────────

class FurnaceUI:
    """Minecraft-style furnace: input slot + fuel slot → output slot."""

    def __init__(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self.is_open  = False
        self.pos: Optional[tuple] = None   # (tx, ty) tile coords

        # Slots
        self.input_slot:  Optional[ItemStack] = None
        self.fuel_slot:   Optional[ItemStack] = None
        self.output_slot: Optional[ItemStack] = None
        self.cursor:      Optional[ItemStack] = None

        self._input_r:  Optional[pygame.Rect] = None
        self._fuel_r:   Optional[pygame.Rect] = None
        self._output_r: Optional[pygame.Rect] = None
        self._inv_rects: List[pygame.Rect] = []
        self._hb_rects:  List[pygame.Rect] = []
        self._panel:    Optional[pygame.Rect] = None
        self._fs: Optional[pygame.font.Font] = None
        self._ft: Optional[pygame.font.Font] = None
        self._rebuild()

    def resize(self, sw: int, sh: int):
        self.sw, self.sh = sw, sh
        self._rebuild()

    def _rebuild(self):
        SS = SLOT_STEP
        cx = self.sw // 2
        cy = self.sh // 2 - 60
        SZ = SLOT_SIZE + 10  # larger slots for furnace

        self._input_r  = pygame.Rect(cx - SZ - 20,  cy - SZ // 2,     SZ, SZ)
        self._fuel_r   = pygame.Rect(cx - SZ - 20,  cy + SZ // 2 + 4, SZ, SZ)
        self._output_r = pygame.Rect(cx + 20,        cy,               SZ + 4, SZ + 4)

        inv_top = cy + SZ * 2 + 16
        inv_ox  = self.sw // 2 - 9 * SS // 2
        self._inv_rects = [
            pygame.Rect(inv_ox + (i % 9) * SS, inv_top + (i // 9) * SS, SLOT_SIZE, SLOT_SIZE)
            for i in range(GRID_N)
        ]
        hb_y = inv_top + GRID_ROWS * SS + 6
        self._hb_rects = [
            pygame.Rect(inv_ox + i * SS, hb_y, SLOT_SIZE, SLOT_SIZE)
            for i in range(HOTBAR_N)
        ]
        all_r = [self._input_r, self._fuel_r, self._output_r] + self._inv_rects + self._hb_rects
        pad = 14
        self._panel = pygame.Rect(
            min(r.x for r in all_r) - pad,
            min(r.y for r in all_r) - pad - 26,
            max(r.right for r in all_r) - min(r.x for r in all_r) + pad * 2,
            max(r.bottom for r in all_r) - min(r.y for r in all_r) + pad * 2 + 26,
        )

    def _fonts(self):
        if self._fs is None:
            self._fs = pygame.font.SysFont(None, 20)
            self._ft = pygame.font.SysFont(None, 14)

    # ── Open / close ──────────────────────────────────────────────────────

    def open(self, tx: int, ty: int, world):
        self.is_open = True
        self.pos = (tx, ty)
        raw = world.get_container(tx, ty)
        def _load(d):
            if d is None: return None
            try: return ItemStack.from_dict(d)
            except Exception: return None
        self.input_slot  = _load(raw[0] if len(raw) > 0 else None)
        self.fuel_slot   = _load(raw[1] if len(raw) > 1 else None)
        self.output_slot = _load(raw[2] if len(raw) > 2 else None)
        self._update_output()

    def close(self, world, inv: "Inventory"):
        if self.cursor:
            inv.add(self.cursor); self.cursor = None
        if self.pos:
            world.save_container(self.pos[0], self.pos[1], [
                self.input_slot.to_dict()  if self.input_slot  else None,
                self.fuel_slot.to_dict()   if self.fuel_slot   else None,
                self.output_slot.to_dict() if self.output_slot else None,
            ] + [None] * 24)
        self.is_open = False
        self.pos = None

    # ── Events ────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event, inv: "Inventory", world) -> bool:
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
            self._click(event.pos, event.button, bool(mods & pygame.KMOD_SHIFT), inv)
        return True

    def _click(self, pos, btn, shift, inv):
        # Input slot
        if self._input_r and self._input_r.collidepoint(pos):
            if shift and btn == 1 and self.input_slot:
                inv.add(self.input_slot); self.input_slot = None
                self._update_output(); return
            if btn == 1: self._lmb_furnace("input")
            elif btn == 3: self._rmb_furnace("input")
            self._update_output(); return
        # Fuel slot
        if self._fuel_r and self._fuel_r.collidepoint(pos):
            if shift and btn == 1 and self.fuel_slot:
                inv.add(self.fuel_slot); self.fuel_slot = None; return
            if btn == 1: self._lmb_furnace("fuel")
            elif btn == 3: self._rmb_furnace("fuel")
            return
        # Output slot — click to collect
        if self._output_r and self._output_r.collidepoint(pos):
            if self.output_slot and not self.output_slot.is_empty():
                if self.fuel_slot and not self.fuel_slot.is_empty() and \
                   self.input_slot and not self.input_slot.is_empty():
                    # Consume fuel and input
                    self.fuel_slot.count -= 1
                    if self.fuel_slot.count <= 0: self.fuel_slot = None
                    self.input_slot.count -= 1
                    if self.input_slot.count <= 0: self.input_slot = None
                    result = self.output_slot.copy()
                    if self.cursor is None:
                        self.cursor = result
                    elif (self.cursor.item_id == result.item_id
                          and self.cursor.can_merge(result)):
                        self.cursor.count += min(
                            self.cursor.max_stack - self.cursor.count, result.count)
                    else:
                        inv.add(result)
                    import sounds as _snd
                    _snd.play("craft", 0.55)
                    from crafting import mark_discovered
                    mark_discovered(self.output_slot.item_id)
                    self._update_output()
            return
        # Inventory grid
        for i, r in enumerate(self._inv_rects):
            if r.collidepoint(pos):
                idx = HOTBAR_N + i
                if shift and btn == 1: self._shift_to_furnace(idx, inv)
                elif btn == 1: self._lmb_inv(inv.slots, idx)
                elif btn == 3: self._rmb_inv(inv.slots, idx)
                return
        # Hotbar
        for i, r in enumerate(self._hb_rects):
            if r.collidepoint(pos):
                if shift and btn == 1: self._shift_to_furnace(i, inv)
                elif btn == 1: self._lmb_inv(inv.slots, i)
                elif btn == 3: self._rmb_inv(inv.slots, i)
                return
        if self.cursor:
            inv.add(self.cursor); self.cursor = None

    def _get_furnace_slot(self, name):
        if name == "input":  return self.input_slot
        if name == "fuel":   return self.fuel_slot
        return None

    def _set_furnace_slot(self, name, val):
        if name == "input":  self.input_slot  = val
        elif name == "fuel": self.fuel_slot   = val

    def _lmb_furnace(self, name):
        slot = self._get_furnace_slot(name)
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot; self._set_furnace_slot(name, None)
        else:
            if slot is None or slot.is_empty():
                self._set_furnace_slot(name, self.cursor); self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                move = min(slot.max_stack - slot.count, self.cursor.count)
                slot.count += move; self.cursor.count -= move
                if self.cursor.count <= 0: self.cursor = None
            else:
                self._set_furnace_slot(name, self.cursor)
                self.cursor = slot if not slot.is_empty() else None

    def _rmb_furnace(self, name):
        slot = self._get_furnace_slot(name)
        if self.cursor is None:
            if slot and not slot.is_empty():
                self.cursor = slot.split_half()
                if slot.is_empty(): self._set_furnace_slot(name, None)
        else:
            if slot is None or slot.is_empty():
                self._set_furnace_slot(name, ItemStack(self.cursor.item_id, 1, self.cursor.durability))
                self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                slot.count += 1; self.cursor.count -= 1
                if self.cursor.count <= 0: self.cursor = None

    def _lmb_inv(self, slots, i):
        slot = slots[i]
        if self.cursor is None:
            if slot and not slot.is_empty(): self.cursor = slot; slots[i] = None
        else:
            if slot is None or slot.is_empty(): slots[i] = self.cursor; self.cursor = None
            elif slot.item_id == self.cursor.item_id and slot.can_merge(self.cursor):
                move = min(slot.max_stack - slot.count, self.cursor.count)
                slot.count += move; self.cursor.count -= move
                if self.cursor.count <= 0: self.cursor = None
            else:
                slots[i] = self.cursor
                self.cursor = slot if not slot.is_empty() else None

    def _rmb_inv(self, slots, i):
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

    def _shift_to_furnace(self, idx, inv):
        s = inv.slots[idx]
        if not s or s.is_empty(): return
        from crafting import get_smelt_result, _FUEL_ITEMS
        if get_smelt_result(s.item_id) and self.input_slot is None:
            self.input_slot = s; inv.slots[idx] = None
            self._update_output(); return
        if s.item_id in _FUEL_ITEMS and self.fuel_slot is None:
            self.fuel_slot = s; inv.slots[idx] = None; return

    def _update_output(self):
        from crafting import get_smelt_result
        if self.input_slot and not self.input_slot.is_empty():
            res = get_smelt_result(self.input_slot.item_id)
            if res and res[0] in ITEMS:
                self.output_slot = ItemStack(res[0], res[1])
                return
        self.output_slot = None

    # ── Drawing ───────────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, inv: "Inventory", mouse_pos: tuple):
        if not self.is_open:
            return
        self._fonts()
        sw, sh = screen.get_size()

        dim = pygame.Surface((sw, sh), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 145))
        screen.blit(dim, (0, 0))

        pr = self._panel
        ps = pygame.Surface((pr.w, pr.h), pygame.SRCALPHA)
        ps.fill((28, 22, 18, 235))
        screen.blit(ps, pr.topleft)
        pygame.draw.rect(screen, (90, 75, 55), pr, 2)

        title = self._fs.render("ПЕЧЬ  [E/Esc]", True, (220, 200, 140))
        screen.blit(title, (pr.x + 10, pr.y + 6))

        # Labels
        inp_lbl = self._ft.render("Вход", True, (140, 130, 110))
        screen.blit(inp_lbl, (self._input_r.x, self._input_r.y - 14))
        fuel_lbl = self._ft.render("Топливо", True, (140, 130, 110))
        screen.blit(fuel_lbl, (self._fuel_r.x, self._fuel_r.y - 14))
        out_lbl = self._ft.render("Результат", True, (140, 130, 110))
        screen.blit(out_lbl, (self._output_r.x, self._output_r.y - 14))

        self._draw_furnace_slot(screen, self._input_r,  self.input_slot)
        self._draw_furnace_slot(screen, self._fuel_r,   self.fuel_slot)

        has_result = (self.output_slot and not self.output_slot.is_empty()
                      and self.fuel_slot and not self.fuel_slot.is_empty())

        # Arrow (input → output)
        ax = self._input_r.right + 8
        ay = self._input_r.centery
        arrow_col = (200, 160, 60) if has_result else (70, 65, 55)
        pygame.draw.polygon(screen, arrow_col, [
            (ax, ay - 8), (ax + 22, ay), (ax, ay + 8)
        ])

        # Flame (fuel burning indicator)
        fx = self._fuel_r.x + self._fuel_r.w // 2 - 8
        fy = self._fuel_r.y - 22
        if has_result:
            flame_pts = [(fx+8, fy+16), (fx+4, fy+8), (fx, fy+14),
                         (fx+2, fy+6), (fx+8, fy), (fx+14, fy+6),
                         (fx+16, fy+14), (fx+12, fy+8)]
            pygame.draw.polygon(screen, (255, 160, 30), flame_pts)
            pygame.draw.polygon(screen, (255, 220, 80), [
                (fx+8, fy+10), (fx+6, fy+14), (fx+10, fy+14)
            ])
        else:
            pygame.draw.rect(screen, (60, 55, 50), (fx, fy, 16, 16))

        # Output slot
        out_r = self._output_r
        pygame.draw.rect(screen, (35, 30, 20), out_r)
        out_bdr = (255, 215, 50) if has_result else (80, 75, 60)
        pygame.draw.rect(screen, out_bdr, out_r, 2)
        if self.output_slot and not self.output_slot.is_empty():
            from assets import get_item_texture
            col = (200, 200, 200, 128) if not has_result else None
            tex = get_item_texture(self.output_slot.item_id, out_r.w - 8)
            if not has_result:
                tex = tex.copy(); tex.set_alpha(100)
            screen.blit(tex, (out_r.x + 4, out_r.y + 4))

        # Inventory
        sep_y = self._inv_rects[0].y - 12
        sep = self._fs.render("── Инвентарь ──", True, (100, 90, 70))
        screen.blit(sep, (sw // 2 - sep.get_width() // 2, sep_y))
        for i, rect in enumerate(self._inv_rects):
            self._draw_slot(screen, rect, inv.slots[HOTBAR_N + i])
        for i, rect in enumerate(self._hb_rects):
            self._draw_slot(screen, rect, inv.slots[i], selected=(i == inv.selected))

        if self.cursor and not self.cursor.is_empty():
            sz = SLOT_SIZE - 8
            from assets import get_item_texture
            tex = get_item_texture(self.cursor.item_id, sz)
            screen.blit(tex, (mouse_pos[0] - sz // 2, mouse_pos[1] - sz // 2))

    def _draw_furnace_slot(self, screen, rect, stack):
        pygame.draw.rect(screen, (42, 38, 32), rect)
        pygame.draw.rect(screen, (90, 80, 65), rect, 2)
        if stack and not stack.is_empty():
            from assets import get_item_texture
            sz  = rect.w - 8
            tex = get_item_texture(stack.item_id, sz)
            screen.blit(tex, (rect.x + 4, rect.y + 4))
            if stack.count > 1:
                num = str(stack.count)
                s   = self._ft.render(num, True, (0, 0, 0))
                t   = self._ft.render(num, True, (255, 255, 255))
                screen.blit(s, (rect.right - t.get_width() + 2, rect.bottom - t.get_height() + 2))
                screen.blit(t, (rect.right - t.get_width() + 1, rect.bottom - t.get_height() + 1))

    def _draw_slot(self, screen, rect, stack, selected=False):
        bg  = (72, 60, 44) if selected else (42, 38, 32)
        bdr = (255, 215, 50) if selected else (72, 65, 52)
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, bdr, rect, 2 if selected else 1)
        if stack and not stack.is_empty():
            from assets import get_item_texture
            sz  = rect.w - 8
            tex = get_item_texture(stack.item_id, sz)
            screen.blit(tex, (rect.x + 4, rect.y + 4))
