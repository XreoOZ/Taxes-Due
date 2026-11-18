"""
Unit tests for Agent 1: Collision Sliding, Pathfinding Improvements,
Waiting for Route Permanent Stuck Fix, and Route Lifecycle Recovery.
"""

import unittest
import math
import time
import pygame

from game.data.config import (
    TILE_SIZE,
    ROUTE_REQUEST_TIMEOUT,
    ROUTE_MAX_RETRIES,
    ROUTE_STATE_NONE,
    ROUTE_STATE_REQUESTED,
    ROUTE_STATE_PROCESSING,
    ROUTE_STATE_ASSIGNED,
    ROUTE_STATE_ACTIVE,
    ROUTE_STATE_COMPLETED,
    ROUTE_STATE_FAILED,
)
from game.entities.villagers import Villager, VillagerManager
from game.entities.servants import Servant, ServantManager
from game.entities.player import Player
from game.buildings.buildings import BuildingManager, Building
from game.buildings.furniture import FurnitureManager, Furniture
from game.world.pathfinding import GlobalPathRegistry, calculate_collision_slide
from game.world.permits import PermitManager
from game.world.stockpile import StockpileManager


class TestCollisionSlidingAndRouteRecovery(unittest.TestCase):
    def setUp(self):
        GlobalPathRegistry.get_instance().reset()
        self.building_manager = BuildingManager()
        self.furniture_manager = FurnitureManager()
        self.permit_manager = PermitManager()
        self.stockpile_manager = StockpileManager()

    def tearDown(self):
        GlobalPathRegistry.get_instance().reset()

    def test_01_two_ai_head_on_collision_sliding(self):
        """1. Two AI walking directly toward each other slide smoothly past each other without freezing."""
        # Villager 1 at (100, 200) moving right toward (300, 200)
        v1 = Villager("vil_1", "John", "Miller", "Male", 25, 2, "Father", "fam_1", 100.0, 200.0)
        # Villager 2 at (220, 200) moving left toward (50.0, 200.0)
        v2 = Villager("vil_2", "Arthur", "Smith", "Male", 26, 2, "Father", "fam_2", 220.0, 200.0)

        all_ents = [v1, v2]
        dt = 0.05

        # Step v1 towards (300, 200) and v2 towards (50, 200)
        for _ in range(30):
            v1._move_towards(300.0, 200.0, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)
            v2._move_towards(50.0, 200.0, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)

        # Neither AI should be permanently frozen or stopped
        self.assertTrue(v1.x > 100.0, f"v1 should have advanced rightward, current x: {v1.x}")
        self.assertTrue(v2.x < 220.0, f"v2 should have advanced leftward, current x: {v2.x}")
        self.assertFalse(v1.is_waiting_for_path, "v1 must not be waiting for route")
        self.assertFalse(v2.is_waiting_for_path, "v2 must not be waiting for route")

    def test_02_ai_crossing_at_angle_slides_smoothly(self):
        """2. AI crossing paths at an angle slide smoothly along tangent."""
        v1 = Villager("vil_cross1", "Emma", "Miller", "Female", 22, 2, "Mother", "fam_1", 200.0, 100.0)
        v2 = Villager("vil_cross2", "Walter", "Carter", "Male", 24, 2, "Father", "fam_2", 100.0, 200.0)
        all_ents = [v1, v2]

        dt = 0.05
        # v1 moving Down to (200, 300), v2 moving Right to (300, 200) - intersection near (200, 200)
        for _ in range(40):
            v1._move_towards(200.0, 300.0, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)
            v2._move_towards(300.0, 200.0, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)

        self.assertTrue(v1.y > 150.0, "v1 should have advanced downward")
        self.assertTrue(v2.x > 150.0, "v2 should have advanced rightward")

    def test_03_four_ai_in_narrow_aisle_anti_deadlock(self):
        """3. Four AI clustered in a narrow corridor (like the bedroom in screenshot) pass each other without deadlock."""
        # Setup bedroom layout: 8x4 tiles building with corridor in middle row (gy = 2, 3)
        # Beds at (1, 1), (3, 1) and (1, 4), (3, 4)
        bed1 = Furniture("b1", "bed", 1, 1)
        bed2 = Furniture("b2", "bed", 4, 1)
        bed3 = Furniture("b3", "bed", 1, 4)
        bed4 = Furniture("b4", "bed", 4, 4)
        self.furniture_manager.furnitures.extend([bed1, bed2, bed3, bed4])

        # 4 villagers in aisle between beds
        v1 = Villager("v1", "Cecily", "Brewer", "Female", 20, 2, "Mother", "fam_1", 1.5 * TILE_SIZE, 2.5 * TILE_SIZE)
        v2 = Villager("v2", "William", "Brewer", "Male", 22, 2, "Father", "fam_1", 1.5 * TILE_SIZE, 3.5 * TILE_SIZE)
        v3 = Villager("v3", "Alice", "Mason", "Female", 20, 2, "Mother", "fam_2", 3.5 * TILE_SIZE, 2.5 * TILE_SIZE)
        v4 = Villager("v4", "Thomas", "Mason", "Male", 22, 2, "Father", "fam_2", 3.5 * TILE_SIZE, 3.5 * TILE_SIZE)

        all_ents = [v1, v2, v3, v4]
        dt = 0.04

        # v1 and v2 want to walk right to (5.0 * TILE_SIZE, 3.0 * TILE_SIZE)
        # v3 and v4 want to walk left to (0.5 * TILE_SIZE, 3.0 * TILE_SIZE)
        target_right = (5.0 * TILE_SIZE, 3.0 * TILE_SIZE)
        target_left = (0.5 * TILE_SIZE, 3.0 * TILE_SIZE)

        for _ in range(60):
            v1._move_towards(target_right[0], target_right[1], dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager, furniture_manager=self.furniture_manager)
            v2._move_towards(target_right[0], target_right[1], dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager, furniture_manager=self.furniture_manager)
            v3._move_towards(target_left[0], target_left[1], dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager, furniture_manager=self.furniture_manager)
            v4._move_towards(target_left[0], target_left[1], dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager, furniture_manager=self.furniture_manager)

        # None of them should remain stuck in [WAITING ROUTE]
        for v in all_ents:
            self.assertFalse(v.is_waiting_for_path, f"{v.first_name} must not be permanently stuck waiting for route")

    def test_04_collision_sliding_never_clips_through_walls(self):
        """4. Collision resolution never allows an entity to clip through walls or inside solid buildings."""
        # Create solid building at (3, 3) to (4, 4)
        b_tiles = {(3, 3), (4, 3), (3, 4), (4, 4)}
        b = Building("well", b_tiles)
        self.building_manager.buildings.append(b)
        self.building_manager.rebuild_tile_cache()

        v1 = Villager("v_wall1", "Hugh", "Ward", "Male", 30, 2, "Father", "fam_1", 2.2 * TILE_SIZE, 3.5 * TILE_SIZE)
        v2 = Villager("v_wall2", "Geoffrey", "Ward", "Male", 32, 2, "Uncle", "fam_1", 2.6 * TILE_SIZE, 3.5 * TILE_SIZE)
        all_ents = [v1, v2]

        dt = 0.05
        # Move them towards each other, right against the solid wall
        for _ in range(20):
            v1._move_towards(3.0 * TILE_SIZE, 3.5 * TILE_SIZE, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)
            v2._move_towards(2.0 * TILE_SIZE, 3.5 * TILE_SIZE, dt, arrival_dist=10, all_entities=all_ents, building_manager=self.building_manager)

        # Confirm neither entity penetrated inside the solid building tiles
        for v in (v1, v2):
            vgx = int(math.floor(v.x / TILE_SIZE))
            vgy = int(math.floor(v.y / TILE_SIZE))
            self.assertNotIn((vgx, vgy), b_tiles, f"Entity {v.first_name} clipped inside solid building at ({vgx}, {vgy})")

    def test_05_route_lifecycle_transitions(self):
        """5. Route requests follow a well-defined lifecycle."""
        v = Villager("vil_life", "Eleanor", "Tanner", "Female", 21, 2, "Daughter", "fam_1", 50.0, 50.0)
        self.assertEqual(v.route_state, ROUTE_STATE_NONE)

        # Move to a reachable target
        v._move_towards(150.0, 50.0, 0.05, arrival_dist=10, building_manager=self.building_manager)
        self.assertIn(v.route_state, (ROUTE_STATE_ASSIGNED, ROUTE_STATE_ACTIVE))

        # Advance until arrival
        for _ in range(50):
            reached = v._move_towards(150.0, 50.0, 0.05, arrival_dist=10, building_manager=self.building_manager)
            if reached:
                break

        self.assertEqual(v.route_state, ROUTE_STATE_COMPLETED)
        self.assertFalse(v.is_waiting_for_path)

    def test_06_route_request_timeout_auto_recovery(self):
        """6. Route request automatically recovers when pending/waiting exceeds ROUTE_REQUEST_TIMEOUT."""
        s = Servant("serv_recover", "Servant Recover", 100.0, 100.0)
        s.is_waiting_for_path = True
        s.wait_timer = 1.0

        # Register waiting in GlobalPathRegistry
        reg = GlobalPathRegistry.get_instance()
        reg.register_waiting(s.id, (5, 5))

        # Simulate time passing exceeding ROUTE_REQUEST_TIMEOUT (2.0s)
        dt = 0.5
        for _ in range(int(ROUTE_REQUEST_TIMEOUT / dt) + 2):
            s._move_towards(200.0, 200.0, dt, arrival_dist=10, building_manager=self.building_manager)

        # After timeout window, automatic recovery must have cleared waiting state
        self.assertFalse(s.is_waiting_for_path, "Servant must not remain stuck in is_waiting_for_path after timeout recovery")
        self.assertEqual(len([w for w in reg.waiting_queue if w[0] == str(s.id)]), 0, "Waiting queue entry must be cleared")

    def test_07_stale_route_reservations_do_not_block_other_ai(self):
        """7. Stale reservations are automatically cleaned and do not block subsequent route requests."""
        reg = GlobalPathRegistry.get_instance()
        # Create a stale reservation from 20 seconds ago
        cand_path = [(100.0, 100.0), (200.0, 100.0)]
        success, res = reg.request_path_reservation("stale_ghost", cand_path, (100.0, 100.0), (3, 1), exclusive_target=True)
        self.assertTrue(success)

        # Force its last_update to be ancient
        res.last_update = time.time() - 30.0

        # Now entity 2 requests the same target tile
        v = Villager("active_v", "Matilda", "Miller", "Female", 28, 2, "Mother", "fam_1", 100.0, 100.0)
        cand_path2 = [(100.0, 100.0), (200.0, 100.0)]
        success2, res2 = reg.request_path_reservation(v.id, cand_path2, (100.0, 100.0), (3, 1), exclusive_target=True)

        self.assertTrue(success2, "New entity must successfully acquire reservation after stale reservation is pruned")
        self.assertNotIn("stale_ghost", reg.reservations)

    def test_08_fast_forward_simulation_speed_no_route_drop(self):
        """8. High simulation speeds (e.g., Fast 2x, Very Fast 4x dt steps) execute reliably without route drop."""
        vm = VillagerManager()
        sm = ServantManager()
        player = Player(100.0, 100.0)

        # Simulate 20 ticks with large dt (representing fast-forward simulation)
        dt_fast = 0.08  # ~4x normal physics step
        for _ in range(30):
            sm.update(dt_fast, self.building_manager, self.permit_manager, self.stockpile_manager, {"Wood": 100, "Food": 100, "Stone": 100, "Water": 100}, player)
            vm.update(dt_fast, self.permit_manager, self.building_manager, sm.servants, player, stockpile_manager=self.stockpile_manager)

        for s in sm.servants:
            self.assertFalse(s.is_waiting_for_path, f"{s.name} should not be locked in [WAITING ROUTE] at high speed")

    def test_09_state_preservation_during_route_recovery(self):
        """9. Recovering a blocked route preserves task, target, inventory, and health without corruption."""
        v = Villager("vil_preserve", "Robert", "Thatcher", "Male", 35, 2, "Father", "fam_thatcher", 64.0, 64.0)
        v.task = "SEEKING_FOOD"
        v.inventory = {"Potato": 2, "Hoe": 1}
        v.hunger = 42.0
        v.thirst = 58.0
        v.is_waiting_for_path = True
        v.wait_timer = 0.5

        # Trigger timeout recovery
        dt = 0.5
        for _ in range(int(ROUTE_REQUEST_TIMEOUT / dt) + 2):
            v._move_towards(300.0, 300.0, dt, arrival_dist=10, building_manager=self.building_manager)

        # State must be preserved!
        self.assertEqual(v.task, "SEEKING_FOOD")
        self.assertEqual(v.inventory.get("Potato"), 2)
        self.assertEqual(v.inventory.get("Hoe"), 1)
        self.assertEqual(v.hunger, 42.0)
        self.assertEqual(v.thirst, 58.0)
        self.assertFalse(v.is_waiting_for_path)

    def test_10_unreachable_destination_fallback(self):
        """10. Genuinely unreachable destination triggers graceful fallback and transitions out of waiting."""
        # Enclose target (10, 10) in a stone structure with door_pos set to None (completely sealed)
        solid_box = {(x, y) for x in range(8, 13) for y in range(8, 13)}
        b_enclosed = Building("stone_structure", solid_box)
        b_enclosed.door_pos = None
        b_enclosed.door_side = None
        self.building_manager.buildings.append(b_enclosed)
        self.building_manager.rebuild_tile_cache()

        v = Villager("vil_unreach", "Agnes", "Smith", "Female", 30, 2, "Mother", "fam_smith", 32.0, 32.0)
        target_x = 10.5 * TILE_SIZE
        target_y = 10.5 * TILE_SIZE

        # Step multiple times through retries exceeding ROUTE_MAX_RETRIES
        dt = 0.5
        for _ in range(30):
            v._move_towards(target_x, target_y, dt, arrival_dist=10, building_manager=self.building_manager, exclusive_target=True)

        # Entity must NOT be frozen in is_waiting_for_path
        self.assertFalse(v.is_waiting_for_path, "Entity must not be stuck in is_waiting_for_path for unreachable target")
        self.assertEqual(v.route_state, ROUTE_STATE_FAILED)


if __name__ == "__main__":
    unittest.main()
