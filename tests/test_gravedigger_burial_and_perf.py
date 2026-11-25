import os
import unittest
from types import SimpleNamespace
import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.data.config import PATH_FRAME_ASTAR_BUDGET
from game.entities.villagers import Family, Villager, VillagerManager
from game.permits import PermitManager
from game.systems.core.ai_simulation_scheduler import AISimulationScheduler
from game.systems.village_life.cemetery_system import CemeterySystem
from game.systems.work.commission_schedule import CommissionScheduleSystem
from game.systems.work.schedule import ScheduleManager
from game.world.camera import Camera
from game.world.navigation.pathfinding import Pathfinder
from game.world.stockpile import StockpileManager


class TestGravediggerBurialAndPerf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def setUp(self):
        inst = CemeterySystem.get_instance()
        inst.pending_commissions = []
        inst.overflow_corpses = []

        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = StockpileManager()
        self.sched = ScheduleManager()
        self.sched.job_schedules["Gravedigger"] = ["WORK"] * 24

    def test_gravedigger_buries_own_family_member_end_to_end(self):
        cem = self.pm.add_permit("Cemetery", "cemetery", {(5, 5), (5, 6)})
        CemeterySystem.ensure_cemetery_graves(cem)

        fam = Family("fam_gd", "Graves")
        gd = Villager("gd_1", "Cole", "Graves", "Male", 35, 2, "Father", family_id="fam_gd", x=160.0, y=160.0)
        gd.set_job("Gravedigger")
        gd.inventory = {"Hoe": 1}
        gd.hunger = gd.thirst = gd.need_toilet = gd.energy = 100.0

        spouse = Villager("sp_1", "Mara", "Graves", "Female", 32, 2, "Mother", family_id="fam_gd", x=165.0, y=160.0)
        spouse.is_alive = False
        spouse.task = "DECEASED"
        spouse.is_buried = False
        spouse.is_picked_up = False

        # Also add a child who should NEVER deadlock payment for the Gravedigger
        child = Villager("ch_1", "Tim", "Graves", "Male", 6, 1, "Son", family_id="fam_gd", x=160.0, y=165.0)
        fam.members = [gd, spouse, child]
        self.vm.families = [fam]
        self.vm.invalidate_villager_cache()

        chest = Furniture("chest_gd", "household_storage", 5, 5, permit_id="p_home", family_id="fam_gd")
        chest.inventory = {"Wood": 5, "Stone": 5, "Copper": 50}
        self.fm.furnitures.append(chest)

        day_cycle = SimpleNamespace(day_number=1, current_hour=10.0, day_length_seconds=24.0)

        for _ in range(100):
            self.vm.update(
                0.2, self.pm, self.bm, None, None,
                stockpile_manager=self.sm, furniture_manager=self.fm,
                day_cycle=day_cycle, schedule_manager=self.sched,
                ai_dt=0.2,
            )
            if spouse.is_buried:
                break

        self.assertTrue(spouse.is_buried, f"Own family corpse must be buried; gravedigger task={gd.task}")

    def test_commission_schedule_allows_gravedigger_landlord_fee_during_work(self):
        gd = Villager("gd_2", "Cole", "Graves", "Male", 35, 2, "Father", family_id="fam_gd")
        CommissionScheduleSystem.queue(
            gd, "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE",
            burial_payment_target_corpse_id="c99",
            burial_payment_gravedigger_id="gd_2",
        )
        activated = CommissionScheduleSystem.activate(gd, "WORK")
        self.assertTrue(activated)
        self.assertEqual(gd.task, "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE")

    def test_pathfinder_straight_line_fast_path_and_frame_budget(self):
        bm = BuildingManager()
        pf = Pathfinder(bm)
        pf.get_performance_stats(reset=True)
        # Open exterior tiles -> straight-line fast path uses 0 A* nodes
        route = pf.find_path((10 * 32 + 16, 10 * 32 + 16), (25 * 32 + 16, 20 * 32 + 16), bm, 32)
        self.assertEqual(len(route), 1)
        self.assertEqual(pf.get_performance_stats()["astar_nodes"], 0)

        # Obstructed route hits A*, capped by per-frame budget when begin_frame() is active
        wall = Building("wooden_structure", {(15, y) for y in range(8, 28)}, door_pos=(15, 8), door_side="top")
        bm.buildings.append(wall)
        pf.begin_frame()
        for i in range(PATH_FRAME_ASTAR_BUDGET + 2):
            pf.find_path((12 * 32 + 16, (9 + i) * 32 + 16), (18 * 32 + 16, (9 + i) * 32 + 16), bm, 32)
        blocked = pf.find_path((11 * 32 + 16, 12 * 32 + 16), (19 * 32 + 16, 12 * 32 + 16), bm, 32)
        self.assertEqual(blocked, [])

    def test_active_interval_scales_with_population_and_lod_draw_works(self):
        small_dt = AISimulationScheduler.active_interval_for_population(20)
        large_dt = AISimulationScheduler.active_interval_for_population(5000)
        self.assertLess(small_dt, large_dt)

        vm = VillagerManager()
        fam = Family("f_lod", "Crowd")
        v = Villager("v_lod", "Dot", "Crowd", "Male", 25, 2, "Son", "f_lod", x=200.0, y=200.0)
        fam.members = [v]
        vm.families = [fam]
        cam = Camera(1280, 720)
        cam.zoom = 0.35
        surf = pygame.Surface((1280, 720))
        vm.draw(surf, cam)


if __name__ == "__main__":
    unittest.main()
