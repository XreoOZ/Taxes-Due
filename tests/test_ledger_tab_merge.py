import os
import unittest
import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager
from game.entities.servants import ServantManager
from game.entities.villagers import VillagerManager
from game.permits import PermitManager
from game.systems.work.schedule import ScheduleManager
from game.ui.ui_raport import RaportUI


class TestLedgerTabMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.ui = RaportUI()
        self.ui.is_open = True
        self.bm = BuildingManager()
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = ScheduleManager()
        self.fm = FurnitureManager()
        self.srv = ServantManager()
        self.surf = pygame.Surface((1280, 720))
        self.resources = {"Wood": 50, "Stone": 50, "Potato": 20}

    def _draw(self):
        self.ui.draw(
            self.surf, self.bm, self.pm, self.resources,
            servant_manager=self.srv, villager_manager=self.vm,
            schedule_manager=self.sm, furniture_manager=self.fm,
        )

    def _click(self, pos):
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": pos})
        return self.ui.handle_event(
            ev, self.bm, self.pm, self.resources,
            servant_manager=self.srv, villager_manager=self.vm,
            schedule_manager=self.sm, furniture_manager=self.fm,
        )

    def test_top_bar_shows_exactly_five_primary_tabs_and_header_roadmap(self):
        self._draw()
        visible_tabs = [
            (i, t["title"]) for i, t in enumerate(self.ui.tabs)
            if not t.get("hidden", False)
        ]
        self.assertEqual(len(visible_tabs), 5)
        self.assertEqual(
            {t[1] for t in visible_tabs},
            {"Town Hall", "Household", "Jobs", "Taxes", "Property"},
        )
        self.assertIsNotNone(self.ui.roadmap_header_btn_rect)
        res = self._click(self.ui.roadmap_header_btn_rect.center)
        self.assertEqual(res, "open_roadmap_tab")
        self.assertEqual(self.ui.active_tab, 8)

    def test_household_and_immigration_subview_toggle(self):
        self.ui.active_tab = 4
        self._draw()
        self.assertIn(4, self.ui.subview_toggle_rects)
        self.assertIn(6, self.ui.subview_toggle_rects)
        res = self._click(self.ui.subview_toggle_rects[6].center)
        self.assertEqual(res, "switch_subview_6")
        self.assertEqual(self.ui.active_tab, 6)
        self.assertTrue(self.ui._tab_is_visually_active(4))

        self._draw()
        res_back = self._click(self.ui.subview_toggle_rects[4].center)
        self.assertEqual(res_back, "switch_subview_4")
        self.assertEqual(self.ui.active_tab, 4)

    def test_jobs_and_servant_priority_subview_toggle(self):
        self.ui.active_tab = 5
        self._draw()
        self.assertIn(5, self.ui.subview_toggle_rects)
        self.assertIn(2, self.ui.subview_toggle_rects)
        res = self._click(self.ui.subview_toggle_rects[2].center)
        self.assertEqual(res, "switch_subview_2")
        self.assertEqual(self.ui.active_tab, 2)
        self.assertTrue(self.ui._tab_is_visually_active(5))

        self._draw()
        res_back = self._click(self.ui.subview_toggle_rects[5].center)
        self.assertEqual(res_back, "switch_subview_5")
        self.assertEqual(self.ui.active_tab, 5)

    def test_property_buildings_and_permits_subview_toggle(self):
        self.ui.active_tab = 0
        self._draw()
        self.assertIn(0, self.ui.subview_toggle_rects)
        self.assertIn(1, self.ui.subview_toggle_rects)
        res = self._click(self.ui.subview_toggle_rects[1].center)
        self.assertEqual(res, "switch_subview_1")
        self.assertEqual(self.ui.active_tab, 1)
        self.assertTrue(self.ui._tab_is_visually_active(0))

        self._draw()
        res_back = self._click(self.ui.subview_toggle_rects[0].center)
        self.assertEqual(res_back, "switch_subview_0")
        self.assertEqual(self.ui.active_tab, 0)


if __name__ == "__main__":
    unittest.main()
