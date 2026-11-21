import unittest
from types import SimpleNamespace

from game.systems.activity_preview import ActivityPreviewSystem
from game.systems.scheduled_activity import ScheduledActivitySystem


class TestActivityPreview(unittest.TestCase):
    def test_preview_recomputes_when_the_active_task_changes(self):
        villager = SimpleNamespace(
            is_alive=True,
            task="CARPENTER_RESTOCK_HAULING_HOME",
            pending_commission_tasks=[],
            pending_schedule_tasks=[],
        )

        self.assertEqual(
            ActivityPreviewSystem.get_next_activities(villager),
            ["Store materials", "Resume Carpenter work"],
        )

        villager.task = "IDLE"
        self.assertEqual(ActivityPreviewSystem.get_next_activities(villager), [])

    def test_preview_combines_workflow_and_queued_tasks_and_caps_at_five(self):
        villager = SimpleNamespace(
            is_alive=True,
            task="BUYING_FOOD_RETRIEVE_GROUND_COINS",
            pending_commission_tasks=[{"task": "CONFESSION_TRAVEL_TO_PRIEST"}],
            pending_schedule_tasks=[{"task": "ACTIVE_WORK"}],
        )

        activities = ActivityPreviewSystem.get_next_activities(villager)

        self.assertEqual(len(activities), 5)
        self.assertEqual(activities[:4], [
            "Collect household coins",
            "Travel to the market",
            "Purchase food",
            "Return home and eat",
        ])

    def test_artisan_work_tasks_require_work_but_fee_errands_keep_free_time(self):
        for task in (
            "CARPENTER_RESTOCK_TRAVEL_TO_MARKET",
            "CARPENTER_CONSTRUCTING",
            "BLACKSMITH_FORGING",
            "BAKER_BAKING",
        ):
            self.assertTrue(ScheduledActivitySystem.task_is_allowed(task, "WORK"))
            self.assertFalse(ScheduledActivitySystem.task_is_allowed(task, "LEISURE"))
            self.assertFalse(ScheduledActivitySystem.task_is_allowed(task, "ANY"))

        self.assertTrue(ScheduledActivitySystem.task_is_allowed("CARPENTER_FEE_TRAVEL", "ANY"))


if __name__ == "__main__":
    unittest.main()
