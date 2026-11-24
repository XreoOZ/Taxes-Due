import unittest
import pygame
import os
from time import perf_counter

from game.buildings.furniture import Furniture
from game.ui.modals.toolmaker_catalog_modal import ToolmakerCatalogModal
from game.systems.work.toolmaker_system import ToolmakerSystem, ToolOrderSubject
from game.entities.villagers import Villager, Family
from game.data.config import TILE_SIZE


class DummyBuildingManager:
    def __init__(self):
        self.buildings = []

    def get_building_at(self, gx, gy):
        return None

    def find_path(self, start, end, tile_size):
        return [end]

    def get_pending_demolition(self):
        return None

    def get_pending_site(self):
        return None


class DummyFurnitureManager:
    def __init__(self):
        self.furnitures = []

    def get_storage_for_family(self, family_id):
        for f in self.furnitures:
            if getattr(f, "furniture_type", "") == "household_storage" and str(getattr(f, "family_id", "")) == str(family_id):
                return f
        return None


class DummyStockpileManager:
    def __init__(self):
        self.dropped = []

    def drop_resource(self, name, qty, gx, gy, owner_type="villager", owner_id=None):
        self.dropped.append({"name": name, "qty": qty, "gx": gx, "gy": gy, "owner_type": owner_type, "owner_id": owner_id})

    def get_available_storage_tile(self, permit_manager, item_name):
        return (5, 5)


class DummyVillagerManager:
    def __init__(self):
        self.villagers = []
        self.families = []

    def get_all_villagers(self):
        return self.villagers

    def get_family_by_id(self, fam_id):
        for fam in self.families:
            if str(fam.id) == str(fam_id):
                return fam
        return None

    def invalidate_villager_cache(self):
        pass


class DummyPlayer:
    def __init__(self):
        self.x = 100
        self.y = 100
        self.radius = 16
        self.inventory = {}
        self.speech_text = None

    def say(self, text, duration=2.0):
        self.speech_text = text


class DummyDayCycle:
    def __init__(self):
        self.day_number = 1
        self.day_length_seconds = 1200.0


class TestToolmakerWorkbenchInventoryPickup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((800, 600))

    def setUp(self):
        self.bm = DummyBuildingManager()
        self.fm = DummyFurnitureManager()
        self.vm = DummyVillagerManager()
        self.sm = DummyStockpileManager()
        self.player = DummyPlayer()
        self.day_cycle = DummyDayCycle()

        # Toolmaker workbench
        self.wb = Furniture("wb_1", "toolmaker_workbench", 10, 10)
        self.fm.furnitures.append(self.wb)

    def test_catalog_modal_retention_and_set_order(self):
        modal = ToolmakerCatalogModal()
        modal.open(self.wb)
        self.assertTrue(modal.is_open)
        self.assertIs(modal.workbench, self.wb)
        self.assertIs(modal.last_workbench, self.wb)

        # Simulate ordering a set
        modal._ensure_fonts()
        modal.draw(pygame.display.get_surface(), self.bm, self.vm)

        # Trigger order set
        order_key = next((k for k in modal.order_rects if k.startswith("SET|Farmer")), None)
        self.assertIsNotNone(order_key)
        rect = modal.order_rects[order_key]
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": rect.center})
        action = modal.handle_event(event)

        self.assertIsNotNone(action)
        self.assertTrue(action.startswith("tool_order_set_Farmer_"))
        self.assertFalse(modal.is_open)
        # Even though modal is closed, last_workbench is preserved
        self.assertIs(modal.last_workbench, self.wb)

        # main.py resolution
        resolved_wb = modal.workbench or getattr(modal, "last_workbench", None)
        self.assertIs(resolved_wb, self.wb)

        # Create tool set order
        subjects, err = ToolmakerSystem.create_tool_set_order(
            resolved_wb, "Farmer", 1, payer_family_id=None,
            building_manager=self.bm, villager_manager=self.vm
        )
        self.assertIsNone(err)
        self.assertEqual(len(subjects), 3)  # Farmer Set: Hoe, Watering_Can, Sickle
        self.assertEqual(len(self.wb.tool_order_subjects), 3)

    def test_output_rack_tab_and_actions(self):
        modal = ToolmakerCatalogModal()
        self.wb.output_inventory = {"Hoe": 2, "Sickle": 1}
        modal.open(self.wb)

        # Draw to initialize rects
        surface = pygame.display.get_surface()
        modal.draw(surface, self.bm, self.vm)

        # Click OUTPUT_RACK tab
        tab_rect = modal.tab_rects["OUTPUT_RACK"]
        ev_tab = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": tab_rect.center})
        res = modal.handle_event(ev_tab)
        self.assertEqual(res, "tab_change")
        self.assertEqual(modal.current_tab, "OUTPUT_RACK")

        # Draw OUTPUT_RACK view
        modal.draw(surface, self.bm, self.vm)
        self.assertIn("TAKE|Hoe", modal.rack_action_rects)
        self.assertIn("HAUL|Hoe", modal.rack_action_rects)

        # Click Take 1
        btn_take = modal.rack_action_rects["TAKE|Hoe"]
        ev_take = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": btn_take.center})
        take_action = modal.handle_event(ev_take)
        self.assertEqual(take_action, "tool_take_Hoe")

        # Click Haul
        btn_haul = modal.rack_action_rects["HAUL|Hoe"]
        ev_haul = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": btn_haul.center})
        haul_action = modal.handle_event(ev_haul)
        self.assertEqual(haul_action, "tool_haul_Hoe")

    def test_manual_take_tool_action(self):
        self.wb.output_inventory = {"Pickaxe": 1}
        tool_name = "Pickaxe"

        # Simulate main.py tool_take action
        if hasattr(self.wb, "output_inventory") and isinstance(self.wb.output_inventory, dict):
            curr = self.wb.output_inventory.get(tool_name, 0)
            if curr > 0:
                self.wb.output_inventory[tool_name] = curr - 1
                if self.wb.output_inventory[tool_name] <= 0:
                    self.wb.output_inventory.pop(tool_name, None)
                self.player.inventory[tool_name] = int(self.player.inventory.get(tool_name, 0)) + 1

        self.assertEqual(self.player.inventory.get("Pickaxe"), 1)
        self.assertNotIn("Pickaxe", self.wb.output_inventory)

    def test_household_tool_commission_pickup(self):
        # Create family and farmer
        fam = Family("1", "Smith")
        self.vm.families.append(fam)

        farmer = Villager(
            villager_id="v1", first_name="John", last_name="Smith",
            gender="male", age=30, generation=1, role="father",
            family_id="1", x=10 * TILE_SIZE, y=10 * TILE_SIZE
        )
        farmer.job = "Farmer"
        self.vm.villagers.append(farmer)

        # Queue a tool commission
        subject, err = ToolmakerSystem.create_tool_order(
            self.wb, "Hoe", 1, payer_family_id="1",
            building_manager=self.bm, villager_manager=self.vm, payer_id="v1"
        )
        self.assertIsNone(err)
        order = subject.construction_order
        self.assertEqual(order["status"], "AWAITING_PAYMENT")

        # Pay and finish crafting
        order["status"] = "PAID"
        self.wb.output_inventory["Hoe"] = 1
        order["status"] = "READY_FOR_PICKUP"

        # Ensure _ensure_tool_commissions treats READY_FOR_PICKUP as covered
        covered = farmer._ensure_tool_commissions([("Hoe", 1)], self.bm, self.fm, self.vm)
        self.assertTrue(covered)
        # Should not create duplicate orders
        self.assertEqual(len(self.wb.tool_order_subjects), 1)

        # Update farmer at workbench approach point
        dest = self.wb.get_approach_point(farmer.x, farmer.y)
        farmer.x = dest[0]
        farmer.y = dest[1]
        farmer.update(
            dt=0.1, permit_manager=None, building_manager=self.bm,
            all_entities=[farmer], player=self.player, stockpile_manager=self.sm,
            furniture_manager=self.fm, day_cycle=self.day_cycle, villager_manager=self.vm
        )

        # Farmer should have picked up the tool from the output rack!
        self.assertEqual(order["status"], "COMPLETE")
        self.assertEqual(farmer.inventory.get("Hoe"), 1)
        self.assertEqual(self.wb.output_inventory.get("Hoe", 0), 0)

    def test_toolmaker_fallback_delivery(self):
        # Customer family with household chest
        fam = Family("2", "Miller")
        self.vm.families.append(fam)
        chest = Furniture("chest_2", "household_storage", 20, 20, family_id="2")
        self.fm.furnitures.append(chest)

        # Toolmaker
        tm_fam = Family("3", "Forge")
        self.vm.families.append(tm_fam)
        tm_chest = Furniture("chest_3", "household_storage", 5, 5, family_id="3")
        self.fm.furnitures.append(tm_chest)

        toolmaker = Villager(
            villager_id="tm1", first_name="Tom", last_name="Forge",
            gender="male", age=35, generation=1, role="father",
            family_id="3", x=10 * TILE_SIZE, y=10 * TILE_SIZE
        )
        toolmaker.job = "Toolmaker"
        self.vm.villagers.append(toolmaker)

        # Finished order on workbench
        subject, _ = ToolmakerSystem.create_tool_order(
            self.wb, "Sickle", 1, payer_family_id="2",
            building_manager=self.bm, villager_manager=self.vm, payer_id="v2"
        )
        order = subject.construction_order
        order["status"] = "READY_FOR_PICKUP"
        order["builder_id"] = "tm1"
        order["_pickup_grace_until"] = perf_counter() - 1.0  # Grace expired
        self.wb.output_inventory["Sickle"] = 1

        # Toolmaker updates: picks up from workbench output rack and delivers to customer chest
        dest = chest.get_approach_point(toolmaker.x, toolmaker.y)
        toolmaker.x = dest[0]
        toolmaker.y = dest[1]
        ToolmakerSystem.update_worker(
            toolmaker, dt=0.1, schedule_activity="WORK", building_manager=self.bm,
            furniture_manager=self.fm, villager_manager=self.vm, all_entities=[toolmaker],
            player=self.player, day_cycle=self.day_cycle, stockpile_manager=self.sm
        )

        self.assertEqual(order["status"], "COMPLETE")
        self.assertEqual(chest.inventory.get("Sickle"), 1)
        self.assertEqual(self.wb.output_inventory.get("Sickle", 0), 0)

    def test_save_load_output_inventory(self):
        self.wb.output_inventory = {"Axe": 3, "Hoe": 1}
        sub, _ = ToolmakerSystem.create_tool_order(
            self.wb, "Hoe", 1, payer_family_id=None,
            building_manager=self.bm, villager_manager=self.vm
        )

        # Serialize as in save_system.py
        f_data = {
            "furniture_type": self.wb.furniture_type,
            "grid_x": self.wb.grid_x,
            "grid_y": self.wb.grid_y,
            "output_inventory": dict(getattr(self.wb, "output_inventory", {}) or {}),
            "tool_orders": [dict(s.construction_order) for s in (getattr(self.wb, "tool_order_subjects", None) or []) if getattr(s, "construction_order", None)],
        }

        # Deserialize as in save_system.py
        loaded_wb = Furniture("wb_loaded", f_data["furniture_type"], f_data["grid_x"], f_data["grid_y"])
        loaded_wb.output_inventory = dict(f_data.get("output_inventory", {}) or {})
        loaded_wb.tool_order_subjects = []
        for order_d in f_data.get("tool_orders", []) or []:
            loaded_wb.tool_order_subjects.append(ToolOrderSubject(loaded_wb, dict(order_d)))

        self.assertEqual(loaded_wb.output_inventory.get("Axe"), 3)
        self.assertEqual(loaded_wb.output_inventory.get("Hoe"), 1)
        self.assertEqual(len(loaded_wb.tool_order_subjects), 1)
        self.assertEqual(loaded_wb.tool_order_subjects[0].construction_order.get("tool_name"), "Hoe")

    def test_unaffordable_tool_commission_creates_no_phantom_orders(self):
        """When household has 0 coins, no order is placed on workbench."""
        fam = Family("10", "Poor")
        self.vm.families.append(fam)
        chest = Furniture("chest_10", "household_storage", 20, 20, family_id="10")
        chest.inventory = {}
        self.fm.furnitures.append(chest)

        farmer = Villager(
            villager_id="v_poor", first_name="Poor", last_name="Poor",
            gender="male", age=30, generation=1, role="father",
            family_id="10", x=10 * TILE_SIZE, y=10 * TILE_SIZE
        )
        farmer.job = "Farmer"
        farmer.inventory = {}
        self.vm.villagers.append(farmer)

        covered = farmer._ensure_tool_commissions([("Hoe", 1)], self.bm, self.fm, self.vm)
        self.assertFalse(covered)
        # Workbench must have 0 orders (no phantom orders!)
        self.assertEqual(len(getattr(self.wb, "tool_order_subjects", [])), 0)
        self.assertNotEqual(farmer.task, "COMMISSIONING_TOOL_TRAVEL")

    def test_affordable_tool_commission_starts_physical_errand(self):
        """When household has coins in chest, villager retrieves them and walks to bench."""
        fam = Family("11", "Rich")
        self.vm.families.append(fam)
        chest = Furniture("chest_11", "household_storage", 20, 20, family_id="11")
        chest.inventory = {"Copper": 100}
        self.fm.furnitures.append(chest)

        farmer = Villager(
            villager_id="v_rich", first_name="Rich", last_name="Farmer",
            gender="male", age=30, generation=1, role="father",
            family_id="11", x=10 * TILE_SIZE, y=10 * TILE_SIZE
        )
        farmer.job = "Farmer"
        farmer.inventory = {}
        self.vm.villagers.append(farmer)

        covered = farmer._ensure_tool_commissions([("Hoe", 1)], self.bm, self.fm, self.vm)
        self.assertFalse(covered)  # Errand started, not yet covered by placed order
        self.assertEqual(farmer.task, "COMMISSIONING_TOOL_RETRIEVE_COINS")
        self.assertEqual(farmer.commission_tool_name, "Hoe")

        # Teleport to chest and update to retrieve coins
        chest_pos = chest.get_world_pos(TILE_SIZE)
        farmer.x, farmer.y = chest_pos[0], chest_pos[1]
        farmer.update(
            dt=0.1, permit_manager=None, building_manager=self.bm,
            all_entities=[farmer], player=self.player, stockpile_manager=self.sm,
            furniture_manager=self.fm, day_cycle=self.day_cycle, villager_manager=self.vm
        )
        self.assertEqual(farmer.task, "COMMISSIONING_TOOL_TRAVEL")
        self.assertGreater(farmer.inventory.get("Copper", 0), 0)

        # Teleport to workbench and arrive
        bench_pos = self.wb.get_approach_point(farmer.x, farmer.y)
        farmer.x, farmer.y = bench_pos[0], bench_pos[1]
        farmer.update(
            dt=0.1, permit_manager=None, building_manager=self.bm,
            all_entities=[farmer], player=self.player, stockpile_manager=self.sm,
            furniture_manager=self.fm, day_cycle=self.day_cycle, villager_manager=self.vm
        )
        # Order placed and PAID on arrival!
        self.assertEqual(len(self.wb.tool_order_subjects), 1)
        placed_order = self.wb.tool_order_subjects[0].construction_order
        self.assertEqual(placed_order["status"], "PAID")
        self.assertEqual(placed_order["tool_name"], "Hoe")

    def test_clean_completed_orders_purges_from_workbench(self):
        """Completed orders are deleted from workbench subjects."""
        sub, _ = ToolmakerSystem.create_tool_order(
            self.wb, "Hoe", 1, payer_family_id=None,
            building_manager=self.bm, villager_manager=self.vm
        )
        self.assertEqual(len(self.wb.tool_order_subjects), 1)
        sub.construction_order["status"] = "COMPLETE"
        ToolmakerSystem.clean_completed_orders(self.wb)
        self.assertEqual(len(self.wb.tool_order_subjects), 0)


if __name__ == "__main__":
    unittest.main()
