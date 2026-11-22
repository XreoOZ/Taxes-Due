"""Island natural resources: forests (tree tiles) and ore mines (5x5).

Generated once per Island world from the world seed, so terrain, forest
floor tiles, initial trees and mines are fully deterministic. Only tree
*state* changes during play (mature -> empty -> growing -> mature); those
deltas are persisted as compact overrides in the save file.

Forest floor tiles are walkable but apply FOREST_MOVE_SPEED_FACTOR.
Trees may only be replanted on the exact tile they were cut from, and a
planted tree needs TREE_GROWTH_DAYS in-game days before it can be felled.
Mines are unlimited deposits; their tier only changes the per-hour yield.
"""
import math
import random

import pygame

from game.data.config import (
    FOREST_DENSITY_TIERS,
    FOREST_DENSITY_SAMPLE_AREA,
    FOREST_BIOME_NOISE_FREQ,
    FOREST_BIOME_OCTAVE2_FREQ_MULT,
    FOREST_BIOME_OCTAVE2_WEIGHT,
    FOREST_BIOME_THRESHOLD_BASE,
    FOREST_BIOME_THRESHOLD_STEP,
    FOREST_BIOME_MINE_CLEARING_TILES,
    FOREST_MAP_COLOR,
    FOREST_MOVE_SPEED_FACTOR,
    FOREST_TREE_CHUNK_TILES,
    TREE_GROWTH_DAYS,
    ISLAND_BEACH_WIDTH,
    MINE_SIZE_TILES,
    MINE_SPAWN_COUNT_MIN,
    MINE_SPAWN_COUNT_MAX,
    MINE_SPAWN_GUARANTEE_TYPE,
    MINE_SPAWN_GUARANTEE_DIST_MIN_TILES,
    MINE_SPAWN_GUARANTEE_DIST_MAX_TILES,
    MINE_TYPE_TABLE,
    MINE_YIELD_PER_INGAME_HOUR,
    TILE_SIZE,
)
from game.world import island as _island
from game.world.island import get_terrain, world_type

TREE_STATE_MATURE = "mature"
TREE_STATE_GROWING = "growing"
TREE_STATE_EMPTY = "empty"

# Island-wide forest abundance rolled once per world; sets biome coverage
# threshold and tree density tier.
FOREST_ISLAND_TIER_WEIGHTS = {1: 10, 2: 20, 3: 40, 4: 20, 5: 10}


def _weighted_choice(rng, weights):
    total = sum(weights.values())
    pick = rng.uniform(0, total)
    acc = 0.0
    for key, weight in weights.items():
        acc += weight
        if pick <= acc:
            return key
    return next(reversed(weights))


class NaturalResourceManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.reset()

    def reset(self):
        self.forest_tiles = set()      # (gx, gy) forest floor — walkable, slowed
        self.trees = {}                # (gx, gy) -> {"state", "planted_day"}
        self.mines = []                # [{"id","kind","anchor","tier","tiles"}]
        self._tree_claims = {}         # (gx, gy) -> worker_id
        self._tree_index = {}          # (chunk_x, chunk_y) -> [(gx, gy), ...]
        self._forest_mask = None       # map-overlay biome surface (lazy)
        self._forest_mask_dirty = True
        # Tiles suppressed by construction: (gx,gy) -> {"refs", "forest",
        # "tree"}. Forest floor and tree state are restored when the last
        # occupying structure is removed.
        self._suppressed = {}
        self._mature_count = 0
        self._growing_count = 0
        self._empty_count = 0
        self._recount_trees()

    def _build_tree_index(self):
        """Bucket tree tiles into fixed-size chunks so draw() only visits
        trees near the viewport instead of scanning every tree each frame."""
        chunk = FOREST_TREE_CHUNK_TILES
        index = {}
        for gx, gy in self.trees:
            key = (gx // chunk, gy // chunk)
            index.setdefault(key, []).append((gx, gy))
        self._tree_index = index

    # ------------------------------------------------------------------
    # Generation (deterministic from the island world seed)
    # ------------------------------------------------------------------
    def generate(self, seed):
        self.reset()
        if world_type() != "island":
            return
        terrain = get_terrain()
        if terrain is None:
            return
        rng = random.Random((int(seed) if seed is not None else 0) ^ 0x4E545552)
        # Mines first: the forest biome grows around them and leaves clearings.
        self._generate_mines(terrain, rng)
        self._generate_forests(terrain, rng)
        self._recount_trees()
        self._build_tree_index()
        self._forest_mask_dirty = True

    def _is_forestable(self, terrain, gx, gy):
        return terrain.is_land(gx, gy) and not terrain.is_beach(gx, gy)

    def _mine_keep_out_tiles(self):
        """Mine footprints plus a clearing margin — forest never grows here."""
        margin = FOREST_BIOME_MINE_CLEARING_TILES
        keep_out = set()
        for mine in self.mines:
            ax, ay = mine["anchor"]
            for gx in range(ax - margin, ax + MINE_SIZE_TILES + margin):
                for gy in range(ay - margin, ay + MINE_SIZE_TILES + margin):
                    keep_out.add((gx, gy))
        return keep_out

    def _generate_forests(self, terrain, rng):
        """Seeded value-noise biome covering the island landmass organically.

        Coverage threshold drops per island forest tier (Scarce -> Abundant);
        tree density inside the biome uses the same tier's FOREST_DENSITY_TIERS
        range. Two noise octaves give large forest masses with ragged edges.
        """
        island_tier = _weighted_choice(rng, FOREST_ISLAND_TIER_WEIGHTS)
        threshold = (FOREST_BIOME_THRESHOLD_BASE
                     - (island_tier - 1) * FOREST_BIOME_THRESHOLD_STEP)
        noise_seed = rng.randint(1, 10 ** 9)
        noise_seed2 = rng.randint(1, 10 ** 9)
        tier_cfg = FOREST_DENSITY_TIERS[island_tier]
        density = rng.uniform(tier_cfg["min"], tier_cfg["max"]) / (
            FOREST_DENSITY_SAMPLE_AREA * FOREST_DENSITY_SAMPLE_AREA)

        np = _island._np
        keep_out = self._mine_keep_out_tiles()
        min_gx, max_gx = terrain.min_gx, terrain.max_gx
        min_gy, max_gy = terrain.min_gy, terrain.max_gy

        if np is not None:
            xs = np.arange(min_gx, max_gx + 1, dtype=np.float64)
            ys = np.arange(min_gy, max_gy + 1, dtype=np.float64)
            gx, gy = np.meshgrid(xs, ys)
            lv = terrain.land_value_array(gx, gy)
            # land & inland of the beach band == forestable
            forestable = lv <= -ISLAND_BEACH_WIDTH
            n1 = _island.IslandTerrain._value_noise_np(
                gx * FOREST_BIOME_NOISE_FREQ, gy * FOREST_BIOME_NOISE_FREQ,
                noise_seed)
            n2 = _island.IslandTerrain._value_noise_np(
                gx * FOREST_BIOME_NOISE_FREQ * FOREST_BIOME_OCTAVE2_FREQ_MULT,
                gy * FOREST_BIOME_NOISE_FREQ * FOREST_BIOME_OCTAVE2_FREQ_MULT,
                noise_seed2)
            biome = ((1.0 - FOREST_BIOME_OCTAVE2_WEIGHT) * n1
                     + FOREST_BIOME_OCTAVE2_WEIGHT * n2)
            mask = forestable & (biome > threshold)
            for kx, ky in keep_out:
                if min_gx <= kx <= max_gx and min_gy <= ky <= max_gy:
                    mask[ky - min_gy, kx - min_gx] = False
            rows = np.argwhere(mask)
            tiles = [(int(min_gx + x), int(min_gy + y)) for y, x in rows]
        else:
            # Scalar fallback (numpy absent): per-tile noise, slower but rare.
            tiles = []
            for ty in range(min_gy, max_gy + 1):
                for tx in range(min_gx, max_gx + 1):
                    if not self._is_forestable(terrain, tx, ty):
                        continue
                    if (tx, ty) in keep_out:
                        continue
                    n1 = _island._value_noise(
                        tx * FOREST_BIOME_NOISE_FREQ,
                        ty * FOREST_BIOME_NOISE_FREQ, noise_seed)
                    n2 = _island._value_noise(
                        tx * FOREST_BIOME_NOISE_FREQ * FOREST_BIOME_OCTAVE2_FREQ_MULT,
                        ty * FOREST_BIOME_NOISE_FREQ * FOREST_BIOME_OCTAVE2_FREQ_MULT,
                        noise_seed2)
                    biome = ((1.0 - FOREST_BIOME_OCTAVE2_WEIGHT) * n1
                             + FOREST_BIOME_OCTAVE2_WEIGHT * n2)
                    if biome > threshold:
                        tiles.append((tx, ty))

        for gx, gy in tiles:
            self.forest_tiles.add((gx, gy))
            if rng.random() < density:
                self.trees[(gx, gy)] = {
                    "state": TREE_STATE_MATURE,
                    "planted_day": 0.0,
                }

    def _generate_mines(self, terrain, rng):
        count = rng.randint(MINE_SPAWN_COUNT_MIN, MINE_SPAWN_COUNT_MAX)
        occupied = set()

        def try_place_mine(kind=None, anchor=None):
            half = MINE_SIZE_TILES // 2
            if anchor is None:
                for _ in range(500):
                    cx = rng.randint(terrain.min_gx + half, terrain.max_gx - half)
                    cy = rng.randint(terrain.min_gy + half, terrain.max_gy - half)
                    ax, ay = cx - half, cy - half
                    if self._mine_anchor_valid(terrain, ax, ay, occupied):
                        anchor = (ax, ay)
                        break
            else:
                ax, ay = anchor
                if not self._mine_anchor_valid(terrain, ax, ay, occupied):
                    return None
            if anchor is None:
                return None
            ax, ay = anchor
            tiles = {(ax + dx, ay + dy)
                     for dx in range(MINE_SIZE_TILES)
                     for dy in range(MINE_SIZE_TILES)}
            if kind is None:
                kind = self._roll_mine_kind(rng)
            mine = {
                "id": f"mine_{len(self.mines)}",
                "kind": kind,
                "anchor": (ax, ay),
                "tier": rng.randint(1, len(MINE_YIELD_PER_INGAME_HOUR)),
                "tiles": tiles,
            }
            self.mines.append(mine)
            occupied.update(tiles)
            return mine

        # Guaranteed Stone Mine 50-100 tiles from the player spawn (0,0).
        guaranteed = self._place_guaranteed_mine(terrain, rng, occupied, try_place_mine)
        for _ in range(count - (0 if guaranteed is None else 1)):
            try_place_mine()

    def _mine_anchor_valid(self, terrain, ax, ay, occupied):
        tiles = {(ax + dx, ay + dy)
                 for dx in range(MINE_SIZE_TILES)
                 for dy in range(MINE_SIZE_TILES)}
        if tiles & occupied:
            return False
        for gx, gy in tiles:
            if not self._is_forestable(terrain, gx, gy):
                return False
            if (gx, gy) in self.forest_tiles:
                return False
        return True

    def _roll_mine_kind(self, rng):
        kinds = list(MINE_TYPE_TABLE.keys())
        weights = [MINE_TYPE_TABLE[k].get("weight", 1) for k in kinds]
        return rng.choices(kinds, weights=weights, k=1)[0]

    def _place_guaranteed_mine(self, terrain, rng, occupied, try_place_mine):
        half = MINE_SIZE_TILES // 2
        for _ in range(400):
            angle = rng.uniform(0, math.tau)
            dist = rng.uniform(MINE_SPAWN_GUARANTEE_DIST_MIN_TILES,
                               MINE_SPAWN_GUARANTEE_DIST_MAX_TILES)
            cx = int(round(math.cos(angle) * dist))
            cy = int(round(math.sin(angle) * dist))
            ax, ay = cx - half, cy - half
            if self._mine_anchor_valid(terrain, ax, ay, occupied):
                return try_place_mine(kind=MINE_SPAWN_GUARANTEE_TYPE, anchor=(ax, ay))
        return None

    # ------------------------------------------------------------------
    # Terrain queries
    # ------------------------------------------------------------------
    def is_forest_tile(self, gx, gy):
        return (int(gx), int(gy)) in self.forest_tiles

    # ------------------------------------------------------------------
    # Construction suppression — anything built on forest tiles annuls the
    # forest there until the tile is empty again (refcounted).
    # ------------------------------------------------------------------
    @staticmethod
    def _bump_tree_count(counters, entry, delta):
        state = (entry or {}).get("state")
        if state == TREE_STATE_MATURE:
            counters[0] += delta
        elif state == TREE_STATE_GROWING:
            counters[1] += delta
        elif state == TREE_STATE_EMPTY:
            counters[2] += delta

    # *** ESTABLISHED — DO NOT REGRESS ***
    # occupy/release are REFCOUNTED pairs: every occupy_tiles() call MUST be
    # matched by exactly one release_tiles() for the same tiles (guarded by
    # was_placed at call sites). Skipping occupy -> trees render inside
    # buildings; skipping release -> forest never regrows after demolition.
    # Released tiles restore the PRE-BUILD tree state — never auto-replant.
    def occupy_tiles(self, tiles):
        """Suppress forest floor + trees on tiles about to be built on."""
        changed = False
        counters = [self._mature_count, self._growing_count, self._empty_count]
        for gx, gy in tiles:
            key = (int(gx), int(gy))
            rec = self._suppressed.get(key)
            if rec is not None:
                rec["refs"] += 1
                continue
            was_forest = key in self.forest_tiles
            entry = self.trees.pop(key, None)
            if not was_forest and entry is None:
                continue
            if was_forest:
                self.forest_tiles.discard(key)
            self._bump_tree_count(counters, entry, -1)
            self._suppressed[key] = {"refs": 1, "forest": was_forest, "tree": entry}
            changed = True
        if changed:
            (self._mature_count, self._growing_count, self._empty_count) = counters
            self._rebuild_spatial()

    def release_tiles(self, tiles):
        """Restore suppressed forest when the last structure leaves a tile."""
        changed = False
        counters = [self._mature_count, self._growing_count, self._empty_count]
        for gx, gy in tiles:
            key = (int(gx), int(gy))
            rec = self._suppressed.get(key)
            if rec is None:
                continue
            rec["refs"] -= 1
            if rec["refs"] > 0:
                continue
            del self._suppressed[key]
            if rec["forest"]:
                self.forest_tiles.add(key)
            if rec["tree"] is not None:
                self.trees[key] = rec["tree"]
                self._bump_tree_count(counters, rec["tree"], +1)
            changed = True
        if changed:
            (self._mature_count, self._growing_count, self._empty_count) = counters
            self._rebuild_spatial()

    def _rebuild_spatial(self):
        self._build_tree_index()
        self._forest_mask_dirty = True

    def speed_factor_at(self, wx, wy, tile_size=TILE_SIZE):
        gx = int(math.floor(wx / tile_size))
        gy = int(math.floor(wy / tile_size))
        return FOREST_MOVE_SPEED_FACTOR if self.is_forest_tile(gx, gy) else 1.0

    def _apply_growth(self, tile, entry, current_day):
        if entry["state"] == TREE_STATE_GROWING and current_day is not None:
            if current_day - float(entry.get("planted_day", 0.0)) >= TREE_GROWTH_DAYS:
                entry["state"] = TREE_STATE_MATURE
        return entry["state"]

    def tree_state(self, gx, gy, current_day=None):
        entry = self.trees.get((int(gx), int(gy)))
        if entry is None:
            return None
        return self._apply_growth((int(gx), int(gy)), entry, current_day)

    def is_tree_mature(self, gx, gy, current_day=None):
        return self.tree_state(gx, gy, current_day) == TREE_STATE_MATURE

    def is_tree_claimed(self, gx, gy, exclude_worker_id=None):
        claim = self._tree_claims.get((int(gx), int(gy)))
        return claim is not None and str(claim) != str(exclude_worker_id)

    def claim_tree(self, gx, gy, worker_id):
        self._tree_claims[(int(gx), int(gy))] = worker_id

    def release_tree_claims(self, worker_id):
        wid = str(worker_id)
        for tile in [t for t, w in self._tree_claims.items() if str(w) == wid]:
            del self._tree_claims[tile]

    def _recount_trees(self):
        self._mature_count = self._growing_count = self._empty_count = 0
        for entry in self.trees.values():
            state = entry.get("state")
            if state == TREE_STATE_MATURE:
                self._mature_count += 1
            elif state == TREE_STATE_GROWING:
                self._growing_count += 1
            elif state == TREE_STATE_EMPTY:
                self._empty_count += 1

    def mature_tree_count(self):
        return self._mature_count

    def plantable_tile_count(self):
        return self._empty_count

    def nearest_tree(self, wx, wy, current_day=None, exclude_worker_id=None):
        """Nearest mature, unclaimed tree tile to a world position."""
        best = None
        best_d = float("inf")
        for (gx, gy), entry in self.trees.items():
            if entry.get("state") != TREE_STATE_MATURE:
                continue
            if current_day is not None:
                self._apply_growth((gx, gy), entry, current_day)
                if entry["state"] != TREE_STATE_MATURE:
                    continue
            if self.is_tree_claimed(gx, gy, exclude_worker_id):
                continue
            d = math.hypot((gx + 0.5) * TILE_SIZE - wx, (gy + 0.5) * TILE_SIZE - wy)
            if d < best_d:
                best_d = d
                best = (gx, gy)
        return best

    def nearest_replantable_tile(self, wx, wy, exclude_worker_id=None):
        """Nearest cut ('empty') forest tile — the only legal replant spots."""
        best = None
        best_d = float("inf")
        for (gx, gy), entry in self.trees.items():
            if entry.get("state") != TREE_STATE_EMPTY:
                continue
            if self.is_tree_claimed(gx, gy, exclude_worker_id):
                continue
            d = math.hypot((gx + 0.5) * TILE_SIZE - wx, (gy + 0.5) * TILE_SIZE - wy)
            if d < best_d:
                best_d = d
                best = (gx, gy)
        return best

    def cut_tree(self, gx, gy):
        entry = self.trees.get((int(gx), int(gy)))
        if entry is None or entry.get("state") != TREE_STATE_MATURE:
            return False
        entry["state"] = TREE_STATE_EMPTY
        entry["planted_day"] = 0.0
        self._tree_claims.pop((int(gx), int(gy)), None)
        self._mature_count -= 1
        self._empty_count += 1
        return True

    def plant_tree(self, gx, gy, current_day):
        entry = self.trees.get((int(gx), int(gy)))
        if entry is None or entry.get("state") != TREE_STATE_EMPTY:
            return False
        entry["state"] = TREE_STATE_GROWING
        entry["planted_day"] = float(current_day or 0.0)
        self._tree_claims.pop((int(gx), int(gy)), None)
        self._empty_count -= 1
        self._growing_count += 1
        return True

    # ------------------------------------------------------------------
    # Mines
    # ------------------------------------------------------------------
    def get_mine_at(self, gx, gy):
        point = (int(gx), int(gy))
        for mine in self.mines:
            if point in mine["tiles"]:
                return mine
        return None

    def mine_for_footprint(self, tiles):
        """Return the mine whose 5x5 tile set exactly equals `tiles`."""
        target = {(int(x), int(y)) for x, y in tiles}
        for mine in self.mines:
            if mine["tiles"] == target:
                return mine
        return None

    @staticmethod
    def mine_output_item(mine):
        return MINE_TYPE_TABLE.get(mine.get("kind"), {}).get("output_item", "Stone")

    @staticmethod
    def mine_yield_range(mine):
        cfg = MINE_YIELD_PER_INGAME_HOUR.get(int(mine.get("tier", 3)),
                                             MINE_YIELD_PER_INGAME_HOUR[3])
        return int(cfg["min"]), int(cfg["max"])

    @staticmethod
    def mine_tier_name(mine):
        cfg = MINE_YIELD_PER_INGAME_HOUR.get(int(mine.get("tier", 3)),
                                             MINE_YIELD_PER_INGAME_HOUR[3])
        return cfg["name"]

    # ------------------------------------------------------------------
    # Persistence — tree states are the only mutable world data; forests
    # and mines regenerate identically from the world seed.
    # ------------------------------------------------------------------
    def serialize_overrides(self):
        overrides = {}
        for key, entry in self.trees.items():
            state = entry.get("state")
            if state == TREE_STATE_MATURE and not entry.get("planted_day"):
                continue
            overrides[f"{key[0]},{key[1]}"] = [state, float(entry.get("planted_day", 0.0))]
        return overrides

    def apply_overrides(self, overrides):
        if not overrides:
            return
        for key, value in overrides.items():
            try:
                gx, gy = (int(part) for part in str(key).split(","))
            except (TypeError, ValueError):
                continue
            entry = self.trees.get((gx, gy))
            if entry is None:
                continue
            state, planted_day = value[0], float(value[1]) if len(value) > 1 else 0.0
            entry["state"] = state
            entry["planted_day"] = planted_day
        self._recount_trees()

    # ------------------------------------------------------------------
    # Rendering — forest floor tint, trees and mine heads (visible tiles only)
    # ------------------------------------------------------------------
    def _tile_sprite(self, cache_attr, size, color):
        cache = getattr(self, cache_attr, None)
        if cache is None or cache.get_size() != (size, size):
            sprite = pygame.Surface((size, size), pygame.SRCALPHA)
            sprite.fill(color)
            setattr(self, cache_attr, sprite)
            cache = sprite
        return cache

    def draw(self, surface, camera, tile_size=TILE_SIZE):
        if not self.forest_tiles and not self.mines:
            return
        w, h = camera.screen_w, camera.screen_h
        tl = camera.screen_to_world(0, 0)
        br = camera.screen_to_world(w, h)
        min_gx = int(math.floor(tl[0] / tile_size)) - 1
        max_gx = int(math.ceil(br[0] / tile_size)) + 1
        min_gy = int(math.floor(tl[1] / tile_size)) - 1
        max_gy = int(math.ceil(br[1] / tile_size)) + 1

        s = max(1, int(math.ceil(tile_size * camera.zoom)))
        forest_sprite = self._tile_sprite("_forest_sprite", s, (18, 68, 32, 110))
        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                if (gx, gy) not in self.forest_tiles:
                    continue
                sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
                surface.blit(forest_sprite, (sx, sy))

        self._draw_trees(surface, camera, min_gx, max_gx, min_gy, max_gy,
                         tile_size)

        for mine in self.mines:
            ax, ay = mine["anchor"]
            if not (ax + MINE_SIZE_TILES - 1 < min_gx or ax > max_gx
                    or ay + MINE_SIZE_TILES - 1 < min_gy or ay > max_gy):
                self._draw_mine(surface, camera, mine, tile_size, s)

    def _draw_trees(self, surface, camera, min_gx, max_gx, min_gy, max_gy,
                    tile_size):
        """Chunked tree rendering: only buckets overlapping the viewport."""
        chunk = FOREST_TREE_CHUNK_TILES
        cx0, cx1 = min_gx // chunk, max_gx // chunk
        cy0, cy1 = min_gy // chunk, max_gy // chunk
        zoom = camera.zoom
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                for gx, gy in self._tree_index.get((cx, cy), ()):
                    entry = self.trees.get((gx, gy))
                    if entry is None:
                        continue
                    state = entry.get("state")
                    if state == TREE_STATE_EMPTY:
                        continue
                    sx, sy = camera.world_to_screen(
                        (gx + 0.5) * tile_size, (gy + 0.5) * tile_size)
                    # Deterministic per-tile variation keeps the forest from
                    # looking like stamped copies.
                    variant = (gx * 31 + gy * 17) % 3
                    r = max(3, int(tile_size * 0.30 * zoom))
                    if state == TREE_STATE_GROWING:
                        self._draw_sapling(surface, sx, sy, r, variant)
                        continue
                    self._draw_mature_tree(surface, sx, sy, r, variant)

    @staticmethod
    def _draw_sapling(surface, sx, sy, r, variant):
        stem = (139, 90, 43)
        pygame.draw.line(surface, stem,
                         (sx, sy), (sx, sy - r), max(1, r // 5))
        leaf = ((34, 197, 94), (16, 185, 129), (34, 139, 74))[variant]
        NaturalResourceManager._draw_pine(surface, sx, sy - r,
                                          max(2, int(r * 0.45)), leaf,
                                          light=leaf)

    @staticmethod
    def _draw_pine(surface, cx, base_y, size, dark, mid=None, light=None):
        """Conifer silhouette: three stacked triangles, widest at the
        bottom, apex on top — reads as a pine from a top-down view."""
        mid = mid or dark
        light = light or mid
        # (width_frac, bottom_y_off, top_y_off) per tier, relative to `size`.
        tiers = (
            (1.00, 0.00, -0.85),
            (0.72, -0.60, -1.35),
            (0.44, -1.10, -1.80),
        )
        for width_frac, y0, y1 in tiers:
            w = size * width_frac
            by = base_y + y0 * size
            ty = base_y + y1 * size
            # dark outline tier, then a slightly smaller mid tier on top
            pygame.draw.polygon(surface, dark,
                                [(cx - w / 2, by), (cx + w / 2, by),
                                 (cx, ty)])
            iw = w * 0.72
            iy = ty + (by - ty) * 0.18
            pygame.draw.polygon(surface, mid,
                                [(cx - iw / 2, by - (by - iy) * 0.4),
                                 (cx + iw / 2, by - (by - iy) * 0.4),
                                 (cx, iy)])
        # highlight wedge inside the top tier for a lit look
        pygame.draw.polygon(surface, light,
                            [(cx - size * 0.10, base_y - 1.15 * size),
                             (cx + size * 0.10, base_y - 1.15 * size),
                             (cx, base_y - 1.68 * size)])

    @staticmethod
    def _draw_mature_tree(surface, sx, sy, r, variant):
        palettes = (
            ((8, 84, 42), (21, 128, 61), (74, 222, 128)),    # classic green
            ((4, 96, 78), (5, 150, 105), (52, 211, 153)),     # teal
            ((12, 64, 34), (22, 101, 52), (60, 180, 110)),    # deep forest
        )
        dark, mid, light = palettes[variant]
        trunk_w = max(2, int(r * 0.22))
        trunk_h = int(r * 0.45)
        pygame.draw.rect(surface, (101, 67, 33),
                         (sx - trunk_w // 2, sy - trunk_h // 2,
                          trunk_w, trunk_h))
        NaturalResourceManager._draw_pine(surface, sx,
                                          sy - r * 0.30, r,
                                          dark, mid, light)

    def _draw_mine(self, surface, camera, mine, tile_size, s):
        rock = (100, 116, 139)
        ax, ay = mine["anchor"]
        rock_sprite = self._tile_sprite("_mine_sprite", s, (71, 85, 105, 120))
        for gx, gy in mine["tiles"]:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            surface.blit(rock_sprite, (sx, sy))
            pygame.draw.rect(surface, rock, (sx, sy, s, s), 1)
        # Center marker: tier-colored pick head.
        cx, cy = camera.world_to_screen(
            (ax + MINE_SIZE_TILES / 2.0) * tile_size,
            (ay + MINE_SIZE_TILES / 2.0) * tile_size)
        r = max(6, int(tile_size * 0.55 * camera.zoom))
        tier_colors = {1: (148, 163, 184), 2: (100, 116, 139), 3: (71, 85, 105),
                       4: (180, 83, 9), 5: (234, 179, 8)}
        color = tier_colors.get(int(mine.get("tier", 3)), rock)
        pygame.draw.circle(surface, color, (cx, cy), r)
        pygame.draw.circle(surface, (15, 23, 42), (cx, cy), r, max(1, int(camera.zoom * 2)))
        # Pickaxe glyph: handle + curved head (no unicode/emoji glyphs).
        lw = max(2, int(camera.zoom * 2.5))
        handle = (cx - r // 2, cy + r // 2, cx + r // 2, cy - r // 2)
        pygame.draw.line(surface, (226, 232, 240), handle[:2], handle[2:], lw)
        head_rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
        pygame.draw.arc(surface, (226, 232, 240), head_rect,
                        math.radians(210), math.radians(330), lw)


    # ------------------------------------------------------------------
    # Map overlay: biome mask aligned with the island terrain mask
    # ------------------------------------------------------------------
    def get_forest_mask_surface(self):
        """RGBA surface (same origin/sample as terrain mask) tinting forest
        tiles, for the world-map overlay. Rebuilt lazily; forest floor is
        static after generation so the mask never needs invalidation."""
        if not self._forest_mask_dirty and self._forest_mask is not None:
            return self._forest_mask
        terrain = get_terrain()
        if terrain is None or not self.forest_tiles:
            self._forest_mask = None
            self._forest_mask_dirty = False
            return None
        sample = terrain.mask_sample
        min_gx, min_gy = terrain.mask_origin_tiles
        w_tiles = terrain.max_gx - terrain.min_gx + 1
        h_tiles = terrain.max_gy - terrain.min_gy + 1
        w = max(1, w_tiles // sample)
        h = max(1, h_tiles // sample)
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        px = pygame.PixelArray(surf)
        color = FOREST_MAP_COLOR + (150,)
        inv = 1.0 / sample
        for gx, gy in self.forest_tiles:
            mx = int((gx - min_gx) * inv)
            my = int((gy - min_gy) * inv)
            if 0 <= mx < w and 0 <= my < h:
                px[mx, my] = color
        px.close()
        self._forest_mask = surf
        self._forest_mask_dirty = False
        return surf


_NATURAL_RESOURCES = None


def get_natural_resources():
    global _NATURAL_RESOURCES
    if _NATURAL_RESOURCES is None:
        _NATURAL_RESOURCES = NaturalResourceManager.get_instance()
    return _NATURAL_RESOURCES
