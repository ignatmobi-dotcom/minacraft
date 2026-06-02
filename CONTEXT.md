# Minacraft — Контекст проекта (для восстановления сессии)

## Что это
Terraria-подобный 2D платформер на pygame с семантическим крафтом. Игрок сам придумывает рецепты раскладывая предметы на верстаке 3×3.

## Текущая версия: 1.0-beta-patch2

## Файлы проекта
| Файл | Роль |
|---|---|
| `main.py` | Игровой цикл, GameSession, меню (Resolution/Nickname/WorldSelect/Pause) |
| `world.py` | Генерация мира, физика игрока, рендер тайлов, draw_player |
| `inventory.py` | Инвентарь (4×9 + хотбар 9 = 45 слотов + 4 брони), drag-and-drop |
| `crafting.py` | Верстак (семантика + ванильный режим), RecipeBook, зачарования, варка |
| `items.py` | Реестр предметов (~100+), теги, свойства |
| `assets.py` | Загрузка текстур из Faithful 32x, fallback-генерация, end_portal текстура |
| `mobs.py` | Мобы, ИИ, рендер (humanoid + кастомные pig/spider), боссы |
| `sounds.py` | Загрузка OGG из sound3/, newsound/, музыка |
| `keys.py` | Нормализация клавиш по scancode (WASD работают на любой раскладке) |
| `learning.py` | Логирование действий игрока в learning_data/*.jsonl для обучения ИИ |
| `ai_player.py` | BotBrain (KNN по обучающим данным), draw_bot (синяя фигурка) |
| `launcher.py` | Tkinter-лаунчер (установка версий, управление мирами) |

## Текстуры
`resources/Faithful-32x-1.21.11/assets/minecraft/`
- `textures/block/`, `textures/item/`, `textures/entity/` — PNG текстуры
- `resources copy/sound3/dig/` — звуки копания (НЕ `sound/step/`!)
- `resources copy/sound3/step/` — звуки шагов
- `resources copy/sound3/random/` — UI звуки (break, click, pop, eat...)
- `resources copy/newsound/damage/` — звуки урона
- `resources copy/newsound/ambient/` — кейвы, дождь, гром
- `resources copy/music/`, `resources copy/newmusic/` — фоновая музыка

## Архитектура мира
- `WORLD_W = 2800` тайлов, `WORLD_H = 130`, тайл = 32px
- `_base` (генерированный из seed) + `_mods` (только изменения игрока)
- Биомы: tundra/mountains/forest/plains/desert (value noise + fBm)
- Сохранение: `saves/world_N.json` (только mods, не весь массив)
- Два слоя: foreground (fg) и background (bg), Tab — переключить

## Система боя
- **LMB клик** → мгновенный удар в направлении мыши (кулдаун 0.45с)
- Попадает по мобам в радиусе 3.2 тайла в пределах ~105° дуги
- **LMB удержание** → добыча блоков (мобов НЕ бьёт)
- Анимация: `_swing_t` в GameSession, `attack_swing` параметр в draw_player
- Критический удар: ×1.5 урона в прыжке при vy > 2

## Инвентарь
- Слоты [0:9] хотбар, [9:45] грид 4×9, [45:49] броня
- `GRID_ROWS = 4`

## Крафт
- Два режима: Семантический (по тегам) и Ванильный (точные позиции)
- Кнопка переключения в UI верстака
- Ванильные рецепты: верстак, печь, сундук, бочка, дверь, сталь, бронза, незерит
- Семантические: инструменты, броня, факелы, луки, стрелы, редстоун

## Нижний мир (Ад)
- Блоки: netherrack, bedrock, nether_quartz_ore, nether_gold_ore, ancient_debris, soul_sand, basalt, nether_brick, nether_wart_block, glowstone, magma_block, lava
- Структуры: `_place_nether_fortress()` — крепость из nether_brick с сундуками с лутом
- Мобы: zombified_piglin, blaze, blaze_boss, ghast
- Портал: `nether_portal` тайл, стоять 3с → телепорт. Координаты: оверворлд ÷ 8 = незер
- Магма: 1 HP/сек при стоянии (блокируется fire_resistance)
- Лава светится, туман (`_draw_nether_fog`), частицы огня каждые 0.15с

## Звуки
- Копание: `sound3/dig/grass1-4`, `stone1-4`, `wood1-4`, `sand1-4`
- Шаги: `sound3/step/grass1-6`, `stone1-6`, `wood1-6`
- Разрушение блока → dig-звук тайла (НЕ `random/break.ogg`)
- `random/break.ogg` → только при поломке инструмента
- `successful_hit` → удар по мобу, `explode` → взрывы

## Мобы
- Текстуры из `textures/entity/` (Minecraft humanoid UV, MobParts)
- Свинья: `_draw_pig` — горизонтальный квадрупед, 46×28px
- Паук: `_draw_spider` — широкое тело, 8 суставчатых ног
- Zombie/Skeleton/Creeper/Villager/Enderman: MobParts (humanoid UV)
- Боссы: Скелет-Король, Лесной Голем, Дракон Края (у каждого 2 фазы)
- DroppedItem: физика, гравитация, боб, despawn

## ИИ-игрок (ai_player.py)
- `BotBrain` загружает до 20 000 семплов из `learning_data/*.jsonl`
- Вектор признаков 12D: vx, vy, on_ground, hp_ratio, hunger_ratio, плотность врагов,
  расстояние до ближайшего врага, is_weapon, is_pickaxe, is_food, time_of_day, dimension
- KNN (k=7) через `np.argpartition`, голосование: move_x (среднее), jump (>40%), lmb (>50%)
- `draw_bot()`: синяя фигурка, метка `[AI] nick_bot`, HP-бар, анимация ходьбы
- Бот инстанцируется в `GameSession.__init__` только при наличии данных
- Тикается каждый кадр, вызывает `update_player` с фиктивными клавишами

## Система логирования действий (learning.py)
- `PlayerLogger` пишет JSONL в `learning_data/session_YYYYMMDD_HHMMSS.jsonl`
- В frozen .app путь: `~/Library/Application Support/Minacraft/learning_data/`
- Каждая запись: `{"state": {...}, "action": {...}, "dt": float}`
- `collect_state()` и `collect_action()` — хелперы для сборки данных из GameSession

## Экран никнейма (NicknameScreen)
- Показывается один раз после выбора разрешения (launcher-bypass пропускает)
- Только латинские буквы, цифры, `_` (2–16 символов)
- Фильтр мата: `_PROFANITY` frozenset, substring-поиск
- Ник хранится в глобальном `_PLAYER_NICKNAME`

## Лог крашей
- При необработанном исключении трейсбек пишется в `~/Desktop/minacraft_crash.log`
- Реализовано: обёртка `try/except` вокруг `main()` в `if __name__ == "__main__"`

## Редстоун
- Источники: lever, button (stone/wood), pressure_plate (stone/wood), redstone_torch
- BFS распространение через redstone_wire (15 тайлов)
- Двери автоматически открываются от сигнала

## Погода
- Состояния: clear → rain → thunder → snow
- `_update_weather(dt)` и `_draw_weather(screen)` в GameSession

## Достижения
- 15 ачивок, хранятся в `world._achievements: set`
- Popup справа снизу, анимация slide-in, 3.5с показа

## Контейнеры
- Сундук/бочка: ContainerUI (27 слотов), ПКМ для открытия
- Данные в `world._containers`, часть `_mods` (сохраняются)
- При разрушении — предметы в инвентарь

## Тест-режим
- Кнопка «🧪 Тест» на экране выбора мира
- Новый мир в тест-режиме: алмазный набор + броня + все ресурсы + 5000 XP
- `_new_game(slot, cheat=True)`

## CI/CD и сборка
- `.github/workflows/build.yml`: build-windows (windows-latest) + build-macos (macos-13)
- Артефакты: `Minacraft-1.0-beta-windows.zip` и `Minacraft-1.0-beta.dmg` (90 дней)
- Иконка: `grass_block_side` 32px
- Лицензия: проприетарная, все права защищены, Роман (ignatmobi-dotcom) 2026

## Ключевые константы
```python
TILE_SIZE  = 32     # px
WORLD_W    = 2800   # тайлов
WORLD_H    = 130
FPS        = 60
MOB_W      = 24     # px (humanoid bounds)
MOB_H      = 48
MINE_REACH = 5      # тайлов
GRID_ROWS  = 4      # ряды инвентаря
```

## Менеджер состояний (main.py)
```
resolution → nickname → world_select ↔ playing ↔ paused ↔ help
```
- `_LAUNCHER_SLOT`: env-var от launcher, пропускает resolution + nickname + world_select
- `SAVES_DIR`: env-var `MINACRAFT_SAVES_DIR` или платформенный путь (~/Library/... на macOS)

## Известные особенности
- Нет мобов при запуске — `spawn_mobs()` размещает их на старте (не динамически)
- Вода течёт только в видимой области (tick-система)
- Губка удаляет воду в радиусе 4 при размещении
- Двери: 2 тайла (oak_door + oak_door_top), cascade-break при ломании
- Выстрелы минигана логируются пачками по 100 (`_minigun_burst`)
