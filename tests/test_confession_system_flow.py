import unittest
from unittest.mock import patch

from game.config import TILE_SIZE
from game.systems.village_life.church_system import ChurchSystem
from game.systems.village_life.confession_system import ConfessionSystem
from game.systems.economy.currency import to_copper
from game.systems.work.schedule import ScheduleManager


class _Actor:
    def __init__(self, actor_id, job, family_id=None, x=0.0, y=0.0):
        self.id = actor_id
        self.job = job
        self.family_id = family_id
        self.is_alive = True
        self.faith = 100.0
        self.x = x
        self.y = y
        self.inventory = {}
        self.task = "IDLE"
        self.confession_task = None
        self.move_target = None
        self.messages = []

    def _move_towards(self, x, y, _dt, **_kwargs):
        self.move_target = (x, y)
        return False

    def say(self, message, **_kwargs):
        self.messages.append(message)


class TestConfessionSystemFlow(unittest.TestCase):
    def setUp(self):
        instance = ConfessionSystem.get_instance()
        instance.queues.clear()
        instance.active.clear()

    def tearDown(self):
        instance = ConfessionSystem.get_instance()
        instance.queues.clear()
        instance.active.clear()

    @staticmethod
    def _request(villager_id, payment_ready=True):
        return {
            "villager_id": villager_id,
            "church_id": "church-1",
            "priest_id": "priest-1",
            "box_id": "box-1",
            "wait_seconds": 0.0,
            "fee_due": 0,
            "fee_offer": 0,
            "payment_ready": payment_ready,
            "self_confession": False,
            "state": "READY" if payment_ready else "RETRIEVING_PAYMENT",
        }

    def test_available_priest_drives_active_request_after_payment_preparation(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-2", x=256.0, y=128.0)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": ["priest-1"],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        instance = ConfessionSystem.get_instance()
        instance.queues["church-1"] = [request]

        handled = ConfessionSystem.update_villager(
            visitor, 0.1, "LEISURE",
            type("DayCycle", (), {"day_number": 1, "day_length_seconds": 1200.0})(),
            permit_manager, villager_manager, None, furniture_manager, [visitor, priest],
            None,
        )

        priest_handled = ConfessionSystem.update_priest(
            priest, 0.1,
            type("DayCycle", (), {"day_number": 1, "day_length_seconds": 1200.0})(),
            None, permit_manager, villager_manager, None, furniture_manager,
            [visitor, priest], None,
        )

        self.assertTrue(handled)
        self.assertTrue(priest_handled)
        self.assertEqual(visitor.task, "CONFESSION_TRAVEL_TO_PRIEST")
        self.assertEqual(visitor.move_target, (priest.x, priest.y))
        self.assertEqual(priest.task, "GOING_TO_CONFESSOR")
        self.assertIs(instance.active["church-1"], request)
        self.assertEqual(instance.queues["church-1"], [])

    def test_confession_request_can_start_during_any_schedule(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        visitor.faith = 0.0
        priest = _Actor("priest-1", "Priest", "family-2")
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
            "get_storage_for_family": lambda _self, _family_id: None,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        day_cycle = type("DayCycle", (), {
            "current_hour": 10.0,
            "day_number": 1,
            "day_length_seconds": 1200.0,
        })()
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 10, "ANY")
        schedule_manager.set_hour_activity("Priest", 10, "ANY")

        with patch.object(
            ConfessionSystem, "_find_service", return_value=(church, priest, box)
        ):
            handled = ConfessionSystem.update_villager(
                visitor, 0.1, "ANY", day_cycle, permit_manager,
                villager_manager, None, furniture_manager, [visitor, priest],
                None, schedule_manager,
            )

        self.assertTrue(handled)
        self.assertEqual(
            ConfessionSystem.get_instance().active["church-1"]["villager_id"],
            visitor.id,
        )

    def test_confession_queue_waits_until_visitor_free_time_ends(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-2", x=3 * TILE_SIZE)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        day_cycle = type("DayCycle", (), {
            "current_hour": 10.0,
            "day_number": 1,
            "day_length_seconds": 1200.0,
        })()
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 10, "LEISURE")
        schedule_manager.set_hour_activity("Priest", 10, "LEISURE")
        request = self._request(visitor.id)
        request["state"] = "VISITOR_TO_PRIEST"
        ConfessionSystem.get_instance().active["church-1"] = request

        ConfessionSystem.update_priest(
            priest, day_cycle.day_length_seconds, day_cycle,
            schedule_manager, permit_manager,
            villager_manager, None, furniture_manager, [visitor, priest], None,
        )
        self.assertIs(
            ConfessionSystem.get_instance().active["church-1"], request
        )

        schedule_manager.set_hour_activity("Farmer", 10, "WORK")
        ConfessionSystem.update_priest(
            priest, 0.1, day_cycle, schedule_manager, permit_manager,
            villager_manager, None, furniture_manager, [visitor, priest], None,
        )
        self.assertNotIn("church-1", ConfessionSystem.get_instance().active)
        self.assertEqual(visitor.task, "IDLE")

    def test_confession_stops_when_priest_schedule_ends_and_refunds_offering(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-2")
        priest.inventory = {"Copper": 10}
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        day_cycle = type("DayCycle", (), {
            "current_hour": 10.0,
            "day_number": 1,
        })()
        schedule_manager = ScheduleManager()
        schedule_manager.set_hour_activity("Farmer", 10, "LEISURE")
        schedule_manager.set_hour_activity("Priest", 10, "WORK")
        request = self._request(visitor.id)
        request.update({"state": "IN_PROGRESS", "fee_paid": 10})
        ConfessionSystem.get_instance().active["church-1"] = request

        handled = ConfessionSystem.update_priest(
            priest, 0.1, day_cycle, schedule_manager, permit_manager,
            villager_manager, None, furniture_manager, [visitor, priest], None,
        )

        self.assertFalse(handled)
        self.assertNotIn("church-1", ConfessionSystem.get_instance().active)
        self.assertEqual(to_copper(visitor.inventory), 10)
        self.assertEqual(priest.inventory, {})
        self.assertEqual(visitor.task, "IDLE")

    def test_confessor_and_priest_interact_within_one_tile(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-1", x=TILE_SIZE - 4.0)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": ["priest-1"],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        request["state"] = "VISITOR_TO_PRIEST"
        ConfessionSystem.get_instance().active["church-1"] = request

        handled = ConfessionSystem.update_priest(
            priest, 0.1, type("DayCycle", (), {})(), None,
            permit_manager, villager_manager, None, furniture_manager,
            [visitor, priest], None,
        )

        self.assertTrue(handled)
        self.assertEqual(request["state"], "BOTH_TO_BOX")

    def test_priest_advances_when_confessor_is_within_one_tile(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-2", x=TILE_SIZE - 4.0)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        request["state"] = "VISITOR_TO_PRIEST"
        ConfessionSystem.get_instance().active["church-1"] = request

        with patch.object(ConfessionSystem, "_move_to_box"):
            handled = ConfessionSystem.update_priest(
                priest, 0.1, type("DayCycle", (), {})(), None,
                permit_manager, villager_manager, None, furniture_manager,
                [visitor, priest], None,
            )

        self.assertTrue(handled)
        self.assertEqual(request["state"], "BOTH_TO_BOX")
        self.assertEqual(priest.task, "GOING_TO_CONFESSION_BOX")
        self.assertEqual(priest.confession_task, "GOING_TO_BOX")

    def test_priest_moves_toward_active_confessor_instead_of_waiting(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        priest = _Actor("priest-1", "Priest", "family-2", x=3 * TILE_SIZE)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        request["state"] = "VISITOR_TO_PRIEST"
        ConfessionSystem.get_instance().active["church-1"] = request

        with patch.object(ConfessionSystem, "_move_to_box"):
            handled = ConfessionSystem.update_priest(
                priest, 0.1, type("DayCycle", (), {})(), None,
                permit_manager, villager_manager, None, furniture_manager,
                [visitor, priest], None,
            )

        self.assertTrue(handled)
        self.assertEqual(priest.task, "GOING_TO_CONFESSOR")
        self.assertEqual(priest.confession_task, "APPROACHING_VISITOR")
        self.assertEqual(priest.move_target, (visitor.x, visitor.y))
        self.assertEqual(request["state"], "VISITOR_TO_PRIEST")

    def test_priest_owns_confession_progression_and_starts_next_fifo_request(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        next_visitor = _Actor("visitor-2", "Farmer", "family-1", x=2 * TILE_SIZE)
        priest = _Actor("priest-1", "Priest", "family-1", x=TILE_SIZE - 4.0)
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, next_visitor, priest],
        })()
        first_request = self._request(visitor.id)
        first_request["state"] = "VISITOR_TO_PRIEST"
        next_request = self._request(next_visitor.id)
        instance = ConfessionSystem.get_instance()
        instance.active["church-1"] = first_request
        instance.queues["church-1"] = [next_request]
        day_cycle = type("DayCycle", (), {
            "day_number": 1,
            "day_length_seconds": 1200.0,
        })()

        self.assertTrue(ConfessionSystem.update_priest(
            priest, 0.1, day_cycle, None, permit_manager, villager_manager,
            None, furniture_manager, [visitor, next_visitor, priest], None,
        ))
        self.assertEqual(first_request["state"], "BOTH_TO_BOX")
        self.assertEqual(priest.inventory, {})

        with patch.object(ConfessionSystem, "_move_to_box"), \
                patch.object(ConfessionSystem, "_at_approach", return_value=True):
            ConfessionSystem.update_priest(
                priest, 0.1, day_cycle, None, permit_manager, villager_manager,
                None, furniture_manager, [visitor, next_visitor, priest], None,
            )
        self.assertEqual(first_request["state"], "IN_PROGRESS")

        with patch("game.systems.village_life.happiness_system.HappinessSystem.record_event"):
            ConfessionSystem.update_priest(
                priest, 5.0, day_cycle, None, permit_manager, villager_manager,
                None, furniture_manager, [visitor, next_visitor, priest], None,
            )
        self.assertNotIn("church-1", instance.active)
        self.assertEqual(instance.queues["church-1"], [next_request])

        ConfessionSystem.update_priest(
            priest, 0.1, day_cycle, None, permit_manager, villager_manager,
            None, furniture_manager, [visitor, next_visitor, priest], None,
        )
        self.assertIs(instance.active["church-1"], next_request)

    def test_fifo_activates_only_the_first_ready_confessor(self):
        first = self._request("visitor-1")
        second = self._request("visitor-2")
        queue = [first, second]

        active = ConfessionSystem._activate_next_request("church-1", queue)

        self.assertIs(active, first)
        self.assertEqual(active["state"], "VISITOR_TO_PRIEST")
        self.assertEqual(queue, [second])
        self.assertIs(ConfessionSystem._activate_next_request("church-1", queue), first)
        self.assertEqual(queue, [second])

    def test_priest_retains_funds_until_the_confession_queue_is_empty(self):
        priest = _Actor("priest-1", "Priest")
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
            "assigned_workers": [priest.id],
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        instance = ConfessionSystem.get_instance()
        instance.queues["church-1"] = [self._request("visitor-1")]

        self.assertTrue(ConfessionSystem.has_pending_requests_for_priest(
            priest, permit_manager,
        ))

        instance.queues["church-1"].clear()
        instance.active["church-1"] = self._request("visitor-2")
        self.assertTrue(ConfessionSystem.has_pending_requests_for_priest(
            priest, permit_manager,
        ))

        instance.active.clear()
        self.assertFalse(ConfessionSystem.has_pending_requests_for_priest(
            priest, permit_manager,
        ))

    def test_confession_takes_five_simulation_seconds(self):
        self.assertEqual(ConfessionSystem._confession_duration(), 5.0)

    def test_later_confessor_waits_inside_church_while_first_is_active(self):
        visitor = _Actor("visitor-2", "Farmer", "family-2")
        priest = _Actor("priest-1", "Priest", "family-3")
        active = self._request("visitor-1")
        queued = self._request(visitor.id, payment_ready=False)
        queued["fee_due"] = 20
        church = type("Church", (), {
            "id": "church-1",
            "permit_type": "church",
        })()
        box = type("Box", (), {
            "id": "box-1",
            "is_available_for_use": True,
        })()
        permit_manager = type("PermitManager", (), {"permits": [church]})()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _box_id: box,
            "_furniture_tiles": lambda _self, _furniture: set(),
            "get_furniture_at": lambda _self, *_tile: None,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        instance = ConfessionSystem.get_instance()
        instance.active["church-1"] = active
        instance.queues["church-1"] = [queued]

        with patch.object(
                ChurchSystem, "get_church_walkable_tiles",
                return_value=[(2, 2), (3, 2)]):
            handled = ConfessionSystem.update_villager(
                visitor, 0.1, "LEISURE",
                type("DayCycle", (), {"day_number": 1, "day_length_seconds": 1200.0})(),
                permit_manager, villager_manager, None, furniture_manager, [visitor, priest],
                None,
            )

        self.assertTrue(handled)
        self.assertEqual(visitor.task, "CONFESSION_QUEUED")
        self.assertEqual(visitor.move_target, (2.5 * TILE_SIZE, 2.5 * TILE_SIZE))
        self.assertIs(instance.queues["church-1"][0], queued)
        self.assertIs(instance.active["church-1"], active)

    def test_cancelled_request_refunds_withdrawn_coins_to_household_chest(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        visitor.inventory = {"Copper": 20}
        priest = _Actor("priest-1", "Priest")
        chest = type("Chest", (), {
            "id": "chest-1",
            "family_id": "family-1",
            "inventory": {"Copper": 80},
        })()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _chest_id: chest,
            "get_storage_for_family": lambda _self, _family_id: chest,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        request.update({
            "payment_chest_id": chest.id,
            "payment_family_id": visitor.family_id,
            "payment_source": "inventory",
            "withdrawn_amount": 20,
        })
        ConfessionSystem.get_instance().queues["church-1"] = [request]

        ConfessionSystem._cancel_request(
            request, villager_manager, "The confession was canceled.",
            furniture_manager,
        )

        self.assertEqual(to_copper(chest.inventory), 100)
        self.assertEqual(to_copper(visitor.inventory), 0)
        self.assertEqual(ConfessionSystem.get_instance().queues["church-1"], [])

    def test_cancellation_after_offering_refunds_offering_then_household_withdrawal(self):
        visitor = _Actor("visitor-1", "Farmer", "family-1")
        visitor.inventory = {"Copper": 5}
        priest = _Actor("priest-1", "Priest")
        priest.inventory = {"Copper": 15}
        chest = type("Chest", (), {
            "id": "chest-1",
            "family_id": "family-1",
            "inventory": {"Copper": 80},
        })()
        furniture_manager = type("FurnitureManager", (), {
            "get_furniture_by_id": lambda _self, _chest_id: chest,
            "get_storage_for_family": lambda _self, _family_id: chest,
        })()
        villager_manager = type("VillagerManager", (), {
            "get_all_villagers": lambda _self: [visitor, priest],
        })()
        request = self._request(visitor.id)
        request.update({
            "payment_chest_id": chest.id,
            "payment_family_id": visitor.family_id,
            "payment_source": "inventory",
            "withdrawn_amount": 20,
            "fee_paid": 15,
        })
        ConfessionSystem.get_instance().active["church-1"] = request

        ConfessionSystem._cancel_request(
            request, villager_manager, "The confession was canceled.",
            furniture_manager,
        )

        self.assertEqual(to_copper(chest.inventory), 100)
        self.assertEqual(to_copper(visitor.inventory), 0)
        self.assertEqual(to_copper(priest.inventory), 0)
        self.assertNotIn("church-1", ConfessionSystem.get_instance().active)


if __name__ == "__main__":
    unittest.main()
