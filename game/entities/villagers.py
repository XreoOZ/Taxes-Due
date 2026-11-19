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
    NAVIGATION_RETRY_INTERVAL,
    EMERGENCY_STUCK_TIMEOUT,
    EMERGENCY_COLLISION_BYPASS_DURATION,
    PATH_WAIT_RECHECK_INTERVAL,
    AI_NEED_MAX,
    AI_NEED_HUNGER_DECAY_PER_DAY,
    AI_NEED_THIRST_DECAY_PER_DAY,
    AI_NEED_TOILET_DECAY_PER_DAY,
    AI_NEED_TOILET_URGENT_THRESHOLD,
    AI_NEED_TOILET_RESTORE,
    AI_CRITICAL_NEED_THRESHOLD,
    AI_DEATH_COUNTDOWN_HOURS,
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
    COLOR_CORPSE_OUTLINE,
    CORPSE_CARRY_SPEED_RATIO,
    SCHEDULE_NON_WORK_TASKS,
    is_food_item,
    is_water_item,
    get_item_category,
    COLLISION_SLIDE_TANGENT_FACTOR,
    COLLISION_MIN_SEPARATION,
    COLLISION_SLIDE_SMOOTHING,
    ROUTE_REQUEST_TIMEOUT,
    ROUTE_MAX_RETRIES,
    ROUTE_RETRY_BACKOFF,
    ROUTE_FALLBACK_COOLDOWN,
    ROUTE_STATE_NONE,
    ROUTE_STATE_REQUESTED,
    ROUTE_STATE_PROCESSING,
    ROUTE_STATE_ASSIGNED,
    ROUTE_STATE_ACTIVE,
    ROUTE_STATE_COMPLETED,
    ROUTE_STATE_FAILED,
    DOORWAY_IDLE_MIN_DISTANCE,
    DOORWAY_QUEUE_LATERAL_OFFSET,
    TILE_OCCUPANCY_TIMEOUT,
    TILE_STEP_RESERVATION_TIMEOUT,
    NARROW_PASSAGE_WAIT_DISTANCE
)
from game.world.pathfinding import GlobalPathRegistry, calculate_collision_slide, is_narrow_passage_tile
from game.world.navigation import find_navigation_path, find_nearest_target
from game.systems.market_interface import request_market_food_purchase
from game.systems.market_purchasing import AIFoodPurchasingSystem, AIMarketPurchasingSystem
from game.systems.market_service import MarketService
from game.systems.currency import to_copper, normalize_wallet, from_copper, canonical_denomination
from game.systems.job_tool_system import (
    get_job_required_tools,
    get_missing_tools_for_worker,
    get_irrelevant_tools_in_inventory,
    collect_all_job_tools,
    deposit_irrelevant_tools,
    is_tool_item
)

class Villager:
    def __init__(self, villager_id, first_name, last_name, gender, age, generation, role, family_id=None, x=0.0, y=0.0):
        self.id = villager_id
        self.first_name = first_name
        self.last_name = last_name
        self.gender = gender
        self.age = age
        self.generation = generation  # 1: Grandparents, 2: Parents, 3: Adult Offspring
        self.role = role              # Grandfather, Grandmother, Father, Mother, Adult Son, Adult Daughter
        self.family_id = family_id if family_id is not None else "fam_default"
        if role in DEDICATED_JOBS:
            self.job = role
        elif role == "Peasant Farmer":
            self.job = "Farmer"
        elif role == "Village Builder":
            self.job = "Builder"
        elif role == "Village Priest":
            self.job = "Priest"
        elif role == "Cemetery Gravedigger":
            self.job = "Gravedigger"
        else:
            self.job = "Unassigned"           # Dedicated Job starts as Unassigned (Requirement 3)
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
        self.path_retry_timer = 0.0
        self.yield_timer = 0.0
        self.wait_timer = 0.0
        self.is_waiting_for_path = False
        self.stuck_timer = 0.0
        self.hard_stuck_timer = 0.0
        self.collision_bypass_timer = 0.0
        self.route_state = ROUTE_STATE_NONE
        self.route_request_timer = 0.0
        self.route_retry_count = 0

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

        # Needs & Bodily Hygiene System (Agent 1)
        self.hunger = float(AI_NEED_MAX)
        self.thirst = float(AI_NEED_MAX)
        self.need_toilet = float(AI_NEED_MAX)
        self.toilet_use_timer = 0.0
        self.target_toilet = None
        self.interrupted_task_state = None
        self.activity_description = None
        self.recovery_target_drop = None
        self.recovery_state = "APPROACHING_DROP"
        self.hunger_death_timer = None  # None when hunger > 0; float remaining in-game hours when hunger <= 0
        self.thirst_death_timer = None  # None when thirst > 0; float remaining in-game hours when thirst <= 0
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
        self.purchase_target_market_id = None
        self.purchase_food_item = None
        self.purchase_target_price = 0
        self.purchase_target_qty = 1

        # Agent 3: Toilet, Church, Priest & Cemetery / Gravedigger
        self.need_toilet = 100.0
        self.toilet_target_building = None
        self.toilet_timer = 0.0
        self.carrying_corpse_id = None
        self.carrying_corpse_name = None
        self.gravedigger_target_corpse_id = None
        self.gravedigger_target_grave_tile = None
        self.gravedigger_timer = 0.0
        self.burial_payment_target_corpse_id = None
        self.burial_payment_gravedigger_id = None
        self.target_restock_market = None
        self.target_restock_mat = None
        self.target_restock_qty = 0
        self.profession = self.job
        job_cfg = DEDICATED_JOBS.get(self.job, {})
        self.title = job_cfg.get("title", self.job)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def toilet(self):
        return getattr(self, "need_toilet", 100.0)

    @toilet.setter
    def toilet(self, val):
        self.need_toilet = float(val)

    @property
    def profession(self):
        return getattr(self, "job", "Farmer")

    @profession.setter
    def profession(self, val):
        self.job = val

    @property
    def title(self):
        if getattr(self, "_title", None):
            return self._title
        job_cfg = DEDICATED_JOBS.get(self.job, {})
        return job_cfg.get("title", self.job)

    @title.setter
    def title(self, val):
        self._title = val

    @property
    def activity(self):
        return self.get_current_activity()

    def get_current_activity(self):
        """Returns a concise, human-readable description of current AI activity."""
        if not getattr(self, "is_alive", True):
            return "DECEASED"
        if getattr(self, "activity_description", None):
            return self.activity_description

        task = getattr(self, "task", "IDLE")
        if getattr(self, "is_waiting_for_path", False):
            return "Waiting for path to clear"

        if task == "SEEKING_TOILET":
            if getattr(self, "toilet_use_timer", 0.0) > 0.0:
                return "Using Toilet"
            return "Walking to Toilet"
        elif task == "SEEKING_FOOD":
            if getattr(self, "purchase_target_market_id", None):
                return "Walking to Market to purchase Food"
            return "Seeking Food"
        elif task == "SEEKING_WATER":
            return "Walking to Water Well"
        elif task == "FETCHING_WATER":
            if getattr(self, "is_moving", False):
                return "Walking to Water Well"
            return "Drawing Water from Well"
        elif task == "TILLING":
            if getattr(self, "is_moving", False):
                return "Walking to Farm plot"
            elif getattr(self, "tilling_timer", 0.0) > 0.0:
                return "Tilling soil with Hoe"
            return "Tilling soil at Farm"
        elif task == "WATERING":
            if getattr(self, "is_moving", False):
                return "Walking to crop to water"
            elif getattr(self, "watering_timer", 0.0) > 0.0:
                return "Watering crops with Watering Can"
            return "Watering crops at Farm"
        elif task == "HARVESTING":
            if getattr(self, "is_moving", False):
                return "Walking to harvest crop"
            return "Harvesting crops with Sickle"
        elif task == "HAULING_HOME":
            return "Hauling harvest to household storage"
        elif task == "COLLECTING_HOUSEHOLD_WATER":
            if getattr(self, "is_moving", False):
                return "Walking to Water Well for household water"
            return "Drawing household water from Well"
        elif task == "HAULING_HOUSEHOLD_WATER":
            return "Carrying water to household storage"
        elif task == "EQUIPPING_JOB_TOOLS":
            return f"Equipping tools for {self.job}"
        elif task in ("BUYING_JOB_TOOLS_RETRIEVE_COINS", "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET", "BUYING_JOB_TOOLS_RETURN_HOME"):
            return "Buying required job tools"
        elif task == "RETURNING_TOOLS":
            return "Returning unused tools to storage"
        elif task == "MISSING_TOOL":
            return f"Waiting for required tool ({self.job})"
        elif task == "RECOVER_DEATH_ITEMS":
            if getattr(self, "recovery_state", "") == "DEPOSITING":
                return "Depositing recovered items to chest"
            elif getattr(self, "recovery_state", "") == "RETURNING_TO_CHEST":
                return "Carrying recovered items to household chest"
            return "Collecting dropped items of deceased family member"
        elif task == "PRAYING":
            return "Attending prayer at Church"
        elif task == "PREACHING":
            return "Conducting sermons and prayers"
        elif task == "DIGGING_GRAVE":
            if getattr(self, "is_moving", False):
                return "Walking to Cemetery grave"
            return "Digging grave with Hoe"
        elif task == "BURYING_CORPSE":
            if getattr(self, "is_moving", False):
                return "Walking to grave site"
            return "Burying deceased in Cemetery"
        elif task == "CARRYING_CORPSE":
            return "Transporting corpse to Cemetery"
        elif task == "WAITING_FOR_BURIAL_PAYMENT":
            return "Waiting for burial fee"
        elif task == "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE":
            return "Collecting burial fee from landlord storage"
        elif task in ("BURIAL_PAYMENT_RETRIEVE", "BURIAL_PAYMENT_TRAVEL"):
            return "Collecting or delivering household burial fee"
        elif task == "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS":
            return "Walking to household storage for grave supplies" if getattr(self, "is_moving", False) else "Preparing coins for grave supplies"
        elif task == "GRAVEDIGGER_RESTOCK_TRAVEL_TO_MARKET":
            return "Walking to market for grave supplies" if getattr(self, "is_moving", False) else "Buying grave supplies"
        elif task == "GRAVEDIGGER_RESTOCK_HAULING_HOME":
            return "Carrying grave supplies home"
        elif task == "HAULING_STALL_COINS_FETCH":
            return "Collecting market stall earnings"
        elif task == "HAULING_STALL_COINS_DELIVER":
            return "Depositing market stall coins to chest"
        elif task == "HAULING_STALL_GOODS_FETCH":
            return "Fetching allocated goods for market stall"
        elif task == "HAULING_STALL_GOODS_DELIVER":
            return "Hauling goods to market stall"
        elif task == "SLEEPING":
            if getattr(self, "assigned_bed_id", None):
                return "Sleeping in Bed"
            return "Resting on floor"
        elif task == "IDLE":
            if getattr(self, "is_moving", False):
                return "Wandering leisurely"
            return "Idling leisurely"
        else:
            return task.replace("_", " ").title()

    def set_activity(self, desc):
        self.activity_description = desc

    def interrupt_task(self, reason="URGENT_NEED", activity_label=None):
        """
        Captures full execution state of current task before interrupting for urgent needs.
        Preserves work tile reservations, tool state, and timers.
        """
        if self.task in ("IDLE", "DECEASED", "SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET", "RECOVER_DEATH_ITEMS"):
            return

        self.interrupted_task_state = {
            "task": self.task,
            "target_work_tile": self.current_work_tile,
            "active_tool": self.active_tool,
            "tilling_timer": self.tilling_timer,
            "watering_timer": self.watering_timer,
            "well_draw_timer": self.well_draw_timer,
            "carrying_crop": self.carrying_crop,
            "carrying_res": self.carrying_res,
            "carrying_amount": self.carrying_amount,
            "carrying_furniture": self.carrying_furniture,
            "interrupt_reason": reason,
            "interrupted_at": time.time()
        }
        if activity_label:
            self.activity_description = activity_label

    def resume_interrupted_task(self, permit_manager=None, building_manager=None):
        """
        Restores interrupted task if still valid; otherwise gracefully falls back to IDLE.
        """
        state = getattr(self, "interrupted_task_state", None)
        self.interrupted_task_state = None
        self.activity_description = None

        if not state:
            self.task = "IDLE"
            return False

        old_task = state.get("task")
        if not old_task or old_task in ("IDLE", "DECEASED"):
            self.task = "IDLE"
            return False

        tile = state.get("target_work_tile")
        if tile and permit_manager:
            farm = permit_manager.get_farm_permit_for_villager(self)
            if not farm or not farm.contains_tile(tile[0], tile[1]):
                self.task = "IDLE"
                return False

        self.task = old_task
        self.current_work_tile = state.get("target_work_tile")
        self.active_tool = state.get("active_tool")
        self.tilling_timer = state.get("tilling_timer", 0.0)
        self.watering_timer = state.get("watering_timer", 0.0)
        self.well_draw_timer = state.get("well_draw_timer", 0.0)
        self.carrying_crop = state.get("carrying_crop", 0)
        self.carrying_res = state.get("carrying_res")
        self.carrying_amount = state.get("carrying_amount", 0)
        self.carrying_furniture = state.get("carrying_furniture")
        return True

    def die(self, reason="Starvation", day=1, stockpile_manager=None, family=None):
        """Transition this villager to the DECEASED state (corpse) and drop 100% of personal inventory."""
        self.is_alive = False
        self.status = "DECEASED"
        self.death_reason = reason
        self.death_day = day
        self.task = "DECEASED"
        self.activity_description = "DECEASED"
        self.hunger_death_timer = None
        self.thirst_death_timer = None
        self.is_moving = False
        self.current_path = []
        self.path_target = None
        self.path_target_tile = None
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

        # Drop 100% of personal inventory at exact death location into stockpile_manager
        sm = stockpile_manager or getattr(self, "stockpile_manager", None)
        cur_gx = int(math.floor(self.x / TILE_SIZE))
        cur_gy = int(math.floor(self.y / TILE_SIZE))
        fam_str = str(self.family_id)

        if sm and hasattr(sm, "drop_resource"):
            for it_name, count in list(getattr(self, "inventory", {}).items()):
                if count > 0:
                    sm.drop_resource(it_name, count, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)
            if getattr(self, "active_tool", None) and self.inventory.get(self.active_tool, 0) == 0:
                sm.drop_resource(self.active_tool, 1, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)
            if getattr(self, "carrying_crop", 0) > 0:
                sm.drop_resource("Potato", self.carrying_crop, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)
            if getattr(self, "carrying_res", None) and getattr(self, "carrying_amount", 0) > 0:
                sm.drop_resource(self.carrying_res, self.carrying_amount, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)
            if hasattr(self, "currency") and isinstance(self.currency, dict):
                for denom in ("Copper", "Silver", "Gold"):
                    c_amt = self.currency.get(denom, 0)
                    if c_amt > 0 and denom not in self.inventory:
                        sm.drop_resource(denom, c_amt, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)

        self.inventory = {}
        self.active_tool = None
        self.carrying_crop = 0
        self.carrying_res = None
        self.carrying_amount = 0

        # Register death drop on household for recovery representative
        fam = family
        if fam is None and hasattr(self, "villager_manager") and self.villager_manager:
            fam = self.villager_manager.get_family_by_id(self.family_id)
        if fam and hasattr(fam, "register_death_drop"):
            fam.register_death_drop(self.id, cur_gx, cur_gy)

        self.say(f"Alas... ({reason})", duration=4.0)

    def _resume_or_idle_after_need(self):
        """Safely cleans up after fulfilling a critical need and resumes previously interrupted task."""
        self.need_seek_cooldown = 0.0
        self.previous_task_before_need = None
        if getattr(self, "interrupted_task_state", None):
            resumed = self.resume_interrupted_task(
                permit_manager=getattr(self, "permit_manager", None),
                building_manager=getattr(self, "building_manager", None)
            )
            if resumed:
                return
        self.task = "IDLE"


    def _idle_behavior(self, dt, player=None, all_entities=None, building_manager=None, furniture_manager=None):
        """Idle & wandering behavior, keeping clear from doorways."""
        # Pastikan target santai tidak berada di celah atau koridor pintu
        if building_manager and hasattr(building_manager, "is_near_any_door") and building_manager.is_near_any_door(self.idle_target[0], self.idle_target[1], min_dist=DOORWAY_IDLE_MIN_DISTANCE):
            for offset in (40.0, -40.0, 60.0, -60.0):
                cand_x = self.idle_target[0] + offset
                cand_y = self.idle_target[1] + offset
                if not building_manager.is_near_any_door(cand_x, cand_y, min_dist=DOORWAY_IDLE_MIN_DISTANCE):
                    self.idle_target = (cand_x, cand_y)
                    break

        # Bebaskan celah pintu jika tanpa sengaja berada di threshold saat idle
        if building_manager and hasattr(building_manager, "is_near_any_door") and building_manager.is_near_any_door(self.x, self.y, min_dist=32.0):
            for b in getattr(building_manager, "buildings", []):
                if b.door_pos and b.is_in_door_threshold(self.x, self.y, TILE_SIZE):
                    d_out = b.get_door_world_outside(TILE_SIZE)
                    n_dx = d_out[0] - self.x
                    n_dy = d_out[1] - self.y
                    n_dist = math.hypot(n_dx, n_dy)
                    if n_dist > 0.001:
                        step = max(2.0, self.speed * dt * 0.8)
                        self.x += (n_dx / n_dist) * step
                        self.y += (n_dy / n_dist) * step

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
        well, _, _ = find_nearest_target(
            (self.x, self.y), wells,
            lambda building: building.get_approach_point(
                self.x, self.y, worker_id=self.id, tile_size=TILE_SIZE, bm=building_manager
            ),
            building_manager=building_manager,
            furniture_manager=getattr(self, "furniture_manager", None),
            tile_size=TILE_SIZE,
        )
        return well

    def _find_nearest_household_item_source(self, matches_item, furniture_manager,
                                           stockpile_manager, building_manager,
                                           all_entities=None):
        """Choose the closest chest or ground stack holding a household item."""
        family_id = str(self.family_id)
        candidates = []
        chest = furniture_manager.get_storage_for_family(family_id) if furniture_manager else None
        if chest and isinstance(getattr(chest, "inventory", None), dict):
            candidates.extend(
                ("chest", chest, item_name)
                for item_name, amount in chest.inventory.items()
                if amount > 0 and matches_item(item_name)
            )
        if stockpile_manager:
            candidates.extend(
                ("ground", stack, stack.resource_type)
                for stack in getattr(stockpile_manager, "stacks", [])
                if getattr(stack, "owner_type", None) == "villager"
                and str(getattr(stack, "owner_id", "")) == family_id
                and getattr(stack, "amount", 0) > 0
                and matches_item(getattr(stack, "resource_type", ""))
            )
        if not candidates:
            return None, None

        def get_position(source):
            source_type, obj, _ = source
            if source_type == "chest":
                return obj.get_approach_point(
                    self.x, self.y, worker_id=self.id, all_entities=all_entities,
                    tile_size=TILE_SIZE, bm=building_manager,
                )
            return ((obj.grid_x + 0.5) * TILE_SIZE, (obj.grid_y + 0.5) * TILE_SIZE)

        source, position, _ = find_nearest_target(
            (self.x, self.y), candidates, get_position,
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            tile_size=TILE_SIZE,
        )
        return source, position

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

        # 4. Choose the nearest household-owned stack.
        nearest, _, _ = find_nearest_target(
            (self.x, self.y), avail_candidates,
            lambda stack: ((stack.grid_x + 0.5) * TILE_SIZE,
                           (stack.grid_y + 0.5) * TILE_SIZE),
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            tile_size=TILE_SIZE,
        )
        return nearest

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
        self.profession = new_job
        job_cfg = DEDICATED_JOBS.get(new_job, {})
        self.title = job_cfg.get("title", new_job)
        self.needs_tool_reassessment = True

        # Deposit irrelevant tools and collect missing tools if storage is accessible
        fm = getattr(self, "furniture_manager", None)
        sm = getattr(self, "stockpile_manager", None)
        if fm or sm:
            self.deposit_irrelevant_tools(fm, sm)

    def _get_unused_tools(self, assigned_farm=None, sched_activity=None):
        """
        Backward compatibility: mengembalikan alat yang tidak relevan atau berlebih.
        Alat yang relevan dengan pekerjaan TIDAK AKAN PERNAH dikembalikan ke peti hanya karena tidak dipakai sesaat.
        """
        return self.get_irrelevant_tools()

    def _find_tool_storage(self, furniture_manager, stockpile_manager, all_entities=None,
                           building_manager=None, required_items=None):
        """Mencari lokasi penyimpanan alat keluarga (peti atau tumpukan tanah)"""
        fam_str = str(self.family_id)
        required = set(required_items or ())
        candidates = []
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(fam_str)
            chest_has_needed_item = chest and (
                not required or any(chest.inventory.get(item, 0) > 0 for item in required)
            )
            if chest_has_needed_item:
                pos = chest.get_approach_point(
                    self.x, self.y, worker_id=self.id, all_entities=all_entities,
                    tile_size=TILE_SIZE, bm=building_manager,
                ) if hasattr(chest, "get_approach_point") else chest.get_world_pos(TILE_SIZE)
                candidates.append((pos, "chest", chest))
        if stockpile_manager:
            for s in stockpile_manager.stacks:
                if (getattr(s, "owner_type", None) == "villager"
                        and str(getattr(s, "owner_id", "")) == fam_str
                        and getattr(s, "amount", 0) > 0
                        and (not required or s.resource_type in required)):
                    pos = ((s.grid_x + 0.5) * TILE_SIZE, (s.grid_y + 0.5) * TILE_SIZE)
                    candidates.append((pos, "ground", s))
        if not required:
            return candidates[0] if candidates else (None, None, None)
        source, position, _ = find_nearest_target(
            (self.x, self.y), candidates,
            lambda candidate: candidate[0],
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            tile_size=TILE_SIZE,
        )
        if source:
            return position, source[1], source[2]
        return None, None, None

    def _collect_job_tools_from_source(self, source_type, source, stockpile_manager):
        """Collect only missing tools available at the storage location the worker reached."""
        collected = []
        for tool_name, count in self.get_missing_job_tools():
            if source_type == "chest":
                amount = source.take_item(tool_name, count)
            elif getattr(source, "resource_type", None) == tool_name and stockpile_manager:
                amount = stockpile_manager.take_from_stack(source, count)
            else:
                amount = 0
            if amount > 0:
                self.inventory[tool_name] = self.inventory.get(tool_name, 0) + amount
                collected.extend([tool_name] * amount)
        return collected

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

    def _get_unneeded_inventory(self):
        required_tools = get_job_required_tools(self.job)
        return {
            item: amount - required_tools.get(item, 0)
            for item, amount in self.inventory.items()
            if amount > required_tools.get(item, 0)
        }

    def _deposit_unneeded_inventory(self, dt, furniture_manager, all_entities,
                                    player, building_manager):
        chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
        if not chest:
            self.task = "IDLE"
            return False

        target = chest.get_approach_point(
            self.x, self.y, worker_id=self.id, all_entities=all_entities,
            tile_size=TILE_SIZE, bm=building_manager,
        )
        arrived = self._move_towards(
            target[0], target[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
        )
        if arrived:
            deposited = []
            for item, amount in self._get_unneeded_inventory().items():
                if amount <= 0:
                    continue
                chest.store_item(item, amount)
                self.inventory[item] -= amount
                if self.inventory[item] <= 0:
                    self.inventory.pop(item, None)
                deposited.append((item, amount))
            if deposited:
                summary = ", ".join(f"{amount}x {item}" for item, amount in deposited)
                self.say(f"Stored unused items in household chest: {summary}.", duration=2.5)
            self.task = "IDLE"
            self.active_tool = None
        return True

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

    def _execute_death_recovery_routine(self, dt, furniture_manager=None, stockpile_manager=None, all_entities=None, player=None, building_manager=None):
        drop = getattr(self, "recovery_target_drop", None)
        if not drop:
            self._resume_or_idle_after_need()
            return True

        gx = drop.get("gx", 0)
        gy = drop.get("gy", 0)
        state = getattr(self, "recovery_state", "APPROACHING_DROP")

        if state == "APPROACHING_DROP":
            target_x = (gx + 0.5) * TILE_SIZE
            target_y = (gy + 0.5) * TILE_SIZE
            self.set_activity("Collecting dropped items of deceased family member")
            arrived = self._move_towards(target_x, target_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                fam_str = str(self.family_id)
                collected = 0
                if stockpile_manager:
                    to_remove = []
                    for s in getattr(stockpile_manager, "stacks", []):
                        if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                            if abs(s.grid_x - gx) <= 1 and abs(s.grid_y - gy) <= 1:
                                res_type = s.resource_type
                                amt = s.amount
                                self.inventory[res_type] = self.inventory.get(res_type, 0) + amt
                                collected += amt
                                to_remove.append(s)
                    for s in to_remove:
                        if s in stockpile_manager.stacks:
                            stockpile_manager.stacks.remove(s)
                self.say("Gathered our fallen kin's possessions.", duration=2.0)
                self.recovery_state = "DEPOSITING"

        elif state == "DEPOSITING":
            self.set_activity("Depositing recovered items to chest")
            chest = furniture_manager.get_storage_for_family(str(self.family_id)) if furniture_manager else None
            if not chest:
                self.recovery_state = "APPROACHING_DROP"
                self._resume_or_idle_after_need()
                return True

            pos = chest.get_world_pos(TILE_SIZE) if hasattr(chest, "get_world_pos") else ((chest.grid_x + 0.5) * TILE_SIZE, (chest.grid_y + 0.5) * TILE_SIZE)
            arrived = self._move_towards(pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                job_required = DEDICATED_JOBS.get(self.job, {}).get("required_tools", [])
                for it_name, count in list(self.inventory.items()):
                    if count <= 0:
                        continue
                    keep = 1 if it_name in job_required else 0
                    to_deposit = count - keep
                    if to_deposit > 0:
                        if not hasattr(chest, "inventory") or not isinstance(chest.inventory, dict):
                            chest.inventory = {}
                        chest.inventory[it_name] = chest.inventory.get(it_name, 0) + to_deposit
                        self.inventory[it_name] = keep
                        if self.inventory[it_name] <= 0:
                            del self.inventory[it_name]

                vm = getattr(self, "villager_manager", None)
                if vm:
                    fam = vm.get_family_by_id(self.family_id)
                    if fam:
                        fam.complete_death_drop(drop.get("deceased_id"))

                self.recovery_target_drop = None
                self.recovery_state = "APPROACHING_DROP"
                self.say("Safely stored our kin's belongings in the chest.", duration=2.5)
                self._resume_or_idle_after_need()

        return True

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

        # Decay Hunger, Thirst, and Toilet according to in-game day cycle
        day_sec = day_cycle.day_length_seconds if day_cycle else 1200.0
        self.hunger = max(0.0, self.hunger - (AI_NEED_HUNGER_DECAY_PER_DAY / day_sec) * dt)
        self.thirst = max(0.0, self.thirst - (AI_NEED_THIRST_DECAY_PER_DAY / day_sec) * dt)
        self.need_toilet = max(0.0, getattr(self, "need_toilet", 100.0) - (AI_NEED_TOILET_DECAY_PER_DAY / day_sec) * dt)

        # -------------------------------------------------------------
        # 24-In-Game-Hour Death Countdown (0% Threshold ONLY)
        # -------------------------------------------------------------
        in_game_hours_passed = (dt / max(1.0, day_sec)) * 24.0

        # 1. Hunger Death Countdown
        if self.hunger <= 0.0:
            if getattr(self, "hunger_death_timer", None) is None:
                self.hunger_death_timer = float(AI_DEATH_COUNTDOWN_HOURS)
            self.hunger_death_timer = max(0.0, self.hunger_death_timer - in_game_hours_passed)
        else:
            self.hunger_death_timer = None

        # 2. Thirst Death Countdown
        if self.thirst <= 0.0:
            if getattr(self, "thirst_death_timer", None) is None:
                self.thirst_death_timer = float(AI_DEATH_COUNTDOWN_HOURS)
            self.thirst_death_timer = max(0.0, self.thirst_death_timer - in_game_hours_passed)
        else:
            self.thirst_death_timer = None

        # 3. Check for Death upon Unresolved Countdown Expiration (Reaches 0)
        cur_day = getattr(day_cycle, "day_number", 1) if day_cycle else 1
        h_expired = (self.hunger_death_timer is not None and self.hunger_death_timer <= 0.0)
        t_expired = (self.thirst_death_timer is not None and self.thirst_death_timer <= 0.0)

        if h_expired or t_expired:
            if h_expired and t_expired:
                reason = "Starvation & Dehydration"
            elif h_expired:
                reason = "Starvation"
            else:
                reason = "Dehydration"
            vm = villager_manager or getattr(self, "villager_manager", None)
            fam = vm.get_family_by_id(self.family_id) if vm else None
            self.die(reason=reason, day=cur_day, stockpile_manager=stockpile_manager, family=fam)
            return

        if market_service is not None:
            self.market_service = market_service
        self.building_manager = building_manager
        self.furniture_manager = furniture_manager
        if villager_manager is not None:
            self.villager_manager = villager_manager
        if stockpile_manager is not None:
            self.stockpile_manager = stockpile_manager

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

        from game.systems.cemetery_system import CemeterySystem
        if CemeterySystem.update_burial_payment_task(
            self, dt, building_manager, furniture_manager, stockpile_manager,
            all_entities, player,
        ):
            return

        # Finish an active task before honoring the next scheduled activity.
        # Cargo is also considered active work so older saves with a carried
        # corpse but an IDLE task resume correctly.
        has_pending_work = (
            self.task not in SCHEDULE_NON_WORK_TASKS
            or bool(getattr(self, "carrying_crop", 0))
            or bool(getattr(self, "carrying_res", None))
            or bool(getattr(self, "carrying_furniture", None))
            or bool(getattr(self, "carrying_corpse_id", None))
        )
        if has_pending_work:
            sched_activity = "WORK"

        # -------------------------------------------------------------
        # Rutinitas Kebutuhan Pokok: Critical Needs (<= 20%) & Evening Dinner
        # -------------------------------------------------------------
        is_crit_hunger = (self.hunger <= AI_CRITICAL_NEED_THRESHOLD)
        is_crit_thirst = (self.thirst <= AI_CRITICAL_NEED_THRESHOLD)
        is_crit_toilet = (self.need_toilet <= AI_NEED_TOILET_URGENT_THRESHOLD)
        is_dinner = (sched_activity == "LEISURE" and cur_hour >= 18.0)
        wants_food = (self.daily_food_consumed < DAILY_FOOD_REQUIREMENT and (is_crit_hunger or is_dinner))
        wants_water = (self.daily_water_consumed < DAILY_WATER_REQUIREMENT and (is_crit_thirst or is_dinner))

        # Critical interruption: Interupsi pekerjaan apa pun jika lapar, haus, atau toilet mencapai <= 20%
        if (is_crit_hunger or is_crit_thirst or is_crit_toilet):
            if self.task not in ("SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET", "BUYING_FOOD_RETRIEVE_COINS", "BUYING_FOOD_TRAVEL_TO_MARKET", "BUYING_FOOD_HAULING_HOME", "RECOVER_DEATH_ITEMS") and self.need_seek_cooldown <= 0.0:
                if is_crit_hunger or is_crit_thirst or is_crit_toilet or (sched_activity in ("LEISURE", "ANY") and self.task in ("IDLE", "LEISURE", "STROLLING")):
                    self.interrupt_task("CRITICAL_NEED")
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

                    if is_crit_toilet:
                        self.task = "SEEKING_TOILET"
                    elif is_crit_thirst or (self.thirst <= self.hunger):
                        self.task = "SEEKING_WATER"
                    else:
                        self.task = "SEEKING_FOOD"

        # Household food is a shared need: start a market purchase whenever its
        # configured daily stock is short, rather than waiting for hunger to become critical.
        food_purchase_tasks = (
            "SEEKING_FOOD",
            "BUYING_FOOD_RETRIEVE_COINS",
            "BUYING_FOOD_TRAVEL_TO_MARKET",
            "BUYING_FOOD_HAULING_HOME",
            "BUYING_JOB_TOOLS_RETRIEVE_COINS",
            "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET",
            "BUYING_JOB_TOOLS_RETURN_HOME",
            "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS",
            "GRAVEDIGGER_RESTOCK_TRAVEL_TO_MARKET",
            "GRAVEDIGGER_RESTOCK_HAULING_HOME",
        )
        if (sched_activity != "SLEEP" and self.task not in food_purchase_tasks
                and self.task not in ("SEEKING_WATER", "SEEKING_TOILET", "RECOVER_DEATH_ITEMS")
                and self.need_seek_cooldown <= 0.0):
            household_food_need = MarketService.get_household_food_need(
                self, furniture_manager=furniture_manager, villager_manager=villager_manager,
                stockpile_manager=stockpile_manager,
            )
            vm = getattr(self, "villager_manager", None) or villager_manager
            if (household_food_need > 0
                    and not AIFoodPurchasingSystem.is_family_member_purchasing_food(self, vm)):
                self.interrupt_task("HOUSEHOLD_FOOD_SHORTAGE")
                if self.current_work_tile and permit_manager:
                    farm = next((p for p in permit_manager.permits
                                 if p.permit_type == "farm" and self.id in getattr(p, "assigned_workers", [])), None)
                    if farm:
                        farm.release_worker_reservations(self.id)
                    self.current_work_tile = None
                GlobalPathRegistry.get_instance().release_reservation(self.id)
                self.current_path = []
                self.is_waiting_for_path = False
                self.task = "SEEKING_FOOD"

        # Eksekusi Pencarian Makanan (SEEKING_FOOD) - Category-Based, Zero Hardcoding
        if self.task == "SEEKING_FOOD":
            self.active_tool = None
            household_food_need = MarketService.get_household_food_need(
                self, furniture_manager=furniture_manager, villager_manager=villager_manager,
                stockpile_manager=stockpile_manager
            )
            needs_household_restock = False
            if building_manager and household_food_need > 0:
                candidate_market, candidate_food, _ = AIFoodPurchasingSystem.find_nearest_eligible_market(
                    self, building_manager, furniture_manager=furniture_manager,
                    villager_manager=villager_manager, stockpile_manager=stockpile_manager
                )
                needs_household_restock = bool(candidate_market and AIFoodPurchasingSystem.get_household_purchase_quantity(
                    self, candidate_market, candidate_food, furniture_manager=furniture_manager,
                    villager_manager=villager_manager, stockpile_manager=stockpile_manager
                ) > 0)
            # 1. Dari inventory pribadi (makanan yang dibawa di saku)
            inv_food = next((it for it, c in self.inventory.items() if is_food_item(it) and c > 0), None)
            if inv_food and not needs_household_restock:
                self.inventory[inv_food] -= 1
                if self.inventory[inv_food] <= 0:
                    del self.inventory[inv_food]
                self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                self.hunger_death_timer = None
                self.daily_food_consumed += 1
                self.say(f"Ate {inv_food} from personal inventory!", duration=2.5)
                self._resume_or_idle_after_need()
                return

            # 2. Compare family chest and loose food by distance from the villager.
            food_source, food_pos = self._find_nearest_household_item_source(
                is_food_item, furniture_manager, stockpile_manager,
                building_manager, all_entities,
            )
            if food_source and not needs_household_restock:
                source_type, source_obj, food_name = food_source
                arrival_dist = CHEST_INTERACTION_RADIUS if source_type == "chest" else LOOSE_ITEM_ARRIVAL_DIST
                arrived = self._move_towards(
                    food_pos[0], food_pos[1], dt, arrival_dist=arrival_dist,
                    all_entities=all_entities, player=player, building_manager=building_manager,
                    furniture_manager=furniture_manager, exclusive_target=False,
                )
                if arrived:
                    if source_type == "chest":
                        taken = source_obj.take_item(food_name, 1)
                    else:
                        taken = stockpile_manager.take_from_stack(source_obj, 1)
                    if taken > 0:
                        self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                        self.hunger_death_timer = None
                        self.daily_food_consumed += 1
                        self.say(f"Ate {food_name} from household supplies!", duration=2.5)
                        self._resume_or_idle_after_need()
                return

            # 4. Inisiasi proses belanja makanan fisik ke pasar jika makanan di rumah kosong (Agent 3)
            # Dukungan backward-compatibility jika ada custom mock market_service yang di-inject (misal unit test Agent 1)
            ms = getattr(self, "market_service", None)
            if ms is not None and not building_manager and hasattr(ms, "purchase_food"):
                bought, food_name, amt = ms.purchase_food(self.family_id, self, "Potato", 1)
                if bought and amt > 0:
                    self.hunger = min(AI_NEED_MAX, self.hunger + AI_NEED_FOOD_RESTORE)
                    self.hunger_death_timer = None
                    self.daily_food_consumed += 1
                    self.say(f"Purchased {food_name or 'Food'} from Market and ate!", duration=2.5)
                    self._resume_or_idle_after_need()
                    return
                else:
                    self.need_seek_cooldown = 4.0
                    self.say("No food at home and market has none!", duration=2.5)
                    self.task = "IDLE"
                    return

            vm = getattr(self, "villager_manager", None) or villager_manager
            if AIFoodPurchasingSystem.is_family_member_purchasing_food(self, vm):
                self.need_seek_cooldown = 3.0
                self.say("Waiting: family member is already purchasing food!", duration=2.5)
                self.task = "IDLE"
                return

            market, food_item, price = AIFoodPurchasingSystem.find_nearest_eligible_market(
                self, building_manager, furniture_manager=furniture_manager, villager_manager=vm,
                stockpile_manager=stockpile_manager
            )
            if not market:
                self.need_seek_cooldown = 4.0
                self.say("No food at home and market has none!", duration=2.5)
                self.task = "IDLE"
                return

            purchase_qty = AIFoodPurchasingSystem.get_household_purchase_quantity(
                self, market, food_item, furniture_manager=furniture_manager,
                villager_manager=vm, stockpile_manager=stockpile_manager
            )
            if purchase_qty <= 0:
                current_need = MarketService.get_household_food_need(
                    self, furniture_manager=furniture_manager, villager_manager=vm,
                    stockpile_manager=stockpile_manager,
                )
                if current_need <= 0:
                    self.task = "IDLE"
                    self._resume_or_idle_after_need()
                    return

                if MarketService.get_market_stock(food_item, market) <= 0:
                    message = f"The market ran out of {food_item}."
                else:
                    message = "The household does not have enough coins for food."
                self.need_seek_cooldown = 4.0
                self.say(message, duration=2.5)
                self.task = "IDLE"
                return

            self.purchase_target_market_id = getattr(market, "id", None)
            self.purchase_food_item = food_item
            self.purchase_target_qty = purchase_qty
            self.purchase_target_price = price * purchase_qty

            my_coins = to_copper(normalize_wallet(self.inventory))
            if my_coins >= self.purchase_target_price:
                self.task = "BUYING_FOOD_TRAVEL_TO_MARKET"
                self.say(f"Heading to Market to buy {purchase_qty} {food_item}!", duration=2.0)
            else:
                chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                chest_wallet = normalize_wallet(getattr(chest, "inventory", {})) if chest else {}
                remaining_cost = self.purchase_target_price - my_coins
                ground_stack = AIFoodPurchasingSystem.find_nearest_household_currency_stack(
                    self, stockpile_manager, building_manager, furniture_manager
                )
                if ground_stack and to_copper(chest_wallet) < remaining_cost:
                    self.target_loose_stack = ground_stack
                    self.task = "BUYING_FOOD_RETRIEVE_GROUND_COINS"
                    self.say("Picking up household coins from the ground before buying food.", duration=2.0)
                elif chest:
                    self.task = "BUYING_FOOD_RETRIEVE_COINS"
                    self.say(f"Getting coins from household storage to buy {purchase_qty} {food_item} at Market!", duration=2.0)
                else:
                    self.need_seek_cooldown = 4.0
                    self.say("Household coins could not be collected.", duration=2.5)
                    self.task = "IDLE"
            return

        # -------------------------------------------------------------
        # Eksekusi Belanja Makanan Fisik ke Pasar (Agent 3)
        # -------------------------------------------------------------
        if self.task == "BUYING_FOOD_RETRIEVE_COINS":
            self.active_tool = None
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
            if not chest:
                self.task = "IDLE"
                self.need_seek_cooldown = 4.0
                return
            cx, cy = chest.get_world_pos(TILE_SIZE)
            arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                price = getattr(self, "purchase_target_price", 3)
                ok, msg = AIFoodPurchasingSystem.retrieve_coins_from_storage(self, price, furniture_manager=furniture_manager)
                if ok:
                    self.task = "BUYING_FOOD_TRAVEL_TO_MARKET"
                    self.say(f"Retrieved coins, heading to Market for {getattr(self, 'purchase_food_item', 'Food')}!", duration=2.0)
                else:
                    self.say("Not enough coins in chest for Market food!", duration=2.5)
                    self.task = "IDLE"
                    self.need_seek_cooldown = 4.0
            return

        if self.task == "BUYING_FOOD_RETRIEVE_GROUND_COINS":
            self.active_tool = None
            stack = getattr(self, "target_loose_stack", None)
            if not stockpile_manager or stack not in getattr(stockpile_manager, "stacks", []):
                stack = AIFoodPurchasingSystem.find_nearest_household_currency_stack(
                    self, stockpile_manager, building_manager, furniture_manager
                )
                self.target_loose_stack = stack
            if not stack:
                chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                if chest:
                    self.task = "BUYING_FOOD_RETRIEVE_COINS"
                else:
                    self.task = "IDLE"
                    self.need_seek_cooldown = 4.0
                return
            tx = (stack.grid_x + 0.5) * TILE_SIZE
            ty = (stack.grid_y + 0.5) * TILE_SIZE
            arrived = self._move_towards(tx, ty, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                all_entities=all_entities, player=player, building_manager=building_manager,
                furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                amount = stockpile_manager.take_from_stack(stack, min(stack.amount, VILLAGER_CARRY_CAPACITY))
                denomination = canonical_denomination(stack.resource_type)
                if amount > 0 and denomination:
                    self.inventory[denomination] = self.inventory.get(denomination, 0) + amount
                self.target_loose_stack = None
                if to_copper(normalize_wallet(self.inventory)) >= getattr(self, "purchase_target_price", 0):
                    self.task = "BUYING_FOOD_TRAVEL_TO_MARKET"
                else:
                    self.target_loose_stack = AIFoodPurchasingSystem.find_nearest_household_currency_stack(
                        self, stockpile_manager, building_manager, furniture_manager
                    )
                    self.task = "BUYING_FOOD_RETRIEVE_GROUND_COINS" if self.target_loose_stack else "BUYING_FOOD_RETRIEVE_COINS"
            return

        if self.task == "BUYING_FOOD_TRAVEL_TO_MARKET":
            self.active_tool = None
            target_m_id = getattr(self, "purchase_target_market_id", None)
            market = None
            if building_manager:
                if target_m_id:
                    market = next((b for b in building_manager.buildings if getattr(b, "id", None) == target_m_id and getattr(b, "building_type", "") == "market"), None)
                if not market:
                    market = next((b for b in building_manager.buildings if getattr(b, "building_type", "") == "market"), None)

            if not market:
                self.say("Market no longer available, returning coins home!", duration=2.5)
                self.task = "BUYING_FOOD_HAULING_HOME"
                return

            approach_pt = market.get_approach_point((self.x, self.y), TILE_SIZE, building_manager)
            arrived = self._move_towards(approach_pt[0], approach_pt[1], dt, arrival_dist=32, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                food_item = getattr(self, "purchase_food_item", "Potato")
                ok, msg = AIFoodPurchasingSystem.execute_market_transaction(
                    self, market, food_item, building_manager=building_manager,
                    quantity=getattr(self, "purchase_target_qty", 1)
                )
                if ok:
                    self.say(f"Bought {food_item} at Market! Hauling home.", duration=2.5)
                else:
                    self.say(f"Market purchase failed ({msg}), returning home.", duration=2.5)
                self.task = "BUYING_FOOD_HAULING_HOME"
            return

        if self.task == "BUYING_FOOD_HAULING_HOME":
            self.active_tool = None
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
            if chest:
                cx, cy = chest.get_world_pos(TILE_SIZE)
            elif permit_manager and self.family_id:
                vm = getattr(self, "villager_manager", None) or villager_manager
                fam = vm.get_family_by_id(self.family_id) if vm else None
                pid = getattr(fam, "assigned_permit_id", None)
                p = permit_manager.get_permit_by_id(pid) if pid else None
                cx, cy = p.get_center_world(TILE_SIZE) if p else (self.x, self.y)
            else:
                cx, cy = (self.x, self.y)

            arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)
            if arrived:
                AIFoodPurchasingSystem.deliver_and_consume_food(self, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager)
            return

        # Eksekusi Pencarian Air Minum (SEEKING_WATER)
        if self.task == "SEEKING_WATER":
            self.active_tool = None
            # 1. Dari inventory pribadi
            inv_water = next((it for it, c in self.inventory.items() if is_water_item(it) and c > 0), None)
            if inv_water:
                self.inventory[inv_water] -= 1
                if self.inventory[inv_water] <= 0:
                    del self.inventory[inv_water]
                self.thirst = min(AI_NEED_MAX, self.thirst + AI_NEED_WATER_RESTORE)
                self.thirst_death_timer = None
                self.daily_water_consumed += 1
                self.say("Drank water from personal supply!", duration=2.5)
                self._resume_or_idle_after_need()
                return

            water_source, water_pos = self._find_nearest_household_item_source(
                is_water_item, furniture_manager, stockpile_manager,
                building_manager, all_entities,
            )
            if water_source:
                source_type, source_obj, water_name = water_source
                arrival_dist = CHEST_INTERACTION_RADIUS if source_type == "chest" else LOOSE_ITEM_ARRIVAL_DIST
                arrived = self._move_towards(
                    water_pos[0], water_pos[1], dt, arrival_dist=arrival_dist,
                    all_entities=all_entities, player=player, building_manager=building_manager,
                    furniture_manager=furniture_manager, exclusive_target=False,
                )
                if arrived:
                    if source_type == "chest":
                        taken = source_obj.take_item(water_name, 1)
                    else:
                        taken = stockpile_manager.take_from_stack(source_obj, 1)
                    if taken > 0:
                        self.thirst = min(AI_NEED_MAX, self.thirst + AI_NEED_WATER_RESTORE)
                        self.thirst_death_timer = None
                        self.daily_water_consumed += 1
                        self.say(f"Drank {water_name} from household supplies!", duration=2.5)
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
                        self.thirst_death_timer = None
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

        # Eksekusi Pencarian Toilet (SEEKING_TOILET)
        if self.task == "SEEKING_TOILET":
            from game.systems.toilet_system import ToiletSystem
            handled = ToiletSystem.execute_villager_toilet_routine(
                self, dt, building_manager, all_entities=all_entities, player=player, furniture_manager=furniture_manager
            )
            if handled:
                return

        # Eksekusi Pemulihan Barang Almarhum Keluarga (RECOVER_DEATH_ITEMS)
        if self.task == "RECOVER_DEATH_ITEMS":
            handled = self._execute_death_recovery_routine(
                dt, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager,
                all_entities=all_entities, player=player, building_manager=building_manager
            )
            if handled:
                return

        if self.task == "DEPOSITING_UNUSED_ITEMS":
            self._deposit_unneeded_inventory(
                dt, furniture_manager, all_entities, player, building_manager
            )
            return

        # -------------------------------------------------------------
        # Rutinitas Sholat / Doa (Church & Prayer Time) - AGENT 3
        # -------------------------------------------------------------
        from game.systems.church_system import ChurchSystem
        church_p = ChurchSystem.get_church_permit(permit_manager)
        priest_worker = ChurchSystem.get_assigned_priest(permit_manager, villager_manager)
        is_prayer = ChurchSystem.is_prayer_time(cur_hour, schedule_manager) and not has_pending_work

        if is_prayer:
            if self == priest_worker:
                # 1. Travel to Church
                # 2. Receive Church Tax from household representatives
                # 3. Remain at the Church until Prayer Time ends
                if church_p:
                    tiles = ChurchSystem.get_church_walkable_tiles(church_p, building_manager)
                    if tiles:
                        altar_tile = tiles[0]
                        twx = (altar_tile[0] + 0.5) * TILE_SIZE
                        twy = (altar_tile[1] + 0.5) * TILE_SIZE
                        self.task = "LEADING_PRAYER"
                        self._move_towards(twx, twy, dt, arrival_dist=12, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=True)
                        return
                else:
                    self.task = "LEADING_PRAYER"
                    return
            else:
                church_tile = ChurchSystem.find_free_church_tile(self, church_p, building_manager)
                if church_tile and church_p:
                    twx = (church_tile[0] + 0.5) * TILE_SIZE
                    twy = (church_tile[1] + 0.5) * TILE_SIZE
                    self.task = "ATTENDING_PRAYER"
                    arrived = self._move_towards(twx, twy, dt, arrival_dist=12, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    if priest_worker:
                        dist_to_church = math.hypot(self.x - twx, self.y - twy)
                        if dist_to_church <= 48.0 or arrived:
                            ChurchSystem.process_church_tax_payment(self, priest_worker, church_p, furniture_manager)
                    return
                # If Church is full: immediately proceed to normal activity without waiting outside or blocking doors
        else:
            ChurchSystem.release_church_tile(self)
            if self == priest_worker:
                # 4. After Prayer Time ends, return to the Household Chest of assigned household
                # 5. Deposit all collected coins into that Household Chest
                fam_id = getattr(self, "family_id", None)
                chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
                priest_copper = to_copper(getattr(self, "currency", {}))
                if chest and priest_copper > 0:
                    cx, cy = chest.get_world_pos(TILE_SIZE)
                    dist_to_chest = math.hypot(self.x - cx, self.y - cy)
                    if dist_to_chest > 20.0:
                        self.task = "RETURNING_TITHES_HOME"
                        self._move_towards(cx, cy, dt, arrival_dist=16, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                        return
                    else:
                        ChurchSystem.priest_deposit_tithes_home(self, furniture_manager)

                # 6. If it is Work Time, begin preaching near village infrastructure
                if sched_activity in ("WORK", "ANY"):
                    ChurchSystem.execute_priest_preaching(self, dt, building_manager, all_entities=all_entities)
                    return


        # -------------------------------------------------------------
        # Rutinitas 1: Tidur Malam (SLEEP)
        # -------------------------------------------------------------
        if sched_activity == "SLEEP":
            if (self._get_unneeded_inventory() and furniture_manager
                    and furniture_manager.get_storage_for_family(self.family_id)):
                self.task = "DEPOSITING_UNUSED_ITEMS"
                self._deposit_unneeded_inventory(
                    dt, furniture_manager, all_entities, player, building_manager
                )
                return

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
                id_str = str(self.id)
                num_part = id_str.split("_")[-1] if "_" in id_str else ""
                fallback_idx = int(num_part) if num_part.isdigit() else abs(hash(id_str))
                fam_members = [e for e in all_entities if getattr(e, "family_id", None) == self.family_id] if all_entities else []
                if not fam_members and getattr(self, "villager_manager", None):
                    fam_members = [v for v in self.villager_manager.get_all_villagers() if getattr(v, "family_id", None) == self.family_id]
                m_idx = fam_members.index(self) if self in fam_members else fallback_idx

                if p and p.tiles:
                    sorted_tiles = sorted(list(p.tiles), key=lambda t: (t[1], t[0]))
                    floor_tile = sorted_tiles[m_idx % len(sorted_tiles)]
                    slot_ox = ((m_idx % 3) - 1) * 18.0
                    slot_oy = (((m_idx // 3) % 3) - 1) * 18.0
                    floor_x = (floor_tile[0] + 0.5) * TILE_SIZE + slot_ox
                    floor_y = (floor_tile[1] + 0.5) * TILE_SIZE + slot_oy
                else:
                    # Homeless at Town Center: spread out radially with generous spacing
                    total_m = max(1, len(fam_members) or 6)
                    ang = (m_idx / total_m) * (2.0 * math.pi)
                    floor_x = math.cos(ang) * 75.0
                    floor_y = math.sin(ang) * 75.0

                arrived = self._move_towards(floor_x, floor_y, dt, arrival_dist=6, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
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
        # Rutinitas 1.55: Household Stall Tasks (Hauling allocated goods / collecting earnings)
        # -------------------------------------------------------------
        if self.task.startswith("HAULING_STALL_"):
            from game.systems.household_stall_system import HouseholdStallSystem
            handled = HouseholdStallSystem.execute_stall_chores_tick(
                self, dt, building_manager, furniture_manager,
                all_entities=all_entities, player=player, tile_size=TILE_SIZE
            )
            if handled:
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
        if sched_activity != "SLEEP" and (furniture_manager or stockpile_manager):
            # A. Jika sedang mengangkut air hasil timba menuju peti keluarga (HAULING_HOUSEHOLD_WATER)
            if self.task == "HAULING_HOUSEHOLD_WATER":
                chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
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
                elif stockpile_manager:
                    cur_gx = int(math.floor(self.x / TILE_SIZE))
                    cur_gy = int(math.floor(self.y / TILE_SIZE))
                    amt = self.inventory.get("Water", 0)
                    if amt > 0:
                        stockpile_manager.drop_resource("Water", amt, cur_gx, cur_gy, owner_type="villager", owner_id=self.family_id)
                        del self.inventory["Water"]
                    self.say("Stored fresh water at home!", duration=2.5)
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
        tool_purchase_tasks = {
            "BUYING_JOB_TOOLS_RETRIEVE_COINS",
            "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET",
            "BUYING_JOB_TOOLS_RETURN_HOME",
        }
        if self.task in tool_purchase_tasks:
            market = getattr(self, "job_tool_purchase_market", None)
            requested_items = getattr(self, "job_tool_purchase_items", {})
            if not market or not requested_items:
                self.task = "IDLE"
                self.job_tool_purchase_market = None
                self.job_tool_purchase_items = {}
                return

            total_cost = sum(
                MarketService.get_item_price(item, market) * quantity
                for item, quantity in requested_items.items()
            )
            chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None

            if self.task == "BUYING_JOB_TOOLS_RETRIEVE_COINS":
                pocket_funds = to_copper(normalize_wallet(self.inventory))
                if pocket_funds >= total_cost:
                    self.task = "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET"
                elif chest:
                    chest_x, chest_y = chest.get_world_pos(TILE_SIZE)
                    arrived = self._move_towards(
                        chest_x, chest_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                        all_entities=all_entities, player=player,
                        building_manager=building_manager, furniture_manager=furniture_manager,
                    )
                    if arrived:
                        success, message = AIMarketPurchasingSystem.withdraw_household_coins(
                            self, total_cost, furniture_manager, villager_manager
                        )
                        if success:
                            self.task = "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET"
                        else:
                            self.task = "MISSING_TOOL"
                            self.say(message, duration=2.5)
                else:
                    success, message = AIMarketPurchasingSystem.withdraw_household_coins(
                        self, total_cost, furniture_manager, villager_manager
                    )
                    if success:
                        self.task = "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET"
                    else:
                        self.task = "MISSING_TOOL"
                        self.say(message, duration=2.5)
                return

            if self.task == "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET":
                market_x, market_y = market.get_center_world(TILE_SIZE)
                arrived = self._move_towards(
                    market_x, market_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                )
                if arrived:
                    success, message = AIMarketPurchasingSystem.execute_items_transaction(
                        self, market, requested_items
                    )
                    if success:
                        self.task = "BUYING_JOB_TOOLS_RETURN_HOME"
                    else:
                        self.task = "MISSING_TOOL"
                        self.say(message, duration=2.5)
                return

            if self.task == "BUYING_JOB_TOOLS_RETURN_HOME":
                if chest:
                    chest_x, chest_y = chest.get_world_pos(TILE_SIZE)
                    arrived = self._move_towards(
                        chest_x, chest_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                        all_entities=all_entities, player=player,
                        building_manager=building_manager, furniture_manager=furniture_manager,
                    )
                    if arrived:
                        AIMarketPurchasingSystem.deposit_materials_and_change_to_chest(self, furniture_manager)
                        self.say("Stored market change; tools are ready for work.", duration=2.0)
                else:
                    self.task = "IDLE"
                if self.task == "IDLE":
                    self.job_tool_purchase_market = None
                    self.job_tool_purchase_items = {}
                return

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
        if self.task not in ("HAULING_FURNITURE", "FETCHING_FURNITURE", "HAULING_HOME", "FETCHING_POSSESSION"):
            missing_tools = self.get_missing_job_tools()
            if missing_tools:
                available_to_fetch = [t for t, _ in missing_tools if self._has_tool_in_storage(t, furniture_manager, stockpile_manager)]
                if available_to_fetch:
                    storage_pos, storage_type, storage_obj = self._find_tool_storage(
                        furniture_manager, stockpile_manager, required_items=available_to_fetch,
                        building_manager=building_manager,
                    )
                    if storage_pos:
                        dist = math.hypot(storage_pos[0] - self.x, storage_pos[1] - self.y)
                        cur_vgx = int(math.floor(self.x / TILE_SIZE))
                        cur_vgy = int(math.floor(self.y / TILE_SIZE))
                        st_gx = int(math.floor(storage_pos[0] / TILE_SIZE))
                        st_gy = int(math.floor(storage_pos[1] / TILE_SIZE))
                        is_near = (dist <= CHEST_INTERACTION_RADIUS) or (abs(cur_vgx - st_gx) <= 1 and abs(cur_vgy - st_gy) <= 1)

                        if is_near:
                            col = self._collect_job_tools_from_source(
                                storage_type, storage_obj, stockpile_manager
                            )
                            if col:
                                self.say(f"Equipped {', '.join(col)} for {self.job}!", duration=2.0)
                            self.task = "IDLE"
                            return
                        else:
                            self.task = "EQUIPPING_JOB_TOOLS"
                            self.active_tool = None
                            self._move_towards(storage_pos[0], storage_pos[1], dt, arrival_dist=TOOL_STOW_ARRIVAL_DIST, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                            return
                else:
                    requested_items = dict(missing_tools)
                    market, total_cost = AIMarketPurchasingSystem.find_market_for_items(
                        self, requested_items, building_manager, furniture_manager, villager_manager
                    )
                    if market:
                        self.job_tool_purchase_market = market
                        self.job_tool_purchase_items = requested_items
                        self.task = "BUYING_JOB_TOOLS_RETRIEVE_COINS"
                        return
                    self.task = "MISSING_TOOL"
                    if not getattr(self, "speech_text", None):
                        self.say("My job tools are missing, and no market can supply the complete set.", duration=2.5)
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

            # Auto-sync job if worker is assigned to a workplace permit
            if self.job in ("Unassigned", None) and permit_manager:
                assigned_p = next((p for p in permit_manager.permits if (hasattr(p, "assigned_workers") and self.id in p.assigned_workers) or (hasattr(self, "assigned_permit_id") and p.id == self.assigned_permit_id)), None)
                if assigned_p:
                    if assigned_p.permit_type == "farm":
                        self.set_job("Farmer")
                    elif assigned_p.permit_type == "church":
                        self.set_job("Priest")
                    elif assigned_p.permit_type == "cemetery":
                        self.set_job("Gravedigger")

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
                    # Each tile uses the configured in-game labor duration.
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
                                        cur_day = (day_cycle.day_number + (day_cycle.current_hour / 24.0)) if day_cycle else None
                                        assigned_farm.till_and_sow_tile(target_t[0], target_t[1], current_day=cur_day)
                                        assigned_farm.release_tile_reservation(target_t[0], target_t[1], self.id)
                                        self.tilling_timer = 0.0
                                        self.current_work_tile = None
                                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                                        self.say("Finished tilling and sowing tile!", duration=1.5)
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
                                        self.say("Watered crop tile!", duration=1.5)
                                return

                    # Selesai seluruh garapan ladang hari ini atau seluruh tile sedang dikerjakan pekerja lain
                    if self.current_work_tile:
                        assigned_farm.release_worker_reservations(self.id)
                        self.current_work_tile = None
                        GlobalPathRegistry.get_instance().release_reservation(self.id)
                    self.active_tool = None

            # Pekerjaan spesifik: Penggali Kubur (Gravedigger) - AGENT 3
            if self.job == "Gravedigger":
                from game.systems.cemetery_system import CemeterySystem
                restock_tasks = {
                    "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS",
                    "GRAVEDIGGER_RESTOCK_TRAVEL_TO_MARKET",
                    "GRAVEDIGGER_RESTOCK_HAULING_HOME",
                }
                if self.task in restock_tasks and (
                    not getattr(self, "target_restock_market", None)
                    or not getattr(self, "target_restock_mat", None)
                    or getattr(self, "target_restock_qty", 0) <= 0
                ):
                    # Save files retain task names but not live market references.
                    # Rebuild the purchase plan from current stock and funds.
                    self.task = "IDLE"
                    self.target_restock_market = None
                    self.target_restock_mat = None
                    self.target_restock_qty = 0

                # Buy any missing tools before starting burial work. Process each
                # missing tool through the same physical market workflow.
                missing_tools = self.get_missing_job_tools()
                if missing_tools and self.task not in restock_tasks:
                    tool_name, tool_qty = missing_tools[0]
                    market, _, buy_qty = AIMarketPurchasingSystem.find_nearest_market_for_material(
                        self, tool_name, tool_qty, building_manager, furniture_manager, villager_manager
                    )
                    if market and buy_qty > 0:
                        self.target_restock_market = market
                        self.target_restock_mat = tool_name
                        self.target_restock_qty = buy_qty
                        self.task = "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS"
                    elif not getattr(self, "speech_text", None):
                        self.say(f"I need {tool_name} to work, but no market has it in stock.", duration=2.5)
                    return

                cemetery_p = CemeterySystem.get_cemetery_permit(permit_manager)
                if cemetery_p:
                    CemeterySystem.update_grave_lifecycles(cemetery_p, cur_day)

                # A. Sedang mengangkut jenazah -> Menuju pemakaman
                if getattr(self, "carrying_corpse_id", None) and self.task not in ("DIGGING_GRAVE", "BURYING_GRAVE"):
                    self.task = "CARRYING_CORPSE"
                    target_cid = self.carrying_corpse_id
                    grave_tile = getattr(self, "gravedigger_target_grave_tile", None)
                    if not grave_tile and cemetery_p:
                        grave_tile = CemeterySystem.get_available_grave_tile(cemetery_p, cur_day)
                        self.gravedigger_target_grave_tile = grave_tile

                    if not grave_tile or not cemetery_p:
                        # Pemakaman PENUH (Full Cemetery Overflow)
                        corpse_entity = next((v for v in villager_manager.get_all_villagers() if str(v.id) == str(target_cid)), None)
                        overflow_corpse = corpse_entity or {"id": target_cid, "first_name": "Villager"}
                        overflow_x, overflow_y = CemeterySystem.get_overflow_position(cemetery_p, overflow_corpse, TILE_SIZE)
                        arrived = self._move_towards(overflow_x, overflow_y, dt, arrival_dist=14, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                        if arrived:
                            CemeterySystem.handle_full_cemetery_overflow(self, overflow_corpse, cemetery_p, TILE_SIZE)
                            self.carrying_corpse_id = None
                            self.carrying_corpse_name = None
                            self.gravedigger_target_corpse_id = None
                            self.gravedigger_target_grave_tile = None
                            self.gravedigger_materials_committed = False
                            self.task = "IDLE"
                        return

                    g_wx = (grave_tile[0] + 0.5) * TILE_SIZE
                    g_wy = (grave_tile[1] + 0.5) * TILE_SIZE
                    self.active_tool = "Hoe"
                    arrived = self._move_towards(g_wx, g_wy, dt, arrival_dist=14, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    if arrived:
                        if CemeterySystem.consume_grave_materials(self, furniture_manager):
                            self.gravedigger_materials_committed = True
                            self.task = "DIGGING_GRAVE"
                            self.gravedigger_timer = 0.0
                        else:
                            self.say("I need one Wood and one Stone to finish preparing this grave.", duration=2.5)
                    return

                # B. Sedang menggali kubur (1.0 jam in-game)
                if self.task == "DIGGING_GRAVE":
                    self.active_tool = "Hoe"
                    if not getattr(self, "gravedigger_materials_committed", False):
                        if not CemeterySystem.consume_grave_materials(self, furniture_manager):
                            self.task = "IDLE"
                            self.say("I need one Wood and one Stone before digging.", duration=2.5)
                            return
                        self.gravedigger_materials_committed = True
                    one_hour = (day_cycle.day_length_seconds / 24.0) if day_cycle else 50.0
                    self.gravedigger_timer += dt
                    grave_tile = getattr(self, "gravedigger_target_grave_tile", None)
                    if grave_tile and cemetery_p and hasattr(cemetery_p, "tile_graves"):
                        g = cemetery_p.tile_graves.get(grave_tile)
                        if g:
                            g["dig_progress"] = min(1.0, self.gravedigger_timer / one_hour)

                    if self.gravedigger_timer >= one_hour:
                        self.task = "BURYING_GRAVE"
                        self.gravedigger_timer = 0.0
                    return

                # C. Sedang memakamkan / mengubur jenazah (0.5 jam in-game)
                if self.task == "BURYING_GRAVE":
                    self.active_tool = "Hoe"
                    half_hour = ((day_cycle.day_length_seconds / 24.0) if day_cycle else 50.0) * 0.5
                    self.gravedigger_timer += dt
                    grave_tile = getattr(self, "gravedigger_target_grave_tile", None)
                    if grave_tile and cemetery_p and hasattr(cemetery_p, "tile_graves"):
                        g = cemetery_p.tile_graves.get(grave_tile)
                        if g:
                            g["bury_progress"] = min(1.0, self.gravedigger_timer / half_hour)

                    if self.gravedigger_timer >= half_hour:
                        target_cid = getattr(self, "gravedigger_target_corpse_id", None)
                        corpse_entity = next((v for v in villager_manager.get_all_villagers() if str(v.id) == str(target_cid)), None)
                        CemeterySystem.complete_burial_on_tile(cemetery_p, grave_tile, corpse_entity or {"id": target_cid, "first_name": "Villager"}, cur_day)
                        CemeterySystem.complete_burial_commission(target_cid)
                        if corpse_entity:
                            corpse_entity.is_buried = True
                            corpse_entity.is_picked_up = False
                        self.say("Burial complete. May they rest in peace.", duration=3.0)
                        self.carrying_corpse_id = None
                        self.carrying_corpse_name = None
                        self.gravedigger_target_corpse_id = None
                        self.gravedigger_target_grave_tile = None
                        self.gravedigger_materials_committed = False
                        self.gravedigger_timer = 0.0
                        self.task = "IDLE"
                    return

                # D. Cek apakah ada jenazah yang belum dimakamkan
                all_vils = villager_manager.get_all_villagers()
                ready_overflow = CemeterySystem.release_ready_overflow_corpse(cemetery_p, cur_day)
                overflow_ids = CemeterySystem.get_overflow_corpse_ids()
                unburied_corpses = [
                    v for v in all_vils
                    if not getattr(v, "is_alive", True)
                    and not getattr(v, "is_buried", False)
                    and not getattr(v, "is_picked_up", False)
                    and str(getattr(v, "id", "")) not in overflow_ids
                ]
                unburied_corpses.sort(key=lambda v: not getattr(v, "is_cemetery_overflow", False))

                if (ready_overflow or unburied_corpses) and self.task not in restock_tasks:
                    target_corpse = ready_overflow or unburied_corpses[0]
                    w_count, s_count, miss_w, miss_s = CemeterySystem.check_gravedigger_stock(self, furniture_manager)
                    if miss_w > 0 or miss_s > 0:
                        mat_to_buy = "Wood" if miss_w > 0 else "Stone"
                        qty_to_buy = miss_w if miss_w > 0 else miss_s
                        mkt, p_cop, can_buy = AIMarketPurchasingSystem.find_nearest_market_for_material(
                            self, mat_to_buy, qty_to_buy, building_manager, furniture_manager, villager_manager
                        )
                        if mkt and can_buy > 0:
                            self.target_restock_market = mkt
                            self.target_restock_mat = mat_to_buy
                            self.target_restock_qty = can_buy
                            self.task = "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS"
                            return
                        else:
                            self.say("Need 1 Wood and 1 Stone to prepare grave.", duration=2.5)
                            return

                    # Arrange payment first. The family representative visits the
                    # gravedigger, or the gravedigger collects from landlord storage.
                    commission = CemeterySystem.commission_burial(
                        target_corpse, villager_manager, furniture_manager,
                        stockpile_manager, gravedigger=self,
                    )
                    if (commission and commission.get("gravedigger_id")
                            and str(commission["gravedigger_id"]) != str(self.id)):
                        return
                    if commission and commission.get("status") != "PAID":
                        if self.task != "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE":
                            self.task = "WAITING_FOR_BURIAL_PAYMENT"
                        return

                    # Menuju jenazah untuk diangkat
                    self.active_tool = "Hoe"
                    self.gravedigger_target_corpse_id = target_corpse.id
                    self.task = "FETCHING_CORPSE"
                    arrived = self._move_towards(target_corpse.x, target_corpse.y, dt, arrival_dist=16, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    if arrived:
                        target_corpse.is_picked_up = True
                        target_corpse.is_cemetery_overflow = False
                        self.carrying_corpse_id = target_corpse.id
                        self.carrying_corpse_name = target_corpse.full_name
                        self.task = "CARRYING_CORPSE"
                        self.say(f"Carrying {target_corpse.first_name}'s body to the cemetery...", duration=2.5)
                    return

                # E. Restocking material rutin (Target 5 Wood, 5 Stone)
                if self.task == "IDLE":
                    w_count, s_count, miss_w, miss_s = CemeterySystem.check_gravedigger_stock(self, furniture_manager)
                    if miss_w > 0 or miss_s > 0:
                        mat_to_buy = "Wood" if miss_w > 0 else "Stone"
                        qty_to_buy = miss_w if miss_w > 0 else miss_s
                        mkt, p_cop, can_buy = AIMarketPurchasingSystem.find_nearest_market_for_material(
                            self, mat_to_buy, qty_to_buy, building_manager, furniture_manager, villager_manager
                        )
                        if mkt and can_buy > 0:
                            self.target_restock_market = mkt
                            self.target_restock_mat = mat_to_buy
                            self.target_restock_qty = can_buy
                            self.task = "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS"

                if self.task == "GRAVEDIGGER_RESTOCK_RETRIEVE_COINS":
                    chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                    mkt = getattr(self, "target_restock_market", None)
                    mat = getattr(self, "target_restock_mat", "Wood")
                    qty = getattr(self, "target_restock_qty", 1)
                    unit_price = MarketService.get_item_price(mat, mkt)
                    pocket_funds = to_copper(normalize_wallet(self.inventory))
                    if pocket_funds >= unit_price * qty:
                        arrived = True
                    elif chest:
                        cx, cy = chest.get_world_pos(TILE_SIZE)
                        arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    else:
                        arrived = True
                    if arrived:
                        enough_coins, message = AIMarketPurchasingSystem.withdraw_household_coins(
                            self, unit_price * qty, furniture_manager, villager_manager
                        )
                        if enough_coins:
                            self.task = "GRAVEDIGGER_RESTOCK_TRAVEL_TO_MARKET"
                        else:
                            self.task = "IDLE"
                            if not getattr(self, "speech_text", None):
                                self.say(message, duration=2.5)
                    return

                if self.task == "GRAVEDIGGER_RESTOCK_TRAVEL_TO_MARKET":
                    mkt = getattr(self, "target_restock_market", None)
                    if mkt:
                        mx, my = mkt.get_center_world(TILE_SIZE)
                        arrived = self._move_towards(mx, my, dt, arrival_dist=36, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                        if arrived:
                            mat = getattr(self, "target_restock_mat", "Wood")
                            qty = getattr(self, "target_restock_qty", 1)
                            ok, msg = AIMarketPurchasingSystem.execute_material_transaction(self, mkt, mat, qty)
                            if ok:
                                self.say(f"Bought {qty}x {mat} for burials.", duration=2.5)
                            self.task = "GRAVEDIGGER_RESTOCK_HAULING_HOME"
                    return

                if self.task == "GRAVEDIGGER_RESTOCK_HAULING_HOME":
                    chest = furniture_manager.get_storage_for_family(self.family_id) if furniture_manager else None
                    if chest:
                        cx, cy = chest.get_world_pos(TILE_SIZE)
                        arrived = self._move_towards(cx, cy, dt, arrival_dist=CHEST_INTERACTION_RADIUS, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                        if arrived:
                            AIMarketPurchasingSystem.deposit_materials_and_change_to_chest(self, furniture_manager)
                            self.say("Stored materials in chest.", duration=2.0)
                    else:
                        AIMarketPurchasingSystem.deposit_materials_and_change_to_chest(self, furniture_manager)
                    return

        # -------------------------------------------------------------
        # Rutinitas 3: Waktu Santai / Istirahat (LEISURE / Chores Finished)
        # -------------------------------------------------------------
        self.task = "IDLE"
        self.active_tool = None

        if self._get_unneeded_inventory() and furniture_manager and furniture_manager.get_storage_for_family(self.family_id):
            self.task = "DEPOSITING_UNUSED_ITEMS"
            self._deposit_unneeded_inventory(
                dt, furniture_manager, all_entities, player, building_manager
            )
            return

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

        # Evaluasi Makan & Minum (Mealtime & Daily Needs Fulfillment)
        if sched_activity in ("LEISURE", "ANY") and self.need_seek_cooldown <= 0.0:
            is_mealtime = (cur_hour >= 18.0 or cur_hour < 8.0 or self.hunger < 95.0 or self.thirst < 95.0)
            if is_mealtime:
                if self.daily_food_consumed < DAILY_FOOD_REQUIREMENT and (self.hunger < 95.0 or cur_hour >= 20.0 or (cur_hour < 8.0 and self.hunger < 98.0)):
                    self.task = "SEEKING_FOOD"
                    return
                if self.daily_water_consumed < DAILY_WATER_REQUIREMENT and (self.thirst < 95.0 or cur_hour >= 20.0 or (cur_hour < 8.0 and self.thirst < 98.0)):
                    self.task = "SEEKING_WATER"
                    return

        # Evaluasi Household Market Stall (Stall Chores during Leisure Time)
        if sched_activity in ("LEISURE", "ANY") and self.task in ("IDLE", "LEISURE", "STROLLING"):
            from game.systems.household_stall_system import HouseholdStallSystem
            started = HouseholdStallSystem.check_and_start_stall_chores(
                self, building_manager, furniture_manager, all_entities=all_entities
            )
            if started:
                return

        self._idle_behavior(dt, player=player, all_entities=all_entities, building_manager=building_manager, permit_manager=permit_manager, furniture_manager=furniture_manager)

    def _idle_behavior(self, dt, player=None, all_entities=None, building_manager=None, permit_manager=None, furniture_manager=None):
        self.idle_wander_timer -= dt
        if self.idle_wander_timer <= 0:
            self.idle_wander_timer = random.uniform(4.0, 8.0)

            if getattr(self, "assigned_permit_id", None) and permit_manager:
                home_b = self._get_home_building(permit_manager, building_manager)
                if home_b and random.random() < 0.60:
                    avail_tiles = [t for t in home_b.tiles if t != getattr(home_b, "door_pos", None)]
                    if getattr(home_b, "door_pos", None) and getattr(home_b, "door_side", None):
                        dx, dy = home_b.door_pos
                        adj_tile = (dx, dy + 1) if home_b.door_side == "top" else (
                                   (dx, dy - 1) if home_b.door_side == "bottom" else (
                                   (dx + 1, dy) if home_b.door_side == "left" else (dx - 1, dy)))
                        avail_tiles = [t for t in avail_tiles if t != adj_tile]
                    
                    # Rule: Narrow doorways & passages must NEVER become an AI idle position
                    from game.world.pathfinding import is_narrow_passage_tile
                    open_tiles = [t for t in avail_tiles if not is_narrow_passage_tile(t, building_manager=building_manager)]
                    if open_tiles:
                        avail_tiles = open_tiles

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
                ] if getattr(self, "assigned_permit_id", None) else [
                    "Seeking land to farm, my Lord...",
                    "Awaiting the Landlord's deed assignment."
                ]
                self.say(random.choice(phrases), duration=2.5)

        # Bebaskan lorong sempit jika tanpa sengaja berada di lorong sempit saat idle (Image 2 unjamming)
        from game.world.pathfinding import is_narrow_passage_tile
        cur_gx = int(math.floor(self.x / TILE_SIZE))
        cur_gy = int(math.floor(self.y / TILE_SIZE))
        if is_narrow_passage_tile((cur_gx, cur_gy), building_manager=building_manager):
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                cand_t = (cur_gx + dx, cur_gy + dy)
                if not is_narrow_passage_tile(cand_t, building_manager=building_manager):
                    cand_wx = (cand_t[0] + 0.5) * TILE_SIZE
                    cand_wy = (cand_t[1] + 0.5) * TILE_SIZE
                    self.idle_target = (cand_wx, cand_wy)
                    self._move_towards(cand_wx, cand_wy, dt, arrival_dist=12, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager)
                    break

        # Pastikan target santai tidak berada di celah atau koridor pintu
        if building_manager and hasattr(building_manager, "is_near_any_door") and building_manager.is_near_any_door(self.idle_target[0], self.idle_target[1], min_dist=DOORWAY_IDLE_MIN_DISTANCE):
            for offset in (40.0, -40.0, 60.0, -60.0):
                cand_x = self.idle_target[0] + offset
                cand_y = self.idle_target[1] + offset
                if not building_manager.is_near_any_door(cand_x, cand_y, min_dist=DOORWAY_IDLE_MIN_DISTANCE):
                    self.idle_target = (cand_x, cand_y)
                    break

        # Bebaskan celah pintu jika tanpa sengaja berada di threshold saat idle
        if building_manager and hasattr(building_manager, "is_near_any_door") and building_manager.is_near_any_door(self.x, self.y, min_dist=32.0):
            for b in getattr(building_manager, "buildings", []):
                if b.door_pos and b.is_in_door_threshold(self.x, self.y, TILE_SIZE):
                    d_out = b.get_door_world_outside(TILE_SIZE)
                    n_dx = d_out[0] - self.x
                    n_dy = d_out[1] - self.y
                    n_dist = math.hypot(n_dx, n_dy)
                    if n_dist > 0.1:
                        self.x += (n_dx / n_dist) * (self.speed * dt * 0.8)
                        self.y += (n_dy / n_dist) * (self.speed * dt * 0.8)

        self.is_waiting_for_path = False
        self._move_towards(self.idle_target[0], self.idle_target[1], dt, arrival_dist=16, all_entities=all_entities, player=player, building_manager=building_manager, furniture_manager=furniture_manager, exclusive_target=False)

    def _move_towards(self, tx, ty, dt, arrival_dist=10, all_entities=None, player=None, building_manager=None, furniture_manager=None, exclusive_target=False):
        if getattr(self, "player_avoid_speech_cooldown", 0.0) > 0.0:
            self.player_avoid_speech_cooldown = max(0.0, self.player_avoid_speech_cooldown - dt)
        self.path_retry_timer = max(0.0, getattr(self, "path_retry_timer", 0.0) - dt)

        # Direct arrival check
        direct_dist = math.hypot(tx - self.x, ty - self.y)
        if direct_dist <= arrival_dist:
            self.is_moving = False
            self.current_path = []
            self.path_index = 0
            self.path_target = None
            self.is_waiting_for_path = False
            self.route_state = ROUTE_STATE_COMPLETED
            return True

        target_dist = math.hypot(tx - (self.path_target[0] if self.path_target else 999999),
                                 ty - (self.path_target[1] if self.path_target else 999999))
        target_changed = self.path_target is None or target_dist > PATH_WAYPOINT_TOLERANCE
        needs_new_path = (
            target_changed
            or (self.current_path and self.path_index >= len(self.current_path))
            or (not self.current_path and self.path_retry_timer <= 0.0)
        )

        if needs_new_path:
            self.path_target = (tx, ty)
            if target_changed:
                self.path_retry_timer = 0.0
            cand_path = find_navigation_path(
                (self.x, self.y), (tx, ty), building_manager,
                furniture_manager=furniture_manager, tile_size=TILE_SIZE,
            )

            if cand_path:
                self.current_path = cand_path
                self.path_index = 0
                self.is_waiting_for_path = False
                self.route_state = ROUTE_STATE_ASSIGNED
            else:
                self.route_state = ROUTE_STATE_FAILED
                self.path_retry_timer = NAVIGATION_RETRY_INTERVAL
                self.current_path = []
                self.path_index = 0
                self.is_moving = False
                self.is_waiting_for_path = False
                return False

        if not self.current_path or self.path_index >= len(self.current_path):
            self.is_moving = False
            return False

        # 2. Waypoint stepping
        target_wp = self.current_path[self.path_index]
        wp_dx = target_wp[0] - self.x
        wp_dy = target_wp[1] - self.y
        dist_to_wp = math.hypot(wp_dx, wp_dy)
        is_last_wp = (self.path_index == len(self.current_path) - 1)
        tol = arrival_dist if is_last_wp else 8.0

        if dist_to_wp <= tol:
            if is_last_wp:
                self.is_moving = False
                self.current_path = []
                self.path_index = 0
                self.path_target = None
                self.is_waiting_for_path = False
                self.route_state = ROUTE_STATE_COMPLETED
                return True
            else:
                self.path_index += 1
                if self.path_index >= len(self.current_path):
                    self.is_moving = False
                    self.current_path = []
                    self.path_index = 0
                    self.route_state = ROUTE_STATE_COMPLETED
                    return True
                target_wp = self.current_path[self.path_index]
                wp_dx = target_wp[0] - self.x
                wp_dy = target_wp[1] - self.y
                dist_to_wp = math.hypot(wp_dx, wp_dy)

        if dist_to_wp < 0.001:
            return False

        self.is_moving = True
        self.route_state = ROUTE_STATE_ACTIVE
        self.is_waiting_for_path = False

        speed_mult = CORPSE_CARRY_SPEED_RATIO if getattr(self, "carrying_corpse_id", None) else 1.0
        cur_speed = self.speed * speed_mult
        move_dist = min(cur_speed * dt, dist_to_wp)
        dir_x = wp_dx / dist_to_wp
        dir_y = wp_dy / dist_to_wp
        vx = dir_x * move_dist
        vy = dir_y * move_dist

        # 3. Player / Landlord Avoidance & Speech Bubble
        if player:
            p_dx = player.x - self.x
            p_dy = player.y - self.y
            p_dist = math.hypot(p_dx, p_dy)
            min_p_dist = self.radius + getattr(player, "radius", 14) + 6.0
            if p_dist < min_p_dist and p_dist > 0.001:
                nx = -p_dx / p_dist
                ny = -p_dy / p_dist
                tx_dir = -ny
                ty_dir = nx
                if (vx * tx_dir + vy * ty_dir) < 0:
                    tx_dir, ty_dir = -tx_dir, -ty_dir

                overlap = min_p_dist - p_dist
                push_dist = max(overlap * 0.6, move_dist * 0.5)
                vx = nx * push_dist + tx_dir * move_dist * 0.9
                vy = ny * push_dist + ty_dir * move_dist * 0.9

                if getattr(self, "player_avoid_speech_cooldown", 0.0) <= 0.0:
                    polite_msgs = [
                        "Sorry, my lord.",
                        "Pardon me, my lord.",
                        "Excuse me, my lord.",
                        "My apologies, my lord.",
                        "Coming through, my lord."
                    ]
                    self.say(random.choice(polite_msgs), duration=2.2)
                    self.player_avoid_speech_cooldown = 4.5

        # 4. Movement execution with substepping & collision
        old_x, old_y = self.x, self.y
        max_step = 6.0
        step_len = math.hypot(vx, vy)
        steps = max(1, math.ceil(step_len / max_step))
        sub_vx = vx / steps
        sub_vy = vy / steps

        for _ in range(steps):
            step_ox, step_oy = self.x, self.y
            self.x += sub_vx
            self.y += sub_vy
            if building_manager:
                self.x, self.y = building_manager.resolve_collision(self.x, self.y, self.radius, TILE_SIZE, old_x=step_ox, old_y=step_oy)

        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if getattr(b, "door_pos", None) and (b.is_in_door_threshold(self.x, self.y, TILE_SIZE) or b.is_in_door_threshold(old_x, old_y, TILE_SIZE)):
                    b.door_active_user = str(self.id)
                    break

        # 5. Stuck Recovery
        actual_dist = math.hypot(self.x - old_x, self.y - old_y)
        if actual_dist < (move_dist * 0.15) and dist_to_wp > tol:
            self.stuck_timer += dt
            if self.stuck_timer >= 2.0:
                self.stuck_timer = 0.0
                self.current_path = []
                self.path_index = 0
                self.path_target = None
        else:
            self.stuck_timer = max(0.0, self.stuck_timer - dt * 2.0)

        if vx != 0 or vy != 0:
            self.facing_angle = math.atan2(vy, vx)
            self.walk_cycle += dt * 10.0

        return False

    def draw(self, surface, camera, font_bubble):
        sx, sy = camera.world_to_screen(self.x, self.y)
        r = max(4, int(self.radius * camera.zoom))

        if not getattr(self, "is_alive", True):
            if getattr(self, "is_buried", False) or getattr(self, "is_picked_up", False):
                return
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
        job_colors = DEDICATED_JOBS.get(self.job, DEDICATED_JOBS["Unassigned"])
        body_color = job_colors.get("color", DEDICATED_JOBS["Unassigned"]["color"])
        pygame.draw.circle(surface, body_color, (sx, char_y), r)
        outline_w = max(1, int(3 * camera.zoom))
        pygame.draw.circle(surface, COLOR_VILLAGER_OUTLINE, (sx, char_y), r, outline_w)

        # Visual Jenazah yang sedang dipanggul (Agent 3 Gravedigger)
        if getattr(self, "carrying_corpse_id", None):
            cc_w = int(r * 2.2)
            cc_h = max(4, int(r * 1.0))
            cc_rect = pygame.Rect(sx - cc_w // 2, char_y - int(r * 0.4), cc_w, cc_h)
            pygame.draw.ellipse(surface, (148, 163, 184), cc_rect)
            pygame.draw.ellipse(surface, (51, 65, 85), cc_rect, 1)
            pygame.draw.line(surface, (100, 70, 40), (sx - cc_w // 4, char_y - int(r * 0.4)), (sx - cc_w // 4, char_y - int(r * 0.4) + cc_h), 1)
            pygame.draw.line(surface, (100, 70, 40), (sx + cc_w // 4, char_y - int(r * 0.4)), (sx + cc_w // 4, char_y - int(r * 0.4) + cc_h), 1)

        # 3. Mata / Direction Pointer
        eye_dist = r * 0.55
        eye_x = sx + int(math.cos(self.facing_angle) * eye_dist)
        eye_y = char_y + int(math.sin(self.facing_angle) * eye_dist)
        eye_r = max(2, int(4 * camera.zoom))
        pygame.draw.circle(surface, (255, 255, 255), (eye_x, eye_y), eye_r)
        pygame.draw.circle(surface, COLOR_VILLAGER_OUTLINE, (eye_x, eye_y), eye_r, 1)

        # 4. Alat Kerja yang Sedang Dipegang (Cangkul / Siraman / Sickle / Hammer)
        hand_dist = r * 0.85
        hx = sx + int(math.cos(self.facing_angle + 0.45) * hand_dist)
        hy = char_y + int(math.sin(self.facing_angle + 0.45) * hand_dist)

        active_t = getattr(self, "active_tool", None)
        if not active_t:
            if self.task in ("TILLING", "DIGGING_GRAVE", "DIGGING", "BURYING"):
                active_t = "Hoe"
            elif self.task == "WATERING":
                active_t = "Watering_Can"
            elif self.task == "HARVESTING":
                active_t = "Sickle"
            elif self.task in ("BUILDING", "REPAIRING"):
                active_t = "Hammer"

        if active_t == "Hoe":
            is_hoeing = (getattr(self, "tilling_timer", 0.0) > 0.0 or
                         getattr(self, "digging_timer", 0.0) > 0.0 or
                         (self.task in ("TILLING", "DIGGING_GRAVE", "DIGGING", "BURYING") and not getattr(self, "is_moving", False)))
            shaft_len = int(16 * camera.zoom)
            blade_w = max(4, int(7 * camera.zoom))

            if is_hoeing:
                t_val = getattr(self, "tilling_timer", 0.0) or getattr(self, "digging_timer", 0.0) or (time.time() * 0.8)
                swing_phase = (t_val * 7.0) % (math.pi * 2.0)
                swing_val = math.sin(swing_phase)
                hoe_angle = self.facing_angle - 0.4 + swing_val * 0.75
                end_x = hx + int(math.cos(hoe_angle) * shaft_len)
                end_y = hy + int(math.sin(hoe_angle) * shaft_len)

                pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
                perp = hoe_angle + math.pi / 2.0
                bx1 = end_x + int(math.cos(perp) * blade_w)
                by1 = end_y + int(math.sin(perp) * blade_w)
                bx2 = end_x - int(math.cos(perp) * (blade_w // 2))
                by2 = end_y - int(math.sin(perp) * (blade_w // 2))
                pygame.draw.line(surface, (100, 116, 139), (bx1, by1), (bx2, by2), max(2, int(4 * camera.zoom)))

                if swing_val < -0.3:
                    for p_i in range(3):
                        p_rad = max(1, int(2 * camera.zoom))
                        p_dx = int(math.cos(swing_phase * 2 + p_i) * (6 * camera.zoom))
                        p_dy = int(math.sin(swing_phase * 2 + p_i) * (4 * camera.zoom))
                        soil_color = (101, 67, 33) if self.task == "TILLING" else (80, 60, 40)
                        pygame.draw.circle(surface, soil_color, (end_x + p_dx, end_y + p_dy), p_rad)
            else:
                end_x = hx + int(math.cos(self.facing_angle) * shaft_len)
                end_y = hy + int(math.sin(self.facing_angle) * shaft_len)
                pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
                perp = self.facing_angle + math.pi / 2.0
                bx1 = end_x + int(math.cos(perp) * blade_w)
                by1 = end_y + int(math.sin(perp) * blade_w)
                bx2 = end_x - int(math.cos(perp) * (blade_w // 2))
                by2 = end_y - int(math.sin(perp) * (blade_w // 2))
                pygame.draw.line(surface, (100, 116, 139), (bx1, by1), (bx2, by2), max(2, int(4 * camera.zoom)))

        elif active_t == "Watering_Can":
            is_watering = (getattr(self, "watering_timer", 0.0) > 0.0 or
                           (self.task == "WATERING" and not getattr(self, "is_moving", False)))
            pot_r = max(4, int(5 * camera.zoom))

            if is_watering:
                tilt = self.facing_angle + 0.35 + math.sin(time.time() * 4.0) * 0.08
                pot_x = hx + int(math.cos(tilt) * 2)
                pot_y = hy + int(math.sin(tilt) * 2)
                pygame.draw.circle(surface, (180, 105, 55), (pot_x, pot_y), pot_r)
                pygame.draw.circle(surface, (120, 65, 30), (pot_x, pot_y), pot_r, 1)
                pygame.draw.arc(surface, (100, 50, 20), (pot_x - pot_r, pot_y - pot_r - 3, pot_r * 2, pot_r * 2), 0, math.pi, max(1, int(2 * camera.zoom)))

                spout_len = int(12 * camera.zoom)
                spout_x = pot_x + int(math.cos(tilt) * spout_len)
                spout_y = pot_y + int(math.sin(tilt) * spout_len)
                pygame.draw.line(surface, (160, 90, 45), (pot_x, pot_y - 1), (spout_x, spout_y), max(2, int(2 * camera.zoom)))
                rose_r = max(2, int(3 * camera.zoom))
                pygame.draw.circle(surface, (217, 149, 44), (spout_x, spout_y), rose_r)

                for i in range(1, 4):
                    d_phase = (time.time() * 8.0 + i * 1.5) % 4.0
                    drop_x = spout_x + int(math.cos(self.facing_angle) * (d_phase * 2.5 * camera.zoom))
                    drop_y = spout_y + int(math.sin(self.facing_angle) * (d_phase * 1.5 * camera.zoom)) + int(d_phase * 2.2 * camera.zoom)
                    pygame.draw.circle(surface, (186, 230, 253), (drop_x, drop_y), max(1, int(2 * camera.zoom)))

                puddle_x = spout_x + int(math.cos(self.facing_angle) * (8 * camera.zoom))
                puddle_y = spout_y + int(7 * camera.zoom)
                puddle_rect = pygame.Rect(puddle_x - int(5 * camera.zoom), puddle_y - int(2 * camera.zoom), int(10 * camera.zoom), int(4 * camera.zoom))
                pygame.draw.ellipse(surface, (56, 189, 248), puddle_rect, 1)
            else:
                pygame.draw.circle(surface, (180, 105, 55), (hx, hy), pot_r)
                pygame.draw.circle(surface, (120, 65, 30), (hx, hy), pot_r, 1)
                pygame.draw.arc(surface, (100, 50, 20), (hx - pot_r, hy - pot_r - 3, pot_r * 2, pot_r * 2), 0, math.pi, max(1, int(2 * camera.zoom)))
                spout_len = int(10 * camera.zoom)
                spout_x = hx + int(math.cos(self.facing_angle) * spout_len)
                spout_y = hy + int(math.sin(self.facing_angle) * spout_len)
                pygame.draw.line(surface, (160, 90, 45), (hx, hy - 1), (spout_x, spout_y), max(2, int(2 * camera.zoom)))
                rose_r = max(2, int(3 * camera.zoom))
                pygame.draw.circle(surface, (217, 149, 44), (spout_x, spout_y), rose_r)

        elif active_t == "Sickle":
            is_harvesting = (self.task == "HARVESTING" and not getattr(self, "is_moving", False))
            arc_r = max(4, int(7 * camera.zoom))
            if is_harvesting:
                sweep = math.sin(time.time() * 7.0) * 0.75
                blade_angle = self.facing_angle + sweep
                pygame.draw.circle(surface, (180, 120, 70), (hx, hy), max(2, int(3 * camera.zoom)))
                pygame.draw.arc(surface, (226, 232, 240), (hx - arc_r // 2, hy - arc_r, arc_r * 2, arc_r * 2), blade_angle, blade_angle + math.pi * 0.9, max(2, int(2 * camera.zoom)))
                if abs(sweep) > 0.4:
                    chip_x = hx + int(math.cos(blade_angle) * (8 * camera.zoom))
                    chip_y = hy + int(math.sin(blade_angle) * (8 * camera.zoom))
                    pygame.draw.circle(surface, (234, 179, 8), (chip_x, chip_y), max(1, int(2 * camera.zoom)))
            else:
                pygame.draw.circle(surface, (180, 120, 70), (hx, hy), max(2, int(3 * camera.zoom)))
                pygame.draw.arc(surface, (226, 232, 240), (hx - arc_r // 2, hy - arc_r, arc_r * 2, arc_r * 2), self.facing_angle, self.facing_angle + math.pi * 0.9, max(2, int(2 * camera.zoom)))

        elif active_t == "Hammer":
            is_building = (self.task in ("BUILDING", "REPAIRING") and not getattr(self, "is_moving", False))
            shaft_len = int(14 * camera.zoom)
            head_w = max(4, int(8 * camera.zoom))
            head_h = max(3, int(5 * camera.zoom))
            if is_building:
                strike_swing = math.sin(time.time() * 8.0) * 0.6
                h_angle = self.facing_angle + strike_swing
                end_x = hx + int(math.cos(h_angle) * shaft_len)
                end_y = hy + int(math.sin(h_angle) * shaft_len)
                pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
                pygame.draw.rect(surface, (148, 163, 184), (end_x - head_w // 2, end_y - head_h // 2, head_w, head_h))
                if strike_swing < -0.3:
                    pygame.draw.circle(surface, (253, 224, 71), (end_x, end_y), max(1, int(2 * camera.zoom)))
            else:
                end_x = hx + int(math.cos(self.facing_angle) * shaft_len)
                end_y = hy + int(math.sin(self.facing_angle) * shaft_len)
                pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
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
        self.pending_death_recovery = []  # list of {"deceased_id": ..., "gx": ..., "gy": ..., "claimed_by": ...}

    @property
    def is_extinct(self):
        return self.living_member_count == 0

    def register_death_drop(self, deceased_id, gx, gy):
        """Registers a dropped personal inventory location from a deceased family member."""
        if not hasattr(self, "pending_death_recovery"):
            self.pending_death_recovery = []
        d_id = str(deceased_id)
        if not any(d.get("deceased_id") == d_id for d in self.pending_death_recovery):
            self.pending_death_recovery.append({
                "deceased_id": d_id,
                "gx": int(gx),
                "gy": int(gy),
                "claimed_by": None
            })

    def get_available_recovery_representative(self):
        """Finds an available living member of the household to recover death items."""
        living = [m for m in self.living_members if getattr(m, "is_alive", True)]
        if not living:
            return None
        candidates = [
            m for m in living
            if m.task not in ("SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET", "RECOVER_DEATH_ITEMS")
            and getattr(m, "hunger", 100.0) > 20.0
            and getattr(m, "thirst", 100.0) > 20.0
            and getattr(m, "need_toilet", 100.0) > 20.0
        ]
        if candidates:
            return candidates[0]
        for m in living:
            if m.task != "RECOVER_DEATH_ITEMS":
                return m
        return None

    def claim_death_drop(self, villager_id):
        """Exclusively claims a pending death drop for a representative."""
        if not hasattr(self, "pending_death_recovery"):
            self.pending_death_recovery = []
        v_id = str(villager_id)
        for drop in self.pending_death_recovery:
            if drop.get("claimed_by") is None:
                drop["claimed_by"] = v_id
                return drop
            elif drop.get("claimed_by") == v_id:
                return drop
        return None

    def complete_death_drop(self, deceased_id):
        """Marks a death recovery task completed and removes it from pending list."""
        if not hasattr(self, "pending_death_recovery"):
            self.pending_death_recovery = []
        d_id = str(deceased_id)
        self.pending_death_recovery = [d for d in self.pending_death_recovery if d.get("deceased_id") != d_id]

    def release_death_drop_claim(self, villager_id):
        """Releases claim if representative gets interrupted or dies."""
        if not hasattr(self, "pending_death_recovery"):
            return
        v_id = str(villager_id)
        for d in self.pending_death_recovery:
            if d.get("claimed_by") == v_id:
                d["claimed_by"] = None

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
        """
        Derives total available food from actual household-owned items categorized as FOOD.
        Single source of truth reading directly from storage chests and ground stockpiles.
        Zero hardcoded item checks.
        """
        total = 0
        fam_str = str(self.id)
        if furniture_manager:
            checked_chests = set()
            furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture_list", []))
            for f in furn_list:
                if str(getattr(f, "family_id", "")) == fam_str and not getattr(f, "is_dropped", False) and hasattr(f, "inventory") and isinstance(f.inventory, dict):
                    checked_chests.add(id(f))
                    for it_name, count in f.inventory.items():
                        if is_food_item(it_name) and count > 0:
                            total += count
            if not checked_chests:
                chest = furniture_manager.get_storage_for_family(fam_str)
                if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
                    for it_name, count in chest.inventory.items():
                        if is_food_item(it_name) and count > 0:
                            total += count
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                    if is_food_item(getattr(s, "resource_type", "")):
                        total += getattr(s, "amount", 0)
        return total

    def get_water_stock(self, furniture_manager=None, stockpile_manager=None):
        """
        Derives total available water from actual household-owned water resources.
        Single source of truth reading directly from storage chests and ground stockpiles.
        """
        total = 0
        fam_str = str(self.id)
        if furniture_manager:
            checked_chests = set()
            furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture_list", []))
            for f in furn_list:
                if str(getattr(f, "family_id", "")) == fam_str and not getattr(f, "is_dropped", False) and hasattr(f, "inventory") and isinstance(f.inventory, dict):
                    checked_chests.add(id(f))
                    for it_name, count in f.inventory.items():
                        if is_water_item(it_name) and count > 0:
                            total += count
            if not checked_chests:
                chest = furniture_manager.get_storage_for_family(fam_str)
                if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
                    for it_name, count in chest.inventory.items():
                        if is_water_item(it_name) and count > 0:
                            total += count
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == fam_str:
                    if is_water_item(getattr(s, "resource_type", "")):
                        total += getattr(s, "amount", 0)
        return total

    def get_possessions(self, furniture_manager=None, stockpile_manager=None, servant_manager=None):
        """
        Single Source of Truth: returns dict of {canonical_item_name: quantity}
        for all actual possessions currently owned by this household.
        """
        from game.systems.household_inventory import get_household_possessions
        return get_household_possessions(self, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager, servant_manager=servant_manager)

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

        # Dispatch pending household death recoveries
        for fam in self.families:
            if getattr(fam, "pending_death_recovery", None):
                unclaimed = [d for d in fam.pending_death_recovery if d.get("claimed_by") is None]
                if unclaimed:
                    rep = fam.get_available_recovery_representative()
                    if rep:
                        drop = fam.claim_death_drop(rep.id)
                        if drop:
                            rep.interrupt_task("DEATH_RECOVERY", activity_label="Collecting dropped items of deceased family member")
                            rep.task = "RECOVER_DEATH_ITEMS"
                            rep.recovery_target_drop = drop
                            rep.recovery_state = "APPROACHING_DROP"

        for v in all_vils:
            v.update(dt, permit_manager, building_manager, all_entities, player, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, day_cycle=day_cycle, schedule_manager=schedule_manager, production_system=production_system, villager_manager=self)

        # AI entities pass freely through each other while moving.
        # AI must never pass through the Landlord/player.
        # Gentle micro-separation so no two living AI ever occupy the exact identical coordinate.
        for _ in range(2):
            for i in range(len(all_vils)):
                v1 = all_vils[i]
                if not getattr(v1, "is_alive", True):
                    continue
                for j in range(i + 1, len(all_vils)):
                    v2 = all_vils[j]
                    if not getattr(v2, "is_alive", True):
                        continue
                    dx = v1.x - v2.x
                    dy = v1.y - v2.y
                    dist = math.hypot(dx, dy)
                    if dist < 1.2:
                        push = (1.5 - dist) if dist > 0.001 else 1.5
                        angle = (i * 1.57 + j * 0.785)
                        nx = (dx / dist) if dist > 0.001 else math.cos(angle)
                        ny = (dy / dist) if dist > 0.001 else math.sin(angle)
                        v1.x += nx * (push * 0.6)
                        v1.y += ny * (push * 0.6)
                        v2.x -= nx * (push * 0.6)
                        v2.y -= ny * (push * 0.6)
                    elif getattr(v1, "task", "") == "SLEEPING" and getattr(v2, "task", "") == "SLEEPING" and dist < 8.0:
                        push = (8.0 - dist) * 0.5
                        v1.x += (dx / dist) * push
                        v1.y += (dy / dist) * push
                        v2.x -= (dx / dist) * push
                        v2.y -= (dy / dist) * push

        old_vil_pos = [(v.x, v.y) for v in all_vils]
        old_serv_pos = [(s.x, s.y) for s in all_servants] if all_servants else []

        if player:
            min_p_gap = 2.0
            for v1 in all_vils:
                if not getattr(v1, "is_alive", True):
                    continue
                dx = v1.x - player.x
                dy = v1.y - player.y
                p_dist = math.hypot(dx, dy)
                min_p_dist = player.radius + v1.radius + min_p_gap
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
        - Resets daily consumption records for living members (used for daily reports/tracking).
        - Midnight NEVER triggers death. Deaths only occur when a 24-in-game-hour countdown reaches 0.
        """
        for fam in self.families:
            for m in list(fam.living_members):
                m.daily_food_consumed = 0
                m.daily_water_consumed = 0

        # Reset church daily tax records for new day
        from game.systems.church_system import ChurchSystem
        ChurchSystem.reset_daily_taxes(day_number)

    def draw(self, surface, camera):
        self._ensure_font()
        for v in self.get_all_villagers():
            v.draw(surface, camera, self.font_bubble)

