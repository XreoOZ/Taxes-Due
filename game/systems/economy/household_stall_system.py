"""
Household Stall System (AGENT 2 & AGENT 3 Integration)
Manages market stall assignment to settler households, independent per-item
allocation percentages, physical goods transport during leisure time,
and physical coin withdrawal back to household chests.
Zero hardcoding, zero teleportation, zero coin duplication.
"""
import math
from game.systems.economy.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    canonical_denomination,
    compact_currency_wallet,
)
from game.systems.economy.market_pricing import MarketPricingSystem
from game.systems.economy.wealth_system import VillageWealthSystem
from game.systems.economy.household_inventory import canonical_item_name
from game.config import TILE_SIZE
from game.data.config import (
    HOUSEHOLD_STALL_HAUL_CAPACITY,
    MARKET_TRADEABLE_ITEMS,
    MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT,
)


class HouseholdStallSystem:
    @staticmethod
    def _inventory_item_quantity(inventory, item_name):
        if not isinstance(inventory, dict):
            return 0
        target = canonical_item_name(item_name)
        if not target:
            return 0
        return sum(
            max(0, int(amount or 0))
            for stored_name, amount in inventory.items()
            if canonical_item_name(stored_name) == target
        )

    @classmethod
    def _take_inventory_item(cls, inventory, item_name, amount):
        remaining = max(0, int(amount))
        target = canonical_item_name(item_name)
        taken = 0
        for stored_name in list(inventory):
            if canonical_item_name(stored_name) != target:
                continue
            actual = min(remaining, max(0, int(inventory.get(stored_name, 0))))
            if actual <= 0:
                continue
            inventory[stored_name] -= actual
            remaining -= actual
            taken += actual
            if inventory[stored_name] <= 0:
                inventory.pop(stored_name, None)
            if remaining <= 0:
                break
        return taken

    @staticmethod
    def _store_inventory_item(inventory, item_name, amount):
        if not isinstance(inventory, dict) or amount <= 0:
            return
        canonical = canonical_item_name(item_name)
        storage_key = next(
            (key for key in inventory if canonical_item_name(key) == canonical),
            MARKET_TRADEABLE_ITEMS.get(item_name, item_name),
        )
        inventory[storage_key] = max(0, int(inventory.get(storage_key, 0))) + int(amount)

    @staticmethod
    def _family_chests(family_id, furniture_manager):
        """Every installed household_storage chest owned by the family."""
        if not family_id or not furniture_manager:
            return []
        fam_str = str(family_id)
        furn_list = getattr(furniture_manager, "furnitures",
                            getattr(furniture_manager, "furniture_list", []))
        chests, seen = [], set()
        for f in furn_list or []:
            if (getattr(f, "furniture_type", "") == "household_storage"
                    and str(getattr(f, "family_id", "")) == fam_str
                    and getattr(f, "is_available_for_use", True)
                    and id(f) not in seen):
                chests.append(f)
                seen.add(id(f))
        # Include the resolved household storage even if its family_id was
        # never stamped (get_storage_for_family may claim an unowned chest).
        if hasattr(furniture_manager, "get_storage_for_family"):
            st = furniture_manager.get_storage_for_family(fam_str)
            if st is not None and id(st) not in seen:
                chests.append(st)
        return chests

    @staticmethod
    def _family_member_ids(family_id, villager_manager):
        """Family id plus every member id — both can own loose ground stacks."""
        ids = {str(family_id)}
        if villager_manager and hasattr(villager_manager, "get_family_by_id"):
            fam = villager_manager.get_family_by_id(family_id)
            if fam:
                ids.update(str(m.id) for m in getattr(fam, "members", []))
        return ids

    @classmethod
    def _household_loose_stacks(cls, family_id, stockpile_manager, villager_manager=None):
        """Loose ground stacks owned by the household (family or member id)."""
        if not stockpile_manager or not family_id:
            return []
        owner_ids = cls._family_member_ids(family_id, villager_manager)
        return [s for s in getattr(stockpile_manager, "stacks", [])
                if getattr(s, "owner_type", None) == "villager"
                and str(getattr(s, "owner_id", "")) in owner_ids
                and getattr(s, "amount", 0) > 0]

    @classmethod
    def _stall_source_stock(cls, family_id, item_name, furniture_manager,
                            stockpile_manager=None, villager_manager=None):
        """Quantity of item_name the stall chore can physically source:
        household chests plus household-owned loose ground stacks."""
        total = 0
        for chest in cls._family_chests(family_id, furniture_manager):
            total += cls._inventory_item_quantity(getattr(chest, "inventory", None), item_name)
        target = canonical_item_name(item_name)
        for stack in cls._household_loose_stacks(family_id, stockpile_manager, villager_manager):
            if canonical_item_name(getattr(stack, "resource_type", "")) == target:
                total += max(0, int(getattr(stack, "amount", 0) or 0))
        return total

    @classmethod
    def _nearest_goods_source(cls, villager, item_name, furniture_manager,
                              stockpile_manager=None, villager_manager=None,
                              tile_size=TILE_SIZE):
        """Nearest household storage point (chest or owned loose stack) that
        physically holds item_name. Returns (kind, source, x, y, qty) or None."""
        fam_id = getattr(villager, "family_id", None)
        vx, vy = getattr(villager, "x", 0.0), getattr(villager, "y", 0.0)
        target = canonical_item_name(item_name)
        best = None
        for chest in cls._family_chests(fam_id, furniture_manager):
            qty = cls._inventory_item_quantity(getattr(chest, "inventory", None), item_name)
            if qty <= 0:
                continue
            cx, cy = chest.get_world_pos(tile_size)
            dist = math.hypot(cx - vx, cy - vy)
            if best is None or dist < best[0]:
                best = (dist, "chest", chest, cx, cy, qty)
        for stack in cls._household_loose_stacks(fam_id, stockpile_manager, villager_manager):
            if canonical_item_name(getattr(stack, "resource_type", "")) != target:
                continue
            qty = max(0, int(getattr(stack, "amount", 0) or 0))
            if qty <= 0:
                continue
            sx = (getattr(stack, "grid_x", 0) + 0.5) * tile_size
            sy = (getattr(stack, "grid_y", 0) + 0.5) * tile_size
            dist = math.hypot(sx - vx, sy - vy)
            if best is None or dist < best[0]:
                best = (dist, "stack", stack, sx, sy, qty)
        if best is None:
            return None
        return (best[1], best[2], best[3], best[4], best[5])

    @classmethod
    def _take_goods_source(cls, kind, source, item_name, amount, stockpile_manager=None):
        """Withdraw up to `amount` of item_name from a picked goods source."""
        if kind == "stack":
            if stockpile_manager and hasattr(stockpile_manager, "take_from_stack"):
                return stockpile_manager.take_from_stack(source, amount)
            return 0
        inventory = getattr(source, "inventory", None)
        if isinstance(inventory, dict):
            return cls._take_inventory_item(inventory, item_name, amount)
        return 0

    @classmethod
    def get_household_owned_sale_items(cls, family_id, furniture_manager,
                                       villager_manager=None, stockpile_manager=None):
        """Tradeable goods the household stall can physically haul: stock held
        in household chests or household-owned loose ground stacks. Items only
        carried in member pockets or in-transit grants are not listed because
        the stall chore cannot source them."""
        if not family_id or not furniture_manager:
            return set()
        return {
            item_name for item_name in MARKET_TRADEABLE_ITEMS
            if cls._stall_source_stock(
                family_id, item_name, furniture_manager,
                stockpile_manager=stockpile_manager,
                villager_manager=villager_manager,
            ) > 0
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
    def remove_sale_item(cls, market, item_name, furniture_manager=None,
                         stockpile_manager=None):
        """Stop listing an item and drop remaining stock for its owner to haul."""
        if not market or item_name not in getattr(market, "sale_items", []):
            return False
        family_id = getattr(market, "assigned_family_id", None)
        stock = max(0, int(getattr(market, "inventory", {}).get(item_name, 0)))
        if stock and stockpile_manager:
            storage_item = MARKET_TRADEABLE_ITEMS.get(item_name, item_name)
            market_center = market.get_center_world(TILE_SIZE)
            approach = market.get_approach_point(market_center, TILE_SIZE, bm=None)
            drop_tile = (int(math.floor(approach[0] / TILE_SIZE)),
                         int(math.floor(approach[1] / TILE_SIZE)))
            owner_type = "villager" if family_id is not None else "landlord"
            stockpile_manager.drop_resource(
                storage_item, stock, *drop_tile,
                owner_type=owner_type,
                owner_id=str(family_id) if family_id is not None else None,
            )
            market.inventory[item_name] = 0
            market.inventory.pop(item_name, None)
        market.sale_items = [item for item in market.sale_items if item != item_name]
        for field in ("item_allocations", "household_sale_limits", "_stall_requested_qty"):
            values = getattr(market, field, None)
            if isinstance(values, dict):
                values.pop(item_name, None)
        if stock:
            MarketPricingSystem.update_market_prices(market)
        VillageWealthSystem.mark_dirty()
        return True

    @classmethod
    def get_item_allocation(cls, market, item_name):
        """Gets configured allocation percentage for an item (default 0)."""
        if not market or not hasattr(market, "item_allocations") or not isinstance(market.item_allocations, dict):
            return 0
        return market.item_allocations.get(item_name, 0)

    @classmethod
    def retain_household_owned_sale_items(cls, market, furniture_manager,
                                          villager_manager=None, stockpile_manager=None):
        """Keep only listed goods physically owned by the newly assigned household."""
        family_id = getattr(market, "assigned_family_id", None) if market else None
        owned = cls.get_household_owned_sale_items(
            family_id, furniture_manager, villager_manager, stockpile_manager
        )
        market.sale_items = [item for item in getattr(market, "sale_items", []) if item in owned]
        market.item_allocations = {
            item: percentage for item, percentage in getattr(market, "item_allocations", {}).items()
            if item in market.sale_items
        }
        return list(market.sale_items)

    @classmethod
    def calculate_allocatable_goods(cls, market, family_id, item_name, furniture_manager,
                                    stockpile_manager=None, villager_manager=None):
        """
        Calculates the maximum quantity of an item that may be hauled to the market.
        Formula:
            alloc_pct = market.item_allocations.get(item_name, 0)
            household_stock = total of item_name in household chests + owned loose stacks
            max_allocatable = floor(household_stock * (alloc_pct / 100.0))
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

        # Stock the stall chore can physically reach: every household chest
        # plus household-owned loose ground stacks (canonical-name matched).
        chest_stock = cls._stall_source_stock(
            family_id, item_name, furniture_manager,
            stockpile_manager=stockpile_manager,
            villager_manager=villager_manager,
        )
        if chest_stock <= 0:
            return 0

        # Percentage is live: the cap always tracks the household's CURRENT
        # chest stock, so 10% of 100 potatoes sells 10, and if the chest
        # grows to 200 it sells up to 20 — never a stale absolute number.
        max_alloc = int(math.ceil(chest_stock * (pct / 100.0)))
        if not isinstance(getattr(market, "household_sale_limits", None), dict):
            market.household_sale_limits = {}
        market.household_sale_limits[item_name] = max_alloc
        current_mkt_stock = market.inventory.get(item_name, 0) if hasattr(market, "inventory") else 0
        in_transit = getattr(market, "_stall_in_transit", {}).get(item_name, 0)

        remaining_alloc = max(0, max_alloc - (current_mkt_stock + in_transit))
        # Replenish sales up to the percentage cap without exceeding actual household stock.
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
    def request_goods_restock(cls, market, item_name, amount, furniture_manager,
                              stockpile_manager=None, villager_manager=None):
        available = cls.calculate_allocatable_goods(
            market, getattr(market, "assigned_family_id", None), item_name, furniture_manager,
            stockpile_manager=stockpile_manager, villager_manager=villager_manager,
        )
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
    def check_and_start_stall_chores(cls, villager, building_manager, furniture_manager,
                                     all_entities=None, allow_restock=True,
                                     stockpile_manager=None, villager_manager=None):
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
            family_entities = (
                all_entities.by_family(fam_str)
                if hasattr(all_entities, "by_family") else all_entities
            )
            for other in family_entities:
                if other != villager and str(getattr(other, "family_id", "")) == fam_str:
                    o_task = getattr(other, "task", "")
                    if o_task.startswith("HAULING_STALL_"):
                        return False

        # Managers are optional; fall back to the references villagers cache on themselves.
        stockpile_manager = stockpile_manager or getattr(villager, "stockpile_manager", None)
        villager_manager = villager_manager or getattr(villager, "villager_manager", None)

        chest = furniture_manager.get_storage_for_family(fam_str) if furniture_manager else None
        if not chest and not cls._household_loose_stacks(fam_id, stockpile_manager, villager_manager):
            return False

        # A. Priority 1: Household Coin Collection from Market
        # (requires a chest to deliver earnings into)
        mkt_curr = normalize_wallet(getattr(market, "currency", {}))
        total_coins = sum(mkt_curr.values())
        if total_coins > 0 and chest:
            villager.task = "HAULING_STALL_COINS_FETCH"
            villager.stall_target_market = market
            villager.say("Going to collect stall earnings from Market...", duration=2.5)
            return True

        # B. Priority 2: Physical Goods Transportation to Market
        if not allow_restock:
            return False
        for item_name in getattr(market, "sale_items", []):
            alloc_qty = cls.calculate_allocatable_goods(
                market, fam_id, item_name, furniture_manager,
                stockpile_manager=stockpile_manager, villager_manager=villager_manager,
            )
            if alloc_qty > 0:
                villager.task = "HAULING_STALL_GOODS_FETCH"
                villager.stall_target_market = market
                villager.stall_target_item = item_name
                villager.stall_target_qty = min(alloc_qty, HOUSEHOLD_STALL_HAUL_CAPACITY)
                villager.say(f"Preparing to haul {villager.stall_target_qty} {item_name} to stall...", duration=2.5)
                return True

        return False

    @classmethod
    def execute_stall_chores_tick(cls, villager, dt, building_manager, furniture_manager,
                                 all_entities=None, player=None, tile_size=TILE_SIZE,
                                 stockpile_manager=None, villager_manager=None):
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
                                             furniture_manager=furniture_manager,
                                             interaction_target=market)
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
                                             furniture_manager=furniture_manager,
                                             interaction_target=chest)
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
            item_name = getattr(villager, "stall_target_item", None)
            if (not market or market not in getattr(building_manager, "buildings", [])
                    or not item_name or item_name not in getattr(market, "sale_items", [])):
                villager.task = "IDLE"
                villager.stall_target_market = None
                villager.stall_target_item = None
                villager.stall_target_qty = 0
                return False

            # Source can be any household chest or household-owned loose stack;
            # re-picked every tick so depleted sources are skipped automatically.
            vm = villager_manager or getattr(villager, "villager_manager", None)
            source = cls._nearest_goods_source(
                villager, item_name, furniture_manager,
                stockpile_manager=stockpile_manager, villager_manager=vm,
                tile_size=tile_size,
            )
            if source is None:
                villager.task = "IDLE"
                villager.stall_target_market = None
                villager.stall_target_item = None
                villager.stall_target_qty = 0
                return False

            src_kind, src_obj, src_x, src_y, src_qty = source
            arrived = villager._move_towards(src_x, src_y, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager,
                                             interaction_target=src_obj)
            if arrived:
                target_qty = getattr(villager, "stall_target_qty", HOUSEHOLD_STALL_HAUL_CAPACITY)
                take_amt = min(target_qty, src_qty)
                taken = cls._take_goods_source(src_kind, src_obj, item_name, take_amt, stockpile_manager)
                if taken <= 0:
                    # Source raced dry; the next tick re-picks another source.
                    return True

                # Withdraw from source into villager inventory (now in-transit!)
                villager.inventory[item_name] = villager.inventory.get(item_name, 0) + taken
                villager.stall_carried_item = item_name
                villager.stall_carried_qty = taken

                # Track in-transit quantity on market so allocation does not duplicate
                if not hasattr(market, "_stall_in_transit"):
                    market._stall_in_transit = {}
                market._stall_in_transit[item_name] = market._stall_in_transit.get(item_name, 0) + taken

                villager.say(f"Carrying {taken} {item_name} to Market stall.", duration=2.5)
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
                    cls._store_inventory_item(chest.inventory, item_name, carried_qty)
                    villager.inventory[item_name] = max(0, villager.inventory.get(item_name, 0) - carried_qty)
                villager.task = "IDLE"
                villager.stall_target_market = None
                return False

            if item_name not in getattr(market, "sale_items", []):
                dropped = False
                if item_name and carried_qty > 0 and stockpile_manager:
                    gx = int(math.floor(villager.x / tile_size))
                    gy = int(math.floor(villager.y / tile_size))
                    family_id = getattr(market, "assigned_family_id", None)
                    stockpile_manager.drop_resource(
                        MARKET_TRADEABLE_ITEMS.get(item_name, item_name), carried_qty, gx, gy,
                        owner_type="villager" if family_id is not None else "landlord",
                        owner_id=str(family_id) if family_id is not None else None,
                    )
                    dropped = True
                elif chest and item_name and carried_qty > 0:
                    cls._store_inventory_item(chest.inventory, item_name, carried_qty)
                    villager.inventory[item_name] = max(0, villager.inventory.get(item_name, 0) - carried_qty)
                if hasattr(market, "_stall_in_transit") and item_name:
                    market._stall_in_transit[item_name] = max(
                        0, market._stall_in_transit.get(item_name, 0) - carried_qty
                    )
                villager.task = "IDLE"
                villager.stall_target_market = None
                villager.stall_target_item = None
                villager.stall_target_qty = 0
                villager.stall_carried_item = None
                villager.stall_carried_qty = 0
                villager.say(
                    "Dropped goods for the owner to collect." if dropped else "Returned goods because this item was removed from the stall.",
                    duration=2.5,
                )
                return True

            app_x, app_y = market.get_approach_point((villager.x, villager.y), tile_size, building_manager)
            arrived = villager._move_towards(app_x, app_y, dt, arrival_dist=24,
                                             all_entities=all_entities, player=player,
                                             building_manager=building_manager,
                                             furniture_manager=furniture_manager,
                                             interaction_target=market)
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
