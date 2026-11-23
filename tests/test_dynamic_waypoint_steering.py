"""
Unit Tests: Dynamic Waypoint Steering
Validates that actors cut corners / skip stale waypoints using line-of-sight
steering instead of rigidly following the A* polyline order.
"""

import unittest
import pygame
from game.config import TILE_SIZE, PATH_STEER_LOOKAHEAD
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.world.navigation import steer_towards_visible_waypoint, resolve_steer_index


class _DummyEntity:
    pass


class TestDynamicWaypointSteering(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()

    def test_open_field_skips_to_furthest_visible_waypoint(self):
        """With no obstacles, steering should jump ahead up to the lookahead bound."""
        ts = TILE_SIZE
        pos = (0.0, 0.0)
        path = [(i * ts, 0.0) for i in range(8)]
        idx = steer_towards_visible_waypoint(pos, path, 0, self.bm)
        expected = min(PATH_STEER_LOOKAHEAD - 1, len(path) - 1)
        self.assertEqual(idx, expected)
        # Never beyond the lookahead window
        self.assertLessEqual(idx, PATH_STEER_LOOKAHEAD - 1)

    def test_wall_blocks_steering_past_building(self):
        """A waypoint behind a solid wall must never be steered to directly."""
        ts = TILE_SIZE
        tiles = set((x, y) for x in range(4, 8) for y in range(2, 6))
        self.bm.buildings.append(
            Building("wooden_structure", tiles, door_pos=(4, 4), door_side="left")
        )

        pos = (3.0 * ts, 3.5 * ts)  # west of the building, off the door lane
        path = [
            pos,
            (3.5 * ts, 3.5 * ts),   # still west of the wall
            (5.5 * ts, 5.5 * ts),   # inside/behind the building
            (10.5 * ts, 3.5 * ts),  # far east — straight line crosses the wall
        ]
        idx = steer_towards_visible_waypoint(pos, path, 0, self.bm)
        self.assertGreaterEqual(idx, 0)
        # The far east waypoint is unreachable by a straight segment
        self.assertFalse(
            self.bm.pathfinder.is_segment_clear(pos, path[3], self.bm),
            "sanity: direct line to far waypoint must cross the wall",
        )
        chosen = path[idx]
        self.assertTrue(
            self.bm.pathfinder.is_segment_clear(pos, chosen, self.bm),
            "steered waypoint must be line-of-sight clear",
        )

    def test_resolve_steer_index_is_throttled_and_path_aware(self):
        """Cached steer index is reused within the rescan interval and reset on new path."""
        ts = TILE_SIZE
        pos = (0.0, 0.0)
        path_a = [(i * ts, 0.0) for i in range(8)]
        path_b = [(i * ts, 5.0 * ts) for i in range(8)]
        ent = _DummyEntity()

        i1 = resolve_steer_index(ent, pos, path_a, 0, 0.016, self.bm)
        i2 = resolve_steer_index(ent, pos, path_a, 0, 0.016, self.bm)
        self.assertEqual(i1, i2, "within rescan interval the cached index must be reused")

        i3 = resolve_steer_index(ent, pos, path_b, 0, 1.0, self.bm)
        self.assertGreaterEqual(i3, 0)

        # path_index advanced past cached index -> clamps forward, never backwards
        i4 = resolve_steer_index(ent, pos, path_a, 5, 1.0, self.bm)
        self.assertGreaterEqual(i4, 5)
        self.assertLessEqual(i4, len(path_a) - 1)

    def test_steer_never_returns_index_before_path_index(self):
        ts = TILE_SIZE
        pos = (0.0, 0.0)
        path = [(i * ts, 0.0) for i in range(8)]
        idx = steer_towards_visible_waypoint(pos, path, 4, self.bm)
        self.assertGreaterEqual(idx, 4)
        self.assertLessEqual(idx, len(path) - 1)


if __name__ == "__main__":
    unittest.main()
