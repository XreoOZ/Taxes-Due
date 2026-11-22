"""Island terrain: a single finite landmass surrounded by infinite water.

The island shape is a radial blob whose boundary is displaced by a few
seeded sine harmonics plus smooth value noise. Because the boundary is a
single-valued function of angle, the land set is always one connected
mass — no detached islands, no square edges.

A module-level registry tracks the active terrain so walkability,
placement, rendering and the map overlay can query it without threading
a reference through every system. Infinite mode keeps ``_current`` as
``None`` and every tile counts as land.
"""
import math
import random

import pygame

try:
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is present in this project env
    _np = None

from game.data.config import (
    ISLAND_RADIUS_X_TILES,
    ISLAND_RADIUS_Y_TILES,
    ISLAND_EDGE_NOISE_AMP,
    ISLAND_BEACH_WIDTH,
    COLOR_WATER_DEEP,
    COLOR_WATER_SHALLOW,
    COLOR_SAND,
    COLOR_GRASS_A,
    COLOR_GRASS_B,
)


def _hash2(ix, iy, seed):
    """Deterministic integer hash -> [0, 1)."""
    h = (ix * 374761393 + iy * 668265263 + seed * 144665) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _value_noise(x, y, seed):
    """Smooth 2D value noise in [0, 1]."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    a = _hash2(ix, iy, seed)
    b = _hash2(ix + 1, iy, seed)
    c = _hash2(ix, iy + 1, seed)
    d = _hash2(ix + 1, iy + 1, seed)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


class IslandTerrain:
    """Seeded island landmass. All queries are pure functions of (gx, gy)."""

    def __init__(self, seed):
        self.seed = int(seed)
        rng = random.Random(self.seed)
        # Boundary harmonics: a few incommensurate sine terms give organic,
        # continent-like coastlines without ever splitting the landmass.
        self._harmonics = [
            (rng.randint(2, 4), rng.uniform(0.0, math.tau), rng.uniform(0.05, 0.11))
            for _ in range(4)
        ]
        self._noise_seed = rng.randint(1, 10 ** 9)
        self._noise_freq = rng.uniform(1.4, 2.2)
        self._noise_amp = rng.uniform(0.6, 1.0) * ISLAND_EDGE_NOISE_AMP
        # Conservative tile bounds used for cheap rejection and the map mask.
        self.min_gx = -ISLAND_RADIUS_X_TILES - 80
        self.max_gx = ISLAND_RADIUS_X_TILES + 80
        self.min_gy = -ISLAND_RADIUS_Y_TILES - 80
        self.max_gy = ISLAND_RADIUS_Y_TILES + 80
        # *** ESTABLISHED FEATURE — DO NOT REMOVE/REVERT ***
        # WARNING (FPS-critical, user-verified): land_value() runs hypot +
        # atan2 + harmonics + value noise per call. is_land() is invoked twice
        # per A* edge inside Pathfinder.can_traverse_edge, so uncached calls
        # cost ~130ms per failed pathfind — when the whole village repaths at
        # once (e.g. prayer exit) this dropped FPS to ~1. With this cache the
        # user verified 30+ AI exiting church prayer simultaneously stays
        # smooth. Terrain is static per IslandTerrain instance, so memoizing
        # per tile is safe. DO NOT remove this cache, DO NOT bypass it with
        # direct land_value() calls in hot paths (pathfinding/movement).
        self._land_cache = {}
        self._mask_surface = None
        # Pre-build the map mask now (~0.1s) so the first map open doesn't hitch.
        self.get_mask_surface()

    # ------------------------------------------------------------------
    # Shape queries
    # ------------------------------------------------------------------
    def _edge_offset(self, gx, gy):
        """Signed boundary displacement in normalized-radius units."""
        d = math.hypot(gx / ISLAND_RADIUS_X_TILES, gy / ISLAND_RADIUS_Y_TILES)
        if d <= 1e-6:
            theta = 0.0
        else:
            theta = math.atan2(gy / ISLAND_RADIUS_Y_TILES, gx / ISLAND_RADIUS_X_TILES)
        offset = sum(amp * math.sin(freq * theta + phase)
                     for freq, phase, amp in self._harmonics)
        # Smooth noise sampled on a coarse lattice keeps the coast organic.
        offset += (self._noise_amp
                   * (_value_noise(gx * self._noise_freq * 0.02,
                                   gy * self._noise_freq * 0.02,
                                   self._noise_seed) - 0.5) * 2.0)
        return offset

    def land_value(self, gx, gy):
        """<0 deep inland, ~0 coastline, >0 open water."""
        d = math.hypot(gx / ISLAND_RADIUS_X_TILES, gy / ISLAND_RADIUS_Y_TILES)
        return d + self._edge_offset(gx, gy) - 1.0

    def is_land(self, gx, gy):
        # *** ESTABLISHED — DO NOT REMOVE ***
        # PERF: this memoized result is load-bearing for FPS — see the
        # _land_cache warning in __init__. Never replace this lookup with
        # land_value().
        if gx < self.min_gx or gx > self.max_gx or gy < self.min_gy or gy > self.max_gy:
            return False
        key = (gx, gy)
        cached = self._land_cache.get(key)
        if cached is None:
            cached = self.land_value(gx, gy) < 0.0
            self._land_cache[key] = cached
        return cached

    def is_beach(self, gx, gy):
        if not self.is_land(gx, gy):
            return False
        return self.land_value(gx, gy) > -ISLAND_BEACH_WIDTH

    def is_water(self, gx, gy):
        return not self.is_land(gx, gy)

    def is_land_world(self, wx, wy, tile_size):
        return self.is_land(int(math.floor(wx / tile_size)),
                            int(math.floor(wy / tile_size)))

    # ------------------------------------------------------------------
    # Precomputed land mask for the map overlay (1 px per 2x2 tiles)
    # ------------------------------------------------------------------
    @staticmethod
    def _value_noise_np(x, y, seed):
        """Vectorized _value_noise returning an array in [0, 1]."""
        np = _np
        ix = np.floor(x).astype(np.int64)
        iy = np.floor(y).astype(np.int64)
        fx = x - ix
        fy = y - iy
        fx = fx * fx * (3.0 - 2.0 * fx)
        fy = fy * fy * (3.0 - 2.0 * fy)

        def h(a, b):
            v = (a * 374761393 + b * 668265263 + seed * 144665)
            v = v & 0xFFFFFFFF
            v = (v ^ (v >> 13)) * 1274126177
            v = v & 0xFFFFFFFF
            v = (v ^ (v >> 16)) & 0xFFFF
            return v.astype(np.float64) / 65535.0

        a = h(ix, iy)
        b = h(ix + 1, iy)
        c = h(ix, iy + 1)
        d = h(ix + 1, iy + 1)
        return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy

    def land_value_array(self, gx, gy):
        """Vectorized land_value(): <0 inland, ~0 coast, >0 water (numpy)."""
        np = _np
        nx = gx / ISLAND_RADIUS_X_TILES
        ny = gy / ISLAND_RADIUS_Y_TILES
        d = np.hypot(nx, ny)
        theta = np.arctan2(ny, nx)
        edge = np.zeros_like(d)
        for freq, phase, amp in self._harmonics:
            edge += amp * np.sin(freq * theta + phase)
        noise = self._value_noise_np(
            gx * self._noise_freq * 0.02, gy * self._noise_freq * 0.02,
            self._noise_seed,
        )
        return d + edge + self._noise_amp * (noise - 0.5) * 2.0 - 1.0

    def _mask_array(self, w, h, sample):
        """RGB array (h, w, 3) of the island mask."""
        np = _np
        xs = self.min_gx + np.arange(w, dtype=np.float64) * sample + sample // 2
        ys = self.min_gy + np.arange(h, dtype=np.float64) * sample + sample // 2
        gx, gy = np.meshgrid(xs, ys)
        lv = self.land_value_array(gx, gy)

        land = lv < 0.0
        beach = land & (lv > -ISLAND_BEACH_WIDTH)
        shallow = (~land) & (lv < ISLAND_BEACH_WIDTH * 3.0)
        grass_a = (gx + gy) % 2 == 0

        arr = np.empty((h, w, 3), dtype=np.uint8)
        arr[:, :] = COLOR_WATER_DEEP
        arr[shallow] = COLOR_WATER_SHALLOW
        arr[land & ~beach & grass_a] = COLOR_GRASS_A
        arr[land & ~beach & ~grass_a] = COLOR_GRASS_B
        arr[beach] = COLOR_SAND
        return arr

    def get_mask_surface(self, sample=2):
        """Pygame surface covering the island bbox; land/beach/water colors."""
        if self._mask_surface is not None:
            return self._mask_surface
        w_tiles = self.max_gx - self.min_gx + 1
        h_tiles = self.max_gy - self.min_gy + 1
        w = max(1, w_tiles // sample)
        h = max(1, h_tiles // sample)
        if _np is not None:
            from pygame.surfarray import make_surface
            arr = self._mask_array(w, h, sample)
            # make_surface expects (width, height, 3)
            self._mask_surface = make_surface(arr.transpose(1, 0, 2))
            return self._mask_surface

        surf = pygame.Surface((w, h))
        surf.fill(COLOR_WATER_DEEP)
        for py in range(h):
            gy = self.min_gy + py * sample + sample // 2
            for px in range(w):
                gx = self.min_gx + px * sample + sample // 2
                if self.is_land(gx, gy):
                    surf.set_at((px, py), COLOR_SAND if self.is_beach(gx, gy)
                                else (COLOR_GRASS_A if (gx + gy) % 2 == 0 else COLOR_GRASS_B))
                else:
                    if self.land_value(gx, gy) < ISLAND_BEACH_WIDTH * 3.0:
                        surf.set_at((px, py), COLOR_WATER_SHALLOW)
        self._mask_surface = surf
        return surf

    @property
    def mask_origin_tiles(self):
        return self.min_gx, self.min_gy

    @property
    def mask_sample(self):
        return 2


# ----------------------------------------------------------------------
# Active-terrain registry
# ----------------------------------------------------------------------
_current = None


def set_world(world_type, seed=None):
    """Activate a world type for the current session."""
    global _current
    if world_type == "island":
        _current = IslandTerrain(seed if seed is not None else random.randint(1, 10 ** 9))
    else:
        _current = None
    return _current


def get_terrain():
    return _current


def get_seed():
    return _current.seed if _current else None


def is_land_tile(gx, gy):
    t = _current
    return t is None or t.is_land(gx, gy)


def is_beach_tile(gx, gy):
    t = _current
    return t is not None and t.is_beach(gx, gy)


def is_land_world(wx, wy, tile_size):
    t = _current
    return t is None or t.is_land_world(wx, wy, tile_size)


def world_type():
    return "island" if _current is not None else "infinite"
