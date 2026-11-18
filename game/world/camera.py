"""
2D Camera System
"""

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
