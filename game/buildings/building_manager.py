"""BuildingManager: owns buildings, construction sites, and demolition sites."""
import math
import pygame
from game.render_cache import alpha_fill_surface, ellipse_surface, inset_rect_surface
from game.config import (
    TILE_SIZE,
    BUILDING_TYPES,
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
    COLOR_STONE_DOOR,
    DOORWAY_IDLE_MIN_DISTANCE,
)
from game.buildings.construction_site import ConstructionSite
from game.buildings.building import Building
from game.buildings.demolition_site import DemolitionSite

class BuildingManager:
    def __init__(self):
        self.buildings = []
        self.construction_sites = []
        self.demolition_sites = []
        self.font = None
        self._pathfinder = None
        self._tile_to_building = {}
        self._all_wall_rects_cache = {}
        self._navigation_revision = 0
        # *** ESTABLISHED — DO NOT REMOVE ***
        # PERF: flattened door anchor points (center/outside/inside) cached per
        # navigation revision so is_near_any_door() — called for every living
        # villager every frame — does not recompute door geometry per building.
        # Invalidated in rebuild_tile_cache().
        self._door_anchors_cache = None
        self._door_anchors_key = None
        # *** ESTABLISHED — DO NOT REMOVE ***
        # PERF: (outside, inside) door world-point pairs used by segment
        # validation in Pathfinder.is_segment_clear; cached per navigation
        # revision like _door_anchors_cache. Invalidated in rebuild_tile_cache().
        self._door_transit_pairs = None
        self._door_transit_key = None

    def rebuild_tile_cache(self):
        """Membangun pemetaan spasial O(1) dari petak (gx, gy) ke objek Building (Demolition sites are not solid)"""
        tb = {}
        for b in self.buildings:
            for t in b.tiles:
                tb[t] = b
        self._tile_to_building = tb
        self._all_wall_rects_cache.clear()
        self._navigation_revision += 1
        self._door_anchors_cache = None
        self._door_anchors_key = None
        self._door_transit_pairs = None
        self._door_transit_key = None

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
        # Commissionable public structures are paid for through the Carpenter's
        # landlord commission, not by consuming the Lord's construction stockpile.
        if b_cfg.get("carpenter_commissionable"):
            return True
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

        site = ConstructionSite(building_type, tiles, door_pos, door_side, rotation=rotation)
        self.construction_sites.append(site)
        from game.world.natural_resources import get_natural_resources
        get_natural_resources().occupy_tiles(tiles)
        return True

    def update(self, dt):
        completed = []
        for site in self.construction_sites:
            if site.is_complete():
                b = Building(
                    site.building_type, site.tiles,
                    door_pos=site.door_pos, door_side=site.door_side,
                    rotation=getattr(site, "_rotation", 0)
                )
                self.buildings.append(b)
                completed.append(site)

        if completed:
            for site in completed:
                self.construction_sites.remove(site)
            self.rebuild_tile_cache()
            from game.world.pathfinding import GlobalPathRegistry
            GlobalPathRegistry.get_instance().reset()

        for b in self.buildings:
            b.update_door_queue(dt)

    def get_pending_site(self):
        for site in self.construction_sites:
            if site.is_complete():
                continue
            order = getattr(site, "construction_order", None) or {}
            if order.get("order_type") == "PUBLIC_BUILD":
                # The Carpenter sources and pays for public-build materials from
                # the commission. Servants must not fetch them from the Lord's stockpile.
                continue
            return site
        return None

    def daily_public_maintenance_update(self, days=1):
        """Apply configured wear to public structures and create carpenter repair orders."""
        import random
        from game.data.config import BUILDING_TYPES, PUBLIC_STRUCTURE_DAILY_BREAK_CHANCE
        from game.systems.carpenter_system import CarpenterSystem

        damaged = []
        for _ in range(max(0, int(days))):
            for building in self.buildings:
                cfg = BUILDING_TYPES.get(getattr(building, "building_type", ""), {})
                order = getattr(building, "construction_order", None) or {}
                if (not cfg.get("public_structure") or not cfg.get("maintainable", True)
                        or building.is_broken or order.get("status") not in (None, "COMPLETE")):
                    continue
                if random.random() >= PUBLIC_STRUCTURE_DAILY_BREAK_CHANCE:
                    continue
                building.condition = 0.0
                order = CarpenterSystem.create_repair_order(
                    building, self, getattr(self, "villager_manager", None)
                )
                order.update({
                    "id": f"building:{building.building_type}:{building.grid_x}:{building.grid_y}",
                    "status": "LANDLORD_PAYMENT_PENDING",
                    "payer_type": "landlord",
                    "payer_id": "landlord",
                })
                building.construction_order = order
                damaged.append(building)
        return damaged

    def get_completed_wells(self):
        """Mendapatkan daftar seluruh bangunan sumur yang sudah selesai dibangun"""
        return [b for b in self.buildings
                if b.building_type == "well" and b.is_available_for_use]

    def get_all_wall_rects(self, tile_size):
        if tile_size not in self._all_wall_rects_cache:
            self._all_wall_rects_cache[tile_size] = [
                wall for building in self.buildings
                for wall in building.get_wall_rects(tile_size)
            ]
        return self._all_wall_rects_cache[tile_size]

    def get_site_at(self, gx, gy):
        """Mencari construction site yang berada di koordinat tile (gx, gy)"""
        for site in self.construction_sites:
            if (gx, gy) in site.tiles:
                return site
        return None

    def get_demolition_at(self, gx, gy):
        """Mencari demolition site yang berada di koordinat tile (gx, gy)"""
        for demo in self.demolition_sites:
            if (gx, gy) in demo.tiles:
                return demo
        return None

    def cancel_construction(self, site, resources=None, stockpile_manager=None, all_servants=None, furniture_manager=None):
        """
        Membatalkan proyek pembangunan bangunan (Blueprint atau sedang berjalan).
        - Mengembalikan material yang sudah diantar ke site.
        - Membebaskan reservasi sumber daya di stockpile.
        - Menghapus site dan membebaskan penugasan pekerja/servant.
        """
        if site not in self.construction_sites:
            return False

        # Carpenter-delivered materials go back to the paying household/treasury;
        # only the non-carpenter portion falls back to the generic pools.
        carpenter_delivered = {}
        order = getattr(site, "construction_order", None)
        if order and order.get("status") != "COMPLETE":
            from game.systems.carpenter_system import CarpenterSystem
            carpenter_delivered = CarpenterSystem.refund_order_materials(
                order, site, furniture_manager, stockpile_manager,
            )

        # 1. Refund material yang sudah diantar ke site
        for res, amt in getattr(site, "delivered_cost", {}).items():
            amt = max(0, int(amt) - int(carpenter_delivered.get(res, 0)))
            if amt > 0:
                if resources is not None and res in resources:
                    resources[res] += amt
                elif stockpile_manager is not None:
                    stockpile_manager.add_resource(res, amt)

        # 2. Release reservasi pada stockpile jika ada
        for res, amt in getattr(site, "reserved_cost", {}).items():
            if amt > 0 and stockpile_manager:
                for stack in getattr(stockpile_manager, "stacks", []):
                    stack_res = getattr(stack, "resource_type", getattr(stack, "item_name", None))
                    if stack_res == res and getattr(stack, "reserved_amount", 0) > 0:
                        unres = min(stack.reserved_amount, amt)
                        stack.reserved_amount -= unres
                        amt -= unres
                        if amt <= 0:
                            break

        # 3. Hapus site dari daftar konstruksi aktif
        self.construction_sites.remove(site)
        from game.world.natural_resources import get_natural_resources
        get_natural_resources().release_tiles(getattr(site, "tiles", ()))

        # 4. Bebaskan servant/pekerja yang sedang ditugaskan ke site ini
        if all_servants:
            for s in all_servants:
                if getattr(s, "target_site", None) == site or getattr(s, "target_construction", None) == site:
                    s.target_site = None
                    s.target_construction = None
                    s.state = "IDLE"
                    s.task = "IDLE"
                    s.is_moving = False
                    s.current_path = []
                    s.path_target = None

        # 5. Reset rute dan reservasi pathfinding
        from game.world.pathfinding import GlobalPathRegistry
        GlobalPathRegistry.get_instance().reset()
        return True

    def cancel_demolition(self, site_or_building, all_servants=None):
        """
        Membatalkan pembongkaran bangunan (Demolition).
        - Menghentikan proses pembongkaran.
        - Mengembalikan bangunan ke status utuh (SOLID) di daftar buildings.
        - Membebaskan penugasan pekerja/servant.
        - Menjaga seluruh isi bangunan (furnitur, inventaris, izin tanah) tetap utuh.
        """
        target_site = None
        for d in self.demolition_sites:
            if d == site_or_building or getattr(d, "building", None) == site_or_building:
                target_site = d
                break

        if not target_site:
            return False

        self.demolition_sites.remove(target_site)
        b = target_site.building
        if b and b not in self.buildings:
            self.buildings.append(b)

        self.rebuild_tile_cache()

        if all_servants:
            for s in all_servants:
                if getattr(s, "target_demolition", None) == target_site or getattr(s, "target_site", None) == target_site:
                    s.target_demolition = None
                    s.target_site = None
                    s.state = "IDLE"
                    s.task = "IDLE"
                    s.is_moving = False
                    s.current_path = []
                    s.path_target = None

        from game.world.pathfinding import GlobalPathRegistry
        GlobalPathRegistry.get_instance().reset()
        return True

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
            in_door = (
                b.is_in_door_threshold(ref_x, ref_y, tile_size, radius=radius)
                or b.is_in_door_threshold(new_x, new_y, tile_size, radius=radius)
                or b.crosses_doorway(ref_x, ref_y, new_x, new_y, tile_size, radius=radius)
            )
            # NOTE: was_inside is per-BUILDING, not per-wall. On concave
            # footprints an entity can be inside the footprint yet stand on the
            # courtyard side of an interior-facing wall — the per-wall distance
            # bounds below are what keep that case from teleporting entities.
            was_inside = b.occupies_tile(int(math.floor(ref_x / tile_size)), int(math.floor(ref_y / tile_size)))

            for wr, side in b.get_oriented_walls(tile_size):
                if side == "door_post":
                    # Door posts are only the visible ends of an opening. Once
                    # an actor is crossing the doorway, their body radius must
                    # not turn those decorative edges into a narrow collision
                    # funnel that traps actors against the jamb.
                    if in_door:
                        continue
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
                            # *** ESTABLISHED — DO NOT REGRESS ***
                            # The perpendicular bound (wr.top - radius < new_y)
                            # is REQUIRED: on concave footprints (U/L shapes)
                            # a courtyard-facing wall sits between two interior
                            # regions, and an unbounded check teleports entities
                            # ~2 tiles through the wall (measured 130px flings).
                            if wr.top - radius < new_y < wr.bottom + radius:
                                new_y = wr.bottom + radius
                        else:
                            if new_y > wr.top - radius and new_y < wr.bottom:
                                new_y = wr.top - radius
                elif side == "bottom":
                    if wr.left - radius < new_x < wr.right + radius:
                        if was_inside:
                            # *** ESTABLISHED — DO NOT REGRESS *** same as "top"
                            if wr.top - radius < new_y < wr.bottom + radius:
                                new_y = wr.top - radius
                        else:
                            if new_y < wr.bottom + radius and new_y > wr.top:
                                new_y = wr.bottom + radius
                elif side == "left":
                    if wr.top - radius < new_y < wr.bottom + radius:
                        if was_inside:
                            # *** ESTABLISHED — DO NOT REGRESS *** same as "top"
                            if wr.left - radius < new_x < wr.right + radius:
                                new_x = wr.right + radius
                        else:
                            if new_x > wr.left - radius and new_x < wr.right:
                                new_x = wr.left - radius
                elif side == "right":
                    if wr.top - radius < new_y < wr.bottom + radius:
                        if was_inside:
                            # *** ESTABLISHED — DO NOT REGRESS *** same as "top"
                            if wr.left - radius < new_x < wr.right + radius:
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
            nearby_entities = (
                all_entities.for_tiles([door_pos], include_targets=False)
                if hasattr(all_entities, "for_tiles") else all_entities
            )
            for e in nearby_entities:
                if e == exclude_entity:
                    continue
                if b.is_in_door_threshold(e.x, e.y, tile_size):
                    return True
            return False

        cx = (door_pos[0] + 0.5) * tile_size
        cy = (door_pos[1] + 0.5) * tile_size
        nearby_entities = (
            all_entities.for_tiles([door_pos], include_targets=False)
            if hasattr(all_entities, "for_tiles") else all_entities
        )
        for e in nearby_entities:
            if e == exclude_entity:
                continue
            dist = math.hypot(e.x - cx, e.y - cy)
            if dist < radius:
                return True
        return False

    def _get_door_anchors(self, tile_size):
        """Cached flat list of (x, y) door anchor points for proximity checks."""
        key = (tile_size, self._navigation_revision, len(self.buildings))
        if self._door_anchors_key != key:
            anchors = []
            for b in self.buildings:
                if getattr(b, "door_pos", None):
                    cx = (b.door_pos[0] + 0.5) * tile_size
                    cy = (b.door_pos[1] + 0.5) * tile_size
                    anchors.append((cx, cy))
                    d_out = b.get_door_world_outside(tile_size)
                    d_in = b.get_door_world_inside(tile_size)
                    anchors.append(d_out)
                    anchors.append(d_in)
            self._door_anchors_cache = anchors
            self._door_anchors_key = key
        return self._door_anchors_cache

    def get_door_transit_pairs(self, tile_size):
        """Cached (outside, inside) world-point pairs for every door building."""
        key = (tile_size, self._navigation_revision, len(self.buildings))
        if self._door_transit_key != key:
            pairs = [
                (b.get_door_world_outside(tile_size), b.get_door_world_inside(tile_size))
                for b in self.buildings
                if getattr(b, "door_pos", None)
            ]
            self._door_transit_pairs = pairs
            self._door_transit_key = key
        return self._door_transit_pairs

    def is_near_any_door(self, x, y, min_dist=DOORWAY_IDLE_MIN_DISTANCE, tile_size=TILE_SIZE):
        """Mengecek apakah posisi (x, y) terlalu dekat dengan celah pintu atau koridor threshold pintu bangunan mana pun"""
        # *** ESTABLISHED — DO NOT REMOVE ***
        # PERF: door anchors are cached per navigation revision — this runs for
        # every living villager every frame, so keep it allocation-free.
        anchors = self._get_door_anchors(tile_size)
        near_center = min_dist
        near_side = min_dist * 0.75
        for i in range(0, len(anchors), 3):
            cx, cy = anchors[i]
            if math.hypot(x - cx, y - cy) < near_center:
                return True
            d_out = anchors[i + 1]
            d_in = anchors[i + 2]
            if math.hypot(x - d_out[0], y - d_out[1]) < near_side or \
               math.hypot(x - d_in[0], y - d_in[1]) < near_side:
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
        """
        Menyelesaikan pembongkaran dan menjatuhkan 50% refund material secara fisik di tanah.
        RECOVER ALL MARKET CONTENTS (Requirement 5):
        Menjatuhkan seluruh barang tersimpan dan seluruh koin (Copper, Silver, Gold)
        pada petak pembongkaran dengan kepemilikan utuh (villager jika assigned household,
        landlord jika unassigned).
        """
        b = getattr(site, "building", None)
        sorted_tiles = sorted(site.tiles, key=lambda t: (t[1], t[0])) if site.tiles else []

        if stockpile_manager and sorted_tiles:
            tile_w = sorted_tiles[0]
            tile_s = sorted_tiles[1] if len(sorted_tiles) > 1 else sorted_tiles[0]
            stockpile_manager.drop_resource("Wood", site.refund_wood, tile_w[0], tile_w[1])
            stockpile_manager.drop_resource("Stone", site.refund_stone, tile_s[0], tile_s[1])

            # Drop all building contents (items & currency) with preserved ownership
            if b:
                assigned_fam = getattr(b, "assigned_household_id", None) or getattr(b, "assigned_family_id", None)
                owner_type = "villager" if assigned_fam else "landlord"
                owner_id = str(assigned_fam) if assigned_fam else None

                t_idx = 0
                num_tiles = len(sorted_tiles)

                # 1. Drop stored items
                if hasattr(b, "inventory") and isinstance(b.inventory, dict):
                    for it_name, it_count in list(b.inventory.items()):
                        if it_count > 0:
                            drop_t = sorted_tiles[t_idx % num_tiles]
                            stockpile_manager.drop_resource(it_name, it_count, drop_t[0], drop_t[1], owner_type=owner_type, owner_id=owner_id)
                            t_idx += 1
                    b.inventory.clear()

                # 2. Drop stored currency
                if hasattr(b, "currency") and isinstance(b.currency, dict):
                    for denom in ("Copper", "Silver", "Gold"):
                        c_amt = b.currency.get(denom, 0)
                        if c_amt > 0:
                            drop_t = sorted_tiles[t_idx % num_tiles]
                            stockpile_manager.drop_resource(denom, c_amt, drop_t[0], drop_t[1], owner_type=owner_type, owner_id=owner_id)
                            t_idx += 1
                    b.currency.clear()

            stockpile_manager.refresh_stacks(resources, None)
        else:
            resources["Wood"] = resources.get("Wood", 0) + site.refund_wood
            resources["Stone"] = resources.get("Stone", 0) + site.refund_stone
            if b:
                if hasattr(b, "inventory") and isinstance(b.inventory, dict):
                    for it_name, it_count in list(b.inventory.items()):
                        if it_count > 0:
                            resources[it_name] = resources.get(it_name, 0) + it_count
                    b.inventory.clear()
                if hasattr(b, "currency") and isinstance(b.currency, dict):
                    for denom in ("Copper", "Silver", "Gold"):
                        c_amt = b.currency.get(denom, 0)
                        if c_amt > 0:
                            resources[denom] = resources.get(denom, 0) + c_amt
                    b.currency.clear()

        # Invalidate village wealth cache
        try:
            from game.systems.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        except ImportError:
            pass

        if site in self.demolition_sites:
            self.demolition_sites.remove(site)
            self.rebuild_tile_cache()
        from game.world.natural_resources import get_natural_resources
        get_natural_resources().release_tiles(getattr(site, "tiles", ()))

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        for site in self.construction_sites:
            site.draw(surface, camera, tile_size)

        for site in self.demolition_sites:
            site.draw(surface, camera, tile_size)

        for b in self.buildings:
            self._draw_building(surface, camera, tile_size, b)
            self._draw_public_repair_order(surface, camera, tile_size, b)

    def draw_public_structure_preview(self, surface, camera, tile_size, building_type, tiles, rotation=0):
        """Draw the configured visual for a public structure while the player places it."""
        if building_type not in BUILDING_TYPES or not tiles:
            return
        preview = Building(building_type, tiles, rotation=rotation)
        self._draw_building(surface, camera, tile_size, preview)

    def _draw_public_repair_order(self, surface, camera, tile_size, building):
        """Show public structure repairs with the same visible repair state as furniture orders."""
        order = getattr(building, "construction_order", None) or {}
        if (not (getattr(building, "type_cfg", {}) or {}).get("public_structure")
                or order.get("order_type") != "REPAIR"
                or order.get("status") == "COMPLETE"):
            return
        if building.tiles and not camera.is_world_rect_visible(
                building.grid_x * tile_size, building.grid_y * tile_size,
                building.tiles_w * tile_size, building.tiles_h * tile_size):
            return

        status_colors = {
            "AWAITING_PAYMENT": (234, 179, 8),
            "LANDLORD_PAYMENT_PENDING": (234, 179, 8),
            "LANDLORD_RETRIEVING": (56, 189, 248),
            "PAYMENT_TRAVELING": (56, 189, 248),
            "PAID": (56, 189, 248),
            "BUILDING": (34, 197, 94),
        }
        color = status_colors.get(order.get("status"), (56, 189, 248))
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))
        world_bounds = (
            building.grid_x * tile_size, building.grid_y * tile_size,
            (building.grid_x + building.tiles_w) * tile_size,
            (building.grid_y + building.tiles_h) * tile_size,
        )
        visible_tiles = list(camera.iter_visible_tiles(building.tiles, tile_size, world_bounds))
        for gx, gy in visible_tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            overlay = alpha_fill_surface(scaled_tile + 1, scaled_tile + 1, (*color, 58))
            surface.blit(overlay, (sx, sy))
            pygame.draw.rect(surface, color, (sx, sy, scaled_tile + 1, scaled_tile + 1), width=1)

        if not visible_tiles:
            return
        self._ensure_font()
        anchor = min(visible_tiles, key=lambda tile: (
            (tile[0] - (building.grid_x + building.tiles_w / 2)) ** 2
            + (tile[1] - (building.grid_y + building.tiles_h / 2)) ** 2
        ))
        sx, sy = camera.world_to_screen(anchor[0] * tile_size, anchor[1] * tile_size)
        label = self.font.render("REPAIR", True, (255, 255, 255))
        if scaled_tile >= max(label.get_width() + 10, label.get_height() + 6):
            badge = pygame.Rect(0, 0, label.get_width() + 10, label.get_height() + 6)
            badge.center = (sx + scaled_tile // 2, sy + scaled_tile // 2)
            pygame.draw.rect(surface, (15, 23, 42), badge, border_radius=4)
            pygame.draw.rect(surface, color, badge, width=1, border_radius=4)
            surface.blit(label, (badge.x + 5, badge.y + 3))

        center_x, center_y = building.get_center_world(tile_size)
        bar_center_x, bar_top_y = camera.world_to_screen(center_x, building.grid_y * tile_size)
        bar_width = max(1, min(240, int(len(building.tiles) * 12 * camera.zoom)))
        bar_height = max(3, math.ceil(5 * camera.zoom))
        bar_x, bar_y = bar_center_x - bar_width // 2, bar_top_y - 20
        pygame.draw.rect(surface, (15, 23, 42), (bar_x - 2, bar_y - 2, bar_width + 4, bar_height + 4), border_radius=4)
        pygame.draw.rect(surface, color, (bar_x - 2, bar_y - 2, bar_width + 4, bar_height + 4), width=1, border_radius=4)
        fill = pygame.Rect(bar_x, bar_y, int(bar_width * max(0.0, min(1.0, float(order.get("progress_ratio", 0.0))))), bar_height)
        if fill.width:
            pygame.draw.rect(surface, color, fill, border_radius=3)

    def _draw_building(self, surface, camera, tile_size, b):
        if b.tiles and not camera.is_world_rect_visible(
                b.grid_x * tile_size, b.grid_y * tile_size,
                b.tiles_w * tile_size, b.tiles_h * tile_size):
            return
        if b.building_type == "well":
            self._draw_well(surface, camera, tile_size, b)
            return
        if b.building_type == "market":
            self._draw_market(surface, camera, tile_size, b)
            return
        if b.building_type == "toilet":
            self._draw_toilet(surface, camera, tile_size, b)
            return
        if b.building_type == "tax_house":
            self._draw_tax_office(surface, camera, tile_size, b)
            return

        world_bounds = (
            b.grid_x * tile_size, b.grid_y * tile_size,
            (b.grid_x + b.tiles_w) * tile_size,
            (b.grid_y + b.tiles_h) * tile_size,
        )
        visible_tiles = list(camera.iter_visible_tiles(b.tiles, tile_size, world_bounds))

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

        for (gx, gy) in visible_tiles:
            wx = gx * tile_size
            wy = gy * tile_size
            sx, sy = camera.world_to_screen(wx, wy)

            floor_color = floor_a if (gx + gy) % 2 == 0 else floor_b
            rect = pygame.Rect(sx, sy, scaled_tile + 1, scaled_tile + 1)
            pygame.draw.rect(surface, floor_color, rect)

        # 2. Dinding Luar dan Celah Pintu untuk setiap tile
        for (gx, gy) in visible_tiles:
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
        shadow_surf = ellipse_surface(shadow_rect.w, shadow_rect.h, (0, 0, 0, 90))
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

    def _draw_market(self, surface, camera, tile_size, b):
        """
        Render completed medieval market stall (Footprint 3x2, Unlimited Storage).
        Authentic medieval market aesthetic:
        - Timber deck & cobblestone foundation plaza
        - Wooden sales counters, balance scales, wicker produce baskets, sacks, and barrels
        - Striped burgundy & cream cloth canopy / awning with support timber posts
        - Carved wooden 'MARKET' merchant sign
        """
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))
        if not b.tiles:
            return

        min_gx = min(x for x, y in b.tiles)
        max_gx = max(x for x, y in b.tiles)
        min_gy = min(y for x, y in b.tiles)
        max_gy = max(y for x, y in b.tiles)

        span_w = (max_gx - min_gx + 1) * scaled_tile
        span_h = (max_gy - min_gy + 1) * scaled_tile
        origin_sx, origin_sy = camera.world_to_screen(min_gx * tile_size, min_gy * tile_size)

        # -------------------------------------------------------------
        # 1. FOUNDATION: Timber & Cobblestone Marketplace Decking
        # -------------------------------------------------------------
        for (gx, gy) in b.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            deck_col = (195, 150, 105) if (gx + gy) % 2 == 0 else (180, 135, 90)
            pygame.draw.rect(surface, deck_col, (sx, sy, scaled_tile + 1, scaled_tile + 1))
            # Plank texture grooves
            plank_gap = max(3, int(scaled_tile / 4))
            for p_off in range(plank_gap, scaled_tile, plank_gap):
                pygame.draw.line(surface, (140, 100, 65), (sx, sy + p_off), (sx + scaled_tile, sy + p_off), 1)

        # Foundation outer timber curb & perimeter
        for (gx, gy) in b.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            if (gx, gy - 1) not in b.tiles:
                pygame.draw.line(surface, (100, 65, 35), (sx, sy), (sx + scaled_tile, sy), 2)
            if (gx, gy + 1) not in b.tiles:
                pygame.draw.line(surface, (100, 65, 35), (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)
            if (gx - 1, gy) not in b.tiles:
                pygame.draw.line(surface, (100, 65, 35), (sx, sy), (sx, sy + scaled_tile), 2)
            if (gx + 1, gy) not in b.tiles:
                pygame.draw.line(surface, (100, 65, 35), (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

        # -------------------------------------------------------------
        # 2. MARKET GOODS & COUNTER FURNISHINGS
        # -------------------------------------------------------------
        # Sturdy wooden display counter along the top half
        counter_y = origin_sy + int(span_h * 0.22)
        counter_h = max(8, int(span_h * 0.26))
        counter_margin = max(6, int(span_w * 0.08))
        counter_w = span_w - counter_margin * 2

        # Counter shadow
        pygame.draw.rect(surface, (0, 0, 0, 70), (origin_sx + counter_margin + 2, counter_y + 3, counter_w, counter_h), border_radius=3)
        # Counter top
        pygame.draw.rect(surface, (139, 90, 43), (origin_sx + counter_margin, counter_y, counter_w, counter_h), border_radius=3)
        pygame.draw.rect(surface, (90, 55, 20), (origin_sx + counter_margin, counter_y, counter_w, counter_h), width=1, border_radius=3)

        # Scales / Balance on the counter
        scale_x = origin_sx + counter_margin + int(counter_w * 0.72)
        scale_y = counter_y + counter_h // 2
        post_len = max(6, int(counter_h * 0.7))
        pygame.draw.line(surface, (234, 179, 8), (scale_x, scale_y - post_len), (scale_x, scale_y + 2), max(1, int(2 * camera.zoom)))
        beam_len = max(8, int(counter_w * 0.12))
        pygame.draw.line(surface, (234, 179, 8), (scale_x - beam_len, scale_y - post_len), (scale_x + beam_len, scale_y - post_len), max(1, int(2 * camera.zoom)))
        # Scale pans
        pan_r = max(2, int(beam_len * 0.45))
        pygame.draw.arc(surface, (234, 179, 8), (scale_x - beam_len - pan_r, scale_y - post_len + 2, pan_r * 2, pan_r * 2), 0, math.pi, max(1, int(2 * camera.zoom)))
        pygame.draw.arc(surface, (234, 179, 8), (scale_x + beam_len - pan_r, scale_y - post_len + 2, pan_r * 2, pan_r * 2), 0, math.pi, max(1, int(2 * camera.zoom)))

        # Produce Baskets with Potatoes on the Counter & Floor
        # Basket 1 (Produce basket)
        bask_x = origin_sx + counter_margin + int(counter_w * 0.22)
        bask_y = counter_y + counter_h // 2
        bw = max(10, int(counter_w * 0.16))
        bh = max(8, int(counter_h * 0.75))
        pygame.draw.ellipse(surface, (180, 120, 60), (bask_x - bw // 2, bask_y - bh // 2, bw, bh))
        pygame.draw.ellipse(surface, (110, 65, 25), (bask_x - bw // 2, bask_y - bh // 2, bw, bh), 1)
        # Potatoes inside basket
        pot_r = max(2, int(bw * 0.22))
        pygame.draw.circle(surface, (194, 120, 60), (bask_x - 2, bask_y - 1), pot_r)
        pygame.draw.circle(surface, (194, 120, 60), (bask_x + 3, bask_y), pot_r)
        pygame.draw.circle(surface, (160, 95, 40), (bask_x, bask_y - 2), pot_r)

        # Wooden Barrels & Sacks on the floor
        barrel_x = origin_sx + counter_margin + 6
        barrel_y = origin_sy + int(span_h * 0.65)
        bar_w = max(12, int(span_w * 0.12))
        bar_h = max(14, int(span_h * 0.24))
        pygame.draw.ellipse(surface, (150, 95, 45), (barrel_x, barrel_y, bar_w, bar_h))
        pygame.draw.ellipse(surface, (70, 40, 15), (barrel_x, barrel_y, bar_w, bar_h), 1)
        # Iron rings on barrel
        pygame.draw.line(surface, (71, 85, 105), (barrel_x + 2, barrel_y + bar_h // 3), (barrel_x + bar_w - 2, barrel_y + bar_h // 3), max(1, int(1.5 * camera.zoom)))
        pygame.draw.line(surface, (71, 85, 105), (barrel_x + 2, barrel_y + (bar_h * 2) // 3), (barrel_x + bar_w - 2, barrel_y + (bar_h * 2) // 3), max(1, int(1.5 * camera.zoom)))

        # Sacks of Grain / Tubers
        sack_x = origin_sx + span_w - counter_margin - bar_w - 8
        sack_y = origin_sy + int(span_h * 0.62)
        sk_w = max(14, int(span_w * 0.14))
        sk_h = max(12, int(span_h * 0.20))
        pygame.draw.ellipse(surface, (214, 195, 150), (sack_x, sack_y, sk_w, sk_h))
        pygame.draw.ellipse(surface, (140, 120, 80), (sack_x, sack_y, sk_w, sk_h), 1)
        # Sack neck tied with string
        pygame.draw.circle(surface, (180, 155, 110), (sack_x + sk_w // 2, sack_y - 2), max(2, int(sk_w * 0.2)))
        pygame.draw.line(surface, (120, 75, 25), (sack_x + sk_w // 2 - 3, sack_y), (sack_x + sk_w // 2 + 3, sack_y), 1)

        # -------------------------------------------------------------
        # 3. FOUR CORNER TIMBER POSTS
        # -------------------------------------------------------------
        post_sz = max(4, int(7 * camera.zoom))
        posts = [
            (origin_sx + 4, origin_sy + 4),
            (origin_sx + span_w - post_sz - 4, origin_sy + 4),
            (origin_sx + 4, origin_sy + span_h - post_sz - 4),
            (origin_sx + span_w - post_sz - 4, origin_sy + span_h - post_sz - 4),
        ]
        for px, py in posts:
            pygame.draw.rect(surface, (100, 60, 25), (px, py, post_sz, post_sz), border_radius=2)
            pygame.draw.rect(surface, (50, 25, 10), (px, py, post_sz, post_sz), width=1, border_radius=2)

        # -------------------------------------------------------------
        # 4. MEDIEVAL STRIPED MERCHANT CANOPY / AWNING
        # -------------------------------------------------------------
        # Overhead cloth canopy with bold merchant stripes: Burgundy & Cream
        canopy_y = origin_sy - max(6, int(10 * camera.zoom))
        canopy_h = max(16, int(span_h * 0.52))
        canopy_w = span_w + max(6, int(10 * camera.zoom))
        canopy_x = origin_sx - (canopy_w - span_w) // 2

        # Canopy cast shadow
        shadow_rect = pygame.Rect(canopy_x + 4, canopy_y + canopy_h - 2, canopy_w - 8, max(4, int(6 * camera.zoom)))
        shadow_surf = alpha_fill_surface(shadow_rect.w, shadow_rect.h, (0, 0, 0, 65))
        surface.blit(shadow_surf, shadow_rect.topleft)

        # Striped panels
        num_stripes = 10
        stripe_w = canopy_w / num_stripes
        color_red = (185, 28, 28)       # Merchant crimson burgundy
        color_cream = (245, 240, 224)   # Linen cream
        valance_r = max(3, int(stripe_w / 2))

        for i in range(num_stripes):
            st_x = int(canopy_x + i * stripe_w)
            st_next_x = int(canopy_x + (i + 1) * stripe_w)
            st_w = st_next_x - st_x
            st_col = color_red if i % 2 == 0 else color_cream

            # Main canopy stripe slope
            pygame.draw.rect(surface, st_col, (st_x, canopy_y, st_w, canopy_h))
            pygame.draw.line(surface, (120, 20, 20) if i % 2 == 0 else (200, 195, 175), (st_x, canopy_y), (st_x, canopy_y + canopy_h), 1)

            # Scalloped valance / fringe at bottom edge
            scallop_center_x = st_x + st_w // 2
            pygame.draw.circle(surface, st_col, (scallop_center_x, canopy_y + canopy_h), valance_r)
            pygame.draw.circle(surface, (120, 20, 20) if i % 2 == 0 else (180, 175, 155), (scallop_center_x, canopy_y + canopy_h), valance_r, 1)

        # Canopy front ridge beam & trim
        pygame.draw.line(surface, (100, 50, 20), (canopy_x, canopy_y), (canopy_x + canopy_w, canopy_y), max(2, int(2.5 * camera.zoom)))
        pygame.draw.line(surface, (100, 50, 20), (canopy_x, canopy_y + canopy_h), (canopy_x + canopy_w, canopy_y + canopy_h), max(1, int(1.5 * camera.zoom)))

        # -------------------------------------------------------------
        # 5. CARVED TIMBER MERCHANT SIGN
        # -------------------------------------------------------------
        sign_w = max(60, min(140, int(span_w * 0.48)))
        sign_h = max(14, int(20 * camera.zoom))
        sign_x = origin_sx + (span_w - sign_w) // 2
        sign_y = canopy_y + canopy_h - 4

        # Hanging chains
        pygame.draw.line(surface, (71, 85, 105), (sign_x + 8, canopy_y + canopy_h - 6), (sign_x + 8, sign_y), 1)
        pygame.draw.line(surface, (71, 85, 105), (sign_x + sign_w - 8, canopy_y + canopy_h - 6), (sign_x + sign_w - 8, sign_y), 1)

        # Wooden sign plank
        pygame.draw.rect(surface, (15, 23, 42, 230), (sign_x, sign_y, sign_w, sign_h), border_radius=4)
        pygame.draw.rect(surface, (250, 204, 21), (sign_x, sign_y, sign_w, sign_h), width=1, border_radius=4)

        sign_txt = self.font.render("MARKET", True, (250, 204, 21))
        surface.blit(sign_txt, (sign_x + (sign_w - sign_txt.get_width()) // 2, sign_y + (sign_h - sign_txt.get_height()) // 2))

    def _draw_toilet(self, surface, camera, tile_size, b):
        """
        Renders a completed medieval wooden outhouse latrine (1x1 footprint).
        Authentic medieval wooden outhouse aesthetic:
        - Timber floor plank foundation
        - Sloped wooden shingle roof
        - Vertical timber planks with carved crescent moon door aperture
        - Subtle occupied indicator and label
        """
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        for (gx, gy) in b.tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)

            # 1. Foundation Drop Shadow
            shadow_surf = inset_rect_surface(scaled_tile, scaled_tile, (0, 0, 0, 75), 4, 3)
            surface.blit(shadow_surf, (sx, sy))

            # 2. Wooden Floor Foundation
            pygame.draw.rect(surface, (101, 67, 33), (sx + 2, sy + 2, scaled_tile - 4, scaled_tile - 4), border_radius=2)
            pygame.draw.rect(surface, (60, 35, 15), (sx + 2, sy + 2, scaled_tile - 4, scaled_tile - 4), width=1, border_radius=2)

            # 3. Wooden Booth Walls
            wall_margin = max(2, int(4 * camera.zoom))
            booth_w = scaled_tile - wall_margin * 2
            booth_h = scaled_tile - wall_margin * 2
            bx = sx + wall_margin
            by = sy + wall_margin

            pygame.draw.rect(surface, (139, 90, 43), (bx, by, booth_w, booth_h), border_radius=3)
            pygame.draw.rect(surface, (78, 48, 20), (bx, by, booth_w, booth_h), width=max(1, int(2 * camera.zoom)), border_radius=3)

            # Planks vertical texture
            plank_count = 3
            for p in range(1, plank_count):
                px_line = bx + int(booth_w * (p / plank_count))
                pygame.draw.line(surface, (95, 60, 25), (px_line, by + 2), (px_line, by + booth_h - 2), 1)

            # 4. Sloped Wooden Roof Overhang
            roof_h = max(4, int(booth_h * 0.32))
            roof_points = [
                (bx - 3, by + roof_h),
                (bx + booth_w // 2, by - 3),
                (bx + booth_w + 3, by + roof_h)
            ]
            pygame.draw.polygon(surface, (115, 75, 35), roof_points)
            pygame.draw.polygon(surface, (55, 30, 10), roof_points, max(1, int(1.5 * camera.zoom)))

            # 5. Out-house Door Crescent Aperture (Iconic medieval crescent moon)
            c_center_x = bx + booth_w // 2
            c_center_y = by + int(booth_h * 0.62)
            c_radius = max(2, int(3.5 * camera.zoom))
            if c_radius >= 2:
                pygame.draw.circle(surface, (45, 25, 10), (c_center_x, c_center_y), c_radius)
                pygame.draw.circle(surface, (139, 90, 43), (c_center_x + max(1, int(c_radius * 0.45)), c_center_y), int(c_radius * 0.82))

            # 6. Subtle Occupied Indicator
            is_occupied = getattr(b, "occupied_by", None) is not None
            if is_occupied:
                pip_r = max(2, int(3 * camera.zoom))
                pygame.draw.circle(surface, (239, 68, 68), (bx + booth_w - pip_r - 2, by + pip_r + 2), pip_r)
            else:
                pip_r = max(2, int(3 * camera.zoom))
                pygame.draw.circle(surface, (34, 197, 94), (bx + booth_w - pip_r - 2, by + pip_r + 2), pip_r)

            # 7. Subtle Label
            lbl = self.font.render("WC", True, (245, 245, 240))
            surface.blit(lbl, (bx + 3, by + 3))

    def _draw_tax_office(self, surface, camera, tile_size, b):
        """Render the Tax Office as an open medieval clerk's station, not a residence."""
        self._ensure_font()
        style = (getattr(b, "type_cfg", {}) or {}).get("visual_style", {})
        platform = style.get("platform", (95, 75, 53))
        platform_light = style.get("platform_light", platform)
        platform_dark = style.get("platform_dark", platform)
        wood = style.get("wood", (121, 78, 42))
        wood_light = style.get("wood_light", (166, 112, 61))
        wood_dark = style.get("wood_dark", (62, 39, 26))
        royal_cloth = style.get("royal_cloth", (126, 32, 35))
        gold = style.get("gold", (226, 174, 73))
        parchment = style.get("parchment", (221, 202, 158))
        metal = style.get("metal", (105, 112, 119))

        sx, sy = camera.world_to_screen(b.grid_x * tile_size, b.grid_y * tile_size)
        width = max(1, int(b.tiles_w * tile_size * camera.zoom))
        height = max(1, int(b.tiles_h * tile_size * camera.zoom))
        border = max(1, int(3 * camera.zoom))
        x_pad = max(2, int(width * 0.07))
        y_pad = max(2, int(height * 0.07))

        # Draw the platform as individually readable floor tiles so its 4x4
        # footprint remains clear beneath the counter and clerk's station.
        pygame.draw.rect(surface, (0, 0, 0, 75), (sx + 3, sy + 4, width, height), border_radius=5)
        cell_w = width / max(1, int(b.tiles_w))
        cell_h = height / max(1, int(b.tiles_h))
        for row in range(max(1, int(b.tiles_h))):
            for col in range(max(1, int(b.tiles_w))):
                tile_rect = pygame.Rect(
                    sx + round(col * cell_w), sy + round(row * cell_h),
                    max(1, round((col + 1) * cell_w) - round(col * cell_w)),
                    max(1, round((row + 1) * cell_h) - round(row * cell_h)),
                )
                tile_color = platform_light if (row + col) % 2 == 0 else platform_dark
                pygame.draw.rect(surface, tile_color, tile_rect)
        # Restore subtle tile seams after the base fill; these expose the true
        # tile count even where the station does not cover the platform.
        seam_color = style.get("tile_seam", platform)
        for col in range(1, max(1, int(b.tiles_w))):
            px = sx + round(col * cell_w)
            pygame.draw.line(surface, seam_color, (px, sy + y_pad), (px, sy + height - y_pad), border)
        for row in range(1, max(1, int(b.tiles_h))):
            py = sy + round(row * cell_h)
            pygame.draw.line(surface, seam_color, (sx + x_pad, py), (sx + width - x_pad, py), border)
        pygame.draw.rect(surface, platform, (sx, sy, width, height), width=border, border_radius=5)
        pygame.draw.rect(surface, wood_dark, (sx, sy, width, height), width=border, border_radius=5)

        # Clerk's backboard and royal cloth identify it as a civic workplace.
        board = pygame.Rect(sx + x_pad, sy + y_pad, width - x_pad * 2, max(1, int(height * 0.27)))
        pygame.draw.rect(surface, wood, board, border_radius=4)
        pygame.draw.rect(surface, wood_dark, board, width=border, border_radius=4)
        banner_w = max(1, int(board.width * 0.40))
        banner_h = max(1, int(board.height * 0.78))
        banner = pygame.Rect(board.centerx - banner_w // 2, board.y + max(1, int(board.height * 0.12)), banner_w, banner_h)
        pygame.draw.rect(surface, royal_cloth, banner, border_radius=2)
        pygame.draw.line(surface, gold, (banner.centerx, banner.y + int(banner.height * 0.12)),
                         (banner.centerx, banner.y + int(banner.height * 0.75)), max(1, int(2 * camera.zoom)))
        pygame.draw.circle(surface, gold, (banner.centerx, banner.centery), max(1, int(min(banner.width, banner.height) * 0.12)))

        # Broad clerk's counter, book, quill and coin scale.
        counter = pygame.Rect(sx + x_pad, sy + int(height * 0.50), width - x_pad * 2, max(1, int(height * 0.30)))
        pygame.draw.rect(surface, wood_dark, (counter.x + 2, counter.y + 3, counter.width, counter.height), border_radius=3)
        pygame.draw.rect(surface, wood, counter, border_radius=3)
        pygame.draw.rect(surface, wood_light, (counter.x, counter.y, counter.width, max(1, int(counter.height * 0.22))), border_radius=3)
        pygame.draw.rect(surface, wood_dark, counter, width=border, border_radius=3)
        pygame.draw.line(surface, wood_dark, (counter.x, counter.centery), (counter.right, counter.centery), max(1, int(camera.zoom)))

        book = pygame.Rect(counter.x + int(counter.width * 0.18), counter.y + int(counter.height * 0.24),
                           max(1, int(counter.width * 0.22)), max(1, int(counter.height * 0.48)))
        pygame.draw.rect(surface, parchment, book, border_radius=2)
        pygame.draw.line(surface, wood_dark, book.midtop, book.midbottom, max(1, int(camera.zoom)))
        for line in (0.35, 0.53, 0.71):
            yy = book.y + int(book.height * line)
            pygame.draw.line(surface, wood, (book.x + 2, yy), (book.right - 2, yy), max(1, int(camera.zoom)))
        quill_start = (book.right + max(2, int(counter.width * 0.035)), book.bottom - 1)
        quill_end = (quill_start[0] + max(3, int(counter.width * 0.08)), book.y)
        pygame.draw.line(surface, parchment, quill_start, quill_end, max(1, int(2 * camera.zoom)))

        scale_x = counter.x + int(counter.width * 0.72)
        scale_y = counter.y + int(counter.height * 0.48)
        beam = max(3, int(counter.width * 0.09))
        pygame.draw.line(surface, metal, (scale_x, scale_y - beam), (scale_x, scale_y + beam), max(1, int(2 * camera.zoom)))
        pygame.draw.line(surface, gold, (scale_x - beam, scale_y - beam), (scale_x + beam, scale_y - beam), max(1, int(2 * camera.zoom)))
        pan = max(2, int(beam * 0.35))
        pygame.draw.circle(surface, gold, (scale_x - beam, scale_y + max(1, int(beam * 0.4))), pan)
        pygame.draw.circle(surface, gold, (scale_x + beam, scale_y + max(1, int(beam * 0.4))), pan)

        # Small readable sign remains visible at normal zoom.
        if camera.zoom >= 0.55:
            sign = self.font.render("TAX OFFICE", True, parchment)
            surface.blit(sign, (board.centerx - sign.get_width() // 2,
                                board.y + board.height - sign.get_height() - max(1, int(camera.zoom * 2))))
