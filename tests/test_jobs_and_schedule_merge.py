import unittest
import os
import pygame
from game.data.config import (
    DEDICATED_JOBS,
    DEFAULT_RESOURCES,
    DEFAULT_JOB_SCHEDULE,
    RAPORT_MODAL_WIDTH,
    RAPORT_MODAL_HEIGHT
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.world.permits import PermitManager, AreaPermit
from game.buildings.buildings import BuildingManager
from game.systems.schedule import ScheduleManager
from game.ui.ui_raport import RaportUI
from game.systems.save_system import save_to_slot, load_from_slot, get_slot_path


class TestJobsAndScheduleMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.surface = pygame.Surface((1280, 720))
        self.permit_manager = PermitManager()
        self.building_manager = BuildingManager()
        self.villager_manager = VillagerManager()
        self.schedule_manager = ScheduleManager()
        self.resources = dict(DEFAULT_RESOURCES)

        # Set up a test family with a farmer and builder
        self.family = Family(1, "Brewer")
        v1 = Villager(1, "Hugh", "Brewer", "male", 34, 2, "Father", 1)
        v1.job = "Farmer"
        v2 = Villager(2, "Agnes", "Brewer", "female", 32, 2, "Mother", 1)
        v2.job = "Farmer"
        v3 = Villager(3, "Bob", "Brewer", "male", 18, 2, "Son", 1)
        v3.job = "Builder"
        self.family.members.extend([v1, v2, v3])
        self.villager_manager.families.append(self.family)

        # Farm lot
        self.farm_lot = AreaPermit(8, "Farm Lot #8", "farm", 10, 10, 8, 8)
        self.farm_lot.assigned_workers.append(v1.id)
        self.permit_manager.permits.append(self.farm_lot)

        self.ui = RaportUI()
        self.ui.is_open = True

    def _render_ui(self):
        self.ui.draw(
            self.surface,
            self.building_manager,
            self.permit_manager,
            self.resources,
            villager_manager=self.villager_manager,
            schedule_manager=self.schedule_manager
        )

    def test_01_main_menu_displays_jobs_not_workers_and_schedule_hidden(self):
        """1. Main menu displays 'Jobs', not 'Workers', and standalone Schedule is removed."""
        visible_tabs = [t for t in self.ui.tabs if not t.get("hidden", False)]
        visible_titles = [t["title"] for t in visible_tabs]

        self.assertIn("Jobs", visible_titles, "Visible menu tabs must contain 'Jobs'")
        self.assertNotIn("Workers", visible_titles, "Visible menu tabs must NOT contain 'Workers'")
        self.assertNotIn("Schedule", visible_titles, "Standalone 'Schedule' tab must NOT be in visible header tabs")

        # Render UI to verify tab rects
        self._render_ui()
        # Find rect for Jobs tab (index 5)
        jobs_tab_idx = next(i for i, t in enumerate(self.ui.tabs) if t.get("title") == "Jobs")
        self.assertEqual(jobs_tab_idx, 5)
        jobs_rect = self.ui.tab_rects[jobs_tab_idx]
        self.assertGreater(jobs_rect.width, 0, "Jobs tab must have a visible interactive rect on screen")

        # Hidden schedule tab must have dummy or off-screen rect
        sched_tab_idx = next(i for i, t in enumerate(self.ui.tabs) if t.get("id") == "schedule")
        sched_rect = self.ui.tab_rects[sched_tab_idx]
        self.assertEqual(sched_rect.x, -9999, "Hidden schedule tab must NOT be on screen")

    def test_02_clicking_jobs_displays_available_job_categories_dynamically(self):
        """2. Clicking Jobs tab displays available job categories dynamically from DEDICATED_JOBS."""
        self._render_ui()
        jobs_tab_idx = next(i for i, t in enumerate(self.ui.tabs) if t.get("title") == "Jobs")
        jobs_rect = self.ui.tab_rects[jobs_tab_idx]

        # Click Jobs tab
        click_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": jobs_rect.center, "button": 1})
        res = self.ui.handle_event(click_event, self.building_manager, self.permit_manager, self.resources,
                                    villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(self.ui.active_tab, jobs_tab_idx)
        self.assertIsNone(self.ui.selected_job_id)
        self.assertIsNone(self.ui.selected_schedule_job_id)

        self._render_ui()

        # Both Farmer and Builder are active jobs
        self.assertIn("Farmer", self.ui.job_select_btn_rects)
        self.assertIn("Builder", self.ui.job_select_btn_rects)

    def test_03_each_job_category_provides_view_workers_and_edit_schedule_actions(self):
        """3. Each active job category card provides two actions: [View Workers] and [Edit Schedule]."""
        self.ui.active_tab = 5
        self._render_ui()

        for job_id, job_cfg in DEDICATED_JOBS.items():
            if not job_cfg.get("wip", False):
                self.assertIn(job_id, self.ui.job_select_btn_rects, f"{job_id} must have a [View Workers] button")
                self.assertIn(job_id, self.ui.job_schedule_btn_rects, f"{job_id} must have an [Edit Schedule] button")

                vw_rect = self.ui.job_select_btn_rects[job_id]
                es_rect = self.ui.job_schedule_btn_rects[job_id]
                self.assertGreater(vw_rect.width, 50)
                self.assertGreater(es_rect.width, 50)
                # Buttons must not overlap
                self.assertFalse(vw_rect.colliderect(es_rect), f"Buttons for {job_id} must not overlap")

    def test_04_view_workers_opens_existing_worker_management_filtered_to_selected_job(self):
        """4. Clicking [View Workers] filters to the chosen job, displays assigned workers, and has Back button."""
        self.ui.active_tab = 5
        self._render_ui()

        vw_rect = self.ui.job_select_btn_rects["Farmer"]
        click_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": vw_rect.center, "button": 1})
        res = self.ui.handle_event(click_event, self.building_manager, self.permit_manager, self.resources,
                                    villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)

        self.assertEqual(self.ui.selected_job_id, "Farmer")
        self.assertIsNone(self.ui.selected_schedule_job_id)

        # Render Worker Roster view
        self._render_ui()
        self.assertIsNotNone(self.ui.back_to_jobs_btn_rect)

        # Click Back to Jobs button
        back_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": self.ui.back_to_jobs_btn_rect.center, "button": 1})
        back_res = self.ui.handle_event(back_event, self.building_manager, self.permit_manager, self.resources,
                                         villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(back_res, "back_to_jobs")
        self.assertIsNone(self.ui.selected_job_id, "Should return cleanly to Jobs directory")

    def test_05_edit_schedule_opens_existing_schedule_matrix_for_selected_job(self):
        """5. Clicking [Edit Schedule] opens the existing Schedule interface for the clicked job."""
        self.ui.active_tab = 5
        self._render_ui()

        es_rect = self.ui.job_schedule_btn_rects["Farmer"]
        click_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": es_rect.center, "button": 1})
        res = self.ui.handle_event(click_event, self.building_manager, self.permit_manager, self.resources,
                                    villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)

        self.assertEqual(res, "edit_schedule_Farmer")
        self.assertEqual(self.ui.selected_schedule_job_id, "Farmer")

        # Render Schedule view within Jobs tab
        self._render_ui()
        self.assertIsNotNone(self.ui.schedule_back_btn_rect)
        self.assertGreater(len(self.ui.schedule_hour_cell_rects), 0, "24-hour timetable slots must be rendered")
        self.assertIn("SLEEP", self.ui.schedule_brush_btn_rects)
        self.assertIn("WORK", self.ui.schedule_brush_btn_rects)

        # Click Back to Jobs button in Schedule view
        back_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": self.ui.schedule_back_btn_rect.center, "button": 1})
        back_res = self.ui.handle_event(back_event, self.building_manager, self.permit_manager, self.resources,
                                         villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(back_res, "back_to_jobs")
        self.assertIsNone(self.ui.selected_schedule_job_id, "Should return cleanly to Jobs directory")

    def test_06_schedule_editing_and_saving_still_work(self):
        """6. Painting hours and applying presets in Schedule view modifies ScheduleManager."""
        self.ui.active_tab = 5
        self.ui.selected_schedule_job_id = "Farmer"
        self._render_ui()

        # Select LEISURE brush
        leisure_rect = self.ui.schedule_brush_btn_rects["LEISURE"]
        click_brush = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": leisure_rect.center, "button": 1})
        self.ui.handle_event(click_brush, self.building_manager, self.permit_manager, self.resources,
                             villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(self.ui.selected_schedule_brush, "LEISURE")

        # Paint hour 12
        h12_rect = self.ui.schedule_hour_cell_rects[12]
        click_h12 = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": h12_rect.center, "button": 1})
        paint_res = self.ui.handle_event(click_h12, self.building_manager, self.permit_manager, self.resources,
                                         villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(paint_res, "paint_hour_12_LEISURE")
        self.assertEqual(self.schedule_manager.get_current_activity("Farmer", 12.0), "LEISURE")

        # Apply Hard Work preset
        hw_rect = self.ui.schedule_preset_btn_rects["hardwork"]
        click_hw = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": hw_rect.center, "button": 1})
        self.ui.handle_event(click_hw, self.building_manager, self.permit_manager, self.resources,
                             villager_manager=self.villager_manager, schedule_manager=self.schedule_manager)
        self.assertEqual(self.schedule_manager.get_current_activity("Farmer", 10.0), "WORK")

    def test_07_save_and_load_persistence_unaffected(self):
        """7. Existing schedules and worker assignments remain intact after save/load."""
        from game.systems.day_cycle import DayCycleSystem
        from game.entities.player import Player
        from game.world.stockpile import StockpileManager
        from game.buildings.furniture import FurnitureManager
        from game.entities.servants import ServantManager

        day_cycle = DayCycleSystem()
        player = Player(0, 0)
        stockpile = StockpileManager()
        furniture = FurnitureManager()
        servant_mgr = ServantManager()

        # Modify schedule
        self.schedule_manager.set_hour_activity("Farmer", 14, "SLEEP")
        test_slot = 99
        save_path = get_slot_path(test_slot)

        try:
            ok, msg = save_to_slot(test_slot, day_cycle, self.resources, player, self.permit_manager,
                                   self.building_manager, stockpile, furniture, self.villager_manager,
                                   servant_mgr, self.schedule_manager)
            self.assertTrue(ok, f"Save failed: {msg}")

            # Fresh schedule manager
            fresh_sched = ScheduleManager()
            fresh_vils = VillagerManager()
            fresh_permits = PermitManager()

            load_ok, load_msg = load_from_slot(test_slot, day_cycle, dict(DEFAULT_RESOURCES), player, fresh_permits,
                                               self.building_manager, stockpile, furniture, fresh_vils,
                                               servant_mgr, fresh_sched)
            self.assertTrue(load_ok, f"Load failed: {load_msg}")
            self.assertEqual(fresh_sched.get_current_activity("Farmer", 14.0), "SLEEP")
            self.assertEqual(len(fresh_vils.families), 1)
        finally:
            if os.path.exists(save_path):
                os.remove(save_path)

    def test_08_wip_professions_do_not_cause_errors_or_display_invented_functionality(self):
        """8. WIP professions display their existing name and WIP status without invented/broken controls."""
        self.ui.active_tab = 5
        self._render_ui()

        for job_id, job_cfg in DEDICATED_JOBS.items():
            if job_cfg.get("wip", False):
                # Must NOT create interactive buttons that trigger broken states
                self.assertNotIn(job_id, self.ui.job_select_btn_rects)
                self.assertNotIn(job_id, self.ui.job_schedule_btn_rects)


if __name__ == "__main__":
    unittest.main()
