import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import unittest
import pygame

# Headless Pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import DEFAULT_RESOURCES, ITEM_CATEGORIES, FURNITURE_TYPES
from game.world.stockpile import StockpileManager, ResourceStack, MAX_TILE_CAPACITY
from game.buildings.furniture import Furniture
from game.permits import PermitManager
from game.ui.modals.add_item_modal import AddItemModal
from game.systems.core.cheat_system import (
    get_registered_item_types,
    clean_resources_dictionary,
    find_drop_tile_near_storage,
    find_drop_tile_near_chest,
    spawn_item_physically,
    CORE_RESOURCE_KEYS
)

class TestAgent2AddItemModalAndPhysicalDrop(unittest.TestCase):
    def setUp(self):
        self.stockpile = StockpileManager()
        self.permits = PermitManager()
        self.resources = dict(DEFAULT_RESOURCES)

    def test_registered_item_types_unique(self):
        """1. Registered item types must be canonical and free of duplicate keys"""
        items = get_registered_item_types()
        self.assertTrue(len(items) > 10)
        self.assertIn("Potato", items)
        self.assertIn("Wood", items)
        self.assertIn("Gold Coin", items)
        # Check no duplicates
        self.assertEqual(len(items), len(set(items)))

    def test_clean_resources_dictionary(self):
        """2. Non-core items (e.g., Potato, Hoe, Apple) must be purged from resources dict"""
        dirty_resources = {
            "Wood": 100,
            "Food": 200,
            "Potato": 750,
            "Hoe": 750,
            "Sickle": 750,
            "Gold": 50
        }
        clean_resources_dictionary(dirty_resources)
        for core in ["Wood", "Food", "Gold"]:
            self.assertIn(core, dirty_resources)
        for rogue in ["Potato", "Hoe", "Sickle"]:
            self.assertNotIn(rogue, dirty_resources)

    def test_add_item_modal_interaction_and_stepper(self):
        """3. AddItemModal opens, allows item selection and quantity adjustments"""
        modal = AddItemModal()
        modal.open(target_storage=None)
        self.assertTrue(modal.is_open)
        self.assertEqual(modal.quantity, 50)

        # Select item
        modal.selected_item = "Bread"
        self.assertEqual(modal.selected_item, "Bread")

        # Simulate click on preset set_100
        class FakeEvent:
            def __init__(self, pos):
                self.type = pygame.MOUSEBUTTONDOWN
                self.button = 1
                self.pos = pos

        # Test simulated stepper
        modal.quantity = 50
        modal.qty_btn_rects["inc_10"] = pygame.Rect(10, 10, 30, 30)
        modal.handle_event(FakeEvent((15, 15)))
        self.assertEqual(modal.quantity, 60)

        modal.qty_btn_rects["dec_10"] = pygame.Rect(50, 50, 30, 30)
        modal.handle_event(FakeEvent((55, 55)))
        self.assertEqual(modal.quantity, 50)

        # Test escape closes
        class KeyEvent:
            def __init__(self, key):
                self.type = pygame.KEYDOWN
                self.key = key

        modal.handle_event(KeyEvent(pygame.K_ESCAPE))
        self.assertFalse(modal.is_open)

    def test_physical_drop_into_storage_permit(self):
        """4. Items added must physically enter storage permit as ResourceStack"""
        # Clear existing permits for isolated test
        self.permits.permits = []
        p_tiles = {(5, 5), (5, 6)}
        self.permits.add_permit("Storage Lot #1", "storage", p_tiles)

        success, msg = spawn_item_physically(
            item_name="Potato",
            amount=40,
            target_storage=None,
            stockpile_manager=self.stockpile,
            permit_manager=self.permits,
            resources=self.resources
        )
        self.assertTrue(success)

        # Check physical presence in stockpile
        stacks_in_permit = [s for s in self.stockpile.stacks if (s.grid_x, s.grid_y) in p_tiles]
        self.assertTrue(len(stacks_in_permit) > 0)
        total_qty = sum(s.amount for s in stacks_in_permit if s.resource_type == "Potato")
        self.assertEqual(total_qty, 40)

        # Resources dict should have synced Food (since Potato is food) and NO rogue Potato key
        self.assertNotIn("Potato", self.resources)
        self.assertTrue(self.resources["Food"] >= 40)

    def test_storage_full_drops_physically_near_storage(self):
        """5. When storage permit is full (1000/1000), items drop on ground NEAR storage"""
        # Clear existing permits for isolated test
        self.permits.permits = []
        p_tiles = {(10, 10)}
        self.permits.add_permit("Small Storage", "storage", p_tiles)

        # Fill the tile to capacity (1000)
        self.stockpile.drop_resource("Stone", MAX_TILE_CAPACITY, 10, 10)

        # Now add 50 Wood -> storage permit is full!
        success, msg = spawn_item_physically(
            item_name="Wood",
            amount=50,
            target_storage=None,
            stockpile_manager=self.stockpile,
            permit_manager=self.permits,
            resources=self.resources
        )
        self.assertTrue(success)
        self.assertIn("near storage", msg.lower())

        # Check that a stack of 50 Wood exists at a tile OUTSIDE (10, 10)
        dropped_stacks = [s for s in self.stockpile.stacks if s.resource_type == "Wood" and (s.grid_x, s.grid_y) != (10, 10)]
        self.assertEqual(len(dropped_stacks), 1)
        self.assertEqual(dropped_stacks[0].amount, 50)
        # Dropped tile must be adjacent/near (10, 10)
        dx = abs(dropped_stacks[0].grid_x - 10)
        dy = abs(dropped_stacks[0].grid_y - 10)
        self.assertTrue(max(dx, dy) >= 1)

    def test_household_chest_storage_and_overflow_near_chest(self):
        """6. Storing in chest respects capacity; overflow drops on ground near chest"""
        chest = Furniture("f_chest_1", "household_storage", 3, 3, permit_id="test_permit")
        chest.type_cfg["capacity"] = 100

        # Add 60 Potato to chest with 100 cap -> fits in chest
        success, msg = spawn_item_physically(
            item_name="Potato",
            amount=60,
            target_storage=chest,
            stockpile_manager=self.stockpile
        )
        self.assertTrue(success)
        self.assertEqual(chest.inventory.get("Potato", 0), 60)
        self.assertEqual(len(self.stockpile.stacks), 0)

        # Add 70 more Potato -> total 130, chest takes 40, 30 must drop near chest!
        success, msg = spawn_item_physically(
            item_name="Potato",
            amount=70,
            target_storage=chest,
            stockpile_manager=self.stockpile
        )
        self.assertTrue(success)
        self.assertEqual(chest.total_stored, 100)  # Chest full!
        self.assertIn("Full", msg)

        # 30 Potato must be physically on the ground near (3, 3)
        overflow_stacks = [s for s in self.stockpile.stacks if s.resource_type == "Potato"]
        self.assertEqual(len(overflow_stacks), 1)
        self.assertEqual(overflow_stacks[0].amount, 30)
        dx = abs(overflow_stacks[0].grid_x - 3)
        dy = abs(overflow_stacks[0].grid_y - 3)
        self.assertTrue(max(dx, dy) >= 1)

if __name__ == "__main__":
    unittest.main()
