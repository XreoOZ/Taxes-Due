import unittest
import pygame
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import (
    TILE_SIZE,
    BUILDING_TYPES,
    FURNITURE_TYPES,
    PERMIT_TYPES,
    DEDICATED_JOBS,
    ITEM_CATEGORIES,
    MARKET_TRADEABLE_ITEMS,
    SCHEDULE_PRAYER,
    SCHEDULE_WORK,
    get_building_categories,
)
from game.buildings.buildings import BuildingManager, Building
from game.buildings.furniture import FurnitureManager
from game.world.permits import PermitManager, AreaPermit
from game.entities.villagers import VillagerManager, Villager, Family
from game.systems.schedule import ScheduleManager
from game.ui.ui_raport import RaportUI
from game.ui.market_modal import MarketProfileModal
from game.systems.market_service import MarketService
from game.systems.currency import to_copper, from_copper


class TestAgent1BuildingJobsScheduleMarketUI(unittest.TestCase):
    def setUp(self):
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = ScheduleManager()
        self.resources = {"Wood": 100, "Stone": 100}

    # -------------------------------------------------------------------------
    # 1. BUILDING MENU RESTRUCTURE
    # -------------------------------------------------------------------------
    def test_01_building_menu_category_hierarchy_and_structure_grouping(self):
        """1. Building -> Structure -> [Wooden Structure, Stone Structure] and Furniture alongside."""
        cats = get_building_categories()
        cat_ids = [c["id"] for c in cats]

        self.assertIn("structure", cat_ids)
        self.assertIn("public_structure", cat_ids)
        self.assertIn("furniture", cat_ids)

        struct_cat = next(c for c in cats if c["id"] == "structure")
        self.assertEqual(struct_cat["name"], "Structure")
        self.assertIn("wooden_structure", struct_cat["building_types"])
        self.assertIn("stone_structure", struct_cat["building_types"])

        public_cat = next(c for c in cats if c["id"] == "public_structure")
        self.assertIn("well", public_cat["building_types"])
        self.assertIn("market", public_cat["building_types"])
        self.assertIn("toilet", public_cat["building_types"])

        furn_cat = next(c for c in cats if c["id"] == "furniture")
        self.assertEqual(furn_cat["name"], "Furniture")
        self.assertIn("household_storage", furn_cat["building_types"])
        self.assertIn("bed", furn_cat["building_types"])

    def test_02_building_tab_screens_render_cleanly(self):
        """2. Screen 1 renders categories; clicking Structure opens blueprints for Wooden & Stone Structure."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 0
        ui.selected_building_category = None

        surf = pygame.Surface((1280, 720))
        ui._draw_building_tab(surf, 210, 110, self.bm, self.pm, self.resources, furniture_manager=self.fm, villager_manager=self.vm)

        # Screen 1 must show Structure and Furniture, not individual building blueprints directly
        self.assertIn("structure", ui.building_category_btn_rects)
        self.assertIn("public_structure", ui.building_category_btn_rects)
        self.assertIn("furniture", ui.building_category_btn_rects)
        self.assertEqual(len(ui.building_select_rects), 0)

        # Click on Structure category card
        struct_rect = ui.building_category_btn_rects["structure"]
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": struct_rect.center})
        act = ui.handle_event(ev, self.bm, self.pm, self.resources)
        self.assertEqual(act, "select_building_category_structure")
        self.assertEqual(ui.selected_building_category, "structure")

        # Screen 2 now renders blueprints for Wooden Structure and Stone Structure
        ui._draw_building_tab(surf, 210, 110, self.bm, self.pm, self.resources, furniture_manager=self.fm, villager_manager=self.vm)
        self.assertIsNotNone(ui.building_category_back_btn_rect)
        self.assertIn("wooden_structure", ui.building_select_rects)
        self.assertIn("stone_structure", ui.building_select_rects)

    # -------------------------------------------------------------------------
    # 2. PERMIT UI: CHURCH & CEMETERY PERMITS
    # -------------------------------------------------------------------------
    def test_03_church_and_cemetery_permits_properties_and_building_rules(self):
        """3. Church & Cemetery are permits, not buildings. Cemetery forbids buildings; Church allows structures."""
        self.assertIn("church", PERMIT_TYPES)
        self.assertIn("cemetery", PERMIT_TYPES)

        # Cemetery permit is placed and expanded via tiles
        cem_tiles = {(10, 10), (10, 11), (11, 10), (11, 11)}
        cem_permit = self.pm.add_permit("Village Cemetery", "cemetery", cem_tiles)
        self.assertIsNotNone(cem_permit)
        self.assertEqual(cem_permit.permit_type, "cemetery")

        # Buildings are strictly forbidden on cemetery tiles
        match, err = self.pm.find_matching_permit_for_tiles("wooden_structure", {(10, 10)}, self.bm)
        self.assertIsNone(match)
        self.assertIn("Cemetery", err)

        # Church permit allows Wooden Structure or Stone Structure
        church_tiles = {(20, 20), (20, 21), (21, 20), (21, 21)}
        church_permit = self.pm.add_permit("Village Church", "church", church_tiles)
        self.assertIsNotNone(church_permit)
        match_church, err_church = self.pm.find_matching_permit_for_tiles("wooden_structure", {(20, 20)}, self.bm)
        self.assertIsNotNone(match_church)
        self.assertEqual(match_church.id, church_permit.id)

    # -------------------------------------------------------------------------
    # 3. JOB ASSIGNMENT SYSTEM — REMOVE PREDETERMINED JOBS
    # -------------------------------------------------------------------------
    def test_04_ai_individuals_start_unassigned_and_change_jobs_dynamically(self):
        """4. Every AI starts with job Unassigned; assigned job updates title, tools, and replaces previous job."""
        v = Villager("vil_new", "Rowan", "Smith", "Male", 26, 2, "Father", "fam_smith")
        self.assertEqual(v.job, "Unassigned")
        self.assertEqual(v.title, "Unassigned")

        # Assign Farmer
        v.set_job("Farmer")
        self.assertEqual(v.job, "Farmer")
        self.assertEqual(v.profession, "Farmer")
        self.assertEqual(v.title, "Farmer")

        # Assign Builder (replaces Farmer, single active job)
        v.set_job("Builder")
        self.assertEqual(v.job, "Builder")
        self.assertEqual(v.title, "Builder")

        # Assign Priest
        v.set_job("Priest")
        self.assertEqual(v.job, "Priest")
        self.assertEqual(v.title, "Priest")

        # Assign Gravedigger
        v.set_job("Gravedigger")
        self.assertEqual(v.job, "Gravedigger")
        self.assertEqual(v.title, "Gravedigger")

    # -------------------------------------------------------------------------
    # 4. WORKER ASSIGNMENT UI — REUSABLE SYSTEM
    # -------------------------------------------------------------------------
    def test_05_reusable_worker_assignment_for_priest_gravedigger_farmer(self):
        """5. Priest and Gravedigger use reusable [- num +] worker assignment selecting closest Unassigned AI."""
        fam = Family("fam_1", "Carter")
        v1 = Villager("v1", "John", "Carter", "Male", 30, 2, "Father", "fam_1", x=100.0, y=100.0)
        v2 = Villager("v2", "Mary", "Carter", "Female", 28, 2, "Mother", "fam_1", x=120.0, y=120.0)
        fam.members = [v1, v2]
        self.vm.families = [fam]

        # Both start Unassigned
        self.assertEqual(v1.job, "Unassigned")
        self.assertEqual(v2.job, "Unassigned")

        # Setup Church permit (initially 0 workers)
        church = self.pm.add_permit("Church", "church", {(10, 10), (10, 11)})
        church.max_workers = 0
        church.assigned_workers = []

        # Click [+] on Church worker control: increases count & assigns closest unassigned member (v2 at 120, 120 is closer to permit at 320, 320)
        self.pm.change_max_workers(church.id, +1, villager_manager=self.vm)
        self.assertEqual(church.max_workers, 1)
        self.assertEqual(len(church.assigned_workers), 1)
        assigned_priest_id = church.assigned_workers[0]
        assigned_priest = next(v for v in (v1, v2) if v.id == assigned_priest_id)
        self.assertEqual(assigned_priest.job, "Priest")
        self.assertEqual(assigned_priest.title, "Priest")

        # Click [-] on Church worker control: releases worker back to Unassigned
        self.pm.change_max_workers(church.id, -1, villager_manager=self.vm)
        self.assertEqual(church.max_workers, 0)
        self.assertEqual(len(church.assigned_workers), 0)
        self.assertEqual(assigned_priest.job, "Unassigned")

        # Setup Cemetery permit
        cem = self.pm.add_permit("Cemetery", "cemetery", {(30, 30), (30, 31)})
        cem.max_workers = 0
        cem.assigned_workers = []

        # Click [+] on Cemetery worker control: assigns closest unassigned member
        self.pm.change_max_workers(cem.id, +1, villager_manager=self.vm)
        self.assertEqual(cem.max_workers, 1)
        self.assertEqual(len(cem.assigned_workers), 1)
        assigned_gd_id = cem.assigned_workers[0]
        assigned_gd = next(v for v in (v1, v2) if v.id == assigned_gd_id)
        self.assertEqual(assigned_gd.job, "Gravedigger")
        self.assertEqual(assigned_gd.title, "Gravedigger")

    # -------------------------------------------------------------------------
    # 5. SCHEDULE UI
    # -------------------------------------------------------------------------
    def test_06_schedule_no_weekdays_and_priest_prayer_block(self):
        """6. Monday-Sunday removed from Schedule UI. 24-hour job timeline with contiguous Priest prayer block."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 3  # Schedule tab
        ui.selected_schedule_job_id = "Farmer"

        surf = pygame.Surface((1280, 720))
        ui._draw_schedule_tab(surf, 210, 110, schedule_manager=self.sm)

        # No weekday selector buttons on schedule UI
        self.assertFalse(hasattr(ui, "schedule_day_btn_rects") and len(ui.schedule_day_btn_rects) > 0)

        # 24 hour cells present
        self.assertEqual(len(ui.schedule_hour_cell_rects), 24)

        # Priest prayer time decree automatically applies
        self.sm.set_prayer_time(11, 13)
        self.assertEqual(self.sm.get_current_activity("Farmer", 11.5), SCHEDULE_PRAYER)
        self.assertEqual(self.sm.get_current_activity("Priest", 11.5), SCHEDULE_PRAYER)
        self.assertNotEqual(self.sm.get_current_activity("Farmer", 14.0), SCHEDULE_PRAYER)

    # -------------------------------------------------------------------------
    # 6. MARKET UI
    # -------------------------------------------------------------------------
    def test_07_market_ui_all_registered_items_and_separate_pricing(self):
        """7. All registered tradeable items available with pagination, denomination pricing, and buy/sell separation."""
        class FakeMarket:
            def __init__(self):
                self.building_type = "market"
                self.inventory = {"Potato": 25, "Bread": 10, "Wood": 40}
                self.prices = {"Potato": 12, "Bread": 25}
                self.buying_prices = {"Potato": 6, "Bread": 12}
                self.currency = {"Copper": 50, "Silver": 2, "Gold": 0}

        market = FakeMarket()
        modal = MarketProfileModal()
        modal.open(market)
        self.assertTrue(modal.is_open)

        surf = pygame.Surface((1280, 720))
        modal.draw(surf)

        # All configured market-tradeable items are offered by the modal
        self.assertGreaterEqual(len(modal.tradeable_items), len(MARKET_TRADEABLE_ITEMS))
        self.assertIn("Potato", modal.tradeable_items)
        self.assertIn("Wood", modal.tradeable_items)
        self.assertIn("Hoe", modal.tradeable_items)

        # Separate selling price and buying price
        sell_p = MarketService.get_item_price("Potato", market)
        buy_p = MarketService.get_buying_price("Potato", market)
        self.assertEqual(sell_p, 12)
        self.assertEqual(buy_p, 6)

        # Price adjustment in coin denominations (Gold +100, Silver +10, Copper +1)
        modal.price_s_inc_btns["Potato"] = pygame.Rect(100, 100, 16, 16)
        ev_inc = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (105, 105)})
        modal.handle_event(ev_inc)
        self.assertEqual(market.prices["Potato"], 22)

    def test_08_activity_description_reflects_actual_current_behavior(self):
        """8. Activity description accurately reflects actual current AI behavior."""
        v = Villager("vil_act", "Edmund", "Miller", "Male", 25, 2, "Father", "fam_m")
        v.is_alive = True
        v.is_moving = False
        v.task = "IDLE"
        self.assertEqual(v.activity, "Idling leisurely")

        v.task = "SEEKING_FOOD"
        v.purchase_target_market_id = "market_1"
        self.assertEqual(v.activity, "Walking to Market to purchase Food")

        v.task = "FETCHING_WATER"
        v.is_moving = True
        self.assertEqual(v.activity, "Walking to Water Well")
        v.is_moving = False
        self.assertEqual(v.activity, "Drawing Water from Well")


if __name__ == "__main__":
    unittest.main()
