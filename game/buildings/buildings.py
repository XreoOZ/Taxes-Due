"""
Building & Construction System (Arbitrary Connected Shapes, Player-Placed Doors, Zero Templates)
"""

import math
import time
import pygame
from game.config import (
    TILE_SIZE,
    BUILDING_TYPES,
    BUILD_DURATION_SECONDS,
    DEMOLISH_DURATION_SECONDS,
    DEMOLITION_REFUND_RATIO,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    COLOR_BUILDING_WALL,
    COLOR_BUILDING_WALL_OUTLINE,
    COLOR_BUILDING_FLOOR,
    COLOR_BUILDING_FLOOR_ALT,
    COLOR_BUILDING_DOOR,
    COLOR_STONE_WALL,
    COLOR_STONE_WALL_OUTLINE,
    COLOR_STONE_FLOOR,
    COLOR_STONE_FLOOR_ALT,
    COLOR_STONE_DOOR
)
from game.permits import get_exterior_edges_for_tile

class ConstructionSite:
    def __init__(self, building_type, tiles, door_pos=None, door_side=None):
        self.building_type = building_type
        self.type_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])
        self.tiles = set(tiles)
        self._recalculate_bounds()
        self.name = f"{self.type_cfg['name']} ({len(self.tiles)} tiles)"

        # Door Placement
        if self.type_cfg.get("has_door", True) is False or self.building_type == "well":
            self.door_pos = None
            self.door_side = None
            self.is_solid = True
        else:
            self.door_pos, self.door_side = self._resolve_door(door_pos, door_side)
            self.is_solid = False

        total_tiles = len(self.tiles)
        if self.type_cfg.get("fixed_cost", False):
            self.required_cost = {
                "Wood": self.type_cfg.get("cost_wood", 5),
                "Stone": self.type_cfg.get("cost_stone", 20)
            }
        else:
            cost_w = self.type_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
            cost_s = self.type_cfg.get("cost_stone", COST_PER_BLOCK_STONE)
            self.required_cost = {
                "Wood": total_tiles * cost_w,
                "Stone": total_tiles * cost_s
            }
        self.delivered_cost = {res: 0 for res in self.required_cost}
        self.reserved_cost = {res: 0 for res in self.required_cost}
        self.build_progress = 0.0
        self.font = None

    def get_wall_rects(self, tile_size):
        # Construction sites are open blueprints/groundwork; workers must be able to walk onto them to build!
        return []

    def _recalculate_bounds(self):
        if self.tiles:
            self.grid_x = min(x for x, y in self.tiles)
            self.grid_y = min(y for x, y in self.tiles)
            self.tiles_w = max(x for x, y in self.tiles) - self.grid_x + 1
            self.tiles_h = max(y for x, y in self.tiles) - self.grid_y + 1
        else:
            self.grid_x, self.grid_y, self.tiles_w, self.tiles_h = 0, 0, 0, 0

    def _resolve_door(self, door_pos, door_side):
        if door_pos and door_pos in self.tiles:
            edges = get_exterior_edges_for_tile(door_pos, self.tiles)
            if edges:
                side = door_side if door_side in edges else edges[0]
                return door_pos, side

        # Default fallback door: Southernmost tile with a bottom edge
        sorted_tiles = sorted(self.tiles, key=lambda t: (-t[1], t[0]))
        for t in sorted_tiles:
            edges = get_exterior_edges_for_tile(t, self.tiles)
            if "bottom" in edges:
                return t, "bottom"
            if edges:
                return t, edges[0]

        first_tile = next(iter(self.tiles))
        return first_tile, "bottom"

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 10, bold=True)

    @property
    def rotation(self):
        side_map = {"bottom": 0, "left": 1, "top": 2, "right": 3}
        return side_map.get(getattr(self, "door_side", "bottom"), 0)

    def total_required(self):
        return sum(self.required_cost.values())

    def total_delivered(self):
        return sum(self.delivered_cost.values())

    def is_materials_complete(self):
        return all(self.delivered_cost[res] >= self.required_cost[res] for res in self.required_cost)

    def is_complete(self):
        return self.build_progress >= BUILD_DURATION_SECONDS

    def overlaps_tiles(self, tiles):
        return bool(self.tiles & tiles)

    def get_needed_resource(self):
        for res, required in self.required_cost.items():
            delivered = self.delivered_cost.get(res, 0)
            reserved = self.reserved_cost.get(res, 0)
            if delivered + reserved < required:
                return res
        return None

    def reserve_resource(self, res, amount):
        needed = self.required_cost[res] - (self.delivered_cost[res] + self.reserved_cost[res])
        actual = min(amount, max(0, needed))
        self.reserved_cost[res] += actual
        return actual

    def deposit_resource(self, res, amount):
        self.reserved_cost[res] = max(0, self.reserved_cost[res] - amount)
        self.delivered_cost[res] += amount

    def get_center_world(self, tile_size):
        if not self.tiles:
            return 0, 0
        avg_x = sum(x for x, y in self.tiles) / len(self.tiles) + 0.5
        avg_y = sum(y for x, y in self.tiles) / len(self.tiles) + 0.5
        return avg_x * tile_size, avg_y * tile_size

    def get_door_world_inside(self, tile_size=TILE_SIZE):
        """World coordinates comfortably inside the door tile"""
        if not self.door_pos:
            return self.get_center_world(tile_size)
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        offset = tile_size * 0.70
        if self.door_side == "bottom":
            return cx, cy - offset
        elif self.door_side == "top":
            return cx, cy + offset
        elif self.door_side == "left":
            return cx + offset, cy
        elif self.door_side == "right":
            return cx - offset, cy
        return cx, cy

    def get_door_world_outside(self, tile_size=TILE_SIZE):
        """World coordinates just outside the doorway threshold or outside perimeter for doorless structures"""
        if not self.door_pos:
            return (self.grid_x + self.tiles_w + 0.2) * tile_size, (self.grid_y + 0.5) * tile_size
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        offset = tile_size * 0.75
        if self.door_side == "bottom":
            return cx, cy + offset
        elif self.door_side == "top":
            return cx, cy - offset
        elif self.door_side == "left":
            return cx - offset, cy
        elif self.door_side == "right":
            return cx + offset, cy
        return cx, cy + offset

    def get_door_world_threshold(self, tile_size=TILE_SIZE):
        """World coordinates exactly at the door threshold center"""
        if not self.door_pos:
            return self.get_center_world(tile_size)
        dx, dy = self.door_pos
        return (dx + 0.5) * tile_size, (dy + 0.5) * tile_size

    def is_in_door_threshold(self, x, y, tile_size=TILE_SIZE):
        """Mengecek apakah posisi (x, y) tepat berada di dalam celah kusen dinding pintu atau petak pintu"""
        if not self.door_pos or not self.door_side:
            return False
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        return abs(x - cx) < 32.0 and abs(y - cy) < 32.0

    def get_approach_point(self, worker_x, worker_y, worker_id=None, all_entities=None, tile_size=TILE_SIZE, bm=None):
        """
        Mendapatkan titik pendekatan (approach point) di sekeliling perimeter site/bangunan.
        Mendukung multi-worker parallel: mendistribusikan pekerja ke petak perimeter yang berbeda
        agar tidak bertumpuk atau berebut satu koordinat.
        """
        if not self.tiles:
            return worker_x, worker_y

        if self.door_pos:
            return self.get_door_world_outside(tile_size)

        perimeter_tiles = []
        for (gx, gy) in self.tiles:
            for (ndx, ndy) in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                adj = (gx + ndx, gy + ndy)
                if adj not in self.tiles and adj not in perimeter_tiles:
                    if bm:
                        b_other = bm.get_building_at(adj[0], adj[1])
                        if b_other and b_other != self and (getattr(b_other, "is_solid", False) or not getattr(b_other, "door_pos", None)):
                            continue
                    perimeter_tiles.append(adj)

        if not perimeter_tiles:
            cx, cy = self.get_center_world(tile_size)
            return cx, cy

        occupied = set()
        if all_entities:
            for other in all_entities:
                if worker_id is not None and str(getattr(other, "id", "")) == str(worker_id):
                    continue
                ogx = int(math.floor(other.x / tile_size))
                ogy = int(math.floor(other.y / tile_size))
                occupied.add((ogx, ogy))
                otgt = getattr(other, "path_target_tile", None)
                if otgt:
                    occupied.add(otgt)

        free_tiles = [t for t in perimeter_tiles if t not in occupied]
        candidates = free_tiles if free_tiles else perimeter_tiles
        candidates.sort(key=lambda t: math.hypot((t[0] + 0.5) * tile_size - worker_x, (t[1] + 0.5) * tile_size - worker_y))
        best_t = candidates[0]
        return (best_t[0] + 0.5) * tile_size, (best_t[1] + 0.5) * tile_size

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        # 1. Blueprint Grid & Foundation per tile
        for (gx, gy) in self.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            tile_surf = pygame.Surface((scaled_tile + 1, scaled_tile + 1), pygame.SRCALPHA)
            tile_surf.fill((30, 58, 138, 90))
            surface.blit(tile_surf, (sx, sy))

            # Blueprint grid borders
            pygame.draw.rect(surface, (59, 130, 246, 120), (sx, sy, scaled_tile + 1, scaled_tile + 1), width=1)

            # Exterior perimeter lines
            if (gx, gy - 1) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy), (sx + scaled_tile, sy), 2)
            if (gx, gy + 1) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)
            if (gx - 1, gy) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy), (sx, sy + scaled_tile), 2)
            if (gx + 1, gy) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

        # 2. Door Marker
        if self.door_pos:
            dx, dy = self.door_pos
            dsx, dsy = camera.world_to_screen(dx * tile_size, dy * tile_size)
            door_rect = pygame.Rect(dsx + 4, dsy + 4, scaled_tile - 8, scaled_tile - 8)
            pygame.draw.rect(surface, (234, 179, 8, 180), door_rect, border_radius=4)
            d_txt = self.font.render("DOOR", True, (0, 0, 0))
            surface.blit(d_txt, (door_rect.centerx - d_txt.get_width() // 2, door_rect.centery - d_txt.get_height() // 2))

        # 3. Progress Bar (Above center tile)
        cx, cy = self.get_center_world(tile_size)
        scx, scy = camera.world_to_screen(cx, self.grid_y * tile_size)

        bar_w = max(80, min(240, int(len(self.tiles) * 12 * camera.zoom)))
        bar_h = 10
        bar_x = scx - bar_w // 2
        bar_y = scy - 26

        pygame.draw.rect(surface, (15, 23, 42, 220), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), border_radius=4)
        pygame.draw.rect(surface, (71, 85, 105), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), width=1, border_radius=4)

        if not self.is_materials_complete():
            pct = self.total_delivered() / max(1, self.total_required())
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                pygame.draw.rect(surface, (234, 179, 8), (bar_x, bar_y, fill_w, bar_h), border_radius=3)
            lbl_txt = f"{self.name}: {self.total_delivered()}/{self.total_required()}"
        else:
            pct = min(1.0, self.build_progress / BUILD_DURATION_SECONDS)
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                pygame.draw.rect(surface, (34, 197, 94), (bar_x, bar_y, fill_w, bar_h), border_radius=3)
            lbl_txt = f"Building: {int(pct * 100)}%"

        txt_surf = self.font.render(lbl_txt, True, (255, 255, 255))
        surface.blit(txt_surf, (bar_x + (bar_w - txt_surf.get_width()) // 2, bar_y - 14))


class Building:
    def __init__(self, building_type, tiles, door_pos=None, door_side="bottom"):
        self.building_type = building_type
        self.type_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])
        self.tiles = set(tiles)
        self._recalculate_bounds()
        self.name = f"{self.type_cfg['name']} ({len(self.tiles)} tiles)"
        if self.type_cfg.get("has_door", True) is False or self.building_type == "well":
            self.door_pos = None
            self.door_side = None
            self.is_solid = True
        else:
            self.door_pos, self.door_side = self._resolve_door(door_pos, door_side)
            self.is_solid = False
        self.wall_thickness = 10
        self._cached_oriented_walls = None
        self._cached_wall_rects = None
        self._cached_tile_size = None

        # Doorway Bottleneck Access & Smart Queuing
        self.door_active_user = None
        self.door_transit_start = 0.0
        self.door_outside_queue = []
        self.door_inside_queue = []

    def request_door_passage(self, entity_id, is_outside, tile_size=TILE_SIZE):
        """
        Meminta izin melintasi celah pintu (Doorway Bottleneck Access).
        Jika pintu kosong dan entitas di urutan pertama antrean: izin diberikan (True, None).
        Jika pintu sedang digunakan atau ada antrean di depan: masuk antrean (False, queue_target_pos).
        """
        if not self.door_pos:
            return True, None

        eid_str = str(entity_id)
        now = time.time()

        # Timeout guard: jika entitas sebelumnya stuck > 3.0 detik, lepas paksa
        if self.door_active_user and (now - self.door_transit_start > 3.0):
            self.door_active_user = None

        q = self.door_outside_queue if is_outside else self.door_inside_queue

        # Jika entitas ini sudah memegang izin transit pintu
        if self.door_active_user == eid_str:
            return True, None

        # Jika pintu bebas dan tidak ada antrean yang mendahului
        if self.door_active_user is None:
            if not q or q[0] == eid_str:
                self.door_active_user = eid_str
                self.door_transit_start = now
                if q and q[0] == eid_str:
                    q.pop(0)
                return True, None

        # Pintu sedang dipakai atau ada antrean lain di depan -> Daftarkan ke antrean
        if eid_str not in q:
            q.append(eid_str)
        q_idx = q.index(eid_str)

        q_pos = self.get_door_queue_pos(q_idx, is_outside, tile_size=tile_size)
        return False, q_pos

    def release_door_passage(self, entity_id):
        """Melepaskan izin celah pintu dan menghapus dari antrean pintu"""
        eid_str = str(entity_id)
        if self.door_active_user == eid_str:
            self.door_active_user = None
            self.door_transit_start = 0.0
        if eid_str in self.door_outside_queue:
            self.door_outside_queue.remove(eid_str)
        if eid_str in self.door_inside_queue:
            self.door_inside_queue.remove(eid_str)

    def get_door_queue_pos(self, queue_idx, is_outside, tile_size=TILE_SIZE):
        """
        Menghitung koordinat posisi antrean di dekat pintu (staggered fan-out agar tidak bertumpuk).
        Berada di ruang terbuka dekat pintu, memungkinkan AI mendekati pintu dan mengantre rapi.
        """
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size

        dist_offset = tile_size * (1.1 + queue_idx * 0.55)
        stagger = 18.0 if (queue_idx % 2 == 1) else -18.0

        side = self.door_side
        if side == "top":
            sign = -1.0 if is_outside else 1.0
            return (cx + stagger, cy + sign * dist_offset)
        elif side == "bottom":
            sign = 1.0 if is_outside else -1.0
            return (cx + stagger, cy + sign * dist_offset)
        elif side == "left":
            sign = -1.0 if is_outside else 1.0
            return (cx + sign * dist_offset, cy + stagger)
        elif side == "right":
            sign = 1.0 if is_outside else -1.0
            return (cx + sign * dist_offset, cy + stagger)

        return (cx, cy)

    def update_door_queue(self, dt):
        """Pembersihan timeout otomatis antrean pintu"""
        if self.door_active_user and (time.time() - self.door_transit_start > 3.0):
            self.door_active_user = None

    def _resolve_door(self, door_pos, door_side):
        if door_pos and door_pos in self.tiles:
            edges = get_exterior_edges_for_tile(door_pos, self.tiles)
            if edges:
                side = door_side if door_side in edges else edges[0]
                return door_pos, side

        # Default fallback door: Southernmost tile with a bottom edge
        sorted_tiles = sorted(self.tiles, key=lambda t: (-t[1], t[0]))
        for t in sorted_tiles:
            edges = get_exterior_edges_for_tile(t, self.tiles)
            if "bottom" in edges:
                return t, "bottom"
            if edges:
                return t, edges[0]

        first_tile = next(iter(self.tiles)) if self.tiles else (0, 0)
        return first_tile, "bottom"

    def _recalculate_bounds(self):
        if self.tiles:
            self.grid_x = min(x for x, y in self.tiles)
            self.grid_y = min(y for x, y in self.tiles)
            self.tiles_w = max(x for x, y in self.tiles) - self.grid_x + 1
            self.tiles_h = max(y for x, y in self.tiles) - self.grid_y + 1
        else:
            self.grid_x, self.grid_y, self.tiles_w, self.tiles_h = 0, 0, 0, 0

    @property
    def rotation(self):
        side_map = {"bottom": 0, "left": 1, "top": 2, "right": 3}
        return side_map.get(getattr(self, "door_side", "bottom"), 0)

    def occupies_tile(self, tx, ty):
        return (tx, ty) in self.tiles

    def get_center_world(self, tile_size):
        if not self.tiles:
            return 0, 0
        avg_x = sum(x for x, y in self.tiles) / len(self.tiles) + 0.5
        avg_y = sum(y for x, y in self.tiles) / len(self.tiles) + 0.5
        return avg_x * tile_size, avg_y * tile_size

    def get_door_world_inside(self, tile_size=TILE_SIZE):
        """World coordinates comfortably inside the door tile"""
        if not self.door_pos:
            return self.get_center_world(tile_size)
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        offset = tile_size * 0.70
        if self.door_side == "bottom":
            return cx, cy - offset
        elif self.door_side == "top":
            return cx, cy + offset
        elif self.door_side == "left":
            return cx + offset, cy
        elif self.door_side == "right":
            return cx - offset, cy
        return cx, cy

    def get_door_world_outside(self, tile_size=TILE_SIZE):
        """World coordinates just outside the doorway threshold or outside perimeter for doorless structures"""
        if not self.door_pos:
            return (self.grid_x + self.tiles_w + 0.2) * tile_size, (self.grid_y + 0.5) * tile_size
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        offset = tile_size * 0.75
        if self.door_side == "bottom":
            return cx, cy + offset
        elif self.door_side == "top":
            return cx, cy - offset
        elif self.door_side == "left":
            return cx - offset, cy
        elif self.door_side == "right":
            return cx + offset, cy
        return cx, cy + offset

    def get_door_world_threshold(self, tile_size=TILE_SIZE):
        """World coordinates exactly at the door threshold center"""
        if not self.door_pos:
            return self.get_center_world(tile_size)
        dx, dy = self.door_pos
        return (dx + 0.5) * tile_size, (dy + 0.5) * tile_size

    def is_in_door_threshold(self, x, y, tile_size=TILE_SIZE):
        """Mengecek apakah posisi (x, y) tepat berada di dalam celah kusen dinding pintu atau petak pintu"""
        if not self.door_pos or not self.door_side:
            return False
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        return abs(x - cx) < 32.0 and abs(y - cy) < 32.0

    def get_approach_point(self, worker_x, worker_y, worker_id=None, all_entities=None, tile_size=TILE_SIZE, bm=None):
        """
        Mendapatkan titik pendekatan (approach point) di sekeliling perimeter site/bangunan.
        Mendukung multi-worker parallel: mendistribusikan pekerja ke petak perimeter yang berbeda
        agar tidak bertumpuk atau berebut satu koordinat.
        """
        if not self.tiles:
            return worker_x, worker_y

        if self.door_pos:
            return self.get_door_world_outside(tile_size)

        perimeter_tiles = []
        for (gx, gy) in self.tiles:
            for (ndx, ndy) in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                adj = (gx + ndx, gy + ndy)
                if adj not in self.tiles and adj not in perimeter_tiles:
                    if bm:
                        b_other = bm.get_building_at(adj[0], adj[1])
                        if b_other and b_other != self and (getattr(b_other, "is_solid", False) or not getattr(b_other, "door_pos", None)):
                            continue
                    perimeter_tiles.append(adj)

        if not perimeter_tiles:
            cx, cy = self.get_center_world(tile_size)
            return cx, cy

        occupied = set()
        if all_entities:
            for other in all_entities:
                if worker_id is not None and str(getattr(other, "id", "")) == str(worker_id):
                    continue
                ogx = int(math.floor(other.x / tile_size))
                ogy = int(math.floor(other.y / tile_size))
                occupied.add((ogx, ogy))
                otgt = getattr(other, "path_target_tile", None)
                if otgt:
                    occupied.add(otgt)

        free_tiles = [t for t in perimeter_tiles if t not in occupied]
        candidates = free_tiles if free_tiles else perimeter_tiles
        candidates.sort(key=lambda t: math.hypot((t[0] + 0.5) * tile_size - worker_x, (t[1] + 0.5) * tile_size - worker_y))
        best_t = candidates[0]
        return (best_t[0] + 0.5) * tile_size, (best_t[1] + 0.5) * tile_size

    def overlaps_tiles(self, tiles):
        return bool(self.tiles & tiles)

    def get_oriented_walls(self, tile_size):
        """Menghitung rect dinding beserta orientasi sisinya ('top', 'bottom', 'left', 'right', 'door_post', 'solid')"""
        if self._cached_oriented_walls is not None and self._cached_tile_size == tile_size:
            return self._cached_oriented_walls

        if getattr(self, "is_solid", False) or self.building_type == "well" or not self.type_cfg.get("has_door", True):
            walls = [(pygame.Rect(x * tile_size, y * tile_size, tile_size, tile_size), "solid") for x, y in self.tiles]
            self._cached_oriented_walls = walls
            self._cached_tile_size = tile_size
            self._cached_wall_rects = [w[0] for w in walls]
            return walls

        walls = []
        thick = self.wall_thickness
        seg_post = 2  # Celah pintu lapang (clearance luas), tiang tipis di sudut

        for (x, y) in self.tiles:
            wx = x * tile_size
            wy = y * tile_size

            # Sisi Atas
            if (x, y - 1) not in self.tiles:
                if (x, y) == self.door_pos and self.door_side == "top":
                    walls.append((pygame.Rect(wx, wy, seg_post, thick), "door_post"))
                    walls.append((pygame.Rect(wx + tile_size - seg_post, wy, seg_post, thick), "door_post"))
                else:
                    walls.append((pygame.Rect(wx, wy, tile_size, thick), "top"))

            # Sisi Bawah
            if (x, y + 1) not in self.tiles:
                if (x, y) == self.door_pos and self.door_side == "bottom":
                    walls.append((pygame.Rect(wx, wy + tile_size - thick, seg_post, thick), "door_post"))
                    walls.append((pygame.Rect(wx + tile_size - seg_post, wy + tile_size - thick, seg_post, thick), "door_post"))
                else:
                    walls.append((pygame.Rect(wx, wy + tile_size - thick, tile_size, thick), "bottom"))

            # Sisi Kiri
            if (x - 1, y) not in self.tiles:
                if (x, y) == self.door_pos and self.door_side == "left":
                    walls.append((pygame.Rect(wx, wy, thick, seg_post), "door_post"))
                    walls.append((pygame.Rect(wx, wy + tile_size - seg_post, thick, seg_post), "door_post"))
                else:
                    walls.append((pygame.Rect(wx, wy, thick, tile_size), "left"))

            # Sisi Kanan
            if (x + 1, y) not in self.tiles:
                if (x, y) == self.door_pos and self.door_side == "right":
                    walls.append((pygame.Rect(wx + tile_size - thick, wy, thick, seg_post), "door_post"))
                    walls.append((pygame.Rect(wx + tile_size - thick, wy + tile_size - seg_post, thick, seg_post), "door_post"))
                else:
                    walls.append((pygame.Rect(wx + tile_size - thick, wy, thick, tile_size), "right"))

        self._cached_oriented_walls = walls
        self._cached_tile_size = tile_size
        self._cached_wall_rects = [w[0] for w in walls]
        return walls

    def get_wall_rects(self, tile_size):
        """Menghitung rect dinding luar untuk sistem tabrakan (dengan celah pintu yang lapang)"""
        if self._cached_wall_rects is not None and self._cached_tile_size == tile_size:
            return self._cached_wall_rects
        self.get_oriented_walls(tile_size)
        return self._cached_wall_rects


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

    def get_center_world(self, tile_size):
        return self.building.get_center_world(tile_size)

    def overlaps_tiles(self, tiles):
        return bool(self.tiles & tiles)

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        # Overlay merah pada bangunan yang sedang dihancurkan
        for (gx, gy) in self.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            tile_surf = pygame.Surface((scaled_tile + 1, scaled_tile + 1), pygame.SRCALPHA)
            tile_surf.fill((220, 38, 38, 90))
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


class BuildingManager:
    def __init__(self):
        self.buildings = []
        self.construction_sites = []
        self.demolition_sites = []
        self.font = None
        self._pathfinder = None
        self._tile_to_building = {}

    def rebuild_tile_cache(self):
        """Membangun pemetaan spasial O(1) dari petak (gx, gy) ke objek Building"""
        tb = {}
        for b in self.buildings:
            for t in b.tiles:
                tb[t] = b
        for d in getattr(self, "demolition_sites", []):
            b_dem = getattr(d, "building", None)
            if b_dem:
                for t in b_dem.tiles:
                    tb[t] = b_dem
        self._tile_to_building = tb

    @property
    def pathfinder(self):
        if self._pathfinder is None:
            from game.world.pathfinding import Pathfinder
            self._pathfinder = Pathfinder(self)
        return self._pathfinder

    def find_path(self, start_pos, target_pos, tile_size=TILE_SIZE, furniture_manager=None, avoid_tiles=None):
        """Mencari rute navigasi A* bebas dinding & rintangan"""
        return self.pathfinder.find_path(start_pos, target_pos, self, tile_size, furniture_manager=furniture_manager, avoid_tiles=avoid_tiles)

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def can_afford(self, building_type, resources, tile_count):
        b_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])
        if b_cfg.get("fixed_cost", False):
            cost_w = b_cfg.get("cost_wood", 5)
            cost_s = b_cfg.get("cost_stone", 20)
        else:
            cost_w = tile_count * b_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
            cost_s = tile_count * b_cfg.get("cost_stone", COST_PER_BLOCK_STONE)
        return resources.get("Wood", 0) >= cost_w and resources.get("Stone", 0) >= cost_s

    def start_construction(self, building_type, tiles_or_gx, gy_or_door=None, tw_or_side=None, th=None, permit_manager=None, rotation=0):
        """Mendukung inisialisasi via kumpulan tile atau koordinat rect untuk backward compatibility"""
        if isinstance(tiles_or_gx, (set, list, tuple)):
            tiles = set(tiles_or_gx)
            door_pos = gy_or_door
            door_side = tw_or_side
            pm = th if th is not None else permit_manager
        else:
            gx = tiles_or_gx
            gy = gy_or_door
            tw = tw_or_side
            tiles = {(gx + c, gy + r) for c in range(tw) for r in range(th)}
            door_pos = (gx + tw // 2, gy + th - 1)
            door_side = "bottom"
            pm = permit_manager

        type_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])

        # Validasi izin tanah (harus berada di dalam batas permit yang sesuai dan terhubung)
        matching_permit, _ = pm.find_matching_permit_for_tiles(building_type, tiles, self)
        if not matching_permit:
            return False

        # Cek tumpang tindih dengan bangunan yang sudah jadi
        for b in self.buildings:
            if b.overlaps_tiles(tiles):
                return False

        # Cek tumpang tindih dengan site lain
        for site in self.construction_sites:
            if site.overlaps_tiles(tiles):
                return False

        site = ConstructionSite(building_type, tiles, door_pos, door_side)
        self.construction_sites.append(site)
        return True

    def update(self, dt):
        completed = []
        for site in self.construction_sites:
            if site.is_complete():
                b = Building(
                    site.building_type, site.tiles,
                    door_pos=site.door_pos, door_side=site.door_side
                )
                self.buildings.append(b)
                completed.append(site)

        if completed:
            for site in completed:
                self.construction_sites.remove(site)
            self.rebuild_tile_cache()

        for b in self.buildings:
            b.update_door_queue(dt)

    def get_pending_site(self):
        for site in self.construction_sites:
            if not site.is_complete():
                return site
        return None

    def get_completed_wells(self):
        """Mendapatkan daftar seluruh bangunan sumur yang sudah selesai dibangun"""
        return [b for b in self.buildings if b.building_type == "well"]

    def get_all_wall_rects(self, tile_size):
        all_walls = []
        for b in self.buildings:
            all_walls.extend(b.get_wall_rects(tile_size))
        for d in getattr(self, "demolition_sites", []):
            if hasattr(d, "building"):
                all_walls.extend(d.building.get_wall_rects(tile_size))
        return all_walls

    def resolve_collision(self, px, py, radius, tile_size, old_x=None, old_y=None):
        new_x = px
        new_y = py

        if self._tile_to_building is None or (not self._tile_to_building and self.buildings):
            self.rebuild_tile_cache()

        cur_gx = int(math.floor(new_x / tile_size))
        cur_gy = int(math.floor(new_y / tile_size))

        nearby_buildings = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                b = self._tile_to_building.get((cur_gx + dx, cur_gy + dy))
                if b is not None:
                    nearby_buildings.add(b)

        if old_x is not None and old_y is not None:
            old_gx = int(math.floor(old_x / tile_size))
            old_gy = int(math.floor(old_y / tile_size))
            if (old_gx, old_gy) != (cur_gx, cur_gy):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        b = self._tile_to_building.get((old_gx + dx, old_gy + dy))
                        if b is not None:
                            nearby_buildings.add(b)

        if not nearby_buildings:
            return new_x, new_y

        for b in nearby_buildings:
            is_solid_structure = getattr(b, "is_solid", False) or b.building_type == "well" or not getattr(b, "door_pos", None)

            if is_solid_structure:
                for wr in b.get_wall_rects(tile_size):
                    closest_x = max(wr.left, min(new_x, wr.right))
                    closest_y = max(wr.top, min(new_y, wr.bottom))

                    dist_x = new_x - closest_x
                    dist_y = new_y - closest_y
                    dist_sq = dist_x * dist_x + dist_y * dist_y

                    if dist_sq < radius * radius:
                        dist = math.sqrt(dist_sq)
                        if dist == 0:
                            d_left = new_x - wr.left
                            d_right = wr.right - new_x
                            d_top = new_y - wr.top
                            d_bottom = wr.bottom - new_y
                            min_d = min(d_left, d_right, d_top, d_bottom)
                            if min_d == d_left:
                                new_x = wr.left - radius
                            elif min_d == d_right:
                                new_x = wr.right + radius
                            elif min_d == d_top:
                                new_y = wr.top - radius
                            else:
                                new_y = wr.bottom + radius
                        else:
                            overlap = radius - dist
                            new_x += (dist_x / dist) * overlap
                            new_y += (dist_y / dist) * overlap
                continue

            ref_x = old_x if old_x is not None else px
            ref_y = old_y if old_y is not None else py
            in_door = b.is_in_door_threshold(ref_x, ref_y, tile_size) or b.is_in_door_threshold(new_x, new_y, tile_size)
            was_inside = b.occupies_tile(int(math.floor(ref_x / tile_size)), int(math.floor(ref_y / tile_size)))

            for wr, side in b.get_oriented_walls(tile_size):
                if side == "door_post":
                    closest_x = max(wr.left, min(new_x, wr.right))
                    closest_y = max(wr.top, min(new_y, wr.bottom))
                    dist_x = new_x - closest_x
                    dist_y = new_y - closest_y
                    dist_sq = dist_x * dist_x + dist_y * dist_y
                    if 0 < dist_sq < radius * radius:
                        dist = math.sqrt(dist_sq)
                        overlap = radius - dist
                        new_x += (dist_x / dist) * overlap
                        new_y += (dist_y / dist) * overlap
                    continue

                if in_door:
                    continue

                if side == "top":
                    if wr.left - radius < new_x < wr.right + radius:
                        if was_inside:
                            if new_y < wr.bottom + radius:
                                new_y = wr.bottom + radius
                        else:
                            if new_y > wr.top - radius and new_y < wr.bottom:
                                new_y = wr.top - radius
                elif side == "bottom":
                    if wr.left - radius < new_x < wr.right + radius:
                        if was_inside:
                            if new_y > wr.top - radius:
                                new_y = wr.top - radius
                        else:
                            if new_y < wr.bottom + radius and new_y > wr.top:
                                new_y = wr.bottom + radius
                elif side == "left":
                    if wr.top - radius < new_y < wr.bottom + radius:
                        if was_inside:
                            if new_x < wr.right + radius:
                                new_x = wr.right + radius
                        else:
                            if new_x > wr.left - radius and new_x < wr.right:
                                new_x = wr.left - radius
                elif side == "right":
                    if wr.top - radius < new_y < wr.bottom + radius:
                        if was_inside:
                            if new_x > wr.left - radius:
                                new_x = wr.left - radius
                        else:
                            if new_x < wr.right + radius and new_x > wr.left:
                                new_x = wr.right + radius

        return new_x, new_y

    def get_building_at(self, gx, gy):
        """Mencari bangunan yang berada di koordinat tile (gx, gy) secara O(1)"""
        if self._tile_to_building is None or (not self._tile_to_building and self.buildings):
            self.rebuild_tile_cache()
        return self._tile_to_building.get((gx, gy))

    def get_door_waypoints(self, start_x, start_y, target_x, target_y, tile_size=TILE_SIZE):
        """
        Menghasilkan rangkaian waypoint koridor pintu (outside, inside) 
        jika rute memerlukan transisi masuk atau keluar bangunan.
        """
        cur_gx = int(math.floor(start_x / tile_size))
        cur_gy = int(math.floor(start_y / tile_size))
        tar_gx = int(math.floor(target_x / tile_size))
        tar_gy = int(math.floor(target_y / tile_size))

        b_cur = self.get_building_at(cur_gx, cur_gy)
        b_tar = self.get_building_at(tar_gx, tar_gy)

        if b_cur == b_tar:
            return []

        waypoints = []

        # 1. Jika sedang di dalam bangunan dan perlu keluar
        if b_cur and b_cur.door_pos:
            d_in = b_cur.get_door_world_inside(tile_size)
            d_out = b_cur.get_door_world_outside(tile_size)
            dist_in = math.hypot(d_in[0] - start_x, d_in[1] - start_y)
            dist_out = math.hypot(d_out[0] - start_x, d_out[1] - start_y)
            if dist_in > 16.0 and dist_in <= dist_out:
                waypoints.append(d_in)
            waypoints.append(d_out)

        # 2. Jika tujuan berada di dalam bangunan dan perlu masuk
        if b_tar and b_tar.door_pos:
            d_out = b_tar.get_door_world_outside(tile_size)
            d_in = b_tar.get_door_world_inside(tile_size)
            dist_out = math.hypot(d_out[0] - start_x, d_out[1] - start_y)
            dist_in = math.hypot(d_in[0] - start_x, d_in[1] - start_y)
            if dist_out > 16.0 and dist_out <= dist_in:
                waypoints.append(d_out)
            waypoints.append(d_in)

        return waypoints

    def is_door_occupied(self, door_pos, all_entities, exclude_entity=None, radius=32.0, tile_size=TILE_SIZE):
        """Mengecek apakah ada entitas lain yang sedang berada di area celah pintu"""
        if not door_pos or not all_entities:
            return False

        b = self.get_building_at(door_pos[0], door_pos[1]) if isinstance(door_pos, (tuple, list)) else None
        if b:
            for e in all_entities:
                if e == exclude_entity:
                    continue
                if b.is_in_door_threshold(e.x, e.y, tile_size):
                    return True
            return False

        cx = (door_pos[0] + 0.5) * tile_size
        cy = (door_pos[1] + 0.5) * tile_size
        for e in all_entities:
            if e == exclude_entity:
                continue
            dist = math.hypot(e.x - cx, e.y - cy)
            if dist < radius:
                return True
        return False

    def is_near_any_door(self, x, y, min_dist=48.0, tile_size=TILE_SIZE):
        """Mengecek apakah posisi (x, y) terlalu dekat dengan celah pintu bangunan mana pun"""
        for b in self.buildings:
            if b.door_pos:
                cx = (b.door_pos[0] + 0.5) * tile_size
                cy = (b.door_pos[1] + 0.5) * tile_size
                if math.hypot(x - cx, y - cy) < min_dist:
                    return True
        return False

    def start_demolition(self, building):
        """Menandai bangunan untuk dihancurkan oleh servant"""
        if building in self.buildings:
            self.buildings.remove(building)
            site = DemolitionSite(building)
            self.demolition_sites.append(site)
            self.rebuild_tile_cache()
            return site
        return None

    def get_pending_demolition(self):
        """Mendapatkan tugas pembongkaran yang belum selesai"""
        for site in self.demolition_sites:
            if not site.is_complete():
                return site
        return None

    def complete_demolition(self, site, resources, stockpile_manager=None):
        """Menyelesaikan pembongkaran dan menjatuhkan 50% resource secara fisik di tanah"""
        if stockpile_manager and site.tiles:
            sorted_tiles = sorted(site.tiles, key=lambda t: (t[1], t[0]))
            tile_w = sorted_tiles[0]
            tile_s = sorted_tiles[1] if len(sorted_tiles) > 1 else sorted_tiles[0]
            stockpile_manager.drop_resource("Wood", site.refund_wood, tile_w[0], tile_w[1])
            stockpile_manager.drop_resource("Stone", site.refund_stone, tile_s[0], tile_s[1])
            stockpile_manager.refresh_stacks(resources, None)
        else:
            resources["Wood"] += site.refund_wood
            resources["Stone"] += site.refund_stone
        if site in self.demolition_sites:
            self.demolition_sites.remove(site)
            self.rebuild_tile_cache()

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        for site in self.construction_sites:
            site.draw(surface, camera, tile_size)

        for site in self.demolition_sites:
            site.draw(surface, camera, tile_size)

        for b in self.buildings:
            self._draw_building(surface, camera, tile_size, b)

    def _draw_building(self, surface, camera, tile_size, b):
        if b.building_type == "well":
            self._draw_well(surface, camera, tile_size, b)
            return

        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))
        wall_thick = max(2, int(8 * camera.zoom))
        door_w = min(scaled_tile - 6, max(14, int(scaled_tile * 0.7)))

        # 1. Lantai Interior bergaya RimWorld (Kayu vs Batu)
        is_stone = (b.building_type in ("stone_structure", "manor"))
        floor_a = COLOR_STONE_FLOOR if is_stone else COLOR_BUILDING_FLOOR
        floor_b = COLOR_STONE_FLOOR_ALT if is_stone else COLOR_BUILDING_FLOOR_ALT
        wall_col = COLOR_STONE_WALL if is_stone else COLOR_BUILDING_WALL
        wall_out = COLOR_STONE_WALL_OUTLINE if is_stone else COLOR_BUILDING_WALL_OUTLINE
        door_col = COLOR_STONE_DOOR if is_stone else COLOR_BUILDING_DOOR

        for (gx, gy) in b.tiles:
            wx = gx * tile_size
            wy = gy * tile_size
            sx, sy = camera.world_to_screen(wx, wy)

            floor_color = floor_a if (gx + gy) % 2 == 0 else floor_b
            rect = pygame.Rect(sx, sy, scaled_tile + 1, scaled_tile + 1)
            pygame.draw.rect(surface, floor_color, rect)

        # 2. Dinding Luar dan Celah Pintu untuk setiap tile
        for (gx, gy) in b.tiles:
            wx = gx * tile_size
            wy = gy * tile_size
            sx, sy = camera.world_to_screen(wx, wy)

            is_door_tile = ((gx, gy) == b.door_pos)

            # Top Wall
            if (gx, gy - 1) not in b.tiles:
                if is_door_tile and b.door_side == "top":
                    seg_w = max(2, (scaled_tile - door_w) // 2)
                    pygame.draw.rect(surface, wall_col, (sx, sy, seg_w, wall_thick))
                    pygame.draw.rect(surface, wall_col, (sx + scaled_tile - seg_w, sy, seg_w, wall_thick))
                    pygame.draw.rect(surface, door_col, (sx + seg_w, sy, door_w, wall_thick // 2))
                else:
                    pygame.draw.rect(surface, wall_col, (sx, sy, scaled_tile, wall_thick))
                pygame.draw.line(surface, wall_out, (sx, sy), (sx + scaled_tile, sy), 2)

            # Bottom Wall
            if (gx, gy + 1) not in b.tiles:
                bottom_y = sy + scaled_tile - wall_thick
                if is_door_tile and b.door_side == "bottom":
                    seg_w = max(2, (scaled_tile - door_w) // 2)
                    pygame.draw.rect(surface, wall_col, (sx, bottom_y, seg_w, wall_thick))
                    pygame.draw.rect(surface, wall_col, (sx + scaled_tile - seg_w, bottom_y, seg_w, wall_thick))
                    pygame.draw.rect(surface, door_col, (sx + seg_w, bottom_y + wall_thick // 2, door_w, wall_thick // 2))
                else:
                    pygame.draw.rect(surface, wall_col, (sx, bottom_y, scaled_tile, wall_thick))
                pygame.draw.line(surface, wall_out, (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)

            # Left Wall
            if (gx - 1, gy) not in b.tiles:
                if is_door_tile and b.door_side == "left":
                    seg_h = max(2, (scaled_tile - door_w) // 2)
                    pygame.draw.rect(surface, wall_col, (sx, sy, wall_thick, seg_h))
                    pygame.draw.rect(surface, wall_col, (sx, sy + scaled_tile - seg_h, wall_thick, seg_h))
                    pygame.draw.rect(surface, door_col, (sx, sy + seg_h, wall_thick // 2, door_w))
                else:
                    pygame.draw.rect(surface, wall_col, (sx, sy, wall_thick, scaled_tile))
                pygame.draw.line(surface, wall_out, (sx, sy), (sx, sy + scaled_tile), 2)

            # Right Wall
            if (gx + 1, gy) not in b.tiles:
                right_x = sx + scaled_tile - wall_thick
                if is_door_tile and b.door_side == "right":
                    seg_h = max(2, (scaled_tile - door_w) // 2)
                    pygame.draw.rect(surface, wall_col, (right_x, sy, wall_thick, seg_h))
                    pygame.draw.rect(surface, wall_col, (right_x, sy + scaled_tile - seg_h, wall_thick, seg_h))
                    pygame.draw.rect(surface, door_col, (right_x + wall_thick // 2, sy + seg_h, wall_thick // 2, door_w))
                else:
                    pygame.draw.rect(surface, wall_col, (right_x, sy, wall_thick, scaled_tile))
                pygame.draw.line(surface, wall_out, (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

        # 3. Building Label
        if b.tiles:
            min_tile = min(b.tiles, key=lambda t: (t[1], t[0]))
            bx, by = camera.world_to_screen(min_tile[0] * tile_size, min_tile[1] * tile_size)
            lbl = self.font.render(f"{b.name}", True, (241, 245, 249))
            surface.blit(lbl, (bx + 8, by + 8))

    def _draw_well(self, surface, camera, tile_size, b):
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        # 1. Cobblestone Floor Foundation for all tiles
        for (gx, gy) in b.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            pygame.draw.rect(surface, (140, 145, 155), (sx, sy, scaled_tile + 1, scaled_tile + 1))
            pygame.draw.rect(surface, (100, 105, 115), (sx, sy, scaled_tile + 1, scaled_tile + 1), width=1)

        # 2. Outer Perimeter Border of the Well Foundation
        for (gx, gy) in b.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            if (gx, gy - 1) not in b.tiles:
                pygame.draw.line(surface, COLOR_STONE_WALL_OUTLINE, (sx, sy), (sx + scaled_tile, sy), 2)
            if (gx, gy + 1) not in b.tiles:
                pygame.draw.line(surface, COLOR_STONE_WALL_OUTLINE, (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)
            if (gx - 1, gy) not in b.tiles:
                pygame.draw.line(surface, COLOR_STONE_WALL_OUTLINE, (sx, sy), (sx, sy + scaled_tile), 2)
            if (gx + 1, gy) not in b.tiles:
                pygame.draw.line(surface, COLOR_STONE_WALL_OUTLINE, (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

        # 3. Center Well Curb & Water Pool
        cx_world, cy_world = b.get_center_world(tile_size)
        cx, cy = camera.world_to_screen(cx_world, cy_world)

        min_gx = min(x for x, y in b.tiles)
        max_gx = max(x for x, y in b.tiles)
        span_w = (max_gx - min_gx + 1) * scaled_tile
        well_rad = max(10, int(span_w * 0.38))

        # Drop shadow
        shadow_rect = pygame.Rect(cx - well_rad - 2, cy - well_rad + 3, (well_rad + 2) * 2, (well_rad + 2) * 2)
        shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, 90), (0, 0, shadow_rect.w, shadow_rect.h))
        surface.blit(shadow_surf, shadow_rect.topleft)

        # Stone Outer Wall Curb
        pygame.draw.circle(surface, COLOR_STONE_WALL, (cx, cy), well_rad)
        pygame.draw.circle(surface, COLOR_STONE_WALL_OUTLINE, (cx, cy), well_rad, max(2, int(4 * camera.zoom)))

        # Inner Well Hole (Chasm)
        inner_rad = max(6, int(well_rad * 0.72))
        pygame.draw.circle(surface, (15, 23, 42), (cx, cy), inner_rad)

        # Deep Fresh Water
        water_rad = max(4, int(inner_rad * 0.88))
        pygame.draw.circle(surface, (14, 116, 144), (cx, cy), water_rad)
        # Water shine & ripples
        shine_r = max(2, int(water_rad * 0.35))
        pygame.draw.circle(surface, (56, 189, 248), (cx - int(water_rad * 0.25), cy - int(water_rad * 0.25)), shine_r)
        pygame.draw.circle(surface, (186, 230, 253), (cx - int(water_rad * 0.3), cy - int(water_rad * 0.3)), max(1, shine_r // 2))

        # 4. Wooden Support Posts & Crossbeam
        post_w = max(3, int(6 * camera.zoom))
        post_h = max(14, int(well_rad * 1.5))
        py1 = cy - post_h // 2

        # Left Timber Post
        px_l = cx - well_rad - post_w // 2
        pygame.draw.rect(surface, (120, 80, 50), (px_l, py1, post_w, post_h), border_radius=2)
        pygame.draw.rect(surface, (60, 35, 15), (px_l, py1, post_w, post_h), width=1, border_radius=2)

        # Right Timber Post
        px_r = cx + well_rad - post_w // 2
        pygame.draw.rect(surface, (120, 80, 50), (px_r, py1, post_w, post_h), border_radius=2)
        pygame.draw.rect(surface, (60, 35, 15), (px_r, py1, post_w, post_h), width=1, border_radius=2)

        # Crossbeam (Horizontal Roof/Winch Timber)
        beam_w = (well_rad + 8) * 2
        beam_h = max(4, int(8 * camera.zoom))
        pygame.draw.rect(surface, (140, 90, 55), (cx - beam_w // 2, py1, beam_w, beam_h), border_radius=3)
        pygame.draw.rect(surface, (60, 35, 15), (cx - beam_w // 2, py1, beam_w, beam_h), width=1, border_radius=3)

        # Rope & Bucket
        rope_len = max(6, int(well_rad * 0.55))
        pygame.draw.line(surface, (217, 119, 6), (cx, py1 + beam_h), (cx, py1 + beam_h + rope_len), max(1, int(2 * camera.zoom)))
        buck_w = max(6, int(10 * camera.zoom))
        buck_h = max(5, int(8 * camera.zoom))
        pygame.draw.rect(surface, (180, 83, 9), (cx - buck_w // 2, py1 + beam_h + rope_len, buck_w, buck_h), border_radius=2)
        pygame.draw.rect(surface, (60, 35, 15), (cx - buck_w // 2, py1 + beam_h + rope_len, buck_w, buck_h), width=1, border_radius=2)

        # 5. Label
        lbl = self.font.render("Well", True, (241, 245, 249))
        min_tile = min(b.tiles, key=lambda t: (t[1], t[0]))
        bx, by = camera.world_to_screen(min_tile[0] * tile_size, min_tile[1] * tile_size)
        surface.blit(lbl, (bx + 6, by + 6))
