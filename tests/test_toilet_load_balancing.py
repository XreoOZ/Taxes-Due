"""
Unit tests for Toilet Load Balancing & Smart Queue Distribution
"""
import unittest
from game.config import TILE_SIZE
from game.data.config import (
    TOILET_QUEUE_DISTANCE_PENALTY,
    TOILET_OCCUPIED_DISTANCE_PENALTY,
    TOILET_REEVALUATE_INTERVAL_SECONDS,
    TOILET_REEVALUATE_SCORE_MARGIN,
)
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.entities.villagers import Villager
from game.systems.village_life.toilet_system import ToiletSystem


class TestToiletLoadBalancing(unittest.TestCase):
    def setUp(self):
        self.building_mgr = BuildingManager()

        # Create 3 toilets at different coordinates:
        # Toilet A: (10, 10) -> (672, 672)
        # Toilet B: (12, 10) -> (800, 672) (approx 128px further from origin)
        # Toilet C: (15, 10) -> (992, 672) (approx 320px further from origin)
        self.toilet_a = Building("toilet", {(10, 10)})
        self.toilet_b = Building("toilet", {(12, 10)})
        self.toilet_c = Building("toilet", {(15, 10)})
        self.building_mgr.buildings.extend([self.toilet_a, self.toilet_b, self.toilet_c])

    def test_empty_toilets_picks_closest(self):
        """When all toilets are free, villager chooses the physically closest toilet."""
        v = Villager("v1", "Alice", "Smith", "F", 25, 1, "Farmer", "fam1")
        # Alice is close to Toilet A
        v.x, v.y = 9 * TILE_SIZE, 10 * TILE_SIZE

        chosen, is_free = ToiletSystem.find_best_toilet(v, self.building_mgr)
        self.assertEqual(chosen, self.toilet_a)
        self.assertTrue(is_free)

    def test_congested_closest_toilet_diverts_to_free_toilet(self):
        """
        When closest Toilet A has 2 people in queue, a new villager
        should pick Toilet B (free) even if Toilet B is slightly further.
        """
        # Occupy Toilet A and add 2 people to its queue
        self.toilet_a.toilet_active_user = "v_other1"
        self.toilet_a.toilet_queue = ["v_other2", "v_other3"]

        # Toilet B and C are empty
        self.toilet_b.toilet_active_user = None
        self.toilet_b.toilet_queue = []
        self.toilet_c.toilet_active_user = None
        self.toilet_c.toilet_queue = []

        v = Villager("v_new", "Bob", "Smith", "M", 28, 1, "Miner", "fam1")
        v.x, v.y = 9 * TILE_SIZE, 10 * TILE_SIZE

        chosen, is_free = ToiletSystem.find_best_toilet(v, self.building_mgr)
        # Bob should pick Toilet B instead of joining the long queue at Toilet A!
        self.assertEqual(chosen, self.toilet_b)
        self.assertTrue(is_free)

    def test_three_villagers_distribute_across_three_toilets(self):
        """
        Three villagers seeking toilets consecutively should each pick a different toilet,
        preventing single-toilet bottlenecks.
        """
        v1 = Villager("v1", "Villager1", "Doe", "M", 20, 1, "Farmer", "fam1")
        v2 = Villager("v2", "Villager2", "Doe", "M", 21, 1, "Farmer", "fam1")
        v3 = Villager("v3", "Villager3", "Doe", "M", 22, 1, "Farmer", "fam1")

        for v in (v1, v2, v3):
            v.x, v.y = 9 * TILE_SIZE, 10 * TILE_SIZE

        # V1 chooses and claims
        chosen1, _ = ToiletSystem.find_best_toilet(v1, self.building_mgr)
        self.assertEqual(chosen1, self.toilet_a)
        ToiletSystem.request_toilet_access(v1, chosen1)

        # V2 chooses and claims
        chosen2, _ = ToiletSystem.find_best_toilet(v2, self.building_mgr)
        self.assertEqual(chosen2, self.toilet_b)
        ToiletSystem.request_toilet_access(v2, chosen2)

        # V3 chooses and claims
        chosen3, _ = ToiletSystem.find_best_toilet(v3, self.building_mgr)
        self.assertEqual(chosen3, self.toilet_c)
        ToiletSystem.request_toilet_access(v3, chosen3)

        # All 3 toilets are now utilized in parallel!
        self.assertEqual(self.toilet_a.toilet_active_user, "v1")
        self.assertEqual(self.toilet_b.toilet_active_user, "v2")
        self.assertEqual(self.toilet_c.toilet_active_user, "v3")

        # Now 3 more villagers arrive. They should distribute evenly across the queues:
        # V4 -> A (queue 1), V5 -> B (queue 1), V6 -> C (queue 1)
        v4 = Villager("v4", "Villager4", "Doe", "M", 23, 1, "Farmer", "fam1")
        v5 = Villager("v5", "Villager5", "Doe", "M", 24, 1, "Farmer", "fam1")
        v6 = Villager("v6", "Villager6", "Doe", "M", 25, 1, "Farmer", "fam1")
        for v in (v4, v5, v6):
            v.x, v.y = 9 * TILE_SIZE, 10 * TILE_SIZE

        chosen4, _ = ToiletSystem.find_best_toilet(v4, self.building_mgr)
        self.assertEqual(chosen4, self.toilet_a)
        ToiletSystem.request_toilet_access(v4, chosen4)

        chosen5, _ = ToiletSystem.find_best_toilet(v5, self.building_mgr)
        self.assertEqual(chosen5, self.toilet_b)
        ToiletSystem.request_toilet_access(v5, chosen5)

        chosen6, _ = ToiletSystem.find_best_toilet(v6, self.building_mgr)
        self.assertEqual(chosen6, self.toilet_c)
        ToiletSystem.request_toilet_access(v6, chosen6)

        # Each toilet now has exactly 1 active user and 1 in queue!
        self.assertEqual(len(self.toilet_a.toilet_queue), 1)
        self.assertEqual(len(self.toilet_b.toilet_queue), 1)
        self.assertEqual(len(self.toilet_c.toilet_queue), 1)

    def test_dynamic_reevaluation_switches_when_better_toilet_opens(self):
        """
        If a villager is queued at Toilet A and Toilet B frees up and is much better,
        they should switch to Toilet B.
        """
        # Toilet A has 1 active user and 1 ahead in queue
        self.toilet_a.toilet_active_user = "user_inside"
        self.toilet_a.toilet_queue = ["ahead_in_line"]

        # Villager 4 joins line at Toilet A
        v4 = Villager("v4", "Switchy", "Doe", "M", 30, 1, "Builder", "fam1")
        v4.x, v4.y = 10 * TILE_SIZE, 12 * TILE_SIZE
        v4.task = "SEEKING_TOILET"
        v4.target_toilet = self.toilet_a
        v4.toilet_use_timer = 0.0

        # Enqueue v4 at Toilet A
        ToiletSystem.request_toilet_access(v4, self.toilet_a)
        self.assertIn("v4", self.toilet_a.toilet_queue)

        # Toilet B is now free (empty)
        self.toilet_b.toilet_active_user = None
        self.toilet_b.toilet_queue = []

        # Advance reevaluation timer past interval
        v4.toilet_reeval_timer = TOILET_REEVALUATE_INTERVAL_SECONDS + 0.1

        handled = ToiletSystem.execute_villager_toilet_routine(v4, 0.1, self.building_mgr)
        self.assertTrue(handled)

        # v4 should have switched target to toilet_b and left toilet_a's queue
        self.assertEqual(v4.target_toilet, self.toilet_b)
        self.assertNotIn("v4", self.toilet_a.toilet_queue)


if __name__ == "__main__":
    unittest.main()
