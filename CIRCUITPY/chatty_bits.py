"""Small helpers shared by the Matrix node's files: settings, a millisecond clock, dimming
(and the red night glow)."""
# pylint: disable=import-error,broad-except
import os
import time

try:
    from secrets import secrets as SECRETS
except ImportError:
    SECRETS = {}


def setting(key, default=None):
    if key in SECRETS:
        return SECRETS[key]
    try:
        value = os.getenv(key.upper())
    except Exception:
        value = None
    return default if value is None else value


def flag(value):
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def now_ms():
    return time.monotonic_ns() // 1000000


RED = [False]   # the red night glow is on (chatty_matrix sets it): dim() gives shades of red


def dim(color, level):
    if RED[0]:
        r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
        v = (3 * max(r, g, b) + (77 * r + 150 * g + 29 * b) // 128) // 5
        return int(min(v, 255) * min(level, 1)) << 16
    if level >= 1:
        return color
    r = int(((color >> 16) & 255) * level)
    g = int(((color >> 8) & 255) * level)
    b = int((color & 255) * level)
    return (r << 16) | (g << 8) | b
