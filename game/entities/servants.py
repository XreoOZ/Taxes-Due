"""
Servant AI System (RimWorld-style Autonomous Hauling, Work Priorities, Construction, Door Navigation & Entity Collision)
"""

import math
import random
import time
import pygame
from game.render_cache import ellipse_surface
from game.config import (
    TILE_SIZE,
    LOOSE_ITEM_ARRIVAL_DIST,
    INTERACTION_CONTACT_RADIUS,
    SERVANT_COUNT,
    SERVANT_RADIUS,
    SERVANT_SPEED,
    SERVANT_CARRY_CAPACITY,
    SERVANT_AI_DECISION_TICK_INTERVAL_SECONDS,
    DEFAULT_PRIORITIES,
    ENTITY_AVOIDANCE_RADIUS,
    SERVANT_YIELD_FORCE,
    MIN_ENTITY_SEPARATION,
    COLOR_SERVANT_OUTLINE,
    COLOR_SHADOW,
    RESOURCE_COLORS,
    DEDICATED_JOBS,
    PATH_WAYPOINT_TOLERANCE,
    NAVIGATION_RETRY_INTERVAL,
    NAVIGATION_BLOCKED_TILE_TIMEOUT,
    NAVIGATION_BLOCKED_PROBE_DISTANCE,
    STUCK_THRESHOLD_SECONDS,
    STUCK_AVOIDANCE_DURATION,
    EMERGENCY_STUCK_TIMEOUT,
    EMERGENCY_COLLISION_BYPASS_DURATION,
    PATH_WAIT_RECHECK_INTERVAL,
    is_food_item,
    is_water_item,
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
    DOORWAY_QUEUE_LATERAL_OFFSET,
    TILE_OCCUPANCY_TIMEOUT,
    TILE_STEP_RESERVATION_TIMEOUT,
    NARROW_PASSAGE_WAIT_DISTANCE,
    SERVANT_STUCK_TELEPORT_THRESHOLD,
    SERVANT_TELEPORT_SEARCH_RADIUS_TILES,
    SERVANT_MAX_TELEPORTS_PER_TARGET,
)
from game.data.config import MARKET_TRADEABLE_ITEMS, MARKET_CURRENCY_DENOMINATIONS
from game.systems.ai_simulation_scheduler import AISimulationScheduler
from game.systems.spatial_entities import SpatialEntityIndex
from game.world.pathfinding import GlobalPathRegistry, calculate_collision_slide, is_narrow_passage_tile
from game.world.navigation import find_navigation_path, interaction_arrival_distance, resolve_steer_index
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
        self.target_treasury_chest = None
        self.target_storage_tile = None

        # Royal Grant hauling targets
        self.target_grant_order = None
        self.target_grant_stack = None
        self.target_grant_pos = None
        self.target_grant_dest = None
        self.target_grant_fam_id = None
        self.target_grant_res = None
        self.target_grant_amount = 0
        self.target_grant_treasury = None

        # Market Restock hauling targets (Agent 2)
        self.target_restock_order = None
        self.target_restock_stack = None
        self.target_restock_market = None
        self.target_restock_pos = None
        self.target_restock_dest = None
        self.target_restock_res = None
        self.target_restock_amount = 0

        # Lord's Purchase Order targets: buy household stall goods with
        # Lord Treasury coins, haul to landlord storage, return change.
        self.target_buy_order = None
        self.target_buy_market = None
        self.target_buy_treasury = None
        self.target_buy_fetch_pos = None
        self.target_buy_market_pos = None
        self.target_buy_drop_pos = None
        self.target_buy_drop_tile = None
        self.target_buy_chunk = 0
        self.target_buy_total = 0
        self.buy_wallet = {}
        self.carpenter_commission_order_id = None
        self.carpenter_commission_carpenter_id = None
        self.carpenter_commission_fee_copper = 0
        self.carpenter_commission_remaining_copper = 0
        self.carpenter_commission_storage_tile = None
        self.carpenter_commission_treasury_id = None

        # Dead-artisan commission refund: recover coins from the deceased
        # artisan's household funds, return them to the Lord Treasury.
        self.carpenter_refund_from_family = None
        self.carpenter_refund_amount = 0

        # Carried items (Max 5 items)
        self.carried_res = None
        self.carried_amount = 0
        self.carrying_furniture = None

        # Needs & Survival Profile (Agent 1)
        self.hunger = 100.0
        self.thirst = 100.0
        self.is_alive = True
        self.status = "ALIVE"
        self.daily_food_consumed = 1
        self.daily_water_consumed = 1
        self.role = "Royal Servant"
        self.family_id = "Landlord Manor"

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
        self.path_retry_timer = 0.0
        self.path_seq = 0
        self.yield_timer = 0.0
        self.wait_timer = 0.0
        self.is_waiting_for_path = False
        self.stuck_timer = 0.0
        self.hard_stuck_timer = 0.0
        self.collision_bypass_timer = 0.0
        self.consecutive_stuck_recoveries = 0
        self.stuck_blocked_tiles = {}
        self.route_state = ROUTE_STATE_NONE
        self.route_request_timer = 0.0
        self.route_retry_count = 0

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

        if self.state in ("CARPENTER_COMMISSION_RETRIEVE", "CARPENTER_COMMISSION_DELIVER"):
            from game.systems.carpenter_system import CarpenterSystem
            from game.systems.cemetery_system import CemeterySystem
            from game.systems.currency import compact_currency_wallet, from_copper, to_copper
            order_subject = next((entity for entity in (
                list(getattr(furniture_manager, "furnitures", []))
                + list(getattr(building_manager, "buildings", []))
                + list(getattr(building_manager, "construction_sites", []))
            ) if str((getattr(entity, "construction_order", None) or {}).get("id"))
                 == str(self.carpenter_commission_order_id)), None)
            order = getattr(order_subject, "construction_order", None) if order_subject else None
            carpenter = next((worker for worker in (villager_manager.get_all_villagers() if villager_manager else [])
                              if str(getattr(worker, "id", "")) == str(self.carpenter_commission_carpenter_id)
                              and getattr(worker, "is_alive", True)), None)
            if not order or order.get("status") not in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING") or not carpenter:
                CarpenterSystem.refund_public_courier_coins(self, stockpile_manager, furniture_manager)
                if order and order.get("payer_type") == "landlord":
                    order["status"] = "AWAITING_PAYMENT"
                    order["payer_id"] = None
                self.carpenter_commission_order_id = None
                self.carpenter_commission_carpenter_id = None
                self.state = "IDLE"
                return

            if self.state == "CARPENTER_COMMISSION_RETRIEVE":
                from game.systems.lord_treasury import LordTreasurySystem
                treasury = LordTreasurySystem.get_chest(furniture_manager)
                if treasury and str(getattr(treasury, "id", "")) == str(
                        getattr(self, "carpenter_commission_treasury_id", treasury.id)):
                    approach_x, approach_y = treasury.get_approach_point(
                        self.x, self.y, worker_id=self.id, all_entities=all_entities,
                        tile_size=TILE_SIZE, bm=building_manager,
                    )
                    arrived = self._move_towards(
                        approach_x, approach_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                        all_servants=all_servants, player=player,
                        building_manager=building_manager, all_entities=all_entities,
                        furniture_manager=furniture_manager,
                        interaction_target=treasury,
                    )
                    if arrived:
                        fee = max(0, int(self.carpenter_commission_remaining_copper))
                        success, _ = LordTreasurySystem.withdraw_covering(
                            furniture_manager, self.inventory, fee
                        )
                        if success:
                            self.carpenter_commission_remaining_copper = 0
                            order["status"] = "PAYMENT_TRAVELING"
                            self.state = "CARPENTER_COMMISSION_DELIVER"
                            self.say("I have the commission coins; taking them to the Carpenter, my Lord.", duration=2.5)
                        else:
                            order["status"] = "LANDLORD_PAYMENT_PENDING"
                            self.say("The Lord's Treasury Chest no longer has enough coin, my Lord.", duration=3.0)
                    return

                stacks = CemeterySystem._landlord_coin_stacks(stockpile_manager)
                remaining = max(0, int(self.carpenter_commission_remaining_copper))
                if not stacks:
                    CarpenterSystem.refund_public_courier_coins(self, stockpile_manager, furniture_manager)
                    if order:
                        order["status"] = "AWAITING_PAYMENT"
                        order["payer_id"] = None
                    self.say("Landlord storage has no commission coins, my Lord.", duration=3.0)
                    self.carpenter_commission_order_id = None
                    self.carpenter_commission_carpenter_id = None
                    self.state = "IDLE"
                    return
                target_stack = min(stacks, key=lambda stack: math.hypot(
                    (stack.grid_x + 0.5) * TILE_SIZE - self.x,
                    (stack.grid_y + 0.5) * TILE_SIZE - self.y,
                ))
                target_x = (target_stack.grid_x + 0.5) * TILE_SIZE
                target_y = (target_stack.grid_y + 0.5) * TILE_SIZE
                arrived = self._move_towards(
                    target_x, target_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                    all_servants=all_servants, player=player,
                    building_manager=building_manager, all_entities=all_entities,
                    furniture_manager=furniture_manager,
                    interaction_target=target_stack,
                )
                if arrived:
                    denomination = CemeterySystem._landlord_coin_stacks(stockpile_manager)
                    if target_stack not in denomination:
                        return
                    from game.systems.currency import canonical_denomination
                    coin_type = canonical_denomination(target_stack.resource_type)
                    unit_value = to_copper({coin_type: 1})
                    available = max(0, int(getattr(target_stack, "available_amount", target_stack.amount)))
                    take = min(available, (remaining + unit_value - 1) // unit_value)
                    if take <= 0:
                        return
                    value_taken = take * unit_value
                    target_stack.amount -= take
                    target_tile = [target_stack.grid_x, target_stack.grid_y]
                    if value_taken >= remaining:
                        exact_fee = remaining
                        change = from_copper(value_taken - exact_fee)
                        for change_type, change_amount in change.items():
                            if change_amount:
                                stockpile_manager.drop_resource(change_type, change_amount, *target_tile, owner_type="landlord")
                        for coin, amount in from_copper(exact_fee).items():
                            if amount:
                                self.inventory[coin] = self.inventory.get(coin, 0) + amount
                        self.carpenter_commission_remaining_copper = 0
                    else:
                        for coin, amount in from_copper(value_taken).items():
                            if amount:
                                self.inventory[coin] = self.inventory.get(coin, 0) + amount
                        self.carpenter_commission_remaining_copper = remaining - value_taken
                    if target_stack.amount <= 0 and target_stack in stockpile_manager.stacks:
                        stockpile_manager.stacks.remove(target_stack)
                    stockpile_manager.mark_totals_dirty()
                    compact_currency_wallet(self.inventory)
                    if self.carpenter_commission_remaining_copper <= 0:
                        order["status"] = "PAYMENT_TRAVELING"
                        self.state = "CARPENTER_COMMISSION_DELIVER"
                        self.say("I have the commission coins; taking them to the Carpenter, my Lord.", duration=2.5)
                return

            arrived = self._move_towards(
                carpenter.x, carpenter.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_servants=all_servants, player=player, building_manager=building_manager,
                all_entities=all_entities, furniture_manager=furniture_manager,
                interaction_target=carpenter,
            )
            if arrived:
                fee = max(0, int(order.get("price_copper", 0)))
                if CarpenterSystem._move_exact_value(self.inventory, carpenter.inventory, fee):
                    order["status"] = "PAID"
                    order["commission_paid"] = True
                    order["paid_by_id"] = "landlord"
                    order["paid_amount_copper"] = fee
                    CarpenterSystem._ensure_paid_seq(order, furniture_manager, building_manager)
                    from game.systems.market_sales_report import MarketSalesReportSystem
                    MarketSalesReportSystem.record_household_income(
                        villager_manager, getattr(carpenter, "family_id", None),
                        "Public Carpenter Commissions", fee,
                        getattr(villager_manager, "current_day_number", 1),
                    )
                    carpenter.say(f"Public commission received: {fee} Copper.", duration=3.0)
                    self.say("Commission delivered to the Carpenter, my Lord.", duration=2.5)
                    CarpenterSystem.refund_public_courier_coins(self, stockpile_manager, furniture_manager)
                else:
                    CarpenterSystem.refund_public_courier_coins(self, stockpile_manager, furniture_manager)
                    order["status"] = "AWAITING_PAYMENT"
                    order["payer_id"] = None
                    self.say("The commission coins could not be transferred, my Lord.", duration=3.0)
                self.carpenter_commission_order_id = None
                self.carpenter_commission_carpenter_id = None
                self.carpenter_commission_fee_copper = 0
                self.carpenter_commission_remaining_copper = 0
                self.carpenter_commission_storage_tile = None
                self.carpenter_commission_treasury_id = None
                self.state = "IDLE"
            return

        if self.state in ("COMMISSION_REFUND_COLLECT", "COMMISSION_REFUND_DELIVER"):
            from game.systems.carpenter_system import CarpenterSystem
            from game.systems.lord_treasury import LordTreasurySystem
            from game.systems.currency import (
                compact_currency_wallet, normalize_wallet, to_copper,
            )

            if self.state == "COMMISSION_REFUND_COLLECT":
                amount = max(0, int(getattr(self, "carpenter_refund_amount", 0) or 0))
                if to_copper(normalize_wallet(self.inventory)) >= amount:
                    self.state = "COMMISSION_REFUND_DELIVER"
                    self.say("Coins recovered; returning them to the Treasury, my Lord.", duration=2.5)
                    return
                # 1) Deceased artisan's household chest.
                src_chest = (furniture_manager.get_storage_for_family(self.carpenter_refund_from_family)
                             if furniture_manager else None)
                if src_chest is not None and to_copper(normalize_wallet(src_chest.inventory)) > 0:
                    approach_x, approach_y = src_chest.get_approach_point(
                        self.x, self.y, worker_id=self.id, all_entities=all_entities,
                        tile_size=TILE_SIZE, bm=building_manager,
                    )
                    arrived = self._move_towards(
                        approach_x, approach_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                        all_servants=all_servants, player=player,
                        building_manager=building_manager, all_entities=all_entities,
                        furniture_manager=furniture_manager,
                        interaction_target=src_chest,
                    )
                    if arrived:
                        take = min(amount - to_copper(normalize_wallet(self.inventory)),
                                   to_copper(normalize_wallet(src_chest.inventory)))
                        CarpenterSystem._move_exact_value(src_chest.inventory, self.inventory, take)
                        compact_currency_wallet(self.inventory)
                    return
                # 2) Abstract household wallets, then 3) Treasury backstop.
                remaining = amount - to_copper(normalize_wallet(self.inventory))
                for wallet in CarpenterSystem._family_abstract_wallets(
                        self.carpenter_refund_from_family, villager_manager):
                    remaining = amount - to_copper(normalize_wallet(self.inventory))
                    if remaining <= 0:
                        break
                    take = min(remaining, to_copper(normalize_wallet(wallet)))
                    if take > 0:
                        CarpenterSystem._move_exact_value(wallet, self.inventory, take)
                remaining = amount - to_copper(normalize_wallet(self.inventory))
                if remaining > 0:
                    treasury_value = LordTreasurySystem.value(furniture_manager)
                    take = min(remaining, treasury_value)
                    if take > 0:
                        LordTreasurySystem.withdraw_covering(furniture_manager, self.inventory, take)
                self.state = "COMMISSION_REFUND_DELIVER"
                self.say("Coins recovered; returning them to the Treasury, my Lord.", duration=2.5)
                return

            # COMMISSION_REFUND_DELIVER: walk to the Treasury Chest and deposit.
            treasury = LordTreasurySystem.get_chest(furniture_manager)
            if not treasury:
                self.carpenter_refund_from_family = None
                self.carpenter_refund_amount = 0
                self.state = "IDLE"
                return
            approach_x, approach_y = treasury.get_approach_point(
                self.x, self.y, worker_id=self.id, all_entities=all_entities,
                tile_size=TILE_SIZE, bm=building_manager,
            )
            arrived = self._move_towards(
                approach_x, approach_y, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                all_servants=all_servants, player=player,
                building_manager=building_manager, all_entities=all_entities,
                furniture_manager=furniture_manager,
                interaction_target=treasury,
            )
            if arrived:
                LordTreasurySystem.deposit_all(furniture_manager, self.inventory)
                compact_currency_wallet(self.inventory)
                self.carpenter_refund_from_family = None
                self.carpenter_refund_amount = 0
                self.state = "IDLE"
                self.say("Refund returned to the Treasury, my Lord.", duration=2.5)
            return

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
                width, height = f.footprint_dimensions
                dest_x = (tgx + width / 2.0) * TILE_SIZE
                dest_y = (tgy + height / 2.0) * TILE_SIZE
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
                    site = self.target_site
                    other_reserved = site.reserved_cost.get(self.target_res, 0) - getattr(self, "target_site_reserved", 0)
                    needed_at_site = max(
                        0,
                        site.required_cost[self.target_res]
                        - site.delivered_cost[self.target_res]
                        - max(0, other_reserved),
                    )

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
                site = self.target_site
                if getattr(self, "target_site_reserved", 0) > 0:
                    site.release_resource(self.carried_res, self.target_site_reserved)
                    self.target_site_reserved = 0
                site.deposit_resource(self.carried_res, self.carried_amount)
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
                    order = getattr(self.target_site, "construction_order", None) or {}
                    if order.get("order_type") == "PUBLIC_BUILD":
                        self._reset_task()
                    elif self.work_priorities.get("Building", 0) > 0:
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
            order = getattr(self.target_site, "construction_order", None) or {}
            if order.get("order_type") == "PUBLIC_BUILD":
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
                treasury_chest = None
                from game.systems.currency import canonical_denomination, CURRENCY_DENOMINATIONS
                if canonical_denomination(res_type) in CURRENCY_DENOMINATIONS:
                    from game.systems.lord_treasury import LordTreasurySystem
                    treasury_chest = LordTreasurySystem.get_chest(furniture_manager)
                avail_dest = (
                    (treasury_chest.grid_x, treasury_chest.grid_y)
                    if treasury_chest else stockpile_manager.get_available_storage_tile(permit_manager, res_type)
                )

                if not avail_dest:
                    self.say("No storage lot available to haul to, Lord!")
                    self._reset_task()
                    return

                pick_amt = min(
                    SERVANT_CARRY_CAPACITY,
                    int(getattr(self.target_loose_stack, "available_amount", self.target_loose_stack.amount)),
                )
                actual = stockpile_manager.take_from_stack(self.target_loose_stack, pick_amt)
                if actual > 0:
                    self.carried_res = res_type
                    self.carried_amount = actual
                    self.target_storage_tile = avail_dest
                    self.target_treasury_chest = treasury_chest
                    self.state = "HAULING_LOOSE_DELIVER"
                    self.say("Hauling coins to the Lord's Treasury Chest..." if treasury_chest
                             else f"Hauling {self.carried_res} to storage...")
                else:
                    self._reset_task()

        elif self.state == "HAULING_LOOSE_DELIVER":
            # Coins go to the dedicated Lord Treasury Chest; other goods use storage permits.
            if not self.target_storage_tile:
                self._reset_task()
                return

            treasury_chest = self.target_treasury_chest
            if treasury_chest:
                tx, ty = treasury_chest.get_approach_point(
                    self.x, self.y, worker_id=self.id, all_entities=all_entities,
                    tile_size=TILE_SIZE, bm=building_manager,
                )
            else:
                tx = (self.target_storage_tile[0] + 0.5) * TILE_SIZE
                ty = (self.target_storage_tile[1] + 0.5) * TILE_SIZE

            if self._move_towards(tx, ty, dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, interaction_target=treasury_chest):
                if treasury_chest:
                    stored = treasury_chest.store_item(self.carried_res, self.carried_amount)
                    if stored < self.carried_amount:
                        stockpile_manager.drop_resource(
                            self.carried_res, self.carried_amount - stored,
                            self.target_storage_tile[0], self.target_storage_tile[1], owner_type="landlord",
                        )
                    from game.systems.lord_treasury import LordTreasurySystem
                    LordTreasurySystem._mark_wealth_dirty()
                    self.say(f"Stored {stored} {self.carried_res} in the Lord's Treasury Chest!")
                else:
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
                self.target_treasury_chest = None
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
            treasury_chest = getattr(self, "target_grant_treasury", None)
            grant_stack = self.target_grant_stack
            if treasury_chest is not None:
                if not getattr(treasury_chest, "inventory", None):
                    self._reset_task()
                    return
            elif not grant_stack or grant_stack not in stockpile_manager.stacks or grant_stack.amount <= 0:
                self._reset_task()
                return

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_grant_pos[0], self.target_grant_pos[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                if treasury_chest is not None:
                    from game.systems.currency import canonical_denomination
                    from game.systems.wealth_system import VillageWealthSystem
                    denom = canonical_denomination(self.target_grant_res) or self.target_grant_res
                    actual = treasury_chest.take_item(denom, self.target_grant_amount)
                    if actual > 0:
                        VillageWealthSystem.mark_dirty()
                else:
                    actual = stockpile_manager.take_from_stack(grant_stack, self.target_grant_amount)
                    if actual > 0:
                        stockpile_manager.refresh_stacks(resources, permit_manager)
                if actual > 0:
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

        elif self.state == "RESTOCK_FETCH":
            if not self.target_restock_stack or self.target_restock_stack not in stockpile_manager.stacks or self.target_restock_stack.amount <= 0:
                self._reset_task()
                return

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_restock_pos[0], self.target_restock_pos[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                actual = stockpile_manager.take_from_stack(self.target_restock_stack, self.target_restock_amount)
                if actual > 0:
                    stockpile_manager.refresh_stacks(resources, permit_manager)
                    self.carried_res = self.target_restock_res
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
                    self.state = "RESTOCK_DELIVER"
                    self.say(f"Hauling {actual} {self.carried_res} to Market...")
                else:
                    if self.target_restock_order:
                        self.target_restock_order["in_transit"] = max(0, self.target_restock_order.get("in_transit", 0) - self.target_restock_amount)
                    self._reset_task()

        elif self.state == "RESTOCK_DELIVER":
            if not self.target_restock_dest or not self.target_restock_market:
                self._reset_task()
                return

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils

            if self._move_towards(self.target_restock_dest[0], self.target_restock_dest[1], dt, arrival_dist=32, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                # Arrived at Market! Deposit physical items into market inventory
                mkt = self.target_restock_market
                if not hasattr(mkt, "inventory") or mkt.inventory is None:
                    mkt.inventory = {}

                if self.carried_res in MARKET_CURRENCY_DENOMINATIONS:
                    if not isinstance(getattr(mkt, "currency", None), dict):
                        mkt.currency = {denom: 0 for denom in MARKET_CURRENCY_DENOMINATIONS}
                    mkt.currency[self.carried_res] = mkt.currency.get(self.carried_res, 0) + self.carried_amount
                    from game.systems.currency import compact_currency_wallet
                    compact_currency_wallet(mkt.currency)
                else:
                    mkt.inventory[self.carried_res] = mkt.inventory.get(self.carried_res, 0) + self.carried_amount
                    from game.systems.market_pricing import MarketPricingSystem
                    MarketPricingSystem.update_market_prices(mkt)

                if self.target_restock_order:
                    self.target_restock_order["delivered"] = self.target_restock_order.get("delivered", 0) + self.carried_amount
                    self.target_restock_order["in_transit"] = max(0, self.target_restock_order.get("in_transit", 0) - self.carried_amount)
                    if self.target_restock_order["delivered"] >= self.target_restock_order["amount"]:
                        if servant_manager and self.target_restock_order in getattr(servant_manager, "restock_orders", []):
                            servant_manager.restock_orders.remove(self.target_restock_order)

                self.say(f"Delivered {self.carried_amount} {self.carried_res} to Market, Sire!", duration=2.5)
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

        # -------------------------------------------------------------
        # LORD'S PURCHASE ORDER: BUY -> MARKET -> LANDLORD STORAGE -> TREASURY CHANGE
        # -------------------------------------------------------------
        elif self.state == "BUY_FETCH":
            chest = self.target_buy_treasury
            if chest is None or not getattr(chest, "inventory", None):
                if self.target_buy_order:
                    self.target_buy_order["in_transit"] = max(0, self.target_buy_order.get("in_transit", 0) - self.target_buy_chunk)
                self._reset_task()
                return
            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_buy_fetch_pos[0], self.target_buy_fetch_pos[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                from game.systems.lord_treasury import LordTreasurySystem
                ok, _msg = LordTreasurySystem.withdraw_covering(
                    furniture_manager, self.buy_wallet, self.target_buy_total)
                if not ok:
                    if self.target_buy_order:
                        self.target_buy_order["in_transit"] = max(0, self.target_buy_order.get("in_transit", 0) - self.target_buy_chunk)
                    self._reset_task()
                    return
                self.state = "BUY_GO_MARKET"
                self.say("Collected coins for market purchase, Lord!", duration=2.0)

        elif self.state == "BUY_GO_MARKET":
            mkt = self.target_buy_market
            order = self.target_buy_order
            if mkt is None or order is None or not getattr(mkt, "inventory", None):
                self.state = "BUY_RETURN"
                return
            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_buy_market_pos[0], self.target_buy_market_pos[1], dt, arrival_dist=32, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                from game.systems.market_service import MarketService
                from game.systems.currency import (
                    calculate_payment_and_change, execute_currency_transfer,
                )
                item_name = order["item_name"]
                stock = max(0, int(mkt.inventory.get(item_name, 0)))
                qty = min(self.target_buy_chunk, stock)
                if qty <= 0:
                    # Stall sold out meanwhile -> refund coins at treasury.
                    self.state = "BUY_RETURN"
                    return
                price = MarketService.get_item_price(item_name, mkt)
                if price <= 0:
                    self.state = "BUY_RETURN"
                    return
                total = price * qty
                mkt_curr = getattr(mkt, "currency", None)
                if not isinstance(mkt_curr, dict):
                    mkt_curr = {"Copper": 0, "Silver": 0, "Gold": 0}
                    mkt.currency = mkt_curr
                ok, payment, change, _msg = calculate_payment_and_change(self.buy_wallet, total, mkt_curr)
                if not ok:
                    self.state = "BUY_RETURN"
                    return
                transfer_ok, _sw, _rw, _tmsg = execute_currency_transfer(
                    self.buy_wallet, mkt_curr, payment, change)
                if not transfer_ok:
                    self.state = "BUY_RETURN"
                    return
                mkt.inventory[item_name] -= qty
                if mkt.inventory[item_name] <= 0:
                    del mkt.inventory[item_name]
                from game.systems.market_pricing import MarketPricingSystem
                MarketPricingSystem.update_market_prices(mkt)
                from game.systems.market_sales_report import MarketSalesReportSystem
                MarketSalesReportSystem.record_sale(mkt, item_name, qty, price)

                order["fulfilled"] = order.get("fulfilled", 0) + qty
                order["in_transit"] = max(0, order.get("in_transit", 0) - self.target_buy_chunk)
                self.carried_res = item_name
                self.carried_amount = qty
                self.target_buy_chunk = qty
                self.state = "BUY_DELIVER"
                self.say(f"Purchased {qty}x {item_name} for the Lord!", duration=2.0)

        elif self.state == "BUY_DELIVER":
            if not self.target_buy_drop_pos or not self.target_buy_drop_tile:
                self.state = "BUY_RETURN"
                return
            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            if self._move_towards(self.target_buy_drop_pos[0], self.target_buy_drop_pos[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                gx, gy = self.target_buy_drop_tile
                stockpile_manager.drop_resource(
                    self.carried_res, self.carried_amount, gx, gy,
                    owner_type="landlord", owner_id=None)
                stockpile_manager.refresh_stacks(resources, permit_manager)
                self.say(f"Stored {self.carried_amount}x {self.carried_res} for the Lord!", duration=2.0)
                self.carried_res = None
                self.carried_amount = 0
                self.state = "BUY_RETURN"

        elif self.state == "BUY_RETURN":
            chest = self.target_buy_treasury
            if chest is None or not getattr(chest, "inventory", None):
                self._refund_buy_wallet_fallback(stockpile_manager, resources, permit_manager)
                self._finish_buy_order(servant_manager)
                return
            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            all_ents = list(all_servants or []) + all_vils
            dest = self.target_buy_fetch_pos
            if self._move_towards(dest[0], dest[1], dt, arrival_dist=24, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_ents, furniture_manager=furniture_manager, exclusive_target=False):
                from game.systems.lord_treasury import LordTreasurySystem
                LordTreasurySystem.deposit_all(furniture_manager, self.buy_wallet)
                self.buy_wallet = {}
                self._finish_buy_order(servant_manager)

    def _refund_buy_wallet_fallback(self, stockpile_manager, resources=None, permit_manager=None):
        """Treasury chest missing mid-order: drop carried coins as a
        landlord-owned stack at the servant's tile so value is never voided."""
        if not self.buy_wallet or stockpile_manager is None:
            self.buy_wallet = {}
            return
        gx = int(math.floor(self.x / TILE_SIZE))
        gy = int(math.floor(self.y / TILE_SIZE))
        for denom, amt in list(self.buy_wallet.items()):
            if amt > 0:
                stockpile_manager.drop_resource(
                    denom, int(amt), gx, gy, owner_type="landlord", owner_id=None)
        self.buy_wallet = {}
        stockpile_manager.refresh_stacks(resources, permit_manager)

    def _finish_buy_order(self, servant_manager):
        order = self.target_buy_order
        if order is not None and servant_manager is not None:
            if order.get("fulfilled", 0) >= order.get("quantity", 0):
                if order in getattr(servant_manager, "buy_orders", []):
                    servant_manager.buy_orders.remove(order)
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

    def _is_matching_grant_item(self, stack_res_type, requested_item):
        """Generic matching between landlord stockpile stack and requested grant item."""
        if not stack_res_type or not requested_item:
            return False
        if stack_res_type == requested_item:
            return True
        s_low = str(stack_res_type).strip().lower()
        r_low = str(requested_item).strip().lower()
        if s_low == r_low:
            return True
        try:
            from game.systems.household_inventory import canonical_item_name
            if canonical_item_name(stack_res_type) == canonical_item_name(requested_item):
                return True
        except ImportError:
            pass
        # FOOD category matching: generic Food stack can fulfill Potato, Bread, etc., or vice versa
        if is_food_item(stack_res_type) and is_food_item(requested_item):
            if s_low in ("food", "any_food") or r_low in ("food", "any_food"):
                return True
        return False

    def _evaluate_and_assign_priority_task(self, building_manager, permit_manager, stockpile_manager, resources, player, all_servants=None, furniture_manager=None, villager_manager=None, servant_manager=None):
        """RimWorld-style Priority Scan: 1 (Highest) down to 4 (Lowest)"""
        # Royal Decree: Hauling Granted Items from Landlord Storage to Villager Households
        if servant_manager and getattr(servant_manager, "grant_orders", None):
            for order in servant_manager.grant_orders:
                remaining = order["amount"] - order.get("in_transit", 0) - order.get("delivered", 0)
                if remaining > 0:
                    item_type = order["item_type"]
                    fam_id = order["family_id"]

                    # Determine family destination (shared by all sources).
                    # Orders may carry an explicit "dest_pos" override (e.g.
                    # immigration rewards paid to a homeless household standing
                    # at the Notice Board, which has no chest/permit yet).
                    dest_pos = order.get("dest_pos")
                    if not dest_pos and furniture_manager:
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

                    worker_idx = all_servants.index(self) if (all_servants and self in all_servants) else 0
                    offsets = [(0, -10), (0, 10), (-10, 0), (10, 0)]
                    ox, oy = offsets[worker_idx % len(offsets)]

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

                    # Source A: coin grants are fetched from the Lord Treasury Chest
                    from game.systems.currency import canonical_denomination
                    from game.systems.lord_treasury import LordTreasurySystem
                    denom = canonical_denomination(item_type)
                    if denom and furniture_manager is not None:
                        treasury_chest = LordTreasurySystem.get_chest(furniture_manager)
                        treasury_avail = LordTreasurySystem.wallet(furniture_manager).get(denom, 0) if treasury_chest else 0
                        amt_to_take = min(SERVANT_CARRY_CAPACITY, remaining, treasury_avail)
                        if amt_to_take > 0:
                            order["in_transit"] = order.get("in_transit", 0) + amt_to_take
                            self.target_grant_order = order
                            self.target_grant_stack = None
                            self.target_grant_treasury = treasury_chest
                            tx, ty = treasury_chest.get_world_pos(TILE_SIZE)
                            self.target_grant_pos = (tx + ox, ty + oy)
                            self.target_grant_dest = dest_pos
                            self.target_grant_fam_id = fam_id
                            self.target_grant_res = item_type
                            self.target_grant_amount = amt_to_take
                            self.state = "GRANT_FETCH"
                            fam_name = fam_id
                            if villager_manager:
                                fam_obj = villager_manager.get_family_by_id(fam_id)
                                if fam_obj is not None:
                                    fam_name = f"The {fam_obj.surname} Family"
                            self.say(f"Fetching {amt_to_take} {denom} from the treasury for {fam_name}, Lord!")
                            return True

                    # Source B: find stack in Landlord's stockpile with available capacity
                    storage_stack = None
                    # Pass 1: exact match
                    for s in stockpile_manager.stacks:
                        if getattr(s, "owner_type", "landlord") == "landlord" and getattr(s, "available_amount", s.amount) > 0:
                            if s.resource_type == item_type or str(s.resource_type).lower() == str(item_type).lower():
                                storage_stack = s
                                break
                    # Pass 2: canonical or generic category match (e.g. starter Food stack for Potato)
                    if not storage_stack:
                        for s in stockpile_manager.stacks:
                            if getattr(s, "owner_type", "landlord") == "landlord" and getattr(s, "available_amount", s.amount) > 0:
                                if self._is_matching_grant_item(s.resource_type, item_type):
                                    storage_stack = s
                                    break
                    if storage_stack:
                        amt_to_take = min(SERVANT_CARRY_CAPACITY, remaining, getattr(storage_stack, "available_amount", storage_stack.amount))
                        if amt_to_take <= 0:
                            continue
                        order["in_transit"] = order.get("in_transit", 0) + amt_to_take
                        if hasattr(storage_stack, "reserve"):
                            storage_stack.reserve(amt_to_take)

                        self.target_grant_order = order
                        self.target_grant_stack = storage_stack
                        self.target_grant_treasury = None
                        self.target_grant_pos = ((storage_stack.grid_x + 0.5) * TILE_SIZE + ox, (storage_stack.grid_y + 0.5) * TILE_SIZE + oy)
                        self.target_grant_dest = dest_pos
                        self.target_grant_fam_id = fam_id
                        self.target_grant_res = item_type
                        self.target_grant_amount = amt_to_take
                        self.state = "GRANT_FETCH"
                        self.say(f"Fetching {amt_to_take} {item_type} for The {fam_id} Family, Lord!")
                        return True

        # Royal Decree: Hauling Restock Items to Market (Agent 2)
        if servant_manager and getattr(servant_manager, "restock_orders", None):
            for order in servant_manager.restock_orders:
                remaining = order["amount"] - order.get("in_transit", 0) - order.get("delivered", 0)
                if remaining > 0:
                    item_type = order["item_type"]
                    target_res = "Food" if item_type in ("Potato", "potato") else item_type
                    # Find stack in Landlord's stockpile with available capacity
                    storage_stack = None
                    for s in stockpile_manager.stacks:
                        if getattr(s, "owner_type", "landlord") == "landlord" and getattr(s, "available_amount", s.amount) > 0:
                            if s.resource_type in (item_type, target_res) or self._is_matching_grant_item(s.resource_type, item_type):
                                storage_stack = s
                                break
                    if storage_stack:
                        mkt = order["market_building"]
                        dest_pos = mkt.get_world_pos(TILE_SIZE) if hasattr(mkt, "get_world_pos") else None
                        if not dest_pos and getattr(mkt, "tiles", None):
                            t_list = list(mkt.tiles)
                            avg_x = sum(t[0] for t in t_list) / len(t_list)
                            avg_y = sum(t[1] for t in t_list) / len(t_list)
                            dest_pos = ((avg_x + 0.5) * TILE_SIZE, (avg_y + 0.5) * TILE_SIZE)
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

                        self.target_restock_order = order
                        self.target_restock_stack = storage_stack
                        self.target_restock_pos = ((storage_stack.grid_x + 0.5) * TILE_SIZE + ox, (storage_stack.grid_y + 0.5) * TILE_SIZE + oy)
                        self.target_restock_dest = dest_pos
                        self.target_restock_market = mkt
                        self.target_restock_res = item_type
                        self.target_restock_amount = amt_to_take
                        self.state = "RESTOCK_FETCH"
                        self.say(f"Fetching {amt_to_take} {item_type} for Market restock, Sire!")
                        return True

        # Lord's Purchase Order: buy household stall goods into landlord storage.
        # Coins come from the Lord Treasury; the stall's selling price (set by
        # the household's auto-pricing/manual price) is paid into market.currency,
        # which the household later collects as earnings. Change returns to treasury.
        if servant_manager and getattr(servant_manager, "buy_orders", None) and furniture_manager:
            from game.systems.lord_treasury import LordTreasurySystem
            from game.systems.market_service import MarketService
            treasury_chest = LordTreasurySystem.get_chest(furniture_manager)
            if treasury_chest is not None:
                for order in list(servant_manager.buy_orders):
                    mkt = order.get("market")
                    if mkt is None or mkt not in getattr(building_manager, "buildings", []):
                        servant_manager.buy_orders.remove(order)
                        continue
                    remaining = order.get("quantity", 0) - order.get("fulfilled", 0) - order.get("in_transit", 0)
                    if remaining <= 0:
                        if order.get("fulfilled", 0) >= order.get("quantity", 0):
                            servant_manager.buy_orders.remove(order)
                        continue
                    item_name = order["item_name"]
                    stock = max(0, int(getattr(mkt, "inventory", {}).get(item_name, 0)))
                    chunk = min(SERVANT_CARRY_CAPACITY, remaining, stock)
                    if chunk <= 0:
                        continue
                    price = MarketService.get_item_price(item_name, mkt)
                    if price <= 0:
                        continue
                    total = price * chunk
                    if LordTreasurySystem.value(furniture_manager) < total:
                        continue  # treasury can't cover this trip yet

                    order["in_transit"] = order.get("in_transit", 0) + chunk

                    # Positions: treasury chest -> market approach -> drop tile in front of chest.
                    tx, ty = treasury_chest.get_world_pos(TILE_SIZE)
                    bw = max(1, int(getattr(treasury_chest, "footprint_dimensions", (1, 1))[0]))
                    bh = max(1, int(getattr(treasury_chest, "footprint_dimensions", (1, 1))[1]))
                    drop_gx = treasury_chest.grid_x + bw // 2
                    drop_gy = treasury_chest.grid_y + bh + 1
                    drop_pos = ((drop_gx + 0.5) * TILE_SIZE, (drop_gy + 0.5) * TILE_SIZE)
                    market_pos = mkt.get_approach_point(
                        self.x, self.y, self.id, tile_size=TILE_SIZE, bm=building_manager) \
                        if hasattr(mkt, "get_approach_point") else mkt.get_world_pos(TILE_SIZE)

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

                    self.target_buy_order = order
                    self.target_buy_market = mkt
                    self.target_buy_treasury = treasury_chest
                    self.target_buy_fetch_pos = (tx, ty)
                    self.target_buy_market_pos = market_pos
                    self.target_buy_drop_pos = drop_pos
                    self.target_buy_drop_tile = (drop_gx, drop_gy)
                    self.target_buy_chunk = chunk
                    self.target_buy_total = total
                    self.state = "BUY_FETCH"
                    self.say(f"Fetching coins to buy {chunk}x {item_name}, Lord!", duration=2.0)
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
                        order = getattr(pending_site, "construction_order", None) or {}
                        if order.get("order_type") != "PUBLIC_BUILD":
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
                # A0. Coin stacks stored inside storage permits are not "loose", so they
                # never reach the Lord's Treasury Chest unless we haul them explicitly.
                from game.systems.currency import CURRENCY_DENOMINATIONS, canonical_denomination
                from game.systems.lord_treasury import LordTreasurySystem
                treasury_chest = LordTreasurySystem.get_chest(furniture_manager)
                if treasury_chest:
                    for stack in stockpile_manager.stacks:
                        if (
                            getattr(stack, "owner_type", "landlord") != "landlord"
                            or canonical_denomination(getattr(stack, "resource_type", "")) not in CURRENCY_DENOMINATIONS
                            or int(getattr(stack, "available_amount", stack.amount)) <= 0
                            or not stockpile_manager.is_tile_in_storage(stack.grid_x, stack.grid_y, permit_manager)
                            or stack in claimed_loose_stacks
                        ):
                            continue
                        self.target_loose_stack = stack
                        self.target_treasury_chest = treasury_chest
                        self.state = "HAULING_LOOSE_FETCH"
                        self.say(f"Hauling {stack.resource_type} to the Lord's Treasury Chest!")
                        return True

                # A. Hauling loose items on ground into active storage
                if loose_stacks:
                    for stack in loose_stacks:
                        # Avoid duplicate targeting if another worker is already fetching this small stack
                        if stack in claimed_loose_stacks and stack.amount <= SERVANT_CARRY_CAPACITY:
                            continue

                        treasury_chest = None
                        if canonical_denomination(stack.resource_type) in CURRENCY_DENOMINATIONS:
                            from game.systems.lord_treasury import LordTreasurySystem
                            treasury_chest = LordTreasurySystem.get_chest(furniture_manager)
                        dest_tile = (
                            (treasury_chest.grid_x, treasury_chest.grid_y)
                            if treasury_chest else stockpile_manager.get_available_storage_tile(permit_manager, stack.resource_type)
                        )
                        if dest_tile:
                            self.target_loose_stack = stack
                            self.target_treasury_chest = treasury_chest
                            self.state = "HAULING_LOOSE_FETCH"
                            self.say(f"Hauling loose {stack.resource_type} to storage!")
                            return True

                # B. Construction supply is still eligible when loose goods exist.
                # Loose goods can remain un-haulable (for example, when storage is full),
                # and must not block workers from supplying an active construction site.
                if pending_site and not pending_site.is_materials_complete():
                    assigned = self._assign_construction_task(pending_site, stockpile_manager, resources, player, all_servants=all_servants)
                    if assigned:
                        return True

        return False

    def _assign_construction_task(self, site, stockpile_manager, resources, player, all_servants=None):
        self.target_site = site

        if site.is_materials_complete():
            order = getattr(site, "construction_order", None) or {}
            if order.get("order_type") == "PUBLIC_BUILD":
                return False
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
            self.target_site_reserved = reserved
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
        # *** ESTABLISHED — DO NOT REGRESS ***
        # Release the servant's OWN recorded reservation (target_site_reserved),
        # for both FETCHING and HAULING. Using a fixed SERVANT_CARRY_CAPACITY or
        # only handling FETCHING leaks reserved_cost -> blueprint never completes.
        if (self.target_site and self.target_res
                and self.state in ("FETCHING", "HAULING")
                and getattr(self, "target_site_reserved", 0) > 0):
            self.target_site.release_resource(self.target_res, self.target_site_reserved)
        self.target_site_reserved = 0
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

        # Refund restock order in_transit count (Agent 2)
        if self.target_restock_order:
            self.target_restock_order["in_transit"] = max(0, self.target_restock_order.get("in_transit", 0) - self.target_restock_amount)
        if self.target_restock_stack and hasattr(self.target_restock_stack, "release_reservation"):
            self.target_restock_stack.release_reservation(self.target_restock_amount)
        self.target_restock_order = None
        self.target_restock_stack = None
        self.target_restock_market = None
        self.target_restock_pos = None
        self.target_restock_dest = None
        self.target_restock_res = None
        self.target_restock_amount = 0

        # Refund buy order in_transit count. NOTE: self.buy_wallet is intentionally
        # NOT cleared here — coins already fetched from the treasury stay on the
        # servant and are deposited on the next BUY_RETURN (or reused), so fetched
        # value is never silently voided by an abort.
        if self.target_buy_order:
            self.target_buy_order["in_transit"] = max(0, self.target_buy_order.get("in_transit", 0) - self.target_buy_chunk)
        self.target_buy_order = None
        self.target_buy_market = None
        self.target_buy_treasury = None
        self.target_buy_fetch_pos = None
        self.target_buy_market_pos = None
        self.target_buy_drop_pos = None
        self.target_buy_drop_tile = None
        self.target_buy_chunk = 0
        self.target_buy_total = 0

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
        self.consecutive_stuck_recoveries = 0

        self.state = "IDLE"
        self.target_site = None
        self.target_demolition = None
        self.target_res = None
        self.target_storage_pos = None
        self.target_loose_stack = None
        self.target_treasury_chest = None
        self.target_storage_tile = None
        self.target_grant_order = None
        self.target_grant_stack = None
        self.target_grant_pos = None
        self.target_grant_dest = None
        self.target_grant_fam_id = None
        self.target_grant_res = None
        self.target_grant_amount = 0
        self.target_grant_treasury = None
        # Commission refund errand cleanup: any coins already collected stay
        # in self.inventory (same convention as commission/buy wallets —
        # physical coins the servant holds are never voided).
        self.carpenter_refund_from_family = None
        self.carpenter_refund_amount = 0
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
            self.idle_target = (tx, ty)

        # Bebaskan lorong sempit jika tanpa sengaja berada di lorong sempit saat idle
        cur_gx = int(math.floor(self.x / TILE_SIZE))
        cur_gy = int(math.floor(self.y / TILE_SIZE))
        if is_narrow_passage_tile((cur_gx, cur_gy), building_manager=building_manager):
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                cand_t = (cur_gx + dx, cur_gy + dy)
                if not is_narrow_passage_tile(cand_t, building_manager=building_manager):
                    cand_wx = (cand_t[0] + 0.5) * TILE_SIZE
                    cand_wy = (cand_t[1] + 0.5) * TILE_SIZE
                    self.idle_target = (cand_wx, cand_wy)
                    self._move_towards(cand_wx, cand_wy, dt, arrival_dist=16, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager)
                    break

        self.is_waiting_for_path = False
        self._move_towards(self.idle_target[0], self.idle_target[1], dt, arrival_dist=20, all_servants=all_servants, player=player, building_manager=building_manager, all_entities=all_entities, furniture_manager=furniture_manager, exclusive_target=False)

    def _move_towards(self, tx, ty, dt, arrival_dist=10, all_servants=None, player=None, building_manager=None, all_entities=None, furniture_manager=None, exclusive_target=False, interaction_target=None):
        if getattr(self, "player_avoid_speech_cooldown", 0.0) > 0.0:
            self.player_avoid_speech_cooldown = max(0.0, self.player_avoid_speech_cooldown - dt)
        self.path_retry_timer = max(0.0, getattr(self, "path_retry_timer", 0.0) - dt)
        if interaction_target is not None:
            arrival_dist = interaction_arrival_distance(
                interaction_target, tx, ty, arrival_dist, TILE_SIZE,
            )

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
            candidate_path = find_navigation_path(
                (self.x, self.y), (tx, ty), building_manager,
                furniture_manager=furniture_manager, tile_size=TILE_SIZE,
            )
            if candidate_path:
                self.current_path = candidate_path
                self.path_index = 0
                self.is_waiting_for_path = False
                self.route_state = ROUTE_STATE_ASSIGNED
            else:
                self.current_path = []
                self.path_index = 0
                self.path_retry_timer = NAVIGATION_RETRY_INTERVAL
                self.is_moving = False
                self.is_waiting_for_path = False
                self.route_state = ROUTE_STATE_FAILED
                return False

        if not self.current_path or self.path_index >= len(self.current_path):
            self.is_moving = False
            return False

        # 2. Waypoint stepping — steer to the furthest visible waypoint so
        # the actor cuts corners instead of retracing the stale polyline.
        steer_idx = resolve_steer_index(
            self, (self.x, self.y), self.current_path, self.path_index, dt,
            building_manager, furniture_manager=furniture_manager,
            tile_size=TILE_SIZE,
        )
        target_wp = self.current_path[steer_idx]
        wp_dx = target_wp[0] - self.x
        wp_dy = target_wp[1] - self.y
        dist_to_wp = math.hypot(wp_dx, wp_dy)
        is_last_wp = (steer_idx == len(self.current_path) - 1)
        tol = arrival_dist if is_last_wp else PATH_WAYPOINT_TOLERANCE

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
                self.path_index = steer_idx + 1
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

        terrain_mult = 1.0
        try:
            from game.world.natural_resources import get_natural_resources
            from game.world.roads import get_roads
            terrain_mult = (get_natural_resources().speed_factor_at(self.x, self.y, TILE_SIZE)
                            * get_roads().speed_factor_at(self.x, self.y, TILE_SIZE))
        except Exception:
            pass
        move_dist = min(self.speed * terrain_mult * dt, dist_to_wp)
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

        from game.world.island import is_land_world
        for _ in range(steps):
            step_ox, step_oy = self.x, self.y
            self.x += sub_vx
            self.y += sub_vy
            if not is_land_world(self.x, self.y, TILE_SIZE):
                self.x, self.y = step_ox, step_oy
                break
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
            # *** ESTABLISHED — DO NOT REGRESS ***
            # Servants share the villager stuck tolerance (2.0s). The old 0.5s
            # threshold made servants abandon tight 1-tile corridors that
            # villagers grind through — causing try/cancel/retry loops.
            # Combined with the anti-softlock teleport below, a servant must
            # never permanently fail to reach its destination: the Landlord
            # cannot act without servants.
            if self.stuck_timer >= 2.0:
                cur_gx = int(math.floor(self.x / TILE_SIZE))
                cur_gy = int(math.floor(self.y / TILE_SIZE))
                blocked_gx = int(math.floor((self.x + dir_x * NAVIGATION_BLOCKED_PROBE_DISTANCE) / TILE_SIZE))
                blocked_gy = int(math.floor((self.y + dir_y * NAVIGATION_BLOCKED_PROBE_DISTANCE) / TILE_SIZE))
                if not hasattr(self, "stuck_blocked_tiles") or not isinstance(self.stuck_blocked_tiles, dict):
                    self.stuck_blocked_tiles = {}
                self.stuck_blocked_tiles[(blocked_gx, blocked_gy)] = time.time() + NAVIGATION_BLOCKED_TILE_TIMEOUT
                self.stuck_timer = 0.0
                # ESTABLISHED ANTI-SOFTLOCK: the Landlord cannot act without
                # servants, so a servant that keeps failing to reach its target
                # must never soft-lock forever. After SERVANT_STUCK_TELEPORT_THRESHOLD
                # consecutive stuck recoveries it teleports to the nearest
                # walkable tile around its destination and repaths the last mile.
                self.consecutive_stuck_recoveries = getattr(self, "consecutive_stuck_recoveries", 0) + 1
                teleported = (
                    self.consecutive_stuck_recoveries >= SERVANT_STUCK_TELEPORT_THRESHOLD
                    and self.path_target is not None
                    and self._teleport_near_target(building_manager, furniture_manager)
                )
                if teleported:
                    self.say("Pardon the abrupt movement, my Lord!", duration=2.0)
                elif (self.consecutive_stuck_recoveries >= SERVANT_STUCK_TELEPORT_THRESHOLD
                      and self.path_target is not None
                      and getattr(self, "task_teleport_count", 0) >= SERVANT_MAX_TELEPORTS_PER_TARGET):
                    # *** ESTABLISHED — DO NOT REGRESS ***
                    # Destination unreachable after repeated teleports: abandon
                    # the task. Removing this re-enables infinite A->B->A bounce
                    # loops on unreachable targets (user-reported bug).
                    self._reset_task()
                    return False
                self.current_path = []
                self.path_index = 0
                if not teleported:
                    self.path_target = None
        else:
            self.stuck_timer = max(0.0, self.stuck_timer - dt * 2.0)
            self.consecutive_stuck_recoveries = 0

        if vx != 0 or vy != 0:
            self.facing_angle = math.atan2(vy, vx)
            self.walk_cycle += dt * 10.0

        return False

    def _teleport_near_target(self, building_manager, furniture_manager):
        """Anti-softlock teleport: relocate to the nearest walkable tile around the current path target."""
        if self.path_target is None:
            return False
        tx, ty = self.path_target
        tgt_gx = int(math.floor(tx / TILE_SIZE))
        tgt_gy = int(math.floor(ty / TILE_SIZE))
        radius = max(1, int(SERVANT_TELEPORT_SEARCH_RADIUS_TILES))
        best = None
        best_dist = float("inf")
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                gx, gy = tgt_gx + dx, tgt_gy + dy
                wx = (gx + 0.5) * TILE_SIZE
                wy = (gy + 0.5) * TILE_SIZE
                d = math.hypot(wx - tx, wy - ty)
                if d >= best_dist:
                    continue
                if not self._is_tile_walkable_for_teleport(gx, gy, building_manager, furniture_manager):
                    continue
                best = (wx, wy)
                best_dist = d
        if best is None:
            return False
        tgt_key = (tgt_gx, tgt_gy)
        if getattr(self, "_teleport_target_key", None) != tgt_key:
            self._teleport_target_key = tgt_key
            self.task_teleport_count = 0
        self.task_teleport_count = getattr(self, "task_teleport_count", 0) + 1
        if self.task_teleport_count > SERVANT_MAX_TELEPORTS_PER_TARGET:
            return False
        self.x, self.y = best
        self.current_path = []
        self.path_index = 0
        self.path_target = None
        self.stuck_timer = 0.0
        self.consecutive_stuck_recoveries = 0
        return True

    @staticmethod
    def _is_tile_walkable_for_teleport(gx, gy, building_manager, furniture_manager):
        """Walkable = land, not a solid/doorless building tile, not furniture-occupied."""
        from game.world.island import is_land_tile
        if not is_land_tile(gx, gy):
            return False
        if building_manager:
            b = building_manager.get_building_at(gx, gy)
            if b and (getattr(b, "is_solid", False)
                      or getattr(b, "building_type", "") == "well"
                      or not getattr(b, "door_pos", None)):
                return False
        if furniture_manager and hasattr(furniture_manager, "get_occupied_tiles"):
            if (gx, gy) in furniture_manager.get_occupied_tiles():
                return False
        # Reject tiles with no traversable exit — e.g. courtyards fully enclosed
        # by concave building shapes (U/L footprints). Teleporting there traps
        # the servant: every neighbour is a walled building tile.
        # *** ESTABLISHED — DO NOT REGRESS *** removing this check re-enables
        # infinite teleport loops inside concave buildings.
        if building_manager:
            pf = getattr(building_manager, "pathfinder", None)
            if pf is not None:
                escapes = False
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    try:
                        if pf.can_traverse_edge(gx, gy, gx + ddx, gy + ddy,
                                                building_manager, furniture_manager):
                            escapes = True
                            break
                    except Exception:
                        escapes = True
                        break
                if not escapes:
                    return False
        return True

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

    def activity_progress(self):
        """0..1 completion of the current timed activity, or None when not working."""
        if getattr(self, "is_moving", False):
            return None
        state = getattr(self, "state", "")
        if state == "BUILDING" and getattr(self, "target_site", None) is not None:
            return self.target_site.progress_fraction()
        if state == "DEMOLISHING" and getattr(self, "target_demolition", None) is not None:
            return self.target_demolition.progress_fraction()
        return None

    def draw(self, surface, camera, font_bubble, render_position=None):
        render_x, render_y = render_position or (self.x, self.y)
        sx, sy = camera.world_to_screen(render_x, render_y)
        r = max(4, int(self.radius * camera.zoom))
        bob = math.sin(self.walk_cycle) * (2.5 * camera.zoom) if self.is_moving else 0.0
        char_y = sy + int(bob)

        # 1. Bayangan di tanah
        shadow_w = int(r * 1.8)
        shadow_h = max(2, int(r * 0.9))
        shadow_surf = ellipse_surface(shadow_w, shadow_h, COLOR_SHADOW)
        surface.blit(shadow_surf, (sx - shadow_w // 2, sy + int(r * 0.4)))

        # 2. Badan AI Servant (Lingkaran Amber)
        job_colors = DEDICATED_JOBS.get(self.job, DEDICATED_JOBS["Unassigned"])
        body_color = job_colors.get("color", DEDICATED_JOBS["Unassigned"]["color"])
        pygame.draw.circle(surface, body_color, (sx, char_y), r)
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

        # 4.6. Animasi Membangun (Building Hammer Tool)
        elif getattr(self, "state", "") == "BUILDING" and not getattr(self, "is_moving", False):
            hx = sx + int(math.cos(self.facing_angle + 0.45) * (r * 0.85))
            hy = char_y + int(math.sin(self.facing_angle + 0.45) * (r * 0.85))
            shaft_len = int(14 * camera.zoom)
            strike_swing = math.sin(time.time() * 8.0) * 0.6
            h_angle = self.facing_angle + strike_swing
            end_x = hx + int(math.cos(h_angle) * shaft_len)
            end_y = hy + int(math.sin(h_angle) * shaft_len)
            pygame.draw.line(surface, (180, 120, 70), (hx, hy), (end_x, end_y), max(2, int(3 * camera.zoom)))
            head_w = max(4, int(8 * camera.zoom))
            head_h = max(3, int(5 * camera.zoom))
            pygame.draw.rect(surface, (148, 163, 184), (end_x - head_w // 2, end_y - head_h // 2, head_w, head_h))
            if strike_swing < -0.3:
                pygame.draw.circle(surface, (253, 224, 71), (end_x, end_y), max(1, int(2 * camera.zoom)))

        # 4.9. Activity progress bar (timed work indicator above the head)
        prog = self.activity_progress()
        if prog is not None:
            bar_w = max(18, int(30 * camera.zoom))
            bar_h = max(3, int(4 * camera.zoom))
            carry_offset = int(14 * camera.zoom) if (self.carried_res and self.carried_amount > 0) else 0
            bar_x = sx - bar_w // 2
            bar_y = char_y - r - bar_h - 4 - carry_offset
            pygame.draw.rect(surface, (15, 23, 42, 200), (bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2), border_radius=2)
            fill_w = int(bar_w * prog)
            if fill_w > 0:
                pygame.draw.rect(surface, (34, 197, 94), (bar_x, bar_y, fill_w, bar_h), border_radius=2)

        # 5. Speech Bubble (Pesan kepada Landlord)
        if self.speech_text and font_bubble:
            cache_key = (id(font_bubble), self.speech_text)
            if getattr(self, "_speech_cache_key", None) != cache_key:
                self._speech_cache_key = cache_key
                self._speech_cache_surface = font_bubble.render(self.speech_text, True, (15, 23, 42))
            txt_surf = self._speech_cache_surface
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
        self.restock_orders = []
        self.buy_orders = []
        self.font_bubble = None
        self.ai_updates_since_profile = 0

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

    def add_restock_order(self, market_building, item_type, amount, stockpile_manager=None, resources=None):
        """Mendaftarkan tugas restock fisik barang dari storage Landlord ke pasar oleh Servant (Agent 2)"""
        if amount <= 0 or not market_building or (item_type not in MARKET_TRADEABLE_ITEMS and item_type not in MARKET_CURRENCY_DENOMINATIONS):
            return None
        if item_type in MARKET_TRADEABLE_ITEMS and item_type not in getattr(market_building, "sale_items", []):
            return None

        # Cek ketersediaan di Landlord storage
        target_res = "Food" if item_type in ("Potato", "potato") else item_type
        avail_stock = 0
        if stockpile_manager:
            for s in getattr(stockpile_manager, "stacks", []):
                if s.owner_type == "landlord" and s.resource_type in (item_type, target_res):
                    avail_stock += getattr(s, "available_amount", s.amount)
        elif resources:
            avail_stock = resources.get(target_res, resources.get(item_type, 0))

        if avail_stock <= 0:
            return None

        order_amt = min(amount, avail_stock)
        order = {
            "id": f"restock_{int(time.time()*1000)}_{len(self.restock_orders)}",
            "market_building": market_building,
            "item_type": item_type,
            "amount": order_amt,
            "in_transit": 0,
            "delivered": 0
        }
        self.restock_orders.append(order)
        return order

    def add_buy_order(self, market_building, item_name, quantity):
        """Registers a Lord purchase order: a servant fetches coins from the
        Lord Treasury, buys `quantity` of `item_name` at the market stall,
        hauls it to landlord storage, and returns the change to the treasury.
        Only valid for stalls assigned to a household (the household earns
        the coins sitting in market.currency)."""
        if not market_building or quantity <= 0:
            return None
        if not getattr(market_building, "assigned_family_id", None):
            return None
        if not hasattr(market_building, "inventory") or not isinstance(market_building.inventory, dict):
            return None
        stock = max(0, int(market_building.inventory.get(item_name, 0)))
        if stock <= 0:
            return None
        order = {
            "id": f"buy_{int(time.time()*1000)}_{len(self.buy_orders)}",
            "market": market_building,
            "item_name": item_name,
            "quantity": int(quantity),
            "fulfilled": 0,
            "in_transit": 0,
        }
        self.buy_orders.append(order)
        return order

    def get_in_transit_for_market(self, market_building, item_type=None):
        """Mengembalikan total jumlah barang yang sedang dalam proses pengiriman oleh Servant ke pasar"""
        total = 0
        for o in self.restock_orders:
            if o.get("market_building") == market_building:
                if item_type is None or o.get("item_type") == item_type:
                    total += (o.get("amount", 0) - o.get("delivered", 0))
        return total

    def _ensure_font(self):
        if self.font_bubble is None:
            self.font_bubble = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def update(self, dt, building_manager, permit_manager, stockpile_manager, resources, player, furniture_manager=None, villager_manager=None, run_ai_scheduler=True, ai_dt=None, day_cycle=None):
        all_vils = villager_manager.get_all_villagers() if villager_manager else []

        if run_ai_scheduler:
            from game.systems.carpenter_system import CarpenterSystem
            CarpenterSystem.dispatch_pending_public_commissions(
                building_manager, self, villager_manager, furniture_manager,
                day_cycle=day_cycle, stockpile_manager=stockpile_manager,
            )
            all_entities = SpatialEntityIndex(
                list(self.servants) + list(all_vils), TILE_SIZE
            )

            def update_servant(servant, actor_dt):
                servant.update(
                    actor_dt, building_manager, permit_manager, stockpile_manager,
                    resources, player, self.servants,
                    furniture_manager=furniture_manager, villager_manager=villager_manager,
                    servant_manager=self, all_entities=all_entities,
                )
                all_entities.update(servant)

            self.last_ai_update_count = AISimulationScheduler.update_actors(
                self.servants, dt if ai_dt is None else ai_dt,
                SERVANT_AI_DECISION_TICK_INTERVAL_SECONDS, update_servant,
                active_interval=SERVANT_AI_DECISION_TICK_INTERVAL_SECONDS,
            )
            self.ai_updates_since_profile += self.last_ai_update_count

        # AI entities pass freely through each other.
        # AI must never pass through the Landlord/player.
        old_serv_pos = [(s.x, s.y) for s in self.servants]

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
            render_position = AISimulationScheduler.render_position(
                s, AISimulationScheduler.render_alpha(
                    s, SERVANT_AI_DECISION_TICK_INTERVAL_SECONDS
                )
            )
            render_x, render_y = render_position
            radius = max(0, float(getattr(s, "radius", 0)))
            if not camera.is_world_rect_visible(render_x - radius, render_y - radius, radius * 2, radius * 2):
                continue
            s.draw(surface, camera, self.font_bubble, render_position=render_position)
