"""
Furniture System (Household Storages, Chests, Beds, Move & Drop Mechanics)
"""

import math
import pygame
from game.config import FURNITURE_TYPES, TILE_SIZE, FURNITURE_CLAIM_BED_SEARCH_RADIUS

class Furniture:
    def __init__(self, furniture_id, furniture_type, gx, gy, permit_id=None, family_id=None, assigned_villager_id=None):
        self.id = furniture_id
        self.furniture_type = furniture_type
        self.type_cfg = FURNITURE_TYPES.get(furniture_type, FURNITURE_TYPES.get("household_storage", {}))
        self.grid_x = int(gx)
        self.grid_y = int(gy)
        self.permit_id = permit_id
        self.family_id = family_id
        self.assigned_villager_id = assigned_villager_id  # For beds: 1 bed = 1 villager
        self.inventory = {}  # For chests: {item_name: amount}
        self.is_dropped = False  # True when lot was deleted/revoked (becomes a droppable item on the ground)
        self.condition = 1.0
        self.designated_target = None  # (tgx, tgy, target_permit_id) when marked for move/reinstall
        self.carrier_id = None  # ID of villager or servant currently hauling this furniture
        self.is_selected = False
        self.font = None

    @property
    def name(self):
        return self.type_cfg.get("name", self.furniture_type.capitalize())

    @property
    def status(self):
        """Mengembalikan status formal furniture: MOVING | UNINSTALLED | INSTALLED"""
        if self.carrier_id is not None:
            return "MOVING"
        if self.is_dropped or self.permit_id is None:
            return "UNINSTALLED"
        return "INSTALLED"

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
            self.font = pygame.font.SysFont("Segoe UI", 9, bold=True)

    @property
    def total_stored(self):
        return sum(self.inventory.values())

    def store_item(self, item_name, amount):
        if amount <= 0:
            return 0
        current = self.inventory.get(item_name, 0)
        self.inventory[item_name] = current + amount
        return amount

    def take_item(self, item_name, amount):
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

    def get_approach_point(self, worker_x, worker_y, worker_id=None, all_entities=None, tile_size=TILE_SIZE, bm=None):
        """Mendapatkan titik pendekatan bebas rintangan di sekeliling furniture untuk multi-worker concurrency"""
        gx, gy = self.grid_x, self.grid_y
        cardinals = [(gx, gy - 1), (gx, gy + 1), (gx - 1, gy), (gx + 1, gy)]
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
            for other in all_entities:
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
        candidates.sort(key=lambda pt: math.hypot(pt[0] - worker_x, pt[1] - worker_y))
        return candidates[0]

    def drop_to_ground(self, stockpile_manager=None):
        """Ketika Lot dihapus, furniture beralih ke status UNINSTALLED tanpa menghilangkan kepemilikan maupun isi inventarisnya"""
        self.permit_id = None
        self.is_dropped = True
        self.designated_target = None
        self.carrier_id = None
        # Catatan: Isi chest dan ID pemilik TETAP UTUH di dalam furniture (tidak tercecer/hilang)
        # Menunggu dipindahkan (Move) atau dihancurkan (Destroy)

    def move_to(self, new_gx, new_gy, new_permit_id=None, new_family_id=None):
        """Memindahkan furniture ke petak baru dengan tetap mempertahankan identitas dan isi barangnya"""
        self.grid_x = int(new_gx)
        self.grid_y = int(new_gy)
        if new_permit_id is not None:
            self.permit_id = new_permit_id
        if new_family_id is not None:
            self.family_id = new_family_id
        self.is_dropped = False
        self.designated_target = None
        self.carrier_id = None

    def destroy(self, stockpile_manager=None, resources=None):
        """Menghancurkan furniture: keluarkan seluruh isi chest ke tanah dan kembalikan sebagian kayu"""
        if self.furniture_type == "household_storage" and stockpile_manager:
            for item_name, count in list(self.inventory.items()):
                if count > 0:
                    owner_type = "villager" if self.family_id else "landlord"
                    owner_id = self.family_id if self.family_id else None
                    stockpile_manager.drop_resource(
                        item_name, count, self.grid_x, self.grid_y,
                        owner_type=owner_type, owner_id=owner_id
                    )
            self.inventory.clear()

        if resources is not None and isinstance(resources, dict):
            cost_w = self.type_cfg.get("cost_wood", 10)
            refund_w = max(1, cost_w // 2)
            resources["Wood"] = resources.get("Wood", 0) + refund_w

    def draw(self, surface, camera, tile_size):
        self._ensure_font()
        sx, sy = camera.world_to_screen(self.grid_x * tile_size, self.grid_y * tile_size)
        scaled_t = int(tile_size * camera.zoom)
        if scaled_t < 10:
            return

        # -------------------------------------------------------------
        # 1. PENDING MOVE BLUEPRINT GHOST AT DESTINATION TILE (RIMWORLD STYLE)
        # -------------------------------------------------------------
        if self.designated_target:
            tgx, tgy, _ = self.designated_target
            tsx, tsy = camera.world_to_screen(tgx * tile_size, tgy * tile_size)
            # Translucent blueprint box
            bp_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
            bp_surf.fill((56, 189, 248, 70))
            surface.blit(bp_surf, (tsx, tsy))
            pygame.draw.rect(surface, (56, 189, 248), (tsx, tsy, scaled_t, scaled_t), width=2, border_radius=4)
            bp_txt = self.font.render("REINSTALL", True, (255, 255, 255))
            surface.blit(bp_txt, (tsx + (scaled_t - bp_txt.get_width()) // 2, tsy + 3))

            # Directional connecting path line from current position to target destination
            if not self.carrier_id:
                start_pt = (sx + scaled_t // 2, sy + scaled_t // 2)
                end_pt = (tsx + scaled_t // 2, tsy + scaled_t // 2)
                pygame.draw.line(surface, (56, 189, 248), start_pt, end_pt, 2)

        # Jika furniture sedang dipanggul/dibawa oleh villager/servant, jangan gambar fisik di tanah
        if self.carrier_id:
            return

        # Selection Highlight Glow
        if self.is_selected:
            pygame.draw.rect(surface, (255, 255, 255), (sx - 2, sy - 2, scaled_t + 4, scaled_t + 4), width=2, border_radius=5)
            pygame.draw.rect(surface, (56, 189, 248), (sx - 4, sy - 4, scaled_t + 8, scaled_t + 8), width=1, border_radius=6)

        # -------------------------------------------------------------
        # TIPE 1: HOUSEHOLD STORAGE (CHEST)
        # -------------------------------------------------------------
        if self.furniture_type == "household_storage":
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
            bw = int(scaled_t * 0.72)
            bh = int(scaled_t * 0.86)
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
        self._cached_occupied = set()
        self._storage_cache = {}

    def invalidate_cache(self):
        self._dirty = True
        self._storage_cache.clear()

    def set_managers(self, building_manager=None, permit_manager=None, villager_manager=None):
        if building_manager is not None:
            self.building_manager = building_manager
        if permit_manager is not None:
            self.permit_manager = permit_manager
        if villager_manager is not None:
            self.villager_manager = villager_manager
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
                    self._cached_occupied.add((int(f.grid_x), int(f.grid_y)))
            self._dirty = False

        if not exclude_furniture_id and not exclude_tile:
            return self._cached_occupied

        occupied = set(self._cached_occupied)
        if exclude_furniture_id:
            for f in self.furnitures:
                if f.id == exclude_furniture_id:
                    occupied.discard((int(f.grid_x), int(f.grid_y)))
        if exclude_tile:
            occupied.discard(exclude_tile)
        return occupied

    def add_furniture(self, f_type, gx, gy, permit_manager, villager_manager, resources=None, building_manager=None):
        cfg = FURNITURE_TYPES.get(f_type, FURNITURE_TYPES.get("household_storage", {}))
        cost_w = cfg.get("cost_wood", 10)
        cost_s = cfg.get("cost_stone", 0)

        if resources:
            if resources.get("Wood", 0) < cost_w or resources.get("Stone", 0) < cost_s:
                return None, "Not enough materials!"

        # Check existing furniture on this tile
        for f in self.furnitures:
            if f.grid_x == gx and f.grid_y == gy and not f.is_dropped:
                return None, "Tile already occupied by furniture!"

        # Identify permit and owner family
        p = permit_manager.get_permit_at(gx, gy) if permit_manager else None
        family_id = None
        if p and villager_manager:
            for fam in villager_manager.families:
                if fam.assigned_permit_id == p.id:
                    family_id = fam.id
                    break

        bm = building_manager or getattr(self, "building_manager", None)
        vm = villager_manager or getattr(self, "villager_manager", None)
        pm = permit_manager or getattr(self, "permit_manager", None)

        if not family_id and bm:
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
        if not family_id and vm:
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
        f = Furniture(f_id, f_type, gx, gy, permit_id=p.id if p else None, family_id=family_id)
        self.furnitures.append(f)
        self.invalidate_cache()

        if resources:
            resources["Wood"] -= cost_w
            resources["Stone"] -= cost_s

        owner_txt = f" (Owned by Family {family_id})" if family_id else ""
        item_name = cfg.get("name", "Furniture")
        return f, f"{item_name} placed{owner_txt}!"

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

    def update_permit_ownership(self, permit_id, family_id):
        for f in self.furnitures:
            if f.permit_id == permit_id:
                f.family_id = family_id

    def handle_permit_deleted(self, permit_id, stockpile_manager=None):
        """Ketika Lot dihapus, semua furniture di atasnya berubah menjadi Droppable Item di dunia (tidak hilang diam-diam)"""
        for f in self.furnitures:
            if f.permit_id == permit_id:
                f.drop_to_ground(stockpile_manager)

    def get_storage_for_family(self, family_id, building_manager=None, villager_manager=None, permit_manager=None):
        if family_id is None:
            return None
        fam_str = str(family_id)
        if not self._dirty and fam_str in self._storage_cache:
            st = self._storage_cache[fam_str]
            if not getattr(st, "is_dropped", False):
                return st

        # 1. Pencocokan langsung family_id
        for f in self.furnitures:
            if f.furniture_type == "household_storage" and str(getattr(f, "family_id", "")) == fam_str and not f.is_dropped:
                self._storage_cache[fam_str] = f
                return f

        bm = building_manager or getattr(self, "building_manager", None)
        vm = villager_manager or getattr(self, "villager_manager", None)
        pm = permit_manager or getattr(self, "permit_manager", None)

        # 2. Cek apakah keluarga memiliki ranjang yang terpasang di dunia
        family_beds = [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "family_id", "")) == fam_str and not f.is_dropped]
        if not family_beds and vm:
            fam = vm.get_family_by_id(family_id)
            if fam:
                member_ids = {str(m.id) for m in fam.members}
                family_beds = [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "assigned_villager_id", "")) in member_ids and not f.is_dropped]

        if family_beds:
            bed_pts = [(b.grid_x, b.grid_y) for b in family_beds]
            for f in self.furnitures:
                if f.furniture_type == "household_storage" and not f.is_dropped:
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
                        if f.furniture_type == "household_storage" and not f.is_dropped and not getattr(f, "family_id", None):
                            if p.contains_tile(f.grid_x, f.grid_y):
                                f.family_id = family_id
                                return f

        # 4. Jika hanya ada 1 keluarga di desa dan 1 peti tanpa pemilik
        if vm and len(vm.families) == 1:
            for f in self.furnitures:
                if f.furniture_type == "household_storage" and not f.is_dropped and not getattr(f, "family_id", None):
                    f.family_id = family_id
                    return f

        return None

    def get_storage_at(self, gx, gy):
        for f in self.furnitures:
            if f.grid_x == gx and f.grid_y == gy and not f.is_dropped:
                return f
        return None

    def get_furniture_at(self, gx, gy):
        for f in self.furnitures:
            if f.grid_x == gx and f.grid_y == gy:
                return f
        return None

    def get_bed_for_villager(self, villager_id, family_id):
        """Mencari Bed yang menjadi hak individu. 1 Bed hanya untuk 1 individu."""
        if not villager_id:
            return None

        # 1. Cek apakah villager sudah terikat dengan satu Bed tertentu
        for f in self.furnitures:
            if f.furniture_type == "bed" and not f.is_dropped and getattr(f, "assigned_villager_id", None) == villager_id:
                return f

        # 2. Jika belum, cari Bed kosong milik keluarga yang belum diisi
        fam_str = str(family_id) if family_id is not None else None
        if fam_str:
            for f in self.furnitures:
                if f.furniture_type == "bed" and not f.is_dropped and str(getattr(f, "family_id", "")) == fam_str:
                    if getattr(f, "assigned_villager_id", None) is None:
                        f.assigned_villager_id = villager_id
                        return f

        return None

    def get_beds_for_family(self, family_id):
        fam_str = str(family_id)
        return [f for f in self.furnitures if f.furniture_type == "bed" and str(getattr(f, "family_id", "")) == fam_str and not f.is_dropped]

    def release_bed_for_villager(self, villager_id):
        for f in self.furnitures:
            if f.furniture_type == "bed" and getattr(f, "assigned_villager_id", None) == villager_id:
                f.assigned_villager_id = None

    def move_furniture(self, furniture_id, new_gx, new_gy, permit_manager=None, villager_manager=None, building_manager=None):
        """Memindahkan furniture ke petak baru dengan mempertahankan seluruh data dan isi barangnya"""
        f = self.get_furniture_by_id(furniture_id)
        if not f:
            return False, "Furniture not found!"

        # Cek apakah petak target sudah terisi
        for other in self.furnitures:
            if other.id != f.id and other.grid_x == new_gx and other.grid_y == new_gy and not other.is_dropped:
                return False, "Target tile already occupied by furniture!"

        p = permit_manager.get_permit_at(new_gx, new_gy) if permit_manager else None
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

        f.move_to(new_gx, new_gy, new_permit_id=p.id if p else None, new_family_id=new_fam_id)
        self.invalidate_cache()
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

        f.destroy(stockpile_manager=stockpile_manager, resources=resources)
        if f in self.furnitures:
            self.furnitures.remove(f)
        self.invalidate_cache()
        return True, "Furniture destroyed successfully!"

    def draw(self, surface, camera, tile_size):
        for f in self.furnitures:
            f.draw(surface, camera, tile_size)
