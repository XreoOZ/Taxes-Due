import unittest
from collections import Counter
from game.data.config import (
    TREE_WOOD_YIELD_MIN,
    TREE_WOOD_YIELD_MAX,
    TREE_WOOD_YIELD_DISTRIBUTION,
    MINE_YIELD_PER_INGAME_HOUR,
)
from game.world.natural_resources import NaturalResourceManager


class TestResourceYieldRebalance(unittest.TestCase):
    def test_wood_yield_config(self):
        """Wood yield must be between 1 and 2, with 80% for 1 and 20% for 2."""
        self.assertEqual(TREE_WOOD_YIELD_MIN, 1)
        self.assertEqual(TREE_WOOD_YIELD_MAX, 2)
        dist = {entry["amount"]: entry["weight"] for entry in TREE_WOOD_YIELD_DISTRIBUTION}
        self.assertAlmostEqual(dist[1], 0.80)
        self.assertAlmostEqual(dist[2], 0.20)

    def test_mine_yield_tiers_config(self):
        """Mine yield must have 6 tiers with the specified rates and probabilities."""
        self.assertEqual(len(MINE_YIELD_PER_INGAME_HOUR), 6)

        # Tier 1: Scarce (0-1/hr, 0: 50%, 1: 50%)
        t1 = MINE_YIELD_PER_INGAME_HOUR[1]
        self.assertEqual(t1["min"], 0)
        self.assertEqual(t1["max"], 1)
        d1 = {e["amount"]: e["weight"] for e in t1["yield_distribution"]}
        self.assertAlmostEqual(d1[0], 0.50)
        self.assertAlmostEqual(d1[1], 0.50)

        # Tier 2: Low (0-1/hr, 0: 30%, 1: 70%)
        t2 = MINE_YIELD_PER_INGAME_HOUR[2]
        self.assertEqual(t2["min"], 0)
        self.assertEqual(t2["max"], 1)
        d2 = {e["amount"]: e["weight"] for e in t2["yield_distribution"]}
        self.assertAlmostEqual(d2[0], 0.30)
        self.assertAlmostEqual(d2[1], 0.70)

        # Tier 3: Normal (1/hr, 100% 1)
        t3 = MINE_YIELD_PER_INGAME_HOUR[3]
        self.assertEqual(t3["min"], 1)
        self.assertEqual(t3["max"], 1)
        d3 = {e["amount"]: e["weight"] for e in t3["yield_distribution"]}
        self.assertAlmostEqual(d3[1], 1.00)

        # Tier 4: Rich (1-2/hr, 1: 80%, 2: 20%)
        t4 = MINE_YIELD_PER_INGAME_HOUR[4]
        self.assertEqual(t4["min"], 1)
        self.assertEqual(t4["max"], 2)
        d4 = {e["amount"]: e["weight"] for e in t4["yield_distribution"]}
        self.assertAlmostEqual(d4[1], 0.80)
        self.assertAlmostEqual(d4[2], 0.20)

        # Tier 5: Very Rich (1-2/hr, 1: 50%, 2: 50%)
        t5 = MINE_YIELD_PER_INGAME_HOUR[5]
        self.assertEqual(t5["min"], 1)
        self.assertEqual(t5["max"], 2)
        d5 = {e["amount"]: e["weight"] for e in t5["yield_distribution"]}
        self.assertAlmostEqual(d5[1], 0.50)
        self.assertAlmostEqual(d5[2], 0.50)

        # Tier 6: Abundant (2/hr, 100% 2)
        t6 = MINE_YIELD_PER_INGAME_HOUR[6]
        self.assertEqual(t6["min"], 2)
        self.assertEqual(t6["max"], 2)
        d6 = {e["amount"]: e["weight"] for e in t6["yield_distribution"]}
        self.assertAlmostEqual(d6[2], 1.00)

    def test_roll_mine_yield_simulation(self):
        """Simulate rolls for all mine tiers and verify distribution matches expectations."""
        n_rolls = 2000

        # Tier 3 must ALWAYS yield 1
        mine_t3 = {"tier": 3, "kind": "Stone Mine"}
        results_t3 = [NaturalResourceManager.roll_mine_yield(mine_t3) for _ in range(n_rolls)]
        self.assertTrue(all(r == 1 for r in results_t3))

        # Tier 6 must ALWAYS yield 2
        mine_t6 = {"tier": 6, "kind": "Iron Mine"}
        results_t6 = [NaturalResourceManager.roll_mine_yield(mine_t6) for _ in range(n_rolls)]
        self.assertTrue(all(r == 2 for r in results_t6))

        # Tier 1 (50% 0, 50% 1)
        mine_t1 = {"tier": 1, "kind": "Stone Mine"}
        results_t1 = [NaturalResourceManager.roll_mine_yield(mine_t1) for _ in range(n_rolls)]
        c1 = Counter(results_t1)
        self.assertTrue(set(c1.keys()).issubset({0, 1}))
        self.assertAlmostEqual(c1[0] / n_rolls, 0.50, delta=0.06)

        # Tier 2 (30% 0, 70% 1)
        mine_t2 = {"tier": 2, "kind": "Stone Mine"}
        results_t2 = [NaturalResourceManager.roll_mine_yield(mine_t2) for _ in range(n_rolls)]
        c2 = Counter(results_t2)
        self.assertTrue(set(c2.keys()).issubset({0, 1}))
        self.assertAlmostEqual(c2[0] / n_rolls, 0.30, delta=0.06)

        # Tier 4 (80% 1, 20% 2)
        mine_t4 = {"tier": 4, "kind": "Iron Mine"}
        results_t4 = [NaturalResourceManager.roll_mine_yield(mine_t4) for _ in range(n_rolls)]
        c4 = Counter(results_t4)
        self.assertTrue(set(c4.keys()).issubset({1, 2}))
        self.assertAlmostEqual(c4[1] / n_rolls, 0.80, delta=0.06)

        # Tier 5 (50% 1, 50% 2)
        mine_t5 = {"tier": 5, "kind": "Iron Mine"}
        results_t5 = [NaturalResourceManager.roll_mine_yield(mine_t5) for _ in range(n_rolls)]
        c5 = Counter(results_t5)
        self.assertTrue(set(c5.keys()).issubset({1, 2}))
        self.assertAlmostEqual(c5[1] / n_rolls, 0.50, delta=0.06)

    def test_wood_yield_roll_simulation(self):
        """Simulate wood yield rolls and verify 80% 1 and 20% 2."""
        import random
        from game.data.config import TREE_WOOD_YIELD_DISTRIBUTION
        n_rolls = 2000
        rolls = [
            random.choices(
                [int(entry["amount"]) for entry in TREE_WOOD_YIELD_DISTRIBUTION],
                weights=[float(entry["weight"]) for entry in TREE_WOOD_YIELD_DISTRIBUTION],
            )[0]
            for _ in range(n_rolls)
        ]
        c = Counter(rolls)
        self.assertTrue(set(c.keys()).issubset({1, 2}))
        self.assertAlmostEqual(c[1] / n_rolls, 0.80, delta=0.06)
        self.assertAlmostEqual(c[2] / n_rolls, 0.20, delta=0.06)


if __name__ == "__main__":
    unittest.main()
