"""
Market Pricing System (Dynamic Scarcity and Abundance Curve)
Calculates dynamic unit prices in Copper based on actual in-market stock.
Higher stock -> lower price. Lower stock -> higher price.
Minimum price: 1 Copper. No maximum price.
Zero hardcoding, config-driven.
"""
import math
from game.data.config import DEFAULT_ITEM_PRICES

class MarketPricingSystem:
    # Baseline reference stock for normal default price
    BASELINE_STOCK = 20
    CURVE_K = 5.0
    MIN_PRICE = 1

    @classmethod
    def get_base_price(cls, item_name):
        return DEFAULT_ITEM_PRICES.get(item_name, 3)

    @classmethod
    def calculate_price(cls, item_name, current_stock, base_price=None):
        """
        Calculates dynamic unit price in Copper.
        Formula:
            P = max(1, round(P_base * (S_0 + k) / (S + k)))
        Properties:
        - When S = 0: P = P_base * (25 / 5) = 5 * P_base (scarcity premium)
        - When S = S_0 (20): P = P_base * (25 / 25) = P_base
        - When S > S_0: P decreases monotonically towards MIN_PRICE (1 Copper)
        - Price is strictly >= 1 Copper, strictly integer, non-negative.
        """
        if base_price is None:
            base_price = cls.get_base_price(item_name)
        base_price = max(1, int(base_price))

        stock = max(0, int(current_stock))
        ratio = (cls.BASELINE_STOCK + cls.CURVE_K) / (stock + cls.CURVE_K)
        calc = int(round(base_price * ratio))
        return max(cls.MIN_PRICE, calc)

    @classmethod
    def get_market_stock(cls, market, item_name):
        if not market or not hasattr(market, "inventory") or not isinstance(market.inventory, dict):
            return 0
        return max(0, int(market.inventory.get(item_name, 0)))

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

        stock = cls.get_market_stock(market, item_name)
        base_p = cls.get_base_price(item_name)
        return cls.calculate_price(item_name, stock, base_p)

    @classmethod
    def update_market_prices(cls, market):
        """
        Synchronizes market.prices with dynamic auto prices for all known items
        and items in inventory, making it immediately available to Agent 2's UI.
        """
        if not market or not getattr(market, "auto_pricing", True):
            return

        if not hasattr(market, "prices") or not isinstance(market.prices, dict):
            market.prices = {}

        # Items to price: default items + items in market inventory
        item_keys = set(DEFAULT_ITEM_PRICES.keys())
        if hasattr(market, "inventory") and isinstance(market.inventory, dict):
            item_keys.update(market.inventory.keys())

        for it in item_keys:
            market.prices[it] = cls.get_price(market, it)
