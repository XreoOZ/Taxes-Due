"""
Servant AI System (RimWorld-style Autonomous Hauling, Work Priorities, Construction, Door Navigation & Entity Collision)
"""

import math
import random
import time
import pygame
from game.config import (
    TILE_SIZE,
    SERVANT_COUNT,
    SERVANT_RADIUS,
    SERVANT_SPEED,
    SERVANT_CARRY_CAPACITY,
    DEFAULT_PRIORITIES,
    ENTITY_AVOIDANCE_RADIUS,
    SERVANT_YIELD_FORCE,
    MIN_ENTITY_SEPARATION,
    COLOR_SERVANT_BODY,
    COLOR_SERVANT_OUTLINE,
    COLOR_SHADOW,
    RESOURCE_COLORS,
    PATH_WAYPOINT_TOLERANCE,
    STUCK_THRESHOLD_SECONDS,
    STUCK_AVOIDANCE_DURATION,
    PATH_WAIT_RECHECK_INTERVAL
)
from game.world.pathfinding import GlobalPathRegistry
from game.systems.job_tool_system import (
    get_job_required_tools,
    get_missing_tools_for_worker,
    get_irrelevant_tools_in_inventory,
    collect_all_job_tools,
    deposit_irrelevant_tools,
    is_tool_item
)

class Servant:
    def __init__(self, servant_id, name, x, y):
        self.id = servant_id
        self.name = name
        self.x = float(x)
        self.y = float(y)
        self.radius = SERVANT_RADIUS
        self.speed = SERVANT_SPEED
        self.facing_angle = 0.0
        self.walk_cycle = 0.0
        self.is_moving = False

        # Work Priorities (RimWorld style: 1=Highest, 2=Normal, 3=Low, 4=Lowest, 0=Disabled)
        self.work_priorities = dict(DEFAULT_PRIORITIES)
        self.job = "Builder"
        self.previous_job = None
        self.needs_tool_reassessment = False
        self.inventory = {}
        self.active_tool = None

        # State: IDLE, FETCHING, HAULING, BUILDING, DEMOLISHING, HAULING_LOOSE_FETCH, HAULING_LOOSE_DELIVER, ALERTING
        self.state = "IDLE"
        self.target_site = None
        self.target_demolition = None
        self.target_res = None
        self.target_storage_pos = None

        # Loose items hauling targets
        self.target_loose_stack = None
        self.target_storage_tile = None

        # Royal Grant hauling targets
        self.target_grant_order = None
        self.target_grant_stack = None
        self.target_grant_pos = None
        self.target_grant_dest = None
        self.target_grant_fam_id = None
        self.target_grant_res = None
        self.target_grant_amount = 0

        # Carried items (Max 5 items)
        self.carried_res = None
        self.carried_amount = 0
        self.carrying_furniture = None

        # Dialogue / Speech Bubble
        self.speech_text = None
        self.speech_timer = 0.0

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

        self.idle_wander_timer = random.uniform(1.0, 3.0)
        self.idle_target = (self.x, self.y)

    def say(self, text, duration=3.5):
        self.speech_text = text
        self.speech_timer = duration

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
        self.say(f"Received {amount}x {item_name}!", duration=2.5)

    def grant_item(self, item_name, amount=1):
        """Alias untuk receive_granted_item"""
        self.receive_granted_item(item_name, amount)

    def set_job(self, new_job):
        """Mengubah pekerjaan/profesi worker secara dinamis dan memicu reassessment alat"""
        if getattr(self, "job", None) == new_job:
            return
        self.previous_job = getattr(self, "job", None)
        self.job = new_job
        self.needs_tool_reassessment = True

    def set_priority(self, work_type, priority_value):
        """Set priority 0 (disabled), 1 (highest), 2, 3, or 4 (lowest)"""
        if work_type in self.work_priorities:
            self.work_priorities[work_type] = priority_value

    def cycle_priority(self, work_type):
        """Cycle priority: 1 -> 2 -> 3 -> 4 -> 0 (Off) -> 1"""
        cur = self.work_priorities.get(work_type, 1)
        next_p = (cur % 4) + 1 if cur > 0 and cur < 4 else (0 if cur == 4 else 1)
        self.work_priorities[work_type] = next_p
        return next_p

    def update(self, dt, building_manager, permit_manager, stockpile_manager, resources, player, all_servants=None, furniture_manager=None, villager_manager=None, servant_manager=None, all_entities=None):
        # Update Speech Timer
        if self.speech_timer > 0:
            self.speech_timer -= dt
            if self.speech_timer <= 0:
                self.speech_text = None

        pending_demo = building_manager.get_pending_demolition()
        pending_site = building_manager.get_pending_site()

        # -----------------------------------------------------------------
        # State Machine Logic
        # -----------------------------------------------------------------
        if getattr(self, "carrying_furniture", None):
            f = self.carrying_furniture
            if not f.designated_target:
                f.carrier_id = None
                self.carrying_furniture = None
                self.state = "IDLE"
            else:
                tgx, tgy, target_permit_id = f.designated_target
                dest_x = (tgx + 0.5) * TILE_SIZE
                dest_y = (tgy + 0.5) * TILE_SIZE
                self.state = "HAULING"
                arrived = self._move_towards(dest_x, dest_y, dt, arrival_dist=18, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager)
                if arrived:
                    if furniture_manager:
                        furniture_manager.move_furniture(f.id, tgx, tgy, permit_manager, villager_manager=villager_manager)
                    f.cancel_move()
                    self.carrying_furniture = None
                    self.state = "IDLE"
                    self.say(f"Reinstalled {f.name}, my Lord!", duration=3.0)
            return

        if self.state == "IDLE":
            assigned = self._evaluate_and_assign_priority_task(
                building_manager, permit_manager, stockpile_manager, resources, player, all_servants,
                furniture_manager=furniture_manager, villager_manager=villager_manager, servant_manager=servant_manager
            )
            if not assigned:
                self._idle_behavior(dt, player, all_servants, building_manager, all_entities=all_entities, furniture_manager=furniture_manager)

        elif self.state == "DEMOLISHING":
            if not self.target_demolition or self.target_demolition not in building_manager.demolition_sites:
                self._reset_task()
                return

            wx, wy = self._get_site_work_pos(self.target_demolition, all_servants)
            self._move_towards(wx, wy, dt, arrival_dist=20, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager)

            self.target_demolition.progress += dt
            self.walk_cycle += dt * 10.0

            if self.target_demolition.is_complete():
                self.say("Demolished! Salvaged materials dropped on ground, Lord!")
                building_manager.complete_demolition(self.target_demolition, resources, stockpile_manager)
                self._reset_task()

        elif self.state == "FETCHING":
            if not pending_site or pending_site != self.target_site:
                self._reset_task()
                return

            # Move towards storage stack or storage position
            if self.target_storage_pos:
                tx, ty = self.target_storage_pos
                if self._move_towards(tx, ty, dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=False):
                    needed_at_site = (self.target_site.required_cost[self.target_res] - 
                                     self.target_site.delivered_cost[self.target_res])

                    storage_stack = getattr(self, "target_storage_stack", None)
                    if not storage_stack or storage_stack not in stockpile_manager.stacks or storage_stack.amount <= 0:
                        for s in stockpile_manager.stacks:
                            if s.resource_type == self.target_res and s.amount > 0:
                                storage_stack = s
                                break

                    if storage_stack and storage_stack.amount > 0:
                        pick_amt = min(SERVANT_CARRY_CAPACITY, storage_stack.amount, needed_at_site)
                        actual = stockpile_manager.take_from_stack(storage_stack, pick_amt)
                        self.carried_res = self.target_res
                        self.carried_amount = actual
                        stockpile_manager.refresh_stacks(resources, permit_manager)
                        self.target_storage_stack = None
                        self.target_storage_reserved = 0
                        # Clear old path & reservation before HAULING
                        reg = GlobalPathRegistry.get_instance()
                        reg.release_reservation(self.id)
                        self.current_path = []
                        self.path_index = 0
                        self.path_target = None
                        self.path_target_tile = None
                        self.is_waiting_for_path = False
                        self.wait_timer = 0.0
                        self.repath_cooldown = 0.0
                        self.state = "HAULING"
                        self.say(f"Delivering {self.carried_res} to site...")
                    else:
                        # Resource out of stock
                        self._trigger_alert(self.target_res)

        elif self.state == "HAULING":
            if not pending_site or pending_site != self.target_site:
                # Site cancelled/done; return carried items to ground as drop
                if self.carried_res and self.carried_amount > 0:
                    gx = int(math.floor(self.x / TILE_SIZE))
                    gy = int(math.floor(self.y / TILE_SIZE))
                    stockpile_manager.drop_resource(self.carried_res, self.carried_amount, gx, gy)
                    stockpile_manager.refresh_stacks(resources, permit_manager)
                self._reset_task()
                return

            # Move towards construction site work position around perimeter
            wx, wy = self._get_site_work_pos(self.target_site, all_servants)
            if self._move_towards(wx, wy, dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=False):
                # Deposit carried resource into construction site
                self.target_site.deposit_resource(self.carried_res, self.carried_amount)
                self.carried_res = None
                self.carried_amount = 0
                reg = GlobalPathRegistry.get_instance()
                reg.release_reservation(self.id)
                self.current_path = []
                self.path_index = 0
                self.path_target = None
                self.path_target_tile = None
                self.is_waiting_for_path = False
                self.wait_timer = 0.0
                self.repath_cooldown = 0.0

                # Check if materials complete or need to re-evaluate next action
                if self.target_site.is_materials_complete():
                    if self.work_priorities.get("Building", 0) > 0:
                        self.state = "BUILDING"
                        self.say("Materials delivered! Constructing building...")
                    else:
                        self._reset_task()
                else:
                    # Finished this delivery trip; reset to IDLE so priorities are cleanly re-evaluated
                    self._reset_task()
                return

        elif self.state == "BUILDING":
            if not pending_site or pending_site != self.target_site:
                self._reset_task()
                return

            # Move to construction site work position around perimeter
            wx, wy = self._get_site_work_pos(self.target_site, all_servants)
            self._move_towards(wx, wy, dt, arrival_dist=20, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=False)

            # Hammering construction progress
            self.target_site.build_progress += dt
            self.walk_cycle += dt * 10.0

            if self.target_site.is_complete():
                self.say("Building complete, my Lord!")
                # Step safely outside the newly finished building's door threshold
                cur_gx = int(math.floor(self.x / TILE_SIZE))
                cur_gy = int(math.floor(self.y / TILE_SIZE))
                b_new = building_manager.get_building_at(cur_gx, cur_gy)
                if b_new:
                    out_x, out_y = b_new.get_door_world_outside(TILE_SIZE)
                    self.x, self.y = out_x, out_y
                self._reset_task()

        elif self.state == "HAULING_LOOSE_FETCH":
            # Loose item hauling: Walking to loose stack to pick it up
            if not self.target_loose_stack or self.target_loose_stack not in stockpile_manager.stacks:
                self._reset_task()
                return

            tx = (self.target_loose_stack.grid_x + 0.5) * TILE_SIZE
            ty = (self.target_loose_stack.grid_y + 0.5) * TILE_SIZE

            if self._move_towards(tx, ty, dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=True):
                # Arrived at loose item! Pick it up
                res_type = self.target_loose_stack.resource_type
                avail_dest = stockpile_manager.get_available_storage_tile(permit_manager, res_type)

                if not avail_dest:
                    self.say("No storage lot available to haul to, Lord!")
                    self._reset_task()
                    return

                pick_amt = min(SERVANT_CARRY_CAPACITY, self.target_loose_stack.amount)
                actual = stockpile_manager.take_from_stack(self.target_loose_stack, pick_amt)
                if actual > 0:
                    self.carried_res = res_type
                    self.carried_amount = actual
                    self.target_storage_tile = avail_dest
                    self.state = "HAULING_LOOSE_DELIVER"
                    self.say(f"Hauling {self.carried_res} to storage...")
                else:
                    self._reset_task()

        elif self.state == "HAULING_LOOSE_DELIVER":
            # Delivering loose items into an active storage permit tile
            if not self.target_storage_tile:
                self._reset_task()
                return

            tx = (self.target_storage_tile[0] + 0.5) * TILE_SIZE
            ty = (self.target_storage_tile[1] + 0.5) * TILE_SIZE

            if self._move_towards(tx, ty, dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager):
                # Arrived at storage! Deposit item
                stockpile_manager.deposit_to_tile(
                    self.carried_res, self.carried_amount,
                    self.target_storage_tile[0], self.target_storage_tile[1]
                )
                stockpile_manager.refresh_stacks(resources, permit_manager)
                self.say(f"Stored {self.carried_amount} {self.carried_res} in stockpile!")
                self.carried_res = None
                self.carried_amount = 0
                self.target_storage_tile = None
                self.target_loose_stack = None
                self.state = "IDLE"

        elif self.state == "ALERTING":
            # Running towards player to report lack of materials
            dist_to_player = math.hypot(player.x - self.x, player.y - self.y)
            self._move_towards(player.x, player.y, dt, arrival_dist=60, all_servants=all_servants, player=None, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager)

            if dist_to_player <= 80:
                if not self.speech_text:
                    self.say(f"My Lord, we need more {self.target_res}!")
                if self.speech_timer <= 0.5:
                    self._reset_task()

        elif self.state == "GRANT_FETCH":
            if not self.target_grant_stack or self.target_grant_stack not in stockpile_manager.stacks or self.target_grant_stack.amount <= 0:
                self._reset_task()
                return

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_grant_pos[0], self.target_grant_pos[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                actual = stockpile_manager.take_from_stack(self.target_grant_stack, self.target_grant_amount)
                if actual > 0:
                    stockpile_manager.refresh_stacks(resources, permit_manager)
                    self.carried_res = self.target_grant_res
                    self.carried_amount = actual
                    reg = GlobalPathRegistry.get_instance()
                    reg.release_reservation(self.id)
                    self.current_path = []
                    self.path_index = 0
                    self.path_target = None
                    self.path_target_tile = None
                    self.is_waiting_for_path = False
                    self.wait_timer = 0.0
                    self.repath_cooldown = 0.0
                    self.state = "GRANT_DELIVER"
                    self.say(f"Delivering {actual} {self.carried_res} to family...")
                else:
                    self._reset_task()

        elif self.state == "GRANT_DELIVER":
            if not self.target_grant_dest:
                self._reset_task()
                return

            chest = furniture_manager.get_storage_for_family(self.target_grant_fam_id, building_manager=building_manager, villager_manager=villager_manager, permit_manager=permit_manager) if furniture_manager else None
            close_to_chest = False
            if chest:
                cx, cy = chest.get_world_pos(TILE_SIZE)
                if math.hypot(cx - self.x, cy - self.y) <= 36.0:
                    close_to_chest = True

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils

            if close_to_chest or self._move_towards(self.target_grant_dest[0], self.target_grant_dest[1], dt, arrival_dist=32, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                # Arrived at family home or chest!
                deposited = False
                if chest:
                    chest.store_item(self.carried_res, self.carried_amount)
                    deposited = True
                if not deposited:
                    cur_gx = int(math.floor(self.x / TILE_SIZE))
                    cur_gy = int(math.floor(self.y / TILE_SIZE))
                    stockpile_manager.drop_resource(self.carried_res, self.carried_amount, cur_gx, cur_gy, owner_type="villager", owner_id=str(self.target_grant_fam_id))

                if self.target_grant_order:
                    self.target_grant_order["delivered"] = self.target_grant_order.get("delivered", 0) + self.carried_amount
                    self.target_grant_order["in_transit"] = max(0, self.target_grant_order.get("in_transit", 0) - self.carried_amount)
                    if self.target_grant_order["delivered"] >= self.target_grant_order["amount"]:
                        if servant_manager and self.target_grant_order in getattr(servant_manager, "grant_orders", []):
                            servant_manager.grant_orders.remove(self.target_grant_order)

                self.say(f"Delivered {self.carried_amount} {self.carried_res} to household, my Lord!", duration=2.5)
                self.carried_res = None
                self.carried_amount = 0
                reg = GlobalPathRegistry.get_instance()
                reg.release_reservation(self.id)
                self.current_path = []
                self.path_index = 0
                self.path_target = None
                self.path_target_tile = None
                self.is_waiting_for_path = False
                self.wait_timer = 0.0
                self.repath_cooldown = 0.0
                self._reset_task()

    def _evaluate_and_assign_priority_task(self, building_manager, permit_manager, stockpile_manager, resources, player, all_servants=None, furniture_manager=None, villager_manager=None, servant_manager=None):
        """RimWorld-style Priority Scan: 1 (Highest) down to 4 (Lowest)"""
        # Royal Decree: Hauling Granted Items from Landlord Storage to Villager Households
        if servant_manager and getattr(servant_manager, "grant_orders", None):
            for order in servant_manager.grant_orders:
                remaining = order["amount"] - order.get("in_transit", 0) - order.get("delivered", 0)
                if remaining > 0:
                    item_type = order["item_type"]
                    # Find stack in Landlord's stockpile with available capacity
                    storage_stack = None
                    for s in stockpile_manager.stacks:
                        if s.resource_type == item_type and getattr(s, "owner_type", "landlord") == "landlord" and getattr(s, "available_amount", s.amount) > 0:
                            storage_stack = s
                            break
                    if storage_stack:
                        # Determine family destination
                        fam_id = order["family_id"]
                        dest_pos = None
                        if furniture_manager:
                            chest = furniture_manager.get_storage_for_family(fam_id, building_manager=building_manager, villager_manager=villager_manager, permit_manager=permit_manager)
                            if chest:
                                dest_pos = chest.get_world_pos(TILE_SIZE)
                        if not dest_pos and villager_manager:
                            fam = villager_manager.get_family_by_id(fam_id)
                            if fam and fam.assigned_permit_id:
                                hp = next((p for p in permit_manager.permits if p.id == fam.assigned_permit_id), None)
                                if hp:
                                    dest_pos = ((hp.grid_x + hp.tiles_w / 2.0) * TILE_SIZE, (hp.grid_y + hp.tiles_h / 2.0) * TILE_SIZE)
                        if not dest_pos:
                            dest_pos = (player.x + 40, player.y + 40)

                        amt_to_take = min(SERVANT_CARRY_CAPACITY, remaining, getattr(storage_stack, "available_amount", storage_stack.amount))
                        if amt_to_take <= 0:
                            continue
                        order["in_transit"] = order.get("in_transit", 0) + amt_to_take
                        if hasattr(storage_stack, "reserve"):
                            storage_stack.reserve(amt_to_take)

                        # Clear old path & reservation before switching task
                        reg = GlobalPathRegistry.get_instance()
                        reg.release_reservation(self.id)
                        self.current_path = []
                        self.path_index = 0
                        self.path_target = None
                        self.path_target_tile = None
                        self.is_waiting_for_path = False
                        self.wait_timer = 0.0
                        self.repath_cooldown = 0.0

                        worker_idx = all_servants.index(self) if (all_servants and self in all_servants) else 0
                        offsets = [(0, -10), (0, 10), (-10, 0), (10, 0)]
                        ox, oy = offsets[worker_idx % len(offsets)]

                        self.target_grant_order = order
                        self.target_grant_stack = storage_stack
                        self.target_grant_pos = ((storage_stack.grid_x + 0.5) * TILE_SIZE + ox, (storage_stack.grid_y + 0.5) * TILE_SIZE + oy)
                        self.target_grant_dest = dest_pos
                        self.target_grant_fam_id = fam_id
                        self.target_grant_res = item_type
                        self.target_grant_amount = amt_to_take
                        self.state = "GRANT_FETCH"
                        self.say(f"Fetching {amt_to_take} {item_type} for The {fam_id} Family, Lord!")
                        return True

        # Hauling Designated Landlord / Unassigned Furniture
        if furniture_manager:
            for f in furniture_manager.furnitures:
                if f.designated_target and f.carrier_id is None and (f.family_id is None or (villager_manager and not villager_manager.get_family_by_id(f.family_id))):
                    f.carrier_id = self.id
                    self.carrying_furniture = f
                    self.state = "HAULING"
                    self.say(f"Moving {f.name} as commanded, Lord!")
                    return True

        pending_demo = building_manager.get_pending_demolition()
        pending_site = building_manager.get_pending_site()
        loose_stacks = stockpile_manager.get_loose_stacks(permit_manager)

        if all_servants is None:
            all_servants = [self]

        claimed_loose_stacks = {
            other.target_loose_stack
            for other in all_servants
            if other != self and other.target_loose_stack is not None
        }

        for p_level in [1, 2, 3, 4]:
            # 1. Building tasks at this priority: Demolition, Site Hammering & Site Materials Supply
            if self.work_priorities.get("Building", 0) == p_level:
                # A. Demolition task
                if pending_demo:
                    self.target_demolition = pending_demo
                    self.state = "DEMOLISHING"
                    self.say("Dismantling structure, my Lord!")
                    return True

                # B. Construction site (Fetch required materials for site OR hammer structure)
                if pending_site:
                    if pending_site.is_materials_complete():
                        self.target_site = pending_site
                        self.state = "BUILDING"
                        self.say("Constructing building, my Lord!")
                        return True
                    else:
                        assigned = self._assign_construction_task(pending_site, stockpile_manager, resources, player, all_servants=all_servants)
                        if assigned:
                            return True

            # 2. Hauling tasks at this priority: Haul loose ground items into storage (Primary)
            #    or assist supplying construction sites ONLY if no loose items exist
            if self.work_priorities.get("Hauling", 0) == p_level:
                # A. Hauling loose items on ground into active storage
                if loose_stacks:
                    for stack in loose_stacks:
                        # Avoid duplicate targeting if another worker is already fetching this small stack
                        if stack in claimed_loose_stacks and stack.amount <= SERVANT_CARRY_CAPACITY:
                            continue

                        dest_tile = stockpile_manager.get_available_storage_tile(permit_manager, stack.resource_type)
                        if dest_tile:
                            self.target_loose_stack = stack
                            self.state = "HAULING_LOOSE_FETCH"
                            self.say(f"Hauling loose {stack.resource_type} to storage!")
                            return True

                # B. Hauling materials to construction site ONLY IF no loose items are left on the ground!
                if pending_site and not pending_site.is_materials_complete() and not loose_stacks:
                    assigned = self._assign_construction_task(pending_site, stockpile_manager, resources, player, all_servants=all_servants)
                    if assigned:
                        return True

        return False

    def _assign_construction_task(self, site, stockpile_manager, resources, player, all_servants=None):
        self.target_site = site

        if site.is_materials_complete():
            if self.work_priorities.get("Building", 0) > 0:
                self.state = "BUILDING"
                self.say("Constructing building, my Lord!")
                return True
            return False

        needed_res = site.get_needed_resource()
        if not needed_res:
            if site.is_materials_complete() and self.work_priorities.get("Building", 0) > 0:
                self.state = "BUILDING"
                self.say("Constructing building, my Lord!")
                return True
            return False

        # Find resource stack in stockpile or ground with available quantity
        storage_stack = None
        for s in stockpile_manager.stacks:
            if s.resource_type == needed_res and getattr(s, "available_amount", s.amount) > 0:
                storage_stack = s
                break

        if not storage_stack:
            self._trigger_alert(needed_res)
            return False

        # Reserve resource at site and on stack
        reserved = site.reserve_resource(needed_res, SERVANT_CARRY_CAPACITY)
        if reserved > 0:
            actual_res = storage_stack.reserve(reserved) if hasattr(storage_stack, "reserve") else reserved
            self.target_res = needed_res
            self.target_storage_stack = storage_stack
            self.target_storage_reserved = actual_res

            # Clear old path & reservation before switching task
            reg = GlobalPathRegistry.get_instance()
            reg.release_reservation(self.id)
            self.current_path = []
            self.path_index = 0
            self.path_target = None
            self.path_target_tile = None
            self.is_waiting_for_path = False
            self.wait_timer = 0.0
            self.repath_cooldown = 0.0

            # Staggered interaction offset around resource stack to prevent stacking
            worker_idx = all_servants.index(self) if (all_servants and self in all_servants) else 0
            offsets = [(0, -10), (0, 10), (-10, 0), (10, 0)]
            ox, oy = offsets[worker_idx % len(offsets)]
            self.target_storage_pos = ((storage_stack.grid_x + 0.5) * TILE_SIZE + ox, (storage_stack.grid_y + 0.5) * TILE_SIZE + oy)
            self.state = "FETCHING"
            self.say(f"Supplying {needed_res} for {site.name}!")
            return True

        return False

    def _trigger_alert(self, needed_res):
        self.target_res = needed_res
        self.state = "ALERTING"
        self.say(f"Lord! We lack {needed_res} for the construction!")

    def _reset_task(self):
        if self.target_site and self.target_res and self.state == "FETCHING":
            if self.target_res in self.target_site.reserved_cost:
                self.target_site.reserved_cost[self.target_res] = max(
                    0, self.target_site.reserved_cost[self.target_res] - SERVANT_CARRY_CAPACITY
                )
        if getattr(self, "target_storage_stack", None) and getattr(self, "target_storage_reserved", 0) > 0:
            if hasattr(self.target_storage_stack, "release_reservation"):
                self.target_storage_stack.release_reservation(self.target_storage_reserved)
        self.target_storage_stack = None
        self.target_storage_reserved = 0

        # Refund grant order in_transit count so other servants or future scans can pick it up!
        if self.target_grant_order:
            self.target_grant_order["in_transit"] = max(0, self.target_grant_order.get("in_transit", 0) - self.target_grant_amount)
        if self.target_grant_stack and hasattr(self.target_grant_stack, "release_reservation"):
            self.target_grant_stack.release_reservation(self.target_grant_amount)

        # Release any path reservation and reset route state
        reg = GlobalPathRegistry.get_instance()
        reg.release_reservation(self.id)
        self.current_path = []
        self.path_index = 0
        self.path_target = None
        self.path_target_tile = None
        self.is_waiting_for_path = False
        self.wait_timer = 0.0
        self.repath_cooldown = 0.0

        self.state = "IDLE"
        self.target_site = None
        self.target_demolition = None
        self.target_res = None
        self.target_storage_pos = None
        self.target_loose_stack = None
        self.target_storage_tile = None
        self.target_grant_order = None
        self.target_grant_stack = None
        self.target_grant_pos = None
        self.target_grant_dest = None
        self.target_grant_fam_id = None
        self.target_grant_res = None
        self.target_grant_amount = 0
        self.nav_target = None
        self.door_waypoints = []

    def _idle_behavior(self, dt, player, all_servants=None, building_manager=None, all_entities=None, furniture_manager=None):
        self.idle_wander_timer -= dt
        if self.idle_wander_timer <= 0:
            self.idle_wander_timer = random.uniform(2.5, 5.0)
            offset_x = random.uniform(-90, 90)
            offset_y = random.uniform(-90, 90)
            tx = player.x + offset_x
            ty = player.y + offset_y
            if building_manager and building_manager.is_near_any_door(tx, ty, min_dist=48.0):
                tx += 40.0 if offset_x >= 0 else -40.0
                ty += 40.0 if offset_y >= 0 else -40.0
            self.idle_target = (tx, ty)

        self._move_towards(self.idle_target[0], self.idle_target[1], dt, arrival_dist=20, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=False)

    def _move_towards(self, tx, ty, dt, arrival_dist=10, all_servants=None, player=None, building_manager=None, all_entities=None, furniture_manager=None, exclusive_target=False):
        reg = GlobalPathRegistry.get_instance()

        # 0. Penanganan Antrean Menunggu Jalur & Cooldown Re-path Throttling
        if getattr(self, "repath_cooldown", 0.0) > 0.0:
            self.repath_cooldown -= dt

        if self.wait_timer > 0.0:
            self.wait_timer -= dt
            self.is_moving = False
            if not reg.is_path_blocked_for(self.id, (self.x, self.y), (tx, ty)):
                self.wait_timer = 0.0
            else:
                return False

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

            # Hindari perabotan terpasang (Beds lain, Chest lain) kecuali petak target tujuan
            if furniture_manager and hasattr(furniture_manager, "get_occupied_tiles"):
                avoid_set.update(furniture_manager.get_occupied_tiles(exclude_tile=self.path_target_tile))

            # Hindari petak yang ditempati oleh entitas lain yang sedang tidur atau diam di tempat
            check_ents = all_entities or all_servants or []
            for other in check_ents:
                if other != self and (getattr(other, "task", "") == "SLEEPING" or not getattr(other, "is_moving", False)):
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
                    self.current_path = []
                    self.path_index = 0
                    self.is_moving = False
                    self.is_waiting_for_path = True
                    self.wait_timer = PATH_WAIT_RECHECK_INTERVAL
                    if exclusive_target:
                        reg.register_waiting(self.id, self.path_target_tile)
                    return False
            else:
                self.current_path = []
                self.path_index = 0
                self.is_moving = False
                self.is_waiting_for_path = True
                self.wait_timer = PATH_WAIT_RECHECK_INTERVAL
                self.repath_cooldown = 0.4
                if exclusive_target:
                    reg.register_waiting(self.id, self.path_target_tile)
                return False

        # 2. Prioritas Target Bersama:
        # "kalau kedua AI itu pathfindingnya ke tile yg sama, maka prioritaskan yg pertama pathfinding garisnya muncul"
        if not reg.has_priority(self.id, self.path_target_tile, self.path_seq, exclusive_target=exclusive_target):
            if getattr(self, "target_loose_stack", None) and (getattr(self.target_loose_stack, "grid_x", None), getattr(self.target_loose_stack, "grid_y", None)) == self.path_target_tile:
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
        check_ents = all_entities if all_entities else (all_servants or [])
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
                        door_phys = building_manager.is_door_occupied(b.door_pos, check_ents, exclude_entity=self, tile_size=TILE_SIZE)
                        is_outside = (dist_out <= dist_in) and not b.occupies_tile(cur_gx, cur_gy)
                        can_pass, q_pos = b.request_door_passage(self.id, is_outside, tile_size=TILE_SIZE)
                        if door_phys or (not can_pass and q_pos):
                            self.is_waiting_for_path = True
                            self.is_moving = False
                            return False
                        else:
                            self.is_waiting_for_path = False
                else:
                    if b.door_active_user == str(self.id):
                        b.release_door_passage(self.id)

        # 6. Menghindari Tabrakan Antar Karakter (Yielding Right of Way tanpa terdorong ke tembok)
        if check_ents:
            for other in check_ents:
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
        self.walk_cycle += dt * 14.0
        return False

    def _get_site_work_pos(self, site, all_servants=None):
        """Mendapatkan posisi kerja terdistribusi di sekeliling perimeter site/bangunan agar servant tidak bertumpuk"""
        if not site:
            return self.x, self.y
        cx, cy = site.get_center_world(TILE_SIZE)
        s_idx = 0
        if all_servants and self in all_servants:
            s_idx = all_servants.index(self)
        else:
            s_idx = abs(hash(str(self.id))) % 4
        total_workers = len(all_servants) if all_servants else 2
        ang = (s_idx / max(1, total_workers)) * (2.0 * math.pi) + 0.35
        sw = (getattr(site, "tiles_w", 2) * TILE_SIZE) / 2.0 + 20.0
        sh = (getattr(site, "tiles_h", 2) * TILE_SIZE) / 2.0 + 20.0
        return cx + math.cos(ang) * sw, cy + math.sin(ang) * sh

    def draw(self, surface, camera, font_bubble):
        sx, sy = camera.world_to_screen(self.x, self.y)
        r = max(4, int(self.radius * camera.zoom))
        bob = math.sin(self.walk_cycle) * (2.5 * camera.zoom) if self.is_moving else 0.0
        char_y = sy + int(bob)

        # 1. Bayangan di tanah
        shadow_w = int(r * 1.8)
        shadow_h = max(2, int(r * 0.9))
        shadow_surf = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, COLOR_SHADOW, (0, 0, shadow_w, shadow_h))
        surface.blit(shadow_surf, (sx - shadow_w // 2, sy + int(r * 0.4)))

        # 2. Badan AI Servant (Lingkaran Amber)
        pygame.draw.circle(surface, COLOR_SERVANT_BODY, (sx, char_y), r)
        outline_w = max(1, int(3 * camera.zoom))
        pygame.draw.circle(surface, COLOR_SERVANT_OUTLINE, (sx, char_y), r, outline_w)

        # 3. Mata / Pointer Arah Hadap
        eye_dist = r * 0.55
        eye_x = sx + int(math.cos(self.facing_angle) * eye_dist)
        eye_y = char_y + int(math.sin(self.facing_angle) * eye_dist)
        eye_r = max(2, int(4 * camera.zoom))
        pygame.draw.circle(surface, (255, 255, 255), (eye_x, eye_y), eye_r)
        pygame.draw.circle(surface, COLOR_SERVANT_OUTLINE, (eye_x, eye_y), eye_r, 1)

        # 4. Animasi Membawa Barang (Carrying Animation)
        if self.carried_res and self.carried_amount > 0:
            box_w = max(8, int(14 * camera.zoom))
            box_h = max(6, int(10 * camera.zoom))
            carry_x = sx + int(math.cos(self.facing_angle) * (r * 0.8)) - box_w // 2
            carry_y = char_y - r - box_h - 2

            col = RESOURCE_COLORS.get(self.carried_res, (200, 200, 200))
            pygame.draw.rect(surface, col, (carry_x, carry_y, box_w, box_h), border_radius=2)
            pygame.draw.rect(surface, (0, 0, 0), (carry_x, carry_y, box_w, box_h), width=1, border_radius=2)

        # 4.5. Membawa Furniture
        elif getattr(self, "carrying_furniture", None):
            furn = self.carrying_furniture
            box_w = max(10, int(18 * camera.zoom))
            box_h = max(8, int(14 * camera.zoom))
            carry_x = sx + int(math.cos(self.facing_angle) * (r * 0.9)) - box_w // 2
            carry_y = char_y - r - box_h - 2
            pygame.draw.rect(surface, (140, 85, 40), (carry_x, carry_y, box_w, box_h), border_radius=2)
            pygame.draw.rect(surface, (230, 180, 70), (carry_x, carry_y, box_w, box_h), width=1, border_radius=2)
            if getattr(furn, "furniture_type", "") == "bed":
                pygame.draw.rect(surface, (59, 130, 246), (carry_x + 2, carry_y + 3, box_w - 4, box_h - 5))
            else:
                pygame.draw.rect(surface, (234, 179, 8), (carry_x + box_w // 2 - 2, carry_y + box_h // 2 - 2, 4, 4))

        # 5. Speech Bubble (Pesan kepada Landlord)
        if self.speech_text and font_bubble:
            txt_surf = font_bubble.render(self.speech_text, True, (15, 23, 42))
            bw = txt_surf.get_width() + 16
            bh = txt_surf.get_height() + 10
            bx = sx - bw // 2
            by = char_y - r - bh - (18 if (self.carried_res and self.carried_amount > 0) else 10)

            # Bubble background
            pygame.draw.rect(surface, (255, 255, 255), (bx, by, bw, bh), border_radius=8)
            pygame.draw.rect(surface, (15, 23, 42), (bx, by, bw, bh), width=2, border_radius=8)

            # Bubble tail triangle
            tail_points = [
                (sx - 4, by + bh),
                (sx + 4, by + bh),
                (sx, by + bh + 6)
            ]
            pygame.draw.polygon(surface, (255, 255, 255), tail_points)
            pygame.draw.line(surface, (15, 23, 42), tail_points[0], tail_points[2], 2)
            pygame.draw.line(surface, (15, 23, 42), tail_points[1], tail_points[2], 2)

            surface.blit(txt_surf, (bx + 8, by + 5))


class ServantManager:
    def __init__(self):
        self.servants = []
        self.grant_orders = []
        self.font_bubble = None

        # Inisialisasi 2 Servant awal
        names = ["Servant Alden", "Servant Barnaby"]
        for i in range(SERVANT_COUNT):
            spawn_x = (i * 40) - 20
            spawn_y = 60
            s = Servant(f"servant_{i+1}", names[i % len(names)], spawn_x, spawn_y)
            self.servants.append(s)

    def add_grant_order(self, family_id, item_type, amount):
        """Mendaftarkan tugas angkut bantuan royal grant dari storage Landlord ke rumah keluarga Villager"""
        if amount <= 0:
            return
        self.grant_orders.append({
            "family_id": family_id,
            "item_type": item_type,
            "amount": amount,
            "in_transit": 0,
            "delivered": 0
        })

    def _ensure_font(self):
        if self.font_bubble is None:
            self.font_bubble = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def update(self, dt, building_manager, permit_manager, stockpile_manager, resources, player, furniture_manager=None, villager_manager=None):
        all_vils = villager_manager.get_all_villagers() if villager_manager else []
        all_entities = list(self.servants) + all_vils

        # 1. Update State Machine & Desired Movements
        for s in self.servants:
            s.update(dt, building_manager, permit_manager, stockpile_manager, resources, player, self.servants,
                     furniture_manager=furniture_manager, villager_manager=villager_manager, servant_manager=self, all_entities=all_entities)

        # 2. Hard Entity Collision Resolution: Servant vs Servant (Solid Physical Separation)
        min_gap = MIN_ENTITY_SEPARATION
        old_serv_pos = [(s.x, s.y) for s in self.servants]
        for i in range(len(self.servants)):
            s1 = self.servants[i]
            for j in range(i + 1, len(self.servants)):
                s2 = self.servants[j]
                dx = s2.x - s1.x
                dy = s2.y - s1.y
                dist = math.hypot(dx, dy)
                min_dist = s1.radius + s2.radius + min_gap
                if dist < min_dist:
                    if dist < 0.001:
                        dx = random.uniform(-1.0, 1.0)
                        dy = random.uniform(-1.0, 1.0)
                        dist = math.hypot(dx, dy) or 1.0

                    overlap = min_dist - dist
                    nx = dx / dist
                    ny = dy / dist

                    # Push apart symmetrically along collision normal
                    s1.x -= nx * overlap * 0.5
                    s1.y -= ny * overlap * 0.5
                    s2.x += nx * overlap * 0.5
                    s2.y += ny * overlap * 0.5

        # 3. Hard Entity Collision Resolution: Servant vs Player (Servant Yields & Steps Aside)
        if player:
            for s in self.servants:
                dx = s.x - player.x
                dy = s.y - player.y
                dist = math.hypot(dx, dy)
                min_dist = player.radius + s.radius + 6.4  # Minimum 10 cm gap (6.4 px)
                if dist < min_dist:
                    if dist < 0.001:
                        dx = math.cos(player.facing_angle) or 1.0
                        dy = math.sin(player.facing_angle) or 0.0
                        dist = math.hypot(dx, dy) or 1.0

                    overlap = min_dist - dist
                    nx = dx / dist
                    ny = dy / dist

                    # Servant is displaced 100% of overlap away from the player (player dominates)
                    s.x += nx * overlap
                    s.y += ny * overlap

                    # Servant slides sideways to clear the player's path
                    perp_x = -ny
                    perp_y = nx
                    s.x += perp_x * SERVANT_YIELD_FORCE * dt
                    s.y += perp_y * SERVANT_YIELD_FORCE * dt

                    # Polite verbal acknowledgment when stepping aside
                    if not s.speech_text and random.random() < 0.25:
                        s.say(random.choice(["Making way, Lord!", "Pardon, my Lord!", "Right away, Lord!"]), duration=1.8)

        # 4. Building Wall Collision Resolution for Servants
        if building_manager:
            for idx, s in enumerate(self.servants):
                ox, oy = old_serv_pos[idx]
                s.x, s.y = building_manager.resolve_collision(s.x, s.y, s.radius, TILE_SIZE, old_x=ox, old_y=oy)

        # 5. Re-check player vs pinned servant (if servant was backed against a wall)
        if player:
            for s in self.servants:
                dx = player.x - s.x
                dy = player.y - s.y
                dist = math.hypot(dx, dy)
                min_dist = player.radius + s.radius
                if dist < min_dist and dist > 0.001:
                    overlap = min_dist - dist
                    player.x += (dx / dist) * overlap
                    player.y += (dy / dist) * overlap

    def draw(self, surface, camera):
        self._ensure_font()
        for s in self.servants:
            s.draw(surface, camera, self.font_bubble)
