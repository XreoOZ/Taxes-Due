import unittest
from types import SimpleNamespace

from game.systems.economy.wealth_system import VillageWealthSystem


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

    def test_empty_household_storage_chest_ignores_stale_currency_mirror(self):
        from game.buildings.furniture import Furniture
        family = SimpleNamespace(
            id="fam_1",
            surname="Weaver",
            members=[SimpleNamespace(id="w1", inventory={}, currency={})],
        )
        chest = Furniture("furn_2", "household_storage", 2, 2, family_id="fam_1", permit_id=1)
        chest.inventory = {"Copper": 0, "Silver": 0, "Gold": 0}
        chest.currency = {"Copper": 4, "Silver": 5, "Gold": 0}
        fm = SimpleNamespace(furnitures=[chest], get_storage_for_family=lambda fid: chest)
        wealth = VillageWealthSystem.calculate_village_wealth(
            villager_manager=SimpleNamespace(families=[family]),
            furniture_manager=fm,
            force_recompute=True,
        )
        self.assertEqual(wealth["households"][0]["wealth_copper"], 0)
        self.assertEqual(wealth["total_wealth_copper"], 0)

    def test_church_tax_prep_and_tithe_deposit_never_resurrect_or_double_coins(self):
        from game.buildings.furniture import Furniture, FurnitureManager
        from game.entities.villagers import Family, Villager
        from game.systems.economy.currency import to_copper, normalize_wallet
        from game.systems.village_life.church_system import ChurchSystem
        from game.world.permits import PermitManager

        pm = PermitManager()
        c_permit = pm.add_permit("Church", "church", {(0, 0)})
        ChurchSystem.set_tax_settings(0, 0, 1, pm)
        prev_enabled = ChurchSystem.is_tax_enabled()
        ChurchSystem.set_tax_enabled(True)
        try:
            fm = FurnitureManager()
            fam = Family("fam_1", "Cooper")
            rep = Villager("v1", "Bob", "Cooper", "Male", 30, 1, "Farmer", family_id="fam_1")
            fam.members.append(rep)
            chest = Furniture("c1", "household_storage", 2, 2, family_id="fam_1", permit_id=1)
            chest.inventory = {"Copper": 5, "Silver": 0, "Gold": 0}
            # Stale mirror says 1 Gold, 7 Silver -> MUST NEVER resurrect 1 Gold!
            chest.currency = {"Copper": 0, "Silver": 7, "Gold": 1}

            priest = Villager("p1", "Father", "Tom", "Male", 40, 1, "Priest", family_id="fam_p")
            priest_chest = Furniture("cp", "household_storage", 3, 3, family_id="fam_p", permit_id=2)
            fm.furnitures = [chest, priest_chest]

            prepared = ChurchSystem.prepare_church_tax_payment(rep, c_permit, fm, day_number=1)
            self.assertEqual(prepared, 1)
            self.assertEqual(to_copper(normalize_wallet(chest.inventory)), 4)

            paid = ChurchSystem.process_church_tax_payment(rep, priest, c_permit, fm, day_number=1)
            self.assertEqual(paid, 1)
            deposited = ChurchSystem.priest_deposit_tithes_home(priest, fm)
            # Must deposit exactly 1c (never 2c by summing priest.inventory + priest.currency)
            self.assertEqual(deposited, 1)
            self.assertEqual(to_copper(normalize_wallet(priest_chest.inventory)), 1)
        finally:
            ChurchSystem.set_tax_enabled(prev_enabled)


if __name__ == "__main__":
    unittest.main()
