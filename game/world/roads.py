"""Player-built road tiles: a flat tile layer giving movement speed bonuses.

Roads are placed instantly by drag-painting (no construction sites), cost
resources per tile, annul forest underneath like any other structure, and
are removed through the Destroy mode with no refund. State is a simple
{(gx, gy): road_type} map persisted in the save file.
"""
import math

import pygame

from game.data.config import (
    ROAD_TYPES,
    TILE_SIZE,
)


class RoadManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.tiles = {}  # (gx, gy) -> road_type id
        self._sprites = {}

    def reset(self):
        self.tiles.clear()
        self._sprites.clear()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def road_type_at(self, gx, gy):
        return self.tiles.get((int(gx), int(gy)))

    def speed_factor_at(self, wx, wy, tile_size=TILE_SIZE):
        gx = int(math.floor(wx / tile_size))
        gy = int(math.floor(wy / tile_size))
        rtype = self.tiles.get((gx, gy))
        if rtype is None:
            return 1.0
        return float(ROAD_TYPES.get(rtype, {}).get("speed_multiplier", 1.0))

    # ------------------------------------------------------------------
    # Mutation — forest suppression is refcounted inside NaturalResourceManager
    # ------------------------------------------------------------------
    def set_tiles(self, tiles, road_type):
        """Place `road_type` on `tiles` (a set of (gx, gy)); skips existing."""
        from game.world.natural_resources import get_natural_resources
        new_tiles = [t for t in tiles if (int(t[0]), int(t[1])) not in self.tiles]
        if not new_tiles:
            return 0
        for gx, gy in new_tiles:
            self.tiles[(int(gx), int(gy))] = road_type
        get_natural_resources().occupy_tiles(new_tiles)
        return len(new_tiles)

    def remove_tiles(self, tiles):
        """Remove road tiles; returns count removed. No refund."""
        from game.world.natural_resources import get_natural_resources
        removed = []
        for gx, gy in tiles:
            key = (int(gx), int(gy))
            if key in self.tiles:
                del self.tiles[key]
                removed.append(key)
        if removed:
            get_natural_resources().release_tiles(removed)
        return len(removed)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def serialize(self):
        return [[gx, gy, rtype] for (gx, gy), rtype in self.tiles.items()]

    def load(self, data):
        self.reset()
        for entry in data or []:
            try:
                gx, gy, rtype = int(entry[0]), int(entry[1]), str(entry[2])
            except (TypeError, ValueError, IndexError):
                continue
            if rtype in ROAD_TYPES:
                self.tiles[(gx, gy)] = rtype

    # ------------------------------------------------------------------
    # Rendering — flat colored tile with a subtle wheel-worn center line
    # ------------------------------------------------------------------
    def draw(self, surface, camera, tile_size=TILE_SIZE):
        if not self.tiles:
            return
        w, h = camera.screen_w, camera.screen_h
        tl = camera.screen_to_world(0, 0)
        br = camera.screen_to_world(w, h)
        min_gx = int(math.floor(tl[0] / tile_size)) - 1
        max_gx = int(math.ceil(br[0] / tile_size)) + 1
        min_gy = int(math.floor(tl[1] / tile_size)) - 1
        max_gy = int(math.ceil(br[1] / tile_size)) + 1
        s = max(1, int(math.ceil(tile_size * camera.zoom)))
        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                rtype = self.tiles.get((gx, gy))
                if rtype is None:
                    continue
                cfg = ROAD_TYPES.get(rtype)
                if cfg is None:
                    continue
                sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
                color = cfg["color"]
                sprite = self._sprites.get((rtype, s))
                if sprite is None:
                    sprite = pygame.Surface((s, s))
                    sprite.fill(color)
                    # Two subtle wheel-rut lines along the tile's long axis.
                    rut = cfg.get("rut_color", tuple(max(0, c - 30) for c in color))
                    pygame.draw.line(sprite, rut, (0, s // 3), (s, s // 3), 1)
                    pygame.draw.line(sprite, rut, (0, 2 * s // 3), (s, 2 * s // 3), 1)
                    self._sprites[(rtype, s)] = sprite
                surface.blit(sprite, (sx, sy))


_ROAD_MANAGER = None


def get_roads():
    global _ROAD_MANAGER
    if _ROAD_MANAGER is None:
        _ROAD_MANAGER = RoadManager()
    return _ROAD_MANAGER
