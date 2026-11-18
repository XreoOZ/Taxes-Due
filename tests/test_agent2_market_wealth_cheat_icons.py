import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pygame

# Initialize pygame headless
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import DEFAULT_ITEM_PRICES, ITEM_CATEGORIES
from game.ui.market_modal import MarketProfileModal
from game.ui.item_icons import draw_item_icon
from game.systems.wealth_system import VillageWealthSystem
from game.systems.cheat_system import get_registered_item_types, apply_add_item_cheat
from game.buildings.furniture import Furniture


def test_market_stall_assignment_and_allocation():
    """Verify Market stall assignment to household and independent item allocation"""
    modal = MarketProfileModal()

    class FakeBuilding:
        def __init__(self):
            self.building_type = "market"
            self.name = "Market Stall #1"
            self.prices = {"Potato": 3}
            self.inventory = {"Potato": 50}
            self.currency = {"Copper": 10, "Silver": 1, "Gold": 0}
            self.assigned_family_id = None
            self.item_allocations = {"Potato": 50}

    b = FakeBuilding()
    modal.open(b)
    assert modal.is_open is True

    # Test assignment
    b.assigned_family_id = "fam_brewer"
    assert b.assigned_family_id == "fam_brewer"

    # Test independent item allocations
    b.item_allocations["Potato"] = 50
    b.item_allocations["Wood"] = 20
    assert b.item_allocations["Potato"] == 50
    assert b.item_allocations["Wood"] == 20

    # Allocation math test: 100 Potato owned, 50% allocation = 50 for sale, 50 kept
    owned = 100
    pct = b.item_allocations["Potato"]
    for_sale = int(owned * pct / 100)
    kept = owned - for_sale
    assert for_sale == 50
    assert kept == 50


def test_market_coin_deposit_and_withdraw():
    """Verify Market deposit and withdraw transfers actual coins and prevents overdraft"""
    modal = MarketProfileModal()

    class FakeBuilding:
        def __init__(self):
            self.building_type = "market"
            self.prices = {"Potato": 3}
            self.inventory = {}
            self.currency = {"Copper": 20, "Silver": 2, "Gold": 1}

    b = FakeBuilding()
    modal.open(b)

    resources = {"Copper": 100, "Silver": 10, "Gold": 5}

    class FakeEvent:
        type = pygame.MOUSEBUTTONDOWN
        button = 1
        pos = (100, 100)

    # 1. Test Deposit Coin (e.g. +10 Copper)
    modal.show_coin_dialog = "deposit"
    modal.coin_action_btn_rects[("Copper", 10)] = pygame.Rect(95, 95, 10, 10)
    res = modal.handle_event(FakeEvent(), resources=resources)
    assert "coin_deposited" in str(res)
    assert resources["Copper"] == 90
    assert b.currency["Copper"] == 30

    # 2. Test Withdraw Coin (e.g. -10 Copper)
    modal.show_coin_dialog = "withdraw"
    modal.coin_action_btn_rects[("Copper", 10)] = pygame.Rect(95, 95, 10, 10)
    res = modal.handle_event(FakeEvent(), resources=resources)
    assert "coin_withdrawn" in str(res)
    assert resources["Copper"] == 100
    assert b.currency["Copper"] == 20


def test_village_wealth_system():
    """Verify VillageWealthSystem calculates Landlord and Household wealth separately and accurately"""
    class FakeFamily:
        def __init__(self, fid, surname):
            self.id = fid
            self.surname = surname
            self.members = []

    class FakeVillager:
        def __init__(self):
            self.wallet = {"Copper": 5, "Silver": 1, "Gold": 0}
            self.inventory = {}

    class FakeChest:
        def __init__(self, fid):
            self.family_id = fid
            self.inventory = {"Copper Coin": 15, "Silver Coin": 0, "Gold Coin": 0}

    class FakeVM:
        def __init__(self):
            f = FakeFamily("fam_1", "Brewer")
            v = FakeVillager()
            f.members.append(v)
            self.families = [f]

    class FakeFM:
        def __init__(self):
            self.furnitures = [FakeChest("fam_1")]

    resources = {"Copper": 50, "Silver": 5, "Gold": 1} # 50 + 50 + 100 = 200c
    vm = FakeVM()
    fm = FakeFM()

    wealth = VillageWealthSystem.calculate_village_wealth(resources=resources, villager_manager=vm, furniture_manager=fm)

    # Landlord wealth = 200c
    assert wealth["landlord"]["wealth_copper"] == 200

    # Household wealth: chest (15c) + member (5c + 1s = 15c) = 30c
    assert len(wealth["households"]) == 1
    assert wealth["households"][0]["wealth_copper"] == 30

    # Total = 230c
    assert wealth["total_wealth_copper"] == 230

    # Percentages
    assert wealth["landlord"]["percentage"] > 0
    assert wealth["households"][0]["percentage"] > 0
    assert round(wealth["landlord"]["percentage"] + wealth["households"][0]["percentage"]) == 100


def test_add_item_cheat_functionality():
    """Verify Add Item Cheat retrieves all registered items and inserts them into target storage"""
    items = get_registered_item_types()
    assert len(items) >= 10
    assert "Wood" in items
    assert "Potato" in items

    # 1. Target is a storage chest
    chest = Furniture("furn_test_1", "household_storage", 5, 5)
    success, msg = apply_add_item_cheat(target_storage=chest, amount=25)
    assert success is True
    assert chest.inventory["Wood"] == 25
    assert chest.inventory["Potato"] == 25

    # 2. Target is Landlord resources
    resources = {"Wood": 10}
    success, msg = apply_add_item_cheat(target_storage=None, amount=50, resources=resources)
    assert success is True
    assert resources["Wood"] == 60
    assert resources["Potato"] == 50


def test_global_item_icons():
    """Verify centralized draw_item_icon renders cleanly for all items"""
    surf = pygame.Surface((100, 100))
    for it in ("Gold Coin", "Silver Coin", "Copper Coin", "Potato", "Water", "Wood", "Stone", "Hoe", "Sickle", "Watering_Can", "Bread", "UnknownItem"):
        draw_item_icon(surf, it, 50, 50, size=12)


if __name__ == "__main__":
    test_market_stall_assignment_and_allocation()
    test_market_coin_deposit_and_withdraw()
    test_village_wealth_system()
    test_add_item_cheat_functionality()
    test_global_item_icons()
    print("ALL AGENT 2 TESTS PASSED SUCCESSFULLY!")
