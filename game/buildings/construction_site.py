"""Construction site: a planned building under construction before it becomes a Building."""
import math
import pygame
from game.render_cache import alpha_fill_surface
from game.config import (
    TILE_SIZE,
    BUILDING_TYPES,
    BUILD_DURATION_SECONDS,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    DEFAULT_COMMISSION_ARTISAN_JOB,
)
from game.permits import get_exterior_edges_for_tile
from game.ui.ui_theme import ui_font, upx

class ConstructionSite:
    def __init__(self, building_type, tiles, door_pos=None, door_side=None, rotation=0):
        self.building_type = building_type
        self._rotation = int(rotation) % 360
        self.type_cfg = BUILDING_TYPES.get(building_type, BUILDING_TYPES["wooden_structure"])
        self.tiles = set(tiles)
        self._recalculate_bounds()
        self.name = f"{self.type_cfg['name']} ({len(self.tiles)} tiles)"
        self.construction_order = None
        if self.type_cfg.get("builder_commissionable"):
            self.construction_order = {
                "id": f"public:{building_type}:{self.grid_x}:{self.grid_y}",
                "order_type": "PUBLIC_BUILD",
                "building_type": building_type,
                "status": "AWAITING_PAYMENT",
                "payer_family_id": None,
                "payer_id": None,
                "builder_id": None,
                "artisan_job": DEFAULT_COMMISSION_ARTISAN_JOB,
                "commission_paid": False,
            }

        # Door Placement
        if self.type_cfg.get("has_door", True) is False or self.building_type in ("well", "market"):
            self.door_pos = None
            self.door_side = None
            self.is_solid = False
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
            self.font = ui_font(10, bold=True)

    @property
    def rotation(self):
        side_map = {"bottom": 0, "left": 1, "top": 2, "right": 3}
        return getattr(self, "_rotation", side_map.get(getattr(self, "door_side", "bottom"), 0) * 90) // 90

    def total_required(self):
        return sum(self.required_cost.values())

    def total_delivered(self):
        return sum(self.delivered_cost.values())

    def is_materials_complete(self):
        return all(self.delivered_cost[res] >= self.required_cost[res] for res in self.required_cost)

    def is_complete(self):
        duration = BUILD_DURATION_SECONDS
        order = getattr(self, "construction_order", None)
        if order and order.get("order_type") == "PUBLIC_BUILD":
            duration = max(1.0, float(order.get("build_duration_seconds", duration)))
        return self.build_progress >= duration

    def progress_fraction(self):
        duration = BUILD_DURATION_SECONDS
        order = getattr(self, "construction_order", None)
        if order and order.get("order_type") == "PUBLIC_BUILD":
            duration = max(1.0, float(order.get("build_duration_seconds", duration)))
        return min(1.0, self.build_progress / duration) if duration > 0 else 0.0

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

    # *** ESTABLISHED — DO NOT REGRESS ***
    # Reservation accounting contract: reserve_resource() returns the ACTUAL
    # amount reserved; callers MUST release exactly that amount via
    # release_resource() (never a fixed capacity) or reserved_cost leaks and
    # get_needed_resource() returns None forever -> blueprint stalls mid-build.
    # deposit_resource() only counts delivered material; it must NOT touch
    # reserved_cost (builders never reserve, servants release explicitly).
    def release_resource(self, res, amount):
        self.reserved_cost[res] = max(0, self.reserved_cost[res] - amount)

    def deposit_resource(self, res, amount):
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

    def draw(self, surface, camera, tile_size):
        if self.tiles and not camera.is_world_rect_visible(
                self.grid_x * tile_size, self.grid_y * tile_size,
                self.tiles_w * tile_size, self.tiles_h * tile_size):
            return
        self._ensure_font()
        scaled_tile = max(1, math.ceil(tile_size * camera.zoom))

        # 1. Blueprint Grid & Foundation per visible tile
        world_bounds = (
            self.grid_x * tile_size, self.grid_y * tile_size,
            (self.grid_x + self.tiles_w) * tile_size,
            (self.grid_y + self.tiles_h) * tile_size,
        )
        visible_tiles = list(camera.iter_visible_tiles(self.tiles, tile_size, world_bounds))
        order = getattr(self, "construction_order", None) or {}
        is_public_build = order.get("order_type") == "PUBLIC_BUILD"
        public_status = order.get("status")
        if public_status == "BUILDING":
            public_label = "BUILD"
        elif "PAYMENT" in str(public_status) or public_status in ("AWAITING_PAYMENT", "LANDLORD_RETRIEVING"):
            public_label = "PAY"
        else:
            public_label = "MATERIAL"
        public_color = (234, 179, 8) if public_status == "AWAITING_PAYMENT" else (56, 189, 248)
        public_shade_color = (234, 179, 8) if public_status == "AWAITING_PAYMENT" else (56, 189, 248)
        label_tile = min(
            self.tiles,
            key=lambda tile: math.hypot(tile[0] - (self.grid_x + self.tiles_w / 2),
                                        tile[1] - (self.grid_y + self.tiles_h / 2)),
        ) if self.tiles else None
        visible_label_tile = label_tile if label_tile in visible_tiles else (visible_tiles[0] if visible_tiles else None)
        if is_public_build and visible_tiles:
            # Match the full-footprint state overlay used by commissioned furniture.
            overlay = alpha_fill_surface(
                max(1, self.tiles_w * scaled_tile),
                max(1, self.tiles_h * scaled_tile),
                (*public_shade_color, 90 if public_status != "BUILDING" else 58),
            )
            overlay_x, overlay_y = camera.world_to_screen(self.grid_x * tile_size, self.grid_y * tile_size)
            surface.blit(overlay, (overlay_x, overlay_y))
        for (gx, gy) in visible_tiles:
            sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
            if not is_public_build:
                tile_surf = alpha_fill_surface(scaled_tile + 1, scaled_tile + 1, (30, 58, 138, 90))
                surface.blit(tile_surf, (sx, sy))

            # Blueprint grid borders
            border_color = (*public_color, 190) if is_public_build else (59, 130, 246, 120)
            pygame.draw.rect(surface, border_color, (sx, sy, scaled_tile + 1, scaled_tile + 1), width=1)

            # Exterior perimeter lines
            if (gx, gy - 1) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy), (sx + scaled_tile, sy), 2)
            if (gx, gy + 1) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)
            if (gx - 1, gy) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx, sy), (sx, sy + scaled_tile), 2)
            if (gx + 1, gy) not in self.tiles:
                pygame.draw.line(surface, (96, 165, 250), (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

            if is_public_build and (gx, gy) == visible_label_tile:
                state_text = self.font.render(public_label, True, (255, 255, 255))
                if scaled_tile < max(state_text.get_width() + 10, state_text.get_height() + 6):
                    continue
                label_bg = pygame.Rect(0, 0, state_text.get_width() + 10, state_text.get_height() + 6)
                label_bg.center = (sx + scaled_tile // 2, sy + scaled_tile // 2)
                pygame.draw.rect(surface, (15, 23, 42), label_bg, border_radius=4)
                pygame.draw.rect(surface, public_color, label_bg, width=1, border_radius=4)
                surface.blit(state_text, (label_bg.x + 5, label_bg.y + 3))

        if is_public_build and visible_tiles:
            pygame.draw.rect(
                surface, (250, 204, 21),
                (overlay_x, overlay_y, self.tiles_w * scaled_tile, self.tiles_h * scaled_tile),
                width=2, border_radius=4,
            )

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

        if is_public_build and public_status in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING",
                                                 "LANDLORD_RETRIEVING", "PAYMENT_TRAVELING"):
            lbl_txt = "Awaiting Builder commission"
        elif not self.is_materials_complete():
            pct = self.total_delivered() / max(1, self.total_required())
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                pygame.draw.rect(surface, (234, 179, 8), (bar_x, bar_y, fill_w, bar_h), border_radius=3)
            lbl_txt = ("Builder gathering materials" if is_public_build
                       else f"{self.name}: {self.total_delivered()}/{self.total_required()}")
        else:
            duration = BUILD_DURATION_SECONDS
            if is_public_build:
                duration = max(1.0, float(order.get("build_duration_seconds", duration)))
            pct = min(1.0, self.build_progress / duration)
            fill_w = int(bar_w * pct)
            if fill_w > 0:
                pygame.draw.rect(surface, (34, 197, 94), (bar_x, bar_y, fill_w, bar_h), border_radius=3)
            lbl_txt = f"{public_label}: {int(pct * 100)}%" if is_public_build else f"Building: {int(pct * 100)}%"

        txt_surf = self.font.render(lbl_txt, True, (255, 255, 255))
        surface.blit(txt_surf, (bar_x + (bar_w - txt_surf.get_width()) // 2, bar_y - 14))

