"""Shared access to the landlord's coin-only treasury furniture."""

from game.systems.currency import (
    CURRENCY_DENOMINATIONS,
    canonical_denomination,
    compact_currency_wallet,
    to_copper,
    transfer_currency_value,
)


class LordTreasurySystem:
    @staticmethod
    def get_chest(furniture_manager):
        return (furniture_manager.get_lord_treasury_chest()
                if furniture_manager and hasattr(furniture_manager, "get_lord_treasury_chest")
                else None)

    @classmethod
    def wallet(cls, furniture_manager):
        chest = cls.get_chest(furniture_manager)
        if not chest:
            return {denomination: 0 for denomination in CURRENCY_DENOMINATIONS}
        wallet = {denomination: 0 for denomination in CURRENCY_DENOMINATIONS}
        for item, amount in getattr(chest, "inventory", {}).items():
            denomination = canonical_denomination(item)
            if denomination:
                wallet[denomination] += max(0, int(amount))
        return compact_currency_wallet(wallet)

    @classmethod
    def value(cls, furniture_manager):
        return to_copper(cls.wallet(furniture_manager))

    @classmethod
    def withdraw_covering(cls, furniture_manager, destination_wallet, amount):
        chest = cls.get_chest(furniture_manager)
        if not chest:
            return False, "Lord Treasury Chest is unavailable."
        success, message = transfer_currency_value(chest.inventory, destination_wallet, amount)
        if success:
            cls._mark_wealth_dirty()
        return success, message

    @classmethod
    def deposit_all(cls, furniture_manager, source_wallet):
        chest = cls.get_chest(furniture_manager)
        if not chest or not isinstance(source_wallet, dict):
            return False
        moved = False
        for key in list(source_wallet):
            denomination = canonical_denomination(key)
            if not denomination:
                continue
            amount = max(0, int(source_wallet.get(key, 0)))
            if amount:
                chest.store_item(denomination, amount)
                moved = True
            source_wallet.pop(key, None)
        compact_currency_wallet(chest.inventory)
        if moved:
            cls._mark_wealth_dirty()
        return moved

    @staticmethod
    def _mark_wealth_dirty():
        try:
            from game.systems.wealth_system import VillageWealthSystem
            VillageWealthSystem.mark_dirty()
        except ImportError:
            pass
