"""Unit tests verifying that chestless households drop goods/tithes on their home tiles
and that Woodsman, Miner, and Priest continue working without deadlock across multiple days.
"""
import os
import unittest
import math

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
pygame.init()

from game.entities.villagers import Villager
from game.buildings.furniture import Furniture, FurnitureManager
from game.buildings.building_manager import BuildingManager
from game.world.permits import PermitManager, AreaPermit
from game.world.stockpile import StockpileManager
from game.world.natural_resources import get_natural_resources
from game.systems.work.station_jobs import StationJobSystem
from game.systems.village_life.church_system import ChurchSystem
from game.systems.village_life.confession_system import ConfessionSystem
from game.data.config import TILE_SIZE


class FakeDayCycle:
    def __init__(self, hour=10.0, day_number=1):
        self.day_length_seconds = 1200.0
        self.day_number = day_number
        self.current_hour = hour

    def get_time_ratio(self):
        return self.current_hour / 24.0


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
    def __init__(self, fid, members, assigned_permit_id="lot1"):
        self.id = fid
        self.members = list(members)
        self.currency = {}
        self.assigned_permit_id = assigned_permit_id

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


class FakeScheduleManager:
    def get_prayer_hours(self):
        return (12.0, 13.0)

    def get_scheduled_activity(self, job, hour):
        return "WORK"

    def get_current_activity(self, job, hour):
        return "WORK"


class TestChestlessJobsAndPriest(unittest.TestCase):
    def setUp(self):
        self.nr = get_natural_resources()
        self.nr.reset()
        self.building_mgr = BuildingManager()
        self.permit_mgr = PermitManager()
        self.permit_mgr.permits.clear()
        self.furniture_mgr = FurnitureManager()
        self.stockpile_mgr = StockpileManager()
        self.schedule_mgr = FakeScheduleManager()

    def test_chestless_woodsman_delivers_to_ground_and_works_next_day(self):
        """Woodsman without a chest deposits output to home lot ground and resumes working next day."""
        # 1. Home permit for fam1 (no chest inside)
        home_permit = self.permit_mgr.add_permit("Home Lot", "residence", {(2, 2), (2, 3), (3, 2), (3, 3)})

        v = Villager("w1", "Woody", "Wood", "male", 30, 1, "Woodsman", family_id="fam1", x=200.0, y=200.0)
        v.assigned_permit_id = home_permit.id
        v.inventory = {"Felling_Axe": 1, "Spade": 1}

        # 2. Woodsman lodge
        lodge = Furniture("lodge1", "woodsman_lodge", 15, 15)
        lodge.assigned_workers = [v.id]
        lodge.station_quota_daily = 10
        lodge.station_quota_today = 10  # quota exhausted
        lodge.station_quota_day = 1
        self.furniture_mgr.furnitures = [lodge]

        fam = FakeFamily("fam1", [v], assigned_permit_id=home_permit.id)
        vm = FakeVillagerManager([fam])
        entities = FakeEntities([v])
        dc = FakeDayCycle(10.0, day_number=1)

        # Give Woodsman carried Wood to simulate harvest delivery home (quota met)
        v.inventory["Wood"] = 5

        # Update: Woodsman should deliver to home ground because chest is None
        # Move him to destination
        dest_x, dest_y = v._get_home_storage_dest(self.permit_mgr, self.building_mgr, self.furniture_mgr, all_entities=entities)
        v.x, v.y = dest_x, dest_y

        res = StationJobSystem.update(
            v, 0.5, "Woodsman", self.building_mgr, self.furniture_mgr,
            vm, entities, None, dc,
            stockpile_manager=self.stockpile_mgr, permit_manager=self.permit_mgr
        )
        self.assertTrue(res)

        # Output should be dropped onto home lot as loose stack
        home_stacks = [s for s in self.stockpile_mgr.stacks if str(s.owner_id) == "fam1" and s.resource_type == "Wood"]
        self.assertGreater(len(home_stacks), 0)
        self.assertEqual(sum(s.amount for s in home_stacks), 5)
        self.assertEqual(v.inventory.get("Wood", 0), 0)

        # Day 2: Quota resets, woodsman is NOT stuck in station_carry and can work
        dc.day_number = 2
        # Set up a mature tree
        self.nr.forest_tiles.add((16, 16))
        self.nr.trees[(16, 16)] = {"state": "mature", "planted_day": 0.0}
        self.nr._recount_trees()

        has_work = StationJobSystem.has_work(v, "Woodsman", self.furniture_mgr, dc)
        self.assertTrue(has_work, "Woodsman must have work on Day 2")

    def test_chestless_miner_delivers_leftovers_to_ground(self):
        """Miner without a chest hauls workstation leftovers to home ground without freezing."""
        home_permit = self.permit_mgr.add_permit("Home Lot", "residence", {(2, 2), (2, 3), (3, 2), (3, 3)})

        v = Villager("m1", "Minnie", "Ore", "female", 28, 1, "Miner", family_id="fam1", x=200.0, y=200.0)
        v.assigned_permit_id = home_permit.id
        v.inventory = {"Pickaxe": 1, "Sledgehammer": 1}

        # Miner workstation bound to mine
        mine_tiles = {(10 + dx, 10 + dy) for dx in range(5) for dy in range(5)}
        mine = {"id": "mine_1", "kind": "Stone Mine", "anchor": (10, 10), "tier": 3, "tiles": mine_tiles}
        self.nr.mines.append(mine)

        station = Furniture("mws1", "miner_workstation", 10, 10)
        station.bound_mine_id = "mine_1"
        station.assigned_workers = [v.id]
        station.station_quota_daily = 5
        station.station_quota_today = 5  # quota reached
        station.station_quota_day = 1
        station.inventory["Stone"] = 8   # leftovers in station
        self.furniture_mgr.furnitures = [station]

        fam = FakeFamily("fam1", [v], assigned_permit_id=home_permit.id)
        vm = FakeVillagerManager([fam])
        entities = FakeEntities([v])
        dc = FakeDayCycle(14.0, day_number=1)

        # 1. Fetch leftovers from station
        dest_station = StationJobSystem.station_point(station, v, entities, self.building_mgr)
        v.x, v.y = dest_station[0], dest_station[1]
        res = StationJobSystem.update(
            v, 0.5, "Miner", self.building_mgr, self.furniture_mgr,
            vm, entities, None, dc,
            stockpile_manager=self.stockpile_mgr, permit_manager=self.permit_mgr
        )
        self.assertTrue(res)
        self.assertIn("Stone", getattr(v, "station_carry", {}))

        # 2. Deliver leftovers home (chestless)
        dest_x, dest_y = v._get_home_storage_dest(self.permit_mgr, self.building_mgr, self.furniture_mgr, all_entities=entities)
        v.x, v.y = dest_x, dest_y
        res2 = StationJobSystem.update(
            v, 0.5, "Miner", self.building_mgr, self.furniture_mgr,
            vm, entities, None, dc,
            stockpile_manager=self.stockpile_mgr, permit_manager=self.permit_mgr
        )
        self.assertTrue(res2)
        self.assertEqual(getattr(v, "station_carry", {}), {})

        # Verify stone dropped on home lot
        stone_stacks = [s for s in self.stockpile_mgr.stacks if str(s.owner_id) == "fam1" and s.resource_type == "Stone"]
        self.assertGreater(len(stone_stacks), 0)

        # Day 2: Miner has work on Day 2
        dc.day_number = 2
        has_work = StationJobSystem.has_work(v, "Miner", self.furniture_mgr, dc)
        self.assertTrue(has_work, "Miner must have work on Day 2")

    def test_priest_work_schedule_has_work_and_preaches(self):
        """Priest does not get forced into LEISURE during WORK schedule when Church exists."""
        church_p = self.permit_mgr.add_permit("Church Lot", "church", {(20, 20), (20, 21), (21, 20), (21, 21)})
        church_p.assigned_workers = ["p1"]

        priest = Villager("p1", "Father", "Benedict", "male", 45, 1, "Priest", family_id="fam_church", x=20 * TILE_SIZE, y=20 * TILE_SIZE)
        priest.assigned_permit_id = church_p.id

        fam = FakeFamily("fam_church", [priest], assigned_permit_id=church_p.id)
        vm = FakeVillagerManager([fam])
        entities = FakeEntities([priest])
        dc = FakeDayCycle(10.0, day_number=1)  # 10:00 AM (WORK schedule)

        # Update priest during WORK
        priest.update(
            0.5, self.permit_mgr, self.building_mgr, entities, None,
            stockpile_manager=self.stockpile_mgr, furniture_manager=self.furniture_mgr,
            day_cycle=dc, schedule_manager=self.schedule_mgr, villager_manager=vm
        )

        # Priest should NOT be forced into LEISURE; task should be PREACHING or moving toward church
        self.assertNotEqual(priest.task, "LEISURE")
        self.assertIn(priest.task, ("PREACHING", "IDLE"))

    def test_chestless_priest_deposits_tithes_home_to_ground(self):
        """Priest without a chest deposits collected tithes to home ground."""
        home_permit = self.permit_mgr.add_permit("Priest Lot", "residence", {(5, 5), (5, 6), (6, 5), (6, 6)})

        priest = Villager("p1", "Father", "Benedict", "male", 45, 1, "Priest", family_id="fam_church", x=50.0, y=50.0)
        priest.assigned_permit_id = home_permit.id
        priest.inventory = {"Copper": 12}

        fam = FakeFamily("fam_church", [priest], assigned_permit_id=home_permit.id)
        vm = FakeVillagerManager([fam])

        # Deposit tithes home
        deposited = ChurchSystem.priest_deposit_tithes_home(
            priest, self.furniture_mgr,
            stockpile_manager=self.stockpile_mgr,
            permit_manager=self.permit_mgr,
            building_manager=self.building_mgr,
        )
        self.assertEqual(deposited, 12)
        self.assertEqual(priest.inventory.get("Copper", 0), 0)

        # Check dropped coins on ground
        from game.systems.economy.currency import to_copper
        coin_stacks = [s for s in self.stockpile_mgr.stacks if str(s.owner_id) == "fam_church"]
        self.assertGreater(len(coin_stacks), 0)
        total_copper = to_copper({s.resource_type: s.amount for s in coin_stacks})
        self.assertEqual(total_copper, 12)

    def test_chestless_villager_deposits_unneeded_inventory_to_ground(self):
        """Villager with unneeded items deposits them to home ground before sleep."""
        home_permit = self.permit_mgr.add_permit("Home Lot", "residence", {(4, 4), (4, 5)})
        v = Villager("v1", "John", "Doe", "male", 25, 1, "Farmer", family_id="fam1", x=40.0, y=40.0)
        v.assigned_permit_id = home_permit.id
        # Extra wood and stone in inventory (not required for Farmer)
        v.inventory = {"Wood": 3, "Stone": 2, "Hoe": 1}

        fam = FakeFamily("fam1", [v], assigned_permit_id=home_permit.id)
        entities = FakeEntities([v])

        # Move to home storage dest
        dest_x, dest_y = v._get_home_storage_dest(self.permit_mgr, self.building_mgr, self.furniture_mgr, all_entities=entities)
        v.x, v.y = dest_x, dest_y

        res = v._deposit_unneeded_inventory(
            0.5, self.furniture_mgr, entities, None, self.building_mgr,
            stockpile_manager=self.stockpile_mgr, permit_manager=self.permit_mgr
        )
        self.assertTrue(res)
        self.assertEqual(v.inventory.get("Wood", 0), 0)
        self.assertEqual(v.inventory.get("Stone", 0), 0)
        self.assertEqual(v.inventory.get("Hoe", 0), 1)  # Required tool kept!

        # Check dropped stacks on ground
        wood_stacks = [s for s in self.stockpile_mgr.stacks if str(s.owner_id) == "fam1" and s.resource_type == "Wood"]
        stone_stacks = [s for s in self.stockpile_mgr.stacks if str(s.owner_id) == "fam1" and s.resource_type == "Stone"]
        self.assertGreater(len(wood_stacks), 0)
        self.assertGreater(len(stone_stacks), 0)

    def test_null_permit_manager_safety(self):
        """_get_home_building and _get_home_storage_dest handle permit_manager=None safely without raising AttributeError."""
        v = Villager("v1", "John", "Doe", "male", 25, 1, "Farmer", family_id="fam1", x=100.0, y=100.0)
        v.assigned_permit_id = "lot_nonexistent"
        self.assertIsNone(v._get_home_building(None, self.building_mgr))
        dest = v._get_home_storage_dest(None, self.building_mgr, None)
        self.assertEqual(dest, (100.0, 100.0))


if __name__ == "__main__":
    unittest.main()
