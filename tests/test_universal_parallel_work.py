"""
Unit Tests for Universal Parallel Work Execution across All Jobs & Activities.
Rules verified:
1. Universal parallel execution for all jobs (Farming, Building, Gathering, Household).
2. No artificial exclusive locks on shared facilities (Wells, Chests, Sites, Stockpiles).
3. First-come first-served pathing without false target conflicts on shared structures.
4. Clean reservation lifecycles: no lingering reservations trapping workers in [WAITING ROUTE].
"""

import unittest
import math
import pygame
from game.config import TILE_SIZE, WATERING_DURATION_INGAME_HOURS
from game.entities.villagers import Villager
from game.entities.servants import Servant
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.construction_site import ConstructionSite
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.permits import AreaPermit, PermitManager
from game.world.stockpile import StockpileManager, ResourceStack
from game.systems.core.day_cycle import DayCycleSystem
from game.world.navigation.pathfinding import GlobalPathRegistry

class TestUniversalParallelWork(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.reg = GlobalPathRegistry.get_instance()
        self.reg.reset()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.day_cycle = DayCycleSystem()

    def tearDown(self):
        self.reg.reset()

    def test_three_farmers_fetch_water_concurrently_no_waiting_route(self):
        """
        Verify that 3 farmers (e.g. Hugh, Agnes, Alice) needing water from the same Well
        can approach the Well simultaneously without ANY of them entering [WAITING ROUTE].
        """
        # Create a 2x2 Well at (14, 12)
        well_tiles = {(14, 12), (15, 12), (14, 13), (15, 13)}
        well = Building("well", well_tiles)
        self.bm.buildings.append(well)

        # Create 3 farmers at different initial positions
        hugh = Villager("vil_hugh", "Hugh", "Ward", "male", 30, 2, "Father", "fam_1", x=14.5 * TILE_SIZE, y=8.0 * TILE_SIZE)
        agnes = Villager("vil_agnes", "Agnes", "Ward", "female", 28, 2, "Mother", "fam_1", x=13.5 * TILE_SIZE, y=8.0 * TILE_SIZE)
        alice = Villager("vil_alice", "Alice", "Ward", "female", 20, 2, "Adult Daughter", "fam_1", x=15.5 * TILE_SIZE, y=8.0 * TILE_SIZE)

        farm = AreaPermit("farm_1", "Farm Lot", "farm", 13, 2, 4, 8)
        farm.assigned_workers = ["vil_hugh", "vil_agnes", "vil_alice"]
        farm.crop = "Potato"
        farm.tile_crops = {t: {"crop": "Potato", "growth_days": 1.0, "watered_today": False, "unwatered_days": 0, "is_dead": False} for t in farm.tiles}
        self.pm.permits.append(farm)

        for f in (hugh, agnes, alice):
            f.inventory["Watering_Can"] = 1
            f.has_water = False
            f.water_day = -1
            f.assigned_permit_id = "farm_1"

        all_entities = [hugh, agnes, alice]

        # Simulate 15 frames
        for _ in range(15):
            for worker in all_entities:
                worker.update(0.1, self.pm, self.bm, all_entities, player=None,
                              stockpile_manager=self.sm, furniture_manager=self.fm,
                              day_cycle=self.day_cycle)
            # NONE of the 3 farmers must ever enter [WAITING ROUTE] while fetching water
            self.assertFalse(hugh.is_waiting_for_path, "Hugh should never be in waiting route!")
            self.assertFalse(agnes.is_waiting_for_path, "Agnes should never be in waiting route!")
            self.assertFalse(alice.is_waiting_for_path, "Alice should never be in waiting route!")

        # All 3 farmers must have successfully obtained water concurrently
        self.assertTrue(hugh.has_water, "Hugh should have obtained water!")
        self.assertTrue(agnes.has_water, "Agnes should have obtained water!")
        self.assertTrue(alice.has_water, "Alice should have obtained water!")

    def test_three_farmers_water_different_tiles_in_parallel(self):
        """
        Verify that 3 farmers watering the same farm lot execute in PARALLEL simultaneously
        on distinct tiles without artificial serialization.
        """
        farm = AreaPermit("farm_1", "Farm Lot", "farm", 10, 10, 4, 6)
        farm.assigned_workers = ["vil_1", "vil_2", "vil_3"]
        farm.crop = "Potato"
        current_day = self.day_cycle.day_number
        farm.tile_crops = {t: {"crop": "Potato", "growth_days": 1.0, "watered_today": False, "unwatered_days": 0, "is_dead": False} for t in farm.tiles}
        self.pm.permits.append(farm)

        v1 = Villager("vil_1", "Worker1", "Test", "male", 25, 2, "Father", "fam_1", x=10.5 * TILE_SIZE, y=10.5 * TILE_SIZE)
        v2 = Villager("vil_2", "Worker2", "Test", "female", 24, 2, "Mother", "fam_1", x=11.5 * TILE_SIZE, y=10.5 * TILE_SIZE)
        v3 = Villager("vil_3", "Worker3", "Test", "male", 26, 2, "Adult Son", "fam_1", x=12.5 * TILE_SIZE, y=10.5 * TILE_SIZE)

        all_workers = [v1, v2, v3]
        for w in all_workers:
            w.inventory["Watering_Can"] = 1
            w.has_water = True
            w.water_day = current_day
            w.assigned_permit_id = "farm_1"

        # Update 1 frame to claim initial unwatered tiles
        for w in all_workers:
            w.update(0.05, self.pm, self.bm, all_workers, player=None,
                     stockpile_manager=self.sm, furniture_manager=self.fm,
                     day_cycle=self.day_cycle)

        # All 3 workers must be WATERING
        self.assertEqual(v1.task, "WATERING")
        self.assertEqual(v2.task, "WATERING")
        self.assertEqual(v3.task, "WATERING")

        # Each must have claimed a DISTINCT tile
        tiles = {v1.current_work_tile, v2.current_work_tile, v3.current_work_tile}
        self.assertEqual(len(tiles), 3, "All 3 farmers must have distinct work tiles!")

        # None of them should be in [WAITING ROUTE]
        for w in all_workers:
            self.assertFalse(w.is_waiting_for_path, f"{w.first_name} should not be waiting route!")

    def test_multiple_builders_haul_and_deliver_in_parallel(self):
        """
        Verify that multiple builders collecting from the same stockpile and delivering
        to the same construction site work in parallel without blocking each other.
        """
        site_tiles = {(20, 20), (21, 20), (20, 21), (21, 21)}
        site = ConstructionSite("wooden_structure", site_tiles)
        site.required_cost = {"Wood": 20, "Stone": 0}
        site.delivered_cost = {"Wood": 0, "Stone": 0}
        site.reserved_cost = {"Wood": 0, "Stone": 0}
        self.bm.construction_sites.append(site)

        # Stockpile with wood at (10, 10)
        self.sm.stacks.append(ResourceStack("Wood", 50, 10, 10))

        s1 = Servant("s1", "Builder1", x=10.0 * TILE_SIZE, y=10.0 * TILE_SIZE)
        s2 = Servant("s2", "Builder2", x=10.5 * TILE_SIZE, y=10.0 * TILE_SIZE)
        s1.work_priorities["Building"] = 1
        s2.work_priorities["Building"] = 1
        all_servants = [s1, s2]

        resources = {"Wood": 50, "Stone": 0}

        # Step 1: Both servants should be able to FETCH without conflict
        s1.update(0.1, self.bm, self.pm, self.sm, resources, player=None, all_servants=all_servants)
        s2.update(0.1, self.bm, self.pm, self.sm, resources, player=None, all_servants=all_servants)

        self.assertFalse(s1.is_waiting_for_path)
        self.assertFalse(s2.is_waiting_for_path)

        # Fast forward: both fetch wood
        s1.carried_res = "Wood"
        s1.carried_amount = 5
        s1.state = "HAULING"
        s1.target_site = site

        s2.carried_res = "Wood"
        s2.carried_amount = 5
        s2.state = "HAULING"
        s2.target_site = site

        # Move towards construction site
        for _ in range(10):
            s1.update(0.1, self.bm, self.pm, self.sm, resources, player=None, all_servants=all_servants)
            s2.update(0.1, self.bm, self.pm, self.sm, resources, player=None, all_servants=all_servants)

        # Both arrive and deposit materials in parallel
        self.assertFalse(s1.is_waiting_for_path)
        self.assertFalse(s2.is_waiting_for_path)

    def test_household_family_members_access_chest_concurrently(self):
        """
        Verify that multiple family members accessing the household chest
        do not trigger TARGET_CONFLICT or [WAITING ROUTE] on the chest tile.
        """
        chest = Furniture("chest_1", "household_storage", 5, 5, permit_id="house_1", family_id="fam_1")
        chest.store_item("Hoe", 3)
        chest.store_item("Watering_Can", 3)
        self.fm.furnitures.append(chest)

        v1 = Villager("v1", "Father", "Ward", "male", 40, 2, "Father", "fam_1", x=4.0 * TILE_SIZE, y=5.0 * TILE_SIZE)
        v2 = Villager("v2", "Mother", "Ward", "female", 38, 2, "Mother", "fam_1", x=6.0 * TILE_SIZE, y=5.0 * TILE_SIZE)
        all_ents = [v1, v2]

        # Both need to equip job tools from the chest
        for v in (v1, v2):
            v.task = "EQUIPPING_JOB_TOOLS"
            v.assigned_permit_id = "farm_1"

        # Update both towards chest
        v1.update(0.05, self.pm, self.bm, all_ents, player=None,
                  stockpile_manager=self.sm, furniture_manager=self.fm,
                  day_cycle=self.day_cycle)
        v2.update(0.05, self.pm, self.bm, all_ents, player=None,
                  stockpile_manager=self.sm, furniture_manager=self.fm,
                  day_cycle=self.day_cycle)

        self.assertFalse(v1.is_waiting_for_path, "v1 should not be blocked accessing chest!")
        self.assertFalse(v2.is_waiting_for_path, "v2 should not be blocked accessing chest!")

if __name__ == "__main__":
    unittest.main()
