"""
Agent 3 Feature Verification Test Suite:
- Toilet building & usage routine (1x1, 5 wood, no permit, FIFO lateral queue, need restore)
- Church & Priest (structure on permit, exactly 1 priest, prayer time from schedule, tax payment, tithes deposit)
- Cemetery & Gravedigger (blocks normal buildings, Hoe tool, 1 wood + 1 stone consumption, 5 tombstone models,
  30-day grave reuse with corpse history retention, full cemetery overflow handling)
- Universal Market Purchasing for materials (Wood, Stone)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from game.config import TILE_SIZE, AI_NEED_MAX
from game.data.config import (
    BUILDING_TYPES,
    PERMIT_TYPES,
    DEDICATED_JOBS,
    DEFAULT_ITEM_PRICES,
    DEFAULT_CHURCH_TAX,
    GRAVEDIGGER_TARGET_WOOD,
    GRAVEDIGGER_TARGET_STONE,
    GRAVE_COST_WOOD,
    GRAVE_COST_STONE,
    GRAVE_DIG_HOURS,
    GRAVE_BURY_HOURS,
    GRAVE_REUSE_DAYS,
    BURIAL_FEE_MAX_SILVER,
    CORPSE_CARRY_SPEED_RATIO,
    TOMBSTONE_MODELS_COUNT,
    AI_NEED_TOILET_DECAY_PER_DAY,
    AI_NEED_TOILET_URGENT_THRESHOLD,
    AI_NEED_TOILET_RESTORE
)
from game.buildings.buildings import Building, BuildingManager
from game.world.permits import AreaPermit, PermitManager
from game.entities.villagers import Villager, Family, VillagerManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.systems.schedule import ScheduleManager
from game.systems.toilet_system import ToiletSystem
from game.systems.church_system import ChurchSystem
from game.systems.cemetery_system import CemeterySystem
from game.systems.market_purchasing import AIMarketPurchasingSystem


class TestAgent3ChurchCemeteryToiletMarket(unittest.TestCase):

    def setUp(self):
        self.building_mgr = BuildingManager()
        self.permit_mgr = PermitManager()
        self.furniture_mgr = FurnitureManager()
        self.villager_mgr = VillagerManager()
        self.schedule_mgr = ScheduleManager()

        ChurchSystem.reset_daily_taxes(1.0, self.permit_mgr)
        inst_cem = CemeterySystem.get_instance()
        inst_cem.pending_commissions.clear()
        inst_cem.overflow_corpses.clear()

    # -------------------------------------------------------------------------
    # 1. Toilet Building Specifications & Usage
    # -------------------------------------------------------------------------
    def test_toilet_building_specs(self):
        cfg = BUILDING_TYPES["toilet"]
        self.assertEqual(cfg["width_tiles"], 1)
        self.assertEqual(cfg["height_tiles"], 1)
        self.assertEqual(cfg["cost_wood"], 5)
        self.assertEqual(cfg["cost_stone"], 0)
        self.assertTrue(cfg["fixed_cost"])

        # No permit required for toilet
        t_tiles = {(10, 10)}
        res, msg = self.permit_mgr.find_matching_permit_for_tiles("toilet", t_tiles, self.building_mgr)
        self.assertTrue(res)
        self.assertIn("No Permit Required", msg)

    def test_toilet_usage_and_queue(self):
        toilet_b = Building("toilet", {(5, 5)})
        self.building_mgr.buildings.append(toilet_b)

        v1 = Villager("v1", "John", "Doe", "M", 25, 1, "Builder", "fam_1")
        v2 = Villager("v2", "Jane", "Doe", "F", 24, 1, "Farmer", "fam_1")
        v1.x, v1.y = 5 * TILE_SIZE, 5 * TILE_SIZE
        v2.x, v2.y = 6 * TILE_SIZE, 5 * TILE_SIZE
        v1.need_toilet = 10.0
        v2.need_toilet = 15.0

        # v1 enters toilet
        can_access, q_pos = ToiletSystem.request_toilet_access(v1, toilet_b)
        self.assertTrue(can_access)
        self.assertIsNone(q_pos)
        self.assertEqual(toilet_b.occupied_by, "v1")

        # v2 requests toilet while occupied -> queued with lateral offset
        can_access_2, q_pos_2 = ToiletSystem.request_toilet_access(v2, toilet_b)
        self.assertFalse(can_access_2)
        self.assertIsNotNone(q_pos_2)
        self.assertEqual(len(toilet_b.toilet_queue), 1)

        # Release toilet by v1
        ToiletSystem.release_toilet(toilet_b, v1.id)
        self.assertIsNone(toilet_b.occupied_by)

        # Now v2 can access
        can_access_2_now, _ = ToiletSystem.request_toilet_access(v2, toilet_b)
        self.assertTrue(can_access_2_now)
        self.assertEqual(toilet_b.occupied_by, "v2")

    # -------------------------------------------------------------------------
    # 2. Church & Priest
    # -------------------------------------------------------------------------
    def test_church_permit_and_single_priest_limit(self):
        # Church is a permit
        p = self.permit_mgr.add_permit("Village Church", "church", {(10, 10), (10, 11), (11, 10), (11, 11)})
        self.assertIsNotNone(p)
        self.assertEqual(p.permit_type, "church")
        self.assertEqual(p.max_workers, 1)

        # Assign 1 priest
        ok1, _ = self.permit_mgr.assign_worker_to_permit(p.id, "priest_1")
        self.assertTrue(ok1)
        self.assertEqual(len(p.assigned_workers), 1)

        # Exactly ONE priest allowed: 2nd assignment must fail
        ok2, msg2 = self.permit_mgr.assign_worker_to_permit(p.id, "priest_2")
        self.assertFalse(ok2)
        self.assertIn("exactly one Priest", msg2)

    def test_church_prayer_time_and_tax_payment(self):
        # Priest job schedule
        self.schedule_mgr.set_prayer_time(9, 11)
        self.assertTrue(ChurchSystem.is_prayer_time(9.5, self.schedule_mgr))
        self.assertFalse(ChurchSystem.is_prayer_time(12.0, self.schedule_mgr))

        # Setup Church permit & Priest
        church_p = self.permit_mgr.add_permit("Church", "church", {(20, 20), (20, 21)})
        priest = Villager("p1", "Father", "Thomas", "M", 50, 1, "Priest", "fam_p")
        priest.job = "Priest"
        priest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.permit_mgr.assign_worker_to_permit(church_p.id, priest.id)

        fam_p = Family("fam_p", "Thomas")
        fam_p.members = [priest]
        self.villager_mgr.families.append(fam_p)

        # Peasant family with 5 Copper in chest
        peasant = Villager("peas_1", "Adam", "Smith", "M", 30, 1, "Farmer", "fam_smith")
        peasant.family_id = "fam_smith"
        fam_s = Family("fam_smith", "Smith")
        fam_s.members = [peasant]
        self.villager_mgr.families.append(fam_s)

        chest = Furniture("chest_1", "household_storage", 30, 30, permit_id="p_smith", family_id="fam_smith")
        chest.currency = {"Copper": 5, "Silver": 0, "Gold": 0}
        self.furniture_mgr.furnitures.append(chest)

        # Pay church tax (default 1 Copper)
        paid = ChurchSystem.process_church_tax_payment(peasant, priest, church_p, self.furniture_mgr)
        self.assertEqual(paid, 1)
        self.assertEqual(chest.currency["Copper"], 4)
        self.assertEqual(priest.currency["Copper"], 1)
        self.assertTrue(ChurchSystem.has_household_paid_tax("fam_smith", church_p))

        # Second payment on same day pays 0 (paid only once per day)
        paid_again = ChurchSystem.process_church_tax_payment(peasant, priest, church_p, self.furniture_mgr)
        self.assertEqual(paid_again, 0)
        self.assertEqual(priest.currency["Copper"], 1)

        # Priest deposits tithes home after prayer
        priest_chest = Furniture("chest_p", "household_storage", 25, 25, permit_id="p_p", family_id="fam_p")
        priest_chest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        self.furniture_mgr.furnitures.append(priest_chest)

        deposited = ChurchSystem.priest_deposit_tithes_home(priest, self.furniture_mgr)
        self.assertEqual(deposited, 1)
        self.assertEqual(priest.currency["Copper"], 0)
        self.assertEqual(priest_chest.currency["Copper"], 1)

    # -------------------------------------------------------------------------
    # 3. Cemetery Permit & Gravedigger Workflow
    # -------------------------------------------------------------------------
    def test_cemetery_blocks_normal_buildings(self):
        self.permit_mgr.add_permit("Holy Cemetery", "cemetery", {(15, 15), (15, 16), (16, 15), (16, 16)})
        # Trying to build a wooden structure on cemetery tiles must fail
        b_tiles = {(15, 15), (15, 16)}
        res, msg = self.permit_mgr.find_matching_permit_for_tiles("wooden_structure", b_tiles, self.building_mgr)
        self.assertIsNone(res)
        self.assertIn("Cannot build structures on Cemetery Lot", msg)

    def test_gravedigger_tool_is_hoe(self):
        # Strict requirement: Gravedigger uses Hoe, never Shovel
        job_cfg = DEDICATED_JOBS["Gravedigger"]
        self.assertEqual(job_cfg["required_tools"], ["Hoe"])
        self.assertNotIn("Shovel", job_cfg["required_tools"])

    def test_grave_lifecycle_and_30_day_reuse(self):
        cem_p = self.permit_mgr.add_permit("Cem", "cemetery", {(50, 50)})
        CemeterySystem.ensure_cemetery_graves(cem_p)

        # Initially available
        avail_t = CemeterySystem.get_available_grave_tile(cem_p, current_day=1.0)
        self.assertEqual(avail_t, (50, 50))

        # Complete burial on tile
        var = CemeterySystem.complete_burial_on_tile(cem_p, (50, 50), {"id": "corpse_99", "full_name": "Old Man"}, current_day=1.0)
        self.assertIn(var, range(TOMBSTONE_MODELS_COUNT))
        self.assertTrue(cem_p.tile_graves[(50, 50)]["is_occupied"])

        # Tile is now occupied -> cemetery is full
        avail_none = CemeterySystem.get_available_grave_tile(cem_p, current_day=10.0)
        self.assertIsNone(avail_none)

        # After 30 days (day 31.0): grave becomes reusable, old corpse preserved in history
        CemeterySystem.update_grave_lifecycles(cem_p, current_day=31.0)
        self.assertFalse(cem_p.tile_graves[(50, 50)]["is_occupied"])
        self.assertIn("corpse_99", cem_p.tile_graves[(50, 50)]["corpse_history"])
        self.assertIsNone(cem_p.tile_graves[(50, 50)]["tombstone_variant"])

        # Available again
        avail_reused = CemeterySystem.get_available_grave_tile(cem_p, current_day=31.0)
        self.assertEqual(avail_reused, (50, 50))

    def test_full_cemetery_overflow_message(self):
        cem_p = self.permit_mgr.add_permit("CemTiny", "cemetery", {(60, 60)})
        CemeterySystem.complete_burial_on_tile(cem_p, (60, 60), {"id": "c1"}, current_day=1.0)

        gd = Villager("gd1", "Grave", "Digger", "M", 40, 1, "Gravedigger", "fam_gd")
        CemeterySystem.handle_full_cemetery_overflow(gd, {"id": "c2", "first_name": "Deceased2"}, cem_p)
        self.assertEqual(gd.speech_text, "The cemetery is currently full. Please consider expanding it, Landlord.")

    def test_gravedigger_material_consumption_and_market_restock(self):
        gd = Villager("gd1", "Grave", "Digger", "M", 40, 1, "Gravedigger", "fam_gd")
        gd.family_id = "fam_gd"
        chest_gd = Furniture("chest_gd", "household_storage", 70, 70, permit_id="p_gd", family_id="fam_gd")
        chest_gd.inventory = {"Wood": 1, "Stone": 1}
        self.furniture_mgr.furnitures.append(chest_gd)

        # Consume 1 Wood + 1 Stone for grave
        ok = CemeterySystem.consume_grave_materials(gd, self.furniture_mgr)
        self.assertTrue(ok)
        self.assertEqual(chest_gd.inventory["Wood"], 0)
        self.assertEqual(chest_gd.inventory["Stone"], 0)

        # Missing materials: target 5 Wood, 5 Stone
        w_cnt, s_cnt, miss_w, miss_s = CemeterySystem.check_gravedigger_stock(gd, self.furniture_mgr)
        self.assertEqual(miss_w, 5)
        self.assertEqual(miss_s, 5)

        # Market restocking check
        mkt = Building("market", {(80, 80), (81, 80), (82, 80)})
        mkt.inventory = {"Wood": 20, "Stone": 20}
        mkt.prices = {"Wood": 2, "Stone": 3}
        mkt.currency = {"Copper": 50, "Silver": 0, "Gold": 0}
        self.building_mgr.buildings.append(mkt)

        gd.inventory = {"Copper": 10, "Silver": 0, "Gold": 0}
        bought, msg = AIMarketPurchasingSystem.execute_material_transaction(gd, mkt, "Wood", quantity=3)
        self.assertTrue(bought)
        self.assertEqual(gd.inventory["Wood"], 3)
        self.assertEqual(mkt.inventory["Wood"], 17)
        self.assertEqual(gd.inventory["Copper"], 4)  # 10 - (3 * 2) = 4


if __name__ == "__main__":
    unittest.main()
