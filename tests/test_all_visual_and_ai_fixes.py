import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

from game.config import TILE_SIZE, DEFAULT_RESOURCES
from game.buildings.buildings import Building, BuildingManager, ConstructionSite
from game.world.permits import PermitManager, AreaPermit
from game.entities.villagers import VillagerManager, Villager, Family
from game.entities.servants import ServantManager, Servant
from game.buildings.furniture import FurnitureManager, Furniture
from game.systems.day_cycle import DayCycleSystem
from game.systems.schedule import ScheduleManager
from game.ui.ui_raport import RaportUI
from game.ui.save_modal import SaveLoadModal
from game.ui.settings import SettingsModal


def test_no_unicode_emoji_in_ui():
    """Verify that key UI components contain zero emoji glyphs that would render as tofu boxes [□]."""
    test_files = [
        "game/buildings/buildings.py",
        "game/buildings/furniture.py",
        "game/systems/day_cycle.py",
        "game/ui/settings.py",
        "game/ui/save_modal.py",
        "game/ui/ui_raport.py",
        "main.py"
    ]
    problematic_emojis = ["💧", "🥔", "🛌", "⛏", "🌾", "🏺", "📜", "👥", "🎁", "⚙", "💾", "📂", "⚠️", "👑", "🔨", "🪑"]
    for fpath in test_files:
        with open(fpath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                # Ignore draw_item_icon procedural drawings and comments
                if "def draw_item_icon" in line:
                    continue
                for em in problematic_emojis:
                    if em in line and ("render(" in line or "title_str" in line or "stat_txt" in line or "info_txt" in line):
                        assert False, f"Found emoji '{em}' in font render line at {fpath}:{line_no}: {line.strip()}"
    print("[PASS] Zero emoji glyphs in UI text rendering (no □ tofu boxes).")


def test_farmer_task_dispersion():
    """Verify that multiple farmers pick spatially dispersed, non-adjacent tiles across the farm field."""
    pm = PermitManager()
    vm = VillagerManager()
    dc = DayCycleSystem()

    farm = pm.permits[2]  # Starter Farm Lot (-6, -6, 6x6 = 36 tiles)
    farm.set_crop("potato")

    members = [
        Villager("v1", "A", "S", "Male", 30, 2, "Father", "f1", x=0, y=0),
        Villager("v2", "B", "S", "Female", 28, 2, "Mother", "f1", x=0, y=0),
        Villager("v3", "C", "S", "Male", 20, 3, "Son", "f1", x=0, y=0),
        Villager("v4", "D", "S", "Female", 19, 3, "Daughter", "f1", x=0, y=0),
    ]
    fam = Family("f1", "S", members, assigned_permit_id=farm.id)
    vm.families.append(fam)

    farm.assigned_workers = ["v1", "v2", "v3", "v4"]
    for m in members:
        m.inventory["Hoe"] = 1

    # Simulate 5 ticks
    for _ in range(5):
        vm.update(0.016, pm, None, None, None, day_cycle=dc)

    work_tiles = [m.current_work_tile for m in members]
    assert len(set(work_tiles)) == 4, f"Each worker must have a distinct tile! Got: {work_tiles}"

    # Verify workers are NOT all clustered on immediately adjacent (grid_dist < 1.5) tiles
    for i in range(len(work_tiles)):
        for j in range(i + 1, len(work_tiles)):
            t1 = work_tiles[i]
            t2 = work_tiles[j]
            grid_dist = math.hypot(t1[0] - t2[0], t1[1] - t2[1])
            # Dispersed selection must choose non-adjacent tiles across quadrants when available
            assert grid_dist >= 1.5, f"Workers {i} and {j} picked adjacent tiles: {t1} and {t2} (dist={grid_dist:.2f})"
    print(f"[PASS] 4 Farmers assigned dispersed tiles: {work_tiles}")


def test_sleeping_floor_positions():
    """Verify that family members sleeping on the floor take separate tiles with >= 40px separation."""
    pm = PermitManager()
    vm = VillagerManager()
    dc = DayCycleSystem()
    sm = ScheduleManager()

    house = pm.permits[0]  # Starter Housing Lot
    members = [
        Villager(f"v_{i}", f"Name{i}", "Carter", "Male", 20 + i, 2, "Member", "f1", x=0, y=0)
        for i in range(5)
    ]
    fam = Family("f1", "Carter", members, assigned_permit_id=house.id)
    vm.families.append(fam)

    # Night time
    dc.current_time_seconds = dc.day_length_seconds * (23.0 / 24.0)

    for _ in range(120):
        vm.update(0.016, pm, None, None, None, day_cycle=dc, schedule_manager=sm)

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            dist = math.hypot(members[i].x - members[j].x, members[i].y - members[j].y)
            assert dist >= 40.0, f"Villagers {members[i].id} and {members[j].id} overlap when sleeping! Dist: {dist:.1f}px"
    print("[PASS] Family members sleep on separate tiles without overlapping.")


def test_servant_perimeter_work_positions():
    """Verify that multiple servants work from different perimeter angles around a construction site."""
    site = ConstructionSite("well", {(0, 0), (1, 0), (0, 1), (1, 1)})
    s1 = Servant("servant_1", "Alden", 0, 0)
    s2 = Servant("servant_2", "Barnaby", 0, 0)
    all_s = [s1, s2]

    pos1 = s1._get_site_work_pos(site, all_s)
    pos2 = s2._get_site_work_pos(site, all_s)

    dist = math.hypot(pos1[0] - pos2[0], pos1[1] - pos2[1])
    assert dist >= 64.0, f"Servants work positions are too close! Pos1: {pos1}, Pos2: {pos2}, Dist: {dist:.1f}px"
    print(f"[PASS] Servants work from different angles around site perimeter (Dist: {dist:.1f}px).")


def test_minimum_separation_distance():
    """Verify that circular rigid separation enforces clearance (>= 2*radius + 6.4px) between any entities."""
    vm = VillagerManager()
    v1 = Villager("v1", "A", "C", "Male", 25, 2, "Son", "f1", x=100.0, y=100.0)
    v2 = Villager("v2", "B", "C", "Female", 24, 2, "Daughter", "f1", x=100.1, y=100.1)
    fam = Family("f1", "C", [v1, v2])
    vm.families.append(fam)

    # Force a tick
    vm.update(0.016, PermitManager(), None, None, None)

    dist = math.hypot(v1.x - v2.x, v1.y - v2.y)
    min_required = v1.radius + v2.radius + 6.4
    assert dist >= min_required - 0.1, f"Separation failed: dist={dist:.2f}px < min_required={min_required:.2f}px"
    print(f"[PASS] Physical separation enforced: dist={dist:.2f}px >= min_required={min_required:.2f}px")


if __name__ == "__main__":
    test_no_unicode_emoji_in_ui()
    test_farmer_task_dispersion()
    test_sleeping_floor_positions()
    test_servant_perimeter_work_positions()
    test_minimum_separation_distance()
    print("\nALL VISUAL AND AI VERIFICATION TESTS PASSED SUCCESSFULLY!")
