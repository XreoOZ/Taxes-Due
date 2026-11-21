"""
Unit tests for Tile Occupancy, Step Reservation, Narrow Doorway Management, and Route Recovery.
Agent 1 - Verification of Acceptance Criteria.
"""

import unittest
import math
import time
from game.config import (
    TILE_SIZE,
    ROUTE_STATE_NONE,
    ROUTE_STATE_REQUESTED,
    ROUTE_STATE_ASSIGNED,
    ROUTE_STATE_ACTIVE,
    ROUTE_STATE_COMPLETED,
    ROUTE_STATE_FAILED,
    DOORWAY_IDLE_MIN_DISTANCE,
    DOORWAY_QUEUE_LATERAL_OFFSET,
    TILE_OCCUPANCY_TIMEOUT,
    TILE_STEP_RESERVATION_TIMEOUT
)
from game.world.pathfinding import (
    GlobalPathRegistry,
    Pathfinder,
    is_narrow_passage_tile,
    calculate_collision_slide
)
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.villagers import Villager
from game.entities.servants import Servant
from game.entities.player import Player

class TestTileOccupancyDoorwaysAndRouteRecovery(unittest.TestCase):
    def setUp(self):
        self.reg = GlobalPathRegistry.get_instance()
        self.reg.clear()

        # Dummy Building Manager with a single-room building with a door at (5, 5)
        self.bm = BuildingManager()
        self.b = Building("wooden_structure", tiles={(5, 5), (5, 6), (6, 5), (6, 6)}, door_pos=(5, 5), door_side="top")
        self.bm.buildings = [self.b]
        self.bm.rebuild_tile_cache()

        # Dummy furniture manager
        self.fm = FurnitureManager()

        # Dummy player
        self.player = Player(100.0, 100.0)

    def tearDown(self):
        self.reg.clear()

    def test_01_tile_occupancy_exclusive_claim(self):
        """1. Multiple AI do not simultaneously claim the same exclusive tile."""
        tile = (10, 10)
        # Entity 1 claims tile
        success1 = self.reg.occupy_tile("vil_1", tile)
        self.assertTrue(success1)
        self.assertEqual(self.reg.get_tile_occupant(tile), "vil_1")

        # Entity 2 attempts to claim the same tile -> must fail
        success2 = self.reg.occupy_tile("vil_2", tile)
        self.assertFalse(success2)
        self.assertEqual(self.reg.get_tile_occupant(tile), "vil_1")

        # Entity 1 moves to (11, 10) -> old tile (10, 10) released
        self.reg.occupy_tile("vil_1", (11, 10))
        self.assertIsNone(self.reg.get_tile_occupant(tile))
        self.assertEqual(self.reg.get_tile_occupant((11, 10)), "vil_1")

        # Entity 2 can now claim (10, 10)
        success2_retry = self.reg.occupy_tile("vil_2", tile)
        self.assertTrue(success2_retry)

    def test_02_step_reservation_prevents_fight_over_tile(self):
        """2. Step reservation coordinates next tile movement so AI don't fight over the same space."""
        next_tile = (8, 8)
        # Entity 1 reserves step into (8, 8)
        res1 = self.reg.reserve_step_tile("vil_1", next_tile)
        self.assertTrue(res1)
        self.assertFalse(self.reg.is_tile_claimable("vil_2", next_tile))
        self.assertTrue(self.reg.is_tile_claimable("vil_1", next_tile))

        # Entity 2 attempts to reserve same step tile -> rejected
        res2 = self.reg.reserve_step_tile("vil_2", next_tile)
        self.assertFalse(res2)

        # Release step tile
        self.reg.release_step_tile("vil_1", next_tile)
        self.assertTrue(self.reg.is_tile_claimable("vil_2", next_tile))

    def test_03_narrow_passage_detection(self):
        """3. Narrow passages (doors, 1-tile hallways bounded by walls/furniture) are accurately identified."""
        # Door tile (5, 5) is registered on building
        self.assertEqual(self.b.door_pos, (5, 5))

        # Open grass tile at (20, 20) is NOT a narrow passage
        self.assertFalse(is_narrow_passage_tile((20, 20), building_manager=self.bm, furniture_manager=self.fm))

        # Simulate narrow 1-tile corridor between furniture:
        # Corridor at (15, 10), blocked north at (15, 9) and south at (15, 11)
        furn_n = Furniture("furn_1", "bed", 15, 9, permit_id="permit_1", family_id="fam_1")
        furn_s = Furniture("furn_2", "bed", 15, 11, permit_id="permit_1", family_id="fam_1")
        self.fm.furnitures = [furn_n, furn_s]
        self.fm.invalidate_cache()
        self.assertTrue(is_narrow_passage_tile((15, 10), building_manager=self.bm, furniture_manager=self.fm))

    def test_04_ai_never_idles_on_doorways(self):
        """4. AI must stay away from doorways when idling, and threshold positions are cleared."""
        v = Villager(villager_id="vil_1", first_name="John", last_name="Miller", gender="Male", age=35, generation=1, role="Father", family_id="fam_1")
        # Place directly on door threshold
        door_cx = (self.b.door_pos[0] + 0.5) * TILE_SIZE
        door_cy = (self.b.door_pos[1] + 0.5) * TILE_SIZE
        v.x, v.y = door_cx, door_cy
        v.idle_target = (door_cx, door_cy)

        # Execute idle behavior
        v._idle_behavior(dt=0.1, player=self.player, all_entities=[v], building_manager=self.bm)

        # Idle target must NOT be near the door
        self.assertFalse(self.bm.is_near_any_door(v.idle_target[0], v.idle_target[1], min_dist=DOORWAY_IDLE_MIN_DISTANCE))

        # And physically, the entity must be nudged outward away from the threshold center
        dist_from_threshold_center = math.hypot(v.x - door_cx, v.y - door_cy)
        self.assertGreater(dist_from_threshold_center, 0.5)

    def test_05_doorway_waiting_queue_has_lateral_offset(self):
        """5. Waiting positions for narrow doorways have lateral clearance away from the door transit corridor."""
        # Calculate queue position for outside waiting
        q_pos_0 = self.b.get_door_queue_pos(0, is_outside=True, tile_size=TILE_SIZE)
        q_pos_1 = self.b.get_door_queue_pos(1, is_outside=True, tile_size=TILE_SIZE)

        door_cx = (self.b.door_pos[0] + 0.5) * TILE_SIZE
        # Lateral distance (along X axis for top/bottom doors) must be at least DOORWAY_QUEUE_LATERAL_OFFSET
        lat_dist_0 = abs(q_pos_0[0] - door_cx)
        lat_dist_1 = abs(q_pos_1[0] - door_cx)

        self.assertGreaterEqual(lat_dist_0, DOORWAY_QUEUE_LATERAL_OFFSET - 1.0)
        self.assertGreaterEqual(lat_dist_1, DOORWAY_QUEUE_LATERAL_OFFSET - 1.0)

    def test_06_entity_in_doorway_threshold_does_not_freeze(self):
        """6. An entity currently in the doorway threshold finishes traversing without freezing."""
        v = Villager(villager_id="vil_1", first_name="John", last_name="Miller", gender="Male", age=35, generation=1, role="Father", family_id="fam_1")
        door_thresh = self.b.get_door_world_threshold(TILE_SIZE)
        v.x, v.y = door_thresh

        # Target is inside the building
        inside_target = self.b.get_door_world_inside(TILE_SIZE)
        v.current_path = [inside_target]
        v.path_index = 0
        v.path_target = inside_target

        # Step movement
        v._move_towards(inside_target[0], inside_target[1], dt=0.1, arrival_dist=10, all_entities=[v], building_manager=self.bm)

        # Entity must be active, not frozen in waiting
        self.assertTrue(v.is_moving)
        self.assertFalse(v.is_waiting_for_path)
        self.assertEqual(self.b.door_active_user, "vil_1")

    def test_07_opposing_ai_narrow_passage_conflict(self):
        """7. Opposing AI approaching narrow passages coordinate access without head-on deadlock."""
        # Villager 1 reserves path through door into building
        v1_path = [self.b.get_door_world_outside(TILE_SIZE), self.b.get_door_world_threshold(TILE_SIZE), self.b.get_door_world_inside(TILE_SIZE)]
        v1_start = (self.b.door_pos[0] * TILE_SIZE, (self.b.door_pos[1] - 2) * TILE_SIZE)
        ok1, res1 = self.reg.request_path_reservation("vil_1", v1_path, v1_start, self.b.door_pos, building_manager=self.bm)
        self.assertTrue(ok1)

        # Villager 2 approaches from inside moving outside
        v2_path = [self.b.get_door_world_threshold(TILE_SIZE), self.b.get_door_world_outside(TILE_SIZE)]
        v2_start = (self.b.door_pos[0] * TILE_SIZE, (self.b.door_pos[1] + 1) * TILE_SIZE)
        ok2, confs2 = self.reg.request_path_reservation("vil_2", v2_path, v2_start, (self.b.door_pos[0], self.b.door_pos[1] - 2), building_manager=self.bm)

        # AI pass freely through doorways in opposite directions without deadlock
        self.assertTrue(ok2)

    def test_08_cleanup_on_death_and_task_cancellation(self):
        """8. Tile occupancies and reservations are completely cleaned up on death or cancellation."""
        v = Villager(villager_id="vil_9", first_name="Beatrice", last_name="Mason", gender="Female", age=33, generation=1, role="Mother", family_id="fam_2")
        v.x, v.y = 200.0, 200.0
        cur_tile = (int(v.x // TILE_SIZE), int(v.y // TILE_SIZE))

        # Occupy tile and step tile
        self.reg.occupy_tile(v.id, cur_tile)
        self.reg.reserve_step_tile(v.id, (cur_tile[0] + 1, cur_tile[1]))

        self.assertEqual(self.reg.get_tile_occupant(cur_tile), "vil_9")
        self.assertFalse(self.reg.is_tile_claimable("vil_10", (cur_tile[0] + 1, cur_tile[1])))

        # Villager dies
        v.die(reason="Starvation", day=2)

        # All tile occupancies and reservations must be released
        self.assertIsNone(self.reg.get_tile_occupant(cur_tile))
        self.assertTrue(self.reg.is_tile_claimable("vil_10", (cur_tile[0] + 1, cur_tile[1])))

    def test_09_servant_waiting_for_route_recovery(self):
        """9. AI servants do not remain permanently stuck in Waiting for Route; auto-recovers."""
        # Create building manager with a completely enclosed solid fortress of walls (no entrance)
        solid_bm = BuildingManager()
        wall_tiles = {(x, y) for x in range(8, 13) for y in range(8, 13)}
        solid_wall = Building("wooden_structure", tiles=wall_tiles)
        solid_wall.is_solid = True
        solid_wall.door_pos = None
        solid_bm.buildings = [solid_wall]
        solid_bm.rebuild_tile_cache()

        s = Servant(servant_id="servant_1", name="Alden", x=150.0, y=150.0)
        s.route_state = ROUTE_STATE_REQUESTED
        s.is_waiting_for_path = True
        s.wait_timer = 0.5
        s.route_request_timer = 0.0

        # Attempt to move to the deep center of the solid wall fortress (completely unreachable)
        target_x = 10.5 * TILE_SIZE
        target_y = 10.5 * TILE_SIZE

        # Accumulate time beyond ROUTE_REQUEST_TIMEOUT (2.0s)
        s._move_towards(target_x, target_y, dt=2.5, arrival_dist=10, player=self.player, building_manager=solid_bm)

        # Automatic route recovery should have triggered retry count increment
        self.assertEqual(s.route_retry_count, 1)
        self.assertEqual(s.route_request_timer, 0.0)

    def test_10_very_fast_simulation_speed_movement(self):
        """10. Movement remains functional and coordinated at VERY FAST simulation speed (dt=0.33)."""
        v = Villager(villager_id="vil_3", first_name="Thomas", last_name="Fletcher", gender="Male", age=19, generation=1, role="Adult Son", family_id="fam_1")
        v.x, v.y = 100.0, 100.0
        dest = (250.0, 100.0)

        dt_fast = 0.333  # Represents 5x very fast speed frame
        for _ in range(5):
            v._move_towards(dest[0], dest[1], dt=dt_fast, arrival_dist=10, all_entities=[v], building_manager=self.bm)

        # Villager should have made significant progress toward dest without crashing or overflowing
        self.assertGreater(v.x, 150.0)
        self.assertIn(v.route_state, (ROUTE_STATE_ACTIVE, ROUTE_STATE_COMPLETED))

if __name__ == "__main__":
    unittest.main()
