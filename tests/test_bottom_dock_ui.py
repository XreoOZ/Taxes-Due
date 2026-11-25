"""
Tests for BottomDockUI (Intuitive Action Dock & Hierarchical Building Palette).
Verifies:
- 5 Compact primary tabs (Building, Zones, Roads, Demolish, Ledger).
- Hierarchical sub-categories for Building (Structures, Civic/Public, Workstations, Furniture).
- Hotkey handling (B, C, T, F, Z, P, X, Esc).
- Item retrieval across sub-categories.
- Sub-category pill clicking and item card selection.
- Planning pill confirm / cancel event dispatch.
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
        self.assertEqual(len(self.dock.tabs), 5)
        tab_ids = [t["id"] for t in self.dock.tabs]
        self.assertEqual(tab_ids, ["building", "zones", "roads", "demolish", "ledger"])

        self.assertEqual(len(self.dock.building_subcats), 4)
        subcat_ids = [s["id"] for s in self.dock.building_subcats]
        self.assertEqual(subcat_ids, ["structures", "public", "workstations", "furniture"])

    def test_category_items(self):
        # 1. Structures sub-category
        self.dock.active_building_subcat = "structures"
        structs = self.dock.get_items_for_category("building")
        self.assertEqual(len(structs), 2)
        struct_ids = [s["id"] for s in structs]
        self.assertIn("wooden_structure", struct_ids)
        self.assertIn("stone_structure", struct_ids)

        # 2. Public / Civic sub-category
        self.dock.active_building_subcat = "public"
        pub_items = self.dock.get_items_for_category("building")
        self.assertEqual(len(pub_items), 6)
        pub_ids = [p["id"] for p in pub_items]
        self.assertIn("well", pub_ids)
        self.assertIn("toilet", pub_ids)
        self.assertIn("market", pub_ids)
        self.assertIn("tax_house", pub_ids)
        self.assertIn("notice_board", pub_ids)
        self.assertIn("confession_box", pub_ids)

        # 3. Workstations sub-category
        self.dock.active_building_subcat = "workstations"
        workstations = self.dock.get_items_for_category("building")
        self.assertEqual(len(workstations), 4)
        ws_ids = [w["id"] for w in workstations]
        self.assertIn("builder_workbench", ws_ids)
        self.assertIn("toolmaker_workbench", ws_ids)
        self.assertIn("woodsman_lodge", ws_ids)
        self.assertIn("miner_workstation", ws_ids)

        # 4. Household Furniture sub-category
        self.dock.active_building_subcat = "furniture"
        furns = self.dock.get_items_for_category("building")
        self.assertEqual(len(furns), 3)
        furn_ids = [f["id"] for f in furns]
        self.assertIn("bed", furn_ids)
        self.assertIn("household_storage", furn_ids)
        self.assertIn("lord_treasury_chest", furn_ids)

        # 5. Zones
        zones = self.dock.get_items_for_category("zones")
        self.assertEqual(len(zones), 7)

        # 6. Roads
        roads = self.dock.get_items_for_category("roads")
        self.assertEqual(len(roads), 3)

    def test_hotkeys(self):
        # B toggles building at structures
        ev_b = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_b})
        res = self.dock.handle_event(ev_b, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertEqual(self.dock.active_category, "building")
        self.assertEqual(self.dock.active_building_subcat, "structures")

        # Esc closes palette
        ev_esc = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
        res = self.dock.handle_event(ev_esc, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertIsNone(self.dock.active_category)

        # C jumps directly to Civic/Public
        ev_c = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_c})
        self.dock.handle_event(ev_c, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "building")
        self.assertEqual(self.dock.active_building_subcat, "public")

        # T jumps directly to Workstations
        ev_t = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_t})
        self.dock.handle_event(ev_t, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "building")
        self.assertEqual(self.dock.active_building_subcat, "workstations")

        # F jumps directly to Furniture
        ev_f = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_f})
        self.dock.handle_event(ev_f, planning_mode="NONE")
        self.assertEqual(self.dock.active_category, "building")
        self.assertEqual(self.dock.active_building_subcat, "furniture")

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

        # 5 Category buttons should have valid rects
        self.assertIn("building", self.dock.category_btn_rects)
        self.assertIn("zones", self.dock.category_btn_rects)
        self.assertIn("roads", self.dock.category_btn_rects)
        self.assertIn("demolish", self.dock.category_btn_rects)
        self.assertIn("ledger", self.dock.category_btn_rects)

        # Click Building tab
        build_rect = self.dock.category_btn_rects["building"]
        ev_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": build_rect.center})
        res = self.dock.handle_event(ev_click, planning_mode="NONE")
        self.assertEqual(res, {"action": "HANDLED"})
        self.assertEqual(self.dock.active_category, "building")

        # Draw dock with active Building palette
        self.dock.draw(surf, planning_mode="NONE", planning_info=None)

        # Sub-category pills should be present
        self.assertIn("structures", self.dock.subcat_pill_rects)
        self.assertIn("public", self.dock.subcat_pill_rects)
        self.assertIn("workstations", self.dock.subcat_pill_rects)
        self.assertIn("furniture", self.dock.subcat_pill_rects)

        # Click Public sub-category pill
        pub_pill_rect = self.dock.subcat_pill_rects["public"]
        ev_pill_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": pub_pill_rect.center})
        res_pill = self.dock.handle_event(ev_pill_click, planning_mode="NONE")
        self.assertEqual(res_pill, {"action": "HANDLED"})
        self.assertEqual(self.dock.active_building_subcat, "public")

        # Re-render with public sub-category active
        self.dock.draw(surf, planning_mode="NONE", planning_info=None)

        # Click toilet item card in palette
        toilet_rect = self.dock.item_card_rects.get("toilet")
        self.assertIsNotNone(toilet_rect)
        ev_item_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": toilet_rect.center})
        res_item = self.dock.handle_event(ev_item_click, planning_mode="NONE")
        self.assertEqual(res_item, {"action": "START_PLANNING", "kind": "BUILDING", "id": "toilet"})
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
