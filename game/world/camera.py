"""
2D Camera System
"""

import math

from game.config import (
    CAMERA_LERP_SPEED,
    CAMERA_ZOOM_DEFAULT,
    CAMERA_ZOOM_MIN,
    CAMERA_ZOOM_MAX,
    CAMERA_ZOOM_STEP
)

class Camera:
    def __init__(self, screen_w, screen_h):
        self.x = 0.0
        self.y = 0.0
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.offset_x = screen_w / 2.0
        self.offset_y = screen_h / 2.0
        self.lerp_speed = CAMERA_LERP_SPEED
        self.zoom = CAMERA_ZOOM_DEFAULT

    def resize(self, new_w, new_h):
        self.screen_w = new_w
        self.screen_h = new_h
        self.offset_x = new_w / 2.0
        self.offset_y = new_h / 2.0

    def follow(self, target):
        # Smooth interpolation menuju target
        self.x += (target.x - self.x) * self.lerp_speed
        self.y += (target.y - self.y) * self.lerp_speed

    def handle_zoom(self, delta):
        # delta positif = zoom in, negatif = zoom out
        self.zoom = round(max(CAMERA_ZOOM_MIN, min(CAMERA_ZOOM_MAX, self.zoom + delta * CAMERA_ZOOM_STEP)), 2)

    def world_to_screen(self, wx, wy):
        return (
            int((wx - self.x) * self.zoom + self.offset_x),
            int((wy - self.y) * self.zoom + self.offset_y)
        )

    def screen_to_world(self, sx, sy):
        return (
            (sx - self.offset_x) / self.zoom + self.x,
            (sy - self.offset_y) / self.zoom + self.y
        )

    def get_visible_world_bounds(self, screen_margin=0):
        """World rectangle currently visible at the active viewport size and zoom."""
        left, top = self.screen_to_world(-screen_margin, -screen_margin)
        right, bottom = self.screen_to_world(
            self.screen_w + screen_margin, self.screen_h + screen_margin
        )
        return left, top, right, bottom

    def get_visible_tile_bounds(self, tile_size, world_bounds=None):
        """Tile coordinates intersecting the current viewport, optionally clipped to a world rect."""
        left, top, right, bottom = self.get_visible_world_bounds()
        if world_bounds:
            bounds_left, bounds_top, bounds_right, bounds_bottom = world_bounds
            left, top = max(left, bounds_left), max(top, bounds_top)
            right, bottom = min(right, bounds_right), min(bottom, bounds_bottom)
        if right <= left or bottom <= top:
            return None
        return (
            math.floor(left / tile_size),
            math.floor(top / tile_size),
            math.ceil(right / tile_size) - 1,
            math.ceil(bottom / tile_size) - 1,
        )

    def iter_visible_tiles(self, occupied_tiles, tile_size, world_bounds=None):
        """Iterate only viewport-intersecting occupied tiles; zoom changes the iteration range."""
        tile_bounds = self.get_visible_tile_bounds(tile_size, world_bounds)
        if tile_bounds is None:
            return
        min_x, min_y, max_x, max_y = tile_bounds
        for gy in range(min_y, max_y + 1):
            for gx in range(min_x, max_x + 1):
                tile = (gx, gy)
                if tile in occupied_tiles:
                    yield tile

    def is_world_rect_visible(self, wx, wy, width, height, screen_margin=0):
        """Return whether any part of a world-space rectangle overlaps the viewport."""
        sx, sy = self.world_to_screen(wx, wy)
        ex, ey = self.world_to_screen(wx + width, wy + height)
        return not (
            ex < -screen_margin or ey < -screen_margin
            or sx > self.screen_w + screen_margin
            or sy > self.screen_h + screen_margin
        )
