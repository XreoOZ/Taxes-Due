import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pygame

pygame.init()

from game.systems import day_cycle as day_cycle_module
from game.systems.day_cycle import DayCycleSystem
from game.systems.speed_control import SpeedController
from game.systems.taxation_system import TaxationSystem
from game.ui.ui_raport import RaportUI


class TestConfigurableControlsAndAmbient(unittest.TestCase):
    def test_speed_shortcut_uses_configured_level_key_and_action(self):
        controller = SpeedController()
        controller.levels = [
            {"id": "custom", "key_label": "9", "speed": 3.0, "short_label": "3×"}
        ]
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_9)

        self.assertEqual(controller.handle_event(event), "speed_custom")
        self.assertEqual(controller.active_index, 0)
        self.assertEqual(controller.get_multiplier(), 3.0)

    def test_tax_rate_digits_are_handled_by_open_town_ledger(self):
        ledger = RaportUI()
        ledger.open()
        ledger.active_tab = 7
        ledger.socage_tax_input_active = True
        original_rate = TaxationSystem.get_socage_percent()

        try:
            for digit in "12345":
                ledger.socage_tax_input_text = ""
                event = pygame.event.Event(
                    pygame.KEYDOWN,
                    key=getattr(pygame, f"K_{digit}"),
                    unicode=digit,
                )
                action = ledger.handle_event(
                    event, None, None, {}, villager_manager=None,
                )

                self.assertEqual(action, "socage_tax_input_edit")
                self.assertEqual(ledger.socage_tax_input_text, digit)

            ledger.socage_tax_input_text = "5"
            ledger.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r"),
                None, None, {}, villager_manager=None,
            )
            self.assertEqual(TaxationSystem.get_socage_percent(), 5)
        finally:
            TaxationSystem.set_socage_percent(original_rate)

    def test_day_cycle_ambient_boundaries_follow_lighting_config(self):
        cycle = DayCycleSystem()
        with patch.dict(day_cycle_module.DAY_CYCLE_LIGHTING, {"sunset_start_hour": 17.0}):
            cycle.time_seconds = (17.0 / day_cycle_module.HOURS_PER_DAY) * cycle.day_length_seconds
            overlay = cycle.get_ambient_overlay(1, 1)

        self.assertIsNotNone(overlay)
        self.assertEqual(overlay.get_at((0, 0)), (*day_cycle_module.DAY_CYCLE_LIGHTING["sunset_start_color"], 30))


if __name__ == "__main__":
    unittest.main()
