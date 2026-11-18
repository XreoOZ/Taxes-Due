"""
Comprehensive Acceptance Tests for AGENT 3 Deliverables:
- Production Distribution & Household Shares (Cases A, B, C, D, Indivisible Handling, Zero Loss)
- Potato Farming Yield Adjustment (2 Potatoes / Tile, 8 Tiles = 16 Potatoes)
- Tax System (WIP reporting, zero deductions)
- Persistent WIP Planning Registry & In-Game UI Overview
"""

import unittest
import os
import pygame

# Headless pygame environment for headless test runner
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import CROP_TYPES, RAPORT_MODAL_WIDTH, RAPORT_MODAL_HEIGHT
from game.systems.production_distribution import ProductionDistributionSystem
from game.data.planning import (
    PLANNING_FEATURES,
    get_all_planning_features,
    get_features_by_status,
    STATUS_IMPLEMENTED,
    STATUS_PARTIAL,
    STATUS_PLANNED
)
from game.world.permits import AreaPermit, PermitManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.world.stockpile import StockpileManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.ui.ui_raport import RaportUI


class TestProductionDistributionAndWIP(unittest.TestCase):
    def setUp(self):
        self.ps = ProductionDistributionSystem.get_instance()
        self.ps.household_records.clear()
        self.ps.remainder_credits.clear()
        self.furniture_manager = FurnitureManager()
        self.stockpile_manager = StockpileManager()
        self.permit_manager = PermitManager()
        self.villager_manager = VillagerManager()

    # =========================================================================
    # 1. PRODUCTION DISTRIBUTION — HOUSEHOLD SHARES & MATH
    # =========================================================================

    def test_case_a_single_household_100_percent(self):
        """Case A: Household A: 1 worker. Total: 1. A receives 100%."""
        workers = {"Household_A": 1}
        shares = self.ps.calculate_shares(workers)
        self.assertAlmostEqual(shares["Household_A"], 1.0)

        dist = self.ps.calculate_distribution(10, workers, workplace_id="wp_test_a")
        self.assertEqual(dist["Household_A"], 10)
        self.assertEqual(sum(dist.values()), 10)

    def test_case_b_two_equal_households_50_percent(self):
        """Case B: Household A: 1 worker, Household B: 1 worker. Total: 2. A: 50%, B: 50%."""
        workers = {"Household_A": 1, "Household_B": 1}
        shares = self.ps.calculate_shares(workers)
        self.assertAlmostEqual(shares["Household_A"], 0.5)
        self.assertAlmostEqual(shares["Household_B"], 0.5)

        dist = self.ps.calculate_distribution(10, workers, workplace_id="wp_test_b")
        self.assertEqual(dist["Household_A"], 5)
        self.assertEqual(dist["Household_B"], 5)
        self.assertEqual(sum(dist.values()), 10)

    def test_case_c_unequal_households_33_and_67_percent(self):
        """Case C: Household A: 1 worker, Household B: 2 workers. Total: 3. A: 33.33%, B: 66.67%."""
        workers = {"Household_A": 1, "Household_B": 2}
        shares = self.ps.calculate_shares(workers)
        self.assertAlmostEqual(shares["Household_A"], 1.0 / 3.0)
        self.assertAlmostEqual(shares["Household_B"], 2.0 / 3.0)

        dist = self.ps.calculate_distribution(15, workers, workplace_id="wp_test_c")
        self.assertEqual(dist["Household_A"], 5)
        self.assertEqual(dist["Household_B"], 10)
        self.assertEqual(sum(dist.values()), 15)

    def test_case_d_two_households_40_and_60_percent(self):
        """Case D: Household A: 2 workers, Household B: 3 workers. Total: 5. A: 40%, B: 60%."""
        workers = {"Household_A": 2, "Household_B": 3}
        shares = self.ps.calculate_shares(workers)
        self.assertAlmostEqual(shares["Household_A"], 0.40)
        self.assertAlmostEqual(shares["Household_B"], 0.60)

        dist = self.ps.calculate_distribution(10, workers, workplace_id="wp_test_d")
        self.assertEqual(dist["Household_A"], 4)
        self.assertEqual(dist["Household_B"], 6)
        self.assertEqual(sum(dist.values()), 10)

    def test_any_number_of_participating_households(self):
        """Support any number of participating households dynamically."""
        workers = {f"Household_{i}": i + 1 for i in range(7)}  # 7 households with counts 1..7
        total_workers = sum(workers.values())
        shares = self.ps.calculate_shares(workers)

        for h, count in workers.items():
            expected_ratio = count / total_workers
            self.assertAlmostEqual(shares[h], expected_ratio)

        # Distribute 100 items
        dist = self.ps.calculate_distribution(100, workers, workplace_id="wp_test_many")
        self.assertEqual(sum(dist.values()), 100, "Must distribute exactly 100 items without loss")

    def test_indivisible_item_quantities_zero_loss_zero_duplication(self):
        """Indivisible quantities must never create or destroy resources across varying amounts."""
        workers = {"Household_A": 1, "Household_B": 2}  # 1/3 vs 2/3
        for amt in [1, 2, 3, 4, 5, 7, 8, 11, 16, 23, 100]:
            dist = self.ps.calculate_distribution(amt, workers, workplace_id=f"wp_indivisible_{amt}")
            self.assertEqual(sum(dist.values()), amt, f"Mismatch for total amount {amt}: sum was {sum(dist.values())}")
            # All quantities must be non-negative integers
            for h, q in dist.items():
                self.assertIsInstance(q, int)
                self.assertGreaterEqual(q, 0)

    def test_indivisible_quantities_over_repeated_cycles_converges(self):
        """Over repeated single-item or two-item cycles, distribution converges accurately to true share."""
        workers = {"Household_A": 1, "Household_B": 1}  # 50% / 50%
        wp = "wp_repeated_cycle_test"

        total_a = 0
        total_b = 0
        # Distribute 1 potato per tile 40 times
        for _ in range(40):
            dist = self.ps.calculate_distribution(1, workers, workplace_id=wp)
            total_a += dist["Household_A"]
            total_b += dist["Household_B"]

        self.assertEqual(total_a + total_b, 40)
        self.assertEqual(total_a, 20)
        self.assertEqual(total_b, 20)

    def test_participating_workers_as_object_list(self):
        """Accepts participating workers as a list of objects with family_id."""
        class MockWorker:
            def __init__(self, w_id, fam_id):
                self.id = w_id
                self.family_id = fam_id

        workers = [
            MockWorker("w1", "fam_A"),
            MockWorker("w2", "fam_B"),
            MockWorker("w3", "fam_B")
        ]
        shares = self.ps.calculate_shares(workers)
        self.assertAlmostEqual(shares["fam_A"], 1.0 / 3.0)
        self.assertAlmostEqual(shares["fam_B"], 2.0 / 3.0)

    # =========================================================================
    # 2. HOUSEHOLD STORAGE DEPOSITION & NO AUTO-MARKET TRANSFER
    # =========================================================================

    def test_deposit_into_household_storage_chest(self):
        """Output reaches the respective household storage chest."""
        chest_a = Furniture("f1", "household_storage", 5, 5, family_id="fam_A")
        chest_b = Furniture("f2", "household_storage", 10, 10, family_id="fam_B")
        self.furniture_manager.furnitures.extend([chest_a, chest_b])

        workers = {"fam_A": 1, "fam_B": 1}
        res = self.ps.distribute_production(
            resource_name="Potato",
            amount=4,
            participating_workers=workers,
            furniture_manager=self.furniture_manager,
            workplace_id="farm_lot_1",
            auto_deposit=True
        )

        self.assertEqual(chest_a.inventory.get("Potato"), 2)
        self.assertEqual(chest_b.inventory.get("Potato"), 2)
        self.assertEqual(res["distribution"]["fam_A"], 2)
        self.assertEqual(res["distribution"]["fam_B"], 2)

    def test_deposit_to_ground_when_no_chest(self):
        """Output drops at household's location via stockpile_manager when chest is absent."""
        workers = {"fam_homeless": 1}
        res = self.ps.distribute_production(
            resource_name="Potato",
            amount=2,
            participating_workers=workers,
            furniture_manager=self.furniture_manager,
            stockpile_manager=self.stockpile_manager,
            workplace_id="farm_lot_homeless",
            auto_deposit=True
        )

        self.assertEqual(res["distribution"]["fam_homeless"], 2)
        ground_stacks = [s for s in self.stockpile_manager.stacks if s.owner_id == "fam_homeless"]
        self.assertGreater(len(ground_stacks), 0)
        self.assertEqual(sum(s.amount for s in ground_stacks), 2)

    def test_production_not_transferred_to_market(self):
        """Production belongs to household storage and is never deposited into market stalls."""
        chest = Furniture("f_h", "household_storage", 2, 2, family_id="fam_1")
        self.furniture_manager.furnitures.append(chest)

        self.ps.distribute_production(
            resource_name="Potato",
            amount=6,
            participating_workers={"fam_1": 1},
            furniture_manager=self.furniture_manager,
            stockpile_manager=self.stockpile_manager,
            auto_deposit=True
        )

        self.assertEqual(chest.inventory.get("Potato"), 6)
        # Verify market storage / global stockpile is untouched
        landlord_stacks = [s for s in self.stockpile_manager.stacks if getattr(s, "owner_type", None) == "landlord"]
        self.assertEqual(len(landlord_stacks), 0)

    def test_generic_across_professions(self):
        """Distribution system works generically across all professions and item types."""
        items = ["Potato", "Iron_Tool", "Wood_Beam", "Bread", "Cloth"]
        for it in items:
            dist = self.ps.calculate_distribution(6, {"H1": 1, "H2": 2}, workplace_id=f"wp_{it}")
            self.assertEqual(dist["H1"], 2)
            self.assertEqual(dist["H2"], 4)
            self.assertEqual(sum(dist.values()), 6)

    # =========================================================================
    # 3. POTATO FARMING PRODUCTION ADJUSTMENT (2 / Tile Every 10 Days)
    # =========================================================================

    def test_potato_config_yield_value(self):
        """CROP_TYPES potato config must define yield 2 per tile."""
        potato_cfg = CROP_TYPES.get("potato", {})
        self.assertEqual(potato_cfg.get("yield_per_tile"), 2)
        self.assertEqual(potato_cfg.get("yield"), 2)
        self.assertEqual(potato_cfg.get("growth_days"), 10.0)

    def test_potato_harvest_tile_yields_exactly_two(self):
        """Each successfully harvested potato tile must produce exactly 2 Potatoes."""
        farm = AreaPermit("farm_1", "Potato Farm", "farm", [(5, 5)])
        farm.crop = "Potato"
        farm.tile_crops = {
            (5, 5): {
                "crop": "Potato",
                "growth_days": 10.0,
                "watered_today": True,
                "unwatered_days": 0,
                "is_dead": False
            }
        }

        yield_amt = farm.harvest_tile(5, 5)
        self.assertEqual(yield_amt, 2, "Harvested tile must yield exactly 2 potatoes")

    def test_farmer_managing_8_tiles_harvests_16_potatoes(self):
        """A farmer managing 8 potato tiles harvests 16 Potatoes after 10 days."""
        tiles = [(x, y) for x in range(4) for y in range(2)]  # 8 tiles
        farm = AreaPermit("farm_8", "Eight Tile Farm", "farm", tiles)
        farm.crop = "Potato"
        farm.tile_crops = {
            t: {
                "crop": "Potato",
                "growth_days": 10.0,
                "watered_today": True,
                "unwatered_days": 0,
                "is_dead": False
            }
            for t in tiles
        }

        total_harvest = 0
        for t in tiles:
            total_harvest += farm.harvest_tile(t[0], t[1])

        self.assertEqual(total_harvest, 16, "8 potato tiles must yield exactly 16 potatoes")

    def test_unripe_potato_tile_produces_zero(self):
        """Growth stages & 10-day cycle preserved: tile under 10 days produces 0."""
        farm = AreaPermit("farm_unripe", "Unripe Farm", "farm", [(2, 2)])
        farm.crop = "Potato"
        farm.tile_crops = {
            (2, 2): {
                "crop": "Potato",
                "growth_days": 9.9,
                "watered_today": True,
                "unwatered_days": 0,
                "is_dead": False
            }
        }

        yield_amt = farm.harvest_tile(2, 2)
        self.assertEqual(yield_amt, 0, "Unripe tile (< 10.0 days) must produce 0 yield")

    def test_other_crops_unaffected(self):
        """Other crop types maintain their own WIP / config properties."""
        for c_name in ["wheat", "carrot", "corn"]:
            cfg = CROP_TYPES.get(c_name, {})
            self.assertTrue(cfg.get("wip", False))

    # =========================================================================
    # 4. TAX SYSTEM (WIP)
    # =========================================================================

    def test_tax_section_in_reports_marked_wip(self):
        """Tax section exists in Reports tabs and is marked WIP."""
        ui = RaportUI()
        tax_tab = next((t for t in ui.tabs if t["id"] == "tax"), None)
        self.assertIsNotNone(tax_tab, "Tax tab must exist in Reports")
        self.assertTrue(tax_tab["wip"], "Tax section must be marked as WIP")

    def test_no_tax_deductions_applied(self):
        """Zero tax deductions applied to household storage or inventory."""
        chest = Furniture("f_tax", "household_storage", 1, 1, family_id="fam_tax")
        chest.inventory["Potato"] = 20
        self.furniture_manager.furnitures.append(chest)

        # Distribute production
        self.ps.distribute_production(
            resource_name="Potato",
            amount=4,
            participating_workers={"fam_tax": 1},
            furniture_manager=self.furniture_manager,
            auto_deposit=True
        )

        # 20 + 4 = 24. Zero tax deduction taken.
        self.assertEqual(chest.inventory["Potato"], 24)

    # =========================================================================
    # 5. PERSISTENT WIP PLANNING & IN-GAME ROADMAP OVERVIEW
    # =========================================================================

    def test_all_nine_wip_items_recorded(self):
        """All 9 required postponed features are tracked in persistent planning."""
        required_wip_ids = [
            "corpse_burial",
            "household_market_mgmt",
            "market_assignment",
            "production_market_inventory",
            "different_production_types",
            "dynamic_pricing",
            "household_taxation",
            "food_categories",
            "water_market"
        ]

        all_features = get_all_planning_features()
        tracked_ids = [f["id"] for f in all_features]

        for req_id in required_wip_ids:
            self.assertIn(req_id, tracked_ids, f"Required WIP item {req_id} missing from planning registry")
            feature = next(f for f in all_features if f["id"] == req_id)
            self.assertTrue(len(feature["name"]) > 0)
            self.assertTrue(len(feature["description"]) > 0)
            self.assertIn(feature["status"], (STATUS_PLANNED, STATUS_PARTIAL, STATUS_IMPLEMENTED))

    def test_implemented_features_distinguishable_from_wip(self):
        """Player can distinguish between Implemented, Partial, and Planned WIP features."""
        implemented = get_features_by_status(STATUS_IMPLEMENTED)
        partial = get_features_by_status(STATUS_PARTIAL)
        planned = get_features_by_status(STATUS_PLANNED)

        self.assertGreater(len(implemented), 0, "Must have active implemented features tracked")
        self.assertGreater(len(partial), 0, "Taxation should be tracked as Partial WIP")
        self.assertEqual(len(planned), 8, "8 items must be in PLANNED status")

        # IDs must be disjoint
        impl_ids = {f["id"] for f in implemented}
        plan_ids = {f["id"] for f in planned}
        self.assertEqual(len(impl_ids.intersection(plan_ids)), 0)

    def test_roadmap_tab_in_reports_ui(self):
        """Planning & Roadmap tab is accessible in Reports UI."""
        ui = RaportUI()
        plan_tab = next((t for t in ui.tabs if t["id"] == "planning"), None)
        self.assertIsNotNone(plan_tab, "Roadmap tab must be present in Reports")
        self.assertTrue(plan_tab["wip"])

    def test_reports_tabs_contain_production_and_taxes(self):
        """Reports UI has Production, Taxes, and Roadmap tabs."""
        ui = RaportUI()
        tab_ids = [t["id"] for t in ui.tabs]
        self.assertIn("production", tab_ids)
        self.assertIn("tax", tab_ids)
        self.assertIn("planning", tab_ids)

    def test_production_records_survive_save_load(self):
        """Production distribution records serialize and deserialize cleanly in save_system."""
        from game.systems.save_system import serialize_game_state, save_to_slot, load_from_slot, get_slot_path
        from game.systems.day_cycle import DayCycleSystem
        from game.systems.schedule import ScheduleManager
        from game.entities.servants import ServantManager
        from game.entities.player import Player
        from game.buildings.buildings import BuildingManager

        dc = DayCycleSystem()
        sched = ScheduleManager()
        serv = ServantManager()
        player = Player(0, 0)
        bm = BuildingManager()

        # Record some production
        self.ps.record_production("fam_save_test", "Potato", 42, workplace_id="farm_save_lot", day_number=5)

        data = serialize_game_state(
            dc, {"Wood": 10}, player, self.permit_manager, bm,
            self.stockpile_manager, self.furniture_manager, self.villager_manager,
            serv, sched
        )

        self.assertIn("production_records", data)
        self.assertIn("fam_save_test", data["production_records"])
        self.assertEqual(data["production_records"]["fam_save_test"]["total_produced"]["Potato"], 42)

        # Save to slot 99
        save_to_slot(99, dc, {"Wood": 10}, player, self.permit_manager, bm,
                     self.stockpile_manager, self.furniture_manager, self.villager_manager,
                     serv, sched)

        # Clear records in singleton
        self.ps.household_records.clear()
        self.assertEqual(len(self.ps.household_records), 0)

        # Load from slot 99
        load_from_slot(99, dc, {"Wood": 0}, player, self.permit_manager, bm,
                       self.stockpile_manager, self.furniture_manager, self.villager_manager,
                       serv, sched)

        summary = self.ps.get_household_production_summary("fam_save_test")
        self.assertEqual(summary["total_produced"].get("Potato"), 42)
        self.assertIn("farm_save_lot", summary["workplaces"])

        # Clean up test save file
        slot_file = get_slot_path(99)
        if os.path.exists(slot_file):
            os.remove(slot_file)


if __name__ == "__main__":
    unittest.main()
