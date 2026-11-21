"""
Comprehensive Integration Tests for:
1. Save / Load / Overwrite round-trips with verified data updates across multiple overwrites.
2. Uninstalled Furniture state transitions (INSTALLED -> UNINSTALLED -> MOVING -> INSTALLED).
3. Preservation of furniture inventory, ownership, and relations across moves and saves.
4. Safe destruction of furniture with resource refund and inventory drop.
"""

import os
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
pygame.init()

from game.config import DEFAULT_RESOURCES, DEFAULT_STARTER_TOOLS, TILE_SIZE
from game.entities.player import Player
from game.buildings.building_manager import BuildingManager
from game.world.permits import AreaPermit, PermitManager
from game.world.stockpile import StockpileManager
from game.entities.servants import ServantManager
from game.entities.villagers import VillagerManager, Family, Villager
from game.buildings.furniture import Furniture, FurnitureManager
from game.systems.day_cycle import DayCycleSystem
from game.systems.schedule import ScheduleManager
from game.systems.save_system import save_to_slot, load_from_slot, get_slot_meta, get_slot_path


class TestSaveOverwriteAndFurnitureMove(unittest.TestCase):
    def setUp(self):
        self.day_cycle = DayCycleSystem()
        self.resources = dict(DEFAULT_RESOURCES)
        self.player = Player(10.0, 20.0)
        self.permit_manager = PermitManager()
        self.building_manager = BuildingManager()
        self.stockpile_manager = StockpileManager()
        self.stockpile_manager.initialize_starter_stockpile(self.resources, self.permit_manager, DEFAULT_STARTER_TOOLS)
        self.furniture_manager = FurnitureManager()
        self.villager_manager = VillagerManager()
        self.servant_manager = ServantManager()
        self.schedule_manager = ScheduleManager()

        # Clean test save slot 3
        slot_file = get_slot_path(3)
        if os.path.exists(slot_file):
            try:
                os.remove(slot_file)
            except Exception:
                pass

    def tearDown(self):
        slot_file = get_slot_path(3)
        if os.path.exists(slot_file):
            try:
                os.remove(slot_file)
            except Exception:
                pass

    def test_save_overwrite_multiple_cycles(self):
        """
        Wajib:
        1. Save ke slot kosong.
        2. Ubah kondisi dunia (pindahkan furniture, ubah waktu, ubah resource).
        3. Overwrite slot yang sama.
        4. Load slot tersebut -> pastikan perubahan terbaru muncul.
        5. Ubah kondisi dunia lagi.
        6. Overwrite slot yang sama sekali lagi.
        7. Load ulang -> pastikan data terbaru kedua kembali muncul.
        """
        # --- Cycle 1: Save awal ---
        lot1 = self.permit_manager.add_permit("Housing 1", "housing", {(0, 0), (0, 1), (1, 0), (1, 1)})
        fam1 = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam1.id, lot1.id, self.permit_manager, self.building_manager)
        chest, _ = self.furniture_manager.add_furniture("household_storage", 0, 0, self.permit_manager, self.villager_manager, self.resources)
        chest.inventory["Potato"] = 25
        self.day_cycle.day_number = 1
        self.resources["Wood"] = 1000

        ok1, msg1 = save_to_slot(
            3, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager,
            self.schedule_manager
        )
        self.assertTrue(ok1, f"Initial save failed: {msg1}")
        meta1 = get_slot_meta(3)
        self.assertFalse(meta1["is_empty"])
        self.assertEqual(meta1["day_number"], 1)

        # --- Cycle 2: Ubah dunia & Overwrite ---
        self.day_cycle.day_number = 3
        self.resources["Wood"] = 750
        chest.inventory["Potato"] = 40
        self.player.x = 250.0

        ok2, msg2 = save_to_slot(
            3, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager,
            self.schedule_manager
        )
        self.assertTrue(ok2, f"First overwrite failed: {msg2}")
        meta2 = get_slot_meta(3)
        self.assertEqual(meta2["day_number"], 3)
        self.assertEqual(meta2["wood"], 750)

        # Reset in-memory state then Load
        self.day_cycle.day_number = 99
        self.resources["Wood"] = 0
        self.player.x = 0.0

        ok_load1, msg_l1 = load_from_slot(
            3, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager,
            self.schedule_manager
        )
        self.assertTrue(ok_load1, f"Load 1 failed: {msg_l1}")
        self.assertEqual(self.day_cycle.day_number, 3, "Day number must reflect overwrite 1")
        self.assertEqual(self.resources["Wood"], 750, "Wood must reflect overwrite 1")
        self.assertEqual(self.player.x, 250.0, "Player pos must reflect overwrite 1")
        loaded_chest = self.furniture_manager.get_furniture_at(0, 0)
        self.assertIsNotNone(loaded_chest)
        self.assertEqual(loaded_chest.inventory.get("Potato"), 40)

        # --- Cycle 3: Ubah dunia lagi & Overwrite ke-2 ---
        self.day_cycle.day_number = 8
        self.resources["Wood"] = 420
        loaded_chest.inventory["Potato"] = 99
        self.player.x = 512.0

        ok3, msg3 = save_to_slot(
            3, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager,
            self.schedule_manager
        )
        self.assertTrue(ok3, f"Second overwrite failed: {msg3}")

        # Reset and load again
        self.day_cycle.day_number = 1
        self.resources["Wood"] = 0
        self.player.x = 0.0

        ok_load2, msg_l2 = load_from_slot(
            3, self.day_cycle, self.resources, self.player,
            self.permit_manager, self.building_manager, self.stockpile_manager,
            self.furniture_manager, self.villager_manager, self.servant_manager,
            self.schedule_manager
        )
        self.assertTrue(ok_load2, f"Load 2 failed: {msg_l2}")
        self.assertEqual(self.day_cycle.day_number, 8, "Day number must reflect second overwrite")
        self.assertEqual(self.resources["Wood"], 420, "Wood must reflect second overwrite")
        self.assertEqual(self.player.x, 512.0, "Player x must reflect second overwrite")
        chest_final = self.furniture_manager.get_furniture_at(0, 0)
        self.assertEqual(chest_final.inventory.get("Potato"), 99)

    def test_uninstalled_furniture_states_and_move_lifecycle(self):
        """
        Verifies:
        - Lot deletion sets furniture status to UNINSTALLED without destroying inventory.
        - Moving designated furniture transitions to MOVING when picked up.
        - Arriving at target reinstall transitions to INSTALLED.
        - Family ownership and contents survive the move.
        """
        lot = self.permit_manager.add_permit("Test Housing", "housing", {(5, 5), (5, 6)})
        fam = self.villager_manager.generate_random_family()
        self.villager_manager.assign_family_to_permit(fam.id, lot.id, self.permit_manager, self.building_manager)

        chest, _ = self.furniture_manager.add_furniture("household_storage", 5, 5, self.permit_manager, self.villager_manager, self.resources)
        chest.inventory["Potato"] = 50
        chest.inventory["Sickle"] = 2
        self.assertEqual(chest.status, "INSTALLED")

        # 1. Hapus Lot -> Furniture menjadi UNINSTALLED
        self.permit_manager.delete_permit(lot.id, self.building_manager, furniture_manager=self.furniture_manager, stockpile_manager=self.stockpile_manager)
        self.assertEqual(chest.status, "UNINSTALLED")
        self.assertTrue(chest.is_dropped)
        self.assertEqual(chest.family_id, fam.id)
        self.assertEqual(chest.inventory["Potato"], 50, "Inventory must NOT be cleared on lot deletion")
        self.assertEqual(chest.inventory["Sickle"], 2)

        # 2. Landlord membuat lot baru dan merencanakan pemindahan (Move)
        new_lot = self.permit_manager.add_permit("New Housing", "housing", {(10, 10), (10, 11)})
        self.villager_manager.assign_family_to_permit(fam.id, new_lot.id, self.permit_manager, self.building_manager)

        chest.designate_move(10, 10, new_lot.id)
        self.assertEqual(chest.designated_target, (10, 10, new_lot.id))

        # 3. AI (Villager anggota keluarga) berjalan dan memanggul furniture -> Status MOVING
        worker = fam.members[0]
        worker.x = 5 * TILE_SIZE
        worker.y = 5 * TILE_SIZE
        chest.carrier_id = worker.id
        worker.carrying_furniture = chest
        self.assertEqual(chest.status, "MOVING")

        # 4. AI tiba di lokasi target -> Pasang ulang -> Status INSTALLED
        worker.x = 10 * TILE_SIZE
        worker.y = 10 * TILE_SIZE
        ok, msg = self.furniture_manager.move_furniture(chest.id, 10, 10, self.permit_manager, self.villager_manager)
        self.assertTrue(ok)
        worker.carrying_furniture = None

        self.assertEqual(chest.status, "INSTALLED")
        self.assertFalse(chest.is_dropped)
        self.assertEqual(chest.grid_x, 10)
        self.assertEqual(chest.grid_y, 10)
        self.assertEqual(chest.inventory["Potato"], 50, "Potato count must survive move")
        self.assertEqual(chest.inventory["Sickle"], 2, "Sickle count must survive move")
        self.assertEqual(chest.family_id, fam.id, "Ownership must be retained")

    def test_destroy_furniture_refunds_and_drops_items(self):
        """
        Verifies that destroying furniture:
        - Drops all chest contents to the ground owned by the family.
        - Refunds half of the wood cost to landlord resources.
        - Removes the furniture from the world.
        """
        fam = self.villager_manager.generate_random_family()
        chest = Furniture("furn_test_del", "household_storage", 3, 3, permit_id="test_permit", family_id=fam.id)
        chest.inventory["Potato"] = 12
        self.furniture_manager.furnitures.append(chest)

        initial_wood = self.resources.get("Wood", 0)
        ok = self.furniture_manager.destroy_furniture(
            chest.id,
            stockpile_manager=self.stockpile_manager,
            resources=self.resources,
            villager_manager=self.villager_manager,
            servant_manager=self.servant_manager
        )
        self.assertTrue(ok)
        self.assertIsNone(self.furniture_manager.get_furniture_by_id("furn_test_del"))

        # Check resource refund
        self.assertGreater(self.resources.get("Wood", 0), initial_wood)

        # Check that dropped stack exists on ground
        fam_loose = self.stockpile_manager.get_villager_loose_stacks([fam.id])
        self.assertEqual(len(fam_loose), 1)
        self.assertEqual(fam_loose[0].amount, 12)


if __name__ == "__main__":
    unittest.main()
