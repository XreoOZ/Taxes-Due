import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game.systems.work.carpenter_system import CarpenterSystem


class _FurnitureManager:
    furnitures = []

    def get_storage_for_family(self, family_id):
        return None


class _Carpenter:
    id = "carpenter"
    job = "Carpenter"
    family_id = "family"

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.inventory = {"Wood": 2}
        self.task = "IDLE"
        self.movement_target = None
        self.movement_arrival_dist = None

    def _move_towards(self, x, y, dt, **kwargs):
        self.movement_target = (x, y)
        self.movement_arrival_dist = kwargs.get("arrival_dist")
        return False


class _RepairTarget:
    def __init__(self):
        self.grid_x = 0
        self.grid_y = 0
        self.tiles = {(0, 0), (1, 0), (2, 0)}
        self.type_cfg = {"width_tiles": 1, "height_tiles": 1}
        self.condition = 0.0
        self.construction_progress = 0.0
        self.construction_order = {
            "order_type": "REPAIR",
            "commission_paid": True,
            "carpenter_id": "carpenter",
            "status": "PAID",
            "materials_committed": True,
            "build_duration_seconds": 10.0,
        }

    def get_approach_point(self, x, y, **kwargs):
        return 96.0, 96.0


class TestCarpenterAssetWorkRange(unittest.TestCase):
    def _run_repair(self, carpenter):
        target = _RepairTarget()
        building_manager = SimpleNamespace(buildings=[target], construction_sites=[])
        CarpenterSystem.update_worker(
            carpenter, 0.25, "WORK", building_manager, _FurnitureManager(),
            None, [], None, None,
        )
        return target

    def test_public_repair_routes_to_perimeter_and_waits_until_in_range(self):
        carpenter = _Carpenter(96.0, 126.0)

        target = self._run_repair(carpenter)

        self.assertEqual(carpenter.movement_target, (96.0, 96.0))
        self.assertEqual(target.construction_progress, 0.0)

        carpenter.y = 121.0
        target = self._run_repair(carpenter)

        self.assertEqual(target.construction_progress, 0.25)

    def test_shared_work_range_checks_distance_to_asset_bounds(self):
        carpenter = _Carpenter(96.0, 126.0)
        target = _RepairTarget()

        self.assertFalse(CarpenterSystem._within_asset_work_range(carpenter, target))
        carpenter.y = 121.0
        self.assertTrue(CarpenterSystem._within_asset_work_range(carpenter, target))

    def test_material_delivery_moves_close_enough_to_enter_asset_work_range(self):
        carpenter = _Carpenter(224.0, 132.0)
        target = _RepairTarget()
        target.get_approach_point = lambda *args, **kwargs: (224.0, 96.0)
        order = {"id": "repair:market:0:0", "materials_delivered": {}}
        required = {"Wood": 2}

        CarpenterSystem._deliver_build_materials(
            carpenter, target, order, required, None, 0.25,
            [], None, None, _FurnitureManager(), furniture_target=True,
        )

        self.assertEqual(carpenter.movement_target, (224.0, 96.0))
        self.assertLess(carpenter.movement_arrival_dist, 36.0)

        carpenter.y = 108.0
        CarpenterSystem._deliver_build_materials(
            carpenter, target, order, required, None, 0.25,
            [], None, None, _FurnitureManager(), furniture_target=True,
        )
        self.assertTrue(order["materials_committed"])

    def test_restock_is_started_only_during_work(self):
        carpenter = _Carpenter(96.0, 96.0)
        building_manager = SimpleNamespace(buildings=[], construction_sites=[])
        furniture_manager = _FurnitureManager()

        with patch.object(CarpenterSystem, "_begin_restock", return_value=True) as begin_restock:
            for schedule in ("LEISURE", "ANY"):
                self.assertFalse(CarpenterSystem.update_worker(
                    carpenter, 0.25, schedule, building_manager, furniture_manager,
                    None, [], None, None,
                ))
            begin_restock.assert_not_called()

            self.assertTrue(CarpenterSystem.update_worker(
                carpenter, 0.25, "WORK", building_manager, furniture_manager,
                None, [], None, None,
            ))
            begin_restock.assert_called_once()

    def test_active_restock_pauses_outside_work(self):
        carpenter = _Carpenter(96.0, 96.0)
        carpenter.task = "CARPENTER_RESTOCK_HAULING_HOME"
        building_manager = SimpleNamespace(buildings=[], construction_sites=[])
        furniture_manager = _FurnitureManager()

        with patch.object(CarpenterSystem, "_update_restock", return_value=True) as update_restock:
            self.assertFalse(CarpenterSystem.update_worker(
                carpenter, 0.25, "LEISURE", building_manager, furniture_manager,
                None, [], None, None,
            ))
            self.assertFalse(CarpenterSystem.update_worker(
                carpenter, 0.25, "ANY", building_manager, furniture_manager,
                None, [], None, None,
            ))
            update_restock.assert_not_called()

            self.assertTrue(CarpenterSystem.update_worker(
                carpenter, 0.25, "WORK", building_manager, furniture_manager,
                None, [], None, None,
            ))
            update_restock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
