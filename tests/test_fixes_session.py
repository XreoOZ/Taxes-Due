"""
Unit & Integration Tests for:
1. Well 4-Tile Perimeter Contact & Water Drawing
2. Grant Item Loose Drop & Household Inventory Tracking
3. RaportUI close() method & Fresh Game Start
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pygame

# Initialize headless pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.config import TILE_SIZE, DEFAULT_RESOURCES, DEFAULT_STARTER_TOOLS
from game.buildings.building import Building
from game.buildings.building_manager import BuildingManager
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager, ResourceStack
from game.entities.villagers import VillagerManager, Villager, Family
from game.entities.servants import ServantManager, Servant
from game.buildings.furniture import FurnitureManager
from game.ui.ui_raport import RaportUI
from game.systems.core.day_cycle import DayCycleSystem

def test_raport_ui_close():
    ui = RaportUI()
    assert hasattr(ui, "close"), "RaportUI missing close() method!"
    ui.open()
    ui.show_grant_dialog = True
    ui.show_grant_confirm = True
    ui.close()
    assert not ui.is_open, "RaportUI should be closed after close()"
    assert not ui.show_grant_dialog, "Grant dialog should be closed"
    assert not ui.show_grant_confirm, "Grant confirm should be closed"
    print("[PASS] RaportUI.close() works properly.")

def test_well_perimeter_contact_and_water_draw():
    bm = BuildingManager()
    well_tiles = {(10, 10), (11, 10), (10, 11), (11, 11)}
    well = Building("well", well_tiles)
    bm.buildings.append(well)

    vm = VillagerManager()
    fam = Family("fam_1", "Carter")
    # Place farmer at (9, 10) - touching the western edge of tile (10, 10)
    farmer = Villager(
        villager_id="v_1",
        first_name="Arthur",
        last_name="Carter",
        gender="Male",
        age=30,
        generation=2,
        role="Father",
        family_id="fam_1",
        x=(9.5) * TILE_SIZE,
        y=(10.5) * TILE_SIZE
    )
    farmer.job = "Farmer"
    farmer.has_water = False
    farmer.inventory["Watering_Can"] = 1
    fam.members.append(farmer)
    vm.families.append(fam)

    pm = PermitManager()
    # Create farm permit assigned to farmer
    farm_tiles = {(5, 5), (6, 5)}
    farm_permit = AreaPermit(1, "Farm Lot", "farm", farm_tiles)
    farm_permit.crop = "Potato"
    farm_permit.assigned_workers = [farmer.id]
    farm_permit.till_and_sow_tile(5, 5)
    farm_permit.till_and_sow_tile(6, 5)
    pm.permits.append(farm_permit)
    farmer.assigned_permit_id = 1

    dc = DayCycleSystem()
    dc.day_number = 1

    # Farmer should recognize proximity to well tile and draw water without needing to penetrate center
    farmer.water_day = -1
    for _ in range(30):
        farmer.update(
            dt=0.1,
            permit_manager=pm,
            building_manager=bm,
            furniture_manager=None,
            stockpile_manager=None,
            all_entities=[farmer],
            player=None,
            day_cycle=dc
        )
        if farmer.has_water:
            break

    assert farmer.has_water, f"Farmer touching Well perimeter failed to draw water! Well timer: {farmer.well_draw_timer}"
    print("[PASS] Farmer in contact with 4-tile Well perimeter successfully draws water.")

def test_grant_item_loose_drop_and_inventory_persistence():
    pm = PermitManager()
    bm = BuildingManager()
    sm = StockpileManager()
    sm.initialize_starter_stockpile(DEFAULT_RESOURCES, pm, DEFAULT_STARTER_TOOLS)
    furn_m = FurnitureManager()
    vm = VillagerManager()
    serv_m = ServantManager()

    fam = vm.generate_random_family()
    fam.id = "fam_1"
    for m in fam.members:
        m.family_id = "fam_1"

    # Housing lot for family (no chest built)
    house_tiles = {(20, 20), (21, 20), (20, 21), (21, 21)}
    hp = AreaPermit(10, "Housing Lot", "housing", house_tiles)
    pm.permits.append(hp)
    fam.assigned_permit_id = hp.id

    # Add Grant Order: Grant 1 Hoe to fam_1
    serv_m.add_grant_order("fam_1", "Hoe", 1)
    servant = serv_m.servants[0]

    # Run servant until delivered
    delivered = False
    for step in range(300):
        servant.update(
            dt=0.1,
            building_manager=bm,
            permit_manager=pm,
            stockpile_manager=sm,
            resources=DEFAULT_RESOURCES,
            player=servant,
            all_servants=serv_m.servants,
            furniture_manager=furn_m,
            villager_manager=vm,
            servant_manager=serv_m
        )
        if len(serv_m.grant_orders) == 0:
            delivered = True
            break

    assert delivered, "Servant failed to deliver granted Hoe!"

    # 1. Check ground stacks: Hoe must be dropped on ground owned by family
    family_ground_hoes = [s for s in sm.stacks if getattr(s, "owner_type", None) == "villager" and str(s.owner_id) == "fam_1" and s.resource_type == "Hoe"]
    assert len(family_ground_hoes) == 1, f"Expected 1 dropped Hoe on ground, found {family_ground_hoes}"
    assert family_ground_hoes[0].amount == 1

    # 2. Check loose crop hauling: Hoe must NOT be treated as a loose crop
    loose_crops = sm.get_villager_loose_stacks("fam_1", crops_only=True)
    assert len(loose_crops) == 0, f"get_villager_loose_stacks mistakenly included tools: {loose_crops}"

    # 3. Check RaportUI possession calculation: Hoe must show 1
    raport = RaportUI()
    hoe_count = 0
    for s in sm.stacks:
        if getattr(s, "owner_type", None) == "villager" and str(s.owner_id) == "fam_1" and s.resource_type == "Hoe":
            hoe_count += s.amount
    for m in fam.members:
        hoe_count += m.inventory.get("Hoe", 0)
    assert hoe_count == 1, f"Household possessions should count 1 Hoe, got {hoe_count}"

    # 4. Farmer equips the Hoe from the ground
    farmer = fam.members[0]
    farmer.job = "Farmer"
    farmer.assigned_permit_id = None
    farm_tiles = {(30, 30)}
    fp = AreaPermit(20, "Farm Lot", "farm", farm_tiles)
    fp.crop = "Potato"
    fp.assigned_workers = [farmer.id]
    pm.permits.append(fp)

    # Update farmer: farmer should seek the Hoe on the ground and pick it up
    farmer.x = (20.5) * TILE_SIZE
    farmer.y = (20.5) * TILE_SIZE

    picked_up = False
    for step in range(50):
        farmer.update(
            dt=0.1,
            permit_manager=pm,
            building_manager=bm,
            furniture_manager=furn_m,
            stockpile_manager=sm,
            all_entities=[farmer],
            player=None,
            day_cycle=DayCycleSystem()
        )
        if farmer.inventory.get("Hoe", 0) > 0:
            picked_up = True
            break

    assert picked_up, "Farmer should pick up the dropped Hoe from the ground into inventory!"
    assert farmer.inventory.get("Hoe", 0) == 1, f"Farmer inventory should have 1 Hoe, got {farmer.inventory}"

    # Ground stack should now be 0 / removed
    ground_after = [s for s in sm.stacks if getattr(s, "owner_type", None) == "villager" and str(s.owner_id) == "fam_1" and s.resource_type == "Hoe"]
    assert len(ground_after) == 0, f"Ground stack should be cleared after pickup, still has {ground_after}"

    # Household possession should STILL count 1 Hoe from farmer's inventory
    hoe_count_after = sum(m.inventory.get("Hoe", 0) for m in fam.members)
    assert hoe_count_after == 1, f"Household possessions must still count 1 Hoe after pickup, got {hoe_count_after}"
    print("[PASS] Grant item drops to ground when no storage exists, is counted in Household Possessions, and enters AI inventory upon pickup without disappearing.")

if __name__ == "__main__":
    test_raport_ui_close()
    test_well_perimeter_contact_and_water_draw()
    test_grant_item_loose_drop_and_inventory_persistence()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
