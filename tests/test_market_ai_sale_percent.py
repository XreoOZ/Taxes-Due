import unittest
import pygame
from game.buildings.building import Building
from game.buildings.furniture import Furniture, FurnitureManager
from game.data.config import (
    MARKET_HOUSEHOLD_SALE_PERCENT_MIN,
    MARKET_HOUSEHOLD_SALE_PERCENT_MAX,
    MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT,
)
from game.systems.economy.household_stall_system import HouseholdStallSystem
from game.ui.modals.market_modal import MarketProfileModal


class TestMarketAISalePercent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.fm = FurnitureManager()

    def test_set_item_allocation_clamp_10_to_100(self):
        tiles = {(10, 10), (10, 11)}
        market = Building("market", tiles)
        family_id = "fam_1"
        HouseholdStallSystem.assign_stall(market, family_id)

        # Test below 10 clamps to 10
        pct = HouseholdStallSystem.set_item_allocation(market, "Potato", 5)
        self.assertEqual(pct, 10)
        self.assertEqual(HouseholdStallSystem.get_item_allocation(market, "Potato"), 10)

        # Test 0 clamps to 10
        pct = HouseholdStallSystem.set_item_allocation(market, "Potato", 0)
        self.assertEqual(pct, 10)

        # Test valid percentage (e.g. 50%)
        pct = HouseholdStallSystem.set_item_allocation(market, "Potato", 50)
        self.assertEqual(pct, 50)
        self.assertEqual(HouseholdStallSystem.get_item_allocation(market, "Potato"), 50)

        # Test above 100 clamps to 100
        pct = HouseholdStallSystem.set_item_allocation(market, "Potato", 125)
        self.assertEqual(pct, 100)
        self.assertEqual(HouseholdStallSystem.get_item_allocation(market, "Potato"), 100)

    def test_calculate_allocatable_goods_uses_clamped_percent(self):
        tiles = {(10, 10), (10, 11)}
        market = Building("market", tiles)
        family_id = "fam_1"
        HouseholdStallSystem.assign_stall(market, family_id)

        chest = Furniture("furn_chest_1", "household_storage", 5, 5, permit_id="p1", family_id=family_id)
        chest.inventory = {"Potato": 100}
        self.fm.furnitures.append(chest)

        # Default is 20%
        HouseholdStallSystem.set_item_allocation(market, "Potato", 20)
        alloc = HouseholdStallSystem.calculate_allocatable_goods(market, family_id, "Potato", self.fm)
        self.assertEqual(alloc, 20)

        # 10% min
        HouseholdStallSystem.set_item_allocation(market, "Potato", 10)
        alloc = HouseholdStallSystem.calculate_allocatable_goods(market, family_id, "Potato", self.fm)
        self.assertEqual(alloc, 10)

        # 100% max
        HouseholdStallSystem.set_item_allocation(market, "Potato", 100)
        alloc = HouseholdStallSystem.calculate_allocatable_goods(market, family_id, "Potato", self.fm)
        self.assertEqual(alloc, 100)

    def test_market_modal_num_field_commit_and_bounds(self):
        tiles = {(10, 10), (10, 11)}
        market = Building("market", tiles)
        family_id = "fam_1"
        HouseholdStallSystem.assign_stall(market, family_id)
        market.sale_items = ["Potato"]
        HouseholdStallSystem.set_item_allocation(market, "Potato", 20)

        modal = MarketProfileModal()
        modal.open(market)

        # Mock num_input state for alloc field
        pct_key = ("num", "alloc", "Potato")
        modal.num_fields[pct_key] = {
            "rect": pygame.Rect(0, 0, 50, 20),
            "kind": "alloc",
            "item": "Potato",
            "min": MARKET_HOUSEHOLD_SALE_PERCENT_MIN,
            "max": MARKET_HOUSEHOLD_SALE_PERCENT_MAX,
        }

        # Typing 5 -> should commit as 10
        modal.num_input.focus(pct_key, 20)
        modal.num_input.text = "5"
        modal._commit_num_field()
        self.assertEqual(market.item_allocations["Potato"], 10)

        # Typing 75 -> should commit as 75
        modal.num_input.focus(pct_key, 10)
        modal.num_input.text = "75"
        modal._commit_num_field()
        self.assertEqual(market.item_allocations["Potato"], 75)

        # Typing 200 -> should commit as 100
        modal.num_input.focus(pct_key, 75)
        modal.num_input.text = "200"
        modal._commit_num_field()
        self.assertEqual(market.item_allocations["Potato"], 100)


if __name__ == "__main__":
    unittest.main()
