"""
learning.py — сбор обучающих данных из действий живого игрока.

Формат: JSON Lines (jsonl), один объект на строку.
Каждая запись = одно (состояние, действие) — пригодно для имитационного обучения.

Использование:
    from learning import PlayerLogger
    logger = PlayerLogger()          # создать в GameSession.__init__
    logger.record(state, action)     # вызывать каждый тик
    logger.close()                   # при выходе / смене мира
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ── Датаклассы ────────────────────────────────────────────────────────────────

@dataclass
class PlayerState:
    """Наблюдаемое состояние игрока в момент принятия действия."""
    # Позиция и скорость (тайловые единицы)
    tx: float          # x в тайлах
    ty: float          # y в тайлах
    vx: float          # скорость x
    vy: float          # скорость y
    on_ground: bool

    # Жизненные показатели
    hp: float
    max_hp: float
    hunger: float
    xp: int
    level: int
    dimension: str     # "overworld" | "nether" | "end"

    # Инвентарь
    held_item: Optional[str]    # item_id или None
    hotbar: list                # [item_id or None, ...] × 9

    # Ближайшее окружение (тайлы в радиусе 3×3 вокруг игрока)
    nearby_tiles: list          # 7×7 сетка → список строк / None

    # Мобы в радиусе 10 тайлов
    mobs_nearby: list           # [{"kind": str, "dx": float, "dy": float, "hp": float}]

    # Время суток (0.0–1.0)
    time_of_day: float


@dataclass
class PlayerAction:
    """Действие, совершённое игроком в данном тике."""
    # Движение: -1 / 0 / +1
    move_x: int
    jump: bool

    # Взаимодействие
    lmb_held: bool      # добыча / атака
    rmb: bool           # размещение / взаимодействие
    open_inv: bool
    open_craft: bool
    select_slot: int    # 0-8; -1 = без изменений

    # Прицел (нормированный вектор к цели мыши)
    aim_dx: float
    aim_dy: float


@dataclass
class Sample:
    """Одна запись датасета."""
    ts: float           # unix-timestamp
    dt: float           # длительность тика (сек)
    state: dict
    action: dict


# ── Логгер ────────────────────────────────────────────────────────────────────

import sys as _sys

def _learning_dir() -> Path:
    if getattr(_sys, "frozen", False):
        if _sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "Minacraft"
        elif _sys.platform == "win32":
            import os as _os
            base = Path(_os.environ.get("APPDATA", Path.home())) / "Minacraft"
        else:
            base = Path.home() / ".minacraft"
        return base / "learning_data"
    return Path("learning_data")

LOG_DIR = _learning_dir()

class PlayerLogger:
    """Записывает пары (state, action) в файл jsonl.

    Файл создаётся при первой записи (lazy), закрывается при вызове close().
    Один файл = одна игровая сессия.
    """

    def __init__(self, enabled: bool = True):
        self._enabled  = enabled
        self._file     = None
        self._path: Optional[Path] = None
        self._count    = 0
        self._session_start = time.time()

    def _open(self):
        LOG_DIR.mkdir(exist_ok=True)
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(self._session_start))
        self._path = LOG_DIR / f"session_{ts_str}.jsonl"
        self._file = open(self._path, "w", encoding="utf-8")

    def record(self, state: PlayerState, action: PlayerAction, dt: float = 0.0) -> None:
        """Записать одну пару (state, action). Вызывать каждый игровой тик."""
        if not self._enabled:
            return
        if self._file is None:
            self._open()
        sample = {
            "ts": time.time(),
            "dt": dt,
            "state": asdict(state),
            "action": asdict(action),
        }
        self._file.write(json.dumps(sample, ensure_ascii=False) + "\n")
        self._count += 1

    def close(self) -> int:
        """Закрыть файл. Возвращает число записанных семплов."""
        if self._file:
            self._file.close()
            self._file = None
        return self._count

    @property
    def sample_count(self) -> int:
        return self._count


# ── Вспомогательные функции для сбора состояния ──────────────────────────────

def collect_state(
    player,
    world,
    inv,
    mobs: list,
    dimension: str,
    day_t: float,
    tile_size: int = 32,
    nearby_r: int = 3,
    mob_r: int = 10,
) -> PlayerState:
    """Собрать PlayerState из текущих объектов игры.

    Вызывать из GameSession.update() перед обработкой ввода.
    """
    tx = player.x / tile_size
    ty = player.y / tile_size

    # Хотбар (первые 9 слотов инвентаря)
    hotbar = []
    for s in inv.slots[:9]:
        hotbar.append(s.item_id if (s and s.item) else None)

    held_id = inv.held.item_id if (inv.held and inv.held.item) else None

    # Сетка тайлов вокруг игрока (nearby_r тайлов в каждую сторону)
    px_tile = int(tx + 0.5)
    py_tile = int(ty + 0.5)
    nearby: list = []
    for dy in range(-nearby_r, nearby_r + 1):
        row = []
        for dx in range(-nearby_r, nearby_r + 1):
            t = world.get(px_tile + dx, py_tile + dy)
            row.append(t)
        nearby.append(row)

    # Ближайшие мобы
    pcx, pcy = player.x + 12, player.y + 24   # приблизительный центр
    mob_range_px = mob_r * tile_size
    mobs_nearby = []
    for mob in mobs:
        if not mob.alive:
            continue
        mcx, mcy = getattr(mob, "x", 0) + 12, getattr(mob, "y", 0) + 24
        dist = math.hypot(mcx - pcx, mcy - pcy)
        if dist <= mob_range_px:
            mobs_nearby.append({
                "kind": mob.kind,
                "dx": round((mcx - pcx) / tile_size, 2),
                "dy": round((mcy - pcy) / tile_size, 2),
                "hp": getattr(mob, "hp", 0),
            })

    return PlayerState(
        tx=round(tx, 2),
        ty=round(ty, 2),
        vx=round(getattr(player, "vx", 0.0), 2),
        vy=round(getattr(player, "vy", 0.0), 2),
        on_ground=bool(getattr(player, "on_ground", False)),
        hp=player.hp,
        max_hp=player.max_hp,
        hunger=round(getattr(player, "hunger", 20.0), 1),
        xp=player.xp,
        level=player.level,
        dimension=dimension,
        held_item=held_id,
        hotbar=hotbar,
        nearby_tiles=nearby,
        mobs_nearby=mobs_nearby,
        time_of_day=round(day_t, 3),
    )


def collect_action(
    keys_pressed: set,
    lmb_held: bool,
    rmb_pressed: bool,
    open_inv: bool,
    open_craft: bool,
    selected_slot: int,
    prev_slot: int,
    aim_dx: float,
    aim_dy: float,
    move_x: int,
    jump: bool,
) -> PlayerAction:
    """Собрать PlayerAction из текущего состояния ввода."""
    return PlayerAction(
        move_x=move_x,
        jump=jump,
        lmb_held=lmb_held,
        rmb=rmb_pressed,
        open_inv=open_inv,
        open_craft=open_craft,
        select_slot=selected_slot if selected_slot != prev_slot else -1,
        aim_dx=round(aim_dx, 3),
        aim_dy=round(aim_dy, 3),
    )
