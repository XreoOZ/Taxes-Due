"""Unit tests for Universal Commission Payment, Budget Reservation, and Toolmaker Supply Chain.

Verifies:
1. Single household representative: only 1 member pays at a time.
2. Budget reservation: 4 Silver pays exactly 4 beds (1 Silver each), orders 5 and 6 remain AWAITING_PAYMENT.
3. Bulk restock: Toolmaker buys Iron Ore in batches (e.g. 10 at once), never 1 by 1.
4. Smelting chain: Toolmaker smelts Iron Ore into Iron Bars for paid orders without artificial blockage.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.systems.work.commission_schedule import CommissionScheduleSystem
from game.systems.work.builder_system import BuilderSystem
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.systems.economy.market_purchasing import AIMarketPurchasingSystem


class TestBudgetReservationAndSingleRep(unittest.TestCase):
    def test_four_silver_pays_four_beds_not_six(self):
        """A household with 400 Copper (4 Silver) commissioning 6 beds (100 Copper each)
        must only pay for 4 beds. Orders 5 and 6 must stay AWAITING_PAYMENT."""
        rep = SimpleNamespace(
            id="v_head", family_id="fam_1", is_alive=True,
            task="IDLE", x=0.0, y=0.0, inventory={},
            hunger=100.0, thirst=100.0, need_toilet=100.0,
            pending_commission_tasks=[], pending_commission_task=None,
            builder_payment_order_id=None, builder_payment_builder_id=None,
            builder_fee_needed=None,
        )
        rep.say = lambda *a, **k: None
        rep._resume_or_idle_after_need = lambda: None

        fam = SimpleNamespace(id="fam_1", members=[rep], currency={})
        vm = SimpleNamespace(
            get_family_by_id=lambda fid: fam if fid == "fam_1" else None,
            get_all_villagers=lambda: [rep],
        )

        chest_inv = {"Copper": 400}
        chest = SimpleNamespace(inventory=chest_inv)
        fm = SimpleNamespace(
            furnitures=[],
            get_storage_for_family=lambda fid: chest if fid == "fam_1" else None,
        )

        orders = []
        subjects = []
        for i in range(1, 7):
            order = {
                "id": f"bed_order_{i}",
                "status": "AWAITING_PAYMENT",
                "payer_family_id": "fam_1",
                "builder_id": "builder_bob",
                "price_copper": 100,
                "order_type": "FURNITURE",
                "artisan_job": "Builder",
            }
            orders.append(order)
            subjects.append(SimpleNamespace(id=f"subj_{i}", construction_order=order))

        paid_count = 0
        for i, subj in enumerate(subjects):
            # Attempt to assign payment
            assigned = BuilderSystem._assign_payment(subj, vm, fm, None)
            if assigned:
                self.assertEqual(orders[i]["status"], "PAYMENT_REQUESTED")
                # Simulate physical execution: rep withdraws 100 copper from chest
                self.assertGreaterEqual(chest_inv["Copper"], 100)
                chest_inv["Copper"] -= 100
                rep.inventory["Copper"] = 100
                # Rep delivers to builder
                rep.inventory.clear()
                orders[i]["status"] = "PAID"
                rep.builder_payment_order_id = None
                rep.pending_commission_tasks.clear()
                rep.pending_commission_task = None
                rep.pending_commission_data.clear() if hasattr(rep, "pending_commission_data") and isinstance(rep.pending_commission_data, dict) else None
                rep.task = "IDLE"
                paid_count += 1
            else:
                self.assertEqual(orders[i]["status"], "AWAITING_PAYMENT")

        self.assertEqual(paid_count, 4, "Exactly 4 beds should be paid from 400 Copper")
        self.assertEqual(orders[4]["status"], "AWAITING_PAYMENT", "Bed 5 must remain unpaid")
        self.assertEqual(orders[5]["status"], "AWAITING_PAYMENT", "Bed 6 must remain unpaid")
        self.assertEqual(chest_inv["Copper"], 0, "Chest must have 0 Copper remaining")


class TestBulkMaterialRestock(unittest.TestCase):
    def test_toolmaker_restocks_batch_of_ore_not_one(self):
        """Toolmaker needing Iron Ore must restock a batch (10 items), not 1."""
        toolmaker = SimpleNamespace(
            id="tm_1", family_id="fam_tm", job="Toolmaker", is_alive=True,
            task="IDLE", x=100.0, y=100.0, inventory={},
            hunger=100.0, thirst=100.0, need_toilet=100.0,
        )
        toolmaker.say = lambda *a, **k: None

        chest = SimpleNamespace(inventory={"Copper": 500})
        fm = SimpleNamespace(
            furnitures=[],
            get_storage_for_family=lambda fid: chest if fid == "fam_tm" else None,
        )
        fam = SimpleNamespace(id="fam_tm", members=[toolmaker], currency={})
        vm = SimpleNamespace(
            get_family_by_id=lambda fid: fam if fid == "fam_tm" else None,
            get_all_villagers=lambda: [toolmaker],
        )

        market = SimpleNamespace(
            id="mkt_1", building_type="market", is_under_construction=False,
            inventory={"Iron Ore": 50, "Wood": 50},
            currency={"Copper": 0, "Silver": 0, "Gold": 0},
            grid_x=5, grid_y=5,
        )
        market.get_approach_point = lambda *a, **k: (160.0, 160.0)
        bm = SimpleNamespace(buildings=[market])

        # Missing 1 ore for single craft: system must batch to 10
        missing = {"Iron Ore": 1}
        started = BuilderSystem._begin_restock(toolmaker, missing, bm, fm, vm)
        self.assertTrue(started)
        self.assertEqual(toolmaker.target_restock_mat, "Iron Ore")
        self.assertEqual(toolmaker.target_restock_qty, 10, "Should restock batch of 10, not 1")
        self.assertEqual(toolmaker.task, "BUILDER_RESTOCK_RETRIEVE_COINS")


class TestToolmakerSmeltingSupplyChain(unittest.TestCase):
    def test_smelting_for_order_bypasses_daily_idle_cap(self):
        """When smelting to fulfill a paid customer order, TOOLMAKER_BAR_DAILY_CAP
        must not block the artisan from producing bars."""
        toolmaker = SimpleNamespace(
            id="tm_1", family_id="fam_tm", job="Toolmaker", is_alive=True,
            task="IDLE", x=100.0, y=100.0, inventory={},
            hunger=100.0, thirst=100.0, need_toilet=100.0,
            toolmaker_bars_day=1, toolmaker_bars_smelted=10,  # Already hit daily idle cap!
            toolmaker_smelt_timer=0.0,
        )
        toolmaker.say = lambda *a, **k: None
        toolmaker._move_towards = lambda *a, **k: True  # Instantly arrived at bench

        chest_inv = {"Iron Ore": 10, "Wood": 10, "Iron Bar": 0}
        chest = SimpleNamespace(
            inventory=chest_inv,
            store_item=lambda item, amt: chest_inv.update({item: chest_inv.get(item, 0) + amt}),
        )
        fm = SimpleNamespace(
            furnitures=[],
            get_storage_for_family=lambda fid: chest if fid == "fam_tm" else None,
        )

        workbench = SimpleNamespace(
            furniture_type="toolmaker_workbench",
            construction_order=None,
            id="wb_1",
            grid_x=3, grid_y=3,
        )
        workbench.get_world_pos = lambda *a, **k: (100.0, 100.0)
        workbench.get_approach_point = lambda *a, **k: (100.0, 100.0)
        fm.furnitures = [workbench]

        day_cycle = SimpleNamespace(day_number=1, day_length_seconds=1440.0)

        # 1. Background idle smelting (for_order=False) must be BLOCKED by cap
        can_idle_smelt = ToolmakerSystem._smelt_step(
            toolmaker, 1.0, fm, None, None, [], None, day_cycle, for_order=False
        )
        self.assertFalse(can_idle_smelt, "Idle background smelting must respect daily cap")

        # 2. Commission order smelting (for_order=True) must PROCEED
        can_order_smelt = ToolmakerSystem._smelt_step(
            toolmaker, 100.0, fm, None, None, [], None, day_cycle, for_order=True
        )
        self.assertTrue(can_order_smelt, "Order smelting must bypass idle cap")
        self.assertEqual(chest_inv["Iron Bar"], 1, "Should have smelted 1 Iron Bar into chest")
        self.assertEqual(chest_inv["Iron Ore"], 9, "Should have consumed 1 Iron Ore")
        self.assertEqual(chest_inv["Wood"], 9, "Should have consumed 1 Wood")


class TestChestlessGroundCoinsToolErrands(unittest.TestCase):
    def test_chestless_immigrant_can_commission_and_buy_tools_with_ground_coins(self):
        """Chestless households with coins dropped on house tiles can both commission and buy tools."""
        from game.entities.villagers import Villager, Family, VillagerManager
        from game.world.stockpile import ResourceStack, StockpileManager
        from game.systems.economy.market_purchasing import AIMarketPurchasingSystem
        from game.buildings.furniture import Furniture

        vm = VillagerManager()
        fam = Family("fam_imm", "Settler")
        farmer = Villager("v_imm", "Leo", "Settler", "Male", 25, 2, "Father", family_id="fam_imm", x=100.0, y=100.0)
        farmer.set_job("Farmer")
        farmer.inventory = {}
        farmer._move_towards = lambda *a, **k: True
        fam.members = [farmer]
        vm.families = [fam]

        spm = StockpileManager()
        coin_stack = ResourceStack("Gold", 1, 2, 2, owner_type="villager", owner_id="fam_imm")
        spm.stacks.append(coin_stack)

        bench = Furniture("wb_1", "toolmaker_workbench", 6, 6, family_id="fam_tm")
        fm = SimpleNamespace(
            furnitures=[bench],
            get_storage_for_family=lambda fid: None,  # Chestless household!
            invalidate_cache=lambda: None,
        )
        bm = SimpleNamespace(buildings=[])

        # 1. Ground coins allow tool commission
        farmer._ensure_tool_commissions([("Hoe", 1)], bm, fm, vm, stockpile_manager=spm)
        self.assertEqual(farmer.task, "COMMISSIONING_TOOL_RETRIEVE_COINS")
        status, _ = farmer._retrieve_household_coins_for_errand(
            farmer.commission_tool_fee, 0.1, fm, spm, vm, bm, [], None
        )
        self.assertEqual(status, "READY")
        self.assertGreaterEqual(farmer.inventory.get("Gold", 0), 1)
        self.assertNotIn(coin_stack, spm.stacks)

        # 2. Ground coins allow finding & withdrawing for Market tool purchase
        farmer.inventory = {}
        coin_stack2 = ResourceStack("Silver", 5, 2, 2, owner_type="villager", owner_id="fam_imm")
        spm.stacks.append(coin_stack2)
        market = SimpleNamespace(
            id="mkt_tools", building_type="market", is_under_construction=False,
            inventory={"Hoe": 2}, prices={"Hoe": 8}, sale_items=["Hoe"],
            currency={"Copper": 100}, grid_x=8, grid_y=8,
        )
        market.get_approach_point = lambda *a, **k: (512.0, 512.0)
        bm_with_mkt = SimpleNamespace(buildings=[market])

        found_mkt, items, cost = AIMarketPurchasingSystem.find_market_for_items(
            farmer, {"Hoe": 1}, bm_with_mkt, fm, vm, stockpile_manager=spm
        )
        self.assertIs(found_mkt, market)
        self.assertEqual(items, {"Hoe": 1})
        self.assertEqual(cost, 8)
        status2, _ = farmer._retrieve_household_coins_for_errand(
            cost, 0.1, fm, spm, vm, bm_with_mkt, [], None, use_market_withdraw=True
        )
        self.assertEqual(status2, "READY")


if __name__ == "__main__":
    unittest.main()
