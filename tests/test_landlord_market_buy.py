import unittest
import pygame
from game.config import TILE_SIZE
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.permits import PermitManager
from game.entities.servants import ServantManager
from game.entities.villagers import VillagerManager
from game.world.stockpile import StockpileManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.systems.lord_treasury import LordTreasurySystem
from game.systems.currency import to_copper
from game.systems.market_service import MarketService


class TestLandlordMarketBuy(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.servant_manager = ServantManager()
        self.villager_manager = VillagerManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()
        self.resources = {"Wood": 100, "Stone": 100, "Food": 50, "Potato": 50}

        # Household-assigned market stall selling Potato
        market_tiles = {(5, 5), (5, 6), (6, 5), (6, 6)}
        self.market = Building("market", market_tiles, door_pos=(5, 5), door_side="top")
        self.market.assigned_family_id = "fam_a"
        self.market.auto_pricing = True
        self.market.sale_items = ["Potato"]
        self.market.inventory = {"Potato": 30}
        self.market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.building_manager.buildings.append(self.market)

        # Lord Treasury Chest with coins
        self.chest = Furniture("treasury_1", "lord_treasury_chest", 20, 20)
        self.furniture_manager.furnitures.append(self.chest)
        self.chest.store_item("Gold", 2)  # 200c

        self.price = MarketService.get_item_price("Potato", self.market)
        self.assertGreater(self.price, 0)

    def _update(self, servant, dt=0.1):
        servant.update(
            dt, self.building_manager, self.permit_manager, self.stockpile_manager,
            self.resources, None,
            all_servants=self.servant_manager.servants,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            servant_manager=self.servant_manager,
        )

    def _evaluate(self, servant):
        servant._evaluate_and_assign_priority_task(
            self.building_manager, self.permit_manager, self.stockpile_manager,
            self.resources, None,
            all_servants=self.servant_manager.servants,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager,
            servant_manager=self.servant_manager,
        )

    def _teleport_to(self, servant, pos):
        servant.x, servant.y = pos

    def test_01_add_buy_order_validation(self):
        # Unassigned market rejected
        self.market.assigned_family_id = None
        self.assertIsNone(self.servant_manager.add_buy_order(self.market, "Potato", 5))
        self.market.assigned_family_id = "fam_a"
        # Out-of-stock item rejected
        self.assertIsNone(self.servant_manager.add_buy_order(self.market, "Wood", 5))
        # Valid order created
        order = self.servant_manager.add_buy_order(self.market, "Potato", 5)
        self.assertIsNotNone(order)
        self.assertEqual(order["quantity"], 5)
        self.assertEqual(len(self.servant_manager.buy_orders), 1)

    def test_02_full_buy_lifecycle(self):
        qty = 4
        total_cost = self.price * qty
        treasury_before = LordTreasurySystem.value(self.furniture_manager)
        market_before = self.market.inventory["Potato"]

        order = self.servant_manager.add_buy_order(self.market, "Potato", qty)
        self.assertIsNotNone(order)

        servant = self.servant_manager.servants[0]
        self._evaluate(servant)
        self.assertEqual(servant.state, "BUY_FETCH")
        self.assertEqual(servant.target_buy_chunk, min(50, qty))

        # Arrive at treasury -> coins withdrawn into buy_wallet
        self._teleport_to(servant, servant.target_buy_fetch_pos)
        self._update(servant)
        self.assertEqual(servant.state, "BUY_GO_MARKET")
        self.assertGreater(to_copper(servant.buy_wallet), 0)
        self.assertEqual(
            LordTreasurySystem.value(self.furniture_manager),
            treasury_before - to_copper(servant.buy_wallet))

        # Arrive at market -> purchase executes
        self._teleport_to(servant, servant.target_buy_market_pos)
        self._update(servant)
        self.assertEqual(servant.state, "BUY_DELIVER")
        self.assertEqual(servant.carried_res, "Potato")
        self.assertEqual(servant.carried_amount, qty)
        self.assertEqual(self.market.inventory["Potato"], market_before - qty)
        # Stall earned the sale price (payment minus change stays in market.currency)
        self.assertGreater(to_copper(self.market.currency), 0)
        self.assertLessEqual(to_copper(self.market.currency), total_cost)

        # Arrive at drop tile -> goods become landlord-owned stock
        self._teleport_to(servant, servant.target_buy_drop_pos)
        self._update(servant)
        self.assertEqual(servant.state, "BUY_RETURN")
        self.assertIsNone(servant.carried_res)
        landlord_stacks = [s for s in self.stockpile_manager.stacks
                           if s.resource_type == "Potato" and s.owner_type == "landlord"]
        self.assertTrue(any(s.amount >= qty for s in landlord_stacks))

        # Return to treasury -> change deposited, order completed & removed
        self._teleport_to(servant, servant.target_buy_fetch_pos)
        self._update(servant)
        self.assertEqual(len(self.servant_manager.buy_orders), 0)
        self.assertEqual(servant.buy_wallet, {})
        # Treasury lost exactly the sale price
        self.assertEqual(
            LordTreasurySystem.value(self.furniture_manager),
            treasury_before - total_cost)

    def test_03_partial_fill_when_stock_runs_out(self):
        # Stock only 2 but order wants 5 -> first chunk buys 2, second finds 0
        self.market.inventory["Potato"] = 2
        order = self.servant_manager.add_buy_order(self.market, "Potato", 5)
        self.assertIsNotNone(order)
        servant = self.servant_manager.servants[0]
        self._evaluate(servant)
        self._teleport_to(servant, servant.target_buy_fetch_pos)
        self._update(servant)
        self._teleport_to(servant, servant.target_buy_market_pos)
        self._update(servant)
        # Only 2 purchased (chunk capped by stock at assignment AND at purchase)
        self.assertLessEqual(servant.carried_amount, 2)
        self.assertEqual(self.market.inventory.get("Potato", 0), 0)

    def test_04_market_currency_and_treasury_conservation(self):
        qty = 3
        treasury_before = LordTreasurySystem.value(self.furniture_manager)
        self.servant_manager.add_buy_order(self.market, "Potato", qty)
        servant = self.servant_manager.servants[0]
        self._evaluate(servant)
        self._teleport_to(servant, servant.target_buy_fetch_pos)
        self._update(servant)
        self._teleport_to(servant, servant.target_buy_market_pos)
        self._update(servant)
        self._teleport_to(servant, servant.target_buy_drop_pos)
        self._update(servant)
        self._teleport_to(servant, servant.target_buy_fetch_pos)
        self._update(servant)
        spent = treasury_before - LordTreasurySystem.value(self.furniture_manager)
        gained = to_copper(self.market.currency)
        self.assertEqual(spent, gained)

    def test_05_buy_button_only_on_assigned_stall(self):
        from game.ui.market_modal import MarketProfileModal
        modal = MarketProfileModal()
        surface = pygame.Surface((1280, 720))

        # Assigned household stall -> BUY button rendered
        modal.open(self.market)
        modal.draw(surface, self.resources, self.stockpile_manager,
                   servant_manager=self.servant_manager,
                   villager_manager=self.villager_manager,
                   furniture_manager=self.furniture_manager)
        self.assertIn("Potato", modal.buy_btns)
        self.assertIn("Potato", modal.buy_qty_rects)

        # Unassigned (landlord) stall -> no BUY controls
        self.market.assigned_family_id = None
        modal.open(self.market)
        modal.draw(surface, self.resources, self.stockpile_manager,
                   servant_manager=self.servant_manager,
                   villager_manager=self.villager_manager,
                   furniture_manager=self.furniture_manager)
        self.assertEqual(modal.buy_btns, {})
        self.assertEqual(modal.buy_qty_rects, {})


if __name__ == "__main__":
    unittest.main()
