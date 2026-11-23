"""Regression: a starving villager must BUY food when household food exists
only in unreachable member pockets.

Universal rule under test: NEED -> no reachable resource -> physically acquire
it (market purchase). Household-level "enough food" accounting must not count
food that the starving member cannot physically reach (another member's
pocket across the map), otherwise the purchase is skipped forever and the
villager oscillates between SEEKING_FOOD and work without ever eating.
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
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.systems.economy.market_service import MarketService


class TestUnreachablePocketFood(unittest.TestCase):
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

        # Second member carries the household's only food — but is standing
        # at the market, physically unreachable for John.
        self.member_b = Villager(2, "Jane", "Smith", "Female", 28, 1, "Mother", "fam_1")
        self.member_b.x = 15 * TILE_SIZE
        self.member_b.y = 15 * TILE_SIZE
        self.member_b.inventory["Potato"] = 1
        self.member_b.daily_food_consumed = 1  # already ate today
        self.member_b.hunger = 100.0
        self.member_b.thirst = 100.0
        self.member_b.need_toilet = 100.0
        self.member_b.task = "IDLE"

        self.fam.members.extend([self.villager, self.member_b])
        self.villager_manager.families.append(self.fam)

        lot_tiles = {(x, y) for x in range(4, 7) for y in range(4, 7)}
        self.permit = self.permit_manager.add_permit("Smith Housing", "housing", lot_tiles)
        self.fam.assigned_permit_id = self.permit.id

        # Household chest holds coins (no food).
        chest = Furniture("chest_1", "household_storage", 5, 5,
                          permit_id=self.permit.id, family_id="fam_1")
        chest.inventory["Copper"] = 100
        self.furniture_manager.furnitures.append(chest)

        market_tiles = {(x, y) for x in range(14, 17) for y in range(14, 17)}
        self.market = Building("market", market_tiles, door_pos=(15, 16), door_side="bottom")
        self.market.inventory = {"Potato": 20}
        self.market.prices = {"Potato": 3}
        self.market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.building_manager.buildings.append(self.market)

    def _tick(self, n=1500, dt=0.1):
        for _ in range(n):
            self.villager.update(
                dt, self.permit_manager, self.building_manager, [], None,
                stockpile_manager=self.stockpile_manager,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
            )

    def test_starving_member_buys_when_only_pocket_food_is_unreachable(self):
        self.villager.hunger = 5.0
        self.villager.daily_food_consumed = 0
        self.villager.task = "IDLE"

        # Household accounting sees member_b's pocket potato -> need == 0,
        # which is exactly the trap: stock exists on paper but John cannot
        # reach it, so he must still go buy.
        need = MarketService.get_household_food_need(
            self.villager, furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager)
        self.assertEqual(need, 0)

        self._tick()

        self.assertLess(
            self.market.inventory.get("Potato", 0), 20,
            "Starving villager never bought food: household pocket food "
            "counted as reachable stock and blocked the market purchase.")
        self.assertGreater(self.villager.hunger, 5.0)


if __name__ == "__main__":
    unittest.main()
