"""
Automated Unit Tests: Obstacle-Aware Pathfinding & Stuck Recovery System
Validates all requirements from user prompt:
1. Obstacle-aware pathfinding: account for actual walkability, never generate paths through blocked cells.
2. Calculate alternative routes around obstacles (buildings, walls, solid structures).
3. Validate every path segment against actual movement and collision rules (is_segment_clear).
4. Stuck detection: detect lack of progress, identify obstruction, invalidate path, and recalculate alternative route.
5. Prevent path oscillation with temporary avoidance cooldown.
6. Zero hardcoding: completely dynamic and data-driven.
"""

import unittest
import math
import pygame
from game.config import (
    TILE_SIZE,
    STUCK_THRESHOLD_SECONDS,
    STUCK_AVOIDANCE_DURATION,
    PATH_SEGMENT_COLLISION_RADIUS
)
from game.buildings.buildings import Building, BuildingManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.entities.servants import Servant
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager
from game.systems.day_cycle import DayCycleSystem
from game.world.pathfinding import Pathfinder

class TestObstacleAwarePathfinding(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.vm = VillagerManager()
        self.day_cycle = DayCycleSystem()

    def test_1_never_generate_path_through_solid_wall(self):
        """Pathfinder must NEVER generate a direct line cutting through a solid building wall."""
        # 4x4 wooden structure at x=4..7, y=2..5. Door at (4, 4) on west side.
        tiles = set((x, y) for x in range(4, 8) for y in range(2, 6))
        b = Building("wooden_structure", tiles, door_pos=(4, 4), door_side="left")
        self.bm.buildings.append(b)

        # Entity inside house near east wall at (7.5*64, 3.5*64)
        # Target outside to the east at (10.5*64, 3.5*64)
        start = (7.5 * TILE_SIZE, 3.5 * TILE_SIZE)
        target = (10.5 * TILE_SIZE, 3.5 * TILE_SIZE)

        path = self.bm.find_path(start, target)
        self.assertTrue(len(path) > 1, "Must generate a multi-waypoint path around the house!")

        # Verify EVERY segment is clear of wall collisions
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]
            clear = self.bm.pathfinder.is_segment_clear(p1, p2, self.bm)
            self.assertTrue(clear, f"Path segment {i}->{i+1} ({p1}->{p2}) must NOT intersect any solid wall!")

        # Verify path leaves through the west door (x <= 4.5*64) and around, not cutting through east wall
        min_x = min(p[0] for p in path)
        self.assertLessEqual(min_x, 4.5 * TILE_SIZE, "Path must traverse through the west doorway!")

    def test_2_route_around_solid_building_between_two_outside_points(self):
        """Entity outside must navigate completely around an intervening solid building."""
        # Solid structure (Well) at x=5..6, y=4..5 (2x2)
        well_tiles = {(5, 4), (6, 4), (5, 5), (6, 5)}
        well = Building("well", well_tiles)
        self.bm.buildings.append(well)

        start = (3.5 * TILE_SIZE, 4.5 * TILE_SIZE)  # West of well
        target = (8.5 * TILE_SIZE, 4.5 * TILE_SIZE) # East of well

        path = self.bm.find_path(start, target)
        self.assertTrue(len(path) >= 2)

        # Verify no segment cuts through the solid well
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i + 1]
            clear = self.bm.pathfinder.is_segment_clear(p1, p2, self.bm)
            self.assertTrue(clear, f"Segment {p1}->{p2} must not cut through solid well!")

    def test_3_unreachable_target_never_appends_path_through_obstacle(self):
        """If a target is completely enclosed by impassable walls with no door, return empty path."""
        # Fully enclosed room with no door (is_solid=True)
        tiles = set((x, y) for x in range(10, 14) for y in range(10, 14))
        vault = Building("wooden_structure", tiles)
        vault.is_solid = True
        vault.door_pos = None
        self.bm.buildings.append(vault)

        start = (5.5 * TILE_SIZE, 12.5 * TILE_SIZE)  # Outside
        target = (11.5 * TILE_SIZE, 12.5 * TILE_SIZE) # Inside enclosed room

        path = self.bm.find_path(start, target)
        # Must NOT generate a path through the wall!
        self.assertEqual(path, [], "Target inside impassable enclosed room must return empty path, never jump walls!")

    def test_4_stuck_detection_and_alternative_path_recovery(self):
        """Servant walking into an obstacle must detect stuck and recalculate an alternative route."""
        # Place a house blocking direct route
        tiles = set((x, y) for x in range(5, 8) for y in range(3, 7))
        house = Building("wooden_structure", tiles, door_pos=(5, 6), door_side="bottom")
        self.bm.buildings.append(house)

        servant = Servant("serv_1", "Jack", 4.5 * TILE_SIZE, 4.5 * TILE_SIZE)
        # Directly target a point to the east across the house
        target_x = 9.5 * TILE_SIZE
        target_y = 4.5 * TILE_SIZE

        # Force servant right against the west wall of the house (x=300 touches wall at x=320 with radius 20)
        servant.x = 300.0
        servant.y = 4.5 * TILE_SIZE
        servant.path_target = (target_x, target_y)
        servant.path_target_tile = (9, 4)
        servant.current_path = [(target_x, target_y)]  # Direct path into wall
        servant.path_index = 0

        # Simulate update ticks where servant tries to move east but is stopped by wall
        initial_stuck_timer = servant.stuck_timer
        self.assertEqual(initial_stuck_timer, 0.0)

        # Update for STUCK_THRESHOLD_SECONDS in small dt steps (15 steps = 0.75s, well exceeding 0.5s threshold)
        step_dt = 0.05
        steps = 15

        for _ in range(steps):
            servant._move_towards(target_x, target_y, step_dt, arrival_dist=12, building_manager=self.bm)

        # Stuck detection must have triggered: blocked node registered in avoidance set
        self.assertTrue(len(servant.stuck_blocked_tiles) > 0, "Blocked tile must be registered in stuck_blocked_tiles!")
        # Path must be recalculated and valid
        self.assertTrue(len(servant.current_path) > 0)
        # Verify new path segments are all clear
        for i in range(len(servant.current_path) - 1):
            p1 = servant.current_path[i]
            p2 = servant.current_path[i + 1]
            self.assertTrue(self.bm.pathfinder.is_segment_clear(p1, p2, self.bm))

    def test_5_avoid_oscillation_with_stuck_cooldown(self):
        """Stuck avoidance retains blocked node memory to prevent flipping back and forth."""
        servant = Servant("serv_2", "Robin", 5.0 * TILE_SIZE, 5.0 * TILE_SIZE)
        blocked_tile = (6, 5)
        servant.stuck_blocked_tiles[blocked_tile] = 9999999999.0  # Far future expiration

        # Request path towards east
        path = self.bm.find_path((servant.x, servant.y), (8.5 * TILE_SIZE, 5.5 * TILE_SIZE),
                                avoid_tiles=set(servant.stuck_blocked_tiles.keys()))
        # Verify tile (6, 5) is NOT in any waypoint of path
        for p in path:
            wp_gx = int(math.floor(p[0] / TILE_SIZE))
            wp_gy = int(math.floor(p[1] / TILE_SIZE))
            self.assertNotEqual((wp_gx, wp_gy), blocked_tile, "Path must actively avoid the blocked tile!")

    def test_villager_replans_around_stalled_waypoint(self):
        villager = Villager(
            villager_id="villager_stuck", first_name="A", last_name="B",
            gender="Male", age=30, generation=1, role="Father", family_id="fam_1",
        )
        villager.x, villager.y = 2.5 * TILE_SIZE, 2.5 * TILE_SIZE
        target = (8.5 * TILE_SIZE, 2.5 * TILE_SIZE)
        villager.path_target = target
        villager.current_path = [target]

        def slide_without_progress(px, py, radius, tile_size, old_x=None, old_y=None):
            return old_x, old_y + abs(px - old_x)

        self.bm.resolve_collision = slide_without_progress
        for _ in range(12):
            villager._move_towards(
                *target, dt=0.05, building_manager=self.bm,
                recover_blocked_routes=True,
            )

        self.assertTrue(villager.stuck_blocked_tiles)
        blocked_tile = next(iter(villager.stuck_blocked_tiles))

        self.bm.resolve_collision = BuildingManager.resolve_collision.__get__(self.bm)
        self.assertTrue(villager.current_path)
        self.assertNotIn(
            blocked_tile,
            {(int(x // TILE_SIZE), int(y // TILE_SIZE)) for x, y in villager.current_path},
        )

    def test_villager_keeps_route_stable_when_waiting_at_door(self):
        villager = Villager(
            villager_id="villager_door", first_name="A", last_name="B",
            gender="Male", age=30, generation=1, role="Father", family_id="fam_1",
        )
        door_house = Building(
            "wooden_structure", {(5, 5), (5, 6), (6, 5), (6, 6)},
            door_pos=(5, 5), door_side="top",
        )
        self.bm.buildings.append(door_house)
        self.bm.rebuild_tile_cache()
        outside = door_house.get_door_world_outside(TILE_SIZE)
        target = door_house.get_door_world_inside(TILE_SIZE)
        villager.x, villager.y = outside

        def block_door(px, py, radius, tile_size, old_x=None, old_y=None):
            return old_x, old_y

        self.bm.resolve_collision = block_door
        for _ in range(12):
            villager._move_towards(
                *target, dt=0.05, building_manager=self.bm,
                recover_blocked_routes=True,
            )

        self.assertTrue(villager.current_path)
        self.assertEqual(villager.path_target, target)
        self.assertFalse(villager.stuck_blocked_tiles)

if __name__ == "__main__":
    unittest.main()
