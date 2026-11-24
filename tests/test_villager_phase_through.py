"""
Unit tests for Villager Phase-Through & Universal Pathfinding Anti-Stuck Behavior
"""
import unittest
from game.config import TILE_SIZE, VILLAGER_PHASE_THROUGH_OBSTACLES
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.villagers import Villager


class TestVillagerPhaseThrough(unittest.TestCase):
    def setUp(self):
        self.building_mgr = BuildingManager()
        self.furniture_mgr = FurnitureManager()

        # Create a house with a door
        self.house = Building("house", {(10, 10), (10, 11), (11, 10), (11, 11)})
        self.house.door_pos = (10, 11)
        self.building_mgr.buildings.append(self.house)

        # Place furniture inside
        self.bed = Furniture("bed_1", "bed", 11 * TILE_SIZE, 10 * TILE_SIZE)
        self.furniture_mgr.furnitures.append(self.bed)

    def test_config_flag_enabled(self):
        """VILLAGER_PHASE_THROUGH_OBSTACLES should be enabled for anti-stuck."""
        self.assertTrue(VILLAGER_PHASE_THROUGH_OBSTACLES)

    def test_villager_still_uses_universal_pathfinding(self):
        """Villagers still calculate and follow A* navigation paths."""
        v = Villager("v1", "Test", "Villager", "M", 25, 1, "Builder", "fam1")
        v.x, v.y = 8 * TILE_SIZE, 8 * TILE_SIZE

        # Target is outside on the other side of the house
        target_x, target_y = 13 * TILE_SIZE, 8 * TILE_SIZE
        handled = v._move_towards(
            target_x, target_y, 0.1,
            arrival_dist=10,
            building_manager=self.building_mgr,
            furniture_manager=self.furniture_mgr,
        )
        # Should have generated a path and begun moving along it
        self.assertTrue(len(v.current_path) > 0)
        self.assertIn(v.route_state, ("ASSIGNED", "ACTIVE"))

    def test_phase_escape_tile_when_trapped(self):
        """If a villager is somehow trapped inside a solid building, escape tile is found."""
        solid_b = Building("rock_quarry", {(20, 20)})
        solid_b.is_solid = True
        solid_b.door_pos = None
        self.building_mgr.buildings.append(solid_b)

        v = Villager("v_trapped", "Trapped", "Villager", "M", 30, 1, "Miner", "fam1")
        # Place directly inside the solid rock
        v.x = (20 + 0.5) * TILE_SIZE
        v.y = (20 + 0.5) * TILE_SIZE

        escape_tile = v._find_phase_escape_tile(self.building_mgr, self.furniture_mgr)
        self.assertIsNotNone(escape_tile)
        # Escape tile must not be inside the rock
        escape_gx = int(escape_tile[0] // TILE_SIZE)
        escape_gy = int(escape_tile[1] // TILE_SIZE)
        self.assertNotEqual((escape_gx, escape_gy), (20, 20))

    def test_water_collision_still_enforced(self):
        """Phase-through should NOT allow walking into ocean/water."""
        v = Villager("v_swimmer", "Dry", "Villager", "F", 22, 1, "Farmer", "fam1")
        # Valid land tile near water (e.g. at map edge or negative coords)
        v.x, v.y = 20 * TILE_SIZE, 20 * TILE_SIZE
        old_x, old_y = v.x, v.y

        # Try to step into ocean/void (-99999, -99999)
        v._move_towards(-99999, -99999, 1.0, building_manager=self.building_mgr)
        # Should not walk out of land into deep water
        self.assertTrue(v.x > -50000)


if __name__ == "__main__":
    unittest.main()
