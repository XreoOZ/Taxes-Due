"""
Unit Tests for Agent 1 — AI Core, Needs (Toilet), Job Assignment, Task Interruption/Resumption,
and Household Death Item Recovery System.
"""

import unittest
import math
from game.config import (
    TILE_SIZE,
    AI_NEED_MAX,
    AI_CRITICAL_NEED_THRESHOLD,
    AI_NEED_TOILET_DECAY_PER_DAY,
    AI_NEED_TOILET_URGENT_THRESHOLD,
    AI_NEED_TOILET_RESTORE,
    DEDICATED_JOBS
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.world.stockpile import StockpileManager
from game.world.permits import AreaPermit, PermitManager
from game.systems.core.day_cycle import DayCycleSystem
from game.systems.work.schedule import ScheduleManager
from game.systems.core.save_system import save_to_slot, load_from_slot, get_slot_path
import os


class TestAgent1AICoreNeedsJobsAndDeathRecovery(unittest.TestCase):
    def setUp(self):
        self.vm = VillagerManager()
        self.fm = FurnitureManager()
        self.bm = BuildingManager()
        self.sm = StockpileManager()
        self.pm = PermitManager()
        self.day_cycle = DayCycleSystem()

    def test_01_job_assignment_updates_profession_and_title_immediately(self):
        """1. Assigning a job immediately changes the individual's profession and title."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 35, 2, "Father", "fam_mason")
        self.assertEqual(v.job, "Unassigned")

        v.set_job("Farmer")
        self.assertEqual(v.job, "Farmer")
        self.assertEqual(v.profession, "Farmer")
        self.assertEqual(v.title, "Farmer")

        v.set_job("Builder")
        self.assertEqual(v.job, "Builder")
        self.assertEqual(v.profession, "Builder")
        self.assertEqual(v.title, "Builder")

        v.set_job("Gravedigger")
        self.assertEqual(v.job, "Gravedigger")
        self.assertEqual(v.profession, "Gravedigger")
        self.assertEqual(v.title, "Gravedigger")

        v.set_job("Priest")
        self.assertEqual(v.job, "Priest")
        self.assertEqual(v.profession, "Priest")
        self.assertEqual(v.title, "Priest")

    def test_02_household_members_can_have_different_jobs(self):
        """2. Members of the same household can hold different dedicated professions without affecting ownership."""
        v1 = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        v2 = Villager("vil_2", "Beatrice", "Mason", "Female", 38, 2, "Mother", "fam_mason")
        v3 = Villager("vil_3", "Charles", "Mason", "Male", 19, 3, "Adult Son", "fam_mason")
        fam = Family("fam_mason", "Mason", [v1, v2, v3])

        v1.set_job("Farmer")
        v2.set_job("Builder")
        v3.set_job("Gravedigger")

        self.assertEqual(v1.job, "Farmer")
        self.assertEqual(v2.job, "Builder")
        self.assertEqual(v3.job, "Gravedigger")
        self.assertEqual(v1.family_id, "fam_mason")
        self.assertEqual(v2.family_id, "fam_mason")
        self.assertEqual(v3.family_id, "fam_mason")
        self.assertEqual(fam.member_count, 3)

    def test_03_tool_reassessment_on_job_change_deposits_irrelevant_and_fetches_required(self):
        """3. Changing jobs deposits unneeded tools to storage and fetches required tools without duplication."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        chest = Furniture("chest_1", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_mason")
        chest.inventory = {"Hammer": 1}
        self.fm.furnitures.append(chest)
        v.furniture_manager = self.fm
        v.stockpile_manager = self.sm

        # Arthur starts as Farmer holding Hoe and Sickle
        v.inventory = {"Hoe": 1, "Sickle": 1}
        v.set_job("Builder")

        # Irrelevant tools (Hoe, Sickle) deposited into chest, Hammer retrieved from chest
        self.assertNotIn("Hoe", v.inventory)
        self.assertNotIn("Sickle", v.inventory)
        self.assertEqual(v.inventory.get("Hammer"), 1)
        self.assertEqual(chest.inventory.get("Hoe"), 1)
        self.assertEqual(chest.inventory.get("Sickle"), 1)
        self.assertNotIn("Hammer", chest.inventory)

    def test_04_need_toilet_initialization_decay_and_relief(self):
        """4. Need Toilet initializes to 100, decays over time, and restores upon toilet usage."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        self.assertEqual(v.need_toilet, float(AI_NEED_MAX))
        self.assertEqual(v.toilet, float(AI_NEED_MAX))

        # Decay over 10 seconds
        dt = 10.0
        day_sec = 1200.0
        v.update(dt, self.pm, self.bm, [v], None, day_cycle=self.day_cycle)
        expected_decay = (AI_NEED_TOILET_DECAY_PER_DAY / day_sec) * dt
        self.assertAlmostEqual(v.need_toilet, AI_NEED_MAX - expected_decay, delta=0.5)

        # Build a completed toilet in the village
        toilet_b = Building("toilet", {(5, 5)})
        toilet_b.is_under_construction = False
        self.bm.buildings.append(toilet_b)

        # Trigger critical need toilet
        v.need_toilet = 15.0
        self.assertTrue(v.need_toilet <= AI_NEED_TOILET_URGENT_THRESHOLD)
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity(
            v.job, int(self.day_cycle.current_hour), "LEISURE"
        )
        v.update(
            0.1, self.pm, self.bm, [v], None,
            day_cycle=self.day_cycle, schedule_manager=schedule_manager,
        )
        self.assertEqual(v.task, "SEEKING_TOILET")

    def test_05_task_interruption_preserves_state_and_resumes_after_need(self):
        """5. Urgent need interrupts active task, captures state, and resumes upon need resolution."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        farm = AreaPermit("permit_farm", "farm", 0, 0, 10, 10)
        farm.assigned_workers = ["vil_1"]
        self.pm.permits.append(farm)
        v.assigned_permit_id = "permit_farm"

        # Arthur is currently tilling a tile
        v.task = "TILLING"
        v.current_work_tile = (2, 2)
        v.active_tool = "Hoe"
        v.tilling_timer = 1.5

        # Interrupted by urgent hunger
        v.hunger = 10.0
        v.interrupt_task("URGENT_NEED")
        v.task = "SEEKING_FOOD"
        self.assertEqual(v.task, "SEEKING_FOOD")
        self.assertIsNotNone(v.interrupted_task_state)
        self.assertEqual(v.interrupted_task_state["task"], "TILLING")
        self.assertEqual(v.interrupted_task_state["target_work_tile"], (2, 2))
        self.assertEqual(v.interrupted_task_state["active_tool"], "Hoe")
        self.assertEqual(v.interrupted_task_state["tilling_timer"], 1.5)

        # Arthur consumes food and resolves need
        v.hunger = 100.0
        v._resume_or_idle_after_need()

        # Task resumed back to TILLING with exact tile and timer intact
        self.assertEqual(v.task, "TILLING")
        self.assertEqual(v.current_work_tile, (2, 2))
        self.assertEqual(v.active_tool, "Hoe")
        self.assertEqual(v.tilling_timer, 1.5)
        self.assertIsNone(v.interrupted_task_state)

    def test_06_current_activity_state_descriptions(self):
        """6. Current activity state exposes clear human-readable strings for UI inspection."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        v.task = "SEEKING_TOILET"
        self.assertIn("Toilet", v.activity)

        v.task = "TILLING"
        self.assertEqual(v.activity, "Tilling soil at Farm")

        v.task = "WATERING"
        self.assertEqual(v.activity, "Watering crops at Farm")

        v.task = "RECOVER_DEATH_ITEMS"
        v.recovery_state = "APPROACHING_DROP"
        self.assertEqual(v.activity, "Collecting dropped items of deceased family member")

        v.recovery_state = "DEPOSITING"
        self.assertEqual(v.activity, "Depositing recovered items to chest")

        v.die(reason="Old Age", day=10)
        self.assertEqual(v.activity, "DECEASED")

    def test_07_death_drops_all_personal_inventory_separate_from_corpse(self):
        """7. When an AI dies, 100% of personal inventory drops to the ground into stockpile_manager."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason", x=160.0, y=160.0)
        fam = Family("fam_mason", "Mason", [v])
        self.vm.families = [fam]
        v.inventory = {"Copper": 10, "Hoe": 1, "Wood": 2}
        v.carrying_crop = 3
        v.active_tool = "Hoe"

        death_gx = int(160.0 // TILE_SIZE)
        death_gy = int(160.0 // TILE_SIZE)

        v.die(reason="Starvation", day=5, stockpile_manager=self.sm, family=fam)

        # Villager is DECEASED and personal inventory is emptied
        self.assertFalse(v.is_alive)
        self.assertEqual(v.task, "DECEASED")
        self.assertEqual(len(v.inventory), 0)
        self.assertIsNone(v.active_tool)
        self.assertEqual(v.carrying_crop, 0)

        # Dropped stacks exist at death location in stockpile manager owned by household
        dropped = [s for s in self.sm.stacks if s.grid_x == death_gx and s.grid_y == death_gy]
        self.assertGreater(len(dropped), 0)
        dropped_dict = {s.resource_type: s.amount for s in dropped}
        self.assertEqual(dropped_dict.get("Copper"), 10)
        self.assertEqual(dropped_dict.get("Hoe"), 1)
        self.assertEqual(dropped_dict.get("Wood"), 2)
        self.assertEqual(dropped_dict.get("Potato"), 3)

        # Family registers pending death drop
        self.assertEqual(len(fam.pending_death_recovery), 1)
        self.assertEqual(fam.pending_death_recovery[0]["deceased_id"], "vil_1")

    def test_08_household_death_item_recovery_workflow(self):
        """8. Surviving household member collects dropped items, deposits to chest, and resumes task."""
        v1 = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason", x=160.0, y=160.0)
        v2 = Villager("vil_2", "Beatrice", "Mason", "Female", 38, 2, "Mother", "fam_mason", x=100.0, y=100.0)
        fam = Family("fam_mason", "Mason", [v1, v2])
        self.vm.families = [fam]

        chest = Furniture("chest_mason", "household_storage", 2, 2, permit_id="test_permit", family_id="fam_mason")
        self.fm.furnitures.append(chest)

        # v1 dies dropping 5 Wood and 5 Copper
        v1.inventory = {"Wood": 5, "Copper": 5}
        v1.die(reason="Starvation", day=3, stockpile_manager=self.sm, family=fam)

        # v2 was previously relaxing
        v2.task = "IDLE"

        # VillagerManager dispatches recovery
        self.vm.update(0.1, self.pm, self.bm, [], None, stockpile_manager=self.sm, furniture_manager=self.fm)

        self.assertEqual(v2.task, "RECOVER_DEATH_ITEMS")
        self.assertIsNotNone(v2.recovery_target_drop)

        # Step 1: Simulate v2 arrival at death drop location
        v2.x, v2.y = 160.0, 160.0
        v2._execute_death_recovery_routine(0.1, furniture_manager=self.fm, stockpile_manager=self.sm)
        self.assertEqual(v2.recovery_state, "DEPOSITING")
        self.assertEqual(v2.inventory.get("Wood"), 5)
        self.assertEqual(v2.inventory.get("Copper"), 5)

        # Step 2: Simulate v2 arrival at household chest
        chest_pos = chest.get_world_pos(TILE_SIZE)
        v2.x, v2.y = chest_pos[0], chest_pos[1]
        v2.villager_manager = self.vm
        v2._execute_death_recovery_routine(0.1, furniture_manager=self.fm, stockpile_manager=self.sm)

        # Items deposited into chest, pending drop cleared, v2 resumes IDLE
        self.assertEqual(chest.inventory.get("Wood"), 5)
        self.assertEqual(chest.inventory.get("Copper"), 5)
        self.assertEqual(len(fam.pending_death_recovery), 0)
        self.assertEqual(v2.task, "IDLE")

    def test_09_save_load_preserves_toilet_interrupted_state_and_death_drops(self):
        """9. Save/load accurately preserves need_toilet, interrupted_task_state, and pending_death_recovery."""
        v = Villager("vil_1", "Arthur", "Mason", "Male", 40, 2, "Father", "fam_mason")
        v.need_toilet = 45.0
        v.interrupted_task_state = {"task": "TILLING", "active_tool": "Hoe"}
        v.activity_description = "Special Activity"
        fam = Family("fam_mason", "Mason", [v])
        fam.pending_death_recovery = [{"deceased_id": "vil_old", "gx": 8, "gy": 8, "claimed_by": None}]
        self.vm.families = [fam]

        from game.entities.servants import ServantManager
        from game.systems.work.schedule import ScheduleManager
        from game.data.config import DEFAULT_RESOURCES

        class MockPlayer:
            x = 0.0
            y = 0.0

        mock_player = MockPlayer()
        servants = ServantManager()
        schedules = ScheduleManager()
        test_slot = 95
        save_path = get_slot_path(test_slot)

        try:
            ok, msg = save_to_slot(test_slot, self.day_cycle, dict(DEFAULT_RESOURCES), mock_player, self.pm, self.bm, self.sm, self.fm, self.vm, servants, schedules)
            self.assertTrue(ok, f"Save error: {msg}")

            fresh_vm = VillagerManager()
            fresh_pm = PermitManager()
            fresh_servants = ServantManager()
            fresh_sched = ScheduleManager()

            load_ok, lmsg = load_from_slot(test_slot, self.day_cycle, dict(DEFAULT_RESOURCES), mock_player, fresh_pm, self.bm, self.sm, self.fm, fresh_vm, fresh_servants, fresh_sched)
            self.assertTrue(load_ok, f"Load error: {lmsg}")

            loaded_fam = fresh_vm.get_family_by_id("fam_mason")
            self.assertIsNotNone(loaded_fam)
            self.assertEqual(len(loaded_fam.pending_death_recovery), 1)
            self.assertEqual(loaded_fam.pending_death_recovery[0]["deceased_id"], "vil_old")

            loaded_v = loaded_fam.members[0]
            self.assertAlmostEqual(loaded_v.need_toilet, 45.0, delta=0.1)
            self.assertIsNotNone(loaded_v.interrupted_task_state)
            self.assertEqual(loaded_v.interrupted_task_state["task"], "TILLING")
            self.assertEqual(loaded_v.activity_description, "Special Activity")
        finally:
            if os.path.exists(save_path):
                os.remove(save_path)


if __name__ == "__main__":
    unittest.main()
