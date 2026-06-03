"""
ai_player.py — ИИ-игрок на основе поведенческого клонирования.

Алгоритм: k-ближайших соседей (KNN) по числовым признакам состояния.
Загружает learning_data/*.jsonl и на каждом тике находит k наиболее
похожих ситуаций из обучающей выборки, голосованием определяя действие.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Optional

import pygame
import numpy as np


# ── Загрузка данных ───────────────────────────────────────────────────────────

def _find_data_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Minacraft" / "learning_data"
    return Path("learning_data")


def _state_to_vec(s: dict) -> np.ndarray:
    """Преобразовать запись состояния в числовой вектор признаков."""
    mobs = s.get("mobs_nearby", [])
    if mobs:
        closest = min(abs(m["dx"]) + abs(m["dy"]) for m in mobs)
        enemy_count = len(mobs)
    else:
        closest = 15.0
        enemy_count = 0

    held = s.get("held_item") or ""
    is_weapon   = int(any(t in held for t in ("sword", "gun", "bow", "minigun")))
    is_pickaxe  = int("pickaxe" in held)
    is_food     = int(any(t in held for t in ("apple", "bread", "beef", "potato")))

    hp_ratio  = s["hp"] / max(s["max_hp"], 1)
    hun_ratio = s.get("hunger", 20) / 20.0

    dim_map = {"overworld": 0.0, "nether": 0.5, "end": 1.0}
    dim = dim_map.get(s.get("dimension", "overworld"), 0.0)

    return np.array([
        s["vx"],                    # горизонтальная скорость
        s["vy"],                    # вертикальная скорость
        float(s["on_ground"]),      # на земле?
        hp_ratio,                   # HP / maxHP
        hun_ratio,                  # голод
        min(enemy_count, 5) / 5.0,  # плотность врагов (норм)
        min(closest, 15.0) / 15.0,  # расстояние до ближайшего врага
        is_weapon,
        is_pickaxe,
        is_food,
        s.get("time_of_day", 0.5),
        dim,
    ], dtype=np.float32)


# Виды мобов, которые бот считает враждебными
_HOSTILE_KINDS = frozenset({
    "zombie", "skeleton", "spider", "creeper",
    "zombified_piglin", "blaze", "ghast", "enderman",
    "skeleton_king", "forest_golem", "ender_dragon",
})

# Дистанции (в пикселях)
_LEASH_PX   = 15 * 32   # дальше этого — бот бежит к игроку игнорируя всё
_FIGHT_PX   = 8  * 32   # ближе этого — бот атакует врага
_ATTACK_PX  = 2.5 * 32  # ближе этого — lmb=True (удар)
_FOLLOW_GAP = 48         # мёртвая зона следования (~1.5 тайла)


class BotBrain:
    """Загружает обучающие данные и принимает решения методом KNN."""

    K = 7       # число соседей для голосования
    MAX_SAMPLES = 20_000  # ограничение для быстрого запуска

    def __init__(self):
        self._X: Optional[np.ndarray] = None   # матрица признаков N×D
        self._actions: list = []               # список action-словарей
        self._ready = False
        self._tick = 0
        self.goal: str = "idle"               # текущая цель для HUD

    def load(self) -> int:
        """Загрузить данные из всех jsonl-файлов. Вернуть число семплов."""
        data_dir = _find_data_dir()
        if not data_dir.exists():
            return 0

        X_rows, actions = [], []
        files = sorted(data_dir.glob("*.jsonl"), reverse=True)   # новые сначала
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    for line in f:
                        if len(X_rows) >= self.MAX_SAMPLES:
                            break
                        try:
                            d = json.loads(line)
                            vec = _state_to_vec(d["state"])
                            X_rows.append(vec)
                            actions.append(d["action"])
                        except Exception:
                            continue
            except Exception:
                continue
            if len(X_rows) >= self.MAX_SAMPLES:
                break

        if not X_rows:
            return 0

        self._X = np.stack(X_rows)
        self._actions = actions
        self._ready = True
        return len(X_rows)

    def decide(self, state_vec: np.ndarray) -> dict:
        """Вернуть action-словарь для данного вектора состояния."""
        if not self._ready:
            return self._idle()

        dists = np.linalg.norm(self._X - state_vec, axis=1)
        k = min(self.K, len(self._actions))
        top_k = np.argpartition(dists, k)[:k]
        neighbors = [self._actions[i] for i in top_k]

        move_votes = [n["move_x"] for n in neighbors]
        move_x = int(round(sum(move_votes) / len(move_votes)))
        move_x = max(-1, min(1, move_x))

        jump      = sum(n["jump"]     for n in neighbors) > k * 0.4
        lmb       = sum(n["lmb_held"] for n in neighbors) > k * 0.5

        return {"move_x": move_x, "jump": jump, "lmb": lmb}

    def _idle(self) -> dict:
        return {"move_x": 0, "jump": False, "lmb": False}

    def decide_with_goals(
        self,
        state_vec: np.ndarray,
        bot_x: float, bot_y: float,
        player_x: float, player_y: float,
        mobs: list,
    ) -> dict:
        """Цель-ориентированное решение: KNN + приоритетная FSM поверх него."""
        base = self.decide(state_vec)

        bot_cx  = bot_x + 12
        bot_cy  = bot_y + 24
        play_cx = player_x + 12
        play_cy = player_y + 24

        dist_player = math.hypot(play_cx - bot_cx, play_cy - bot_cy)

        # Приоритет 1: слишком далеко от игрока — возврат
        if dist_player > _LEASH_PX:
            self.goal = "return"
            dx = play_cx - bot_cx
            move_x = 1 if dx > 16 else (-1 if dx < -16 else 0)
            jump = play_cy < bot_cy - 32
            return {"move_x": move_x, "jump": jump, "lmb": False}

        # Приоритет 2: найти ближайшего враждебного моба
        nearest_mob  = None
        nearest_dist = float("inf")
        for mob in mobs:
            if not getattr(mob, "alive", False):
                continue
            if getattr(mob, "kind", "") not in _HOSTILE_KINDS:
                continue
            mx = getattr(mob, "x", 0) + 12
            my = getattr(mob, "y", 0) + 24
            d  = math.hypot(mx - bot_cx, my - bot_cy)
            if d < nearest_dist:
                nearest_dist = d
                nearest_mob  = mob

        if nearest_mob and nearest_dist < _FIGHT_PX:
            self.goal = "fight"
            mx = getattr(nearest_mob, "x", 0) + 12
            my = getattr(nearest_mob, "y", 0) + 24
            dx = mx - bot_cx
            move_x = 1 if dx > 8 else (-1 if dx < -8 else 0)
            lmb  = nearest_dist < _ATTACK_PX
            jump = base["jump"] or (my < bot_cy - 24)
            return {"move_x": move_x, "jump": jump, "lmb": lmb}

        # Приоритет 3: следовать за игроком
        self.goal = "follow"
        dx = play_cx - bot_cx
        if abs(dx) > _FOLLOW_GAP:
            move_x = 1 if dx > 0 else -1
        else:
            move_x = 0
        # Прыжок если игрок заметно выше и мы рядом по горизонтали
        jump = base["jump"] or (play_cy < bot_cy - 32 and abs(dx) < 5 * 32)
        return {"move_x": move_x, "jump": jump, "lmb": False}

    def keys_for(self, action: dict) -> dict:
        """Преобразовать action-словарь в dict pygame-клавиш для update_player."""
        keys: dict = {}
        if action["move_x"] < 0:
            keys[pygame.K_a] = True
        elif action["move_x"] > 0:
            keys[pygame.K_d] = True
        if action["jump"]:
            keys[pygame.K_w] = True
        return keys


# ── Отрисовка бота ────────────────────────────────────────────────────────────

_BOT_SKIN  = (90,  160, 255)   # синеватый оттенок тела
_BOT_SKIN2 = (60,  120, 210)
_BOT_OUT   = (20,   40, 100)
_BOT_EYE   = (255, 255, 100)
_BOT_NAME_FONT: Optional[pygame.font.Font] = None


_GOAL_ICON = {"follow": "→", "fight": "⚔", "return": "↩", "idle": "…"}
_GOAL_COL  = {"follow": (160, 220, 160), "fight": (255, 100, 80),
               "return": (255, 220, 60),  "idle":  (160, 160, 160)}


def draw_bot(screen: pygame.Surface, bot_player, camera,
             nickname: str = "Bot", goal: str = "idle"):
    """Нарисовать ИИ-игрока — упрощённый вариант draw_player с синей палитрой."""
    global _BOT_NAME_FONT
    if _BOT_NAME_FONT is None:
        _BOT_NAME_FONT = pygame.font.SysFont(None, 20)

    from world import PLAYER_W, PLAYER_H, Camera
    sx, sy = camera.world_to_screen(bot_player.x, bot_player.y)
    W = PLAYER_W

    # Пропорции (те же, что у игрока)
    head_w, head_h = 22, 22
    body_w, body_h = 16, 10
    leg_w,  leg_h  = 8,  20
    arm_w,  arm_h  = 5,  15

    hx = sx + (W - head_w) // 2
    hy = sy
    bx = sx + (W - body_w) // 2
    by = hy + head_h
    ll_x = sx + (W - leg_w * 2 - 2) // 2
    rl_x = ll_x + leg_w + 2
    leg_y = by + body_h
    la_x  = bx - arm_w - 1
    ra_x  = bx + body_w + 1
    arm_y = by + 1

    sw = math.sin(getattr(bot_player, "walk_frame", 0)) * 6.0
    lean = int(getattr(bot_player, "facing", 1) * 0)

    def _rect(r, c):
        pygame.draw.rect(screen, c, r)

    # Ноги
    for lx, off in ((ll_x, int(sw)), (rl_x, int(-sw))):
        y0 = leg_y + max(0, off)
        h  = leg_h - abs(off)
        _rect((lx + lean, y0, leg_w, max(2, h)), _BOT_SKIN2)
        pygame.draw.rect(screen, _BOT_OUT, (lx + lean, y0, leg_w, max(2, h)), 1)

    # Руки
    for ax, off in ((la_x, int(-sw)), (ra_x, int(sw))):
        y0 = arm_y + max(0, off)
        h  = arm_h - abs(off)
        _rect((ax + lean, y0, arm_w, max(2, h)), _BOT_SKIN2)
        pygame.draw.rect(screen, _BOT_OUT, (ax + lean, y0, arm_w, max(2, h)), 1)

    # Тело
    _rect((bx + lean, by, body_w, body_h), _BOT_SKIN)
    pygame.draw.rect(screen, _BOT_OUT, (bx + lean, by, body_w, body_h), 1)

    # Голова
    _rect((hx + lean, hy, head_w, head_h), _BOT_SKIN)
    pygame.draw.rect(screen, _BOT_OUT, (hx + lean, hy, head_w, head_h), 1)

    # Глаз
    f = getattr(bot_player, "facing", 1)
    eye_x = hx + lean + (head_w * 2 // 3 if f > 0 else head_w // 5)
    pygame.draw.rect(screen, _BOT_EYE, (eye_x, hy + head_h // 3, 4, 4))

    # Никнейм + иконка цели над головой
    icon     = _GOAL_ICON.get(goal, "")
    icon_col = _GOAL_COL.get(goal, (180, 220, 255))
    label    = _BOT_NAME_FONT.render(f"[AI] {nickname}  {icon}", True, icon_col)
    screen.blit(label, (sx + W // 2 - label.get_width() // 2, hy - 18))

    # HP-бар
    hp_ratio = bot_player.hp / max(bot_player.max_hp, 1)
    bar_w = PLAYER_W
    pygame.draw.rect(screen, (60, 20, 20), (sx, hy - 6, bar_w, 4))
    pygame.draw.rect(screen, (60, 180, 60), (sx, hy - 6, int(bar_w * hp_ratio), 4))
