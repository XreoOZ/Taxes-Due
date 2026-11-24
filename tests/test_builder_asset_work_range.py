import unittest
from types import SimpleNamespace
from unittest.mock import patch

from game.systems.work.builder_system import BuilderSystem


class _FurnitureManager:
    furnitures = []

    def get_storage_for_family(self, family_id):
        return None


class _Builder:
    id = "builder"
    job = "Builder"
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
            "builder_id": "builder",
            "status": "PAID",
            "materials_committed": True,
            "build_duration_seconds": 10.0,
        }

    def get_approach_point(self, x, y, **kwargs):
        return 96.0, 96.0


class TestBuilderAssetWorkRange(unittest.TestCase):
    def _run_repair(self, builder):
        target = _RepairTarget()
        building_manager = SimpleNamespace(buildings=[target], construction_sites=[])
        BuilderSystem.update_worker(
            builder, 0.25, "WORK", building_manager, _FurnitureManager(),
            None, [], None, None,
        )
        return target

    def test_public_repair_routes_to_perimeter_and_waits_until_in_range(self):
        builder = _Builder(96.0, 126.0)

        target = self._run_repair(builder)

        self.assertEqual(builder.movement_target, (96.0, 96.0))
        self.assertEqual(target.construction_progress, 0.0)

        builder.y = 121.0
        target = self._run_repair(builder)

        self.assertEqual(target.construction_progress, 0.25)

    def test_shared_work_range_checks_distance_to_asset_bounds(self):
        builder = _Builder(96.0, 126.0)
        target = _RepairTarget()

        self.assertFalse(BuilderSystem._within_asset_work_range(builder, target))
        builder.y = 121.0
        self.assertTrue(BuilderSystem._within_asset_work_range(builder, target))

    def test_material_delivery_moves_close_enough_to_enter_asset_work_range(self):
        builder = _Builder(224.0, 132.0)
        target = _RepairTarget()
        target.get_approach_point = lambda *args, **kwargs: (224.0, 96.0)
        order = {"id": "repair:market:0:0", "materials_delivered": {}}
        required = {"Wood": 2}

        BuilderSystem._deliver_build_materials(
            builder, target, order, required, None, 0.25,
            [], None, None, _FurnitureManager(), furniture_target=True,
        )

        self.assertEqual(builder.movement_target, (224.0, 96.0))
        self.assertLess(builder.movement_arrival_dist, 36.0)

        builder.y = 108.0
        BuilderSystem._deliver_build_materials(
            builder, target, order, required, None, 0.25,
            [], None, None, _FurnitureManager(), furniture_target=True,
        )
        self.assertTrue(order["materials_committed"])

    def test_restock_is_started_only_during_work(self):
        builder = _Builder(96.0, 96.0)
        building_manager = SimpleNamespace(buildings=[], construction_sites=[])
        furniture_manager = _FurnitureManager()

        with patch.object(BuilderSystem, "_begin_restock", return_value=True) as begin_restock:
            for schedule in ("LEISURE", "ANY"):
                self.assertFalse(BuilderSystem.update_worker(
                    builder, 0.25, schedule, building_manager, furniture_manager,
                    None, [], None, None,
                ))
            begin_restock.assert_not_called()

            self.assertTrue(BuilderSystem.update_worker(
                builder, 0.25, "WORK", building_manager, furniture_manager,
                None, [], None, None,
            ))
            begin_restock.assert_called_once()

    def test_active_restock_pauses_outside_work(self):
        builder = _Builder(96.0, 96.0)
        builder.task = "BUILDER_RESTOCK_HAULING_HOME"
        building_manager = SimpleNamespace(buildings=[], construction_sites=[])
        furniture_manager = _FurnitureManager()

        with patch.object(BuilderSystem, "_update_restock", return_value=True) as update_restock:
            self.assertFalse(BuilderSystem.update_worker(
                builder, 0.25, "LEISURE", building_manager, furniture_manager,
                None, [], None, None,
            ))
            self.assertFalse(BuilderSystem.update_worker(
                builder, 0.25, "ANY", building_manager, furniture_manager,
                None, [], None, None,
            ))
            update_restock.assert_not_called()

            self.assertTrue(BuilderSystem.update_worker(
                builder, 0.25, "WORK", building_manager, furniture_manager,
                None, [], None, None,
            ))
            update_restock.assert_called_once()

    def test_repair_order_materials_is_one_wood_and_one_stone(self):
        from game.data.structures import BUILDER_REPAIR_MATERIALS
        self.assertEqual(BUILDER_REPAIR_MATERIALS, {"Wood": 1, "Stone": 1})

        target = _RepairTarget()
        order = BuilderSystem.create_repair_order(target)
        self.assertEqual(order["materials"], {"Wood": 1, "Stone": 1})
        # Default Wood (2) + Default Stone (3) = 5 copper material cost
        self.assertEqual(order["material_cost_copper"], 5)
        # Default food unit price (3) * 1 * 3 days = 9 copper living wage
        self.assertEqual(order["living_wage_copper"], 9)
        self.assertEqual(order["price_copper"], 14)


if __name__ == "__main__":
    unittest.main()
