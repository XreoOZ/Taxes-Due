import unittest
import os
import pygame
from game.data.config import (
    DEFAULT_RESOURCES,
    TOOL_TYPES,
    CROP_TYPES,
    RAPORT_MODAL_WIDTH,
    RAPORT_MODAL_HEIGHT
)
from game.entities.villagers import Villager, Family, VillagerManager
from game.buildings.furniture import FurnitureManager, Furniture
from game.world.stockpile import StockpileManager, ResourceStack
from game.entities.servants import ServantManager
from game.systems.household_inventory import (
    get_household_possessions,
    canonical_item_name,
    sort_possession_items
)
from game.ui.ui_raport import RaportUI, draw_item_icon
from game.data.planning import get_all_planning_features
from game.systems.save_system import save_to_slot, load_from_slot


class TestHouseholdPossessionUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.villager_manager = VillagerManager()
        self.furniture_manager = FurnitureManager()
        self.stockpile_manager = StockpileManager()
        self.servant_manager = ServantManager()

        # Create a test family with 2 members
        self.family = Family(1, "Brewer")
        v1 = Villager(1, "John", "Brewer", "male", 30, 2, "Father", 1)
        v2 = Villager(2, "Mary", "Brewer", "female", 28, 2, "Mother", 1)
        self.family.members.append(v1)
        self.family.members.append(v2)
        self.villager_manager.families.append(self.family)

        # Create a household chest for the family
        self.chest = Furniture(1, "household_storage", 10, 10, permit_id=1, family_id=1)
        self.chest.inventory = {}
        self.furniture_manager.furnitures.append(self.chest)

    def test_01_empty_household_inventory_displays_no_entries(self):
        """1. Empty household inventory displays no item entries."""
        possessions = get_household_possessions(
            self.family,
            self.furniture_manager,
            self.stockpile_manager,
            self.servant_manager
        )
        self.assertEqual(possessions, {})

        items = sort_possession_items(possessions)
        self.assertEqual(items, [])
        self.assertEqual(len(items), 0)

        # UI test: render with empty inventory
        ui = RaportUI()
        ui.is_open = True
        ui.active_tab = 4  # Household tab
        ui.selected_family_id = 1
        ui.show_household_possession = True

        screen = pygame.Surface((1280, 720))
        ui.draw(
            screen,
            building_manager=type("BM", (), {"buildings": []})(),
            permit_manager=type("PM", (), {"permits": []})(),
            resources=DEFAULT_RESOURCES,
            villager_manager=self.villager_manager,
            furniture_manager=self.furniture_manager,
            stockpile_manager=self.stockpile_manager,
            servant_manager=self.servant_manager
        )
        # With zero items, no pagination buttons exist
        self.assertIsNone(ui.possession_prev_btn_rect)
        self.assertIsNone(ui.possession_next_btn_rect)

    def test_02_adding_potato_displays_actual_quantity(self):
        """2. Adding Potato displays Potato with its actual quantity."""
        self.chest.store_item("Potato", 45)

        possessions = get_household_possessions(
            self.family,
            self.furniture_manager,
            self.stockpile_manager,
            self.servant_manager
        )
        self.assertIn("Potato", possessions)
        self.assertEqual(possessions["Potato"], 45)

        items = sort_possession_items(possessions)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Potato")
        self.assertEqual(items[0]["count"], 45)

    def test_03_collecting_water_displays_actual_water_quantity(self):
        """3. Collecting Water displays the actual Water quantity."""
        # Water can be collected in villager member inventory or stored in chest
        v1 = self.family.members[0]
        v1.inventory["Water"] = 3
        self.chest.store_item("Water", 7)

        possessions = get_household_possessions(
            self.family,
            self.furniture_manager,
            self.stockpile_manager,
            self.servant_manager
        )
        # Total possessed water = 3 (carried) + 7 (chest) = 10
        self.assertIn("Water", possessions)
        self.assertEqual(possessions["Water"], 10)

        items = sort_possession_items(possessions)
        water_item = next((it for it in items if it["name"] == "Water"), None)
        self.assertIsNotNone(water_item)
        self.assertEqual(water_item["count"], 10)

    def test_04_producing_or_purchasing_automatically_adds_item(self):
        """4. Producing or purchasing an item automatically adds it."""
        from game.systems.market_service import MarketService
        from game.buildings.buildings import Building

        market = Building("market", [(20, 20), (21, 20), (22, 20), (20, 21), (21, 21), (22, 21)])
        market.inventory = {"Potato": 50}
        market.prices = {"Potato": 3}
        market.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        # Fund household chest
        self.chest.inventory["Copper"] = 30

        # Purchase 4 potatoes (costs 12 Copper)
        bm_mock = type("BM", (), {"buildings": [market]})()
        ok, msg, receipt = MarketService.execute_purchase(
            self.family, "Potato", 4,
            building_manager=bm_mock,
            furniture_manager=self.furniture_manager,
            villager_manager=self.villager_manager
        )
        self.assertTrue(ok)

        # Check possessions
        possessions = get_household_possessions(
            self.family,
            self.furniture_manager,
            self.stockpile_manager,
            self.servant_manager
        )
        self.assertEqual(possessions["Potato"], 4)
        self.assertEqual(possessions["Copper"], 18)

    def test_05_consuming_item_decreases_displayed_quantity(self):
        """5. Consuming an item decreases its displayed quantity."""
        self.chest.store_item("Potato", 10)
        possessions_before = get_household_possessions(self.family, self.furniture_manager)
        self.assertEqual(possessions_before["Potato"], 10)

        # AI eats 2 potatoes
        taken = self.chest.take_item("Potato", 2)
        self.assertEqual(taken, 2)

        possessions_after = get_household_possessions(self.family, self.furniture_manager)
        self.assertEqual(possessions_after["Potato"], 8)

    def test_06_transferring_item_updates_correct_household(self):
        """6. Transferring an item updates the correct household."""
        fam2 = Family(2, "Miller")
        chest2 = Furniture(2, "household_storage", 12, 12, permit_id=2, family_id=2)
        chest2.inventory = {}
        self.furniture_manager.furnitures.append(chest2)

        # Family 1 starts with 20 Wood
        self.chest.store_item("Wood", 20)

        # Transfer 8 Wood from Family 1 to Family 2
        moved = self.chest.take_item("Wood", 8)
        chest2.store_item("Wood", moved)

        pos1 = get_household_possessions(self.family, self.furniture_manager)
        pos2 = get_household_possessions(fam2, self.furniture_manager)

        self.assertEqual(pos1["Wood"], 12)
        self.assertEqual(pos2["Wood"], 8)

    def test_07_items_with_zero_quantity_disappear(self):
        """7. Items with zero quantity disappear."""
        self.chest.inventory["Potato"] = 5
        self.chest.inventory["Hoe"] = 0
        self.chest.inventory["Water"] = 0

        possessions = get_household_possessions(self.family, self.furniture_manager)
        self.assertIn("Potato", possessions)
        self.assertNotIn("Hoe", possessions)
        self.assertNotIn("Water", possessions)

        # Eat remaining potatoes
        self.chest.take_item("Potato", 5)
        possessions_empty = get_household_possessions(self.family, self.furniture_manager)
        self.assertNotIn("Potato", possessions_empty)
        self.assertEqual(possessions_empty, {})

    def test_08_wip_and_placeholder_entries_never_appear(self):
        """8. WIP and placeholder entries never appear."""
        self.chest.inventory = {"Potato": 115, "Hoe": 3, "Sickle": 3}
        possessions = get_household_possessions(self.family, self.furniture_manager)
        items = sort_possession_items(possessions)
        item_names = [it["name"] for it in items]

        forbidden_wip = [
            "Bread (WIP)",
            "Timber (WIP)",
            "Carved Stone (WIP)",
            "Linen Cloth (WIP)",
            "Copper Coins (WIP)",
            "Bread",
            "Timber",
            "Carved Stone",
            "Linen Cloth"
        ]
        for wip in forbidden_wip:
            self.assertNotIn(wip, item_names)

    def test_09_newly_implemented_item_types_appear_automatically(self):
        """9. Newly implemented item types appear automatically without UI code changes."""
        # Add future items not previously present
        self.chest.inventory["Carrot"] = 15
        self.chest.inventory["Iron_Bar"] = 4

        possessions = get_household_possessions(self.family, self.furniture_manager)
        self.assertIn("Carrot", possessions)
        self.assertEqual(possessions["Carrot"], 15)
        self.assertIn("Iron Bar", possessions)
        self.assertEqual(possessions["Iron Bar"], 4)

        items = sort_possession_items(possessions)
        names = [it["name"] for it in items]
        self.assertIn("Carrot", names)
        self.assertIn("Iron Bar", names)

    def test_10_save_load_preserves_correct_displayed_inventory(self):
        """10. Save/load preserves the correct displayed inventory."""
        self.chest.inventory = {"Potato": 88, "Hoe": 2, "Water": 12, "Copper": 105}
        before_pos = get_household_possessions(self.family, self.furniture_manager)

        from game.systems.day_cycle import DayCycleSystem
        from game.entities.player import Player
        from game.systems.schedule import ScheduleManager

        from game.world.permits import PermitManager
        from game.buildings.buildings import BuildingManager

        day_cycle = DayCycleSystem()
        player = Player(100.0, 100.0)
        schedule_mgr = ScheduleManager()
        pm = PermitManager()
        bm = BuildingManager()

        test_slot = 9
        save_to_slot(
            test_slot,
            day_cycle,
            DEFAULT_RESOURCES,
            player,
            pm,
            bm,
            self.stockpile_manager,
            self.furniture_manager,
            self.villager_manager,
            self.servant_manager,
            schedule_mgr
        )

        # Clear chest in-memory to verify loading restores it
        self.chest.inventory = {}

        ok, msg = load_from_slot(
            test_slot,
            day_cycle,
            DEFAULT_RESOURCES,
            player,
            pm,
            bm,
            self.stockpile_manager,
            self.furniture_manager,
            self.villager_manager,
            self.servant_manager,
            schedule_mgr
        )
        self.assertTrue(ok, msg)

        loaded_fam = self.villager_manager.get_family_by_id(1)
        after_pos = get_household_possessions(loaded_fam, self.furniture_manager)
        self.assertEqual(before_pos, after_pos)
        self.assertEqual(after_pos["Potato"], 88)
        self.assertEqual(after_pos["Hoe"], 2)
        self.assertEqual(after_pos["Water"], 12)
        self.assertEqual(after_pos["Copper"], 105)

        # Clean up test save file
        for p in (f"save_slot_{test_slot}.json", f"saves/save_slot_{test_slot}.json"):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_11_existing_wip_planning_records_remain_intact(self):
        """11. Existing WIP Planning records remain intact in planning registry."""
        all_features = get_all_planning_features()
        feature_names = [f["name"] for f in all_features]

        # Verify key WIP items are still present in persistent planning
        self.assertIn("Household-Owned Market Management", feature_names)
        self.assertIn("Market Assignment", feature_names)
        self.assertIn("Household Production-Based Market Inventory", feature_names)
        self.assertIn("Dynamic Market Pricing", feature_names)
        self.assertIn("Household Taxation", feature_names)

    def test_12_ui_rendering_and_pagination(self):
        """12. UI responsive layout and pagination for 10+ items."""
        # Add 12 items to chest
        for i in range(12):
            self.chest.inventory[f"CustomItem_{i:02d}"] = i + 1

        possessions = get_household_possessions(self.family, self.furniture_manager)
        self.assertEqual(len(possessions), 12)

        items = sort_possession_items(possessions)
        self.assertEqual(len(items), 12)

        ui = RaportUI()
        ui.is_open = True
        ui.active_tab = 4
        ui.selected_family_id = 1
        ui.show_household_possession = True

        screen = pygame.Surface((1280, 720))
        ui.draw(
            screen,
            building_manager=type("BM", (), {"buildings": []})(),
            permit_manager=type("PM", (), {"permits": []})(),
            resources=DEFAULT_RESOURCES,
            villager_manager=self.villager_manager,
            furniture_manager=self.furniture_manager,
            stockpile_manager=self.stockpile_manager,
            servant_manager=self.servant_manager
        )

        # Pagination should be active (12 items > 9 per page)
        self.assertIsNotNone(ui.possession_prev_btn_rect)
        self.assertIsNotNone(ui.possession_next_btn_rect)
        self.assertEqual(ui.possession_page, 0)

        # Click Next
        next_pos = (ui.possession_next_btn_rect.centerx, ui.possession_next_btn_rect.centery)
        ev_next = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': next_pos, 'button': 1})
        ui.handle_event(
            ev_next,
            building_manager=type("BM", (), {"buildings": []})(),
            permit_manager=type("PM", (), {"permits": []})(),
            resources=DEFAULT_RESOURCES,
            villager_manager=self.villager_manager
        )
        self.assertEqual(ui.possession_page, 1)

        # Click Prev
        prev_pos = (ui.possession_prev_btn_rect.centerx, ui.possession_prev_btn_rect.centery)
        ev_prev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'pos': prev_pos, 'button': 1})
        ui.handle_event(
            ev_prev,
            building_manager=type("BM", (), {"buildings": []})(),
            permit_manager=type("PM", (), {"permits": []})(),
            resources=DEFAULT_RESOURCES,
            villager_manager=self.villager_manager
        )
        self.assertEqual(ui.possession_page, 0)


if __name__ == "__main__":
    unittest.main()
