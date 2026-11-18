"""
AI Food Purchasing & Market Transaction System (Agent 3)

Coordinates the complete, realistic physical market food purchasing workflow for villagers:
1. Household food stock check (Zero remote purchases when food is available at home).
2. Family coordination (Prevents duplicate simultaneous purchases by household members).
3. Nearest eligible market selection (Valid stock, configured price, affordable).
4. Physical coin retrieval from household storage (Real money transfer to villager pocket).
5. Physical navigation to Market interaction position (Zero teleportation or remote purchasing).
6. Atomic market transaction at Market location (Exact payment, currency conservation, change calculation).
7. Physical hauling back to household storage.
8. Safe deposit of change, food consumption, hunger restoration, and activity resumption.
"""

import math
from game.config import TILE_SIZE, AI_NEED_MAX, AI_NEED_FOOD_RESTORE
from game.data.config import is_food_item, CHEST_INTERACTION_RADIUS
from game.systems.currency import (
    to_copper,
    normalize_wallet,
    calculate_payment_and_change,
    execute_currency_transfer,
    CURRENCY_DENOMINATIONS
)
from game.systems.market_service import MarketService


class AIFoodPurchasingSystem:
    """
    Dedicated modular controller for AI Food Purchasing (Agent 3).
    """

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
        return avail > 0

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
                "BUYING_FOOD_RETRIEVE_COINS",
                "BUYING_FOOD_TRAVEL_TO_MARKET",
                "BUYING_FOOD_HAULING_HOME"
            ):
                return True
        return False

    @classmethod
    def find_nearest_eligible_market(cls, villager, building_manager, furniture_manager=None, villager_manager=None, preferred_food=None):
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

        # Calculate total household funds (pocket + chest)
        wallet, _ = MarketService.get_household_funds_and_source(villager, furniture_manager, villager_manager)
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
                if count > 0 and is_food_item(item_name):
                    if preferred_food is None or item_name == preferred_food:
                        available_foods.append(item_name)

            for food_item in available_foods:
                unit_price = MarketService.get_item_price(food_item, m)
                if unit_price <= 0:
                    continue  # Food is never free! Must have configured price > 0

                if total_funds_copper >= unit_price:
                    # Calculate distance to market interaction approach point
                    try:
                        approach_pt = m.get_approach_point((villager.x, villager.y), TILE_SIZE, building_manager)
                    except Exception:
                        approach_pt = m.get_center_world(TILE_SIZE)
                    dist = math.hypot(approach_pt[0] - villager.x, approach_pt[1] - villager.y)
                    candidates.append((dist, m, food_item, unit_price))

        if not candidates:
            return None, None, 0

        # Sort by distance (nearest eligible market first)
        candidates.sort(key=lambda c: c[0])
        best_candidate = candidates[0]
        return best_candidate[1], best_candidate[2], best_candidate[3]

    @classmethod
    def retrieve_coins_from_storage(cls, villager, price_in_copper, furniture_manager=None):
        """
        Transfers required coins from household chest into villager's pocket.
        Ensures zero free money creation, conservation of currency, and proper coin withdrawal.
        Returns:
            (success: bool, message: str)
        """
        cur_pocket = normalize_wallet(getattr(villager, "inventory", {}))
        cur_pocket_val = to_copper(cur_pocket)

        if cur_pocket_val >= price_in_copper:
            return True, "Villager already carries enough coins in pocket."

        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if not chest or not hasattr(chest, "inventory") or not isinstance(chest.inventory, dict):
            return False, "Household has no storage chest to retrieve coins from."

        deficit = price_in_copper - cur_pocket_val
        ok, payment_dict, change_dict, msg = calculate_payment_and_change(chest.inventory, deficit)
        if not ok or not payment_dict:
            return False, f"Chest has insufficient coins to cover purchase: {msg}"

        # Deduct coins from chest and transfer into villager inventory
        if not hasattr(villager, "inventory") or not isinstance(villager.inventory, dict):
            villager.inventory = {}

        for denom, count in payment_dict.items():
            if count > 0:
                chest.inventory[denom] = chest.inventory.get(denom, 0) - count
                if chest.inventory[denom] <= 0:
                    del chest.inventory[denom]
                villager.inventory[denom] = villager.inventory.get(denom, 0) + count

        return True, "Successfully retrieved coins from household storage."

    @classmethod
    def execute_market_transaction(cls, villager, market, food_item, building_manager=None):
        """
        Executes the atomic purchase transaction physically at the Market interaction location.
        Returns:
            (success: bool, message: str)
        """
        if not market or not hasattr(market, "inventory"):
            return False, "Market building is invalid or missing."

        stock = market.inventory.get(food_item, 0)
        if stock < 1:
            return False, f"Market ran out of {food_item} while traveling."

        unit_price = MarketService.get_item_price(food_item, market)
        if unit_price <= 0:
            return False, "Item has invalid selling price."

        vil_wallet = normalize_wallet(getattr(villager, "inventory", {}))
        vil_copper = to_copper(vil_wallet)
        if vil_copper < unit_price:
            return False, f"Villager has insufficient coins in pocket ({vil_copper}c < {unit_price}c)."

        if not hasattr(market, "currency") or not isinstance(market.currency, dict):
            market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        # Calculate exact payment & change
        ok, payment, change, msg = calculate_payment_and_change(vil_wallet, unit_price, market.currency)
        if not ok:
            return False, f"Cannot resolve payment/change: {msg}"

        # Execute currency transfer between villager pocket and market
        transfer_ok, new_vil_w, new_mkt_w, t_msg = execute_currency_transfer(
            villager.inventory, market.currency, payment, change
        )
        if not transfer_ok:
            return False, f"Currency transfer failed: {t_msg}"

        # Deduct item from market stock
        market.inventory[food_item] -= 1
        if market.inventory[food_item] <= 0:
            del market.inventory[food_item]

        # Add item to villager inventory
        villager.inventory[food_item] = villager.inventory.get(food_item, 0) + 1

        return True, f"Successfully purchased 1x {food_item} for {unit_price} Copper."

    @classmethod
    def deliver_and_consume_food(cls, villager, furniture_manager=None, stockpile_manager=None):
        """
        Delivers change back to household chest, consumes purchased food,
        recovers hunger, and resumes activity.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None

        # 1. Return any coins (change or leftover funds) back to household storage chest
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
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
            villager.say(f"Ate hearty meal of {food_it} brought from Market!", duration=2.5)

        # 3. If any extra food remains, store it in the chest
        if chest:
            for it, c in list(getattr(villager, "inventory", {}).items()):
                if is_food_item(it) and c > 0:
                    chest.store_item(it, c)
                    del villager.inventory[it]

        # 4. Clear purchasing tracking attributes
        villager.purchase_target_market_id = None
        villager.purchase_food_item = None
        villager.purchase_target_price = 0

        # 5. Safely resume next activity or return to idle
        villager._resume_or_idle_after_need()

    @classmethod
    def return_coins_to_storage(cls, villager, furniture_manager=None):
        """
        Safety fallback: returns coins back to chest if purchasing failed or aborted.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                    del villager.inventory[denom]

        villager.purchase_target_market_id = None
        villager.purchase_food_item = None
        villager.purchase_target_price = 0
        villager.task = "IDLE"
        villager.need_seek_cooldown = 4.0


class AIMarketPurchasingSystem:
    """
    Universal Market Purchasing System for AI (Agent 3).
    Handles needed materials purchasing (e.g. Wood and Stone restocking for Gravedigger).
    """

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
        from game.systems.currency import to_copper
        wallet, _ = MarketService.get_household_funds_and_source(villager, furniture_manager, villager_manager)
        total_funds = to_copper(wallet)
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
        min_dist = float('inf')

        for m in completed_markets:
            inv = getattr(m, "inventory", {})
            stock = inv.get(material_name, 0)
            if stock <= 0:
                continue
            prices = getattr(m, "prices", {})
            from game.data.config import DEFAULT_ITEM_PRICES
            unit_price = prices.get(material_name, DEFAULT_ITEM_PRICES.get(material_name, 2))
            if unit_price <= 0:
                continue
            if total_funds < unit_price:
                continue

            affordable_qty = min(stock, needed_amount, total_funds // unit_price)
            if affordable_qty <= 0:
                continue

            mx, my = m.get_center_world(TILE_SIZE)
            d = math.hypot(villager.x - mx, villager.y - my)
            if d < min_dist:
                min_dist = d
                best_mkt = m
                best_price = unit_price
                best_qty = affordable_qty

        return best_mkt, best_price, best_qty

    @classmethod
    def execute_material_transaction(cls, villager, market, material_name, quantity=1):
        """
        Executes atomic purchase of material at the market counter.
        Returns (success: bool, msg: str).
        """
        if not market or not hasattr(market, "inventory"):
            return False, "Market is invalid."
        stock = market.inventory.get(material_name, 0)
        if stock < quantity:
            return False, f"Insufficient stock: requested {quantity}, available {stock}."

        prices = getattr(market, "prices", {})
        from game.data.config import DEFAULT_ITEM_PRICES
        unit_price = prices.get(material_name, DEFAULT_ITEM_PRICES.get(material_name, 2))
        total_cost = unit_price * quantity

        from game.systems.currency import calculate_payment_and_change, execute_currency_transfer
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
        return True, f"Successfully purchased {quantity}x {material_name} for {total_cost} Copper."

    @classmethod
    def deposit_materials_and_change_to_chest(cls, villager, furniture_manager=None):
        """
        Deposits purchased materials (Wood, Stone) and any remaining coins into household chest.
        """
        chest = furniture_manager.get_storage_for_family(villager.family_id) if furniture_manager else None
        if chest and hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
            from game.systems.currency import CURRENCY_DENOMINATIONS
            # Deposit coins
            for denom in CURRENCY_DENOMINATIONS:
                amt = villager.inventory.get(denom, 0)
                if amt > 0:
                    chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                    del villager.inventory[denom]

            # Deposit materials
            for mat in ("Wood", "Stone"):
                amt = villager.inventory.get(mat, 0)
                if amt > 0:
                    chest.store_item(mat, amt)
                    del villager.inventory[mat]

        villager.target_restock_market = None
        villager.target_restock_mat = None
        villager.target_restock_qty = 0
        villager.task = "IDLE"
