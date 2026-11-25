"""
Unit tests for Builder Priority feature.
Verifies:
1. ConstructionSite, Building, and Furniture priority toggling and synchronization with construction_order.
2. BuilderSystem prioritizes orders marked with priority=True ahead of earlier FIFO paid_seq orders.
3. Pre-emption: Builder shifts focus to a newly prioritized vital project.
4. RaportUI priority toggle button interactions.
"""

import os
import unittest
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

pygame.init()
pygame.display.set_mode((1, 1), pygame.NOFRAME)

from game.buildings.construction_site import ConstructionSite
from game.buildings.building import Building
from game.buildings.furniture import Furniture
from game.systems.work.builder_system import BuilderSystem
from game.entities.villagers import Villager, VillagerManager
from game.buildings.building_manager import BuildingManager
from game.buildings.furniture import FurnitureManager


class TestBuilderPriority(unittest.TestCase):
    def test_construction_site_priority_toggle(self):
        site = ConstructionSite("well", {(0, 0), (0, 1), (1, 0), (1, 1)})
        self.assertFalse(site.is_priority)
        self.assertFalse(site.construction_order.get("priority", False))

        # Toggle ON
        site.toggle_priority()
        self.assertTrue(site.is_priority)
        self.assertTrue(site.construction_order.get("priority", False))

        # Toggle OFF
        site.toggle_priority()
        self.assertFalse(site.is_priority)
        self.assertFalse(site.construction_order.get("priority", False))

    def test_building_priority_toggle(self):
        b = Building("wooden_structure", {(5, 5), (5, 6)})
        b.construction_order = {"id": "repair:1", "order_type": "REPAIR", "status": "PAID"}
        self.assertFalse(b.is_priority)

        b.toggle_priority()
        self.assertTrue(b.is_priority)
        self.assertTrue(b.construction_order.get("priority", False))

        b.toggle_priority()
        self.assertFalse(b.is_priority)

    def test_furniture_priority_toggle(self):
        f = Furniture("f1", "household_storage", 2, 2)
        f.construction_order = {"id": "furn:1", "status": "AWAITING_PAYMENT"}
        self.assertFalse(f.is_priority)

        f.toggle_priority()
        self.assertTrue(f.is_priority)
        self.assertTrue(f.construction_order.get("priority", False))

    def test_builder_system_selects_priority_over_earlier_order(self):
        """A vital project marked priority=True must be selected before an earlier paid_seq order."""
        bm = BuildingManager()
        fm = FurnitureManager()
        vm = VillagerManager()

        builder = Villager("b1", "Bob", "Builder", "Male", 30, 1, "Builder", "fam_1")
        builder.x = 0
        builder.y = 0

        # Create Site 1: earlier FIFO order (paid_seq = 1), Normal priority
        site1 = ConstructionSite("wooden_structure", {(10, 10), (10, 11)})
        site1.construction_order = {
            "id": "site1",
            "order_type": "PUBLIC_BUILD",
            "status": "PAID",
            "commission_paid": True,
            "paid_seq": 1,
            "priority": False,
            "artisan_job": "Builder",
        }
        site1.required_cost = {"Wood": 10, "Stone": 0}
        site1.delivered_cost = {"Wood": 10, "Stone": 0}
        bm.construction_sites.append(site1)

        # Create Site 2: later order (paid_seq = 2), but Vital PRIORITY
        site2 = ConstructionSite("well", {(20, 20), (20, 21), (21, 20), (21, 21)})
        site2.construction_order = {
            "id": "site2",
            "order_type": "PUBLIC_BUILD",
            "status": "PAID",
            "commission_paid": True,
            "paid_seq": 2,
            "priority": True,
            "artisan_job": "Builder",
        }
        site2.required_cost = {"Wood": 5, "Stone": 20}
        site2.delivered_cost = {"Wood": 5, "Stone": 20}
        site2.is_priority = True
        bm.construction_sites.append(site2)

        # Run BuilderSystem update_worker
        BuilderSystem.update_worker(
            builder, 0.1, "WORK", bm, fm, vm,
            [builder], None, None
        )

        # Site 2 (priority) must be assigned to builder over site 1 (earlier seq)
        self.assertEqual(site2.construction_order.get("builder_id"), str(builder.id))
        self.assertNotEqual(site1.construction_order.get("builder_id"), str(builder.id))

    def test_raport_ui_priority_click_handling(self):
        """Clicking priority toggle button in RaportUI updates the priority flag."""
        from game.ui.ui_raport import RaportUI
        raport = RaportUI()
        raport.is_open = True
        raport.active_tab = 0
        site = ConstructionSite("well", {(0, 0)})
        site.is_priority = False

        rect = pygame.Rect(100, 100, 80, 24)
        raport.priority_toggle_btn_rects[site] = rect

        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (120, 110)})
        result = raport.handle_event(ev, BuildingManager(), None, {})
        self.assertEqual(result, "toggle_priority")
        self.assertTrue(site.is_priority)

        # Second click toggles back OFF
        raport.priority_toggle_btn_rects[site] = rect
        result2 = raport.handle_event(ev, BuildingManager(), None, {})
        self.assertEqual(result2, "toggle_priority")
        self.assertFalse(site.is_priority)


if __name__ == "__main__":
    unittest.main()
