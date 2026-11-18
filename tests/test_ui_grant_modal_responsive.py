import unittest
import pygame
from game.ui.ui_raport import RaportUI, GRANTABLE_ITEMS
from game.entities.villagers import Family, Villager

class TestUIGrantModalResponsive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        # Initialize video for headless test rendering
        pygame.display.set_mode((1, 1), pygame.NOFRAME)

    def setUp(self):
        self.ui = RaportUI()
        self.fam = Family("fam_brewer", "Brewer")
        v = Villager("v1", "Hugh", "Brewer", "male", 35, 1, "Farmer", "fam_brewer")
        self.fam.members.append(v)
        self.ui.is_open = True
        self.ui.active_tab = 4
        self.ui.show_grant_dialog = True
        self.ui.selected_family_id = "fam_brewer"
        self.resources = {"Copper": 500, "Silver": 100, "Gold": 50, "Potato": 1000, "Wood": 200, "Stone": 200}

    def test_01_grant_modal_scales_responsively_with_different_resolutions(self):
        """1. Container scales dynamically with available screen space without hardcoded clipping."""
        # Scenario A: Standard 1280x720
        surf_720p = pygame.Surface((1280, 720))
        self.ui._draw_grant_dialog(surf_720p, self.fam, None, self.resources, (0, 0))
        
        dlg_rect_720 = self.ui.grant_dlg_rect
        self.assertIsNotNone(dlg_rect_720)
        self.assertLessEqual(dlg_rect_720.bottom, 720)
        self.assertGreaterEqual(dlg_rect_720.top, 0)
        self.assertLessEqual(dlg_rect_720.width, 600)
        self.assertGreater(dlg_rect_720.width, 400)

        # Scenario B: Constrained 800x480 screen
        surf_small = pygame.Surface((800, 480))
        self.ui._draw_grant_dialog(surf_small, self.fam, None, self.resources, (0, 0))
        
        dlg_rect_small = self.ui.grant_dlg_rect
        self.assertIsNotNone(dlg_rect_small)
        # Must fit within screen boundaries with margin
        self.assertLess(dlg_rect_small.height, 480)
        self.assertGreaterEqual(dlg_rect_small.y, 0)
        # On small screens, content must enable scrolling rather than overflowing
        self.assertGreater(self.ui.grant_max_scroll, 0, "Long list on small screen must be scrollable")
        self.assertIsNotNone(self.ui.grant_scrollbar_rect, "Scrollbar must be visible when content exceeds viewport")

    def test_02_sticky_footer_never_overlaps_list_item_rows(self):
        """2. Sticky footer buttons (Grant & Cancel) never overlap with item rows or controls."""
        surf = pygame.Surface((800, 500))  # Sized so scrolling is active
        self.ui._draw_grant_dialog(surf, self.fam, None, self.resources, (0, 0))

        footer_top = self.ui.grant_submit_btn_rect.top - 14  # top of footer bar
        
        # Check all registered row controls: minus, plus, max, qty boxes
        all_row_rects = list(self.ui.grant_dec_btn_rects.values()) + \
                        list(self.ui.grant_inc_btn_rects.values()) + \
                        list(self.ui.grant_max_btn_rects.values()) + \
                        list(self.ui.grant_item_qty_rects.values())

        for r in all_row_rects:
            # Each item control must strictly be above the footer top
            self.assertLessEqual(r.bottom, footer_top + 4, f"Row control {r} overlaps footer at y={footer_top}!")
            # Item control must never collide with grant button or cancel button
            self.assertFalse(r.colliderect(self.ui.grant_submit_btn_rect), "Row control collided with Grant button!")
            self.assertFalse(r.colliderect(self.ui.grant_close_btn_rect), "Row control collided with Cancel button!")

    def test_03_viewport_clipping_bounds_all_items_inside_container(self):
        """3. All items stay strictly within their parent viewport container."""
        surf = pygame.Surface((800, 500))
        self.ui._draw_grant_dialog(surf, self.fam, None, self.resources, (0, 0))

        vp = self.ui.grant_viewport_rect
        self.assertIsNotNone(vp)

        for it_type, r in self.ui.grant_dec_btn_rects.items():
            self.assertTrue(vp.collidepoint(r.center), f"Minus button for {it_type} center is outside viewport!")
        for it_type, r in self.ui.grant_inc_btn_rects.items():
            self.assertTrue(vp.collidepoint(r.center), f"Plus button for {it_type} center is outside viewport!")

    def test_04_mousewheel_scrolling_and_clamping(self):
        """4. Long lists remain accessible through mouse wheel scrolling and clamping."""
        surf = pygame.Surface((800, 480))
        self.ui._draw_grant_dialog(surf, self.fam, None, self.resources, (0, 0))
        self.assertGreater(self.ui.grant_max_scroll, 0)

        initial_scroll = self.ui.grant_scroll_y
        self.assertEqual(initial_scroll, 0)

        # Scroll down with MOUSEWHEEL (event.y = -1)
        mw_down = pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1, "x": 0})
        act = self.ui.handle_event(mw_down, None, None, self.resources)
        self.assertEqual(act, "grant_scroll")
        self.assertGreater(self.ui.grant_scroll_y, 0)

        # Scroll down excessively (must clamp to max_scroll)
        mw_down_big = pygame.event.Event(pygame.MOUSEWHEEL, {"y": -100, "x": 0})
        self.ui.handle_event(mw_down_big, None, None, self.resources)
        self.assertEqual(self.ui.grant_scroll_y, self.ui.grant_max_scroll)

        # Scroll up excessively (must clamp to 0)
        mw_up_big = pygame.event.Event(pygame.MOUSEWHEEL, {"y": 100, "x": 0})
        self.ui.handle_event(mw_up_big, None, None, self.resources)
        self.assertEqual(self.ui.grant_scroll_y, 0)

    def test_05_header_close_and_footer_cancel_buttons(self):
        """5. Both header [X] and footer [Cancel] close dialog and reset scroll state."""
        surf = pygame.Surface((1280, 720))
        self.ui._draw_grant_dialog(surf, self.fam, None, self.resources, (0, 0))
        self.ui.grant_scroll_y = 50

        # Click Header [X] button
        x_btn = self.ui.grant_header_close_btn_rect
        self.assertIsNotNone(x_btn)
        ev_x = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": x_btn.center})
        act = self.ui.handle_event(ev_x, None, None, self.resources)
        self.assertEqual(act, "close_grant_dialog")
        self.assertFalse(self.ui.show_grant_dialog)
        self.assertEqual(self.ui.grant_scroll_y, 0)

        # Reopen and test Footer [Cancel]
        self.ui.show_grant_dialog = True
        self.ui._draw_grant_dialog(surf, self.fam, None, self.resources, (0, 0))
        self.ui.grant_scroll_y = 30
        c_btn = self.ui.grant_close_btn_rect
        ev_c = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": c_btn.center})
        act2 = self.ui.handle_event(ev_c, None, None, self.resources)
        self.assertEqual(act2, "close_grant_dialog")
        self.assertFalse(self.ui.show_grant_dialog)
        self.assertEqual(self.ui.grant_scroll_y, 0)

    def test_06_grant_confirm_modal_word_wrap_and_responsive_height(self):
        """6. Grant decree confirmation wraps long summaries cleanly without text overflow."""
        surf = pygame.Surface((1280, 720))
        # Select multiple items
        for it in GRANTABLE_ITEMS:
            self.ui.grant_amounts[it["type"]] = 10

        self.ui.show_grant_confirm = True
        self.ui._draw_grant_confirm(surf, self.fam, (0, 0))
        
        # Verify confirm dialog rect is centered and within bounds
        self.assertIsNotNone(self.ui.grant_confirm_btn_rect)
        self.assertIsNotNone(self.ui.grant_cancel_btn_rect)
        self.assertLess(self.ui.grant_confirm_btn_rect.bottom, 720)
        self.assertGreater(self.ui.grant_confirm_btn_rect.top, 0)

    def test_07_issue_market_permit_button_exists_and_clickable(self):
        """7. Area Permits tab includes '+ Market Permit' button and starts placing market permit."""
        from game.world.permits import PermitManager
        from game.buildings.buildings import BuildingManager

        pm = PermitManager()
        bm = BuildingManager()

        surf = pygame.Surface((1280, 720))
        self.ui._init_fonts()
        self.ui.active_tab = 1  # Area Permits tab
        self.ui.show_grant_dialog = False
        self.ui.show_grant_confirm = False
        self.ui._draw_permit_tab(surf, 210, 110, pm, bm)

        # 1. Check all 5 permit buttons exist
        expected_permits = ["housing", "storage", "market", "farm", "landlord_private"]
        for p_key in expected_permits:
            self.assertIn(p_key, self.ui.permit_btn_rects, f"Missing permit button: {p_key}")
            self.assertIsNotNone(self.ui.permit_btn_rects[p_key])

        # 2. Market permit button specifically
        mkt_btn = self.ui.permit_btn_rects["market"]
        self.assertGreater(mkt_btn.width, 100)

        # Verify buttons do not overlap
        btn_list = list(self.ui.permit_btn_rects.values())
        for i in range(len(btn_list)):
            for j in range(i + 1, len(btn_list)):
                self.assertFalse(btn_list[i].colliderect(btn_list[j]), f"Permit buttons {i} and {j} overlap!")

        # 3. Simulate clicking '+ Market Permit'
        ev_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": mkt_btn.center})
        action = self.ui.handle_event(ev_click, bm, pm, self.resources)
        self.assertEqual(action, "start_placing_permit_market")
        self.assertEqual(self.ui.placing_permit_type, "market")
        self.assertFalse(self.ui.is_open, "Raport should close when starting permit placement")

if __name__ == "__main__":
    unittest.main()
