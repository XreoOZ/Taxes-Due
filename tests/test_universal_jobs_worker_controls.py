import unittest
import pygame
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import DEDICATED_JOBS, TILE_SIZE
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.permits import PermitManager, AreaPermit
from game.systems.job_tool_system import assign_job_worker, release_job_worker
from game.systems.cemetery_system import CemeterySystem
from game.ui.ui_raport import RaportUI


class TestUniversalJobsWorkerControls(unittest.TestCase):
    def setUp(self):
        self.vm = VillagerManager()
        self.pm = PermitManager()

        # Create two families with members
        self.fam1 = Family("fam_1", "Miller")
        self.v1 = Villager("vil_1", "Henry", "Miller", "Male", 35, 1, "Father", family_id="fam_1", x=100.0, y=100.0)
        self.v2 = Villager("vil_2", "Alice", "Miller", "Female", 33, 1, "Mother", family_id="fam_1", x=102.0, y=100.0)
        self.fam1.members.extend([self.v1, self.v2])
        self.vm.families.append(self.fam1)

        self.fam2 = Family("fam_2", "Smith")
        self.v3 = Villager("vil_3", "John", "Smith", "Male", 25, 1, "Adult Son", family_id="fam_2", x=200.0, y=200.0)
        self.v4 = Villager("vil_4", "Mary", "Smith", "Female", 22, 1, "Adult Daughter", family_id="fam_2", x=202.0, y=200.0)
        self.fam2.members.extend([self.v3, self.v4])
        self.vm.families.append(self.fam2)

        # Create permits: Farm, Church, Cemetery
        self.farm_p = AreaPermit(
            "farm_1",
            "North Farm",
            "farm",
            {(5+x, 5+y) for x in range(4) for y in range(4)}
        )
        self.pm.permits.append(self.farm_p)

        self.cemetery_p = AreaPermit(
            "cemetery_1",
            "Parish Cemetery",
            "cemetery",
            {(10+x, 10+y) for x in range(3) for y in range(3)}
        )
        self.pm.permits.append(self.cemetery_p)

        self.church_p = AreaPermit(
            "church_1",
            "Village Church",
            "church",
            {(15+x, 15+y) for x in range(3) for y in range(3)}
        )
        self.pm.permits.append(self.church_p)

    def test_01_gravedigger_worker_inc_and_dec(self):
        """Increasing and decreasing Gravedigger workers via universal assignment."""
        all_v = self.vm.get_all_villagers()
        self.assertTrue(len(all_v) >= 2)

        # Initially 0 Gravediggers
        initial_gds = [v for v in all_v if v.job == "Gravedigger"]
        self.assertEqual(len(initial_gds), 0)

        # Increase Gravedigger count
        ok, chosen = assign_job_worker("Gravedigger", self.pm, self.vm)
        self.assertTrue(ok)
        self.assertEqual(chosen.job, "Gravedigger")
        self.assertEqual(chosen.title, "Gravedigger")
        self.assertIn(chosen.id, self.cemetery_p.assigned_workers)

        # Increase again (2nd Gravedigger)
        ok2, chosen2 = assign_job_worker("Gravedigger", self.pm, self.vm)
        self.assertTrue(ok2)
        self.assertNotEqual(chosen.id, chosen2.id)
        self.assertEqual(chosen2.job, "Gravedigger")
        self.assertEqual(len(self.cemetery_p.assigned_workers), 2)

        # Decrease Gravedigger count
        ok_dec, released = release_job_worker("Gravedigger", self.pm, self.vm)
        self.assertTrue(ok_dec)
        self.assertNotEqual(released.job, "Gravedigger")
        self.assertEqual(len(self.cemetery_p.assigned_workers), 1)

    def test_02_all_dedicated_jobs_support_worker_assignment(self):
        """Every dedicated job in DEDICATED_JOBS can increase and decrease workers."""
        test_jobs = ["Farmer", "Builder", "Priest", "Gravedigger"]
        for j_id in test_jobs:
            ok, v = assign_job_worker(j_id, self.pm, self.vm)
            self.assertTrue(ok, f"Failed to assign worker to {j_id}")
            self.assertEqual(v.job, j_id)

            ok_rel, v_rel = release_job_worker(j_id, self.pm, self.vm)
            self.assertTrue(ok_rel, f"Failed to release worker from {j_id}")
            self.assertNotEqual(v_rel.job, j_id)

    def test_03_ui_raport_view_1_has_controls_for_all_jobs(self):
        """In View 1 of Raport Jobs tab, +/- controls exist for all jobs."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 5
        ui.selected_job_id = None
        surface = pygame.Surface((1280, 720))

        ui._draw_workers_tab(surface, 210, 110, self.vm, self.pm)

        # Verify buttons were created for Gravedigger, Farmer, Builder, Priest, etc.
        self.assertIn("Gravedigger", ui.job_inc_btn_rects)
        self.assertIn("Gravedigger", ui.job_dec_btn_rects)
        self.assertIn("Farmer", ui.job_inc_btn_rects)
        self.assertIn("Farmer", ui.job_dec_btn_rects)
        self.assertIn("Builder", ui.job_inc_btn_rects)
        self.assertIn("Builder", ui.job_dec_btn_rects)
        self.assertIn("Priest", ui.job_inc_btn_rects)
        self.assertIn("Priest", ui.job_dec_btn_rects)

        # Test clicking '+' on Gravedigger through handle_event
        gd_inc_rect = ui.job_inc_btn_rects["Gravedigger"]
        ev_inc = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": gd_inc_rect.center, "button": 1})
        res = ui.handle_event(ev_inc, None, self.pm, None, villager_manager=self.vm)
        self.assertEqual(res, "job_worker_inc_Gravedigger")

        # Verify worker is now a Gravedigger
        gds = [v for v in self.vm.get_all_villagers() if v.job == "Gravedigger"]
        self.assertEqual(len(gds), 1)

        # Test clicking '-' on Gravedigger through handle_event
        gd_dec_rect = ui.job_dec_btn_rects["Gravedigger"]
        ev_dec = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": gd_dec_rect.center, "button": 1})
        res_dec = ui.handle_event(ev_dec, None, self.pm, None, villager_manager=self.vm)
        self.assertEqual(res_dec, "job_worker_dec_Gravedigger")

        gds_after = [v for v in self.vm.get_all_villagers() if v.job == "Gravedigger"]
        self.assertEqual(len(gds_after), 0)

    def test_04_ui_raport_view_2_has_controls_for_selected_job(self):
        """In View 2 (Roster view), +/- controls are drawn in the banner for the selected job."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 5
        ui.selected_job_id = "Gravedigger"
        surface = pygame.Surface((1280, 720))

        ui._draw_workers_tab(surface, 210, 110, self.vm, self.pm)

        self.assertIn("Gravedigger", ui.job_inc_btn_rects)
        self.assertIn("Gravedigger", ui.job_dec_btn_rects)

        # Clicking '+' on banner inc button
        inc_rect = ui.job_inc_btn_rects["Gravedigger"]
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": inc_rect.center, "button": 1})
        res = ui.handle_event(ev, None, self.pm, None, villager_manager=self.vm)
        self.assertEqual(res, "job_worker_inc_Gravedigger")

        gds = [v for v in self.vm.get_all_villagers() if v.job == "Gravedigger"]
        self.assertEqual(len(gds), 1)


if __name__ == "__main__":
    unittest.main()
