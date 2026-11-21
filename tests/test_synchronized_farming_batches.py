"""
Test Suite for Synchronized Farming Batches
Verifies all 10 Acceptance Criteria:
1. All crops planted in one batch become harvestable simultaneously after exactly 10 in-game days.
2. Tiles missed before batch closure remain empty.
3. Late planting cannot join a closed batch.
4. Missed tiles can be planted in the next batch.
5. Multiple farmers can plant different tiles simultaneously.
6. One unavailable farmer does not stop the others.
7. Growing crops cannot be planted again.
8. Harvested tiles can enter a future batch correctly.
9. Save/load preserves batch timing, tile membership, and growth progress.
10. Existing harvesting, production, and distribution systems remain functional.
"""

import unittest
from game.world.permits import AreaPermit, FarmingBatch, PermitManager
from game.systems.save_system import serialize_game_state, deserialize_game_state
from game.systems.day_cycle import DayCycleSystem
from game.entities.player import Player
from game.buildings.building_manager import BuildingManager
from game.world.stockpile import StockpileManager
from game.buildings.furniture import FurnitureManager
from game.entities.villagers import VillagerManager, Family, Villager
from game.entities.servants import ServantManager
from game.systems.schedule import ScheduleManager
from game.systems.production_distribution import ProductionDistributionSystem


class TestSynchronizedFarmingBatches(unittest.TestCase):

    def setUp(self):
        self.tiles = {(0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1)}
        self.permit = AreaPermit(1, "North Farm", "farm", self.tiles)
        self.permit.set_crop("Potato")

    def test_01_simultaneous_harvest_after_10_days(self):
        """1. All crops planted in one batch become harvestable simultaneously after exactly 10 in-game days."""
        # Start batch at day 1.0
        batch = self.permit.start_planting_batch(start_day=1.0)
        for t in self.tiles:
            success = self.permit.till_and_sow_tile(t[0], t[1], current_day=1.0)
            self.assertTrue(success)

        # Check membership
        self.assertEqual(len(batch.tiles), len(self.tiles))
        for t in self.tiles:
            self.assertEqual(self.permit.tile_crops[t]["batch_id"], batch.id)

        # Simulate 9 days of watering and growth
        for day in range(1, 10):
            for t in self.tiles:
                self.permit.water_tile(t[0], t[1])
            self.permit.update_growth(1.0, current_day=float(day))
            # Not yet harvestable at day < 10
            self.assertEqual(len(self.permit.get_harvestable_tiles()), 0)
            self.assertFalse(batch.is_harvestable)
            for t in self.tiles:
                self.assertAlmostEqual(self.permit.tile_crops[t]["growth_days"], float(day))

        # Day 10 arrives
        for t in self.tiles:
            self.permit.water_tile(t[0], t[1])
        self.permit.update_growth(1.0, current_day=10.0)

        # All crops become harvestable simultaneously at the exact same moment!
        self.assertTrue(batch.is_harvestable)
        self.assertAlmostEqual(batch.growth_days, 10.0)
        harvestable = self.permit.get_harvestable_tiles()
        self.assertEqual(len(harvestable), len(self.tiles))
        for t in self.tiles:
            self.assertIn(t, harvestable)
            self.assertAlmostEqual(self.permit.tile_crops[t]["growth_days"], 10.0)

    def test_02_and_03_missed_tiles_remain_empty_and_late_planting_rejected(self):
        """
        2. Tiles missed before batch closure remain empty.
        3. Late planting cannot join a closed batch.
        """
        # Batch 1 starts with 4 planted tiles, leaving 2 unplanted
        batch1 = self.permit.start_planting_batch(start_day=1.0)
        planted = [(0, 0), (1, 0), (2, 0), (3, 0)]
        unplanted = [(0, 1), (1, 1)]

        for t in planted:
            self.permit.till_and_sow_tile(t[0], t[1], current_day=1.0)

        # Close Batch 1 planting window
        self.permit.close_active_batch(current_day=2.0)
        self.assertTrue(batch1.closed)

        # Missed tiles must remain empty
        empty_tiles = self.permit.get_empty_tiles()
        for t in unplanted:
            self.assertIn(t, empty_tiles)
            tc = self.permit.tile_crops.get(t)
            self.assertTrue(tc is None or tc.get("crop") is None)

        # Late planting cannot join closed batch
        for t in unplanted:
            res = self.permit.till_and_sow_tile(t[0], t[1], current_day=2.5)
            self.assertFalse(res, "Late planting must not be accepted into closed batch!")
            self.assertNotIn(t, batch1.tiles)

    def test_04_missed_tiles_can_be_planted_in_next_batch(self):
        """4. Missed tiles can be planted in the next batch."""
        # Batch 1: 4 tiles planted at day 1.0, 2 missed
        batch1 = self.permit.start_planting_batch(start_day=1.0)
        for t in [(0, 0), (1, 0), (2, 0), (3, 0)]:
            self.permit.till_and_sow_tile(t[0], t[1], current_day=1.0)
            self.permit.water_tile(t[0], t[1])
        # Day 1 growth for Batch 1
        self.permit.update_growth(1.0, current_day=1.0)
        self.permit.close_active_batch(current_day=2.0)

        # Open Batch 2 at day 2.0
        batch2 = self.permit.open_next_batch(start_day=2.0)
        self.assertNotEqual(batch1.id, batch2.id)

        # Plant the missed tiles into Batch 2
        for t in [(0, 1), (1, 1)]:
            res = self.permit.till_and_sow_tile(t[0], t[1], current_day=2.0)
            self.assertTrue(res)
            self.assertIn(t, batch2.tiles)
            self.assertEqual(self.permit.tile_crops[t]["batch_id"], batch2.id)

        # Advance 9 days (from day 2 to day 10):
        # Batch 1 reaches 1.0 + 9.0 = 10.0 days (harvestable)
        # Batch 2 reaches 0.0 + 9.0 = 9.0 days (not harvestable yet)
        for day in range(2, 11):
            for t in self.tiles:
                self.permit.water_tile(t[0], t[1])
            self.permit.update_growth(1.0, current_day=float(day))

        # At day 10: Batch 1 is harvestable, Batch 2 is NOT
        self.assertTrue(batch1.is_harvestable)
        self.assertFalse(batch2.is_harvestable)
        ready_tiles = self.permit.get_harvestable_tiles()
        self.assertEqual(len(ready_tiles), 4)
        for t in [(0, 0), (1, 0), (2, 0), (3, 0)]:
            self.assertIn(t, ready_tiles)
        for t in [(0, 1), (1, 1)]:
            self.assertNotIn(t, ready_tiles)

        # Advance 1 more day: Batch 2 reaches 10 days and becomes harvestable!
        for t in self.tiles:
            self.permit.water_tile(t[0], t[1])
        self.permit.update_growth(1.0, current_day=11.0)
        self.assertTrue(batch2.is_harvestable)
        ready_tiles_day11 = self.permit.get_harvestable_tiles()
        self.assertEqual(len(ready_tiles_day11), 6)

    def test_05_and_06_farmer_parallelism_and_resilience(self):
        """
        5. Multiple farmers can plant different tiles simultaneously.
        6. One unavailable farmer does not stop the others.
        """
        # Farmer 1 and Farmer 2 reserve distinct eligible tiles
        avail = self.permit.get_available_untilled_tiles()
        self.assertEqual(len(avail), 6)

        # Farmer 1 reserves tile (0, 0)
        f1_tile = avail[0]
        self.assertTrue(self.permit.reserve_tile(f1_tile[0], f1_tile[1], worker_id=101, task_type="TILL"))

        # Farmer 2 queries available tiles - (0,0) is excluded
        avail_for_f2 = self.permit.get_available_untilled_tiles(worker_id=102)
        self.assertNotIn(f1_tile, avail_for_f2)

        # Farmer 2 reserves tile (1, 0)
        f2_tile = avail_for_f2[0]
        self.assertTrue(self.permit.reserve_tile(f2_tile[0], f2_tile[1], worker_id=102, task_type="TILL"))

        # Scenario 6: Farmer 1 becomes unavailable / drops out
        self.permit.release_worker_reservations(worker_id=101)
        self.assertFalse(self.permit.is_tile_reserved(f1_tile[0], f1_tile[1]))

        # Farmer 2 continues unaffected and finishes tilling/sowing
        self.assertTrue(self.permit.till_and_sow_tile(f2_tile[0], f2_tile[1]))
        self.permit.release_tile_reservation(f2_tile[0], f2_tile[1], worker_id=102)

        # Farmer 3 can now pick up Farmer 1's abandoned tile
        avail_for_f3 = self.permit.get_available_untilled_tiles(worker_id=103)
        self.assertIn(f1_tile, avail_for_f3)
        self.assertNotIn(f2_tile, avail_for_f3)  # f2_tile is now planted!

    def test_07_growing_crops_cannot_be_planted_again(self):
        """7. Growing crops cannot be planted again."""
        self.permit.start_planting_batch(start_day=1.0)
        self.assertTrue(self.permit.till_and_sow_tile(0, 0, current_day=1.0))

        # Replanting an occupied growing tile must be rejected
        res = self.permit.till_and_sow_tile(0, 0, current_day=1.0)
        self.assertFalse(res, "Cannot plant on a tile already occupied by a growing crop!")

    def test_08_harvested_tiles_can_enter_future_batch(self):
        """8. Harvested tiles can enter a future batch correctly."""
        self.permit.start_planting_batch(start_day=1.0)
        self.permit.till_and_sow_tile(0, 0, current_day=1.0)
        self.permit.water_tile(0, 0)
        self.permit.update_growth(10.0, current_day=10.0)

        # Tile is ready to harvest
        self.assertIn((0, 0), self.permit.get_harvestable_tiles())
        yield_amount = self.permit.harvest_tile(0, 0)
        self.assertEqual(yield_amount, 2)

        # Tile is now empty again and eligible for next batch
        self.assertIn((0, 0), self.permit.get_empty_tiles())

        # Open Batch 2 and plant into it
        batch2 = self.permit.open_next_batch(start_day=11.0)
        success = self.permit.till_and_sow_tile(0, 0, current_day=11.0)
        self.assertTrue(success)
        self.assertIn((0, 0), batch2.tiles)
        self.assertEqual(self.permit.tile_crops[(0, 0)]["batch_id"], batch2.id)

    def test_09_save_load_preserves_batch_system(self):
        """9. Save/load preserves batch timing, tile membership, and growth progress."""
        # Setup permit with Batch 1 (closed, 6.0 growth days) and Batch 2 (open, 1.0 growth day)
        pm = PermitManager()
        pm.permits.clear()
        pm.permits.append(self.permit)

        # Batch 1
        b1 = self.permit.start_planting_batch(start_day=1.0)
        self.permit.till_and_sow_tile(0, 0, current_day=1.0)
        self.permit.till_and_sow_tile(1, 0, current_day=1.0)
        self.permit.water_tile(0, 0)
        self.permit.water_tile(1, 0)
        self.permit.update_growth(6.0, current_day=7.0)
        self.permit.close_active_batch(current_day=7.0)

        # Midnight transition: resets daily watering
        self.permit.reset_daily_watering()

        # Batch 2
        b2 = self.permit.open_next_batch(start_day=7.0)
        self.permit.till_and_sow_tile(2, 0, current_day=7.0)
        self.permit.water_tile(2, 0)
        self.permit.update_growth(0.5, current_day=7.5)

        # Setup supporting dummy managers for serialization
        dc = DayCycleSystem()
        dc.day_number = 7
        res = {"food": 10}
        player = Player(100, 100)
        bm = BuildingManager()
        sm = StockpileManager()
        fm = FurnitureManager()
        vm = VillagerManager()
        svm = ServantManager()
        sched_m = ScheduleManager()

        # Serialize
        saved_data = serialize_game_state(dc, res, player, pm, bm, sm, fm, vm, svm, sched_m)

        # Create new managers to deserialize into
        new_pm = PermitManager()
        new_bm = BuildingManager()
        new_sm = StockpileManager()
        new_fm = FurnitureManager()
        new_vm = VillagerManager()
        new_svm = ServantManager()
        new_sched_m = ScheduleManager()
        new_dc = DayCycleSystem()
        new_res = {}
        new_player = Player(0, 0)

        # Deserialize
        deserialize_game_state(saved_data, new_dc, new_res, new_player, new_pm, new_bm, new_sm, new_fm, new_vm, new_svm, new_sched_m)

        # Verify loaded permit
        self.assertEqual(len(new_pm.permits), 1)
        loaded_p = new_pm.permits[0]
        self.assertEqual(len(loaded_p.batches), 2)

        # Verify Batch 1
        self.assertIn(b1.id, loaded_p.batches)
        loaded_b1 = loaded_p.batches[b1.id]
        self.assertTrue(loaded_b1.closed)
        self.assertEqual(loaded_b1.start_day, 1.0)
        self.assertAlmostEqual(loaded_b1.growth_days, 6.0)
        self.assertEqual(loaded_b1.tiles, {(0, 0), (1, 0)})

        # Verify Batch 2
        self.assertIn(b2.id, loaded_p.batches)
        loaded_b2 = loaded_p.batches[b2.id]
        self.assertFalse(loaded_b2.closed)
        self.assertEqual(loaded_b2.start_day, 7.0)
        self.assertAlmostEqual(loaded_b2.growth_days, 0.5)
        self.assertEqual(loaded_b2.tiles, {(2, 0)})

        # Verify empty tiles remain empty
        empty = loaded_p.get_empty_tiles()
        self.assertIn((3, 0), empty)
        self.assertIn((0, 1), empty)
        self.assertIn((1, 1), empty)

    def test_10_production_and_distribution_compatibility(self):
        """10. Existing harvesting, production, and distribution systems remain functional."""
        self.permit.start_planting_batch(start_day=1.0)
        for t in self.tiles:
            self.permit.till_and_sow_tile(t[0], t[1], current_day=1.0)
            self.permit.water_tile(t[0], t[1])
        self.permit.update_growth(10.0, current_day=10.0)

        # Total harvest from 6 tiles at 2 potatoes per tile = 12 potatoes
        harvestable = self.permit.get_harvestable_tiles()
        self.assertEqual(len(harvestable), 6)
        total_yield = sum(self.permit.harvest_tile(t[0], t[1]) for t in harvestable)
        self.assertEqual(total_yield, 12)

        # Distribute into households: Household 1 has 1 worker, Household 2 has 2 workers
        from game.buildings.furniture import Furniture
        fm = FurnitureManager()
        # Setup chest in house 1
        c1 = Furniture(1, "household_storage", 10, 10, permit_id=10, family_id=1)
        # Setup chest in house 2
        c2 = Furniture(2, "household_storage", 20, 20, permit_id=20, family_id=2)
        fm.furnitures = [c1, c2]

        participating_workers = {"1": 1, "2": 2}  # Household 1 has 1 worker, Household 2 has 2 workers
        ps = ProductionDistributionSystem()
        dist_result = ps.distribute_production(
            resource_name="Potato",
            amount=total_yield,
            participating_workers=participating_workers,
            furniture_manager=fm,
            stockpile_manager=None,
            workplace_id=self.permit.id,
            auto_deposit=True
        )

        dist = dist_result["distribution"]
        # House 1 receives 1/3 (4 potatoes), House 2 receives 2/3 (8 potatoes)
        self.assertEqual(dist["1"], 4)
        self.assertEqual(dist["2"], 8)
        self.assertEqual(c1.inventory.get("Potato", 0), 4)
        self.assertEqual(c2.inventory.get("Potato", 0), 8)


if __name__ == "__main__":
    unittest.main()
