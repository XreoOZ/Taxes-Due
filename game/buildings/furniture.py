"""
Furniture System (Household Storages, Chests, Beds, Move & Drop Mechanics)
"""

import math
import random
import pygame
from game.config import FURNITURE_TYPES, TILE_SIZE, FURNITURE_CLAIM_BED_SEARCH_RADIUS
from game.data.config import FURNITURE_DAILY_BREAK_CHANCE
from game.render_cache import alpha_fill_surface
from game.ui.ui_theme import ui_font, upx

class Furniture:
    def __init__(self, furniture_id, furniture_type, gx, gy, permit_id=None, family_id=None, assigned_villager_id=None, rotation=0):
        self.id = furniture_id
        self.furniture_type = furniture_type
        self.type_cfg = FURNITURE_TYPES.get(furniture_type, FURNITURE_TYPES.get("household_storage", {}))
        self.grid_x = int(gx)
        self.grid_y = int(gy)
        self.permit_id = permit_id
        self.family_id = family_id
        self.assigned_villager_id = assigned_villager_id  # For beds: 1 bed = 1 villager
        self.rotation = int(rotation) % 360
        self.inventory = {}  # For chests: {item_name: amount}
        self.is_dropped = False  # True when lot was deleted/revoked (becomes a droppable item on the ground)
        self.stored_in_id = None
        self.construction_order = None
        self.construction_progress = 0.0
        self.condition = 1.0
        self.designated_target = None  # (tgx, tgy, target_permit_id) when marked for move/reinstall
        self.carrier_id = None  # ID of villager or servant currently hauling this furniture
        self.is_selected = False
        self.font = None
        self.break_check_day = 1  # Day number for which break_check_hour is valid
        self.break_check_hour = random.uniform(0, 24)  # Random hour during day to check for break
        self.break_checked_today = False  # Prevent repeated rolls within the check window
        # Production workstation state (Woodsman Lodge / Miner Workstation)
        self.station_quota_daily = 0      # 0 = unlimited daily output quota
        self.station_quota_today = 0      # output deposited today (resets daily)
        self.station_quota_day = -1       # day_number the quota counter belongs to
        self.plant_tree_enabled = False   # Woodsman Lodge "Plant a Tree" toggle
        self.bound_mine_id = None         # Miner Workstation -> generated mine

    @property
    def name(self):
        return self.type_cfg.get("name", self.furniture_type.capitalize())

    @property
    def status(self):
        """Mengembalikan status formal furniture: MOVING | UNINSTALLED | INSTALLED"""
        if self.carrier_id is not None:
            return "MOVING"
        if self.stored_in_id is not None:
            return "STORED"
        if (self.construction_order and self.construction_order.get("order_type") == "REPAIR"
                and not self.is_dropped and self.permit_id is not None):
            return "INSTALLED"
        if self.construction_order and self.construction_order.get("status") != "COMPLETE":
            order_status = self.construction_order.get("status", "ORDERED")
            return {
                "AWAITING_PAYMENT": "AWAITING PAYMENT",
                "PAYMENT_REQUESTED": "PAYMENT REQUESTED",
                "LANDLORD_RETRIEVING": "RETRIEVING LANDLORD COINS",
                "PAYMENT_TRAVELING": "PAYMENT TRAVELING",
                "LANDLORD_PAYMENT_PENDING": "AWAITING PAYMENT",
                "PAID": "AWAITING MATERIALS",
            }.get(order_status, order_status)
        if self.is_dropped or (
                self.permit_id is None
                and not self.type_cfg.get("placement_anywhere")):
            return "UNINSTALLED"
        return "INSTALLED"

    @property
    def is_available_for_use(self):
        """Furniture works only after its construction order is complete and it is installed."""
        order = getattr(self, "construction_order", None)
        is_repair_order = bool(order and order.get("order_type") == "REPAIR"
                               and order.get("status") != "COMPLETE")
        if (self.furniture_type == "household_storage" and is_repair_order
                and not self.is_dropped and self.stored_in_id is None):
            return True
        return (
            not self.is_dropped
            and self.stored_in_id is None
            and self.status == "INSTALLED"
            and (not order or order.get("status") == "COMPLETE")
            and not self.is_broken
        )

    @property
    def is_broken(self):
        return float(getattr(self, "condition", 1.0)) <= 0.0

    @property
    def can_be_dropped(self):
        return bool(self.type_cfg.get("can_be_dropped", True))

    def designate_move(self, tgx, tgy, permit_id=None):
        """Menetapkan petak tujuan baru untuk memindahkan/memasang ulang furniture ini"""
        self.designated_target = (int(tgx), int(tgy), permit_id)
        self.carrier_id = None

    def cancel_move(self):
        """Membatalkan rencana pemindahan furniture"""
        self.designated_target = None
        self.carrier_id = None

    def _ensure_font(self):
        if self.font is None:
            self.font = ui_font(9, bold=True)

    @property
    def total_stored(self):
        return sum(self.inventory.values())

    def station_accepted_items(self):
        """Items a production workstation inventory accepts, or None if unrestricted."""
        cfg = self.type_cfg
        if cfg.get("station_inventory_items"):
            return set(cfg["station_inventory_items"])
        if cfg.get("station_inventory_mine_bound"):
            from game.world.natural_resources import (
                NaturalResourceManager, get_natural_resources,
            )
            nr = get_natural_resources()
            mine = next((m for m in nr.mines if m.get("id") == self.bound_mine_id), None)
            if mine is None:
                return set()
            return {NaturalResourceManager.mine_output_item(mine)}
        return None

    def store_item(self, item_name, amount):
        if amount <= 0:
            return 0
        accepted = self.station_accepted_items()
        if accepted is not None and item_name not in accepted:
            return 0
        if self.furniture_type == "lord_treasury_chest":
            from game.systems.economy.currency import canonical_denomination
            denomination = canonical_denomination(item_name)
            if not denomination:
                return 0
            item_name = denomination
        current = self.inventory.get(item_name, 0)
        self.inventory[item_name] = current + amount
        return amount

    def take_item(self, item_name, amount):
        if self.furniture_type == "lord_treasury_chest":
            from game.systems.economy.currency import canonical_denomination
            item_name = canonical_denomination(item_name)
            if not item_name:
                return 0
        if item_name not in self.inventory:
            return 0
        avail = self.inventory[item_name]
        taken = min(avail, amount)
        self.inventory[item_name] -= taken
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        return taken

    def get_world_pos(self, tile_size=TILE_SIZE):
        return (self.grid_x + 0.5) * tile_size, (self.grid_y + 0.5) * tile_size

    def get_approach_point(self, worker_x, worker_y, worker_id=None, all_entities=None, tile_size=TILE_SIZE, bm=None, excluded_points=None):
        """Mendapatkan titik pendekatan bebas rintangan di sekeliling furniture untuk multi-worker concurrency"""
        gx, gy = self.grid_x, self.grid_y
        width, height = self.footprint_dimensions
        cardinals = ([(gx + dx, gy - 1) for dx in range(width)]
                     + [(gx + dx, gy + height) for dx in range(width)]
                     + [(gx - 1, gy + dy) for dy in range(height)]
                     + [(gx + width, gy + dy) for dy in range(height)])
        valid_points = []
        for cgx, cgy in cardinals:
            if bm:
                b = bm.get_building_at(cgx, cgy)
                if b and (getattr(b, "is_solid", False) or not getattr(b, "door_pos", None)):
                    continue
            valid_points.append(((cgx + 0.5) * tile_size, (cgy + 0.5) * tile_size))
        if not valid_points:
            return self.get_world_pos(tile_size)

        occupied = set()
        if all_entities:
            nearby_entities = (
                all_entities.for_tiles(cardinals)
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

        free_points = [pt for pt in valid_points if (int(pt[0] // tile_size), int(pt[1] // tile_size)) not in occupied]
        candidates = free_points if free_points else valid_points
        excluded_points = {tuple(point) for point in (excluded_points or ())}
        if excluded_points:
            candidates = [point for point in candidates if tuple(point) not in excluded_points]
            if not candidates:
                return None
        candidates.sort(key=lambda pt: math.hypot(pt[0] - worker_x, pt[1] - worker_y))
        if bm:
            reachable = []
            for point in candidates:
                route = bm.find_path((worker_x, worker_y), point, tile_size)
                if not route:
                    continue
                route_length = math.dist((worker_x, worker_y), route[0])
                route_length += sum(math.dist(route[index - 1], route[index])
                                    for index in range(1, len(route)))
                reachable.append((route_length, point))
            if reachable:
                reachable.sort(key=lambda entry: entry[0])
                return reachable[0][1]
        return candidates[0]

    @property
    def footprint_dimensions(self):
        width = max(1, int(self.type_cfg.get("width_tiles", 1)))
        height = max(1, int(self.type_cfg.get("height_tiles", 1)))
        return (height, width) if self.rotation % 180 else (width, height)

    def drop_to_ground(self, stockpile_manager=None):
        """Ketika Lot dihapus, furniture beralih ke status UNINSTALLED tanpa menghilangkan kepemilikan maupun isi inventarisnya"""
        if not self.can_be_dropped:
            return False
        self.permit_id = None
        self.is_dropped = True
        self.stored_in_id = None
        self.designated_target = None
        self.carrier_id = None
        # Catatan: Isi chest dan ID pemilik TETAP UTUH di dalam furniture (tidak tercecer/hilang)
        # Menunggu dipindahkan (Move) atau dihancurkan (Destroy)
        return True

    def move_to(self, new_gx, new_gy, new_permit_id=None, new_family_id=None):
        """Memindahkan furniture ke petak baru dengan tetap mempertahankan identitas dan isi barangnya"""
        self.grid_x = int(new_gx)
        self.grid_y = int(new_gy)
        if new_permit_id is not None:
            self.permit_id = new_permit_id
        if new_family_id is not None:
            self.family_id = new_family_id
        self.is_dropped = False
        self.stored_in_id = None
        self.designated_target = None
        self.carrier_id = None

    def destroy(self, stockpile_manager=None, resources=None):
        """Menghancurkan furniture: keluarkan seluruh isi chest ke tanah dan kembalikan sebagian kayu"""
        dump_types = ("household_storage", "lord_treasury_chest",
                      "woodsman_lodge", "miner_workstation")
        if self.furniture_type in dump_types and stockpile_manager:
            for item_name, count in list(self.inventory.items()):
                if count > 0:
                    owner_type = "villager" if self.family_id and self.furniture_type != "lord_treasury_chest" else "landlord"
                    owner_id = self.family_id if self.family_id else None
                    stockpile_manager.drop_resource(
                        item_name, count, self.grid_x, self.grid_y,
                        owner_type=owner_type, owner_id=owner_id
                    )
            self.inventory.clear()

        if resources is not None and isinstance(resources, dict):
            cost_w = self.type_cfg.get("materials", {}).get("Wood", 0)
            refund_w = max(1, cost_w // 2)
            resources["Wood"] = resources.get("Wood", 0) + refund_w

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        sx, sy = camera.world_to_screen(self.grid_x * tile_size, self.grid_y * tile_size)
        scaled_t = int(tile_size * camera.zoom)
        footprint_w, footprint_h = self.footprint_dimensions
        scaled_w, scaled_h = scaled_t * footprint_w, scaled_t * footprint_h
        if scaled_t < 10:
            return
        if not camera.is_world_rect_visible(
                self.grid_x * tile_size, self.grid_y * tile_size,
                footprint_w * tile_size, footprint_h * tile_size):
            return

        # -------------------------------------------------------------
        # 1. PENDING MOVE BLUEPRINT GHOST AT DESTINATION TILE (RIMWORLD STYLE)
        # -------------------------------------------------------------
        if self.designated_target:
            tgx, tgy, _ = self.designated_target
            tsx, tsy = camera.world_to_screen(tgx * tile_size, tgy * tile_size)
            # Translucent blueprint box
            bp_surf = alpha_fill_surface(scaled_w, scaled_h, (56, 189, 248, 70))
            surface.blit(bp_surf, (tsx, tsy))
            pygame.draw.rect(surface, (56, 189, 248), (tsx, tsy, scaled_w, scaled_h), width=2, border_radius=4)
            bp_txt = self.font.render("REINSTALL", True, (255, 255, 255))
            surface.blit(bp_txt, (tsx + (scaled_t - bp_txt.get_width()) // 2, tsy + 3))

            # Directional connecting path line from current position to target destination
            if not self.carrier_id:
                start_pt = (sx + scaled_t // 2, sy + scaled_t // 2)
                end_pt = (tsx + scaled_t // 2, tsy + scaled_t // 2)
                pygame.draw.line(surface, (56, 189, 248), start_pt, end_pt, 2)

        # Jika furniture sedang dipanggul/dibawa oleh villager/servant, jangan gambar fisik di tanah
        if self.carrier_id or self.stored_in_id is not None:
            return

        # Selection Highlight Glow
        if self.is_selected:
            pygame.draw.rect(surface, (255, 255, 255), (sx - 2, sy - 2, scaled_w + 4, scaled_h + 4), width=2, border_radius=5)
            pygame.draw.rect(surface, (56, 189, 248), (sx - 4, sy - 4, scaled_w + 8, scaled_h + 8), width=1, border_radius=6)

        if self.construction_order and self.construction_order.get("status") != "COMPLETE":
            shade_color = (234, 179, 8, 90) if self.construction_order.get("status") == "AWAITING_PAYMENT" else (56, 189, 248, 100)
            shade = alpha_fill_surface(scaled_w, scaled_h, shade_color)
            surface.blit(shade, (sx, sy))
            pygame.draw.rect(surface, (250, 204, 21), (sx, sy, scaled_w, scaled_h), width=2, border_radius=4)
            is_repair = self.construction_order.get("order_type") == "REPAIR"
            label_text = "REPAIR" if is_repair else (
                "BUILD" if self.construction_order.get("status") == "BUILDING" else
                "PAY" if "PAYMENT" in self.construction_order.get("status", "") or self.construction_order.get("status") == "AWAITING_PAYMENT" else "MATERIAL")
            label = self.font.render(label_text, True, (255, 255, 255))
            surface.blit(label, (sx + (scaled_t - label.get_width()) // 2, sy + 3))
            if self.construction_order.get("status") == "BUILDING":
                progress = max(0.0, min(1.0, float(self.construction_order.get("progress_ratio", 0.0))))
                margin = max(2, int(4 * camera.zoom))
                bar_h = max(3, int(5 * camera.zoom))
                bar = pygame.Rect(sx + margin, sy + scaled_h - bar_h - margin,
                                  max(1, scaled_w - margin * 2), bar_h)
                pygame.draw.rect(surface, (15, 23, 42), bar, border_radius=2)
                fill = bar.copy()
                fill.width = int(bar.width * progress)
                if fill.width > 0:
                    pygame.draw.rect(surface, (34, 197, 94), fill, border_radius=2)
            return

        # -------------------------------------------------------------
        # Storage furniture
        # -------------------------------------------------------------
        if self.furniture_type in ("household_storage", "lord_treasury_chest"):
            margin = max(4, int(10 * camera.zoom))
            cw = scaled_t - (margin * 2)
            ch = max(14, int(scaled_t * 0.55))
            cx = sx + margin
            cy = sy + scaled_t - ch - margin // 2

            # Shadow
            shadow_rect = pygame.Rect(cx + 2, cy + 3, cw, ch)
            pygame.draw.rect(surface, (0, 0, 0, 80), shadow_rect, border_radius=4)

            # Chest Body
            chest_rect = pygame.Rect(cx, cy, cw, ch)
            body_col = self.type_cfg.get("color_body", (139, 90, 43))
            lid_col = self.type_cfg.get("color_lid", (160, 105, 55))
            clasp_col = self.type_cfg.get("color_clasp", (234, 179, 8))

            pygame.draw.rect(surface, body_col, chest_rect, border_radius=4)
            pygame.draw.rect(surface, (70, 40, 15), chest_rect, width=1, border_radius=4)

            # Chest Lid
            lid_h = max(4, ch // 3)
            lid_rect = pygame.Rect(cx, cy, cw, lid_h)
            pygame.draw.rect(surface, lid_col, lid_rect, border_radius=3)
            pygame.draw.rect(surface, (70, 40, 15), lid_rect, width=1, border_radius=3)

            # Bronze Clasp & Lock
            clasp_w = max(3, int(6 * camera.zoom))
            clasp_h = max(4, int(8 * camera.zoom))
            clasp_rect = pygame.Rect(cx + (cw - clasp_w) // 2, cy + lid_h - 2, clasp_w, clasp_h)
            pygame.draw.rect(surface, clasp_col, clasp_rect, border_radius=2)

            if self.furniture_type == "lord_treasury_chest":
                trim = self.type_cfg.get("color_trim", (203, 213, 225))
                band_w = max(2, int(4 * camera.zoom))
                for band_x in (cx + cw // 4, cx + (cw * 3) // 4):
                    pygame.draw.rect(surface, trim, (band_x, cy, band_w, ch), border_radius=1)
                crown_w = max(7, int(cw * 0.34))
                crown_h = max(5, int(ch * 0.24))
                crown = pygame.Rect(cx + (cw - crown_w) // 2, cy - crown_h // 2,
                                    crown_w, crown_h)
                pygame.draw.rect(surface, clasp_col, crown, border_radius=2)
                pygame.draw.rect(surface, (65, 48, 22), crown, width=1, border_radius=2)

            # Stored Inventory Badge
            if self.total_stored > 0:
                inv_str = f"x{self.inventory.get('Potato', 0)}" if "Potato" in self.inventory and len(self.inventory) == 1 else f"x{self.total_stored}"
                txt = self.font.render(inv_str, True, (255, 255, 255))
                bw = txt.get_width() + 8
                bh = txt.get_height() + 4
                bx = cx + (cw - bw) // 2
                by = cy - bh - 2
                pygame.draw.rect(surface, (15, 23, 42, 220), (bx, by, bw, bh), border_radius=4)
                surface.blit(txt, (bx + 4, by + 2))

        # -------------------------------------------------------------
        # TIPE 2: BED (TEMPAT TIDUR INDIVIDUAL)
        # -------------------------------------------------------------
        elif self.furniture_type == "bed":
            bw = int(scaled_t * (0.86 if self.rotation % 180 else 0.72))
            bh = int(scaled_t * (0.72 if self.rotation % 180 else 0.86))
            bx = sx + (scaled_t - bw) // 2
            by = sy + (scaled_t - bh) // 2

            # Shadow
            pygame.draw.rect(surface, (0, 0, 0, 70), (bx + 2, by + 3, bw, bh), border_radius=4)

            # Wooden Bed Frame
            frame_col = self.type_cfg.get("color_frame", (120, 75, 30))
            pygame.draw.rect(surface, frame_col, (bx, by, bw, bh), border_radius=4)
            pygame.draw.rect(surface, (60, 35, 10), (bx, by, bw, bh), width=1, border_radius=4)

            # Mattress / Linen Sheet (Cream/White)
            mattress_rect = pygame.Rect(bx + 3, by + 4, bw - 6, bh - 8)
            pygame.draw.rect(surface, (245, 240, 225), mattress_rect, border_radius=3)

            # Soft Pillow at Head of Bed
            pw = max(8, int(bw * 0.65))
            ph = max(5, int(bh * 0.22))
            px = bx + (bw - pw) // 2
            py = by + 6
            pygame.draw.rect(surface, (255, 255, 255), (px, py, pw, ph), border_radius=3)
            pygame.draw.rect(surface, (203, 213, 225), (px, py, pw, ph), width=1, border_radius=3)

            # Blanket / Quilt covering lower 60% of bed
            blanket_h = int(bh * 0.58)
            blanket_y = by + bh - blanket_h - 4
            blanket_col = self.type_cfg.get("color_blanket", (59, 130, 246))
            blanket_rect = pygame.Rect(bx + 3, blanket_y, bw - 6, blanket_h)
            pygame.draw.rect(surface, blanket_col, blanket_rect, border_radius=3)
            pygame.draw.rect(surface, (29, 78, 216), blanket_rect, width=1, border_radius=3)

            # Folded blanket trim
            pygame.draw.line(surface, (147, 197, 253), (bx + 4, blanket_y + 1), (bx + bw - 4, blanket_y + 1), 2)

            # Bed Owner Badge
            if self.assigned_villager_id:
                badge_txt = self.font.render(f"Bed: {self.assigned_villager_id}", True, (255, 255, 255))
                bb_w = badge_txt.get_width() + 6
                bb_h = badge_txt.get_height() + 2
                bb_x = bx + (bw - bb_w) // 2
                bb_y = by - bb_h - 2
                pygame.draw.rect(surface, (15, 23, 42, 210), (bb_x, bb_y, bb_w, bb_h), border_radius=3)
                surface.blit(badge_txt, (bb_x + 3, bb_y + 1))

        elif self.furniture_type == "builder_workbench":
            inset = max(2, int(scaled_t * 0.09))
            top_h = max(6, int(scaled_t * 0.24))
            if self.rotation % 180:
                table = pygame.Rect(sx + int(scaled_t * 0.35), sy + inset,
                                    max(6, int(scaled_t * 0.24)), scaled_h - inset * 2)
            else:
                table = pygame.Rect(sx + inset, sy + int(scaled_t * 0.35), scaled_w - inset * 2, top_h)
            wood = self.type_cfg.get("color_frame", (112, 72, 38))
            top = self.type_cfg.get("color_top", (170, 119, 70))
            iron = self.type_cfg.get("color_iron", (82, 91, 101))
            pygame.draw.rect(surface, wood, table.move(0, max(1, int(2 * camera.zoom))), border_radius=2)
            pygame.draw.rect(surface, top, table, border_radius=2)
            pygame.draw.rect(surface, (75, 48, 27), table, width=1, border_radius=2)
            leg_w, leg_h = max(2, int(scaled_t * 0.07)), max(3, int(scaled_t * 0.25))
            if self.rotation % 180:
                for ly in (table.top + leg_h, table.bottom - leg_h * 2):
                    pygame.draw.rect(surface, wood, (table.right - 1, ly, leg_h, leg_w))
            else:
                for lx in (table.left + leg_w, table.right - leg_w * 2):
                    pygame.draw.rect(surface, wood, (lx, table.bottom - 1, leg_w, leg_h))
            vise = pygame.Rect(table.left + int(table.width * 0.15), table.top - max(2, int(scaled_t * 0.07)), max(4, int(scaled_t * 0.24)), max(2, int(scaled_t * 0.08)))
            pygame.draw.rect(surface, iron, vise, border_radius=1)
            swing = math.sin(pygame.time.get_ticks() / 150.0) if getattr(self, "assigned_workers", []) else 0.0
            tool_end = (table.centerx + max(3, int(scaled_t * (0.12 + swing * 0.025))),
                        table.top - max(2, int(scaled_t * (0.10 + abs(swing) * 0.025))))
            pygame.draw.line(surface, iron, (table.centerx, table.top + 1), tool_end, max(1, int(camera.zoom * 2)))

        elif self.furniture_type == "toolmaker_workbench":
            # Smithy: stone forge base, anvil, quench trough, tool rack.
            inset = max(3, int(scaled_t * 0.08))
            pad = pygame.Rect(sx + inset, sy + inset,
                              max(4, scaled_w - inset * 2), max(4, scaled_h - inset * 2))
            u = max(4, int(min(pad.width, pad.height) * 0.16))
            frame = self.type_cfg.get("color_frame", (70, 55, 38))
            top = self.type_cfg.get("color_top", (112, 85, 48))
            iron = self.type_cfg.get("color_iron", (100, 116, 139))
            anvil_col = self.type_cfg.get("color_anvil", (71, 85, 105))
            pygame.draw.rect(surface, (0, 0, 0, 60), pad.move(2, 3), border_radius=6)
            pygame.draw.rect(surface, frame, pad, border_radius=6)
            pygame.draw.rect(surface, top, pad.inflate(-u // 2, -u // 2), border_radius=4)
            # Forge mouth (left): dark opening with ember glow
            forge_x = pad.left + u
            forge_y = pad.top + pad.height * 0.45
            forge_r = pygame.Rect(forge_x, forge_y, u * 1.6, u * 1.5)
            pygame.draw.rect(surface, (40, 30, 24), forge_r, border_radius=3)
            pygame.draw.rect(surface, (220, 90, 30),
                             (forge_r.left + u // 4, forge_r.bottom - u // 2, u, u // 3), border_radius=2)
            pygame.draw.circle(surface, (255, 200, 80), forge_r.center, max(2, u // 6))
            # Anvil (center): base + body + horn
            ax = pad.centerx + u // 2
            ay = pad.bottom - u * 1.1
            pygame.draw.rect(surface, anvil_col, (ax - u // 2, ay, u, u // 3), border_radius=2)
            pygame.draw.rect(surface, anvil_col, (ax - u // 3, ay - u // 3, int(u * 0.75), u // 3), border_radius=2)
            pygame.draw.polygon(surface, anvil_col,
                                [(ax + int(u * 0.42), ay - u // 3), (ax + int(u * 0.85), ay - u // 5),
                                 (ax + int(u * 0.42), ay - u // 6)])
            pygame.draw.rect(surface, (40, 48, 60), (ax - u // 3, ay - u // 3, int(u * 0.75), u // 8), border_radius=1)
            # Quench trough (right): barrel with water glint
            qx = pad.right - u * 1.9
            qy = pad.bottom - u * 1.2
            pygame.draw.rect(surface, (88, 58, 32), (qx, qy, u * 0.9, u * 1.1), border_radius=3)
            pygame.draw.rect(surface, (56, 189, 248), (qx + 2, qy + 2, u * 0.9 - 4, u * 0.3), border_radius=2)
            # Tool rack (top-right): hanging pick silhouettes
            rx = pad.right - u * 1.1
            ry = pad.top + u // 2
            pygame.draw.line(surface, iron, (rx - u // 4, ry), (rx + u, ry), max(1, u // 8))
            for i in range(3):
                tx = rx + i * u * 0.32
                pygame.draw.line(surface, (120, 80, 50), (tx, ry), (tx, ry + u * 0.45), max(1, u // 10))
                pygame.draw.rect(surface, iron, (tx - u // 12, ry + u * 0.45, u // 6, u // 5), border_radius=1)

        elif self.furniture_type == "confession_box":
            frame = self.type_cfg.get("color_frame", (92, 57, 34))
            panel = self.type_cfg.get("color_panel", (122, 75, 42))
            cloth = self.type_cfg.get("color_cloth", (112, 35, 42))
            trim = self.type_cfg.get("color_trim", (190, 151, 83))
            inset = max(2, int(scaled_t * 0.12))
            body = pygame.Rect(sx + inset, sy + int(scaled_t * 0.12),
                               max(4, scaled_w - inset * 2), int(scaled_t * 0.76))
            pygame.draw.rect(surface, (30, 20, 15), body.move(1, max(1, int(2 * camera.zoom))), border_radius=3)
            pygame.draw.rect(surface, frame, body, border_radius=3)
            pygame.draw.rect(surface, panel, body.inflate(-max(2, inset // 2), -max(2, inset // 2)), border_radius=2)
            if self.rotation % 180:
                opening = pygame.Rect(body.left + max(2, int(body.width * 0.12)),
                                      body.centery - max(2, int(body.height * 0.16)),
                                      max(5, int(body.width * 0.58)), max(4, int(body.height * 0.32)))
            else:
                opening = pygame.Rect(body.centerx - max(2, int(body.width * 0.16)),
                                      body.top + max(2, int(body.height * 0.12)),
                                      max(4, int(body.width * 0.32)), max(5, int(body.height * 0.58)))
            pygame.draw.rect(surface, (32, 24, 20), opening, border_radius=max(1, int(camera.zoom * 2)))
            curtain_w = max(2, opening.width // 3)
            pygame.draw.rect(surface, cloth, (opening.left, opening.top, curtain_w, opening.height))
            pygame.draw.rect(surface, cloth, (opening.right - curtain_w, opening.top, curtain_w, opening.height))
            pygame.draw.line(surface, trim, (body.left + 2, body.bottom - 2),
                             (body.right - 2, body.bottom - 2), max(1, int(camera.zoom * 2)))
            cross_x = body.centerx
            cross_y = body.top - max(1, int(camera.zoom * 2))
            pygame.draw.line(surface, trim, (cross_x, cross_y), (cross_x, cross_y + max(3, int(scaled_t * 0.12))), max(1, int(camera.zoom * 2)))
            pygame.draw.line(surface, trim, (cross_x - max(2, int(scaled_t * 0.06)), cross_y + max(2, int(scaled_t * 0.04))),
                             (cross_x + max(2, int(scaled_t * 0.06)), cross_y + max(2, int(scaled_t * 0.04))), max(1, int(camera.zoom * 2)))

        elif self.furniture_type == "notice_board":
            # Public signboard: two posts + wide plank with pinned notices.
            frame = self.type_cfg.get("color_frame", (101, 67, 33))
            panel = self.type_cfg.get("color_panel", (146, 96, 48))
            paper = self.type_cfg.get("color_paper", (241, 245, 249))
            pin = self.type_cfg.get("color_pin", (220, 38, 38))
            post_w = max(2, int(scaled_t * 0.09))
            post_h = int(scaled_h * 0.92)
            post_y = sy + scaled_h - post_h
            pygame.draw.rect(surface, frame, (sx + scaled_w * 0.14, post_y, post_w, post_h), border_radius=1)
            pygame.draw.rect(surface, frame, (sx + scaled_w * 0.86 - post_w, post_y, post_w, post_h), border_radius=1)
            board_rect = pygame.Rect(sx + scaled_w * 0.06, sy + scaled_h * 0.12,
                                     scaled_w * 0.88, scaled_h * 0.66)
            pygame.draw.rect(surface, (0, 0, 0, 70), board_rect.move(1, 2), border_radius=4)
            pygame.draw.rect(surface, frame, board_rect, border_radius=4)
            pygame.draw.rect(surface, panel, board_rect.inflate(-max(2, int(scaled_t * 0.08)),
                                                                -max(2, int(scaled_t * 0.08))), border_radius=3)
            # Pinned paper notices.
            note_cols = [(paper, pin), ((230, 230, 230), (30, 41, 59)), (paper, (34, 197, 94))]
            n_notes = 3
            nw = max(4, int(board_rect.width * 0.2))
            nh = max(4, int(board_rect.height * 0.55))
            for i, (nc, pc) in enumerate(note_cols[:n_notes]):
                nx = board_rect.centerx - (n_notes * (nw + 3)) / 2 + i * (nw + 3)
                ny = board_rect.centery - nh / 2 + (i % 2) * 2
                pygame.draw.rect(surface, nc, (nx, ny, nw, nh), border_radius=1)
                pygame.draw.circle(surface, pc, (nx + nw / 2, ny + 2), max(1, int(scaled_t * 0.04)))

        elif self.furniture_type in ("woodsman_lodge", "miner_workstation"):
            # Production station: footprint-sized work pad with stock badge.
            inset = max(3, int(scaled_t * 0.07))
            pad = pygame.Rect(sx + inset, sy + inset,
                              max(4, scaled_w - inset * 2), max(4, scaled_h - inset * 2))

            if self.furniture_type == "woodsman_lodge":
                # ===== Forest camp: clearing, canvas tents, campfire, log pile =====
                u = max(4, int(min(pad.width, pad.height) * 0.14))

                pygame.draw.rect(surface, (0, 0, 0, 70), pad.move(2, 3), border_radius=8)
                pygame.draw.rect(surface, (96, 74, 52), pad, border_radius=8)
                pygame.draw.rect(surface, (74, 56, 40), pad, width=max(1, u // 5), border_radius=8)
                inner = pad.inflate(-u, -u)
                pygame.draw.rect(surface, (104, 80, 56), inner, border_radius=6)

                def _tent(tx, ty, tw, th):
                    # guy ropes
                    for rx, ry in ((tx + tw // 2, ty + th - u // 3), (tx + tw // 5, ty + th - u // 4)):
                        pygame.draw.line(surface, (60, 45, 30), (rx, ry),
                                         (rx + (u if rx < pad.centerx else -u), pad.bottom - u // 2),
                                         max(1, u // 8))
                    pygame.draw.polygon(surface, (52, 38, 26),
                                        [(tx - u // 6, ty + th), (tx + tw // 2, ty - u // 3), (tx + tw + u // 6, ty + th)])
                    pygame.draw.polygon(surface, (216, 190, 142),
                                        [(tx, ty + th), (tx + tw // 2, ty), (tx + tw, ty + th)])
                    pygame.draw.polygon(surface, (172, 142, 98),
                                        [(tx + tw // 2 - tw // 7, ty + th), (tx + tw // 2, ty + th // 4),
                                         (tx + tw // 2 + tw // 7, ty + th)])
                    pygame.draw.line(surface, (140, 112, 76), (tx, ty + th), (tx + tw, ty + th), max(1, u // 6))

                # Big tent (left), small tent (top-right)
                _tent(pad.left + u, pad.top + u, int(pad.width * 0.52), int(pad.height * 0.62))
                _tent(pad.left + int(pad.width * 0.56), pad.top + u,
                      int(pad.width * 0.36), int(pad.height * 0.44))

                # Campfire (center-bottom): stone ring + logs + flame
                fx = pad.centerx + u // 2
                fy = pad.bottom - u * 1.6
                fr = u * 0.95
                for i in range(6):
                    a = i * math.pi / 3
                    pygame.draw.circle(surface, (110, 106, 100),
                                       (fx + int(math.cos(a) * fr), fy + int(math.sin(a) * fr * 0.55)),
                                       max(2, u // 5))
                pygame.draw.line(surface, (88, 58, 32), (fx - fr * 0.5, fy), (fx + fr * 0.5, fy + u // 4), max(2, u // 4))
                pygame.draw.line(surface, (88, 58, 32), (fx + fr * 0.5, fy), (fx - fr * 0.5, fy + u // 4), max(2, u // 4))
                pygame.draw.circle(surface, (220, 90, 30), (fx, fy - u // 5), max(3, u // 3))
                pygame.draw.circle(surface, (250, 180, 60), (fx, fy - u // 6), max(2, u // 5))
                pygame.draw.circle(surface, (255, 235, 160), (fx, fy - u // 8), max(1, u // 8))

                # Log pile (right of fire)
                lx = pad.right - u * 1.9
                ly = pad.bottom - u * 0.9
                for row in range(3):
                    for col in range(2 - (row % 2)):
                        rr = u * 0.22
                        pygame.draw.rect(surface, (96, 64, 36),
                                         (lx + col * u * 0.5 - row * u * 0.12,
                                          ly - row * u * 0.34, int(u * 0.52), int(rr * 1.7)),
                                         border_radius=max(1, int(rr * 0.5)))
                        pygame.draw.circle(surface, (176, 132, 82),
                                           (lx + col * u * 0.5 - row * u * 0.12 + int(u * 0.5),
                                            ly - row * u * 0.34 + int(rr * 0.85)), max(1, int(rr * 0.45)))

                # Supply crate beside the fire
                cwx, cwy = fx - u * 1.5, fy + u * 0.7
                cw = u * 0.9
                pygame.draw.rect(surface, (0, 0, 0, 60), (cwx + u // 8, cwy + u // 6, cw, cw), border_radius=2)
                pygame.draw.rect(surface, (126, 88, 48), (cwx, cwy, cw, cw), border_radius=2)
                pygame.draw.rect(surface, (150, 108, 62), (cwx, cwy, cw, cw), width=max(1, u // 8), border_radius=2)
                pygame.draw.line(surface, (96, 66, 36), (cwx, cwy), (cwx + cw, cwy + cw), max(1, u // 10))
                pygame.draw.line(surface, (96, 66, 36), (cwx + cw, cwy), (cwx, cwy + cw), max(1, u // 10))

            else:
                frame_col = self.type_cfg.get("color_frame", (100, 116, 139))
                panel_col = self.type_cfg.get("color_roof", (51, 65, 85))
                pygame.draw.rect(surface, (0, 0, 0, 70), pad.move(2, 3), border_radius=6)
                pygame.draw.rect(surface, frame_col, pad, border_radius=6)
                pygame.draw.rect(surface, panel_col,
                                 pad.inflate(-max(4, int(scaled_t * 0.18)),
                                             -max(4, int(scaled_t * 0.18))), border_radius=4)
                pygame.draw.rect(surface, frame_col, pad, width=2, border_radius=6)

                # Center emblem: pick head for the mine station.
                cx, cy = pad.center
                r = max(6, int(scaled_t * 0.22))
                pygame.draw.circle(surface, self.type_cfg.get("color_rock", (100, 116, 139)),
                                   (cx, cy), r)
                pygame.draw.circle(surface, (15, 23, 42), (cx, cy), r, max(1, int(camera.zoom * 2)))
                pick = self.font.render("P", True, (255, 255, 255))
                surface.blit(pick, (cx - pick.get_width() // 2, cy - pick.get_height() // 2))

            # Stock badge (unlimited, filtered workstation inventory).
            if self.total_stored > 0:
                stock_parts = [f"{amt}x {item}" for item, amt in sorted(self.inventory.items()) if amt > 0]
                inv_str = ", ".join(stock_parts) if stock_parts else f"x{self.total_stored}"
                txt = self.font.render(inv_str, True, (255, 255, 255))
                bw = txt.get_width() + 8
                bh = txt.get_height() + 4
                bx = sx + (scaled_w - bw) // 2
                by = sy - bh - 2
                pygame.draw.rect(surface, (15, 23, 42, 220), (bx, by, bw, bh), border_radius=4)
                surface.blit(txt, (bx + 4, by + 2))

        # -------------------------------------------------------------
        # DROPPED ITEM INDICATOR (Bila kehilangan Lot)
        # -------------------------------------------------------------
        if self.is_dropped:
            # Yellow dashed border & uninstalled package badge
            pygame.draw.rect(surface, (234, 179, 8), (sx + 2, sy + 2, scaled_t - 4, scaled_t - 4), width=2, border_radius=4)
            d_txt = self.font.render("UNINSTALLED", True, (234, 179, 8))
            surface.blit(d_txt, (sx + (scaled_t - d_txt.get_width()) // 2, sy + 3))


class FurnitureManager:
    def __init__(self):
        self.furnitures = []
        self.counter = 1
        self.permit_manager = None
        self.building_manager = None
        self.villager_manager = None
        self._dirty = True
        self._navigation_revision = 0
        self._cached_occupied = set()
        # *** ESTABLISHED — DO NOT REMOVE ***
        # PERF: precomputed sorted-tile signature of _cached_occupied so the
        # pathfinder can key its route cache in O(1) instead of re-sorting every
        # occupied tile on every find_path call (hundreds of tiles x every AI
        # repath = measurable frame cost at village scale — part of the
        # user-verified prayer-exit FPS fix). Recomputed automatically whenever
        # invalidate_cache() marks the occupancy dirty.
        self._occupied_signature = ()
        self._cached_rects_by_tile_size = {}
        self._storage_cache = {}
        self._bed_cache = {}

    def invalidate_cache(self):
        self._dirty = True
        self._navigation_revision += 1
        self._cached_rects_by_tile_size.clear()
        self._storage_cache.clear()
        self._bed_cache.clear()

    def daily_wear_update(self, days=1):
        """Schedule random break-check times for each furniture at midnight."""
        day_cycle_day = getattr(self.villager_manager, "current_day_number", 1) if self.villager_manager else 1
        for _ in range(max(0, int(days))):
            day_cycle_day += 1
            for furniture in self.furnitures:
                furniture.break_check_day = day_cycle_day
                furniture.break_check_hour = random.uniform(0, 24)
        return []

    def check_breaks_by_time(self, current_day, current_hour):
        """Check furniture breaks at their scheduled random time during the day."""
        from game.systems.work.builder_system import BuilderSystem

        newly_broken = []
        for furniture in self.furnitures:
            if furniture.break_check_day != current_day:
                continue
            if furniture.break_checked_today:
                continue
            if abs(current_hour - furniture.break_check_hour) > 0.25:  # Within ~15 min window
                continue
            furniture.break_checked_today = True  # Mark as checked so it only rolls once
            is_household_owned = (
                furniture.type_cfg.get("household_owned", True)
                and getattr(furniture, "family_id", None) is not None
            )
            is_public_maintainable = (
                furniture.type_cfg.get("public_structure")
                and furniture.type_cfg.get("maintainable", True)
            )
            order = getattr(furniture, "construction_order", None) or {}
            if not is_household_owned and not is_public_maintainable:
                continue
            if (furniture.is_dropped or furniture.stored_in_id is not None
                    or furniture.status != "INSTALLED"
                    or (order and order.get("status") != "COMPLETE")
                    or furniture.is_broken):
                continue
            if random.random() >= FURNITURE_DAILY_BREAK_CHANCE:
                continue
            furniture.condition = 0.0
            furniture.construction_progress = 0.0
            furniture.construction_order = BuilderSystem.create_repair_order(
                furniture, self.building_manager, self.villager_manager
            )
            if is_public_maintainable:
                furniture.construction_order.update({
                    "status": "LANDLORD_PAYMENT_PENDING",
                    "payer_type": "landlord",
                    "payer_id": "landlord",
                })
            newly_broken.append(furniture)
        if newly_broken:
            self.invalidate_cache()
        return newly_broken

    def set_managers(self, building_manager=None, permit_manager=None, villager_manager=None):
        changed = False
        if building_manager is not None:
            changed = changed or self.building_manager is not building_manager
            self.building_manager = building_manager
        if permit_manager is not None:
            changed = changed or self.permit_manager is not permit_manager
            self.permit_manager = permit_manager
        if villager_manager is not None:
            changed = changed or self.villager_manager is not villager_manager
            self.villager_manager = villager_manager
        if changed:
            self.invalidate_cache()

    def get_occupied_tiles(self, exclude_furniture_id=None, exclude_tile=None):
        """
        Mengembalikan set petak grid (gx, gy) yang ditempati oleh perabotan (Bed, Chest, dll)
        yang berstatus INSTALLED. Menggunakan caching untuk performa tinggi.
        """
        if self._dirty:
            self._cached_occupied = set()
            for f in getattr(self, "furnitures", []):
                if getattr(f, "status", "") == "INSTALLED" and not getattr(f, "is_dropped", False):
                    width, height = f.footprint_dimensions
                    for dx in range(width):
                        for dy in range(height):
                            self._cached_occupied.add((int(f.grid_x) + dx, int(f.grid_y) + dy))
            # Sorted once per furniture change; reused by every path cache key.
            self._occupied_signature = tuple(sorted(self._cached_occupied))
            self._dirty = False

        if not exclude_furniture_id and not exclude_tile:
            return self._cached_occupied

        occupied = set(self._cached_occupied)
        if exclude_furniture_id:
            for f in self.furnitures:
                if f.id == exclude_furniture_id:
                    width, height = f.footprint_dimensions
                    for dx in range(width):
                        for dy in range(height):
                            occupied.discard((int(f.grid_x) + dx, int(f.grid_y) + dy))
        if exclude_tile:
            occupied.discard(tuple(exclude_tile))
        return occupied

    def get_furniture_rects(self, tile_size=TILE_SIZE, exclude_furniture_id=None, exclude_tile=None):
        """
        Mengembalikan daftar pygame.Rect dari seluruh perabotan yang terpasang (Beds, Chests),
        digunakan oleh is_segment_clear agar rute tidak memotong menembus ranjang/perabotan lain.
        """
        cached = self._cached_rects_by_tile_size.get(tile_size)
        if cached is None:
            cached = []
            for furniture in getattr(self, "furnitures", []):
                if getattr(furniture, "status", "") != "INSTALLED" or getattr(furniture, "is_dropped", False):
                    continue
                width_tiles, height_tiles = furniture.footprint_dimensions
                rect = pygame.Rect(furniture.grid_x * tile_size, furniture.grid_y * tile_size,
                                   width_tiles * tile_size, height_tiles * tile_size)
                cached.append((furniture, rect, width_tiles, height_tiles))
            self._cached_rects_by_tile_size[tile_size] = cached

        excluded_tile = tuple(exclude_tile) if exclude_tile else None
        rects = []
        for furniture, rect, width_tiles, height_tiles in cached:
            if exclude_furniture_id and furniture.id == exclude_furniture_id:
                continue
            if excluded_tile and (
                furniture.grid_x <= excluded_tile[0] < furniture.grid_x + width_tiles
                and furniture.grid_y <= excluded_tile[1] < furniture.grid_y + height_tiles
            ):
                continue
            rects.append(rect)
        return rects

    def add_furniture(self, f_type, gx, gy, permit_manager, villager_manager, resources=None, building_manager=None, rotation=0):
        cfg = FURNITURE_TYPES.get(f_type, FURNITURE_TYPES.get("household_storage", {}))
        if cfg.get("unique") and any(
            f.furniture_type == f_type and not f.is_dropped for f in self.furnitures
        ):
            return None, f"{cfg.get('name', 'Furniture')} already exists."
        allowed_permits = cfg.get("allowed_permits")
        placement_permit = permit_manager.get_permit_at(gx, gy) if permit_manager else None
        if (allowed_permits and not cfg.get("placement_anywhere")
                and (not placement_permit or placement_permit.permit_type not in allowed_permits)):
            return None, f"{cfg.get('name', 'Furniture')} must be placed on an allowed permit."
        # Check existing furniture on this tile
        fw, fh = max(1, int(cfg.get("width_tiles", 1))), max(1, int(cfg.get("height_tiles", 1)))
        if int(rotation) % 180:
            fw, fh = fh, fw
        target_tiles = {(int(gx) + dx, int(gy) + dy) for dx in range(fw) for dy in range(fh)}
        bm_for_placement = building_manager or self.building_manager
        if bm_for_placement:
            # *** ESTABLISHED — DO NOT REGRESS ***
            # Furniture on a door tile seals the only entrance -> AI pathing
            # deadlocks inside the building (teleport loops). The permit check
            # below alone does NOT cover this because permits can overlap doors.
            for tx, ty in target_tiles:
                b_at = bm_for_placement.get_building_at(tx, ty)
                if b_at and getattr(b_at, "door_pos", None) == (tx, ty):
                    return None, f"{cfg.get('name', 'Furniture')} cannot be placed on a doorway."
        if cfg.get("placement_anywhere") and bm_for_placement and any(
            bm_for_placement.get_building_at(tx, ty) for tx, ty in target_tiles
        ):
            return None, f"{cfg.get('name', 'Furniture')} cannot overlap a structure."
        if allowed_permits and not cfg.get("placement_anywhere") and any(
            not (permit_manager and (tile_permit := permit_manager.get_permit_at(tx, ty))
                 and tile_permit.permit_type in allowed_permits)
            for tx, ty in target_tiles
        ):
            return None, f"{cfg.get('name', 'Furniture')} must fit inside an allowed permit."
        for f in self.furnitures:
            ow, oh = f.footprint_dimensions
            occupied = {(int(f.grid_x) + dx, int(f.grid_y) + dy) for dx in range(ow) for dy in range(oh)}
            if target_tiles & occupied and not f.is_dropped and f.stored_in_id is None:
                return None, "Tile already occupied by furniture!"

        # Identify permit and owner family
        p = permit_manager.get_permit_at(gx, gy) if permit_manager else None
        family_id = None
        p = placement_permit
        if cfg.get("household_owned", True) and p and villager_manager:
            for fam in villager_manager.families:
                if fam.assigned_permit_id == p.id:
                    family_id = fam.id
                    break

        bm = building_manager or getattr(self, "building_manager", None)
        vm = villager_manager or getattr(self, "villager_manager", None)
        pm = permit_manager or getattr(self, "permit_manager", None)

        if not family_id and bm and cfg.get("household_owned", True):
            b_at = bm.get_building_at(gx, gy)
            if b_at:
                # 1. Apakah bangunan ini sudah memiliki ranjang/perabotan milik keluarga tertentu?
                for other_f in self.furnitures:
                    if not other_f.is_dropped and getattr(other_f, "family_id", None):
                        if b_at.occupies_tile(other_f.grid_x, other_f.grid_y):
                            family_id = other_f.family_id
                            break
                # 2. Apakah bangunan ini bertumpang-tindih dengan permit keluarga?
                if not family_id and pm and vm:
                    for fam in vm.families:
                        if fam.assigned_permit_id:
                            hp = next((p_item for p_item in pm.permits if p_item.id == fam.assigned_permit_id), None)
                            if hp and hp.overlaps_building(b_at):
                                family_id = fam.id
                                break

        # 3. Cek kedekatan dengan ranjang keluarga terdekat dalam radius
        if not family_id and vm and cfg.get("household_owned", True):
            closest_bed_dist = float('inf')
            closest_fam = None
            for other_f in self.furnitures:
                if other_f.furniture_type == "bed" and not other_f.is_dropped and getattr(other_f, "family_id", None):
                    d = math.hypot(other_f.grid_x - gx, other_f.grid_y - gy)
                    if d <= FURNITURE_CLAIM_BED_SEARCH_RADIUS and d < closest_bed_dist:
                        closest_bed_dist = d
                        closest_fam = other_f.family_id
            if closest_fam:
                family_id = closest_fam
            elif len(vm.families) == 1:
                family_id = vm.families[0].id

        f_id = f"furn_{self.counter}"
        self.counter += 1
        f = Furniture(f_id, f_type, gx, gy, permit_id=p.id if p else None,
                      family_id=family_id, rotation=rotation)
        if f_type == "miner_workstation":
            from game.world.natural_resources import get_natural_resources
            mine = get_natural_resources().mine_for_footprint(target_tiles)
            if mine is None:
                return None, "Miner Workstation must be placed exactly on top of a generated mine."
            f.bound_mine_id = mine["id"]
        if cfg.get("instant_place"):
            f.construction_order = None
        else:
            from game.systems.work.builder_system import BuilderSystem
            f.construction_order = BuilderSystem.create_order(f, bm, vm)
        self.furnitures.append(f)
        self.invalidate_cache()
        from game.world.natural_resources import get_natural_resources
        get_natural_resources().occupy_tiles(target_tiles)

        owner_txt = f" (Owned by Family {family_id})" if family_id else ""
        item_name = cfg.get("name", "Furniture")
        if cfg.get("instant_place"):
            return f, f"{item_name} placed and ready to use{owner_txt}!"
        return f, f"{item_name} order submitted{owner_txt}!"

    @property
    def furniture(self):
        return self.furnitures

    def get_furniture_for_family(self, family_id):
        fam_str = str(family_id)
        return [f for f in self.furnitures if str(f.family_id) == fam_str and not f.is_dropped]

    def get_furniture_by_id(self, f_id):
        for f in self.furnitures:
            if f.id == f_id:
                return f
        return None

    @staticmethod
    def _furniture_tiles(furniture):
        width, height = furniture.footprint_dimensions
        return {(int(furniture.grid_x) + dx, int(furniture.grid_y) + dy)
                for dx in range(width)
                for dy in range(height)}

    def get_furniture_at(self, gx, gy):
        point = (int(gx), int(gy))
        return next((f for f in self.furnitures if not f.is_dropped and f.stored_in_id is None
                     and point in self._furniture_tiles(f)), None)

    def store_uninstalled_furniture(self, furniture_id):
        """Store an uninstalled furniture object without losing its type or contents."""
        item = self.get_furniture_by_id(furniture_id)
        if not item or not (item.is_dropped or item.status in ("UNINSTALLED", "MOVING")):
            return False, "Furniture is not available to store."
        storage_id = None
        if item.family_id is not None:
            chest = self.get_storage_for_family(item.family_id)
            if chest is not item:
                storage_id = getattr(chest, "id", None)
            if storage_id is None:
                vm = getattr(self, "villager_manager", None)
                pm = getattr(self, "permit_manager", None)
                family = vm.get_family_by_id(item.family_id) if vm else None
                household_permit = next((p for p in getattr(pm, "permits", []) if family and p.id == family.assigned_permit_id), None)
                if household_permit:
                    storage_id = f"permit:{household_permit.id}"
        else:
            town_chest = next((f for f in self.furnitures if f.furniture_type == "household_storage" and not f.is_dropped and not f.family_id and f.stored_in_id is None), None)
            storage_id = getattr(town_chest, "id", None) if town_chest is not item else None
        if storage_id is None:
            return False, "No storage owned by this household is available."
        # Blueprint/uninstalled items still occupy their tiles; dropped ground
        # items do not — only release suppression the furniture actually held.
        was_placed = not item.is_dropped
        item.stored_in_id = storage_id
        item.permit_id = None
        item.is_dropped = False
        item.designated_target = None
        item.carrier_id = None
        self.invalidate_cache()
        if was_placed:
            from game.world.natural_resources import get_natural_resources
            get_natural_resources().release_tiles(self._furniture_tiles(item))
        return True, f"{item.name} stored."

    def update_permit_ownership(self, permit_id, family_id):
        for f in self.furnitures:
            if f.permit_id == permit_id:
                f.family_id = family_id

    def handle_permit_deleted(self, permit_id, stockpile_manager=None):
        """Ketika Lot dihapus, semua furniture di atasnya berubah menjadi Droppable Item di dunia (tidak hilang diam-diam)"""
        for f in self.furnitures:
            if f.permit_id == permit_id:
                self.uninstall_furniture(f.id, stockpile_manager)

    def uninstall_furniture(self, furniture_id, stockpile_manager=None):
        furniture = self.get_furniture_by_id(furniture_id)
        was_placed = furniture is not None and not furniture.is_dropped and furniture.stored_in_id is None
        if not furniture or not furniture.drop_to_ground(stockpile_manager):
            return False
        villager_manager = getattr(self, "villager_manager", None)
        for worker_id in getattr(furniture, "assigned_workers", []):
            worker = next((v for v in villager_manager.get_all_villagers()
                           if str(v.id) == str(worker_id)), None) if villager_manager else None
            if worker and getattr(worker, "job", None) != "Unassigned":
                worker.set_job("Unassigned")
        furniture.assigned_workers = []
        self.invalidate_cache()
        if was_placed:
            from game.world.natural_resources import get_natural_resources
            get_natural_resources().release_tiles(self._furniture_tiles(furniture))
        return True

    def get_lord_treasury_chest(self):
        return next((f for f in self.furnitures
                     if f.furniture_type == "lord_treasury_chest"
                     and not f.is_dropped and f.stored_in_id is None), None)

    def ensure_lord_treasury_chest(self, permit_manager=None, villager_manager=None,
                                  building_manager=None, stockpile_manager=None,
                                  preferred_tile=None):
        """Create the free royal coffer once and migrate legacy landlord coin stacks."""
        chest = self.get_lord_treasury_chest()
        if chest:
            return chest

        from game.data.config import LORD_TREASURY_PLACEMENT_SEARCH_RADIUS, LORD_TREASURY_START_TILE
        pm = permit_manager or self.permit_manager
        vm = villager_manager or self.villager_manager
        bm = building_manager or self.building_manager
        origin = preferred_tile or LORD_TREASURY_START_TILE
        ox, oy = int(origin[0]), int(origin[1])
        candidates = sorted(
            ((ox + dx, oy + dy) for dx in range(-LORD_TREASURY_PLACEMENT_SEARCH_RADIUS,
                                                LORD_TREASURY_PLACEMENT_SEARCH_RADIUS + 1)
             for dy in range(-LORD_TREASURY_PLACEMENT_SEARCH_RADIUS,
                             LORD_TREASURY_PLACEMENT_SEARCH_RADIUS + 1)
             if abs(dx) + abs(dy) <= LORD_TREASURY_PLACEMENT_SEARCH_RADIUS),
            key=lambda tile: (abs(tile[0] - ox) + abs(tile[1] - oy), tile[1], tile[0]),
        )
        for gx, gy in candidates:
            if bm and bm.get_building_at(gx, gy):
                continue
            if self.get_furniture_at(gx, gy):
                continue
            chest, _ = self.add_furniture(
                "lord_treasury_chest", gx, gy, pm, vm, building_manager=bm,
            )
            if chest:
                self._move_legacy_landlord_coins_to_treasury(chest, stockpile_manager)
                return chest
        return None

    @staticmethod
    def _move_legacy_landlord_coins_to_treasury(chest, stockpile_manager):
        if not chest or not stockpile_manager:
            return
        from game.data.config import CURRENCY_DENOMINATIONS
        moved = False
        for stack in list(getattr(stockpile_manager, "stacks", [])):
            if (getattr(stack, "owner_type", "landlord") != "landlord"
                    or stack.resource_type not in CURRENCY_DENOMINATIONS):
                continue
            chest.store_item(stack.resource_type, stack.amount)
            stockpile_manager.stacks.remove(stack)
            moved = True
        if moved:
            stockpile_manager.mark_totals_dirty()

    def get_storage_for_family(self, family_id, building_manager=None, villager_manager=None, permit_manager=None):
        if family_id is None:
            return None
        fam_str = str(family_id)
        if not self._dirty and fam_str in self._storage_cache:
            st = self._storage_cache[fam_str]
            if getattr(st, "is_available_for_use", False):
                return st

        # 1. Pencocokan langsung family_id
        for f in self.furnitures:
            if f.furniture_type == "household_storage" and str(getattr(f, "family_id", "")) == fam_str and f.is_available_for_use:
                self._storage_cache[fam_str] = f
                return f

        bm = building_manager or getattr(self, "building_manager", None)
        vm = villager_manager or getattr(self, "villager_manager", None)
        pm = permit_manager or getattr(self, "permit_manager", None)

        # 2. Cek apakah keluarga memiliki ranjang yang terpasang di dunia
        family_beds = [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "family_id", "")) == fam_str and f.is_available_for_use]
        if not family_beds and vm:
            fam = vm.get_family_by_id(family_id)
            if fam:
                member_ids = {str(m.id) for m in fam.members}
                family_beds = [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "assigned_villager_id", "")) in member_ids and f.is_available_for_use]

        if family_beds:
            bed_pts = [(b.grid_x, b.grid_y) for b in family_beds]
            for f in self.furnitures:
                if f.furniture_type == "household_storage" and f.is_available_for_use:
                    if not getattr(f, "family_id", None):
                        near = any(math.hypot(f.grid_x - bx, f.grid_y - by) <= FURNITURE_CLAIM_BED_SEARCH_RADIUS for bx, by in bed_pts)
                        if near:
                            f.family_id = family_id
                            self.invalidate_cache()
                            self._storage_cache[fam_str] = f
                            return f

        # 3. Cek apakah ada peti tanpa pemilik di dalam petak izin lot keluarga
        if pm and vm:
            fam = vm.get_family_by_id(family_id)
            if fam and fam.assigned_permit_id:
                p = next((p for p in pm.permits if p.id == fam.assigned_permit_id), None)
                if p:
                    for f in self.furnitures:
                        if f.furniture_type == "household_storage" and f.is_available_for_use and not getattr(f, "family_id", None):
                            if p.contains_tile(f.grid_x, f.grid_y):
                                f.family_id = family_id
                                return f

        # 4. Jika hanya ada 1 keluarga di desa dan 1 peti tanpa pemilik
        if vm and len(vm.families) == 1:
            for f in self.furnitures:
                if f.furniture_type == "household_storage" and f.is_available_for_use and not getattr(f, "family_id", None):
                    f.family_id = family_id
                    return f

        return None

    def get_storage_at(self, gx, gy):
        for f in self.furnitures:
            if f.grid_x == gx and f.grid_y == gy and f.furniture_type == "household_storage" and f.is_available_for_use:
                return f
        return None

    def get_furniture_at(self, gx, gy):
        point = (int(gx), int(gy))
        return next((f for f in self.furnitures if not f.is_dropped and f.stored_in_id is None
                     and point in self._furniture_tiles(f)), None)

    def get_bed_for_villager(self, villager_id, family_id):
        """Mencari Bed yang menjadi hak individu. 1 Bed hanya untuk 1 individu."""
        if not villager_id:
            return None

        villager_key = str(villager_id)
        cached_bed = self._bed_cache.get(villager_key)
        if (cached_bed and cached_bed.is_available_for_use
                and str(getattr(cached_bed, "assigned_villager_id", "")) == villager_key):
            return cached_bed
        self._bed_cache.pop(villager_key, None)

        # 1. Cek apakah villager sudah terikat dengan satu Bed tertentu
        for f in self.furnitures:
            if f.furniture_type == "bed" and f.is_available_for_use and getattr(f, "assigned_villager_id", None) == villager_id:
                self._bed_cache[villager_key] = f
                return f

        # 2. Jika belum, cari Bed kosong milik keluarga yang belum diisi
        fam_str = str(family_id) if family_id is not None else None
        if fam_str:
            for f in self.furnitures:
                if f.furniture_type == "bed" and f.is_available_for_use and str(getattr(f, "family_id", "")) == fam_str:
                    if getattr(f, "assigned_villager_id", None) is None:
                        f.assigned_villager_id = villager_id
                        self._bed_cache[villager_key] = f
                        return f

        return None

    def get_beds_for_family(self, family_id):
        fam_str = str(family_id)
        return [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "family_id", "")) == fam_str and f.is_available_for_use]

    def release_bed_for_villager(self, villager_id):
        for f in self.furnitures:
            if f.furniture_type == "bed" and getattr(f, "assigned_villager_id", None) == villager_id:
                f.assigned_villager_id = None

    def move_furniture(self, furniture_id, new_gx, new_gy, permit_manager=None, villager_manager=None, building_manager=None):
        """Memindahkan furniture ke petak baru dengan mempertahankan seluruh data dan isi barangnya"""
        f = self.get_furniture_by_id(furniture_id)
        if not f:
            return False, "Furniture not found!"
        if not f.type_cfg.get("movable", True):
            return False, f"{f.name} cannot be moved!"

        # Check the complete configured footprint, while allowing overlap with the furniture's old cells.
        width, height = f.footprint_dimensions
        target_tiles = {(int(new_gx) + dx, int(new_gy) + dy)
                        for dx in range(width) for dy in range(height)}
        for other in self.furnitures:
            if (other.id != f.id and not other.is_dropped and other.stored_in_id is None
                    and target_tiles & self._furniture_tiles(other)):
                return False, "Target tile already occupied by furniture!"

        p = permit_manager.get_permit_at(new_gx, new_gy) if permit_manager else None
        allowed_permits = f.type_cfg.get("allowed_permits")
        if allowed_permits:
            for tx, ty in target_tiles:
                tile_permit = permit_manager.get_permit_at(tx, ty) if permit_manager else None
                if not tile_permit or tile_permit.permit_type not in allowed_permits:
                    return False, f"{f.name} must remain inside an allowed permit."
        vm = villager_manager or getattr(self, "villager_manager", None)
        bm = building_manager or getattr(self, "building_manager", None)

        new_fam_id = f.family_id
        if p and vm:
            for fam in vm.families:
                if fam.assigned_permit_id == p.id:
                    new_fam_id = fam.id
                    break

        if not new_fam_id and bm:
            b_at = bm.get_building_at(new_gx, new_gy)
            if b_at:
                for other_f in self.furnitures:
                    if other_f.id != f.id and not other_f.is_dropped and getattr(other_f, "family_id", None):
                        if b_at.occupies_tile(other_f.grid_x, other_f.grid_y):
                            new_fam_id = other_f.family_id
                            break

        was_placed = not f.is_dropped and f.stored_in_id is None
        old_tiles = self._furniture_tiles(f)
        f.move_to(new_gx, new_gy, new_permit_id=p.id if p else None, new_family_id=new_fam_id)
        self.invalidate_cache()
        from game.world.natural_resources import get_natural_resources
        nr = get_natural_resources()
        if was_placed:
            nr.release_tiles(old_tiles)
        nr.occupy_tiles(target_tiles)
        return True, "Furniture moved successfully!"

    def destroy_furniture(self, furniture_id, stockpile_manager=None, resources=None, villager_manager=None, servant_manager=None):
        """Menghancurkan furniture secara aman: seluruh isi chest tumpah ke tanah, material refund dicatat"""
        f = self.get_furniture_by_id(furniture_id)
        if not f:
            return False, "Furniture not found!"

        if villager_manager:
            for v in villager_manager.get_all_villagers():
                if getattr(v, "carrying_furniture", None) == f:
                    v.carrying_furniture = None
                    v.task = "IDLE"
        if servant_manager:
            for s in servant_manager.servants:
                if getattr(s, "carrying_furniture", None) == f:
                    s.carrying_furniture = None
                    s.state = "IDLE"

        order = getattr(f, "construction_order", None)
        if order and order.get("status") != "COMPLETE":
            from game.systems.work.builder_system import BuilderSystem
            BuilderSystem.refund_order_materials(order, f, self, stockpile_manager)

        f.destroy(stockpile_manager=stockpile_manager, resources=resources)
        was_placed = not f.is_dropped and f.stored_in_id is None
        if f in self.furnitures:
            self.furnitures.remove(f)
        self.invalidate_cache()
        if was_placed:
            from game.world.natural_resources import get_natural_resources
            get_natural_resources().release_tiles(self._furniture_tiles(f))
        return True, "Furniture destroyed successfully!"

    def draw(self, surface, camera, tile_size):
        for f in self.furnitures:
            f.draw(surface, camera, tile_size)
