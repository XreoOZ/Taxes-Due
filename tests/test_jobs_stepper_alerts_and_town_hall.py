"""
Tests for:
1. Top-to-bottom job staffing via set_job_worker_count and [- input +] stepper in Jobs tab.
2. Adjustable workstation max cap (lowerable e.g. 0/2 -> 0/1, clamped at hardware limit e.g. cannot become 0/3).
3. Village alerts collection (homeless, 0 coins, no food, missing tools, unemployed, broken structure).
4. Right-side VillageAlertsHUD rendering, collapsing, and click routing.
5. RaportUI Town Hall Overview tab rendering & click actions while preserving tab indices 0..8.
"""

import os
import unittest
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

pygame.init()
pygame.display.set_mode((1280, 720))

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.entities.villagers import Family, Villager, VillagerManager
from game.furniture import Furniture, FurnitureManager
from game.systems.village_life.village_alerts import collect_village_alerts
from game.systems.work.workplace_system import (
    auto_sort_all_workers,
    set_job_worker_count,
    set_workplace_max_workers,
    workplace_base_capacity,
    workplace_capacity,
)
from game.ui.ui_raport import RaportUI
from game.ui.village_alerts_hud import VillageAlertsHUD
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager


class TestJobsStepperAlertsAndTownHall(unittest.TestCase):
    def setUp(self):
        self.pm = PermitManager()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.sm = StockpileManager()
        self.resources = {"Wood": 100, "Stone": 100, "Potato": 20}

        # Create 1 family with 6 living adult villagers (all Unassigned initially)
        self.fam = Family("fam_1", "Miller")
        for i in range(6):
            v = Villager(f"v_{i}", f"Worker{i}", "Miller", "male", 25, 1, "father", "fam_1")
            v.job = "Unassigned"
            self.fam.members.append(v)
        self.vm.families.append(self.fam)

    def test_top_to_bottom_farm_fill_and_bottom_up_removal(self):
        """Assigning workers fills topmost farm plot first, and unassigns bottommost first."""
        f1 = self.pm.add_permit("Farm Plot 1", "farm", {(1, 1), (2, 1), (1, 2), (2, 2)})
        f2 = self.pm.add_permit("Farm Plot 2", "farm", {(5, 1), (6, 1), (5, 2), (6, 2)})
        f3 = self.pm.add_permit("Farm Plot 3", "farm", {(9, 1), (10, 1), (9, 2), (10, 2)})
        for p in (f1, f2, f3):
            p.max_workers = 2

        # Set 3 Farmers -> Plot 1 gets 2/2, Plot 2 gets 1/2, Plot 3 gets 0/2
        filled = set_job_worker_count("Farmer", 3, self.pm, self.fm, self.vm, self.bm)
        self.assertEqual(filled, 3)
        self.assertEqual(len(f1.assigned_workers), 2)
        self.assertEqual(len(f2.assigned_workers), 1)
        self.assertEqual(len(f3.assigned_workers), 0)

        # Requesting 99 clamps to combined cap 6 -> 2/2, 2/2, 2/2
        filled = set_job_worker_count("Farmer", 99, self.pm, self.fm, self.vm, self.bm)
        self.assertEqual(filled, 6)
        self.assertEqual((len(f1.assigned_workers), len(f2.assigned_workers), len(f3.assigned_workers)), (2, 2, 2))

        # Reducing down to 2 removes bottom-up so Plot 1 stays full (2, 0, 0)
        filled = set_job_worker_count("Farmer", 2, self.pm, self.fm, self.vm, self.bm)
        self.assertEqual(filled, 2)
        self.assertEqual((len(f1.assigned_workers), len(f2.assigned_workers), len(f3.assigned_workers)), (2, 0, 0))

    def test_hardware_capped_workstation_can_lower_max_but_not_exceed(self):
        """Builder Workbench (base cap 2) can be lowered to 1, never raised to 3, and Auto Sort respects it."""
        self.pm.add_permit("Builder Lot", "housing", {(20, 20), (21, 20), (20, 21), (21, 21)})
        self.fm.add_furniture("builder_workbench", 20, 20, self.pm, self.vm, self.resources, building_manager=self.bm)
        wb = self.fm.furnitures[-1]
        wb.construction_order = None
        wb.assigned_workers = []

        wp = ("furniture", wb)
        self.assertEqual(workplace_base_capacity(wp), 2)
        self.assertEqual(workplace_capacity(wp), 2)

        # Trying to raise to 3 clamps to 2
        res_hi = set_workplace_max_workers("Builder", wp, 3, self.pm, self.fm, self.vm)
        self.assertEqual(res_hi, 2)
        self.assertEqual(workplace_capacity(wp), 2)

        # Lowering to 1 succeeds (0/2 -> 0/1)
        res_lo = set_workplace_max_workers("Builder", wp, 1, self.pm, self.fm, self.vm)
        self.assertEqual(res_lo, 1)
        self.assertEqual(workplace_capacity(wp), 1)

        # Auto Sort respects lowered max = 1
        auto_sort_all_workers(self.pm, self.fm, self.vm, building_manager=self.bm)
        self.assertEqual(len(wb.assigned_workers), 1)

    def test_jobs_tab_stepper_render_and_click(self):
        """Jobs directory renders [- num +] next to View Workers and responds to clicks."""
        f1 = self.pm.add_permit("Farm Plot 1", "farm", {(1, 1), (2, 1), (1, 2), (2, 2)})
        f1.max_workers = 2

        ui = RaportUI()
        ui.is_open = True
        ui.active_tab = 5  # Jobs tab

        surf = pygame.Surface((1280, 720))
        ui.draw(surf, self.bm, self.pm, self.resources, villager_manager=self.vm, furniture_manager=self.fm, stockpile_manager=self.sm)

        # Stepper controls & typable num field registered
        self.assertIn(("num", "job_workers", "Farmer"), ui.num_fields)
        self.assertIn(("Farmer", 1), ui.job_worker_step_rects)
        self.assertEqual(ui.num_fields[("num", "job_workers", "Farmer")]["max"], 2)

        # Click '+' on Farmer row
        plus_rect = ui.job_worker_step_rects[("Farmer", 1)]
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": plus_rect.center})
        res = ui.handle_event(ev, self.bm, self.pm, self.resources, villager_manager=self.vm, furniture_manager=self.fm, stockpile_manager=self.sm)
        self.assertEqual(res, "job_worker_step_Farmer_1")
        self.assertEqual(len(f1.assigned_workers), 1)

    def test_village_alerts_hud_and_town_hall_tab(self):
        """VillageAlertsHUD and Town Hall detect homeless, 0 coins, no food, missing tools, and unemployed."""
        # Make one villager a Farmer without Hoe/Sickle/Watering_Can so tools alert triggers too
        self.fam.members[0].job = "Farmer"
        toilet = Building("toilet", {(12, 12)})
        toilet.condition = 0.0
        self.bm.buildings.append(toilet)

        alerts = collect_village_alerts(
            villager_manager=self.vm,
            permit_manager=self.pm,
            building_manager=self.bm,
            furniture_manager=self.fm,
            stockpile_manager=self.sm,
        )
        cats = {a["category"] for a in alerts}
        self.assertIn("housing", cats)
        self.assertIn("currency", cats)
        self.assertIn("food", cats)
        self.assertIn("water", cats)
        self.assertIn("tools", cats)
        self.assertIn("jobs", cats)
        self.assertIn("repair", cats)

        # Right-side HUD renders and toggles collapse
        hud = VillageAlertsHUD()
        hud.refresh(self.vm, self.pm, self.bm, self.fm, self.sm)
        surf = pygame.Surface((1280, 720))
        hud.draw(surf, right_x=1264, top_y=220)
        self.assertGreater(len(hud.alert_row_rects), 0)

        ev_collapse = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": hud.toggle_btn_rect.center})
        res = hud.handle_event(ev_collapse)
        self.assertEqual(res, {"action": "TOGGLE_COLLAPSE"})
        self.assertTrue(hud.collapsed)

        # RaportUI opens on Town Hall (tab 9) by default and routes alert clicks
        ui = RaportUI()
        self.assertEqual(ui.active_tab, 9)
        ui.is_open = True
        ui.draw(surf, self.bm, self.pm, self.resources, villager_manager=self.vm, furniture_manager=self.fm, stockpile_manager=self.sm)
        self.assertGreater(len(ui.town_hall_action_btns), 0)

        # Routing grant alert opens Household Possession + Grant dialog directly
        act_res = ui.execute_alert_action("OPEN_GRANT", self.fam.id)
        self.assertEqual(act_res, f"alert_open_grant_{self.fam.id}")
        self.assertEqual(ui.active_tab, 4)
        self.assertTrue(ui.show_grant_dialog)

    def test_grouped_notice_board_and_town_hall_category_filter_and_culling(self):
        """Notice Board collapses large alert counts into category summaries; clicking opens filtered Town Hall."""
        # Create 40 broken fixtures + 40 struggling families
        for i in range(40):
            f_broken = Furniture(f"b_fix_{i}", "bed", 2 + i, 2, permit_id=None, family_id=None)
            f_broken.condition = 0.0
            self.fm.furnitures.append(f_broken)
            fam = Family(f"fam_need_{i}", f"Need{i}")
            v = Villager(f"v_need_{i}", "A", f"Need{i}", "Male", 25, 2, "Father", f"fam_need_{i}")
            fam.members = [v]
            self.vm.families.append(fam)

        hud = VillageAlertsHUD()
        hud.refresh(self.vm, self.pm, self.bm, self.fm, self.sm)
        surf = pygame.Surface((1280, 720))
        hud.draw(surf, right_x=1264, top_y=220)

        titles = [a["title"] for _, a in hud.alert_row_rects]
        self.assertLessEqual(len(hud.alert_row_rects), hud.max_visible)
        self.assertTrue(any(t.startswith("Needs Repair: ") for t in titles), titles)
        self.assertTrue(any(t.startswith("Households in Need: ") for t in titles), titles)

        # Click "Needs Repair: ..." row -> routes to Town Hall filtered to "repair"
        repair_rect, _ = next((r, a) for r, a in hud.alert_row_rects if a.get("group") == "repair")
        click_res = hud.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": repair_rect.center}))
        self.assertEqual(click_res["action"], "OPEN_TOWN_HALL")
        self.assertEqual(click_res["target_id"], "repair")

        ui = RaportUI()
        ui.execute_alert_action(click_res["action"], click_res["target_id"])
        self.assertEqual(ui.active_tab, 9)
        self.assertEqual(ui.town_hall_filter, "repair")
        ui.draw(surf, self.bm, self.pm, self.resources, villager_manager=self.vm, furniture_manager=self.fm, stockpile_manager=self.sm)
        # Viewport culling must only create buttons for visible rows, not all 40+
        self.assertLess(len(ui.town_hall_action_btns), 15)
        self.assertTrue(all(a["category"] == "repair" for _, a in ui.town_hall_action_btns))

        # Clicking "Households (...)" chip switches filter to household_need
        hh_chip = ui.town_hall_filter_rects["household_need"]
        ui.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": hh_chip.center}),
            self.bm, self.pm, self.resources, villager_manager=self.vm, furniture_manager=self.fm, stockpile_manager=self.sm,
        )
        self.assertEqual(ui.town_hall_filter, "household_need")


if __name__ == "__main__":
    unittest.main()
