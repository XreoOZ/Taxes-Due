"""Shared UI theme: resolution-aware font + pixel scaling.

Every UI element should size itself through ui_font()/upx() so the whole
interface stays proportional and readable at any window size, with a global
boost so text is larger than the original compact sizes.

Scale = UI_FONT_BOOST * clamp(window_height / 720, 0.8, 2.0)
Fonts are cached per (size, bold, scale-bucket); call sites keep their
logical pixel sizes — the helpers do the multiplying.
"""
import pygame

from game.data.config import UI_FONT_BOOST

_FONT_CACHE = {}
_SCALE_CACHE = {"value": None, "w": 0, "h": 0}


def ui_scale():
    """Current UI scale factor (boost * resolution ratio)."""
    try:
        surf = pygame.display.get_surface()
        w, h = surf.get_size() if surf else (1280, 720)
    except Exception:
        w, h = 1280, 720
    if _SCALE_CACHE["w"] != w or _SCALE_CACHE["h"] != h:
        res = max(0.8, min(2.0, h / 720.0))
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
