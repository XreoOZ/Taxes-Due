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
from game.systems.currency import canonical_denomination, is_currency_item


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


def canonical_item_name(raw_name):
    """
    Returns the canonical display name for an item or resource without hardcoding logic.
    Uses existing TOOL_TYPES, CROP_TYPES, DEFAULT_RESOURCES, and CURRENCY definitions.
    Strips WIP tags to ensure only clean actual item names appear.
    """
    if not raw_name or not isinstance(raw_name, str):
        return ""
    name_str = raw_name.replace("(WIP)", "").replace("(wip)", "").strip()
    name_lower = name_str.lower()

    # 1. Check Tool Types
    for tool_id, tool_data in TOOL_TYPES.items():
        t_name = tool_data.get("name", tool_id).replace("(WIP)", "").replace("(wip)", "").strip()
        if name_lower in (tool_id.lower(), t_name.lower()):
            return t_name

    # Known tool aliases in codebase (legacy/multilingual)
    if name_lower == "cangkul":
        return TOOL_TYPES.get("Hoe", {}).get("name", "Hoe")
    if name_lower == "sabit":
        return TOOL_TYPES.get("Sickle", {}).get("name", "Sickle")
    if name_lower in ("siraman", "wateringcan", "watering_can"):
        return TOOL_TYPES.get("Watering_Can", {}).get("name", "Watering Can")

    # 2. Check Crop Types
    for crop_id, crop_data in CROP_TYPES.items():
        c_name = crop_data.get("name", crop_id.capitalize()).replace("(WIP)", "").replace("(wip)", "").strip()
        if name_lower in (crop_id.lower(), c_name.lower()):
            return c_name

    # 3. Check Currency Denominations
    c_denom = canonical_denomination(name_str)
    if c_denom:
        return c_denom

    # 4. Check Default Resources
    for res_id in DEFAULT_RESOURCES:
        if name_lower == res_id.lower():
            if res_id.lower() == "food":
                return "Potato"
            return res_id

    # 5. Generic fallback for future items (e.g. "bread" -> "Bread", "iron_ore" -> "Iron Ore")
    return name_str.replace("_", " ").title()


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
        # A. Hand / Bag Inventory
        m_inv = getattr(m, "inventory", {})
        if isinstance(m_inv, dict):
            for it_name, it_count in m_inv.items():
                _add_item(it_name, it_count)

        # B. Carried harvest crops
        carried_crop = getattr(m, "carrying_crop", 0)
        if carried_crop > 0:
            c_type = getattr(m, "crop_type", "Potato") or "Potato"
            _add_item(c_type, carried_crop)

        # C. Carried general resource
        carried_res = getattr(m, "carrying_res", None)
        carried_amt = getattr(m, "carrying_amount", 0)
        if carried_res and carried_amt > 0:
            _add_item(carried_res, carried_amt)

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
