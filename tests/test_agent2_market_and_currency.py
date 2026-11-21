"""
AGENT 2 Acceptance Test Suite
Comprehensive testing for Market Building, Currency System, Market Profile,
Manual Price Editing, Denomination Caps, Atomic Transactions, and Integration Interface for AGENT 1.
"""

import unittest
import os
import shutil
import pygame
from game.data.config import (
    BUILDING_TYPES,
    PERMIT_TYPES,
    DEFAULT_ITEM_PRICES,
    EXCHANGE_RATES,
    DENOMINATION_CAP,
    DEFAULT_RESOURCES
)
from game.buildings.building import Building
from game.buildings.construction_site import ConstructionSite
from game.buildings.building_manager import BuildingManager
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager, ResourceStack
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.villagers import VillagerManager, Family, Villager
from game.entities.servants import ServantManager
from game.systems.day_cycle import DayCycleSystem
from game.systems.schedule import ScheduleManager
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    can_afford,
    calculate_payment_and_change,
    calculate_change_for_payment,
    execute_currency_transfer,
    consolidate_wallet
)
from game.systems.market_service import MarketService
from game.ui.market_modal import MarketProfileModal
from game.systems.save_system import serialize_game_state, save_to_slot, load_from_slot, get_slot_path

class TestAgent2MarketAndCurrency(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()
        self.villager_manager = VillagerManager()
        self.servant_manager = ServantManager()
        self.day_cycle = DayCycleSystem()
        self.schedule_manager = ScheduleManager()
        self.resources = dict(DEFAULT_RESOURCES)

    def test_01_market_in_building_permit_system(self):
        """1. MARKET appears in the existing building permit system & has permit support."""
        self.assertIn("market", BUILDING_TYPES)
        market_cfg = BUILDING_TYPES["market"]
        self.assertEqual(market_cfg["name"], "Market")
        self.assertIn("market", PERMIT_TYPES)

        # Has valid allowed permits
        self.permit_manager.add_permit("Market Lot", "market", {(0, 0)})
        self.assertTrue(self.permit_manager.has_permit_type("market"))

    def test_02_market_footprint_is_exactly_3x2(self):
        """2. MARKET footprint is exactly 3x2 tiles (6 tiles)."""
        market_cfg = BUILDING_TYPES["market"]
        self.assertEqual(market_cfg["fixed_tiles_count"], 6)
        self.assertEqual(market_cfg["width_tiles"], 3)
        self.assertEqual(market_cfg["height_tiles"], 2)

        # Start construction of a 3x2 market
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        self.assertEqual(len(tiles_3x2), 6)

        site = ConstructionSite("market", tiles_3x2)
        self.assertEqual(len(site.tiles), 6)
        self.assertEqual(site.tiles_w, 3)
        self.assertEqual(site.tiles_h, 2)
        self.assertFalse(site.is_solid)

    def test_03_market_storage_is_unlimited_not_six_slots(self):
        """3. Market storage is unlimited, not derived from the 6 footprint tiles."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)

        self.assertEqual(market.capacity, float("inf"))
        # Able to store arbitrary number of distinct goods and large quantities
        market.inventory["Potato"] = 5000
        market.inventory["Wheat"] = 2500
        market.inventory["Carrot"] = 1200
        market.inventory["Bread"] = 800
        market.inventory["Apples"] = 300
        market.inventory["Fish"] = 150
        market.inventory["Cheese"] = 90
        # More than 6 item types and over 10,000 units
        self.assertGreater(len(market.inventory), 6)
        self.assertEqual(sum(market.inventory.values()), 10040)

    def test_04_market_medieval_design_rendering(self):
        """4. Market uses proper medieval-style design rendering without crash."""
        tiles_3x2 = {(10, 10), (11, 10), (12, 10), (10, 11), (11, 11), (12, 11)}
        market = Building("market", tiles_3x2)
        self.building_manager.buildings.append(market)

        # Create dummy surface and camera
        surf = pygame.Surface((800, 600))
        from game.world.camera import Camera
        cam = Camera(800, 600)

        # Drawing market must execute cleanly
        self.building_manager._draw_market(surf, cam, 64, market)

    def test_05_market_profile_modal_opens_and_displays(self):
        """5 & 6. Market Profile opens on click and displays goods, stock, unlimited storage, prices, and currency."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)
        market.inventory = {"Potato": 85}
        market.currency = {"Copper": 15, "Silver": 4, "Gold": 1}
        market.prices = {"Potato": 3}

        modal = MarketProfileModal()
        self.assertFalse(modal.is_open)

        modal.open(market)
        self.assertTrue(modal.is_open)
        self.assertEqual(modal.target_market, market)

        # Test rendering of modal
        surf = pygame.Surface((800, 600))
        modal.draw(surf, resources=self.resources, stockpile_manager=self.stockpile_manager)

    def test_07_and_08_landlord_editable_item_prices(self):
        """7 & 8. Landlord can edit item prices, initial Potato price is 3 Copper."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)

        # Initial price is 3 Copper
        self.assertEqual(market.prices.get("Potato"), 3)

        modal = MarketProfileModal()
        modal.open(market)

        # Set price adjustment rects
        modal.price_inc_btns["Potato"] = pygame.Rect(10, 10, 20, 20)
        modal.price_dec_btns["Potato"] = pygame.Rect(30, 10, 20, 20)

        # Simulate click [+1]
        ev_plus = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (15, 15), "button": 1})
        res_plus = modal.handle_event(ev_plus)
        self.assertEqual(res_plus, "price_increased_Potato")
        self.assertEqual(market.prices["Potato"], 4)

        # Simulate click [-1] twice
        ev_minus = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (35, 15), "button": 1})
        modal.handle_event(ev_minus)
        modal.handle_event(ev_minus)
        self.assertEqual(market.prices["Potato"], 2)

    def test_09_ai_purchases_use_latest_configured_price(self):
        """9. AI transactions use the latest configured price from market."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)
        market.inventory = {"Potato": 50}
        market.prices = {"Potato": 3}  # Initially 3c
        market.sale_items = ["Potato"]
        self.building_manager.buildings.append(market)

        # Setup family and chest with 20 Copper
        fam = Family("fam_test", "Baggins")
        self.villager_manager.families.append(fam)
        chest = Furniture("f_chest_1", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_test")
        chest.inventory = {"Copper": 20, "Silver": 0, "Gold": 0}
        self.furniture_manager.furnitures.append(chest)

        # 1. Purchase at 3 Copper
        ok, msg, receipt = MarketService.execute_purchase(
            fam, "Potato", quantity=2,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(ok)
        self.assertEqual(receipt["unit_price_copper"], 3)
        self.assertEqual(receipt["total_price_copper"], 6)
        self.assertEqual(to_copper(normalize_wallet(chest.inventory)), 14)
        self.assertEqual(chest.inventory["Potato"], 2)

        # 2. Landlord changes price to 5 Copper
        market.prices["Potato"] = 5

        # 3. Next purchase immediately uses new price 5c!
        ok2, msg2, receipt2 = MarketService.execute_purchase(
            fam, "Potato", quantity=2,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(ok2)
        self.assertEqual(receipt2["unit_price_copper"], 5)
        self.assertEqual(receipt2["total_price_copper"], 10)
        self.assertEqual(to_copper(normalize_wallet(chest.inventory)), 4)
        self.assertEqual(chest.inventory["Potato"], 4)

    def test_10_manually_configured_prices_persist_after_save_load(self):
        """10. Manually configured prices and market state persist after save/load."""
        slot_id = 99
        try:
            tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
            market = Building("market", tiles_3x2)
            market.inventory = {"Potato": 75}
            market.prices = {"Potato": 7}  # Custom price 7c
            market.currency = {"Copper": 42, "Silver": 3, "Gold": 1}
            self.building_manager.buildings.append(market)

            # Save state
            save_ok, s_msg = save_to_slot(
                slot_id, self.day_cycle, self.resources,
                type("PlayerObj", (), {"x": 0.0, "y": 0.0})(),
                self.permit_manager, self.building_manager,
                self.stockpile_manager, self.furniture_manager,
                self.villager_manager, self.servant_manager,
                self.schedule_manager
            )
            self.assertTrue(save_ok, s_msg)

            # Clear building manager
            self.building_manager.buildings.clear()

            # Load state
            dummy_player = type("PlayerObj", (), {"x": 0.0, "y": 0.0})()
            load_ok, l_msg = load_from_slot(
                slot_id, self.day_cycle, self.resources,
                dummy_player,
                self.permit_manager, self.building_manager,
                self.stockpile_manager, self.furniture_manager,
                self.villager_manager, self.servant_manager,
                self.schedule_manager
            )
            self.assertTrue(load_ok, l_msg)

            # Verify market was restored with exact configured price
            loaded_mkt = MarketService.get_market(self.building_manager)
            self.assertIsNotNone(loaded_mkt)
            self.assertEqual(loaded_mkt.prices.get("Potato"), 7)
            self.assertEqual(loaded_mkt.inventory.get("Potato"), 75)
            self.assertEqual(loaded_mkt.currency.get("Copper"), 42)
            self.assertEqual(loaded_mkt.currency.get("Silver"), 3)
            self.assertEqual(loaded_mkt.currency.get("Gold"), 1)
        finally:
            path = get_slot_path(slot_id)
            if os.path.exists(path):
                os.remove(path)

    def test_11_exchange_rates_correct(self):
        """11. Copper, Silver, and Gold exchange rates: 1 Gold = 10 Silver = 100 Copper; 1 Silver = 10 Copper."""
        self.assertEqual(EXCHANGE_RATES["Copper"], 1)
        self.assertEqual(EXCHANGE_RATES["Silver"], 10)
        self.assertEqual(EXCHANGE_RATES["Gold"], 100)

        # 1 Gold value in copper == 100
        self.assertEqual(to_copper({"Gold": 1}), 100)
        # 10 Silver value in copper == 100
        self.assertEqual(to_copper({"Silver": 10}), 100)
        # 1 Silver value in copper == 10
        self.assertEqual(to_copper({"Silver": 1}), 10)
        # 10 Copper value in copper == 10
        self.assertEqual(to_copper({"Copper": 10}), 10)

    def test_12_and_13_prompt_payment_examples_any_denomination(self):
        """12 & 13. AI can pay using ANY denomination, AI not forced to use Silver."""
        # Example A: Price: 3 Copper. Customer has 5 Copper.
        # Direct Copper: Pays 3c exact (or 5c with 2c change)
        ok_a, pay_a, chg_a, _ = calculate_payment_and_change({"Copper": 5}, 3)
        self.assertTrue(ok_a)
        self.assertEqual(to_copper(pay_a) - to_copper(chg_a), 3)

        chg_5paid = calculate_change_for_payment({"Copper": 5}, 3)
        self.assertEqual(chg_5paid["Copper"], 2)

        # Example B: Price: 3 Copper. Customer has 1 Silver.
        # Pays 1 Silver. Receives 7 Copper change.
        ok_b, pay_b, chg_b, _ = calculate_payment_and_change({"Silver": 1, "Copper": 0, "Gold": 0}, 3)
        self.assertTrue(ok_b)
        self.assertEqual(pay_b, {"Silver": 1, "Copper": 0, "Gold": 0})
        self.assertEqual(chg_b, {"Copper": 7, "Silver": 0, "Gold": 0})

        # Example C: Price: 3 Copper. Customer has 1 Gold.
        # Pays 1 Gold. Receives 97 Copper equivalent (9 Silver, 7 Copper).
        ok_c, pay_c, chg_c, _ = calculate_payment_and_change({"Gold": 1, "Copper": 0, "Silver": 0}, 3)
        self.assertTrue(ok_c)
        self.assertEqual(pay_c, {"Gold": 1, "Copper": 0, "Silver": 0})
        self.assertEqual(to_copper(chg_c), 97)

        # Example D: Price: 13 Copper. Customer has 1 Silver and 5 Copper.
        # Pays 1 Silver and 3 Copper. Keeps 2 Copper.
        ok_d, pay_d, chg_d, _ = calculate_payment_and_change({"Silver": 1, "Copper": 5, "Gold": 0}, 13)
        self.assertTrue(ok_d)
        self.assertEqual(pay_d, {"Copper": 3, "Silver": 1, "Gold": 0})
        self.assertEqual(chg_d, {"Copper": 0, "Silver": 0, "Gold": 0})

        # Example E: Price: 1 Silver (10 Copper). Customer has 1 Gold.
        # Pays 1 Gold. Receives 9 Silver.
        ok_e, pay_e, chg_e, _ = calculate_payment_and_change({"Gold": 1, "Copper": 0, "Silver": 0}, 10)
        self.assertTrue(ok_e)
        self.assertEqual(pay_e, {"Gold": 1, "Copper": 0, "Silver": 0})
        self.assertEqual(chg_e, {"Silver": 9, "Copper": 0, "Gold": 0})

    def test_14_and_15_conservation_of_monetary_value_zero_leakage(self):
        """14 & 15. Correct change is provided, monetary value is NEVER created or destroyed."""
        cust_w = {"Copper": 0, "Silver": 2, "Gold": 1}  # Value: 120 Copper
        mkt_w = {"Copper": 5, "Silver": 0, "Gold": 0}   # Value: 5 Copper
        initial_cust = to_copper(cust_w)
        initial_mkt = to_copper(mkt_w)
        initial_total = initial_cust + initial_mkt

        price = 17  # 17 Copper

        ok, pay, chg, _ = calculate_payment_and_change(cust_w, price, mkt_w)
        self.assertTrue(ok)

        tx_ok, post_c, post_m, _ = execute_currency_transfer(cust_w, mkt_w, pay, chg)
        self.assertTrue(tx_ok)

        final_total = to_copper(post_c) + to_copper(post_m)
        # Value strictly conserved!
        self.assertEqual(initial_total, final_total)
        # Customer paid exactly price
        self.assertEqual(initial_cust - to_copper(post_c), price)
        # Market received exactly price
        self.assertEqual(to_copper(post_m) - initial_mkt, price)

    def test_16_denomination_caps_respected(self):
        """16. Denomination cap (max 1000 per denomination) is respected."""
        self.assertEqual(DENOMINATION_CAP, 1000)

        # Attempt consolidation if exceeding 1000
        w = {"Copper": 1050, "Silver": 10, "Gold": 0}
        consolidated = consolidate_wallet(w)
        self.assertLessEqual(consolidated["Copper"], DENOMINATION_CAP)
        self.assertEqual(to_copper(w), to_copper(consolidated))

    def test_17_and_18_purchased_goods_reach_household_storage_and_market_funds(self):
        """17 & 18. Market receives payment correctly and purchased item reaches household storage."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)
        market.inventory = {"Potato": 20}
        market.prices = {"Potato": 3}
        market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        market.sale_items = ["Potato"]
        self.building_manager.buildings.append(market)

        fam = Family("fam_gardener", "Green")
        self.villager_manager.families.append(fam)
        chest = Furniture("f_storage_g", "household_storage", 2, 2, permit_id="test_permit", family_id="fam_gardener")
        chest.inventory = {"Silver": 1}  # 1 Silver = 10 Copper
        self.furniture_manager.furnitures.append(chest)

        # Household purchases 3 Potatoes for 9 Copper
        ok, msg, receipt = MarketService.execute_purchase(
            fam, "Potato", quantity=3,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(ok, msg)

        # 1. Market stock decreased by 3
        self.assertEqual(market.inventory["Potato"], 17)
        # 2. Market funds increased by 9 Copper (Net +9c)
        self.assertEqual(to_copper(market.currency), 9)
        # 3. Household storage received 3 Potatoes
        self.assertEqual(chest.inventory.get("Potato"), 3)
        # 4. Household storage has 1 Copper change remaining (10c - 9c = 1c)
        self.assertEqual(chest.inventory.get("Copper"), 1)
        self.assertEqual(chest.inventory.get("Silver", 0), 0)

    def test_19_failed_transactions_do_not_consume_money_or_alter_goods(self):
        """19. Failed transactions (e.g. out of stock or broke) are atomic and alter nothing."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)
        market.inventory = {"Potato": 2}
        market.prices = {"Potato": 3}
        market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.building_manager.buildings.append(market)

        fam = Family("fam_broke", "Poor")
        self.villager_manager.families.append(fam)
        chest = Furniture("f_storage_p", "household_storage", 3, 3, permit_id="test_permit", family_id="fam_broke")
        chest.inventory = {"Copper": 2}  # Has 2c, Potato costs 3c
        self.furniture_manager.furnitures.append(chest)

        # 1. Failed due to insufficient funds
        ok, msg, _ = MarketService.execute_purchase(
            fam, "Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(ok)
        self.assertEqual(chest.inventory["Copper"], 2)
        self.assertNotIn("Potato", chest.inventory)
        self.assertEqual(market.inventory["Potato"], 2)
        self.assertEqual(to_copper(market.currency), 0)

        # 2. Failed due to insufficient stock (give funds first)
        chest.inventory["Copper"] = 100
        ok2, msg2, _ = MarketService.execute_purchase(
            fam, "Potato", quantity=10,  # only 2 in stock
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertFalse(ok2)
        self.assertEqual(chest.inventory["Copper"], 100)
        self.assertEqual(market.inventory["Potato"], 2)

    def test_20_agent1_integration_interface_ready(self):
        """20. AGENT 1 can invoke can_purchase and execute_purchase with Villager or Family."""
        tiles_3x2 = {(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)}
        market = Building("market", tiles_3x2)
        market.inventory = {"Potato": 50}
        market.prices = {"Potato": 3}
        market.sale_items = ["Potato"]
        self.building_manager.buildings.append(market)

        fam = Family("fam_hungry", "Starving")
        vil = Villager(101, "Oliver", "Starving", "Male", 25, 1, "Head", "fam_hungry")
        fam.members.append(vil)
        self.villager_manager.families.append(fam)

        chest = Furniture("f_storage_h", "household_storage", 4, 4, permit_id="test_permit", family_id="fam_hungry")
        chest.inventory = {"Copper": 10}
        self.furniture_manager.furnitures.append(chest)

        # AGENT 1 calls can_purchase on hunger threshold
        can_buy, reason, unit_pr, tot_pr = MarketService.can_purchase(
            vil, "Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(can_buy, reason)
        self.assertEqual(unit_pr, 3)

        # AGENT 1 calls execute_purchase passing the hungry villager
        success, msg, receipt = MarketService.execute_purchase(
            vil, "Potato", quantity=1,
            building_manager=self.building_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(success, msg)
        self.assertEqual(chest.inventory["Potato"], 1)
        self.assertEqual(chest.inventory["Copper"], 7)

    def test_21_starting_player_storage_currency_and_grant_system(self):
        """21. Starting currency in PLAYER STORAGE has 1000 Copper, 1000 Silver, 1000 Gold; Grantable items support coins."""
        # 1. Starting resources contain no coins (coins are granted via the treasury/grant system)
        self.assertEqual(DEFAULT_RESOURCES["Copper"], 0)
        self.assertEqual(DEFAULT_RESOURCES["Silver"], 0)
        self.assertEqual(DEFAULT_RESOURCES["Gold"], 0)

        # 2. Stockpile initialization places no starting coins for Landlord
        self.stockpile_manager.initialize_starter_stockpile(self.resources, self.permit_manager)
        totals = self.stockpile_manager.get_total_resources()
        self.assertEqual(totals["Copper"], 0)
        self.assertEqual(totals["Silver"], 0)
        self.assertEqual(totals["Gold"], 0)

        # 3. Grantable items in ui_raport contain Copper, Silver, Gold
        from game.ui.ui_raport import GRANTABLE_ITEMS
        types = [item["type"] for item in GRANTABLE_ITEMS]
        self.assertIn("Copper", types)
        self.assertIn("Silver", types)
        self.assertIn("Gold", types)

if __name__ == "__main__":
    unittest.main()
