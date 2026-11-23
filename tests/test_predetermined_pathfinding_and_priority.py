"""
Tests for Predetermined Pathfinding, Priority Claiming, and Path Visualizations
Rules applied: Modular, Zero Hardcode, Lean Code.
"""

import unittest
import pygame
from game.config import TILE_SIZE
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.servants import Servant, ServantManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.navigation.pathfinding import Pathfinder, GlobalPathRegistry
from game.world.camera import Camera
from game.ui.path_debug_overlay import PathDebugOverlay

class TestPredeterminedPathfindingAndPriority(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.servant_mgr = ServantManager()
        self.reg = GlobalPathRegistry.get_instance()
        self.reg.reset()

        # Build a 5x5 wooden house at (10, 10) with bottom door at (12, 14)
        tiles = set((x, y) for x in range(10, 15) for y in range(10, 15))
        self.house = Building("wooden_structure", tiles, door_pos=(12, 14), door_side="bottom")
        self.bm.buildings.append(self.house)

    def test_global_path_registry_priority_claim(self):
        """First AI claiming target tile must have priority; second claimant must not have priority"""
        target_tile = (20, 20)
        seq1 = self.reg.register_claim("agent_1", target_tile)
        seq2 = self.reg.register_claim("agent_2", target_tile)

        # agent_1 claimed first
        self.assertTrue(self.reg.has_priority("agent_1", target_tile, seq1))
        # agent_2 claimed second, must yield
        self.assertFalse(self.reg.has_priority("agent_2", target_tile, seq2))

        # Releasing agent_1's claim allows agent_2 to obtain priority upon re-claim
        self.reg.release_claim("agent_1", target_tile)
        seq2_new = self.reg.register_claim("agent_2", target_tile)
        self.assertTrue(self.reg.has_priority("agent_2", target_tile, seq2_new))

    def test_predetermined_path_generation_with_door_corridor(self):
        """Pathfinder generates valid waypoints through doorway without corner cutting"""
        start_world = (12.5 * TILE_SIZE, 17.0 * TILE_SIZE)  # Outside south of door
        target_world = (10.5 * TILE_SIZE, 11.5 * TILE_SIZE) # Inside house north-west

        path = self.bm.find_path(start_world, target_world, TILE_SIZE)
        self.assertGreater(len(path), 1)

        # Check that doorway threshold waypoint exists in the path
        d_thresh = self.house.get_door_world_threshold(TILE_SIZE)
        has_thresh = any(abs(wp[0] - d_thresh[0]) < 2.0 and abs(wp[1] - d_thresh[1]) < 2.0 for wp in path)
        self.assertTrue(has_thresh, "Doorway threshold waypoint must be preserved in predetermined path")

    def test_villagers_resolve_same_tile_conflict(self):
        """When two villagers target the same work tile, the later one detects lack of priority and yields"""
        v1 = Villager("v1", "Adam", "Smith", "male", 30, 1, "Peasant Farmer", "fam1", x=100.0, y=100.0)
        v2 = Villager("v2", "Bob", "Smith", "male", 25, 1, "Peasant Farmer", "fam1", x=120.0, y=100.0)
        fam = Family("fam1", "Smith", [v1, v2])
        self.vm.families.append(fam)

        target_tx = 250.0
        target_ty = 250.0

        # Step v1 first: registers first sequence
        v1._move_towards(target_tx, target_ty, dt=0.05, arrival_dist=12, all_entities=[v1, v2], building_manager=self.bm)
        # Step v2 second: registers second sequence
        v2._move_towards(target_tx, target_ty, dt=0.05, arrival_dist=12, all_entities=[v1, v2], building_manager=self.bm)

        self.assertLess(v1.path_seq, v2.path_seq)
        self.assertTrue(self.reg.has_priority(v1.id, v1.path_target_tile, v1.path_seq))
        self.assertFalse(self.reg.has_priority(v2.id, v2.path_target_tile, v2.path_seq))

    def test_draw_ai_paths_rendering_toggle(self):
        """draw_ai_paths should execute cleanly with show_lines=True and show_lines=False"""
        surface = pygame.Surface((800, 600))
        camera = Camera(800, 600)

        v = Villager("v_render", "Test", "Man", "male", 30, 1, "Peasant Farmer", "fam1", x=100.0, y=100.0)
        v.current_path = [(100.0, 100.0), (150.0, 100.0), (200.0, 150.0)]
        v.path_index = 0
        v.path_target = (200.0, 150.0)
        v.is_moving = True

        s = Servant("s_render", "Serv", 300.0, 300.0)
        s.current_path = [(300.0, 300.0), (350.0, 320.0)]
        s.path_index = 0
        s.path_target = (350.0, 320.0)
        s.is_moving = True

        # Test with visible lines
        PathDebugOverlay(enabled=True).draw_routes(surface, camera, [v, s])
        # Test with lines turned off
        PathDebugOverlay(enabled=False).draw_routes(surface, camera, [v, s])

if __name__ == "__main__":
    unittest.main()
