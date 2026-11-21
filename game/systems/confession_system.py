"""Faith-driven church confession queue using existing permits, furniture, currency and navigation."""

import random

from game.config import (
    TILE_SIZE,
    AI_NEED_FAITH_CONFESSION_THRESHOLD,
    AI_NEED_FAITH_CONFESSION_RESTORE_MIN,
    AI_NEED_FAITH_CONFESSION_RESTORE_MAX,
    AI_NEED_FAITH_PRAYER_RESTORE_MIN,
    AI_NEED_FAITH_PRAYER_RESTORE_MAX,
    CONFESSION_DURATION_SECONDS,
    CONFESSION_BUBBLE_DURATION_SECONDS,
)
from game.data.config import (
    DEFAULT_ITEM_PRICES,
    FREE_TIME_SCHEDULE_ACTIVITIES,
    MARKET_TRADEABLE_ITEMS,
    is_food_item,
)
from game.systems.church_system import ChurchSystem
from game.systems.currency import (
    normalize_wallet,
    to_copper,
)
from game.config import INTERACTION_CONTACT_RADIUS
from game.world.navigation import distance_to_object
from game.systems.market_service import MarketService


class ConfessionSystem:
    """Coordinates FIFO confession requests per church and protects against duplicate charges."""

    _instance = None

    def __init__(self):
        self.queues = {}
        self.active = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def to_dict(self):
        return {
            "queues": {key: [dict(request) for request in requests]
                       for key, requests in self.queues.items()},
            "active": {key: dict(request) for key, request in self.active.items()},
        }

    def load_dict(self, data):
        data = data if isinstance(data, dict) else {}
        self.queues = {
            str(key): [dict(request) for request in requests if isinstance(request, dict)]
            for key, requests in data.get("queues", {}).items()
            if isinstance(requests, list)
        }
        self.active = {
            str(key): dict(request) for key, request in data.get("active", {}).items()
            if isinstance(request, dict)
        }

    @staticmethod
    def _confession_duration():
        return max(0.0, float(CONFESSION_DURATION_SECONDS))

    @classmethod
    def _prepare_payment(cls, villager, request, dt, building_manager,
                         furniture_manager, all_entities, player):
        """Retrieve up to one day's cheapest-food cost before traveling to the Priest."""
        from game.systems.carpenter_system import CarpenterSystem

        due = max(0, int(request.get("fee_due", 0)))
        personal_wallet = normalize_wallet(getattr(villager, "inventory", {}))
        personal_value = to_copper(personal_wallet)
        remaining = max(0, due - personal_value)
        if remaining <= 0:
            request["fee_offer"] = due
            request["payment_ready"] = True
            request["state"] = "READY"
            return True

        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if not chest:
            request["fee_offer"] = min(due, personal_value)
            request["payment_ready"] = True
            request["state"] = "READY"
            return True

        source = getattr(chest, "inventory", {})
        source_name = "inventory"
        if to_copper(normalize_wallet(source)) <= 0:
            source = getattr(chest, "currency", {})
            source_name = "currency"
        chest_value = to_copper(normalize_wallet(source))
        if chest_value <= 0:
            request["fee_offer"] = min(due, personal_value)
            request["payment_ready"] = True
            request["state"] = "READY"
            return True

        if not request.get("at_payment_storage"):
            pos = chest.get_approach_point(
                villager.x, villager.y, worker_id=villager.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
            arrived = villager._move_towards(
                pos[0], pos[1], dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                interaction_target=chest,
            )
            villager.task = "CONFESSION_RETRIEVE_COINS"
            villager.confession_task = "RETRIEVING_PAYMENT"
            if not arrived:
                return False

        request["at_payment_storage"] = True
        withdraw = min(remaining, chest_value)
        if withdraw > 0:
            if not CarpenterSystem._move_exact_value(source, villager.inventory, withdraw):
                return False
            request["payment_chest_id"] = getattr(chest, "id", None)
            request["payment_family_id"] = getattr(villager, "family_id", None)
            request["payment_source"] = source_name
            request["withdrawn_amount"] = (
                max(0, int(request.get("withdrawn_amount", 0))) + withdraw
            )
            from game.systems.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        request["fee_offer"] = min(due, to_copper(normalize_wallet(villager.inventory)))
        request["payment_ready"] = True
        request["state"] = "READY"
        return True

    @classmethod
    def _church_priests(cls, permit_manager, villager_manager):
        villagers = villager_manager.get_all_villagers() if villager_manager else []
        priests = []
        for church in ChurchSystem.get_all_church_permits(permit_manager):
            assigned_ids = {str(worker_id) for worker_id in getattr(church, "assigned_workers", [])}
            priest = next((villager for villager in villagers
                           if getattr(villager, "is_alive", True)
                           and getattr(villager, "job", "") == "Priest"
                           and str(villager.id) in assigned_ids), None)
            if priest:
                priests.append((church, priest))
        return priests

    @classmethod
    def _find_service(cls, villager, permit_manager, villager_manager, building_manager, furniture_manager):
        options = []
        for church, priest in cls._church_priests(permit_manager, villager_manager):
            boxes = [furniture for furniture in getattr(furniture_manager, "furnitures", [])
                     if getattr(furniture, "furniture_type", "") == "confession_box"
                     and getattr(furniture, "permit_id", None) == church.id
                     and getattr(furniture, "is_available_for_use", False)]
            if not boxes:
                continue
            box = min(boxes, key=lambda item: math_distance(
                villager.x, villager.y, *item.get_world_pos(TILE_SIZE)
            ))
            bx, by = box.get_world_pos(TILE_SIZE)
            options.append((math_distance(villager.x, villager.y, bx, by), church, priest, box))
        return min(options, key=lambda item: item[0])[1:] if options else None

    @classmethod
    def _request(cls, villager, service, building_manager=None):
        inst = cls.get_instance()
        church, priest, box = service
        church_key = str(church.id)
        if any(str(req.get("villager_id")) == str(villager.id)
               for req in inst.queues.get(church_key, [])):
            return
        active = inst.active.get(church_key)
        if active and str(active.get("villager_id")) == str(villager.id):
            return
        inst.queues.setdefault(church_key, []).append({
            "villager_id": villager.id,
            "church_id": church.id,
            "priest_id": priest.id,
            "box_id": box.id,
            "wait_seconds": 0.0,
            "paid": False,
            "payment_ready": str(villager.id) == str(priest.id),
            "fee_due": 0 if str(villager.id) == str(priest.id) else cls._daily_livelihood_cost(building_manager),
            "fee_offer": 0,
            "elapsed": 0.0,
            "self_confession": str(villager.id) == str(priest.id),
            "state": "READY" if str(villager.id) == str(priest.id) else "RETRIEVING_PAYMENT",
        })
        villager.confession_church_id = church.id
        villager.confession_task = "QUEUED"
        villager.task = "CONFESSION_QUEUED"
        villager.say("I should seek confession.", duration=2.5)

    @classmethod
    def _activate_next_request(cls, church_key, queue):
        inst = cls.get_instance()
        if inst.active.get(church_key) or not queue:
            return inst.active.get(church_key)
        request = queue[0]
        if not request.get("self_confession") and not request.get("payment_ready"):
            return None
        queue.pop(0)
        request["state"] = (
            "PRIEST_TO_VISITOR" if request.get("self_confession")
            else "VISITOR_TO_PRIEST"
        )
        request["wait_seconds"] = 0.0
        inst.active[church_key] = request
        return request

    @classmethod
    def update_villager(cls, villager, dt, sched_activity, day_cycle, permit_manager,
                        villager_manager, building_manager, furniture_manager,
                        all_entities, player, schedule_manager=None):
        if not villager or not getattr(villager, "is_alive", True):
            return False
        inst = cls.get_instance()
        faith = float(getattr(villager, "faith", 100.0))
        has_request = cls._request_for_villager(villager.id) is not None
        current_schedule = (
            schedule_manager.get_current_activity(
                villager.job, getattr(day_cycle, "current_hour", 0.0)
            )
            if schedule_manager else sched_activity
        )
        if (not has_request and faith <= AI_NEED_FAITH_CONFESSION_THRESHOLD
                and current_schedule in FREE_TIME_SCHEDULE_ACTIVITIES):
            service = cls._find_service(villager, permit_manager, villager_manager,
                                        building_manager, furniture_manager)
            if service:
                cls._request(villager, service, building_manager)
                has_request = True
        if not has_request:
            return False

        request = cls._request_for_villager(villager.id)
        if not request:
            villager.confession_task = None
            return False
        if "fee_due" not in request:
            request["fee_due"] = (0 if request.get("self_confession") else
                                  cls._daily_livelihood_cost(building_manager))
        if request.get("state") == "WAITING_FOR_VISITOR":
            request["state"] = "VISITOR_TO_PRIEST"
            request["payment_ready"] = True
        church_key = str(request["church_id"])
        church = next((p for p in ChurchSystem.get_all_church_permits(permit_manager)
                       if str(p.id) == church_key), None)
        box = furniture_manager.get_furniture_by_id(request["box_id"]) if furniture_manager else None
        if not church or not box or not box.is_available_for_use:
            cls._cancel_request(
                request, villager_manager,
                "Confession unavailable; I will return later.",
                furniture_manager,
            )
            return False
        if not request.get("self_confession"):
            priest = cls._find_priest(request, villager_manager)
            if (not priest or not getattr(priest, "is_alive", True)
                    or getattr(priest, "job", "") != "Priest"):
                cls._cancel_request(request, villager_manager,
                                    "The Priest is unavailable; I will return later.",
                                    furniture_manager)
                return False
        if cls._free_time_ended(
                request, villager_manager, day_cycle, schedule_manager):
            cls._cancel_request(
                request, villager_manager,
                "My free time is over; I will return later.",
                furniture_manager,
            )
            return False

        queue = inst.queues.get(church_key, [])
        active = inst.active.get(church_key)
        is_active_visitor = (
            active and str(active.get("villager_id")) == str(villager.id)
        )
        # Allow ALL queued villagers to prepare payment in parallel while waiting
        can_prepare_payment = is_active_visitor or (request in queue)
        if (not request.get("self_confession") and not request.get("payment_ready")
                and can_prepare_payment):
            cls._prepare_payment(
                villager, request, dt, building_manager, furniture_manager,
                all_entities, player,
            )
            if not request.get("payment_ready"):
                return True
        if not active:
            active = cls._activate_next_request(church_key, queue)
        if active and str(active.get("villager_id")) == str(villager.id):
            if not request.get("self_confession"):
                return True
            if active.get("state") == "IN_PROGRESS":
                active["elapsed"] += max(0.0, dt)
                villager.task = "CONFESSING"
                villager.confession_task = "IN_PROGRESS"
                villager.is_moving = False
                if active["elapsed"] >= cls._confession_duration():
                    villager.faith = random.uniform(AI_NEED_FAITH_CONFESSION_RESTORE_MIN,
                                                    AI_NEED_FAITH_CONFESSION_RESTORE_MAX)
                    villager.last_confession_day = getattr(day_cycle, "day_number", 1)
                    from game.systems.happiness_system import HappinessSystem
                    HappinessSystem.record_event(
                        villager, "confession_completed",
                        getattr(day_cycle, "day_number", 1),
                    )
                    villager.say("I feel at peace again.", duration=2.5)
                    cls._finish_request(church_key, villager, villager, success=True)
                return True
            active["wait_seconds"] += max(0.0, dt)
            cls._move_to_box(villager, box, dt, all_entities, player,
                             building_manager, furniture_manager, side=0)
            if cls._at_approach(villager, box, building_manager, furniture_manager, side=0):
                active["state"] = "IN_PROGRESS"
                active["elapsed"] = 0.0
                villager.task = "CONFESSING"
                villager.confession_task = "IN_PROGRESS"
                villager.say("I seek quiet reflection and confession.", duration=CONFESSION_BUBBLE_DURATION_SECONDS)
            return True

        if request in queue:
            index = queue.index(request)
            request["wait_seconds"] += max(0.0, dt)
            tiles = ChurchSystem.get_church_walkable_tiles(church, building_manager)
            position = cls._queue_position(index, tiles, furniture_manager, box)
            if position:
                world_position = ((position[0] + 0.5) * TILE_SIZE,
                                  (position[1] + 0.5) * TILE_SIZE)
                cls._move_to_point(villager, world_position, dt, all_entities, player,
                                   building_manager, furniture_manager)
            villager.task = "WAITING_FOR_CONFESSION" if index else "CONFESSION_QUEUED"
            villager.confession_task = "QUEUED"
            return True
        return False

    @classmethod
    def update_priest(cls, priest, dt, day_cycle, schedule_manager, permit_manager,
                      villager_manager, building_manager, furniture_manager,
                      all_entities, player):
        inst = cls.get_instance()
        church = next((p for p in ChurchSystem.get_all_church_permits(permit_manager)
                       if str(priest.id) in {str(worker_id) for worker_id in getattr(p, "assigned_workers", [])}), None)
        if not church:
            return False
        church_key = str(church.id)
        queue = inst.queues.setdefault(church_key, [])
        if (schedule_manager and schedule_manager.get_current_activity(
                priest.job, getattr(day_cycle, "current_hour", 0.0),
        ) not in FREE_TIME_SCHEDULE_ACTIVITIES):
            request = inst.active.get(church_key)
            if request:
                cls._cancel_request(
                    request, villager_manager,
                    "The Priest's free time is over; I will return later.",
                    furniture_manager,
                )
            priest.confession_task = None
            return False
        request = inst.active.get(church_key)
        if request is None:
            request = cls._activate_next_request(church_key, queue)
            if request is None and queue:
                priest.task = "WAITING_FOR_CONFESSION"
                priest.confession_task = "WAITING_FOR_PAYMENT"
                return True
        if request is None:
            priest.confession_task = None
            return False
        if request.get("self_confession"):
            return False
        visitor = cls._find_priest(request, villager_manager, priest_role=False)
        box = furniture_manager.get_furniture_by_id(request.get("box_id")) if furniture_manager else None
        if not visitor or not getattr(visitor, "is_alive", True) or not box or not box.is_available_for_use:
            cls._cancel_request(
                request, villager_manager,
                "Confession could not be completed; I will return later.",
                furniture_manager,
            )
            return False
        if request.get("state") != "IN_PROGRESS":
            request["wait_seconds"] = request.get("wait_seconds", 0.0) + max(0.0, dt)
        if cls._free_time_ended(
                request, villager_manager, day_cycle, schedule_manager):
            cls._cancel_request(
                request, villager_manager,
                "My free time is over; I will return later.",
                furniture_manager,
            )
            return False
        interrupted_state = getattr(visitor, "interrupted_task_state", None)
        if (interrupted_state
                and interrupted_state.get("task") in (
                    "CONFESSION_QUEUED", "CONFESSION_RETRIEVE_COINS",
                    "CONFESSION_TRAVEL_TO_PRIEST", "GOING_TO_CONFESSION_BOX",
                    "CONFESSING",
                )):
            priest.task = "PREACHING"
            priest.confession_task = "WAITING_FOR_VISITOR"
            return True
        if request.get("state") == "VISITOR_TO_PRIEST":
            priest.task = "GOING_TO_CONFESSOR"
            priest.confession_task = "APPROACHING_VISITOR"
            visitor.task = "CONFESSION_TRAVEL_TO_PRIEST"
            visitor.confession_task = "APPROACHING_PRIEST"
            visitor._move_towards(
                priest.x, priest.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                exclusive_target=False, interaction_target=priest,
            )
            priest._move_towards(
                visitor.x, visitor.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                exclusive_target=False, interaction_target=visitor,
            )
            if distance_to_object(priest, visitor.x, visitor.y, TILE_SIZE) <= TILE_SIZE:
                fee_due = max(0, int(request.get("fee_due", 0)))
                fee_offer = min(fee_due, to_copper(normalize_wallet(visitor.inventory)))
                cls._transfer_offering(visitor, priest, fee_offer)
                if (fee_offer > 0 and str(getattr(priest, "family_id", ""))
                        != str(getattr(visitor, "family_id", ""))):
                    from game.systems.market_sales_report import MarketSalesReportSystem
                    MarketSalesReportSystem.record_household_income(
                        villager_manager, getattr(priest, "family_id", None),
                        "Confession Offerings", fee_offer,
                        getattr(day_cycle, "day_number", 1),
                    )
                request["paid"] = True
                request["fee_paid"] = fee_offer
                request["state"] = "BOTH_TO_BOX"
                visitor.task = "GOING_TO_CONFESSION_BOX"
                visitor.confession_task = "GOING_TO_BOX"
                priest.task = "GOING_TO_CONFESSION_BOX"
                priest.confession_task = "GOING_TO_BOX"
            return True
        if request.get("state") == "BOTH_TO_BOX":
            visitor.task = "GOING_TO_CONFESSION_BOX"
            visitor.confession_task = "GOING_TO_BOX"
            priest.task = "GOING_TO_CONFESSION_BOX"
            priest.confession_task = "GOING_TO_BOX"
            cls._move_to_box(visitor, box, dt, all_entities, player,
                             building_manager, furniture_manager, side=0)
            cls._move_to_box(priest, box, dt, all_entities, player,
                             building_manager, furniture_manager, side=1)
            visitor_at_box = cls._at_approach(
                visitor, box, building_manager, furniture_manager, side=0,
            )
            request["visitor_at_box"] = visitor_at_box
            priest_at_box = cls._at_approach(
                priest, box, building_manager, furniture_manager, side=1,
            )
            if visitor_at_box:
                visitor.task = "CONFESSING"
                visitor.confession_task = "WAITING_FOR_PRIEST"
            if visitor_at_box and priest_at_box:
                request["state"] = "IN_PROGRESS"
                request["elapsed"] = 0.0
                priest.task = "HEARING_CONFESSION"
                priest.confession_task = "IN_PROGRESS"
                visitor.task = "CONFESSING"
                visitor.confession_task = "IN_PROGRESS"
                visitor.say("Forgive me, Father...", duration=CONFESSION_BUBBLE_DURATION_SECONDS)
                priest.say("Speak freely. I am listening.", duration=CONFESSION_BUBBLE_DURATION_SECONDS)
            return True
        if request.get("state") == "IN_PROGRESS":
            request["elapsed"] = request.get("elapsed", 0.0) + max(0.0, dt)
            priest.task = "HEARING_CONFESSION"
            priest.confession_task = "IN_PROGRESS"
            priest.is_moving = False
            visitor.task = "CONFESSING"
            visitor.confession_task = "IN_PROGRESS"
            visitor.is_moving = False
            if request.get("elapsed", 0.0) >= cls._confession_duration():
                visitor.faith = random.uniform(AI_NEED_FAITH_CONFESSION_RESTORE_MIN,
                                               AI_NEED_FAITH_CONFESSION_RESTORE_MAX)
                visitor.last_confession_day = getattr(day_cycle, "day_number", 1)
                from game.systems.happiness_system import HappinessSystem
                HappinessSystem.record_event(
                    visitor, "confession_completed",
                    getattr(day_cycle, "day_number", 1),
                )
                visitor.confession_task = None
                visitor.say("I feel at peace again.", duration=2.5)
                cls._finish_request(church_key, visitor, priest, success=True)
            return True
        return False

    @classmethod
    def on_prayer_completed(cls, villager, day_number):
        if (getattr(villager, "prayer_attendance_day", None) == day_number
                and getattr(villager, "last_faith_prayer_day", None) != day_number):
            restore_amount = random.uniform(
                AI_NEED_FAITH_PRAYER_RESTORE_MIN,
                AI_NEED_FAITH_PRAYER_RESTORE_MAX,
            )
            villager.faith = min(100.0, float(getattr(villager, "faith", 100.0)) + restore_amount)
            villager.last_faith_prayer_day = day_number
            villager.prayer_attendance_day = None
            from game.systems.happiness_system import HappinessSystem
            HappinessSystem.record_daily_event(villager, "prayer_completed", day_number)

    @classmethod
    def _request_for_villager(cls, villager_id):
        inst = cls.get_instance()
        for queue in inst.queues.values():
            for request in queue:
                if str(request.get("villager_id")) == str(villager_id):
                    return request
        for request in inst.active.values():
            if str(request.get("villager_id")) == str(villager_id):
                return request
        return None

    @classmethod
    def has_pending_requests_for_priest(cls, priest, permit_manager):
        if not priest:
            return False
        church = next((
            permit for permit in ChurchSystem.get_all_church_permits(permit_manager)
            if str(priest.id) in {
                str(worker_id) for worker_id in getattr(permit, "assigned_workers", [])
            }
        ), None)
        if not church:
            return False
        church_key = str(church.id)
        inst = cls.get_instance()
        return bool(inst.active.get(church_key) or inst.queues.get(church_key))

    @classmethod
    def _find_priest(cls, request, villager_manager, priest_role=True):
        if not villager_manager:
            return None
        return next((villager for villager in villager_manager.get_all_villagers()
                     if str(villager.id) == str(request.get("priest_id" if priest_role else "villager_id"))), None)

    @classmethod
    def _queue_position(cls, index, tiles, furniture_manager, box):
        if not tiles:
            return None
        box_tiles = furniture_manager._furniture_tiles(box) if furniture_manager else set()
        candidates = [tile for tile in tiles if tile not in box_tiles]
        if furniture_manager:
            candidates = [tile for tile in candidates if furniture_manager.get_furniture_at(*tile) is None]
        if index >= len(candidates):
            return None
        return candidates[index]

    @classmethod
    def _approach_points(cls, box, building_manager, furniture_manager):
        width, height = box.footprint_dimensions
        candidates = set()
        for gx in range(box.grid_x, box.grid_x + width):
            candidates.update(((gx, box.grid_y - 1), (gx, box.grid_y + height)))
        for gy in range(box.grid_y, box.grid_y + height):
            candidates.update(((box.grid_x - 1, gy), (box.grid_x + width, gy)))
        occupied = furniture_manager._furniture_tiles(box) if furniture_manager else set()
        candidates = [tile for tile in candidates if tile not in occupied
                      and (not furniture_manager or furniture_manager.get_furniture_at(*tile) is None)]
        return sorted(candidates)

    @classmethod
    def _move_to_box(cls, villager, box, dt, all_entities, player,
                     building_manager, furniture_manager, side=0):
        points = cls._approach_points(box, building_manager, furniture_manager)
        if points:
            point = points[min(side, len(points) - 1)]
            cls._move_to_point(villager, ((point[0] + 0.5) * TILE_SIZE, (point[1] + 0.5) * TILE_SIZE),
                               dt, all_entities, player, building_manager, furniture_manager,
                               interaction_target=box)

    @classmethod
    def _move_to_point(cls, villager, point, dt, all_entities, player, building_manager,
                       furniture_manager, interaction_target=None):
        from game.config import INTERACTION_CONTACT_RADIUS
        villager._move_towards(point[0], point[1], dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                               all_entities=all_entities, player=player,
                               building_manager=building_manager,
                               furniture_manager=furniture_manager, exclusive_target=False,
                               interaction_target=interaction_target)

    @classmethod
    def _at_approach(cls, villager, box, building_manager, furniture_manager, side=0):
        if not cls._approach_points(box, building_manager, furniture_manager):
            return False
        return distance_to_object(box, villager.x, villager.y, TILE_SIZE) <= TILE_SIZE

    @classmethod
    def _free_time_ended(cls, request, villager_manager, day_cycle,
                         schedule_manager=None):
        visitor = cls._find_priest(request, villager_manager, priest_role=False)
        if not visitor:
            return True
        if not schedule_manager:
            return False
        actors = [visitor]
        if not request.get("self_confession"):
            priest = cls._find_priest(request, villager_manager)
            if not priest:
                return True
            actors.append(priest)
        current_hour = getattr(day_cycle, "current_hour", 0.0)
        return any(
            schedule_manager.get_current_activity(
                actor.job, current_hour,
            ) not in FREE_TIME_SCHEDULE_ACTIVITIES
            for actor in actors
        )

    @classmethod
    def cancel_if_schedule_ended(cls, villager, villager_manager,
                                 furniture_manager, day_cycle,
                                 schedule_manager):
        request = cls._request_for_villager(getattr(villager, "id", None))
        if (not request or not cls._free_time_ended(
                request, villager_manager, day_cycle, schedule_manager)):
            return False
        cls._cancel_request(
            request, villager_manager,
            "My free time is over; I will return later.",
            furniture_manager,
        )
        return True

    @classmethod
    def _daily_livelihood_cost(cls, building_manager):
        markets = MarketService.get_all_markets(building_manager)
        quotes = []
        for item in MARKET_TRADEABLE_ITEMS:
            if is_food_item(item):
                market, price = MarketService.get_lowest_available_item_quote(
                    item, building_manager=building_manager, markets=markets, minimum_stock=1
                )
                if market:
                    quotes.append(int(price))
        if quotes:
            return max(1, min(quotes))
        configured = [int(price) for item, price in DEFAULT_ITEM_PRICES.items()
                      if is_food_item(item) and int(price) > 0]
        return max(1, min(configured)) if configured else 1

    @classmethod
    def _transfer_offering(cls, confessor, priest, amount):
        from game.systems.carpenter_system import CarpenterSystem
        amount = max(0, int(amount))
        if amount:
            CarpenterSystem._move_exact_value(
                getattr(confessor, "inventory", {}),
                getattr(priest, "inventory", {}), amount,
            )
        confessor.say(f"I offer {amount}c for confession.", duration=CONFESSION_BUBBLE_DURATION_SECONDS)
        priest.say("I have received your offering. Come, let us confess.",
                   duration=CONFESSION_BUBBLE_DURATION_SECONDS)
        return amount

    @classmethod
    def _refund_prepared_payment(cls, request, villager, furniture_manager):
        amount = max(0, int(request.get("withdrawn_amount", 0)))
        if amount <= 0:
            return True
        if not villager or not furniture_manager:
            return False

        family_id = request.get("payment_family_id", getattr(villager, "family_id", None))
        chest_id = request.get("payment_chest_id")
        chest = furniture_manager.get_furniture_by_id(chest_id) if chest_id is not None else None
        if (chest and str(getattr(chest, "family_id", "")) != str(family_id)):
            chest = None
        if not chest and family_id is not None:
            chest = furniture_manager.get_storage_for_family(family_id)
        if not chest:
            return False

        source_name = request.get("payment_source", "inventory")
        if source_name not in ("inventory", "currency"):
            source_name = "inventory"
        destination = getattr(chest, source_name, None)
        if not isinstance(destination, dict):
            destination = getattr(chest, "inventory", None)
        if not isinstance(destination, dict):
            return False

        from game.systems.carpenter_system import CarpenterSystem
        if not CarpenterSystem._move_exact_value(
                getattr(villager, "inventory", {}), destination, amount):
            return False
        request["withdrawn_amount"] = 0
        from game.systems.wealth_system import VillageWealthSystem
        VillageWealthSystem.mark_dirty()
        return True

    @classmethod
    def _cancel_request(cls, request, villager_manager, message, furniture_manager=None):
        church_key = str(request.get("church_id"))
        inst = cls.get_instance()
        inst.queues[church_key] = [item for item in inst.queues.get(church_key, []) if item is not request]
        was_active = inst.active.get(church_key) is request
        if was_active:
            inst.active.pop(church_key, None)
        villager = cls._find_priest(request, villager_manager, priest_role=False)
        priest = cls._find_priest(request, villager_manager)
        actors = (villager, priest) if was_active else (villager,)
        for actor in actors:
            if actor:
                actor.confession_task = None
                if actor.task in ("CONFESSION_QUEUED", "WAITING_FOR_CONFESSION", "HEARING_CONFESSION",
                                  "CONFESSING", "CONFESSION_RETRIEVE_COINS",
                                  "CONFESSION_TRAVEL_TO_PRIEST", "GOING_TO_CONFESSOR",
                                  "GOING_TO_CONFESSION_BOX"):
                    actor.task = "IDLE"
        if was_active and request.get("fee_paid", 0) > 0:
            payer = villager
            if payer and priest:
                from game.systems.carpenter_system import CarpenterSystem
                CarpenterSystem._move_exact_value(
                    getattr(priest, "inventory", {}),
                    getattr(payer, "inventory", {}),
                    request["fee_paid"],
                )
                payer.say("The confession was canceled; my offering has been returned.", duration=2.5)
        refunded = cls._refund_prepared_payment(request, villager, furniture_manager)
        if villager:
            if not refunded and int(request.get("withdrawn_amount", 0)) > 0:
                message = (
                    f"{message} The withdrawn offering could not be returned "
                    "to household storage."
                )
            villager.say(message, duration=2.5)

    @classmethod
    def _finish_request(cls, church_key, visitor, priest, success):
        inst = cls.get_instance()
        inst.active.pop(church_key, None)
        for actor in (visitor, priest):
            if actor:
                actor.confession_task = None
                if actor.task in ("WAITING_FOR_CONFESSION", "HEARING_CONFESSION", "CONFESSING",
                                  "CONFESSION_QUEUED", "CONFESSION_RETRIEVE_COINS",
                                  "CONFESSION_TRAVEL_TO_PRIEST", "GOING_TO_CONFESSOR",
                                  "GOING_TO_CONFESSION_BOX"):
                    actor.task = "IDLE"
        if success and priest:
            priest.say("May you walk in peace.", duration=2.5)


def math_distance(ax, ay, bx, by):
    return ((float(ax) - float(bx)) ** 2 + (float(ay) - float(by)) ** 2) ** 0.5
