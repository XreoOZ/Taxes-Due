"""Demolition site: a building marked for teardown with refund progress."""
import math
import pygame
from game.render_cache import alpha_fill_surface
from game.config import (
    BUILDING_TYPES,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    DEMOLISH_DURATION_SECONDS,
    DEMOLITION_REFUND_RATIO,
)

class DemolitionSite:
    def __init__(self, building):
        self.building = building
        self.tiles = set(building.tiles)
        self.grid_x = building.grid_x
        self.grid_y = building.grid_y
        self.tiles_w = building.tiles_w
        self.tiles_h = building.tiles_h
        self.name = f"Demolish {building.name}"
        self.progress = 0.0
        self.duration = DEMOLISH_DURATION_SECONDS

        total_tiles = len(self.tiles)
        b_cfg = BUILDING_TYPES.get(building.building_type, BUILDING_TYPES["wooden_structure"])
        cost_w = b_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
        cost_s = b_cfg.get("cost_stone", COST_PER_BLOCK_STONE)
        self.refund_wood = int(total_tiles * cost_w * DEMOLITION_REFUND_RATIO)
        self.refund_stone = int(total_tiles * cost_s * DEMOLITION_REFUND_RATIO)
        self.font = None

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 10, bold=True)

    def is_complete(self):
        return self.progress >= self.duration

    def progress_fraction(self):
        return min(1.0, self.progress / self.duration) if self.duration > 0 else 0.0

    def get_center_world(self, tile_size):
        return self.building.get_center_world(tile_size)

    def overlaps_tiles(self, tiles):
        return bool(self.tiles & tiles)

    def draw(self, surface, camera, tile_size):
        if self.tiles and not camera.is_world_rect_visible(
                self.grid_x * tile_size, self.grid_y * tile_size,
                self.tiles_w * tile_size, self.tiles_h * tile_size):
            return
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        # Overlay merah pada bangunan yang sedang dihancurkan
        world_bounds = (
            self.grid_x * tile_size, self.grid_y * tile_size,
            (self.grid_x + self.tiles_w) * tile_size,
            (self.grid_y + self.tiles_h) * tile_size,
        )
        visible_tiles = list(camera.iter_visible_tiles(self.tiles, tile_size, world_bounds))
        for (gx, gy) in visible_tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            tile_surf = alpha_fill_surface(scaled_tile + 1, scaled_tile + 1, (220, 38, 38, 90))
            surface.blit(tile_surf, (sx, sy))
            pygame.draw.rect(surface, (239, 68, 68), (sx, sy, scaled_tile + 1, scaled_tile + 1), width=1)

        # Progress bar pembongkaran
        cx, cy = self.get_center_world(tile_size)
        scx, scy = camera.world_to_screen(cx, self.grid_y * tile_size)

        bar_w = max(100, min(240, int(len(self.tiles) * 12 * camera.zoom)))
        bar_h = 10
        bar_x = scx - bar_w // 2
        bar_y = scy - 26

        pygame.draw.rect(surface, (15, 23, 42, 220), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), border_radius=4)
        pygame.draw.rect(surface, (239, 68, 68), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), width=1, border_radius=4)

        pct = min(1.0, self.progress / self.duration)
        fill_w = int(bar_w * pct)
        if fill_w > 0:
            pygame.draw.rect(surface, (239, 68, 68), (bar_x, bar_y, fill_w, bar_h), border_radius=3)

        lbl_txt = f"Demolishing: {int(pct * 100)}% (+{self.refund_wood}W, +{self.refund_stone}S)"
        txt_surf = self.font.render(lbl_txt, True, (255, 255, 255))
        surface.blit(txt_surf, (bar_x + (bar_w - txt_surf.get_width()) // 2, bar_y - 14))

