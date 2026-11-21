import unittest

from game.buildings.furniture import Furniture, FurnitureManager
from game.config import HOURS_PER_DAY, TILE_SIZE
from game.data.config import (
    AI_CRITICAL_NEED_THRESHOLD,
    SLEEP_ANY_WAKE_THRESHOLD,
    SLEEP_FULL_RECOVERY_INGAME_HOURS,
    SLEEP_FORCED_WAKE_THRESHOLD,
    SLEEP_MAX_VALUE,
)
from game.entities.villagers import Family, Villager, VillagerManager
from game.systems.schedule import ScheduleManager
from game.systems.scheduled_activity import ScheduledActivitySystem
from game.systems.sleep_system import SleepSystem
from game.world.permits import PermitManager


class TestSleepUrgentInterruption(unittest.TestCase):
    def test_eight_hours_of_sleep_repay_twenty_awake_hours(self):
        villager = Villager(
            "villager-sleep-rate", "Ada", "Smith", "Female", 30, 2, "Mother",
            "family-1",
        )
        day_length_seconds = 1200.0
        waking_seconds = day_length_seconds * 20.0 / HOURS_PER_DAY
        sleeping_seconds = day_length_seconds * 8.0 / HOURS_PER_DAY

        SleepSystem.advance(
            villager, waking_seconds, day_length_seconds,
            sleeping_active=False, has_bed=True, day_number=1,
        )
        self.assertEqual(villager.sleep_need, 0.0)
        self.assertTrue(villager.sleep_forced)

        SleepSystem.advance(
            villager, sleeping_seconds, day_length_seconds,
            sleeping_active=True, has_bed=True, day_number=1,
        )

        self.assertEqual(villager.sleep_need, SLEEP_MAX_VALUE)
        self.assertFalse(villager.sleep_forced)

    def test_scheduled_sleep_pauses_active_work_and_recharges(self):
        villager = Villager(
            "villager-scheduled-sleep", "Ada", "Smith", "Female", 30, 2, "Mother",
            "family-1",
        )
        villager.job = "Unassigned"
        villager.task = "ACTIVE_WORK"
        villager.sleep_need = 50.0
        family = Family("family-1", "Smith")
        family.members = [villager]
        villager_manager = VillagerManager()
        villager_manager.families = [family]

        bed = Furniture(
            "bed-scheduled-sleep", "bed", 1, 1, permit_id="home",
            family_id=family.id, assigned_villager_id=villager.id,
        )
        furniture_manager = FurnitureManager()
        furniture_manager.furnitures.append(bed)
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Unassigned", 22, "SLEEP")
        permit_manager = PermitManager()

        class DayCycle:
            current_hour = 22.0
            day_length_seconds = 1200.0
            day_number = 1

        villager._move_towards = lambda *_args, **_kwargs: True
        villager.update(
            0.1, permit_manager, None, [villager], None,
            furniture_manager=furniture_manager, day_cycle=DayCycle(),
            schedule_manager=schedule_manager, villager_manager=villager_manager,
        )

        self.assertEqual(villager.task, "SLEEPING")
        self.assertEqual(villager.pending_schedule_tasks[0]["task"], "ACTIVE_WORK")
        self.assertGreater(villager.sleep_need, 50.0)

        ScheduledActivitySystem.reconcile(villager, "WORK", permit_manager)
        self.assertEqual(villager.task, "ACTIVE_WORK")

    def test_scheduled_sleep_does_not_interrupt_for_urgent_water_need(self):
        villager = Villager(
            "villager-1", "Ada", "Smith", "Female", 30, 2, "Mother",
            "family-1", 500.0, 500.0,
        )
        villager.job = "Farmer"
        villager.task = "SLEEPING"
        villager.sleep_need = SLEEP_ANY_WAKE_THRESHOLD - 1.0
        villager.thirst = AI_CRITICAL_NEED_THRESHOLD - 1.0
        villager.inventory["Water"] = 1

        family = Family("family-1", "Smith")
        family.members = [villager]
        villager_manager = VillagerManager()
        villager_manager.families = [family]

        bed = Furniture(
            "bed-1", "bed", 1, 1, permit_id="home",
            family_id=family.id, assigned_villager_id=villager.id,
        )
        furniture_manager = FurnitureManager()
        furniture_manager.furnitures.append(bed)

        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 2, "SLEEP")
        permit_manager = PermitManager()

        class DayCycle:
            current_hour = 2.0
            day_length_seconds = 1200.0
            day_number = 1

        day_cycle = DayCycle()
        movement_targets = []

        def move_towards(self, x, y, _dt, **_kwargs):
            movement_targets.append((x, y))
            return True

        villager._move_towards = move_towards.__get__(villager, Villager)
        starting_sleep_need = villager.sleep_need
        sleep_recovery_per_second = (
            SLEEP_MAX_VALUE / SLEEP_FULL_RECOVERY_INGAME_HOURS
            * HOURS_PER_DAY / day_cycle.day_length_seconds
        )
        urgent_dt = (
            SLEEP_ANY_WAKE_THRESHOLD - villager.sleep_need + 1.0
        ) / sleep_recovery_per_second

        villager.update(
            urgent_dt, permit_manager, None, [villager], None,
            furniture_manager=furniture_manager, day_cycle=day_cycle,
            schedule_manager=schedule_manager, villager_manager=villager_manager,
        )
        self.assertEqual(villager.task, "SLEEPING")
        self.assertGreater(villager.sleep_need, starting_sleep_need)
        self.assertLess(villager.thirst, AI_CRITICAL_NEED_THRESHOLD)

        villager.update(
            0.1, permit_manager, None, [villager], None,
            furniture_manager=furniture_manager, day_cycle=day_cycle,
            schedule_manager=schedule_manager, villager_manager=villager_manager,
        )

        bed_position = bed.get_world_pos(TILE_SIZE)
        self.assertIn(bed_position, movement_targets)
        self.assertEqual((villager.x, villager.y), bed_position)
        self.assertEqual(villager.task, "SLEEPING")
        self.assertEqual(villager.inventory["Water"], 1)

    def test_forced_sleep_moves_villager_to_assigned_bed(self):
        villager = Villager(
            "villager-forced-sleep", "Ada", "Smith", "Female", 30, 2, "Mother",
            "family-1",
        )
        villager.job = "Farmer"
        villager.task = "SLEEPING"
        villager.sleep_need = 0.0
        villager.sleep_forced = True
        bed = Furniture(
            "bed-forced-sleep", "bed", 1, 1, permit_id="home",
            family_id="family-1", assigned_villager_id=villager.id,
        )
        furniture_manager = FurnitureManager()
        furniture_manager.furnitures.append(bed)
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 2, "SLEEP")
        movement_targets = []
        villager._move_towards = (
            lambda x, y, *_args, **_kwargs: movement_targets.append((x, y)) or True
        )

        class DayCycle:
            current_hour = 2.0
            day_length_seconds = 1200.0
            day_number = 1

        villager.update(
            0.1, PermitManager(), None, [villager], None,
            furniture_manager=furniture_manager, day_cycle=DayCycle(),
            schedule_manager=schedule_manager,
        )

        bed_position = bed.get_world_pos(TILE_SIZE)
        self.assertEqual(villager.task, "ZONKED_SLEEP")
        self.assertIn(bed_position, movement_targets)
        self.assertEqual((villager.x, villager.y), bed_position)

    def test_scheduled_sleep_continues_after_zonked_recovery_threshold(self):
        villager = Villager(
            "villager-scheduled-wake", "Ada", "Smith", "Female", 30, 2, "Mother",
            "family-1",
        )
        villager.job = "Farmer"
        villager.task = "ZONKED_SLEEP"
        villager.sleep_need = SLEEP_FORCED_WAKE_THRESHOLD - 1.0
        villager.sleep_forced = True
        villager.sleeping_recharge_active = True
        bed = Furniture(
            "bed-scheduled-wake", "bed", 1, 1, permit_id="home",
            family_id="family-1", assigned_villager_id=villager.id,
        )
        furniture_manager = FurnitureManager()
        furniture_manager.furnitures.append(bed)
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 2, "SLEEP")
        movement_targets = []
        villager._move_towards = (
            lambda x, y, *_args, **_kwargs: movement_targets.append((x, y)) or True
        )

        class DayCycle:
            current_hour = 2.0
            day_length_seconds = 1200.0
            day_number = 1

        recovery_per_second = (
            SLEEP_MAX_VALUE / SLEEP_FULL_RECOVERY_INGAME_HOURS
            * HOURS_PER_DAY / DayCycle.day_length_seconds
        )
        crossing_dt = 1.1 / recovery_per_second
        update_args = (
            PermitManager(), None, [villager], None,
        )
        update_kwargs = {
            "furniture_manager": furniture_manager,
            "day_cycle": DayCycle(),
            "schedule_manager": schedule_manager,
        }

        villager.update(crossing_dt, *update_args, **update_kwargs)

        self.assertFalse(villager.sleep_forced)
        self.assertEqual(villager.task, "SLEEPING")
        self.assertGreaterEqual(villager.sleep_need, SLEEP_FORCED_WAKE_THRESHOLD)
        self.assertIn(bed.get_world_pos(TILE_SIZE), movement_targets)

        recovered_sleep_need = villager.sleep_need
        villager.update(0.1, *update_args, **update_kwargs)

        self.assertEqual(villager.task, "SLEEPING")
        self.assertGreater(villager.sleep_need, recovered_sleep_need)

    def test_critical_need_cooldown_does_not_disable_sleep_recovery(self):
        villager = Villager(
            "villager-2", "Ben", "Smith", "Male", 32, 2, "Father",
            "family-2",
        )
        villager.job = "Farmer"
        villager.task = "SLEEPING"
        villager.sleep_need = SLEEP_ANY_WAKE_THRESHOLD - 10.0
        villager.sleeping_recharge_active = True
        villager.thirst = AI_CRITICAL_NEED_THRESHOLD - 1.0
        villager.need_seek_cooldown = 10.0

        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 2, "SLEEP")
        villager._move_towards = lambda *_args, **_kwargs: False

        class DayCycle:
            current_hour = 2.0
            day_length_seconds = 1200.0
            day_number = 1

        villager.update(
            0.1, PermitManager(), None, [villager], None,
            day_cycle=DayCycle(), schedule_manager=schedule_manager,
        )

        self.assertEqual(villager.task, "SLEEPING")
        self.assertTrue(villager.sleeping_recharge_active)
        self.assertGreater(villager.sleep_need, SLEEP_ANY_WAKE_THRESHOLD - 10.0)


if __name__ == "__main__":
    unittest.main()
