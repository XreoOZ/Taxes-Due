"""
Cheat & Developer Utility System (AGENT 2 & AGENT 3 Integration)
Provides dynamic insertion of items into Storage (Chests or Stockpile Permits)
with full physical world representation and overflow drops near storage when full.
Zero hardcoding, config-driven.
"""

from game.data.config import MARKET_CURRENCY_DENOMINATIONS, MARKET_TRADEABLE_ITEMS, TOOL_TYPES
from game.world.stockpile import MAX_TILE_CAPACITY, is_food_item, is_water_item

CORE_RESOURCE_KEYS = ["Wood", "Food", "Stone", "Water", "Copper", "Silver", "Gold"]

def get_registered_item_types():
    """
    Return canonical items with active market/storage/tool behavior for the cheat UI.
    Union of the market trade catalog, currency denominations, and every
    defined tool type — TOOL_TYPES only contains implemented tools, so WIP
    gear stays out automatically.
    """
    return list(dict.fromkeys((
        *MARKET_TRADEABLE_ITEMS.keys(),
        *TOOL_TYPES.keys(),
        *MARKET_CURRENCY_DENOMINATIONS,
    )))

def clean_resources_dictionary(resources):
    """
    Prunes rogue non-core keys from the top-level resources dictionary,
    ensuring HUD and resource counters remain clean and uncorrupted.
    """
    if not isinstance(resources, dict):
        return
    rogue_keys = [k for k in list(resources.keys()) if k not in CORE_RESOURCE_KEYS]
    for k in rogue_keys:
        del resources[k]

def find_drop_tile_near_storage(permit_manager, building_manager=None, stockpile_manager=None, item_name="Wood"):
    """
    Finds the closest walkable open tile immediately adjacent to / outside storage permit boundaries.
    If no storage permits exist, searches outward from (0, 0).
    """
    storage_tiles = set()
    if permit_manager and hasattr(permit_manager, "permits"):
        for p in permit_manager.permits:
            if getattr(p, "permit_type", "") == "storage":
                storage_tiles.update(getattr(p, "tiles", []))

    # Existing stacks lookup
    occupied_tiles = {}
    if stockpile_manager and hasattr(stockpile_manager, "stacks"):
        for s in stockpile_manager.stacks:
            occupied_tiles[(s.grid_x, s.grid_y)] = s

    def is_tile_available(gx, gy):
        if (gx, gy) in storage_tiles:
            return False
        if building_manager and hasattr(building_manager, "get_building_at"):
            b = building_manager.get_building_at(gx, gy)
            if b and (getattr(b, "is_solid", False) or getattr(b, "building_type", "") == "well" or getattr(b, "is_wall", False)):
                return False
        # Check if tile has a stack
        if (gx, gy) in occupied_tiles:
            s = occupied_tiles[(gx, gy)]
            if s.resource_type != item_name or s.amount >= MAX_TILE_CAPACITY:
                return False
        return True

    # Search outward in expanding rings from storage permit perimeter
    if storage_tiles:
        for dist in range(1, 20):
            for (sx, sy) in storage_tiles:
                for dx in range(-dist, dist + 1):
                    for dy in range(-dist, dist + 1):
                        if max(abs(dx), abs(dy)) != dist:
                            continue
                        tx, ty = sx + dx, sy + dy
                        if is_tile_available(tx, ty):
                            return (tx, ty)

    # Fallback: search around origin (0, 0)
    for dist in range(1, 30):
        for dx in range(-dist, dist + 1):
            for dy in range(-dist, dist + 1):
                if max(abs(dx), abs(dy)) != dist:
                    continue
                if is_tile_available(dx, dy):
                    return (dx, dy)

    return (1, 1)

def find_drop_tile_near_chest(furniture, building_manager=None, stockpile_manager=None, item_name="Wood"):
    """
    Finds the closest open tile adjacent to a full storage chest to drop overflow items.
    """
    cx = getattr(furniture, "grid_x", 0)
    cy = getattr(furniture, "grid_y", 0)

    occupied_tiles = {}
    if stockpile_manager and hasattr(stockpile_manager, "stacks"):
        for s in stockpile_manager.stacks:
            occupied_tiles[(s.grid_x, s.grid_y)] = s

    for dist in range(1, 15):
        for dx in range(-dist, dist + 1):
            for dy in range(-dist, dist + 1):
                if max(abs(dx), abs(dy)) != dist:
                    continue
                tx, ty = cx + dx, cy + dy
                if building_manager and hasattr(building_manager, "get_building_at"):
                    b = building_manager.get_building_at(tx, ty)
                    if b and (getattr(b, "is_solid", False) or getattr(b, "is_wall", False)):
                        continue
                if (tx, ty) in occupied_tiles:
                    s = occupied_tiles[(tx, ty)]
                    if s.resource_type != item_name or s.amount >= MAX_TILE_CAPACITY:
                        continue
                return (tx, ty)

    return (cx + 1, cy)

def spawn_item_physically(item_name, amount, target_storage=None, stockpile_manager=None, permit_manager=None, resources=None, building_manager=None, furniture_manager=None):
    """
    Physically spawns a specific item and quantity into Storage:
    1. If target_storage is a Furniture (Chest):
       - Stores up to chest capacity.
       - If full, drops overflow physically on the ground near the chest!
    2. If target_storage is None (Landlord Storage):
       - Fills active Storage Permit lots physically up to MAX_TILE_CAPACITY (1000).
       - If storage permits are full (or none exist), drops physically on ground near the storage perimeter!
       - Synchronizes physical stacks and purges any rogue keys from resources.
    Returns (success: bool, message: str)
    """
    if amount <= 0:
        return False, "Quantity must be greater than 0."

    item_name = str(item_name).strip()
    if not item_name:
        return False, "Invalid item selected."

    # -------------------------------------------------------------------------
    # CASE 1: TARGET IS A HOUSEHOLD CHEST (FURNITURE)
    # -------------------------------------------------------------------------
    if target_storage is not None and hasattr(target_storage, "store_item"):
        capacity = getattr(target_storage, "type_cfg", {}).get("capacity", 500)
        curr_stored = getattr(target_storage, "total_stored", sum(getattr(target_storage, "inventory", {}).values()))
        available_space = max(0, capacity - curr_stored)

        chest_name = getattr(target_storage, "name", "Storage Chest")
        owner_id = getattr(target_storage, "family_id", None)
        owner_type = "villager" if owner_id else "landlord"

        if amount <= available_space:
            target_storage.store_item(item_name, amount)
            new_total = curr_stored + amount
            return True, f"Stored {amount}x {item_name} in {chest_name} ({new_total}/{capacity})."
        else:
            # Chest capacity exceeded -> Store partial, drop overflow on ground near chest!
            stored_qty = available_space
            if stored_qty > 0:
                target_storage.store_item(item_name, stored_qty)

            overflow_qty = amount - stored_qty
            if stockpile_manager:
                drop_tile = find_drop_tile_near_chest(target_storage, building_manager, stockpile_manager, item_name)
                stockpile_manager.drop_resource(item_name, overflow_qty, drop_tile[0], drop_tile[1], owner_type=owner_type, owner_id=owner_id)
                return True, (
                    f"{chest_name} Full ({capacity}/{capacity})! Stored {stored_qty}x {item_name} in chest "
                    f"and dropped {overflow_qty}x on ground near chest at ({drop_tile[0]}, {drop_tile[1]})!"
                )
            else:
                return True, f"Stored {stored_qty}x {item_name} in {chest_name} (Full! Overflow: {overflow_qty}x lost: no stockpile)."

    # -------------------------------------------------------------------------
    # CASE 2: TARGET IS LANDLORD STORAGE / STOCKPILE PERMIT
    # -------------------------------------------------------------------------
    # Currency granted to the landlord goes straight into the Lord Treasury
    # Chest (auto-created if missing) instead of loose ground stacks.
    if furniture_manager is not None:
        from game.systems.economy.currency import canonical_denomination, is_currency_item
        from game.systems.economy.lord_treasury import LordTreasurySystem
        if is_currency_item(item_name):
            chest = None
            if hasattr(furniture_manager, "ensure_lord_treasury_chest"):
                chest = furniture_manager.ensure_lord_treasury_chest(
                    permit_manager=permit_manager,
                    building_manager=building_manager,
                    stockpile_manager=stockpile_manager,
                )
            if chest is None:
                chest = LordTreasurySystem.get_chest(furniture_manager)
            if chest is not None:
                LordTreasurySystem.deposit_all(furniture_manager, {item_name: amount})
                denom = canonical_denomination(item_name)
                return True, f"Deposited {amount}x {denom} into the Lord Treasury Chest."

    if stockpile_manager is not None:
        remaining_to_place = amount
        placed_in_storage = 0
        placed_near_storage = 0
        last_drop_pos = None

        while remaining_to_place > 0:
            # Check for available slot inside an official storage permit lot
            tile = None
            if permit_manager:
                tile = stockpile_manager.get_available_storage_tile(permit_manager, item_name)

            if tile is not None:
                # Place inside storage permit
                stack = stockpile_manager.get_stack_at(tile[0], tile[1])
                space_in_tile = (MAX_TILE_CAPACITY - stack.amount) if stack else MAX_TILE_CAPACITY
                qty_to_drop = min(remaining_to_place, space_in_tile)

                stockpile_manager.drop_resource(item_name, qty_to_drop, tile[0], tile[1], owner_type="landlord")
                remaining_to_place -= qty_to_drop
                placed_in_storage += qty_to_drop
                last_drop_pos = tile
            else:
                # STORAGE PERMIT IS FULL OR NONE EXIST!
                # "KALAU STORAGE NYA PENUH, DROP NEAR THE STORAGE!"
                near_tile = find_drop_tile_near_storage(permit_manager, building_manager, stockpile_manager, item_name)
                stack = stockpile_manager.get_stack_at(near_tile[0], near_tile[1])
                space_in_tile = (MAX_TILE_CAPACITY - stack.amount) if stack else MAX_TILE_CAPACITY
                qty_to_drop = min(remaining_to_place, space_in_tile)

                stockpile_manager.drop_resource(item_name, qty_to_drop, near_tile[0], near_tile[1], owner_type="landlord")
                remaining_to_place -= qty_to_drop
                placed_near_storage += qty_to_drop
                last_drop_pos = near_tile

        # Synchronize physical stacks to landlord resources
        if resources is not None:
            stockpile_manager.refresh_stacks(resources, permit_manager)
            clean_resources_dictionary(resources)

        if placed_near_storage > 0:
            if placed_in_storage > 0:
                return True, (
                    f"Storage permit filled! Added {placed_in_storage}x into storage, "
                    f"and dropped {placed_near_storage}x {item_name} near storage at ({last_drop_pos[0]}, {last_drop_pos[1]})!"
                )
            else:
                return True, (
                    f"Storage permit full/absent! Dropped {placed_near_storage}x {item_name} "
                    f"physically on ground near storage at ({last_drop_pos[0]}, {last_drop_pos[1]})!"
                )
        else:
            return True, f"Physically added {placed_in_storage}x {item_name} to Storage Permit Lot at ({last_drop_pos[0]}, {last_drop_pos[1]})!"

    # Fallback if no stockpile manager
    return False, "Stockpile manager is not available."

def apply_add_item_cheat(target_storage=None, amount=50, resources=None, stockpile_manager=None, permit_manager=None, building_manager=None):
    """
    Legacy wrapper: spawns default item physically into storage.
    """
    return spawn_item_physically(
        item_name="Potato",
        amount=amount,
        target_storage=target_storage,
        stockpile_manager=stockpile_manager,
        permit_manager=permit_manager,
        resources=resources,
        building_manager=building_manager
    )
