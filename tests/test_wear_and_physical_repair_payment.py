import unittest
from unittest.mock import patch

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.entities.servants import Servant
from game.entities.villagers import Family, Villager
from game.systems.work.builder_system import BuilderSystem
from game.world.stockpile import StockpileManager


class TestWearAndPhysicalRepairPayment(unittest.TestCase):
    def test_household_furniture_wear_resets_daily_and_can_break_on_later_days(self):
        bm = BuildingManager()
        fm = FurnitureManager()
        fm.building_manager = bm
        bed = Furniture("f_bed1", "bed", 2, 2, family_id=1, permit_id=101)
        fm.furnitures.append(bed)

        # Day 2: roll doesn't break (0.99 >= 0.05) -> break_checked_today becomes True
        fm.daily_wear_update(1, current_day=2)
        with patch("random.random", return_value=0.99):
            fm.check_breaks_by_time(2, bed.break_check_hour)
        self.assertTrue(bed.break_checked_today)
        self.assertFalse(bed.is_broken)

        # Day 3: daily_wear_update MUST reset break_checked_today so bed can roll again
        fm.daily_wear_update(1, current_day=3)
        self.assertFalse(bed.break_checked_today)
        with patch("random.random", return_value=0.0):
            broken = fm.check_breaks_by_time(3, bed.break_check_hour)
        self.assertIn(bed, broken)
        self.assertTrue(bed.is_broken)
        self.assertIsNotNone(bed.construction_order)

    def test_public_repair_requires_physical_servant_payment_no_free_teleport(self):
        bm = BuildingManager()
        fm = FurnitureManager()
        fm.building_manager = bm
        sm = StockpileManager()

        well = Building("well", {(5, 5)})
        well.condition = 0.0
        well.construction_order = BuilderSystem.create_repair_order(well, bm, None)
        well.construction_order.update({
            "status": "LANDLORD_PAYMENT_PENDING",
            "payer_type": "landlord",
            "payer_id": "landlord",
            "price_copper": 20,
        })
        bm.buildings.append(well)

        fam = Family(1, "Bob")
        builder = Villager(1, 0, 0, "Bob", 25, 1, "Father", family_id=1)
        builder.set_job("Builder")
        fam.members.append(builder)

        class DummyVM:
            families = [fam]
            def get_all_villagers(self):
                return [builder]

        class DummySM:
            def __init__(self, servants):
                self.servants = servants

        servant = Servant("s1", "Servant", 10, 10)
        servant_mgr = DummySM([servant])

        # 1. Empty treasury -> MUST NOT allow unpaid emergency repair
        ok, _ = BuilderSystem.request_public_commission(
            well, None, servant_mgr, DummyVM(), bm,
            stockpile_manager=sm, furniture_manager=fm,
        )
        self.assertFalse(ok)
        self.assertEqual(well.construction_order["status"], "LANDLORD_PAYMENT_PENDING")
        self.assertEqual(servant.state, "IDLE")

        # 2. Funded treasury chest -> Servant physically dispatched to retrieve & deliver coins
        treasury = Furniture("f_treasury", "lord_treasury_chest", 1, 0)
        treasury.inventory = {"Silver": 5}
        fm.furnitures.append(treasury)

        ok2, _ = BuilderSystem.request_public_commission(
            well, None, servant_mgr, DummyVM(), bm,
            stockpile_manager=sm, furniture_manager=fm,
        )
        self.assertTrue(ok2)
        self.assertEqual(well.construction_order["status"], "LANDLORD_RETRIEVING")
        self.assertEqual(servant.state, "BUILDER_COMMISSION_RETRIEVE")
        self.assertFalse(well.construction_order.get("commission_paid", False))


if __name__ == "__main__":
    unittest.main()
