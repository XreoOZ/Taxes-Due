"""
Villagers & Family Clan System (Dedicated Jobs, Multi-Generation Family Rosters & Tenant Land Deeds)
"""

import math
import random
import time
import pygame
from game.config import (
    VILLAGER_RADIUS,
    VILLAGER_SPEED,
    VILLAGER_CARRY_CAPACITY,
    WATERING_DURATION_SECONDS,
    DOORWAY_WAYPOINT_DISTANCE,
    TILE_SIZE,
    CROP_TYPES,
    COLOR_VILLAGER_BODY,
    COLOR_VILLAGER_OUTLINE,
    COLOR_SHADOW,
    VILLAGER_SURNAMES,
    VILLAGER_MALE_NAMES,
    VILLAGER_FEMALE_NAMES,
    DEDICATED_JOBS,
    ENTITY_AVOIDANCE_RADIUS,
    MIN_ENTITY_SEPARATION,
    WATERING_DURATION_INGAME_HOURS,
    TILLING_DURATION_INGAME_HOURS,
    FARM_TILE_PROXIMITY_PENALTY_ADJACENT,
    FARM_TILE_PROXIMITY_PENALTY_NEAR,
    FARM_TILE_ARRIVAL_DIST,
    INTERACTION_CONTACT_RADIUS,
    TOOL_STOW_ARRIVAL_DIST,
    LOOSE_ITEM_ARRIVAL_DIST,
    CHEST_INTERACTION_RADIUS,
    PATH_WAYPOINT_TOLERANCE,
    STUCK_THRESHOLD_SECONDS,
    STUCK_AVOIDANCE_DURATION,
    PATH_WAIT_RECHECK_INTERVAL,
    AI_NEED_MAX,
    AI_NEED_HUNGER_DECAY_PER_DAY,
    AI_NEED_THIRST_DECAY_PER_DAY,
    AI_CRITICAL_NEED_THRESHOLD,
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    AI_NEED_FOOD_RESTORE,
    AI_NEED_WATER_RESTORE,
    HOUSEHOLD_WATER_MAX_COLLECTORS,
    COLOR_NEED_HUNGER_HIGH,
    COLOR_NEED_HUNGER_MED,
    COLOR_NEED_HUNGER_LOW,
    COLOR_NEED_THIRST_HIGH,
    COLOR_NEED_THIRST_MED,
    COLOR_NEED_THIRST_LOW,
    COLOR_STATUS_ALIVE,
    COLOR_STATUS_DECEASED,
    COLOR_CORPSE_BODY,
    COLOR_CORPSE_OUTLINE
)
from game.world.pathfinding import GlobalPathRegistry
from game.systems.market_interface import request_market_food_purchase
from game.systems.job_tool_system import (
    get_job_required_tools,
    get_missing_tools_for_worker,
    get_irrelevant_tools_in_inventory,
    collect_all_job_tools,
    deposit_irrelevant_tools,
    is_tool_item
)

class Villager:
    def __init__(self, villager_id, first_name, last_name, gender, age, generation, role, family_id, x=0.0, y=0.0):
        self.id = villager_id
        self.first_name = first_name
        self.last_name = last_name
        self.gender = gender
        self.age = age
        self.generation = generation  # 1: Grandparents, 2: Parents, 3: Adult Offspring
        self.role = role              # Grandfather, Grandmother, Father, Mother, Adult Son, Adult Daughter
        self.family_id = family_id
        self.job = "Farmer"           # Dedicated Job (Concept: Job is the uniform/dedicated profession)
        self.previous_job = None
        self.needs_tool_reassessment = False
        self.assigned_permit_id = None

        # World Physics & Position
        self.x = float(x)
        self.y = float(y)
        self.radius = VILLAGER_RADIUS
        self.speed = VILLAGER_SPEED
        self.facing_angle = random.uniform(0, math.pi * 2)
        self.walk_cycle = 0.0
        self.is_moving = False

        # Speech & Behavior
        self.speech_text = None
        self.speech_timer = 0.0
        self.idle_wander_timer = random.uniform(2.0, 5.0)
        self.idle_target = (self.x, self.y)

        # Predetermined Route Navigation
        self.nav_target = None
        self.door_waypoints = []
        self.current_path = []
        self.path_index = 0
        self.path_target = None
        self.path_target_tile = None
        self.path_seq = 0
        self.yield_timer = 0.0
        self.wait_timer = 0.0
        self.is_waiting_for_path = False
        self.stuck_timer = 0.0
        self.stuck_blocked_tiles = {}

        # Work Tasks & Farming Routine
        self.task = "IDLE"  # "IDLE" | "TILLING" | "FETCHING_WATER" | "WATERING" | "HARVESTING" | "HAULING_HOME"
        self.carrying_crop = 0
        self.watering_timer = 0.0
        self.tilling_timer = 0.0
        self.has_water = False
        self.water_day = -1
        self.water_charges = 0
        self.well_draw_timer = 0.0
        self.current_work_tile = None
        self.active_tool = None  # None | "Hoe" | "Sickle" | "Watering_Can"
        self.inventory = {}  # {item_name: count}
        self.assigned_bed_id = None
        self.carrying_furniture = None
        self.carrying_res = None
        self.carrying_amount = 0
        self.target_loose_stack = None

        # Needs & Survival System (Agent 1)
        self.hunger = float(AI_NEED_MAX)
        self.thirst = float(AI_NEED_MAX)
        self.daily_food_consumed = 0
        self.daily_water_consumed = 0
        self.is_alive = True
        self.status = "ALIVE"          # "ALIVE" | "DECEASED"
        self.death_reason = None       # None | "Starvation" | "Dehydration"
        self.death_day = None
        self.previous_task_before_need = None
        self.need_seek_cooldown = 0.0
        self.market_service = None
        self.water_collect_amount = 0

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def die(self, reason="Starvation", day=1):
        """Transition this villager to the DECEASED state (corpse)."""
        self.is_alive = False
        self.status = "DECEASED"
        self.death_reason = reason
        self.death_day = day
        self.task = "DECEASED"
        self.is_moving = False
        self.current_path = []
        self.path_target = None
        self.path_target_tile = None
        self.active_tool = None
        self.yield_timer = 0.0
        self.wait_timer = 0.0
        self.is_waiting_for_path = False

        # Release any path reservation
        reg = GlobalPathRegistry.get_instance()
        reg.release_reservation(self.id)

        # Release work tile reservation if holding one
        self.current_work_tile = None

        # Drop carried furniture if applicable
        if getattr(self, "carrying_furniture", None):
            self.carrying_furniture.carrier_id = None
            self.carrying_furniture = None

        # Speech bubble showing demise
        self.say(f"Alas... ({reason})", duration=4.0)

    def _resume_or_idle_after_need(self):
        """Safely cleans up after fulfilling a critical need."""
        self.task = "IDLE"
        self.previous_task_before_need = None
        self.need_seek_cooldown = 0.0


    def say(self, text, duration=3.0):
        self.speech_text = text
        self.speech_timer = duration

    def set_home_permit(self, permit_id, home_x, home_y):
        self.assigned_permit_id = permit_id
        # Walk realistically to the newly assigned lot instead of teleporting
        offset_x = random.uniform(-20, 20)
        offset_y = random.uniform(-20, 20)
        self.idle_target = (home_x + offset_x, home_y + offset_y)
        self.idle_wander_timer = random.uniform(10.0, 16.0)
        self.say("Moving to our newly assigned family lot, Lord!", duration=4.0)

    def _find_nearest_well(self, building_manager):
        if not building_manager:
            return None
        wells = [b for b in building_manager.buildings if b.building_type == "well"]
        if not wells:
            return None
        wells.sort(key=lambda w: math.hypot(w.get_center_world(TILE_SIZE)[0] - self.x, w.get_center_world(TILE_SIZE)[1] - self.y))
        return wells[0]

    def _find_family_tool_source(self, tool_name, furniture_manager, stockpile_manager):
        """Mencari lokasi penyimpanan atau tumpukan alat milik keluarga di tanah"""
        fam_str = str(self.family_id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and chest.inventory.get(tool_name, 0) > 0:
                return chest.get_world_pos(TILE_SIZE), "chest", chest
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str and s.resource_type == tool_name and s.amount > 0:
                    return ((s.grid_x + 0.5) * TILE_SIZE, (s.grid_y + 0.5) * TILE_SIZE), "ground", s
        return None, None, None

    def _find_family_loose_stack_to_retrieve(self, stockpile_manager, furniture_manager, permit_manager, building_manager, all_entities):
        """Mencari tumpukan barang milik keluarga di tanah yang tercecer di luar rumah untuk dipungut dan diamankan"""
        if not stockpile_manager or not self.family_id:
            return None
        fam_str = str(self.family_id)

        # 1. Identifikasi lokasi rumah / chest keluarga
        chest = furniture_manager.get_storage_for_family(fam_str) if furniture_manager else None
        home_p = next((p for p in permit_manager.permits if p.id == self.assigned_permit_id), None) if (self.assigned_permit_id and permit_manager) else None
        home_b = self._get_home_building(permit_manager, building_manager) if (permit_manager and building_manager) else None

        # 2. Cari tumpukan barang milik keluarga di tanah
        candidates = []
        for s in list(stockpile_manager.stacks):
            if getattr(s, "amount", 0) <= 0:
                continue
            if getattr(s, "owner_type", None) != "villager" or str(getattr(s, "owner_id", "")) != fam_str:
                continue

            # Apakah barang ini sudah tersimpan aman di rumah?
            is_at_home = False
            if chest:
                if (s.grid_x, s.grid_y) == (chest.grid_x, chest.grid_y):
                    # Sudah berada tepat di petak peti, langsung serap ke peti
                    chest.store_item(s.resource_type, s.amount)
                    s.amount = 0
                    continue
            else:
                # Bila belum punya peti, petak dalam batas Lot rumah atau di dalam bangunan rumah dianggap aman
                if home_b and home_b.occupies_tile(s.grid_x, s.grid_y):
                    is_at_home = True
                elif home_p and home_p.contains_tile(s.grid_x, s.grid_y):
                    is_at_home = True

            if not is_at_home:
                candidates.append(s)

        # Bersihkan stack yang sudah kosong
        stockpile_manager.stacks = [s for s in stockpile_manager.stacks if s.amount > 0]

        if not candidates:
            return None

        # 3. Hindari berebut: abaikan stack yang sedang dituju anggota keluarga lain
        reserved_stacks = set()
        if all_entities:
            for other in all_entities:
                if other != self and str(getattr(other, "family_id", "")) == fam_str:
                    st = getattr(other, "target_loose_stack", None)
                    if st:
                        reserved_stacks.add(id(st))

        avail_candidates = [s for s in candidates if id(s) not in reserved_stacks]
        if not avail_candidates:
            return None

        # 4. Pilih yang terdekat
        avail_candidates.sort(key=lambda s: math.hypot((s.grid_x + 0.5) * TILE_SIZE - self.x, (s.grid_y + 0.5) * TILE_SIZE - self.y))
        return avail_candidates[0]

    def _family_has_tool(self, tool_name, furniture_manager, stockpile_manager):
        """Mengecek apakah keluarga memiliki alat tersebut (di inventory, peti rumah, atau lantai rumah)"""
        if self.inventory.get(tool_name, 0) > 0:
            return True
        fam_str = str(self.family_id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and chest.inventory.get(tool_name, 0) > 0:
                return True
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str and s.resource_type == tool_name and s.amount > 0:
                    return True
        return False

    def _select_dispersed_tile(self, candidate_tiles, farm_permit, all_entities=None):
        """Memilih petak pekerjaan dari candidate_tiles secara terdistribusi merata (mencegah bertumpuk/bergerombol)."""
        if not candidate_tiles:
            return None

        wid_str = str(self.id)
        other_positions = set()
        for t, res in farm_permit.task_reservations.items():
            if str(res.get("worker_id")) != wid_str:
                other_positions.add(t)

        if all_entities:
            for ent in all_entities:
                if ent != self and str(getattr(ent, "id", "")) != wid_str:
                    is_same_farm = (getattr(ent, "assigned_permit_id", None) == farm_permit.id or 
                                    (hasattr(farm_permit, "assigned_workers") and getattr(ent, "id", None) in farm_permit.assigned_workers))
                    if is_same_farm:
                        egx = int(math.floor(ent.x / TILE_SIZE))
                        egy = int(math.floor(ent.y / TILE_SIZE))
                        other_positions.add((egx, egy))
                        tgt = getattr(ent, "current_work_tile", None)
                        if tgt and tgt != self.current_work_tile:
                            other_positions.add(tgt)

        def tile_score(t):
            gx, gy = t
            dist = math.hypot((gx + 0.5) * TILE_SIZE - self.x, (gy + 0.5) * TILE_SIZE - self.y)
            proximity_penalty = 0.0
            for ogx, ogy in other_positions:
                grid_dist = math.hypot(gx - ogx, gy - ogy)
                if grid_dist < 1.5:
                    proximity_penalty += FARM_TILE_PROXIMITY_PENALTY_ADJACENT
                elif grid_dist < 2.5:
                    proximity_penalty += FARM_TILE_PROXIMITY_PENALTY_NEAR
            return dist + proximity_penalty

        candidate_tiles.sort(key=tile_score)
        return candidate_tiles[0]

    def get_job_required_tools(self):
        """Mendapatkan daftar alat yang dibutuhkan oleh profesi/pekerjaan worker secara data-driven"""
        return get_job_required_tools(self.job)

    def get_missing_job_tools(self):
        """Mendapatkan daftar alat yang belum dimiliki untuk pekerjaan saat ini"""
        return get_missing_tools_for_worker(self)

    def get_irrelevant_tools(self):
        """
        Mendapatkan daftar alat kerja yang TIDAK LAGI RELEVAN dengan pekerjaan saat ini
        (misal akibat pergantian job) atau alat berlebih (excess duplicates).
        Alat yang sedang tidak terpakai sementara DALAM SATU JOB TETAP DIPERTAHANKAN.
        """
        return get_irrelevant_tools_in_inventory(self)

    def set_job(self, new_job):
        """Mengubah pekerjaan/profesi worker secara dinamis dan memicu reassessment alat"""
        if getattr(self, "job", None) == new_job:
            return
        self.previous_job = getattr(self, "job", None)
        self.job = new_job
        self.needs_tool_reassessment = True

    def _get_unused_tools(self, assigned_farm=None, sched_activity=None):
        """
        Backward compatibility: mengembalikan alat yang tidak relevan atau berlebih.
        Alat yang relevan dengan pekerjaan TIDAK AKAN PERNAH dikembalikan ke peti hanya karena tidak dipakai sesaat.
        """
        return self.get_irrelevant_tools()

    def _find_tool_storage(self, furniture_manager, stockpile_manager, all_entities=None, building_manager=None):
        """Mencari lokasi penyimpanan alat keluarga (peti atau tumpukan tanah)"""
        fam_str = str(self.family_id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest:
                if hasattr(chest, "get_approach_point"):
                    pos = chest.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                    return pos, "chest", chest
                return chest.get_world_pos(TILE_SIZE), "chest", chest
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                    return ((s.grid_x + 0.5) * TILE_SIZE, (s.grid_y + 0.5) * TILE_SIZE), "ground", s
        return None, None, None

    def _has_tool_in_storage(self, tool_name, furniture_manager, stockpile_manager):
        """Mengecek apakah alat kerja tersebut tersedia di peti atau tumpukan keluarga"""
        fam_str = str(self.family_id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and chest.inventory.get(tool_name, 0) > 0:
                return True
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str and s.resource_type == tool_name and s.amount > 0:
                    return True
        return False

    def collect_all_job_tools(self, furniture_manager, stockpile_manager):
        """Mengumpulkan SEMUA alat yang dibutuhkan untuk pekerjaan saat ini dalam satu kali kunjungan"""
        return collect_all_job_tools(self, furniture_manager, stockpile_manager)

    def deposit_irrelevant_tools(self, furniture_manager, stockpile_manager):
        """Mengembalikan alat-alat yang tidak lagi relevan atau berlebih ke penyimpanan"""
        return deposit_irrelevant_tools(self, furniture_manager, stockpile_manager)

    def _equip_family_tool(self, tool_name, furniture_manager, stockpile_manager):
        """Memastikan alat sudah dipegang oleh karakter dari penyimpanan keluarga"""
        fam_str = str(self.family_id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and chest.inventory.get(tool_name, 0) > 0:
                chest.inventory[tool_name] -= 1
                if chest.inventory[tool_name] <= 0:
                    del chest.inventory[tool_name]
                self.inventory[tool_name] = self.inventory.get(tool_name, 0) + 1
                return True
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str and s.resource_type == tool_name and s.amount > 0:
                    stockpile_manager.take_from_stack(s, 1)
                    self.inventory[tool_name] = self.inventory.get(tool_name, 0) + 1
                    return True
        return False

    def _get_home_building(self, permit_manager, building_manager):
        if not self.assigned_permit_id or not building_manager:
            return None
        p = next((p for p in permit_manager.permits if p.id == self.assigned_permit_id), None)
        if not p:
            return None
        for b in building_manager.buildings:
            if p.overlaps_building(b):
                return b
        return None

    def _get_home_storage_dest(self, permit_manager, building_manager, furniture_manager, all_entities=None):
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(self.family_id)
            if chest:
                if hasattr(chest, "get_approach_point"):
                    return chest.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                return chest.get_world_pos(TILE_SIZE)
        home_b = self._get_home_building(permit_manager, building_manager)
        if home_b:
            if hasattr(home_b, "get_approach_point"):
                return home_b.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
            return home_b.get_center_world(TILE_SIZE)
        if self.assigned_permit_id:
            p = next((p for p in permit_manager.permits if p.id == self.assigned_permit_id), None)
            if p:
                return (p.grid_x + p.tiles_w / 2.0) * TILE_SIZE, (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE
        return 0.0, 0.0

    def deposit_item_to_chest(self, item_name, amount, furniture_manager):
        """Memindahkan item dari Inventory individu ke Chest keluarga tanpa mengubah total Household Possession"""
        if amount <= 0 or self.inventory.get(item_name, 0) < amount:
            return False, "Not enough items in inventory!"
        chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
        if not chest:
            return False, "Household has no storage chest!"
        actual = min(amount, self.inventory[item_name])
        self.inventory[item_name] -= actual
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        chest.store_item(item_name, actual)
        return True, f"Deposited {actual}x {item_name} to household chest."

    def withdraw_item_from_chest(self, item_name, amount, furniture_manager):
        """Memindahkan item dari Chest keluarga ke Inventory individu tanpa mengubah total Household Possession"""
        if amount <= 0:
            return False, "Invalid amount!"
        chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
        if not chest or chest.inventory.get(item_name, 0) < amount:
            return False, "Not enough items in chest!"
        actual = chest.take_item(item_name, amount)
        self.inventory[item_name] = self.inventory.get(item_name, 0) + actual
        return True, f"Withdrew {actual}x {item_name} from household chest."

    def drop_inventory_item(self, item_name, amount, stockpile_manager):
        """Menjatuhkan barang dari inventory individu ke tanah sebagai item milik keluarga"""
        if amount <= 0 or self.inventory.get(item_name, 0) < amount:
            return False, "Not enough items in inventory!"
        actual = min(amount, self.inventory[item_name])
        self.inventory[item_name] -= actual
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        cur_gx = int(math.floor(self.x / TILE_SIZE))
        cur_gy = int(math.floor(self.y / TILE_SIZE))
        stockpile_manager.drop_resource(item_name, actual, cur_gx, cur_gy, owner_type="villager", owner_id=self.family_id)
        return True, f"Dropped {actual}x {item_name} on ground."

    def use_item(self, item_name, amount=1):
        """Mengonsumsi item dari inventory, mengurangi total kepemilikan keluarga sesuai jumlah yang digunakan"""
        if self.inventory.get(item_name, 0) < amount:
            return False
        self.inventory[item_name] -= amount
        if self.inventory[item_name] <= 0:
            del self.inventory[item_name]
        return True

    def receive_granted_item(self, item_name, amount=1):
        """Menerima pemberian item/peralatan secara langsung tanpa merusak task state"""
        if amount <= 0:
            return
        self.inventory[item_name] = self.inventory.get(item_name, 0) + amount
        # Lepaskan segala path locking lama agar responsive
        reg = GlobalPathRegistry.get_instance()
        reg.release_reservation(self.id)
        self.is_waiting_for_path = False
        self.wait_timer = 0.0
        self.repath_cooldown = 0.0
        self.say(f"Received {amount}x {item_name}! Thank you, Lord!", duration=2.5)

    def grant_item(self, item_name, amount=1):
        """Alias untuk receive_granted_item"""
        self.receive_granted_item(item_name, amount)

    def update(self, dt, permit_manager, building_manager, all_entities, player, stockpile_manager=None, furniture_manager=None, day_cycle=None, schedule_manager=None, production_system=None, villager_manager=None, market_service=None):
        # Guard: Deceased AI stops performing all jobs and activities
        if not getattr(self, "is_alive", True):
            self.task = "DECEASED"
            self.is_moving = False
            self.current_path = []
            return

        if self.speech_timer > 0:
            self.speech_timer -= dt
            if self.speech_timer <= 0:
                self.speech_text = None

        if getattr(self, "need_seek_cooldown", 0.0) > 0.0:
            self.need_seek_cooldown = max(0.0, self.need_seek_cooldown - dt)

        # Decay Hunger and Thirst according to in-game day cycle
        day_sec = day_cycle.day_length_seconds if day_cycle else 1200.0
        self.hunger = max(0.0, self.hunger - (AI_NEED_HUNGER_DECAY_PER_DAY / day_sec) * dt)
        self.thirst = max(0.0, self.thirst - (AI_NEED_THIRST_DECAY_PER_DAY / day_sec) * dt)

        if market_service is not None:
            self.market_service = market_service
        self.building_manager = building_manager
        self.furniture_manager = furniture_manager

        # Evaluasi Jadwal 24-Jam (Work, Leisure, Sleep, Anything)
        cur_hour = getattr(day_cycle, "current_hour", 8.0) if day_cycle else 8.0
        if schedule_manager:
            sched_activity = schedule_manager.get_current_activity(self.job, cur_hour)
        else:
            if cur_hour < 6.0 or cur_hour >= 22.0:
                sched_activity = "SLEEP"
            elif 8.0 <= cur_hour < 18.0:
                sched_activity = "WORK"
            else:
                sched_activity = "LEISURE"

        # -------------------------------------------------------------
        # Rutinitas Kebutuhan Pokok: Critical Needs (<= 20%) & Evening Dinner
        # -------------------------------------------------------------
        is_crit_hunger = (self.hunger <= AI_CRITICAL_NEED_THRESHOLD)
        is_crit_thirst = (self.thirst <= AI_CRITICAL_NEED_THRESHOLD)
        is_dinner = (sched_activity == "LEISURE" and cur_hour >= 18.0)
        wants_food = (self.daily_food_consumed < DAILY_FOOD_REQUIREMENT and (is_crit_hunger or is_dinner))
        wants_water = (self.daily_water_consumed < DAILY_WATER_REQUIREMENT and (is_crit_thirst or is_dinner))

        # Critical interruption: Interupsi pekerjaan apa pun jika lapar atau haus mencapai <= 20%
        if (is_crit_hunger or is_crit_thirst):
            if self.task not in ("SEEKING_FOOD", "SEEKING_WATER") and self.need_seek_cooldown <= 0.0:
                if is_crit_hunger or is_crit_thirst or (sched_activity in ("LEISURE", "ANY") and self.task in ("IDLE", "LEISURE", "STROLLING")):
                    # Lepaskan reservasi pekerjaan jika sedang bekerja
                    if self.current_work_tile and permit_manager:
                        assigned_farm = next((p for p in permit_manager.permits if p.permit_type == "farm" and hasattr(p, "assigned_workers") and self.id in p.assigned_workers), None)
                        if assigned_farm:
                            assigned_farm.release_worker_reservations(self.id)
                        self.current_work_tile = None
                    reg = GlobalPathRegistry.get_instance()
                    reg.release_reservation(self.id)
                    self.current_path = []
                    self.is_waiting_for_path = False
                    if not getattr(self, "previous_task_before_need", None):
                        self.previous_task_before_need = self.task

                    if is_crit_thirst or (self.thirst <= self.hunger):
                        self.task = "SEEKING_WATER"
                    else:
                        self.task = "SEEKING_FOOD"

        # Eksekusi Pencarian Makanan (SEEKING_FOOD)
        if self.task == "SEEKING_FOOD":
            self.active_tool = None
            # 1. Dari inventory pribadi
            inv_food = next((it for it in ("Potato", "Food", "Bread") if self.inventory.get(it, 0) > 0), None)
            if inv_food:
                self.inventory[inv_food] -= 1
                if self.inventory[inv_food] <= 0:
                    del self.inventory[inv_food]
                self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                self.daily_food_consumed += 1
                self.say("Ate food from personal inventory!", duration=2.5)
                self._resume_or_idle_after_need()
                return

            # 2. Dari peti penyimpanan keluarga
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
            chest_food = None
            if chest and hasattr(chest, "inventory"):
                chest_food = next((it for it in ("Potato", "Food", "Bread") if chest.inventory.get(it, 0) > 0), None)

            if chest and chest_food:
                cx, cy = chest.get_world_pos(TILE_SIZE)
                arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived:
                    taken = chest.take_item(chest_food, 1)
                    if taken > 0:
                        self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                        self.daily_food_consumed += 1
                        self.say("Ate hearty meal from household chest!", duration=2.5)
                        self._resume_or_idle_after_need()
                return

            # 3. Dari tumpukan di tanah milik keluarga
            ground_food = None
            if stockpile_manager:
                fam_str = str(self.family_id)
                for s in getattr(stockpile_manager, "stacks", []):
                    if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                        if s.resource_type in ("Potato", "Food", "Bread") and s.amount > 0:
                            ground_food = s
                            break

            if ground_food:
                gx_pos = (ground_food.grid_x + 0.5) * TILE_SIZE
                gy_pos = (ground_food.grid_y + 0.5) * TILE_SIZE
                arrived = self._move_towards(gx_pos, gy_pos, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived:
                    ground_food.amount -= 1
                    if ground_food.amount <= 0:
                        stockpile_manager.stacks = [st for st in stockpile_manager.stacks if st != ground_food]
                    self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                    self.daily_food_consumed += 1
                    self.say("Ate food from family stockpile!", duration=2.5)
                    self._resume_or_idle_after_need()
                return

            # 4. Hubungi interface pasar AGENT 2 jika makanan di rumah kosong
            bought, food_name, amt = request_market_food_purchase(self.family_id, self, market_service=getattr(self, "market_service", None))
            if bought and amt > 0:
                self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                self.daily_food_consumed += 1
                self.say(f"Purchased {food_name or 'Food'} from Market and ate!", duration=2.5)
                self._resume_or_idle_after_need()
                return
            else:
                self.need_seek_cooldown = 4.0
                self.say("No food at home and market has none!", duration=2.5)
                self.task = "IDLE"
                return

        # Eksekusi Pencarian Air Minum (SEEKING_WATER)
        if self.task == "SEEKING_WATER":
            self.active_tool = None
            # 1. Dari inventory pribadi
            if self.inventory.get("Water", 0) > 0:
                self.inventory["Water"] -= 1
                if self.inventory["Water"] <= 0:
                    del self.inventory["Water"]
                self.thirst = min(AI_NEED_MAX, self.thirst + AI_NEED_WATER_RESTORE)
                self.daily_water_consumed += 1
                self.say("Drank water from personal supply!", duration=2.5)
                self._resume_or_idle_after_need()
                return

            # 2. Dari peti penyimpanan keluarga
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
            if chest and hasattr(chest, "inventory") and chest.inventory.get("Water", 0) > 0:
                cx, cy = chest.get_world_pos(TILE_SIZE)
                arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived:
                    taken = chest.take_item("Water", 1)
                    if taken > 0:
                        self.thirst = min(AI_NEED_MAX, self.thirst + AI_NEED_WATER_RESTORE)
                        self.daily_water_consumed += 1
                        self.say("Drank fresh water from storage chest!", duration=2.5)
                        self._resume_or_idle_after_need()
                return

            # 3. Dari sumur desa (jika air di rumah habis, ambil minum di sumur)
            well = self._find_nearest_well(building_manager)
            if well:
                try:
                    approach_pt = well.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                except TypeError:
                    approach_pt = well.get_approach_point((self.x, self.y), TILE_SIZE, building_manager)
                arrived = self._move_towards(approach_pt[0], approach_pt[1], dt, arrival_dist=24, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived:
                    self.well_draw_timer += dt
                    if self.well_draw_timer >= 0.5:
                        self.thirst = min(AI_NEED_MAX, self.thirst + AI_NEED_WATER_RESTORE)
                        self.daily_water_consumed += 1
                        self.say("Drank cold water directly from the well!", duration=2.5)
                        self.well_draw_timer = 0.0
                        self._resume_or_idle_after_need()
                return
            else:
                self.need_seek_cooldown = 4.0
                self.say("No water available! I am dying of thirst!", duration=2.5)
                self.task = "IDLE"
                return


        # -------------------------------------------------------------
        # Rutinitas 1: Tidur Malam (SLEEP)
        # -------------------------------------------------------------
        if sched_activity == "SLEEP":
            if getattr(self, "carrying_furniture", None):
                self.carrying_furniture.carrier_id = None
                self.carrying_furniture = None
            if furniture_manager:
                for f in furniture_manager.furnitures:
                    if f.carrier_id == self.id and not getattr(self, "carrying_furniture", None):
                        f.carrier_id = None

            # Kembalikan semua alat ke peti keluarga saat tidur malam
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
            if chest:
                for tool in ("Hoe", "Sickle", "Watering_Can"):
                    amt = self.inventory.get(tool, 0)
                    if amt > 0:
                        chest.store_item(tool, amt)
                        del self.inventory[tool]

            self.task = "SLEEPING"
            self.active_tool = None

            # 1. Cari Bed milik individu / keluarga
            bed = furniture_manager.get_bed_for_villager(self.id, self.family_id) if furniture_manager else None
            if bed:
                self.assigned_bed_id = bed.id
                bx, by = bed.get_world_pos(TILE_SIZE)
                arrived = self._move_towards(bx, by, dt, arrival_dist=12, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                if arrived:
                    self.x, self.y = bx, by
                    if not self.speech_text and random.random() < 0.015:
                        self.say("Zzz...", duration=2.0)
            else:
                self.assigned_bed_id = None
                # Perilaku alternatif: Tidur di lantai rumah secara tersebar pada petak berbeda (64px separation)
                p = next((p for p in permit_manager.permits if p.id == self.assigned_permit_id), None) if permit_manager else None
                fam_members = [e for e in all_entities if getattr(e, "family_id", None) == self.family_id] if all_entities else []
                m_idx = fam_members.index(self) if self in fam_members else (abs(hash(str(self.id))) % 8)

                if p and p.tiles:
                    sorted_tiles = sorted(list(p.tiles), key=lambda t: (t[1], t[0]))
                    floor_tile = sorted_tiles[m_idx % len(sorted_tiles)]
                    floor_x = (floor_tile[0] + 0.5) * TILE_SIZE
                    floor_y = (floor_tile[1] + 0.5) * TILE_SIZE
                else:
                    # Homeless at Town Center: spread out radially with generous spacing
                    total_m = max(1, len(fam_members) or 6)
                    ang = (m_idx / total_m) * (2.0 * math.pi)
                    floor_x = math.cos(ang) * 75.0
                    floor_y = math.sin(ang) * 75.0

                arrived = self._move_towards(floor_x, floor_y, dt, arrival_dist=14, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                if not self.speech_text and random.random() < 0.015:
                    self.say("Sleeping on the floor... I wish we had a Bed!", duration=2.5)
            return

        # -------------------------------------------------------------
        # Rutinitas 1.5: Relokasi / Hauling Furniture (Pindahan Perabotan Rumah Tangga)
        # -------------------------------------------------------------
        if sched_activity != "SLEEP" and furniture_manager:
            # A. Jika sedang membawa perabotan menuju target pemasangan baru
            if getattr(self, "carrying_furniture", None):
                f = self.carrying_furniture
                if not f.designated_target:
                    f.carrier_id = None
                    self.carrying_furniture = None
                    self.task = "IDLE"
                else:
                    tgx, tgy, target_permit_id = f.designated_target
                    dest_x = (tgx + 0.5) * TILE_SIZE
                    dest_y = (tgy + 0.5) * TILE_SIZE
                    self.task = "HAULING_FURNITURE"
                    self.active_tool = None
                    arrived = self._move_towards(dest_x, dest_y, dt, arrival_dist=18, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    if arrived:
                        furniture_manager.move_furniture(f.id, tgx, tgy, permit_manager=permit_manager, building_manager=building_manager)
                        f.cancel_move()
                        self.carrying_furniture = None
                        self.task = "IDLE"
                        self.say(f"Reinstalled our {f.name} here, Lord!", duration=3.0)
                return

            # B. Jika belum membawa, cari perabotan milik keluarga yang telah didesain untuk dipindahkan
            fam_str = str(self.family_id)
            target_f = None
            for f in furniture_manager.furnitures:
                if f.designated_target and (f.carrier_id is None or f.carrier_id == self.id):
                    if str(getattr(f, "family_id", "")) == fam_str:
                        target_f = f
                        break
                    elif f.family_id is None and target_f is None:
                        target_f = f

            if target_f:
                target_f.carrier_id = self.id
                fx, fy = target_f.get_world_pos(TILE_SIZE)
                self.task = "FETCHING_FURNITURE"
                self.active_tool = None
                if self.current_work_tile:
                    assigned_farm = next((p for p in permit_manager.permits if p.permit_type == "farm" and hasattr(p, "assigned_workers") and self.id in p.assigned_workers), None) if permit_manager else None
                    if assigned_farm:
                        assigned_farm.release_worker_reservations(self.id)
                    self.current_work_tile = None
                arrived = self._move_towards(fx, fy, dt, arrival_dist=20, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                if arrived:
                    self.carrying_furniture = target_f
                    self.say(f"Hauling our {target_f.name}...", duration=2.5)
                return

        # -------------------------------------------------------------
        # Rutinitas 1.6: Pengamanan & Pengangkutan Barang Milik Keluarga (Household Possession Retrieval)
        # -------------------------------------------------------------
        if sched_activity != "SLEEP" and stockpile_manager:
            # A. Jika sedang membawa barang hasil pungut / panen menuju rumah (HAULING_HOME)
            carried_res = getattr(self, "carrying_res", None) or ("Potato" if (self.carrying_crop > 0 or self.inventory.get("Potato", 0) > 0) else None)
            carried_amt = getattr(self, "carrying_amount", 0) or (self.carrying_crop if self.carrying_crop > 0 else self.inventory.get("Potato", 0))

            if self.task == "HAULING_HOME" and carried_res and carried_amt > 0:
                self.active_tool = None
                dest_x, dest_y = self._get_home_storage_dest(permit_manager, building_manager, furniture_manager, all_entities=all_entities)
                chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                cur_vgx = int(math.floor(self.x / TILE_SIZE))
                cur_vgy = int(math.floor(self.y / TILE_SIZE))
                is_near_chest = chest and abs(cur_vgx - chest.grid_x) <= 1 and abs(cur_vgy - chest.grid_y) <= 1
                arrived = self._move_towards(dest_x, dest_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived or is_near_chest:
                    self.is_moving = False
                    self.current_path = []
                    self.path_index = 0
                    self.path_target = None
                    self.path_target_tile = None
                    self.is_waiting_for_path = False
                    GlobalPathRegistry.get_instance().release_reservation(self.id)
                    if chest:
                        chest.store_item(carried_res, carried_amt)
                        self.say(f"Stored {carried_amt}x {carried_res} in household chest.", duration=2.5)
                    else:
                        cur_gx = int(math.floor(self.x / TILE_SIZE))
                        cur_gy = int(math.floor(self.y / TILE_SIZE))
                        stockpile_manager.drop_resource(carried_res, carried_amt, cur_gx, cur_gy, owner_type="villager", owner_id=self.family_id)
                        self.say(f"Stored {carried_amt}x {carried_res} safely at home.", duration=2.5)

                    self.inventory[carried_res] = max(0, self.inventory.get(carried_res, 0) - carried_amt)
                    if self.inventory.get(carried_res, 0) <= 0 and carried_res in self.inventory:
                        del self.inventory[carried_res]
                    self.carrying_res = None
                    self.carrying_amount = 0
                    self.carrying_crop = 0
                    self.task = "IDLE"
                return

            # B. Jika sedang aktif dalam perjalanan mengambil barang tercecer (FETCHING_POSSESSION)
            if self.task == "FETCHING_POSSESSION" and getattr(self, "target_loose_stack", None):
                target_s = self.target_loose_stack
                if target_s not in stockpile_manager.stacks or target_s.amount <= 0:
                    self.target_loose_stack = None
                    self.task = "IDLE"
                else:
                    tx = (target_s.grid_x + 0.5) * TILE_SIZE
                    ty = (target_s.grid_y + 0.5) * TILE_SIZE
                    self.active_tool = None
                    arrived = self._move_towards(tx, ty, dt, arrival_dist=32, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                    dist_to_stack = math.hypot(tx - self.x, ty - self.y)
                    cur_vgx = int(math.floor(self.x / TILE_SIZE))
                    cur_vgy = int(math.floor(self.y / TILE_SIZE))
                    is_near_enough = arrived or (abs(cur_vgx - target_s.grid_x) <= 1 and abs(cur_vgy - target_s.grid_y) <= 1 and dist_to_stack <= 58.0)
                    if is_near_enough:
                        take_amt = min(target_s.amount, VILLAGER_CARRY_CAPACITY)
                        actual = stockpile_manager.take_from_stack(target_s, take_amt)
                        if actual > 0:
                            res_name = target_s.resource_type
                            self.carrying_res = res_name
                            self.carrying_amount = actual
                            self.inventory[res_name] = self.inventory.get(res_name, 0) + actual
                            if res_name in ("Potato", "Food", "potato"):
                                self.carrying_crop = actual
                            self.say(f"Retrieved our {res_name} (x{actual})!", duration=2.0)
                            self.task = "HAULING_HOME"
                        self.target_loose_stack = None
                    return

            # C. Jika sedang IDLE / LEISURE / belum ada pekerjaan aktif, cari barang keluarga yang tercecer di luar
            if self.task in ("IDLE", "LEISURE") and not getattr(self, "carrying_furniture", None):
                candidate_s = self._find_family_loose_stack_to_retrieve(stockpile_manager, furniture_manager, permit_manager, building_manager, all_entities)
                if candidate_s:
                    self.task = "FETCHING_POSSESSION"
                    self.target_loose_stack = candidate_s
                    self.active_tool = None
                    self.say(f"Going to retrieve our {candidate_s.resource_type}!", duration=2.0)
                    tx = (candidate_s.grid_x + 0.5) * TILE_SIZE
                    ty = (candidate_s.grid_y + 0.5) * TILE_SIZE
                    self._move_towards(tx, ty, dt, arrival_dist=22, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    return

        # -------------------------------------------------------------
        # Rutinitas 1.65: Household Water Production & Storage Execution (Agent 1)
        # -------------------------------------------------------------
        if sched_activity != "SLEEP" and furniture_manager:
            # A. Jika sedang mengangkut air hasil timba menuju peti keluarga (HAULING_HOUSEHOLD_WATER)
            if self.task == "HAULING_HOUSEHOLD_WATER":
                chest = furniture_manager.get_storage_for_family(self.family_id)
                if chest:
                    cx, cy = chest.get_world_pos(TILE_SIZE)
                    arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                    if arrived:
                        amt = self.inventory.get("Water", 0)
                        if amt > 0:
                            chest.store_item("Water", amt)
                            del self.inventory["Water"]
                        self.say("Stored fresh water in household chest!", duration=2.5)
                        self.task = "IDLE"
                else:
                    self.task = "IDLE"
                return

            # B. Jika sedang menimba air di sumur untuk kebutuhan rumah tangga (COLLECTING_HOUSEHOLD_WATER)
            if self.task == "COLLECTING_HOUSEHOLD_WATER":
                well = self._find_nearest_well(building_manager)
                if well:
                    try:
                        approach_pt = well.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                    except TypeError:
                        approach_pt = well.get_approach_point((self.x, self.y), TILE_SIZE, building_manager)
                    arrived = self._move_towards(approach_pt[0], approach_pt[1], dt, arrival_dist=24, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                    if arrived:
                        self.well_draw_timer += dt
                        if self.well_draw_timer >= 1.0:
                            draw_amt = getattr(self, "water_collect_amount", 1) or 1
                            self.inventory["Water"] = self.inventory.get("Water", 0) + draw_amt
                            self.task = "HAULING_HOUSEHOLD_WATER"
                            self.well_draw_timer = 0.0
                            self.say(f"Drew {draw_amt}x water, hauling home to storage!", duration=2.0)
                else:
                    self.task = "IDLE"
                return

        # -------------------------------------------------------------
        # Rutinitas 1.7: Generic Work Tool Management & Job Workflow
        # -------------------------------------------------------------
        # A. Kembalikan HANYA alat kerja yang tidak lagi relevan (misal setelah berganti job) atau alat berlebih
        irrelevant_tools = self.get_irrelevant_tools()
        if irrelevant_tools and self.task not in ("HAULING_FURNITURE", "FETCHING_FURNITURE", "HAULING_HOME", "FETCHING_POSSESSION"):
            storage_pos, storage_type, storage_obj = self._find_tool_storage(furniture_manager, stockpile_manager)
            if storage_pos:
                dist = math.hypot(storage_pos[0] - self.x, storage_pos[1] - self.y)
                cur_vgx = int(math.floor(self.x / TILE_SIZE))
                cur_vgy = int(math.floor(self.y / TILE_SIZE))
                st_gx = int(math.floor(storage_pos[0] / TILE_SIZE))
                st_gy = int(math.floor(storage_pos[1] / TILE_SIZE))
                is_near = (dist <= CHEST_INTERACTION_RADIUS) or (abs(cur_vgx - st_gx) <= 1 and abs(cur_vgy - st_gy) <= 1)

                if is_near:
                    dep = self.deposit_irrelevant_tools(furniture_manager, stockpile_manager)
                    if dep:
                        dep_txt = ", ".join(f"{c} {t}" for t, c in dep)
                        self.say(f"Returned irrelevant tools ({dep_txt}) to storage.", duration=2.0)
                    self.task = "IDLE"
                else:
                    self.task = "RETURNING_TOOLS"
                    self.active_tool = None
                    self._move_towards(storage_pos[0], storage_pos[1], dt, arrival_dist=TOOL_STOW_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    return

        # B. Kumpulkan SEMUA alat kerja yang dibutuhkan untuk pekerjaan saat ini dalam satu kali kunjungan
        # Ketentuan: "Collect ALL tools relevant to the current job before starting work.
        # Do NOT collect one tool, perform one task, return to storage, and collect another tool."
        if sched_activity in ("WORK", "ANY") and self.task not in ("HAULING_FURNITURE", "FETCHING_FURNITURE", "HAULING_HOME", "FETCHING_POSSESSION"):
            missing_tools = self.get_missing_job_tools()
            if missing_tools:
                available_to_fetch = [t for t, _ in missing_tools if self._has_tool_in_storage(t, furniture_manager, stockpile_manager)]
                if available_to_fetch:
                    storage_pos, storage_type, storage_obj = self._find_tool_storage(furniture_manager, stockpile_manager)
                    if storage_pos:
                        dist = math.hypot(storage_pos[0] - self.x, storage_pos[1] - self.y)
                        cur_vgx = int(math.floor(self.x / TILE_SIZE))
                        cur_vgy = int(math.floor(self.y / TILE_SIZE))
                        st_gx = int(math.floor(storage_pos[0] / TILE_SIZE))
                        st_gy = int(math.floor(storage_pos[1] / TILE_SIZE))
                        is_near = (dist <= CHEST_INTERACTION_RADIUS) or (abs(cur_vgx - st_gx) <= 1 and abs(cur_vgy - st_gy) <= 1)

                        if is_near:
                            col = self.collect_all_job_tools(furniture_manager, stockpile_manager)
                            if col:
                                self.say(f"Equipped {', '.join(col)} for {self.job}!", duration=2.0)
                            self.task = "IDLE"
                        else:
                            self.task = "EQUIPPING_JOB_TOOLS"
                            self.active_tool = None
                            self._move_towards(storage_pos[0], storage_pos[1], dt, arrival_dist=TOOL_STOW_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                            return

        # -------------------------------------------------------------
        # Rutinitas 2: Jam Kerja (WORK / ANY)
        # -------------------------------------------------------------
        if sched_activity in ("WORK", "ANY"):
            # Jika sedang membawa hasil panen di tangan, antar langsung ke Household Storage keluarga
            if self.carrying_crop > 0:
                self.task = "HAULING_HOME"
                self.active_tool = None
                dest_x, dest_y = self._get_home_storage_dest(permit_manager, building_manager, furniture_manager, all_entities=all_entities)
                chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                cur_vgx = int(math.floor(self.x / TILE_SIZE))
                cur_vgy = int(math.floor(self.y / TILE_SIZE))
                is_near_chest = chest and abs(cur_vgx - chest.grid_x) <= 1 and abs(cur_vgy - chest.grid_y) <= 1
                arrived = self._move_towards(dest_x, dest_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                if arrived or is_near_chest:
                    self.is_moving = False
                    self.current_path = []
                    self.path_index = 0
                    self.path_target = None
                    self.path_target_tile = None
                    self.is_waiting_for_path = False
                    GlobalPathRegistry.get_instance().release_reservation(self.id)
                    if chest:
                        chest.store_item("Potato", self.carrying_crop)
                        self.say(f"Stored {self.carrying_crop} potatoes in household chest.", duration=2.5)
                    elif stockpile_manager:
                        cur_gx = int(math.floor(self.x / TILE_SIZE))
                        cur_gy = int(math.floor(self.y / TILE_SIZE))
                        stockpile_manager.drop_resource("Food", self.carrying_crop, cur_gx, cur_gy, owner_type="villager", owner_id=self.family_id)
                        self.say(f"Stored {self.carrying_crop} potatoes at home.", duration=2.5)
                    self.carrying_crop = 0
                    self.inventory["Potato"] = 0
                return

            # Cek apakah ada sisa hasil panen keluarga di ladang yang belum diangkut
            if stockpile_manager:
                loose_crops = stockpile_manager.get_villager_loose_stacks(self.family_id, crops_only=True)
                if loose_crops:
                    self.task = "HAULING_HOME"
                    self.active_tool = None
                    target_stack = loose_crops[0]
                    tx = (target_stack.grid_x + 0.5) * TILE_SIZE
                    ty = (target_stack.grid_y + 0.5) * TILE_SIZE
                    arrived = self._move_towards(tx, ty, dt, arrival_dist=20, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    if arrived:
                        amt = stockpile_manager.take_from_stack(target_stack, VILLAGER_CARRY_CAPACITY)
                        self.carrying_crop = amt
                        self.inventory["Potato"] = self.inventory.get("Potato", 0) + amt
                        self.say(f"Carrying {amt} potatoes home...", duration=2.0)
                    return

            # Pekerjaan spesifik: Petani (Farmer)
            if self.job == "Farmer":
                assigned_farm = next((p for p in permit_manager.permits if p.permit_type == "farm" and hasattr(p, "assigned_workers") and self.id in p.assigned_workers), None)

                if assigned_farm and getattr(assigned_farm, "crop", None):
                    one_in_game_hour = (day_cycle.day_length_seconds / 24.0) if day_cycle else 50.0
                    current_day = day_cycle.day_number if day_cycle else 1

                    # Reset air siraman jika berganti hari (Wajib ambil air setiap hari baru)
                    if self.water_day != current_day:
                        self.has_water = False

                    # A. Panen tile yang sudah matang (Day 10+) menggunakan SICKLE (Sabit)
                    ready_tiles = assigned_farm.get_harvestable_tiles()
                    if ready_tiles:
                        if self.inventory.get("Sickle", 0) <= 0:
                            # Jika tidak memegang sabit, cek apakah bisa mengerjakan tilling atau watering dengan alat yang ada
                            can_till = assigned_farm.get_untilled_tiles() and self.inventory.get("Hoe", 0) > 0
                            can_water = assigned_farm.get_unwatered_tiles() and self.inventory.get("Watering_Can", 0) > 0
                            if not can_till and not can_water:
                                if not self._family_has_tool("Sickle", furniture_manager, stockpile_manager):
                                    self.task = "MISSING_TOOL"
                                    self.active_tool = None
                                    if self.current_work_tile:
                                        assigned_farm.release_worker_reservations(self.id)
                                        self.current_work_tile = None
                                    if not self.speech_text and random.random() < 0.05:
                                        self.say("The crops are ripe, but we need a Sickle to harvest them, Lord!", duration=3.0)
                                else:
                                    self.task = "EQUIPPING_JOB_TOOLS"
                                    self.active_tool = None
                                return
                        else:
                            self.active_tool = "Sickle"

                            target_t = None
                            if self.current_work_tile and self.task == "HARVESTING":
                                if self.current_work_tile in ready_tiles and not assigned_farm.is_tile_reserved(self.current_work_tile[0], self.current_work_tile[1], exclude_worker_id=self.id):
                                    target_t = self.current_work_tile
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "HARVEST")
                                else:
                                    assigned_farm.release_tile_reservation(self.current_work_tile[0], self.current_work_tile[1], self.id)
                                    self.current_work_tile = None

                            if not target_t:
                                avail_ready = assigned_farm.get_available_harvestable_tiles(worker_id=self.id)
                                if avail_ready:
                                    target_t = self._select_dispersed_tile(avail_ready, assigned_farm, all_entities=all_entities)
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "HARVEST")
                                    self.current_work_tile = target_t

                            if target_t:
                                self.task = "HARVESTING"
                                tx = (target_t[0] + 0.5) * TILE_SIZE
                                ty = (target_t[1] + 0.5) * TILE_SIZE
                                arrived = self._move_towards(tx, ty, dt, arrival_dist=FARM_TILE_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                                if arrived:
                                    yield_amt = assigned_farm.harvest_tile(target_t[0], target_t[1])
                                    assigned_farm.release_tile_reservation(target_t[0], target_t[1], self.id)
                                    self.current_work_tile = None
                                    GlobalPathRegistry.get_instance().release_reservation(self.id)
                                    if yield_amt > 0:
                                        from game.systems.production_distribution import ProductionDistributionSystem
                                        ps = production_system or ProductionDistributionSystem.get_instance()
                                        workplace_id = getattr(assigned_farm, "id", "farm")
                                        participating_workers = getattr(assigned_farm, "assigned_workers", [self.id])
                                        if not participating_workers:
                                            participating_workers = [self.id]

                                        crop_name = getattr(assigned_farm, "crop", "Potato") or "Potato"
                                        dist_res = ps.distribute_production(
                                            resource_name=crop_name,
                                            amount=yield_amt,
                                            participating_workers=participating_workers,
                                            furniture_manager=furniture_manager,
                                            stockpile_manager=stockpile_manager,
                                            permit_manager=permit_manager,
                                            villager_manager=villager_manager,
                                            workplace_id=workplace_id,
                                            day_number=day_cycle.day_number if day_cycle else 1,
                                            auto_deposit=False
                                        )

                                        distribution = dist_res.get("distribution", {})
                                        my_fam_str = str(self.family_id)
                                        my_share = distribution.get(my_fam_str, 0)

                                        # Auto-deposit shares for other participating households directly into their household chests
                                        for other_fam_id, other_qty in distribution.items():
                                            if other_fam_id != my_fam_str and other_qty > 0:
                                                ps.deposit_to_household_storage(
                                                    other_fam_id, crop_name, other_qty,
                                                    furniture_manager=furniture_manager,
                                                    stockpile_manager=stockpile_manager,
                                                    permit_manager=permit_manager,
                                                    villager_manager=villager_manager
                                                )

                                        # Harvester carries own household's share home
                                        self.carrying_crop = my_share
                                        if my_share > 0:
                                            self.inventory[crop_name] = self.inventory.get(crop_name, 0) + my_share
                                            self.active_tool = None
                                            self.say(f"Reaped {yield_amt} ripe {crop_name.lower()}s with sickle!", duration=2.2)
                                        else:
                                            self.active_tool = None
                                            self.say(f"Harvested {yield_amt} for co-workers!", duration=2.0)
                                return

                    # B. Nyangkul & Menanam Benih menggunakan CANGKUL (Hoe)
                    # 1 Tile membutuhkan 1 jam in-game labor
                    untilled_tiles = assigned_farm.get_untilled_tiles()
                    if untilled_tiles:
                        if self.inventory.get("Hoe", 0) <= 0:
                            # Jika tidak memegang cangkul, cek apakah bisa menyiram dengan watering can yang ada
                            can_water = assigned_farm.get_unwatered_tiles() and self.inventory.get("Watering_Can", 0) > 0
                            if not can_water:
                                if not self._family_has_tool("Hoe", furniture_manager, stockpile_manager):
                                    self.task = "MISSING_TOOL"
                                    self.active_tool = None
                                    if self.current_work_tile:
                                        assigned_farm.release_worker_reservations(self.id)
                                        self.current_work_tile = None
                                    if not self.speech_text and random.random() < 0.05:
                                        self.say("I need a Hoe to till the farm, Lord! Please grant our household a Hoe.", duration=3.0)
                                else:
                                    self.task = "EQUIPPING_JOB_TOOLS"
                                    self.active_tool = None
                                return
                        else:
                            self.active_tool = "Hoe"

                            target_t = None
                            if self.current_work_tile and self.task == "TILLING":
                                if self.current_work_tile in untilled_tiles and not assigned_farm.is_tile_reserved(self.current_work_tile[0], self.current_work_tile[1], exclude_worker_id=self.id):
                                    target_t = self.current_work_tile
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "TILL")
                                else:
                                    assigned_farm.release_tile_reservation(self.current_work_tile[0], self.current_work_tile[1], self.id)
                                    self.current_work_tile = None

                            if not target_t:
                                avail_untilled = assigned_farm.get_available_untilled_tiles(worker_id=self.id)
                                if avail_untilled:
                                    target_t = self._select_dispersed_tile(avail_untilled, assigned_farm, all_entities=all_entities)
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "TILL")
                                    self.current_work_tile = target_t

                            if target_t:
                                self.task = "TILLING"
                                tx = (target_t[0] + 0.5) * TILE_SIZE
                                ty = (target_t[1] + 0.5) * TILE_SIZE
                                arrived = self._move_towards(tx, ty, dt, arrival_dist=FARM_TILE_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                                if arrived:
                                    self.tilling_timer += dt
                                    tilling_target_time = one_in_game_hour * TILLING_DURATION_INGAME_HOURS
                                    if self.tilling_timer >= tilling_target_time:
                                        assigned_farm.till_and_sow_tile(target_t[0], target_t[1])
                                        assigned_farm.release_tile_reservation(target_t[0], target_t[1], self.id)
                                        self.tilling_timer = 0.0
                                        self.current_work_tile = None
                                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                                        self.say("Finished tilling & sowing tile (1h labor completed)!", duration=1.5)
                                return

                    # C. Menyiram petak ladang menggunakan SIRAMAN (Watering Can)
                    unwatered_tiles = assigned_farm.get_unwatered_tiles()
                    if unwatered_tiles:
                        if self.inventory.get("Watering_Can", 0) <= 0:
                            if not self._family_has_tool("Watering_Can", furniture_manager, stockpile_manager):
                                self.task = "MISSING_TOOL"
                                self.active_tool = None
                                if self.current_work_tile:
                                    assigned_farm.release_worker_reservations(self.id)
                                    self.current_work_tile = None
                                    GlobalPathRegistry.get_instance().release_reservation(self.id)
                                if not self.speech_text and random.random() < 0.05:
                                    self.say("I need a Watering Can to water crops, Lord! Please grant our household one.", duration=3.0)
                            else:
                                self.task = "EQUIPPING_JOB_TOOLS"
                                self.active_tool = None
                            return
                        else:
                            self.active_tool = "Watering_Can"

                            # Syarat Wajib: Ambil air dari SUMUR (Well) jika belum punya air untuk hari ini
                            if not self.has_water or self.water_day != current_day:
                                self.task = "FETCHING_WATER"
                                well = self._find_nearest_well(building_manager)
                                if well:
                                    # Hitung titik pendekatan terdistribusi di perimeter Well
                                    if hasattr(well, "get_approach_point"):
                                        try:
                                            approach_pt = well.get_approach_point(self.x, self.y, worker_id=self.id, all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                                        except TypeError:
                                            approach_pt = well.get_approach_point((self.x, self.y), TILE_SIZE, building_manager)
                                    else:
                                        approach_pt = well.get_center_world(TILE_SIZE)

                                    min_dist = float('inf')
                                    for (gx, gy) in well.tiles:
                                        t_rect = pygame.Rect(gx * TILE_SIZE, gy * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                                        cx = max(t_rect.left, min(self.x, t_rect.right))
                                        cy = max(t_rect.top, min(self.y, t_rect.bottom))
                                        d = math.hypot(self.x - cx, self.y - cy)
                                        if d < min_dist:
                                            min_dist = d

                                    # Kontak dengan salah satu petak Well (toleransi 28px dari tepi petak atau berada pada tile adjacent)
                                    cur_vgx = int(math.floor(self.x / TILE_SIZE))
                                    cur_vgy = int(math.floor(self.y / TILE_SIZE))
                                    is_adjacent_tile = any(abs(cur_vgx - gx) <= 1 and abs(cur_vgy - gy) <= 1 for (gx, gy) in well.tiles)
                                    arrived_well = (min_dist <= (self.radius + 28.0)) or is_adjacent_tile
                                    if not arrived_well and approach_pt:
                                        self._move_towards(approach_pt[0], approach_pt[1], dt, arrival_dist=self.radius + 8.0, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
                                        new_d = math.hypot(self.x - approach_pt[0], self.y - approach_pt[1])
                                        cur_vgx = int(math.floor(self.x / TILE_SIZE))
                                        cur_vgy = int(math.floor(self.y / TILE_SIZE))
                                        is_adjacent_tile = any(abs(cur_vgx - gx) <= 1 and abs(cur_vgy - gy) <= 1 for (gx, gy) in well.tiles)
                                        if new_d <= (self.radius + 28.0) or is_adjacent_tile:
                                            arrived_well = True

                                    if arrived_well:
                                        self.is_moving = False
                                        self.current_path = []
                                        self.path_index = 0
                                        self.path_target = None
                                        self.path_target_tile = None
                                        self.is_waiting_for_path = False
                                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                                        self.well_draw_timer += dt
                                        if self.well_draw_timer >= 0.6:
                                            self.has_water = True
                                            self.water_day = current_day
                                            self.water_charges = 9999  # Cukup untuk seluruh hari ini
                                            self.well_draw_timer = 0.0
                                            self.say("Drew a full day's supply of water from the Well!", duration=2.0)
                                    return
                                else:
                                    if not self.speech_text and random.random() < 0.05:
                                        self.say("We need a Well to draw water for crops, Lord! Please construct a Well.", duration=3.0)
                                    return

                            # Petani sudah memiliki air dari Well untuk hari ini: cari petak unwatered eksklusif
                            target_t = None
                            if self.current_work_tile and self.task == "WATERING":
                                if self.current_work_tile in unwatered_tiles and not assigned_farm.is_tile_reserved(self.current_work_tile[0], self.current_work_tile[1], exclude_worker_id=self.id):
                                    target_t = self.current_work_tile
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "WATER")
                                else:
                                    assigned_farm.release_tile_reservation(self.current_work_tile[0], self.current_work_tile[1], self.id)
                                    self.current_work_tile = None
                                    GlobalPathRegistry.get_instance().release_reservation(self.id)

                            if not target_t:
                                avail_unwatered = assigned_farm.get_available_unwatered_tiles(worker_id=self.id)
                                if avail_unwatered:
                                    target_t = self._select_dispersed_tile(avail_unwatered, assigned_farm, all_entities=all_entities)
                                    assigned_farm.reserve_tile(target_t[0], target_t[1], self.id, "WATER")
                                    self.current_work_tile = target_t

                            if target_t:
                                self.task = "WATERING"
                                tx = (target_t[0] + 0.5) * TILE_SIZE
                                ty = (target_t[1] + 0.5) * TILE_SIZE
                                arrived = self._move_towards(tx, ty, dt, arrival_dist=FARM_TILE_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                                if arrived:
                                    watering_target_time = one_in_game_hour * WATERING_DURATION_INGAME_HOURS
                                    self.watering_timer += dt
                                    if self.watering_timer >= watering_target_time:
                                        assigned_farm.water_tile(target_t[0], target_t[1])
                                        assigned_farm.release_tile_reservation(target_t[0], target_t[1], self.id)
                                        self.watering_timer = 0.0
                                        self.current_work_tile = None
                                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                                        self.say("Watered crop tile (30m labor completed)!", duration=1.5)
                                return

                    # Selesai seluruh garapan ladang hari ini atau seluruh tile sedang dikerjakan pekerja lain
                    if self.current_work_tile:
                        assigned_farm.release_worker_reservations(self.id)
                        self.current_work_tile = None
                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                    self.active_tool = None

        # -------------------------------------------------------------
        # Rutinitas 3: Waktu Santai / Istirahat (LEISURE / Chores Finished)
        # -------------------------------------------------------------
        self.task = "IDLE"
        self.active_tool = None

        # Evaluasi Kebutuhan Air Rumah Tangga (Household Water Shortage Check)
        if sched_activity in ("LEISURE", "ANY") and furniture_manager:
            chest = furniture_manager.get_storage_for_family(self.family_id)
            well = self._find_nearest_well(building_manager)
            if chest and well and self.hunger > AI_CRITICAL_NEED_THRESHOLD and self.thirst > AI_CRITICAL_NEED_THRESHOLD:
                fam_str = str(self.family_id)
                all_family_members = [e for e in all_entities if str(getattr(e, "family_id", "")) == fam_str and getattr(e, "is_alive", True)]
                living_count = len(all_family_members)
                if living_count > 0:
                    required_water = living_count * DAILY_WATER_REQUIREMENT
                    current_stock = chest.inventory.get("Water", 0)
                    if stockpile_manager:
                        for s in getattr(stockpile_manager, "stacks", []):
                            if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str and s.resource_type == "Water":
                                current_stock += getattr(s, "amount", 0)
                    shortage = required_water - current_stock
                    if shortage > 0:
                        active_collectors = sum(1 for m in all_family_members if getattr(m, "task", "") in ("COLLECTING_HOUSEHOLD_WATER", "HAULING_HOUSEHOLD_WATER"))
                        if active_collectors < min(HOUSEHOLD_WATER_MAX_COLLECTORS, shortage):
                            self.task = "COLLECTING_HOUSEHOLD_WATER"
                            self.water_collect_amount = min(VILLAGER_CARRY_CAPACITY, shortage)
                            self.well_draw_timer = 0.0
                            self.say("Collecting water for our household needs!", duration=2.5)
                            return

        self.idle_wander_timer -= dt
        if self.idle_wander_timer <= 0:
            self.idle_wander_timer = random.uniform(4.0, 8.0)

            if self.assigned_permit_id:
                home_b = self._get_home_building(permit_manager, building_manager)
                if home_b and random.random() < 0.60:
                    avail_tiles = [t for t in home_b.tiles if t != getattr(home_b, "door_pos", None)]
                    if getattr(home_b, "door_pos", None) and getattr(home_b, "door_side", None):
                        dx, dy = home_b.door_pos
                        adj_tile = (dx, dy + 1) if home_b.door_side == "top" else (
                                   (dx, dy - 1) if home_b.door_side == "bottom" else (
                                   (dx + 1, dy) if home_b.door_side == "left" else (dx - 1, dy)))
                        avail_tiles = [t for t in avail_tiles if t != adj_tile]
                    if not avail_tiles:
                        avail_tiles = list(home_b.tiles)
                    tile = random.choice(avail_tiles)
                    ang = ((hash(self.id) * 37) % 360) * (math.pi / 180.0)
                    rad = 6.0 + ((hash(self.id) * 11) % 10)
                    self.idle_target = ((tile[0] + 0.5) * TILE_SIZE + math.cos(ang) * rad,
                                        (tile[1] + 0.5) * TILE_SIZE + math.sin(ang) * rad)
                else:
                    p = next((p for p in permit_manager.permits if p.id == self.assigned_permit_id), None)
                    if p and p.tiles:
                        tile = random.choice(list(p.tiles))
                        ang = ((hash(self.id) * 37) % 360) * (math.pi / 180.0)
                        rad = 6.0 + ((hash(self.id) * 11) % 10)
                        self.idle_target = ((tile[0] + 0.5) * TILE_SIZE + math.cos(ang) * rad,
                                            (tile[1] + 0.5) * TILE_SIZE + math.sin(ang) * rad)
                    else:
                        self.idle_target = (self.x + random.uniform(-40, 40), self.y + random.uniform(-40, 40))
            else:
                # Natural scatter around Town Center
                ang = ((hash(self.id) * 47) % 360) * (math.pi / 180.0)
                rad = 50.0 + ((hash(self.id) * 19) % 45)
                self.idle_target = (math.cos(ang) * rad, math.sin(ang) * rad)

            if not self.speech_text and random.random() < 0.12:
                phrases = [
                    "Resting at home after watering crops.",
                    "Enjoying our family leisure time.",
                    "Checking our household supplies.",
                    "The crops are thriving nicely, Lord!"
                ] if self.assigned_permit_id else [
                    "Seeking land to farm, my Lord...",
                    "Awaiting the Landlord's deed assignment."
                ]
                self.say(random.choice(phrases), duration=2.5)

        self.is_waiting_for_path = False
        self._move_towards(self.idle_target[0], self.idle_target[1], dt, arrival_dist=16, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)

    def _move_towards(self, tx, ty, dt, arrival_dist=10, all_entities=None, player=None, building_manager=None, furniture_manager=None, exclusive_target=False):
        reg = GlobalPathRegistry.get_instance()

        # 0. Penanganan Antrean Menunggu Jalur (Waiting for Route Clearance)
        if self.wait_timer > 0.0:
            self.wait_timer -= dt
            self.is_moving = False
            # Jika jalur atau petak target sudah dibebaskan lebih awal, batalkan jeda tunggu
            if not reg.is_path_blocked_for(self.id, (self.x, self.y), (tx, ty)):
                self.wait_timer = 0.0
            else:
                return False

        if getattr(self, "repath_cooldown", 0.0) > 0.0:
            self.repath_cooldown -= dt

        # 1. Rute Predetermined Pathfinding A* (Jalur Garis yang Ditentukan)
        target_dist = math.hypot(tx - (self.path_target[0] if self.path_target else 999999),
                                 ty - (self.path_target[1] if self.path_target else 999999))
        needs_new_path = (self.path_target is None or target_dist > 18.0 or not self.current_path or self.path_index >= len(self.current_path))

        if needs_new_path:
            if getattr(self, "repath_cooldown", 0.0) > 0.0:
                self.is_moving = False
                return False

            self.path_target = (tx, ty)
            tgt_gx = int(math.floor(tx / TILE_SIZE))
            tgt_gy = int(math.floor(ty / TILE_SIZE))
            self.path_target_tile = (tgt_gx, tgt_gy)
            self.path_seq = reg.register_claim(self.id, self.path_target_tile)

            now = time.time()
            if hasattr(self, "stuck_blocked_tiles"):
                self.stuck_blocked_tiles = {t: exp for t, exp in self.stuck_blocked_tiles.items() if exp > now}
            else:
                self.stuck_blocked_tiles = {}

            avoid_set = set(self.stuck_blocked_tiles.keys())

            # Hindari target eksklusif milik AI lain (Hanya yang exclusive_target=True, misal ranjang atau petak ladang)
            for other_eid, other_res in reg.reservations.items():
                if other_eid != str(self.id) and getattr(other_res, "exclusive_target", False) and other_res.target_tile:
                    avoid_set.add(other_res.target_tile)

            # Hindari perabotan yang terpasang (Beds lain, Chest lain) kecuali target tujuan sendiri
            if furniture_manager and hasattr(furniture_manager, "get_occupied_tiles"):
                avoid_set.update(furniture_manager.get_occupied_tiles(exclude_tile=self.path_target_tile))

            # Hindari HANYA entitas lain yang sedang tidur di ranjang (rintangan fisik padat)
            if all_entities:
                for other in all_entities:
                    if other != self and getattr(other, "task", "") == "SLEEPING":
                        avoid_set.add((int(math.floor(other.x / TILE_SIZE)), int(math.floor(other.y / TILE_SIZE))))

            cur_gx = int(math.floor(self.x / TILE_SIZE))
            cur_gy = int(math.floor(self.y / TILE_SIZE))
            avoid_set.discard((cur_gx, cur_gy))
            avoid_set.discard(self.path_target_tile)

            # Celah pintu bangunan jangan pernah diblokir saat perancangan rute agar AI bisa mendekat
            if building_manager:
                for b in getattr(building_manager, "buildings", []):
                    if getattr(b, "door_pos", None):
                        avoid_set.discard(b.door_pos)

            if building_manager:
                cand_path = building_manager.find_path((self.x, self.y), (tx, ty), TILE_SIZE, furniture_manager=furniture_manager, avoid_tiles=avoid_set)
            else:
                cand_path = [(tx, ty)]

            if cand_path:
                success, res_or_conf = reg.request_path_reservation(self.id, cand_path, (self.x, self.y), self.path_target_tile, building_manager=building_manager, exclusive_target=exclusive_target)
                if success:
                    self.current_path = cand_path
                    self.path_index = 0
                    self.path_seq = res_or_conf.seq
                    self.is_waiting_for_path = False
                    self.wait_timer = 0.0
                    self.repath_cooldown = 0.0
                else:
                    # Ada konflik celah pintu / target yang sedang dipakai AI lain -> Masuk antrean menunggu
                    self.current_path = []
                    self.path_index = 0
                    self.is_moving = False
                    has_blocker = any(c[1] in ("DOORWAY_CONFLICT", "DOORWAY_THRESHOLD_JAM", "TARGET_CONFLICT", "QUEUE_PRIORITY") for c in res_or_conf) if isinstance(res_or_conf, list) else False
                    if exclusive_target or has_blocker:
                        self.is_waiting_for_path = True
                        self.wait_timer = PATH_WAIT_RECHECK_INTERVAL
                        reg.register_waiting(self.id, self.path_target_tile)
                    else:
                        self.is_waiting_for_path = False
                        self.wait_timer = 0.3
                    return False
            else:
                # Tidak ada jalur alternatif bebas rintangan
                self.current_path = []
                self.path_index = 0
                self.is_moving = False
                if exclusive_target:
                    self.is_waiting_for_path = True
                    self.wait_timer = PATH_WAIT_RECHECK_INTERVAL
                    reg.register_waiting(self.id, self.path_target_tile)
                else:
                    self.is_waiting_for_path = False
                    self.wait_timer = 0.4
                self.repath_cooldown = 0.4
                return False

        # 2. Prioritas Target Bersama:
        # "kalau kedua AI itu pathfindingnya ke tile yg sama, maka prioritaskan yg pertama pathfinding garisnya muncul"
        if not reg.has_priority(self.id, self.path_target_tile, self.path_seq, exclusive_target=exclusive_target):
            # Target telah diklaim lebih awal oleh AI lain!
            if getattr(self, "current_work_tile", None) == self.path_target_tile:
                # Pekerjaan ladang eksklusif: batalkan dan cari petak lain
                self.current_work_tile = None
                self.current_path = []
                self.path_index = 0
                self.is_moving = False
                reg.release_reservation(self.id)
                return False
            elif getattr(self, "target_loose_stack", None) and (getattr(self.target_loose_stack, "grid_x", None), getattr(self.target_loose_stack, "grid_y", None)) == self.path_target_tile:
                self.target_loose_stack = None
                self.current_path = []
                self.path_index = 0
                self.is_moving = False
                reg.release_reservation(self.id)
                return False

        # 3. Yielding Pause (Mengalah jika sedang berpapasan dengan entitas berprioritas lebih tinggi)
        if getattr(self, "yield_timer", 0.0) > 0.0:
            self.yield_timer -= dt
            self.is_moving = False
            return False

        if not self.current_path or self.path_index >= len(self.current_path):
            self.is_moving = False
            return False

        # 4. Melangkah Mengikuti Waypoint Jalur Garis & Update Reservasi
        target_wp = self.current_path[self.path_index]
        wp_dx = target_wp[0] - self.x
        wp_dy = target_wp[1] - self.y
        dist_to_wp = math.hypot(wp_dx, wp_dy)
        is_last_wp = (self.path_index == len(self.current_path) - 1)
        tol = arrival_dist if is_last_wp else PATH_WAYPOINT_TOLERANCE

        if dist_to_wp <= tol:
            if is_last_wp:
                # Tiba di tujuan akhir -> Bebaskan seluruh reservasi rute untuk AI lain
                self.is_moving = False
                self.current_path = []
                self.path_index = 0
                self.path_target = None
                self.is_waiting_for_path = False
                reg.release_reservation(self.id)
                if building_manager:
                    for b in getattr(building_manager, "buildings", []):
                        b.release_door_passage(self.id)
                return True
            else:
                self.path_index += 1
                if self.path_index >= len(self.current_path):
                    self.is_moving = False
                    self.current_path = []
                    self.path_index = 0
                    self.path_target = None
                    self.is_waiting_for_path = False
                    reg.release_reservation(self.id)
                    if building_manager:
                        for b in getattr(building_manager, "buildings", []):
                            b.release_door_passage(self.id)
                    return True
                target_wp = self.current_path[self.path_index]
                wp_dx = target_wp[0] - self.x
                wp_dy = target_wp[1] - self.y
                dist_to_wp = math.hypot(wp_dx, wp_dy)

        if dist_to_wp < 0.001:
            return False

        self.is_moving = True
        dir_x = wp_dx / dist_to_wp
        dir_y = wp_dy / dist_to_wp

        # Perbarui geometri segmen reservasi di GlobalPathRegistry (menyusutkan rute yang sudah dilewati)
        reg.update_entity_progress(self.id, (self.x, self.y), self.current_path, self.path_index)

        # 5. Antrean Celah Pintu (Doorway Approach & Transit Queueing)
        cur_gx = int(math.floor(self.x / TILE_SIZE))
        cur_gy = int(math.floor(self.y / TILE_SIZE))
        b_at = building_manager.get_building_at(cur_gx, cur_gy) if building_manager else None
        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if not getattr(b, "door_pos", None):
                    continue
                d_out = b.get_door_world_outside(TILE_SIZE)
                d_in = b.get_door_world_inside(TILE_SIZE)
                dist_out = math.hypot(self.x - d_out[0], self.y - d_out[1])
                dist_in = math.hypot(self.x - d_in[0], self.y - d_in[1])
                near_door = dist_out < 64.0 or dist_in < 64.0 or b.is_in_door_threshold(self.x, self.y, TILE_SIZE)

                if near_door:
                    tar_gx = int(math.floor(tx / TILE_SIZE))
                    tar_gy = int(math.floor(ty / TILE_SIZE))
                    b_tgt = building_manager.get_building_at(tar_gx, tar_gy)
                    crosses_door = (b_at != b and b_tgt == b) or (b_at == b and b_tgt != b) or \
                                   (getattr(self, "door_waypoints", None) and any(b.occupies_tile(int(wp[0]//TILE_SIZE), int(wp[1]//TILE_SIZE)) for wp in self.door_waypoints)) or \
                                   (self.current_path and any(b.occupies_tile(int(wp[0]//TILE_SIZE), int(wp[1]//TILE_SIZE)) for wp in self.current_path[self.path_index:]))
                    if crosses_door:
                        door_phys = building_manager.is_door_occupied(b.door_pos, all_entities, exclude_entity=self, tile_size=TILE_SIZE)
                        is_outside = (dist_out <= dist_in) and not b.occupies_tile(cur_gx, cur_gy)
                        can_pass, q_pos = b.request_door_passage(self.id, is_outside, tile_size=TILE_SIZE)
                        if door_phys or (not can_pass and q_pos):
                            # Pintu sedang aktif dipakai AI lain -> Menunggu di posisi antrean dekat pintu
                            self.is_waiting_for_path = True
                            self.is_moving = False
                            return False
                        else:
                            self.is_waiting_for_path = False
                else:
                    if b.door_active_user == str(self.id):
                        b.release_door_passage(self.id)

        # 6. Menghindari Tabrakan Antar Karakter (Yielding Right of Way tanpa terdorong ke tembok)
        if all_entities:
            for other in all_entities:
                if other == self:
                    continue
                ox = other.x - self.x
                oy = other.y - self.y
                o_dist = math.hypot(ox, oy)
                min_sep = (self.radius + getattr(other, "radius", 20.0) + 6.0)
                if 0.0 < o_dist < min_sep:
                    dot = dir_x * (ox / o_dist) + dir_y * (oy / o_dist)
                    if dot > 0.65:
                        other_seq = getattr(other, "path_seq", float('inf'))
                        if other_seq < self.path_seq:
                            # Entitas lain memiliki hak jalan (jalur garisnya muncul lebih dulu) -> mengalah sejenak
                            self.yield_timer = 0.25
                            self.is_moving = False
                            return False

        # 7. Pergerakan Fisik dengan Substepping & Resolusi Benturan Dinding
        old_x, old_y = self.x, self.y
        total_dist = self.speed * dt
        max_step_dist = 6.0
        num_steps = max(1, math.ceil(total_dist / max_step_dist))
        sub_dt = dt / num_steps

        for _ in range(num_steps):
            old_step_x, old_step_y = self.x, self.y
            self.x += dir_x * self.speed * sub_dt
            self.y += dir_y * self.speed * sub_dt
            if building_manager:
                self.x, self.y = building_manager.resolve_collision(self.x, self.y, self.radius, TILE_SIZE, old_x=old_step_x, old_y=old_step_y)

        # 8. Stuck Detection & Dynamic Obstacle Recovery
        actual_moved = math.hypot(self.x - old_x, self.y - old_y)
        expected_moved = self.speed * dt * 0.20

        if actual_moved < expected_moved and dist_to_wp > tol:
            self.stuck_timer += dt
            if self.stuck_timer >= STUCK_THRESHOLD_SECONDS:
                cur_gx = int(math.floor(self.x / TILE_SIZE))
                cur_gy = int(math.floor(self.y / TILE_SIZE))
                blocked_gx = int(math.floor((self.x + dir_x * 24.0) / TILE_SIZE))
                blocked_gy = int(math.floor((self.y + dir_y * 24.0) / TILE_SIZE))

                now = time.time()
                self.stuck_blocked_tiles[(blocked_gx, blocked_gy)] = now + STUCK_AVOIDANCE_DURATION

                # Nudge ke arah tengah petak saat ini agar tidak lengket pada dinding/kolider
                center_x = (cur_gx + 0.5) * TILE_SIZE
                center_y = (cur_gy + 0.5) * TILE_SIZE
                nudge_dx = center_x - self.x
                nudge_dy = center_y - self.y
                nudge_dist = math.hypot(nudge_dx, nudge_dy)
                if nudge_dist > 0.1:
                    self.x += (nudge_dx / nudge_dist) * min(4.0, nudge_dist)
                    self.y += (nudge_dy / nudge_dist) * min(4.0, nudge_dist)

                # Batalkan rute lama dan bebaskan reservasi
                reg.release_reservation(self.id)
                self.current_path = []
                self.path_index = 0
                self.stuck_timer = 0.0

                avoid_set = set(self.stuck_blocked_tiles.keys())
                avoid_set.update(reg.get_all_reserved_tiles(exclude_entity=self.id))
                if furniture_manager and hasattr(furniture_manager, "get_occupied_tiles"):
                    avoid_set.update(furniture_manager.get_occupied_tiles(exclude_tile=self.path_target_tile))
                cur_gx = int(math.floor(self.x / TILE_SIZE))
                cur_gy = int(math.floor(self.y / TILE_SIZE))
                avoid_set.discard((cur_gx, cur_gy))
                avoid_set.discard(self.path_target_tile)

                if building_manager:
                    cand_path = building_manager.find_path((self.x, self.y), (tx, ty), TILE_SIZE, furniture_manager=furniture_manager, avoid_tiles=avoid_set)
                    if cand_path:
                        success, res = reg.request_path_reservation(self.id, cand_path, (self.x, self.y), self.path_target_tile)
                        if success:
                            self.current_path = cand_path
                return False
        else:
            self.stuck_timer = max(0.0, self.stuck_timer - dt * 2.0)

        self.facing_angle = math.atan2(dir_y, dir_x)
        self.walk_cycle += dt * 10.0
        return False

    def draw(self, surface, camera, font_bubble):
        sx, sy = camera.world_to_screen(self.x, self.y)
        r = max(4, int(self.radius * camera.zoom))

        if not getattr(self, "is_alive", True):
            # Render Deceased Corpse (Fallen pose, desaturated grey)
            shadow_w = int(r * 2.2)
            shadow_h = max(2, int(r * 0.9))
            shadow_surf = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow_surf, COLOR_SHADOW, (0, 0, shadow_w, shadow_h))
            surface.blit(shadow_surf, (sx - shadow_w // 2, sy + int(r * 0.2)))

            corpse_w = int(r * 2.0)
            corpse_h = max(3, int(r * 1.1))
            corpse_rect = pygame.Rect(sx - corpse_w // 2, sy - corpse_h // 2, corpse_w, corpse_h)
            pygame.draw.ellipse(surface, COLOR_CORPSE_BODY, corpse_rect)
            outline_w = max(1, int(2 * camera.zoom))
            pygame.draw.ellipse(surface, COLOR_CORPSE_OUTLINE, corpse_rect, outline_w)

            eye_x = sx + int(corpse_w * 0.25)
            eye_y = sy - 2
            eye_size = max(2, int(3 * camera.zoom))
            pygame.draw.line(surface, (255, 255, 255), (eye_x - eye_size, eye_y - eye_size), (eye_x + eye_size, eye_y + eye_size), 1)
            pygame.draw.line(surface, (255, 255, 255), (eye_x - eye_size, eye_y + eye_size), (eye_x + eye_size, eye_y - eye_size), 1)

            if font_bubble:
                rip_surf = font_bubble.render(f"[RIP] {self.first_name}", True, (203, 213, 225))
                surface.blit(rip_surf, (sx - rip_surf.get_width() // 2, sy - corpse_h - 10))
            return

        bob = math.sin(self.walk_cycle) * (2.2 * camera.zoom) if self.is_moving else 0.0
        char_y = sy + int(bob)

        # 1. Bayangan di tanah
        shadow_w = int(r * 1.8)
        shadow_h = max(2, int(r * 0.9))
        shadow_surf = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, COLOR_SHADOW, (0, 0, shadow_w, shadow_h))
        surface.blit(shadow_surf, (sx - shadow_w // 2, sy + int(r * 0.4)))

        # 2. Badan Karakter Villager (Peasant Forest Green Tunic)
        pygame.draw.circle(surface, COLOR_VILLAGER_BODY, (sx, char_y), r)
        outline_w = max(1, int(3 * camera.zoom))
        pygame.draw.circle(surface, COLOR_VILLAGER_OUTLINE, (sx, char_y), r, outline_w)

        # 3. Mata / Direction Pointer
        eye_dist = r * 0.55
        eye_x = sx + int(math.cos(self.facing_angle) * eye_dist)
        eye_y = char_y + int(math.sin(self.facing_angle) * eye_dist)
        eye_r = max(2, int(4 * camera.zoom))
        pygame.draw.circle(surface, (255, 255, 255), (eye_x, eye_y), eye_r)
        pygame.draw.circle(surface, COLOR_VILLAGER_OUTLINE, (eye_x, eye_y), eye_r, 1)

        # 4. Alat Kerja yang Sedang Dipegang (Cangkul / Siraman / Sickle)
        hand_dist = r * 0.85
        hx = sx + int(math.cos(self.facing_angle + 0.45) * hand_dist)
        hy = char_y + int(math.sin(self.facing_angle + 0.45) * hand_dist)

        active_t = getattr(self, "active_tool", None)
        if active_t == "Hoe":
            # Visual Cangkul: Gagang kayu + mata cangkul besi tegap
            shaft_len = int(15 * camera.zoom)
            end_x = hx + int(math.cos(self.facing_angle) * shaft_len)
            end_y = hy + int(math.sin(self.facing_angle) * shaft_len)
            pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
            # Mata cangkul tegak lurus
            blade_w = max(4, int(7 * camera.zoom))
            perp = self.facing_angle + math.pi / 2.0
            bx1 = end_x + int(math.cos(perp) * blade_w)
            by1 = end_y + int(math.sin(perp) * blade_w)
            bx2 = end_x - int(math.cos(perp) * (blade_w // 2))
            by2 = end_y - int(math.sin(perp) * (blade_w // 2))
            pygame.draw.line(surface, (100, 116, 139), (bx1, by1), (bx2, by2), max(2, int(4 * camera.zoom)))

        elif active_t == "Watering_Can":
            # Medieval Watering Pot (Chantepleure / copper & terracotta vessel)
            pot_r = max(4, int(5 * camera.zoom))
            # Earthen/burnished copper pot body
            pygame.draw.circle(surface, (180, 105, 55), (hx, hy), pot_r)
            pygame.draw.circle(surface, (120, 65, 30), (hx, hy), pot_r, 1)
            # Arched loop handle
            pygame.draw.arc(surface, (100, 50, 20), (hx - pot_r, hy - pot_r - 3, pot_r * 2, pot_r * 2), 0, math.pi, max(1, int(2 * camera.zoom)))
            # Angled copper spout
            spout_len = int(10 * camera.zoom)
            spout_x = hx + int(math.cos(self.facing_angle) * spout_len)
            spout_y = hy + int(math.sin(self.facing_angle) * spout_len)
            pygame.draw.line(surface, (160, 90, 45), (hx, hy - 1), (spout_x, spout_y), max(2, int(2 * camera.zoom)))
            # Perforated sprinkler brass rose at tip
            rose_r = max(2, int(3 * camera.zoom))
            pygame.draw.circle(surface, (217, 149, 44), (spout_x, spout_y), rose_r)
            # Water droplets falling from the sprinkler rose
            if getattr(self, "task", None) == "WATERING" or getattr(self, "watering_timer", 0) > 0:
                drop_x = spout_x + int(math.cos(self.facing_angle) * 5)
                drop_y = spout_y + int(math.sin(self.facing_angle) * 5)
                pygame.draw.circle(surface, (186, 230, 253), (drop_x, drop_y), max(1, int(2 * camera.zoom)))

        elif active_t == "Sickle":
            # Visual Sickle: Gagang kayu + bilah sabit melengkung
            pygame.draw.circle(surface, (180, 120, 70), (hx, hy), max(2, int(3 * camera.zoom)))
            arc_r = max(4, int(7 * camera.zoom))
            pygame.draw.arc(surface, (226, 232, 240), (hx - arc_r // 2, hy - arc_r, arc_r * 2, arc_r * 2), self.facing_angle, self.facing_angle + math.pi * 0.9, max(2, int(2 * camera.zoom)))

        elif active_t == "Hammer":
            # Visual Hammer: Gagang kayu + kepala palu besi tebal
            shaft_len = int(14 * camera.zoom)
            end_x = hx + int(math.cos(self.facing_angle) * shaft_len)
            end_y = hy + int(math.sin(self.facing_angle) * shaft_len)
            pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
            head_w = max(4, int(8 * camera.zoom))
            head_h = max(3, int(5 * camera.zoom))
            pygame.draw.rect(surface, (148, 163, 184), (end_x - head_w // 2, end_y - head_h // 2, head_w, head_h))

        # 5. Karung Hasil Panen Kentang jika sedang mengangkut (Hauling Crops)
        if getattr(self, "carrying_crop", 0) > 0:
            sack_dist = r * 0.95
            sack_x = sx + int(math.cos(self.facing_angle + 0.9) * sack_dist)
            sack_y = char_y + int(math.sin(self.facing_angle + 0.9) * sack_dist)
            sw = max(5, int(9 * camera.zoom))
            sh = max(5, int(8 * camera.zoom))
            pygame.draw.ellipse(surface, (180, 130, 70), (sack_x - sw // 2, sack_y - sh // 2, sw, sh))
            pygame.draw.ellipse(surface, (100, 60, 20), (sack_x - sw // 2, sack_y - sh // 2, sw, sh), 1)

        # 5.5. Miniatur perabotan yang sedang dipindahkan (Hauling Furniture)
        if getattr(self, "carrying_furniture", None):
            furn = self.carrying_furniture
            carry_dist = r * 1.05
            cx = sx + int(math.cos(self.facing_angle) * carry_dist)
            cy = char_y + int(math.sin(self.facing_angle) * carry_dist)
            fw = max(10, int(18 * camera.zoom))
            fh = max(8, int(14 * camera.zoom))
            pygame.draw.rect(surface, (140, 85, 40), (cx - fw // 2, cy - fh // 2, fw, fh), border_radius=2)
            pygame.draw.rect(surface, (230, 180, 70), (cx - fw // 2, cy - fh // 2, fw, fh), width=1, border_radius=2)
            if getattr(furn, "furniture_type", "") == "bed":
                pygame.draw.rect(surface, (59, 130, 246), (cx - fw // 2 + 2, cy - fh // 2 + 3, fw - 4, fh - 5))
            else:
                pygame.draw.rect(surface, (234, 179, 8), (cx - 2, cy - 2, 4, 4))

        # 6. Speech Bubble
        if self.speech_text and font_bubble:
            txt_surf = font_bubble.render(self.speech_text, True, (15, 23, 42))
            bw = txt_surf.get_width() + 16
            bh = txt_surf.get_height() + 10
            bx = sx - bw // 2
            by = char_y - r - bh - 8

            pygame.draw.rect(surface, (255, 255, 255), (bx, by, bw, bh), border_radius=8)
            pygame.draw.rect(surface, (15, 23, 42), (bx, by, bw, bh), width=2, border_radius=8)

            tail_points = [(sx - 4, by + bh), (sx + 4, by + bh), (sx, by + bh + 6)]
            pygame.draw.polygon(surface, (255, 255, 255), tail_points)
            pygame.draw.line(surface, (15, 23, 42), tail_points[0], tail_points[2], 2)
            pygame.draw.line(surface, (15, 23, 42), tail_points[1], tail_points[2], 2)

            surface.blit(txt_surf, (bx + 8, by + 5))


class Family:
    def __init__(self, family_id, surname, members=None, assigned_permit_id=None):
        self.id = family_id
        self.surname = surname
        self.members = members if members is not None else []
        self.assigned_permit_id = assigned_permit_id

    @property
    def member_count(self):
        return len(self.members)

    @property
    def living_members(self):
        return [m for m in self.members if getattr(m, "is_alive", True)]

    @property
    def living_member_count(self):
        return len(self.living_members)

    @property
    def daily_food_required(self):
        return self.living_member_count * DAILY_FOOD_REQUIREMENT

    @property
    def daily_water_required(self):
        return self.living_member_count * DAILY_WATER_REQUIREMENT

    def get_primary_needs_progress(self):
        """
        Returns (food_fulfilled_count, water_fulfilled_count, living_total)
        Food: y/x | Water: z/x
        Where:
        - x = number of living individuals in that household
        - y = living individuals who fulfilled daily food requirement
        - z = living individuals who fulfilled daily water requirement
        """
        living = self.living_members
        x = len(living)
        y = sum(1 for m in living if getattr(m, "daily_food_consumed", 0) >= DAILY_FOOD_REQUIREMENT)
        z = sum(1 for m in living if getattr(m, "daily_water_consumed", 0) >= DAILY_WATER_REQUIREMENT)
        return y, z, x

    def get_food_stock(self, furniture_manager=None, stockpile_manager=None):
        total = 0
        fam_str = str(self.id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and hasattr(chest, "inventory"):
                for it in ("Potato", "Food", "Bread"):
                    total += chest.inventory.get(it, 0)
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                    if s.resource_type in ("Potato", "Food", "Bread"):
                        total += getattr(s, "amount", 0)
        return total

    def get_water_stock(self, furniture_manager=None, stockpile_manager=None):
        total = 0
        fam_str = str(self.id)
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            if chest and hasattr(chest, "inventory"):
                total += chest.inventory.get("Water", 0)
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                    if s.resource_type == "Water":
                        total += getattr(s, "amount", 0)
        return total

    @property
    def generations_present(self):
        gens = sorted(list({m.generation for m in self.members}))
        return gens

    def get_generation_label(self):
        gens = self.generations_present
        if not gens:
            return "1 Gen"
        if len(gens) == 1:
            return f"{gens[0]} Generation"
        return f"{min(gens)}–{max(gens)} Generations ({len(gens)} Gens)"

    def assign_to_permit(self, permit_id, permit_manager, building_manager):
        self.assigned_permit_id = permit_id
        p = next((p for p in permit_manager.permits if p.id == permit_id), None)
        if not p:
            return

        # Find center or entrance of permit
        home_x = (p.grid_x + (p.tiles_w / 2.0)) * TILE_SIZE
        home_y = (p.grid_y + (p.tiles_h / 2.0)) * TILE_SIZE

        for m in self.members:
            m.set_home_permit(permit_id, home_x, home_y)

    def unassign_permit(self):
        self.assigned_permit_id = None
        for m in self.members:
            m.assigned_permit_id = None
            m.idle_target = (random.uniform(-40, 40), random.uniform(-40, 40))
            m.idle_wander_timer = random.uniform(8.0, 12.0)
            m.say("Deed revoked. Walking back to Town Center, Lord.", duration=3.0)


class VillagerManager:
    def __init__(self):
        self.families = []
        self.family_counter = 1
        self.villager_counter = 1
        self.font_bubble = None

    def _ensure_font(self):
        if self.font_bubble is None:
            self.font_bubble = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def get_all_villagers(self):
        all_v = []
        for f in self.families:
            all_v.extend(f.members)
        return all_v

    def get_family_by_id(self, fam_id):
        if fam_id is None:
            return None
        for f in self.families:
            if str(f.id) == str(fam_id):
                return f
        return None

    def ensure_unique_family_ids(self):
        """Menjamin setiap keluarga memiliki ID yang unik dan tidak bertabrakan"""
        seen = set()
        for f in self.families:
            if str(f.id) in seen:
                while f"fam_{self.family_counter}" in seen:
                    self.family_counter += 1
                new_id = f"fam_{self.family_counter}"
                self.family_counter += 1
                f.id = new_id
                for m in f.members:
                    m.family_id = new_id
            seen.add(str(f.id))

    def generate_random_family(self):
        """Generates a randomized family with 1-3 adult generations (min 2 members: Male & Female)"""
        used_ids = {str(f.id) for f in self.families}
        while f"fam_{self.family_counter}" in used_ids:
            self.family_counter += 1
        fam_id = f"fam_{self.family_counter}"
        self.family_counter += 1

        used_surnames = {f.surname for f in self.families}
        avail_surnames = [s for s in VILLAGER_SURNAMES if s not in used_surnames] or VILLAGER_SURNAMES
        surname = random.choice(avail_surnames)

        members = []
        num_gens = random.choice([1, 2, 3])

        # Generation 1: Grandparents (Ages 60-76)
        has_gen1 = (num_gens == 3) or (num_gens == 2 and random.random() < 0.4)
        # Generation 2: Parents (Ages 38-52) - always present as the core couple
        has_gen2 = True
        # Generation 3: Adult Offspring (Ages 18-25)
        has_gen3 = (num_gens == 3) or (num_gens == 2 and not has_gen1) or (num_gens == 1 and random.random() < 0.25)

        # Core Gen 2 Couple (Father & Mother)
        f_name = random.choice(VILLAGER_MALE_NAMES)
        m_name = random.choice(VILLAGER_FEMALE_NAMES)

        father = Villager(
            f"vil_{self.villager_counter}", f_name, surname, "Male",
            random.randint(40, 52), 2, "Father", fam_id,
            x=random.uniform(-40, 40), y=random.uniform(-40, 40)
        )
        self.villager_counter += 1

        mother = Villager(
            f"vil_{self.villager_counter}", m_name, surname, "Female",
            random.randint(38, 50), 2, "Mother", fam_id,
            x=random.uniform(-40, 40), y=random.uniform(-40, 40)
        )
        self.villager_counter += 1
        members.extend([father, mother])

        # Add Gen 1 Grandparents if selected
        if has_gen1:
            gf_name = random.choice([n for n in VILLAGER_MALE_NAMES if n != f_name])
            gm_name = random.choice([n for n in VILLAGER_FEMALE_NAMES if n != m_name])

            gfather = Villager(
                f"vil_{self.villager_counter}", gf_name, surname, "Male",
                random.randint(64, 76), 1, "Grandfather", fam_id,
                x=random.uniform(-50, 50), y=random.uniform(-50, 50)
            )
            self.villager_counter += 1

            gmother = Villager(
                f"vil_{self.villager_counter}", gm_name, surname, "Female",
                random.randint(62, 74), 1, "Grandmother", fam_id,
                x=random.uniform(-50, 50), y=random.uniform(-50, 50)
            )
            self.villager_counter += 1
            members.insert(0, gfather)
            members.insert(1, gmother)

        # Add Gen 3 Adult Offspring if selected
        if has_gen3:
            child_count = random.choice([1, 2])
            for _ in range(child_count):
                c_gender = random.choice(["Male", "Female"])
                c_role = "Adult Son" if c_gender == "Male" else "Adult Daughter"
                c_name_pool = VILLAGER_MALE_NAMES if c_gender == "Male" else VILLAGER_FEMALE_NAMES
                c_name = random.choice([n for n in c_name_pool if n not in [m.first_name for m in members]])

                child = Villager(
                    f"vil_{self.villager_counter}", c_name, surname, c_gender,
                    random.randint(18, 25), 3, c_role, fam_id,
                    x=random.uniform(-40, 40), y=random.uniform(-40, 40)
                )
                self.villager_counter += 1
                members.append(child)

        new_family = Family(fam_id, surname, members, assigned_permit_id=None)
        self.families.append(new_family)
        return new_family

    def assign_family_to_permit(self, family_id, permit_id, permit_manager, building_manager, furniture_manager=None):
        fam = self.get_family_by_id(family_id)
        if not fam:
            return False
        # Guard: Deed yang sudah dimiliki keluarga lain tidak boleh diambil kecuali direvoke terlebih dahulu
        other_fam = next((f for f in self.families if f.assigned_permit_id == permit_id and f.id != family_id), None)
        if other_fam:
            return False
        fam.assign_to_permit(permit_id, permit_manager, building_manager)
        if furniture_manager:
            furniture_manager.update_permit_ownership(permit_id, family_id)
        return True

    def unassign_family(self, family_id):
        fam = self.get_family_by_id(family_id)
        if fam:
            fam.unassign_permit()
            return True
        return False

    def update(self, dt, permit_manager, building_manager, all_servants, player, stockpile_manager=None, furniture_manager=None, day_cycle=None, schedule_manager=None, production_system=None):
        if furniture_manager and hasattr(furniture_manager, "set_managers"):
            furniture_manager.set_managers(building_manager=building_manager, permit_manager=permit_manager, villager_manager=self)
        all_vils = self.get_all_villagers()
        all_entities = list(all_vils)
        if all_servants:
            all_entities.extend(all_servants)

        for v in all_vils:
            v.update(dt, permit_manager, building_manager, all_entities, player, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, day_cycle=day_cycle, schedule_manager=schedule_manager, production_system=production_system, villager_manager=self)

        # Minimum personal space separation (MIN_ENTITY_SEPARATION gap) antar seluruh individu AI
        # Mencegah AI bertumpuk/bergerombol pada satu titik
        min_gap = MIN_ENTITY_SEPARATION
        old_vil_pos = [(v.x, v.y) for v in all_vils]
        old_serv_pos = [(s.x, s.y) for s in all_servants] if all_servants else []

        for i in range(len(all_vils)):
            v1 = all_vils[i]
            if not getattr(v1, "is_alive", True):
                continue
            for j in range(i + 1, len(all_vils)):
                v2 = all_vils[j]
                if not getattr(v2, "is_alive", True):
                    continue
                dx = v2.x - v1.x
                dy = v2.y - v1.y
                dist = math.hypot(dx, dy)
                min_dist = v1.radius + v2.radius + min_gap
                if dist < min_dist:
                    if dist <= 0.001:
                        # Jika tepat bertumpuk di titik yang sama, pisahkan ke arah sudut berlawanan
                        ang = (i * 1.57 + j)
                        dx = math.cos(ang) * 0.1
                        dy = math.sin(ang) * 0.1
                        dist = 0.1
                    overlap = min_dist - dist
                    nx, ny = dx / dist, dy / dist
                    push = overlap * 0.5
                    v1.x -= nx * push
                    v1.y -= ny * push
                    v2.x += nx * push
                    v2.y += ny * push

            # Personal space separation with servants
            if all_servants:
                for s in all_servants:
                    dx = s.x - v1.x
                    dy = s.y - v1.y
                    dist = math.hypot(dx, dy)
                    min_s_dist = v1.radius + s.radius + min_gap
                    if dist < min_s_dist:
                        if dist <= 0.001:
                            dx, dy = 0.1, 0.0
                            dist = 0.1
                        overlap = min_s_dist - dist
                        nx, ny = dx / dist, dy / dist
                        push = overlap * 0.5
                        v1.x -= nx * push
                        v1.y -= ny * push
                        s.x += nx * push
                        s.y += ny * push

            # Villager vs Player solid separation
            if player:
                dx = v1.x - player.x
                dy = v1.y - player.y
                p_dist = math.hypot(dx, dy)
                min_p_dist = player.radius + v1.radius + min_gap
                if p_dist < min_p_dist:
                    if p_dist <= 0.001:
                        dx, dy = 0.1, 0.0
                        p_dist = 0.1
                    overlap = min_p_dist - p_dist
                    v1.x += (dx / p_dist) * overlap
                    v1.y += (dy / p_dist) * overlap

        # Resolusi benturan dinding setelah relaksasi personal space (cegah tembus dinding saat berdesakan)
        if building_manager:
            for idx, v1 in enumerate(all_vils):
                ox, oy = old_vil_pos[idx]
                v1.x, v1.y = building_manager.resolve_collision(v1.x, v1.y, v1.radius, TILE_SIZE, old_x=ox, old_y=oy)
            if all_servants:
                for idx, s in enumerate(all_servants):
                    ox, oy = old_serv_pos[idx]
                    s.x, s.y = building_manager.resolve_collision(s.x, s.y, s.radius, TILE_SIZE, old_x=ox, old_y=oy)

    def daily_midnight_update(self, day_number):
        """
        At 00:00 in-game:
        - Evaluates daily consumption records for each individual.
        - If an individual failed to consume at least 1 food or 1 water, they die.
        - Dead AI receives status DECEASED, stops working, and remains as corpse.
        - Surviving living members reset daily consumption records for the new day.
        """
        for fam in self.families:
            for m in list(fam.living_members):
                food_ok = (getattr(m, "daily_food_consumed", 0) >= DAILY_FOOD_REQUIREMENT)
                water_ok = (getattr(m, "daily_water_consumed", 0) >= DAILY_WATER_REQUIREMENT)
                if not food_ok or not water_ok:
                    if not food_ok and not water_ok:
                        reason = "Starvation & Dehydration"
                    elif not food_ok:
                        reason = "Starvation"
                    else:
                        reason = "Dehydration"
                    m.die(reason=reason, day=day_number)
                else:
                    m.daily_food_consumed = 0
                    m.daily_water_consumed = 0

    def draw(self, surface, camera):
        self._ensure_font()
        for v in self.get_all_villagers():
            v.draw(surface, camera, self.font_bubble)

