"""Completed building: arbitrary connected tile shapes with player-placed doors."""
import math
import time
import pygame
from game.config import (
    TILE_SIZE,
    BUILDING_TYPES,
    DEFAULT_ITEM_PRICES,
    MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT,
    DOORWAY_QUEUE_LATERAL_OFFSET,
)
from game.permits import get_exterior_edges_for_tile

class Building:
    def __init__(self, building_type, tiles, door_pos=None, door_side="bottom", rotation=0):
        self.building_type = building_type
        self._rotation = int(rotation) % 360
        self.condition = 1.0
        self.construction_order = None
        self.construction_progress = 0.0
        self.assigned_workers = []
        self.type_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])
        self.tiles = set(tiles)
        self._recalculate_bounds()
        self.name = f"{self.type_cfg['name']} ({len(self.tiles)} tiles)"
        if self.type_cfg.get("has_door", True) is False or self.building_type in ("well", "market"):
            self.door_pos = None
            self.door_side = None
            self.is_solid = (self.building_type in ("well", "market") or self.type_cfg.get("is_solid", False) or not self.type_cfg.get("has_door", True))
        else:
            self.door_pos, self.door_side = self._resolve_door(door_pos, door_side)
            self.is_solid = False

        # Market-specific economy and inventory properties (AGENT 2 & AGENT 3)
        if self.building_type == "market":
            self.owner = "landlord"
            self.inventory = {}  # Newly created Market starts with zero stock (Requirement 1)
            self.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
            self.prices = dict(DEFAULT_ITEM_PRICES)
            self.capacity = float("inf")  # UNLIMITED STORAGE CAPACITY (Not 6 slots)
            self.assigned_family_id = None
            self.item_allocations = {}
            self.sale_items = []
            self.household_sale_percent = MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT
            self.household_sale_limits = {}
            self.auto_pricing = False
            self.village_wealth_factor = 1.0
        else:
            self.owner = "landlord"
            self.inventory = {}
            self.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
            self.prices = {}
            self.capacity = 1000
            self.assigned_family_id = None
            self.item_allocations = {}
            self.auto_pricing = False
        self.wall_thickness = 10
        self._cached_oriented_walls = None
        self._cached_wall_rects = None
        self._cached_tile_size = None

        # Doorway Bottleneck Access & Smart Queuing
        self.door_active_user = None
        self.door_transit_start = 0.0
        self.door_transit_elapsed = 0.0
        self.door_outside_queue = []
        self.door_inside_queue = []

    @property
    def assigned_household_id(self):
        return getattr(self, "assigned_family_id", None)

    @assigned_household_id.setter
    def assigned_household_id(self, value):
        self.assigned_family_id = value

    @property
    def is_broken(self):
        return float(getattr(self, "condition", 1.0)) <= 0.0

    @property
    def is_available_for_use(self):
        order = getattr(self, "construction_order", None) or {}
        return not self.is_broken and order.get("status") in (None, "COMPLETE")

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
        Menghitung koordinat posisi antrean di dekat pintu (staggered lateral fan-out agar tidak bertumpuk).
        Posisi antrean dialihkan ke samping (lateral offset) dari sumbu pintu sehingga tidak menghalangi
        jalur lalu lintas AI yang sedang keluar maupun masuk (doorway clearance).
        """
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size

        dist_offset = tile_size * (1.25 + queue_idx * 0.45)
        # Offset ke samping sumbu pintu minimal DOORWAY_QUEUE_LATERAL_OFFSET agar koridor lurus pintu bersih
        lateral = DOORWAY_QUEUE_LATERAL_OFFSET + (queue_idx * 8.0)
        stagger = lateral if (queue_idx % 2 == 1) else -lateral

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
        if self.door_active_user:
            self.door_transit_elapsed = getattr(self, "door_transit_elapsed", 0.0) + dt
            if self.door_transit_elapsed > 3.0 or (time.time() - self.door_transit_start > 3.0):
                self.door_active_user = None
                self.door_transit_elapsed = 0.0
        else:
            self.door_transit_elapsed = 0.0

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
        return getattr(self, "_rotation", side_map.get(getattr(self, "door_side", "bottom"), 0) * 90) // 90

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

    def is_in_door_threshold(self, x, y, tile_size=TILE_SIZE, radius=0.0):
        """Check doorway transit while accounting for the actor's body clearance."""
        if not self.door_pos or not self.door_side:
            return False
        dx, dy = self.door_pos
        cx = (dx + 0.5) * tile_size
        cy = (dy + 0.5) * tile_size
        half_tile = tile_size / 2.0
        clearance = max(0.0, float(radius))
        if self.door_side in ("top", "bottom"):
            return abs(x - cx) < half_tile and abs(y - cy) < half_tile + clearance
        return abs(y - cy) < half_tile and abs(x - cx) < half_tile + clearance

    def crosses_doorway(self, old_x, old_y, new_x, new_y, tile_size=TILE_SIZE, radius=0.0):
        """True when one movement step crosses this building's actual doorway plane."""
        if not self.door_pos or not self.door_side:
            return False
        dx, dy = self.door_pos
        cx, cy = (dx + 0.5) * tile_size, (dy + 0.5) * tile_size
        if self.door_side in ("top", "bottom"):
            plane = (dy * tile_size + self.wall_thickness / 2
                     if self.door_side == "top"
                     else (dy + 1) * tile_size - self.wall_thickness / 2)
            old_side, new_side = old_y - plane, new_y - plane
            if old_side * new_side > 0 or abs(new_y - old_y) < 0.001:
                return False
            crossing_x = old_x + (new_x - old_x) * (-old_side / (new_side - old_side))
            return abs(crossing_x - cx) <= tile_size / 2
        plane = (dx * tile_size + self.wall_thickness / 2
                 if self.door_side == "left"
                 else (dx + 1) * tile_size - self.wall_thickness / 2)
        old_side, new_side = old_x - plane, new_x - plane
        if old_side * new_side > 0 or abs(new_x - old_x) < 0.001:
            return False
        crossing_y = old_y + (new_y - old_y) * (-old_side / (new_side - old_side))
        return abs(crossing_y - cy) <= tile_size / 2

    def get_approach_point(self, worker_x, worker_y=None, worker_id=None, all_entities=None, tile_size=TILE_SIZE, bm=None):
        """
        Mendapatkan titik pendekatan (approach point) di sekeliling perimeter site/bangunan.
        Mendukung multi-worker parallel: mendistribusikan pekerja ke petak perimeter yang berbeda
        agar tidak bertumpuk atau berebut satu koordinat.
        """
        if isinstance(worker_x, (tuple, list)):
            if isinstance(worker_y, (int, float)) and worker_y >= 32:
                tile_size = int(worker_y)
            if worker_id is not None and hasattr(worker_id, "get_building_at"):
                bm = worker_id
            worker_x, worker_y = float(worker_x[0]), float(worker_x[1])
        elif worker_y is None:
            worker_y = worker_x

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
            nearby_entities = (
                all_entities.for_tiles(perimeter_tiles)
                if hasattr(all_entities, "for_tiles") else all_entities
            )
            for other in nearby_entities:
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

        if getattr(self, "is_solid", False) or self.building_type in ("well", "market") or not self.type_cfg.get("has_door", True):
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

