"""
keys.py — keyboard scancode normalization.

Fixes input on non-US keyboard layouts (Russian, etc.) where event.key
returns layout-translated characters instead of physical key positions.
Uses SDL2 scancodes (physical key positions) to map to pygame key constants.
"""
import pygame

# SDL2 scancode → pygame key constant
# Covers movement, interaction, and hotbar keys
_SC_MAP = {
    4:  pygame.K_a,       # physical A
    7:  pygame.K_d,       # physical D
    22: pygame.K_s,       # physical S
    26: pygame.K_w,       # physical W
    44: pygame.K_SPACE,   # space bar
    8:  pygame.K_e,       # physical E
    9:  pygame.K_f,       # physical F  (eat)
    41: pygame.K_ESCAPE,  # escape
    43: pygame.K_TAB,     # tab
    79: pygame.K_RIGHT,   # right arrow
    80: pygame.K_LEFT,    # left arrow
    81: pygame.K_DOWN,    # down arrow
    82: pygame.K_UP,      # up arrow
    # Number row 1-9
    30: pygame.K_1,
    31: pygame.K_2,
    32: pygame.K_3,
    33: pygame.K_4,
    34: pygame.K_5,
    35: pygame.K_6,
    36: pygame.K_7,
    37: pygame.K_8,
    38: pygame.K_9,
}


def normalize(event: pygame.event.Event) -> int:
    """Return the normalized pygame key constant for a KEYDOWN/KEYUP event.

    Falls back to event.key when no scancode mapping is found.
    """
    return _SC_MAP.get(event.scancode, event.key)
