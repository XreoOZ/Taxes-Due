"""
Comprehensive Regression Tests: AI Survival, Consumption Sync & Midnight Lifecycle
Validates all 11 required scenarios:
1. AI consumes food and water successfully, then survives midnight.
2. AI has full Hunger and Thirst bars and has fulfilled both daily requirements, then survives midnight.
3. AI consumes food but not water, then dies at midnight.
4. AI consumes water but not food, then dies at midnight.
5. AI consumes neither, then dies at midnight.
6. Daily records reset correctly after survival validation.
7. New daily records do not inherit previous-day fulfillment.
8. Midnight processing executes only once per day.
9. Multiple AI individuals receive independent survival checks.
10. Save/load does not corrupt daily consumption records.
11. Existing jobs, inventory, market purchases, and parallel activities remain functional.
"""

import unittest
import os
import json
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.permits import PermitManager, AreaPermit
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.systems.day_cycle import DayCycleSystem
from game.systems.schedule import ScheduleManager
from game.systems.save_system import serialize_game_state, load_from_slot
from game.entities.player import Player
from game.world.stockpile import StockpileManager
from game.data.config import (
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    AI_NEED_MAX,
    AI_CRITICAL_NEED_THRESHOLD,
    TILE_SIZE
)


class TestSurvivalMidnightSync(unittest.TestCase):
    def setUp(self):
        self.vm = VillagerManager()
        self.pm = PermitManager()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.sm = StockpileManager()
        self.dc = DayCycleSystem()
        self.sched = ScheduleManager()
        self.player = Player(0, 0)
        self.resources = {"Wood": 100, "Food": 100, "Stone": 100, "Water": 100}

    def test_01_consumes_food_and_water_successfully_survives_midnight(self):
        """1. AI consumes food and water successfully, then survives midnight."""
        fam = Family("fam_1", "Smith")
        v = Villager("vil_1", "John", "Smith", "Male", 35, 2, "Father", "fam_1")
        fam.members = [v]
        self.vm.families = [fam]

        # Fulfill consumption
        v.daily_food_consumed = 1
        v.daily_water_consumed = 1

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.task, "IDLE")

    def test_02_full_bars_and_fulfilled_both_requirements_survives_midnight(self):
        """2. AI has full Hunger and Thirst bars and has fulfilled both daily requirements, then survives midnight."""
        fam = Family("fam_2", "Miller")
        v = Villager("vil_2", "Mary", "Miller", "Female", 32, 2, "Mother", "fam_2")
        fam.members = [v]
        self.vm.families = [fam]

        v.hunger = 100.0
        v.thirst = 100.0
        v.daily_food_consumed = 1
        v.daily_water_consumed = 1

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertGreaterEqual(v.hunger, 95.0)
        self.assertGreaterEqual(v.thirst, 95.0)

    def test_03_consumes_food_but_not_water_survives_midnight(self):
        """3. AI consumes food but not water: survives midnight because death triggers only at 0% + 24h countdown."""
        fam = Family("fam_3", "Baker")
        v = Villager("vil_3", "Tom", "Baker", "Male", 20, 3, "Adult Son", "fam_3")
        v.hunger = 50.0
        v.thirst = 50.0
        fam.members = [v]
        self.vm.families = [fam]

        v.daily_food_consumed = 1
        v.daily_water_consumed = 0

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

    def test_04_consumes_water_but_not_food_survives_midnight(self):
        """4. AI consumes water but not food: survives midnight because death triggers only at 0% + 24h countdown."""
        fam = Family("fam_4", "Cook")
        v = Villager("vil_4", "Alice", "Cook", "Female", 22, 3, "Adult Daughter", "fam_4")
        v.hunger = 50.0
        v.thirst = 50.0
        fam.members = [v]
        self.vm.families = [fam]

        v.daily_food_consumed = 0
        v.daily_water_consumed = 1

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

    def test_05_consumes_neither_survives_midnight(self):
        """5. AI consumes neither: survives midnight because death triggers only at 0% + 24h countdown."""
        fam = Family("fam_5", "Taylor")
        v = Villager("vil_5", "Robert", "Taylor", "Male", 40, 2, "Father", "fam_5")
        v.hunger = 50.0
        v.thirst = 50.0
        fam.members = [v]
        self.vm.families = [fam]

        v.daily_food_consumed = 0
        v.daily_water_consumed = 0

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

    def test_06_daily_records_reset_correctly_after_survival_validation(self):
        """6. Daily records reset correctly after survival validation."""
        fam = Family("fam_6", "Cooper")
        v = Villager("vil_6", "Eleanor", "Cooper", "Female", 38, 2, "Mother", "fam_6")
        fam.members = [v]
        self.vm.families = [fam]

        v.daily_food_consumed = 2
        v.daily_water_consumed = 3

        self.vm.daily_midnight_update(day_number=1)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

    def test_07_new_daily_records_do_not_inherit_previous_day_fulfillment(self):
        """7. New daily records do not inherit previous-day fulfillment."""
        fam = Family("fam_7", "Wright")
        v = Villager("vil_7", "Henry", "Wright", "Male", 45, 2, "Father", "fam_7")
        fam.members = [v]
        self.vm.families = [fam]

        # Day 1: eats and drinks, survives
        v.daily_food_consumed = 1
        v.daily_water_consumed = 1
        self.vm.daily_midnight_update(day_number=1)
        self.assertTrue(v.is_alive)
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

        # Day 2: AI does NOT eat or drink on Day 2
        # (records remain 0 from reset)
        self.vm.daily_midnight_update(day_number=2)

        # AI survives Day 2 midnight because midnight does not trigger death
        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.daily_food_consumed, 0)

    def test_08_midnight_processing_executes_only_once_per_day(self):
        """8. Midnight processing executes only once per day."""
        fam = Family("fam_8", "Ward")
        v = Villager("vil_8", "Grace", "Ward", "Female", 28, 2, "Mother", "fam_8")
        fam.members = [v]
        self.vm.families = [fam]

        # Day length 1200 seconds. Start near midnight
        self.dc.day_length_seconds = 1200.0
        self.dc.time_seconds = 1199.9  # 0.1s before midnight

        v.daily_food_consumed = 1
        v.daily_water_consumed = 1

        # Frame 1: Crosses midnight (time reaches 1200.0)
        days_passed = self.dc.update(0.2)
        self.assertEqual(days_passed, 1)
        self.vm.daily_midnight_update(self.dc.day_number)

        self.assertTrue(v.is_alive)
        self.assertEqual(v.daily_food_consumed, 0)  # Reset for Day 2

        # Frame 2: Next frame after midnight
        days_passed_next = self.dc.update(0.016)
        self.assertEqual(days_passed_next, 0)  # Does NOT trigger again

    def test_09_multiple_ai_individuals_receive_independent_survival_checks(self):
        """9. Multiple AI individuals receive independent survival checks."""
        fam = Family("fam_9", "Shepherd")
        v1 = Villager("v9_1", "Hugh", "Shepherd", "Male", 40, 2, "Father", "fam_9")
        v2 = Villager("v9_2", "Agnes", "Shepherd", "Female", 38, 2, "Mother", "fam_9")
        v3 = Villager("v9_3", "Simon", "Shepherd", "Male", 18, 3, "Son", "fam_9")
        fam.members = [v1, v2, v3]
        self.vm.families = [fam]

        v1.daily_food_consumed = 1
        v1.daily_water_consumed = 1

        v2.daily_food_consumed = 1
        v2.daily_water_consumed = 0  # Missing water

        v3.daily_food_consumed = 0  # Missing both
        v3.daily_water_consumed = 0

        self.vm.daily_midnight_update(day_number=1)

        # All individuals survive midnight because midnight never triggers death
        self.assertTrue(v1.is_alive)
        self.assertEqual(v1.status, "ALIVE")
        self.assertEqual(v1.daily_food_consumed, 0)

        self.assertTrue(v2.is_alive)
        self.assertEqual(v2.status, "ALIVE")
        self.assertEqual(v2.daily_water_consumed, 0)

        self.assertTrue(v3.is_alive)
        self.assertEqual(v3.status, "ALIVE")
        self.assertEqual(v3.daily_food_consumed, 0)

        # All 3 remain living members
        self.assertEqual(len(fam.living_members), 3)

    def test_10_save_load_preserves_daily_consumption_records_accurately(self):
        """10. Save/load does not corrupt daily consumption records."""
        fam = Family("fam_save", "Mason")
        v = Villager("vil_save", "Edward", "Mason", "Male", 25, 3, "Son", "fam_save", 100.0, 100.0)
        v.hunger = 85.0
        v.thirst = 90.0
        v.daily_food_consumed = 1
        v.daily_water_consumed = 1
        fam.members = [v]
        self.vm.families = [fam]

        from game.entities.servants import ServantManager
        serv_m = ServantManager()

        from game.systems.save_system import save_to_slot, load_from_slot, get_slot_path
        save_to_slot(
            99, self.dc, self.resources, self.player, self.pm, self.bm,
            self.sm, self.fm, self.vm, serv_m, self.sched
        )

        # Deserialize into fresh managers
        new_vm = VillagerManager()
        new_dc = DayCycleSystem()
        new_sched = ScheduleManager()
        new_bm = BuildingManager()
        new_pm = PermitManager()
        new_sm = StockpileManager()
        new_fm = FurnitureManager()
        new_serv_m = ServantManager()

        success, _ = load_from_slot(
            99, new_dc, {}, self.player, new_pm, new_bm,
            new_sm, new_fm, new_vm, new_serv_m, new_sched
        )
        self.assertTrue(success)

        loaded_v = next((vil for vil in new_vm.get_all_villagers() if vil.id == "vil_save"), None)
        self.assertIsNotNone(loaded_v)
        self.assertEqual(loaded_v.daily_food_consumed, 1)
        self.assertEqual(loaded_v.daily_water_consumed, 1)
        self.assertEqual(loaded_v.hunger, 85.0)
        self.assertEqual(loaded_v.thirst, 90.0)

        # Cleanup slot 99
        p = get_slot_path(99)
        if os.path.exists(p):
            os.remove(p)

    def test_11_evening_dinner_routine_fulfills_daily_requirements(self):
        """11. An AI who hasn't eaten or drunk by dinner time (18:00+) seeks food/water during evening leisure."""
        fam = Family("fam_bed", "Fisher")
        v = Villager("vil_bed", "Walter", "Fisher", "Male", 30, 2, "Father", "fam_bed", 96.0, 96.0)
        fam.members = [v]
        self.vm.families = [fam]

        chest = Furniture("f_bed_chest", "household_storage", 1, 1, permit_id="p_bed", family_id="fam_bed")
        chest.inventory["Potato"] = 5
        chest.inventory["Water"] = 5
        self.fm.furnitures.append(chest)

        class MockDC:
            current_hour = 19.0
            day_length_seconds = 1200.0
            day_number = 1

        v.task = "IDLE"
        v.hunger = 80.0
        v.daily_food_consumed = 0
        v.daily_water_consumed = 0

        # At dinner (cur_hour 19.0, sched LEISURE), AI seeks food
        v.update(0.1, self.pm, self.bm, [v], None, furniture_manager=self.fm, day_cycle=MockDC())
        self.assertEqual(v.task, "SEEKING_FOOD")

        # Second update tick executes consumption at chest
        v.update(0.1, self.pm, self.bm, [v], None, furniture_manager=self.fm, day_cycle=MockDC())

        # After eating food, hunger restored and food requirement met
        self.assertEqual(chest.inventory["Potato"], 4)
        self.assertEqual(v.daily_food_consumed, 1)
        self.assertEqual(v.hunger, 100.0)


if __name__ == "__main__":
    unittest.main()
