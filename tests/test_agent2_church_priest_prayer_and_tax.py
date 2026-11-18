"""
Agent 2 Comprehensive Verification Test Suite:
Church, Priest, Prayer Time & Church Tax System
Verifies all 7 core specifications:
1. Church is a Permit, not a Structure blueprint. Wooden and Stone structures buildable inside Church Permit.
2. Priest job assignment via [- Number of Workers +], selecting closest available household member without active job.
3. Prayer Time Schedule: continuous indivisible block on Priest schedule, forced onto all jobs strictly during the prayer block.
4. Household prayer and Church Tax flow: 1 representative pays for household, coins enter Priest inventory, paid once daily.
5. Church Tax Settings: Gold, Silver, Copper denomination controls, no partial payment if insufficient.
6. Priest workflow: receives tithes at church during prayer, deposits into household chest afterwards, preaches during work hours.
7. Prayer time priority over normal activities.
"""

import os
import sys
import unittest
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from game.config import TILE_SIZE, SCHEDULE_PRAYER, SCHEDULE_WORK
from game.data.config import (
    BUILDING_TYPES,
    PERMIT_TYPES,
    DEDICATED_JOBS,
    DEFAULT_CHURCH_TAX
)
from game.buildings.buildings import Building, BuildingManager
from game.world.permits import AreaPermit, PermitManager
from game.entities.villagers import Villager, Family, VillagerManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.systems.schedule import ScheduleManager
from game.systems.church_system import ChurchSystem
from game.systems.currency import to_copper


class TestAgent2ChurchPriestPrayerAndTax(unittest.TestCase):

    def setUp(self):
        self.building_mgr = BuildingManager()
        self.permit_mgr = PermitManager()
        self.permit_mgr.permits.clear()  # Start clean
        self.furniture_mgr = FurnitureManager()
        self.villager_mgr = VillagerManager()
        self.schedule_mgr = ScheduleManager()

        ChurchSystem.reset_daily_taxes(1.0, self.permit_mgr)
        ChurchSystem.set_tax_settings(0, 0, 1, self.permit_mgr)

    def test_church_is_permit_not_structure(self):
        """1. Church is an Area Permit, not a Structure blueprint. Wooden & Stone structures can be built on Church Permit."""
        self.assertIn("church", PERMIT_TYPES)
        self.assertNotIn("church", BUILDING_TYPES)

        # Wooden Structure and Stone Structure allow church permits
        self.assertIn("church", BUILDING_TYPES["wooden_structure"]["allowed_permits"])
        self.assertIn("church", BUILDING_TYPES["stone_structure"]["allowed_permits"])

        # Placing a wooden building inside a church permit is valid
        c_permit = self.permit_mgr.add_permit("Village Church Lot", "church", {(10, 10), (10, 11), (11, 10), (11, 11)})
        valid, msg = self.permit_mgr.find_matching_permit_for_tiles("wooden_structure", {(10, 10), (10, 11), (11, 10), (11, 11)}, self.building_mgr)
        self.assertIsNotNone(valid, f"Expected permit match, got: {msg}")

    def test_priest_job_assignment_via_worker_count(self):
        """2. Priest job assignment selects closest available household member with no other active job."""
        self.assertIn("Priest", DEDICATED_JOBS)
        self.assertFalse(DEDICATED_JOBS["Priest"].get("wip", False))

        c_permit = self.permit_mgr.add_permit("Village Church Lot", "church", {(5, 5), (6, 5)})
        c_permit.max_workers = 1

        # Create two families:
        # Family A at (6, 6) close to church
        fam_a = Family("fam_smith", "Smith")
        vil_a1 = Villager("vil_smith_1", "John", "Smith", "Male", 25, 1, "Farmer", family_id="fam_smith", x=5.5 * TILE_SIZE, y=6.0 * TILE_SIZE)
        vil_a1.job = "Farmer"
        fam_a.members.append(vil_a1)

        # Family B at (50, 50) far from church
        fam_b = Family("fam_baker", "Baker")
        vil_b1 = Villager("vil_baker_1", "William", "Baker", "Male", 30, 1, "Farmer", family_id="fam_baker", x=50.0 * TILE_SIZE, y=50.0 * TILE_SIZE)
        vil_b1.job = "Farmer"
        fam_b.members.append(vil_b1)

        self.villager_mgr.families = [fam_a, fam_b]

        # Increase worker count on Church permit
        success = self.permit_mgr.change_max_workers(c_permit.id, 1, self.villager_mgr)
        self.assertTrue(success)

        # The closest villager (vil_a1) must have become the Priest!
        self.assertEqual(vil_a1.job, "Priest")
        self.assertIn("Priest", vil_a1.title)
        self.assertIn("vil_smith_1", c_permit.assigned_workers)

        # Decreasing worker count releases the Priest back
        self.permit_mgr.change_max_workers(c_permit.id, -1, self.villager_mgr)
        self.assertIn(vil_a1.job, ("Farmer", "Unassigned"))
        self.assertNotIn("Priest", vil_a1.title)
        self.assertEqual(len(c_permit.assigned_workers), 0)

    def test_prayer_time_schedule_forced_onto_all_jobs(self):
        """3. Prayer Time is a continuous block on Priest schedule, forced onto all other jobs during that block."""
        # Set Prayer Time from 05:00 to 07:00
        self.schedule_mgr.set_prayer_time(5, 7)
        s, e = self.schedule_mgr.get_prayer_hours()
        self.assertEqual(s, 5)
        self.assertEqual(e, 7)

        # At 06:00, ALL jobs must follow Prayer Time
        self.assertEqual(self.schedule_mgr.get_current_activity("Farmer", 6.0), SCHEDULE_PRAYER)
        self.assertEqual(self.schedule_mgr.get_current_activity("Builder", 6.0), SCHEDULE_PRAYER)
        self.assertEqual(self.schedule_mgr.get_current_activity("Priest", 6.0), SCHEDULE_PRAYER)

        # Outside Prayer Time (e.g. 10:00), each job follows its own independent schedule
        farmer_act = self.schedule_mgr.get_current_activity("Farmer", 10.0)
        self.assertNotEqual(farmer_act, SCHEDULE_PRAYER)
        self.assertEqual(farmer_act, SCHEDULE_WORK)

    def test_household_representative_pays_church_tax_once_daily(self):
        """4 & 5. 1 representative pays exact coin tax, coins enter Priest inventory, paid once per household daily."""
        c_permit = self.permit_mgr.add_permit("Church", "church", {(0, 0), (1, 0)})
        priest = Villager("priest_1", "Father", "Thomas", "Male", 40, 1, "Priest", family_id="fam_church")
        priest.job = "Priest"
        priest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
        c_permit.assigned_workers = ["priest_1"]

        # Family with 2 adults, chest has 5 Copper
        fam = Family("fam_miller", "Miller")
        dad = Villager("dad_miller", "Henry", "Miller", "Male", 35, 1, "Farmer", family_id="fam_miller")
        mom = Villager("mom_miller", "Alice", "Miller", "Female", 33, 1, "Farmer", family_id="fam_miller")
        fam.members.append(dad)
        fam.members.append(mom)
        self.villager_mgr.families = [fam]

        chest = Furniture("chest_miller", "household_storage", 2, 2, family_id="fam_miller")
        chest.currency = {"Copper": 5, "Silver": 0, "Gold": 0}
        self.furniture_mgr.furnitures = [chest]

        # Set tax to 1 Copper
        ChurchSystem.set_tax_settings(0, 0, 1, self.permit_mgr)

        # Representative dad pays
        rep = ChurchSystem.select_household_representative(fam, self.villager_mgr)
        self.assertEqual(rep.id, dad.id)

        paid = ChurchSystem.process_church_tax_payment(dad, priest, c_permit, self.furniture_mgr)
        self.assertEqual(paid, 1)
        self.assertEqual(priest.currency["Copper"], 1)
        self.assertEqual(chest.currency["Copper"], 4)
        self.assertTrue(ChurchSystem.has_household_paid_tax("fam_miller", c_permit))

        # Second member mom arriving during same prayer time must NOT pay again
        paid_second = ChurchSystem.process_church_tax_payment(mom, priest, c_permit, self.furniture_mgr)
        self.assertEqual(paid_second, 0)
        self.assertEqual(priest.currency["Copper"], 1)

    def test_no_partial_payment_if_insufficient_coins(self):
        """5. If household has insufficient coins, do not collect partial payment."""
        c_permit = self.permit_mgr.add_permit("Church", "church", {(0, 0)})
        priest = Villager("priest_1", "Father", "Thomas", "Male", 40, 1, "Priest", family_id="fam_church")
        priest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        fam = Family("fam_poor", "Poor")
        poor_vil = Villager("poor_1", "Hugh", "Poor", "Male", 25, 1, "Farmer", family_id="fam_poor")
        fam.members.append(poor_vil)
        self.villager_mgr.families = [fam]

        chest = Furniture("chest_poor", "household_storage", 3, 3, family_id="fam_poor")
        chest.currency = {"Copper": 3, "Silver": 0, "Gold": 0}  # Has only 3 Copper
        self.furniture_mgr.furnitures = [chest]

        # Set tax to 1 Silver (10 Copper)
        ChurchSystem.set_tax_settings(0, 1, 0, self.permit_mgr)
        self.assertEqual(ChurchSystem.get_configured_tax_amount(c_permit), 10)

        # Try to pay: household only has 3c (< 10c). MUST NOT collect partial payment!
        paid = ChurchSystem.process_church_tax_payment(poor_vil, priest, c_permit, self.furniture_mgr)
        self.assertEqual(paid, 0)
        self.assertEqual(chest.currency["Copper"], 3)  # Coins untouched!
        self.assertEqual(priest.currency.get("Copper", 0), 0)
        # Marked paid today so they are not harassed repeatedly
        self.assertTrue(ChurchSystem.has_household_paid_tax("fam_poor", c_permit))

    def test_priest_deposits_tithes_into_household_chest(self):
        """6. After prayer ends, Priest deposits all collected tithes into assigned household chest."""
        priest = Villager("priest_1", "Father", "Thomas", "Male", 40, 1, "Priest", family_id="fam_church")
        priest.currency = {"Copper": 8, "Silver": 1, "Gold": 0}

        church_chest = Furniture("chest_church", "household_storage", 0, 0, family_id="fam_church")
        church_chest.currency = {"Copper": 2, "Silver": 0, "Gold": 0}
        self.furniture_mgr.furnitures = [church_chest]

        deposited = ChurchSystem.priest_deposit_tithes_home(priest, self.furniture_mgr)
        self.assertEqual(deposited, 18)  # 8 copper + 1 silver (10) = 18c
        self.assertEqual(priest.currency["Copper"], 0)
        self.assertEqual(priest.currency["Silver"], 0)
        self.assertEqual(church_chest.currency["Copper"], 10)
        self.assertEqual(church_chest.currency["Silver"], 1)

    def test_church_tax_settings_stepper_and_conversion(self):
        """5. Landlord configures specific tax amount using Gold, Silver, Copper denominations."""
        # 1 Gold, 2 Silver, 5 Copper
        ChurchSystem.set_tax_settings(1, 2, 5, self.permit_mgr)
        settings = ChurchSystem.get_tax_settings()
        self.assertEqual(settings["Gold"], 1)
        self.assertEqual(settings["Silver"], 2)
        self.assertEqual(settings["Copper"], 5)

        # Total copper: 100 + 20 + 5 = 125c
        self.assertEqual(ChurchSystem.get_configured_tax_amount(), 125)


if __name__ == "__main__":
    unittest.main()
