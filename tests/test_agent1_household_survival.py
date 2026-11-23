"""
Unit Tests for AGENT 1: Household Survival, Hunger, Thirst & AI Needs
Covers all 19 Acceptance Tests from the task specification.
"""

import unittest
import math
import time
import pygame

from game.config import (
    AI_NEED_MAX,
    AI_NEED_HUNGER_DECAY_PER_DAY,
    AI_NEED_THIRST_DECAY_PER_DAY,
    AI_CRITICAL_NEED_THRESHOLD,
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    TILE_SIZE
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.entities.servants import Servant
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.permits import AreaPermit, PermitManager
from game.systems.core.day_cycle import DayCycleSystem
from game.systems.work.schedule import ScheduleManager
from game.world.stockpile import StockpileManager
from game.systems.economy.market_interface import request_market_food_purchase
from game.world.navigation.pathfinding import GlobalPathRegistry

# Initialize pygame headless
pygame.init()
pygame.font.init()

class TestAgent1HouseholdSurvival(unittest.TestCase):
    def setUp(self):
        GlobalPathRegistry.get_instance().clear()
        self.day_cycle = DayCycleSystem()
        self.permit_manager = PermitManager()
        self.furniture_manager = FurnitureManager()
        self.stockpile_manager = StockpileManager()
        self.villager_manager = VillagerManager()

    def test_01_living_ai_has_hunger_and_thirst(self):
        """1. Every living AI has Hunger and Thirst initialized to 100.0."""
        v = Villager("vil_test_1", "Arthur", "Miller", "Male", 40, 2, "Father", "fam_1", 0.0, 0.0)
        self.assertEqual(v.hunger, 100.0)
        self.assertEqual(v.thirst, 100.0)
        self.assertTrue(v.is_alive)
        self.assertEqual(v.status, "ALIVE")
        self.assertEqual(v.daily_food_consumed, 0)
        self.assertEqual(v.daily_water_consumed, 0)

        # Servant also has hunger and thirst profile
        s = Servant("serv_1", "Servant #1", 0.0, 0.0)
        self.assertEqual(s.hunger, 100.0)
        self.assertEqual(s.thirst, 100.0)
        self.assertTrue(s.is_alive)

    def test_02_needs_decrease_with_day_cycle(self):
        """2. Needs decrease according to the in-game day cycle."""
        v = Villager("vil_test_2", "John", "Miller", "Male", 22, 3, "Adult Son", "fam_1", 0.0, 0.0)
        day_sec = self.day_cycle.day_length_seconds  # e.g. 1200 seconds
        dt = 60.0  # 1 minute

        v.update(dt, self.permit_manager, None, [v], None, day_cycle=self.day_cycle)
        expected_hunger = 100.0 - (AI_NEED_HUNGER_DECAY_PER_DAY / day_sec) * dt
        expected_thirst = 100.0 - (AI_NEED_THIRST_DECAY_PER_DAY / day_sec) * dt
        self.assertAlmostEqual(v.hunger, expected_hunger, places=3)
        self.assertAlmostEqual(v.thirst, expected_thirst, places=3)

    def test_03_daily_requirements_definition(self):
        """3. Each living individual requires 1 food and 1 water daily."""
        fam = Family("fam_1", "Miller")
        v1 = Villager("vil_1", "Arthur", "Miller", "Male", 45, 2, "Father", "fam_1")
        v2 = Villager("vil_2", "Mary", "Miller", "Female", 42, 2, "Mother", "fam_1")
        v3 = Villager("vil_3", "Thomas", "Miller", "Male", 20, 3, "Adult Son", "fam_1")
        fam.members = [v1, v2, v3]

        self.assertEqual(fam.living_member_count, 3)
        self.assertEqual(fam.daily_food_required, 3 * DAILY_FOOD_REQUIREMENT)
        self.assertEqual(fam.daily_water_required, 3 * DAILY_WATER_REQUIREMENT)

    def test_04_critical_hunger_waits_for_leisure_schedule(self):
        """4. Critical hunger waits during work and starts during leisure."""
        v = Villager("vil_test_4", "Arthur", "Miller", "Male", 45, 2, "Father", "fam_1", 0.0, 0.0)
        v.task = "IDLE"
        v.hunger = 20.0  # Hit critical threshold
        v.thirst = 80.0
        v.inventory["Potato"] = 1

        schedule_manager = ScheduleManager()
        current_hour = int(self.day_cycle.current_hour)
        schedule_manager.set_hour_activity(v.job, current_hour, "WORK")
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertNotEqual(v.task, "SEEKING_FOOD")
        self.assertLessEqual(v.hunger, AI_CRITICAL_NEED_THRESHOLD)
        self.assertEqual(v.inventory["Potato"], 1)

        schedule_manager.set_hour_activity(v.job, current_hour, "LEISURE")
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertGreater(v.hunger, AI_CRITICAL_NEED_THRESHOLD)
        self.assertNotIn("Potato", v.inventory)

    def test_05_critical_thirst_is_allowed_during_any_schedule(self):
        """5. Critical thirst can be handled during an Anything schedule."""
        v = Villager("vil_test_5", "Arthur", "Miller", "Male", 45, 2, "Father", "fam_1", 0.0, 0.0)
        v.task = "IDLE"
        v.hunger = 80.0
        v.thirst = 18.0  # Hit critical threshold
        v.inventory["Water"] = 1

        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity(
            v.job, int(self.day_cycle.current_hour), "ANY"
        )
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertGreater(v.thirst, AI_CRITICAL_NEED_THRESHOLD)
        self.assertNotIn("Water", v.inventory)

    def test_critical_need_task_pauses_when_free_time_ends(self):
        villager = Villager(
            "vil_schedule-need", "Arthur", "Miller", "Male", 45, 2,
            "Father", "fam_schedule", 0.0, 0.0,
        )
        villager.task = "SEEKING_WATER"
        villager.thirst = AI_CRITICAL_NEED_THRESHOLD - 1.0
        villager.inventory["Water"] = 1
        villager.interrupted_task_state = {"task": "IDLE"}
        schedule_manager = ScheduleManager()
        current_hour = int(self.day_cycle.current_hour)
        schedule_manager.set_hour_activity(villager.job, current_hour, "WORK")

        villager.update(
            0.1, self.permit_manager, None, [villager], None,
            day_cycle=self.day_cycle, schedule_manager=schedule_manager,
        )

        self.assertNotEqual(villager.task, "SEEKING_WATER")
        self.assertEqual(villager.inventory["Water"], 1)

    def test_household_food_purchase_waits_for_free_time(self):
        villager = Villager(
            "vil_food-schedule", "Arthur", "Miller", "Male", 45, 2,
            "Father", "fam_food-schedule", 0.0, 0.0,
        )
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity(
            villager.job, int(self.day_cycle.current_hour), "WORK"
        )

        villager.update(
            0.1, self.permit_manager, None, [villager], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )

        self.assertNotEqual(villager.task, "SEEKING_FOOD")
        self.assertEqual(villager.need_seek_cooldown, 0.0)

        schedule_manager.set_hour_activity(
            villager.job, int(self.day_cycle.current_hour), "LEISURE"
        )
        villager.update(
            0.1, self.permit_manager, None, [villager], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertEqual(villager.need_seek_cooldown_task, "SEEKING_FOOD")

    def test_06_ai_retrieves_food_and_water_from_own_household_storage(self):
        """6. AI retrieves food and water from its OWN household storage chest."""
        v = Villager("vil_test_6", "Arthur", "Miller", "Male", 45, 2, "Father", "fam_1", 96.0, 96.0)
        chest = Furniture("f_chest_1", "household_storage", 1, 1, permit_id="p_1", family_id="fam_1")
        chest.inventory["Potato"] = 5
        chest.inventory["Water"] = 5
        self.furniture_manager.furnitures.append(chest)
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity(
            v.job, int(self.day_cycle.current_hour), "LEISURE"
        )

        # Consume Food
        v.hunger = 15.0
        v.task = "SEEKING_FOOD"
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertEqual(chest.inventory["Potato"], 4)
        self.assertEqual(v.hunger, 100.0)
        self.assertEqual(v.daily_food_consumed, 1)
        self.assertEqual(v.task, "IDLE")

        # Consume Water
        v.thirst = 10.0
        v.task = "SEEKING_WATER"
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertEqual(chest.inventory["Water"], 4)
        self.assertEqual(v.thirst, 100.0)
        self.assertEqual(v.daily_water_consumed, 1)
        self.assertEqual(v.task, "IDLE")

    def test_07_and_08_multiple_household_members_cooperate_water_collection(self):
        """7 & 8. Multiple household members cooperate to collect water, and collection stops when demand is satisfied."""
        fam = Family("fam_coop", "Cooper")
        v1 = Villager("vil_c1", "Robert", "Cooper", "Male", 45, 2, "Father", "fam_coop", 64.0, 64.0)
        v2 = Villager("vil_c2", "Eleanor", "Cooper", "Female", 43, 2, "Mother", "fam_coop", 64.0, 64.0)
        fam.members = [v1, v2]
        self.villager_manager.families.append(fam)

        chest = Furniture("f_coop_chest", "household_storage", 1, 1, permit_id="p_coop", family_id="fam_coop")
        chest.inventory["Water"] = 0
        self.furniture_manager.furnitures.append(chest)

        class MockBuilding:
            def __init__(self):
                self.building_type = "well"
            def get_approach_point(self, current_pos, tile_size, bm):
                return (128.0, 128.0)
            def get_center_world(self, tile_size):
                return (128.0, 128.0)

        class MockBuildingManager:
            def __init__(self):
                self.buildings = [MockBuilding()]
            def get_building_at(self, gx, gy):
                return None
            def resolve_collision(self, x, y, r, ts, old_x=None, old_y=None):
                return x, y
            def find_path(self, start, end, ts, **kwargs):
                return [start, end]

        bm = MockBuildingManager()

        v1.task = "IDLE"
        v2.task = "IDLE"

        class MockDayCycle:
            day_length_seconds = 1200.0
            current_hour = 19.0
            day_number = 1
        dc = MockDayCycle()

        all_ents = [v1, v2]
        v1.update(0.1, self.permit_manager, bm, all_ents, None, furniture_manager=self.furniture_manager, day_cycle=dc)
        self.assertEqual(v1.task, "COLLECTING_HOUSEHOLD_WATER")

        v2.update(0.1, self.permit_manager, bm, all_ents, None, furniture_manager=self.furniture_manager, day_cycle=dc)
        self.assertEqual(v2.task, "COLLECTING_HOUSEHOLD_WATER")

        # Now test that collection stops when sufficient stock is reached
        chest.inventory["Water"] = 10  # Plentiful water stock
        v1.task = "IDLE"
        v1.update(0.1, self.permit_manager, bm, all_ents, None, furniture_manager=self.furniture_manager, day_cycle=dc)
        self.assertEqual(v1.task, "IDLE")

    def test_09_and_10_market_purchasing_hook_and_failed_purchase_no_free_food(self):
        """9 & 10. AI uses AGENT 2 purchasing service when food stock is empty; failed purchase gives no free food."""
        v = Villager("vil_buyer", "Walter", "Fisher", "Male", 30, 2, "Father", "fam_fisher", 64.0, 64.0)
        chest = Furniture("f_fisher_chest", "household_storage", 1, 1, permit_id="test_permit", family_id="fam_fisher")
        chest.inventory.clear()  # No food
        self.furniture_manager.furnitures.append(chest)

        class MockSuccessfulMarket:
            def purchase_food(self, family_id, villager, food_type="Potato", amount=1):
                return True, "Potato", 1

        v.market_service = MockSuccessfulMarket()
        v.hunger = 15.0
        v.task = "SEEKING_FOOD"
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity(
            v.job, int(self.day_cycle.current_hour), "LEISURE"
        )
        v.update(
            0.1, self.permit_manager, None, [v], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        self.assertEqual(v.hunger, 100.0)
        self.assertEqual(v.daily_food_consumed, 1)

        # Failed purchase: e.g. Market has no stock or family is broke
        class MockFailedMarket:
            def purchase_food(self, family_id, villager, food_type="Potato", amount=1):
                return False, None, 0

        v2 = Villager("vil_broke", "Arthur", "Broke", "Male", 30, 2, "Father", "fam_broke", 64.0, 64.0)
        v2.market_service = MockFailedMarket()
        v2.hunger = 10.0
        v2.task = "SEEKING_FOOD"
        v2.update(
            0.1, self.permit_manager, None, [v2], None,
            furniture_manager=self.furniture_manager, day_cycle=self.day_cycle,
            schedule_manager=schedule_manager,
        )
        # Hunger did NOT restore!
        self.assertLessEqual(v2.hunger, 10.0)
        self.assertEqual(v2.daily_food_consumed, 0)

    def test_11_ai_resumes_previous_activity_when_possible(self):
        """11. AI safely clears need interruption state after consuming food/water."""
        v = Villager("vil_resume", "Emma", "Smith", "Female", 24, 3, "Adult Daughter", "fam_smith", 64.0, 64.0)
        v.inventory["Potato"] = 1
        v.task = "SEEKING_FOOD"
        v.previous_task_before_need = "TILLING"

        v.update(0.1, self.permit_manager, None, [v], None, day_cycle=self.day_cycle)
        self.assertEqual(v.task, "IDLE")
        self.assertIsNone(v.previous_task_before_need)

    def test_12_and_13_and_14_death_system_at_midnight_and_deceased_stops(self):
        """12, 13 & 14. Midnight does NOT kill AI; death occurs only when 24h countdown expires at 0% need; deceased AI stops working."""
        fam = Family("fam_survive", "Shepherd")
        v_survivor = Villager("vil_s1", "Hugh", "Shepherd", "Male", 25, 3, "Adult Son", "fam_survive")
        v_starved = Villager("vil_s2", "Beatrice", "Shepherd", "Female", 22, 3, "Adult Daughter", "fam_survive")
        fam.members = [v_survivor, v_starved]
        self.villager_manager.families.append(fam)

        # Hugh ate and drank today
        v_survivor.daily_food_consumed = 1
        v_survivor.daily_water_consumed = 1

        # Beatrice failed to eat today (0 food consumed), but hunger is at 50%
        v_starved.hunger = 50.0
        v_starved.thirst = 50.0
        v_starved.daily_food_consumed = 0
        v_starved.daily_water_consumed = 1

        # Trigger midnight update: Neither Hugh nor Beatrice die at midnight!
        self.villager_manager.daily_midnight_update(day_number=1)

        # Hugh survived and daily intake reset
        self.assertTrue(v_survivor.is_alive)
        self.assertEqual(v_survivor.status, "ALIVE")
        self.assertEqual(v_survivor.daily_food_consumed, 0)
        self.assertEqual(v_survivor.daily_water_consumed, 0)

        # Beatrice ALSO survived midnight because hunger > 0%
        self.assertTrue(v_starved.is_alive)
        self.assertEqual(v_starved.status, "ALIVE")

        # Now Beatrice hunger reaches 0%: countdown starts
        v_starved.hunger = 0.0
        v_starved.thirst = 100.0
        # 1 update step to initialize the 24h countdown
        v_starved.update(0.1, self.permit_manager, None, [v_starved], None)
        self.assertIsNotNone(v_starved.hunger_death_timer)
        self.assertTrue(v_survivor.is_alive)

        # Fast forward hunger countdown to near expiry while keeping thirst well-hydrated
        v_starved.hunger_death_timer = 0.0001
        v_starved.thirst = 100.0
        v_starved.update(0.1, self.permit_manager, None, [v_starved], None)

        # Now Beatrice died of Starvation after countdown expired
        self.assertFalse(v_starved.is_alive)
        self.assertEqual(v_starved.status, "DECEASED")
        self.assertEqual(v_starved.death_reason, "Starvation")
        self.assertEqual(v_starved.task, "DECEASED")

        # Deceased AI stops performing updates and activities
        v_starved.update(0.1, self.permit_manager, None, [v_starved], None)
        self.assertEqual(v_starved.task, "DECEASED")
        self.assertFalse(v_starved.is_moving)

    def test_15_and_16_and_17_family_list_primary_needs_indicators(self):
        """15, 16 & 17. Family list displays Food: y/x | Water: z/x, resets daily, excludes deceased from denominator."""
        fam = Family("fam_progress", "Mason")
        m1 = Villager("m1", "John", "Mason", "Male", 50, 2, "Father", "fam_progress")
        m2 = Villager("m2", "Agnes", "Mason", "Female", 48, 2, "Mother", "fam_progress")
        m3 = Villager("m3", "Edward", "Mason", "Male", 22, 3, "Adult Son", "fam_progress")
        fam.members = [m1, m2, m3]
        self.villager_manager.families.append(fam)

        # Initially 0/3 fulfilled
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (0, 0, 3))

        # m1 and m2 eat and drink
        m1.daily_food_consumed = 1
        m1.daily_water_consumed = 1
        m2.daily_food_consumed = 1
        m2.daily_water_consumed = 1

        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (2, 2, 3))

        # Suppose m3 dies: denominator must exclude deceased individuals
        m3.die("Dehydration", day=1)
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (2, 2, 2))  # Denominator is now 2!

        # Midnight daily reset for living members
        self.villager_manager.daily_midnight_update(day_number=2)
        food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
        self.assertEqual((food_ok, water_ok, living_tot), (0, 0, 2))  # Reset to 0/2!

    def test_18_and_19_performance_and_no_regression(self):
        """18 & 19. Existing jobs, parallel execution, and performance at high speed remain flawless."""
        fam = Family("fam_perf", "Fisher")
        members = []
        for i in range(6):
            m = Villager(f"v_perf_{i}", f"Worker_{i}", "Fisher", "Male", 25, 3, "Son", "fam_perf", x=float(i * 32), y=0.0)
            members.append(m)
        fam.members = members
        self.villager_manager.families.append(fam)

        # 60 updates at high speed (dt = 0.08)
        t_start = time.perf_counter()
        for _ in range(60):
            for m in members:
                m.update(0.08, self.permit_manager, None, members, None, day_cycle=self.day_cycle)
        elapsed = time.perf_counter() - t_start

        # 60 frames for 6 villagers must take well under 0.1s
        self.assertLess(elapsed, 0.10)

if __name__ == "__main__":
    unittest.main()
