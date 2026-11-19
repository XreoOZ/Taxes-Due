"""
Physical Stockpile & Ground Item System (RimWorld-style Dropped Items & Hauling)
"""

import pygame
from game.config import MAX_STACK_SIZE, MAX_TILE_CAPACITY, DEFAULT_STARTER_TOOLS, is_food_item, is_water_item
from game.item_icons import draw_item_icon

class ResourceStack:
    def __init__(self, resource_type, amount, grid_x, grid_y, owner_type="landlord", owner_id=None):
        self.resource_type = resource_type
        self.amount = amount
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.owner_type = owner_type  # "landlord" | "villager"
        self.owner_id = owner_id      # villager_id if owner_type == "villager"
        self.reserved_amount = 0      # Track amount in transit / claimed by active gatherers

    @property
    def available_amount(self):
        """Kuantitas resource yang tersedia untuk diambil (tidak sedang dipesan oleh worker lain)"""
        return max(0, self.amount - getattr(self, "reserved_amount", 0))

    def reserve(self, amount):
        """Memesan kuantitas resource agar tidak diambil melebihi kapasitas oleh AI lain"""
        avail = self.available_amount
        actual = min(amount, avail)
        self.reserved_amount = getattr(self, "reserved_amount", 0) + actual
        return actual

    def release_reservation(self, amount):
        """Mengembalikan reservasi jika tugas dibatalkan atau dialihkan"""
        self.reserved_amount = max(0, getattr(self, "reserved_amount", 0) - amount)

    def get_display_text(self):
        """Format stack text like (10)100 for 10x100 or (5)100 for 5x100"""
        full_stacks = self.amount // MAX_STACK_SIZE
        remainder = self.amount % MAX_STACK_SIZE

        if full_stacks > 1:
            if remainder == 0:
                return f"({full_stacks}){MAX_STACK_SIZE}"
            else:
                return f"({full_stacks}){MAX_STACK_SIZE}+{remainder}"
        elif full_stacks == 1:
            if remainder == 0:
                return str(MAX_STACK_SIZE)
            else:
                return f"{MAX_STACK_SIZE}+{remainder}"
        else:
            return str(remainder)


class StockpileManager:
    def __init__(self):
        self.stacks = []
        self.font = None

    def _ensure_font(self):
        if self.font is None:
            self.font = pygame.font.SysFont("Segoe UI", 10, bold=True)

    def initialize_starter_stockpile(self, initial_resources, permit_manager, starter_tools=None):
        """Menempatkan item awal di atas tanah pada lot storage starter"""
        self.stacks = []

        # Cari starter storage permit
        storage_tiles = []
        for p in permit_manager.permits:
            if p.permit_type == "storage":
                for tile in sorted(p.tiles, key=lambda t: (t[1], t[0])):
                    storage_tiles.append(tile)

        # Fallback jika belum ada permit
        if not storage_tiles:
            storage_tiles = [(2, -6), (3, -6), (4, -6), (5, -6)]

        tile_idx = 0
        total_tiles = len(storage_tiles)

        # 1. Tempatkan resource dasar (Wood, Food, Stone, Water, Copper, Silver, Gold)
        for res_type in ["Wood", "Food", "Stone", "Water", "Copper", "Silver", "Gold"]:
            remaining = initial_resources.get(res_type, 0)
            while remaining > 0 and tile_idx < total_tiles:
                amount_in_tile = min(remaining, MAX_TILE_CAPACITY)
                gx, gy = storage_tiles[tile_idx]
                self.stacks.append(ResourceStack(res_type, amount_in_tile, gx, gy))
                remaining -= amount_in_tile
                tile_idx += 1

        # 2. Tempatkan starter farming tools (Cangkul, Sickle, Siraman)
        tools = starter_tools if starter_tools is not None else DEFAULT_STARTER_TOOLS
        for tool_name, count in tools.items():
            if count > 0 and tile_idx < total_tiles:
                gx, gy = storage_tiles[tile_idx]
                self.stacks.append(ResourceStack(tool_name, count, gx, gy, owner_type="landlord"))
                tile_idx += 1

    def drop_resource(self, resource_type, amount, gx, gy, owner_type="landlord", owner_id=None):
        """Menjatuhkan barang secara fisik di atas tanah (misal saat panen atau pembongkaran)"""
        if amount <= 0:
            return

        # Cari stack sejenis dan pemilik yang sama di petak tersebut
        for s in self.stacks:
            if s.grid_x == gx and s.grid_y == gy and s.resource_type == resource_type and s.owner_type == owner_type and s.owner_id == owner_id:
                space_left = MAX_TILE_CAPACITY - s.amount
                add_amt = min(space_left, amount)
                s.amount += add_amt
                amount -= add_amt
                if amount <= 0:
                    return

        # Jika masih ada sisa atau petak belum ada stack sejenis, buat stack baru
        self.stacks.append(ResourceStack(resource_type, amount, gx, gy, owner_type=owner_type, owner_id=owner_id))

    def get_stack_at(self, gx, gy):
        for s in self.stacks:
            if s.grid_x == gx and s.grid_y == gy:
                return s
        return None

    def take_from_stack(self, stack, amount):
        """Mengambil sebagian atau seluruh barang dari stack fisik"""
        if not stack:
            return 0
        actual = min(amount, stack.amount)
        stack.amount -= actual
        if hasattr(stack, "reserved_amount"):
            stack.reserved_amount = max(0, stack.reserved_amount - actual)
        if stack.amount <= 0:
            if stack in self.stacks:
                self.stacks.remove(stack)
        return actual

    def deposit_to_tile(self, resource_type, amount, gx, gy, owner_type="landlord", owner_id=None):
        """Menaruh barang hasil angkut ke dalam petak penyimpanan"""
        self.drop_resource(resource_type, amount, gx, gy, owner_type=owner_type, owner_id=owner_id)

    def is_tile_in_storage(self, gx, gy, permit_manager):
        """Mengecek apakah petak berada di dalam permit storage aktif"""
        for p in permit_manager.permits:
            if p.permit_type == "storage" and p.contains_tile(gx, gy):
                return True
        return False

    def get_loose_stacks(self, permit_manager):
        """Mendapatkan daftar item milik Landlord yang berserakan di luar area penyimpanan (perlu di-haul servant)"""
        loose = []
        for s in self.stacks:
            if s.owner_type == "landlord" and not self.is_tile_in_storage(s.grid_x, s.grid_y, permit_manager):
                loose.append(s)
        return loose

    def get_villager_loose_stacks(self, owner_ids, crops_only=False):
        """Mendapatkan daftar barang/hasil panen milik villager/keluarga yang tercecer di tanah"""
        valid_crops = ("Food", "Potato", "potato")
        if isinstance(owner_ids, (list, set, tuple)):
            id_strs = {str(x) for x in owner_ids}
            if crops_only:
                return [s for s in self.stacks if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) in id_strs and s.resource_type in valid_crops and s.amount > 0]
            return [s for s in self.stacks if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) in id_strs and s.amount > 0]
        if crops_only:
            return [s for s in self.stacks if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == str(owner_ids) and s.resource_type in valid_crops and s.amount > 0]
        return [s for s in self.stacks if getattr(s, "owner_type", None) == "villager" and str(getattr(s, "owner_id", "")) == str(owner_ids) and s.amount > 0]

    def get_available_storage_tile(self, permit_manager, resource_type):
        """Mencari petak storage permit kosong atau petak yang memiliki sisa kapasitas untuk barang ini"""
        occupied_tiles = {}
        for s in self.stacks:
            occupied_tiles[(s.grid_x, s.grid_y)] = s

        for p in permit_manager.permits:
            if p.permit_type == "storage":
                for tile in sorted(p.tiles, key=lambda t: (t[1], t[0])):
                    if tile in occupied_tiles:
                        s = occupied_tiles[tile]
                        if s.resource_type == resource_type and s.amount < MAX_TILE_CAPACITY:
                            return tile
                    else:
                        # Petak benar-benar kosong di dalam storage!
                        return tile
        return None

    def get_total_resources(self):
        """Menghitung total seluruh resource fisik milik Landlord di stockpile/dunia"""
        totals = {"Wood": 0, "Food": 0, "Stone": 0, "Water": 0, "Copper": 0, "Silver": 0, "Gold": 0}
        for s in self.stacks:
            if getattr(s, "owner_type", "landlord") == "landlord":
                rt = s.resource_type
                if rt in totals:
                    totals[rt] += s.amount
                elif is_food_item(rt):
                    totals["Food"] += s.amount
                elif is_water_item(rt):
                    totals["Water"] += s.amount
                else:
                    rt_clean = str(rt).replace(" Coin", "").strip()
                    if rt_clean in totals:
                        totals[rt_clean] += s.amount
        return totals

    def refresh_stacks(self, resources, permit_manager):
        """Sinkronisasi berkala (tidak menghapus barang yang tercecer)"""
        # Sinkronkan nilai total resources agar selalu akurat dengan jumlah fisik
        current_totals = self.get_total_resources()
        if resources is not None and isinstance(resources, dict):
            for res, amt in current_totals.items():
                resources[res] = amt

    def draw(self, surface, camera, tile_size, permit_manager=None):
        self._ensure_font()

        for stack in self.stacks:
            if not camera.is_world_rect_visible(
                    stack.grid_x * tile_size, stack.grid_y * tile_size,
                    tile_size, tile_size):
                continue
            sx, sy = camera.world_to_screen(stack.grid_x * tile_size, stack.grid_y * tile_size)
            scaled_tile = int(tile_size * camera.zoom)
            if scaled_tile < 10:
                continue

            center_x = sx + scaled_tile // 2
            center_y = sy + scaled_tile // 2
            if permit_manager and not self.is_tile_in_storage(stack.grid_x, stack.grid_y, permit_manager):
                pygame.draw.rect(
                    surface, (234, 179, 8, 140),
                    (sx + 2, sy + 2, scaled_tile - 4, scaled_tile - 4),
                    width=1, border_radius=4,
                )

            # World stacks use the same canonical icon as Add Item and other item UI.
            draw_item_icon(
                surface, stack.resource_type, center_x, center_y,
                size=max(5, int(scaled_tile * 0.28)),
            )

            if camera.zoom >= 0.6:
                amount_text = stack.get_display_text()
                label_key = (id(self.font), amount_text)
                if getattr(stack, "_label_cache_key", None) != label_key:
                    stack._label_cache_key = label_key
                    stack._label_surface = self.font.render(amount_text, True, (255, 255, 255))
                    stack._label_shadow_surface = self.font.render(amount_text, True, (0, 0, 0))
                text_surface = stack._label_surface
                shadow_surface = stack._label_shadow_surface
                text_x = center_x - text_surface.get_width() // 2
                text_y = center_y + int(scaled_tile * 0.16)
                background = pygame.Rect(
                    text_x - 3, text_y - 1,
                    text_surface.get_width() + 6, text_surface.get_height() + 2,
                )
                pygame.draw.rect(surface, (15, 23, 42, 180), background, border_radius=3)
                surface.blit(shadow_surface, (text_x + 1, text_y + 1))
                surface.blit(text_surface, (text_x, text_y))
