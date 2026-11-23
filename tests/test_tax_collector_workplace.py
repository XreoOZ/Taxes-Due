import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from game.systems.economy.taxation_system import TaxationSystem
from game.systems.economy.currency import to_copper
from game.systems.work.scheduled_activity import ScheduledActivitySystem


class _Collector:
    id = "collector"
    job = "Tax Collector"
    is_alive = True
    x = 0.0
    y = 0.0
    socage_tax_round = None
    socage_tax_last_cycle = None

    def __init__(self):
        self.task = "IDLE"
        self.move_target = None
        self.messages = []

    def _move_towards(self, x, y, dt, **kwargs):
        self.move_target = (x, y)
        self.x, self.y = x, y
        return True

    def say(self, message, duration=0):
        self.messages.append((message, duration))


class _TaxOffice:
    building_type = "tax_house"
    is_available_for_use = True
    assigned_workers = ["collector"]
    tiles = {(2, 0), (3, 0)}

    def __init__(self):
        self.approach_point_calls = 0

    def get_approach_point(self, x, y, **kwargs):
        self.approach_point_calls += 1
        return (128.0, 192.0) if self.approach_point_calls == 1 else (192.0, 192.0)


class _VillagerManager:
    families = []

    def __init__(self, collector):
        self.collector = collector

    def get_all_villagers(self):
        return [self.collector]


class _DayCycle:
    day_number = 1


class TestTaxCollectorWorkplace(unittest.TestCase):
    def _update(self, activity, collector=None, office=None):
        collector = collector or _Collector()
        office = office or _TaxOffice()
        handled = TaxationSystem.update_collector(
            collector, 0.1, activity, _DayCycle(), None,
            _VillagerManager(collector),
            type("BuildingManager", (), {"buildings": [office]})(),
            None, [], None,
        )
        return collector, office, handled

    def test_collector_stations_at_assigned_tax_office_during_work(self):
        collector, _, handled = self._update("WORK")

        self.assertTrue(handled)
        self.assertEqual(collector.task, "STATIONED_AT_TAX_OFFICE")
        self.assertEqual(collector.move_target, (128.0, 192.0))

    def test_collector_also_reports_to_tax_office_during_any_activity(self):
        collector, _, handled = self._update("ANY")

        self.assertFalse(handled)
        self.assertIsNone(collector.move_target)

    def test_collector_does_not_report_to_tax_office_outside_work_time(self):
        collector, _, handled = self._update("LEISURE")

        self.assertFalse(handled)
        self.assertIsNone(collector.move_target)

    def test_station_approach_does_not_toggle_while_collector_moves(self):
        collector = _Collector()
        office = _TaxOffice()

        self._update("WORK", collector, office)
        first_target = collector.move_target
        collector.x = 150.0
        self._update("WORK", collector, office)

        self.assertEqual(collector.move_target, first_target)
        self.assertEqual(office.approach_point_calls, 1)

    def test_collection_round_does_not_start_outside_work_schedule(self):
        collector = _Collector()
        office = _TaxOffice()
        with patch.object(TaxationSystem, "_start_round", return_value=True) as start_round:
            handled = TaxationSystem.update_collector(
                collector, 0.1, "SLEEP", _DayCycle(), None,
                _VillagerManager(collector),
                type("BuildingManager", (), {"buildings": [office]})(),
                object(), [], None,
            )

        self.assertFalse(handled)
        self.assertIsNone(collector.socage_tax_round)
        start_round.assert_not_called()

    def test_collection_tasks_are_bound_to_work_schedule(self):
        tax_tasks = {
            "VISITING_HOUSEHOLD_FOR_TAX",
            "WAITING_FOR_HOUSEHOLD_TAX",
            "RETURNING_TAX_TO_TREASURY",
        }

        for task in tax_tasks:
            self.assertEqual(ScheduledActivitySystem.task_schedule(task), "WORK")
            self.assertFalse(ScheduledActivitySystem.task_is_allowed(task, "LEISURE"))

    def test_active_collection_pauses_outside_work_schedule(self):
        collector = _Collector()
        collector.socage_tax_round = {"status": "RETURN"}
        handled = TaxationSystem.update_collector(
            collector, 0.1, "SLEEP", _DayCycle(), None,
            _VillagerManager(collector),
            type("BuildingManager", (), {"buildings": []})(),
            object(), [], None,
        )

        self.assertFalse(handled)
        self.assertIsNone(collector.move_target)
        self.assertEqual(collector.socage_tax_round["status"], "RETURN")

    def test_new_households_are_added_to_an_active_round_queue_once(self):
        first = type("Family", (), {
            "id": "family-a",
            "members": [type("Member", (), {"is_alive": True})()],
        })()
        added = type("Family", (), {
            "id": "family-b",
            "members": [type("Member", (), {"is_alive": True})()],
        })()
        manager = type("VillagerManager", (), {"families": [first, added]})()
        round_state = {"family_ids": ["family-a"], "index": 1}

        TaxationSystem._refresh_household_queue(round_state, manager)
        TaxationSystem._refresh_household_queue(round_state, manager)

        self.assertEqual(round_state["family_ids"], ["family-a", "family-b"])

    def test_collector_waits_indefinitely_for_household_representative(self):
        collector = _Collector()
        representative = type("Representative", (), {"is_alive": True})()
        family = type("Family", (), {"id": "family-a", "members": [representative]})()
        manager = type("VillagerManager", (), {
            "families": [family],
            "get_all_villagers": lambda _self: [collector],
            "get_family_by_id": lambda _self, family_id: family if family_id == "family-a" else None,
        })()
        collector.socage_tax_round = {
            "family_ids": ["family-a"],
            "index": 0,
            "status": "MEET",
            "target_family_id": "family-a",
            "wait_seconds": 1000000.0,
        }

        with patch.object(TaxationSystem, "_family_meeting_point", return_value=(0.0, 0.0)):
            handled = TaxationSystem.update_collector(
                collector, 1000.0, "WORK", _DayCycle(), None, manager,
                type("BuildingManager", (), {"buildings": [_TaxOffice()]})(),
                object(), [collector], None,
            )

        self.assertTrue(handled)
        self.assertEqual(collector.socage_tax_round["index"], 0)
        self.assertEqual(collector.socage_tax_round["status"], "MEET")

    def test_collector_does_not_skip_household_without_meeting_location(self):
        collector = _Collector()
        representative = type("Representative", (), {"is_alive": True})()
        family = type("Family", (), {"id": "family-a", "members": [representative]})()
        manager = type("VillagerManager", (), {
            "families": [family],
            "get_all_villagers": lambda _self: [collector],
            "get_family_by_id": lambda _self, family_id: family if family_id == "family-a" else None,
        })()
        collector.socage_tax_round = {
            "family_ids": ["family-a"],
            "index": 0,
            "status": "TRAVEL",
        }

        with patch.object(TaxationSystem, "_family_meeting_point", return_value=None):
            handled = TaxationSystem.update_collector(
                collector, 0.1, "WORK", _DayCycle(), None, manager,
                type("BuildingManager", (), {"buildings": [_TaxOffice()]})(),
                object(), [collector], None,
            )

        self.assertTrue(handled)
        self.assertEqual(collector.socage_tax_round["index"], 0)
        self.assertEqual(collector.socage_tax_round["status"], "WAITING_FOR_HOUSEHOLD_LOCATION")

    def test_completed_collection_is_deposited_in_landlord_treasury(self):
        collector = _Collector()
        collector.inventory = {"Copper": 12}
        collector.socage_tax_round = {"status": "RETURN"}

        class Treasury:
            inventory = {}

            def get_approach_point(self, *_args, **_kwargs):
                return 16.0, 16.0

            def store_item(self, item, amount):
                self.inventory[item] = self.inventory.get(item, 0) + amount

        treasury = Treasury()
        household_chest = type("HouseholdChest", (), {
            "inventory": {"Copper": 25},
        })()
        furniture_manager = type("FurnitureManager", (), {
            "get_lord_treasury_chest": lambda _self: treasury,
            "get_storage_for_family": lambda _self, _family_id: household_chest,
        })()
        handled = TaxationSystem.update_collector(
            collector, 0.1, "WORK", _DayCycle(), None,
            _VillagerManager(collector),
            type("BuildingManager", (), {"buildings": []})(),
            furniture_manager, [], None,
        )

        self.assertTrue(handled)
        self.assertEqual(to_copper(treasury.inventory), 12)
        self.assertEqual(household_chest.inventory, {"Copper": 25})
        self.assertEqual(collector.inventory, {})
        self.assertIsNone(collector.socage_tax_round)

    def test_household_payment_flows_to_collector_then_treasury(self):
        collector = _Collector()
        collector.family_id = "collector-family"
        collector.inventory = {}

        class Representative:
            id = "representative"
            family_id = "family-a"
            is_alive = True
            age = 30
            radius = 20
            x = 64.0
            y = 64.0

            def __init__(self):
                self.inventory = {}
                self.task = "IDLE"
                self.socage_tax_prepared_cycle = None
                self.socage_tax_prepared_amount = 0

            def _move_towards(self, x, y, *_args, **_kwargs):
                self.x, self.y = x, y
                return True

            def say(self, *_args, **_kwargs):
                pass

            def _resume_or_idle_after_need(self):
                pass

        representative = Representative()
        family = type("Family", (), {
            "id": "family-a",
            "assigned_permit_id": None,
            "members": [representative],
        })()

        class CollectionManager(_VillagerManager):
            def __init__(self):
                super().__init__(collector)
                self.families = [family]

            def get_family_by_id(self, family_id):
                return next((item for item in self.families if item.id == family_id), None)

        class Treasury:
            def __init__(self):
                self.inventory = {}

            def get_approach_point(self, *_args, **_kwargs):
                return 16.0, 16.0

            def store_item(self, item, amount):
                self.inventory[item] = self.inventory.get(item, 0) + amount

        treasury = Treasury()
        household_chest = type("HouseholdChest", (), {
            "inventory": {"Copper": 100},
        })()
        furniture_manager = type("FurnitureManager", (), {
            "get_lord_treasury_chest": lambda _self: treasury,
            "get_storage_for_family": lambda _self, _family_id: household_chest,
        })()
        building_manager = type("BuildingManager", (), {
            "buildings": [_TaxOffice()],
        })()
        manager = CollectionManager()
        day_cycle = type("DayCycle", (), {"day_number": 10})()
        old_percent = TaxationSystem.get_socage_percent()
        self.addCleanup(TaxationSystem.set_socage_percent, old_percent)
        TaxationSystem.set_socage_percent(10)

        self.assertTrue(TaxationSystem.update_collector(
            collector, 0.1, "WORK", day_cycle, None, manager,
            building_manager, furniture_manager, [collector, representative], None,
        ))
        self.assertEqual(collector.socage_tax_round["status"], "MEET")
        self.assertTrue(TaxationSystem.update_household_representative(
            representative, 0.1, manager, None, building_manager,
            furniture_manager, [collector, representative], None, 10,
            collector_activity="WORK",
        ))
        self.assertEqual(to_copper(household_chest.inventory), 90)
        self.assertEqual(to_copper(collector.inventory), 10)

        TaxationSystem.update_collector(
            collector, 0.1, "WORK", day_cycle, None, manager,
            building_manager, furniture_manager, [collector, representative], None,
        )
        TaxationSystem.update_collector(
            collector, 0.1, "WORK", day_cycle, None, manager,
            building_manager, furniture_manager, [collector, representative], None,
        )
        TaxationSystem.update_collector(
            collector, 0.1, "WORK", day_cycle, None, manager,
            building_manager, furniture_manager, [collector, representative], None,
        )

        self.assertEqual(to_copper(treasury.inventory), 10)
        self.assertEqual(to_copper(household_chest.inventory), 90)
        self.assertEqual(collector.inventory, {})


if __name__ == "__main__":
    unittest.main()
