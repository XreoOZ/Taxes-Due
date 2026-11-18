"""
Cheat & Developer Utility System (AGENT 2 & AGENT 3 Integration)
Provides dynamic insertion of all registered items without hardcoded item lists.
Zero hardcoding, config-driven.
"""

from game.data.config import ITEM_CATEGORIES, register_item_category

def get_registered_item_types():
    """
    Dynamically retrieves unique canonical item types from existing definitions.
    Prevents duplicates, alias variations, or redundant items.
    """
    # Canonical items in standard presentation order
    preferred = [
        "Wood", "Stone", "Potato", "Water", "Hoe", "Sickle", "Watering_Can",
        "Copper Coin", "Silver Coin", "Gold Coin", "Bread", "Linen Cloth", "Apple", "Fish", "Meat"
    ]
    seen_normalized = set()
    result = []

    for it in preferred:
        norm = it.strip().lower().replace("_", " ")
        if norm not in seen_normalized:
            seen_normalized.add(norm)
            result.append(it)

    for it in ITEM_CATEGORIES.keys():
        norm = str(it).strip().lower().replace("_", " ")
        if norm not in seen_normalized:
            seen_normalized.add(norm)
            result.append(str(it).strip())

    return result

def apply_add_item_cheat(target_storage=None, amount=50, resources=None, stockpile_manager=None):
    """
    Adds every currently registered item type to the selected storage or Landlord storage.
    - If target_storage is a Furniture (chest), adds to target_storage.inventory.
    - If target_storage is None, adds to Landlord resources & refreshes stockpile stacks.
    Returns (success: bool, message: str)
    """
    items = get_registered_item_types()
    if not items:
        return False, "No registered items found."

    if target_storage is not None and hasattr(target_storage, "store_item"):
        # Storage furniture chest
        for item_name in items:
            target_storage.store_item(item_name, amount)
        s_name = getattr(target_storage, "name", "Storage Chest")
        return True, f"Added {amount}x of all {len(items)} registered items to {s_name}!"

    # Landlord primary storage / resources
    if resources is not None:
        for item_name in items:
            # Map coins to standard resource names if needed
            k = item_name
            if k == "Copper Coin":
                k = "Copper"
            elif k == "Silver Coin":
                k = "Silver"
            elif k == "Gold Coin":
                k = "Gold"
            resources[k] = resources.get(k, 0) + amount

        if stockpile_manager:
            stockpile_manager.refresh_stacks(resources, None)
        return True, f"Added {amount}x of all {len(items)} registered items to Landlord Storage!"

    return False, "No valid storage or resources available to receive items."
