"""
AGENT 2 Acceptance Test Suite:
1. Household Food Purchasing Restriction (Core Rule: IF HOUSEHOLD HAS FOOD -> DO NOT BUY FOOD)
2. Permit UI Category Organization (Two-tier Navigation: Categories View -> Filtered Permits View)
"""

import unittest
import os
import pygame
from game.data.config import (
    BUILDING_TYPES,
    PERMIT_TYPES,
    DEFAULT_ITEM_PRICES,
    DEFAULT_RESOURCES,
    get_permit_categories,
    is_food_item,
    register_item_category
)
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager, ResourceStack
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.villagers import VillagerManager, Family, Villager
from game.entities.servants import ServantManager
from game.systems.core.day_cycle import DayCycleSystem
from game.systems.work.schedule import ScheduleManager
from game.systems.economy.market_service import MarketService
from game.systems.economy.market_interface import request_market_food_purchase
from game.systems.economy.currency import to_copper, normalize_wallet
from game.systems.core.save_system import save_to_slot, load_from_slot, get_slot_path
from game.ui.ui_raport import RaportUI


class TestAgent2HouseholdFoodPurchasingAndPermitsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()
        self.villager_manager = VillagerManager()
        self.servant_manager = ServantManager()
        self.day_cycle = DayCycleSystem()
        self.schedule_manager = ScheduleManager()
        self.resources = dict(DEFAULT_RESOURCES)

        # Setup standard market building with inventory and prices
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        self.market = Building("market", tiles_3x2)
        self.market.inventory = {"Potato": 100, "Bread": 50, "Carrot": 30, "Hoe": 10, "Wood": 200}
        self.market.prices = {"Potato": 3, "Bread": 5, "Carrot": 2, "Hoe": 15, "Wood": 2}
        self.market.currency = {"Copper": 50, "Silver": 10, "Gold": 0}
        self.building_manager.buildings.append(self.market)

    # =========================================================================
    # PART 1: HOUSEHOLD FOOD PURCHASING RESTRICTION (Acceptance Tests 1 - 9)
    # =========================================================================

    def test_01_household_with_5_potatoes_must_not_purchase_food(self):
        """1. Household has 5 Potatoes -> AI must not purchase food."""
        fam = Family("fam_1", "Smith")
        vil = Villager(1, "John", "Smith", "Male", 30, 2, "Father", "fam_1")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_1", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_1")
        chest.inventory = {"Copper": 50, "Potato": 5}
        self.furniture_manager.furnitures.append(chest)

        # Pre-check rule evaluation
        can_buy, reason = MarketService.can_household_purchase_food(vil, "Potato", furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertFalse(can_buy)
        self.assertIn("enough food", reason.lower())

        # Attempt purchase via request_market_food_purchase
        bought, food_name, amt = request_market_food_purchase(
            "fam_1", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought)
        self.assertEqual(amt, 0)
        self.assertEqual(chest.inventory["Potato"], 5)
        self.assertEqual(chest.inventory["Copper"], 50)
        self.assertEqual(self.market.inventory["Potato"], 100)

    def test_02_household_with_1_potato_must_not_purchase_food(self):
        """2. Household has 1 Potato -> AI must not purchase food."""
        fam = Family("fam_2", "Miller")
        vil = Villager(2, "Alice", "Miller", "Female", 28, 2, "Mother", "fam_2")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_2", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_2")
        chest.inventory = {"Copper": 50, "Potato": 1}
        self.furniture_manager.furnitures.append(chest)

        bought, _, amt = request_market_food_purchase(
            "fam_2", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought)
        self.assertEqual(amt, 0)
        self.assertEqual(chest.inventory["Potato"], 1)

    def test_03_household_with_0_food_may_purchase_food(self):
        """3. Household has 0 food -> AI may purchase food."""
        fam = Family("fam_3", "Baker")
        vil = Villager(3, "Bob", "Baker", "Male", 25, 2, "Father", "fam_3")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_3", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_3")
        chest.inventory = {"Copper": 20}  # 0 food, but has 20c
        self.furniture_manager.furnitures.append(chest)

        # Household has 0 food -> permitted to purchase
        can_buy, reason = MarketService.can_household_purchase_food(vil, "Potato", furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertTrue(can_buy)

        bought, food_name, amt = request_market_food_purchase(
            "fam_3", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(bought)
        self.assertEqual(amt, 1)
        self.assertEqual(chest.inventory["Potato"], 1)
        self.assertEqual(to_copper(normalize_wallet(chest.inventory)), 17)  # 20c - 3c price
        self.assertEqual(self.market.inventory["Potato"], 99)

    def test_04_only_household_without_food_may_purchase(self):
        """4. Household A has food, Household B has none -> only Household B may purchase."""
        # Household A (Has food)
        fam_a = Family("fam_A", "Alpha")
        vil_a = Villager(4, "Adam", "Alpha", "Male", 35, 2, "Head", "fam_A")
        fam_a.members.append(vil_a)
        chest_a = Furniture("chest_a", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_A")
        chest_a.inventory = {"Copper": 50, "Potato": 4}

        # Household B (No food)
        fam_b = Family("fam_B", "Beta")
        vil_b = Villager(5, "Brian", "Beta", "Male", 32, 2, "Head", "fam_B")
        fam_b.members.append(vil_b)
        chest_b = Furniture("chest_b", "household_storage", 6, 6, permit_id="test_permit", family_id="fam_B")
        chest_b.inventory = {"Copper": 50}

        self.villager_manager.families.extend([fam_a, fam_b])
        self.furniture_manager.furnitures.extend([chest_a, chest_b])

        # Household A attempts to purchase -> DENIED
        bought_a, _, _ = request_market_food_purchase(
            "fam_A", vil_a, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought_a)
        self.assertEqual(chest_a.inventory["Potato"], 4)

        # Household B attempts to purchase -> ALLOWED
        bought_b, _, _ = request_market_food_purchase(
            "fam_B", vil_b, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(bought_b)
        self.assertEqual(chest_b.inventory["Potato"], 1)

    def test_05_food_completely_consumed_allows_purchasing_again(self):
        """5. When household food is completely consumed (0 remaining), AI may purchase food again."""
        fam = Family("fam_5", "Cooper")
        vil = Villager(6, "Charlie", "Cooper", "Male", 40, 2, "Head", "fam_5")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_5", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_5")
        chest.inventory = {"Copper": 50, "Potato": 1}
        self.furniture_manager.furnitures.append(chest)

        # Initially has 1 potato -> blocked
        bought1, _, _ = request_market_food_purchase(
            "fam_5", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought1)

        # Consume the single potato
        chest.inventory["Potato"] -= 1
        if chest.inventory["Potato"] <= 0:
            del chest.inventory["Potato"]
        self.assertEqual(MarketService.get_household_available_food_stock(vil, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager), 0)

        # Now household food is completely consumed -> allowed to purchase!
        bought2, _, amt2 = request_market_food_purchase(
            "fam_5", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(bought2)
        self.assertEqual(amt2, 1)
        self.assertEqual(chest.inventory["Potato"], 1)

    def test_06_generic_food_items_block_purchasing(self):
        """6. Test with other FOOD-category items (e.g. Bread, Carrot, custom foods), not just Potato."""
        fam = Family("fam_6", "Farmer")
        vil = Villager(7, "Frank", "Farmer", "Male", 29, 2, "Head", "fam_6")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_6", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_6")
        # Household has 0 Potatoes, but has 2 loaves of Bread
        chest.inventory = {"Copper": 50, "Bread": 2}
        self.furniture_manager.furnitures.append(chest)

        self.assertTrue(is_food_item("Bread"))
        # Bread is a FOOD category item -> AI must NOT purchase potatoes or carrots
        can_buy, _ = MarketService.can_household_purchase_food(vil, "Potato", furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertFalse(can_buy)

        bought, _, _ = request_market_food_purchase(
            "fam_6", vil, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought)

        # Test newly registered food mod item
        register_item_category("Roast_Duck", "FOOD")
        chest.inventory = {"Copper": 50, "Roast_Duck": 1}
        can_buy_duck, _ = MarketService.can_household_purchase_food(vil, "Potato", furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertFalse(can_buy_duck)

    def test_07_non_food_market_purchases_work_normally(self):
        """7. Verify non-food market purchases (e.g. Tool, Resource) still work normally even if household has food."""
        fam = Family("fam_7", "Blacksmith")
        vil = Villager(8, "George", "Blacksmith", "Male", 33, 2, "Head", "fam_7")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_7", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_7")
        chest.inventory = {"Copper": 50, "Potato": 10}  # Has 10 potatoes
        self.furniture_manager.furnitures.append(chest)

        # Attempt to purchase non-food item "Hoe" (Tool)
        self.assertFalse(is_food_item("Hoe"))
        can_buy, reason = MarketService.can_household_purchase_food(vil, "Hoe", furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertTrue(can_buy)

        # Execute purchase of Hoe
        ok, msg, receipt = MarketService.execute_purchase(
            vil, "Hoe", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(ok, msg)
        self.assertEqual(chest.inventory.get("Hoe"), 1)
        self.assertEqual(chest.inventory.get("Potato"), 10)  # Potatoes untouched

    def test_08_multiple_ai_members_do_not_buy_duplicate_food(self):
        """8. Multiple AI members of the same household do not buy duplicate food when food is already available."""
        fam = Family("fam_8", "Brewer")
        v1 = Villager(9, "Hugh", "Brewer", "Male", 40, 2, "Father", "fam_8")
        v2 = Villager(10, "Agnes", "Brewer", "Female", 38, 2, "Mother", "fam_8")
        fam.members.extend([v1, v2])
        self.villager_manager.families.append(fam)

        chest = Furniture("chest_8", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_8")
        chest.inventory = {"Copper": 50}  # Initially 0 food
        self.furniture_manager.furnitures.append(chest)

        # 1. Hugh buys food covering the hungry family's remaining daily need (2 members)
        bought1, _, amt1 = request_market_food_purchase(
            "fam_8", v1, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(bought1)
        self.assertEqual(chest.inventory["Potato"], 2)

        # 2. Immediately Agnes checks -> household now possesses enough food -> Agnes is PREVENTED from duplicate buying
        bought2, _, amt2 = request_market_food_purchase(
            "fam_8", v2, food_item="Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(bought2)
        self.assertEqual(amt2, 0)
        self.assertEqual(chest.inventory["Potato"], 2)  # No duplicate purchases

    def test_09_save_load_preserves_inventory_and_purchasing_behavior(self):
        """9. Verify save/load preserves household food inventory and purchasing restrictions."""
        slot_id = 98
        try:
            fam = Family("fam_save", "Saver")
            vil = Villager(11, "Sam", "Saver", "Male", 25, 2, "Head", "fam_save")
            fam.members.append(vil)
            self.villager_manager.families.append(fam)

            chest = Furniture("chest_s", "household_storage", 3, 3, permit_id="test_permit", family_id="fam_save")
            chest.inventory = {"Copper": 40, "Potato": 3}
            self.furniture_manager.furnitures.append(chest)

            # Save state
            dummy_player = type("PlayerObj", (), {"x": 0.0, "y": 0.0})()
            save_ok, _ = save_to_slot(
                slot_id, self.day_cycle, self.resources,
                dummy_player,
                self.permit_manager, self.building_manager,
                self.stockpile_manager, self.furniture_manager,
                self.villager_manager, self.servant_manager,
                self.schedule_manager
            )
            self.assertTrue(save_ok)

            # Clear state
            self.furniture_manager.furnitures.clear()
            self.villager_manager.families.clear()
            self.building_manager.buildings.clear()

            # Load state
            load_ok, _ = load_from_slot(
                slot_id, self.day_cycle, self.resources,
                dummy_player,
                self.permit_manager, self.building_manager,
                self.stockpile_manager, self.furniture_manager,
                self.villager_manager, self.servant_manager,
                self.schedule_manager
            )
            self.assertTrue(load_ok)

            # Verify loaded household still has 3 potatoes and cannot buy food
            loaded_fam = self.villager_manager.get_family_by_id("fam_save")
            self.assertIsNotNone(loaded_fam)
            loaded_vil = loaded_fam.members[0]
            self.assertIsNotNone(loaded_vil)
            stock = MarketService.get_household_available_food_stock(
                loaded_vil,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager
            )
            self.assertEqual(stock, 3)

            bought, _, _ = request_market_food_purchase(
                "fam_save", loaded_vil, food_item="Potato", quantity=1,
                building_manager=self.building_manager,
                furniture_manager=self.furniture_manager,
                villager_manager=self.villager_manager
            )
            self.assertFalse(bought)
        finally:
            path = get_slot_path(slot_id)
            if os.path.exists(path):
                os.remove(path)

    # =========================================================================
    # PART 2: PERMITS UI CATEGORY ORGANIZATION (Acceptance Tests 1 - 7)
    # =========================================================================

    def test_10_opening_permits_displays_categories_instead_of_all_permits(self):
        """1. Opening Permits displays categories instead of all individual permits."""
        # Create 3 permits of different types
        p1 = AreaPermit(101, "Housing Lot #1", "housing", {(1, 1), (2, 1)})
        p2 = AreaPermit(102, "Farm Lot #2", "farm", {(3, 3), (4, 3)})
        p3 = AreaPermit(103, "Market Lot #3", "market", {(5, 5)})
        self.permit_manager.permits = [p1, p2, p3]

        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1  # Permits Tab
        ui.selected_permit_category = None  # Root screen

        surf = pygame.Surface((1280, 720))
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)

        # 1. Categories are registered
        categories = get_permit_categories()
        for cat in categories:
            self.assertIn(cat["id"], ui.permit_category_btn_rects)
            self.assertIsNotNone(ui.permit_category_btn_rects[cat["id"]])

        # 2. Individual permit action buttons (Delete, Edit, Plant) are NOT on the root screen
        self.assertEqual(len(ui.delete_permit_btn_rects), 0)
        self.assertEqual(len(ui.edit_permit_btn_rects), 0)
        self.assertEqual(len(ui.open_plant_btn_rects), 0)
        self.assertIsNone(ui.permit_category_back_btn_rect)

    def test_11_selecting_category_displays_only_its_corresponding_permits(self):
        """2. Selecting a category displays only the permits belonging to that selected category."""
        p_house1 = AreaPermit(201, "Housing Lot #1", "housing", {(1, 1)})
        p_house2 = AreaPermit(202, "Housing Lot #2", "housing", {(2, 2)})
        p_farm = AreaPermit(203, "Farm Lot #1", "farm", {(3, 3)})
        self.permit_manager.permits = [p_house1, p_house2, p_farm]

        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1
        ui.selected_permit_category = "housing"

        surf = pygame.Surface((1280, 720))
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)

        # Back button is now available
        self.assertIsNotNone(ui.permit_category_back_btn_rect)

        # Edit buttons exist ONLY for housing permits (201, 202) - NOT farm (203)
        self.assertIn(201, ui.edit_permit_btn_rects)
        self.assertIn(202, ui.edit_permit_btn_rects)
        self.assertNotIn(203, ui.edit_permit_btn_rects)

    def test_12_back_button_returns_to_category_selection_screen(self):
        """3. The Back button returns to the category selection screen."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1
        ui.selected_permit_category = "farm"

        surf = pygame.Surface((1280, 720))
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
        self.assertIsNotNone(ui.permit_category_back_btn_rect)

        # Click Back button
        ev_back = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.permit_category_back_btn_rect.center})
        res = ui.handle_event(ev_back, self.building_manager, self.permit_manager, self.resources)
        self.assertEqual(res, "permit_category_back")
        self.assertIsNone(ui.selected_permit_category)

        # Redraw -> Now back at root screen
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
        self.assertIsNone(ui.permit_category_back_btn_rect)
        self.assertGreater(len(ui.permit_category_btn_rects), 0)

    def test_13_permit_details_and_functionality_intact(self):
        """4. Permit details, worker controls, plant popup, and edit functionality remain intact."""
        farm_p = AreaPermit(301, "Main Farm Lot", "farm", {(0, 0), (1, 0)})
        farm_p.max_workers = 3
        self.permit_manager.permits = [farm_p]

        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1
        ui.selected_permit_category = "farm"

        surf = pygame.Surface((1280, 720))
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)

        # Worker controls exist
        self.assertIn(301, ui.worker_inc_btn_rects)
        self.assertIn(301, ui.worker_dec_btn_rects)
        self.assertIn(301, ui.worker_auto_btn_rects)
        self.assertIn(301, ui.open_plant_btn_rects)

        # Click worker [+] increment
        inc_btn = ui.worker_inc_btn_rects[301]
        ev_inc = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": inc_btn.center})
        res = ui.handle_event(ev_inc, self.building_manager, self.permit_manager, self.resources, villager_manager=self.villager_manager)
        self.assertEqual(res, "inc_worker_301")
        self.assertEqual(farm_p.max_workers, 4)

    def test_14_permits_from_different_categories_never_mixed(self):
        """5. Permits from different categories never appear mixed together."""
        p_storage = AreaPermit(401, "Storage Lot", "storage", {(0, 0)})
        p_market = AreaPermit(402, "Market Lot", "market", {(2, 2)})
        p_private = AreaPermit(403, "Private Estate", "landlord_private", {(4, 4)})
        self.permit_manager.permits = [p_storage, p_market, p_private]

        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1

        surf = pygame.Surface((1280, 720))

        # View Storage category
        ui.selected_permit_category = "storage"
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
        self.assertIn(401, ui.edit_permit_btn_rects)
        self.assertNotIn(402, ui.edit_permit_btn_rects)
        self.assertNotIn(403, ui.edit_permit_btn_rects)

        # View Market category
        ui.selected_permit_category = "market"
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
        self.assertNotIn(401, ui.edit_permit_btn_rects)
        self.assertIn(402, ui.edit_permit_btn_rects)
        self.assertNotIn(403, ui.edit_permit_btn_rects)

    def test_15_empty_category_displays_appropriate_empty_state(self):
        """6. Empty categories display an appropriate empty state."""
        self.permit_manager.permits = []  # Zero permits exist

        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 1
        ui.selected_permit_category = "market"  # 0 market lots exist

        surf = pygame.Surface((1280, 720))
        ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)

        # No individual permit rows
        self.assertEqual(len(ui.edit_permit_btn_rects), 0)
        self.assertEqual(len(ui.delete_permit_btn_rects), 0)

        # Category issue button is available to create the first lot
        self.assertIn("market", ui.permit_btn_rects)
        mkt_btn = ui.permit_btn_rects["market"]

        ev_mkt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": mkt_btn.center})
        action = ui.handle_event(ev_mkt, self.building_manager, self.permit_manager, self.resources)
        self.assertEqual(action, "start_placing_permit_market")
        self.assertEqual(ui.placing_permit_type, "market")
        self.assertFalse(ui.is_open)

    def test_16_newly_added_category_automatically_reflected_without_hardcoded_ui(self):
        """7. Newly added categories and permits in config are automatically reflected in UI without hardcoding."""
        # Dynamically register a new modded permit type
        PERMIT_TYPES["brewery_zone"] = {
            "id": "brewery_zone",
            "name": "Brewery Permit",
            "category": "Artisan & Brewing",
            "category_id": "brewery",
            "desc": "Official guild deed for ale fermentation and brewing stills.",
            "color": (217, 119, 6, 60),
            "border_color": (245, 158, 11),
        }

        try:
            cats = get_permit_categories()
            brewery_cat = next((c for c in cats if c["id"] == "brewery"), None)
            self.assertIsNotNone(brewery_cat)
            self.assertEqual(brewery_cat["name"], "Artisan & Brewing")
            self.assertIn("brewery_zone", brewery_cat["permit_types"])

            # Raport UI automatically registers the new category button
            ui = RaportUI()
            ui._init_fonts()
            ui.is_open = True
            ui.active_tab = 1
            ui.selected_permit_category = None

            surf = pygame.Surface((1280, 720))
            ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
            self.assertIn("brewery", ui.permit_category_btn_rects)

            # Click newly registered category
            cat_rect = ui.permit_category_btn_rects["brewery"]
            ev_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": cat_rect.center})
            action = ui.handle_event(ev_click, self.building_manager, self.permit_manager, self.resources)
            self.assertEqual(action, "select_permit_category_brewery")
            self.assertEqual(ui.selected_permit_category, "brewery")

            # In category view, brewery issue button is automatically available
            ui._draw_permit_tab(surf, 210, 110, self.permit_manager, self.building_manager)
            self.assertIn("brewery_zone", ui.permit_btn_rects)
        finally:
            # Clean up dynamic registration
            if "brewery_zone" in PERMIT_TYPES:
                del PERMIT_TYPES["brewery_zone"]

    def test_17_building_categories_dynamic_discovery(self):
        """17. Dynamically discover building & structure categories from config with zero hardcoding."""
        from game.data.config import get_building_categories
        cats = get_building_categories()
        cat_ids = [c["id"] for c in cats]
        self.assertIn("structure", cat_ids)
        self.assertIn("public_structure", cat_ids)
        self.assertIn("furniture", cat_ids)

        for c in cats:
            self.assertIn("name", c)
            self.assertIn("desc", c)
            self.assertIn("building_types", c)
            self.assertIn("color", c)

    def test_18_building_tab_screen1_lists_categories_and_badges(self):
        """18. Screen 1 of Buildings tab lists all categories with built counts and structure categories."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 0
        ui.selected_building_category = None

        # Add a wooden building
        b1 = Building("wooden_structure", {(1, 1), (1, 2), (2, 1), (2, 2)})
        self.building_manager.buildings.append(b1)

        surf = pygame.Surface((1280, 720))
        ui._draw_building_tab(surf, 210, 110, self.building_manager, self.permit_manager, self.resources, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)

        # All categories present
        self.assertIn("structure", ui.building_category_btn_rects)
        self.assertIn("public_structure", ui.building_category_btn_rects)
        self.assertIn("furniture", ui.building_category_btn_rects)

    def test_19_building_tab_screen2_filtered_category_view_and_back(self):
        """19. Selecting category opens Screen 2 with filtered list, category deeds, and Back button returns to Screen 1."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 0
        ui.selected_building_category = None

        surf = pygame.Surface((1280, 720))
        ui._draw_building_tab(surf, 210, 110, self.building_manager, self.permit_manager, self.resources, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)

        # Click on "Structure" category card
        card_rect = ui.building_category_btn_rects["structure"]
        ev_click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": card_rect.center})
        action = ui.handle_event(ev_click, self.building_manager, self.permit_manager, self.resources)
        self.assertEqual(action, "select_building_category_structure")
        self.assertEqual(ui.selected_building_category, "structure")

        # Now render Screen 2
        ui._draw_building_tab(surf, 210, 110, self.building_manager, self.permit_manager, self.resources, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)
        self.assertIsNotNone(ui.building_category_back_btn_rect)
        self.assertIn("wooden_structure", ui.building_select_rects)
        self.assertIn("stone_structure", ui.building_select_rects)

        # Back button returns to Screen 1
        ev_back = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": ui.building_category_back_btn_rect.center})
        act_back = ui.handle_event(ev_back, self.building_manager, self.permit_manager, self.resources)
        self.assertEqual(act_back, "building_category_back")
        self.assertIsNone(ui.selected_building_category)

    def test_20_building_tab_no_duplicate_permits_list(self):
        """20. Ensure Buildings tab does NOT render duplicate 'Issued Area Permits' list."""
        ui = RaportUI()
        ui._init_fonts()
        ui.is_open = True
        ui.active_tab = 0

        surf = pygame.Surface((1280, 720))
        ui._draw_building_tab(surf, 210, 110, self.building_manager, self.permit_manager, self.resources, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)

        # Permit edit/delete buttons must NOT exist in Buildings tab
        self.assertEqual(len(getattr(ui, "delete_permit_btn_rects", {})), 0)
        self.assertEqual(len(getattr(ui, "edit_permit_btn_rects", {})), 0)

    def test_21_modal_title_and_hud_button_no_raport_desa(self):
        """21. Title bar is strictly 'TOWN LEDGER' and HUD button is 'Town Ledger' without 'RAPORT DESA'."""
        ui = RaportUI()
        ui._init_fonts()
        surf = pygame.Surface((1280, 720))
        ui.draw(surf, self.building_manager, self.permit_manager, self.resources, furniture_manager=self.furniture_manager, villager_manager=self.villager_manager)

        # Rendered text verification: Town Ledger button
        self.assertEqual(ui.btn_left_rect.width, 116)
        # Verify no "RAPORT DESA" anywhere in user facing code
        with open("game/ui/ui_raport.py", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("RAPORT DESA", content)
        self.assertIn('"TOWN LEDGER"', content)
        self.assertIn('"Town Ledger"', content)


if __name__ == "__main__":
    unittest.main()
