"""Furniture orders, household commissions, Carpenter materials, and construction."""

import math

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
    MARKET_TRADEABLE_ITEMS,
    ROUTE_STATE_FAILED,
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
        markets = MarketService.get_all_markets(building_manager)
        material_cost = 0
        for material, amount in cfg.get("materials", {}).items():
            amount = max(0, int(amount))
            if not amount:
                continue
            _, available_price = MarketService.get_lowest_available_item_quote(
                material, markets=markets, minimum_stock=amount
            )
            unit_price = available_price if available_price is not None else MarketService.get_item_price(material)
            material_cost += amount * unit_price
        carpenter_family = None
        if villager_manager:
            carpenters = [v for v in villager_manager.get_all_villagers() if getattr(v, "job", None) == "Carpenter" and getattr(v, "is_alive", True)]
            if carpenters:
                carpenter_family = villager_manager.get_family_by_id(carpenters[0].family_id)
        workers_supported = len([m for m in getattr(carpenter_family, "members", []) if getattr(m, "is_alive", True)]) if carpenter_family else 1
        living_household_size = max(CARPENTER_DEFAULT_LIVING_HOUSEHOLD_SIZE, workers_supported)
        daily_food_quantity = DAILY_FOOD_REQUIREMENT * living_household_size
        food_unit_price = cls._food_unit_price(markets, minimum_stock=daily_food_quantity)
        living_wage = food_unit_price * daily_food_quantity
        return {
            "material_cost_copper": material_cost,
            "living_wage_copper": living_wage,
            "price_copper": material_cost + living_wage,
            "food_unit_price_at_order": food_unit_price,
        }

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
    def create_repair_order(cls, furniture, building_manager=None, villager_manager=None):
        markets = MarketService.get_all_markets(building_manager)
        food_unit_price = cls._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT)
        repair_price = food_unit_price * DAILY_FOOD_REQUIREMENT * CARPENTER_REPAIR_FOOD_DAYS
        return {
            "id": str(furniture.id),
            "order_type": "REPAIR",
            "status": "AWAITING_PAYMENT",
            "payer_family_id": furniture.family_id,
            "payer_id": None,
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
                if not cls._move_exact_value(chest.inventory, carpenter.inventory, fee):
                    order["status"] = "AWAITING_PAYMENT"
                    return False
                order["status"] = "PAID"
                order["commission_paid"] = True
                order["paid_by_id"] = str(payer.id)
                order["paid_by_family_id"] = str(family_id)
                order["paid_amount_copper"] = fee
                carpenter.say(f"I paid the furniture commission from our household chest ({fee} Copper).", duration=2.5)
                return True
            order["payer_id"] = str(payer.id)
            order["status"] = "PAYMENT_REQUESTED"
            payer.interrupt_task("CARPENTER_COMMISSION", activity_label="Delivering a furniture commission")
            payer.carpenter_payment_order_id = order["id"]
            payer.carpenter_payment_carpenter_id = order.get("carpenter_id")
            payer.task = "CARPENTER_FEE_RETRIEVE"
            payer.say("I am bringing the household furniture commission to the Carpenter.", duration=2.5)
            return True
        order["status"] = "LANDLORD_PAYMENT_PENDING"
        return True

    @classmethod
    def update_payment_task(cls, villager, dt, building_manager, furniture_manager,
                            stockpile_manager, all_entities, player, villager_manager=None):
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
        carpenter = next((e for e in all_entities if str(getattr(e, "id", "")) == str(order.get("carpenter_id"))), None)
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
                    villager.say("Furniture commission paid.", duration=2.0)
                    carpenter.say(f"Commission received: {fee} Copper. I will begin the order.", duration=2.5)
                else:
                    order["status"] = "AWAITING_PAYMENT"
                    villager.say("I no longer have the full furniture commission.", duration=2.5)
                villager.carpenter_payment_order_id = None
                villager.carpenter_payment_carpenter_id = None
                villager._resume_or_idle_after_need()
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
                recipe = FURNITURE_TYPES.get(getattr(active_order, "furniture_type", ""), {})
                retained = recipe.get("materials", {})
                drop_tile = (int(home_x // TILE_SIZE), int(home_y // TILE_SIZE))
                material_targets = DEDICATED_JOBS.get("Carpenter", {}).get("material_stock_target", {})
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

        waiting_payment = next((f for f in furniture_manager.furnitures
                                if f.construction_order
                                and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)
                                and f.construction_order.get("status") in ("PAYMENT_REQUESTED", "PAYMENT_TRAVELING")), None)
        if waiting_payment:
            waiting_order = waiting_payment.construction_order
            expected_task = ("CARPENTER_FEE_RETRIEVE" if waiting_order.get("status") == "PAYMENT_REQUESTED"
                             else "CARPENTER_FEE_TRAVEL")
            payer = next((villager for villager in villager_manager.get_all_villagers()
                          if str(villager.id) == str(waiting_order.get("payer_id"))), None) if villager_manager else None
            payment_task_active = (
                payer and getattr(payer, "is_alive", True)
                and getattr(payer, "task", None) == expected_task
                and str(getattr(payer, "carpenter_payment_order_id", None)) == str(waiting_payment.id)
            )
            if not payment_task_active:
                waiting_order["status"] = "AWAITING_PAYMENT"
                waiting_order["payer_id"] = None
                if payer and str(getattr(payer, "carpenter_payment_order_id", None)) == str(waiting_payment.id):
                    payer.carpenter_payment_order_id = None
                    payer.carpenter_payment_carpenter_id = None
                    payer._resume_or_idle_after_need()
            else:
                carpenter.task = "WAITING_FOR_CARPENTER_COMMISSION"
                return True

        active = next((f for f in furniture_manager.furnitures
                       if f.construction_order and f.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT", "PAYMENT_REQUESTED", "PAYMENT_TRAVELING", "LANDLORD_PAYMENT_PENDING")
                       and str(f.construction_order.get("carpenter_id")) == str(carpenter.id)), None)
        if not active and schedule_activity not in ("WORK", "ANY"):
            return False
        if not active:
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
                    carpenter.say("Waiting for the household commission.", duration=2.5)
                    return True
                order_status = active.construction_order.get("status")
                if order_status == "LANDLORD_PAYMENT_PENDING":
                    carpenter.carpenter_payment_order_id = active.id
                    carpenter.task = "CARPENTER_FEE_LANDLORD_RETRIEVE"
                    return True
                carpenter.say("Commission requested from the household.", duration=2.0)
                return True
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
            for item, amount in required.items():
                if not amount:
                    continue
                from_inventory = min(carpenter.inventory.get(item, 0), amount)
                carpenter.inventory[item] = carpenter.inventory.get(item, 0) - from_inventory
                if not carpenter.inventory[item]:
                    carpenter.inventory.pop(item, None)
                remaining = amount - from_inventory
                if remaining and chest:
                    chest.inventory[item] = max(0, chest.inventory.get(item, 0) - remaining)
                    if not chest.inventory[item]:
                        chest.inventory.pop(item, None)
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
