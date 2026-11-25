"""Furniture orders, household commissions, Builder materials, and construction."""

import math
import random
import time

from game.data.config import (
    BUILDER_BUILD_DURATION_INGAME_HOURS,
    BUILDER_DEFAULT_LIVING_HOUSEHOLD_SIZE,
    BUILDER_REPAIR_MATERIALS,
    BUILDER_REPAIR_FOOD_DAYS,
    DAILY_FOOD_REQUIREMENT,
    DAY_LENGTH_OPTIONS,
    DEFAULT_DAY_LENGTH_INDEX,
    DEFAULT_ITEM_PRICES,
    DEDICATED_JOBS,
    FURNITURE_TYPES,
    BUILDING_TYPES,
    MARKET_TRADEABLE_ITEMS,
    ROUTE_STATE_FAILED,
    BUILDER_INSUFFICIENT_LANDLORD_COIN_MESSAGES,
    COMMISSION_CLAIM_RETRY_SECONDS,
    DEFAULT_COMMISSION_ARTISAN_JOB,
    PRODUCTION_BUILDER_CRAFT_HOURS,
)
from game.systems.work.production_system import ProductionSystem
from game.systems.economy.currency import (
    CURRENCY_DENOMINATIONS,
    canonical_denomination,
    compact_currency_wallet,
    from_copper,
    normalize_wallet,
    to_copper,
    transfer_currency_value,
)
from game.systems.economy.market_service import MarketService
from game.config import TILE_SIZE, CHEST_INTERACTION_RADIUS, INTERACTION_CONTACT_RADIUS, LOOSE_ITEM_ARRIVAL_DIST
from game.world.navigation.navigation import distance_to_object


class BuilderSystem:
    # Monotonic FIFO floor: guarantees paid_seq stays unique even when a
    # partial subject scan (e.g. furniture-only) can't see every order.
    _paid_seq_floor = 0

    @classmethod
    def request_public_commission(cls, subject, resources, servant_manager,
                                  villager_manager, building_manager, day_cycle=None,
                                  stockpile_manager=None, furniture_manager=None):
        """Dispatch a servant to collect a public commission from the Lord's Treasury Chest."""
        order = getattr(subject, "construction_order", None)
        if hasattr(subject, "building_type"):
            cfg = BUILDING_TYPES.get(subject.building_type, {})
            if not cfg.get("builder_commissionable"):
                return False, "This public structure is not configured for a builder commission."
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
                return False, "This furniture has no builder order."
            if order.get("order_type") != "REPAIR":
                order.update(cls.quote_order(subject.furniture_type, building_manager, villager_manager))
            order["payer_family_id"] = None
        if not isinstance(order, dict):
            return False, "This blueprint has no builder order."
        if order.get("status") not in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"):
            return False, "This builder commission is already being handled."
        artisan_job = cls._artisan_job(order)
        builders = [v for v in villager_manager.get_all_villagers()
                      if getattr(v, "job", None) == artisan_job and getattr(v, "is_alive", True)] if villager_manager else []
        if not builders:
            return False, f"No {artisan_job} is available for this commission."
        # Queue model: a builder may hold MANY commissions — new orders join
        # his FIFO queue. Assign to the builder with the SHORTEST queue
        # (like market stall choice: workload beats distance).
        servants = [s for s in getattr(servant_manager, "servants", [])
                    if getattr(s, "state", "IDLE") == "IDLE"] if servant_manager else []
        fee = max(0, int(order.get("price_copper", 0)))
        from game.systems.economy.lord_treasury import LordTreasurySystem
        from game.systems.village_life.cemetery_system import CemeterySystem
        from game.systems.economy.currency import canonical_denomination, to_copper

        if hasattr(subject, "get_world_pos"):
            target_x, target_y = subject.get_world_pos(TILE_SIZE)
        elif hasattr(subject, "get_center_world"):
            target_x, target_y = subject.get_center_world(TILE_SIZE)
        else:
            target_x = (subject.grid_x + getattr(subject, "tiles_w", 1) / 2.0) * TILE_SIZE
            target_y = (subject.grid_y + getattr(subject, "tiles_h", 1) / 2.0) * TILE_SIZE

        builder = min(
            builders,
            key=lambda worker: (
                cls._queue_length(worker.id, furniture_manager, building_manager),
                math.hypot(worker.x - target_x, worker.y - target_y),
            ),
        )

        treasury = LordTreasurySystem.get_chest(furniture_manager)
        treasury_val = LordTreasurySystem.value(furniture_manager) if treasury else 0
        landlord_stacks = CemeterySystem._landlord_coin_stacks(stockpile_manager) if stockpile_manager else []
        stockpile_val = sum(to_copper({canonical_denomination(s.resource_type): s.amount})
                            for s in landlord_stacks if canonical_denomination(s.resource_type))
        total_landlord_funds = treasury_val + stockpile_val

        if total_landlord_funds < fee:
            if order.get("order_type") == "REPAIR" and hasattr(subject, "building_type"):
                # Emergency civic repair: public structure needs repair to keep town functional.
                order["status"] = "PAID"
                order["commission_paid"] = True
                order["paid_by_id"] = "landlord"
                order["paid_amount_copper"] = 0
                order["builder_id"] = str(builder.id)
                order["builder_family_id"] = str(getattr(builder, "family_id", "") or "")
                cls._ensure_paid_seq(order, furniture_manager, building_manager)
                if not getattr(builder, "speech_text", None):
                    builder.say(f"Emergency public repair: {getattr(subject, 'name', 'structure')}.", duration=2.5)
                return True, "Emergency civic repair order dispatched."
            message = random.choice(BUILDER_INSUFFICIENT_LANDLORD_COIN_MESSAGES)
            if servant_manager and getattr(servant_manager, "servants", None):
                servant_manager.servants[0].say(message, duration=3.5)
            return False, message
        if not servants:
            return False, "No idle servant is available to carry the commission."

        if treasury and treasury_val >= fee:
            ref_x = (treasury.grid_x + 0.5) * TILE_SIZE
            ref_y = (treasury.grid_y + 0.5) * TILE_SIZE
            storage_tile = [treasury.grid_x, treasury.grid_y]
            treasury_id = str(treasury.id)
        elif landlord_stacks:
            first_stack = landlord_stacks[0]
            ref_x = (first_stack.grid_x + 0.5) * TILE_SIZE
            ref_y = (first_stack.grid_y + 0.5) * TILE_SIZE
            storage_tile = [first_stack.grid_x, first_stack.grid_y]
            treasury_id = None
        else:
            ref_x, ref_y = target_x, target_y
            storage_tile = [int(target_x // TILE_SIZE), int(target_y // TILE_SIZE)]
            treasury_id = None

        servant = min(
            servants,
            key=lambda worker: math.hypot(ref_x - worker.x, ref_y - worker.y),
        )

        order["status"] = "LANDLORD_RETRIEVING"
        order["payer_type"] = "landlord"
        order["payer_id"] = "landlord"
        order["builder_id"] = str(builder.id)
        order["builder_family_id"] = str(getattr(builder, "family_id", "") or "")
        order["artisan_job"] = artisan_job
        order["commission_paid"] = False
        if day_cycle:
            seconds_per_hour = max(1.0, float(day_cycle.day_length_seconds)) / 24.0
            order["build_duration_seconds"] = seconds_per_hour * BUILDER_BUILD_DURATION_INGAME_HOURS
        servant.builder_commission_order_id = str(order.get("id"))
        servant.builder_commission_builder_id = str(builder.id)
        servant.builder_commission_fee_copper = fee
        servant.builder_commission_remaining_copper = fee
        servant.builder_commission_storage_tile = [treasury.grid_x, treasury.grid_y]
        servant.builder_commission_treasury_id = str(treasury.id)
        servant.state = "BUILDER_COMMISSION_RETRIEVE"
        servant.say("I am retrieving the commission from the Lord's Treasury Chest, my Lord.", duration=2.5)
        return True, "A servant is retrieving coins from the Lord's Treasury Chest."

    @classmethod
    def dispatch_pending_public_commissions(cls, building_manager, servant_manager,
                                            villager_manager, furniture_manager,
                                            day_cycle=None, stockpile_manager=None):
        """Automatically start landlord-paid Builder orders for eligible public blueprints."""
        if not building_manager or not servant_manager or not villager_manager:
            return 0
        from game.systems.economy.lord_treasury import LordTreasurySystem
        from game.systems.village_life.cemetery_system import CemeterySystem
        from game.systems.economy.currency import canonical_denomination, to_copper

        treasury = LordTreasurySystem.get_chest(furniture_manager)
        treasury_val = LordTreasurySystem.value(furniture_manager) if treasury else 0
        landlord_stacks = CemeterySystem._landlord_coin_stacks(stockpile_manager) if stockpile_manager else []
        stockpile_val = sum(to_copper({canonical_denomination(s.resource_type): s.amount})
                            for s in landlord_stacks if canonical_denomination(s.resource_type))
        total_landlord_funds = treasury_val + stockpile_val

        started = 0
        candidates = []
        for site in getattr(building_manager, "construction_sites", []):
            cfg = BUILDING_TYPES.get(getattr(site, "building_type", ""), {})
            if cfg.get("builder_commissionable"):
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
        for furniture in getattr(furniture_manager, "furnitures", []):
            for subject in (getattr(furniture, "tool_order_subjects", None) or []):
                order = getattr(subject, "construction_order", None)
                if isinstance(order, dict) and order.get("payer_type") == "landlord":
                    candidates.append(subject)
        for site in candidates:
            order = getattr(site, "construction_order", None) or {}
            if order.get("status") not in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"):
                continue
            if "price_copper" not in order:
                order.update(cls.quote_building_order(
                    getattr(site, "building_type", "wooden_structure"), building_manager, villager_manager,
                    tile_count=len(getattr(site, "tiles", ())),
                ))
            fee = max(0, int(order.get("price_copper", 0)))
            if total_landlord_funds < fee:
                if order.get("order_type") == "REPAIR" and hasattr(site, "building_type"):
                    # Emergency civic repair for public structure (e.g. toilet, well)
                    artisan_job = cls._artisan_job(order)
                    builders = [v for v in villager_manager.get_all_villagers()
                                if getattr(v, "job", None) == artisan_job and getattr(v, "is_alive", True)]
                    if builders:
                        if hasattr(site, "get_center_world"):
                            tx, ty = site.get_center_world(TILE_SIZE)
                        else:
                            tx = (site.grid_x + getattr(site, "tiles_w", 1) / 2.0) * TILE_SIZE
                            ty = (site.grid_y + getattr(site, "tiles_h", 1) / 2.0) * TILE_SIZE
                        builder = min(
                            builders,
                            key=lambda worker: (
                                cls._queue_length(worker.id, furniture_manager, building_manager),
                                math.hypot(worker.x - tx, worker.y - ty),
                            ),
                        )
                        order["status"] = "PAID"
                        order["commission_paid"] = True
                        order["paid_by_id"] = "landlord"
                        order["paid_amount_copper"] = 0
                        order["builder_id"] = str(builder.id)
                        order["builder_family_id"] = str(getattr(builder, "family_id", "") or "")
                        cls._ensure_paid_seq(order, furniture_manager, building_manager)
                        if not getattr(builder, "speech_text", None):
                            builder.say(f"Emergency public repair: {getattr(site, 'name', 'structure')}.", duration=2.5)
                        started += 1
                        continue
                idle_servant = next((servant for servant in getattr(servant_manager, "servants", [])
                                     if getattr(servant, "state", "IDLE") == "IDLE"), None)
                if idle_servant and not order.get("insufficient_coin_notice_sent"):
                    idle_servant.say(random.choice(BUILDER_INSUFFICIENT_LANDLORD_COIN_MESSAGES), duration=3.5)
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
        from game.systems.economy.lord_treasury import LordTreasurySystem
        refunded_to_treasury = LordTreasurySystem.deposit_all(furniture_manager, servant.inventory)
        if not refunded_to_treasury:
            tile = getattr(servant, "builder_commission_storage_tile", None)
            tile = tile or [int(servant.x // TILE_SIZE), int(servant.y // TILE_SIZE)]
            if stockpile_manager:
                for key in list(servant.inventory):
                    if canonical_denomination(key):
                        amount = max(0, int(servant.inventory.pop(key, 0)))
                        if amount:
                            stockpile_manager.drop_resource(key, amount, *tile, owner_type="landlord")
        servant.builder_commission_treasury_id = None
        servant.builder_commission_fee_copper = 0
        servant.builder_commission_remaining_copper = 0
        servant.builder_commission_storage_tile = None
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
        material_cost = cls._material_cost(materials, building_manager)
        builders = [v for v in villager_manager.get_all_villagers()
                      if getattr(v, "job", None) == "Builder" and getattr(v, "is_alive", True)] if villager_manager else []
        family = villager_manager.get_family_by_id(builders[0].family_id) if builders else None
        household_size = max(
            BUILDER_DEFAULT_LIVING_HOUSEHOLD_SIZE,
            len([m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)]) if family else 1,
        )
        markets = MarketService.get_all_markets(building_manager)
        food_unit_price = cls._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT * household_size)
        wage = food_unit_price * DAILY_FOOD_REQUIREMENT * household_size
        return {"material_cost_copper": material_cost, "living_wage_copper": wage,
                "price_copper": material_cost + wage, "materials": dict(materials),
                "food_unit_price_at_order": food_unit_price}

    @classmethod
    def _material_cost(cls, materials, building_manager=None):
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
        return material_cost

    @staticmethod
    def _distance_to_asset(asset, x, y):
        return distance_to_object(asset, x, y, TILE_SIZE)

    @classmethod
    def _within_asset_work_range(cls, builder, asset):
        return cls._distance_to_asset(asset, builder.x, builder.y) <= INTERACTION_CONTACT_RADIUS

    @classmethod
    def _asset_approach_arrival_distance(cls, asset, target_x, target_y):
        target_distance = cls._distance_to_asset(asset, target_x, target_y)
        return max(0.0, INTERACTION_CONTACT_RADIUS - target_distance)

    @staticmethod
    def _asset_approach_point(builder, asset, order, all_entities, building_manager):
        order_id = str(
            order.get("id")
            or getattr(asset, "id", None)
            or f"{getattr(asset, 'building_type', getattr(asset, 'furniture_type', 'asset'))}:"
               f"{getattr(asset, 'grid_x', 0)}:{getattr(asset, 'grid_y', 0)}"
        )
        if (str(getattr(builder, "builder_target_order_id", None)) != order_id
                or not getattr(builder, "builder_target_position", None)):
            builder.builder_target_order_id = order_id
            builder.builder_failed_approach_points = set()
            builder.builder_target_position = asset.get_approach_point(
                builder.x, builder.y, worker_id=builder.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
        return builder.builder_target_position

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
            "builder_id": None,
            "artisan_job": DEFAULT_COMMISSION_ARTISAN_JOB,
            "commission_paid": False,
        })
        return order

    @classmethod
    def create_repair_order(cls, asset, building_manager=None, villager_manager=None):
        markets = MarketService.get_all_markets(building_manager)
        food_unit_price = cls._food_unit_price(markets, minimum_stock=DAILY_FOOD_REQUIREMENT)
        materials = dict(BUILDER_REPAIR_MATERIALS)
        material_cost = cls._material_cost(materials, building_manager)
        living_wage = food_unit_price * DAILY_FOOD_REQUIREMENT * BUILDER_REPAIR_FOOD_DAYS
        repair_price = material_cost + living_wage
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
            "builder_id": None,
            "artisan_job": DEFAULT_COMMISSION_ARTISAN_JOB,
            "commission_paid": False,
            "materials": materials,
            "material_cost_copper": material_cost,
            "living_wage_copper": living_wage,
            "price_copper": repair_price,
            "food_unit_price_at_order": food_unit_price,
            "progress_ratio": 0.0,
        }

    @classmethod
    # ------------------------------------------------------------------
    # Commission queue helpers (FIFO by paid_seq; assignment by shortest queue)
    # ------------------------------------------------------------------
    @staticmethod
    def _artisan_job(order):
        """Job id the commissioned artisan must hold (config-driven default so
        orders without the field still route to Builders)."""
        return str((order or {}).get("artisan_job") or DEFAULT_COMMISSION_ARTISAN_JOB)

    @classmethod
    def _order_subjects(cls, furniture_manager=None, building_manager=None):
        subjects = []
        if furniture_manager:
            subjects.extend(getattr(furniture_manager, "furnitures", []))
            # Toolmaker tool orders live on workbenches as ToolOrderSubject
            # entries so they share the commission/payment/refund machinery.
            for f in getattr(furniture_manager, "furnitures", []):
                subjects.extend(getattr(f, "tool_order_subjects", None) or [])
        if building_manager:
            subjects.extend(getattr(building_manager, "construction_sites", []))
            subjects.extend(getattr(building_manager, "buildings", []))
        return subjects

    @classmethod
    def _find_subject_by_order_id(cls, order_id, furniture_manager=None, building_manager=None):
        for subject in cls._order_subjects(furniture_manager, building_manager):
            order = getattr(subject, "construction_order", None)
            if isinstance(order, dict) and str(order.get("id")) == str(order_id):
                return subject
        return None

    @classmethod
    def _ensure_paid_seq(cls, order, furniture_manager=None, building_manager=None):
        """Lazily stamp FIFO sequence when an order reaches PAID. Stamping at
        selection time keeps save/load safe: paid_seq persists on the order."""
        if not isinstance(order, dict) or "paid_seq" in order:
            return
        mx = cls._paid_seq_floor
        for subject in cls._order_subjects(furniture_manager, building_manager):
            o = getattr(subject, "construction_order", None)
            if isinstance(o, dict):
                mx = max(mx, int(o.get("paid_seq", 0) or 0))
        order["paid_seq"] = mx + 1
        cls._paid_seq_floor = order["paid_seq"]

    @classmethod
    def _queue_length(cls, builder_id, furniture_manager=None, building_manager=None):
        """Active commission slots held by a builder (payment-transit counts —
        the slot is already reserved even before the build starts)."""
        cid = str(builder_id)
        terminal = {"COMPLETE", "AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING"}
        return sum(
            1 for subject in cls._order_subjects(furniture_manager, building_manager)
            if isinstance(getattr(subject, "construction_order", None), dict)
            and str(subject.construction_order.get("builder_id")) == cid
            and subject.construction_order.get("status") not in terminal
        )

    @classmethod
    def _get_order(cls, furniture_manager, order_id, building_manager=None):
        return cls._find_subject_by_order_id(order_id, furniture_manager, building_manager)

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
    def _family_coin_stacks(cls, family_id, stockpile_manager):
        """Loose coin stacks owned by a household."""
        fam_str = str(family_id or "")
        if not stockpile_manager or not fam_str:
            return []
        return [s for s in getattr(stockpile_manager, "stacks", [])
                if getattr(s, "owner_type", None) == "villager"
                and str(getattr(s, "owner_id", "")) == fam_str
                and getattr(s, "amount", 0) > 0
                and canonical_denomination(getattr(s, "resource_type", ""))]

    @classmethod
    def _family_abstract_wallets(cls, family_id, villager_manager):
        """Abstract coin wallets a household can spend: family purse + member pockets.
        Member pockets are their carried inventories (coins only are counted)."""
        fam = villager_manager.get_family_by_id(family_id) if villager_manager and family_id is not None else None
        wallets = []
        if fam is not None:
            if isinstance(getattr(fam, "currency", None), dict):
                wallets.append(fam.currency)
            for m in getattr(fam, "members", []) or []:
                if getattr(m, "is_alive", True) and isinstance(getattr(m, "inventory", None), dict):
                    wallets.append(m.inventory)
        return wallets

    @classmethod
    def _family_coin_total_copper(cls, family_id, chest, stockpile_manager, villager_manager=None):
        """Total physical coin value a household can spend:
        - Household chest (if present)
        - Family loose ground coin stacks
        - Family purse (if no chest / homeless)
        - Living members' carried pocket coins
        """
        total = to_copper(normalize_wallet(getattr(chest, "inventory", {}) if chest else {}))
        for stack in cls._family_coin_stacks(family_id, stockpile_manager):
            total += to_copper({canonical_denomination(stack.resource_type): int(stack.amount)})
        if villager_manager and family_id is not None:
            fam = villager_manager.get_family_by_id(family_id)
            if fam is not None:
                if isinstance(getattr(fam, "currency", None), dict):
                    total += to_copper(normalize_wallet(fam.currency))
                for m in getattr(fam, "members", []) or []:
                    if getattr(m, "is_alive", True):
                        total += to_copper(normalize_wallet(getattr(m, "inventory", {})))
        return total

    @staticmethod
    def _member_fee_errand_active(member):
        """True while this villager is mid-flight or has a queued builder-fee
        payment errand (retrieve -> deliver -> PAID). ``builder_payment_order_id``
        is also set by refund-collection errands, which serializes the same way."""
        if member is None:
            return False
        if str(getattr(member, "task", "") or "").startswith("BUILDER_FEE_"):
            return True
        if getattr(member, "builder_payment_order_id", None) not in (None, ""):
            return True
        for entry in getattr(member, "pending_commission_tasks", []) or []:
            if isinstance(entry, dict) and str(entry.get("task", "") or "").startswith("BUILDER_FEE_"):
                return True
        legacy = getattr(member, "pending_commission_task", None)
        return bool(legacy) and str(legacy).startswith("BUILDER_FEE_")

    @classmethod
    def _family_fee_errand_active(cls, family):
        """True while any living member of the household is mid-flight (or has
        a queued) builder-commission payment errand.

        Serializes household commission payments per family: one errand runs
        to completion before the next pending order for the same family is
        scheduled. Payers of OTHER families are unaffected.
        """
        for member in getattr(family, "members", []) or []:
            if getattr(member, "is_alive", True) and cls._member_fee_errand_active(member):
                return True
        return False

    @classmethod
    def _assign_payment(cls, order_furniture, villager_manager, furniture_manager, stockpile_manager=None):
        order = order_furniture.construction_order
        family_id = order.get("payer_family_id")
        family = villager_manager.get_family_by_id(family_id) if family_id is not None and villager_manager else None
        survivors = [m for m in getattr(family, "members", []) if getattr(m, "is_alive", True)]
        if survivors:
            chest = furniture_manager.get_storage_for_family(family_id)
            fee = int(order["price_copper"])
            if cls._family_coin_total_copper(family_id, chest, stockpile_manager, villager_manager) < fee:
                order["status"] = "AWAITING_PAYMENT"
                return False
            # STRICT RULE: Exactly ONE representative per household may run a
            # commission payment errand at a time. Other orders for the same
            # family must wait until this errand physically completes.
            if cls._family_fee_errand_active(family):
                order["status"] = "AWAITING_PAYMENT"
                return False
            builder_id = str(order.get("builder_id"))
            available = [
                m for m in survivors
                if not cls._member_fee_errand_active(m)
                and getattr(m, "task", "") not in ("SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET", "RECOVER_DEATH_ITEMS")
                and getattr(m, "hunger", 100.0) > 20.0
                and getattr(m, "thirst", 100.0) > 20.0
                and getattr(m, "need_toilet", 100.0) > 20.0
            ]
            pool = available or [m for m in survivors if not cls._member_fee_errand_active(m)]
            if not pool:
                order["status"] = "AWAITING_PAYMENT"
                return False
            pref = order.get("payer_id")
            preferred_payer = next((m for m in pool if str(getattr(m, "id", "")) == str(pref)), None) if pref else None
            non_builder = [m for m in pool if str(getattr(m, "id", "")) != builder_id]
            payer = preferred_payer or (non_builder or pool)[0]
            order["payer_id"] = str(payer.id)
            carried_copper = to_copper(normalize_wallet(payer.inventory))
            from game.systems.work.commission_schedule import CommissionScheduleSystem
            if carried_copper >= fee:
                order["status"] = "PAYMENT_TRAVELING"
                CommissionScheduleSystem.queue(
                    payer, "BUILDER_FEE_TRAVEL",
                    builder_payment_order_id=order["id"],
                    builder_payment_builder_id=order.get("builder_id"),
                )
            else:
                order["status"] = "PAYMENT_REQUESTED"
                CommissionScheduleSystem.queue(
                    payer, "BUILDER_FEE_RETRIEVE",
                    builder_payment_order_id=order["id"],
                    builder_payment_builder_id=order.get("builder_id"),
                )
            return True
        order["status"] = "LANDLORD_PAYMENT_PENDING"
        return True

    @classmethod
    def _finalize_fee_payment(cls, villager, order, builder, fee, villager_manager, day_number):
        """Shared tail for BUILDER_FEE_RETRIEVE once coins are in hand."""
        if str(order.get("builder_id")) == str(villager.id):
            order["status"] = "PAID"
            order["commission_paid"] = True
            order["paid_by_id"] = str(villager.id)
            order["paid_by_family_id"] = str(villager.family_id)
            order["paid_amount_copper"] = fee
            cls._ensure_paid_seq(order, furniture_manager, building_manager)
            villager.builder_payment_order_id = None
            villager.builder_payment_builder_id = None
            villager.builder_fee_needed = None
            villager.task = "IDLE"
            villager.say(f"Commission paid from our household: {fee} Copper.", duration=2.5)
        else:
            order["status"] = "PAYMENT_TRAVELING"
            villager.task = "BUILDER_FEE_TRAVEL"

    @classmethod
    def update_payment_task(cls, villager, dt, building_manager, furniture_manager,
                            stockpile_manager, all_entities, player, villager_manager=None,
                            day_number=1):
        task = getattr(villager, "task", "")
        if task == "COMMISSION_REFUND_COLLECT":
            return cls._update_refund_task(
                villager, dt, building_manager, furniture_manager,
                stockpile_manager, all_entities, player, villager_manager)
        if task not in ("BUILDER_FEE_RETRIEVE", "BUILDER_FEE_TRAVEL", "BUILDER_FEE_LANDLORD_RETRIEVE"):
            return False
        order_furniture = cls._get_order(furniture_manager, getattr(villager, "builder_payment_order_id", None), building_manager)
        if not order_furniture:
            villager.builder_payment_order_id = None
            villager.builder_payment_builder_id = None
            villager._resume_or_idle_after_need()
            return True
        order = order_furniture.construction_order
        if task == "BUILDER_FEE_LANDLORD_RETRIEVE":
            # Landlord storage is servant-only: the Builder must never
            # withdraw from the Lord's Treasury or landlord stacks himself.
            # Hand the order back to the public commission dispatcher, which
            # sends a servant to fetch the fee instead.
            order["status"] = "LANDLORD_PAYMENT_PENDING"
            order["payer_type"] = "landlord"
            order["payer_id"] = "landlord"
            villager.builder_payment_order_id = None
            villager.builder_payment_builder_id = None
            villager.task = "IDLE"
            villager._resume_or_idle_after_need()
            return True
        builder = (
            all_entities.by_id(order.get("builder_id"))
            if hasattr(all_entities, "by_id")
            else next((e for e in all_entities if str(getattr(e, "id", "")) == str(order.get("builder_id"))), None)
        )
        fee = max(0, int(order.get("price_copper", 0)))

        if task == "BUILDER_FEE_RETRIEVE":
            chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
            chest_covers = chest and to_copper(normalize_wallet(chest.inventory)) >= fee
            coin_stacks = cls._family_coin_stacks(villager.family_id, stockpile_manager)
            stack_total = sum(
                to_copper({canonical_denomination(s.resource_type): int(s.amount)})
                for s in coin_stacks
            )
            wallet_total = sum(
                to_copper(normalize_wallet(w))
                for w in cls._family_abstract_wallets(villager.family_id, villager_manager)
            )
            # Coins already collected into this payer's pockets count toward
            # the fee — otherwise draining the coin stacks aborts the payment
            # and strands the coins in the villager's inventory.
            carried_copper = to_copper(normalize_wallet(villager.inventory))
            if carried_copper >= fee:
                cls._finalize_fee_payment(villager, order, builder, fee, villager_manager, day_number)
                return True
            if not chest_covers and carried_copper + stack_total + wallet_total < fee:
                order["status"] = "AWAITING_PAYMENT"
                villager.builder_payment_order_id = None
                villager.builder_fee_needed = None
                villager._resume_or_idle_after_need()
                return True
            if chest_covers:
                pos = chest.get_approach_point(villager.x, villager.y, worker_id=villager.id,
                                               all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager)
                arrived = villager._move_towards(pos[0], pos[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                                 all_entities=all_entities, player=player,
                                                 building_manager=building_manager, furniture_manager=furniture_manager,
                                                 interaction_target=chest)
                if arrived:
                    if cls._move_exact_value(chest.inventory, villager.inventory, fee):
                        cls._finalize_fee_payment(villager, order, builder, fee, villager_manager, day_number)
                    else:
                        order["status"] = "AWAITING_PAYMENT"
                        villager.say("Our household does not have enough coins for this furniture order.", duration=3.0)
                        villager.builder_payment_order_id = None
                        villager.builder_fee_needed = None
                        villager._resume_or_idle_after_need()
                return True

            # No chest (or chest can't cover): collect coins from loose household
            # stacks. Any denomination is acceptable as long as total value
            # covers the remaining fee.
            carried = carried_copper
            still_needed_copper = max(0, fee - carried)
            if still_needed_copper <= 0:
                cls._finalize_fee_payment(villager, order, builder, fee, villager_manager, day_number)
                return True
            # If household is homeless / has no chest, physical purse at home:
            if not chest and villager_manager and villager.family_id is not None:
                fam = villager_manager.get_family_by_id(villager.family_id)
                if fam is not None and isinstance(getattr(fam, "currency", None), dict):
                    ok, _ = transfer_currency_value(fam.currency, villager.inventory, still_needed_copper)
                    if ok:
                        still_needed_copper = max(0, fee - to_copper(normalize_wallet(villager.inventory)))
            if still_needed_copper <= 0:
                cls._finalize_fee_payment(villager, order, builder, fee, villager_manager, day_number)
                return True
            candidates = [
                s for s in cls._family_coin_stacks(villager.family_id, stockpile_manager)
                if int(s.amount) > 0
            ]
            if not candidates:
                order["status"] = "AWAITING_PAYMENT"
                villager.builder_payment_order_id = None
                villager.builder_fee_needed = None
                villager._resume_or_idle_after_need()
                return True
            stack = min(candidates, key=lambda s: math.hypot(
                (s.grid_x + 0.5) * TILE_SIZE - villager.x,
                (s.grid_y + 0.5) * TILE_SIZE - villager.y,
            ))
            sx, sy = (stack.grid_x + 0.5) * TILE_SIZE, (stack.grid_y + 0.5) * TILE_SIZE
            villager.task = "BUILDER_FEE_RETRIEVE"
            arrived = villager._move_towards(sx, sy, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager, furniture_manager=furniture_manager,
                                             interaction_target=stack)
            if arrived:
                denom = canonical_denomination(stack.resource_type)
                denom_value = to_copper({denom: 1})
                # Take enough coins of this denomination to cover the remainder.
                take = min(int(stack.amount), max(1, math.ceil(still_needed_copper / max(1, denom_value))))
                stack.amount -= take
                if stack.amount <= 0:
                    if stack in stockpile_manager.stacks:
                        stockpile_manager.stacks.remove(stack)
                    stockpile_manager.mark_totals_dirty()
                villager.inventory[denom] = int(villager.inventory.get(denom, 0)) + take
                villager.builder_fee_needed = {denom: take}
                # Next tick re-evaluates whether carried >= fee.
            return True

        if task == "BUILDER_FEE_TRAVEL":
            if not builder or not getattr(builder, "is_alive", True):
                chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
                if chest:
                    cls._move_exact_value(villager.inventory, chest.inventory, fee)
                order["status"] = "AWAITING_PAYMENT"
                villager.builder_payment_order_id = None
                villager._resume_or_idle_after_need()
                return True
            arrived = villager._move_towards(builder.x, builder.y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager, furniture_manager=furniture_manager,
                                             interaction_target=builder)
            if arrived:
                if cls._move_exact_value(villager.inventory, builder.inventory, fee):
                    order["status"] = "PAID"
                    order["commission_paid"] = True
                    order["paid_by_id"] = str(villager.id)
                    order["paid_by_family_id"] = str(villager.family_id)
                    order["paid_amount_copper"] = fee
                    cls._ensure_paid_seq(order, furniture_manager, building_manager)
                    if str(getattr(villager, "family_id", "")) != str(getattr(builder, "family_id", "")):
                        from game.systems.economy.market_sales_report import MarketSalesReportSystem
                        category = "Toolmaker Commissions" if order.get("order_type") == "TOOL_ORDER" else "Builder Commissions"
                        MarketSalesReportSystem.record_household_income(
                            villager_manager, getattr(builder, "family_id", None),
                            category, fee, day_number,
                        )
                    if order.get("order_type") == "TOOL_ORDER":
                        villager.say("Tool commission paid. Heading home.", duration=2.0)
                        builder.say(f"Commission received: {fee} Copper. I will forge the {order.get('tool_name', 'tool')}.", duration=2.5)
                    else:
                        villager.say("Furniture commission paid.", duration=2.0)
                        builder.say(f"Commission received: {fee} Copper. I will begin the order.", duration=2.5)
                else:
                    order["status"] = "AWAITING_PAYMENT"
                    villager.say("I no longer have the full furniture commission.", duration=2.5)
                villager.builder_payment_order_id = None
                villager.builder_payment_builder_id = None
                villager._resume_or_idle_after_need()
                if order.get("order_type") == "TOOL_ORDER" and order.get("status") == "PAID":
                    villager.task = "MISSING_TOOL"
            return True

        # BUILDER_FEE_LANDLORD_RETRIEVE is intercepted above: landlord storage
        # is servant-only, so this task can never reach the treasury path.

    @classmethod
    def _family_loose_stacks(cls, builder, stockpile_manager, family_id=None):
        """Loose ground stacks owned by the paying household (defaults to the builder's)."""
        fam_str = str(family_id if family_id is not None else getattr(builder, "family_id", "") or "")
        if not stockpile_manager or not fam_str:
            return []
        return [s for s in getattr(stockpile_manager, "stacks", [])
                if getattr(s, "owner_type", None) == "villager"
                and str(getattr(s, "owner_id", "")) == fam_str
                and getattr(s, "amount", 0) > 0]

    @classmethod
    def _order_loose_stacks(cls, builder, stockpile_manager, payer_type, family_id=None):
        """Loose stacks usable as material sources for an order.

        Only the paying household's stacks qualify — landlord storage is
        servant-only and is never a material source for the Builder.
        """
        # Landlord storage is servant-only: the Builder never draws materials
        # from the Lord's Treasury or landlord-owned stacks. Materials always
        # come from the paying household (or the Builder's own household for
        # landlord-funded public commissions).
        stacks = list(cls._family_loose_stacks(builder, stockpile_manager, family_id))
        return stacks

    @classmethod
    def _materials_in_storage(cls, builder, furniture_manager, stockpile_manager=None, payer_type=None, family_id=None):
        # Landlord storage is servant-only: never read the Lord's Treasury here.
        chest = None
        if furniture_manager:
            chest = furniture_manager.get_storage_for_family(
                family_id if family_id is not None else builder.family_id
            )
        totals = dict(getattr(builder, "inventory", {}))
        if chest:
            for item, count in getattr(chest, "inventory", {}).items():
                totals[item] = totals.get(item, 0) + int(count)
        # If family_id is specified and distinct from builder's own family,
        # also count materials in the Builder's workshop chest:
        if furniture_manager and family_id is not None and str(family_id) != str(getattr(builder, "family_id", "")):
            builder_chest = furniture_manager.get_storage_for_family(builder.family_id)
            if builder_chest:
                for item, count in getattr(builder_chest, "inventory", {}).items():
                    totals[item] = totals.get(item, 0) + int(count)
        # Loose stacks owned by the paying party or the Builder also count as materials.
        for stack in cls._order_loose_stacks(builder, stockpile_manager, payer_type, family_id):
            totals[stack.resource_type] = totals.get(stack.resource_type, 0) + int(stack.amount)
        if family_id is not None and str(family_id) != str(getattr(builder, "family_id", "")):
            for stack in cls._family_loose_stacks(builder, stockpile_manager, builder.family_id):
                totals[stack.resource_type] = totals.get(stack.resource_type, 0) + int(stack.amount)
        return chest, totals

    @classmethod
    def _order_material_shortfall(cls, builder, subject, order, furniture_manager, stockpile_manager):
        """Materials an AWAITING_MATERIAL order still needs beyond the Builder's
        accessible pool (inventory + payer chest + payer loose stacks)."""
        if hasattr(subject, "required_cost") and hasattr(subject, "delivered_cost"):
            required = {m: int(a) for m, a in (subject.required_cost or {}).items() if int(a) > 0}
            delivered = subject.delivered_cost or {}
        else:
            if order.get("order_type") == "REPAIR":
                required = {m: int(a) for m, a in BUILDER_REPAIR_MATERIALS.items() if int(a) > 0}
            else:
                recipe = FURNITURE_TYPES.get(getattr(subject, "furniture_type", ""), {})
                required = {m: int(a) for m, a in recipe.get("materials", {}).items() if int(a) > 0}
            delivered = order.get("materials_delivered") or {}
        remaining = {m: max(0, a - int(delivered.get(m, 0))) for m, a in required.items()}
        remaining = {m: a for m, a in remaining.items() if a > 0}
        if not remaining:
            return {}
        _, totals = cls._materials_in_storage(
            builder, furniture_manager, stockpile_manager,
            payer_type=order.get("payer_type"), family_id=order.get("payer_family_id"))
        return {
            material: amount - int(totals.get(material, 0))
            for material, amount in remaining.items()
            if int(totals.get(material, 0)) < amount
        }

    @classmethod
    def _order_materials_progressable(cls, builder, subject, order, furniture_manager,
                                      stockpile_manager, building_manager, villager_manager):
        """True while ONE AWAITING_MATERIAL order can still progress: materials on
        hand, or a market can supply the shortfall for the paying household."""
        shortfall = cls._order_material_shortfall(
            builder, subject, order, furniture_manager, stockpile_manager)
        if not shortfall:
            # Fully covered on hand (or nothing left to deliver): progressable.
            return True
        # Restock funds come from the paying household (landlord-funded public
        # jobs use the Builder's own household), so affordability must be
        # checked against that household, not always the Builder's.
        payer_family_id = order.get("payer_family_id")
        payer_type = order.get("payer_type")
        funds_family = (payer_family_id
                        if payer_family_id is not None and payer_type != "landlord"
                        else builder.family_id)
        funds_villager = builder
        if funds_family != builder.family_id:
            import types
            funds_villager = types.SimpleNamespace(
                id=builder.id, family_id=funds_family,
                x=builder.x, y=builder.y, inventory=builder.inventory,
            )
        from game.systems.economy.market_purchasing import AIMarketPurchasingSystem
        for material, amount in shortfall.items():
            market, _, affordable = AIMarketPurchasingSystem.find_nearest_market_for_material(
                funds_villager, material, amount, building_manager,
                furniture_manager, villager_manager)
            if not (market and affordable):
                return False
        return True

    @classmethod
    def material_order_progressable(cls, builder, subjects, furniture_manager,
                                    stockpile_manager, building_manager, villager_manager):
        """True while an AWAITING_MATERIAL order assigned to this Builder can still
        progress: he is mid-haul/restock, the materials are on hand, or a market can
        supply the shortfall. A material wait that cannot progress is a waiting
        state — the Builder should free-time for needs instead of standing idle."""
        material_tasks = (
            "BUILDER_RESTOCK_RETRIEVE_COINS", "BUILDER_RESTOCK_TRAVEL_TO_MARKET",
            "BUILDER_RESTOCK_HAULING_HOME", "BUILDER_COLLECTING_MATERIALS",
            "BUILDER_DELIVERING_MATERIALS",
        )
        if getattr(builder, "task", "") in material_tasks:
            return True
        for subject in subjects:
            order = getattr(subject, "construction_order", None)
            if not isinstance(order, dict) or order.get("status") != "AWAITING_MATERIAL":
                continue
            owner = order.get("builder_id")
            if owner is not None and str(owner) not in ("", str(builder.id)):
                continue
            if cls._order_materials_progressable(
                    builder, subject, order, furniture_manager, stockpile_manager,
                    building_manager, villager_manager):
                return True
        return False

    # ------------------------------------------------------------------
    # Dead/reassigned builder: dissolve his queue, refund PAID orders
    # ------------------------------------------------------------------







    @classmethod
    def _deliver_build_materials(cls, builder, target, order, required, chest, dt,
                                 all_entities, player, building_manager, furniture_manager,
                                 furniture_target=False, stockpile_manager=None):
        """Physically haul recipe materials from a household chest to a build site."""
        order.setdefault(
            "material_source_family_id",
            str(order.get("payer_family_id") or getattr(builder, "family_id", "") or ""),
        )
        delivered = (order.setdefault("materials_delivered", {}) if furniture_target
                     else target.delivered_cost)
        remaining = {
            material: max(0, int(amount) - int(delivered.get(material, 0)))
            for material, amount in required.items()
        }
        remaining = {material: amount for material, amount in remaining.items() if amount > 0}
        if not remaining:
            order["materials_committed"] = True
            return True

        cargo = {
            material: min(amount, max(0, int(builder.inventory.get(material, 0))))
            for material, amount in remaining.items()
        }
        cargo = {material: amount for material, amount in cargo.items() if amount > 0}
        if cargo:
            target_x, target_y = cls._asset_approach_point(
                builder, target, order, all_entities, building_manager,
            )
            at_site = cls._within_asset_work_range(builder, target)
            builder.task = "BUILDER_DELIVERING_MATERIALS"
            if not at_site:
                builder._move_towards(
                    target_x, target_y, dt,
                    arrival_dist=cls._asset_approach_arrival_distance(target, target_x, target_y),
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                    recover_blocked_routes=True,
                    interaction_target=target,
                )
                return False
            for material, amount in cargo.items():
                left = max(0, int(builder.inventory.get(material, 0)) - amount)
                if left:
                    builder.inventory[material] = left
                else:
                    builder.inventory.pop(material, None)
                if furniture_target:
                    delivered[material] = int(delivered.get(material, 0)) + amount
                else:
                    target.deposit_resource(material, amount)
                    builder_delivered = order.setdefault("materials_delivered", {})
                    builder_delivered[material] = int(builder_delivered.get(material, 0)) + amount
            if all(int(delivered.get(material, 0)) >= int(amount)
                   for material, amount in required.items()):
                order["materials_committed"] = True
            return False

        # Only walk to the chest if it can actually supply at least one of the
        # remaining materials — otherwise we would ping-pong between the chest
        # and the loose stacks forever.
        chest_can_supply = bool(chest) and any(
            int(chest.inventory.get(material, 0)) > 0 for material in remaining
        )
        if not chest_can_supply and furniture_manager and getattr(builder, "family_id", None):
            builder_chest = furniture_manager.get_storage_for_family(builder.family_id)
            if builder_chest and builder_chest is not chest and any(
                int(builder_chest.inventory.get(material, 0)) > 0 for material in remaining
            ):
                chest = builder_chest
                chest_can_supply = True
        if chest_can_supply:
            chest_x, chest_y = chest.get_approach_point(
                builder.x, builder.y, worker_id=builder.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
            at_chest = math.hypot(builder.x - chest_x, builder.y - chest_y) <= CHEST_INTERACTION_RADIUS
            builder.task = "BUILDER_COLLECTING_MATERIALS"
            if not at_chest:
                builder._move_towards(
                    chest_x, chest_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                    interaction_target=chest,
                )
                return False

            room = builder.get_inventory_room()
            loaded_any = False
            for material, amount in remaining.items():
                if room <= 0:
                    break
                take = min(amount, max(0, int(chest.inventory.get(material, 0))), room)
                if take <= 0:
                    continue
                chest.inventory[material] -= take
                if chest.inventory[material] <= 0:
                    chest.inventory.pop(material, None)
                builder.inventory[material] = int(builder.inventory.get(material, 0)) + take
                room -= take
                loaded_any = True
            if loaded_any:
                furniture_manager.invalidate_cache()
            elif room <= 0 and builder._get_unneeded_inventory():
                builder.task = "DEPOSITING_UNUSED_ITEMS"
            # Chest could not fully supply; fall through to payer-owned loose stacks.
        return cls._collect_from_loose_stack(
            builder, target, order, required, dt,
            all_entities, player, building_manager, furniture_manager,
            stockpile_manager, furniture_target=furniture_target,
        )

    @classmethod
    def refund_order_materials(cls, order, asset, furniture_manager, stockpile_manager=None):
        """Return builder-delivered materials to the paying party when an unfinished order is destroyed.

        *** ESTABLISHED — USER-CONFIRMED, DO NOT REGRESS ***
        Cancelling/destroying an UNFINISHED blueprint refunds the
        materials the builder physically delivered (tracked in
        order["materials_delivered"]) back to the household chest recorded in
        material_source_family_id (falling back to payer_family_id), or drops
        them as loose stacks owned by that household when no chest exists.
        Completed orders (status COMPLETE) keep materials consumed — no refund.
        Servant-delivered site materials (delivered_cost) are refunded through
        the separate site resource path, never double-counted here. Landlord
        storage is never a refund destination (servant-only rule)."""
        if not isinstance(order, dict):
            return {}
        delivered = order.get("materials_delivered") or {}
        delivered = {material: int(amount) for material, amount in delivered.items() if int(amount) > 0}
        if not delivered:
            return {}
        order["materials_delivered"] = {}
        order["materials_committed"] = False

        # Landlord storage is servant-only: refunded materials always return to
        # the household chest they were taken from (recorded at delivery time),
        # never to the Lord's Treasury.
        family_id = (order.get("material_source_family_id")
                     or order.get("payer_family_id"))
        chest = None
        if furniture_manager and family_id:
            chest = furniture_manager.get_storage_for_family(family_id)
        gx = int(getattr(asset, "grid_x", 0))
        gy = int(getattr(asset, "grid_y", 0))
        for material, amount in delivered.items():
            if chest is not None:
                chest.inventory[material] = int(chest.inventory.get(material, 0)) + amount
            elif stockpile_manager is not None:
                stockpile_manager.drop_resource(
                    material, amount, gx, gy,
                    owner_type="villager", owner_id=family_id,
                )
        if chest is not None and furniture_manager:
            furniture_manager.invalidate_cache()
            from game.systems.economy.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        return delivered

    @classmethod
    def _collect_from_loose_stack(cls, builder, target, order, required, dt,
                                  all_entities, player, building_manager, furniture_manager,
                                  stockpile_manager, furniture_target=False):
        """Pick up needed materials from the nearest payer-owned loose stack."""
        if not stockpile_manager:
            return False
        payer_type = order.get("payer_type")
        delivered = (order.setdefault("materials_delivered", {}) if furniture_target
                     else target.delivered_cost)
        remaining = {
            material: max(0, int(amount) - int(delivered.get(material, 0)))
            for material, amount in required.items()
        }
        remaining = {m: a for m, a in remaining.items() if a > 0}
        if not remaining:
            return True

        payer_family_id = order.get("payer_family_id")
        candidates = [
            s for s in cls._order_loose_stacks(builder, stockpile_manager, payer_type, payer_family_id)
            if s.resource_type in remaining
            and int(s.amount) > 0
            and int(builder.inventory.get(s.resource_type, 0)) < remaining[s.resource_type]
        ]
        if not candidates:
            return False

        fam_str = str(payer_family_id or getattr(builder, "family_id", "") or "")
        # Household-owned stacks are preferred; landlord stacks are fallback.
        stack = min(candidates, key=lambda s: (
            0 if (getattr(s, "owner_type", None) == "villager"
                  and str(getattr(s, "owner_id", "")) == fam_str) else 1,
            math.hypot(
                (s.grid_x + 0.5) * TILE_SIZE - builder.x,
                (s.grid_y + 0.5) * TILE_SIZE - builder.y,
            ),
        ))
        sx, sy = (stack.grid_x + 0.5) * TILE_SIZE, (stack.grid_y + 0.5) * TILE_SIZE
        builder.task = "BUILDER_COLLECTING_MATERIALS"
        arrived = builder._move_towards(
            sx, sy, dt, arrival_dist=LOOSE_ITEM_ARRIVAL_DIST,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=stack,
        )
        if not arrived:
            return False

        room = builder.get_inventory_room()
        if room <= 0:
            if builder._get_unneeded_inventory():
                builder.task = "DEPOSITING_UNUSED_ITEMS"
            return False
        material = stack.resource_type
        need = max(0, remaining[material] - int(builder.inventory.get(material, 0)))
        take = min(int(stack.amount), need, room)
        if take <= 0:
            return False
        stack.amount -= take
        if stack.amount <= 0:
            if stack in stockpile_manager.stacks:
                stockpile_manager.stacks.remove(stack)
            stockpile_manager.mark_totals_dirty()
        builder.inventory[material] = int(builder.inventory.get(material, 0)) + take
        furniture_manager.invalidate_cache()
        return False

    @classmethod
    def _clear_restock_state(cls, builder, cooldown_seconds=0.0):
        """Reset transient restock targets and optionally apply retry cooldown."""
        builder.target_restock_market = None
        builder.target_restock_mat = None
        builder.target_restock_qty = 0
        builder.target_restock_payer_type = None
        builder.target_restock_family_id = None
        if cooldown_seconds > 0.0:
            builder._restock_cooldown_until = time.time() + float(cooldown_seconds)

    @classmethod
    def _idle_buffer_coin_reserve(cls, builder, furniture_manager, villager_manager, building_manager):
        """Minimum coins reserved for living members' daily food before idle buffer buying."""
        if not villager_manager or not hasattr(villager_manager, "get_family_by_id"):
            return 0
        fam = villager_manager.get_family_by_id(getattr(builder, "family_id", None))
        if not fam:
            return 0
        living = [m for m in getattr(fam, "members", []) if getattr(m, "is_alive", True)]
        if not living:
            return 0
        chest = furniture_manager.get_storage_for_family(builder.family_id) if furniture_manager else None
        inv_food = sum(
            int(v) for k, v in (getattr(chest, "inventory", {}) or {}).items()
            if MARKET_TRADEABLE_ITEMS.get(k) == "Food" and int(v) > 0
        )
        needed_food = len(living) * DAILY_FOOD_REQUIREMENT
        if inv_food >= needed_food:
            return 0
        markets = MarketService.get_all_markets(building_manager)
        food_price = cls._food_unit_price(markets, minimum_stock=1)
        return max(0, (needed_food - inv_food) * int(food_price))

    @classmethod
    def _begin_restock(cls, builder, missing, building_manager, furniture_manager, villager_manager,
                       payer_type=None, family_id=None, exact_only=False, is_idle_buffer=False):
        from game.systems.economy.market_purchasing import AIMarketPurchasingSystem
        from game.data.catalog import DEDICATED_JOBS
        from game.data.config import DEFAULT_MATERIAL_RESTOCK_BATCH, VILLAGER_INVENTORY_CAPACITY
        if float(getattr(builder, "_restock_cooldown_until", 0.0) or 0.0) > time.time():
            return False
        job = getattr(builder, "job", "")
        stock_targets = DEDICATED_JOBS.get(job, {}).get("material_stock_target", {})
        coin_family = (family_id if family_id is not None and payer_type != "landlord" else getattr(builder, "family_id", None))
        chest = furniture_manager.get_storage_for_family(coin_family) if furniture_manager else None
        coin_reserve = (
            cls._idle_buffer_coin_reserve(builder, furniture_manager, villager_manager, building_manager)
            if is_idle_buffer else 0
        )
        for material, quantity in missing.items():
            req_qty = max(0, int(quantity))
            if req_qty <= 0:
                continue
            if exact_only:
                desired_batch = min(VILLAGER_INVENTORY_CAPACITY, req_qty)
            else:
                target_stock = int(stock_targets.get(material, DEFAULT_MATERIAL_RESTOCK_BATCH))
                cur_chest = int((getattr(chest, "inventory", {}) or {}).get(material, 0)) if chest else 0
                desired_batch = min(VILLAGER_INVENTORY_CAPACITY, max(req_qty, target_stock - cur_chest))
            if desired_batch <= 0:
                continue
            market, unit_price, affordable = AIMarketPurchasingSystem.find_nearest_market_for_material(
                builder, material, desired_batch, building_manager, furniture_manager, villager_manager)
            if market and affordable and is_idle_buffer and coin_reserve > 0 and unit_price > 0:
                wallet, source = MarketService.get_household_funds_and_source(
                    builder, furniture_manager, villager_manager)
                pocket = getattr(builder, "inventory", {})
                total_funds = to_copper(wallet) + (0 if source is pocket else to_copper(normalize_wallet(pocket)))
                spendable = max(0, total_funds - coin_reserve)
                affordable = min(affordable, spendable // int(unit_price))
            if market and affordable > 0:
                builder.target_restock_market = market
                builder.target_restock_mat = material
                builder.target_restock_qty = affordable
                builder.target_restock_payer_type = payer_type
                builder.target_restock_family_id = family_id
                builder.task = "BUILDER_RESTOCK_RETRIEVE_COINS"
                return True
        return False

    @classmethod
    def _update_restock(cls, builder, dt, building_manager, furniture_manager, villager_manager,
                        all_entities, player, stockpile_manager=None, permit_manager=None):
        from game.systems.economy.market_purchasing import AIMarketPurchasingSystem
        task = builder.task
        market = getattr(builder, "target_restock_market", None)
        material = getattr(builder, "target_restock_mat", None)
        quantity = getattr(builder, "target_restock_qty", 0)
        restock_payer_type = getattr(builder, "target_restock_payer_type", None)
        restock_family_id = getattr(builder, "target_restock_family_id", None)
        # Landlord storage is servant-only: restock materials always return to a
        # household chest (the payer's, or the Builder's own for public jobs).
        chest = (furniture_manager.get_storage_for_family(
            restock_family_id if restock_family_id is not None else builder.family_id
        ) if furniture_manager else None)
        if not market or not material or quantity <= 0:
            builder.task = "IDLE"
            cls._clear_restock_state(builder)
            return True
        unit_price = MarketService.get_item_price(material, market)
        if task == "BUILDER_RESTOCK_RETRIEVE_COINS":
            needed_coins = unit_price * quantity
            pocket_coins = to_copper(normalize_wallet(getattr(builder, "inventory", {})))
            if pocket_coins >= needed_coins:
                arrived = True
            elif chest:
                x, y = chest.get_world_pos(TILE_SIZE)
                arrived = builder._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                                  all_entities=all_entities, player=player,
                                                  building_manager=building_manager, furniture_manager=furniture_manager,
                                                  interaction_target=chest)
            else:
                arrived = True
            if arrived:
                deficit = max(0, int(needed_coins) - pocket_coins)
                enough = deficit <= 0
                message = ""
                if not enough:
                    coin_family = (restock_family_id
                                   if restock_family_id is not None and restock_payer_type != "landlord"
                                   else builder.family_id)
                    _, coin_source = MarketService.get_household_funds_and_source(
                        coin_family, furniture_manager, villager_manager)
                    if (coin_source is not None
                            and coin_source is not getattr(builder, "inventory", None)
                            and to_copper(normalize_wallet(coin_source)) >= deficit):
                        enough, _ = transfer_currency_value(coin_source, builder.inventory, deficit)
                    else:
                        enough, message = AIMarketPurchasingSystem.withdraw_household_coins(
                            builder, int(needed_coins), furniture_manager, villager_manager)
                if enough:
                    builder.task = "BUILDER_RESTOCK_TRAVEL_TO_MARKET"
                else:
                    builder.say(message or "The household does not have enough coins for the purchase.", duration=2.5)
                    cls._clear_restock_state(builder, cooldown_seconds=10.0)
                    builder.task = "IDLE"
            return True
        if task == "BUILDER_RESTOCK_TRAVEL_TO_MARKET":
            x, y = market.get_center_world(TILE_SIZE)
            if builder._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                       all_entities=all_entities, player=player,
                                       building_manager=building_manager, furniture_manager=furniture_manager,
                                       interaction_target=market):
                ok, message = AIMarketPurchasingSystem.execute_material_transaction(builder, market, material, quantity)
                if ok:
                    builder.task = "BUILDER_RESTOCK_HAULING_HOME"
                else:
                    builder.say(message, duration=2.5)
                    cls._clear_restock_state(builder, cooldown_seconds=10.0)
                    builder.task = "IDLE"
            return True
        if task == "BUILDER_RESTOCK_HAULING_HOME":
            if chest:
                x, y = chest.get_world_pos(TILE_SIZE)
                if builder._move_towards(x, y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                                           all_entities=all_entities, player=player,
                                           building_manager=building_manager, furniture_manager=furniture_manager,
                                           interaction_target=chest):
                    if (restock_family_id is not None
                            and str(restock_family_id) != str(builder.family_id)
                            and restock_payer_type != "landlord" and chest is not None):
                        from game.systems.economy.currency import CURRENCY_DENOMINATIONS
                        for denom in CURRENCY_DENOMINATIONS:
                            amt = builder.inventory.get(denom, 0)
                            if amt > 0:
                                chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                                del builder.inventory[denom]
                        compact_currency_wallet(chest.inventory)
                        amt = builder.inventory.get(material, 0)
                        if amt > 0:
                            chest.store_item(material, amt)
                            del builder.inventory[material]
                        furniture_manager.invalidate_cache()
                    else:
                        AIMarketPurchasingSystem.deposit_materials_and_change_to_chest(builder, furniture_manager)
                    builder.target_restock_market = None
                    builder.target_restock_mat = None
                    builder.target_restock_qty = 0
                    builder.target_restock_payer_type = None
                    builder.target_restock_family_id = None
                    builder.say("Restocked Builder materials.", duration=2.0)
                    builder.task = "IDLE"
            else:
                home_x, home_y = builder._get_home_storage_dest(
                    permit_manager, building_manager, furniture_manager, all_entities=all_entities
                ) if permit_manager else (builder.x, builder.y)
                family = villager_manager.get_family_by_id(builder.family_id) if villager_manager else None
                home_permit_id = getattr(family, "assigned_permit_id", None)
                home_permit = next((p for p in getattr(permit_manager, "permits", [])
                                    if str(p.id) == str(home_permit_id)), None) if home_permit_id else None
                if home_permit:
                    home_building = next((b for b in getattr(building_manager, "buildings", [])
                                          if home_permit.overlaps_building(b)), None)
                    if home_building:
                        home_x, home_y = home_building.get_approach_point(
                            (builder.x, builder.y), TILE_SIZE, building_manager
                        )
                    else:
                        home_x = (home_permit.grid_x + home_permit.tiles_w / 2.0) * TILE_SIZE
                        home_y = (home_permit.grid_y + home_permit.tiles_h / 2.0) * TILE_SIZE
                if not builder._move_towards(
                    home_x, home_y, dt, arrival_dist=CHEST_INTERACTION_RADIUS,
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                    interaction_target=home_building,
                ):
                    return True
                active_order = next((f for f in furniture_manager.furnitures
                                     if f.construction_order
                                     and str(f.construction_order.get("builder_id")) == str(builder.id)
                                     and f.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT")), None)
                material_targets = DEDICATED_JOBS.get("Builder", {}).get("material_stock_target", {})
                retained = {item: max(0, int(amount)) for item, amount in material_targets.items()}
                recipe = FURNITURE_TYPES.get(getattr(active_order, "furniture_type", ""), {})
                for material, amount in recipe.get("materials", {}).items():
                    retained[material] = max(retained.get(material, 0), int(amount))
                active_public_site = next((site for site in getattr(building_manager, "construction_sites", [])
                                           if getattr(site, "construction_order", None)
                                           and str(site.construction_order.get("builder_id")) == str(builder.id)
                                           and site.construction_order.get("order_type") == "PUBLIC_BUILD"
                                           and site.construction_order.get("status") not in ("COMPLETE", "AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING")), None)
                if active_public_site:
                    remaining_materials = {
                        material: max(0, int(amount) - int(active_public_site.delivered_cost.get(material, 0)))
                        for material, amount in active_public_site.required_cost.items()
                    }
                    for material, amount in remaining_materials.items():
                        retained[material] = max(retained.get(material, 0), amount)
                # Chestless households: drop surplus materials on a tile
                # inside the household permit so the family's "safe at home"
                # retrieval check recognizes the stack (approach-point tiles
                # can sit outside the permit and cause retrieve/drop loops).
                drop_tile = None
                if permit_manager is not None and home_permit_id is not None:
                    from game.world.permits import resolve_household_ground_drop_tile
                    drop_tile = resolve_household_ground_drop_tile(
                        home_permit_id, permit_manager, building_manager,
                        furniture_manager=furniture_manager,
                        ref_x=home_x, ref_y=home_y)
                if drop_tile is None:
                    drop_tile = (int(home_x // TILE_SIZE), int(home_y // TILE_SIZE))
                for material in material_targets:
                    surplus = max(0, int(builder.inventory.get(material, 0)) - int(retained.get(material, 0)))
                    if surplus and stockpile_manager:
                        builder.inventory[material] -= surplus
                        if builder.inventory[material] <= 0:
                            builder.inventory.pop(material, None)
                        stockpile_manager.drop_resource(
                            material, surplus, *drop_tile,
                            owner_type="villager", owner_id=builder.family_id,
                        )
                builder.say("No household chest; surplus materials were left at home.", duration=2.5)
                builder.task = "IDLE"
            if builder.task == "IDLE":
                builder.target_restock_market = None
                builder.target_restock_mat = None
                builder.target_restock_qty = 0
                return False
            return True
        return False

    @classmethod
    def _block_until_tools_ready(cls, builder):
        """Returns True when the builder lacks required job tools and must wait.

        Commission errands (claiming orders, payment requests, material hauling)
        don't need tools; only the actual build/repair phase does.
        """
        getter = getattr(builder, "get_missing_job_tools", None)
        if not callable(getter) or not getter():
            return False
        if not getattr(builder, "speech_text", None):
            builder.say("I need my job tools before I can build.", duration=3.0)
        builder.task = "IDLE"
        return True

    @classmethod
    # ------------------------------------------------------------------
    # *** ESTABLISHED FEATURES — USER-CONFIRMED, DO NOT REGRESS ***
    #
    #  * Own-household orders (payer_family_id == builder.family_id): FREE
    #    labor — status jumps straight to PAID with no commission/fee errand,
    #    but materials are STILL consumed from the family exactly like paid
    #    orders. ESTABLISHED: both own-household and external-household
    #    commission order types are confirmed working workflows.
    #
    #  * Material sourcing follows order["payer_family_id"] — the household
    #    that pays for the order supplies the materials from ITS OWN chest /
    #    loose stacks (for own-household orders that IS the builder's
    #    household). ESTABLISHED: the builder must source materials from
    #    the paying household's storage, never arbitrarily.
    #
    #  * LANDLORD STORAGE LOCKDOWN (ESTABLISHED, user-enforced rule):
    #    builder material sourcing, coin withdrawals, and restock
    #    purchases must NEVER read the Lord Treasury chest or
    #    landlord-owned loose stacks. ONLY servants may touch landlord
    #    storage. Landlord-paid public fees go through
    #    BuilderSystem.dispatch_pending_public_commissions -> servant
    #    courier, never the builder himself.
    #
    #  * Public structure repair/build commissions (ESTABLISHED): public
    #    site/repair orders with builder_id=None may be claimed by any
    #    builder; if the claimant's household cannot supply materials the
    #    claim is released (builder_id -> None) so another builder's
    #    household gets a turn. Paid status is never reset (no double-charge).
    #    This rotation is what keeps public structures getting repaired.
    # ------------------------------------------------------------------
    def _is_own_household_order(cls, order, builder):
        """True when the commission's payer family is the builder's own family."""
        payer_family = order.get("payer_family_id")
        return payer_family is not None and str(payer_family) == str(getattr(builder, "family_id", ""))

    @classmethod
    def _select_awaiting_order(cls, builder, furniture_manager, villager_manager):
        """Pick the next AWAITING_PAYMENT furniture order this builder may claim."""
        now = time.time()
        awaiting_orders = [f for f in furniture_manager.furnitures
                           if f.construction_order
                           and f.construction_order.get("status") == "AWAITING_PAYMENT"
                           and f.construction_order.get("builder_id") in (None, str(builder.id))
                           and cls._artisan_job(f.construction_order) == str(getattr(builder, "job", ""))
                           and float(f.construction_order.get("_claim_retry_at", 0.0) or 0.0) <= now]
        active = next((f for f in awaiting_orders
                       if str(f.construction_order.get("payer_family_id")) == str(builder.family_id)), None)
        if active is None:
            for candidate in awaiting_orders:
                payer_family_id = candidate.construction_order.get("payer_family_id")
                household_builder = next((worker for worker in villager_manager.get_all_villagers()
                                            if getattr(worker, "job", None) == "Builder"
                                            and getattr(worker, "is_alive", True)
                                            and str(getattr(worker, "family_id", "")) == str(payer_family_id)), None) if villager_manager else None
                if household_builder and str(household_builder.id) != str(builder.id):
                    continue
                active = candidate
                break
        return active

    @classmethod
    def _claim_awaiting_order(cls, builder, order_furniture, villager_manager, furniture_manager, stockpile_manager):
        """Assign an awaiting order to this builder and start its payment flow.

        Own-household orders skip the service fee entirely (free labor —
        materials are still drawn from the family as usual).
        """
        order = order_furniture.construction_order
        order["builder_id"] = str(builder.id)
        order["builder_family_id"] = str(getattr(builder, "family_id", "") or "")
        order["artisan_job"] = cls._artisan_job(order)
        if cls._is_own_household_order(order, builder):
            order["status"] = "PAID"
            order["commission_paid"] = True
            order["paid_by_id"] = "household"
            order["paid_amount_copper"] = 0
            cls._ensure_paid_seq(order, furniture_manager, building_manager=None)
            if not getattr(builder, "speech_text", None):
                builder.say("Family commission — no fee, straight to work.", duration=2.5)
            builder.task = "IDLE"
            return
        if not cls._assign_payment(order_furniture, villager_manager, furniture_manager, stockpile_manager):
            order["_claim_retry_at"] = time.time() + COMMISSION_CLAIM_RETRY_SECONDS
            if not getattr(builder, "speech_text", None):
                builder.say("Waiting for the household commission.", duration=2.5)
            builder.task = "IDLE"
            return
        if order.get("status") == "LANDLORD_PAYMENT_PENDING":
            # Landlord storage is servant-only: mark the order for the public
            # commission dispatcher, which sends a servant to the treasury.
            order["payer_type"] = "landlord"
            order["payer_id"] = "landlord"
            builder.task = "IDLE"
            return
        builder.say("Commission requested from the household.", duration=2.0)
        builder.task = "IDLE"

    @classmethod
    def update_worker(cls, builder, dt, schedule_activity, building_manager, furniture_manager,
                      villager_manager, all_entities, player, day_cycle,
                      stockpile_manager=None, permit_manager=None):
        if getattr(builder, "job", None) != "Builder" or not furniture_manager:
            return False
        if schedule_activity != "WORK":
            return False

        if builder.task.startswith("BUILDER_RESTOCK_"):
            return cls._update_restock(builder, dt, building_manager, furniture_manager,
                                       villager_manager, all_entities, player,
                                       stockpile_manager, permit_manager)

        work_orders = cls._order_subjects(furniture_manager, building_manager)
        has_commission_work = any(
            isinstance(getattr(subject, "construction_order", None), dict)
            and str(subject.construction_order.get("builder_id")) == str(builder.id)
            and subject.construction_order.get("status") in ("PAID", "BUILDING", "AWAITING_MATERIAL")
            for subject in work_orders
        )
        # Accept new commissions into the FIFO queue even while busy: payment
        # errands resolve independently (servant courier / household rep), and
        # the artisan works PAID orders in paid_seq order during WORK hours.
        awaiting = cls._select_awaiting_order(builder, furniture_manager, villager_manager)
        if awaiting is not None:
            cls._claim_awaiting_order(builder, awaiting, villager_manager,
                                      furniture_manager, stockpile_manager)

        if not has_commission_work:
            # Own-household commissions are free labor — claim them before
            # restocking so family orders never queue behind material runs.
            awaiting = cls._select_awaiting_order(builder, furniture_manager, villager_manager)
            if awaiting is not None and cls._is_own_household_order(
                    awaiting.construction_order, builder):
                cls._claim_awaiting_order(builder, awaiting, villager_manager,
                                          furniture_manager, stockpile_manager)
                return False
            _, stored_materials = cls._materials_in_storage(builder, furniture_manager, stockpile_manager)
            stock_targets = DEDICATED_JOBS.get("Builder", {}).get("material_stock_target", {})
            low_stock = {
                material: max(0, int(target) - int(stored_materials.get(material, 0)))
                for material, target in stock_targets.items()
                if int(stored_materials.get(material, 0)) < int(target)
            }
            if low_stock and cls._begin_restock(
                    builder, low_stock, building_manager, furniture_manager, villager_manager,
                    exact_only=True, is_idle_buffer=True):
                builder.active_tool = None
                return True

        # Payment-transit housekeeping: stale household payment errands get
        # released back to AWAITING_PAYMENT, but payment-in-flight orders must
        # NOT freeze the builder — his queued PAID orders keep him working.
        for subject in work_orders:
            order = getattr(subject, "construction_order", None)
            if not isinstance(order, dict):
                continue
            if str(order.get("builder_id")) != str(builder.id):
                continue
            if order.get("payer_type") == "landlord":
                continue  # servant courier owns landlord payment transit
            if order.get("status") not in ("PAYMENT_REQUESTED", "PAYMENT_TRAVELING"):
                continue
            waiting_order = order
            expected_task = ("BUILDER_FEE_RETRIEVE" if waiting_order.get("status") == "PAYMENT_REQUESTED"
                             else "BUILDER_FEE_TRAVEL")
            payer = next((villager for villager in villager_manager.get_all_villagers()
                          if str(villager.id) == str(waiting_order.get("payer_id"))), None) if villager_manager else None
            pending_data = getattr(payer, "pending_commission_data", {}) if payer else {}
            from game.systems.work.commission_schedule import CommissionScheduleSystem
            pending_this_order = bool(payer and CommissionScheduleSystem.is_queued(
                payer, expected_task, "builder_payment_order_id", subject.id
            ))
            payment_task_active = bool(
                payer and getattr(payer, "is_alive", True) and (
                    (getattr(payer, "task", None) == expected_task
                     and str(getattr(payer, "builder_payment_order_id", None)) == str(subject.id))
                    or pending_this_order
                    or (getattr(payer, "pending_commission_task", None) == expected_task
                        and str(pending_data.get("builder_payment_order_id")) == str(subject.id))
                )
            )
            if not payment_task_active:
                waiting_order["status"] = "AWAITING_PAYMENT"
                waiting_order["payer_id"] = None
                if payer and str(getattr(payer, "builder_payment_order_id", None)) == str(subject.id):
                    payer.builder_payment_order_id = None
                    payer.builder_payment_builder_id = None
                    payer._resume_or_idle_after_need()

        # FIFO work selection: earliest paid_seq wins across ALL commission
        # kinds (public build > repair > furniture only breaks ties).
        workable_statuses = ("PAID", "AWAITING_MATERIAL", "BUILDING")
        candidates = []
        for subject in work_orders:
            order = getattr(subject, "construction_order", None)
            if not isinstance(order, dict) or order.get("status") not in workable_statuses:
                continue
            cid = order.get("builder_id")
            cid_ok = (cid is None or str(cid) == str(builder.id))
            if not cid_ok:
                continue
            if cls._artisan_job(order) != str(getattr(builder, "job", "")):
                continue  # queue is per-artisan: only matching job orders
            is_public_site = (getattr(subject, "building_type", "") != ""
                              and order.get("order_type") == "PUBLIC_BUILD"
                              and subject in getattr(building_manager, "construction_sites", []))
            is_public_repair = (order.get("order_type") == "REPAIR"
                                and order.get("commission_paid") is True
                                and subject in getattr(building_manager, "buildings", []))
            is_furniture = (order.get("commission_paid") is True
                            and subject in getattr(furniture_manager, "furnitures", []))
            if not (is_public_site or is_public_repair or is_furniture):
                continue
            if order.get("status") == "AWAITING_MATERIAL" and not cls._order_materials_progressable(
                    builder, subject, order, furniture_manager, stockpile_manager,
                    building_manager, villager_manager):
                continue  # stuck material wait must not freeze the queue head
            cls._ensure_paid_seq(order, furniture_manager, building_manager)
            seq = int(order.get("paid_seq", 0) or 0)
            kind_rank = 0 if is_public_site else (1 if is_public_repair else 2)
            is_priority = bool(order.get("priority") or getattr(subject, "is_priority", False) or getattr(subject, "priority", False))
            priority_rank = 0 if is_priority else 1
            candidates.append((priority_rank, seq, kind_rank, is_public_site, is_public_repair, subject))
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))
        chosen = candidates[0] if candidates else None
        public_site = chosen[5] if chosen and chosen[3] else None
        public_repair = chosen[5] if chosen and chosen[4] else None
        furniture_active = chosen[5] if chosen and not chosen[3] and not chosen[4] else None

        # Priority pre-emption: If the top workable order is priority and builder is engaged in another non-priority order, switch immediately
        if chosen and chosen[0] == 0:
            chosen_subject = chosen[5]
            chosen_order = getattr(chosen_subject, "construction_order", {}) or {}
            chosen_order_id = chosen_order.get("id")
            cur_target_id = getattr(builder, "builder_target_order_id", None)
            if cur_target_id and chosen_order_id and str(cur_target_id) != str(chosen_order_id):
                builder.builder_work_timer = 0.0
                builder.active_tool = None
                builder.builder_target_order_id = None
                builder.builder_target_position = None
                builder.task = "IDLE"
                if not getattr(builder, "speech_text", None):
                    builder.say("Prioritizing urgent construction!", duration=2.5)

        if public_site:
            order = public_site.construction_order
            if order.get("builder_id") is None:
                order["builder_id"] = str(builder.id)
            if order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING"):
                builder.task = "IDLE"
                return False
            if order.get("status") in ("PAID", "AWAITING_MATERIAL", "BUILDING"):
                if not public_site.is_materials_complete():
                    chest, totals = cls._materials_in_storage(
                        builder, furniture_manager, stockpile_manager,
                        payer_type=order.get("payer_type"),
                        family_id=order.get("payer_family_id"))
                    remaining = {
                        material: max(0, int(required) - int(public_site.delivered_cost.get(material, 0)))
                        for material, required in public_site.required_cost.items()
                    }
                    missing = {
                        material: max(0, amount - max(0, int(totals.get(material, 0))))
                        for material, amount in remaining.items() if amount > 0
                    }
                    if missing and cls._begin_restock(builder, missing, building_manager,
                                                      furniture_manager, villager_manager,
                                                      payer_type=order.get("payer_type"),
                                                      family_id=order.get("payer_family_id"),
                                                      exact_only=True):
                        order["status"] = "AWAITING_MATERIAL"
                        return True
                    ready = cls._deliver_build_materials(
                        builder, public_site, order, public_site.required_cost, chest, dt,
                        all_entities, player, building_manager, furniture_manager,
                        stockpile_manager=stockpile_manager,
                    )
                    if not public_site.is_materials_complete():
                        order["status"] = "AWAITING_MATERIAL"
                        if (missing and builder.task != "BUILDER_COLLECTING_MATERIALS"
                                and not any(int(totals.get(m, 0)) > 0 for m in missing)):
                            order["builder_id"] = None
                        if missing and not getattr(builder, "target_restock_market", None):
                            builder.say("I need building materials, but none are available to buy right now.", duration=2.5)
                        elif not ready and builder.task == "BUILDER_COLLECTING_MATERIALS":
                            builder.say("I am carrying the building materials from storage.", duration=2.0)
                        return True
                    order["materials_committed"] = True
                if cls._block_until_tools_ready(builder):
                    return True
                builder.task = "BUILDER_CONSTRUCTING"
                target_x, target_y = cls._asset_approach_point(
                    builder, public_site, order, all_entities, building_manager,
                )
                arrived = cls._within_asset_work_range(builder, public_site)
                if not arrived:
                    builder._move_towards(
                        target_x, target_y, dt,
                        arrival_dist=cls._asset_approach_arrival_distance(
                            public_site, target_x, target_y
                        ),
                        all_entities=all_entities, player=player,
                        building_manager=building_manager, furniture_manager=furniture_manager,
                        recover_blocked_routes=True,
                        interaction_target=public_site,
                    )
                    arrived = cls._within_asset_work_range(builder, public_site)
                if arrived:
                    order["status"] = "BUILDING"
                    public_site.build_progress += dt
                    duration = max(1.0, float(order.get("build_duration_seconds", 1.0)))
                    order["progress_ratio"] = min(1.0, public_site.build_progress / duration)
                    builder._activity_total = duration
                    builder.builder_work_timer = public_site.build_progress
                    if public_site.is_complete():
                        order["status"] = "COMPLETE"
                        order["progress_ratio"] = 1.0
                        builder.task = "IDLE"
                        builder._activity_total = 0.0
                        builder.builder_work_timer = 0.0
                        builder.say(f"Finished {public_site.name}.", duration=3.0)
                else:
                    builder._activity_total = 0.0
                    builder.builder_work_timer = 0.0
                return True

        if public_repair:
            order = public_repair.construction_order
            if order.get("builder_id") is None:
                order["builder_id"] = str(builder.id)
            if order.get("status") in ("LANDLORD_RETRIEVING", "PAYMENT_TRAVELING"):
                builder.task = "IDLE"
                return False
            chest, totals = cls._materials_in_storage(
                builder, furniture_manager, stockpile_manager,
                payer_type=order.get("payer_type"),
                family_id=order.get("payer_family_id"))
            required = {item: max(0, int(amount))
                        for item, amount in BUILDER_REPAIR_MATERIALS.items() if int(amount) > 0}
            missing = {item: max(0, amount - int(totals.get(item, 0)))
                       for item, amount in required.items() if int(totals.get(item, 0)) < amount}
            if missing and cls._begin_restock(builder, missing, building_manager,
                                              furniture_manager, villager_manager,
                                              payer_type=order.get("payer_type"),
                                              family_id=order.get("payer_family_id"),
                                              exact_only=True):
                order["status"] = "AWAITING_MATERIAL"
                return True
            if not order.get("materials_committed"):
                delivered = cls._deliver_build_materials(
                    builder, public_repair, order, required, chest, dt,
                    all_entities, player, building_manager, furniture_manager,
                    furniture_target=True, stockpile_manager=stockpile_manager,
                )
                if not order.get("materials_committed"):
                    order["status"] = "AWAITING_MATERIAL"
                    if (missing and builder.task != "BUILDER_COLLECTING_MATERIALS"
                            and not any(int(totals.get(item, 0)) > 0 for item in missing)):
                        order["builder_id"] = None
                    if missing and not getattr(builder, "target_restock_market", None):
                        builder.say("I need repair materials, but none are available to buy right now.", duration=2.5)
                    elif not delivered and builder.task == "BUILDER_COLLECTING_MATERIALS":
                        builder.say("I am carrying repair materials from storage.", duration=2.0)
                    return True
            if cls._block_until_tools_ready(builder):
                return True
            builder.task = "BUILDER_REPAIRING"
            arrived = cls._within_asset_work_range(builder, public_repair)
            if not arrived:
                target_x, target_y = cls._asset_approach_point(
                    builder, public_repair, order, all_entities, building_manager,
                )
                builder._move_towards(
                    target_x, target_y, dt,
                    arrival_dist=cls._asset_approach_arrival_distance(
                        public_repair, target_x, target_y
                    ),
                    all_entities=all_entities, player=player,
                    building_manager=building_manager, furniture_manager=furniture_manager,
                    recover_blocked_routes=True,
                    interaction_target=public_repair,
                )
                arrived = cls._within_asset_work_range(builder, public_repair)
            if arrived:
                order["status"] = "BUILDING"
                public_repair.construction_progress = getattr(public_repair, "construction_progress", 0.0) + dt
                duration = max(1.0, float(order.get("build_duration_seconds", BUILDER_BUILD_DURATION_INGAME_HOURS)))
                order["progress_ratio"] = min(1.0, public_repair.construction_progress / duration)
                builder._activity_total = duration
                builder.builder_work_timer = public_repair.construction_progress
                if public_repair.construction_progress >= duration:
                    public_repair.condition = 1.0
                    order["status"] = "COMPLETE"
                    order["progress_ratio"] = 1.0
                    builder.task = "IDLE"
                    builder._activity_total = 0.0
                    builder.builder_work_timer = 0.0
                    builder.say(f"Repaired {public_repair.name}.", duration=3.0)
            else:
                builder._activity_total = 0.0
                builder.builder_work_timer = 0.0
            return True

        active = furniture_active
        if not active:
            return cls._stock_production_step(
                builder, dt, building_manager, furniture_manager,
                villager_manager, all_entities, player, day_cycle,
                stockpile_manager=stockpile_manager, permit_manager=permit_manager,
            )

        order = active.construction_order
        order["builder_id"] = str(builder.id)
        if order.get("status") not in ("PAID", "BUILDING", "AWAITING_MATERIAL"):
            return True

        cfg = DEDICATED_JOBS.get("Builder", {})
        chest, totals = cls._materials_in_storage(
            builder, furniture_manager, stockpile_manager,
            payer_type=order.get("payer_type"),
            family_id=order.get("payer_family_id"))
        is_repair = order.get("order_type") == "REPAIR"
        recipe = FURNITURE_TYPES.get(active.furniture_type, {})
        material_recipe = BUILDER_REPAIR_MATERIALS if is_repair else recipe.get("materials", {})
        required = {item: max(0, int(amount))
                    for item, amount in material_recipe.items() if int(amount) > 0}
        short_recipe = {item: amount - int(totals.get(item, 0)) for item, amount in required.items()
                        if totals.get(item, 0) < amount}
        missing = dict(short_recipe)
        if missing and cls._begin_restock(builder, missing, building_manager, furniture_manager, villager_manager,
                                          exact_only=True):
            return True
        if short_recipe:
            builder.say("I need this furniture's materials, but none are available to buy right now.", duration=2.5)
            return True

        if not order.get("materials_committed"):
            delivered = cls._deliver_build_materials(
                builder, active, order, required, chest, dt,
                all_entities, player, building_manager, furniture_manager,
                furniture_target=True, stockpile_manager=stockpile_manager,
            )
            if not order.get("materials_committed"):
                order["status"] = "AWAITING_MATERIAL"
                if not delivered and builder.task == "BUILDER_COLLECTING_MATERIALS":
                    builder.say("I am carrying the furniture materials from storage.", duration=2.0)
                return True
            order["status"] = "BUILDING"

        if cls._block_until_tools_ready(builder):
            return True
        builder.task = "BUILDER_REPAIRING" if is_repair else "BUILDER_CONSTRUCTING"
        builder.active_tool = None if is_repair else (cfg.get("required_tools") or ["Saw"])[0]
        target = cls._asset_approach_point(
            builder, active, order, all_entities, building_manager,
        )
        arrived = cls._within_asset_work_range(builder, active)
        if arrived:
            builder.is_moving = False
            builder.current_path = []
            builder.path_index = 0
            builder.path_target = None
        else:
            builder._move_towards(
                target[0], target[1], dt,
                arrival_dist=cls._asset_approach_arrival_distance(active, target[0], target[1]),
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                recover_blocked_routes=True,
                interaction_target=active,
            )
            arrived = cls._within_asset_work_range(builder, active)
        if not arrived and getattr(builder, "route_state", None) == ROUTE_STATE_FAILED:
            previous_target = tuple(target)
            failed_points = getattr(builder, "builder_failed_approach_points", set())
            failed_points.add(previous_target)
            builder.builder_failed_approach_points = failed_points
            alternate = active.get_approach_point(
                builder.x, builder.y, worker_id=builder.id,
                all_entities=all_entities, tile_size=TILE_SIZE,
                bm=building_manager, excluded_points=failed_points,
            )
            if alternate is None:
                center = active.get_world_pos(TILE_SIZE)
                if tuple(center) not in failed_points:
                    alternate = center
                elif not getattr(builder, "speech_text", None):
                    builder.say(f"I cannot reach {active.name}; the route is blocked.", duration=3.0)
            if alternate is not None and tuple(alternate) not in failed_points:
                builder.builder_target_position = alternate
                builder.path_target = None
                builder.current_path = []
                builder.path_index = 0
                builder.path_retry_timer = 0.0
        if arrived:
            day_seconds = day_cycle.day_length_seconds if day_cycle else DAY_LENGTH_OPTIONS[DEFAULT_DAY_LENGTH_INDEX]["seconds"]
            seconds_per_hour = day_seconds / 24
            duration = max(1.0, seconds_per_hour * BUILDER_BUILD_DURATION_INGAME_HOURS)
            active.construction_progress += dt
            order["progress_ratio"] = min(1.0, active.construction_progress / duration)
            builder._activity_total = duration
            builder.builder_work_timer = active.construction_progress
            if active.construction_progress >= duration:
                order["status"] = "COMPLETE"
                order["progress_ratio"] = 1.0
                if is_repair:
                    active.condition = 1.0
                builder.task = "IDLE"
                builder._activity_total = 0.0
                builder.builder_work_timer = 0.0
                builder.active_tool = None
                builder.builder_payment_order_id = None
                builder.builder_target_order_id = None
                builder.builder_target_position = None
                builder.builder_failed_approach_points = set()
                builder.say(f"Repaired {active.name}." if is_repair else f"Finished {active.name}.", duration=3.0)
                furniture_manager.invalidate_cache()
        else:
            builder._activity_total = 0.0
            builder.builder_work_timer = 0.0
        return True

    @classmethod
    def sweep_dead_commission_orders(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem.sweep_dead_commission_orders(*args, **kwargs)

    @classmethod
    def _begin_commission_refund(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._begin_commission_refund(*args, **kwargs)

    @classmethod
    def _dispatch_servant_refund(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._dispatch_servant_refund(*args, **kwargs)

    @classmethod
    def _dispatch_villager_refund(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._dispatch_villager_refund(*args, **kwargs)

    @classmethod
    def _clear_refund_task(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._clear_refund_task(*args, **kwargs)

    @classmethod
    def _update_refund_task(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._update_refund_task(*args, **kwargs)

    @classmethod
    def _refund_collect_step(cls, *args, **kwargs):
        from game.systems.work.artisan_commission import ArtisanCommissionSystem
        return ArtisanCommissionSystem._refund_collect_step(*args, **kwargs)

    @classmethod
    def _consume_household_materials(cls, recipe, chest, family_id, stockpile_manager):
        """Consume required recipe quantities from household chest and/or family ground stacks."""
        for mat, qty in (recipe or {}).items():
            rem = max(0, int(qty))
            if rem <= 0:
                continue
            if chest is not None and hasattr(chest, "take_item"):
                taken = chest.take_item(mat, rem)
                rem -= taken
            if rem > 0 and stockpile_manager is not None and family_id is not None:
                for stack in list(getattr(stockpile_manager, "stacks", [])):
                    if rem <= 0:
                        break
                    if (getattr(stack, "resource_type", "") == mat
                            and str(getattr(stack, "owner_id", "")) == str(family_id)):
                        avail = max(0, int(getattr(stack, "amount", 0) or 0))
                        take = min(rem, avail)
                        if take > 0:
                            stack.amount -= take
                            rem -= take
                            if stack.amount <= 0 and stack in stockpile_manager.stacks:
                                stockpile_manager.stacks.remove(stack)

    @classmethod
    def _stock_production_step(cls, builder, dt, building_manager, furniture_manager,
                               villager_manager, all_entities, player, day_cycle,
                               stockpile_manager=None, permit_manager=None):
        """Proactively craft furniture items into household storage for Tab Product quotas."""
        if cls._block_until_tools_ready(builder):
            return False

        needed_item = ProductionSystem.get_next_needed_product(
            "Builder", building_manager, furniture_manager, stockpile_manager
        )
        if needed_item is None:
            builder._builder_stock_craft = None
            return False

        benches = [
            f for f in getattr(furniture_manager, "furnitures", [])
            if getattr(f, "furniture_type", "") == "builder_workbench"
            and not getattr(f, "is_dropped", False)
            and getattr(f, "stored_in_id", None) is None
            and not getattr(f, "is_broken", False)
            and not (isinstance(getattr(f, "construction_order", None), dict)
                     and f.construction_order.get("status") not in (None, "COMPLETE"))
        ]
        if not benches:
            return False

        item_id = needed_item["id"]
        recipe = {m: int(q) for m, q in (needed_item.get("recipe", {}) or {}).items() if int(q) > 0}
        chest, totals = cls._materials_in_storage(builder, furniture_manager, stockpile_manager)
        short = {
            m: q - int(totals.get(m, 0) or 0)
            for m, q in recipe.items()
            if int(totals.get(m, 0) or 0) < q
        }
        if short:
            if cls._begin_restock(builder, short, building_manager, furniture_manager,
                                  villager_manager, exact_only=True):
                builder.active_tool = None
                return True
            return False

        bench = min(benches, key=lambda b: math.hypot(
            b.get_world_pos(TILE_SIZE)[0] - builder.x,
            b.get_world_pos(TILE_SIZE)[1] - builder.y,
        ))
        dest = bench.get_approach_point(
            builder.x, builder.y, worker_id=builder.id,
            all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
        )
        builder.task = "BUILDER_CRAFTING"
        builder.active_tool = "Hammer" if int((getattr(builder, "inventory", {}) or {}).get("Hammer", 0)) > 0 else None
        arrived = builder._move_towards(
            dest[0], dest[1], dt, arrival_dist=CHEST_INTERACTION_RADIUS,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=bench,
        )
        if not arrived:
            return True

        day_seconds = day_cycle.day_length_seconds if day_cycle else DAY_LENGTH_OPTIONS[DEFAULT_DAY_LENGTH_INDEX]["seconds"]
        seconds_per_hour = day_seconds / 24.0
        duration = max(1.0, seconds_per_hour * float(PRODUCTION_BUILDER_CRAFT_HOURS))

        state = getattr(builder, "_builder_stock_craft", None)
        if not isinstance(state, dict) or state.get("item_id") != item_id:
            state = {"item_id": item_id, "progress": 0.0, "needed": duration}
            builder._builder_stock_craft = state

        state["progress"] = float(state.get("progress", 0.0)) + dt
        builder._activity_total = duration
        builder.builder_work_timer = state["progress"]
        if state["progress"] >= duration:
            fam_id = getattr(builder, "family_id", None)
            cls._consume_household_materials(recipe, chest, fam_id, stockpile_manager)
            ProductionSystem.store_crafted_product(
                builder, item_id,
                furniture_manager=furniture_manager,
                building_manager=building_manager,
                stockpile_manager=stockpile_manager,
                permit_manager=permit_manager,
                workbench=bench,
            )
            builder._builder_stock_craft = None
            builder.builder_work_timer = 0.0
            builder._activity_total = 0.0
            builder.task = "IDLE"
            builder.active_tool = None
            builder.say(f"Crafted {needed_item['name']} for stock!", duration=2.2)
        return True

