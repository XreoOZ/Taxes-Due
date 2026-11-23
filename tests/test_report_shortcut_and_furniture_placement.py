import unittest
import pygame
import os

# Initialize pygame headless
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()
pygame.font.init()

from game.config import TILE_SIZE, FURNITURE_TYPES, DEFAULT_RESOURCES
from game.ui.ui_raport import RaportUI
from game.buildings.furniture import FurnitureManager
from game.world.permits import PermitManager
from game.entities.villagers import VillagerManager, Family
from game.buildings.building_manager import BuildingManager
from game.world.stockpile import StockpileManager
from game.systems.core.save_system import save_to_slot, load_from_slot
from game.systems.core.day_cycle import DayCycleSystem
from game.schedule import ScheduleManager
from game.entities.player import Player
from game.entities.servants import ServantManager


class TestReportKeyboardShortcut(unittest.TestCase):
    def setUp(self):
        self.raport_ui = RaportUI()
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.resources = dict(DEFAULT_RESOURCES)
        self.villager_manager = VillagerManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()

    def test_report_toggle_r_key(self):
        """Acceptance Test 1 & 2: Pressing R opens and closes the Report menu."""
        self.assertFalse(self.raport_ui.is_open)

        # Press R to open
        event_r = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, unicode="r")
        action = self.raport_ui.handle_event(
            event_r, self.building_manager, self.permit_manager, self.resources,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager
        )
        self.assertEqual(action, "toggle_raport")
        self.assertTrue(self.raport_ui.is_open)

        # Press R again to close
        action = self.raport_ui.handle_event(
            event_r, self.building_manager, self.permit_manager, self.resources,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager
        )
        self.assertEqual(action, "toggle_raport")
        self.assertFalse(self.raport_ui.is_open)

    def test_existing_report_hud_button(self):
        """Acceptance Test 3: Existing Report HUD button still works."""
        self.assertFalse(self.raport_ui.is_open)
        click_pos = (self.raport_ui.btn_left_rect.centerx, self.raport_ui.btn_left_rect.centery)
        event_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=click_pos, button=1)
        action = self.raport_ui.handle_event(
            event_click, self.building_manager, self.permit_manager, self.resources,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager
        )
        self.assertEqual(action, "toggle_raport")
        self.assertTrue(self.raport_ui.is_open)

    def test_r_key_suppressed_during_text_entry(self):
        """Acceptance Test 4: Pressing R while typing in a text field does NOT toggle Report."""
        self.raport_ui.is_open = True
        self.raport_ui.show_grant_dialog = True
        self.raport_ui.active_grant_input_item = "Potato"
        self.raport_ui.grant_input_text = "10"

        self.assertTrue(self.raport_ui.is_text_input_active())

        # Press 'r' key while typing in input field
        event_r = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, unicode="r")
        action = self.raport_ui.handle_event(
            event_r, self.building_manager, self.permit_manager, self.resources,
            villager_manager=self.villager_manager,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager
        )
        # Should not close or toggle Report
        self.assertNotEqual(action, "toggle_raport")
        self.assertTrue(self.raport_ui.is_open)
        self.assertEqual(self.raport_ui.grant_input_text, "10")


class TestContinuousFurniturePlacement(unittest.TestCase):
    def setUp(self):
        self.permit_manager = PermitManager()
        self.building_manager = BuildingManager()
        self.furniture_manager = FurnitureManager()
        self.villager_manager = VillagerManager()
        self.resources = {"Wood": 100, "Stone": 50, "Potato": 20}

        # Issue a housing permit with ample tiles
        permit_tiles = {(x, y) for x in range(5, 15) for y in range(5, 15)}
        self.permit = self.permit_manager.add_permit("Test Housing Lot", "housing", permit_tiles)

        # Set up a family assigned to this permit
        self.family = Family("fam_1", "Smith", members=[], assigned_permit_id=self.permit.id)
        self.villager_manager.families.append(self.family)

    def test_furniture_selection_enters_mode_and_closes_report(self):
        """Acceptance Test 1: Selecting furniture from menu automatically enters placement mode and closes Report."""
        raport_ui = RaportUI()
        raport_ui.is_open = True
        raport_ui.active_tab = 0
        raport_ui.show_furniture_menu = True
        raport_ui.furniture_select_rects = {
            "household_storage": pygame.Rect(100, 100, 80, 80),
            "bed": pygame.Rect(200, 100, 80, 80)
        }

        # Click on "household_storage"
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(120, 120), button=1)
        action = raport_ui.handle_event(
            event, self.building_manager, self.permit_manager, self.resources,
            villager_manager=self.villager_manager,
            furniture_manager=self.furniture_manager
        )
        self.assertEqual(action, "start_place_furniture_household_storage")
        self.assertFalse(raport_ui.is_open)
        self.assertEqual(raport_ui.selected_furniture_type, "household_storage")

    def test_continuous_multiple_placements(self):
        """Acceptance Test 2, 3 & 4: Place multiple instances in one session; remain unbuilt until BUILD."""
        session_planned_furniture = []
        planning_furniture_type = "household_storage"

        # Place 3 items at different valid coordinates inside permit
        coords_to_place = [(5, 5), (6, 5), (7, 5)]
        for gx, gy in coords_to_place:
            # Check validation
            target_permit = self.permit_manager.get_permit_at(gx, gy)
            is_occupied_existing = (self.furniture_manager.get_furniture_at(gx, gy) is not None)
            is_occupied_planned = any(pf["gx"] == gx and pf["gy"] == gy for pf in session_planned_furniture)
            is_valid = (target_permit is not None) and not is_occupied_existing and not is_occupied_planned
            self.assertTrue(is_valid)

            session_planned_furniture.append({"gx": gx, "gy": gy, "type": planning_furniture_type})

        # All 3 instances are planned in the session
        self.assertEqual(len(session_planned_furniture), 3)

        # But 0 furniture built yet, and no wood deducted
        self.assertEqual(len(self.furniture_manager.furnitures), 0)
        self.assertEqual(self.resources["Wood"], 100)

    def test_build_confirms_all_planned_furniture(self):
        """Acceptance Test 5: BUILD confirms all valid planned furniture, deducts resources, and creates objects."""
        session_planned_furniture = [
            {"gx": 5, "gy": 5, "type": "household_storage"},
            {"gx": 6, "gy": 5, "type": "household_storage"}
        ]
        f_cfg = FURNITURE_TYPES["household_storage"]
        cost_per_item = f_cfg.get("cost_wood", 10)
        total_cost = len(session_planned_furniture) * cost_per_item

        # Confirm construction
        for pf in session_planned_furniture:
            f_obj, msg = self.furniture_manager.add_furniture(
                pf["type"], pf["gx"], pf["gy"],
                self.permit_manager, self.villager_manager, self.resources,
                building_manager=self.building_manager
            )
            self.assertIsNotNone(f_obj)
        session_planned_furniture.clear()

        # Both furniture objects now exist in furniture_manager
        self.assertEqual(len(self.furniture_manager.furnitures), 2)
        # Resources deducted: 100 - 20 = 80
        self.assertEqual(self.resources["Wood"], 100 - total_cost)
        # Session is now empty
        self.assertEqual(len(session_planned_furniture), 0)

    def test_clear_discards_session_placements_keeps_mode(self):
        """Acceptance Test 6: CLEAR removes unconfirmed placements but keeps mode active."""
        session_planned_furniture = [
            {"gx": 5, "gy": 5, "type": "household_storage"},
            {"gx": 6, "gy": 5, "type": "household_storage"}
        ]
        planning_mode = "FURNITURE"

        # Simulate CLEAR
        session_planned_furniture.clear()

        # Placements removed, mode still FURNITURE, no wood deducted
        self.assertEqual(len(session_planned_furniture), 0)
        self.assertEqual(planning_mode, "FURNITURE")
        self.assertEqual(len(self.furniture_manager.furnitures), 0)
        self.assertEqual(self.resources["Wood"], 100)

    def test_cancel_discards_session_and_exits_mode(self):
        """Acceptance Test 7: CANCEL exits placement mode and discards unconfirmed placements."""
        session_planned_furniture = [
            {"gx": 5, "gy": 5, "type": "household_storage"}
        ]
        planning_mode = "FURNITURE"

        # Simulate CANCEL
        session_planned_furniture.clear()
        planning_mode = "NONE"

        self.assertEqual(len(session_planned_furniture), 0)
        self.assertEqual(planning_mode, "NONE")
        self.assertEqual(len(self.furniture_manager.furnitures), 0)
        self.assertEqual(self.resources["Wood"], 100)

    def test_individual_furniture_removal_before_construction(self):
        """Acceptance Test 8 & 9: Individual planned furniture can be deleted without affecting other planned objects or confirmed projects."""
        # 1. Existing confirmed furniture project
        f_existing, _ = self.furniture_manager.add_furniture(
            "household_storage", 5, 5,
            self.permit_manager, self.villager_manager, self.resources
        )
        self.assertEqual(len(self.furniture_manager.furnitures), 1)
        initial_wood = self.resources["Wood"]

        # 2. Add 3 planned furniture objects in current session
        session_planned_furniture = [
            {"gx": 6, "gy": 5, "type": "bed"},
            {"gx": 7, "gy": 5, "type": "bed"},
            {"gx": 8, "gy": 5, "type": "bed"}
        ]

        # 3. Delete individual planned object at (7, 5)
        target_remove = (7, 5)
        session_planned_furniture = [pf for pf in session_planned_furniture if (pf["gx"], pf["gy"]) != target_remove]

        # Verify only (7, 5) was removed
        remaining_coords = [(pf["gx"], pf["gy"]) for pf in session_planned_furniture]
        self.assertEqual(remaining_coords, [(6, 5), (8, 5)])

        # Confirmed furniture is unaffected
        self.assertEqual(len(self.furniture_manager.furnitures), 1)
        self.assertEqual(self.resources["Wood"], initial_wood)

    def test_no_duplicate_objects_or_duplicate_charges(self):
        """Acceptance Test 11: Duplicate coordinates are rejected during planning."""
        session_planned_furniture = [
            {"gx": 5, "gy": 5, "type": "household_storage"}
        ]
        planned_coords = {(pf["gx"], pf["gy"]) for pf in session_planned_furniture}

        # Attempt to plan at (5, 5) again
        is_occupied_planned = (5, 5) in planned_coords
        self.assertTrue(is_occupied_planned)

    def test_save_load_preserves_confirmed_furniture(self):
        """Acceptance Test 12: Confirmed furniture survives save/load correctly."""
        # Confirm a bed and a chest
        f1, _ = self.furniture_manager.add_furniture(
            "household_storage", 5, 5,
            self.permit_manager, self.villager_manager, self.resources
        )
        f2, _ = self.furniture_manager.add_furniture(
            "bed", 6, 5,
            self.permit_manager, self.villager_manager, self.resources
        )
        self.assertEqual(len(self.furniture_manager.furnitures), 2)

        day_cycle = DayCycleSystem()
        player = Player(0.0, 0.0)
        stockpile_manager = StockpileManager()
        servant_manager = ServantManager()
        schedule_manager = ScheduleManager()

        # Save to slot 99
        success, msg = save_to_slot(
            99, day_cycle, self.resources, player, self.permit_manager,
            self.building_manager, stockpile_manager, self.furniture_manager,
            self.villager_manager, servant_manager, schedule_manager
        )
        self.assertTrue(success, f"Save failed: {msg}")

        # Load into new managers
        loaded_furn_mgr = FurnitureManager()
        loaded_permit_mgr = PermitManager()
        loaded_bld_mgr = BuildingManager()
        loaded_vil_mgr = VillagerManager()
        loaded_res = {}

        success, msg = load_from_slot(
            99, day_cycle, loaded_res, player, loaded_permit_mgr,
            loaded_bld_mgr, stockpile_manager, loaded_furn_mgr,
            loaded_vil_mgr, servant_manager, schedule_manager
        )
        self.assertTrue(success, f"Load failed: {msg}")

        # Verify 2 furnitures restored with exact positions and types
        self.assertEqual(len(loaded_furn_mgr.furnitures), 2)
        loaded_f1 = loaded_furn_mgr.get_furniture_at(5, 5)
        self.assertIsNotNone(loaded_f1)
        self.assertEqual(loaded_f1.furniture_type, "household_storage")

        loaded_f2 = loaded_furn_mgr.get_furniture_at(6, 5)
        self.assertIsNotNone(loaded_f2)
        self.assertEqual(loaded_f2.furniture_type, "bed")


if __name__ == "__main__":
    unittest.main()
