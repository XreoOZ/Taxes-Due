import unittest
import os
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import TILE_SIZE
from game.entities.villagers import Villager, VillagerManager, Family
from game.world.permits import PermitManager, AreaPermit, get_villager_home_position, find_closest_unassigned_household_worker
from game.systems.job_tool_system import assign_job_worker, release_job_worker
from game.systems.church_system import ChurchSystem
from game.systems.cemetery_system import CemeterySystem


class TestWorkerDistanceAndRelocation(unittest.TestCase):
    def setUp(self):
        self.vm = VillagerManager()
        self.pm = PermitManager()
        self.pm.permits.clear()

        # Housing Lots
        # Lot A: close to (0, 0) -> grid (4, 4) to (6, 6)
        self.housing_a = AreaPermit("house_a", "Cottage A", "housing", {(4+x, 4+y) for x in range(3) for y in range(3)})
        # Lot B: far at (50, 50) -> grid (50, 50) to (52, 52)
        self.housing_b = AreaPermit("house_b", "Cottage B", "housing", {(50+x, 50+y) for x in range(3) for y in range(3)})
        # Lot C: far away at (80, 80) -> grid (80, 80) to (82, 82)
        self.housing_c = AreaPermit("house_c", "Cottage C", "housing", {(80+x, 80+y) for x in range(3) for y in range(3)})

        # Workplace Lot: at (0, 0) -> grid (0, 0) to (3, 3)
        self.farm_p = AreaPermit("farm_1", "Parish Farm", "farm", {(x, y) for x in range(4) for y in range(4)})
        self.pm.permits.extend([self.housing_a, self.housing_b, self.housing_c, self.farm_p])

        # Family A (Initially in Housing A - close)
        self.fam_a = Family("fam_a", "Aldridge", assigned_permit_id="house_a")
        # Villager A1 is currently walking far away at (200, 200), but lives at House A
        self.va1 = Villager("vil_a1", "Arthur", "Aldridge", "Male", 30, 1, "Father", family_id="fam_a", x=200.0, y=200.0)
        self.va1.assigned_permit_id = "house_a"
        self.va2 = Villager("vil_a2", "Agnes", "Aldridge", "Female", 28, 1, "Mother", family_id="fam_a", x=200.0, y=200.0)
        self.va2.assigned_permit_id = "house_a"
        self.fam_a.members.extend([self.va1, self.va2])
        self.vm.families.append(self.fam_a)

        # Family B (Initially in Housing B - far)
        self.fam_b = Family("fam_b", "Baker", assigned_permit_id="house_b")
        # Villager B1 is currently physically standing near (2, 2), but lives at House B (far)
        self.vb1 = Villager("vil_b1", "Brian", "Baker", "Male", 32, 1, "Father", family_id="fam_b", x=2.0, y=2.0)
        self.vb1.assigned_permit_id = "house_b"
        self.vb2 = Villager("vil_b2", "Beatrice", "Baker", "Female", 29, 1, "Mother", family_id="fam_b", x=2.0, y=2.0)
        self.vb2.assigned_permit_id = "house_b"
        self.fam_b.members.extend([self.vb1, self.vb2])
        self.vm.families.append(self.fam_b)

    def test_01_household_residence_distance_used_not_wandering_coordinates(self):
        """
        Villager A1 is physically wandering at (200, 200) but lives at House A (distance ~5 tiles to Farm).
        Villager B1 is physically walking near (2, 2) but lives at House B (distance ~50 tiles to Farm).
        Assignment MUST select from Family A because Family A lives closest!
        """
        # Farm center is at (2 * TILE_SIZE, 2 * TILE_SIZE)
        self.pm.change_max_workers("farm_1", 1, self.vm)

        self.assertEqual(len(self.farm_p.assigned_workers), 1)
        assigned_id = self.farm_p.assigned_workers[0]
        self.assertIn(assigned_id, [self.va1.id, self.va2.id], "Candidate from Family A should be picked because they live closer!")
        self.assertNotIn(assigned_id, [self.vb1.id, self.vb2.id], "Candidate from Family B should NOT be picked just because they walked near the lot!")

    def test_02_dynamic_household_relocation(self):
        """
        Household A was close (House A), Household B was far (House B).
        Then Household A moves far to House C (80, 80).
        Household B moves close to House A (4, 4).
        Now assigning a worker to Farm MUST dynamically pick from Household B!
        """
        # Relocate Family A far away to House C
        self.fam_a.assigned_permit_id = "house_c"
        for m in self.fam_a.members:
            m.assigned_permit_id = "house_c"

        # Relocate Family B to House A (close!)
        self.fam_b.assigned_permit_id = "house_a"
        for m in self.fam_b.members:
            m.assigned_permit_id = "house_a"

        # Verify get_villager_home_position reflects relocation
        pos_b = get_villager_home_position(self.vb1, self.vm, self.pm)
        pos_a = get_villager_home_position(self.va1, self.vm, self.pm)
        farm_cx = (self.farm_p.grid_x + self.farm_p.tiles_w / 2.0) * TILE_SIZE
        farm_cy = (self.farm_p.grid_y + self.farm_p.tiles_h / 2.0) * TILE_SIZE

        import math
        dist_b = math.hypot(farm_cx - pos_b[0], farm_cy - pos_b[1])
        dist_a = math.hypot(farm_cx - pos_a[0], farm_cy - pos_a[1])
        self.assertLess(dist_b, dist_a, "Household B should now be closer to Farm than Household A")

        # Now assign a worker to Farm
        self.pm.change_max_workers("farm_1", 1, self.vm)
        self.assertEqual(len(self.farm_p.assigned_workers), 1)
        assigned_id = self.farm_p.assigned_workers[0]
        self.assertIn(assigned_id, [self.vb1.id, self.vb2.id], "After relocation, Household B member MUST be picked because they are now closer!")

    def test_03_universal_job_assignment_reflects_relocation(self):
        """
        Assigning jobs via assign_job_worker or ChurchSystem.assign_priest
        strictly uses household residence and dynamically updates with relocation.
        """
        church_p = AreaPermit("church_1", "Parish Church", "church", {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.pm.permits.append(church_p)

        # Move Household A to House C (far away)
        self.fam_a.assigned_permit_id = "house_c"
        for m in self.fam_a.members:
            m.assigned_permit_id = "house_c"

        # Move Household B to House A (close)
        self.fam_b.assigned_permit_id = "house_a"
        for m in self.fam_b.members:
            m.assigned_permit_id = "house_a"

        ok, priest = ChurchSystem.assign_priest(self.pm, self.vm)
        self.assertTrue(ok)
        self.assertIn(priest.id, [self.vb1.id, self.vb2.id], "Priest must be selected from Household B since they live closer!")

    def test_04_unassigned_workers_not_stolen(self):
        """
        Villagers who are already assigned to workplace permits or dedicated jobs
        must not be considered unassigned/unemployed candidates.
        """
        # Assign vb1 as Priest
        self.vb1.set_job("Priest")
        # Put va1 into farm_p
        self.farm_p.assigned_workers.append(self.va1.id)

        # Now find candidate for new job
        candidate = find_closest_unassigned_household_worker(0.0, 0.0, self.pm, self.vm, target_job="Farmer")
        self.assertIsNotNone(candidate)
        # Should NOT be vb1 (he's Priest) and NOT va1 (already assigned to farm_p)
        self.assertNotIn(candidate.id, [self.vb1.id, self.va1.id])
        self.assertIn(candidate.id, [self.va2.id, self.vb2.id])


if __name__ == "__main__":
    unittest.main()
