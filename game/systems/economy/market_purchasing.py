"""
AI Food Purchasing & Market Transaction System (Agent 3)

Coordinates the complete, realistic physical market food purchasing workflow for villagers:
1. Household food stock check (Zero remote purchases when food is available at home).
2. Family coordination (Prevents duplicate simultaneous purchases by household members).
3. Nearest eligible market selection (Valid stock, configured price, affordable quantities).
4. Physical coin retrieval from household storage (Real money transfer to villager pocket).
5. Physical navigation to Market interaction position (Zero teleportation or remote purchasing).
6. Atomic market transaction at Market location (Exact payment, currency conservation, change calculation).
7. Physical hauling back to household storage.
8. Safe deposit of change, food consumption, hunger restoration, and activity resumption.
"""

import math
from game.config import (
    TILE_SIZE,
    AI_NEED_MAX,
    AI_NEED_FOOD_RESTORE,
    AI_NEED_SEEK_COOLDOWN_SECONDS,
)
from game.data.config import is_food_item, CHEST_INTERACTION_RADIUS, VILLAGER_INVENTORY_CAPACITY
from game.systems.economy.currency import (
    to_copper,
    normalize_wallet,
    calculate_payment_and_change,
    transfer_currency_value,
    execute_currency_transfer,
    CURRENCY_DENOMINATIONS,
    canonical_denomination,
)
from game.systems.economy.market_service import MarketService
from game.systems.economy.household_inventory import get_inventory_room
from game.world.navigation.navigation import find_nearest_target


def _inventory_room(inventory):
    return get_inventory_room(inventory, VILLAGER_INVENTORY_CAPACITY)


class AIFoodPurchasingSystem:
    """
    Dedicated modular controller for AI Food Purchasing (Agent 3).
    """

    @classmethod
    def get_household_ground_currency(cls, villager, stockpile_manager=None):
        """Return currency dropped by this household, using the same ownership rules as loose-item recovery."""
        manager = stockpile_manager or getattr(villager, "stockpile_manager", None)
        family_id = str(getattr(villager, "family_id", ""))
        wallet = {}
        if not manager or not family_id:
            return wallet
        for stack in getattr(manager, "stacks", []):
            if getattr(stack, "owner_type", None) != "villager" or str(getattr(stack, "owner_id", "")) != family_id:
                continue
            denomination = canonical_denomination(getattr(stack, "resource_type", ""))
            if denomination and getattr(stack, "amount", 0) > 0:
                wallet[denomination] = wallet.get(denomination, 0) + int(stack.amount)
        return wallet

    @classmethod
    def find_nearest_household_currency_stack(cls, villager, stockpile_manager=None,
                                               building_manager=None, furniture_manager=None):
        manager = stockpile_manager or getattr(villager, "stockpile_manager", None)
        family_id = str(getattr(villager, "family_id", ""))
        candidates = [
            stack for stack in getattr(manager, "stacks", [])
            if getattr(stack, "owner_type", None) == "villager"
            and str(getattr(stack, "owner_id", "")) == family_id
            and canonical_denomination(getattr(stack, "resource_type", ""))
            and getattr(stack, "amount", 0) > 0
        ] if manager and family_id else []
        stack, _, _ = find_nearest_target(
            (villager.x, villager.y), candidates,
            lambda candidate: ((candidate.grid_x + 0.5) * TILE_SIZE,
                               (candidate.grid_y + 0.5) * TILE_SIZE),
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            tile_size=TILE_SIZE,
        )
        return stack

    @classmethod
    def get_household_spendable_wallet(cls, villager, furniture_manager=None,
                                       villager_manager=None, stockpile_manager=None):
        """
        Merged read-only view of every coin source the household can spend on
        market goods: storage chest + family purse + living members' pockets
        (same abstract-wallet rule as commission payments) + family-owned
        ground coin stacks. Used only for affordability checks — physical
        collection still goes through retrieve_coins_from_storage /
        BUYING_FOOD_RETRIEVE_GROUND_COINS.
        """
        wallet = {"Copper": 0, "Silver": 0, "Gold": 0}

        def _add(source):
            for denom, count in normalize_wallet(source).items():
                wallet[denom] = wallet.get(denom, 0) + count

        fam_id = getattr(villager, "family_id", None)
        fam_str = str(fam_id or "")
        vm = villager_manager or getattr(villager, "villager_manager", None)

        # 1. Household storage chest
        chest = furniture_manager.get_storage_for_family(fam_str) if (furniture_manager and fam_str) else None
        if chest and isinstance(getattr(chest, "inventory", None), dict):
            _add(chest.inventory)

        # 2. Family purse + every living member's pocket inventory
        fam = vm.get_family_by_id(fam_str) if (vm and fam_str) else None
        if fam is not None:
            if isinstance(getattr(fam, "currency", None), dict):
                _add(fam.currency)
            members = getattr(fam, "members", []) or []
            rep_counted = False
            for member in members:
                if getattr(member, "is_alive", True) and isinstance(getattr(member, "inventory", None), dict):
                    _add(member.inventory)
                    if member is villager:
                        rep_counted = True
            if not rep_counted:
                _add(getattr(villager, "inventory", {}))
        else:
            _add(getattr(villager, "inventory", {}))

        # 3. Family-owned loose coin stacks on the ground
        _add(cls.get_household_ground_currency(villager, stockpile_manager))
        return wallet

    @classmethod
    def _family_abstract_wallets(cls, villager, villager_manager=None):
        """Lazy delegate to BuilderSystem._family_abstract_wallets (family purse
        + living member pockets) — identical coin sources to commission payments."""
        from game.systems.work.builder_system import BuilderSystem
        fam_id = getattr(villager, "family_id", None)
        vm = villager_manager or getattr(villager, "villager_manager", None)
        return BuilderSystem._family_abstract_wallets(fam_id, vm)

    @classmethod
    def check_household_has_food(cls, villager, furniture_manager=None, villager_manager=None, stockpile_manager=None):
        """
        Returns True if the household already possesses at least 1 FOOD-category item.
        Zero hardcoded item names: uses is_food_item().
        """
        avail = MarketService.get_household_available_food_stock(
            villager,
            furniture_manager=furniture_manager,
            villager_manager=villager_manager,
            stockpile_manager=stockpile_manager
        )
        return MarketService.get_household_food_need(
            villager, furniture_manager=furniture_manager,
            villager_manager=villager_manager, stockpile_manager=stockpile_manager
        ) <= 0

    @classmethod
    def get_household_purchase_quantity(cls, villager, market, food_item, furniture_manager=None,
                                       villager_manager=None, stockpile_manager=None):
        need = MarketService.get_household_food_need(
            villager, furniture_manager=furniture_manager,
            villager_manager=villager_manager, stockpile_manager=stockpile_manager
        )
        stock = MarketService.get_market_stock(food_item, market)
        wallet = cls.get_household_spendable_wallet(
            villager, furniture_manager=furniture_manager,
            villager_manager=villager_manager, stockpile_manager=stockpile_manager,
        )
        unit_price = MarketService.get_item_price(food_item, market)
        affordable = to_copper(wallet) // max(1, unit_price)
        return max(0, min(need, stock, affordable))

    @classmethod
    def is_market_available(cls, market, item_name, quantity=1):
        """Validate a specific stall against its live listing and stock before travel or purchase."""
        if not market or getattr(market, "building_type", "") != "market":
            return False
        if getattr(market, "is_under_construction", False):
            return False
        return (
            MarketService.is_item_for_sale(market, item_name)
            and MarketService.get_market_stock(item_name, market) >= max(1, int(quantity))
        )

    @classmethod
    def is_family_member_purchasing_food(cls, villager, villager_manager=None):
        """
        Prevents multiple household members from independently purchasing duplicate food
        because they checked the inventory simultaneously.
        """
        if not villager_manager or not getattr(villager, "family_id", None):
            return False

        fam = villager_manager.get_family_by_id(villager.family_id)
        if not fam:
            return False

        for member in getattr(fam, "members", []):
            if member != villager and getattr(member, "task", "") in (
                "SEEKING_FOOD",
                "BUYING_FOOD_RETRIEVE_COINS",
                "BUYING_FOOD_RETRIEVE_GROUND_COINS",
                "BUYING_FOOD_TRAVEL_TO_MARKET",
                "BUYING_FOOD_HAULING_HOME"
            ):
                return True
        return False

    @classmethod
    def find_nearest_eligible_market(cls, villager, building_manager, furniture_manager=None, villager_manager=None, preferred_food=None, stockpile_manager=None):
        """
        Finds the nearest completed Market that:
        1. Sells an eligible food item (is_food_item).
        2. Has available stock (>= 1).
        3. Has a valid selling price (> 0).
        4. Household has sufficient funds to purchase.
        
        Returns:
            (market_obj, food_item_name, item_price_copper) or (None, None, 0)
        """
        if not building_manager:
            return None, None, 0

        # Calculate total household funds across every spendable coin source
        # (chest + family purse + member pockets + family-owned ground stacks)
        wallet = cls.get_household_spendable_wallet(
            villager, furniture_manager=furniture_manager,
            villager_manager=villager_manager, stockpile_manager=stockpile_manager,
        )
        total_funds_copper = to_copper(wallet)

        completed_markets = [
            b for b in building_manager.buildings
            if getattr(b, "building_type", "") == "market" and not getattr(b, "is_under_construction", False)
        ]

        if not completed_markets:
            return None, None, 0

        candidates = []

        for m in completed_markets:
            inv = getattr(m, "inventory", {})
            if not isinstance(inv, dict):
                continue

            # Determine food items sold by this market with stock >= 1
            available_foods = []
            for item_name, count in inv.items():
                if count > 0 and is_food_item(item_name) and MarketService.is_item_for_sale(m, item_name):
                    if preferred_food is None or item_name == preferred_food:
                        available_foods.append(item_name)

            for food_item in available_foods:
                unit_price = MarketService.get_item_price(food_item, m)
                if unit_price <= 0:
                    continue  # Food is never free! Must have configured price > 0

                if total_funds_copper >= unit_price:
                    try:
                        _, _, dist = find_nearest_target(
                            (villager.x, villager.y), [m],
                            lambda market: market.get_approach_point(
                                (villager.x, villager.y), TILE_SIZE, building_manager
                            ),
                            building_manager=building_manager,
                            furniture_manager=furniture_manager,
                            tile_size=TILE_SIZE,
                        )
                    except Exception:
                        dist = float("inf")
                    if not math.isfinite(dist):
                        continue
                    candidates.append((unit_price, dist, m, food_item))

        if not candidates:
            return None, None, 0

        # Prefer the cheapest available food; use travel distance to break equal-price ties.
        candidates.sort(key=lambda c: (c[0], c[1]))
        best_candidate = candidates[0]
        return best_candidate[2], best_candidate[3], best_candidate[0]

    @classmethod
    def retrieve_coins_from_storage(cls, villager, price_in_copper, furniture_manager=None,
                                    villager_manager=None):
        """
        Transfers required coins into the villager's pocket from every coin
        source the household can spend: storage chest first, then the
        abstract household wallets (family purse + living members' pockets) —
        the same sources commission payments use. Works without a chest.
        Ensures zero free money creation, conservation of currency.
        Returns:
            (success: bool, message: str)
        """
        if not hasattr(villager, "inventory") or not isinstance(villager.inventory, dict):
            villager.inventory = {}

        def _pocket_copper():
            return to_copper(normalize_wallet(villager.inventory))

        if _pocket_copper() >= price_in_copper:
            return True, "Villager already carries enough coins in pocket."

        # 1. Household storage chest (partial withdrawal allowed — the
        #    remainder is collected from abstract wallets below).
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            chest_copper = to_copper(normalize_wallet(chest.inventory))
            if chest_copper > 0:
                take = min(price_in_copper - _pocket_copper(), chest_copper)
                ok, _ = transfer_currency_value(chest.inventory, villager.inventory, take)
                if ok and _pocket_copper() >= price_in_copper:
                    return True, "Successfully retrieved coins from household storage."

        # 2. Abstract household wallets: family purse + living members'
        #    pockets. No chest or physical stack required — identical to the
        #    commission payment collection rule.
        deficit = price_in_copper - _pocket_copper()
        if deficit > 0:
            for wallet in cls._family_abstract_wallets(villager, villager_manager):
                if deficit <= 0:
                    break
                if wallet is villager.inventory:
                    continue  # own pocket already counted
                wallet_copper = to_copper(normalize_wallet(wallet))
                if wallet_copper <= 0:
                    continue
                ok, _ = transfer_currency_value(
                    wallet, villager.inventory, min(deficit, wallet_copper)
                )
                if ok:
                    deficit = price_in_copper - _pocket_copper()

        if deficit <= 0:
            return True, "Successfully retrieved coins from household wallets."
        return False, "Household does not have enough coins for the purchase."

    @classmethod
    def execute_market_transaction(cls, villager, market, food_item, building_manager=None, quantity=1, day_number=None):
        """
        Executes the atomic purchase transaction physically at the Market interaction location.
        Returns:
            (success: bool, message: str)
        """
        if not market or not hasattr(market, "inventory"):
            return False, "Market building is invalid or missing."

        if not MarketService.is_item_for_sale(market, food_item):
            return False, f"{food_item} is not listed for sale at this market."

        stock = market.inventory.get(food_item, 0)
        if stock < quantity:
            return False, f"Market ran out of {food_item} while traveling."
        if _inventory_room(getattr(villager, "inventory", {})) < quantity:
            return False, "Villager inventory is full."

        unit_price = MarketService.get_item_price(food_item, market)
        if unit_price <= 0:
            return False, "Item has invalid selling price."

        vil_wallet = normalize_wallet(getattr(villager, "inventory", {}))
        vil_copper = to_copper(vil_wallet)
        total_price = unit_price * quantity
        if vil_copper < total_price:
            return False, f"Villager has insufficient coins in pocket ({vil_copper}c < {total_price}c)."

        if not hasattr(market, "currency") or not isinstance(market.currency, dict):
            market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        # Calculate exact payment & change
        ok, payment, change, msg = calculate_payment_and_change(vil_wallet, total_price, market.currency)
        if not ok:
            return False, f"Cannot resolve payment/change: {msg}"

        # Execute currency transfer between villager pocket and market
        transfer_ok, new_vil_w, new_mkt_w, t_msg = execute_currency_transfer(
            villager.inventory, market.currency, payment, change
        )
        if not transfer_ok:
            return False, f"Currency transfer failed: {t_msg}"

        # Deduct item from market stock
        market.inventory[food_item] -= quantity
        if market.inventory[food_item] <= 0:
            del market.inventory[food_item]
        from game.systems.economy.market_pricing import MarketPricingSystem
        MarketPricingSystem.update_market_prices(market)

        # Add item to villager inventory
        villager.inventory[food_item] = villager.inventory.get(food_item, 0) + quantity

        from game.systems.economy.market_sales_report import MarketSalesReportSystem
        MarketSalesReportSystem.record_sale(market, food_item, quantity, unit_price, day_number)

        return True, f"Successfully purchased {quantity}x {food_item} for {total_price} Copper."

    @classmethod
    def deliver_and_consume_food(cls, villager, furniture_manager=None, stockpile_manager=None,
                                 day_number=1):
        """
        Delivers change back to household storage, consumes purchased food,
        recovers hunger, and resumes activity.
        Households without a storage chest receive owner-tagged loose stacks
        dropped at the villager's feet — the same fallback tool deliveries
        use — so family members can still collect and consume the goods.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        fam_str = str(getattr(villager, "family_id", "") or "")
        ground_drop = stockpile_manager is not None and bool(fam_str)

        def _drop_loose(item_name, amount):
            if not ground_drop or amount <= 0:
                return False
            gx = int(math.floor(getattr(villager, "x", 0.0) / TILE_SIZE))
            gy = int(math.floor(getattr(villager, "y", 0.0) / TILE_SIZE))
            stockpile_manager.drop_resource(
                item_name, amount, gx, gy,
                owner_type="villager", owner_id=fam_str,
            )
            return True

        # 1. Return any coins (change or leftover funds) back to household storage
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            from game.systems.economy.currency import compact_currency_wallet
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                    del villager.inventory[denom]
            compact_currency_wallet(chest.inventory)
        elif ground_drop:
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0 and _drop_loose(denom, amt):
                    del villager.inventory[denom]

        # 2. Consume 1 food item from villager's inventory
        food_it = next((it for it, c in getattr(villager, "inventory", {}).items() if is_food_item(it) and c > 0), None)
        if food_it:
            villager.inventory[food_it] -= 1
            if villager.inventory[food_it] <= 0:
                del villager.inventory[food_it]

            villager.hunger = min(AI_NEED_MAX, villager.hunger + AI_NEED_FOOD_RESTORE)
            villager.hunger_death_timer = None
            villager.daily_food_consumed += 1
            from game.systems.village_life.happiness_system import HappinessSystem
            HappinessSystem.record_food_eaten(villager, food_it, day_number)
            villager.say(f"Ate hearty meal of {food_it} brought from Market!", duration=2.5)

        # 3. If any extra food remains, store it in the chest — or drop it
        #    as owner-tagged loose stacks when the household has no chest.
        if chest:
            for it, c in list(getattr(villager, "inventory", {}).items()):
                if is_food_item(it) and c > 0:
                    chest.store_item(it, c)
                    del villager.inventory[it]
        elif ground_drop:
            for it, c in list(getattr(villager, "inventory", {}).items()):
                if is_food_item(it) and c > 0 and _drop_loose(it, c):
                    del villager.inventory[it]

        # 4. Clear purchasing tracking attributes
        villager.purchase_target_market_id = None
        villager.purchase_target_market_location = None
        villager.purchase_food_item = None
        villager.purchase_target_price = 0

        # 5. Safely resume next activity or return to idle
        villager._resume_or_idle_after_need()

    @classmethod
    def return_coins_to_storage(cls, villager, furniture_manager=None, stockpile_manager=None):
        """
        Safety fallback: returns coins back to household storage if purchasing failed or aborted.
        Without a chest, coins become owner-tagged loose stacks at the villager's feet.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        fam_str = str(getattr(villager, "family_id", "") or "")
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            from game.systems.economy.currency import compact_currency_wallet
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                    del villager.inventory[denom]
            compact_currency_wallet(chest.inventory)
        elif stockpile_manager is not None and fam_str:
            gx = int(math.floor(getattr(villager, "x", 0.0) / TILE_SIZE))
            gy = int(math.floor(getattr(villager, "y", 0.0) / TILE_SIZE))
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    stockpile_manager.drop_resource(
                        denom, amt, gx, gy,
                        owner_type="villager", owner_id=fam_str,
                    )
                    del villager.inventory[denom]

        villager.purchase_target_market_id = None
        villager.purchase_target_market_location = None
        villager.purchase_food_item = None
        villager.purchase_target_price = 0
        villager.task = "IDLE"
        villager._set_need_seek_cooldown(
            AI_NEED_SEEK_COOLDOWN_SECONDS,
            task="SEEKING_FOOD",
        )


class AIMarketPurchasingSystem:
    """
    Universal Market Purchasing System for AI (Agent 3).
    Handles needed materials purchasing (e.g. Wood and Stone restocking for Gravedigger).
    """
    execute_market_transaction = AIFoodPurchasingSystem.execute_market_transaction
    find_nearest_eligible_market = AIFoodPurchasingSystem.find_nearest_eligible_market

    @classmethod
    def withdraw_household_coins(cls, villager, amount, furniture_manager=None, villager_manager=None):
        """Move enough household currency into the worker's inventory for a purchase."""
        pocket = getattr(villager, "inventory", {})
        deficit = max(0, int(amount) - to_copper(pocket))
        if deficit <= 0:
            return True, "Enough coins are already in the worker's inventory."

        _, source = MarketService.get_household_funds_and_source(
            villager, furniture_manager, villager_manager
        )
        if not source or source is pocket:
            return False, "Household funds are unavailable."

        source_wallet = normalize_wallet(source)
        if to_copper(source_wallet) < deficit:
            return False, "Household does not have enough coins for the purchase."

        return transfer_currency_value(source, pocket, deficit)

    @classmethod
    def find_market_for_items(cls, villager, requested_items, building_manager, furniture_manager=None, villager_manager=None):
        """Find the nearest market that can sell at least one affordable required item."""
        if not building_manager or not requested_items:
            return None, {}, 0

        wallet, source = MarketService.get_household_funds_and_source(villager, furniture_manager, villager_manager)
        pocket_funds = to_copper(normalize_wallet(getattr(villager, "inventory", {})))
        available_funds = to_copper(wallet) + (0 if source is getattr(villager, "inventory", None) else pocket_funds)
        best_market = None
        best_items = {}
        best_cost = 0
        best_rank = None

        for market in getattr(building_manager, "buildings", []):
            if getattr(market, "building_type", "") != "market" or getattr(market, "is_under_construction", False):
                continue

            purchase_items, total_cost = cls.get_affordable_item_quantities(
                requested_items, market, available_funds,
                inventory_room=_inventory_room(getattr(villager, "inventory", {})),
            )
            if not purchase_items or total_cost <= 0:
                continue

            _, _, distance = find_nearest_target(
                (villager.x, villager.y), [market],
                lambda candidate: candidate.get_approach_point(
                    (villager.x, villager.y), TILE_SIZE, building_manager
                ),
                building_manager=building_manager,
                furniture_manager=furniture_manager,
                tile_size=TILE_SIZE,
            )
            if not math.isfinite(distance):
                continue
            # Choose the lowest complete affordable cart first; use path distance only to break price ties.
            unfilled = sum(max(0, int(qty) - purchase_items.get(name, 0)) for name, qty in requested_items.items())
            rank = (unfilled, total_cost, distance)
            if best_rank is None or rank < best_rank:
                best_market = market
                best_items = purchase_items
                best_cost = total_cost
                best_rank = rank

        return best_market, best_items, best_cost

    @classmethod
    def get_affordable_item_quantities(cls, requested_items, market, available_funds, inventory_room=None):
        """Build a partial purchase cart capped by each requirement, market stock, and funds."""
        if not market or not isinstance(requested_items, dict):
            return {}, 0

        remaining_funds = max(0, int(available_funds))
        remaining_room = max(0, int(inventory_room)) if inventory_room is not None else int(VILLAGER_INVENTORY_CAPACITY)
        purchase_items = {}
        total_cost = 0
        inventory = getattr(market, "inventory", {})
        for item_name, requested_quantity in requested_items.items():
            if not MarketService.is_item_for_sale(market, item_name):
                continue
            unit_price = MarketService.get_item_price(item_name, market)
            market_stock = max(0, int(inventory.get(item_name, 0)))
            required = max(0, int(requested_quantity))
            if unit_price <= 0 or market_stock <= 0 or required <= 0:
                continue

            quantity = min(required, market_stock, remaining_funds // unit_price, remaining_room)
            if quantity <= 0:
                continue
            purchase_items[item_name] = quantity
            remaining_room -= quantity
            item_cost = quantity * unit_price
            total_cost += item_cost
            remaining_funds -= item_cost

        return purchase_items, total_cost

    @classmethod
    def execute_items_transaction(cls, villager, market, requested_items, day_number=None):
        """Buy the requested affordable item quantities atomically."""
        if not market or not requested_items:
            return False, "Market or requested items are unavailable."

        if sum(max(0, int(qty)) for qty in requested_items.values()) > _inventory_room(villager.inventory):
            return False, "Villager inventory is full."

        total_cost = 0
        for item_name, quantity in requested_items.items():
            if not MarketService.is_item_for_sale(market, item_name):
                return False, f"{item_name} is not listed for sale at this market."
            if getattr(market, "inventory", {}).get(item_name, 0) < quantity:
                return False, f"Insufficient stock of {item_name}."
            total_cost += MarketService.get_item_price(item_name, market) * quantity

        market.currency = getattr(market, "currency", None)
        if not isinstance(market.currency, dict):
            market.currency = {denom: 0 for denom in CURRENCY_DENOMINATIONS}
        can_pay, payment, change, _ = calculate_payment_and_change(
            getattr(villager, "inventory", {}), total_cost, market.currency
        )
        if not can_pay:
            return False, "Insufficient coins for the requested tools."
        transferred, _, _, error = execute_currency_transfer(
            villager.inventory, market.currency, payment, change
        )
        if not transferred:
            return False, f"Currency transfer failed: {error}"

        for item_name, quantity in requested_items.items():
            unit_price = MarketService.get_item_price(item_name, market)
            market.inventory[item_name] -= quantity
            if market.inventory[item_name] <= 0:
                del market.inventory[item_name]
            villager.inventory[item_name] = villager.inventory.get(item_name, 0) + quantity
            from game.systems.economy.market_sales_report import MarketSalesReportSystem
            MarketSalesReportSystem.record_sale(market, item_name, quantity, unit_price, day_number)

        from game.systems.economy.market_pricing import MarketPricingSystem
        MarketPricingSystem.update_market_prices(market)
        return True, "Purchased all required tools."

    @classmethod
    def check_gravedigger_stock(cls, villager, furniture_manager=None):
        """
        Target: 5 Wood, 5 Stone in assigned household chest.
        Returns dict with missing amounts: e.g. {"Wood": X, "Stone": Y}.
        """
        if not furniture_manager or not getattr(villager, "family_id", None):
            return {}
        chest = furniture_manager.get_storage_for_family(villager.family_id)
        if not chest or not hasattr(chest, "inventory"):
            return {}
        from game.config import GRAVEDIGGER_TARGET_WOOD, GRAVEDIGGER_TARGET_STONE
        cur_wood = chest.inventory.get("Wood", 0)
        cur_stone = chest.inventory.get("Stone", 0)
        missing = {}
        if cur_wood < GRAVEDIGGER_TARGET_WOOD:
            missing["Wood"] = GRAVEDIGGER_TARGET_WOOD - cur_wood
        if cur_stone < GRAVEDIGGER_TARGET_STONE:
            missing["Stone"] = GRAVEDIGGER_TARGET_STONE - cur_stone
        return missing

    @classmethod
    def find_nearest_market_for_material(cls, villager, material_name, needed_amount, building_manager, furniture_manager=None, villager_manager=None):
        """
        Finds completed market selling material_name with available stock > 0, price > 0,
        and verifies household has enough coins to buy at least 1 unit.
        Returns: (market_obj, unit_price_copper, max_affordable_qty) or (None, 0, 0)
        """
        if not building_manager:
            return None, 0, 0
        from game.systems.economy.currency import to_copper
        wallet, source = MarketService.get_household_funds_and_source(villager, furniture_manager, villager_manager)
        pocket = getattr(villager, "inventory", {})
        pocket_funds = to_copper(normalize_wallet(pocket))
        total_funds = to_copper(wallet) + (0 if source is pocket else pocket_funds)
        if total_funds <= 0:
            return None, 0, 0

        completed_markets = [
            b for b in building_manager.buildings
            if getattr(b, "building_type", "") == "market" and not getattr(b, "is_under_construction", False)
        ]
        if not completed_markets:
            return None, 0, 0

        best_mkt = None
        best_price = 0
        best_qty = 0
        best_rank = None

        for m in completed_markets:
            inv = getattr(m, "inventory", {})
            if not MarketService.is_item_for_sale(m, material_name):
                continue
            stock = inv.get(material_name, 0)
            if stock <= 0:
                continue
            unit_price = MarketService.get_item_price(material_name, m)
            if unit_price <= 0:
                continue
            if total_funds < unit_price:
                continue

            affordable_qty = min(stock, needed_amount, total_funds // unit_price,
                                 _inventory_room(getattr(villager, "inventory", {})))
            if affordable_qty <= 0:
                continue

            _, _, d = find_nearest_target(
                (villager.x, villager.y), [m],
                lambda market: market.get_approach_point(
                    (villager.x, villager.y), TILE_SIZE, building_manager
                ),
                building_manager=building_manager,
                furniture_manager=furniture_manager,
                tile_size=TILE_SIZE,
            )
            if not math.isfinite(d):
                continue
            rank = (max(0, int(needed_amount) - affordable_qty), affordable_qty * unit_price, d)
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_mkt = m
                best_price = unit_price
                best_qty = affordable_qty

        return best_mkt, best_price, best_qty

    @classmethod
    def find_market_for_material_needs(cls, villager, material_needs, building_manager,
                                      furniture_manager=None, villager_manager=None):
        """Select the first configured material deficit that can be purchased now."""
        for material, amount in material_needs.items():
            market, unit_price, quantity = cls.find_nearest_market_for_material(
                villager, material, amount, building_manager,
                furniture_manager, villager_manager,
            )
            if market and quantity > 0:
                return market, material, quantity, unit_price
        return None, None, 0, 0

    @classmethod
    def execute_material_transaction(cls, villager, market, material_name, quantity=1, day_number=None):
        """
        Executes atomic purchase of material at the market counter.
        Returns (success: bool, msg: str).
        """
        if not market or not hasattr(market, "inventory"):
            return False, "Market is invalid."
        if not MarketService.is_item_for_sale(market, material_name):
            return False, f"{material_name} is not listed for sale at this market."
        stock = market.inventory.get(material_name, 0)
        if stock < quantity:
            return False, f"Insufficient stock: requested {quantity}, available {stock}."
        if _inventory_room(getattr(villager, "inventory", {})) < quantity:
            return False, "Villager inventory is full."

        unit_price = MarketService.get_item_price(material_name, market)
        total_cost = unit_price * quantity

        from game.systems.economy.currency import calculate_payment_and_change, execute_currency_transfer
        can_pay, payment, change, _ = calculate_payment_and_change(villager.inventory, total_cost, getattr(market, "currency", None))
        if not can_pay:
            return False, f"Insufficient coins in pocket for {total_cost} Copper."

        ok, _, _, err = execute_currency_transfer(villager.inventory, market.currency, payment, change)
        if not ok:
            return False, f"Currency transfer failed: {err}"

        market.inventory[material_name] -= quantity
        if market.inventory[material_name] <= 0:
            del market.inventory[material_name]

        villager.inventory[material_name] = villager.inventory.get(material_name, 0) + quantity
        from game.systems.economy.market_sales_report import MarketSalesReportSystem
        MarketSalesReportSystem.record_sale(market, material_name, quantity, unit_price, day_number)
        return True, f"Successfully purchased {quantity}x {material_name} for {total_cost} Copper."

    @classmethod
    def deposit_materials_and_change_to_chest(cls, villager, furniture_manager=None):
        """
        Deposits configured job materials and any remaining coins into household chest.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            from game.systems.economy.currency import CURRENCY_DENOMINATIONS, compact_currency_wallet
            # Deposit coins
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                    del villager.inventory[denom]
            compact_currency_wallet(chest.inventory)

            # Job material requirements define which purchased resources return to storage.
            from game.config import DEDICATED_JOBS
            material_targets = DEDICATED_JOBS.get(getattr(villager, "job", ""), {}).get("material_stock_target", {})
            for mat in material_targets:
                amt = villager.inventory.get(mat, 0)
                if amt > 0:
                    chest.store_item(mat, amt)
                    del villager.inventory[mat]

        villager.target_restock_market = None
        villager.target_restock_mat = None
        villager.target_restock_qty = 0
        villager.task = "IDLE"
