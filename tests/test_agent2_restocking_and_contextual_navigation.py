import unittest
import pygame
from game.config import TILE_SIZE
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.permits import AreaPermit, PermitManager
from game.entities.servants import Servant, ServantManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.ui.modals.market_modal import MarketProfileModal
from game.ui.ui_raport import RaportUI
from game.world.stockpile import StockpileManager, ResourceStack
from game.buildings.furniture import Furniture, FurnitureManager

class TestAgent2RestockingAndContextualNavigation(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.servant_manager = ServantManager()
        self.villager_manager = VillagerManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()
        self.resources = {"Wood": 100, "Stone": 100, "Food": 50, "Potato": 50}

        # Market building
        market_tiles = {(5, 5), (5, 6), (6, 5), (6, 6)}
        self.market = Building("market", market_tiles, door_pos=(5, 5), door_side="top")
        self.market.inventory = {"Potato": 0}
        self.market.prices = {"Potato": 10}
        self.building_manager.buildings.append(self.market)

        # Landlord food stockpile stack
        self.food_stack = ResourceStack("Potato", amount=30, grid_x=10, grid_y=10, owner_type="landlord", owner_id=None)
        self.stockpile_manager.stacks.append(self.food_stack)

    def test_01_add_stock_creates_restock_order_no_instant_transfer(self):
        """1. Clicking Add Stock creates a restock order and does NOT magically increase market inventory."""
        modal = MarketProfileModal()
        modal.open(self.market)
        surface = pygame.Surface((1280, 720))
        modal.draw(surface, self.resources, self.stockpile_manager, servant_manager=self.servant_manager)
        initial_stock = self.market.inventory.get("Potato", 0)

        # Simulate clicking deposit (+10 stock)
        rect = modal.stock_dep_btns["Potato"]
        click_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": rect.center})
        action = modal.handle_event(click_event, self.resources, self.stockpile_manager, servant_manager=self.servant_manager)

        self.assertEqual(action, "restock_order_created_Potato")
        # Market inventory must NOT have increased yet!
        self.assertEqual(self.market.inventory.get("Potato", 0), initial_stock)
        # Order exists in servant manager
        self.assertEqual(len(self.servant_manager.restock_orders), 1)
        order = self.servant_manager.restock_orders[0]
        self.assertEqual(order["amount"], 10)
        self.assertEqual(order["delivered"], 0)

    def test_02_in_transit_indicator_reflects_active_restock_orders(self):
        """2. Market UI shows (+X in transit) while restocking orders are being hauled."""
        self.servant_manager.add_restock_order(self.market, "Potato", 10, stockpile_manager=self.stockpile_manager)
        in_transit = self.servant_manager.get_in_transit_for_market(self.market, "Potato")
        self.assertEqual(in_transit, 10)

    def test_03_physical_servant_restocking_delivery_lifecycle(self):
        """3. Servant transitions IDLE -> RESTOCK_FETCH -> retrieves items -> RESTOCK_DELIVER -> deposits to Market."""
        order = self.servant_manager.add_restock_order(self.market, "Potato", 5, stockpile_manager=self.stockpile_manager)
        servant = self.servant_manager.servants[0]
        servant.x = (self.food_stack.grid_x + 0.5) * TILE_SIZE
        servant.y = (self.food_stack.grid_y + 0.5) * TILE_SIZE

        # 1. Assignment
        servant._evaluate_and_assign_priority_task(
            self.building_manager,
            self.permit_manager,
            self.stockpile_manager,
            self.resources,
            None,
            all_servants=self.servant_manager.servants,
            servant_manager=self.servant_manager
        )
        self.assertEqual(servant.state, "RESTOCK_FETCH")
        self.assertEqual(servant.target_restock_amount, 5)

        # 2. Fetching at stockpile
        servant.update(
            0.1,
            self.building_manager,
            self.permit_manager,
            self.stockpile_manager,
            self.resources,
            None,
            all_servants=self.servant_manager.servants,
            servant_manager=self.servant_manager
        )
        self.assertEqual(servant.state, "RESTOCK_DELIVER")
        self.assertEqual(servant.carried_res, "Potato")
        self.assertEqual(servant.carried_amount, 5)
        self.assertEqual(self.food_stack.amount, 25)

        # 3. Deliver to Market
        dest = self.market.get_center_world(TILE_SIZE)
        servant.x, servant.y = dest[0], dest[1]
        servant.update(
            0.1,
            self.building_manager,
            self.permit_manager,
            self.stockpile_manager,
            self.resources,
            None,
            all_servants=self.servant_manager.servants,
            servant_manager=self.servant_manager
        )
        # Deposited into Market inventory!
        self.assertEqual(self.market.inventory.get("Potato", 0), 5)
        self.assertIsNone(servant.carried_res)
        self.assertEqual(servant.carried_amount, 0)
        self.assertEqual(len(self.servant_manager.restock_orders), 0)

    def test_04_open_household_directly_navigation(self):
        """4. Contextual View: open_household_directly navigates to Town Ledger Household tab with selected family."""
        raport = RaportUI()
        self.assertFalse(raport.is_open)

        raport.open_household_directly("fam_brewer")
        self.assertTrue(raport.is_open)
        self.assertEqual(raport.active_tab, 4)
        self.assertEqual(raport.selected_family_id, "fam_brewer")
        self.assertFalse(raport.show_household_possession)

    def test_05_open_possession_directly_navigation(self):
        """5. Contextual View: open_possession_directly navigates to family's actual possessions view."""
        raport = RaportUI()
        raport.open_possession_directly("fam_brewer")
        self.assertTrue(raport.is_open)
        self.assertEqual(raport.active_tab, 4)
        self.assertEqual(raport.selected_family_id, "fam_brewer")
        self.assertTrue(raport.show_household_possession)

    def test_06_open_permit_directly_navigation(self):
        """6. Contextual View: open_permit_directly navigates to exact permit in its category."""
        p = AreaPermit("permit_test_farm", "Farm Lot #1", "farm", {(10, 10)})
        self.permit_manager.permits.append(p)

        raport = RaportUI()
        raport.open_permit_directly("permit_test_farm", self.permit_manager)
        self.assertTrue(raport.is_open)
        self.assertEqual(raport.active_tab, 1)
        self.assertEqual(raport.selected_permit_inspect_id, "permit_test_farm")
        self.assertEqual(raport.selected_permit_category, "farm")

    def test_07_open_building_directly_navigation(self):
        """7. Contextual View: open_building_directly navigates to building in its category."""
        raport = RaportUI()
        raport.open_building_directly(self.market)
        self.assertTrue(raport.is_open)
        self.assertEqual(raport.active_tab, 0)
        self.assertEqual(raport.selected_building_category, "market")
        self.assertEqual(raport.selected_building_inspect, self.market)

    def test_08_cross_tab_navigation_buttons(self):
        """8. Cross-tab navigation from Permit to Household and from Building to Household."""
        v = Villager("vil_1", "Hugh", "Brewer", "male", 40, 1, "Father", "fam_1")
        fam = Family("fam_1", "Brewer", [v])
        fam.assigned_permit_id = "permit_1"
        self.villager_manager.families = [fam]

        p = AreaPermit("permit_1", "Housing Lot #1", "housing", {(10, 10)})
        p.assigned_family_id = "fam_1"
        self.permit_manager.permits = [p]

        b = Building("wooden_structure", {(10, 10)}, door_pos=(10, 10))
        self.building_manager.buildings = [b]

        raport = RaportUI()
        # Open Ledger to Building tab
        raport.open_building_directly(b)
        surface = pygame.Surface((1280, 720))
        raport.draw(surface, self.building_manager, self.permit_manager, self.resources, self.servant_manager, self.villager_manager, furniture_manager=self.furniture_manager)

        # Contextual Household button must be generated for occupied building
        self.assertIn(b, raport.building_household_btn_rects)
        btn_rect, fid = raport.building_household_btn_rects[b]
        self.assertEqual(fid, "fam_1")

        # Simulate click on Household button
        click_evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": btn_rect.center})
        res = raport.handle_event(click_evt, self.building_manager, self.permit_manager, self.resources, servant_manager=self.servant_manager, villager_manager=self.villager_manager)
        self.assertEqual(res, "open_household_fam_1")
        self.assertEqual(raport.active_tab, 4)
        self.assertEqual(raport.selected_family_id, "fam_1")

if __name__ == "__main__":
    unittest.main()
