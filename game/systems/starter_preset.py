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

from game.data.config import STARTER_PRESETS, MAX_STACK_SIZE, TILE_SIZE, BUILDING_TYPES
from game.world.island import is_land_tile


class StarterPresetSystem:
    @classmethod
    def get_preset(cls, preset_id):
        return next((p for p in STARTER_PRESETS if p.get("id") == preset_id), None)

    @classmethod
    def apply(cls, preset_id, villager_manager, furniture_manager,
              building_manager, permit_manager, stockpile_manager=None,
              anchor_tile=None):
        """Materialize a starter preset on a fresh game world.

        ``anchor_tile`` = house-center tile picked by the player; when given,
        zone positions come from the preset's ``cluster`` offsets and every
        rect must validate or nothing is placed. Without it, zones are
        auto-scanned outward from the world origin.

        Returns True on success; disabled/unknown/invalid presets return False.
        """
        preset = cls.get_preset(preset_id)
        if not preset or not preset.get("enabled"):
            return False
        if not all([villager_manager, furniture_manager, building_manager, permit_manager]):
            return False

        pad = int(preset.get("permit_padding", 0) or 0)
        zones = cls._resolve_zones(preset, anchor_tile,
                                   building_manager, permit_manager, furniture_manager)
        if zones is None:
            return False

        # 1) Starter household (size comes from the preset).
        family = villager_manager.generate_starter_family(
            size=preset.get("family_size"))

        # 2) Housing permit (exactly the house footprint) + finished house.
        house_cfg = preset.get("house")
        if house_cfg and "house" in zones:
            hw, hh = int(house_cfg["width"]), int(house_cfg["height"])
            zx, zy, zw, zh = zones["house"]
            hx, hy = zx + pad, zy + pad
            house_permit = permit_manager.add_permit_rect(
                "Starter Housing", "housing", zx, zy, zw, zh)
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
        if market_cfg and "market" in zones:
            mw, mh = int(market_cfg["width"]), int(market_cfg["height"])
            zx, zy, zw, zh = zones["market"]
            mx, my = zx + pad, zy + pad
            permit_manager.add_permit_rect(
                "Starter Market", "market", zx, zy, zw, zh)
            cls._place_finished_building(
                building_manager, market_cfg["building_type"],
                {(mx + dx, my + dy) for dx in range(mw) for dy in range(mh)})

        # 3b) Farm permit — bare deed; farmers sow/tend it once assigned.
        farm_cfg = preset.get("farm")
        if farm_cfg and "farm" in zones:
            zx, zy, zw, zh = zones["farm"]
            permit_manager.add_permit_rect("Starter Farm", "farm", zx, zy, zw, zh)

        # 3c) Extra prop buildings (toilet, well, ...) placed relative to the
        # house and installed instantly — never blueprints.
        for prop in ((preset.get("cluster") or {}).get("props")) or []:
            zkey = f"prop_{prop.get('building')}"
            if zkey not in zones:
                continue
            zx, zy, zw, zh = zones[zkey]
            cls._place_finished_building(
                building_manager, prop.get("building"),
                {(zx + dx, zy + dy) for dx in range(zw) for dy in range(zh)})

        # 4) Landlord storage yard: permit-sized area filled with loose
        # landlord-owned item stacks (the player's physical storage).
        if preset.get("landlord_storage") and "storage" in zones and stockpile_manager is not None:
            zx, zy, zw, zh = zones["storage"]
            permit_manager.add_permit_rect("Starter Storage", "storage",
                                           zx, zy, zw, zh)
            # Keep prop-building footprints (e.g. the well) free of item stacks.
            prop_tiles = set()
            for prop in ((preset.get("cluster") or {}).get("props")) or []:
                zkey = f"prop_{prop.get('building')}"
                if zkey in zones:
                    px, py, pw, ph = zones[zkey]
                    prop_tiles.update((px + dx, py + dy)
                                      for dx in range(pw) for dy in range(ph))
            cls._scatter_storage_items(
                stockpile_manager, preset.get("storage_items") or {},
                zx, zy, zw, zh, exclude_tiles=prop_tiles)

            # Lord Treasury chest belongs to the landlord — park it on open
            # ground beside the storage yard, never on storage tiles.
            if preset.get("treasury_chest_spot") == "beside_storage":
                treasury = furniture_manager.get_lord_treasury_chest()
                if treasury is not None:
                    spot = cls._find_free_tile_beside(
                        zx, zy, zw, zh, building_manager, permit_manager,
                        furniture_manager)
                    if spot is not None:
                        sx, sy = spot
                        spot_permit = permit_manager.get_permit_at(sx, sy)
                        treasury.move_to(
                            sx, sy,
                            new_permit_id=getattr(spot_permit, "id", None))

        # 5) Treasury items (e.g. Gold) into the Lord Treasury chest.
        treasury_items = preset.get("treasury_items") or {}
        if treasury_items:
            chest = furniture_manager.get_lord_treasury_chest()
            if chest is not None:
                for item, amount in treasury_items.items():
                    chest.store_item(item, int(amount))

        return True

    @classmethod
    def _resolve_zones(cls, preset, anchor_tile, building_manager,
                       permit_manager, furniture_manager):
        """Return {zone_name: (x, y, w, h)} permit rects, or None if the
        chosen/auto-scanned layout cannot be placed."""
        if anchor_tile is not None:
            zones = cls.cluster_zone_rects(preset, anchor_tile)
            ok, _ = cls.validate_cluster(zones, building_manager,
                                         permit_manager, furniture_manager)
            return zones if ok else None
        return cls._scan_zones(preset, building_manager, permit_manager,
                               furniture_manager)

    @classmethod
    def get_anchor_preview(cls, preset_id, anchor_tile,
                           building_manager, permit_manager, furniture_manager=None):
        """Ghost-preview helper for the placement UI: returns
        ({zone_name: (x, y, w, h)}, valid_bool) without mutating the world."""
        preset = cls.get_preset(preset_id)
        if not preset or anchor_tile is None:
            return {}, False
        zones = cls.cluster_zone_rects(preset, anchor_tile)
        ok, _ = cls.validate_cluster(zones, building_manager,
                                     permit_manager, furniture_manager)
        return zones, ok

    @classmethod
    def cluster_zone_rects(cls, preset, anchor_tile):
        """Pure geometry for player-picked placement.

        ``anchor_tile`` is the HOUSE-CENTER tile; the house sits at
        anchor - (w/2, h/2) and every other zone is offset from the house
        top-left via the preset's ``cluster`` config block."""
        house_cfg = preset.get("house") or {}
        hw, hh = int(house_cfg.get("width", 0) or 0), int(house_cfg.get("height", 0) or 0)
        if hw <= 0 or hh <= 0:
            return {}
        ax, ay = anchor_tile
        hx, hy = ax - hw // 2, ay - hh // 2
        cluster = preset.get("cluster") or {}
        zones = {}

        def _zone(name):
            off = cluster.get(name) or {}
            return hx + int(off.get("dx", 0) or 0), hy + int(off.get("dy", 0) or 0)

        zones["house"] = (hx, hy, hw, hh)
        if preset.get("market"):
            mc = preset["market"]
            mx, my = _zone("market")
            zones["market"] = (mx, my, int(mc["width"]), int(mc["height"]))
        if preset.get("landlord_storage"):
            sx, sy = _zone("storage")
            zones["storage"] = (sx, sy,
                                int(preset.get("storage_permit_width", 6) or 6),
                                int(preset.get("storage_permit_height", 6) or 6))
        if preset.get("farm"):
            fx, fy = _zone("farm")
            fc = preset["farm"]
            zones["farm"] = (fx, fy, int(fc["width"]), int(fc["height"]))
        for prop in cluster.get("props") or []:
            bcfg = BUILDING_TYPES.get(prop.get("building")) or {}
            fw = int(bcfg.get("width_tiles", 1) or 1)
            fh = int(bcfg.get("height_tiles", 1) or 1)
            zones[f"prop_{prop.get('building')}"] = (
                hx + int(prop.get("dx", 0) or 0),
                hy + int(prop.get("dy", 0) or 0), fw, fh)
        return zones

    @classmethod
    def validate_cluster(cls, zones, building_manager, permit_manager,
                         furniture_manager=None):
        """All zone rects must be land and clear of existing
        permits/buildings/furniture. Permit zones may not overlap each
        other; ``prop_*`` zones (toilet, well, ...) may sit INSIDE a permit
        zone (e.g. the well inside the storage yard) but not on each other.
        Returns (ok, bad_zone)."""
        seen_permits = set()
        seen_props = set()
        for name, (x, y, w, h) in zones.items():
            rect = {(x + dx, y + dy) for dx in range(w) for dy in range(h)}
            if name.startswith("prop_"):
                if rect & seen_props:
                    return False, name
                seen_props |= rect
            else:
                if rect & seen_permits:
                    return False, name
                seen_permits |= rect
            if any(not is_land_tile(tx, ty) for tx, ty in rect):
                return False, name
            if cls._rect_blocked(rect, building_manager, permit_manager,
                                 furniture_manager):
                return False, name
        return True, None

    @classmethod
    def _scan_zones(cls, preset, building_manager, permit_manager,
                    furniture_manager):
        """Auto-scan fallback: find each zone independently outward from the
        world origin (used when the player does not pick a location)."""
        pad = int(preset.get("permit_padding", 0) or 0)
        used_tiles = set()
        zones = {}

        house_cfg = preset.get("house")
        if house_cfg:
            hw, hh = int(house_cfg["width"]), int(house_cfg["height"])
            zx, zy = cls._find_land_origin(
                hw + pad * 2, hh + pad * 2, used_tiles,
                building_manager, permit_manager, furniture_manager)
            if zx is None:
                return None
            zones["house"] = (zx, zy, hw + pad * 2, hh + pad * 2)
            used_tiles.update((gx, gy)
                              for gx in range(zx, zx + hw + pad * 2)
                              for gy in range(zy, zy + hh + pad * 2))

        market_cfg = preset.get("market")
        if market_cfg:
            mw, mh = int(market_cfg["width"]), int(market_cfg["height"])
            zx, zy = cls._find_land_origin(
                mw + pad * 2, mh + pad * 2, used_tiles,
                building_manager, permit_manager, furniture_manager)
            if zx is not None:
                zones["market"] = (zx, zy, mw + pad * 2, mh + pad * 2)
                used_tiles.update((gx, gy)
                                  for gx in range(zx, zx + mw + pad * 2)
                                  for gy in range(zy, zy + mh + pad * 2))

        farm_cfg = preset.get("farm")
        if farm_cfg:
            fw, fh = int(farm_cfg["width"]), int(farm_cfg["height"])
            zx, zy = cls._find_land_origin(
                fw, fh, used_tiles, building_manager, permit_manager,
                furniture_manager)
            if zx is not None:
                zones["farm"] = (zx, zy, fw, fh)
                used_tiles.update((gx, gy)
                                  for gx in range(zx, zx + fw)
                                  for gy in range(zy, zy + fh))

        if preset.get("landlord_storage"):
            sw = int(preset.get("storage_permit_width", 6) or 6)
            sh = int(preset.get("storage_permit_height", 6) or 6)
            zx, zy = cls._find_land_origin(
                sw, sh, used_tiles, building_manager, permit_manager,
                furniture_manager)
            if zx is not None:
                zones["storage"] = (zx, zy, sw, sh)

        # Props are defined relative to the house top-left; in scan mode the
        # house zone is already resolved, so anchor them there and keep only
        # the ones that land on valid free tiles.
        if "house" in zones:
            hx, hy = zones["house"][0] + pad, zones["house"][1] + pad
            cluster = preset.get("cluster") or {}
            for prop in cluster.get("props") or []:
                bcfg = BUILDING_TYPES.get(prop.get("building")) or {}
                fw = int(bcfg.get("width_tiles", 1) or 1)
                fh = int(bcfg.get("height_tiles", 1) or 1)
                px = hx + int(prop.get("dx", 0) or 0)
                py = hy + int(prop.get("dy", 0) or 0)
                rect = {(px + dx, py + dy) for dx in range(fw) for dy in range(fh)}
                if rect & used_tiles:
                    continue
                if any(not is_land_tile(tx, ty) for tx, ty in rect):
                    continue
                if cls._rect_blocked(rect, building_manager, permit_manager,
                                     furniture_manager):
                    continue
                zones[f"prop_{prop.get('building')}"] = (px, py, fw, fh)

        return zones

    @classmethod
    def _find_free_tile_beside(cls, zx, zy, zw, zh, building_manager,
                               permit_manager, furniture_manager):
        """First free 1x1 tile adjacent to a zone rect, scanning the right
        edge first, then bottom, left, and top. Used to park the Lord
        Treasury chest beside the storage yard on open ground."""
        candidates = (
            [(zx + zw, y) for y in range(zy, zy + zh)]
            + [(x, zy + zh) for x in range(zx, zx + zw)]
            + [(zx - 1, y) for y in range(zy + zh - 1, zy - 1, -1)]
            + [(x, zy - 1) for x in range(zx + zw - 1, zx - 1, -1)]
        )
        for cx, cy in candidates:
            if not is_land_tile(cx, cy):
                continue
            if cls._rect_blocked({(cx, cy)}, building_manager, permit_manager,
                                 furniture_manager):
                continue
            return cx, cy
        return None

    @classmethod
    def _scatter_storage_items(cls, stockpile_manager, items, ox, oy, w, h,
                               exclude_tiles=None):
        """Drop preset goods as loose landlord-owned stacks inside the storage
        yard, split into MAX_STACK_SIZE chunks and spread across tiles."""
        skip = exclude_tiles or set()
        tiles = [(ox + dx, oy + dy) for dy in range(h) for dx in range(w)
                 if (ox + dx, oy + dy) not in skip]
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
