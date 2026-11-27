import unittest
import pygame

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.data.config import FURNITURE_TYPES, TOOL_TYPES
from game.entities.villagers import Family, Villager
from game.systems.village_life.toilet_system import ToiletSystem
from game.systems.work.builder_system import BuilderSystem
from game.systems.work.production_system import ProductionSystem
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.ui.ui_raport import RaportUI
from game.world.stockpile import StockpileManager


class TestProductionSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_catalog_contains_tools_and_builder_furniture_including_toilet(self):
        catalog = ProductionSystem.get_catalog()
        by_id = {c["id"]: c for c in catalog}

        for tool_id in TOOL_TYPES:
            self.assertIn(tool_id, by_id)
            self.assertEqual(by_id[tool_id]["artisan"], "Toolmaker")

        for furn_id in ("bed", "household_storage", "builder_workbench", "confession_box", "notice_board", "toilet"):
            self.assertIn(furn_id, by_id)
            self.assertEqual(by_id[furn_id]["artisan"], "Builder")

    def test_toilet_furniture_is_movable_and_usable_by_toilet_system(self):
        cfg = FURNITURE_TYPES["toilet"]
        self.assertTrue(cfg.get("movable", False))
        self.assertTrue(cfg.get("can_be_dropped", False))

        bm = BuildingManager()
        fm = FurnitureManager()
        t_furn = Furniture("f_toilet", "toilet", 5, 5)
        fm.furnitures.append(t_furn)

        toilets = ToiletSystem.get_completed_toilets(bm, fm)
        self.assertIn(t_furn, toilets)
        self.assertEqual(t_furn.get_center_world(32), t_furn.get_world_pos(32))

    def test_product_tab_visible_and_stepper_adjusts_quota(self):
        ui = RaportUI()
        titles = [ui.tabs[i]["title"] for i in ui.tab_display_order if not ui.tabs[i].get("hidden", False)]
        self.assertIn("Product", titles)

        bm = BuildingManager()
        fm = FurnitureManager()
        sm = StockpileManager()
        ui.is_open = True
        ui.active_tab = 10

        surface = pygame.Surface((1280, 720))
        ui.draw(surface, None, None, bm, {}, furniture_manager=fm, stockpile_manager=sm)

        inc_rect = ui.product_quota_inc_rects.get("Hoe")
        self.assertIsNotNone(inc_rect)
        res = ui._handle_product_click(inc_rect.center, bm)
        self.assertEqual(res, "product_inc_Hoe")
        self.assertEqual(ProductionSystem.get_quota(bm, "Hoe"), 1)

        dec_rect = ui.product_quota_dec_rects.get("Hoe")
        res_dec = ui._handle_product_click(dec_rect.center, bm)
        self.assertEqual(res_dec, "product_dec_Hoe")
        self.assertEqual(ProductionSystem.get_quota(bm, "Hoe"), 0)

    def test_toolmaker_crafts_quota_tool_into_chest(self):
        bm = BuildingManager()
        fm = FurnitureManager()
        sm = StockpileManager()

        ProductionSystem.set_quota(bm, "Hoe", 2)

        fam = Family(1, "Smith")
        tm = Villager(1, 0, 0, "Smith", 25, 1, "Father", family_id=1)
        tm.set_job("Toolmaker")
        tm.inventory = {"Hammer": 1, "Tongs": 1}
        fam.members.append(tm)

        chest = Furniture("f_chest1", "household_storage", 1, 1, family_id=1, permit_id=101)
        chest.inventory = {"Wood": 10, "Iron Bar": 10, "Hoe": 5}
        bench = Furniture("f_bench1", "toolmaker_workbench", 2, 1, family_id=1, permit_id=101)
        fm.furnitures.extend([chest, bench])

        # Personal tools in household chest must NOT count toward commercial production stock
        self.assertEqual(ProductionSystem.get_current_stock("Hoe", furniture_manager=fm, building_manager=bm), 0)

        # Move toolmaker next to bench and run craft ticks
        bx, by = bench.get_approach_point(tm.x, tm.y, worker_id=tm.id, tile_size=32, bm=bm)
        tm.x, tm.y = bx, by

        class DummyVM:
            families = [fam]
            def get_family_by_id(self, fid):
                return fam if fid == 1 else None
            def get_all_villagers(self):
                return [tm]

        for _ in range(60):
            ToolmakerSystem.update_worker(
                tm, 10.0, "WORK", bm, fm, DummyVM(), [tm], None, None, stockpile_manager=sm
            )
            if bench.inventory.get("Hoe", 0) >= 1:
                break

        self.assertGreaterEqual(bench.inventory.get("Hoe", 0), 1)
        self.assertEqual(chest.inventory.get("Hoe", 0), 5)

    def test_builder_crafts_quota_toilet_into_workstation(self):
        bm = BuildingManager()
        fm = FurnitureManager()
        sm = StockpileManager()

        ProductionSystem.set_quota(bm, "toilet", 1)

        fam = Family(2, "Carpenter")
        b = Villager(2, 0, 0, "Bob", 25, 1, "Father", family_id=2)
        b.set_job("Builder")
        b.inventory = {"Saw": 1, "Adze": 1}
        fam.members.append(b)

        chest = Furniture("f_chest2", "household_storage", 1, 1, family_id=2, permit_id=102)
        chest.inventory = {"Wood": 10}
        bench = Furniture("f_bench2", "builder_workbench", 2, 1, family_id=2, permit_id=102)
        fm.furnitures.extend([chest, bench])

        bx, by = bench.get_approach_point(b.x, b.y, worker_id=b.id, tile_size=32, bm=bm)
        b.x, b.y = bx, by

        class DummyVM:
            families = [fam]
            def get_family_by_id(self, fid):
                return fam if fid == 2 else None
            def get_all_villagers(self):
                return [b]

        for _ in range(40):
            BuilderSystem.update_worker(
                b, 10.0, "WORK", bm, fm, DummyVM(), [b], None, None, stockpile_manager=sm
            )
            if bench.inventory.get("toilet", 0) >= 1:
                break

        self.assertEqual(bench.inventory.get("toilet", 0), 1)
        self.assertEqual(chest.inventory.get("Wood", 0), 5)

    def test_villager_update_keeps_builder_and_toolmaker_in_work_when_quota_active(self):
        from game.systems.work.schedule import ScheduleManager
        bm = BuildingManager()
        fm = FurnitureManager()
        sm = StockpileManager()

        ProductionSystem.set_quota(bm, "toilet", 1)
        ProductionSystem.set_quota(bm, "Hoe", 1)

        fam = Family(3, "Artisans")
        b = Villager(3, 0, 0, "Bob", 25, 1, "Father", family_id=3)
        b.set_job("Builder")
        b.inventory = {"Saw": 1, "Adze": 1}

        tm = Villager(4, 0, 0, "Tim", 25, 1, "Father", family_id=3)
        tm.set_job("Toolmaker")
        tm.inventory = {"Hammer": 1, "Tongs": 1}
        fam.members.extend([b, tm])

        chest = Furniture("f_chest3", "household_storage", 1, 1, family_id=3, permit_id=103)
        chest.inventory = {"Wood": 20, "Stone": 10, "Iron Bar": 10}
        b_bench = Furniture("f_b3", "builder_workbench", 2, 1, family_id=3, permit_id=103)
        t_bench = Furniture("f_t3", "toolmaker_workbench", 4, 1, family_id=3, permit_id=103)
        fm.furnitures.extend([chest, b_bench, t_bench])

        b.x, b.y = b_bench.get_approach_point(b.x, b.y, worker_id=b.id, tile_size=32, bm=bm)
        tm.x, tm.y = t_bench.get_approach_point(tm.x, tm.y, worker_id=tm.id, tile_size=32, bm=bm)

        class DummyDayCycle:
            current_hour = 9.0
            day_number = 1
            day_length_seconds = 1500.0
            def get_time_of_day(self):
                return 9.0

        class DummyVM:
            families = [fam]
            def get_family_by_id(self, fid):
                return fam if fid == 3 else None
            def get_all_villagers(self):
                return [b, tm]

        sched = ScheduleManager()
        dc = DummyDayCycle()
        vm = DummyVM()

        for _ in range(60):
            b.update(
                10.0,
                day_cycle=dc,
                permit_manager=None,
                building_manager=bm,
                stockpile_manager=sm,
                all_entities=[],
                player=None,
                villager_manager=vm,
                furniture_manager=fm,
                schedule_manager=sched,
            )
            tm.update(
                10.0,
                day_cycle=dc,
                permit_manager=None,
                building_manager=bm,
                stockpile_manager=sm,
                all_entities=[],
                player=None,
                villager_manager=vm,
                furniture_manager=fm,
                schedule_manager=sched,
            )

        self.assertEqual(b_bench.inventory.get("toilet", 0), 1)
        self.assertEqual(t_bench.inventory.get("Hoe", 0), 1)

    def test_market_remove_and_readd_workstation_roundtrip(self):
        from game.systems.economy.household_stall_system import HouseholdStallSystem

        bm = BuildingManager()
        fm = FurnitureManager()
        sm = StockpileManager()

        fam = Family(4, "Artisans")
        chest = Furniture("f_chest4", "household_storage", 1, 1, family_id=4, permit_id=104)
        b_bench = Furniture("f_b4", "builder_workbench", 2, 1, family_id=4, permit_id=104)
        t_bench = Furniture("f_t4", "toolmaker_workbench", 4, 1, family_id=4, permit_id=104)
        fm.furnitures.extend([chest, b_bench, t_bench])

        market = Building("market", {(6, 6)})
        bm.buildings.append(market)
        HouseholdStallSystem.assign_stall(market, 4)

        # Put 1 Hoe and 1 toilet in market as if hauled from workstations
        market.sale_items = ["Hoe", "toilet"]
        market.inventory = {"Hoe": 1, "toilet": 1}

        # Remove from market -> must return directly to workstations, NOT household chest
        self.assertTrue(HouseholdStallSystem.remove_sale_item(market, "Hoe", fm, sm))
        self.assertTrue(HouseholdStallSystem.remove_sale_item(market, "toilet", fm, sm))

        self.assertEqual(t_bench.inventory.get("Hoe", 0), 1)
        self.assertEqual(b_bench.inventory.get("toilet", 0), 1)
        self.assertEqual(chest.inventory.get("Hoe", 0), 0)
        self.assertEqual(chest.inventory.get("toilet", 0), 0)

        # Re-add / auto-list back to market must work seamlessly ("keluar masuk")
        added = HouseholdStallSystem.auto_list_surplus_items(market, fm)
        self.assertIn("Hoe", added)
        self.assertIn("toilet", added)
        self.assertIn("Hoe", market.sale_items)
        self.assertIn("toilet", market.sale_items)


if __name__ == "__main__":
    unittest.main()
