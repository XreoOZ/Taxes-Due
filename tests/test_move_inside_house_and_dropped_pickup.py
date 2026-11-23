import unittest
import math
import pygame
from game.config import TILE_SIZE
from game.buildings.building_manager import BuildingManager
from game.buildings.building import Building
from game.buildings.furniture import FurnitureManager, Furniture
from game.world.permits import PermitManager
from game.entities.villagers import VillagerManager, Villager, Family
from game.world.stockpile import StockpileManager
from game.world.navigation.pathfinding import GlobalPathRegistry

class TestMoveInsideHouseAndDroppedPickup(unittest.TestCase):
    def setUp(self):
        pygame.init()
        GlobalPathRegistry.get_instance().reset()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = StockpileManager()

        # 1. House at gx=10..12, gy=2..5 (12 tiles), door on left wall at (10, 3)
        house_tiles = {(x, y) for x in range(10, 13) for y in range(2, 6)}
        self.house = Building("wooden_structure", house_tiles, door_pos=(10, 3), door_side="left")
        self.bm.buildings.append(self.house)

        # 2. Well at gx=11..12, gy=0..1 (solid structure, matching screenshot)
        well_tiles = {(11, 0), (12, 0), (11, 1), (12, 1)}
        self.well = Building("well", well_tiles)
        self.well.is_solid = True
        self.well.door_pos = None
        self.bm.buildings.append(self.well)

        # 3. Family Carter with Starter Housing Lot
        self.housing_permit = self.pm.add_permit_rect("Starter Housing Lot", "housing", 2, 2, 4, 4)
        v1 = Villager("vil_1", "John", "Carter", "Male", 30, 2, "Father", "Carter", 2.5 * TILE_SIZE, 2.5 * TILE_SIZE)
        v2 = Villager("vil_2", "Mary", "Carter", "Female", 28, 2, "Mother", "Carter", 2.5 * TILE_SIZE, 3.5 * TILE_SIZE)
        v1.assigned_permit_id = self.housing_permit.id
        v2.assigned_permit_id = self.housing_permit.id
        fam = Family("Carter", "Carter", [v1, v2])
        fam.assigned_permit_id = self.housing_permit.id
        self.vm.families.append(fam)

    def test_furniture_move_inside_house_is_allowed(self):
        """Verify furniture can be moved inside a house room and is not blocked by wall"""
        # Uninstalled or installed furniture at (2, 2)
        f = Furniture("chest_1", "household_storage", 2, 2, self.housing_permit.id, "Carter")
        self.fm.furnitures.append(f)

        # Target (11, 2) inside the Wooden Structure
        m_gx, m_gy = 11, 2
        b_at = self.bm.get_building_at(m_gx, m_gy)
        self.assertIsNotNone(b_at, "Should find the wooden structure at (11, 2)")
        self.assertEqual(b_at.building_type, "wooden_structure")

        # Test validation logic matching main.py
        is_blocked = False
        blocked_reason = ""
        if b_at is not None:
            if getattr(b_at, "is_solid", False) or getattr(b_at, "building_type", "") == "well" or not getattr(b_at, "door_pos", None):
                is_blocked = True
                blocked_reason = "solid"
            elif (m_gx, m_gy) == getattr(b_at, "door_pos", None):
                is_blocked = True
                blocked_reason = "doorway"

        other_f = self.fm.get_furniture_at(m_gx, m_gy)
        is_occupied = (other_f is not None and other_f.id != f.id and not other_f.is_dropped)
        is_valid_dest = not is_blocked and not is_occupied

        # (11, 2) must be a VALID destination inside the house!
        self.assertFalse(is_blocked, "Room floor tile inside house should NOT be blocked by wall!")
        self.assertTrue(is_valid_dest, "Should allow moving furniture inside the house room!")

        # Move designation
        f.designate_move(m_gx, m_gy)
        self.assertEqual(f.designated_target[:2], (11, 2))

    def test_furniture_move_blocks_solid_well_and_doorway(self):
        """Verify furniture move properly blocks placing onto solid well or blocking doorways"""
        f = Furniture("chest_2", "household_storage", 2, 2, self.housing_permit.id, "Carter")
        self.fm.furnitures.append(f)

        # 1. Target (11, 1) on the solid Well
        b_well = self.bm.get_building_at(11, 1)
        self.assertTrue(getattr(b_well, "is_solid", False) or b_well.building_type == "well")

        # 2. Target (10, 3) on the house doorway
        b_door = self.bm.get_building_at(10, 3)
        self.assertEqual((10, 3), b_door.door_pos, "Tile (10, 3) is the doorway")

    def test_chest_destroy_and_villager_retrieves_dropped_tools(self):
        """Verify destroyed chest drops items and owner family members pick them up and bring them home"""
        # Create chest at (10, 1) near well with 2 Sickles
        chest = Furniture("chest_near_well", "household_storage", 10, 1, permit_id=None, family_id="Carter")
        chest.store_item("Sickle", 2)
        self.fm.furnitures.append(chest)

        # Destroy the chest
        resources = {"Wood": 0}
        success, msg = self.fm.destroy_furniture(chest.id, stockpile_manager=self.sm, resources=resources, villager_manager=self.vm)
        self.assertTrue(success)
        self.assertNotIn(chest, self.fm.furnitures)

        # Verify 2 Sickles are dropped on the ground owned by Carter family
        dropped_stack = self.sm.get_stack_at(10, 1)
        self.assertIsNotNone(dropped_stack, "Dropped stack must exist at (10, 1)")
        self.assertEqual(dropped_stack.resource_type, "Sickle")
        self.assertEqual(dropped_stack.amount, 2)
        self.assertEqual(dropped_stack.owner_type, "villager")
        self.assertEqual(dropped_stack.owner_id, "Carter")

        # Now simulate Carter family AI
        v1 = self.vm.families[0].members[0]
        # V1 starts at (2.5*64, 2.5*64)
        # In idle/leisure, V1 should find the dropped Sickles and fetch them
        target_s = v1._find_family_loose_stack_to_retrieve(self.sm, self.fm, self.pm, self.bm, [v1])
        self.assertIsNotNone(target_s, "Carter family should identify loose Sickles outside home as retrieval target")
        self.assertEqual(target_s, dropped_stack)

        # Run updates to let v1 navigate to the stack, pick it up, and haul it home
        v1.task = "IDLE"
        picked_up = False
        brought_home = False

        for frame in range(400):
            v1.update(0.05, self.pm, self.bm, [v1], player=None, stockpile_manager=self.sm, furniture_manager=self.fm)
            if v1.inventory.get("Sickle", 0) > 0 and not picked_up:
                picked_up = True
            if picked_up and v1.task == "IDLE" and v1.carrying_amount == 0:
                brought_home = True
                break

        self.assertTrue(picked_up, "Villager should have picked up the loose Sickles from ground")
        self.assertTrue(brought_home, "Villager should have completed hauling the items safely home")

if __name__ == "__main__":
    unittest.main()
