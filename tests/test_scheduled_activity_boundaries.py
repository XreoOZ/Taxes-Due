import json
import unittest

from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager
from game.data.config import SLEEP_ANY_REST_THRESHOLD
from game.entities.player import Player
from game.entities.servants import ServantManager
from game.entities.villagers import Family, Villager, VillagerManager
from game.systems.core.day_cycle import DayCycleSystem
from game.systems.core.save_system import deserialize_game_state, serialize_game_state
from game.systems.work.schedule import ScheduleManager
from game.systems.work.scheduled_activity import ScheduledActivitySystem
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager


class TestScheduledActivityBoundaries(unittest.TestCase):
    def setUp(self):
        self.villager = Villager(
            "schedule-villager", "Ada", "Smith", "Female", 30, 2, "Mother",
            "schedule-family",
        )

    def test_work_task_pauses_and_resumes_with_its_progress_state(self):
        self.villager.task = "CARPENTER_CONSTRUCTING"
        self.villager.tilling_timer = 1.5
        self.villager.current_work_tile = (4, 7)

        ScheduledActivitySystem.reconcile(self.villager, "LEISURE")

        self.assertEqual(self.villager.task, "IDLE")
        self.assertEqual(self.villager.pending_schedule_tasks[0]["task"], "CARPENTER_CONSTRUCTING")

        self.villager.task = "LEISURE"
        ScheduledActivitySystem.reconcile(self.villager, "WORK")

        self.assertEqual(self.villager.task, "CARPENTER_CONSTRUCTING")
        self.assertEqual(self.villager.tilling_timer, 1.5)
        self.assertEqual(self.villager.current_work_tile, (4, 7))
        self.assertEqual(self.villager.pending_schedule_tasks, [])

    def test_any_schedule_keeps_active_tasks_eligible(self):
        self.villager.task = "BUYING_FOOD_TRAVEL_TO_MARKET"

        ScheduledActivitySystem.reconcile(self.villager, "ANY")

        self.assertEqual(self.villager.task, "BUYING_FOOD_TRAVEL_TO_MARKET")
        self.assertEqual(self.villager.pending_schedule_tasks, [])

    def test_missing_schedule_context_does_not_impose_a_work_slot(self):
        self.villager.hunger = 10.0
        self.villager.sleep_need = SLEEP_ANY_REST_THRESHOLD
        self.villager.inventory["Potato"] = 1

        self.villager.update(0.1, None, None, [self.villager], None)

        self.assertGreater(self.villager.hunger, 10.0)
        self.assertNotIn("Potato", self.villager.inventory)

    def test_household_and_farmer_hauling_use_distinct_schedule_slots(self):
        self.assertEqual(
            ScheduledActivitySystem.task_schedule("HAULING_POSSESSION_HOME"),
            "LEISURE",
        )
        self.assertEqual(
            ScheduledActivitySystem.task_schedule("HAULING_HOME"),
            "WORK",
        )

    def test_toilet_reservation_is_released_when_its_schedule_ends(self):
        toilet = type("Toilet", (), {
            "toilet_queue": ["schedule-villager"],
            "toilet_active_user": "schedule-villager",
            "occupied_by": "schedule-villager",
        })()
        self.villager.task = "SEEKING_TOILET"
        self.villager.target_toilet = toilet
        self.villager.toilet_target_building = toilet

        ScheduledActivitySystem.reconcile(self.villager, "WORK")

        self.assertIsNone(toilet.toilet_active_user)
        self.assertIsNone(toilet.occupied_by)
        self.assertEqual(toilet.toilet_queue, [])
        self.assertIsNone(self.villager.target_toilet)
        self.assertEqual(self.villager.pending_schedule_tasks[0]["task"], "SEEKING_TOILET")

    def test_tax_collector_tasks_remain_work_only_even_in_any(self):
        self.assertTrue(
            ScheduledActivitySystem.task_is_allowed("VISITING_HOUSEHOLD_FOR_TAX", "WORK")
        )
        self.assertFalse(
            ScheduledActivitySystem.task_is_allowed("VISITING_HOUSEHOLD_FOR_TAX", "ANY")
        )

    def test_pending_task_state_is_json_serializable(self):
        self.villager.task = "TILLING"
        self.villager.current_work_tile = (4, 7)

        ScheduledActivitySystem.reconcile(self.villager, "LEISURE")

        json.dumps(self.villager.pending_schedule_tasks)

    def test_pending_task_survives_save_and_load(self):
        self.villager.task = "TILLING"
        self.villager.current_work_tile = (4, 7)
        self.villager.tilling_timer = 1.5
        ScheduledActivitySystem.reconcile(self.villager, "LEISURE")

        family = Family("schedule-family", "Smith")
        family.members = [self.villager]
        villager_manager = VillagerManager()
        villager_manager.families = [family]
        day_cycle = DayCycleSystem()
        resources = {}
        player = Player(0, 0)
        permit_manager = PermitManager()
        building_manager = BuildingManager()
        stockpile_manager = StockpileManager()
        furniture_manager = FurnitureManager()
        servant_manager = ServantManager()
        schedule_manager = ScheduleManager()

        saved = serialize_game_state(
            day_cycle, resources, player, permit_manager, building_manager,
            stockpile_manager, furniture_manager, villager_manager,
            servant_manager, schedule_manager,
        )

        loaded_villagers = VillagerManager()
        deserialize_game_state(
            saved, DayCycleSystem(), {}, Player(0, 0), PermitManager(),
            BuildingManager(), StockpileManager(), FurnitureManager(),
            loaded_villagers, ServantManager(), ScheduleManager(),
        )
        loaded_villager = loaded_villagers.get_all_villagers()[0]

        self.assertEqual(loaded_villager.pending_schedule_tasks[0]["task"], "TILLING")
        ScheduledActivitySystem.reconcile(loaded_villager, "WORK")
        self.assertEqual(loaded_villager.task, "TILLING")
        self.assertEqual(loaded_villager.tilling_timer, 1.5)
        self.assertEqual(loaded_villager.current_work_tile, (4, 7))


if __name__ == "__main__":
    unittest.main()
