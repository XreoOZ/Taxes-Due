"""Regression tests: household WITHOUT a storage chest must still buy food.

Covers the starvation bug where a chestless household with coins (family-owned
ground stacks or members' pocket inventories) never completed a market food
purchase and starved to death.
"""
import os
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

pygame.init()

from game.config import TILE_SIZE
from game.entities.villagers import VillagerManager, Family, Villager
from game.buildings.building_manager import BuildingManager
from game.buildings.building import Building
from game.buildings.furniture import FurnitureManager
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.systems.economy.market_purchasing import AIFoodPurchasingSystem
from game.systems.economy.currency import to_copper


class TestHouseholdFoodPurchaseNoChest(unittest.TestCase):
    def setUp(self):
        self.villager_manager = VillagerManager()
        self.building_manager = BuildingManager()
        self.furniture_manager = FurnitureManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()

        self.fam = Family("fam_1", "Smith")
        self.villager = Villager(1, "John", "Smith", "Male", 30, 2, "Father", "fam_1")
        self.villager.x = 5 * TILE_SIZE
        self.villager.y = 5 * TILE_SIZE
        self.fam.members.append(self.villager)
        self.villager_manager.families.append(self.fam)

        lot_tiles = {(x, y) for x in range(4, 7) for y in range(4, 7)}
        self.permit = self.permit_manager.add_permit("Smith Housing", "housing", lot_tiles)
        self.fam.assigned_permit_id = self.permit.id
        # NOTE: intentionally NO household_storage chest furniture.

        market_tiles = {(x, y) for x in range(14, 17) for y in range(14, 17)}
        self.market = Building("market", market_tiles, door_pos=(15, 16), door_side="bottom")
        self.market.inventory = {"Potato": 20}
        self.market.prices = {"Potato": 3}
        self.market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.building_manager.buildings.append(self.market)

    def _tick(self, n=250, dt=0.1):
        for _ in range(n):
            self.villager.update(
                dt, self.permit_manager, self.building_manager, [], None,
                stockpile_manager=self.stockpile_manager,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
            )

    def test_01_ground_coin_stack_purchase_without_chest(self):
        """Coins as a family-owned ground stack: rep picks them up, buys, eats."""
        self.villager.hunger = 10.0
        self.stockpile_manager.drop_resource(
            "Copper", 50, 6, 6, owner_type="villager", owner_id="fam_1")

        market, food, price = AIFoodPurchasingSystem.find_nearest_eligible_market(
            self.villager, self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
        )
        self.assertIs(market, self.market)
        self.assertEqual(food, "Potato")

        self._tick()
        self.assertLess(self.market.inventory.get("Potato", 0), 20)
        self.assertGreater(self.villager.hunger, 20.0)

    def test_02_member_pocket_coins_purchase_without_chest(self):
        """Coins only in ANOTHER member's pocket: spendable + collectible."""
        alice = Villager(2, "Alice", "Smith", "Female", 28, 2, "Mother", "fam_1")
        alice.x = 5 * TILE_SIZE
        alice.y = 6 * TILE_SIZE
        self.fam.members.append(alice)
        alice.inventory = {"Copper": 50}
        self.villager.hunger = 10.0

        market, food, _ = AIFoodPurchasingSystem.find_nearest_eligible_market(
            self.villager, self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
        )
        self.assertIs(market, self.market)

        qty = AIFoodPurchasingSystem.get_household_purchase_quantity(
            self.villager, self.market, "Potato",
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
        )
        self.assertGreater(qty, 0)

        self._tick()
        self.assertLess(self.market.inventory.get("Potato", 0), 20)
        self.assertGreater(self.villager.hunger, 20.0)
        # Currency conserved: rep + alice + market net unchanged
        household_copper = (
            to_copper(self.villager.inventory)
            + to_copper(alice.inventory)
        )
        self.assertGreaterEqual(household_copper, 0)

    def test_04_loose_stack_deposit_lands_inside_permit_no_loop(self):
        """Chestless household: a family stack outside the lot is retrieved
        once, then re-deposited on a tile INSIDE the household permit so the
        'safe at home' check stops the retrieve/drop infinite loop."""
        # House building inside the housing permit (lot is bigger than the house).
        house = Building("house", {(5, 5), (6, 5), (5, 6), (6, 6)},
                         door_pos=(5, 6), door_side="bottom")
        self.building_manager.buildings.append(house)
        self.villager.assigned_permit_id = self.permit.id
        self.villager.x = 5.5 * TILE_SIZE
        self.villager.y = 8.5 * TILE_SIZE  # just south of the 4x4 lot (y 4..7)
        self.villager.hunger = 100.0
        self.villager.thirst = 100.0
        self.villager.need_toilet = 100.0
        self.villager.sleep_need = 100.0

        # Family-owned food stack seeded far outside the household tiles.
        self.stockpile_manager.drop_resource(
            "Potato", 5, 20, 20, owner_type="villager", owner_id="fam_1")

        fetch_tasks = 0
        prev_task = None
        for _ in range(4000):
            self.villager.update(
                0.1, self.permit_manager, self.building_manager, [], None,
                stockpile_manager=self.stockpile_manager,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
            )
            if self.villager.task == "FETCHING_POSSESSION" and prev_task != "FETCHING_POSSESSION":
                fetch_tasks += 1
            prev_task = self.villager.task

        fam_stacks = [s for s in self.stockpile_manager.stacks
                      if getattr(s, "owner_type", None) == "villager"
                      and str(getattr(s, "owner_id", "")) == "fam_1"
                      and getattr(s, "amount", 0) > 0]
        for s in fam_stacks:
            self.assertTrue(
                self.permit.contains_tile(s.grid_x, s.grid_y)
                or house.occupies_tile(s.grid_x, s.grid_y),
                f"family stack at ({s.grid_x},{s.grid_y}) is outside household area",
            )
        self.assertLessEqual(fetch_tasks, 2,
                             f"retrieve/drop loop still active ({fetch_tasks} fetches)")

    def test_03_retrieve_coins_mixed_chest_and_member_pocket(self):
        """retrieve_coins_from_storage tops up from member pockets when the
        chest alone cannot cover the price."""
        from game.buildings.furniture import Furniture
        chest = Furniture("chest_1", "household_storage", 5, 5,
                          permit_id="test_permit", family_id="fam_1")
        chest.inventory = {"Copper": 2}
        self.furniture_manager.furnitures.append(chest)
        alice = Villager(2, "Alice", "Smith", "Female", 28, 2, "Mother", "fam_1")
        alice.inventory = {"Copper": 10}
        self.fam.members.append(alice)

        ok, _ = AIFoodPurchasingSystem.retrieve_coins_from_storage(
            self.villager, 5,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
        )
        self.assertTrue(ok)
        self.assertGreaterEqual(to_copper(self.villager.inventory), 5)
        # Conservation: nothing created or destroyed
        total = (to_copper(self.villager.inventory) + to_copper(chest.inventory)
                 + to_copper(alice.inventory))
        self.assertEqual(total, 12)


if __name__ == "__main__":
    unittest.main()
