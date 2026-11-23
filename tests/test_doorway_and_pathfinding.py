import unittest
import math
import pygame
from game.config import TILE_SIZE, MIN_ENTITY_SEPARATION, SERVANT_RADIUS, VILLAGER_RADIUS
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.servants import Servant, ServantManager
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager
from game.world.navigation.pathfinding import GlobalPathRegistry

class TestDoorwayAndPathfinding(unittest.TestCase):
    def setUp(self):
        pygame.init()
        GlobalPathRegistry.get_instance().reset()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = PermitManager()
        self.sm = StockpileManager()
        self.vm = VillagerManager()
        self.servant_mgr = ServantManager()

        # Build a 6x3 wooden house at grid (5, 5) with top door at (7, 5)
        # Tiles: x in [5..10], y in [5..7]
        house_tiles = set((x, y) for x in range(5, 11) for y in range(5, 8))
        self.house = Building("wooden_structure", house_tiles, door_pos=(7, 5), door_side="top")
        self.bm.buildings.append(self.house)

        # Place a chest at bottom-left corner of the house: grid (5, 7)
        self.chest = Furniture("chest_1", "household_storage", 5, 7, permit_id="permit_1", family_id="Carter")
        self.fm.furnitures.append(self.chest)

    def test_door_waypoints_generation(self):
        """Test that get_door_waypoints accurately produces corridor waypoints for entering and exiting"""
        # Outside at (7.5 * 64, 3.0 * 64) -> Target inside chest at (5.5 * 64, 7.5 * 64)
        outside_x, outside_y = (7.5 * TILE_SIZE, 3.0 * TILE_SIZE)
        chest_x, chest_y = self.chest.get_world_pos(TILE_SIZE)

        wps = self.bm.get_door_waypoints(outside_x, outside_y, chest_x, chest_y, TILE_SIZE)
        self.assertEqual(len(wps), 2)
        d_out = self.house.get_door_world_outside(TILE_SIZE)
        d_in = self.house.get_door_world_inside(TILE_SIZE)
        self.assertAlmostEqual(wps[0][0], d_out[0], delta=1.0)
        self.assertAlmostEqual(wps[0][1], d_out[1], delta=1.0)
        self.assertAlmostEqual(wps[1][0], d_in[0], delta=1.0)
        self.assertAlmostEqual(wps[1][1], d_in[1], delta=1.0)

    def test_servant_navigates_through_door_to_chest(self):
        """Simulate servant pathfinding from outside into the house to deliver an item to the corner chest"""
        servant = Servant("servant_test", "Alden", 7.5 * TILE_SIZE, 3.0 * TILE_SIZE)
        servant.state = "GRANT_DELIVER"
        servant.carried_res = "Hoe"
        servant.carried_amount = 1
        servant.target_grant_fam_id = "Carter"
        chest_x, chest_y = self.chest.get_world_pos(TILE_SIZE)
        servant.target_grant_dest = (chest_x, chest_y)

        order = {
            "family_id": "Carter",
            "item_type": "Hoe",
            "amount": 1,
            "in_transit": 1,
            "delivered": 0
        }
        servant.target_grant_order = order
        self.servant_mgr.grant_orders.append(order)

        # Run simulation loop (dt = 0.05s)
        dt = 0.05
        max_steps = 400
        delivered = False

        for step in range(max_steps):
            servant.update(dt, self.bm, self.pm, self.sm, {}, None,
                           all_servants=[servant], furniture_manager=self.fm,
                           villager_manager=self.vm, servant_manager=self.servant_mgr)
            if self.chest.inventory.get("Hoe", 0) == 1:
                delivered = True
                break

        self.assertTrue(delivered, f"Servant failed to deliver to chest! State: {servant.state}, Pos: ({servant.x}, {servant.y}), Chest: ({chest_x}, {chest_y})")
        self.assertEqual(self.chest.inventory["Hoe"], 1)
        self.assertEqual(order["delivered"], 1)
        self.assertEqual(servant.state, "IDLE")

    def test_door_yielding_prevents_clumping(self):
        """Test that trailing entity yields when another entity is crossing the doorway"""
        door_cx, door_cy = (7.5 * TILE_SIZE, 5.5 * TILE_SIZE)

        # Entity A is right in the doorway
        s1 = Servant("s1", "A", door_cx, door_cy)

        # Entity B is approaching doorway from outside
        d_out = self.house.get_door_world_outside(TILE_SIZE)
        s2 = Servant("s2", "B", d_out[0], d_out[1] - 10.0)
        s2.nav_target = self.chest.get_world_pos(TILE_SIZE)
        s2.door_waypoints = [d_out, self.house.get_door_world_inside(TILE_SIZE)]

        # Run 1 step of move_towards for s2 with s1 present
        arrived = s2._move_towards(s2.nav_target[0], s2.nav_target[1], dt=0.05, arrival_dist=20,
                                   all_servants=[s1, s2], player=None, building_manager=self.bm)

        # s2 should yield and not move into s1
        self.assertFalse(arrived)
        self.assertFalse(s2.is_moving)

    def test_personal_space_separation_no_clumping(self):
        """Verify that AI entities pass freely through each other without collision blocking or separation push"""
        v1 = Villager("v1", "John", "Carter", "male", 30, 1, "Peasant Farmer", "Carter", x=200.0, y=200.0)
        v2 = Villager("v2", "Mary", "Carter", "female", 28, 1, "Peasant Farmer", "Carter", x=202.0, y=200.0)
        fam = Family("Carter", "Carter", [v1, v2])
        self.vm.families.append(fam)

        # Update
        dt = 0.05
        self.vm.update(dt, self.pm, self.bm, [], None)

        # AI do not bounce off or push each other
        self.assertFalse(v1.is_waiting_for_path)
        self.assertFalse(v2.is_waiting_for_path)

    def test_construction_site_work_pos_separation(self):
        """Verify that workers get distinct work positions around site perimeters"""
        s1 = Servant("s1", "Alden", 0, 0)
        s2 = Servant("s2", "Barnaby", 0, 0)
        servants = [s1, s2]

        pos1 = s1._get_site_work_pos(self.house, all_servants=servants)
        pos2 = s2._get_site_work_pos(self.house, all_servants=servants)

        dist_between_workers = math.hypot(pos1[0] - pos2[0], pos1[1] - pos2[1])
        self.assertGreater(dist_between_workers, 64.0, f"Workers at same site are too close: {dist_between_workers}")

    def test_villager_exits_building_through_door(self):
        """Verify that an entity inside a house smoothly exits through the door without getting stuck on walls"""
        chest_x, chest_y = self.chest.get_world_pos(TILE_SIZE)
        v = Villager("v_exit", "Tom", "Carter", "male", 25, 2, "Peasant Farmer", "Carter", x=chest_x, y=chest_y)

        outside_target = (7.5 * TILE_SIZE, 2.0 * TILE_SIZE)
        dt = 0.05
        max_steps = 300
        arrived = False

        for step in range(max_steps):
            reached = v._move_towards(outside_target[0], outside_target[1], dt, arrival_dist=16,
                                      all_entities=[v], player=None, building_manager=self.bm)
            if reached:
                arrived = True
                break

        self.assertTrue(arrived, f"Villager failed to exit building! Pos: ({v.x}, {v.y}), Target: {outside_target}")
        self.assertAlmostEqual(v.x, outside_target[0], delta=20.0)
        self.assertAlmostEqual(v.y, outside_target[1], delta=20.0)

    def test_anti_tunneling_high_speed_player(self):
        """Verify Player running into a solid wall at Very Fast dt never tunnels through"""
        from game.entities.player import Player
        player = Player(500.0, 560.0)  # Below bottom wall of house (bottom wall is at y=512)

        # Mock keys pressing UP (W key)
        keys = {pygame.K_w: True, pygame.K_UP: False, pygame.K_s: False, pygame.K_DOWN: False,
                pygame.K_a: False, pygame.K_LEFT: False, pygame.K_d: False, pygame.K_RIGHT: False}

        # Simulate 20 frames with huge dt=0.15s (equivalent to Very Fast 4x + 25 FPS)
        for _ in range(20):
            player.handle_input(keys, dt=0.15, building_manager=self.bm, tile_size=TILE_SIZE)

        # Player must remain outside the house (y >= 512 + player.radius - 2)
        bottom_wall_y = 8 * TILE_SIZE
        self.assertGreaterEqual(player.y, bottom_wall_y + player.radius - 2.0,
                               f"Player tunneled through solid wall! y={player.y}, wall_y={bottom_wall_y}")

    def test_anti_tunneling_high_speed_servant(self):
        """Verify Servant cannot tunnel through a solid wall even with massive dt"""
        # Servant placed below bottom wall (y=560), trying to move up towards y=450 inside
        s = Servant("s_test", "Alden", 500.0, 560.0)
        bottom_wall_y = 8 * TILE_SIZE

        # Moving straight up towards a point inside the building through solid wall (no door on bottom)
        for _ in range(20):
            s._move_towards(500.0, 450.0, dt=0.15, arrival_dist=10, all_servants=[s], building_manager=self.bm)

        # The servant must not penetrate the bottom wall
        self.assertFalse(self.house.occupies_tile(int(s.x // TILE_SIZE), int(s.y // TILE_SIZE)),
                        f"Servant tunneled through solid wall into house! ({s.x}, {s.y})")

    def test_villager_navigates_around_exterior_wall_to_reach_bed(self):
        """Verify villager on East farm lot routes around house to North door and reaches bed inside"""
        # Villager at East farm lot (x=736, y=416)
        v = Villager("vil_east", "Test", "East", "Male", 25, 2, "Father", "Carter", 11.5 * TILE_SIZE, 6.5 * TILE_SIZE)
        bed_x = 6.5 * TILE_SIZE
        bed_y = 7.5 * TILE_SIZE

        arrived = False
        # Give enough frames to navigate the path (~150 frames at 0.05s)
        for _ in range(250):
            reached = v._move_towards(bed_x, bed_y, dt=0.05, arrival_dist=16.0,
                                     all_entities=[v], building_manager=self.bm)
            # Ensure villager NEVER penetrates a solid wall rect
            for wrect in self.house.get_wall_rects(TILE_SIZE):
                self.assertFalse(wrect.collidepoint(v.x, v.y),
                                f"Villager collided/penetrated solid wall at ({v.x}, {v.y})")
            if reached:
                arrived = True
                break

        self.assertTrue(arrived, f"Villager failed to navigate around wall to bed! Ended at ({v.x}, {v.y})")
        self.assertAlmostEqual(v.x, bed_x, delta=20.0)
        self.assertAlmostEqual(v.y, bed_y, delta=20.0)

if __name__ == "__main__":
    unittest.main()
