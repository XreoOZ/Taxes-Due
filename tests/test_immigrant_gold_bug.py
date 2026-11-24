import unittest
from game.config import TILE_SIZE, DEFAULT_RESOURCES
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager
from game.world.navigation.pathfinding import GlobalPathRegistry
from game.entities.servants import ServantManager
from game.entities.villagers import VillagerManager
from game.buildings.furniture import FurnitureManager
from game.systems.economy.wealth_system import VillageWealthSystem
from game.systems.economy.household_inventory import get_household_possessions
from game.systems.village_life.immigration_system import ImmigrationSystem

class TestImmigrantGoldBug(unittest.TestCase):
    def setUp(self):
        GlobalPathRegistry.get_instance().clear()
        self.bm = BuildingManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.serv_m = ServantManager()
        self.resources = dict(DEFAULT_RESOURCES)
        
        treasury = self.fm.ensure_lord_treasury_chest(
            permit_manager=self.pm,
            villager_manager=self.vm,
            building_manager=self.bm,
            stockpile_manager=self.sm,
            preferred_tile=(2, 2)
        )
        treasury.inventory = {"Gold": 10}

    def test_household_possessions_carried_item_no_duplication(self):
        """Verifies that items carried in both m.inventory and m.carrying_res are counted once."""
        fam = self.vm.generate_starter_family(size=1)
        v = fam.members[0]
        v.inventory["Gold"] = 1
        v.carrying_res = "Gold"
        v.carrying_amount = 1
        
        poss = get_household_possessions(fam, furniture_manager=self.fm, stockpile_manager=self.sm)
        self.assertEqual(poss.get("Gold", 0), 1, "Carried item must not be counted twice in household possessions")

    def test_chestless_immigrant_gold_delivery_and_haul(self):
        """Full end-to-end test of grant delivery to chestless immigrant:
        1. Starter fund (1 Gold) granted from treasury chest (10 -> 9).
        2. Servant delivers and drops 1 Gold outside for homeless immigrant.
        3. Immigrant assigned to chestless house, retrieves 1 Gold.
        4. Immigrant hauls 1 Gold home and drops safely on lot floor.
        5. Total village wealth is strictly 10 Gold (9 Landlord + 1 Immigrant).
        """
        # 1. Spawn and accept immigrant
        imm = ImmigrationSystem()
        fam = self.vm.generate_starter_family(size=1)
        self.vm.families.remove(fam)
        self.vm.invalidate_villager_cache()

        v = fam.members[0]
        v.x = 25 * TILE_SIZE
        v.y = 25 * TILE_SIZE

        hh = {
            "id": "imm_1",
            "family": fam,
            "board_id": "board_1",
            "slot_index": 0,
            "state": "WAITING",
            "arrival_day": 1.0,
            "leave_dir": None,
            "reward_gold": 1,
        }
        imm.pending.append(hh)
        self.assertTrue(imm.accept("imm_1", self.vm, self.serv_m))

        # 2. Servant fetches from treasury and delivers to immigrant
        servant = self.serv_m.servants[0]
        servant._evaluate_and_assign_priority_task(
            self.bm, self.pm, self.sm, self.resources, player=None,
            all_servants=self.serv_m.servants, furniture_manager=self.fm,
            villager_manager=self.vm, servant_manager=self.serv_m
        )
        self.assertEqual(servant.state, "GRANT_FETCH")
        
        # Reach chest & fetch
        servant.x, servant.y = servant.target_grant_pos
        servant.update(
            0.1, self.bm, self.pm, self.sm, self.resources,
            player=None, all_servants=self.serv_m.servants,
            villager_manager=self.vm, furniture_manager=self.fm,
            servant_manager=self.serv_m
        )
        self.assertEqual(servant.state, "GRANT_DELIVER")
        self.assertEqual(servant.carried_res, "Gold")
        self.assertEqual(servant.carried_amount, 1)

        # Reach homeless immigrant & drop
        servant.x, servant.y = (v.x, v.y)
        servant.update(
            0.1, self.bm, self.pm, self.sm, self.resources,
            player=None, all_servants=self.serv_m.servants,
            villager_manager=self.vm, furniture_manager=self.fm,
            servant_manager=self.serv_m
        )
        self.assertEqual(servant.state, "IDLE")

        # 3. Assign family to a chestless house
        permit = AreaPermit("permit_house_1", "House Permit", "housing", [(5, 5), (5, 6), (6, 5), (6, 6)])
        self.pm.permits.append(permit)
        house = Building("house", {(5, 5), (6, 5), (5, 6), (6, 6)}, door_pos=(5, 6), door_side="bottom")
        self.bm.buildings.append(house)
        self.vm.assign_family_to_permit(fam.id, permit.id, self.pm, self.bm, self.fm)

        # 4. Villager retrieves the loose gold and hauls home
        for _ in range(300):
            v.update(
                0.1, self.pm, self.bm, self.serv_m.servants, player=None,
                stockpile_manager=self.sm, furniture_manager=self.fm,
                villager_manager=self.vm
            )

        # Verify: gold is at home, inventory cleared, wealth strictly 10
        self.assertEqual(v.inventory.get("Gold", 0), 0)
        self.assertIsNone(v.carrying_res)

        poss = get_household_possessions(fam, furniture_manager=self.fm, stockpile_manager=self.sm)
        self.assertEqual(poss.get("Gold", 0), 1)

        wealth = VillageWealthSystem.calculate_village_wealth(
            resources=self.resources, villager_manager=self.vm,
            furniture_manager=self.fm, building_manager=self.bm,
            stockpile_manager=self.sm, permit_manager=self.pm,
            force_recompute=True
        )
        self.assertEqual(wealth["total_wallet"]["Gold"], 10)
        self.assertEqual(wealth["landlord"]["wallet"]["Gold"], 9)
        self.assertEqual(wealth["households"][0]["wallet"]["Gold"], 1)
