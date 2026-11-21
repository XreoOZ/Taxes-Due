"""
Unit Tests for Household Food/Water Data Desynchronization & Item Category Integration
Covers:
1. Single Source of Truth (Food/Water quantities derived directly from storage/item data)
2. Category-Based Food System (Zero hardcoding: Potato, Bread, Carrot, custom foods)
3. Water Collected from Well as real item resource in household storage
4. Daily Fulfillment (Fix 0/x bug: updates immediately on consumption, not mere possession)
5. Stock decrement and fulfillment increment synchronization (5 Potatoes -> 4, 3 Water -> 2)
6. Prevention of cross-household consumption
"""

import unittest
import pygame

from game.config import (
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    AI_NEED_MAX,
    AI_CRITICAL_NEED_THRESHOLD,
    TILE_SIZE,
    is_food_item,
    is_water_item,
    get_item_category,
    register_item_category
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.permits import AreaPermit, PermitManager
from game.world.stockpile import StockpileManager
from game.systems.day_cycle import DayCycleSystem
from game.world.pathfinding import GlobalPathRegistry
from game.ui.ui_raport import RaportUI


class TestFoodWaterCategorySync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        GlobalPathRegistry.get_instance().clear()
        self.day_cycle = DayCycleSystem()
        self.permit_manager = PermitManager()
        self.furniture_manager = FurnitureManager()
        self.stockpile_manager = StockpileManager()
        self.villager_manager = VillagerManager()

    def test_01_item_category_system_identifies_food_and_water(self):
        """1. Item category system identifies Potato, Food, Bread, and any registered item as FOOD."""
        self.assertTrue(is_food_item("Potato"))
        self.assertTrue(is_food_item("potato"))
        self.assertTrue(is_food_item("Food"))
        self.assertTrue(is_food_item("Bread"))
        self.assertTrue(is_food_item("Carrot"))
        self.assertFalse(is_food_item("Hoe"))
        self.assertFalse(is_food_item("Water"))
        self.assertFalse(is_food_item("Wood"))

        self.assertTrue(is_water_item("Water"))
        self.assertTrue(is_water_item("water"))
        self.assertFalse(is_water_item("Potato"))

    def test_02_dynamic_registration_supports_future_food_without_code_changes(self):
        """2. Any future item registered as FOOD is automatically recognized without modifying needs logic."""
        register_item_category("Roast_Chicken", "FOOD")
        self.assertTrue(is_food_item("Roast_Chicken"))
        self.assertEqual(get_item_category("Roast_Chicken"), "FOOD")

    def test_03_household_food_and_water_stock_derived_from_storage(self):
        """3. Household Food and Water stock derived directly from storage items (Single Source of Truth)."""
        fam = Family("fam_test_3", "Brewer")
        v1 = Villager("vil_3a", "Hugh", "Brewer", "Male", 40, 2, "Father", "fam_test_3")
        v2 = Villager("vil_3b", "Agnes", "Brewer", "Female", 38, 2, "Mother", "fam_test_3")
        v3 = Villager("vil_3c", "Alice", "Brewer", "Female", 18, 3, "Daughter", "fam_test_3")
        fam.members = [v1, v2, v3]
        self.villager_manager.families.append(fam)

        # Storage chest owns 5 Potatoes and 3 Water
        chest = Furniture("f_chest_3", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_test_3")
        chest.inventory["Potato"] = 5
        chest.inventory["Water"] = 3
        self.furniture_manager.furnitures.append(chest)

        food_stk = fam.get_food_stock(self.furniture_manager, self.stockpile_manager)
        water_stk = fam.get_water_stock(self.furniture_manager, self.stockpile_manager)
        self.assertEqual(food_stk, 5)
        self.assertEqual(water_stk, 3)

    def test_04_consumption_decrements_storage_and_increments_fulfillment(self):
        """
        4. When an individual consumes 1 Potato and 1 Water:
           Food in storage: 5 -> 4
           Water in storage: 3 -> 2
           Food fulfillment increases by 1 (0/3 -> 1/3)
           Water fulfillment increases by 1 (0/3 -> 1/3)
        """
        fam = Family("fam_test_4", "Brewer")
        v1 = Villager("vil_4a", "Hugh", "Brewer", "Male", 40, 2, "Father", "fam_test_4", 352.0, 352.0)
        v2 = Villager("vil_4b", "Agnes", "Brewer", "Female", 38, 2, "Mother", "fam_test_4", 352.0, 352.0)
        v3 = Villager("vil_4c", "Alice", "Brewer", "Female", 18, 3, "Daughter", "fam_test_4", 352.0, 352.0)
        fam.members = [v1, v2, v3]
        self.villager_manager.families.append(fam)

        chest = Furniture("f_chest_4", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_test_4")
        chest.inventory["Potato"] = 5
        chest.inventory["Water"] = 3
        self.furniture_manager.furnitures.append(chest)

        # Initial state before consumption
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (0, 0, 3))
        self.assertEqual(fam.get_food_stock(self.furniture_manager, self.stockpile_manager), 5)
        self.assertEqual(fam.get_water_stock(self.furniture_manager, self.stockpile_manager), 3)

        # Hugh Brewer consumes 1 Potato
        v1.x, v1.y = chest.get_world_pos()
        v1.hunger = 15.0
        v1.task = "SEEKING_FOOD"
        v1.update(0.1, self.permit_manager, None, [v1], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        # Food in storage decremented to 4; Food fulfillment is now 1/3
        self.assertEqual(chest.inventory["Potato"], 4)
        self.assertEqual(fam.get_food_stock(self.furniture_manager, self.stockpile_manager), 4)
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (1, 0, 3))

        # Hugh Brewer consumes 1 Water
        v1.x, v1.y = chest.get_world_pos()
        v1.thirst = 10.0
        v1.task = "SEEKING_WATER"
        v1.update(0.1, self.permit_manager, None, [v1], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        # Water in storage decremented to 2; Water fulfillment is now 1/3
        self.assertEqual(chest.inventory["Water"], 2)
        self.assertEqual(fam.get_water_stock(self.furniture_manager, self.stockpile_manager), 2)
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (1, 1, 3))

    def test_05_mere_possession_does_not_fulfill_daily_requirement(self):
        """
        5. Merely having 115 Potatoes in chest does NOT fulfill daily intake until actually consumed.
           Fulfillment must represent successful consumption.
        """
        fam = Family("fam_test_5", "Brewer")
        v1 = Villager("vil_5a", "Hugh", "Brewer", "Male", 40, 2, "Father", "fam_test_5")
        fam.members = [v1]
        self.villager_manager.families.append(fam)

        chest = Furniture("f_chest_5", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_test_5")
        chest.inventory["Potato"] = 115
        self.furniture_manager.furnitures.append(chest)

        # Possesses 115 potatoes in storage
        self.assertEqual(fam.get_food_stock(self.furniture_manager, self.stockpile_manager), 115)
        # But has not consumed food yet -> fulfillment is 0/1
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (0, 0, 1))

    def test_06_generic_food_item_consumed_correctly(self):
        """6. Any eligible FOOD category item (e.g. Bread) can be consumed to satisfy hunger and daily fulfillment."""
        fam = Family("fam_test_6", "Baker")
        v = Villager("vil_6", "John", "Baker", "Male", 30, 2, "Father", "fam_test_6", 352.0, 352.0)
        fam.members = [v]
        self.villager_manager.families.append(fam)

        # Chest only has Bread (no Potatoes at all)
        chest = Furniture("f_chest_6", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_test_6")
        chest.inventory["Bread"] = 3
        self.furniture_manager.furnitures.append(chest)

        self.assertEqual(fam.get_food_stock(self.furniture_manager, self.stockpile_manager), 3)

        v.x, v.y = chest.get_world_pos()
        v.hunger = 15.0
        v.task = "SEEKING_FOOD"
        v.update(0.1, self.permit_manager, None, [v], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        self.assertEqual(chest.inventory["Bread"], 2)
        self.assertEqual(fam.get_food_stock(self.furniture_manager, self.stockpile_manager), 2)
        self.assertEqual(v.daily_food_consumed, 1)
        self.assertEqual(v.hunger, 100.0)
        food_ok, _, _ = fam.get_primary_needs_progress()
        self.assertEqual(food_ok, 1)

    def test_07_prevent_cross_household_food_and_water_consumption(self):
        """7. Villagers cannot steal or consume food/water from another household's storage."""
        fam_a = Family("fam_A", "Alpha")
        va = Villager("va", "Adam", "Alpha", "Male", 30, 2, "Father", "fam_A", 160.0, 160.0)
        fam_a.members = [va]

        fam_b = Family("fam_B", "Beta")
        vb = Villager("vb", "Bob", "Beta", "Male", 30, 2, "Father", "fam_B", 352.0, 352.0)
        fam_b.members = [vb]

        self.villager_manager.families = [fam_a, fam_b]

        # Family B has plenty of food and water in chest; Family A has NO chest and NO food
        chest_b = Furniture("chest_b", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_B")
        chest_b.inventory["Potato"] = 20
        chest_b.inventory["Water"] = 10
        self.furniture_manager.furnitures = [chest_b]

        # Adam Alpha tries to seek food
        va.hunger = 10.0
        va.task = "SEEKING_FOOD"
        va.update(0.1, self.permit_manager, None, [va, vb], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        # Adam could NOT consume Bob's potatoes
        self.assertEqual(chest_b.inventory["Potato"], 20)
        self.assertEqual(va.daily_food_consumed, 0)
        self.assertLessEqual(va.hunger, 10.0)

    def test_08_water_collection_deposits_into_own_household_storage(self):
        """8. Water collected from well is deposited as real resource into own household chest."""
        fam = Family("fam_well", "Cooper")
        v = Villager("vil_w", "Robert", "Cooper", "Male", 40, 2, "Father", "fam_well", 352.0, 352.0)
        fam.members = [v]
        self.villager_manager.families.append(fam)

        chest = Furniture("f_chest_w", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_well")
        chest.inventory["Water"] = 0
        self.furniture_manager.furnitures.append(chest)

        # Villager is hauling 3 units of water collected from well
        v.x, v.y = chest.get_world_pos()
        v.inventory["Water"] = 3
        v.task = "HAULING_HOUSEHOLD_WATER"
        v.update(0.1, self.permit_manager, None, [v], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        # Water deposited into household chest
        self.assertEqual(chest.inventory.get("Water", 0), 3)
        self.assertNotIn("Water", v.inventory)
        self.assertEqual(fam.get_water_stock(self.furniture_manager, self.stockpile_manager), 3)


if __name__ == "__main__":
    unittest.main()
