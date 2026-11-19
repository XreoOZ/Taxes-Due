"""
World and Map System
"""

import math
import pygame
from game.config import COLOR_GRASS_A, COLOR_GRASS_B, COLOR_GRID, TILE_SIZE

class World:
    def __init__(self, tile_size=TILE_SIZE):
        self.tile_size = tile_size
        self.font = None
        self._terrain_surface = None
        self._terrain_key = None
        self._grid_surface = None
        self._grid_key = None
        self._marker_surfaces = {}
        self._town_center_label = None

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 14)

    def draw(self, surface, camera):
        self._ensure_font()

        w, h = camera.screen_w, camera.screen_h
        
        # Hitung batas dunia yang terlihat di layar kamera (akurat terhadap zoom)
        top_left_w = camera.screen_to_world(0, 0)
        bot_right_w = camera.screen_to_world(w, h)
        
        left, top = top_left_w
        right, bottom = bot_right_w

        start_col = int(math.floor(left / self.tile_size)) - 1
        end_col = int(math.ceil(right / self.tile_size)) + 1
        start_row = int(math.floor(top / self.tile_size)) - 1
        end_row = int(math.ceil(bottom / self.tile_size)) + 1

        scaled_tile = max(1, math.ceil(self.tile_size * camera.zoom))

        terrain_key = (w, h, camera.x, camera.y, camera.zoom,
                       start_col, end_col, start_row, end_row)
        if self._terrain_key != terrain_key:
            if self._terrain_surface is None or self._terrain_surface.get_size() != (w, h):
                self._terrain_surface = pygame.Surface((w, h))
            self._terrain_surface.fill(COLOR_GRASS_A)
            for col in range(start_col, end_col + 1):
                for row in range(start_row, end_row + 1):
                    sx, sy = camera.world_to_screen(col * self.tile_size, row * self.tile_size)
                    color = COLOR_GRASS_A if (col + row) % 2 == 0 else COLOR_GRASS_B
                    pygame.draw.rect(self._terrain_surface, color,
                                     (sx, sy, scaled_tile + 1, scaled_tile + 1))
            self._terrain_key = terrain_key
        surface.blit(self._terrain_surface, (0, 0))

        # The overlay only changes when the camera, zoom or viewport changes.
        grid_key = (w, h, camera.x, camera.y, camera.zoom,
                    start_col, end_col, start_row, end_row)
        if self._grid_key != grid_key:
            if self._grid_surface is None or self._grid_surface.get_size() != (w, h):
                self._grid_surface = pygame.Surface((w, h), pygame.SRCALPHA)
            else:
                self._grid_surface.fill((0, 0, 0, 0))
            for col in range(start_col, end_col + 1):
                wx = col * self.tile_size
                sx, _ = camera.world_to_screen(wx, 0)
                if 0 <= sx <= w:
                    pygame.draw.line(self._grid_surface, COLOR_GRID, (sx, 0), (sx, h))

            for row in range(start_row, end_row + 1):
                wy = row * self.tile_size
                _, sy = camera.world_to_screen(0, wy)
                if 0 <= sy <= h:
                    pygame.draw.line(self._grid_surface, COLOR_GRID, (0, sy), (w, sy))
            self._grid_key = grid_key

        surface.blit(self._grid_surface, (0, 0))

        # Town Center Marker di titik (0, 0)
        cx, cy = camera.world_to_screen(0, 0)
        center_r = max(4, int(48 * camera.zoom))
        cross_len = max(2, int(16 * camera.zoom))
        marker_width = max(1, int(2 * camera.zoom))
        marker_key = (center_r, cross_len, marker_width)
        marker_surf = self._marker_surfaces.get(marker_key)
        if marker_surf is None:
            marker_size = center_r * 2 + 1
            marker_surf = pygame.Surface((marker_size, marker_size), pygame.SRCALPHA)
            marker_center = (center_r, center_r)
            marker_color = (255, 255, 255, 90)
            pygame.draw.circle(marker_surf, marker_color, marker_center, center_r, marker_width)
            pygame.draw.line(marker_surf, marker_color,
                             (center_r - cross_len, center_r), (center_r + cross_len, center_r), marker_width)
            pygame.draw.line(marker_surf, marker_color,
                             (center_r, center_r - cross_len), (center_r, center_r + cross_len), marker_width)
            self._marker_surfaces[marker_key] = marker_surf
        surface.blit(marker_surf, (cx - center_r, cy - center_r))

        # Label Town Center
        if self._town_center_label is None:
            self._town_center_label = self.font.render("Town Center (0, 0)", True, (240, 240, 240))
        surface.blit(self._town_center_label,
                     (cx - self._town_center_label.get_width() // 2, cy - center_r - 20))
