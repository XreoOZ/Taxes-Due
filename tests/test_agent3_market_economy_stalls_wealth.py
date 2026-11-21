"""
Unit tests for AGENT 3 — MARKET ECONOMY, HOUSEHOLD STALLS, VILLAGE WEALTH & RESOURCE TRANSACTIONS
"""
import unittest
import math
from game.buildings.buildings import Building, BuildingManager, DemolitionSite
from game.buildings.furniture import Furniture, FurnitureManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.stockpile import StockpileManager, ResourceStack
from game.permits import AreaPermit, PermitManager
from game.systems.market_pricing import MarketPricingSystem
from game.systems.household_stall_system import HouseholdStallSystem
from game.systems.wealth_system import VillageWealthSystem
from game.systems.market_service import MarketService
from game.systems.market_purchasing import AIMarketPurchasingSystem
from game.systems.save_system import serialize_game_state, deserialize_game_state


class TestMarketEconomyStallsWealth(unittest.TestCase):
    def setUp(self):
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.sm = StockpileManager()
        self.pm = PermitManager()

    def test_1_market_initial_stock_zero(self):
        """1. Market Initial Stock Bug: New market starts with 0 stock, no free starting items."""
        tiles = {(10, 10), (10, 11), (11, 10), (11, 11)}
        market = Building("market", tiles)
        self.assertEqual(market.inventory, {}, "Newly created market must start with empty inventory (zero stock)")
        self.assertEqual(market.currency, {"Copper": 0, "Silver": 0, "Gold": 0})
        self.assertIsNone(market.assigned_family_id)
        self.assertIsNone(market.assigned_household_id)

    def test_2_household_stall_assignment_and_allocation(self):
        """2. Household Stall System: Assignment, unassignment, and per-item percentage allocation."""
        tiles = {(10, 10), (10, 11)}
        market = Building("market", tiles)
        family_id = "fam_brewer"

        # Assign stall
        HouseholdStallSystem.assign_stall(market, family_id)
        self.assertEqual(market.assigned_family_id, family_id)
        self.assertEqual(market.assigned_household_id, family_id)
        self.assertEqual(market.owner, family_id)

        # Set allocation percentage
        HouseholdStallSystem.set_item_allocation(market, "Potato", 50)
        self.assertEqual(HouseholdStallSystem.get_item_allocation(market, "Potato"), 50)

        # Create household chest with 100 potatoes
        chest = Furniture("furn_chest_1", "household_storage", 5, 5, permit_id="test_permit", family_id=family_id)
        chest.inventory = {"Potato": 100}
        self.fm.furnitures.append(chest)

        # Calculate allocatable: 50% of 100 = 50 max allocatable
        allocatable = HouseholdStallSystem.calculate_allocatable_goods(market, family_id, "Potato", self.fm)
        self.assertEqual(allocatable, 50)

        # If market already contains 20 potatoes, remaining allocatable is 30
        market.inventory["Potato"] = 20
        allocatable2 = HouseholdStallSystem.calculate_allocatable_goods(market, family_id, "Potato", self.fm)
        self.assertEqual(allocatable2, 30)

        # Unassign stall
        HouseholdStallSystem.unassign_stall(market)
        self.assertIsNone(market.assigned_family_id)
        self.assertEqual(market.owner, "landlord")

    def test_3_physical_goods_transportation_workflow(self):
        """3. Physical Goods Transportation: AI hauls allocated goods during leisure time without teleporting."""
        tiles = {(10, 10), (10, 11)}
        market = Building("market", tiles, door_pos=(10, 12))
        self.bm.buildings.append(market)
        family_id = "fam_smith"

        HouseholdStallSystem.assign_stall(market, family_id)
        HouseholdStallSystem.set_item_allocation(market, "Potato", 50)

        chest = Furniture("chest_smith", "household_storage", 2, 2, permit_id="test_permit", family_id=family_id)
        chest.inventory = {"Potato": 40}
        self.fm.furnitures.append(chest)

        villager = Villager("vil_1", "John", "Smith", "Male", 30, 2, "Father", family_id=family_id, x=2 * 32, y=2 * 32)
        villager.hunger = 90.0
        villager.thirst = 90.0
        villager.need_toilet = 90.0
        villager.task = "IDLE"

        # Check and start chore
        started = HouseholdStallSystem.check_and_start_stall_chores(villager, self.bm, self.fm, all_entities=[villager])
        self.assertTrue(started)
        self.assertEqual(villager.task, "HAULING_STALL_GOODS_FETCH")

        # Step 1: Arrive at chest and withdraw allocated goods (in-transit)
        # Position villager at chest world pos
        cx, cy = chest.get_world_pos(32)
        villager.x, villager.y = cx, cy
        HouseholdStallSystem.execute_stall_chores_tick(villager, 0.1, self.bm, self.fm, all_entities=[villager], tile_size=32)

        self.assertEqual(villager.task, "HAULING_STALL_GOODS_DELIVER")
        self.assertEqual(villager.inventory.get("Potato"), 20)  # 50% of 40 = 20
        self.assertEqual(chest.inventory.get("Potato"), 20)      # 20 remaining in chest
        self.assertEqual(market.inventory.get("Potato", 0), 0)   # Goods in transit NOT yet in market!

        # Step 2: Arrive at market and deposit goods
        app_x, app_y = market.get_approach_point((villager.x, villager.y), 32, self.bm)
        villager.x, villager.y = app_x, app_y
        HouseholdStallSystem.execute_stall_chores_tick(villager, 0.1, self.bm, self.fm, all_entities=[villager], tile_size=32)

        self.assertEqual(villager.task, "IDLE")
        self.assertEqual(villager.inventory.get("Potato", 0), 0)
        self.assertEqual(market.inventory.get("Potato"), 20)    # Now deposited in market!

    def test_4_automatic_market_pricing_scarcity_curve(self):
        """4. Automatic Market Pricing: Monotonic scarcity curve, min 1 copper, responsive."""
        # Baseline price of Potato is 3 Copper
        # S = 0 -> High scarcity price
        price_0 = MarketPricingSystem.calculate_price("Potato", 0, base_price=3)
        self.assertGreater(price_0, 3)

        # S = 20 -> Baseline stock = baseline price
        price_20 = MarketPricingSystem.calculate_price("Potato", 20, base_price=3)
        self.assertEqual(price_20, 3)

        # S = 100 -> Abundance price
        price_100 = MarketPricingSystem.calculate_price("Potato", 100, base_price=3)
        self.assertLess(price_100, 3)
        self.assertGreaterEqual(price_100, 1)

        # Strictly monotonic non-increasing as stock rises
        prev_p = 999999
        for s in range(0, 120, 10):
            p = MarketPricingSystem.calculate_price("Potato", s, base_price=3)
            self.assertLessEqual(p, prev_p)
            self.assertGreaterEqual(p, 1)
            prev_p = p

    def test_5_household_coin_collection_and_transactions(self):
        """5. Market Sales & Household Coin Collection: Customer pays market, household AI collects to chest."""
        tiles = {(10, 10)}
        market = Building("market", tiles, door_pos=(10, 11))
        self.bm.buildings.append(market)
        family_id = "fam_farmer"
        HouseholdStallSystem.assign_stall(market, family_id)

        market.inventory = {"Potato": 5}
        market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        # Customer buys 1 potato
        buyer = Villager("buyer_1", "Bob", "Buyer", "Male", 25, 2, "Adult Son", x=0, y=0)
        buyer.inventory = {"Copper": 15}

        # Execute purchase
        success, msg = AIMarketPurchasingSystem.execute_market_transaction(buyer, market, "Potato", self.bm)
        self.assertTrue(success, msg)
        self.assertEqual(market.inventory.get("Potato"), 4)
        mkt_copper = market.currency.get("Copper", 0)
        self.assertGreater(mkt_copper, 0)

        # Household AI collects earnings during leisure time
        chest = Furniture("chest_farmer", "household_storage", 1, 1, permit_id="test_permit", family_id=family_id)
        chest.inventory = {}
        self.fm.furnitures.append(chest)

        collector = Villager("vil_col", "Mary", "Farmer", "Female", 28, 2, "Mother", family_id=family_id, x=0, y=0)
        collector.hunger = 90.0
        collector.thirst = 90.0
        collector.need_toilet = 90.0
        collector.task = "IDLE"

        # Check and start coin collection
        started = HouseholdStallSystem.check_and_start_stall_chores(collector, self.bm, self.fm, all_entities=[collector])
        self.assertTrue(started)
        self.assertEqual(collector.task, "HAULING_STALL_COINS_FETCH")

        # Travel to market & withdraw coins
        app_x, app_y = market.get_approach_point((collector.x, collector.y), 32, self.bm)
        collector.x, collector.y = app_x, app_y
        HouseholdStallSystem.execute_stall_chores_tick(collector, 0.1, self.bm, self.fm, all_entities=[collector], tile_size=32)

        self.assertEqual(collector.task, "HAULING_STALL_COINS_DELIVER")
        self.assertEqual(market.currency.get("Copper", 0), 0)
        self.assertEqual(collector.inventory.get("Copper", 0), mkt_copper)

        # Travel to chest & deposit coins
        cx, cy = chest.get_world_pos(32)
        collector.x, collector.y = cx, cy
        HouseholdStallSystem.execute_stall_chores_tick(collector, 0.1, self.bm, self.fm, all_entities=[collector], tile_size=32)

        self.assertEqual(collector.task, "IDLE")
        self.assertEqual(collector.inventory.get("Copper", 0), 0)
        self.assertEqual(chest.inventory.get("Copper"), mkt_copper)

    def test_6_market_destruction_recover_all_contents(self):
        """6. Market Destruction: Dropping all items & coins with preserved ownership."""
        tiles = {(15, 15), (15, 16)}
        market = Building("market", tiles)
        family_id = "fam_merchant"
        HouseholdStallSystem.assign_stall(market, family_id)
        market.inventory = {"Potato": 25, "Bread": 10}
        market.currency = {"Copper": 50, "Silver": 5, "Gold": 1}

        self.bm.buildings.append(market)
        site = DemolitionSite(market)
        self.bm.demolition_sites.append(site)

        resources = {"Wood": 0, "Stone": 0}
        self.bm.complete_demolition(site, resources, stockpile_manager=self.sm)

        # Check market contents dropped as stacks with villager ownership
        dropped_items = {s.resource_type: s.amount for s in self.sm.stacks if s.owner_type == "villager" and s.owner_id == family_id}
        self.assertEqual(dropped_items.get("Potato"), 25)
        self.assertEqual(dropped_items.get("Bread"), 10)
        self.assertEqual(dropped_items.get("Copper"), 50)
        self.assertEqual(dropped_items.get("Silver"), 5)
        self.assertEqual(dropped_items.get("Gold"), 1)

        # Verify building object inventory & currency was emptied (no ghost resources)
        self.assertEqual(market.inventory, {})
        self.assertEqual(market.currency, {})

    def test_7_village_wealth_authoritative_no_double_counting(self):
        """7. Village Wealth: Authoritative calculation without double counting mirrored possessions."""
        fam1 = Family("f1", "Miller")
        m1 = Villager("v1", "Jack", "Miller", "Male", 32, 2, "Father", family_id="f1", x=0, y=0)
        m1.inventory = {"Copper": 10}  # In pocket: 10 Copper
        fam1.members = [m1]
        self.vm.families = [fam1]

        chest1 = Furniture("c1", "household_storage", 3, 3, permit_id="test_permit", family_id="f1")
        chest1.inventory = {"Silver": 2}  # In chest: 2 Silver = 20 Copper
        self.fm.furnitures.append(chest1)

        # Landlord resources: 1 Gold = 100 Copper
        resources = {"Gold": 1, "Copper": 0, "Silver": 0}

        # Market stall assigned to f1: 5 Copper
        tiles = {(5, 5)}
        stall = Building("market", tiles)
        stall.assigned_family_id = "f1"
        stall.currency = {"Copper": 5, "Silver": 0, "Gold": 0}
        self.bm.buildings.append(stall)

        # Unassigned market: 1 Silver = 10 Copper
        tiles2 = {(6, 6)}
        stall2 = Building("market", tiles2)
        stall2.assigned_family_id = None
        stall2.currency = {"Copper": 0, "Silver": 1, "Gold": 0}
        self.bm.buildings.append(stall2)

        wealth = VillageWealthSystem.calculate_village_wealth(
            resources=resources,
            villager_manager=self.vm,
            furniture_manager=self.fm,
            building_manager=self.bm,
            stockpile_manager=self.sm,
            force_recompute=True
        )

        # Landlord: 100 (Gold) + 10 (stall2 Silver) = 110 Copper
        self.assertEqual(wealth["landlord"]["wealth_copper"], 110)

        # Household f1: 10 (m1 pocket) + 20 (chest1 2 Silver) + 5 (stall Copper) = 35 Copper
        hh1 = wealth["households"][0]
        self.assertEqual(hh1["wealth_copper"], 35)

        # Total: 110 + 35 = 145 Copper
        self.assertEqual(wealth["total_wealth_copper"], 145)

        # Percentages
        self.assertAlmostEqual(wealth["landlord"]["percentage"] + hh1["percentage"], 100.0, delta=0.5)

    def test_8_save_load_market_integrity(self):
        """8. Save/Load Integrity: Market allocations, stall assignment, prices persist."""
        tiles = {(12, 12)}
        market = Building("market", tiles, door_pos=(12, 13))
        market.assigned_family_id = "fam_1"
        market.inventory = {"Potato": 15}
        market.currency = {"Copper": 22, "Silver": 2, "Gold": 0}
        market.item_allocations = {"Potato": 60, "Wood": 40}
        market.auto_pricing = True
        self.bm.buildings.append(market)

        from game.systems.day_cycle import DayCycleSystem
        dc = DayCycleSystem()

        class DummyPlayer:
            x = 0.0
            y = 0.0

        class DummyServantManager:
            servants = []

        class DummyScheduleManager:
            job_schedules = {}

        data = serialize_game_state(
            dc, {"Wood": 10}, DummyPlayer(),
            self.pm, self.bm, self.sm, self.fm, self.vm,
            DummyServantManager(), DummyScheduleManager()
        )

        # Fresh building manager
        new_bm = BuildingManager()
        deserialize_game_state(
            data, dc, {}, DummyPlayer(),
            self.pm, new_bm, self.sm, self.fm, self.vm,
            DummyServantManager(), DummyScheduleManager()
        )

        loaded_mkt = new_bm.buildings[0]
        self.assertEqual(loaded_mkt.assigned_family_id, "fam_1")
        self.assertEqual(loaded_mkt.assigned_household_id, "fam_1")
        self.assertEqual(loaded_mkt.inventory.get("Potato"), 15)
        self.assertEqual(loaded_mkt.currency.get("Copper"), 22)
        self.assertEqual(loaded_mkt.currency.get("Silver"), 2)
        self.assertEqual(loaded_mkt.item_allocations, {"Potato": 60, "Wood": 40})
        self.assertTrue(loaded_mkt.auto_pricing)


if __name__ == "__main__":
    unittest.main()
