"""
Market Pricing System (Real-Life Scalable Supply & Demand)
Calculates dynamic unit prices in Copper anchored to base price and scaled
by village-wide Demand vs. Supply, plus gentle village wealth elasticity.
Minimum price: 1 Copper. Bounded by config-driven multipliers.
Zero hardcoding, config-driven.
"""
import math
from game.data.config import (
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    DEFAULT_ITEM_PRICES,
    MARKET_DEFAULT_BULK_DEMAND,
    MARKET_DEFAULT_CRAFTED_DEMAND,
    MARKET_DEMAND_ELASTICITY_K,
    MARKET_FOOD_DEMAND_DAYS,
    MARKET_LOCAL_SUPPLY_WEIGHT,
    MARKET_PRICE_MULTIPLIER_MAX,
    MARKET_PRICE_MULTIPLIER_MIN,
    MARKET_TOILET_VILLAGERS_PER_UNIT,
    MARKET_TRADEABLE_ITEMS,
    MARKET_VILLAGE_SUPPLY_WEIGHT,
    MARKET_WATER_DEMAND_DAYS,
    MARKET_WEALTH_PRICE_ELASTICITY,
    MARKET_WEALTH_PRICE_FACTOR_MAX,
    MARKET_WEALTH_PRICE_FACTOR_MIN,
    MARKET_WEALTH_REFERENCE_DAYS,
    PRODUCTION_BUILDER_FURNITURE_IDS,
    TOOL_TYPES,
)
from game.systems.work.job_tool_system import get_job_required_tools


class MarketPricingSystem:
    MIN_PRICE = 1

    @classmethod
    def get_base_price(cls, item_name):
        return DEFAULT_ITEM_PRICES.get(item_name, 3)

    @classmethod
    def default_demand_for_item(cls, item_name):
        if item_name in TOOL_TYPES or item_name in PRODUCTION_BUILDER_FURNITURE_IDS:
            return MARKET_DEFAULT_CRAFTED_DEMAND
        return MARKET_DEFAULT_BULK_DEMAND

    @classmethod
    def calculate_price(cls, item_name, current_stock, base_price=None, demand=None):
        """
        Calculates dynamic unit price in Copper from Base Price and Supply vs Demand.
        Formula:
            ratio = clamp((D + k) / (S + k), MIN_MULT, MAX_MULT)
            P = max(1, round(P_base * ratio))
        Properties:
        - When S == D: ratio == 1.0 -> P == P_base.
        - When S > D (oversupply): P drops smoothly toward MIN_MULT * P_base.
        - When S < D (shortage): P rises smoothly toward MAX_MULT * P_base.
        - Strictly monotonic non-increasing as stock S rises.
        """
        if base_price is None:
            base_price = cls.get_base_price(item_name)
        base_price = max(1, int(base_price))

        d_val = max(1.0, float(demand if demand is not None else cls.default_demand_for_item(item_name)))
        s_val = max(0.0, float(current_stock))
        k = float(MARKET_DEMAND_ELASTICITY_K)

        raw_ratio = (d_val + k) / (s_val + k)
        clamped_ratio = max(
            float(MARKET_PRICE_MULTIPLIER_MIN),
            min(float(MARKET_PRICE_MULTIPLIER_MAX), raw_ratio),
        )
        calc = int(round(base_price * clamped_ratio))
        return max(cls.MIN_PRICE, calc)

    @classmethod
    def get_market_stock(cls, market, item_name):
        if not market or not hasattr(market, "inventory") or not isinstance(market.inventory, dict):
            return 0
        return max(0, int(market.inventory.get(item_name, 0)))

    @classmethod
    def compute_village_supplies(cls, building_manager=None):
        """Sum total market inventory across all completed markets in the village."""
        supplies = {}
        if not building_manager:
            return supplies
        for b in getattr(building_manager, "buildings", []):
            if getattr(b, "building_type", "") != "market" or getattr(b, "is_under_construction", False):
                continue
            inv = getattr(b, "inventory", None)
            if not isinstance(inv, dict):
                continue
            for item_name, qty in inv.items():
                supplies[item_name] = supplies.get(item_name, 0) + max(0, int(qty or 0))
        return supplies

    @classmethod
    def compute_village_demands(cls, villager_manager=None, building_manager=None,
                                furniture_manager=None):
        """Compute scalable real-life village demand per tradeable item."""
        demands = {}
        living_villagers = [
            v for v in (villager_manager.get_all_villagers() if villager_manager else [])
            if getattr(v, "is_alive", True)
        ]
        living_pop = len(living_villagers)
        families = list(getattr(villager_manager, "families", [])) if villager_manager else []

        # 1. Food & Water scale with living population
        demands["Potato"] = max(1, int(round(living_pop * DAILY_FOOD_REQUIREMENT * MARKET_FOOD_DEMAND_DAYS))) if living_pop > 0 else MARKET_DEFAULT_BULK_DEMAND
        demands["Water"] = max(1, int(round(living_pop * DAILY_WATER_REQUIREMENT * MARKET_WATER_DEMAND_DAYS))) if living_pop > 0 else MARKET_DEFAULT_BULK_DEMAND

        # 2. Tools scale with active workers whose jobs require each tool
        tool_workers = {tool_id: 0 for tool_id in TOOL_TYPES}
        toolmakers = 0
        for v in living_villagers:
            job_id = getattr(v, "job", "Unassigned")
            if job_id == "Toolmaker":
                toolmakers += 1
            req = get_job_required_tools(job_id)
            for tool_id, qty in req.items():
                if tool_id in tool_workers and qty > 0:
                    tool_workers[tool_id] += int(qty)
        for tool_id, w_count in tool_workers.items():
            demands[tool_id] = max(1, w_count)

        # 3. Construction & artisan raw materials scale with active sites & population
        wood_need = max(4, living_pop)
        stone_need = max(4, living_pop)
        if building_manager:
            for site in getattr(building_manager, "construction_sites", []):
                req = getattr(site, "required_cost", {}) or {}
                deliv = getattr(site, "delivered_cost", {}) or {}
                wood_need += max(0, int(req.get("Wood", 0)) - int(deliv.get("Wood", 0)))
                stone_need += max(0, int(req.get("Stone", 0)) - int(deliv.get("Stone", 0)))
        demands["Wood"] = wood_need
        demands["Stone"] = stone_need
        demands["Iron Ore"] = max(4, toolmakers * 5)
        demands["Iron Bar"] = max(3, toolmakers * 3)

        # 4. Furniture scales with unmet household/civic capacity + population
        installed_beds = 0
        installed_chests = 0
        installed_toilets = 0
        if furniture_manager:
            for f in getattr(furniture_manager, "furnitures", []):
                if getattr(f, "is_dropped", False) or getattr(f, "stored_in_id", None) is not None:
                    continue
                ftype = getattr(f, "furniture_type", "")
                if ftype == "bed":
                    installed_beds += 1
                elif ftype == "household_storage":
                    installed_chests += 1
                elif ftype == "toilet":
                    installed_toilets += 1
        if building_manager:
            for b in getattr(building_manager, "buildings", []):
                if getattr(b, "building_type", "") == "toilet" and not getattr(b, "is_under_construction", False):
                    installed_toilets += 1

        quotas = getattr(building_manager, "production_quotas", {}) or {}
        demands["bed"] = max(1, (living_pop - installed_beds) + max(1, len(families) // 2))
        demands["household_storage"] = max(1, len(families) - installed_chests)
        target_toilets = max(1, math.ceil(living_pop / max(1, MARKET_TOILET_VILLAGERS_PER_UNIT))) if living_pop > 0 else 1
        demands["toilet"] = max(1, target_toilets - installed_toilets)
        for furn_id in PRODUCTION_BUILDER_FURNITURE_IDS:
            if furn_id not in demands:
                demands[furn_id] = max(1, int(quotas.get(furn_id, 0) or 1))

        return demands

    @classmethod
    def get_village_wealth_factor(cls, total_wealth_copper, living_population):
        """Scale household-stall prices gently against the village's food-buying capacity."""
        food_prices = [
            cls.get_base_price(item_name)
            for item_name, category in MARKET_TRADEABLE_ITEMS.items()
            if category == "Food"
        ]
        if not food_prices or living_population <= 0:
            return 1.0
        daily_food_cost = max(1, round(sum(food_prices) / len(food_prices))) * max(1, DAILY_FOOD_REQUIREMENT)
        reference_wealth = max(1.0, living_population * daily_food_cost * MARKET_WEALTH_REFERENCE_DAYS)
        relative_wealth = max(0.01, max(0, int(total_wealth_copper)) / reference_wealth)
        factor = 1.0 + MARKET_WEALTH_PRICE_ELASTICITY * math.log(relative_wealth)
        return max(MARKET_WEALTH_PRICE_FACTOR_MIN, min(MARKET_WEALTH_PRICE_FACTOR_MAX, factor))

    @classmethod
    def get_price(cls, market, item_name):
        """
        Returns the active dynamic price for an item in a market.
        If auto_pricing is disabled on the market, returns configured market.prices[item_name].
        """
        if not market:
            return cls.get_base_price(item_name)

        if not getattr(market, "auto_pricing", True):
            if hasattr(market, "prices") and item_name in market.prices:
                return max(cls.MIN_PRICE, int(market.prices[item_name]))
            return cls.get_base_price(item_name)

        local_stock = cls.get_market_stock(market, item_name)
        supplies_map = getattr(market, "village_item_supplies", None)
        if isinstance(supplies_map, dict) and item_name in supplies_map:
            village_stock = max(local_stock, int(supplies_map.get(item_name, 0) or 0))
            effective_stock = (
                MARKET_LOCAL_SUPPLY_WEIGHT * local_stock
                + MARKET_VILLAGE_SUPPLY_WEIGHT * village_stock
            )
        else:
            effective_stock = local_stock

        demands_map = getattr(market, "village_item_demands", None)
        demand = demands_map.get(item_name) if isinstance(demands_map, dict) else None

        base_p = cls.get_base_price(item_name)
        wealth_factor = max(0.0, float(getattr(market, "village_wealth_factor", 1.0)))
        base_p = max(cls.MIN_PRICE, int(round(base_p * wealth_factor)))
        return cls.calculate_price(item_name, effective_stock, base_p, demand=demand)

    @classmethod
    def update_market_prices(cls, market):
        """
        Synchronizes market.prices with dynamic auto prices for all configured sale items.
        """
        if not market or not getattr(market, "assigned_family_id", None):
            return

        if not hasattr(market, "prices") or not isinstance(market.prices, dict):
            market.prices = {}

        item_keys = set(getattr(market, "sale_items", None) or []) & set(MARKET_TRADEABLE_ITEMS)

        for it in item_keys:
            market.prices[it] = cls.get_price(market, it)
