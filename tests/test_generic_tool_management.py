"""
Automated Unit Tests: Generic Work Tool Management & Job Workflow System
Validates all requirements from user prompt:
1. Collect all tools relevant to the current job upfront in one visit.
2. Never return temporarily unused tools.
3. Retain tools throughout tasks, locations, and schedule activities.
4. Return tools only when they become irrelevant after a job change.
5. Generic system: Works data-driven for any job and tool configuration.
"""

import unittest
import pygame
from game.config import TILE_SIZE, DEDICATED_JOBS, TOOL_TYPES
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.entities.servants import Servant
from game.systems.day_cycle import DayCycleSystem
from game.systems.job_tool_system import (
    get_job_required_tools,
    get_missing_tools_for_worker,
    get_irrelevant_tools_in_inventory,
    collect_all_job_tools,
    deposit_irrelevant_tools
)

class TestGenericWorkToolManagement(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.vm = VillagerManager()
        self.day_cycle = DayCycleSystem()

        # Create home house with household storage chest for fam_ward
        tiles = set((x, y) for x in range(5, 9) for y in range(5, 9))
        self.house = Building("wooden_structure", tiles, door_pos=(6, 8), door_side="bottom")
        self.bm.buildings.append(self.house)

        self.chest, _ = self.fm.add_furniture("household_storage", 5, 5, self.pm, self.vm, building_manager=self.bm)
        self.chest.permit_id = "test_permit"
        self.chest.family_id = "fam_ward"
        self.chest.construction_order = {"status": "COMPLETE"}

        # Villager Arthur Ward
        self.worker = Villager("vil_arthur", "Arthur", "Ward", "male", 28, 2, "Father", "fam_ward",
                               x=5.5 * TILE_SIZE, y=5.5 * TILE_SIZE)
        self.family = Family("fam_ward", "Ward", [self.worker])
        self.vm.families.append(self.family)

    def test_1_collect_all_tools_for_job_upfront(self):
        """Worker must identify and collect ALL required tools for their job in one single visit."""
        # Stock chest with complete set of farming tools
        self.chest.inventory["Hoe"] = 2
        self.chest.inventory["Watering_Can"] = 2
        self.chest.inventory["Sickle"] = 2

        self.worker.job = "Farmer"
        self.assertEqual(self.worker.inventory, {})

        # Check missing tools
        missing = get_missing_tools_for_worker(self.worker)
        missing_names = [t for t, _ in missing]
        self.assertIn("Hoe", missing_names)
        self.assertIn("Watering_Can", missing_names)
        self.assertIn("Sickle", missing_names)

        # Worker next to chest collects all tools in one visit
        collected = self.worker.collect_all_job_tools(self.fm, self.sm)
        self.assertEqual(len(collected), 3)
        self.assertEqual(self.worker.inventory.get("Hoe"), 1)
        self.assertEqual(self.worker.inventory.get("Watering_Can"), 1)
        self.assertEqual(self.worker.inventory.get("Sickle"), 1)

        # Chest inventory decremented correctly
        self.assertEqual(self.chest.inventory.get("Hoe"), 1)
        self.assertEqual(self.chest.inventory.get("Watering_Can"), 1)
        self.assertEqual(self.chest.inventory.get("Sickle"), 1)

    def test_2_never_return_temporarily_unused_tools_during_job(self):
        """Tools must remain in worker inventory even when task does not require them."""
        # Equip Arthur with all 3 tools
        self.worker.job = "Farmer"
        self.worker.inventory = {"Hoe": 1, "Watering_Can": 1, "Sickle": 1}

        # Check irrelevant tools: None should be irrelevant!
        irrelevant = self.worker.get_irrelevant_tools()
        self.assertEqual(irrelevant, [], "Temporarily unused job tools must NEVER be marked irrelevant!")

        # Create farm plot where only tilling is needed (no ripe crops, dry soil)
        farm_p = self.pm.add_permit("Farm Plot", "farm", [(10, 10), (10, 11)])
        farm_p.set_crop("potato")
        farm_p.assigned_workers = [self.worker.id]

        # Simulate update tick
        self.worker.update(0.1, self.pm, self.bm, [self.worker], player=None,
                           stockpile_manager=self.sm, furniture_manager=self.fm,
                           day_cycle=self.day_cycle)

        # Both Sickle and Watering Can MUST still be in inventory!
        self.assertEqual(self.worker.inventory.get("Hoe"), 1)
        self.assertEqual(self.worker.inventory.get("Watering_Can"), 1)
        self.assertEqual(self.worker.inventory.get("Sickle"), 1)
        # Chest must NOT have received any returned tools
        self.assertEqual(self.chest.inventory.get("Sickle", 0), 0)
        self.assertEqual(self.chest.inventory.get("Watering_Can", 0), 0)

    def test_3_tools_retained_during_schedule_activities(self):
        """Tools remain in inventory during LEISURE or SLEEP activities."""
        self.worker.job = "Farmer"
        self.worker.inventory = {"Hoe": 1, "Watering_Can": 1, "Sickle": 1}

        # Set schedule activity to LEISURE
        unused_leisure = self.worker._get_unused_tools(assigned_farm=None, sched_activity="LEISURE")
        self.assertEqual(unused_leisure, [], "Tools must not be returned during leisure hours")

        # Set schedule activity to SLEEP
        unused_sleep = self.worker._get_unused_tools(assigned_farm=None, sched_activity="SLEEP")
        self.assertEqual(unused_sleep, [], "Tools must not be returned during sleep hours")

    def test_4_job_change_returns_irrelevant_and_equips_new_tools(self):
        """When changing job (Farmer -> Builder), farming tools are returned and builder tools equipped."""
        self.worker.job = "Farmer"
        self.worker.inventory = {"Hoe": 1, "Watering_Can": 1, "Sickle": 1}

        # Chest has a Hammer for builders
        self.chest.inventory["Hammer"] = 1

        # Reassign Arthur to Builder
        self.worker.set_job("Builder")
        self.assertEqual(self.worker.job, "Builder")

        # Check irrelevant tools: Hoe, Watering Can, Sickle are irrelevant to Builder
        irrelevant = self.worker.get_irrelevant_tools()
        irrel_names = [t for t, _ in irrelevant]
        self.assertIn("Hoe", irrel_names)
        self.assertIn("Watering_Can", irrel_names)
        self.assertIn("Sickle", irrel_names)

        # Run update: Arthur is near chest, so he deposits irrelevant tools and equips Hammer
        self.worker.update(0.1, self.pm, self.bm, [self.worker], player=None,
                           stockpile_manager=self.sm, furniture_manager=self.fm,
                           day_cycle=self.day_cycle)

        # Farming tools returned to chest
        self.assertEqual(self.chest.inventory.get("Hoe"), 1)
        self.assertEqual(self.chest.inventory.get("Watering_Can"), 1)
        self.assertEqual(self.chest.inventory.get("Sickle"), 1)

        # Worker inventory now has Hammer and NO farming tools!
        self.assertEqual(self.worker.inventory.get("Hoe", 0), 0)
        self.assertEqual(self.worker.inventory.get("Watering_Can", 0), 0)
        self.assertEqual(self.worker.inventory.get("Sickle", 0), 0)
        self.assertEqual(self.worker.inventory.get("Hammer"), 1)

    def test_5_shared_tools_retained_across_jobs(self):
        """If two jobs share a tool (e.g. Builder and Blacksmith both use Hammer), Hammer is retained without return."""
        self.worker.job = "Builder"
        self.worker.inventory = {"Hammer": 1}
        self.chest.inventory["Tongs"] = 1

        # Switch Builder -> Blacksmith (both require Hammer; Blacksmith also requires Tongs)
        self.worker.set_job("Blacksmith")

        # Hammer is NOT irrelevant because Blacksmith requires Hammer!
        irrelevant = self.worker.get_irrelevant_tools()
        self.assertEqual(irrelevant, [], "Shared tool Hammer must be retained!")

        # Missing tool is Tongs
        missing = get_missing_tools_for_worker(self.worker)
        self.assertEqual(missing, [("Tongs", 1)])

        # Run update: Arthur retains Hammer and collects Tongs
        self.worker.update(0.1, self.pm, self.bm, [self.worker], player=None,
                           stockpile_manager=self.sm, furniture_manager=self.fm,
                           day_cycle=self.day_cycle)

        self.assertEqual(self.worker.inventory.get("Hammer"), 1)
        self.assertEqual(self.worker.inventory.get("Tongs"), 1)

    def test_6_servant_implements_generic_tool_interface(self):
        """Servant entities implement the identical generic tool management methods."""
        servant = Servant("serv_1", "Alden", 100.0, 100.0)
        self.assertEqual(servant.job, "Builder")
        self.assertEqual(servant.get_job_required_tools(), {"Hammer": 1})
        self.assertEqual(servant.get_missing_job_tools(), [("Hammer", 1)])

        # Give hammer to servant
        servant.inventory["Hammer"] = 1
        self.assertEqual(servant.get_missing_job_tools(), [])
        self.assertEqual(servant.get_irrelevant_tools(), [])

        # Switch servant job to Farmer
        servant.set_job("Farmer")
        irrelevant = servant.get_irrelevant_tools()
        self.assertEqual(irrelevant, [("Hammer", 1)])

if __name__ == "__main__":
    unittest.main()
