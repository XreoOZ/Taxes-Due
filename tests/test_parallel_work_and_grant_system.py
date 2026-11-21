import unittest
import math
import time
import pygame

from game.config import (
    TILE_SIZE,
    DEFAULT_STARTER_TOOLS,
    DEFAULT_RESOURCES,
    SERVANT_CARRY_CAPACITY
)
from game.buildings.buildings import Building, BuildingManager, ConstructionSite
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager, ResourceStack
from game.world.pathfinding import GlobalPathRegistry, Pathfinder
from game.entities.servants import Servant, ServantManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.buildings.furniture import Furniture, FurnitureManager

class TestParallelWorkAndGrantSystem(unittest.TestCase):
    def setUp(self):
        GlobalPathRegistry.get_instance().clear()
        self.bm = BuildingManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.resources = dict(DEFAULT_RESOURCES)
        self.sm.initialize_starter_stockpile(self.resources, self.pm, DEFAULT_STARTER_TOOLS)
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.serv_m = ServantManager()

    def tearDown(self):
        GlobalPathRegistry.get_instance().clear()
        DEFAULT_RESOURCES.update({"Wood": 1000, "Food": 1000, "Stone": 1000, "Water": 1000})

    def test_parallel_resource_collection_from_same_tile_no_waiting(self):
        """
        Verify that multiple builders collecting from the same resource tile
        do so simultaneously without waiting for the other builder to finish.
        """
        # Place a 4x4 building site needing 20 Wood
        tiles = {(15, 10), (16, 10), (15, 11), (16, 11)}
        site = ConstructionSite("wooden_structure", tiles, (15, 11), "bottom")
        self.bm.construction_sites.append(site)
        site.required_cost["Wood"] = 20
        site.required_cost["Stone"] = 0
        site.delivered_cost["Wood"] = 0
        site.delivered_cost["Stone"] = 0
        site.reserved_cost["Wood"] = 0
        site.reserved_cost["Stone"] = 0

        # Stockpile at (5, 5) with 50 Wood
        self.sm.stacks = [ResourceStack("Wood", 50, 5, 5, owner_type="landlord")]

        # 2 Servants initialized
        s1 = self.serv_m.servants[0]
        s2 = self.serv_m.servants[1]
        s1.x, s1.y = 100.0, 100.0
        s2.x, s2.y = 120.0, 100.0

        # Run 1 evaluation step: both servants should be assigned FETCHING
        s1.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)
        s2.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)

        self.assertEqual(s1.state, "FETCHING")
        self.assertEqual(s2.state, "FETCHING")

        # Step 2: Path generation and movement towards stockpile
        s1.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)
        s2.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)

        # Crucial check: Neither servant is put into [WAITING ROUTE]
        self.assertFalse(s1.is_waiting_for_path, "Servant 1 must not be waiting for route")
        self.assertFalse(s2.is_waiting_for_path, "Servant 2 must not be waiting for route")
        self.assertFalse(getattr(s1, "wait_timer", 0.0) > 0.0)
        self.assertFalse(getattr(s2, "wait_timer", 0.0) > 0.0)

        # Both servants must have active valid paths
        self.assertTrue(len(s1.current_path) > 0, "Servant 1 must have a path")
        self.assertTrue(len(s2.current_path) > 0, "Servant 2 must have a path")

        # Advance simulation until both servants collect resources from the stack
        for _ in range(60):
            s1.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)
            s2.update(0.1, self.bm, self.pm, self.sm, self.resources, s1, all_servants=self.serv_m.servants, furniture_manager=self.fm, villager_manager=self.vm, servant_manager=self.serv_m)
            if s1.state == "HAULING" and s2.state == "HAULING":
                break

        self.assertEqual(s1.state, "HAULING", "Servant 1 should have picked up wood and be hauling")
        self.assertEqual(s2.state, "HAULING", "Servant 2 should have picked up wood and be hauling")
        self.assertEqual(s1.carried_amount, SERVANT_CARRY_CAPACITY)
        self.assertEqual(s2.carried_amount, SERVANT_CARRY_CAPACITY)

    def test_staggered_interaction_positions_around_stockpile(self):
        """
        Verify that multiple AI targeting the same resource tile calculate
        distinct interaction positions around the perimeter of the tile.
        """
        self.sm.stacks = [ResourceStack("Wood", 100, 10, 10, owner_type="landlord")]
        tiles = {(20, 20), (21, 20), (20, 21), (21, 21)}
        site = ConstructionSite("wooden_structure", tiles, (20, 21), "bottom")
        self.bm.construction_sites.append(site)
        site.required_cost["Wood"] = 40

        s1 = self.serv_m.servants[0]
        s2 = self.serv_m.servants[1]

        s1._assign_construction_task(site, self.sm, self.resources, s1, all_servants=self.serv_m.servants)
        s2._assign_construction_task(site, self.sm, self.resources, s1, all_servants=self.serv_m.servants)

        # Interaction positions must not be identical
        self.assertIsNotNone(s1.target_storage_pos)
        self.assertIsNotNone(s2.target_storage_pos)
        self.assertNotEqual(s1.target_storage_pos, s2.target_storage_pos, "Servants must use separate interaction offsets around resource")

        dist = math.hypot(s1.target_storage_pos[0] - s2.target_storage_pos[0], s1.target_storage_pos[1] - s2.target_storage_pos[1])
        self.assertGreater(dist, 10.0, "Interaction positions should have at least 10px spacing")

    def test_resource_availability_tracking_prevents_overcollection(self):
        """
        Verify that physical stockpile tracks reserved amounts so that when a stack
        only has enough for 1 servant, the second servant does not overcollect.
        """
        # Stack only has 5 Wood (exactly 1 servant capacity)
        self.sm.stacks = [ResourceStack("Wood", 5, 8, 8, owner_type="landlord")]
        tiles = {(20, 20), (21, 20), (20, 21), (21, 21)}
        site = ConstructionSite("wooden_structure", tiles, (20, 21), "bottom")
        self.bm.construction_sites.append(site)
        site.required_cost["Wood"] = 20

        s1 = self.serv_m.servants[0]
        s2 = self.serv_m.servants[1]

        # S1 assigns first: reserves 5 Wood
        assigned_1 = s1._assign_construction_task(site, self.sm, self.resources, s1, all_servants=self.serv_m.servants)
        self.assertTrue(assigned_1)
        self.assertEqual(self.sm.stacks[0].available_amount, 0)

        # S2 attempts assignment: sees available_amount is 0 -> cannot overcollect!
        assigned_2 = s2._assign_construction_task(site, self.sm, self.resources, s1, all_servants=self.serv_m.servants)
        self.assertFalse(assigned_2, "S2 must not assign to an exhausted resource stack")

        # If S1 resets task: reservation is refunded!
        s1._reset_task()
        self.assertEqual(self.sm.stacks[0].available_amount, 5, "Refunded reservation must restore available amount")

    def test_household_servant_direct_item_grant(self):
        """
        Verify that granting items directly to a Servant or Villager via receive_granted_item
        updates inventory, preserves contents, and releases any path locks without freeze.
        """
        s = self.serv_m.servants[0]
        s.inventory["Bread"] = 2
        s.is_waiting_for_path = True
        s.wait_timer = 5.0

        # Grant 1 Hoe directly to servant
        s.receive_granted_item("Hoe", 1)

        self.assertEqual(s.inventory.get("Hoe", 0), 1)
        self.assertEqual(s.inventory.get("Bread", 0), 2, "Existing inventory must be preserved")
        self.assertFalse(s.is_waiting_for_path, "Path wait state must be released")
        self.assertEqual(s.wait_timer, 0.0)

        # Test Villager direct grant
        v = Villager("v_grant", "Jane", "Doe", "female", 28, 1, "Peasant Farmer", "fam_test", x=50, y=50)
        v.inventory["Watering_Can"] = 1
        v.is_waiting_for_path = True
        v.wait_timer = 3.0

        v.grant_item("Sickle", 1)
        self.assertEqual(v.inventory.get("Sickle", 0), 1)
        self.assertEqual(v.inventory.get("Watering_Can", 0), 1)
        self.assertFalse(v.is_waiting_for_path)

    def test_royal_grant_order_delivery_to_household_chest(self):
        """
        Verify that when a grant order is created, servant fetches item from stockpile
        and delivers it to the household chest through doors without getting stuck.
        """
        fam = self.vm.generate_random_family()
        fam.id = "fam_ward"
        self.vm.families.append(fam)

        # House at (10, 10) with door at (12, 14)
        tiles = set((x, y) for x in range(10, 15) for y in range(10, 15))
        house = Building("wooden_structure", tiles, door_pos=(12, 14), door_side="bottom")
        self.bm.buildings.append(house)

        # Family chest inside house at (10, 10)
        chest = Furniture("chest_1", "household_storage", 10, 10, permit_id="test_permit", family_id="fam_ward")
        self.fm.furnitures.append(chest)

        # Stockpile with 10 Hoes at (2, 2)
        self.sm.stacks = [ResourceStack("Hoe", 10, 2, 2, owner_type="landlord")]

        # Add grant order: Grant 2 Hoes to fam_ward
        self.serv_m.add_grant_order("fam_ward", "Hoe", 2)
        servant = self.serv_m.servants[0]
        servant.x, servant.y = (2.5 * TILE_SIZE, 3.5 * TILE_SIZE)

        delivered = False
        for step in range(250):
            servant.update(
                0.1, self.bm, self.pm, self.sm, self.resources, servant,
                all_servants=self.serv_m.servants,
                furniture_manager=self.fm,
                villager_manager=self.vm,
                servant_manager=self.serv_m
            )
            if chest.inventory.get("Hoe", 0) >= 2:
                delivered = True
                break

        self.assertTrue(delivered, "Servant must successfully deliver granted Hoes to the household chest")
        self.assertEqual(chest.inventory.get("Hoe", 0), 2)
        self.assertEqual(len(self.serv_m.grant_orders), 0, "Completed grant order must be removed")

    def test_reset_task_refunds_grant_order_in_transit(self):
        """
        Verify that if a servant task resets mid-transit, order in_transit count
        is cleanly refunded and does not cause permanent lockup.
        """
        order = {"family_id": "fam_1", "item_type": "Wood", "amount": 10, "in_transit": 0, "delivered": 0}
        self.serv_m.grant_orders.append(order)

        s = self.serv_m.servants[0]
        s.target_grant_order = order
        s.target_grant_amount = 5
        order["in_transit"] = 5

        # Reset task
        s._reset_task()

        self.assertEqual(order["in_transit"], 0, "in_transit count must be refunded on task reset")
        self.assertEqual(s.state, "IDLE")
        self.assertFalse(s.is_waiting_for_path)

    def test_high_speed_substep_throughput(self):
        """
        Verify that parallel resource collection and grant checks execute
        with high performance (>600 FPS) at 4x Very Fast speed.
        """
        tiles = {(15, 10), (16, 10), (15, 11), (16, 11)}
        site = ConstructionSite("wooden_structure", tiles, (15, 11), "bottom")
        self.bm.construction_sites.append(site)
        site.required_cost["Wood"] = 100
        self.sm.stacks = [ResourceStack("Wood", 100, 5, 5, owner_type="landlord")]

        start_time = time.perf_counter()
        frames = 120
        dt = 0.05 * 4.0 # 4x Very Fast

        for _ in range(frames):
            self.serv_m.update(dt, self.bm, self.pm, self.sm, self.resources, self.serv_m.servants[0], furniture_manager=self.fm, villager_manager=self.vm)

        elapsed = time.perf_counter() - start_time
        fps = frames / max(1e-6, elapsed)
        self.assertLess(elapsed, 0.25, f"High speed updates took {elapsed:.4f}s ({fps:.0f} FPS), must be < 0.25s")

if __name__ == "__main__":
    unittest.main()
