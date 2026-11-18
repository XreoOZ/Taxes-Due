"""
Area Permit System (Free-form Landlord Zoning Deeds, Multi-drag & Arbitrary Connected Lots)
"""

import math
import pygame
from game.config import (
    PERMIT_TYPES,
    BUILDING_TYPES,
    CROP_TYPES,
    TILE_SIZE,
    DEFAULT_PLOT_MAX_WORKERS,
    COLOR_SOIL_DRY,
    COLOR_SOIL_WET,
    COLOR_WATER_SHEEN,
    COLOR_CROP_WITHERED,
    DEDICATED_JOBS
)

def is_connected_tiles(tiles):
    """Mengecek apakah kumpulan tile terhubung secara ortogonal (4-arah)"""
    if not tiles:
        return False
    if len(tiles) == 1:
        return True
    start = next(iter(tiles))
    visited = {start}
    queue = [start]
    while queue:
        cx, cy = queue.pop(0)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            neighbor = (cx + dx, cy + dy)
            if neighbor in tiles and neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return len(visited) == len(tiles)

def get_exterior_edges_for_tile(tile, tiles):
    """Mendapatkan daftar sisi luar (top, bottom, left, right) untuk tile tertentu"""
    gx, gy = tile
    edges = []
    if (gx, gy - 1) not in tiles:
        edges.append("top")
    if (gx, gy + 1) not in tiles:
        edges.append("bottom")
    if (gx - 1, gy) not in tiles:
        edges.append("left")
    if (gx + 1, gy) not in tiles:
        edges.append("right")
    return edges

class AreaPermit:
    def __init__(self, permit_id, name, permit_type, tiles_or_gx, gy=None, tw=None, th=None):
        self.id = permit_id
        self.name = name
        self.permit_type = permit_type
        self.crop = None  # None | "Potato" | etc.
        self.tile_crops = {}  # (gx, gy) -> {"crop": str, "growth_days": float, "watered_today": bool, "unwatered_days": int, "is_dead": bool}
        self.growth_days = 0.0  # Legacy / display aggregate
        self.watered_today = False
        self.assigned_workers = []  # List of villager IDs
        self.max_workers = DEFAULT_PLOT_MAX_WORKERS
        self.task_reservations = {}  # (gx, gy) -> {"worker_id": int/str, "task_type": str}

        if isinstance(tiles_or_gx, (set, list, tuple)):
            self.tiles = set(tiles_or_gx)
        else:
            gx = tiles_or_gx
            w = tw if tw is not None else 1
            h = th if th is not None else 1
            self.tiles = {(gx + c, gy + r) for c in range(w) for r in range(h)}

        self._recalculate_bounds()

    def set_crop(self, crop_name):
        """Menetapkan komoditas yang akan digarap petani pada petak ladang"""
        self.crop = crop_name
        self.growth_days = 0.0
        self.watered_today = False
        self.tile_crops.clear()

    def get_untilled_tiles(self):
        """Mendapatkan petak ladang yang belum dicangkul/ditanami benih"""
        if not self.crop or self.permit_type != "farm":
            return []
        untilled = []
        for t in sorted(self.tiles, key=lambda x: (x[1], x[0])):
            if t not in self.tile_crops or not self.tile_crops[t].get("crop"):
                untilled.append(t)
        return untilled

    def till_and_sow_tile(self, gx, gy):
        """Mencangkul dan menabur benih pada petak ladang menggunakan cangkul"""
        if not self.crop:
            return False
        self.tile_crops[(gx, gy)] = {
            "crop": self.crop,
            "growth_days": 0.0,
            "watered_today": False,
            "unwatered_days": 0,
            "is_dead": False
        }
        return True

    def ensure_tile_crops(self):
        """Memastikan semua tile ladang terdaftar di kamus tile_crops"""
        if self.crop and self.permit_type == "farm":
            for t in self.tiles:
                if t not in self.tile_crops:
                    self.tile_crops[t] = {
                        "crop": None,
                        "growth_days": 0.0,
                        "watered_today": False,
                        "unwatered_days": 0,
                        "is_dead": False
                    }

    def get_tile_crop(self, gx, gy):
        self.ensure_tile_crops()
        return self.tile_crops.get((gx, gy), None)

    def water_tile(self, gx, gy):
        self.ensure_tile_crops()
        if (gx, gy) in self.tile_crops:
            tc = self.tile_crops[(gx, gy)]
            if tc.get("crop") and not tc["is_dead"]:
                tc["watered_today"] = True
                tc["unwatered_days"] = 0
                return True
        return False

    def get_unwatered_tiles(self):
        self.ensure_tile_crops()
        unwatered = []
        for t, tc in self.tile_crops.items():
            if tc.get("crop") and not tc["is_dead"] and not tc["watered_today"]:
                unwatered.append(t)
        return unwatered

    def get_harvestable_tiles(self):
        self.ensure_tile_crops()
        ready = []
        crop_cfg = CROP_TYPES.get("potato", {})
        growth_target = crop_cfg.get("growth_days", 10.0)
        for t, tc in self.tile_crops.items():
            if tc.get("crop") and not tc["is_dead"] and tc["growth_days"] >= growth_target:
                ready.append(t)
        return ready

    def harvest_tile(self, gx, gy):
        self.ensure_tile_crops()
        if (gx, gy) in self.tile_crops:
            tc = self.tile_crops[(gx, gy)]
            if tc.get("crop") and not tc["is_dead"] and tc["growth_days"] >= 10.0:
                crop_key = str(tc.get("crop") or "potato").lower()
                crop_cfg = CROP_TYPES.get(crop_key, CROP_TYPES.get("potato", {}))
                yield_val = int(crop_cfg.get("yield_per_tile", crop_cfg.get("yield", 2)))
                # Reset tile to untilled state for next cultivation cycle
                tc["crop"] = None
                tc["growth_days"] = 0.0
                tc["watered_today"] = False
                tc["unwatered_days"] = 0
                return yield_val
        return 0

    def update_growth(self, day_dt):
        """Update pertumbuhan harian tanaman berbasis tile (hanya tumbuh jika disiram)"""
        self.ensure_tile_crops()
        crop_cfg = CROP_TYPES.get("potato", {})
        growth_target = crop_cfg.get("growth_days", 10.0)

        # Update per tile
        for tc in self.tile_crops.values():
            if tc["crop"] and not tc["is_dead"]:
                if tc["watered_today"]:
                    tc["growth_days"] = min(growth_target, tc["growth_days"] + day_dt)

        # Update aggregate display
        living = [tc["growth_days"] for tc in self.tile_crops.values() if not tc["is_dead"]]
        if living:
            self.growth_days = sum(living) / len(living)
        self.watered_today = any(tc["watered_today"] for tc in self.tile_crops.values())

    def is_tile_reserved(self, gx, gy, exclude_worker_id=None):
        """Mengecek apakah petak (gx, gy) sedang dipesan oleh worker lain"""
        if (gx, gy) in self.task_reservations:
            res = self.task_reservations[(gx, gy)]
            if exclude_worker_id is not None and str(res.get("worker_id")) == str(exclude_worker_id):
                return False
            return True
        return False

    def reserve_tile(self, gx, gy, worker_id, task_type):
        """Memesan petak pekerjaan secara eksklusif agar tidak dikerjakan worker lain"""
        if (gx, gy) in self.tiles:
            if self.is_tile_reserved(gx, gy, exclude_worker_id=worker_id):
                return False
            self.task_reservations[(gx, gy)] = {
                "worker_id": str(worker_id),
                "task_type": task_type
            }
            return True
        return False

    def release_tile_reservation(self, gx, gy, worker_id=None):
        """Melepas reservasi pada petak setelah pekerjaan selesai atau dibatalkan"""
        if (gx, gy) in self.task_reservations:
            if worker_id is None or str(self.task_reservations[(gx, gy)].get("worker_id")) == str(worker_id):
                del self.task_reservations[(gx, gy)]
                return True
        return False

    def release_worker_reservations(self, worker_id):
        """Melepas seluruh reservasi yang dimiliki oleh seorang worker"""
        wid_str = str(worker_id)
        to_del = [t for t, res in list(self.task_reservations.items()) if str(res.get("worker_id")) == wid_str]
        for t in to_del:
            del self.task_reservations[t]

    def get_available_untilled_tiles(self, worker_id=None):
        """Mendapatkan petak ladang yang belum dicangkul dan belum direservasi worker lain"""
        untilled = self.get_untilled_tiles()
        return [t for t in untilled if not self.is_tile_reserved(t[0], t[1], exclude_worker_id=worker_id)]

    def get_available_unwatered_tiles(self, worker_id=None):
        """Mendapatkan petak ladang yang belum disiram dan belum direservasi worker lain"""
        unwatered = self.get_unwatered_tiles()
        return [t for t in unwatered if not self.is_tile_reserved(t[0], t[1], exclude_worker_id=worker_id)]

    def get_available_harvestable_tiles(self, worker_id=None):
        """Mendapatkan petak ladang yang siap panen dan belum direservasi worker lain"""
        ready = self.get_harvestable_tiles()
        return [t for t in ready if not self.is_tile_reserved(t[0], t[1], exclude_worker_id=worker_id)]

    def can_resize(self, new_tiles, other_permits=None, building_manager=None, furniture_manager=None):
        """Memvalidasi apakah petak lot dapat diubah ukurannya"""
        new_tiles_set = set(new_tiles)
        if not new_tiles_set:
            return False, "Lot must contain at least 1 tile!"

        # 1. Cek tumpang tindih dengan lot lain
        if other_permits:
            for p in other_permits:
                if p.id != self.id and p.overlaps_tiles(new_tiles_set):
                    return False, f"Overlaps existing lot: {p.name}!"

        # 2. Cek apakah ada objek/bangunan yang tertinggal di luar batas baru jika area diperkecil
        removed_tiles = self.tiles - new_tiles_set
        if removed_tiles:
            if building_manager:
                for b in building_manager.buildings:
                    b_tiles = set(b.tiles) if hasattr(b, "tiles") else set()
                    if b_tiles & removed_tiles:
                        return False, f"Cannot shrink: Building '{b.name}' is on removed tiles!"
                for site in building_manager.construction_sites:
                    s_tiles = set(site.tiles) if hasattr(site, "tiles") else set()
                    if s_tiles & removed_tiles:
                        return False, "Cannot shrink: Construction site is on removed tiles!"

            if furniture_manager:
                furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture_list", []))
                for f in furn_list:
                    f_tile = getattr(f, "tile", None)
                    if f_tile and f_tile in removed_tiles:
                        return False, f"Cannot shrink: Furniture '{f.name}' is on removed tiles!"

        return True, "Valid resize"

    def resize(self, new_tiles):
        """Mengubah ukuran petak lot tanpa menghapus ID, kepemilikan, atau data yang ada"""
        new_tiles_set = set(new_tiles)
        removed_tiles = self.tiles - new_tiles_set
        added_tiles = new_tiles_set - self.tiles

        # Bersihkan tile_crops dan reservasi untuk tile yang dibuang
        for t in removed_tiles:
            if t in self.tile_crops:
                del self.tile_crops[t]
            if t in self.task_reservations:
                del self.task_reservations[t]

        # Inisialisasi tile_crops untuk tile baru yang ditambahkan
        for t in added_tiles:
            self.tile_crops[t] = {
                "crop": None,
                "growth_days": 0.0,
                "watered_today": False,
                "unwatered_days": 0,
                "is_dead": False
            }

        self.tiles = set(new_tiles)
        self._recalculate_bounds()
        return True

    def reset_daily_watering(self):
        """Dipanggil setiap fajar (Day transition)"""
        self.ensure_tile_crops()
        self.task_reservations.clear()  # Reset antrean reservasi tugas setiap fajar
        for tc in self.tile_crops.values():
            if tc.get("crop") and not tc.get("is_dead", False):
                if tc.get("watered_today", False):
                    tc["watered_today"] = False
                    tc["unwatered_days"] = 0
                else:
                    tc["unwatered_days"] = tc.get("unwatered_days", 0) + 1
                    # Jika telat disiram (1 hari terlewat tidak disiram), tanaman mati & menjadi tile kosong
                    if tc["unwatered_days"] >= 1:
                        tc["is_dead"] = True
                        tc["crop"] = None  # Menjadi tile kosong yang siap dicangkul & ditanami kembali
                        tc["growth_days"] = 0.0
                        tc["watered_today"] = False
        self.watered_today = False

    def is_ready_for_harvest(self):
        return len(self.get_harvestable_tiles()) > 0

    def _recalculate_bounds(self):
        if self.tiles:
            self.grid_x = min(x for x, y in self.tiles)
            self.grid_y = min(y for x, y in self.tiles)
            self.tiles_w = max(x for x, y in self.tiles) - self.grid_x + 1
            self.tiles_h = max(y for x, y in self.tiles) - self.grid_y + 1
        else:
            self.grid_x, self.grid_y, self.tiles_w, self.tiles_h = 0, 0, 0, 0

    def contains_tile(self, gx, gy):
        return (gx, gy) in self.tiles

    def contains_all_tiles(self, tiles):
        return set(tiles).issubset(self.tiles)

    def overlaps_tiles(self, tiles):
        return bool(self.tiles & set(tiles))

    def overlaps_rect(self, gx, gy, tw, th):
        rect_tiles = {(gx + c, gy + r) for c in range(tw) for r in range(th)}
        return self.overlaps_tiles(rect_tiles)

    def overlaps_building(self, building):
        if hasattr(building, "tiles"):
            return self.overlaps_tiles(building.tiles)
        return self.overlaps_rect(building.grid_x, building.grid_y, building.tiles_w, building.tiles_h)

class PermitManager:
    def __init__(self):
        self.permits = []
        self.font = None
        self.permit_counter = 1

        # Initial Starter Permits
        self.add_permit_rect("Starter Housing Lot", "housing", 2, 2, 6, 6)
        self.add_permit_rect("Starter Storage Lot", "storage", 2, -6, 5, 5)
        self.add_permit_rect("Starter Farm Lot", "farm", -6, -6, 6, 6)
        self.add_permit_rect("Landlord Private Grounds", "landlord_private", -10, 2, 8, 8)

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def add_permit(self, name, permit_type, tiles):
        permit_id = f"permit_{self.permit_counter}"
        self.permit_counter += 1
        p = AreaPermit(permit_id, name, permit_type, tiles)
        self.permits.append(p)
        return p

    def add_permit_rect(self, name, permit_type, gx, gy, tw, th):
        rect_tiles = {(gx + c, gy + r) for c in range(tw) for r in range(th)}
        return self.add_permit(name, permit_type, rect_tiles)

    def can_place_permit_tiles(self, new_tiles):
        """Validasi apakah set tile permit valid (terhubung & tidak menimpa permit lain)"""
        if not new_tiles:
            return False, "No tiles selected"
        if not is_connected_tiles(new_tiles):
            return False, "Tiles must be connected together"
        for p in self.permits:
            if p.overlaps_tiles(new_tiles):
                return False, f"Overlaps existing permit: {p.name}"
        return True, "Valid"

    def can_place_permit(self, gx, gy, tw, th):
        rect_tiles = {(gx + c, gy + r) for c in range(tw) for r in range(th)}
        valid, _ = self.can_place_permit_tiles(rect_tiles)
        return valid

    def find_matching_permit_for_tiles(self, req_type, building_tiles, building_manager, furniture_manager=None):
        """Mengecek apakah seluruh tile bangunan berada di dalam permit yang cocok dan tidak menabrak bangunan lain"""
        if not building_tiles:
            return None, "No tiles selected"
        if not is_connected_tiles(building_tiles):
            return None, "Building tiles must be connected together"

        # 1. Pastikan tidak menabrak bangunan yang sudah jadi
        for b in building_manager.buildings:
            if b.overlaps_tiles(building_tiles):
                return None, f"Overlaps existing building: {b.name}"

        # 2. Pastikan tidak menabrak lokasi konstruksi aktif
        for s in building_manager.construction_sites:
            if s.overlaps_tiles(building_tiles):
                return None, f"Overlaps construction site: {s.name}"

        # 3. Pastikan tidak menabrak perabotan / peti
        if furniture_manager:
            furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture_list", []))
            for f in furn_list:
                f_tile = getattr(f, "tile", None)
                if f_tile and f_tile in building_tiles:
                    return None, f"Overlaps furniture: {f.name}"

        # 4. Validasi batasan permit & status keterisian lot
        # A. Cek apakah menabrak zona pertanian (Farm Permit)
        for p in self.permits:
            if p.permit_type == "farm" and p.overlaps_tiles(building_tiles):
                return None, f"Cannot build structures on agricultural Farm Lot: {p.name}!"

        # B. Cek apakah menabrak lot yang SUDAH memiliki bangunan (Occupied Lot)
        for p in self.permits:
            if p.overlaps_tiles(building_tiles):
                existing_blds = [b for b in building_manager.buildings if p.overlaps_building(b)]
                existing_sites = [s for s in building_manager.construction_sites if p.overlaps_building(s)]
                if existing_blds:
                    return None, f"Cannot build: Lot '{p.name}' is already occupied by {existing_blds[0].name}!"
                if existing_sites:
                    return None, f"Cannot build: Lot '{p.name}' already has an active construction site!"

        # C. Validasi khusus Well: Tidak memerlukan permit, dapat dibangun di tanah terbuka atau dalam permit kosong
        if req_type == "well":
            for p in self.permits:
                if p.overlaps_tiles(building_tiles):
                    if p.contains_all_tiles(building_tiles):
                        return p, "Valid (Inside Empty Lot)"
                    else:
                        return None, f"Cannot straddle lot boundary of '{p.name}'!"
            return True, "Valid (No Permit Required for Well)"

        # D. Bangunan standar: Wajib berada sepenuhnya di dalam permit kosong yang sesuai
        if req_type in BUILDING_TYPES:
            allowed = BUILDING_TYPES[req_type].get("allowed_permits", ["housing", "storage", "landlord_private"])
        else:
            allowed = [req_type]
            if req_type == "housing":
                allowed.append("landlord_private")

        # Cari permit kosong yang mencakup SELURUH tile bangunan
        for p in self.permits:
            if p.permit_type in allowed and p.contains_all_tiles(building_tiles):
                return p, "Valid"

        return None, "Must be placed entirely inside an empty issued permit lot!"

    def find_matching_permit(self, template, gx, gy, building_manager, tw=None, th=None):
        req_type = template.get("required_permit") if isinstance(template, dict) else template
        width = tw if tw is not None else (template.get("tiles_w", 4) if isinstance(template, dict) else 4)
        height = th if th is not None else (template.get("tiles_h", 4) if isinstance(template, dict) else 4)
        rect_tiles = {(gx + c, gy + r) for c in range(width) for r in range(height)}
        p, _ = self.find_matching_permit_for_tiles(req_type, rect_tiles, building_manager)
        return p

    def find_matching_empty_permit(self, template, gx, gy, building_manager, tw=None, th=None):
        return self.find_matching_permit(template, gx, gy, building_manager, tw, th)

    def has_permit_type(self, req_type):
        """Mengecek apakah ada surat tanah / permit aktif untuk tipe ini"""
        if req_type == "well":
            return True  # Well tidak memerlukan Area Permit
        if req_type in BUILDING_TYPES:
            allowed = BUILDING_TYPES[req_type].get("allowed_permits", ["housing", "storage", "landlord_private"])
            return any(p.permit_type in allowed for p in self.permits)
        return any(
            (p.permit_type == req_type) or (req_type == "housing" and p.permit_type == "landlord_private")
            for p in self.permits
        )

    def get_permit_at(self, gx, gy):
        """Mencari permit yang mencakup tile (gx, gy)"""
        for p in reversed(self.permits):
            if p.contains_tile(gx, gy):
                return p
        return None

    def delete_permit(self, permit_id, building_manager, furniture_manager=None, stockpile_manager=None):
        """Menghapus surat tanah jika tidak ada bangunan atau konstruksi di atasnya"""
        for p in self.permits:
            if p.id == permit_id:
                empty_areas, _ = self.get_permits_status(building_manager)
                if p in empty_areas:
                    if furniture_manager:
                        furniture_manager.handle_permit_deleted(permit_id, stockpile_manager)
                    self.permits.remove(p)
                    return True, "Permit successfully deleted"
                return False, "Cannot delete permit: Area still occupied!"
        return False, "Permit not found"

    def assign_worker_to_permit(self, permit_id, villager_id):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if not p:
            return False, "Permit not found"
        if not hasattr(p, "assigned_workers"):
            p.assigned_workers = []
        if villager_id in p.assigned_workers:
            return False, "Worker already assigned"
        # Tidak ada batas maksimal - jika slot penuh, otomatis bertambah sesuai keinginan pemain
        if len(p.assigned_workers) >= getattr(p, "max_workers", 2):
            p.max_workers = len(p.assigned_workers) + 1
        p.assigned_workers.append(villager_id)
        return True, "Worker assigned"

    def unassign_worker_from_permit(self, permit_id, villager_id):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if p and hasattr(p, "assigned_workers") and villager_id in p.assigned_workers:
            p.assigned_workers.remove(villager_id)
            return True, "Worker removed"
        return False, "Worker not assigned to this permit"

    def change_max_workers(self, permit_id, delta, villager_manager=None):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if p:
            current_max = getattr(p, "max_workers", 2)
            # Bebas semau pemain, tanpa limit atas (hanya batas minimal 0)
            new_max = max(0, current_max + delta)
            p.max_workers = new_max
            if not hasattr(p, "assigned_workers"):
                p.assigned_workers = []
            while len(p.assigned_workers) > p.max_workers:
                p.assigned_workers.pop()

            # Jika kuota bertambah dan ada petani yang menganggur, otomatis tugaskan petani terdekat
            if delta > 0 and villager_manager and len(p.assigned_workers) < p.max_workers:
                all_vils = villager_manager.get_all_villagers()
                idle_farmers = [
                    v for v in all_vils
                    if v.job == "Farmer" and not any(v.id in getattr(other_p, "assigned_workers", []) for other_p in self.permits)
                ]
                if idle_farmers:
                    idle_farmers.sort(key=lambda v: math.hypot((p.grid_x + p.tiles_w / 2.0) * TILE_SIZE - v.x, (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE - v.y))
                    self.assign_worker_to_permit(p.id, idle_farmers[0].id)
            return True
        return False

    def auto_sort_workers(self, villager_manager, job_filter=None):
        """Auto-assigns closest available workers to workplace plots based on distance from home"""
        if not villager_manager:
            return 0
        all_villagers = villager_manager.get_all_villagers()

        jobs_to_process = [job_filter] if job_filter else list(DEDICATED_JOBS.keys())
        total_assigned_overall = 0

        for job_id in jobs_to_process:
            job_cfg = DEDICATED_JOBS.get(job_id)
            if not job_cfg:
                continue
            permit_type_needed = job_cfg.get("workplace_permit", "farm")
            workers = [v for v in all_villagers if v.job == job_id]
            work_permits = [p for p in self.permits if p.permit_type == permit_type_needed]

            if not work_permits or not workers:
                continue

            # Clear assignments for this job's workplace permits
            for p in work_permits:
                if not hasattr(p, "assigned_workers"):
                    p.assigned_workers = []
                p.assigned_workers.clear()

            # Calculate distance between worker's home (or current location) and workplace
            candidates = []
            for p in work_permits:
                p_cx = (p.grid_x + p.tiles_w / 2.0) * TILE_SIZE
                p_cy = (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE
                for w in workers:
                    # If worker's family has an assigned housing deed, use home center
                    home_p = next((hp for hp in self.permits if hp.id == getattr(w, "assigned_permit_id", None)), None)
                    if home_p:
                        w_x = (home_p.grid_x + home_p.tiles_w / 2.0) * TILE_SIZE
                        w_y = (home_p.grid_y + home_p.tiles_h / 2.0) * TILE_SIZE
                    else:
                        w_x, w_y = w.x, w.y
                    dist = math.hypot(w_x - p_cx, w_y - p_cy)
                    candidates.append((dist, w, p))

            # Sort by distance (closest home wins!)
            candidates.sort(key=lambda c: (c[0], c[1].id))
            assigned_workers_set = set()

            for dist, w, p in candidates:
                if w.id in assigned_workers_set:
                    continue
                if len(p.assigned_workers) < getattr(p, "max_workers", 2):
                    p.assigned_workers.append(w.id)
                    assigned_workers_set.add(w.id)
                    total_assigned_overall += 1

        return total_assigned_overall

    def get_permits_status(self, building_manager):
        """Mengelompokkan permit menjadi Occupied Building atau Empty Area"""
        empty_areas = []
        occupied_areas = []

        for p in self.permits:
            overlapping_buildings = [b for b in building_manager.buildings if p.overlaps_building(b)]
            overlapping_sites = [s for s in building_manager.construction_sites if p.overlaps_building(s)]
            overlapping_demos = [d for d in getattr(building_manager, "demolition_sites", []) if p.overlaps_building(d)]
            if overlapping_buildings or overlapping_sites or overlapping_demos:
                occupied_areas.append({"permit": p, "buildings": overlapping_buildings + overlapping_sites + overlapping_demos})
            else:
                empty_areas.append(p)

        return empty_areas, occupied_areas

    def draw(self, surface, camera, tile_size, building_manager):
        self._ensure_font()
        _, occupied_areas = self.get_permits_status(building_manager)
        occupied_map = {item["permit"].id: len(item["buildings"]) for item in occupied_areas}

        scaled_tile = int(tile_size * camera.zoom)

        for p in self.permits:
            type_cfg = PERMIT_TYPES.get(p.permit_type, PERMIT_TYPES["housing"])
            b_count = occupied_map.get(p.id, 0)
            color_fill = type_cfg["color"]
            border_col = type_cfg["border_color"]

            # 1. Gambar fill dan border untuk setiap tile permit yang saling menyambung
            for (gx, gy) in p.tiles:
                sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
                tile_surf = pygame.Surface((scaled_tile, scaled_tile), pygame.SRCALPHA)
                tile_surf.fill(color_fill)
                surface.blit(tile_surf, (sx, sy))

                # Jika zona pertanian (Farm Permit), gambar visual tanah gembur & tanaman per-tile
                if p.permit_type == "farm":
                    t_crop = p.get_tile_crop(gx, gy)
                    is_watered = t_crop and t_crop.get("watered_today", False)
                    is_dead = t_crop and t_crop.get("is_dead", False)
                    g_days = t_crop.get("growth_days", 0.0) if t_crop else 0.0

                    # Garis alur bajak tanah (Basah / Kering)
                    furrow_col = COLOR_SOIL_WET if is_watered else COLOR_SOIL_DRY
                    line_thick = max(1, int(3 * camera.zoom)) if is_watered else max(1, int(2 * camera.zoom))
                    for f_idx in (0.28, 0.58, 0.88):
                        fy = sy + int(scaled_tile * f_idx)
                        pygame.draw.line(surface, furrow_col, (sx + 2, fy), (sx + scaled_tile - 2, fy), line_thick)

                    # Efek kilau air / tetesan air jika petak sudah disiram hari ini
                    if is_watered:
                        sheen_r = max(1, int(2 * camera.zoom))
                        for sx_off, sy_off in [(0.35, 0.24), (0.68, 0.54), (0.42, 0.84)]:
                            sheen_px = sx + int(scaled_tile * sx_off)
                            sheen_py = sy + int(scaled_tile * sy_off)
                            pygame.draw.circle(surface, COLOR_WATER_SHEEN, (sheen_px, sheen_py), sheen_r)

                    # Tanaman jika sudah ditanam
                    if t_crop and t_crop.get("crop") == "Potato":
                        sprout_offsets = [(0.25, 0.28), (0.72, 0.30), (0.48, 0.58), (0.24, 0.86), (0.76, 0.86)]

                        if is_dead:
                            # Tanaman layu / mati mengering karena tidak disiram
                            dead_r = max(2, int(3 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, COLOR_CROP_WITHERED, (px, py), dead_r)
                                pygame.draw.line(surface, (80, 70, 50), (px - 2, py - 2), (px + 2, py + 2), 1)

                        # Tahap 1: Hari 0-1 (Benih dalam alur tanah)
                        elif g_days < 2.0:
                            seed_r = max(1, int(2 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (180, 140, 100), (px, py), seed_r)

                        # Tahap 2: Hari 2-3 (Tunas mulai muncul)
                        elif g_days < 4.0:
                            sprout_r = max(2, int(3 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (34, 197, 94), (px, py), sprout_r)
                                pygame.draw.circle(surface, (20, 83, 45), (px, py), sprout_r, 1)

                        # Tahap 3: Hari 4-9 (Tumbuh daun dan batang)
                        elif g_days < 10.0:
                            leaf_r = max(3, int(5 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (22, 163, 74), (px, py), leaf_r)
                                pygame.draw.circle(surface, (20, 83, 45), (px, py), leaf_r, 1)
                                pygame.draw.circle(surface, (134, 239, 172), (px - 1, py - 1), max(1, leaf_r // 2))

                        # Tahap 4: Hari 10+ (Siap Panen!)
                        else:
                            mature_r = max(4, int(7 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (21, 128, 61), (px, py), mature_r)
                                pygame.draw.circle(surface, (20, 83, 45), (px, py), mature_r, 1)
                                flower_r = max(2, int(3 * camera.zoom))
                                pygame.draw.circle(surface, (254, 240, 138), (px, py - 1), flower_r)
                                pygame.draw.circle(surface, (255, 255, 255), (px, py - 1), max(1, flower_r - 1))

                # Exterior border segments
                if (gx, gy - 1) not in p.tiles:
                    pygame.draw.line(surface, border_col, (sx, sy), (sx + scaled_tile, sy), 2)
                if (gx, gy + 1) not in p.tiles:
                    pygame.draw.line(surface, border_col, (sx, sy + scaled_tile), (sx + scaled_tile, sy + scaled_tile), 2)
                if (gx - 1, gy) not in p.tiles:
                    pygame.draw.line(surface, border_col, (sx, sy), (sx, sy + scaled_tile), 2)
                if (gx + 1, gy) not in p.tiles:
                    pygame.draw.line(surface, border_col, (sx + scaled_tile, sy), (sx + scaled_tile, sy + scaled_tile), 2)

            # 2. Render Label di tile paling kiri atas dari permit
            if p.tiles:
                min_tile = min(p.tiles, key=lambda t: (t[1], t[0]))
                bx, by = camera.world_to_screen(min_tile[0] * tile_size, min_tile[1] * tile_size)
                prefix = "👑 " if p.permit_type == "landlord_private" else ""
                status_suffix = f" ({b_count} Building{'s' if b_count > 1 else ''})" if b_count > 0 else " (Ready)"
                if p.permit_type == "farm":
                    w_count = len(getattr(p, "assigned_workers", []))
                    w_max = getattr(p, "max_workers", 2)
                    workers_info = f" ({w_count}/{w_max} Workers)"

                    if getattr(p, "crop", None):
                        g_days = getattr(p, "growth_days", 0.0)
                        if g_days >= 10.0:
                            stage_txt = "READY TO HARVEST!"
                        elif g_days >= 4.0:
                            stage_txt = f"Day {int(g_days)}/10 Leaves & Stems"
                        elif g_days >= 2.0:
                            stage_txt = f"Day {int(g_days)}/10 Sprouting"
                        else:
                            stage_txt = f"Day {int(g_days)}/10 Planted"
                        crop_lbl = f" | {p.crop} [{stage_txt}]"
                    else:
                        crop_lbl = " | Unplanted"
                    label_txt = f"{prefix}{p.name} [{len(p.tiles)} tiles Farm{crop_lbl}]{workers_info}{status_suffix}"
                else:
                    label_txt = f"{prefix}{p.name} [{len(p.tiles)} tiles {type_cfg['name']}]{status_suffix}"
                lbl = self.font.render(label_txt, True, (255, 255, 255))
                surface.blit(lbl, (bx + 8, by + 8))
