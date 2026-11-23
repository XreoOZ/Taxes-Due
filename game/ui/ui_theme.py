"""Shared UI theme: resolution-aware font + pixel scaling.

Every UI element should size itself through ui_font()/upx() so the whole
interface stays proportional and readable at any window size, with a global
boost so text is larger than the original compact sizes.

Scale = UI_FONT_BOOST * min(window_w / 1280, window_h / 720), clamped.
Using the smaller axis ratio keeps the UI the same fraction of the screen
at any resolution or aspect ratio — fully proportional, never overflowing.
Fonts are cached per (size, bold, scale-bucket); call sites keep their
logical pixel sizes — the helpers do the multiplying.
"""
import pygame

from game.data.config import UI_FONT_BOOST

_FONT_CACHE = {}
_SCALE_CACHE = {"value": None, "w": 0, "h": 0}

# Reference design resolution: UI occupies this fraction of the screen.
_UI_REF_W = 1280
_UI_REF_H = 720
_UI_SCALE_MIN = 0.5
_UI_SCALE_MAX = 2.5


def ui_scale():
    """Current UI scale factor (proportional to window size)."""
    try:
        surf = pygame.display.get_surface()
        w, h = surf.get_size() if surf else (_UI_REF_W, _UI_REF_H)
    except Exception:
        w, h = _UI_REF_W, _UI_REF_H
    if _SCALE_CACHE["w"] != w or _SCALE_CACHE["h"] != h:
        res = min(w / _UI_REF_W, h / _UI_REF_H)
        res = max(_UI_SCALE_MIN, min(_UI_SCALE_MAX, res))
        _SCALE_CACHE["value"] = UI_FONT_BOOST * res
        _SCALE_CACHE["w"], _SCALE_CACHE["h"] = w, h
    return _SCALE_CACHE["value"]


def upx(px):
    """Scale a logical pixel size to current UI scale."""
    return max(1, int(round(float(px) * ui_scale())))


def ui_font(size, bold=False):
    """SysFont scaled by ui_scale(); cached per (size, bold, scale bucket)."""
    scale = ui_scale()
    bucket = int(scale * 20)  # ~5% granularity keeps cache small
    key = (int(size), bool(bold), bucket)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Segoe UI", max(8, int(round(size * scale))),
                                   bold=bold)
        _FONT_CACHE[key] = font
    return font


def clear_font_cache():
    _FONT_CACHE.clear()
