"""Unit test verifying Builder does not infinitely restock materials when commissioned."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.systems.work.builder_system import BuilderSystem
from game.data.structures import FURNITURE_TYPES


class TestBuilderCommissionNoInfiniteRestock(unittest.TestCase):
    def test_builder_does_not_restock_target_stock_when_recipe_satisfied(self):
        """
        When Builder receives a furniture commission (e.g. Bed requiring 5 Wood),
        and the Builder's storage already has 5 Wood (enough to build):
        The Builder MUST NOT trigger restocking for material_stock_target (e.g. 10 Stone),
        and MUST NOT spend coins buying materials.
        """
        builder = SimpleNamespace(
            id="builder_1",
            family_id="fam_builder",
            job="Builder",
            is_alive=True,
            task="IDLE",
            x=100.0,
            y=100.0,
            inventory={"Copper": 50},  # Has coins
            hunger=100.0,
            thirst=100.0,
            need_toilet=100.0,
            current_path=[],
            path_index=0,
            path_target=None,
            is_moving=False,
            active_tool=None,
            builder_payment_order_id=None,
            builder_target_order_id=None,
            builder_target_position=None,
            builder_failed_approach_points=set(),
        )
        builder.say = lambda *a, **k: None
        builder._move_towards = lambda *a, **k: True
        builder.get_inventory_room = lambda: 50
        builder._get_unneeded_inventory = lambda: []

        # Builder chest has 5 Wood and 0 Stone
        builder_chest_inv = {"Wood": 5}
        builder_chest = SimpleNamespace(
            inventory=builder_chest_inv,
            get_approach_point=lambda *a, **k: (100.0, 100.0),
        )

        # Customer chest has 0 Wood and 0 Stone
        customer_chest_inv = {}
        customer_chest = SimpleNamespace(
            inventory=customer_chest_inv,
            get_approach_point=lambda *a, **k: (200.0, 200.0),
        )

        def get_storage(fid):
            if fid == "fam_builder":
                return builder_chest
            elif fid == "fam_customer":
                return customer_chest
            return None

        # Bed furniture asset: requires 5 Wood, 0 Stone
        bed_order = {
            "id": "order_bed_1",
            "order_type": "BUILD",
            "status": "PAID",
            "builder_id": "builder_1",
            "payer_family_id": "fam_customer",
            "payer_type": "household",
            "commission_paid": True,
            "artisan_job": "Builder",
            "paid_seq": 1,
            "materials_delivered": {},
            "materials_committed": False,
        }
        bed_asset = SimpleNamespace(
            id="furniture_bed_1",
            furniture_type="bed",
            construction_order=bed_order,
            construction_progress=0.0,
            name="Bed",
            grid_x=5,
            grid_y=5,
        )
        bed_asset.get_world_pos = lambda *a, **k: (160.0, 160.0)
        bed_asset.get_approach_point = lambda *a, **k: (160.0, 160.0)

        fm = SimpleNamespace(
            furnitures=[bed_asset],
            get_storage_for_family=get_storage,
            invalidate_cache=lambda: None,
        )

        market = SimpleNamespace(
            id="mkt_1",
            building_type="market",
            is_under_construction=False,
            inventory={"Stone": 50, "Wood": 50},
            currency={"Copper": 0},
            grid_x=2,
            grid_y=2,
        )
        market.get_center_world = lambda *a, **k: (64.0, 64.0)
        market.get_approach_point = lambda *a, **k: (64.0, 64.0)

        bm = SimpleNamespace(
            buildings=[market],
            construction_sites=[],
        )

        fam_b = SimpleNamespace(id="fam_builder", members=[builder], currency={})
        fam_c = SimpleNamespace(id="fam_customer", members=[], currency={})
        vm = SimpleNamespace(
            get_family_by_id=lambda fid: fam_b if fid == "fam_builder" else (fam_c if fid == "fam_customer" else None),
            get_all_villagers=lambda: [builder],
        )

        day_cycle = SimpleNamespace(day_number=1, day_length_seconds=1440.0)

        # Run update_worker
        handled = BuilderSystem.update_worker(
            builder, dt=1.0, schedule_activity="WORK",
            building_manager=bm, furniture_manager=fm,
            villager_manager=vm, all_entities=[], player=None,
            day_cycle=day_cycle, stockpile_manager=None, permit_manager=None,
        )

        self.assertTrue(handled)
        # Builder must NOT have started restocking
        self.assertFalse(
            builder.task.startswith("BUILDER_RESTOCK_"),
            f"Builder task should not be restock! Got: {builder.task}"
        )
        # Builder must NOT have target_restock_market set
        self.assertIsNone(getattr(builder, "target_restock_market", None))
        # Coins must NOT have been spent
        self.assertEqual(builder.inventory.get("Copper", 0), 50, "Builder should not have spent his coins!")

    def test_builder_only_restocks_recipe_shortfall_not_unrelated_materials(self):
        """
        When recipe actually lacks materials (e.g. Bed needs 5 Wood, storage has 0 Wood),
        the Builder only restocks Wood, and does NOT restock Stone (which is 0 in storage
        but not needed by the recipe).
        """
        builder = SimpleNamespace(
            id="builder_1",
            family_id="fam_builder",
            job="Builder",
            is_alive=True,
            task="IDLE",
            x=100.0,
            y=100.0,
            inventory={"Copper": 100},
            hunger=100.0,
            thirst=100.0,
            need_toilet=100.0,
            current_path=[],
            path_index=0,
            path_target=None,
            is_moving=False,
            active_tool=None,
            builder_payment_order_id=None,
            builder_target_order_id=None,
            builder_target_position=None,
            builder_failed_approach_points=set(),
        )
        builder.say = lambda *a, **k: None
        builder._move_towards = lambda *a, **k: True
        builder.get_inventory_room = lambda: 50
        builder._get_unneeded_inventory = lambda: []

        builder_chest_inv = {}
        builder_chest = SimpleNamespace(
            inventory=builder_chest_inv,
            get_approach_point=lambda *a, **k: (100.0, 100.0),
        )

        def get_storage(fid):
            if fid == "fam_builder":
                return builder_chest
            return None

        bed_order = {
            "id": "order_bed_1",
            "order_type": "BUILD",
            "status": "PAID",
            "builder_id": "builder_1",
            "payer_family_id": "fam_customer",
            "payer_type": "household",
            "commission_paid": True,
            "artisan_job": "Builder",
            "paid_seq": 1,
            "materials_delivered": {},
            "materials_committed": False,
        }
        bed_asset = SimpleNamespace(
            id="furniture_bed_1",
            furniture_type="bed",
            construction_order=bed_order,
            construction_progress=0.0,
            name="Bed",
            grid_x=5,
            grid_y=5,
        )
        bed_asset.get_world_pos = lambda *a, **k: (160.0, 160.0)
        bed_asset.get_approach_point = lambda *a, **k: (160.0, 160.0)

        fm = SimpleNamespace(
            furnitures=[bed_asset],
            get_storage_for_family=get_storage,
            invalidate_cache=lambda: None,
        )

        market = SimpleNamespace(
            id="mkt_1",
            building_type="market",
            is_under_construction=False,
            inventory={"Stone": 50, "Wood": 50},
            currency={"Copper": 0},
            grid_x=2,
            grid_y=2,
        )
        market.get_center_world = lambda *a, **k: (64.0, 64.0)
        market.get_approach_point = lambda *a, **k: (64.0, 64.0)

        bm = SimpleNamespace(
            buildings=[market],
            construction_sites=[],
        )

        fam_b = SimpleNamespace(id="fam_builder", members=[builder], currency={})
        fam_c = SimpleNamespace(id="fam_customer", members=[], currency={})
        vm = SimpleNamespace(
            get_family_by_id=lambda fid: fam_b if fid == "fam_builder" else (fam_c if fid == "fam_customer" else None),
            get_all_villagers=lambda: [builder],
        )

        day_cycle = SimpleNamespace(day_number=1, day_length_seconds=1440.0)

        handled = BuilderSystem.update_worker(
            builder, dt=1.0, schedule_activity="WORK",
            building_manager=bm, furniture_manager=fm,
            villager_manager=vm, all_entities=[], player=None,
            day_cycle=day_cycle, stockpile_manager=None, permit_manager=None,
        )

        self.assertTrue(handled)
        # Should restock Wood, NOT Stone
        self.assertEqual(builder.target_restock_mat, "Wood")
        self.assertNotEqual(builder.target_restock_mat, "Stone")
        self.assertEqual(builder.task, "BUILDER_RESTOCK_RETRIEVE_COINS")


if __name__ == "__main__":
    unittest.main()
