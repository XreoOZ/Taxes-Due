import unittest
import pygame
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()
pygame.display.set_mode((800, 600))

from game.data.config import (
    TILE_SIZE,
    EMERGENCY_STUCK_TIMEOUT,
    EMERGENCY_COLLISION_BYPASS_DURATION,
)
from game.buildings.buildings import Building, ConstructionSite, DemolitionSite, BuildingManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.entities.servants import Servant, ServantManager
from game.world.pathfinding import GlobalPathRegistry, Pathfinder, is_narrow_passage_tile
from game.world.stockpile import StockpileManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.world.permits import PermitManager, AreaPermit


class TestBuildingSolidityCancellationAndStuckRecovery(unittest.TestCase):
    def setUp(self):
        GlobalPathRegistry.get_instance().reset()
        self.bm = BuildingManager()

    def tearTo(self):
        GlobalPathRegistry.get_instance().reset()

    def test_construction_site_is_not_solid(self):
        """Blueprints and in-progress builds must NOT be solid."""
        # 1. Wooden structure site
        site_wood = ConstructionSite("wooden_structure", {(1, 1), (2, 1), (1, 2), (2, 2)})
        self.assertFalse(site_wood.is_solid)
        self.assertEqual(site_wood.get_wall_rects(TILE_SIZE), [])

        # 2. Well site
        site_well = ConstructionSite("well", {(5, 5), (6, 5), (5, 6), (6, 6)})
        self.assertFalse(site_well.is_solid)
        self.assertEqual(site_well.get_wall_rects(TILE_SIZE), [])

        # 3. Market site
        site_market = ConstructionSite("market", {(10, 10), (11, 10), (12, 10), (10, 11), (11, 11), (12, 11)})
        self.assertFalse(site_market.is_solid)
        self.assertEqual(site_market.get_wall_rects(TILE_SIZE), [])

    def test_completed_market_and_well_solidity(self):
        """Completed Market and Well must be SOLID."""
        # Completed Market 3x2
        market_tiles = {(10, 10), (11, 10), (12, 10), (10, 11), (11, 11), (12, 11)}
        market = Building("market", market_tiles)
        self.assertTrue(market.is_solid)
        wall_rects = market.get_wall_rects(TILE_SIZE)
        self.assertEqual(len(wall_rects), 6)  # 6 tiles solid

        # Completed Well 2x2
        well_tiles = {(5, 5), (6, 5), (5, 6), (6, 6)}
        well = Building("well", well_tiles)
        self.assertTrue(well.is_solid)
        self.assertEqual(len(well.get_wall_rects(TILE_SIZE)), 4)

    def test_demolition_site_is_not_solid(self):
        """Demolition sites must NOT be solid and must not provide wall rects."""
        market_tiles = {(10, 10), (11, 10), (12, 10), (10, 11), (11, 11), (12, 11)}
        market = Building("market", market_tiles)
        self.bm.buildings.append(market)
        self.bm.rebuild_tile_cache()

        # Before demolition, completed market is solid
        self.assertIn((10, 10), self.bm._tile_to_building)
        self.assertEqual(len(self.bm.get_all_wall_rects(TILE_SIZE)), 6)

        # Start demolition
        self.bm.start_demolition(market)
        self.assertEqual(len(self.bm.demolition_sites), 1)
        self.assertNotIn(market, self.bm.buildings)

        # Under demolition: not in tile cache and no solid walls!
        self.assertNotIn((10, 10), self.bm._tile_to_building)
        self.assertEqual(len(self.bm.get_all_wall_rects(TILE_SIZE)), 0)

    def test_cancel_construction_refunds_and_releases(self):
        """Cancelling construction refunds materials, releases reservations, and stops workers."""
        site = ConstructionSite("wooden_structure", {(1, 1), (2, 1), (1, 2), (2, 2)})
        site.delivered_cost = {"Wood": 10, "Stone": 5}
        site.reserved_cost = {"Wood": 6, "Stone": 0}
        self.bm.construction_sites.append(site)

        resources = {"Wood": 20, "Stone": 10}
        sm = StockpileManager()
        sm.drop_resource("Wood", 10, 0, 0)
        stack = sm.stacks[-1]
        stack.reserved_amount = 6

        servant = Servant("servant_1", "Alden", 0, 0)
        servant.target_site = site
        servant.task = "BUILD"
        servant.state = "BUILD"

        success = self.bm.cancel_construction(site, resources=resources, stockpile_manager=sm, all_servants=[servant])
        self.assertTrue(success)
        self.assertNotIn(site, self.bm.construction_sites)
        # Materials refunded
        self.assertEqual(resources["Wood"], 30)  # 20 + 10
        self.assertEqual(resources["Stone"], 15)  # 10 + 5
        # Stockpile reservation released
        self.assertEqual(stack.reserved_amount, 0)
        # Worker reset
        self.assertIsNone(servant.target_site)
        self.assertEqual(servant.task, "IDLE")

    def test_cancel_demolition_restores_building(self):
        """Cancelling demolition halts demolition, restores building and solidity without data loss."""
        market_tiles = {(10, 10), (11, 10), (12, 10), (10, 11), (11, 11), (12, 11)}
        market = Building("market", market_tiles)
        market.inventory = {"Potato": 42}
        self.bm.buildings.append(market)
        self.bm.start_demolition(market)

        demo_site = self.bm.demolition_sites[0]
        servant = Servant("servant_1", "Alden", 0, 0)
        servant.target_demolition = demo_site
        servant.task = "DEMOLISH"

        success = self.bm.cancel_demolition(demo_site, all_servants=[servant])
        self.assertTrue(success)
        self.assertEqual(len(self.bm.demolition_sites), 0)
        self.assertIn(market, self.bm.buildings)
        self.assertEqual(market.inventory["Potato"], 42)
        self.assertTrue(market.is_solid)
        self.assertIn((10, 10), self.bm._tile_to_building)
        self.assertIsNone(servant.target_demolition)
        self.assertEqual(servant.task, "IDLE")

    def test_emergency_stuck_recovery_3_seconds(self):
        """If AI is stuck unable to move for >= 3 continuous seconds, emergency recovery triggers."""
        v = Villager("vil_1", "John", "Doe", "Male", 25, 1, "Father", "fam_1", x=48.0, y=48.0)
        # Block next step tile with another occupant in a narrow passage / exclusive target
        reg = GlobalPathRegistry.get_instance()
        reg.occupy_tile("blocker_ai", (2, 1))

        # Target at (2, 1) with exclusive_target=True
        target_x = 2 * TILE_SIZE + 16.0
        target_y = 1 * TILE_SIZE + 16.0

        # Attempt to move for 1.0s twice (total 2.0s < 3.0s)
        v._move_towards(target_x, target_y, dt=1.0, exclusive_target=True)
        self.assertLess(v.hard_stuck_timer, EMERGENCY_STUCK_TIMEOUT)
        self.assertEqual(v.collision_bypass_timer, 0.0)

        v._move_towards(target_x, target_y, dt=1.0, exclusive_target=True)
        self.assertLess(v.hard_stuck_timer, EMERGENCY_STUCK_TIMEOUT)
        self.assertEqual(v.collision_bypass_timer, 0.0)

        # Move for another 1.5s (total 3.5s >= 3.0s timeout)
        v._move_towards(target_x, target_y, dt=1.5, exclusive_target=True)
        # Emergency collision bypass should now be activated!
        self.assertGreater(v.collision_bypass_timer, 0.0)
        self.assertEqual(v.hard_stuck_timer, 0.0)


if __name__ == "__main__":
    unittest.main()
