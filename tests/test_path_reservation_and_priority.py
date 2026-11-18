import unittest
import pygame
import math
import time

from game.data.config import TILE_SIZE, PATH_RESERVATION_CLEARANCE
from game.buildings.buildings import Building, BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.entities.villagers import Villager, VillagerManager
from game.entities.servants import Servant, ServantManager
from game.world.pathfinding import Pathfinder, GlobalPathRegistry


class TestPathReservationAndPriority(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.reg = GlobalPathRegistry.get_instance()
        self.reg.reset()

        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()

        # Build a 6x4 house: tiles from x=10..15, y=10..13 with door on TOP at (12, 10)
        house_tiles = {(x, y) for x in range(10, 16) for y in range(10, 14)}
        self.house = Building("wooden_structure", house_tiles, door_pos=(12, 10), door_side="top")
        self.bm.buildings.append(self.house)

        # Place a row of beds along the bottom wall inside the house: (10, 13) to (14, 13)
        for i in range(5):
            bx = 10 + i
            by = 13
            bed = Furniture(f"bed_{i+1}", "bed", bx, by, permit_id=1, family_id=1, assigned_villager_id=f"vil_{i+1}")
            self.fm.furniture.append(bed)

    def tearDown(self):
        self.reg.reset()

    def test_path_reservation_enforces_occupied_cells_and_segments(self):
        """Path reservation locks segments and navigation cells for the first AI"""
        path1 = [
            ((12 + 0.5) * TILE_SIZE, (9 + 0.5) * TILE_SIZE),
            ((12 + 0.5) * TILE_SIZE, (10 + 0.5) * TILE_SIZE),
            ((12 + 0.5) * TILE_SIZE, (11 + 0.5) * TILE_SIZE),
        ]
        success, res = self.reg.request_path_reservation("ai_1", path1, path1[0], (12, 11))
        self.assertTrue(success)
        self.assertIn("ai_1", self.reg.reservations)

        reserved_tiles = self.reg.get_all_reserved_tiles(exclude_entity="ai_2")
        self.assertIn((12, 10), reserved_tiles)
        self.assertIn((12, 11), reserved_tiles)

    def test_first_come_first_served_narrow_doorway_waiting(self):
        """When an AI reserves a doorway, a second AI attempting to use or cross that doorway must wait (FIFO)"""
        v1 = Villager("vil_1", "Alice", "Ward", "female", 24, 1, "Peasant Farmer", "fam1",
                      x=(12 + 0.5) * TILE_SIZE, y=(9 + 0.5) * TILE_SIZE)
        v2 = Villager("vil_2", "Bob", "Ward", "male", 26, 1, "Peasant Farmer", "fam1",
                      x=(12 + 0.5) * TILE_SIZE, y=(12 + 0.5) * TILE_SIZE)

        # v1 enters the house through door (12, 10) to bed (10, 13)
        v1_tgt_x = (10 + 0.5) * TILE_SIZE
        v1_tgt_y = (13 + 0.5) * TILE_SIZE
        v1._move_towards(v1_tgt_x, v1_tgt_y, dt=0.02, all_entities=[v1, v2],
                         building_manager=self.bm, furniture_manager=self.fm)

        self.assertTrue(len(v1.current_path) > 0)
        self.assertFalse(v1.is_waiting_for_path)

        # v2 is inside the house and attempts to exit through the SAME door to outside (12, 8)
        v2_tgt_x = (12 + 0.5) * TILE_SIZE
        v2_tgt_y = (8 + 0.5) * TILE_SIZE
        v2._move_towards(v2_tgt_x, v2_tgt_y, dt=0.02, all_entities=[v1, v2],
                         building_manager=self.bm, furniture_manager=self.fm)

        # In the abolished pathfinding system, AI entities pass freely through each other and doorways
        self.assertFalse(v2.is_waiting_for_path, "AI passes through without waiting at doorway")
        self.assertTrue(len(v2.current_path) > 0, "Second AI moves freely along its path")

    def test_clearing_doorway_releases_reservation_and_waiting_ai_proceeds(self):
        """AI entities pass through doorways simultaneously without waiting or blockage"""
        v1 = Villager("vil_1", "Alice", "Ward", "female", 24, 1, "Peasant Farmer", "fam1",
                      x=(12 + 0.5) * TILE_SIZE, y=(9 + 0.5) * TILE_SIZE)
        v2 = Villager("vil_2", "Bob", "Ward", "male", 26, 1, "Peasant Farmer", "fam1",
                      x=(12 + 0.5) * TILE_SIZE, y=(12 + 0.5) * TILE_SIZE)

        v1_tgt_x = (10 + 0.5) * TILE_SIZE
        v1_tgt_y = (13 + 0.5) * TILE_SIZE
        v1._move_towards(v1_tgt_x, v1_tgt_y, dt=0.02, all_entities=[v1, v2],
                         building_manager=self.bm, furniture_manager=self.fm)

        v2_tgt_x = (12 + 0.5) * TILE_SIZE
        v2_tgt_y = (8 + 0.5) * TILE_SIZE
        v2._move_towards(v2_tgt_x, v2_tgt_y, dt=0.02, all_entities=[v1, v2],
                         building_manager=self.bm, furniture_manager=self.fm)
        self.assertFalse(v2.is_waiting_for_path)
        self.assertTrue(len(v2.current_path) > 0)

        # v1 finishes its path or releases its reservation
        self.reg.release_reservation(v1.id)

        # v2 checks again
        v2.wait_timer = 0.0
        v2._move_towards(v2_tgt_x, v2_tgt_y, dt=0.02, all_entities=[v1, v2],
                         building_manager=self.bm, furniture_manager=self.fm)

        self.assertFalse(v2.is_waiting_for_path, "Waiting AI must acquire path once corridor is released")
        self.assertTrue(len(v2.current_path) > 0, "AI must now have an active path through the door")

    def test_pathfinding_to_bed_avoids_other_beds_and_sleeping_villagers(self):
        """Pathfinder routing to a target bed must navigate along the open floor and NEVER step across other beds"""
        pf = Pathfinder(self.bm)
        start_pos = ((10 + 0.5) * TILE_SIZE, (11 + 0.5) * TILE_SIZE)  # Floor inside house
        target_bed_pos = ((14 + 0.5) * TILE_SIZE, (13 + 0.5) * TILE_SIZE)  # Bed 5 at (14, 13)

        # Bed 1..(10..13, 13) are occupied by other sleeping family members
        occupied_beds = self.fm.get_occupied_tiles(exclude_tile=(14, 13))
        self.assertIn((10, 13), occupied_beds)
        self.assertIn((11, 13), occupied_beds)
        self.assertIn((12, 13), occupied_beds)
        self.assertIn((13, 13), occupied_beds)
        self.assertNotIn((14, 13), occupied_beds)

        path = pf.find_path(start_pos, target_bed_pos, self.bm, TILE_SIZE,
                            furniture_manager=self.fm, avoid_tiles=occupied_beds)
        self.assertTrue(len(path) > 0)

        # Check all waypoints along path: none should intersect other beds (10..13, 13)
        for wp in path:
            wgx = int(math.floor(wp[0] / TILE_SIZE))
            wgy = int(math.floor(wp[1] / TILE_SIZE))
            if (wgx, wgy) != (14, 13):
                self.assertNotIn((wgx, wgy), occupied_beds,
                                 f"Path waypoint ({wgx}, {wgy}) must not step onto another family member's bed")

    def test_anti_tunneling_oriented_walls_at_high_speed(self):
        """Inside entity moving into any exterior wall at high speed is clamped inside and never pops outside"""
        # Entity starts comfortably inside the house
        inside_x = (14 + 0.5) * TILE_SIZE
        inside_y = (12 + 0.5) * TILE_SIZE
        radius = 14.0

        # Attempt massive jump to the right (penetrating or jumping across right wall at x=16*64=1024)
        jump_x = inside_x + 120.0
        jump_y = inside_y

        res_x, res_y = self.bm.resolve_collision(jump_x, jump_y, radius, TILE_SIZE, old_x=inside_x, old_y=inside_y)

        # Right wall inner boundary is at 1024 - 10 = 1014. res_x must be <= 1014 - radius = 1000
        self.assertLessEqual(res_x, 1024.0 - 10.0 - radius + 0.01)
        self.assertTrue(self.house.occupies_tile(int(math.floor(res_x / TILE_SIZE)), int(math.floor(res_y / TILE_SIZE))),
                        "Entity must remain inside the house after colliding with right wall")


if __name__ == "__main__":
    unittest.main()
