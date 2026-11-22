import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pygame

# Initialize pygame for headless testing
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.data.config import (
    BUILDING_TYPES,
    PERMIT_TYPES,
    get_building_categories,
    get_permit_categories,
    SCHEDULE_PRAYER,
    SCHEDULE_WORK,
    SCHEDULE_SLEEP,
    SCHEDULE_TYPES,
    DAYS_OF_WEEK,
    DEDICATED_JOBS,
)
from game.systems.schedule import ScheduleManager
from game.world.permits import PermitManager, AreaPermit
from game.buildings.building_manager import BuildingManager
from game.ui.ui_raport import RaportUI
from game.ui.market_modal import MarketProfileModal


def test_building_categories():
    """Verify Building Categories return Structure and Furniture as primary categories"""
    cats = get_building_categories()
    cat_ids = [c["id"] for c in cats]
    assert "structure" in cat_ids
    assert "furniture" in cat_ids
    
    structure_cat = next(c for c in cats if c["id"] == "structure")
    assert "wooden_structure" in structure_cat["building_types"]
    assert "stone_structure" in structure_cat["building_types"]

    public_cat = next(c for c in cats if c["id"] == "public_structure")
    assert "well" in public_cat["building_types"]
    assert "market" in public_cat["building_types"]
    assert "toilet" in public_cat["building_types"]


def test_toilet_blueprint_and_permit_free():
    """Verify toilet blueprint footprint is 1x1, costs 5 wood, and requires no permit"""
    toilet = BUILDING_TYPES.get("toilet")
    assert toilet is not None
    assert toilet.get("width_tiles", toilet.get("width", 1)) == 1
    assert toilet.get("height_tiles", toilet.get("height", 1)) == 1
    assert toilet["cost_wood"] == 5
    assert toilet["cost_stone"] == 0
    assert toilet.get("requires_permit") is False or toilet.get("required_permit") is None

    pm = PermitManager()
    assert pm.has_permit_type("toilet") is True


def test_permit_types_include_church_and_cemetery():
    """Verify PERMIT_TYPES contains church and cemetery with correct properties"""
    assert "church" in PERMIT_TYPES
    assert "cemetery" in PERMIT_TYPES
    assert "Church" in PERMIT_TYPES["church"]["name"]
    assert "Cemetery" in PERMIT_TYPES["cemetery"]["name"]

    pm = PermitManager()
    bm = BuildingManager()
    # Add consecrated cemetery lot
    cemetery_lot = pm.add_permit("Cemetery #1", "cemetery", {(10, 10), (10, 11), (11, 10), (11, 11)})
    assert cemetery_lot is not None

    # Normal building on cemetery must be rejected
    match, err = pm.find_matching_permit_for_tiles("wooden_structure", {(10, 10)}, bm)
    assert match is None
    assert "Cemetery" in err

    # Toilet requires no permit, so it matches anywhere outside consecrated areas
    match_toilet, err = pm.find_matching_permit_for_tiles("toilet", {(50, 50)}, bm)
    assert match_toilet is True


def test_schedule_manager_7_days_and_priest_prayer_override():
    """Verify ScheduleManager supports 7 days and Priest prayer time decree"""
    sm = ScheduleManager()
    assert len(DAYS_OF_WEEK) == 7
    assert "Sunday" in DAYS_OF_WEEK
    assert SCHEDULE_PRAYER == "PRAYER"

    # Default prayer block is 03:00 to 04:00 for Priest
    p_start, p_end = sm.get_prayer_hours()
    assert p_start == 3
    assert p_end == 4

    # Hour 3 should be PRAYER for Priest on any day
    act_hour_3 = sm.get_current_activity("Priest", 3, "Wednesday")
    assert act_hour_3 == SCHEDULE_PRAYER

    # Hour 3 should be PRAYER for Priest
    act_hour_3b = sm.get_current_activity("Priest", 3, "Sunday")
    assert act_hour_3b == SCHEDULE_PRAYER

    # Outside prayer time (e.g. hour 9), normal schedule applies
    act_hour_9 = sm.get_current_activity("Priest", 9, "Monday")
    assert act_hour_9 == SCHEDULE_WORK

    # Changing prayer time updates the override window
    sm.set_prayer_time(10, 12)
    assert sm.get_current_activity("Priest", 10, "Monday") == SCHEDULE_PRAYER
    assert sm.get_current_activity("Priest", 12, "Monday") != SCHEDULE_PRAYER

    # Serialization test
    d = sm.to_dict()
    sm2 = ScheduleManager()
    sm2.load_from_dict(d)
    assert sm2.prayer_start_hour == 10
    assert sm2.prayer_end_hour == 12


def test_church_tax_state():
    """Verify RaportUI church tax state and denomination adjustment"""
    ui = RaportUI()
    assert hasattr(ui, "church_tax")
    assert ui.church_tax.get("Copper") == 1
    assert ui.church_tax.get("Silver") == 0
    assert ui.church_tax.get("Gold") == 0

    # Ensure Taxes tab is not WIP
    tax_tab = next(t for t in ui.tabs if t["id"] == "tax")
    assert tax_tab["wip"] is False

    # Ensure Jobs tab replaces Workers
    jobs_tab = next(t for t in ui.tabs if t["id"] == "workers")
    assert jobs_tab["title"] == "Jobs"


def test_market_modal_denomination_pricing():
    """Verify MarketProfileModal supports gold, silver, copper denomination prices"""
    modal = MarketProfileModal()
    
    class FakeMarket:
        def __init__(self):
            self.building_type = "market"
            self.prices = {"Potato": 12}
            self.inventory = {"Potato": 50}
            self.currency = {"Copper": 50, "Silver": 2, "Gold": 0}

    m = FakeMarket()
    modal.open(m)
    assert modal.is_open is True
    assert m.prices["Potato"] == 12

    # Draw once so the typable PRICE field registers its rect, then type 112
    surf = pygame.Surface((1280, 720))
    modal.draw(surf)
    price_key = ("num", "price", "Potato")
    assert price_key in modal.num_fields
    field_rect = modal.num_fields[price_key]["rect"]

    class FakeClick:
        type = pygame.MOUSEBUTTONDOWN
        button = 1
        pos = field_rect.center

    modal.handle_event(FakeClick())
    assert modal.num_input.active
    for ch in "112":
        class FakeKey:
            type = pygame.KEYDOWN
            key = pygame.K_1 if ch == "1" else (pygame.K_2 if ch == "2" else pygame.K_0)
            unicode = ch
        modal.handle_event(FakeKey())

    class FakeEnter:
        type = pygame.KEYDOWN
        key = pygame.K_RETURN
        unicode = ""

    modal.handle_event(FakeEnter())
    assert m.prices["Potato"] == 112

if __name__ == "__main__":
    test_building_categories()
    test_toilet_blueprint_and_permit_free()
    test_permit_types_include_church_and_cemetery()
    test_schedule_manager_7_days_and_priest_prayer_override()
    test_church_tax_state()
    test_market_modal_denomination_pricing()
    print("ALL AGENT 2 TESTS PASSED SUCCESSFULLY!")
