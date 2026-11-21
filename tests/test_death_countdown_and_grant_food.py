"""
Unit & Integration Tests:
1. Hunger & Thirst Death Mechanic: 0% Threshold + 24 In-Game Hours Countdown
2. Royal Grant System: Granting FOOD Category Items (Potato, Bread, etc.) to Households
"""

import unittest
import pygame

from game.config import (
    TILE_SIZE,
    AI_DEATH_COUNTDOWN_HOURS,
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    DEFAULT_RESOURCES
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.entities.servants import Servant, ServantManager
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.permits import AreaPermit, PermitManager
from game.world.stockpile import ResourceStack, StockpileManager
from game.world.pathfinding import GlobalPathRegistry
from game.systems.day_cycle import DayCycleSystem
from game.systems.household_inventory import get_household_possessions
from game.systems.save_system import save_to_slot, load_from_slot
from game.entities.player import Player


class TestDeathCountdownAndGrantFood(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        GlobalPathRegistry.get_instance().clear()
        self.day_cycle = DayCycleSystem()
        self.permit_manager = PermitManager()
        self.building_manager = BuildingManager()
        self.furniture_manager = FurnitureManager()
        self.stockpile_manager = StockpileManager()
        self.villager_manager = VillagerManager()
        self.servant_manager = ServantManager()
        self.resources = dict(DEFAULT_RESOURCES)
        self.player = Player(100, 100)

    # =========================================================================
    # PART 1: 0% THRESHOLD & 24-IN-GAME-HOUR DEATH COUNTDOWN TESTS
    # =========================================================================

    def test_01_ai_at_50_percent_survives_midnight(self):
        """1. AI at 50% Hunger and 50% Thirst survives midnight without dying."""
        fam = Family(1, "Smith")
        v = Villager(1, "John", "Smith", "Male", 30, 2, "Father", 1, 100, 100)
        v.hunger = 50.0
        v.thirst = 50.0
        v.daily_food_consumed = 0
        v.daily_water_consumed = 0
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        # Midnight strike
        self.villager_manager.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertIsNone(v.hunger_death_timer)
        self.assertIsNone(v.thirst_death_timer)

    def test_02_ai_at_10_percent_survives_midnight(self):
        """2. AI at 10% Hunger and 50% Thirst survives midnight without dying."""
        fam = Family(2, "Baker")
        v = Villager(2, "Mary", "Baker", "Female", 28, 2, "Mother", 2, 100, 100)
        v.hunger = 10.0
        v.thirst = 50.0
        v.daily_food_consumed = 0
        v.daily_water_consumed = 0
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        self.villager_manager.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertIsNone(v.hunger_death_timer)

    def test_03_hunger_at_0_percent_starts_24h_countdown(self):
        """3. AI at 0% Hunger starts a 24-in-game-hour countdown."""
        v = Villager(3, "Bob", "Smith", "Male", 20, 3, "Son", 1, 100, 100)
        v.hunger = 0.0
        v.thirst = 80.0
        self.assertIsNone(v.hunger_death_timer)

        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)

        self.assertTrue(v.is_alive)
        self.assertIsNotNone(v.hunger_death_timer)
        self.assertAlmostEqual(v.hunger_death_timer, AI_DEATH_COUNTDOWN_HOURS, delta=0.1)
        self.assertIsNone(v.thirst_death_timer)

    def test_04_thirst_at_0_percent_starts_24h_countdown(self):
        """4. AI at 0% Thirst starts a 24-in-game-hour countdown."""
        v = Villager(4, "Alice", "Smith", "Female", 18, 3, "Daughter", 1, 100, 100)
        v.hunger = 80.0
        v.thirst = 0.0

        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)

        self.assertTrue(v.is_alive)
        self.assertIsNotNone(v.thirst_death_timer)
        self.assertAlmostEqual(v.thirst_death_timer, AI_DEATH_COUNTDOWN_HOURS, delta=0.1)
        self.assertIsNone(v.hunger_death_timer)

    def test_05_and_06_countdown_continues_across_midnight(self):
        """5 & 6. Midnight does not reset or trigger countdowns; countdown continues across midnight."""
        fam = Family(5, "Miller")
        v = Villager(5, "Thomas", "Miller", "Male", 45, 1, "Father", 5, 100, 100)
        v.hunger = 0.0
        v.thirst = 70.0
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        # 6 in-game hours elapse (day_length = 1200s, so 6h = 300s)
        day_sec = self.day_cycle.day_length_seconds
        dt_6h = (6.0 / 24.0) * day_sec
        v.update(dt_6h, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)

        self.assertAlmostEqual(v.hunger_death_timer, 18.0, delta=0.2)
        remaining_before_midnight = v.hunger_death_timer

        # Midnight strikes!
        self.villager_manager.daily_midnight_update(day_number=2)

        # Must not kill, reset or restart
        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertAlmostEqual(v.hunger_death_timer, remaining_before_midnight, delta=0.01)

        # 6 more hours pass on Day 2
        v.update(dt_6h, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertAlmostEqual(v.hunger_death_timer, 12.0, delta=0.3)
        self.assertTrue(v.is_alive)

    def test_07_recovering_hunger_cancels_countdown(self):
        """7. Recovering Hunger before countdown expires cancels the countdown."""
        fam = Family(7, "Cooper")
        v = Villager(7, "Emma", "Cooper", "Female", 22, 2, "Daughter", 7, 160, 160)
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        chest = Furniture(701, "household_storage", 5, 5, permit_id="test_permit", family_id=7)
        chest.inventory["Potato"] = 5
        self.furniture_manager.furnitures.append(chest)

        v.hunger = 0.0
        v.x, v.y = chest.get_world_pos()
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertIsNotNone(v.hunger_death_timer)

        # Consumes potato
        v.task = "SEEKING_FOOD"
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        self.assertGreater(v.hunger, 0.0)
        self.assertIsNone(v.hunger_death_timer)
        self.assertTrue(v.is_alive)

    def test_08_recovering_thirst_cancels_countdown(self):
        """8. Recovering Thirst before countdown expires cancels the countdown."""
        fam = Family(8, "Cooper")
        v = Villager(8, "Liam", "Cooper", "Male", 24, 2, "Son", 8, 160, 160)
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        chest = Furniture(801, "household_storage", 5, 5, permit_id="test_permit", family_id=8)
        chest.inventory["Water"] = 5
        self.furniture_manager.furnitures.append(chest)

        v.thirst = 0.0
        v.x, v.y = chest.get_world_pos()
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertIsNotNone(v.thirst_death_timer)

        # Consumes water
        v.task = "SEEKING_WATER"
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle)

        self.assertGreater(v.thirst, 0.0)
        self.assertIsNone(v.thirst_death_timer)
        self.assertTrue(v.is_alive)

    def test_09_hunger_and_thirst_countdowns_are_independent(self):
        """9. Hunger and Thirst countdowns operate independently."""
        v = Villager(9, "Noah", "Independent", "Male", 35, 1, "Father", 9, 100, 100)
        v.hunger = 0.0
        v.thirst = 60.0

        # Hunger at 0%: hunger timer starts
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertIsNotNone(v.hunger_death_timer)
        self.assertIsNone(v.thirst_death_timer)

        # Advance 10 in-game hours
        day_sec = self.day_cycle.day_length_seconds
        dt_10h = (10.0 / 24.0) * day_sec
        v.update(dt_10h, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertAlmostEqual(v.hunger_death_timer, 14.0, delta=0.2)
        self.assertIsNone(v.thirst_death_timer)

        # Now thirst also hits 0%
        v.thirst = 0.0
        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertIsNotNone(v.thirst_death_timer)
        self.assertAlmostEqual(v.hunger_death_timer, 14.0, delta=0.3)
        self.assertAlmostEqual(v.thirst_death_timer, 24.0, delta=0.2)

    def test_10_and_11_ai_dies_when_countdown_expires(self):
        """10 & 11. AI dies when unresolved countdown reaches 0; does not die before 24h elapse."""
        v = Villager(10, "Mortal", "Soul", "Male", 50, 1, "Elder", 10, 100, 100)
        v.hunger = 0.0
        v.thirst = 100.0

        v.update(0.1, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertTrue(v.is_alive)

        # 23.5 in-game hours pass: MUST STILL BE ALIVE
        day_sec = self.day_cycle.day_length_seconds
        dt_23_5h = (23.5 / 24.0) * day_sec
        v.thirst = 100.0
        v.update(dt_23_5h, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)
        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertAlmostEqual(v.hunger_death_timer, 0.5, delta=0.2)

        # Remaining 0.6 hours pass: countdown expires!
        dt_0_6h = (0.6 / 24.0) * day_sec
        v.thirst = 100.0
        v.update(dt_0_6h, self.permit_manager, self.building_manager, [v], self.player, day_cycle=self.day_cycle)

        self.assertFalse(v.is_alive)
        self.assertEqual(v.status, "DECEASED")
        self.assertEqual(v.death_reason, "Starvation")

    def test_12_save_load_preserves_active_countdown(self):
        """12. Save/load preserves active countdowns accurately without restarting."""
        import os
        from game.systems.schedule import ScheduleManager
        slot_id = 8
        schedule_mgr = ScheduleManager()

        fam = Family(12, "Persistent")
        v = Villager(12, "Survivor", "Persistent", "Male", 25, 2, "Son", 12, 100, 100)
        v.hunger = 0.0
        v.thirst = 80.0
        v.hunger_death_timer = 15.5
        v.thirst_death_timer = None
        fam.members.append(v)
        self.villager_manager.families.append(fam)

        save_ok, msg = save_to_slot(
            slot_id, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager, schedule_mgr
        )
        self.assertTrue(save_ok, msg)

        # Create fresh managers for loading
        loaded_vm = VillagerManager()
        loaded_fm = FurnitureManager()
        loaded_sm = StockpileManager()
        loaded_bm = BuildingManager()
        loaded_pm = PermitManager()
        loaded_servm = ServantManager()
        loaded_sched = ScheduleManager()
        loaded_res = {}
        loaded_p = Player(0, 0)
        loaded_dc = DayCycleSystem()

        load_ok, msg = load_from_slot(
            slot_id, loaded_dc, loaded_res, loaded_p,
            loaded_pm, loaded_bm, loaded_sm, loaded_fm,
            loaded_vm, loaded_servm, loaded_sched
        )
        self.assertTrue(load_ok, msg)

        loaded_v = loaded_vm.get_all_villagers()[0]
        self.assertTrue(loaded_v.is_alive)
        self.assertEqual(loaded_v.hunger, 0.0)
        self.assertIsNotNone(loaded_v.hunger_death_timer)
        self.assertAlmostEqual(loaded_v.hunger_death_timer, 15.5, places=2)
        self.assertIsNone(loaded_v.thirst_death_timer)

        # Cleanup
        save_file = f"saves/save_slot_{slot_id}.json"
        if os.path.exists(save_file):
            os.remove(save_file)

    # =========================================================================
    # PART 2: ROYAL GRANT SYSTEM — FOOD CATEGORY ITEMS DELIVERIES
    # =========================================================================

    def test_13_grant_potato_successful_servant_delivery(self):
        """13. Servant fetches Potato from landlord stockpile and delivers to household chest."""
        fam = Family(13, "Mason")
        self.villager_manager.families.append(fam)

        # House & Chest
        tiles = set((x, y) for x in range(10, 15) for y in range(10, 15))
        house = Building("wooden_structure", tiles, door_pos=(12, 14), door_side="bottom")
        self.building_manager.buildings.append(house)
        chest = Furniture(130, "household_storage", 10, 10, permit_id="test_permit", family_id=13)
        self.furniture_manager.furnitures.append(chest)

        # Landlord stockpile has 100 Potato at (2, 2)
        self.stockpile_manager.stacks = [
            ResourceStack("Potato", 100, 2, 2, owner_type="landlord")
        ]

        # Decree: Grant 10 Potato to The Mason Family
        self.servant_manager.add_grant_order(13, "Potato", 10)
        servant = self.servant_manager.servants[0]
        servant.x, servant.y = (2.5 * TILE_SIZE, 2.5 * TILE_SIZE)

        delivered = False
        for _ in range(300):
            servant.update(
                0.1, self.building_manager, self.permit_manager,
                self.stockpile_manager, self.resources, self.player,
                all_servants=self.servant_manager.servants,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
                servant_manager=self.servant_manager
            )
            if chest.inventory.get("Potato", 0) >= 10:
                delivered = True
                break

        self.assertTrue(delivered, "Servant must successfully deliver Potato to household chest")
        self.assertEqual(chest.inventory.get("Potato", 0), 10)
        self.assertEqual(len(self.servant_manager.grant_orders), 0)

        # Verify Household Possession reflects the granted potatoes
        possessions = get_household_possessions(fam, self.furniture_manager, self.stockpile_manager, self.servant_manager)
        self.assertEqual(possessions.get("Potato", 0), 10)

    def test_14_grant_potato_from_starter_food_stack(self):
        """14. Servant fulfills Potato grant order using starter generic 'Food' stockpile stack."""
        fam = Family(14, "Miller")
        self.villager_manager.families.append(fam)

        chest = Furniture(140, "household_storage", 10, 10, permit_id="test_permit", family_id=14)
        self.furniture_manager.furnitures.append(chest)

        # Starter stockpile has generic "Food"
        self.stockpile_manager.stacks = [
            ResourceStack("Food", 50, 3, 3, owner_type="landlord")
        ]

        self.servant_manager.add_grant_order(14, "Potato", 5)
        servant = self.servant_manager.servants[0]
        servant.x, servant.y = (3.5 * TILE_SIZE, 3.5 * TILE_SIZE)

        delivered = False
        for _ in range(300):
            servant.update(
                0.1, self.building_manager, self.permit_manager,
                self.stockpile_manager, self.resources, self.player,
                all_servants=self.servant_manager.servants,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
                servant_manager=self.servant_manager
            )
            if chest.inventory.get("Potato", 0) >= 5:
                delivered = True
                break

        self.assertTrue(delivered, "Servant must fulfill Potato grant using Food stockpile stack")
        self.assertEqual(chest.inventory.get("Potato", 0), 5)
        # Landlord food stack was decremented
        food_stack = self.stockpile_manager.stacks[0]
        self.assertEqual(food_stack.amount, 45)

    def test_15_grant_other_food_item_bread(self):
        """15. Grant other FOOD-category items (e.g. Bread) works through the same generic workflow."""
        fam = Family(15, "Baker")
        self.villager_manager.families.append(fam)

        chest = Furniture(150, "household_storage", 8, 8, permit_id="test_permit", family_id=15)
        self.furniture_manager.furnitures.append(chest)

        self.stockpile_manager.stacks = [
            ResourceStack("Bread", 20, 2, 2, owner_type="landlord")
        ]

        self.servant_manager.add_grant_order(15, "Bread", 4)
        servant = self.servant_manager.servants[0]
        servant.x, servant.y = (2.5 * TILE_SIZE, 2.5 * TILE_SIZE)

        delivered = False
        for _ in range(300):
            servant.update(
                0.1, self.building_manager, self.permit_manager,
                self.stockpile_manager, self.resources, self.player,
                all_servants=self.servant_manager.servants,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
                servant_manager=self.servant_manager
            )
            if chest.inventory.get("Bread", 0) >= 4:
                delivered = True
                break

        self.assertTrue(delivered, "Servant must deliver Bread to household chest")
        self.assertEqual(chest.inventory.get("Bread", 0), 4)

    def test_16_grant_non_food_item_wood_regression(self):
        """16. Non-food items (e.g. Wood, Hoe) continue working seamlessly without regression."""
        fam = Family(16, "Carpenter")
        self.villager_manager.families.append(fam)

        chest = Furniture(160, "household_storage", 6, 6, permit_id="test_permit", family_id=16)
        self.furniture_manager.furnitures.append(chest)

        self.stockpile_manager.stacks = [
            ResourceStack("Wood", 50, 2, 2, owner_type="landlord")
        ]

        self.servant_manager.add_grant_order(16, "Wood", 10)
        servant = self.servant_manager.servants[0]
        servant.x, servant.y = (2.5 * TILE_SIZE, 2.5 * TILE_SIZE)

        delivered = False
        for _ in range(300):
            servant.update(
                0.1, self.building_manager, self.permit_manager,
                self.stockpile_manager, self.resources, self.player,
                all_servants=self.servant_manager.servants,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager,
                servant_manager=self.servant_manager
            )
            if chest.inventory.get("Wood", 0) >= 10:
                delivered = True
                break

        self.assertTrue(delivered)
        self.assertEqual(chest.inventory.get("Wood", 0), 10)


if __name__ == "__main__":
    unittest.main()
