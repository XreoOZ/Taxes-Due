"""New-game starter presets: place the "Easy Start" village layout.

Driven entirely by STARTER_PRESETS in game/data/config.py — adding a new
preset is a config change, no code edits required.

Layout rules (per user spec):
- Permits match the structure size exactly (no padding).
- Everything placed is a COMPLETED structure — never a blueprint.
- The household chest sits INSIDE the house; preset goods live as loose
  landlord-owned stacks inside a dedicated storage yard, not in the chest.
- Currency presets go into the Lord Treasury chest.
"""

import random

from game.data.config import STARTER_PRESETS, MAX_STACK_SIZE, TILE_SIZE
from game.world.island import is_land_tile


class StarterPresetSystem:
    @classmethod
    def get_preset(cls, preset_id):
        return next((p for p in STARTER_PRESETS if p.get("id") == preset_id), None)

    @classmethod
    def apply(cls, preset_id, villager_manager, furniture_manager,
              building_manager, permit_manager, stockpile_manager=None):
        """Materialize a starter preset on a fresh game world.

        Returns True on success; disabled/unknown presets return False.
        """
        preset = cls.get_preset(preset_id)
        if not preset or not preset.get("enabled"):
            return False
        if not all([villager_manager, furniture_manager, building_manager, permit_manager]):
            return False

        pad = int(preset.get("permit_padding", 0) or 0)
        used_tiles = set()

        # 1) Starter household (size comes from the preset).
        family = villager_manager.generate_starter_family(
            size=preset.get("family_size"))

        # 2) Housing permit (exactly the house footprint) + finished house.
        house_cfg = preset.get("house")
        hx = hy = hw = hh = None
        if house_cfg:
            hw, hh = int(house_cfg["width"]), int(house_cfg["height"])
            zx, zy = cls._find_land_origin(
                hw + pad * 2, hh + pad * 2, used_tiles,
                building_manager, permit_manager, furniture_manager)
            if zx is None:
                return False
            hx, hy = zx + pad, zy + pad
            house_permit = permit_manager.add_permit_rect(
                "Starter Housing", "housing", zx, zy, hw + pad * 2, hh + pad * 2)
            used_tiles.update((gx, gy)
                              for gx in range(zx, zx + hw + pad * 2)
                              for gy in range(zy, zy + hh + pad * 2))
            cls._place_finished_building(
                building_manager, house_cfg["building_type"],
                {(hx + dx, hy + dy) for dx in range(hw) for dy in range(hh)},
                door_pos=(hx + hw // 2, hy + hh - 1), door_side="bottom")
            if family is not None:
                villager_manager.assign_family_to_permit(
                    family.id, house_permit.id, permit_manager,
                    building_manager, furniture_manager=furniture_manager)
                cls._spawn_family_at_door(family, (hx + hw // 2, hy + hh - 1))

            # Interior furniture: family chest + carpenter workbench, both
            # installed (never blueprints). Avoid the door tile.
            door_tile = (hx + hw // 2, hy + hh - 1)
            interior = [(hx + 1, hy + 1), (hx + 3, hy + 1), (hx + 1, hy),
                        (hx + 4, hy + 1), (hx + 2, hy + 1)]
            if preset.get("storage_chest_inside_house"):
                for tx, ty in interior:
                    if (tx, ty) == door_tile:
                        continue
                    chest = cls._install_furniture(
                        furniture_manager, "household_storage", tx, ty,
                        permit_manager, villager_manager, building_manager)
                    if chest is not None:
                        break
            if preset.get("carpenter_workbench"):
                for tx, ty in interior:
                    # workbench is 2x1 — needs tx and tx+1 free of the chest
                    if (tx, ty) == door_tile or (tx + 1, ty) == door_tile:
                        continue
                    occupied = {(f.grid_x, f.grid_y) for f in furniture_manager.furnitures
                                if not f.is_dropped}
                    if any((tx + dx, ty) in occupied for dx in range(2)):
                        continue
                    wb = cls._install_furniture(
                        furniture_manager, "carpenter_workbench", tx, ty,
                        permit_manager, villager_manager, building_manager)
                    if wb is not None:
                        break

        # 3) Market permit (exactly the stall footprint) + finished market.
        market_cfg = preset.get("market")
        if market_cfg:
            mw, mh = int(market_cfg["width"]), int(market_cfg["height"])
            zx, zy = cls._find_land_origin(
                mw + pad * 2, mh + pad * 2, used_tiles,
                building_manager, permit_manager, furniture_manager)
            if zx is not None:
                mx, my = zx + pad, zy + pad
                permit_manager.add_permit_rect(
                    "Starter Market", "market", zx, zy, mw + pad * 2, mh + pad * 2)
                used_tiles.update((gx, gy)
                                  for gx in range(zx, zx + mw + pad * 2)
                                  for gy in range(zy, zy + mh + pad * 2))
                cls._place_finished_building(
                    building_manager, market_cfg["building_type"],
                    {(mx + dx, my + dy) for dx in range(mw) for dy in range(mh)})

        # 4) Landlord storage yard: permit-sized area filled with loose
        # landlord-owned item stacks (the player's physical storage).
        if preset.get("landlord_storage") and stockpile_manager is not None:
            sw = int(preset.get("storage_permit_width", 6) or 6)
            sh = int(preset.get("storage_permit_height", 6) or 6)
            zx, zy = cls._find_land_origin(
                sw, sh, used_tiles, building_manager, permit_manager, furniture_manager)
            if zx is not None:
                permit_manager.add_permit_rect("Starter Storage", "storage",
                                               zx, zy, sw, sh)
                cls._scatter_storage_items(
                    stockpile_manager, preset.get("storage_items") or {},
                    zx, zy, sw, sh)

        # 5) Treasury items (e.g. Gold) into the Lord Treasury chest.
        treasury_items = preset.get("treasury_items") or {}
        if treasury_items:
            chest = furniture_manager.get_lord_treasury_chest()
            if chest is not None:
                for item, amount in treasury_items.items():
                    chest.store_item(item, int(amount))

        return True

    @classmethod
    def _scatter_storage_items(cls, stockpile_manager, items, ox, oy, w, h):
        """Drop preset goods as loose landlord-owned stacks inside the storage
        yard, split into MAX_STACK_SIZE chunks and spread across tiles."""
        tiles = [(ox + dx, oy + dy) for dy in range(h) for dx in range(w)]
        idx = 0
        for item, amount in items.items():
            remaining = int(amount)
            while remaining > 0:
                gx, gy = tiles[idx % len(tiles)]
                idx += 1
                chunk = min(remaining, MAX_STACK_SIZE)
                stockpile_manager.drop_resource(
                    item, chunk, gx, gy, owner_type="landlord")
                remaining -= chunk

    @classmethod
    def _spawn_family_at_door(cls, family, door_tile):
        """Teleport preset family members to the front yard of their house.

        Family generators spawn members at random offsets around the world
        origin, which can land inside nearby starter structures (e.g. the
        market) and leave them stuck. Placing them at the door keeps the
        opening scene clean regardless of where the cluster was scanned."""
        dx, dy = door_tile
        base_x = (dx + 0.5) * TILE_SIZE
        base_y = (dy + 1.5) * TILE_SIZE  # one tile in front of the door
        for member in getattr(family, "members", []):
            member.x = base_x + random.uniform(-TILE_SIZE * 0.35, TILE_SIZE * 0.35)
            member.y = base_y + random.uniform(0, TILE_SIZE * 0.4)
            member.current_path = []
            member.path_index = 0
            member.task = "IDLE"

    @classmethod
    def _install_furniture(cls, furniture_manager, f_type, gx, gy,
                           permit_manager, villager_manager, building_manager):
        """Place furniture as a COMPLETED structure — starter presets never
        leave blueprints awaiting a carpenter commission."""
        f, msg = furniture_manager.add_furniture(
            f_type, gx, gy, permit_manager, villager_manager,
            building_manager=building_manager)
        if f is not None:
            f.construction_order = None
        return f

    @classmethod
    def _place_finished_building(cls, building_manager, building_type, tiles,
                                 door_pos=None, door_side="bottom"):
        from game.buildings.building import Building
        tiles = set(tiles)
        b = Building(building_type, tiles, door_pos=door_pos, door_side=door_side)
        building_manager.buildings.append(b)
        building_manager.rebuild_tile_cache()
        from game.world.pathfinding import GlobalPathRegistry
        GlobalPathRegistry.get_instance().reset()

    @classmethod
    def _find_land_origin(cls, w, h, used_tiles, building_manager, permit_manager,
                          furniture_manager=None):
        """Scan outward from the world origin for a w×h rect of land tiles that
        does not overlap existing permits, buildings, furniture, or previously
        placed starter zones."""
        max_ring = 200
        for ring in range(max_ring):
            candidates = []
            for gx in range(-ring, ring + 1):
                candidates.append((gx, -ring))
                candidates.append((gx, ring))
            for gy in range(-ring + 1, ring):
                candidates.append((-ring, gy))
                candidates.append((ring, gy))
            for ox, oy in candidates:
                rect = {(ox + dx, oy + dy) for dx in range(w) for dy in range(h)}
                if rect & used_tiles:
                    continue
                if any(not is_land_tile(tx, ty) for tx, ty in rect):
                    continue
                if cls._rect_blocked(rect, building_manager, permit_manager,
                                     furniture_manager):
                    continue
                return ox, oy
        return None, None

    @classmethod
    def _rect_blocked(cls, rect, building_manager, permit_manager, furniture_manager=None):
        for b in getattr(building_manager, "buildings", []):
            if getattr(b, "tiles", set()) & rect:
                return True
        for s in getattr(building_manager, "construction_sites", []):
            if getattr(s, "tiles", set()) & rect:
                return True
        for p in getattr(permit_manager, "permits", []):
            if p.overlaps_tiles(rect):
                return True
        if furniture_manager is not None:
            for f in getattr(furniture_manager, "furnitures", []):
                if getattr(f, "is_dropped", False) or getattr(f, "stored_in_id", None):
                    continue
                fw = getattr(f, "footprint_dimensions", (1, 1))
                f_tiles = {(f.grid_x + dx, f.grid_y + dy)
                           for dx in range(fw[0]) for dy in range(fw[1])}
                if f_tiles & rect:
                    return True
        return False
