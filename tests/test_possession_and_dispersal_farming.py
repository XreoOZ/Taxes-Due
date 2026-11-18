import unittest
import pygame
from game.config import TILE_SIZE, WATERING_DURATION_INGAME_HOURS, TILLING_DURATION_INGAME_HOURS
from game.buildings.buildings import BuildingManager, Building
from game.buildings.furniture import FurnitureManager
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.entities.villagers import VillagerManager, Villager, Family
from game.entities.servants import ServantManager, Servant
from game.systems.day_cycle import DayCycleSystem

class TestPossessionAndDispersalFarming(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.building_manager = BuildingManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()
        self.furniture_manager = FurnitureManager()
        self.villager_manager = VillagerManager()
        self.servant_manager = ServantManager()
        self.day_cycle = DayCycleSystem()

        # Wire up furniture_manager
        self.furniture_manager.set_managers(
            building_manager=self.building_manager,
            permit_manager=self.permit_manager,
            villager_manager=self.villager_manager
        )

    def test_smart_chest_ownership_from_beds(self):
        """Chest in same house as family beds automatically belongs to that family even without permit."""
        # 1. Create a wooden house of 18 tiles (6x3) at (10, 10) to (15, 12)
        house_tiles = [(gx, gy) for gx in range(10, 16) for gy in range(10, 13)]
        b = Building("wooden_structure", house_tiles, door_pos=(10, 11))
        self.building_manager.buildings.append(b)
        self.assertIsNotNone(b)

        # 2. Add family with 2 members
        fam = self.villager_manager.generate_random_family()
        fam.id = "fam_ward"
        for m in fam.members:
            m.family_id = "fam_ward"

        # 3. Place beds inside the house
        bed1, _ = self.furniture_manager.add_furniture("bed", 11, 12, self.permit_manager, self.villager_manager, building_manager=self.building_manager)
        bed2, _ = self.furniture_manager.add_furniture("bed", 12, 12, self.permit_manager, self.villager_manager, building_manager=self.building_manager)
        bed1.family_id = "fam_ward"
        bed2.family_id = "fam_ward"

        # 4. Place chest inside the house (unassigned initially)
        chest, _ = self.furniture_manager.add_furniture("household_storage", 10, 12, self.permit_manager, self.villager_manager, building_manager=self.building_manager)
        
        # 5. Smart lookup should resolve chest for fam_ward
        found_chest = self.furniture_manager.get_storage_for_family("fam_ward", building_manager=self.building_manager, villager_manager=self.villager_manager, permit_manager=self.permit_manager)
        self.assertIsNotNone(found_chest)
        self.assertEqual(found_chest.id, chest.id)
        self.assertEqual(found_chest.family_id, "fam_ward")

    def test_stow_unused_tools(self):
        """Worker retains relevant tools throughout job, deposits only excess duplicates, and stows tools on job change."""
        # Create house & chest for fam_1
        chest, _ = self.furniture_manager.add_furniture("household_storage", 5, 5, self.permit_manager, self.villager_manager)
        chest.family_id = "fam_1"

        # Create villager with Sickle and 2 Hoes on Day 0 farm
        v = Villager("vil_1", "Arthur", "Ward", "Male", 25, 2, "Father", "fam_1", x=5.0 * TILE_SIZE, y=5.0 * TILE_SIZE)
        v.inventory["Sickle"] = 1
        v.inventory["Hoe"] = 2  # 1 excess hoe

        # Farm permit with unwatered & untilled tiles (no harvestable tiles)
        farm_p = self.permit_manager.add_permit("Farm", "farm", [(0, 0), (0, 1), (1, 0), (1, 1)])
        farm_p.set_crop("potato")
        farm_p.assigned_workers = ["vil_1"]

        # Check irrelevant tools: Sickle is RELEVANT to Farmer so it's NOT returned; only excess Hoe is returned!
        unused = v.get_irrelevant_tools()
        self.assertIn(("Hoe", 1), unused)
        self.assertNotIn(("Sickle", 1), [t for t, c in unused])

        # Run update: Arthur is next to chest, so he should deposit the 1 excess Hoe and KEEP Sickle & Hoe!
        all_ents = [v]
        v.update(0.1, self.permit_manager, self.building_manager, all_ents, player=None,
                 stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                 day_cycle=self.day_cycle)

        self.assertEqual(chest.inventory.get("Hoe", 0), 1)
        self.assertEqual(v.inventory.get("Hoe", 0), 1)     # 1 required Hoe remains in inventory
        self.assertEqual(v.inventory.get("Sickle", 0), 1)  # Required Sickle remains in inventory throughout job!

        # Now Arthur changes job to Builder: Farming tools become irrelevant and must be deposited!
        v.set_job("Builder")
        v.update(0.1, self.permit_manager, self.building_manager, all_ents, player=None,
                 stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                 day_cycle=self.day_cycle)

        self.assertEqual(v.inventory.get("Sickle", 0), 0)
        self.assertEqual(v.inventory.get("Hoe", 0), 0)
        self.assertEqual(chest.inventory.get("Sickle", 0), 1)
        self.assertEqual(chest.inventory.get("Hoe", 0), 2)

    def test_dispersed_farming_no_clumping(self):
        """Workers on the same farm lot should disperse across quadrants instead of clustering on adjacent tiles."""
        farm_tiles = [(gx, gy) for gx in range(6) for gy in range(8)]  # 48 tiles
        farm_p = self.permit_manager.add_permit("Farm 48", "farm", farm_tiles)
        farm_p.set_crop("potato")
        farm_p.assigned_workers = ["vil_1", "vil_2", "vil_3"]

        v1 = Villager("vil_1", "Arthur", "Ward", "Male", 30, 2, "Father", "fam_1", x=2.5 * TILE_SIZE, y=2.5 * TILE_SIZE)
        v2 = Villager("vil_2", "John", "Ward", "Male", 28, 2, "Brother", "fam_1", x=2.5 * TILE_SIZE, y=2.5 * TILE_SIZE)

        # Worker 1 reserves (2, 2)
        farm_p.reserve_tile(2, 2, "vil_1", "TILL")
        v1.current_work_tile = (2, 2)

        # Worker 2 selects a tile among untilled tiles
        avail = farm_p.get_available_untilled_tiles(worker_id="vil_2")
        self.assertNotIn((2, 2), avail)  # (2, 2) is strictly reserved

        # Worker 2 selects dispersed tile
        all_ents = [v1, v2]
        chosen = v2._select_dispersed_tile(avail, farm_p, all_entities=all_ents)
        self.assertIsNotNone(chosen)

        # Chosen tile should NOT be adjacent to (2, 2) (< 1.5 grid units: (1,2), (3,2), (2,1), (2,3), etc.)
        dist_to_v1 = ((chosen[0] - 2) ** 2 + (chosen[1] - 2) ** 2) ** 0.5
        self.assertGreaterEqual(dist_to_v1, 1.5, f"Worker 2 selected adjacent tile {chosen} too close to Worker 1 at (2, 2)")

    def test_gather_dropped_items_into_chest(self):
        """Family members gather dropped tools and items into household chest."""
        # 1. Place household chest at (10, 10)
        chest, _ = self.furniture_manager.add_furniture("household_storage", 10, 10, self.permit_manager, self.villager_manager)
        chest.family_id = "fam_1"

        # 2. Drop 6 sickles on the ground outside at (15, 15)
        self.stockpile_manager.drop_resource("Sickle", 6, 15, 15, owner_type="villager", owner_id="fam_1")
        self.assertEqual(len(self.stockpile_manager.stacks), 1)
        self.assertEqual(self.stockpile_manager.stacks[0].amount, 6)

        # 3. Create villager
        v = Villager("vil_1", "Arthur", "Ward", "Male", 25, 2, "Father", "fam_1", x=15.0 * TILE_SIZE, y=15.0 * TILE_SIZE)
        all_ents = [v]

        # 4. Villager spots dropped stack
        s = v._find_family_loose_stack_to_retrieve(self.stockpile_manager, self.furniture_manager, self.permit_manager, self.building_manager, all_ents)
        self.assertIsNotNone(s)
        self.assertEqual(s.resource_type, "Sickle")

        # 5. Villager picks up 5 (capacity limit) and hauls to chest
        # First tick transitions to FETCHING_POSSESSION
        v.update(0.1, self.permit_manager, self.building_manager, all_ents, player=None,
                 stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                 day_cycle=self.day_cycle)
        self.assertEqual(v.task, "FETCHING_POSSESSION")

        # Second tick picks up and transitions to HAULING_HOME
        v.update(0.1, self.permit_manager, self.building_manager, all_ents, player=None,
                 stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                 day_cycle=self.day_cycle)
        self.assertEqual(v.task, "HAULING_HOME")
        self.assertEqual(v.inventory.get("Sickle", 0), 5)

        # Teleport to chest and finish hauling
        v.x, v.y = chest.get_world_pos(TILE_SIZE)
        v.update(0.1, self.permit_manager, self.building_manager, all_ents, player=None,
                 stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                 day_cycle=self.day_cycle)

        # 5 sickles should now be in the chest, 1 remains on ground
        self.assertEqual(chest.inventory.get("Sickle", 0), 5)
        self.assertEqual(self.stockpile_manager.stacks[0].amount, 1)

    def test_farming_task_durations(self):
        """Verify watering takes 30m in-game labor and tilling takes 1h in-game labor."""
        self.assertEqual(WATERING_DURATION_INGAME_HOURS, 0.5)
        self.assertEqual(TILLING_DURATION_INGAME_HOURS, 1.0)

if __name__ == "__main__":
    unittest.main()
