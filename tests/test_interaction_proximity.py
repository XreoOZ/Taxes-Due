import unittest

from game.config import TILE_SIZE
from game.buildings.buildings import Building, BuildingManager
from game.buildings.furniture import Furniture
from game.entities.villagers import Villager
from game.world.navigation import distance_to_object, interaction_arrival_distance


class TestInteractionProximity(unittest.TestCase):
    def test_arrival_distance_is_capped_by_object_footprint(self):
        building = Building("wooden_structure", {(4, 4), (5, 4), (4, 5), (5, 5)})
        approach = (4.5 * TILE_SIZE, 3.5 * TILE_SIZE)

        self.assertEqual(distance_to_object(building, *approach), TILE_SIZE / 2)
        self.assertEqual(
            interaction_arrival_distance(building, *approach, TILE_SIZE, TILE_SIZE),
            TILE_SIZE / 2,
        )

        furniture = Furniture("chest", "household_storage", 4, 4, permit_id="test_permit")
        self.assertEqual(distance_to_object(furniture, *approach), TILE_SIZE / 2)

    def test_interaction_does_not_finish_outside_one_tile_of_building(self):
        building = Building("wooden_structure", {(4, 4)})
        manager = BuildingManager()
        manager.buildings.append(building)
        manager.rebuild_tile_cache()

        villager = Villager(
            villager_id="interactor", first_name="A", last_name="B",
            gender="Male", age=30, generation=1, role="Father", family_id="family",
        )
        target = (4.5 * TILE_SIZE, 3.5 * TILE_SIZE)
        villager.x, villager.y = target[0], target[1] - TILE_SIZE + 10

        arrived = villager._move_towards(
            *target, dt=0.05, arrival_dist=TILE_SIZE,
            building_manager=manager, interaction_target=building,
        )

        self.assertFalse(arrived)
        self.assertGreater(villager.y, target[1] - TILE_SIZE + 10)


if __name__ == "__main__":
    unittest.main()
