import unittest

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager
from game.entities.villagers import Family, Villager
from game.systems.economy.market_pricing import MarketPricingSystem


class TestRealLifeSupplyDemandPricing(unittest.TestCase):
    def test_tool_price_matches_base_when_supply_equals_demand_and_is_bounded(self):
        # 2 Farmers -> demand for Hoe = 2; base_price = 10 Copper
        p_balanced = MarketPricingSystem.calculate_price("Hoe", 2, base_price=10, demand=2)
        self.assertEqual(p_balanced, 10)

        # Even at stock = 0, multiplier is capped at 2.0x (never 5x!)
        p_empty = MarketPricingSystem.calculate_price("Hoe", 0, base_price=10, demand=2)
        self.assertLessEqual(p_empty, 20)
        self.assertGreater(p_empty, 10)

        # Oversupply discounts gently without collapsing to 1 Copper
        p_oversupply = MarketPricingSystem.calculate_price("Hoe", 20, base_price=10, demand=2)
        self.assertGreaterEqual(p_oversupply, 5)
        self.assertLess(p_oversupply, 10)

    def test_demands_scale_with_population_and_workforce(self):
        bm = BuildingManager()
        fm = FurnitureManager()

        class DummyVM:
            def __init__(self, villagers, families):
                self._v = villagers
                self.families = families
            def get_all_villagers(self):
                return self._v

        # Small village: 2 Farmers
        fam_small = Family(1, "Small")
        small_vs = [Villager(i, 0, 0, f"F{i}", 25, 1, "Father", family_id=1) for i in range(2)]
        for v in small_vs:
            v.set_job("Farmer")
        dem_small = MarketPricingSystem.compute_village_demands(DummyVM(small_vs, [fam_small]), bm, fm)

        # Large village: 12 Farmers + 4 Miners
        fam_big = Family(2, "Big")
        big_vs = [Villager(i, 0, 0, f"V{i}", 25, 1, "Father", family_id=2) for i in range(16)]
        for v in big_vs[:12]:
            v.set_job("Farmer")
        for v in big_vs[12:]:
            v.set_job("Miner")
        dem_big = MarketPricingSystem.compute_village_demands(DummyVM(big_vs, [fam_small, fam_big]), bm, fm)

        self.assertGreater(dem_big["Potato"], dem_small["Potato"])
        self.assertGreater(dem_big["Water"], dem_small["Water"])
        self.assertGreater(dem_big["Hoe"], dem_small["Hoe"])
        self.assertGreater(dem_big["Pickaxe"], dem_small["Pickaxe"])
        self.assertGreater(dem_big["toilet"], dem_small["toilet"])
        self.assertGreater(dem_big["bed"], dem_small["bed"])

        # Same stock of 2 Hoes is normal in small village, scarce in large village
        p_small = MarketPricingSystem.calculate_price("Hoe", 2, base_price=10, demand=dem_small["Hoe"])
        p_big = MarketPricingSystem.calculate_price("Hoe", 2, base_price=10, demand=dem_big["Hoe"])
        self.assertEqual(p_small, 10)
        self.assertGreater(p_big, p_small)

    def test_village_supply_blending_and_stall_competition(self):
        bm = BuildingManager()
        m1 = Building("market", {(1, 1)})
        m1.auto_pricing = True
        m1.inventory = {"Hoe": 1}
        m2 = Building("market", {(4, 1)})
        m2.auto_pricing = True
        m2.inventory = {"Hoe": 6}
        bm.buildings.extend([m1, m2])

        supplies = MarketPricingSystem.compute_village_supplies(bm)
        self.assertEqual(supplies["Hoe"], 7)

        for m in (m1, m2):
            m.village_item_supplies = supplies
            m.village_item_demands = {"Hoe": 4}

        p1 = MarketPricingSystem.get_price(m1, "Hoe")
        p2 = MarketPricingSystem.get_price(m2, "Hoe")
        # Abundant stall is slightly cheaper or equal, and neither spikes wildly
        self.assertLessEqual(p2, p1)
        self.assertLessEqual(p1, 12)


if __name__ == "__main__":
    unittest.main()
