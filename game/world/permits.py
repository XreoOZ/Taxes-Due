"""
Area Permit System (Free-form Landlord Zoning Deeds, Multi-drag & Arbitrary Connected Lots)
"""
from game.ui.ui_theme import ui_font, upx

import math
import random
import pygame
from game.render_cache import alpha_fill_surface
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
    DEDICATED_JOBS,
    FARMING_BATCH_GROWTH_DAYS,
    FARMING_BATCH_WINDOW_DAYS
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

def permit_worker_cap(permit):
    """Worker slot cap for a permit; farm lots use a manually set max_workers."""
    return getattr(permit, "max_workers", 2)

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

class FarmingBatch:
    """
    Synchronized Farming Batch
    Ensures all crops planted in the same batch grow and become harvestable simultaneously.
    """
    def __init__(self, batch_id, permit_id, crop_name, start_day=1.0, window_duration_days=FARMING_BATCH_WINDOW_DAYS):
        self.id = str(batch_id)
        self.permit_id = str(permit_id)
        self.crop = crop_name
        self.start_day = float(start_day)
        self.window_duration_days = float(window_duration_days)
        self.close_day = self.start_day + self.window_duration_days
        self.closed = False
        self.tiles = set()  # set of (gx, gy)
        self.growth_days = 0.0
        self.watered_today = False
        self.unwatered_days = 0
        self.is_dead = False

    @property
    def is_harvestable(self):
        crop_cfg = CROP_TYPES.get(str(self.crop).lower(), CROP_TYPES.get("potato", {}))
        target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
        return self.growth_days >= target and len(self.tiles) > 0 and not self.is_dead

    @property
    def completion_day(self):
        crop_cfg = CROP_TYPES.get(str(self.crop).lower(), CROP_TYPES.get("potato", {}))
        target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
        return self.start_day + target

    def can_accept_planting(self, current_day=None):
        if self.closed:
            return False
        if current_day is not None and float(current_day) > self.close_day:
            return False
        return True

    def add_tile(self, gx, gy, current_day=None):
        if not self.can_accept_planting(current_day):
            return False
        self.tiles.add((gx, gy))
        return True

    def remove_tile(self, gx, gy):
        if (gx, gy) in self.tiles:
            self.tiles.remove((gx, gy))
            return True
        return False

    def close(self, current_day=None):
        self.closed = True
        if current_day is not None:
            self.close_day = float(current_day)

    def update_growth(self, current_day):
        if not self.tiles or self.is_dead:
            return
        crop_cfg = CROP_TYPES.get(str(self.crop).lower(), CROP_TYPES.get("potato", {}))
        target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
        self.growth_days = min(target, max(0.0, float(current_day) - self.start_day))

    def to_dict(self):
        return {
            "id": self.id,
            "permit_id": self.permit_id,
            "crop": self.crop,
            "start_day": self.start_day,
            "window_duration_days": self.window_duration_days,
            "close_day": self.close_day,
            "completion_day": self.completion_day,
            "closed": self.closed,
            "tiles": [[gx, gy] for gx, gy in sorted(self.tiles)],
            "growth_days": self.growth_days,
            "watered_today": self.watered_today,
            "unwatered_days": self.unwatered_days,
            "is_dead": self.is_dead
        }

    @classmethod
    def from_dict(cls, d):
        batch = cls(
            batch_id=d["id"],
            permit_id=d.get("permit_id", ""),
            crop_name=d.get("crop", "Potato"),
            start_day=d.get("start_day", 1.0),
            window_duration_days=d.get("window_duration_days", FARMING_BATCH_WINDOW_DAYS)
        )
        batch.close_day = float(d.get("close_day", batch.start_day + batch.window_duration_days))
        batch.closed = bool(d.get("closed", False))
        batch.tiles = {(t[0], t[1]) for t in d.get("tiles", [])}
        batch.growth_days = float(d.get("growth_days", 0.0))
        batch.watered_today = bool(d.get("watered_today", False))
        batch.unwatered_days = int(d.get("unwatered_days", 0))
        batch.is_dead = bool(d.get("is_dead", False))
        return batch

class AreaPermit:
    def __init__(self, permit_id, name, permit_type, tiles_or_gx, gy=None, tw=None, th=None):
        self.id = permit_id
        self.name = name
        self.permit_type = permit_type
        self.crop = None  # None | "Potato" | etc.
        self.tile_crops = {}  # (gx, gy) -> {"crop": str, "growth_days": float, "watered_today": bool, "unwatered_days": int, "is_dead": bool}
        self._tile_crop_sync_needed = True
        self.growth_days = 0.0  # Legacy / display aggregate
        self.watered_today = False
        self.assigned_workers = []  # List of villager IDs
        self.max_workers = DEFAULT_PLOT_MAX_WORKERS
        self.task_reservations = {}  # (gx, gy) -> {"worker_id": int/str, "task_type": str}
        self.batches = {}  # batch_id -> FarmingBatch
        self.active_batch_id = None
        self.batch_counter = 0
        self.current_day_time = 1.0

        # Cemetery & Church Systems (Agent 3)
        self.tile_graves = {}  # (gx, gy) -> grave dict
        self.church_tax = {"Gold": 0, "Silver": 0, "Copper": 1}
        self.church_tax_paid_households = {}  # household_id -> day_number_paid
        if self.permit_type == "church":
            self.max_workers = 1

        if isinstance(tiles_or_gx, (set, list, tuple)):
            self.tiles = set(tiles_or_gx)
        else:
            gx = tiles_or_gx
            w = tw if tw is not None else 1
            h = th if th is not None else 1
            self.tiles = {(gx + c, gy + r) for c in range(w) for r in range(h)}

        self._tiles_revision = 0
        self._ordered_tiles_cache = None
        self._recalculate_bounds()

    def get_ordered_tiles(self):
        """Return the stable row-major tile order used by household floor sleeping."""
        if self._ordered_tiles_cache is None:
            self._ordered_tiles_cache = tuple(sorted(self.tiles, key=lambda tile: (tile[1], tile[0])))
        return self._ordered_tiles_cache

    def _invalidate_tile_cache(self):
        self._tiles_revision += 1
        self._ordered_tiles_cache = None

    def set_crop(self, crop_name):
        """Menetapkan komoditas yang akan digarap petani pada petak ladang"""
        self.crop = crop_name
        self.growth_days = 0.0
        self.watered_today = False
        self.tile_crops.clear()
        self._tile_crop_sync_needed = True
        self.batches.clear()
        self.active_batch_id = None
        self.batch_counter = 0

    def is_planting_window_open(self, current_day=None):
        """Mengecek apakah window penanaman untuk batch sedang aktif/terbuka"""
        if not self.crop or self.permit_type != "farm":
            return False
        if not self.batches:
            return True
        active = self.get_active_batch(current_day)
        if active and not active.closed:
            return True
        return False

    def get_active_batch(self, current_day=None):
        """Mengambil batch penanaman aktif yang belum ditutup"""
        cur_day = float(current_day) if current_day is not None else float(self.current_day_time)
        if self.active_batch_id and self.active_batch_id in self.batches:
            b = self.batches[self.active_batch_id]
            if b.closed:
                self.active_batch_id = None
                return None
            if cur_day > b.close_day:
                b.close(cur_day)
                self.active_batch_id = None
                return None
            return b
        return None

    def start_planting_batch(self, crop_name=None, start_day=None, window_duration_days=None):
        """Membuka batch penanaman baru"""
        cur_day = float(start_day) if start_day is not None else float(self.current_day_time)
        active = self.get_active_batch(cur_day)
        if active:
            return active
        self.batch_counter += 1
        batch_id = f"{self.id}_batch_{self.batch_counter}"
        crop = crop_name or self.crop or "Potato"
        win_days = float(window_duration_days) if window_duration_days is not None else FARMING_BATCH_WINDOW_DAYS
        batch = FarmingBatch(batch_id, self.id, crop, start_day=cur_day, window_duration_days=win_days)
        self.batches[batch_id] = batch
        self.active_batch_id = batch_id
        return batch

    def open_next_batch(self, crop_name=None, start_day=None, window_duration_days=None):
        """Membuka batch tanam baru, menutup batch aktif sebelumnya jika ada"""
        self.close_active_batch()
        return self.start_planting_batch(crop_name=crop_name, start_day=start_day, window_duration_days=window_duration_days)

    def close_active_batch(self, current_day=None):
        """Menutup batch penanaman yang sedang aktif sehingga tidak menerima penanaman susulan"""
        cur_day = float(current_day) if current_day is not None else float(self.current_day_time)
        if self.active_batch_id and self.active_batch_id in self.batches:
            b = self.batches[self.active_batch_id]
            b.close(cur_day)
            self.active_batch_id = None
            if len(b.tiles) == 0:
                del self.batches[b.id]
            return True
        return False

    def get_tile_batch(self, gx, gy):
        """Mencari objek batch yang menaungi tile (gx, gy)"""
        tc = self.tile_crops.get((gx, gy))
        if tc and tc.get("batch_id") and tc["batch_id"] in self.batches:
            return self.batches[tc["batch_id"]]
        for b in self.batches.values():
            if (gx, gy) in b.tiles:
                return b
        return None

    def get_untilled_tiles(self):
        """Mendapatkan petak ladang yang belum dicangkul/ditanami benih dan eligible untuk ditanami"""
        if not self.crop or self.permit_type != "farm":
            return []
        if not self.is_planting_window_open():
            return []
        untilled = []
        for t in sorted(self.tiles, key=lambda x: (x[1], x[0])):
            tc = self.tile_crops.get(t)
            if not tc or not tc.get("crop") or tc.get("is_dead"):
                untilled.append(t)
        return untilled

    def get_empty_tiles(self):
        """Mendapatkan seluruh petak ladang yang saat ini kosong/tidak memiliki tanaman hidup (termasuk missed batch)"""
        if self.permit_type != "farm":
            return []
        empty = []
        for t in sorted(self.tiles, key=lambda x: (x[1], x[0])):
            tc = self.tile_crops.get(t)
            if not tc or not tc.get("crop") or tc.get("is_dead"):
                empty.append(t)
        return empty

    def till_and_sow_tile(self, gx, gy, current_day=None):
        """Mencangkul dan menabur benih pada petak ladang. Bergabung ke batch tanam aktif."""
        if not self.crop or self.permit_type != "farm":
            return False
        if (gx, gy) not in self.tiles:
            return False

        # Tile yang sedang ditumbuhi tanaman TIDAK BISA ditanami lagi
        if (gx, gy) in self.tile_crops:
            existing_tc = self.tile_crops[(gx, gy)]
            if existing_tc.get("crop") and not existing_tc.get("is_dead"):
                return False

        cur_day = float(current_day) if current_day is not None else float(self.current_day_time)
        active_batch = self.get_active_batch(cur_day)
        if not active_batch:
            if not self.batches:
                active_batch = self.start_planting_batch(crop_name=self.crop, start_day=cur_day)
            else:
                # Batch sebelumnya sudah ditutup -> Penanaman susulan ditolak sampai batch baru dibuka
                return False

        if active_batch.closed or not active_batch.can_accept_planting(cur_day):
            return False

        # Pastikan tile tidak berada di batch aktif lain
        for b in self.batches.values():
            if b.id != active_batch.id:
                b.remove_tile(gx, gy)

        success = active_batch.add_tile(gx, gy, cur_day)
        if not success:
            return False

        self.tile_crops[(gx, gy)] = {
            "crop": active_batch.crop,
            "batch_id": active_batch.id,
            "growth_days": active_batch.growth_days,
            "watered_today": False,
            "unwatered_days": 0,
            "is_dead": False
        }
        return True

    def ensure_tile_crops(self):
        """Memastikan semua tile ladang terdaftar di kamus tile_crops"""
        if not self._tile_crop_sync_needed or not self.crop or self.permit_type != "farm":
            return
        for tile in self.tiles:
            if tile not in self.tile_crops:
                self.tile_crops[tile] = {
                    "crop": None,
                    "growth_days": 0.0,
                    "watered_today": False,
                    "unwatered_days": 0,
                    "is_dead": False
                }
        self._tile_crop_sync_needed = False

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
                batch = self.get_tile_batch(gx, gy)
                if batch:
                    batch.watered_today = True
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
        """Mendapatkan petak ladang yang siap panen berbasis sinkronisasi batch"""
        self.ensure_tile_crops()
        ready = []
        # Batch-based harvest readiness: seluruh tile dalam batch siap panen serempak
        for batch in self.batches.values():
            if batch.is_harvestable and not batch.is_dead:
                for t in sorted(batch.tiles):
                    if t in self.tile_crops:
                        tc = self.tile_crops[t]
                        if tc.get("crop") and not tc.get("is_dead") and t not in ready:
                            ready.append(t)

        # Fallback untuk tile tanpa batch
        for t, tc in self.tile_crops.items():
            crop_cfg = CROP_TYPES.get(str(tc.get("crop", "potato")).lower(), CROP_TYPES.get("potato", {}))
            growth_target = crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS)
            if tc.get("crop") and not tc.get("is_dead") and tc.get("growth_days", 0.0) >= growth_target:
                if t not in ready:
                    ready.append(t)
        return ready

    def harvest_tile(self, gx, gy):
        self.ensure_tile_crops()
        if (gx, gy) in self.tile_crops:
            tc = self.tile_crops[(gx, gy)]
            batch = self.get_tile_batch(gx, gy)
            crop_cfg = CROP_TYPES.get(str(tc.get("crop", "potato")).lower(), CROP_TYPES.get("potato", {}))
            growth_target = crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS)
            is_harvestable = (batch.is_harvestable if batch else False) or (tc.get("growth_days", 0.0) >= growth_target)

            if tc.get("crop") and not tc["is_dead"] and is_harvestable:
                crop_key = str(tc.get("crop") or "potato").lower()
                c_cfg = CROP_TYPES.get(crop_key, crop_cfg)
                yield_distribution = c_cfg.get("yield_distribution", [])
                if yield_distribution:
                    yield_val = random.choices(
                        [int(entry["amount"]) for entry in yield_distribution],
                        weights=[float(entry["weight"]) for entry in yield_distribution],
                        k=1,
                    )[0]
                else:
                    yield_val = int(c_cfg.get("yield_per_tile", c_cfg.get("yield", 2)))

                # Hapus tile dari batch
                if batch:
                    batch.remove_tile(gx, gy)
                    if len(batch.tiles) == 0:
                        if batch.id in self.batches:
                            del self.batches[batch.id]
                        if self.active_batch_id == batch.id:
                            self.active_batch_id = None

                # Reset tile menjadi untilled / kosong untuk batch masa depan
                tc["crop"] = None
                tc["growth_days"] = 0.0
                tc["batch_id"] = None
                tc["watered_today"] = False
                tc["unwatered_days"] = 0
                return yield_val
        return 0

    def update_growth(self, day_dt, current_day=None):
        """Update pertumbuhan harian tanaman berbasis synchronized batch"""
        if current_day is not None:
            self.current_day_time = float(current_day)
        else:
            self.current_day_time += float(day_dt)

        self.ensure_tile_crops()
        # Cek jika window batch aktif telah kadaluarsa
        if self.active_batch_id and self.active_batch_id in self.batches:
            act_b = self.batches[self.active_batch_id]
            if not act_b.closed and self.current_day_time >= act_b.close_day:
                self.close_active_batch(self.current_day_time)

        # Update per batch: seluruh tile dalam 1 batch tumbuh bersamaan
        for batch in list(self.batches.values()):
            if batch.is_dead or len(batch.tiles) == 0:
                continue
            batch.update_growth(self.current_day_time)
            # Sinkronisasi growth_days ke seluruh tile anggota batch
            for t in batch.tiles:
                if t in self.tile_crops:
                    self.tile_crops[t]["growth_days"] = batch.growth_days

        # Fallback untuk tile tanpa batch (legacy safety)
        for tc in self.tile_crops.values():
            if tc.get("crop") and not tc.get("is_dead") and not tc.get("batch_id"):
                crop_cfg = CROP_TYPES.get(str(tc.get("crop", "potato")).lower(), CROP_TYPES.get("potato", {}))
                growth_target = crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS)
                if tc.get("watered_today"):
                    tc["growth_days"] = min(growth_target, tc["growth_days"] + day_dt)

        # Update aggregate display
        living = [tc["growth_days"] for tc in self.tile_crops.values() if tc.get("crop") and not tc.get("is_dead")]
        if living:
            self.growth_days = sum(living) / len(living)
        self.watered_today = any(tc.get("watered_today", False) for tc in self.tile_crops.values())

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
        self._invalidate_tile_cache()
        self._tile_crop_sync_needed = True
        self._recalculate_bounds()
        return True

    def reset_daily_watering(self):
        """Dipanggil setiap fajar (Day transition)"""
        self.ensure_tile_crops()
        self.task_reservations.clear()  # Reset antrean reservasi tugas setiap fajar

        # Tutup batch aktif jika batas window telah terlewati
        if self.active_batch_id and self.active_batch_id in self.batches:
            b = self.batches[self.active_batch_id]
            if self.current_day_time >= b.close_day:
                self.close_active_batch(self.current_day_time)

        for t, tc in list(self.tile_crops.items()):
            if tc.get("crop") and not tc.get("is_dead", False):
                if tc.get("watered_today", False):
                    tc["watered_today"] = False
                    tc["unwatered_days"] = 0
                else:
                    tc["unwatered_days"] = tc.get("unwatered_days", 0) + 1
                    # Jika telat disiram (1 hari terlewat tidak disiram), tanaman mati & menjadi tile kosong
                    if tc["unwatered_days"] >= 1:
                        tc["is_dead"] = True
                        b_id = tc.get("batch_id")
                        if b_id and b_id in self.batches:
                            self.batches[b_id].remove_tile(t[0], t[1])
                        tc["crop"] = None  # Menjadi tile kosong yang siap dicangkul & ditanami kembali
                        tc["growth_days"] = 0.0
                        tc["watered_today"] = False
                        tc["batch_id"] = None

        # Reset flag watering pada seluruh batch dan bersihkan batch kosong
        for batch in list(self.batches.values()):
            batch.watered_today = False
            if len(batch.tiles) == 0:
                del self.batches[batch.id]
                if self.active_batch_id == batch.id:
                    self.active_batch_id = None

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

    def add_tiles(self, new_tiles):
        """Expands permit by adding new tiles (like expanding Farm or Cemetery)."""
        if isinstance(new_tiles, (tuple, list)) and len(new_tiles) == 2 and isinstance(new_tiles[0], int):
            new_tiles = {tuple(new_tiles)}
        else:
            new_tiles = set(tuple(t) for t in new_tiles)
        self.tiles.update(new_tiles)
        self._invalidate_tile_cache()
        self._tile_crop_sync_needed = True
        self._recalculate_bounds()
        if self.permit_type == "cemetery":
            from game.systems.village_life.cemetery_system import CemeterySystem
            CemeterySystem.ensure_cemetery_graves(self)

    def expand_tiles(self, new_tiles):
        """Alias for add_tiles."""
        self.add_tiles(new_tiles)

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


def get_villager_home_position(villager, villager_manager=None, permit_manager=None, furniture_manager=None):
    """
    Returns (x, y) coordinates of the villager's household residence in world coordinates.
    Resolution order:
    1. Family's assigned housing permit (or villager's assigned permit) center in world coordinates.
       Always checks the live family.assigned_permit_id from villager_manager first so dynamic household
       relocation is instantly reflected!
    2. Furniture: Bed or Storage Chest assigned to this villager or their family.
    3. Fallback: (villager.x, villager.y).
    """
    fam = None
    if villager_manager and hasattr(villager_manager, "families"):
        f_id = getattr(villager, "family_id", None)
        if f_id:
            fam = next((f for f in villager_manager.families if str(f.id) == str(f_id)), None)

    assigned_pid = getattr(fam, "assigned_permit_id", None) or getattr(villager, "assigned_permit_id", None)
    if assigned_pid and permit_manager and hasattr(permit_manager, "permits"):
        p = next((p for p in permit_manager.permits if str(p.id) == str(assigned_pid)), None)
        if p:
            if hasattr(p, "tiles") and p.tiles:
                avg_x = sum(t[0] for t in p.tiles) / float(len(p.tiles))
                avg_y = sum(t[1] for t in p.tiles) / float(len(p.tiles))
                return (avg_x + 0.5) * TILE_SIZE, (avg_y + 0.5) * TILE_SIZE
            else:
                return (p.grid_x + p.tiles_w / 2.0) * TILE_SIZE, (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE

    # 2. Check assigned furniture (bed or family chest)
    if furniture_manager:
        if hasattr(furniture_manager, "get_bed_for_villager"):
            bed = furniture_manager.get_bed_for_villager(
                getattr(villager, "id", None),
                getattr(villager, "family_id", None),
            )
            if bed and hasattr(bed, "grid_x"):
                return (bed.grid_x + 0.5) * TILE_SIZE, (bed.grid_y + 0.5) * TILE_SIZE
        f_id = getattr(fam, "id", None) or getattr(villager, "family_id", None)
        if f_id and hasattr(furniture_manager, "get_storage_for_family"):
            chest = furniture_manager.get_storage_for_family(str(f_id))
            if chest and hasattr(chest, "grid_x"):
                return (chest.grid_x + 0.5) * TILE_SIZE, (chest.grid_y + 0.5) * TILE_SIZE

    # 3. Fallback: villager's current live coordinates
    return getattr(villager, "x", 0.0), getattr(villager, "y", 0.0)


def find_closest_unassigned_household_worker(
    target_x,
    target_y,
    permit_manager,
    villager_manager,
    target_job="Farmer",
    furniture_manager=None,
    exclude_worker_ids=None
):
    """
    Finds and returns the closest unassigned/unemployed household member to (target_x, target_y).
    Strict criteria:
    - Must be alive.
    - Belongs to a household.
    - Not assigned to any active workplace permit.
    - Not holding another active dedicated job (Priest, Gravedigger, Blacksmith, Builder, etc.).
    - Adults (age >= 16) prioritized.
    - Distance measured from household residence (home permit lot or chest/bed),
      so relocating a household dynamically updates proximity for all subsequent assignments.
    """
    if not villager_manager:
        return None

    all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])

    assigned_worker_ids = set()
    if permit_manager and hasattr(permit_manager, "permits"):
        for p in permit_manager.permits:
            for wid in getattr(p, "assigned_workers", []):
                assigned_worker_ids.add(str(wid))

    if exclude_worker_ids:
        for wid in exclude_worker_ids:
            assigned_worker_ids.add(str(wid))

    # Phase 1: Strict Candidates (alive, in a household, not assigned to a permit, not holding dedicated other job)
    candidates = []
    for v in all_vils:
        if not getattr(v, "is_alive", True):
            continue
        if str(v.id) in assigned_worker_ids:
            continue
        if not getattr(v, "family_id", None):
            continue

        cur_job = getattr(v, "job", "Farmer")
        # Unassigned / Unemployed / default Farmer / Peasant
        if cur_job not in ("Farmer", "Unassigned", "Unemployed", "Peasant", None, ""):
            if cur_job != target_job:
                continue
        candidates.append(v)

    # Phase 2: Relax household requirement if no candidates found
    if not candidates:
        for v in all_vils:
            if not getattr(v, "is_alive", True):
                continue
            if str(v.id) in assigned_worker_ids:
                continue
            cur_job = getattr(v, "job", "Farmer")
            if cur_job not in ("Farmer", "Unassigned", "Unemployed", "Peasant", None, ""):
                if cur_job != target_job:
                    continue
            candidates.append(v)

    # Phase 3: Final fallback to any alive villager not in assigned_worker_ids
    if not candidates:
        candidates = [
            v for v in all_vils
            if getattr(v, "is_alive", True) and str(v.id) not in assigned_worker_ids
        ]

    if not candidates:
        return None

    def sort_key(v):
        hx, hy = get_villager_home_position(v, villager_manager, permit_manager, furniture_manager)
        dist = math.hypot(target_x - hx, target_y - hy)
        has_family = 1 if getattr(v, "family_id", None) else 0
        is_adult = 1 if getattr(v, "age", 20) >= 16 else 0
        return (-has_family, -is_adult, dist, str(v.id))

    candidates.sort(key=sort_key)
    return candidates[0]


class PermitManager:
    def __init__(self):
        self.permits = []
        self.font = None
        self.permit_counter = 1

    def _ensure_font(self):
        if self.font is None:
            self.font = ui_font(11, bold=True)

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
        from game.world.island import is_land_tile
        if any(not is_land_tile(gx, gy) for gx, gy in new_tiles):
            return False, "Cannot claim water tiles"
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
        from game.world.island import is_land_tile
        if any(not is_land_tile(gx, gy) for gx, gy in building_tiles):
            return None, "Cannot build on water"

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
        # A. Cek apakah menabrak zona pertanian (Farm Permit) atau Pemakaman (Cemetery Permit)
        for p in self.permits:
            if p.permit_type in ("farm", "cemetery") and p.overlaps_tiles(building_tiles):
                return None, f"Cannot build structures on {p.permit_type.capitalize()} Lot: {p.name}!"

        # B. Cek apakah menabrak lot yang SUDAH memiliki bangunan (Occupied Lot)
        for p in self.permits:
            if p.overlaps_tiles(building_tiles):
                existing_blds = [b for b in building_manager.buildings if p.overlaps_building(b)]
                existing_sites = [s for s in building_manager.construction_sites if p.overlaps_building(s)]
                if existing_blds:
                    return None, f"Cannot build: Lot '{p.name}' is already occupied by {existing_blds[0].name}!"
                if existing_sites:
                    return None, f"Cannot build: Lot '{p.name}' already has an active construction site!"

        # C. Public structures configured without a required permit may be placed
        # on open ground or inside one empty lot, but cannot straddle a lot edge.
        type_cfg = BUILDING_TYPES.get(req_type, {}) if req_type in BUILDING_TYPES else {}
        if req_type in ("well", "toilet") or (type_cfg and type_cfg.get("required_permit") is None):
            for p in self.permits:
                if p.overlaps_tiles(building_tiles):
                    if p.contains_all_tiles(building_tiles):
                        return p, "Valid (Inside Empty Lot)"
                    else:
                        return None, f"Cannot straddle lot boundary of '{p.name}'!"
            return True, f"Valid (No Permit Required for {req_type.capitalize()})"

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
        if req_type in ("well", "toilet"):
            return True  # Well & Toilet tidak memerlukan Area Permit khusus
        if req_type in BUILDING_TYPES:
            allowed = BUILDING_TYPES[req_type].get("allowed_permits")
            if not allowed:
                return True
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

    def get_farm_permit_for_villager(self, villager):
        """Return the farm workplace assigned to this villager, if one exists."""
        villager_id = str(getattr(villager, "id", ""))
        return next((permit for permit in self.permits
                     if getattr(permit, "permit_type", None) == "farm"
                     and any(str(worker_id) == villager_id
                             for worker_id in getattr(permit, "assigned_workers", []))), None)

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

    def assign_worker_to_permit(self, permit_id, villager_id, villager_manager=None):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if not p:
            return False, "Permit not found"
        if not hasattr(p, "assigned_workers"):
            p.assigned_workers = []
        if villager_id in p.assigned_workers:
            return False, "Worker already assigned"
        if getattr(p, "permit_type", "") == "church" and len(p.assigned_workers) >= 1:
            return False, "Church can have exactly one Priest assigned"
        worker_cap = permit_worker_cap(p)
        if worker_cap is not None and len(p.assigned_workers) >= worker_cap:
            if getattr(p, "permit_type", "") == "church":
                return False, "Church can have exactly one Priest assigned"
            if getattr(p, "permit_type", "") == "farm":
                return False, "Farm worker slots are full"
            p.max_workers = len(p.assigned_workers) + 1

        # Remove worker from any other permit first
        for other_p in self.permits:
            if other_p.id != permit_id and hasattr(other_p, "assigned_workers"):
                if villager_id in other_p.assigned_workers:
                    other_p.assigned_workers.remove(villager_id)
                elif str(villager_id) in [str(x) for x in other_p.assigned_workers]:
                    other_p.assigned_workers = [x for x in other_p.assigned_workers if str(x) != str(villager_id)]

        p.assigned_workers.append(villager_id)

        target_job = "Farmer"
        if p.permit_type == "church":
            target_job = "Priest"
        elif p.permit_type == "cemetery":
            target_job = "Gravedigger"
        else:
            for j_id, j_cfg in DEDICATED_JOBS.items():
                if j_cfg.get("workplace_permit") == p.permit_type:
                    target_job = j_id
                    break

        if villager_manager:
            all_v = villager_manager.get_all_villagers()
            v = next((x for x in all_v if str(x.id) == str(villager_id)), None)
            if v:
                v.set_job(target_job)

        return True, "Worker assigned"

    def unassign_worker_from_permit(self, permit_id, villager_id, villager_manager=None):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if p and hasattr(p, "assigned_workers") and villager_id in p.assigned_workers:
            p.assigned_workers.remove(villager_id)
            if villager_manager:
                all_v = villager_manager.get_all_villagers()
                v = next((x for x in all_v if str(x.id) == str(villager_id)), None)
                if v:
                    v.set_job("Unassigned")
            return True, "Worker removed"
        return False, "Worker not assigned to this permit"

    def change_max_workers(self, permit_id, delta, villager_manager=None, furniture_manager=None, auto_assign=True):
        p = next((p for p in self.permits if p.id == permit_id), None)
        if p:
            current_max = getattr(p, "max_workers", 2 if p.permit_type == "farm" else 1)
            new_max = max(0, current_max + delta)
            p.max_workers = new_max
            if not hasattr(p, "assigned_workers"):
                p.assigned_workers = []

            # 1. Decreasing worker count: release the corresponding worker(s)
            if delta < 0:
                if p.permit_type == "church":
                    from game.systems.village_life.church_system import ChurchSystem
                    ChurchSystem.release_priest(self, villager_manager, target_permit=p)
                elif p.permit_type == "cemetery":
                    from game.systems.village_life.cemetery_system import CemeterySystem
                    CemeterySystem.release_gravedigger(self, villager_manager, target_permit=p)
                else:
                    while len(p.assigned_workers) > p.max_workers:
                        popped_id = p.assigned_workers.pop()
                        if villager_manager:
                            all_v = villager_manager.get_all_villagers()
                            v = next((x for x in all_v if str(x.id) == str(popped_id)), None)
                            if v:
                                v.set_job("Unassigned")

            # 2. Increasing worker count: automatically select closest available household member
            elif auto_assign and delta > 0 and villager_manager and len(p.assigned_workers) < p.max_workers:
                target_job = "Farmer"
                if p.permit_type == "church":
                    target_job = "Priest"
                elif p.permit_type == "cemetery":
                    target_job = "Gravedigger"
                else:
                    for j_id, j_cfg in DEDICATED_JOBS.items():
                        if j_cfg.get("workplace_permit") == p.permit_type:
                            target_job = j_id
                            break

                p_cx = (p.grid_x + p.tiles_w / 2.0) * TILE_SIZE
                p_cy = (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE

                chosen = find_closest_unassigned_household_worker(
                    p_cx, p_cy,
                    permit_manager=self,
                    villager_manager=villager_manager,
                    target_job=target_job,
                    furniture_manager=furniture_manager,
                    exclude_worker_ids=p.assigned_workers
                )
                if chosen:
                    chosen.set_job(target_job)
                    self.assign_worker_to_permit(p.id, chosen.id, villager_manager=villager_manager)
            return True
        return False

    def auto_sort_workers(self, villager_manager, job_filter=None, furniture_manager=None):
        """Backward-compatible shim — delegates to the workplace-system
        recalibration which covers permits, furniture, and buildings."""
        from game.systems.work.workplace_system import auto_sort_all_workers
        return auto_sort_all_workers(self, furniture_manager, villager_manager,
                                     building_manager=None, job_filter=job_filter)

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
        visible_permits = [
            p for p in self.permits
            if p.tiles and camera.is_world_rect_visible(
                p.grid_x * tile_size, p.grid_y * tile_size,
                p.tiles_w * tile_size, p.tiles_h * tile_size,
            )
        ]
        occupied_map = {}
        for p in visible_permits:
            occupied_map[p.id] = sum(
                p.overlaps_building(entity)
                for entity in (
                    list(building_manager.buildings)
                    + list(building_manager.construction_sites)
                    + list(getattr(building_manager, "demolition_sites", []))
                )
            )

        scaled_tile = int(tile_size * camera.zoom)

        for p in visible_permits:
            type_cfg = PERMIT_TYPES.get(p.permit_type, PERMIT_TYPES["housing"])
            b_count = occupied_map.get(p.id, 0)
            color_fill = type_cfg["color"]
            border_col = type_cfg["border_color"]

            # 1. Gambar fill dan border untuk setiap tile permit yang saling menyambung
            permit_world_bounds = (
                p.grid_x * tile_size,
                p.grid_y * tile_size,
                (p.grid_x + p.tiles_w) * tile_size,
                (p.grid_y + p.tiles_h) * tile_size,
            )
            for (gx, gy) in camera.iter_visible_tiles(
                    p.tiles, tile_size, permit_world_bounds):
                sx, sy = camera.world_to_screen(gx * tile_size, gy * tile_size)
                tile_surf = alpha_fill_surface(scaled_tile, scaled_tile, color_fill)
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
                        crop_cfg = CROP_TYPES.get(str(t_crop.get("crop", "potato")).lower(), {})
                        growth_target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
                        sprout_day = float(crop_cfg.get("sprout_day", 0.0))
                        leaf_day = float(crop_cfg.get("leaf_day", sprout_day))
                        harvest_day = float(crop_cfg.get("harvest_day", growth_target))

                        if is_dead:
                            # Tanaman layu / mati mengering karena tidak disiram
                            dead_r = max(2, int(3 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, COLOR_CROP_WITHERED, (px, py), dead_r)
                                pygame.draw.line(surface, (80, 70, 50), (px - 2, py - 2), (px + 2, py + 2), 1)

                        # Tahap 1: Hari 0-1 (Benih dalam alur tanah)
                        elif g_days < sprout_day:
                            seed_r = max(1, int(2 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (180, 140, 100), (px, py), seed_r)

                        # Tahap 2: Hari 2-3 (Tunas mulai muncul)
                        elif g_days < leaf_day:
                            sprout_r = max(2, int(3 * camera.zoom))
                            for ox, oy in sprout_offsets:
                                px = sx + int(scaled_tile * ox)
                                py = sy + int(scaled_tile * oy)
                                pygame.draw.circle(surface, (34, 197, 94), (px, py), sprout_r)
                                pygame.draw.circle(surface, (20, 83, 45), (px, py), sprout_r, 1)

                        # Tahap 3: Hari 4-9 (Tumbuh daun dan batang)
                        elif g_days < harvest_day:
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

                # Jika zona pemakaman (Cemetery Permit), gambar visual tanah kuburan & 5 varian batu nisan
                if p.permit_type == "cemetery":
                    # Tanah dasar makam
                    soil_rect = pygame.Rect(sx + 1, sy + 1, scaled_tile - 2, scaled_tile - 2)
                    pygame.draw.rect(surface, (78, 64, 50), soil_rect)
                    for fx_o, fy_o in ((0.2, 0.3), (0.7, 0.25), (0.4, 0.75), (0.8, 0.8)):
                        pygame.draw.circle(surface, (120, 110, 100), (sx + int(scaled_tile * fx_o), sy + int(scaled_tile * fy_o)), max(1, int(1.5 * camera.zoom)))

                    g = getattr(p, "tile_graves", {}).get((gx, gy))
                    if g:
                        is_occ = g.get("is_occupied", False)
                        dig_prog = g.get("dig_progress", 0.0)
                        bury_prog = g.get("bury_progress", 0.0)
                        var = g.get("tombstone_variant", 0)
                        has_history = bool(g.get("corpse_history", []))

                        if is_occ or dig_prog > 0.0 or bury_prog > 0.0:
                            gx_w = int(scaled_tile * 0.55)
                            gy_h = int(scaled_tile * 0.65)
                            gx_m = sx + (scaled_tile - gx_w) // 2
                            gy_m = sy + int(scaled_tile * 0.25)
                            pygame.draw.rect(surface, (45, 30, 18), (gx_m, gy_m, gx_w, gy_h), border_radius=3)
                            pygame.draw.rect(surface, (30, 18, 10), (gx_m, gy_m, gx_w, gy_h), width=1, border_radius=3)
                        elif has_history and not is_occ:
                            for gx_o, gy_o in ((0.3, 0.4), (0.6, 0.5), (0.4, 0.7)):
                                tx = sx + int(scaled_tile * gx_o)
                                ty = sy + int(scaled_tile * gy_o)
                                pygame.draw.line(surface, (34, 197, 94), (tx, ty), (tx - 2, ty - 4), 1)
                                pygame.draw.line(surface, (34, 197, 94), (tx, ty), (tx + 2, ty - 5), 1)

                        if is_occ and var is not None:
                            head_cx = sx + scaled_tile // 2
                            head_base_y = sy + int(scaled_tile * 0.38)
                            var = var % 5

                            if var == 0:
                                cw = max(2, int(3 * camera.zoom))
                                ch = max(10, int(16 * camera.zoom))
                                bw = max(8, int(12 * camera.zoom))
                                pygame.draw.rect(surface, (148, 163, 184), (head_cx - cw // 2, head_base_y - ch, cw, ch))
                                pygame.draw.rect(surface, (148, 163, 184), (head_cx - bw // 2, head_base_y - int(ch * 0.7), bw, cw))
                                ring_r = max(4, int(5 * camera.zoom))
                                pygame.draw.circle(surface, (148, 163, 184), (head_cx, head_base_y - int(ch * 0.7) + cw // 2), ring_r, 1)
                            elif var == 1:
                                tw = max(10, int(14 * camera.zoom))
                                th = max(12, int(18 * camera.zoom))
                                top_y = head_base_y - th
                                pts = [
                                    (head_cx - tw // 2, head_base_y),
                                    (head_cx - tw // 2, top_y + int(th * 0.35)),
                                    (head_cx, top_y),
                                    (head_cx + tw // 2, top_y + int(th * 0.35)),
                                    (head_cx + tw // 2, head_base_y),
                                ]
                                pygame.draw.polygon(surface, (160, 165, 175), pts)
                                pygame.draw.polygon(surface, (100, 105, 115), pts, 1)
                                pygame.draw.line(surface, (71, 85, 105), (head_cx - tw // 4, head_base_y - int(th * 0.35)), (head_cx + tw // 4, head_base_y - int(th * 0.35)), 1)
                            elif var == 2:
                                tw = max(10, int(14 * camera.zoom))
                                th = max(11, int(16 * camera.zoom))
                                rect_h = int(th * 0.6)
                                pygame.draw.rect(surface, (170, 175, 185), (head_cx - tw // 2, head_base_y - rect_h, tw, rect_h))
                                pygame.draw.circle(surface, (170, 175, 185), (head_cx, head_base_y - rect_h), tw // 2)
                                pygame.draw.rect(surface, (100, 105, 115), (head_cx - tw // 2, head_base_y - rect_h, tw, rect_h), 1)
                                pygame.draw.circle(surface, (100, 105, 115), (head_cx, head_base_y - rect_h), tw // 2, 1)
                            elif var == 3:
                                tw = max(14, int(18 * camera.zoom))
                                th = max(9, int(13 * camera.zoom))
                                base_w = max(16, int(22 * camera.zoom))
                                pygame.draw.rect(surface, (100, 105, 115), (head_cx - base_w // 2, head_base_y - 3, base_w, 4))
                                pygame.draw.rect(surface, (130, 135, 145), (head_cx - tw // 2, head_base_y - th, tw, th - 3))
                                pygame.draw.rect(surface, (71, 85, 105), (head_cx - tw // 2, head_base_y - th, tw, th - 3), 1)
                                pygame.draw.line(surface, (51, 65, 85), (head_cx, head_base_y - th + 2), (head_cx, head_base_y - 5), 1)
                                pygame.draw.line(surface, (51, 65, 85), (head_cx - 2, head_base_y - th + 5), (head_cx + 2, head_base_y - th + 5), 1)
                            elif var == 4:
                                tw = max(14, int(18 * camera.zoom))
                                th = max(12, int(16 * camera.zoom))
                                arch_r = tw // 4
                                rect_h = int(th * 0.55)
                                pygame.draw.rect(surface, (180, 185, 195), (head_cx - tw // 2, head_base_y - rect_h, tw, rect_h))
                                pygame.draw.circle(surface, (180, 185, 195), (head_cx - arch_r, head_base_y - rect_h), arch_r)
                                pygame.draw.circle(surface, (180, 185, 195), (head_cx + arch_r, head_base_y - rect_h), arch_r)
                                pygame.draw.rect(surface, (110, 115, 125), (head_cx - tw // 2, head_base_y - rect_h, tw, rect_h), 1)
                                pygame.draw.circle(surface, (110, 115, 125), (head_cx - arch_r, head_base_y - rect_h), arch_r, 1)
                                pygame.draw.circle(surface, (110, 115, 125), (head_cx + arch_r, head_base_y - rect_h), arch_r, 1)

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
                    workers_info = f" ({w_count} Workers)"

                    if getattr(p, "crop", None):
                        g_days = getattr(p, "growth_days", 0.0)
                        crop_cfg = CROP_TYPES.get(str(p.crop).lower(), {})
                        growth_target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
                        sprout_day = float(crop_cfg.get("sprout_day", 0.0))
                        leaf_day = float(crop_cfg.get("leaf_day", sprout_day))
                        harvest_day = float(crop_cfg.get("harvest_day", growth_target))
                        if g_days >= harvest_day:
                            stage_txt = "READY TO HARVEST!"
                        elif g_days >= leaf_day:
                            stage_txt = f"Day {int(g_days)}/{int(growth_target)} Leaves & Stems"
                        elif g_days >= sprout_day:
                            stage_txt = f"Day {int(g_days)}/{int(growth_target)} Sprouting"
                        else:
                            stage_txt = f"Day {int(g_days)}/{int(growth_target)} Planted"
                        crop_lbl = f" | {p.crop} [{stage_txt}]"
                    else:
                        crop_lbl = " | Unplanted"
                    label_txt = f"{prefix}{p.name} [{len(p.tiles)} tiles Farm{crop_lbl}]{workers_info}{status_suffix}"
                else:
                    label_txt = f"{prefix}{p.name} [{len(p.tiles)} tiles {type_cfg['name']}]{status_suffix}"
                lbl = self.font.render(label_txt, True, (255, 255, 255))
                surface.blit(lbl, (bx + 8, by + 8))
