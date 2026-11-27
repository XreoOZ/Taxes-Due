"""
Unit tests verifying that broken toilets trigger public repairs and do not cause permanent villager freezing or game over.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.config import TILE_SIZE
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.entities.villagers import Villager, VillagerManager
from game.furniture import FurnitureManager
from game.systems.village_life.toilet_system import ToiletSystem
from game.systems.work.builder_system import BuilderSystem


class TestToiletBrokenRepairNoDeadlock(unittest.TestCase):
    def setUp(self):
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()

    def test_need_toilet_never_treated_as_lethal_need_override(self):
        """Need toilet at 0% must never trigger lethal need override or force LEISURE."""
        v = Villager("v1", "John", "Doe", "male", 25, 1, "Farmer", "fam1")
        v.need_toilet = 0.0
        v.hunger = 100.0
        v.thirst = 100.0

        # _lethal_need_task must be None (toilet has no death countdown)
        self.assertIsNone(v._lethal_need_task())

    def test_broken_toilet_requires_servant_delivery_no_telepathy(self):
        """When toilet is broken and Lord has 0 coins, Builder is NOT notified telepathically — a Servant must walk to deliver the order."""
        from game.entities.servants import Servant
        toilet = Building("toilet", {(5, 5)})
        self.bm.buildings.append(toilet)

        builder = Villager("b1", "Bob", "Builder", "male", 30, 1, "father", "fam_builder")
        builder.job = "Builder"
        builder.inventory = {"Hammer": 1, "Saw": 1, "Adze": 1, "Wood": 2, "Stone": 2}
        from game.entities.villagers import Family
        fam = Family("fam_builder", "Builder")
        fam.members.append(builder)
        self.vm.families.append(fam)

        # Toilet breaks down
        toilet.condition = 0.0
        self.assertTrue(toilet.is_broken)
        self.assertFalse(toilet.is_available_for_use)

        repair_order = BuilderSystem.create_repair_order(toilet, self.bm, self.vm)
        repair_order["status"] = "LANDLORD_PAYMENT_PENDING"
        toilet.construction_order = repair_order

        # 1. With no idle servant, Builder must NOT learn about it telepathically
        sm_empty = SimpleNamespace(servants=[], stacks=[])
        started_none = BuilderSystem.dispatch_pending_public_commissions(
            self.bm, sm_empty, self.vm, self.fm, day_cycle=None, stockpile_manager=None
        )
        self.assertEqual(started_none, 0)
        self.assertEqual(repair_order["status"], "LANDLORD_PAYMENT_PENDING")
        self.assertIsNone(repair_order.get("builder_id"))

        # 2. With 0 coins in Treasury and an idle Servant, unpaid repair is NOT dispatched
        servant = Servant("s1", "Jeeves", x=builder.x, y=builder.y)
        servant._move_towards = lambda *a, **k: True
        sm = SimpleNamespace(servants=[servant], stacks=[])
        started_unfunded = BuilderSystem.dispatch_pending_public_commissions(
            self.bm, sm, self.vm, self.fm, day_cycle=None, stockpile_manager=None
        )
        self.assertEqual(started_unfunded, 0)
        self.assertEqual(repair_order["status"], "LANDLORD_PAYMENT_PENDING")

        # 3. Once Treasury holds coins, Servant physically fetches coins -> pays Builder -> PAID
        from game.buildings.furniture import Furniture
        treasury = Furniture("treasury_1", "lord_treasury_chest", 1, 0)
        treasury.inventory = {"Silver": 5}
        self.fm.furnitures.append(treasury)
        started = BuilderSystem.dispatch_pending_public_commissions(
            self.bm, sm, self.vm, self.fm, day_cycle=None, stockpile_manager=None
        )
        self.assertEqual(started, 1)
        self.assertEqual(servant.state, "BUILDER_COMMISSION_RETRIEVE")
        self.assertEqual(repair_order["status"], "LANDLORD_RETRIEVING")

        # Reach Treasury -> fetch coins; then reach Builder -> pay coins -> PAID
        for _ in range(3):
            if repair_order["status"] == "PAID":
                break
            servant.update(
                0.1, self.bm, None, None, {}, None,
                all_servants=[servant], furniture_manager=self.fm,
                villager_manager=self.vm, servant_manager=sm,
                all_entities=[servant, builder],
            )
        self.assertEqual(repair_order["status"], "PAID")
        self.assertTrue(repair_order["commission_paid"])
        self.assertEqual(str(repair_order["builder_id"]), str(builder.id))

        # Position builder at toilet and update
        toilet_pos = toilet.get_center_world(TILE_SIZE)
        builder.x, builder.y = toilet_pos[0], toilet_pos[1]

        # Update builder to perform repair
        for _ in range(50):
            BuilderSystem.update_worker(
                builder, dt=1.0, schedule_activity="WORK",
                building_manager=self.bm, furniture_manager=self.fm,
                villager_manager=self.vm, all_entities=[builder],
                player=None, day_cycle=None, stockpile_manager=None
            )
            if toilet.condition >= 1.0:
                break

        self.assertEqual(toilet.condition, 1.0)
        self.assertFalse(toilet.is_broken)
        self.assertTrue(toilet.is_available_for_use)
        self.assertEqual(repair_order["status"], "COMPLETE")

    def test_villager_relieves_in_open_when_no_toilet_available(self):
        """When toilet is broken and need_toilet is at 0%, villager relieves outdoors instead of freezing in IDLE."""
        toilet = Building("toilet", {(5, 5)})
        toilet.condition = 0.0
        self.bm.buildings.append(toilet)

        v = Villager("v1", "Alice", "Farmer", "female", 22, 1, "mother", "fam1")
        v.job = "Farmer"
        v.task = "SEEKING_TOILET"
        v.need_toilet = 0.0

        handled = ToiletSystem.execute_villager_toilet_routine(
            v, dt=0.1, building_manager=self.bm, all_entities=[v], player=None, furniture_manager=self.fm
        )
        self.assertTrue(handled)
        # Bodily need restored!
        self.assertGreaterEqual(v.need_toilet, 80.0)
        # Villager is relieved and ready to resume work (not stuck)
        self.assertNotEqual(v.task, "SEEKING_TOILET")


if __name__ == "__main__":
    unittest.main()
