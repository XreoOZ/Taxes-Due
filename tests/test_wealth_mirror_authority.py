import unittest
from types import SimpleNamespace

from game.systems.wealth_system import VillageWealthSystem


class TestWealthMirrorAuthority(unittest.TestCase):
    def setUp(self):
        self.original_cache = (
            VillageWealthSystem._cached_result,
            VillageWealthSystem._is_dirty,
            VillageWealthSystem._last_calc_time,
        )

    def tearDown(self):
        (
            VillageWealthSystem._cached_result,
            VillageWealthSystem._is_dirty,
            VillageWealthSystem._last_calc_time,
        ) = self.original_cache

    def test_stale_currency_mirror_does_not_inflate_physical_wealth(self):
        family = SimpleNamespace(
            id="carter",
            surname="Carter",
            members=[
                SimpleNamespace(
                    id="carter-member",
                    inventory={"Copper": 1, "Gold": 1},
                    currency={"Copper": 8, "Silver": 9},
                )
            ],
        )
        villager_manager = SimpleNamespace(families=[family])

        wealth = VillageWealthSystem.calculate_village_wealth(
            villager_manager=villager_manager,
            force_recompute=True,
        )

        self.assertEqual(wealth["households"][0]["wealth_copper"], 101)
        self.assertEqual(wealth["total_wealth_copper"], 101)

    def test_legacy_currency_is_used_when_no_inventory_coins_exist(self):
        family = SimpleNamespace(
            id="legacy",
            surname="Legacy",
            members=[
                SimpleNamespace(
                    id="legacy-member",
                    inventory={"Hoe": 1},
                    currency={"Silver": 2},
                )
            ],
        )
        villager_manager = SimpleNamespace(families=[family])

        wealth = VillageWealthSystem.calculate_village_wealth(
            villager_manager=villager_manager,
            force_recompute=True,
        )

        self.assertEqual(wealth["households"][0]["wealth_copper"], 20)

    def test_screenshot_coin_sources_total_without_stale_currency_mirrors(self):
        households = [
            ("fisher", "Fisher", {"Copper": 12, "Silver": 3}, {"Copper": 3}),
            ("carter", "Carter", {"Copper": 1, "Gold": 1}, {"Copper": 8, "Silver": 9}),
            ("thatcher", "Thatcher", {"Copper": 9, "Silver": 1, "Gold": 1},
             {"Copper": 2, "Silver": 9}),
            ("potter", "Potter", {"Silver": 4, "Gold": 1}, {}),
        ]
        families = []
        furniture = []
        for family_id, surname, coins, mirror in households:
            family = SimpleNamespace(
                id=family_id,
                surname=surname,
                members=[SimpleNamespace(
                    id=f"{family_id}-member",
                    inventory={},
                    currency={},
                )],
            )
            families.append(family)
            furniture.append(SimpleNamespace(
                family_id=family_id,
                inventory=coins,
                currency=mirror,
            ))
        treasury = SimpleNamespace(
            furniture_type="lord_treasury_chest",
            family_id=None,
            inventory={"Copper": 9, "Silver": 8, "Gold": 5},
        )
        furniture.append(treasury)
        furniture_manager = SimpleNamespace(
            furnitures=furniture,
            get_lord_treasury_chest=lambda: treasury,
        )
        building_manager = SimpleNamespace(buildings=[
            SimpleNamespace(
                building_type="market",
                assigned_household_id=None,
                assigned_family_id=None,
                currency={"Copper": 8},
            )
        ])

        wealth = VillageWealthSystem.calculate_village_wealth(
            resources={"Copper": 0, "Silver": 0, "Gold": 0},
            villager_manager=SimpleNamespace(families=families),
            furniture_manager=furniture_manager,
            building_manager=building_manager,
            force_recompute=True,
        )

        self.assertEqual(wealth["landlord"]["wealth_copper"], 597)
        self.assertEqual(
            {household["name"]: household["wealth_copper"]
             for household in wealth["households"]},
            {
                "The Fisher Family": 42,
                "The Carter Family": 101,
                "The Thatcher Family": 119,
                "The Potter Family": 140,
            },
        )
        self.assertEqual(wealth["total_wealth_copper"], 999)


if __name__ == "__main__":
    unittest.main()
