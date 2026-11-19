"""
Household Stall System (AGENT 2 & AGENT 3 Integration)
Manages market stall assignment to settler households, independent per-item
allocation percentages, physical goods transport during leisure time,
and physical coin withdrawal back to household chests.
Zero hardcoding, zero teleportation, zero coin duplication.
"""
import math
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    canonical_denomination,
    compact_currency_wallet,
)
from game.systems.market_pricing import MarketPricingSystem
from game.systems.wealth_system import VillageWealthSystem
from game.data.config import MARKET_TRADEABLE_ITEMS, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT

VILLAGER_STALL_HAUL_CAPACITY = 20


class HouseholdStallSystem:
    @staticmethod
    def _inventory_contains_item(inventory, storage_item):
        if not isinstance(inventory, dict):
            return False
        target = str(storage_item).replace(" ", "_").casefold()
        return any(
            str(item_name).replace(" ", "_").casefold() == target and int(amount or 0) > 0
            for item_name, amount in inventory.items()
        )

    @classmethod
    def get_household_owned_sale_items(cls, family_id, furniture_manager):
        """Return tradeable goods physically available in this household's chest."""
        if not family_id or not furniture_manager:
            return set()
        chest = furniture_manager.get_storage_for_family(str(family_id))
        inventory = getattr(chest, "inventory", {}) if chest else {}
        return {
            item_name for item_name, storage_item in MARKET_TRADEABLE_ITEMS.items()
            if cls._inventory_contains_item(inventory, storage_item)
        }

    @classmethod
    def assign_stall(cls, market, family_id):
        """Assigns a Market Stall to a peasant household."""
        if not market:
            return False
        market.assigned_family_id = family_id
        market.assigned_household_id = family_id
        market.owner = family_id
        market.household_sale_limits = {}
        market._stall_requested_qty = {}
        market.auto_pricing = True
        VillageWealthSystem.mark_dirty()
        return True

    @classmethod
    def unassign_stall(cls, market):
        """Revokes stall assignment, reverting Market ownership to Landlord."""
        if not market:
            return False
        market.assigned_family_id = None
        market.assigned_household_id = None
        market.owner = "landlord"
        market.household_sale_limits = {}
        market._stall_requested_qty = {}
        market.auto_pricing = False
        VillageWealthSystem.mark_dirty()
        return True

    @classmethod
    def set_item_allocation(cls, market, item_name, percentage):
        """Sets the independent allocation percentage (0..100) for a specific item."""
        if not market:
            return
        if not hasattr(market, "item_allocations") or not isinstance(market.item_allocations, dict):
            market.item_allocations = {}
        pct = max(0, min(100, int(percentage)))
        market.item_allocations[item_name] = pct
        if isinstance(getattr(market, "household_sale_limits", None), dict):
            market.household_sale_limits.pop(item_name, None)
        return pct

    @classmethod
    def get_item_allocation(cls, market, item_name):
        """Gets configured allocation percentage for an item (default 0)."""
        if not market or not hasattr(market, "item_allocations") or not isinstance(market.item_allocations, dict):
            return 0
        return market.item_allocations.get(item_name, 0)

    @classmethod
    def retain_household_owned_sale_items(cls, market, furniture_manager):
        """Keep only listed goods physically owned by the newly assigned household."""
        family_id = getattr(market, "assigned_family_id", None) if market else None
        owned = cls.get_household_owned_sale_items(family_id, furniture_manager)
        market.sale_items = [item for item in getattr(market, "sale_items", []) if item in owned]
        market.item_allocations = {
            item: percentage for item, percentage in getattr(market, "item_allocations", {}).items()
            if item in market.sale_items
        }
        return list(market.sale_items)

    @classmethod
    def calculate_allocatable_goods(cls, market, family_id, item_name, furniture_manager):
        """
        Calculates the maximum quantity of an item that may be hauled to the market.
        Formula:
            alloc_pct = market.item_allocations.get(item_name, 0)
            chest_stock = total of item_name in household storage chest
            max_allocatable = floor(chest_stock * (alloc_pct / 100.0))
            market_stock = market.inventory.get(item_name, 0)
            in_transit = carried by hauling villager
            available_to_haul = max(0, max_allocatable - (market_stock + in_transit))
        """
        if not market or not family_id or not furniture_manager:
            return 0

        if item_name not in MARKET_TRADEABLE_ITEMS or item_name not in getattr(market, "sale_items", []):
            return 0
        pct = max(0, min(100, int(getattr(market, "item_allocations", {}).get(
            item_name, getattr(market, "household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
        ))))
        if pct <= 0:
            return 0

        chest = furniture_manager.get_storage_for_family(str(family_id))
        if not chest or not hasattr(chest, "inventory") or not isinstance(chest.inventory, dict):
            return 0

        storage_item = MARKET_TRADEABLE_ITEMS[item_name]
        chest_stock = chest.inventory.get(storage_item, 0)
        if chest_stock <= 0:
            return 0

        if not isinstance(getattr(market, "household_sale_limits", None), dict):
            market.household_sale_limits = {}
        max_alloc = market.household_sale_limits.get(item_name)
        if max_alloc is None:
            max_alloc = int(math.floor(chest_stock * (pct / 100.0)))
            market.household_sale_limits[item_name] = max_alloc
        current_mkt_stock = market.inventory.get(item_name, 0) if hasattr(market, "inventory") else 0
        in_transit = getattr(market, "_stall_in_transit", {}).get(item_name, 0)

        remaining_alloc = max(0, max_alloc - (current_mkt_stock + in_transit))
        # Replenish sales up to the saved cap without exceeding actual household stock.
        return min(remaining_alloc, chest_stock)

    @classmethod
    def get_assigned_market_for_family(cls, family_id, building_manager):
        """Finds any active market assigned to the specified family."""
        if not building_manager or not family_id:
            return None
        fam_str = str(family_id)
        for b in getattr(building_manager, "buildings", []):
            if getattr(b, "building_type", "") == "market":
                b_fam = getattr(b, "assigned_household_id", None) or getattr(b, "assigned_family_id", None)
                if str(b_fam) == fam_str:
                    return b
        return None

    @classmethod
    def request_goods_restock(cls, market, item_name, amount, furniture_manager):
        available = cls.calculate_allocatable_goods(market, getattr(market, "assigned_family_id", None), item_name, furniture_manager)
        if available <= 0:
            return 0
        requests = getattr(market, "_stall_requested_qty", None)
        if not isinstance(requests, dict):
            market._stall_requested_qty = {}
        market._stall_requested_qty[item_name] = min(max(0, int(amount)), available)
        return market._stall_requested_qty[item_name]

    @classmethod
    def deposit_coin(cls, market, denomination, amount, resources):
        """Transfers actual coins from Landlord resources into selected Market currency."""
        if not market or amount <= 0 or not resources:
            return 0
        canon = canonical_denomination(denomination)
        if not canon:
            return 0
        avail = resources.get(canon, 0)
        actual = min(amount, avail)
        if actual <= 0:
            return 0

        resources[canon] = max(0, resources.get(canon, 0) - actual)
        if not hasattr(market, "currency") or not isinstance(market.currency, dict):
            market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        market.currency[canon] = market.currency.get(canon, 0) + actual
        compact_currency_wallet(market.currency)
        compact_currency_wallet(resources)
        VillageWealthSystem.mark_dirty()
        return actual

    @classmethod
    def withdraw_coin(cls, market, denomination, amount, resources):
        """Transfers actual coins from selected Market currency into Landlord resources."""
        if not market or amount <= 0 or not resources:
            return 0
        canon = canonical_denomination(denomination)
        if not canon or not hasattr(market, "currency") or not isinstance(market.currency, dict):
            return 0
        avail = market.currency.get(canon, 0)
        actual = min(amount, avail)
        if actual <= 0:
            return 0

        market.currency[canon] = max(0, market.currency.get(canon, 0) - actual)
        resources[canon] = resources.get(canon, 0) + actual
        compact_currency_wallet(market.currency)
        compact_currency_wallet(resources)
        VillageWealthSystem.mark_dirty()
        return actual

    @classmethod
    def get_available_transporter(cls, family, villager_manager, sched_activity):
        """
        Finds an available representative adult villager from the household
        who is in Free Time (LEISURE or ANY) and not engaged in active work tasks.
        """
        if sched_activity not in ("LEISURE", "ANY"):
            return None
        if not family or not hasattr(family, "members"):
            return None

        for m in family.members:
            if not getattr(m, "is_alive", True):
                continue
            # Must not interrupt critical need or active urgent routine
            if getattr(m, "hunger", 100) <= 20 or getattr(m, "thirst", 100) <= 20 or getattr(m, "need_toilet", 100) <= 20:
                continue
            task = getattr(m, "task", "IDLE")
            if task in ("IDLE", "LEISURE", "STROLLING"):
                return m
        return None

    @classmethod
    def check_and_start_stall_chores(cls, villager, building_manager, furniture_manager, all_entities=None):
        """
        Called during villager free time routines:
        1. Check if household stall has earned coins to collect back to chest.
        2. Check if household chest has allocated items to haul to stall.
        """
        if not villager or not getattr(villager, "family_id", None):
            return False

        fam_id = villager.family_id
        market = cls.get_assigned_market_for_family(fam_id, building_manager)
        if not market:
            return False

        # Ensure no other family member is already executing stall chores
        fam_str = str(fam_id)
        if all_entities:
            for other in all_entities:
                if other != villager and str(getattr(other, "family_id", "")) == fam_str:
                    o_task = getattr(other, "task", "")
                    if o_task.startswith("HAULING_STALL_"):
                        return False

        chest = furniture_manager.get_storage_for_family(fam_str) if furniture_manager else None
        if not chest:
            return False

        # A. Priority 1: Household Coin Collection from Market
        mkt_curr = normalize_wallet(getattr(market, "currency", {}))
        total_coins = sum(mkt_curr.values())
        if total_coins > 0:
            villager.task = "HAULING_STALL_COINS_FETCH"
            villager.stall_target_market = market
            villager.say("Going to collect stall earnings from Market...", duration=2.5)
            return True

        # B. Priority 2: Physical Goods Transportation to Market
        for item_name in getattr(market, "sale_items", []):
            alloc_qty = cls.calculate_allocatable_goods(market, fam_id, item_name, furniture_manager)
            if alloc_qty > 0:
                villager.task = "HAULING_STALL_GOODS_FETCH"
                villager.stall_target_market = market
                villager.stall_target_item = item_name
                villager.stall_target_qty = min(alloc_qty, VILLAGER_STALL_HAUL_CAPACITY)
                villager.say(f"Preparing to haul {villager.stall_target_qty} {item_name} to stall...", duration=2.5)
                return True

        return False

    @classmethod
    def execute_stall_chores_tick(cls, villager, dt, building_manager, furniture_manager,
                                 all_entities=None, player=None, tile_size=32):
        """
        Executes physical movement and transactions for stall hauling and coin collection.
        Returns True if a stall chore is active, False otherwise.
        """
        task = getattr(villager, "task", "")
        if not task.startswith("HAULING_STALL_"):
            return False

        market = getattr(villager, "stall_target_market", None)
        chest = furniture_manager.get_storage_for_family(str(villager.family_id)) if furniture_manager else None

        # -------------------------------------------------------------
        # 1. COIN COLLECTION: FETCH COINS FROM MARKET
        # -------------------------------------------------------------
        if task == "HAULING_STALL_COINS_FETCH":
            if not market or market not in getattr(building_manager, "buildings", []):
                villager.task = "IDLE"
                villager.stall_target_market = None
                return False

            app_x, app_y = market.get_approach_point((villager.x, villager.y), tile_size, building_manager)
            arrived = villager._move_towards(app_x, app_y, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager)
            if arrived:
                # Withdraw coins from market into villager personal pocket
                mkt_curr = getattr(market, "currency", {})
                withdrawn = {}
                for denom in ("Copper", "Silver", "Gold"):
                    amt = mkt_curr.get(denom, 0)
                    if amt > 0:
                        withdrawn[denom] = amt
                        mkt_curr[denom] = 0
                        # Store in villager currency/inventory
                        if not hasattr(villager, "currency") or not isinstance(villager.currency, dict):
                            villager.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
                        villager.currency[denom] = villager.currency.get(denom, 0) + amt
                        villager.inventory[denom] = villager.inventory.get(denom, 0) + amt
                compact_currency_wallet(mkt_curr)
                compact_currency_wallet(villager.currency)
                compact_currency_wallet(villager.inventory)

                VillageWealthSystem.mark_dirty()
                if withdrawn:
                    w_str = ", ".join(f"{v} {k}" for k, v in withdrawn.items())
                    villager.say(f"Collected {w_str}. Carrying home!", duration=2.5)
                villager.task = "HAULING_STALL_COINS_DELIVER"
            return True

        # -------------------------------------------------------------
        # 2. COIN COLLECTION: DELIVER COINS TO HOUSEHOLD CHEST
        # -------------------------------------------------------------
        elif task == "HAULING_STALL_COINS_DELIVER":
            if not chest:
                villager.task = "IDLE"
                villager.stall_target_market = None
                return False

            cx, cy = chest.get_world_pos(tile_size)
            arrived = villager._move_towards(cx, cy, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager)
            if arrived:
                # Deposit carried coins from pocket into chest
                deposited = {}
                for denom in ("Copper", "Silver", "Gold"):
                    # Check villager pocket
                    amt = villager.inventory.get(denom, 0)
                    if hasattr(villager, "currency") and villager.currency.get(denom, 0) > amt:
                        amt = villager.currency[denom]
                    if amt > 0:
                        deposited[denom] = amt
                        villager.inventory[denom] = 0
                        if hasattr(villager, "currency"):
                            villager.currency[denom] = 0
                        # Store into chest
                        if not hasattr(chest, "currency") or not isinstance(chest.currency, dict):
                            chest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
                        chest.currency[denom] = chest.currency.get(denom, 0) + amt
                        if hasattr(chest, "inventory") and isinstance(chest.inventory, dict):
                            chest.inventory[denom] = chest.inventory.get(denom, 0) + amt
                compact_currency_wallet(chest.currency)
                compact_currency_wallet(chest.inventory)
                compact_currency_wallet(villager.currency)
                compact_currency_wallet(villager.inventory)

                VillageWealthSystem.mark_dirty()
                if deposited:
                    d_str = ", ".join(f"{v} {k}" for k, v in deposited.items())
                    villager.say(f"Deposited {d_str} into household chest.", duration=2.5)
                villager.task = "IDLE"
                villager.stall_target_market = None
            return True

        # -------------------------------------------------------------
        # 3. GOODS HAULING: FETCH GOODS FROM HOUSEHOLD CHEST
        # -------------------------------------------------------------
        elif task == "HAULING_STALL_GOODS_FETCH":
            if not chest or not market or market not in getattr(building_manager, "buildings", []):
                villager.task = "IDLE"
                villager.stall_target_market = None
                return False

            cx, cy = chest.get_world_pos(tile_size)
            arrived = villager._move_towards(cx, cy, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager)
            if arrived:
                item_name = getattr(villager, "stall_target_item", None)
                target_qty = getattr(villager, "stall_target_qty", 10)
                if not item_name or not hasattr(chest, "inventory"):
                    villager.task = "IDLE"
                    villager.stall_target_market = None
                    return False

                storage_item = MARKET_TRADEABLE_ITEMS.get(item_name, item_name)
                avail_in_chest = chest.inventory.get(storage_item, 0)
                take_amt = min(target_qty, avail_in_chest)
                if take_amt <= 0:
                    villager.task = "IDLE"
                    villager.stall_target_market = None
                    return False

                # Withdraw from chest into villager inventory (now in-transit!)
                chest.inventory[storage_item] -= take_amt
                if chest.inventory[storage_item] <= 0:
                    del chest.inventory[storage_item]

                villager.inventory[item_name] = villager.inventory.get(item_name, 0) + take_amt
                villager.stall_carried_item = item_name
                villager.stall_carried_qty = take_amt

                # Track in-transit quantity on market so allocation does not duplicate
                if not hasattr(market, "_stall_in_transit"):
                    market._stall_in_transit = {}
                market._stall_in_transit[item_name] = market._stall_in_transit.get(item_name, 0) + take_amt

                villager.say(f"Carrying {take_amt} {item_name} to Market stall.", duration=2.5)
                villager.task = "HAULING_STALL_GOODS_DELIVER"
            return True

        # -------------------------------------------------------------
        # 4. GOODS HAULING: DELIVER GOODS TO MARKET STALL
        # -------------------------------------------------------------
        elif task == "HAULING_STALL_GOODS_DELIVER":
            item_name = getattr(villager, "stall_carried_item", None)
            carried_qty = getattr(villager, "stall_carried_qty", 0)

            if not market or market not in getattr(building_manager, "buildings", []):
                # Market destroyed while traveling: return goods to chest
                if chest and item_name and carried_qty > 0:
                    chest.inventory[item_name] = chest.inventory.get(item_name, 0) + carried_qty
                    villager.inventory[item_name] = max(0, villager.inventory.get(item_name, 0) - carried_qty)
                villager.task = "IDLE"
                villager.stall_target_market = None
                return False

            app_x, app_y = market.get_approach_point((villager.x, villager.y), tile_size, building_manager)
            arrived = villager._move_towards(app_x, app_y, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager)
            if arrived:
                # Deposit goods into market inventory
                if not hasattr(market, "inventory") or not isinstance(market.inventory, dict):
                    market.inventory = {}

                market.inventory[item_name] = market.inventory.get(item_name, 0) + carried_qty
                villager.inventory[item_name] = max(0, villager.inventory.get(item_name, 0) - carried_qty)

                # Clear in-transit tracking
                if hasattr(market, "_stall_in_transit"):
                    market._stall_in_transit[item_name] = max(0, market._stall_in_transit.get(item_name, 0) - carried_qty)

                # Update automatic market pricing immediately based on new stock
                MarketPricingSystem.update_market_prices(market)

                villager.say(f"Delivered {carried_qty} {item_name} to Market stall!", duration=2.5)
                villager.task = "IDLE"
                villager.stall_target_market = None
                villager.stall_carried_item = None
                villager.stall_carried_qty = 0
            return True

        return False
