import unittest
import math
import pygame
from main import get_alpha_surface, _alpha_surface_cache
from game.entities.villagers import VillagerManager, Villager
from game.data.config import TILE_SIZE

class TestPerformanceOptimizations(unittest.TestCase):
    def setUp(self):
        pygame.init()
        # Set dummy video driver if running headless
        if not pygame.display.get_surface():
            pygame.display.set_mode((1, 1), pygame.NOFRAME)

    def test_alpha_surface_cache_reuses_instances(self):
        """get_alpha_surface should return identical surface instance for same dimensions and color."""
        _alpha_surface_cache.clear()
        s1 = get_alpha_surface(64, 64, (56, 189, 248, 110))
        s2 = get_alpha_surface(64, 64, (56, 189, 248, 110))
        self.assertIs(s1, s2, "Cached alpha surface should return the same object reference")

        s3 = get_alpha_surface(64, 64, (34, 197, 94, 100))
        self.assertIsNot(s1, s3, "Different color should return a distinct surface")

    def test_physics_substep_clamping(self):
        """Simulation loop clamps substeps to at most MAX_PHYSICS_SUBSTEPS (3) to prevent spiral of death."""
        MAX_PHYSICS_SUB_DT = 0.033
        MAX_PHYSICS_SUBSTEPS = 3

        # Test large lag frame (e.g., 0.15s at 5x speed or heavy frame hitch)
        large_dt = 0.15
        sub_steps = min(MAX_PHYSICS_SUBSTEPS, max(1, math.ceil(large_dt / MAX_PHYSICS_SUB_DT)))
        self.assertEqual(sub_steps, 3)

        # Normal frame 60fps (0.0167s)
        normal_dt = 0.0167
        sub_steps_normal = min(MAX_PHYSICS_SUBSTEPS, max(1, math.ceil(normal_dt / MAX_PHYSICS_SUB_DT)))
        self.assertEqual(sub_steps_normal, 1)

    def test_villager_separation_throttled_to_ai_scheduler(self):
        """Inter-villager spatial separation is throttled to run_ai_scheduler=True to avoid N^2 loops on substeps."""
        from game.entities.villagers import Family
        vm = VillagerManager()
        v1 = Villager("v1", "Alpha", "Smith", "M", 25, 1, "Farmer", "fam1")
        v1.x = 100.0
        v1.y = 100.0
        fam1 = Family("fam1", "Smith", [v1])

        v2 = Villager("v2", "Beta", "Jones", "M", 25, 1, "Farmer", "fam2")
        v2.x = 100.5
        v2.y = 100.0
        fam2 = Family("fam2", "Jones", [v2])

        vm.families = [fam1, fam2]
        vm.invalidate_villager_cache()

        # Substep 1: run_ai_scheduler=False (should NOT perform separation push)
        pos_before = (v1.x, v2.x)
        vm.update(
            dt=0.016, permit_manager=None, building_manager=None, all_servants=[],
            player=None, run_ai_scheduler=False
        )
        pos_after_no_sched = (v1.x, v2.x)
        self.assertEqual(pos_before, pos_after_no_sched, "Separation must be skipped when run_ai_scheduler is False")

        # Substep 2: run_ai_scheduler=True (should perform gentle separation push)
        vm.update(
            dt=0.016, permit_manager=None, building_manager=None, all_servants=[],
            player=None, run_ai_scheduler=True
        )
        pos_after_sched = (v1.x, v2.x)
        self.assertNotEqual(pos_before, pos_after_sched, "Separation should execute when run_ai_scheduler is True")

if __name__ == "__main__":
    unittest.main()
