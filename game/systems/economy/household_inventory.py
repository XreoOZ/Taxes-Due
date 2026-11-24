"""
Household Inventory & Possession System (Config-Driven, Zero Hardcode)
Single Source of Truth for settler household belongings across chests,
ground stacks, member inventories, and in-transit royal grants.
"""
from game.data.config import (
    TOOL_TYPES,
    CROP_TYPES,
    DEFAULT_RESOURCES,
    CURRENCY_DENOMINATIONS
)
from game.systems.economy.currency import canonical_denomination, is_currency_item


def get_inventory_load(inventory):
    """Count carried goods against item capacity while keeping currency stackable."""
    if not isinstance(inventory, dict):
        return 0
    return sum(
        max(0, int(amount))
        for item, amount in inventory.items()
        if not canonical_denomination(item)
    )


def get_inventory_room(inventory, capacity):
    """Return remaining item capacity using the same rules for every AI workflow."""
    return max(0, int(capacity) - get_inventory_load(inventory))


_CANONICAL_ITEM_NAME_CACHE = {}

def canonical_item_name(raw_name):
    """
    Returns the canonical display name for an item or resource without hardcoding logic.
    Uses existing TOOL_TYPES, CROP_TYPES, DEFAULT_RESOURCES, and CURRENCY definitions.
    Strips WIP tags to ensure only clean actual item names appear.
    """
    if not raw_name or not isinstance(raw_name, str):
        return ""
    cached = _CANONICAL_ITEM_NAME_CACHE.get(raw_name)
    if cached is not None:
        return cached

    name_str = raw_name.replace("(WIP)", "").replace("(wip)", "").strip()
    name_lower = name_str.lower()

    result = None
    # 1. Check Tool Types
    for tool_id, tool_data in TOOL_TYPES.items():
        t_name = tool_data.get("name", tool_id).replace("(WIP)", "").replace("(wip)", "").strip()
        if name_lower in (tool_id.lower(), t_name.lower()):
            result = t_name
            break

    # Known tool aliases in codebase (legacy/multilingual)
    if result is None:
        if name_lower == "cangkul":
            result = TOOL_TYPES.get("Hoe", {}).get("name", "Hoe")
        elif name_lower == "sabit":
            result = TOOL_TYPES.get("Sickle", {}).get("name", "Sickle")
        elif name_lower in ("siraman", "wateringcan", "watering_can"):
            result = TOOL_TYPES.get("Watering_Can", {}).get("name", "Watering Can")

    # 2. Check Crop Types
    if result is None:
        for crop_id, crop_data in CROP_TYPES.items():
            c_name = crop_data.get("name", crop_id.capitalize()).replace("(WIP)", "").replace("(wip)", "").strip()
            if name_lower in (crop_id.lower(), c_name.lower()):
                result = c_name
                break

    # 3. Check Currency Denominations
    if result is None:
        c_denom = canonical_denomination(name_str)
        if c_denom:
            result = c_denom

    # 4. Check Default Resources
    if result is None:
        for res_id in DEFAULT_RESOURCES:
            if name_lower == res_id.lower():
                result = "Potato" if res_id.lower() == "food" else res_id
                break

    # 5. Generic fallback for future items (e.g. "bread" -> "Bread", "iron_ore" -> "Iron Ore")
    if result is None:
        result = name_str.replace("_", " ").title()

    if len(_CANONICAL_ITEM_NAME_CACHE) > 512:
        _CANONICAL_ITEM_NAME_CACHE.clear()
    _CANONICAL_ITEM_NAME_CACHE[raw_name] = result
    return result


def get_household_possessions(fam, furniture_manager=None, stockpile_manager=None, servant_manager=None):
    """
    Aggregates all items, tools, resources, and currency possessed by a household.
    Single Source of Truth reading directly from existing storage chests, ground stacks,
    villager member inventories, and in-transit royal grants.
    Returns: dict of {canonical_item_name: quantity} where quantity > 0.
    """
    if not fam:
        return {}

    possessions = {}
    fam_id_str = str(getattr(fam, "id", ""))
    member_ids = {str(m.id) for m in getattr(fam, "members", [])} if hasattr(fam, "members") else set()

    def _add_item(raw_name, count):
        if not raw_name or count is None:
            return
        try:
            cnt = int(count)
        except (ValueError, TypeError):
            return
        if cnt <= 0:
            return
        c_name = canonical_item_name(raw_name)
        if c_name:
            possessions[c_name] = possessions.get(c_name, 0) + cnt

    # 1. Household Storage Furniture (Chests)
    if furniture_manager:
        visited_chests = set()
        furn_list = getattr(furniture_manager, "furnitures", getattr(furniture_manager, "furniture_list", []))
        for f in furn_list:
            if str(getattr(f, "family_id", "")) == fam_id_str and hasattr(f, "inventory") and isinstance(f.inventory, dict):
                visited_chests.add(id(f))
                for it_name, it_count in f.inventory.items():
                    _add_item(it_name, it_count)

        # In case the designated storage chest has not had family_id explicitly assigned yet
        if hasattr(furniture_manager, "get_storage_for_family"):
            st = furniture_manager.get_storage_for_family(fam_id_str)
            if st and id(st) not in visited_chests and hasattr(st, "inventory") and isinstance(st.inventory, dict):
                visited_chests.add(id(st))
                for it_name, it_count in st.inventory.items():
                    _add_item(it_name, it_count)

    # 2. Ground Item Stacks owned by the family or its members
    if stockpile_manager:
        for s in getattr(stockpile_manager, "stacks", []):
            if getattr(s, "owner_type", None) == "villager":
                s_owner = str(getattr(s, "owner_id", ""))
                if s_owner == fam_id_str or s_owner in member_ids:
                    amt = getattr(s, "amount", 0)
                    r_type = getattr(s, "resource_type", None)
                    _add_item(r_type, amt)

    # 3. Personal AI Villager Inventory & Carried Items
    for m in getattr(fam, "members", []):
        counted_inventory = {}
        # A. Hand / Bag Inventory
        m_inv = getattr(m, "inventory", {})
        if isinstance(m_inv, dict):
            for it_name, it_count in m_inv.items():
                if it_count and int(it_count) > 0:
                    _add_item(it_name, it_count)
                    c_name = canonical_item_name(it_name)
                    if c_name:
                        counted_inventory[c_name] = counted_inventory.get(c_name, 0) + int(it_count)

        # B. Carried harvest crops (only count surplus not already represented in inventory)
        carried_crop = getattr(m, "carrying_crop", 0)
        if carried_crop > 0:
            c_type = getattr(m, "crop_type", "Potato") or "Potato"
            canon_c = canonical_item_name(c_type)
            extra_crop = max(0, carried_crop - counted_inventory.get(canon_c, 0))
            if extra_crop > 0:
                _add_item(c_type, extra_crop)

        # C. Carried general resource (only count surplus not already represented in inventory)
        carried_res = getattr(m, "carrying_res", None)
        carried_amt = getattr(m, "carrying_amount", 0)
        if carried_res and carried_amt > 0:
            canon_r = canonical_item_name(carried_res)
            extra_res = max(0, carried_amt - counted_inventory.get(canon_r, 0))
            if extra_res > 0:
                _add_item(carried_res, extra_res)

    # 4. In-Transit Deliveries by Royal Servants (Grant Items)
    if servant_manager:
        for s in getattr(servant_manager, "servants", []):
            if getattr(s, "state", "") == "GRANT_DELIVER" and str(getattr(s, "target_grant_fam_id", "")) == fam_id_str:
                res_name = getattr(s, "carried_res", "")
                amt = getattr(s, "carried_amount", 0)
                _add_item(res_name, amt)

    # 5. Direct Family Attributes (Fallback / Standalone Funds)
    if hasattr(fam, "inventory") and isinstance(fam.inventory, dict):
        for it_name, it_count in fam.inventory.items():
            _add_item(it_name, it_count)

    if hasattr(fam, "currency") and isinstance(fam.currency, dict):
        for c_name, c_count in fam.currency.items():
            _add_item(c_name, c_count)
    elif hasattr(fam, "coins") and getattr(fam, "coins", 0) > 0:
        _add_item("Copper", fam.coins)
    elif hasattr(fam, "currency_balance") and getattr(fam, "currency_balance", 0) > 0:
        _add_item("Copper", fam.currency_balance)

    # Return only positive possessed items
    return {k: v for k, v in possessions.items() if v > 0}


def sort_possession_items(possessions_dict):
    """
    Sorts possessed items into a logical, aesthetic order:
    1. Crops & Food (e.g. Potato)
    2. Tools (e.g. Hoe, Sickle, Watering Can)
    3. Drinking Water (Water)
    4. Building Materials & Goods (e.g. Wood, Stone)
    5. Currency Denominations (Copper, Silver, Gold)
    6. Generic / Future items alphabetically
    """
    if not possessions_dict:
        return []

    def _sort_key(item_tuple):
        name, _ = item_tuple
        name_lower = name.lower()

        # 1. Food / Crops
        for crop_id, crop_data in CROP_TYPES.items():
            if name_lower in (crop_id.lower(), crop_data.get("name", "").lower(), "food"):
                return (1, name)

        # 2. Tools
        for tool_id, tool_data in TOOL_TYPES.items():
            if name_lower in (tool_id.lower(), tool_data.get("name", "").lower()):
                return (2, name)

        # 3. Water
        if name_lower == "water":
            return (3, name)

        # 4. Resources / Materials
        if name in DEFAULT_RESOURCES and not is_currency_item(name):
            return (4, name)

        # 5. Currency Denominations
        if is_currency_item(name):
            order = {"copper": 1, "silver": 2, "gold": 3}
            c_name = canonical_denomination(name) or name
            return (5, order.get(c_name.lower(), 4), name)

        # 6. Future items
        return (6, name)

    sorted_items = sorted(possessions_dict.items(), key=_sort_key)
    return [{"name": name, "count": count} for name, count in sorted_items if count > 0]
