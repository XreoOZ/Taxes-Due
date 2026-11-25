import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.data.config import TOOLMAKER_BAR_STOCK_TARGET, TOOLMAKER_SPARE_TOOLS_TARGET
from game.entities.villagers import Family, Villager, VillagerManager
from game.permits import PermitManager
from game.systems.economy.household_stall_system import HouseholdStallSystem
from game.systems.work.schedule import ScheduleManager
from game.systems.work.tool_condition import ToolConditionSystem
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.world.stockpile import StockpileManager


class TestToolmakerSelfAndSpareTools(unittest.TestCase):
    def setUp(self):
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = StockpileManager()
        self.sched = ScheduleManager()
        self.sched.job_schedules["Toolmaker"] = ["WORK"] * 24

        self.fam = Family("fam_tm", "Smith")
        self.tm = Villager(
            "tm_1", "Garrick", "Smith", "Male", 32, 2, "Father",
            family_id="fam_tm", x=100.0, y=100.0,
        )
        self.tm.set_job("Toolmaker")
        self.tm.hunger = 100.0
        self.tm.thirst = 100.0
        self.tm.need_toilet = 100.0
        self.tm.energy = 100.0
        self.fam.members = [self.tm]
        self.vm.families = [self.fam]

        self.chest = Furniture("chest_tm", "household_storage", 3, 3, permit_id="p_home", family_id="fam_tm")
        self.fm.furnitures.append(self.chest)

        self.bench = Furniture("wb_tm", "toolmaker_workbench", 3, 3, permit_id="p_home", family_id="fam_tm")
        self.fm.furnitures.append(self.bench)

    def test_broken_tools_self_forged_without_deadlock_or_coins(self):
        # Toolmaker has 0 coins and NO Hammer/Tongs in pocket or chest
        self.tm.inventory = {}
        self.chest.inventory = {"Wood": 10, "Iron Bar": 10}
        day_cycle = SimpleNamespace(day_number=1, current_hour=10.0, day_length_seconds=60.0)

        for _ in range(15):
            self.tm.update(
                2.0, self.pm, self.bm, [self.tm], None,
                stockpile_manager=self.sm, furniture_manager=self.fm,
                day_cycle=day_cycle, schedule_manager=self.sched,
                villager_manager=self.vm,
            )
            self.assertNotEqual(self.tm.task, "MISSING_TOOL", "Toolmaker must never deadlock waiting at home")
            if self.tm.inventory.get("Hammer", 0) >= 1 and self.tm.inventory.get("Tongs", 0) >= 1:
                break

        self.assertGreaterEqual(self.tm.inventory.get("Hammer", 0), 1)
        self.assertGreaterEqual(self.tm.inventory.get("Tongs", 0), 1)
        self.assertEqual(len(ToolmakerSystem._tool_order_subjects(self.fm)), 0)
        self.assertEqual(ToolConditionSystem.conditions_for(self.tm, "Hammer"), ["PRISTINE"])

    def test_idle_toolmaker_crafts_one_spare_set_into_chest(self):
        self.tm.inventory = {"Hammer": 1, "Tongs": 1}
        ToolConditionSystem.register_new_units(self.tm, "Hammer", 1)
        ToolConditionSystem.register_new_units(self.tm, "Tongs", 1)
        # Keep bars at target so Toolmaker immediately focuses on spare tool buffer
        self.chest.inventory = {"Wood": 10, "Iron Bar": TOOLMAKER_BAR_STOCK_TARGET}
        day_cycle = SimpleNamespace(day_number=1, current_hour=10.0, day_length_seconds=60.0)

        for _ in range(30):
            self.tm.update(
                2.0, self.pm, self.bm, [self.tm], None,
                stockpile_manager=self.sm, furniture_manager=self.fm,
                day_cycle=day_cycle, schedule_manager=self.sched,
                villager_manager=self.vm,
            )
            if (self.chest.inventory.get("Hammer", 0) >= TOOLMAKER_SPARE_TOOLS_TARGET
                    and self.chest.inventory.get("Tongs", 0) >= TOOLMAKER_SPARE_TOOLS_TARGET):
                break

        self.assertEqual(self.chest.inventory.get("Hammer", 0), TOOLMAKER_SPARE_TOOLS_TARGET)
        self.assertEqual(self.chest.inventory.get("Tongs", 0), TOOLMAKER_SPARE_TOOLS_TARGET)

        # Extra idle updates must NOT keep forging beyond the 1 spare set
        for _ in range(5):
            self.tm.update(
                2.0, self.pm, self.bm, [self.tm], None,
                stockpile_manager=self.sm, furniture_manager=self.fm,
                day_cycle=day_cycle, schedule_manager=self.sched,
                villager_manager=self.vm,
            )
        self.assertEqual(self.chest.inventory.get("Hammer", 0), TOOLMAKER_SPARE_TOOLS_TARGET)
        self.assertEqual(self.chest.inventory.get("Tongs", 0), TOOLMAKER_SPARE_TOOLS_TARGET)

    def test_household_stall_protects_toolmaker_spare_set(self):
        self.tm.inventory = {"Hammer": 1, "Tongs": 1}
        market = Building("market", {(10, 10), (10, 11)})
        HouseholdStallSystem.assign_stall(market, "fam_tm")
        HouseholdStallSystem.set_item_allocation(market, "Hammer", 100)
        HouseholdStallSystem.set_item_allocation(market, "Tongs", 100)

        # Only 1 spare in chest -> 0 allocatable for sale
        self.chest.inventory = {"Hammer": 1, "Tongs": 1}
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                market, "fam_tm", "Hammer", self.fm, villager_manager=self.vm
            ),
            0,
        )
        # 2 in chest -> 1 spare kept, 1 surplus sellable
        self.chest.inventory = {"Hammer": 2, "Tongs": 1}
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                market, "fam_tm", "Hammer", self.fm, villager_manager=self.vm
            ),
            1,
        )

    def test_toolmaker_forging_duration_is_20_ingame_minutes(self):
        from types import SimpleNamespace
        from game.systems.work.toolmaker_system import ToolmakerSystem
        day_cycle = SimpleNamespace(day_length_seconds=1200.0)
        self.assertAlmostEqual(ToolmakerSystem._unit_seconds(day_cycle), 50.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
