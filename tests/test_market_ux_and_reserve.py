import os
import unittest
import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from game.buildings.building import Building
from game.buildings.furniture import Furniture, FurnitureManager
from game.data.config import (
    DEFAULT_ITEM_PRICES,
    DAILY_FOOD_REQUIREMENT,
    DAILY_WATER_REQUIREMENT,
    HOUSEHOLD_STALL_FOOD_RESERVE_DAYS,
    HOUSEHOLD_STALL_WATER_RESERVE_DAYS,
    MARKET_LORD_COMMON_GOODS,
)
from game.entities.villagers import Family, Villager, VillagerManager
from game.systems.economy.household_stall_system import HouseholdStallSystem
from game.ui.modals.market_modal import MarketProfileModal


class TestMarketUXAndReserve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.font.init()

    def setUp(self):
        self.fm = FurnitureManager()
        self.vm = VillagerManager()
        self.fam = Family("fam_1", "Miller")
        self.farmer = Villager("v1", "Alden", "Miller", "Male", 28, 2, "Father", family_id="fam_1")
        self.farmer.set_job("Farmer")
        self.farmer.inventory = {}  # Missing Hoe & Sickle in pocket
        self.spouse = Villager("v2", "Clara", "Miller", "Female", 26, 2, "Mother", family_id="fam_1")
        self.fam.members = [self.farmer, self.spouse]
        self.vm.families = [self.fam]

        self.chest = Furniture("chest_1", "household_storage", 3, 3, permit_id="p1", family_id="fam_1")
        self.fm.furnitures.append(self.chest)
        self.market = Building("market", {(10, 10), (10, 11)}, door_pos=(10, 12))

    def test_food_water_and_tool_reserves_protect_household_needs(self):
        food_reserve = 2 * DAILY_FOOD_REQUIREMENT * HOUSEHOLD_STALL_FOOD_RESERVE_DAYS
        water_reserve = 2 * DAILY_WATER_REQUIREMENT * HOUSEHOLD_STALL_WATER_RESERVE_DAYS
        self.chest.inventory = {
            "Potato": food_reserve,          # Exactly at reserve -> 0 sellable
            "Water": water_reserve + 5,      # 5 surplus
            "Hoe": 1,                        # Farmer needs 1 Hoe -> 0 sellable
            "Sickle": 2,                     # Farmer needs 1 -> 1 surplus
            "Wood": 10,                      # No reserve -> 10 surplus
        }

        HouseholdStallSystem.assign_stall(self.market, "fam_1")
        for item in ("Potato", "Water", "Hoe", "Sickle", "Wood"):
            HouseholdStallSystem.set_item_allocation(self.market, item, 100)

        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                self.market, "fam_1", "Potato", self.fm, villager_manager=self.vm
            ),
            0,
        )
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                self.market, "fam_1", "Water", self.fm, villager_manager=self.vm
            ),
            5,
        )
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                self.market, "fam_1", "Hoe", self.fm, villager_manager=self.vm
            ),
            0,
        )
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                self.market, "fam_1", "Sickle", self.fm, villager_manager=self.vm
            ),
            1,
        )
        self.assertEqual(
            HouseholdStallSystem.calculate_allocatable_goods(
                self.market, "fam_1", "Wood", self.fm, villager_manager=self.vm
            ),
            10,
        )

    def test_auto_list_surplus_excludes_tools_and_zero_surplus_food(self):
        food_reserve = 2 * DAILY_FOOD_REQUIREMENT * HOUSEHOLD_STALL_FOOD_RESERVE_DAYS
        self.chest.inventory = {
            "Potato": food_reserve,  # Only reserve, no surplus yet
            "Wood": 12,              # Surplus
            "Sickle": 3,             # Tool -> never auto-listed
        }
        HouseholdStallSystem.assign_stall(self.market, "fam_1")
        added = HouseholdStallSystem.auto_list_surplus_items(
            self.market, self.fm, villager_manager=self.vm
        )
        self.assertEqual(added, ["Wood"])
        self.assertEqual(self.market.sale_items, ["Wood"])

        # Once harvest grows past reserve, Auto-List picks up Potato too, still skipping tools
        self.chest.inventory["Potato"] = food_reserve + 6
        added_after = HouseholdStallSystem.auto_list_surplus_items(
            self.market, self.fm, villager_manager=self.vm
        )
        self.assertEqual(added_after, ["Potato"])
        self.assertNotIn("Sickle", self.market.sale_items)

    def test_modal_lord_steppers_quick_add_and_pagination(self):
        modal = MarketProfileModal()
        modal.open(self.market)
        surf = pygame.Surface((1280, 720))

        # Empty state -> Quick Add Common Goods
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        self.assertIsNotNone(modal.quick_add_common_rect)
        ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.quick_add_common_rect.center})
        res = modal.handle_event(ev, villager_manager=self.vm, furniture_manager=self.fm)
        self.assertEqual(res, "market_quick_added_common")
        for item in MARKET_LORD_COMMON_GOODS:
            self.assertIn(item, self.market.sale_items)

        # Price stepper + Base reset
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        inc_rect = modal.price_step_btns[("Potato", 1)]
        base_price = DEFAULT_ITEM_PRICES["Potato"]
        modal.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": inc_rect.center}))
        self.assertEqual(self.market.prices["Potato"], base_price + 1)

        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        self.assertIn("Potato", modal.price_auto_btns)
        modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.price_auto_btns["Potato"].center}
        ))
        self.assertEqual(self.market.prices["Potato"], base_price)

        # Add 5th item -> page 2 reachable via Next >
        self.market.sale_items.append("Iron Bar")
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.page_next_rect.center}
        ))
        self.assertEqual(modal.goods_page, 1)
        modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.page_prev_rect.center}
        ))
        self.assertEqual(modal.goods_page, 0)

    def test_modal_assign_auto_lists_and_alloc_stepper_and_quick_unassign(self):
        self.chest.inventory = {"Potato": 50, "Wood": 10, "Hoe": 2}
        modal = MarketProfileModal()
        modal.open(self.market)
        surf = pygame.Surface((1280, 720))

        # Open assign dialog & assign family -> auto-lists non-tool surplus
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.assign_stall_btn_rect.center}
        ), villager_manager=self.vm, furniture_manager=self.fm)
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        fam_btn = modal.family_assign_btn_rects["fam_1"]
        res = modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": fam_btn.center}
        ), villager_manager=self.vm, furniture_manager=self.fm)
        self.assertEqual(res, "stall_assigned_fam_1")
        self.assertIn("Potato", self.market.sale_items)
        self.assertIn("Wood", self.market.sale_items)
        self.assertNotIn("Hoe", self.market.sale_items)

        # Full Free Market: assigned stall uses 100% surplus automatically (no percentage stepper)
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        self.assertEqual(HouseholdStallSystem.get_item_allocation(self.market, "Potato"), 100)
        self.assertEqual(modal.alloc_step_btns, {})

        # Quick Unassign button reverts to Lord Stall
        modal.draw(surf, villager_manager=self.vm, furniture_manager=self.fm)
        self.assertIsNotNone(modal.quick_unassign_btn_rect)
        res_un = modal.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": modal.quick_unassign_btn_rect.center}
        ), villager_manager=self.vm, furniture_manager=self.fm)
        self.assertEqual(res_un, "stall_unassigned")
        self.assertIsNone(self.market.assigned_family_id)


if __name__ == "__main__":
    unittest.main()
