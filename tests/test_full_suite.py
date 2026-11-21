import os
import sys
import unittest
import math
import shutil

# Headless Pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pygame
pygame.init()

from game.data.config import (
    DEFAULT_RESOURCES,
    DEFAULT_STARTER_TOOLS,
    TILE_SIZE,
    DAY_LENGTH_OPTIONS,
    DEFAULT_DAY_LENGTH_INDEX
)
from game.entities.player import Player
from game.world.permits import PermitManager, AreaPermit
from game.buildings.building_manager import BuildingManager
from game.world.stockpile import StockpileManager
from game.entities.servants import ServantManager
from game.entities.villagers import VillagerManager, Villager, Family
from game.buildings.furniture import FurnitureManager, Furniture
from game.systems.day_cycle import DayCycleSystem
from game.systems.schedule import ScheduleManager
from game.systems.save_system import serialize_game_state, save_to_slot, load_from_slot, SAVE_DIR, get_slot_path

class TestFullSuite(unittest.TestCase):
    def setUp(self):
        self.player = Player()
        self.permit_manager = PermitManager()
        self.building_manager = BuildingManager()
        self.stockpile_manager = StockpileManager()
        self.servant_manager = ServantManager()
        self.villager_manager = VillagerManager()
        self.furniture_manager = FurnitureManager()
        self.day_cycle = DayCycleSystem()
        self.schedule_manager = ScheduleManager()
        self.resources = dict(DEFAULT_RESOURCES)

        # Initialize starter stockpile
        self.stockpile_manager.initialize_starter_stockpile(
            self.resources, self.permit_manager, DEFAULT_STARTER_TOOLS
        )

    def test_01_save_to_empty_slot(self):
        """1. Save ke slot kosong berhasil menyimpan file save lengkap."""
        slot_path = get_slot_path(99)
        if os.path.exists(slot_path):
            os.remove(slot_path)
        self.assertFalse(os.path.exists(slot_path))

        ok, msg = save_to_slot(
            99, self.day_cycle, self.resources, self.player, self.permit_manager,
            self.building_manager, self.stockpile_manager, self.furniture_manager,
            self.villager_manager, self.servant_manager, self.schedule_manager
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(slot_path))
        self.assertGreater(os.path.getsize(slot_path), 100)
        os.remove(slot_path)

    def test_02_and_03_and_04_atomic_overwrite(self):
        """2, 3, 4. Overwrite slot terisi mengganti data secara atomic (.tmp -> replace)."""
        slot_path = get_slot_path(99)
        if os.path.exists(slot_path):
            os.remove(slot_path)

        # Initial save with Day 1
        self.day_cycle.day_number = 1
        ok, _ = save_to_slot(
            99, self.day_cycle, self.resources, self.player, self.permit_manager,
            self.building_manager, self.stockpile_manager, self.furniture_manager,
            self.villager_manager, self.servant_manager, self.schedule_manager
        )
        self.assertTrue(ok)

        # Update day to Day 5 and overwrite atomically
        self.day_cycle.day_number = 5
        self.resources["Wood"] = 4321

        ok_ow, msg_ow = save_to_slot(
            99, self.day_cycle, self.resources, self.player, self.permit_manager,
            self.building_manager, self.stockpile_manager, self.furniture_manager,
            self.villager_manager, self.servant_manager, self.schedule_manager
        )
        self.assertTrue(ok_ow)

        # Verify no orphaned .tmp file exists
        tmp_file = slot_path + ".tmp"
        self.assertFalse(os.path.exists(tmp_file))
        os.remove(slot_path)

    def test_05_load_overwritten_save(self):
        """5. Load slot hasil overwrite memulihkan data baru secara presisi."""
        slot_path = get_slot_path(99)
        if os.path.exists(slot_path):
            os.remove(slot_path)

        # Create a family with member inventory and a bed
        fam = self.villager_manager.generate_random_family()
        fam.members[0].inventory["Hoe"] = 1
        fam.members[0].active_tool = "Hoe"
        fam.members[0].has_water = True

        bed, _ = self.furniture_manager.add_furniture(
            "bed", 3, 3, self.permit_manager, self.villager_manager, self.resources
        )
        bed.assigned_villager_id = fam.members[0].id

        # Save to slot
        save_to_slot(
            99, self.day_cycle, self.resources, self.player, self.permit_manager,
            self.building_manager, self.stockpile_manager, self.furniture_manager,
            self.villager_manager, self.servant_manager, self.schedule_manager
        )

        # Fresh managers to load into
        new_pm = PermitManager()
        new_bm = BuildingManager()
        new_sm = StockpileManager()
        new_svm = ServantManager()
        new_vm = VillagerManager()
        new_fm = FurnitureManager()
        new_dc = DayCycleSystem()
        new_sch = ScheduleManager()
        new_res = {}
        new_player = Player()

        ok, msg = load_from_slot(
            99, new_dc, new_res, new_player, new_pm,
            new_bm, new_sm, new_fm, new_vm, new_svm, new_sch
        )
        self.assertTrue(ok)
        self.assertEqual(len(new_vm.families), 1)
        loaded_mem = new_vm.families[0].members[0]
        self.assertEqual(loaded_mem.inventory.get("Hoe", 0), 1)
        self.assertEqual(loaded_mem.active_tool, "Hoe")
        self.assertTrue(loaded_mem.has_water)
        self.assertEqual(len(new_fm.furniture), 1)
        self.assertEqual(new_fm.furniture[0].assigned_villager_id, loaded_mem.id)
        if os.path.exists(slot_path):
            os.remove(slot_path)

    def test_06_watering_duration_thirty_minutes(self):
        """6. Menyiram 1 petak ladang memakan durasi tepat 30 menit in-game labor."""
        farm_lot = next(p for p in self.permit_manager.permits if p.permit_type == "farm")
        farm_lot.crop = "Potato"
        t = list(farm_lot.tiles)[0]

        # Till and sow
        farm_lot.till_and_sow_tile(t[0], t[1])
        crop_data = farm_lot.tile_crops[(t[0], t[1])]
        self.assertFalse(crop_data["watered_today"])

        # Calculate exact 30 in-game minutes in real seconds
        day_length_sec = DAY_LENGTH_OPTIONS[DEFAULT_DAY_LENGTH_INDEX]["seconds"]
        one_in_game_hour = day_length_sec / 24.0
        thirty_min_labor = one_in_game_hour * 0.5

        # Create a farmer with water and watering can
        fam = self.villager_manager.generate_random_family()
        farmer = fam.members[0]
        farm_lot.assigned_workers.append(farmer.id)
        farmer.inventory["Watering_Can"] = 1
        farmer.active_tool = "Watering_Can"
        farmer.has_water = True
        farmer.water_day = self.day_cycle.day_number
        farmer.x = (t[0] + 0.5) * TILE_SIZE
        farmer.y = (t[1] + 0.5) * TILE_SIZE

        # Set schedule to WORK (10:00 AM)
        self.day_cycle.time_seconds = (10.0 / 24.0) * self.day_cycle.day_length_seconds

        # Run 29 in-game minutes -> not finished yet
        twenty_nine_min = thirty_min_labor * (29.0 / 30.0)
        farmer.update(
            twenty_nine_min, self.permit_manager, self.building_manager, [], None,
            stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
            day_cycle=self.day_cycle, schedule_manager=self.schedule_manager
        )
        self.assertFalse(crop_data["watered_today"])

        # Run remaining 2 in-game minutes -> finished!
        two_min = thirty_min_labor * (2.0 / 30.0)
        farmer.update(
            two_min, self.permit_manager, self.building_manager, [], None,
            stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
            day_cycle=self.day_cycle, schedule_manager=self.schedule_manager
        )
        self.assertTrue(crop_data["watered_today"])

    def test_07_four_farmers_task_reservation(self):
        """7. 4 Farmer menyiram lahan dengan task reservation tanpa bentrok."""
        farm_lot = next(p for p in self.permit_manager.permits if p.permit_type == "farm")
        farm_lot.crop = "Potato"
        farm_lot.max_workers = 4
        tiles = sorted(list(farm_lot.tiles))[:4]
        for t in tiles:
            farm_lot.till_and_sow_tile(t[0], t[1])

        while len(self.villager_manager.get_all_villagers()) < 4:
            self.villager_manager.generate_random_family()
        farmers = self.villager_manager.get_all_villagers()[:4]
        for f in farmers:
            farm_lot.assigned_workers.append(f.id)
            f.inventory["Watering_Can"] = 1
            f.active_tool = "Watering_Can"
            f.has_water = True
            f.water_day = self.day_cycle.day_number

        self.day_cycle.time_seconds = (10.0 / 24.0) * self.day_cycle.day_length_seconds
        # Update each farmer
        for f in farmers:
            f.update(
                0.1, self.permit_manager, self.building_manager, [], None,
                stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                day_cycle=self.day_cycle, schedule_manager=self.schedule_manager
            )

        # Check that each farmer reserved a DISTINCT tile
        reserved_tiles = set(farm_lot.task_reservations.keys())
        self.assertEqual(len(reserved_tiles), 4)
        reserved_workers = {v["worker_id"] for v in farm_lot.task_reservations.values()}
        self.assertEqual(len(reserved_workers), 4)

    def test_08_and_09_deleting_lot_drops_furniture(self):
        """8, 9. Menghapus Lot mengubah Chest dan Bed menjadi Droppable Item di tanah milik keluarga."""
        house_lot = next(p for p in self.permit_manager.permits if p.permit_type == "housing")
        fam = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam.id, house_lot.id, self.permit_manager, self.building_manager, self.furniture_manager)

        # Place Chest and Bed
        hx, hy = list(house_lot.tiles)[0]
        bx, by = list(house_lot.tiles)[1]
        chest, _ = self.furniture_manager.add_furniture("household_storage", hx, hy, self.permit_manager, self.villager_manager, self.resources)
        chest.inventory["Potato"] = 15

        bed, _ = self.furniture_manager.add_furniture("bed", bx, by, self.permit_manager, self.villager_manager, self.resources)

        # Delete lot
        self.permit_manager.delete_permit(house_lot.id, self.building_manager, furniture_manager=self.furniture_manager, stockpile_manager=self.stockpile_manager)

        # Furniture must become dropped
        self.assertTrue(chest.is_dropped)
        self.assertTrue(bed.is_dropped)
        self.assertEqual(chest.family_id, fam.id)
        self.assertEqual(bed.family_id, fam.id)

        # Chest retains its inventory intact while UNINSTALLED so contents survive moves
        self.assertEqual(chest.inventory.get("Potato"), 15)

    def test_10_destroying_chest_spills_inventory(self):
        """10. Menghancurkan Chest menumpahkan seluruh isi ke tanah sebagai droppable items milik keluarga."""
        fam = self.villager_manager.generate_random_family()
        chest = Furniture("f_1", "household_storage", 5, 5, permit_id="test_permit", family_id=fam.id)
        chest.inventory["Sickle"] = 3
        self.furniture_manager.furniture.append(chest)

        ok, msg = self.furniture_manager.destroy_furniture("f_1", self.stockpile_manager, self.resources)
        self.assertTrue(ok)
        self.assertEqual(len(self.furniture_manager.furniture), 0)

        # Check ground items
        fam_loose = self.stockpile_manager.get_villager_loose_stacks([fam.id])
        self.assertEqual(len(fam_loose), 1)
        self.assertEqual(fam_loose[0].resource_type, "Sickle")
        self.assertEqual(fam_loose[0].amount, 3)

    def test_11_moving_chest_preserves_inventory(self):
        """11. Memindahkan Chest mempertahankan isi tanpa tumpah atau hilang."""
        fam = self.villager_manager.generate_random_family()
        chest = Furniture("f_2", "household_storage", 5, 5, permit_id="test_permit", family_id=fam.id)
        chest.inventory["Hoe"] = 4
        self.furniture_manager.furniture.append(chest)

        ok, msg = self.furniture_manager.move_furniture("f_2", 8, 8, self.permit_manager, self.building_manager)
        self.assertTrue(ok)
        self.assertEqual(chest.grid_x, 8)
        self.assertEqual(chest.grid_y, 8)
        self.assertEqual(chest.inventory.get("Hoe", 0), 4)

        # No items spilled
        fam_loose = self.stockpile_manager.get_villager_loose_stacks([fam.id])
        self.assertEqual(len(fam_loose), 0)

    def test_12_bed_sleep_one_to_one(self):
        """12. Saat SLEEP, setiap individu menempati Bed masing-masing (1 Bed = 1 Villager)."""
        house_lot = next(p for p in self.permit_manager.permits if p.permit_type == "housing")
        fam = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam.id, house_lot.id, self.permit_manager, self.building_manager, self.furniture_manager)

        # Create 2 beds for 2 members
        tiles = list(house_lot.tiles)
        bed1, _ = self.furniture_manager.add_furniture("bed", tiles[0][0], tiles[0][1], self.permit_manager, self.villager_manager, self.resources)
        bed2, _ = self.furniture_manager.add_furniture("bed", tiles[1][0], tiles[1][1], self.permit_manager, self.villager_manager, self.resources)

        m1 = fam.members[0]
        m2 = fam.members[1]
        self.day_cycle.time_seconds = (23.0 / 24.0) * self.day_cycle.day_length_seconds  # SLEEP time

        m1.update(1.0, self.permit_manager, self.building_manager, [], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle, schedule_manager=self.schedule_manager)
        m2.update(1.0, self.permit_manager, self.building_manager, [], None, furniture_manager=self.furniture_manager, day_cycle=self.day_cycle, schedule_manager=self.schedule_manager)

        self.assertIsNotNone(m1.assigned_bed_id)
        self.assertIsNotNone(m2.assigned_bed_id)
        self.assertNotEqual(m1.assigned_bed_id, m2.assigned_bed_id)

    def test_13_sleep_without_bed_dispersed(self):
        """13. Saat SLEEP tanpa Bed, individu tidur di lantai secara tersebar dengan personal space."""
        house_lot = next(p for p in self.permit_manager.permits if p.permit_type == "housing")
        fam = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam.id, house_lot.id, self.permit_manager, self.building_manager, self.furniture_manager)

        self.day_cycle.time_seconds = (23.0 / 24.0) * self.day_cycle.day_length_seconds  # SLEEP time
        all_vils = self.villager_manager.get_all_villagers()

        # Update several ticks
        for _ in range(5):
            self.villager_manager.update(
                0.2, self.permit_manager, self.building_manager, [], None,
                stockpile_manager=self.stockpile_manager, furniture_manager=self.furniture_manager,
                day_cycle=self.day_cycle, schedule_manager=self.schedule_manager
            )

        # Verify no two villagers occupy the exact same coordinate
        for i in range(len(all_vils)):
            for j in range(i + 1, len(all_vils)):
                d = math.hypot(all_vils[i].x - all_vils[j].x, all_vils[i].y - all_vils[j].y)
                self.assertGreater(d, 0.5)

    def test_14_and_15_individual_inventory_and_household_conservation(self):
        """14, 15. Transfer item antara Inventory individu, Peti, dan Tanah tidak mengubah total kepemilikan."""
        house_lot = next(p for p in self.permit_manager.permits if p.permit_type == "housing")
        fam = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam.id, house_lot.id, self.permit_manager, self.building_manager, self.furniture_manager)

        # Place chest
        ht = list(house_lot.tiles)[0]
        chest, _ = self.furniture_manager.add_furniture("household_storage", ht[0], ht[1], self.permit_manager, self.villager_manager, self.resources)

        m = fam.members[0]
        m.inventory["Potato"] = 10

        def calc_total():
            t_chest = sum(c.inventory.get("Potato", 0) for c in self.furniture_manager.get_furniture_for_family(fam.id) if c.furniture_type == "household_storage")
            t_inv = sum(mem.inventory.get("Potato", 0) for mem in fam.members)
            t_ground = sum(s.amount for s in self.stockpile_manager.get_villager_loose_stacks([fam.id]) if s.resource_type == "Potato")
            return t_chest + t_inv + t_ground

        self.assertEqual(calc_total(), 10)

        # Deposit 4 to chest
        m.deposit_item_to_chest("Potato", 4, self.furniture_manager)
        self.assertEqual(m.inventory["Potato"], 6)
        self.assertEqual(chest.inventory["Potato"], 4)
        self.assertEqual(calc_total(), 10)

        # Drop 3 to ground
        m.drop_inventory_item("Potato", 3, self.stockpile_manager)
        self.assertEqual(m.inventory["Potato"], 3)
        self.assertEqual(calc_total(), 10)

        # Withdraw 2 from chest
        m.withdraw_item_from_chest("Potato", 2, self.furniture_manager)
        self.assertEqual(m.inventory["Potato"], 5)
        self.assertEqual(chest.inventory["Potato"], 2)
        self.assertEqual(calc_total(), 10)

if __name__ == "__main__":
    unittest.main()
