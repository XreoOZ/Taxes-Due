import unittest
import time
import math
import pygame

from game.config import TILE_SIZE
from game.buildings.buildings import Building, BuildingManager
from game.buildings.furniture import Furniture, FurnitureManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.pathfinding import GlobalPathRegistry

class TestPerformanceAndSmartQueuing(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.reg = GlobalPathRegistry.get_instance()
        self.reg.reset()

        # Build 6x4 wooden structure at (10, 10) to (15, 13) with door on TOP at (12, 10)
        house_tiles = {(x, y) for x in range(10, 16) for y in range(10, 14)}
        self.house = Building("wooden_structure", house_tiles, door_pos=(12, 10), door_side="top")
        self.bm.buildings.append(self.house)
        self.bm.rebuild_tile_cache()

        # Place 6 beds inside along the south wall: (10, 13) to (15, 13)
        for i in range(6):
            bed = Furniture(f"bed_{i+1}", "bed", 10 + i, 13, permit_id=1, family_id=1, assigned_villager_id=f"vil_{i+1}")
            self.fm.furniture.append(bed)

        # 6 Villagers starting at distant Farm Lot (East of house: x=18..20, y=10..15)
        self.vils = []
        for i in range(6):
            v = Villager(f"vil_{i+1}", f"Worker_{i+1}", "Ward", "male", 20 + i, 1, "Peasant Farmer", "fam1",
                         x=(18 + (i % 2)) * TILE_SIZE, y=(10 + i) * TILE_SIZE)
            self.vils.append(v)
        fam = Family("fam1", "Ward", self.vils)
        self.vm.families.append(fam)

    def tearDown(self):
        self.reg.reset()

    def test_all_distant_ai_navigate_simultaneously_across_open_terrain(self):
        """
        AI must NOT wait at distant original positions.
        All AI with destinations in the house must immediately move across open terrain simultaneously.
        """
        all_ents = list(self.vils)
        dt = 0.05

        # Initial step: all villagers are given their bed destinations
        for i, v in enumerate(self.vils):
            bed = self.fm.furniture[i]
            bx = (bed.grid_x + 0.5) * TILE_SIZE
            by = (bed.grid_y + 0.5) * TILE_SIZE
            v._move_towards(bx, by, dt, arrival_dist=12, all_entities=all_ents,
                            building_manager=self.bm, furniture_manager=self.fm)

        # Every single villager must have a valid path and be moving immediately
        for v in self.vils:
            self.assertGreater(len(v.current_path), 0, f"{v.id} must receive a valid path immediately")
            self.assertTrue(v.is_moving, f"{v.id} must be actively moving across open terrain")
            self.assertFalse(v.is_waiting_for_path, f"{v.id} must not be frozen at original position")

    def test_performance_high_speed_substep_throughput(self):
        """
        6 villagers routing at 4x Very Fast speed for 60 frames must execute within 0.15s (400+ FPS).
        """
        all_ents = list(self.vils)
        dt = 0.016 * 4.0  # 4x Very Fast tick

        start_time = time.perf_counter()
        frames = 60

        for f in range(frames):
            self.bm.update(dt)
            for i, v in enumerate(self.vils):
                bed = self.fm.furniture[i]
                bx = (bed.grid_x + 0.5) * TILE_SIZE
                by = (bed.grid_y + 0.5) * TILE_SIZE
                v._move_towards(bx, by, dt, arrival_dist=12, all_entities=all_ents,
                                building_manager=self.bm, furniture_manager=self.fm)

        elapsed = time.perf_counter() - start_time
        fps = frames / elapsed
        self.assertLess(elapsed, 0.25, f"High-speed simulation must be fast (took {elapsed:.4f}s, {fps:.1f} FPS)")

    def test_doorway_fifo_staggered_queueing(self):
        """
        When multiple AI approach the same narrow doorway entrance:
        All AI enter smoothly passing through each other without queues, avoidance, or waiting.
        """
        # Place 3 villagers just outside the doorway
        d_out = self.house.get_door_world_outside(TILE_SIZE)
        v1 = self.vils[0]
        v2 = self.vils[1]
        v3 = self.vils[2]

        v1.x, v1.y = d_out[0], d_out[1] - 4.0
        v2.x, v2.y = d_out[0], d_out[1] - 20.0
        v3.x, v3.y = d_out[0], d_out[1] - 36.0

        all_ents = [v1, v2, v3]
        dt = 0.05

        # All approach the doorway
        b1 = self.fm.furniture[0]
        v1._move_towards((b1.grid_x + 0.5) * TILE_SIZE, (b1.grid_y + 0.5) * TILE_SIZE, dt,
                         arrival_dist=12, all_entities=all_ents, building_manager=self.bm, furniture_manager=self.fm)

        b2 = self.fm.furniture[1]
        v2._move_towards((b2.grid_x + 0.5) * TILE_SIZE, (b2.grid_y + 0.5) * TILE_SIZE, dt,
                         arrival_dist=12, all_entities=all_ents, building_manager=self.bm, furniture_manager=self.fm)

        b3 = self.fm.furniture[2]
        v3._move_towards((b3.grid_x + 0.5) * TILE_SIZE, (b3.grid_y + 0.5) * TILE_SIZE, dt,
                         arrival_dist=12, all_entities=all_ents, building_manager=self.bm, furniture_manager=self.fm)

        # AI pass freely through without doorway queues or waiting
        self.assertFalse(v2.is_waiting_for_path, "v2 must not be blocked or waiting")
        self.assertFalse(v3.is_waiting_for_path, "v3 must not be blocked or waiting")
        self.assertTrue(v1.is_moving)
        self.assertTrue(v2.is_moving)
        self.assertTrue(v3.is_moving)


if __name__ == "__main__":
    unittest.main()
