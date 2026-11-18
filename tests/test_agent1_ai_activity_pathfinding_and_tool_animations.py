"""
Acceptance Test Suite for AGENT 1 - AI ACTIVITY, PATHFINDING & TOOL ANIMATIONS
Covers:
1. Streamlined Pathfinding:
   - AI finds shortest route around solid buildings and furniture.
   - AI-to-AI pass-through: AI entities pass freely through each other without blocking or queues.
   - Landlord / Player Avoidance: AI does not pass through player, navigates tangentially around player.
   - Contextual speech bubbles upon avoiding player with cooldown.
2. AI Idle Activity Synchronization:
   - Activity description matches actual physical behavior (moving vs working vs idle).
   - Tool-specific activity descriptions ("Tilling soil with Hoe", "Watering crops with Watering Can", etc.).
3. Tool-Based Activity Visuals:
   - Visually holding and animating tools (Hoe, Watering Can, Sickle, Hammer) during appropriate activities.
"""

import unittest
import math
import pygame
from game.config import (
    TILE_SIZE,
    VILLAGER_RADIUS,
    ROUTE_STATE_ACTIVE,
    ROUTE_STATE_COMPLETED
)
from game.buildings.buildings import Building, BuildingManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.entities.villagers import Villager, VillagerManager, Family
from game.entities.servants import Servant, ServantManager
from game.entities.player import Player

class TestAgent1AIActivityPathfindingAndToolAnimations(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.bm = BuildingManager()
        self.fm = FurnitureManager()
        self.pm = None
        from game.world.permits import PermitManager
        self.pm = PermitManager()
        self.vm = VillagerManager()
        self.sm = ServantManager()
        self.player = Player(500.0, 500.0)

    def test_01_ai_entities_pass_freely_through_each_other(self):
        """1. All AI entities pass freely through each other without collision avoidance or queues."""
        v1 = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=100.0, y=200.0)
        v2 = Villager("vil_2", "Bob", "Fletcher", "Male", 25, 1, "Son", "fam_1", x=300.0, y=200.0)

        # Opposite routes: v1 moving east to (300, 200), v2 moving west to (100, 200)
        all_ents = [v1, v2]
        dt = 0.05

        for _ in range(30):
            v1._move_towards(300.0, 200.0, dt, arrival_dist=8, all_entities=all_ents, player=None, building_manager=self.bm)
            v2._move_towards(100.0, 200.0, dt, arrival_dist=8, all_entities=all_ents, player=None, building_manager=self.bm)

        # They should have crossed paths smoothly without either stopping or becoming stuck
        self.assertGreater(v1.x, 150.0, "v1 should progress east through v2")
        self.assertLess(v2.x, 250.0, "v2 should progress west through v1")
        self.assertFalse(v1.is_waiting_for_path)
        self.assertFalse(v2.is_waiting_for_path)

    def test_01b_villagers_update_loop_pass_through_without_pushing(self):
        """1b. VillagerManager update loop does not push moving or passing villagers apart."""
        v1 = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=200.0, y=200.0)
        v2 = Villager("vil_2", "Bob", "Fletcher", "Male", 25, 1, "Son", "fam_1", x=205.0, y=200.0)
        fam = Family("fam_1", "Fletcher", [v1, v2])
        self.vm.families = [fam]

        # In VillagerManager.update, villagers passing each other are not physically pushed away
        self.vm.update(0.05, self.pm, self.bm, [v1, v2], None)
        # Position should not have been shoved away to 54px min_gap
        dist = math.hypot(v2.x - v1.x, v2.y - v1.y)
        self.assertLess(dist, 10.0, "Villagers must pass through without collision separation push")

    def test_02_ai_navigates_around_landlord_player_without_passing_through(self):
        """2. AI must not pass through the Landlord/player; navigates tangentially around them."""
        v = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=100.0, y=300.0)
        # Place player directly in the straight path between (100, 300) and (400, 300)
        self.player.x = 250.0
        self.player.y = 300.0

        dt = 0.05
        min_distance_recorded = float("inf")

        for _ in range(60):
            v._move_towards(400.0, 300.0, dt, arrival_dist=10, all_entities=[v], player=self.player, building_manager=self.bm)
            dist_to_p = math.hypot(v.x - self.player.x, v.y - self.player.y)
            if dist_to_p < min_distance_recorded:
                min_distance_recorded = dist_to_p

        # AI must maintain physical separation from player (never overlap center)
        self.assertGreater(min_distance_recorded, v.radius, "AI must not pass through player's physical center")
        self.assertGreater(v.x, 300.0, "AI must continue moving past player toward target")

    def test_03_player_avoidance_triggers_polite_speech_bubbles(self):
        """3. When AI avoids Landlord/player, polite speech bubbles are spoken with cooldown."""
        v = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=240.0, y=300.0)
        self.player.x = 250.0
        self.player.y = 300.0

        v._move_towards(350.0, 300.0, dt=0.05, arrival_dist=10, all_entities=[v], player=self.player, building_manager=self.bm)

        # Bubble spoken
        self.assertIsNotNone(v.speech_text)
        valid_bubbles = ["Sorry, my lord.", "Pardon me, my lord.", "Excuse me, my lord.", "My apologies, my lord.", "Coming through, my lord."]
        self.assertIn(v.speech_text, valid_bubbles)
        self.assertGreater(v.player_avoid_speech_cooldown, 0.0)

    def test_04_activity_description_distinguishes_moving_vs_tool_usage(self):
        """4. AI idle activity bug fix: get_current_activity accurately reflects moving vs active tool work."""
        v = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=100.0, y=100.0)
        v.job = "Farmer"

        # Tilling: moving to plot
        v.task = "TILLING"
        v.is_moving = True
        v.tilling_timer = 0.0
        self.assertEqual(v.get_current_activity(), "Walking to Farm plot")

        # Tilling: actively working with hoe
        v.is_moving = False
        v.tilling_timer = 1.5
        self.assertEqual(v.get_current_activity(), "Tilling soil with Hoe")

        # Watering: moving to crop
        v.task = "WATERING"
        v.is_moving = True
        v.watering_timer = 0.0
        self.assertEqual(v.get_current_activity(), "Walking to crop to water")

        # Watering: actively watering
        v.is_moving = False
        v.watering_timer = 1.0
        self.assertEqual(v.get_current_activity(), "Watering crops with Watering Can")

        # Harvesting with sickle
        v.task = "HARVESTING"
        v.is_moving = False
        self.assertEqual(v.get_current_activity(), "Harvesting crops with Sickle")

    def test_05_tool_animations_render_in_draw(self):
        """5. Villager draw method executes tool-specific visuals without crash."""
        surf = pygame.Surface((800, 600))
        font = pygame.font.SysFont("Segoe UI", 12)
        from game.camera import Camera
        cam = Camera(800, 600)

        v = Villager("vil_1", "Alice", "Fletcher", "Female", 22, 1, "Daughter", "fam_1", x=400.0, y=300.0)
        v.equipped_tool = "Hoe"
        v.task = "TILLING"
        v.tilling_timer = 1.0

        # Draw hoeing
        v.draw(surf, cam, font)

        # Draw watering
        v.equipped_tool = "Watering_Can"
        v.task = "WATERING"
        v.watering_timer = 1.0
        v.draw(surf, cam, font)

        # Draw sickle
        v.equipped_tool = "Sickle"
        v.task = "HARVESTING"
        v.draw(surf, cam, font)

        # Servant hammer
        s = Servant("servant_1", "Alden", x=400.0, y=300.0)
        s.state = "BUILDING"
        s.draw(surf, cam, font)

if __name__ == "__main__":
    unittest.main()
