"""
Tests for Prayer Time editing via the Schedule Paint Tool:
- Contiguous rule: Prayer Time cannot be split (neither by painting disconnected
  PRAYER cells nor by erasing an interior hour of a 3+ hour Prayer block).
- Minimum 1 hour rule: a 1-hour Prayer block cannot be erased by another brush;
  edge erasure is only allowed when duration >= 2 hours (leaving >= 1 hour).
- Schedule presets preserve the decreed Prayer block.
- Schedule tab renders the PRAYER brush button and displays feedback on invalid paints.
"""

import os
import unittest
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

pygame.init()
pygame.display.set_mode((1280, 720))

from game.buildings.building_manager import BuildingManager
from game.config import SCHEDULE_LEISURE, SCHEDULE_PRAYER, SCHEDULE_SLEEP, SCHEDULE_WORK
from game.systems.work.schedule import ScheduleManager, UNIVERSAL_SCHEDULE_ID
from game.ui.ui_raport import RaportUI
from game.world.permits import PermitManager


class TestPrayerPaintTool(unittest.TestCase):
    def setUp(self):
        self.sm = ScheduleManager()
        self.sm.activate_universal_schedule()
        self.sm.set_prayer_time(11, 12)  # 1 hour: [11, 12)

    def test_paint_prayer_expands_adjacent_and_rejects_split(self):
        # Cannot paint disconnected hour 15 -> would split Prayer
        ok, msg = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 15, SCHEDULE_PRAYER)
        self.assertFalse(ok)
        self.assertIn("split", msg.lower())
        self.assertEqual(self.sm.get_prayer_hours(), (11, 12))

        # Expand right (12) and left (10) -> [10, 13)
        ok_r, _ = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 12, SCHEDULE_PRAYER)
        ok_l, _ = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 10, SCHEDULE_PRAYER)
        self.assertTrue(ok_r)
        self.assertTrue(ok_l)
        self.assertEqual(self.sm.get_prayer_hours(), (10, 13))
        for h in (10, 11, 12):
            self.assertEqual(self.sm.get_current_activity("Farmer", h), SCHEDULE_PRAYER)

    def test_cannot_erase_middle_or_below_one_hour(self):
        # At 1 hour [11, 12), painting WORK over 11 is blocked (min 1h)
        ok, msg = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 11, SCHEDULE_WORK)
        self.assertFalse(ok)
        self.assertIn("minimum of 1", msg.lower())
        self.assertEqual(self.sm.get_prayer_hours(), (11, 12))

        # Expand to 3 hours [10, 13)
        self.sm.set_prayer_time(10, 13)
        # Cannot erase middle hour 11 (would split into 10 and 12)
        ok_mid, msg_mid = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 11, SCHEDULE_WORK)
        self.assertFalse(ok_mid)
        self.assertIn("split", msg_mid.lower())
        self.assertEqual(self.sm.get_prayer_hours(), (10, 13))

        # Edge hours (10 and 12) CAN be painted over while >= 2h remain -> leaves >= 1h
        ok_edge1, _ = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 10, SCHEDULE_LEISURE)
        self.assertTrue(ok_edge1)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 13))
        self.assertEqual(self.sm.get_current_activity("Farmer", 10), SCHEDULE_LEISURE)

        ok_edge2, _ = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 12, SCHEDULE_SLEEP)
        self.assertTrue(ok_edge2)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 12))
        self.assertEqual(self.sm.get_current_activity("Farmer", 12), SCHEDULE_SLEEP)

        # Now back at 1 hour [11, 12): cannot erase the final hour
        ok_last, _ = self.sm.paint_hour_activity(UNIVERSAL_SCHEDULE_ID, 11, SCHEDULE_WORK)
        self.assertFalse(ok_last)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 12))

    def test_schedule_tab_has_prayer_brush_and_handles_clicks(self):
        ui = RaportUI()
        ui.is_open = True
        ui.active_tab = 5
        ui.selected_schedule_job_id = UNIVERSAL_SCHEDULE_ID

        bm = BuildingManager()
        pm = PermitManager()
        surf = pygame.Surface((1280, 720))
        ui.draw(surf, bm, pm, {}, schedule_manager=self.sm)

        self.assertIn(SCHEDULE_PRAYER, ui.schedule_brush_btn_rects)

        # Click PRAYER brush
        ev_brush = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.schedule_brush_btn_rects[SCHEDULE_PRAYER].center})
        res = ui.handle_event(ev_brush, bm, pm, {}, schedule_manager=self.sm)
        self.assertEqual(res, f"select_brush_{SCHEDULE_PRAYER}")
        self.assertEqual(ui.selected_schedule_brush, SCHEDULE_PRAYER)

        # Click adjacent hour 12 -> expands to [11, 13)
        ev_h12 = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.schedule_hour_cell_rects[12].center})
        ui.handle_event(ev_h12, bm, pm, {}, schedule_manager=self.sm)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 13))
        self.assertTrue(ui.schedule_feedback_ok)

        # Click disconnected hour 5 -> blocked with negative feedback
        ev_h5 = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.schedule_hour_cell_rects[5].center})
        ui.handle_event(ev_h5, bm, pm, {}, schedule_manager=self.sm)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 13))
        self.assertFalse(ui.schedule_feedback_ok)

        # Presets keep the [11, 13) Prayer block intact
        ev_hw = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.schedule_preset_btn_rects["hardwork"].center})
        ui.handle_event(ev_hw, bm, pm, {}, schedule_manager=self.sm)
        self.assertEqual(self.sm.get_prayer_hours(), (11, 13))


if __name__ == "__main__":
    unittest.main()
