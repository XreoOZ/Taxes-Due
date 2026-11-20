"""Furniture orders, household commissions, Carpenter materials, and construction."""

import math
import random

from game.data.config import (
    CARPENTER_BUILD_DURATION_INGAME_HOURS,
    CARPENTER_DEFAULT_LIVING_HOUSEHOLD_SIZE,
    CARPENTER_REPAIR_FOOD_DAYS,
    DAILY_FOOD_REQUIREMENT,
    DAY_LENGTH_OPTIONS,
    DEFAULT_DAY_LENGTH_INDEX,
    DEFAULT_ITEM_PRICES,
    DEDICATED_JOBS,
    FURNITURE_TYPES,
    BUILDING_TYPES,
    MARKET_TRADEABLE_ITEMS,
    FREE_TIME_SCHEDULE_ACTIVITIES,
    ROUTE_STATE_FAILED,
    CARPENTER_INSUFFICIENT_LANDLORD_COIN_MESSAGES,
)
from game.systems.currency import (
    CURRENCY_DENOMINATIONS,
    canonical_denomination,
    compact_currency_wallet,
    from_copper,
    normalize_wallet,
    to_copper,
)
from game.systems.market_service import MarketService
from game.config import TILE_SIZE, CHEST_INTERACTION_RADIUS, INTERACTION_CONTACT_RADIUS, LOOSE_ITEM_ARRIVAL_DIST


class CarpenterSystem:
    @classmethod
    def request_public_commission(cls, subject, resources, servant_manager,
                                  villager_manager, building_manager, day_cycle=None,
                                  stockpile_manager=None, furniture_manager=None):
        """Dispatch a servant to collect a public commission from the Lord's Treasury Chest."""
        order = getattr(subject, "construction_order", None)
        if hasattr(subject, "building_type"):
            cfg = BUILDING_TYPES.get(subject.building_type, {})
            if not cfg.get("carpenter_commissionable"):
                return False, "This public structure is not configured for a carpenter commission."
            if not (isinstance(order, dict) and order.get("order_type") == "REPAIR"):
                quote = cls._quote_from_materials(
                    getattr(subject, "required_cost", {}), building_manager, villager_manager
                )
                if not isinstance(order, dict):
                    order = {}
                    subject.construction_order = order
                order.update(quote)
                order.update({
                    "id": f"public:{subject.building_type}:{subject.grid_x}:{subject.grid_y}",
                    "order_type": "PUBLIC_BUILD",
                    "building_type": subject.building_type,
                    "payer_family_id": None,
                })
            else:
                order["payer_family_id"] = None
        elif hasattr(subject, "furniture_type"):
            cfg = FURNITURE_TYPES.get(subject.furniture_type, {})
            if cfg.get("household_owned", True) or getattr(subject, "family_id", None) is not None:
                return False, "This furniture is not public property."
            order = getattr(subject, "construction_order", None)
            if not isinstance(order, dict):
                return False, "This furniture has no carpenter order."
            if order.get("order_type") != "REPAIR":
                order.update(cls.quote_order(subject.furniture_type, building_manager, villager_manager))
            order["payer_family_id"] = None
        if not isinstance(order, dict):
            return False, "This blueprint has no carpenter order."
        if order.get("status") not in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"):
            return False, "This carpenter commission is already being handled."
        carpenters = [v for v in villager_manager.get_all_villagers()
                      if getattr(v, "job", None) == "Carpenter" and getattr(v, "is_alive", True)] if villager_manager else []
        if not carpenters:
            return False, "No Carpenter is available for this commission."
        order_sources = (
            list(getattr(furniture_manager, "furnitures", []))
            + list(getattr(building_manager, "construction_sites", []))
            + list(getattr(building_manager, "buildings", []))
        )
        active_statuses = {"COMPLETE", "AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"}
        busy_carpenters = {
            str(source.construction_order.get("carpenter_id"))
            for source in order_sources
            if isinstance(getattr(source, "construction_order", None), dict)
            and source.construction_order.get("carpenter_id") is not None
            and source.construction_order.get("status") not in active_statuses
        }
        carpenters = [worker for worker in carpenters if str(worker.id) not in busy_carpenters]
        if not carpenters:
            return False, "All Carpenters are already handling commissions."
        servants = [s for s in getattr(servant_manager, "servants", [])
                    if getattr(s, "state", "IDLE") == "IDLE"] if servant_manager else []
        fee = max(0, int(order.get("price_copper", 0)))
        from game.systems.lord_treasury import LordTreasurySystem
        treasury = LordTreasurySystem.get_chest(furniture_manager)
        if not treasury or LordTreasurySystem.value(furniture_manager) < fee:
            message = random.choice(CARPENTER_INSUFFICIENT_LANDLORD_COIN_MESSAGES)
            if servant_manager and getattr(servant_manager, "servants", None):
                servant_manager.servants[0].say(message, duration=3.5)
            return False, message
        if not servants:
            return False, "No idle servant is available to carry the commission."

        if hasattr(subject, "get_world_pos"):
            target_x, target_y = subject.get_world_pos(TILE_SIZE)
        elif hasattr(subject, "get_center_world"):
            target_x, target_y = subject.get_center_world(TILE_SIZE)
        else:
            target_x = (subject.grid_x + subject.tiles_w / 2.0) * TILE_SIZE
            target_y = (subject.grid_y + subject.tiles_h / 2.0) * TILE_SIZE
        carpenter = min(carpenters, key=lambda worker: math.hypot(worker.x - target_x, worker.y - target_y))
        servant = min(
            servants,
            key=lambda worker: math.hypot(
                (treasury.grid_x + 0.5) * TILE_SIZE - worker.x,
                (treasury.grid_y + 0.5) * TILE_SIZE - worker.y,
            ),
        )

        order["status"] = "LANDLORD_RETRIEVING"
        order["payer_type"] = "landlord"
        order["payer_id"] = "landlord"
        order["carpenter_id"] = str(carpenter.id)
        order["commission_paid"] = False
        if day_cycle:
            seconds_per_hour = max(1.0, float(day_cycle.day_length_seconds)) / 24.0
            order["build_duration_seconds"] = seconds_per_hour * CARPENTER_BUILD_DURATION_INGAME_HOURS
        servant.carpenter_commission_order_id = str(order.get("id"))
        servant.carpenter_commission_carpenter_id = str(carpenter.id)
        servant.carpenter_commission_fee_copper = fee
        servant.carpenter_commission_remaining_copper = fee
        servant.carpenter_commission_storage_tile = [treasury.grid_x, treasury.grid_y]
        servant.carpenter_commission_treasury_id = str(treasury.id)
        servant.state = "CARPENTER_COMMISSION_RETRIEVE"
        servant.say("I am retrieving the commission from the Lord's Treasury Chest, my Lord.", duration=2.5)
        return True, "A servant is retrieving coins from the Lord's Treasury Chest."

    @classmethod
    def dispatch_pending_public_commissions(cls, building_manager, servant_manager,
                                            villager_manager, furniture_manager,
                                            day_cycle=None, stockpile_manager=None):
        """Automatically start landlord-paid Carpenter orders for eligible public blueprints."""
        if not building_manager or not servant_manager or not villager_manager:
            return 0
        from game.systems.lord_treasury import LordTreasurySystem

        treasury = LordTreasurySystem.get_chest(furniture_manager)
        if not treasury:
            return 0
        started = 0
        candidates = []
        for site in getattr(building_manager, "construction_sites", []):
            cfg = BUILDING_TYPES.get(getattr(site, "building_type", ""), {})
            if cfg.get("carpenter_commissionable"):
                candidates.append(site)
        candidates.extend(
            building for building in getattr(building_manager, "buildings", [])
            if (getattr(building, "construction_order", None) or {}).get("order_type") == "REPAIR"
            and (getattr(building, "type_cfg", {}) or {}).get("public_structure")
        )
        candidates.extend(
            furniture for furniture in getattr(furniture_manager, "furnitures", [])
            if (
                (getattr(furniture, "construction_order", None) or {}).get("payer_type") == "landlord"
                or (
                    getattr(furniture, "family_id", None) is None
                    and not (getattr(furniture, "type_cfg", {}) or {}).get("household_owned", True)
                    and getattr(furniture, "construction_order", None)
                )
            )
        )
        for site in candidates:
            order = getattr(site, "construction_order", None) or {}
            if order.get("status") not in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"):
                continue
            if "price_copper" not in order:
                order.update(cls.quote_building_order(
                    site.building_type, building_manager, villager_manager,
                    tile_count=len(getattr(site, "tiles", ())),
                ))
            if LordTreasurySystem.value(furniture_manager) < max(0, int(order.get("price_copper", 0))):
                idle_servant = next((servant for servant in getattr(servant_manager, "servants", [])
                                     if getattr(servant, "state", "IDLE") == "IDLE"), None)
                if idle_servant and not order.get("insufficient_coin_notice_sent"):
                    idle_servant.say(random.choice(CARPENTER_INSUFFICIENT_LANDLORD_COIN_MESSAGES), duration=3.5)
                    order["insufficient_coin_notice_sent"] = True
                continue
            order.pop("insufficient_coin_notice_sent", None)
            if not any(getattr(servant, "state", "IDLE") == "IDLE"
                       for servant in getattr(servant_manager, "servants", [])):
                continue
            success, message = cls.request_public_commission(
                site, None, servant_manager, villager_manager, building_manager,
                day_cycle=day_cycle, stockpile_manager=stockpile_manager,
                furniture_manager=furniture_manager,
            )
            if success:
                started += 1
                order.pop("dispatch_failure_notice", None)
            elif message and order.get("dispatch_failure_notice") != message:
                idle_servant = next((servant for servant in getattr(servant_manager, "servants", [])
                                     if getattr(servant, "state", "IDLE") == "IDLE"), None)
                if idle_servant:
                    idle_servant.say(message, duration=3.5)
                    order["dispatch_failure_notice"] = message
        return started

    @classmethod
    def refund_public_courier_coins(cls, servant, stockpile_manager, furniture_manager=None):
        from game.systems.lord_treasury import LordTreasurySystem
        refunded_to_treasury = LordTreasurySystem.deposit_all(furniture_manager, servant.inventory)
        if not refunded_to_treasury:
            tile = getattr(servant, "carpenter_commission_storage_tile", None)
            tile = tile or [int(servant.x // TILE_SIZE), int(servant.y // TILE_SIZE)]
            if stockpile_manager:
                for key in list(servant.inventory):
                    if canonical_denomination(key):
                        amount = max(0, int(servant.inventory.pop(key, 0)))
                        if amount:
                            stockpile_manager.drop_resource(key, amount, *tile, owner_type="landlord")
        servant.carpenter_commission_treasury_id = None
        servant.carpenter_commission_fee_copper = 0
        servant.carpenter_commission_remaining_copper = 0
        servant.carpenter_commission_storage_tile = None
        return refunded_to_treasury

    @classmethod
    def quote_building_order(cls, building_type, building_manager=None, villager_manager=None,
                             tile_count=None):
        cfg = BUILDING_TYPES.get(building_type, {})
        if cfg.get("fixed_cost"):
            materials = {
                "Wood": max(0, int(cfg.get("cost_wood", 0))),
                "Stone": max(0, int(cfg.get("cost_stone", 0))),
            }
        else:
            count = max(1, int(tile_count or 1))
            materials = {
                "Wood": count * max(0, int(cfg.get("cost_wood", 0))),
                "Stone": count * max(0, int(cfg.get("cost_stone", 0))),
            }
        return cls._quote_from_materials(materials, building_manager, villager_manager)

    @classmethod
    def _quote_from_materials(cls, materials, building_manager=None, villager_manager=None):
        markets = MarketService.get_all_markets(building_manager)
        material_cost = 0
        for material, amount in materials.items():
            amount = max(0, int(amount))
            if not amount:
                continue
            _, price = MarketService.get_lowest_available_item_quote(
                material, markets=markets, minimum_stock=amount
            )
            unit_price = price if price is not None else MarketService.get_item_price(material)
            material_cost += amount * unit_price
        carpenters = [v for v in villager_manager.get_all_villagers()
                      if getattr(v, "job", None) == "Carpenter" and getattr(v, "is_alive", True)] if villager_manager else []
        family = villager_manager.get_family_by_id(carpenters[0].family_id) if carpenters else None
        household_size = max(
            CARPENTER_DEFAULT_LIVING_HOUSEHOLD_SIZE,
            len([m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)]) if family else 1,
        )
        food_unit_price = cls._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT * household_size)
        wage = food_unit_price * DAILY_FOOD_REQUIREMENT * household_size
        return {"material_cost_copper": material_cost, "living_wage_copper": wage,
                "price_copper": material_cost + wage, "materials": dict(materials),
                "food_unit_price_at_order": food_unit_price}

    @staticmethod
    def _within_furniture_work_range(carpenter, furniture):
        width = max(1, int(furniture.type_cfg.get("width_tiles", 1))) * TILE_SIZE
        height = max(1, int(furniture.type_cfg.get("height_tiles", 1))) * TILE_SIZE
        left = furniture.grid_x * TILE_SIZE
        top = furniture.grid_y * TILE_SIZE
        closest_x = max(left, min(carpenter.x, left + width))
        closest_y = max(top, min(carpenter.y, top + height))
        return math.hypot(carpenter.x - closest_x, carpenter.y - closest_y) <= INTERACTION_CONTACT_RADIUS

    @staticmethod
    def _market_for_furniture(furniture, building_manager):
        markets = MarketService.get_all_markets(building_manager)
        if not markets:
            return None
        wx, wy = furniture.get_world_pos(TILE_SIZE)
        return min(markets, key=lambda market: math.hypot(
            market.get_center_world(TILE_SIZE)[0] - wx,
            market.get_center_world(TILE_SIZE)[1] - wy,
        ))

    @classmethod
    def _food_unit_price(cls, market, minimum_stock=1):
        markets = market if isinstance(market, (list, tuple)) else [market] if market else []
        food_items = [item for item, category in MARKET_TRADEABLE_ITEMS.items() if category == "Food"]
        quotes = [
            MarketService.get_lowest_available_item_quote(
                item, markets=markets, minimum_stock=minimum_stock
            )[1]
            for item in food_items
        ]
        available_quotes = [price for price in quotes if price is not None]
        if available_quotes:
            return min(available_quotes)
        fallback_prices = [DEFAULT_ITEM_PRICES[item] for item in food_items if item in DEFAULT_ITEM_PRICES]
        return min(fallback_prices) if fallback_prices else 1

    @classmethod
    def quote_order(cls, furniture_type, building_manager=None, villager_manager=None, reference_position=None):
        cfg = FURNITURE_TYPES.get(furniture_type, {})
        return cls._quote_from_materials(cfg.get("materials", {}), building_manager, villager_manager)

    @classmethod
    def create_order(cls, furniture, building_manager=None, villager_manager=None):
        order = cls.quote_order(
            furniture.furniture_type, building_manager, villager_manager,
            reference_position=furniture.get_world_pos(TILE_SIZE),
        )
        order.update({
            "id": str(furniture.id),
            "order_type": "BUILD",
            "status": "AWAITING_PAYMENT",
            "payer_family_id": furniture.family_id,
            "payer_id": None,
            "carpenter_id": None,
            "commission_paid": False,
        })
        return order

    @classmethod
    def create_repair_order(cls, asset, building_manager=None, villager_manager=None):
        markets = MarketService.get_all_markets(building_manager)
        food_unit_price = cls._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT)
        repair_price = food_unit_price * DAILY_FOOD_REQUIREMENT * CARPENTER_REPAIR_FOOD_DAYS
        order_id = getattr(asset, "id", None)
        asset_type_cfg = getattr(asset, "type_cfg", {}) or {}
        is_public = bool(asset_type_cfg.get("public_structure"))
        if order_id is None and hasattr(asset, "building_type"):
            order_id = f"building:{asset.building_type}:{asset.grid_x}:{asset.grid_y}"
        return {
            "id": str(order_id),
            "order_type": "REPAIR",
            "status": "AWAITING_PAYMENT",
            "payer_family_id": getattr(asset, "family_id", None),
            "payer_type": "landlord" if is_public else "household",
            "payer_id": "landlord" if is_public else None,
            "carpenter_id": None,
            "commission_paid": False,
            "material_cost_copper": 0,
            "living_wage_copper": repair_price,
            "price_copper": repair_price,
            "food_unit_price_at_order": food_unit_price,
            "progress_ratio": 0.0,
        }

    @classmethod
    def _get_order(cls, furniture_manager, order_id):
        return next((f for f in getattr(furniture_manager, "furnitures", [])
                     if str(getattr(f, "id", "")) == str(order_id)
                     and getattr(f, "construction_order", None)), None)

    @classmethod
    def _move_exact_value(cls, source, destination, amount):
        amount = max(0, int(amount))
        if to_copper(source) < amount:
            return False
        remaining = from_copper(to_copper(source) - amount)
        for key in list(source):
            if canonical_denomination(key):
                del source[key]
        source.update({key: value for key, value in remaining.items() if value})
        for key, value in from_copper(amount).items():
            if value:
                destination[key] = destination.get(key, 0) + value
        compact_currency_wallet(source)
        compact_currency_wallet(destination)
        return True

    @classmethod
    def _assign_payment(cls, order_furniture, villager_manager, furniture_manager):
        order = order_furniture.construction_order
        family_id = order.get("payer_family_id")
        family = villager_manager.get_family_by_id(family_id) if family_id is not None and villager_manager else None
        survivors = [m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)]
        if survivors:
            chest = furniture_manager.get_storage_for_family(family_id)
            fee = int(order["price_copper"])
            if not chest or to_copper(normalize_wallet(chest.inventory)) < fee:
                order["status"] = "AWAITING_PAYMENT"
                return False
            payer = family.get_available_recovery_representative() if hasattr(family, "get_available_recovery_representative") else survivors[0]
            carpenter_id = str(order.get("carpenter_id"))
            if payer and str(getattr(payer, "id", "")) == carpenter_id:
                other_members = [member for member in survivors if str(getattr(member, "id", "")) != carpenter_id]
                if other_members:
                    payer = next((member for member in other_members
                                  if getattr(member, "task", "") not in ("SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET", "RECOVER_DEATH_ITEMS")
                                  and getattr(member, "hunger", 100.0) > 20.0
                                  and getattr(member, "thirst", 100.0) > 20.0
                                  and getattr(member, "need_toilet", 100.0) > 20.0), other_members[0])
            if not payer:
                return False
            carpenter = next((member for member in survivors
                               if str(getattr(member, "id", "")) == carpenter_id), None)
            if str(getattr(payer, "id", "")) == carpenter_id and carpenter:
                order["payer_id"] = str(payer.id)
                order["status"] = "PAYMENT_REQUESTED"
                from game.systems.commission_schedule import CommissionScheduleSystem
                CommissionScheduleSystem.queue(
                    payer, "CARPENTER_FEE_RETRIEVE",
                    carpenter_payment_order_id=order["id"],
                    carpenter_payment_carpenter_id=order.get("carpenter_id"),
                )
                return True
            order["payer_id"] = str(payer.id)
            order["status"] = "PAYMENT_REQUESTED"
            from game.systems.commission_schedule import CommissionScheduleSystem
            CommissionScheduleSystem.queue(
                payer, "CARPENTER_FEE_RETRIEVE",
                carpenter_payment_order_id=order["id"],
                carpenter_payment_carpenter_id=order.get("carpenter_id"),
            )
            return True
        order["status"] = "LANDLORD_PAYMENT_PENDING"
        return True

    @classmethod
    def update_payment_task(cls, villager, dt, building_manager, furniture_manager,
                            stockpile_manager, all_entities, player, villager_manager=None,
                            day_number=1):
        task = getattr(villager, "task", "")
        if task not in ("CARPENTER_FEE_RETRIEVE", "CARPENTER_FEE_TRAVEL", "CARPENTER_FEE_LANDLORD_RETRIEVE"):
            return False
        order_furniture = cls._get_order(furniture_manager, getattr(villager, "carpenter_payment_order_id", None))
        if not order_furniture:
            villager.carpenter_payment_order_id = None
            villager.carpenter_payment_carpenter_id = None
            villager._resume_or_idle_after_need()
            return True
        order = order_furniture.construction_order
        carpenter = (
            all_entities.by_id(order.get("carpenter_id"))
            if hasattr(all_entities, "by_id")
            else next((e for e in all_entities if str(getattr(e, "id", "")) == str(order.get("carpenter_id"))), None)
        )
        fee = max(0, int(order.get("price_copper", 0)))

        if task == "CARPENTER_FEE_RETRIEVE":
            chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
            if not chest:
                order["status"] = "AWAITING_PAYMENT"
                villager.carpenter_payment_order_id = None
                villager._resume_or_idle_after_need()
                return True
            pos = chest.get_approach_point(villager.x, villager.y, worker_id=villager.id,
                                           all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
            arrived = villager._move_towards(pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager, furniture_manager=furniture_manager)
            if arrived:
                if cls._move_exact_value(chest.inventory, villager.inventory, fee):
                    if str(order.get("carpenter_id")) == str(villager.id):
                        order["status"] = "PAID"
                        order["commission_paid"] = True
                        order["paid_by_id"] = str(villager.id)
                        order["paid_by_family_id"] = str(villager.family_id)
                        order["paid_amount_copper"] = fee
                        villager.carpenter_payment_order_id = None
                        villager.carpenter_payment_carpenter_id = None
                        villager.task = "IDLE"
                        villager.say(f"Commission paid from our household: {fee} Copper.", duration=2.5)
                    else:
                        order["status"] = "PAYMENT_TRAVELING"
                        villager.task = "CARPENTER_FEE_TRAVEL"
                else:
                    order["status"] = "AWAITING_PAYMENT"
                    villager.say("Our household does not have enough coins for this furniture order.", duration=3.0)
                    villager.carpenter_payment_order_id = None
                    villager._resume_or_idle_after_need()
            return True

        if task == "CARPENTER_FEE_TRAVEL":
            if not carpenter or not getattr(carpenter, "is_alive", True):
                chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
                if chest:
                    cls._move_exact_value(villager.inventory, chest.inventory, fee)
                order["status"] = "AWAITING_PAYMENT"
                villager.carpenter_payment_order_id = None
                villager._resume_or_idle_after_need()
                return True
            arrived = villager._move_towards(carpenter.x, carpenter.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager, furniture_manager=furniture_manager)
            if arrived:
                if cls._move_exact_value(villager.inventory, carpenter.inventory, fee):
                    order["status"] = "PAID"
                    order["commission_paid"] = True
                    order["paid_by_id"] = str(villager.id)
                    order["paid_by_family_id"] = str(villager.family_id)
                    order["paid_amount_copper"] = fee
                    if str(getattr(villager, "family_id", "")) != str(getattr(carpenter, "family_id", "")):
                        from game.systems.market_sales_report import MarketSalesReportSystem
                        MarketSalesReportSystem.record_household_income(
                            villager_manager, getattr(carpenter, "family_id", None),
                            "Carpenter Commissions", fee, day_number,
                        )
                    villager.say("Furniture commission paid.", duration=2.0)
                    carpenter.say(f"Commission received: {fee} Copper. I will begin the order.", duration=2.5)
                else:
                    order["status"] = "AWAITING_PAYMENT"
                    villager.say("I no longer have the full furniture commission.", duration=2.5)
                villager.carpenter_payment_order_id = None
                villager.carpenter_payment_carpenter_id = None
                villager._resume_or_idle_after_need()
            return True

        from game.systems.lord_treasury import LordTreasurySystem
        treasury = LordTreasurySystem.get_chest(furniture_manager)
        if treasury:
            if not carpenter or LordTreasurySystem.value(furniture_manager) < fee:
                order["status"] = "LANDLORD_PAYMENT_PENDING"
                return True
            pos = treasury.get_approach_point(
                villager.x, villager.y, worker_id=villager.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
            arrived = villager._move_towards(
                pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
            )
            if arrived:
                if LordTreasurySystem.withdraw_covering(furniture_manager, villager.inventory, fee)[0]:
                    order["status"] = "PAYMENT_TRAVELING"
                    villager.task = "CARPENTER_FEE_TRAVEL"
                else:
                    order["status"] = "LANDLORD_PAYMENT_PENDING"
            return True

        stacks = [s for s in getattr(stockpile_manager, "stacks", [])
                  if getattr(s, "owner_type", "landlord") == "landlord"
                  and canonical_denomination(getattr(s, "resource_type", ""))]
        wallet = {denom: 0 for denom in CURRENCY_DENOMINATIONS}
        for stack in stacks:
            wallet[canonical_denomination(stack.resource_type)] += max(0, int(stack.amount))
        if not carpenter or not stacks or to_copper(wallet) < fee:
            order["status"] = "LANDLORD_PAYMENT_PENDING"
            return True
        target = min(stacks, key=lambda s: math.hypot((s.grid_x + .5) * TILE_SIZE - villager.x,
                                                       (s.grid_y + .5) * TILE_SIZE - villager.y))
        arrived = villager._move_towards((target.grid_x + .5) * TILE_SIZE, (target.grid_y + .5) * TILE_SIZE,
                                         dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                                         all_entities=all_entities, player=player,
                                         building_manager=building_manager, furniture_manager=furniture_manager)
        if arrived:
            drop_tile = (target.grid_x, target.grid_y)
            for stack in list(stacks):
                if stack in stockpile_manager.stacks:
                    stockpile_manager.stacks.remove(stack)
            stockpile_manager.mark_totals_dirty()
            remainder = from_copper(to_copper(wallet) - fee)
            for denom, amount in remainder.items():
                if amount:
                    stockpile_manager.drop_resource(denom, amount, *drop_tile, owner_type="landlord")
            for denom, amount in from_copper(fee).items():
                if amount:
                    villager.inventory[denom] = villager.inventory.get(denom, 0) + amount
            compact_currency_wallet(villager.inventory)
            order["status"] = "PAID"
            order["commission_paid"] = True
            order["paid_by_id"] = "landlord"
            order["paid_by_family_id"] = None
            order["paid_amount_copper"] = fee
            villager.task = "IDLE"
        return True

    @classmethod
    def _materials_in_storage(cls, carpenter, furniture_manager):
        chest = furniture_manager.get_storage_for_family(carpenter.family_id) if furniture_manager else None
        totals = dict(getattr(carpenter, "inventory", {}))
        material_types = DEDICATED_JOBS.get("Carpenter", {}).get("material_stock_target", {})
        if chest:
            for item in material_types:
                totals[item] = totals.get(item, 0) + chest.inventory.get(item, 0)
        return chest, totals

    @staticmethod
    def _commit_materials_from_storage(carpenter, chest, materials):
        """Consume a checked recipe from the Carpenter's pocket and household chest."""
        inventory = getattr(carpenter, "inventory", {})
        for item, amount in materials.items():
            amount = max(0, int(amount))
            available = int(inventory.get(item, 0))
            if chest:
                available += int(chest.inventory.get(item, 0))
            if available < amount:
                return False

        for item, amount in materials.items():
            remaining = max(0, int(amount))
            from_inventory = min(int(inventory.get(item, 0)), remaining)
            if from_inventory:
                inventory[item] -= from_inventory
                remaining -= from_inventory
                if inventory[item] <= 0:
                    inventory.pop(item, None)
            if remaining and chest:
                chest.inventory[item] = max(0, int(chest.inventory.get(item, 0)) - remaining)
                if not chest.inventory[item]:
                    chest.inventory.pop(item, None)
        return True

    @classmethod
    def _begin_restock(cls, carpenter, missing, building_manager, furniture_manager, villager_manager):
        from game.systems.market_purchasing import AIMarketPurchasingSystem
        for material, quantity in missing.items():
            market, _, affordable = AIMarketPurchasingSystem.find_nearest_market_for_material(
                carpenter, material, quantity, building_manager, furniture_manager, villager_manager)
            if market and affordable:
                carpenter.target_restock_market = market
                carpenter.target_restock_mat = material
                carpenter.target_restock_qty = affordable
                carpenter.task = "CARPENTER_RESTOCK_RETRIEVE_COINS"
                return True
        return False

    @classmethod
    def _update_restock(cls, carpenter, dt, building_manager, furniture_manager, villager_manager,
                        all_entities, player, stockpile_manager=None, permit_manager=None):
        from game.systems.market_purchasing import AIMarketPurchasingSystem
        task = carpenter.task
        market = getattr(carpenter, "target_restock_market", None)
        material = getattr(carpenter, "target_restock_mat", None)
        quantity = getattr(carpenter, "target_restock_qty", 0)
        chest = furniture_manager.get_storage_for_family(carpenter.family_id) if furniture_manager else None
        if not market or not material or quantity <= 0:
            carpenter.task = "IDLE"
            carpenter.target_restock_market = None
            carpenter.target_restock_mat = None
            carpenter.target_restock_qty = 0
            return True
        unit_price = MarketService.get_item_price(material, market)
        if task == "CARPENTER_RESTOCK_RETRIEVE_COINS":
            if to_copper(normalize_wallet(carpenter.inventory)) >= unit_price * quantity:
                arrived = True
            elif chest:
                x, y = chest.get_world_pos(TILE_SIZE)
                arrived = carpenter._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                                  all_entities=all_entities, player=player,
                                                  building_manager=building_manager, furniture_manager=furniture_manager)
            else:
                arrived = True
            if arrived:
                enough, message = AIMarketPurchasingSystem.withdraw_household_coins(
                    carpenter, unit_price * quantity, furniture_manager, villager_manager)
                if enough:
                    carpenter.task = "CARPENTER_RESTOCK_TRAVEL_TO_MARKET"
                else:
                    carpenter.say(message, duration=2.5)
                    carpenter.task = "IDLE"
            return True
        if task == "CARPENTER_RESTOCK_TRAVEL_TO_MARKET":
            x, y = market.get_center_world(TILE_SIZE)
            if carpenter._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                       all_entities=all_entities, player=player,
                                       building_manager=building_manager, furniture_manager=furniture_manager):
                ok, message = AIMarketPurchasingSystem.execute_material_transaction(carpenter, market, material, quantity)
                if ok:
                    carpenter.task = "CARPENTER_RESTOCK_HAULING_HOME"
                else:
                    carpenter.say(message, duration=2.5)
                    carpenter.task = "IDLE"
            return True
        if task == "CARPENTER_RESTOCK_HAULING_HOME":
            if chest:
                x, y = chest.get_world_pos(TILE_SIZE)
                if carpenter._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                           all_entities=all_entities, player=player,
                                           building_manager=building_manager, furniture_manager=furniture_manager):
                    AIMarketPurchasingSystem.deposit_materials_and_change_to_chest(carpenter, furniture_manager)
                    carpenter.say("Restocked Carpenter materials.", duration=2.0)
                    carpenter.task = "IDLE"
            else:
                home_x, home_y = carpenter._get_home_storage_dest(
                    permit_manager, building_manager, furniture_manager, all_entities=all_entities
                ) if permit_manager else (carpenter.x, carpenter.y)
                family = villager_manager.get_family_by_id(carpenter.family_id) if villager_manager else None
                home_permit_id = getattr(family, "assigned_permit_id", None)
                home_permit = next((p for p in getattr(permit_manager, "permits", [])
                                    if str(p.id) == str(home_permit_id)), None) if home_permit_id else None
                if home_permit:
                    home_building = next((b for b in getattr(building_manager, "buildings", [])
                                          if home_permit.overlaps_building(b)), None)
                    if home_building:
                        home_x, home_y = home_building.get_approach_point(
                            (carpenter.x, carpenter.y), TILE_SIZE, building_manager
                        )
                    else:
                        home_x = (home_permit.grid_x + home_permit.tiles_w / 2.0) * TILE_SIZE
                        home_y = (home_permit.grid_y + home_permit.tiles_h / 2.0) * TILE_SIZE
                if not carpenter._move_towards(
                    home_x, home_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                ):
                    return True
                active_order = next((f for f in furniture_manager.furnitures
                                     if f.construction_order
                                     and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)
                                     and f.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT")), None)
                material_targets = DEDICATED_JOBS.get("Carpenter", {}).get("material_stock_target", {})
                retained = {item: max(0, int(amount)) for item, amount in material_targets.items()}
                recipe = FURNITURE_TYPES.get(getattr(active_order, "furniture_type", ""), {})
                for material, amount in recipe.get("materials", {}).items():
                    retained[material] = max(retained.get(material, 0), int(amount))
                active_public_site = next((site for site in getattr(building_manager, "construction_sites", [])
                                           if getattr(site, "construction_order", None)
                                           and str(site.construction_order.get("carpenter_id")) == str(carpenter.id)
                                           and site.construction_order.get("order_type") == "PUBLIC_BUILD"
                                           and site.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING")), None)
                if active_public_site:
                    remaining_materials = {
                        material: max(0, int(amount) - int(active_public_site.delivered_cost.get(material, 0)))
                        for material, amount in active_public_site.required_cost.items()
                    }
                    for material, amount in remaining_materials.items():
                        retained[material] = max(retained.get(material, 0), amount)
                drop_tile = (int(home_x // TILE_SIZE), int(home_y // TILE_SIZE))
                for material in material_targets:
                    surplus = max(0, int(carpenter.inventory.get(material, 0)) - int(retained.get(material, 0)))
                    if surplus and stockpile_manager:
                        carpenter.inventory[material] -= surplus
                        if carpenter.inventory[material] <= 0:
                            carpenter.inventory.pop(material, None)
                        stockpile_manager.drop_resource(
                            material, surplus, *drop_tile,
                            owner_type="villager", owner_id=carpenter.family_id,
                        )
                carpenter.say("No household chest; surplus materials were left at home.", duration=2.5)
                carpenter.task = "IDLE"
            if carpenter.task == "IDLE":
                carpenter.target_restock_market = None
                carpenter.target_restock_mat = None
                carpenter.target_restock_qty = 0
                return False
            return True
        return False

    @classmethod
    def update_worker(cls, carpenter, dt, schedule_activity, building_manager, furniture_manager,
                      villager_manager, all_entities, player, day_cycle,
                      stockpile_manager=None, permit_manager=None):
        if getattr(carpenter, "job", None) != "Carpenter" or not furniture_manager:
            return False
        if carpenter.task.startswith("CARPENTER_RESTOCK_"):
            if cls._update_restock(carpenter, dt, building_manager, furniture_manager,
                                   villager_manager, all_entities, player,
                                   stockpile_manager, permit_manager):
                return True

        if schedule_activity in FREE_TIME_SCHEDULE_ACTIVITIES:
            work_orders = (
                list(getattr(furniture_manager, "furnitures", []))
                + list(getattr(building_manager, "construction_sites", []))
                + list(getattr(building_manager, "buildings", []))
            )
            has_commission_work = any(
                isinstance(getattr(subject, "construction_order", None), dict)
                and str(subject.construction_order.get("carpenter_id")) == str(carpenter.id)
                and subject.construction_order.get("status") in ("PAID", "BUILDING", "AWAITING_MATERIAL")
                for subject in work_orders
            )
            if not has_commission_work:
                _, stored_materials = cls._materials_in_storage(carpenter, furniture_manager)
                stock_targets = DEDICATED_JOBS.get("Carpenter", {}).get("material_stock_target", {})
                low_stock = {
                    material: max(0, int(target) - int(stored_materials.get(material, 0)))
                    for material, target in stock_targets.items()
                    if int(stored_materials.get(material, 0)) < int(target)
                }
                if low_stock and cls._begin_restock(
                        carpenter, low_stock, building_manager, furniture_manager, villager_manager):
                    carpenter.active_tool = None
                    return True

        landlord_payment = next((f for f in furniture_manager.furnitures
                                 if f.construction_order
                                 and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)
                                 and f.construction_order.get("payer_type") == "landlord"
                                 and f.construction_order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING")), None)
        if not landlord_payment:
            landlord_payment = next((building for building in getattr(building_manager, "buildings", [])
                                     if getattr(building, "construction_order", None)
                                     and str(building.construction_order.get("carpenter_id")) == str(carpenter.id)
                                     and building.construction_order.get("payer_type") == "landlord"
                                     and building.construction_order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING")), None)
        if landlord_payment:
            # The courier handles payment independently. Let the Carpenter
            # follow their normal schedule while the commission is in transit.
            carpenter.task = "IDLE"
            return False

        waiting_payment = next((f for f in furniture_manager.furnitures
                                if f.construction_order
                                and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)
                                and f.construction_order.get("payer_type") != "landlord"
                                and f.construction_order.get("status") in ("PAYMENT_REQUESTED", "PAYMENT_TRAVELING")), None)
        if waiting_payment:
            waiting_order = waiting_payment.construction_order
            expected_task = ("CARPENTER_FEE_RETRIEVE" if waiting_order.get("status") == "PAYMENT_REQUESTED"
                             else "CARPENTER_FEE_TRAVEL")
            payer = next((villager for villager in villager_manager.get_all_villagers()
                          if str(villager.id) == str(waiting_order.get("payer_id"))), None) if villager_manager else None
            pending_data = getattr(payer, "pending_commission_data", {}) if payer else {}
            from game.systems.commission_schedule import CommissionScheduleSystem
            pending_this_order = bool(payer and CommissionScheduleSystem.is_queued(
                payer, expected_task, "carpenter_payment_order_id", waiting_payment.id
            ))
            payment_task_active = bool(
                payer and getattr(payer, "is_alive", True) and (
                    (getattr(payer, "task", None) == expected_task
                     and str(getattr(payer, "carpenter_payment_order_id", None)) == str(waiting_payment.id))
                    or pending_this_order
                    or (getattr(payer, "pending_commission_task", None) == expected_task
                        and str(pending_data.get("carpenter_payment_order_id")) == str(waiting_payment.id))
                )
            )
            if not payment_task_active:
                waiting_order["status"] = "AWAITING_PAYMENT"
                waiting_order["payer_id"] = None
                if payer and str(getattr(payer, "carpenter_payment_order_id", None)) == str(waiting_payment.id):
                    payer.carpenter_payment_order_id = None
                    payer.carpenter_payment_carpenter_id = None
                    payer._resume_or_idle_after_need()
            else:
                # A household representative is already handling the payment;
                # waiting for them must not freeze the Carpenter's other activities.
                carpenter.task = "IDLE"
                return False

        public_sites = list(getattr(building_manager, "construction_sites", []))
        public_site = next((site for site in public_sites
                            if (getattr(site, "construction_order", None) or {}).get("order_type") == "PUBLIC_BUILD"
                            and str(site.construction_order.get("carpenter_id")) == str(carpenter.id)
                            and site.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING")), None)
        if public_site:
            order = public_site.construction_order
            if order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING"):
                carpenter.task = "IDLE"
                return False
            if order.get("status") in ("PAID", "AWAITING_MATERIAL", "BUILDING"):
                carpenter.task = "CARPENTER_CONSTRUCTING"
                if not public_site.is_materials_complete():
                    chest, totals = cls._materials_in_storage(carpenter, furniture_manager)
                    remaining = {
                        material: max(0, int(required) - int(public_site.delivered_cost.get(material, 0)))
                        for material, required in public_site.required_cost.items()
                    }
                    available = {
                        material: min(amount, max(0, int(totals.get(material, 0))))
                        for material, amount in remaining.items()
                        if amount > 0 and int(totals.get(material, 0)) > 0
                    }
                    if available:
                        if not cls._commit_materials_from_storage(carpenter, chest, available):
                            carpenter.say("I am still gathering the building materials.", duration=2.5)
                            return True
                        for material, amount in available.items():
                            public_site.deposit_resource(material, amount)
                        remaining = {
                            material: max(0, int(required) - int(public_site.delivered_cost.get(material, 0)))
                            for material, required in public_site.required_cost.items()
                        }
                    if any(remaining.values()):
                        order["status"] = "AWAITING_MATERIAL"
                        missing = {material: amount for material, amount in remaining.items() if amount > 0}
                        if cls._begin_restock(carpenter, missing, building_manager,
                                              furniture_manager, villager_manager):
                            return True
                        carpenter.say("I need building materials, but none are available to buy right now.", duration=2.5)
                        return True
                    order["materials_committed"] = True
                wx, wy = public_site.get_center_world(TILE_SIZE)
                if cls._within_furniture_work_range(carpenter, public_site):
                    arrived = True
                else:
                    arrived = carpenter._move_towards(
                        wx, wy, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                        all_entities=all_entities, player=player,
                        building_manager=building_manager, furniture_manager=furniture_manager,
                    )
                if arrived:
                    order["status"] = "BUILDING"
                    public_site.build_progress += dt
                    duration = max(1.0, float(order.get("build_duration_seconds", 1.0)))
                    order["progress_ratio"] = min(1.0, public_site.build_progress / duration)
                    if public_site.is_complete():
                        order["status"] = "COMPLETE"
                        order["progress_ratio"] = 1.0
                        carpenter.task = "IDLE"
                        carpenter.say(f"Finished {public_site.name}.", duration=3.0)
                return True

        public_repair = next((building for building in getattr(building_manager, "buildings", [])
                              if getattr(building, "construction_order", None)
                              and building.construction_order.get("order_type") == "REPAIR"
                              and building.construction_order.get("commission_paid") is True
                              and str(building.construction_order.get("carpenter_id")) == str(carpenter.id)
                              and building.construction_order.get("status") in ("PAID", "BUILDING")), None)
        if public_repair:
            order = public_repair.construction_order
            if order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING"):
                carpenter.task = "IDLE"
                return False
            carpenter.task = "CARPENTER_REPAIRING"
            wx, wy = public_repair.get_center_world(TILE_SIZE)
            arrived = math.hypot(carpenter.x - wx, carpenter.y - wy) <= INTERACTION_CONTACT_RADIUS
            if not arrived:
                arrived = carpenter._move_towards(
                    wx, wy, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                )
            if arrived:
                order["status"] = "BUILDING"
                public_repair.construction_progress = getattr(public_repair, "construction_progress", 0.0) + dt
                duration = max(1.0, float(order.get("build_duration_seconds", CARPENTER_BUILD_DURATION_INGAME_HOURS)))
                order["progress_ratio"] = min(1.0, public_repair.construction_progress / duration)
                if public_repair.construction_progress >= duration:
                    public_repair.condition = 1.0
                    order["status"] = "COMPLETE"
                    order["progress_ratio"] = 1.0
                    carpenter.task = "IDLE"
                    carpenter.say(f"Repaired {public_repair.name}.", duration=3.0)
            return True

        active = next((f for f in furniture_manager.furnitures
                       if f.construction_order
                       and f.construction_order.get("commission_paid") is True
                       and f.construction_order.get("status") in ("PAID", "BUILDING")
                       and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)), None)
        if not active:
            # Commission requests are errands for the household, not Carpenter
            # work. Discover and queue them regardless of the Carpenter's shift;
            # CommissionScheduleSystem runs the payer during that household's free time.
            awaiting_orders = [f for f in furniture_manager.furnitures
                               if f.construction_order
                               and f.construction_order.get("status") == "AWAITING_PAYMENT"
                               and f.construction_order.get("carpenter_id") in (None, str(carpenter.id))]
            active = next((f for f in awaiting_orders
                           if str(f.construction_order.get("payer_family_id")) == str(carpenter.family_id)), None)
            if active is None:
                for candidate in awaiting_orders:
                    payer_family_id = candidate.construction_order.get("payer_family_id")
                    household_carpenter = next((worker for worker in villager_manager.get_all_villagers()
                                                if getattr(worker, "job", None) == "Carpenter"
                                                and getattr(worker, "is_alive", True)
                                                and str(getattr(worker, "family_id", "")) == str(payer_family_id)), None) if villager_manager else None
                    if household_carpenter and str(household_carpenter.id) != str(carpenter.id):
                        continue
                    active = candidate
                    break
            if active:
                active.construction_order["carpenter_id"] = str(carpenter.id)
                if not cls._assign_payment(active, villager_manager, furniture_manager):
                    if not getattr(carpenter, "speech_text", None):
                        carpenter.say("Waiting for the household commission.", duration=2.5)
                    carpenter.task = "IDLE"
                    return False
                order_status = active.construction_order.get("status")
                if order_status == "LANDLORD_PAYMENT_PENDING":
                    from game.systems.commission_schedule import CommissionScheduleSystem
                    CommissionScheduleSystem.queue(
                        carpenter, "CARPENTER_FEE_LANDLORD_RETRIEVE",
                        carpenter_payment_order_id=active.id,
                        carpenter_payment_carpenter_id=carpenter.id,
                    )
                    carpenter.task = "IDLE"
                    return False
                carpenter.say("Commission requested from the household.", duration=2.0)
                carpenter.task = "IDLE"
                return False
        if not active:
            return False

        order = active.construction_order
        order["carpenter_id"] = str(carpenter.id)
        if order.get("status") not in ("PAID", "BUILDING"):
            return True

        cfg = DEDICATED_JOBS.get("Carpenter", {})
        chest, totals = cls._materials_in_storage(carpenter, furniture_manager)
        target_stock = cfg.get("material_stock_target", {}) if chest else {}
        is_repair = order.get("order_type") == "REPAIR"
        recipe = {} if is_repair else FURNITURE_TYPES.get(active.furniture_type, {})
        required = {item: max(0, int(amount))
                    for item, amount in recipe.get("materials", {}).items() if int(amount) > 0}
        missing = {} if is_repair else {item: max(0, int(target) - int(totals.get(item, 0)))
                   for item, target in target_stock.items()
                   if totals.get(item, 0) < target}
        short_recipe = {item: amount - int(totals.get(item, 0)) for item, amount in required.items()
                        if totals.get(item, 0) < amount}
        if short_recipe:
            missing.update({item: max(missing.get(item, 0), amount) for item, amount in short_recipe.items()})
        if missing and cls._begin_restock(carpenter, missing, building_manager, furniture_manager, villager_manager):
            return True
        if short_recipe:
            carpenter.say("I need this furniture's materials, but none are available to buy right now.", duration=2.5)
            return True

        if not order.get("materials_committed"):
            if not cls._commit_materials_from_storage(carpenter, chest, required):
                carpenter.say("I am still gathering this furniture's materials.", duration=2.5)
                return True
            order["materials_committed"] = True
            order["status"] = "BUILDING"

        carpenter.task = "CARPENTER_REPAIRING" if is_repair else "CARPENTER_CONSTRUCTING"
        carpenter.active_tool = None if is_repair else "Saw"
        if str(getattr(carpenter, "carpenter_target_order_id", None)) != str(active.id):
            carpenter.carpenter_target_order_id = str(active.id)
            carpenter.carpenter_failed_approach_points = set()
            carpenter.carpenter_target_position = active.get_approach_point(
                carpenter.x, carpenter.y, worker_id=carpenter.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
        target = carpenter.carpenter_target_position
        arrived = cls._within_furniture_work_range(carpenter, active)
        if arrived:
            carpenter.is_moving = False
            carpenter.current_path = []
            carpenter.path_index = 0
            carpenter.path_target = None
        else:
            arrived = carpenter._move_towards(target[0], target[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                              all_entities=all_entities, player=player,
                                              building_manager=building_manager, furniture_manager=furniture_manager)
        if not arrived and getattr(carpenter, "route_state", None) == ROUTE_STATE_FAILED:
            previous_target = tuple(target)
            failed_points = getattr(carpenter, "carpenter_failed_approach_points", set())
            failed_points.add(previous_target)
            carpenter.carpenter_failed_approach_points = failed_points
            alternate = active.get_approach_point(
                carpenter.x, carpenter.y, worker_id=carpenter.id,
                all_entities=all_entities, tile_size=TILE_SIZE,
                bm=building_manager, excluded_points=failed_points,
            )
            if alternate is None:
                center = active.get_world_pos(TILE_SIZE)
                if tuple(center) not in failed_points:
                    alternate = center
                elif not getattr(carpenter, "speech_text", None):
                    carpenter.say(f"I cannot reach {active.name}; the route is blocked.", duration=3.0)
            if alternate is not None and tuple(alternate) not in failed_points:
                carpenter.carpenter_target_position = alternate
                carpenter.path_target = None
                carpenter.current_path = []
                carpenter.path_index = 0
                carpenter.path_retry_timer = 0.0
        if arrived:
            day_seconds = day_cycle.day_length_seconds if day_cycle else DAY_LENGTH_OPTIONS[DEFAULT_DAY_LENGTH_INDEX]["seconds"]
            seconds_per_hour = day_seconds / 24
            duration = seconds_per_hour * CARPENTER_BUILD_DURATION_INGAME_HOURS
            active.construction_progress += dt
            order["progress_ratio"] = min(1.0, active.construction_progress / max(1.0, duration))
            if active.construction_progress >= duration:
                order["status"] = "COMPLETE"
                order["progress_ratio"] = 1.0
                if is_repair:
                    active.condition = 1.0
                carpenter.task = "IDLE"
                carpenter.active_tool = None
                carpenter.carpenter_payment_order_id = None
                carpenter.carpenter_target_order_id = None
                carpenter.carpenter_target_position = None
                carpenter.carpenter_failed_approach_points = set()
                carpenter.say(f"Repaired {active.name}." if is_repair else f"Finished {active.name}.", duration=3.0)
                furniture_manager.invalidate_cache()
        return True
