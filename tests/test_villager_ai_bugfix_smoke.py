"""Headless smoke tests for the three villager-AI bugfixes.

Run: SDL_VIDEODRIVER=dummy python -m pytest tests/test_villager_ai_bugfix_smoke.py -x -q
(or plain python — unittest-style asserts, no pytest required)
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
import types

import pygame
pygame.init()

from game.entities.villagers import Villager
from game.buildings.furniture import Furniture, FurnitureManager
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.systems.work.station_jobs import StationJobSystem
from game.world.natural_resources import get_natural_resources, TREE_STATE_MATURE


# ---------------------------------------------------------------------------
# Minimal fakes
# ---------------------------------------------------------------------------
class FakeDayCycle:
    def __init__(self, hour=10.0):
        self.day_length_seconds = 1200.0
        self.day_number = 1
        self.current_hour = hour

    def get_time_ratio(self):
        return self.current_hour / 24.0


class FakePermitManager:
    def __init__(self):
        self.permits = []


class FakeBuildingManager:
    def __init__(self):
        self.buildings = []
        self.construction_sites = []

    def get_building_at(self, *a, **k):
        return None

    def find_path(self, *a, **k):
        return []


class FakeEntities:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def by_id(self, eid):
        return next((e for e in self._items if str(getattr(e, "id", "")) == str(eid)), None)

    def by_family(self, fid):
        return [e for e in self._items if str(getattr(e, "family_id", "")) == str(fid)]

    def for_tiles(self, tiles):
        return self._items


class FakeFamily:
    def __init__(self, fid, members):
        self.id = fid
        self.members = list(members)
        self.currency = {}
        self.assigned_permit_id = None

    @property
    def living_members(self):
        return [m for m in self.members if getattr(m, "is_alive", True)]

    def get_available_recovery_representative(self):
        living = self.living_members
        return living[0] if living else None


class FakeVillagerManager:
    def __init__(self, families):
        self.families = list(families)

    def get_all_villagers(self):
        return [m for f in self.families for m in f.members]

    def get_family_by_id(self, fid):
        return next((f for f in self.families if str(f.id) == str(fid)), None)

    def invalidate_villager_cache(self):
        pass


def make_villager(vid, role, fam_id, x, y):
    return Villager(vid, "Test", "Subject", "male", 30, 1, role,
                    family_id=fam_id, x=x, y=y)


def make_world(role="Toolmaker", hour=10.0):
    """Villager + furniture manager with a family chest and a work station."""
    v = make_villager("v1", role, "fam1", 200.0, 200.0)
    fm = FurnitureManager()
    chest = Furniture("chest1", "household_storage", 8, 8,
                      family_id="fam1", permit_id="lot1")
    bench = Furniture("bench1", "toolmaker_workbench", 9, 8,
                      family_id="fam1", permit_id="lot1")
    fm.furnitures.extend([chest, bench])
    fam = FakeFamily("fam1", [v])
    vm = FakeVillagerManager([fam])
    bm = FakeBuildingManager()
    pm = FakePermitManager()
    entities = FakeEntities([v])
    dc = FakeDayCycle(hour)
    return v, fm, chest, bench, vm, bm, pm, entities, dc


def run_ticks(v, n, dt, pm, bm, entities, fm, dc, vm):
    for _ in range(n):
        v.update(dt, pm, bm, entities, None,
                 stockpile_manager=None, furniture_manager=fm,
                 day_cycle=dc, schedule_manager=None, villager_manager=vm)


# ---------------------------------------------------------------------------
# TEST 1 — BUG A: toolmaker claims & progresses a paid tool order
# ---------------------------------------------------------------------------
def test_toolmaker_progresses_tool_order():
    v, fm, chest, bench, vm, bm, pm, entities, dc = make_world("Toolmaker", hour=10.0)
    chest.store_item("Wood", 60)
    chest.store_item("Iron Ore", 60)

    subject, err = ToolmakerSystem.create_tool_order(
        bench, "Hammer", 1, payer_family_id="fam1",
        building_manager=bm, villager_manager=vm)
    assert subject is not None and err is None
    order = subject.construction_order

    # Position the toolmaker next to the bench approach tile so crafting starts.
    v.x, v.y = bench.get_world_pos()[0] - 40.0, bench.get_world_pos()[1]

    run_ticks(v, 1400, 0.25, pm, bm, entities, fm, dc, vm)

    status = order.get("status")
    qty_done = int(order.get("qty_done", 0))
    print(f"[BUG-A] final order status={status} qty_done={qty_done} "
          f"task={v.task} bars={chest.inventory.get('Iron Bar', 0)} "
          f"hammer_in_chest={chest.inventory.get('Hammer', 0)}")
    assert status in ("PAID", "CRAFTING", "AWAITING_MATERIAL", "DELIVERING", "COMPLETE"), \
        f"order never left payment queue: {status}"
    assert status != "AWAITING_PAYMENT"
    # The pipeline must actually progress: smelted bars and/or forged units.
    bars = chest.inventory.get("Iron Bar", 0)
    assert qty_done >= 1 or bars > 0 or status in ("DELIVERING", "COMPLETE"), \
        "toolmaker claimed but never smelted/forged anything"


# ---------------------------------------------------------------------------
# TEST 2 — BUG B: tool-less woodsman cannot fell trees
# ---------------------------------------------------------------------------
def test_toolless_woodsman_cannot_work():
    v, fm, chest, bench, vm, bm, pm, entities, dc = make_world("Woodsman", hour=10.0)
    # Replace bench with a woodsman lodge assigned to the villager.
    fm.furnitures = [f for f in fm.furnitures if f.furniture_type != "toolmaker_workbench"]
    lodge = Furniture("lodge1", "woodsman_lodge", 20, 20)
    lodge.assigned_workers = [v.id]
    lodge.station_quota_daily = 10
    fm.furnitures.append(lodge)

    # Seed a mature tree.
    nr = get_natural_resources()
    nr.trees[(30, 30)] = {"state": TREE_STATE_MATURE, "planted_day": 0.0}
    nr._recount_trees()
    nr._build_tree_index()

    # Bare-handed: production must be refused.
    v.inventory = {}
    res = StationJobSystem.update(v, 0.5, "Woodsman", bm, fm, vm, entities, None, dc)
    print(f"[BUG-B] tool-less update -> {res}, task={v.task}, wood={v.inventory.get('Wood', 0)}")
    assert res is False
    assert v.task != "STATION_WORK"
    assert v.inventory.get("Wood", 0) == 0

    # Control: same setup WITH tools -> production proceeds.
    v2, fm2, chest2, _, vm2, bm2, pm2, entities2, dc2 = make_world("Woodsman", hour=10.0)
    fm2.furnitures = [f for f in fm2.furnitures if f.furniture_type != "toolmaker_workbench"]
    lodge2 = Furniture("lodge2", "woodsman_lodge", 20, 20)
    lodge2.assigned_workers = [v2.id]
    lodge2.station_quota_daily = 10
    fm2.furnitures.append(lodge2)
    v2.inventory = {"Felling_Axe": 1, "Spade": 1}
    res2 = StationJobSystem.update(v2, 0.5, "Woodsman", bm2, fm2, vm2, entities2, None, dc2)
    print(f"[BUG-B] tool-ful update -> {res2}, task={v2.task}")
    assert res2 is True


# ---------------------------------------------------------------------------
# TEST 3 — BUG C: lethal hunger overrides WORK; sleep untouched
# ---------------------------------------------------------------------------
def test_lethal_hunger_overrides_work():
    v, fm, chest, bench, vm, bm, pm, entities, dc = make_world("Woodsman", hour=10.0)
    fm.furnitures = [f for f in fm.furnitures if f.furniture_type != "toolmaker_workbench"]
    lodge = Furniture("lodge1", "woodsman_lodge", 20, 20)
    lodge.assigned_workers = [v.id]
    lodge.station_quota_daily = 10
    fm.furnitures.append(lodge)
    nr = get_natural_resources()
    nr.trees[(30, 30)] = {"state": TREE_STATE_MATURE, "planted_day": 0.0}
    nr._recount_trees()
    nr._build_tree_index()

    v.inventory = {"Felling_Axe": 1, "Spade": 1, "Potato": 1}
    v.hunger = 5.0    # ~1.2 in-game hours to 0% -> inside the 2h lethal window
    v.thirst = 100.0
    v.need_toilet = 100.0

    run_ticks(v, 3, 0.5, pm, bm, entities, fm, dc, vm)
    print(f"[BUG-C] lethal: hunger={v.hunger:.1f} task={v.task} sched={v.current_schedule_activity}")
    assert v.hunger > 50.0, "lethal-hunger villager did not eat during WORK slot"

    # Control: same villager, hunger merely low-but-safe -> keeps working.
    v2, fm2, chest2, _, vm2, bm2, pm2, entities2, dc2 = make_world("Woodsman", hour=10.0)
    fm2.furnitures = [f for f in fm2.furnitures if f.furniture_type != "toolmaker_workbench"]
    lodge2 = Furniture("lodge2", "woodsman_lodge", 20, 20)
    lodge2.assigned_workers = [v2.id]
    lodge2.station_quota_daily = 10
    fm2.furnitures.append(lodge2)
    v2.inventory = {"Felling_Axe": 1, "Spade": 1, "Potato": 1}
    v2.hunger = 30.0   # ~7.2h to 0% -> outside lethal window, above crit 20
    v2.thirst = 100.0
    v2.need_toilet = 100.0
    run_ticks(v2, 3, 0.5, pm2, bm2, entities2, fm2, dc2, vm2)
    print(f"[BUG-C] safe: hunger={v2.hunger:.1f} task={v2.task}")
    assert v2.hunger < 35.0, "non-lethal villager wrongly abandoned work to eat"

    # Sleep must not be broken: lethal hunger during SLEEP slot stays asleep.
    v3, fm3, chest3, _, vm3, bm3, pm3, entities3, dc3 = make_world("Woodsman", hour=23.0)
    v3.inventory = {"Felling_Axe": 1, "Spade": 1, "Potato": 1}
    v3.hunger = 5.0
    v3.thirst = 100.0
    v3.need_toilet = 100.0
    run_ticks(v3, 3, 0.5, pm3, bm3, entities3, fm3, dc3, vm3)
    print(f"[BUG-C] sleep: hunger={v3.hunger:.1f} task={v3.task}")
    assert v3.task != "SEEKING_FOOD", "lethal override broke the sleep schedule"


if __name__ == "__main__":
    test_toolmaker_progresses_tool_order()
    test_toolless_woodsman_cannot_work()
    test_lethal_hunger_overrides_work()
    print("ALL SMOKE TESTS PASSED")
