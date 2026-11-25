"""
Tests for BottomDockUI (Intuitive Action Dock & Quick Palette).
Verifies:
- Tabs and category definitions.
- Hotkey handling (B, F, Z, P, X, Esc).
- Item retrieval for structures, furniture, zones, roads.
- Dock clicking and category opening/closing.
- Planning pill confirm / cancel / clear event dispatch.
- Screen rendering without crashes in dummy video mode.
"""

import os
import unittest
import pygame

# Set dummy video driver for headless testing
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

pygame.init()
pygame.display.set_mode((1280, 720))

from game.ui.bottom_dock import BottomDockUI


class TestBottomDockUI(unittest.TestCase):
    def setUp(self):
        self.dock = BottomDockUI()

    def test_initial_state(self):
        self.assertIsNone(self.dock.active_category)
        self.assertEqual(len(self.dock.tabs), 6)
        tab_ids = [t["id"] for t in self.dock.tabs]
        self.assertIn("structures", tab_ids)
        self.assertIn("furniture", tab_ids)
        self.assertIn("zones", tab_ids)
        self.assertIn("roads", tab_ids)
        self.assertIn("demolish", tab_ids)
        self.assertIn("ledger", tab_ids)

    def test_category_items(self):
        # Structures
        structs = self.dock.get_items_for_category("structures")
        self.assertGreater(len(structs), 0)
        self.assertTrue(all(item["kind"] == "BUILDING" for item in structs))

        # Furniture
        furns = self.dock.get_items_for_category("furniture")
        self.assertGreater(len(furns), 0)
        self.assertTrue(all(item["kind"] == "FURNITURE" for item in furns))

        # Zones
        zones = self.dock.get_items_for_category("zones")
        self.assertGreater(len(zones), 0)
        self.assertTrue(all(item["kind"] == "PERMIT" for item in zones))

        # Roads
        roads = self.dock.get_items_for_category("roads")
        self.assertGreater(len(roads), 0)
        self.assertTrue(all(item["kind"] == "ROAD" for item in roads))

    def test_hotkeys(self):
        # B toggles structures
        ev_b = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_b})
        res = self.dock.handle_event(ev_b, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertEqual(self.dock.active_category, "structures")

        # Esc closes palette
        ev_esc = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
        res = self.dock.handle_event(ev_esc, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertIsNone(self.dock.active_category)

        # F toggles furniture
        ev_f = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_f})
        self.dock.handle_event(ev_f, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "furniture")

        # Z toggles zones
        ev_z = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_z})
        self.dock.handle_event(ev_z, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "zones")

        # P toggles roads
        ev_p = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_p})
        self.dock.handle_event(ev_p, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "roads")

        # X triggers Demolish
        ev_x = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_x})
        res = self.dock.handle_event(ev_x, planning_mode="NONE")
        self.assertEqual(res, {"action": "TOGGLE_DEMOLISH"})

    def test_dock_render_and_clicks(self):
        surf = pygame.Surface((1280, 720))

        # Draw dock in idle state
        self.dock.draw(surf, planning_mode="NONE", planning_info=None)

        # Category buttons should have valid rects
        self.assertIn("structures", self.dock.category_btn_rects)
        struct_rect = self.dock.category_btn_rects["structures"]

        # Click structures tab
        ev_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": struct_rect.center})
        res = self.dock.handle_event(ev_click, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertEqual(self.dock.active_category, "structures")

        # Draw dock with active structures palette
        self.dock.draw(surf, planning_mode="NONE", planning_info=None)
        self.assertGreater(len(self.dock.item_card_rects), 0)

        # Click toilet item card in palette
        toilet_rect = self.dock.item_card_rects.get("toilet")
        self.assertIsNotNone(toilet_rect)
        ev_item_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": toilet_rect.center})
        res = self.dock.handle_event(ev_item_click, planning_mode="NONE")
        self.assertEqual(res, {"action": "START_PLANNING", "kind": "BUILDING", "id": "toilet"})
        self.assertIsNone(self.dock.active_category)

    def test_planning_pill_interaction(self):
        surf = pygame.Surface((1280, 720))

        # Draw planning pill
        info = {
            "name": "Toilet",
            "cost_str": "10W 5S",
            "status_msg": "Ready to build",
            "is_valid": True,
            "rotatable": True,
        }
        self.dock.draw(surf, planning_mode="BUILDING", planning_info=info)

        # Confirm & Cancel hitboxes
        self.assertGreater(self.dock.pill_confirm_rect.width, 0)
        self.assertGreater(self.dock.pill_cancel_rect.width, 0)

        # Click Confirm
        ev_confirm = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": self.dock.pill_confirm_rect.center})
        res = self.dock.handle_event(ev_confirm, planning_mode="BUILDING")
        self.assertEqual(res, {"action": "PILL_CONFIRM"})

        # Click Cancel
        ev_cancel = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": self.dock.pill_cancel_rect.center})
        res = self.dock.handle_event(ev_cancel, planning_mode="BUILDING")
        self.assertEqual(res, {"action": "PILL_CANCEL"})


if __name__ == "__main__":
    unittest.main()
