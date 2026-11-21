import unittest
import pygame
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.config import TILE_SIZE, AI_NEED_MAX, AI_NEED_FOOD_RESTORE
from game.data.config import is_food_item
from game.entities.villagers import VillagerManager, Family, Villager
from game.buildings.building_manager import BuildingManager
from game.buildings.building import Building
from game.buildings.furniture import FurnitureManager, Furniture
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.systems.market_service import MarketService
from game.systems.market_purchasing import AIFoodPurchasingSystem
from game.systems.currency import to_copper, normalize_wallet
from game.systems.save_system import save_to_slot, load_from_slot
from game.systems.day_cycle import DayCycleSystem
from game.entities.player import Player
from game.entities.servants import ServantManager
from game.schedule import ScheduleManager


class TestAIFoodPurchasingPhysicalWorkflow(unittest.TestCase):
    def setUp(self):
        self.villager_manager = VillagerManager()
        self.building_manager = BuildingManager()
        self.furniture_manager = FurnitureManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()
        self.resources = {"Wood": 100, "Stone": 50, "Potato": 0}

        # Create Family and Villager
        self.fam = Family("fam_1", "Smith")
        self.villager = Villager(1, "John", "Smith", "Male", 30, 2, "Father", "fam_1")
        self.villager.x = 5 * TILE_SIZE
        self.villager.y = 5 * TILE_SIZE
        self.fam.members.append(self.villager)
        self.villager_manager.families.append(self.fam)

        # Create Housing Lot Permit and Chest
        lot_tiles = {(x, y) for x in range(4, 7) for y in range(4, 7)}
        self.permit = self.permit_manager.add_permit("Smith Housing", "housing", lot_tiles)
        self.fam.assigned_permit_id = self.permit.id

        self.chest = Furniture("chest_1", "household_storage", 5, 5, permit_id="test_permit", family_id="fam_1")
        self.chest.inventory = {}
        self.furniture_manager.furnitures.append(self.chest)

        # Create Market Building at (15, 15)
        market_tiles = {(x, y) for x in range(14, 17) for y in range(14, 17)}
        self.market = Building("market", market_tiles, door_pos=(15, 16), door_side="bottom")
        self.market.inventory = {"Potato": 20}
        self.market.prices = {"Potato": 3}  # 3 Copper
        self.market.currency = {"Copper": 50, "Silver": 10, "Gold": 0}
        self.building_manager.buildings.append(self.market)

    def test_01_no_remote_purchasing_must_travel_to_market(self):
        """Acceptance Test 1 & 2: Having coins alone cannot trigger a remote purchase; AI cannot buy without visiting Market."""
        self.villager.hunger = 10.0  # Hungry!
        self.chest.inventory = {"Copper": 20}

        # 1 update tick
        self.villager.update(
            0.1, self.permit_manager, self.building_manager, [], None,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )

        # Villager must NOT have magically bought food remotely!
        # It must be in the process of getting coins from chest
        self.assertEqual(self.villager.task, "BUYING_FOOD_RETRIEVE_COINS")
        self.assertEqual(self.market.inventory["Potato"], 20)  # Stock untouched!
        self.assertLessEqual(self.villager.hunger, 10.0)       # Hunger not magically restored!
        self.assertLess(self.villager.hunger, 20.0)
        self.assertEqual(self.villager.inventory.get("Potato", 0), 0)

    def test_02_household_with_food_never_purchases(self):
        """Acceptance Test 3 & 4: AI checks own household food; if available, does not purchase."""
        self.villager.hunger = 10.0
        self.chest.inventory = {"Potato": 2, "Copper": 20}

        # Villager updates
        self.villager.update(
            0.1, self.permit_manager, self.building_manager, [], None,
            stockpile_manager=self.stockpile_manager,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )

        # Villager task must be SEEKING_FOOD to eat from chest, NOT buying from market
        self.assertEqual(self.villager.task, "SEEKING_FOOD")
        self.assertNotIn("BUYING_FOOD", self.villager.task)
        self.assertEqual(self.market.inventory["Potato"], 20)

    def test_03_coin_retrieval_from_chest(self):
        """Acceptance Test 5: AI retrieves actual coins from household chest before traveling to Market."""
        self.chest.inventory = {"Silver": 2}  # 20 Copper
        self.villager.inventory = {}

        # Retrieve coins for 3 Copper item
        ok, msg = AIFoodPurchasingSystem.retrieve_coins_from_storage(self.villager, 3, self.furniture_manager)
        self.assertTrue(ok)

        # 1 Silver withdrawn from chest into villager inventory
        self.assertEqual(self.villager.inventory.get("Silver", 0), 1)
        self.assertEqual(self.chest.inventory.get("Silver", 0), 1)
        self.assertEqual(to_copper(self.chest.inventory) + to_copper(self.villager.inventory), 20)

    def test_04_nearest_eligible_market_selection(self):
        """Acceptance Test 6 & 7: Selects nearest eligible market selling the requested item with stock."""
        # Market A: far away (x=50, y=50) with Potato at 3c
        far_tiles = {(x, y) for x in range(50, 53) for y in range(50, 53)}
        market_far = Building("market", far_tiles, door_pos=(51, 52), door_side="bottom")
        market_far.inventory = {"Potato": 10}
        market_far.prices = {"Potato": 3}
        self.building_manager.buildings.append(market_far)

        # Market B: nearest (self.market at 15, 15) with Potato at 3c
        # Market C: closest (8, 8) but 0 stock
        near_empty_tiles = {(x, y) for x in range(8, 10) for y in range(8, 10)}
        market_empty = Building("market", near_empty_tiles, door_pos=(8, 9), door_side="bottom")
        market_empty.inventory = {"Potato": 0}
        market_empty.prices = {"Potato": 3}
        self.building_manager.buildings.append(market_empty)

        self.chest.inventory = {"Copper": 20}
        chosen_m, food, price = AIFoodPurchasingSystem.find_nearest_eligible_market(
            self.villager, self.building_manager, furniture_manager=self.furniture_manager
        )

        # Must choose self.market (nearest with stock >= 1)
        self.assertEqual(chosen_m, self.market)
        self.assertEqual(food, "Potato")
        self.assertEqual(price, 3)

    def test_05_transaction_only_at_market_with_exact_change(self):
        """Acceptance Test 8, 9, 10, 11, 12 & 13: Transaction happens at Market, deducts price, returns change."""
        self.villager.inventory = {"Silver": 1}  # 10 Copper
        initial_market_potatoes = self.market.inventory["Potato"]  # 20

        # Execute transaction at market (item price is 3c)
        ok, msg = AIFoodPurchasingSystem.execute_market_transaction(
            self.villager, self.market, "Potato", building_manager=self.building_manager
        )
        self.assertTrue(ok)

        # Market stock decremented
        self.assertEqual(self.market.inventory["Potato"], initial_market_potatoes - 1)
        # Villager received 1 Potato
        self.assertEqual(self.villager.inventory["Potato"], 1)
        # Villager paid 1 Silver (10c) and received 7 Copper change
        self.assertEqual(self.villager.inventory.get("Silver", 0), 0)
        self.assertEqual(self.villager.inventory.get("Copper", 0), 7)
        # Market received 1 Silver and gave 7 Copper change (net +3 Copper)
        self.assertEqual(to_copper(self.villager.inventory) + to_copper(self.market.currency), 10 + 50 + 100)

    def test_06_hauling_home_deposits_change_and_eats_food(self):
        """Acceptance Test 14, 15, 16 & 17: Delivers change to chest, consumes food, restores hunger."""
        self.villager.hunger = 10.0
        self.villager.inventory = {"Potato": 1, "Copper": 7}
        self.chest.inventory = {"Silver": 1}

        AIFoodPurchasingSystem.deliver_and_consume_food(
            self.villager, furniture_manager=self.furniture_manager, stockpile_manager=self.stockpile_manager
        )

        # Change returned to chest
        self.assertEqual(self.chest.inventory.get("Copper", 0), 7)
        self.assertEqual(self.chest.inventory.get("Silver", 0), 1)
        # Food consumed from inventory
        self.assertEqual(self.villager.inventory.get("Potato", 0), 0)
        # Hunger recovered!
        self.assertEqual(self.villager.hunger, min(AI_NEED_MAX, 10.0 + AI_NEED_FOOD_RESTORE))
        self.assertEqual(self.villager.daily_food_consumed, 1)
        self.assertEqual(self.villager.task, "IDLE")

    def test_07_duplicate_purchase_prevention_between_family_members(self):
        """Acceptance Test 18: Multiple household members do not create unnecessary duplicate purchases."""
        # Add second family member (Alice)
        alice = Villager(2, "Alice", "Smith", "Female", 28, 2, "Mother", "fam_1")
        self.fam.members.append(alice)

        # John is currently travelling to market to buy food
        self.villager.task = "BUYING_FOOD_TRAVEL_TO_MARKET"

        # Check Alice
        is_buying = AIFoodPurchasingSystem.is_family_member_purchasing_food(alice, self.villager_manager)
        self.assertTrue(is_buying)

    def test_08_failed_transaction_safely_returns_coins(self):
        """Acceptance Test 19: If market stock is depleted, coins are returned safely with zero loss."""
        self.villager.inventory = {"Silver": 1}
        self.chest.inventory = {}
        # Deplete market stock
        self.market.inventory["Potato"] = 0

        # Attempt transaction
        ok, msg = AIFoodPurchasingSystem.execute_market_transaction(
            self.villager, self.market, "Potato", building_manager=self.building_manager
        )
        self.assertFalse(ok)

        # Villager returns coins to storage
        AIFoodPurchasingSystem.return_coins_to_storage(self.villager, furniture_manager=self.furniture_manager)
        self.assertEqual(self.chest.inventory.get("Silver", 0), 1)
        self.assertEqual(self.villager.inventory.get("Silver", 0), 0)
        self.assertEqual(self.villager.task, "IDLE")

    def test_09_save_load_preserves_purchasing_task(self):
        """Acceptance Test 20: Save/load correctly preserves active purchasing tasks."""
        self.villager.task = "BUYING_FOOD_TRAVEL_TO_MARKET"
        self.villager.inventory = {"Silver": 1}

        day_cycle = DayCycleSystem()
        player = Player(0.0, 0.0)
        servant_manager = ServantManager()
        schedule_manager = ScheduleManager()

        success, msg = save_to_slot(
            88, day_cycle, self.resources, player, self.permit_manager,
            self.building_manager, self.stockpile_manager, self.furniture_manager,
            self.villager_manager, servant_manager, schedule_manager
        )
        self.assertTrue(success)

        # Load back
        loaded_vil_mgr = VillagerManager()
        loaded_bld_mgr = BuildingManager()
        loaded_furn_mgr = FurnitureManager()
        loaded_permit_mgr = PermitManager()

        success, msg = load_from_slot(
            88, day_cycle, {}, player, loaded_permit_mgr,
            loaded_bld_mgr, self.stockpile_manager, loaded_furn_mgr,
            loaded_vil_mgr, servant_manager, schedule_manager
        )
        self.assertTrue(success)

        all_vils = loaded_vil_mgr.get_all_villagers()
        loaded_vil = next((v for v in all_vils if v.id == 1), None)
        self.assertIsNotNone(loaded_vil)
        self.assertEqual(loaded_vil.task, "BUYING_FOOD_TRAVEL_TO_MARKET")
        self.assertEqual(loaded_vil.inventory.get("Silver", 0), 1)


if __name__ == "__main__":
    unittest.main()
