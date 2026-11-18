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

        # Gambar tiles rumput pedesaan
        for col in range(start_col, end_col + 1):
            for row in range(start_row, end_row + 1):
                wx = col * self.tile_size
                wy = row * self.tile_size
                sx, sy = camera.world_to_screen(wx, wy)

                is_even = (col + row) % 2 == 0
                color = COLOR_GRASS_A if is_even else COLOR_GRASS_B
                
                rect = pygame.Rect(sx, sy, scaled_tile + 1, scaled_tile + 1)
                pygame.draw.rect(surface, color, rect)

        # Gambar garis grid subtle (berguna untuk penempatan bangunan desa)
        grid_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for col in range(start_col, end_col + 1):
            wx = col * self.tile_size
            sx, _ = camera.world_to_screen(wx, 0)
            if 0 <= sx <= w:
                pygame.draw.line(grid_surf, COLOR_GRID, (sx, 0), (sx, h))

        for row in range(start_row, end_row + 1):
            wy = row * self.tile_size
            _, sy = camera.world_to_screen(0, wy)
            if 0 <= sy <= h:
                pygame.draw.line(grid_surf, COLOR_GRID, (0, sy), (w, sy))

        surface.blit(grid_surf, (0, 0))

        # Town Center Marker di titik (0, 0)
        cx, cy = camera.world_to_screen(0, 0)
        center_r = max(4, int(48 * camera.zoom))
        cross_len = max(2, int(16 * camera.zoom))
        marker_color = (255, 255, 255, 90)
        
        marker_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.circle(marker_surf, marker_color, (cx, cy), center_r, max(1, int(2 * camera.zoom)))
        pygame.draw.line(marker_surf, marker_color, (cx - cross_len, cy), (cx + cross_len, cy), max(1, int(2 * camera.zoom)))
        pygame.draw.line(marker_surf, marker_color, (cx, cy - cross_len), (cx, cy + cross_len), max(1, int(2 * camera.zoom)))
        surface.blit(marker_surf, (0, 0))

        # Label Town Center
        label = self.font.render("Town Center (0, 0)", True, (240, 240, 240))
        surface.blit(label, (cx - label.get_width() // 2, cy - center_r - 20))
