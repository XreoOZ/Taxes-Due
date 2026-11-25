"""
Village Alerts & Notice Board Aggregator (Single Source of Truth).
Architecture:
- Reads live state from VillagerManager, PermitManager, BuildingManager,
  FurnitureManager, StockpileManager, and ImmigrationSystem.
- Consumed identically by both the in-game right-side Notice Board HUD
  and the Town Hall Action Center inside the Town Ledger.
"""

from game.data.config import DEDICATED_JOBS, TILE_SIZE
from game.systems.economy.currency import canonical_denomination, to_copper
from game.systems.economy.household_inventory import (
    canonical_item_name,
    get_household_possessions,
)
from game.systems.village_life.immigration_system import (
    STATE_WAITING,
    get_immigration_system,
)
from game.systems.work.job_tool_system import get_missing_tools_for_worker


_IDLE_JOBS = ("Unassigned", "Unemployed", "Peasant", None, "")
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def collect_village_alerts(
    villager_manager=None,
    permit_manager=None,
    building_manager=None,
    furniture_manager=None,
    stockpile_manager=None,
    servant_manager=None,
):
    """Collect sorted, actionable alerts describing urgent village and household needs."""
    alerts = []

    # 1. Waiting immigrants at Notice Board
    imm = get_immigration_system()
    waiting_imm = [q for q in getattr(imm, "queue", []) if q.get("state") == STATE_WAITING]
    if waiting_imm:
        alerts.append({
            "id": "immigration_waiting",
            "severity": "info",
            "category": "immigration",
            "title": f"{len(waiting_imm)} Immigrant Family Waiting",
            "hint": "Accept or review newcomers at the Notice Board.",
            "action_label": "Review",
            "action_type": "OPEN_IMMIGRANT",
            "target_id": None,
        })

    # 2. Broken public / village structures needing urgent repair
    for b in getattr(building_manager, "buildings", []) if building_manager else []:
        if getattr(b, "is_broken", False):
            b_name = getattr(b, "type_cfg", {}).get("name", getattr(b, "building_type", "Structure"))
            gx = getattr(b, "grid_x", 0)
            gy = getattr(b, "grid_y", 0)
            alerts.append({
                "id": f"repair_bldg:{getattr(b, 'id', id(b))}",
                "severity": "critical",
                "category": "repair",
                "title": f"{b_name} Needs Repair!",
                "hint": "Structure is broken. Ensure a Builder is staffed with Wood & Stone.",
                "action_label": "Locate",
                "action_type": "FOCUS_TILE",
                "target_id": (gx * TILE_SIZE, gy * TILE_SIZE),
            })

    for f in getattr(furniture_manager, "furnitures", []) if furniture_manager else []:
        if getattr(f, "is_broken", False) and not getattr(f, "is_dropped", False):
            f_name = getattr(f, "type_cfg", {}).get("name", getattr(f, "furniture_type", "Fixture"))
            gx = getattr(f, "grid_x", 0)
            gy = getattr(f, "grid_y", 0)
            alerts.append({
                "id": f"repair_furn:{getattr(f, 'id', id(f))}",
                "severity": "critical",
                "category": "repair",
                "title": f"{f_name} Needs Repair!",
                "hint": "Fixture is broken. Ensure a Builder is staffed.",
                "action_label": "Locate",
                "action_type": "FOCUS_TILE",
                "target_id": (gx * TILE_SIZE, gy * TILE_SIZE),
            })

    # 3. Household-level checks (House, Coins, Food, Tools)
    families = getattr(villager_manager, "families", []) if villager_manager else []
    total_living = 0
    total_household_water = 0

    for fam in families:
        living_members = [m for m in getattr(fam, "members", []) if getattr(m, "is_alive", True)]
        if not living_members:
            continue
        total_living += len(living_members)

        # A. Missing House Deed
        if not getattr(fam, "assigned_permit_id", None):
            alerts.append({
                "id": f"homeless:{fam.id}",
                "severity": "warning",
                "category": "housing",
                "title": f"The {fam.surname}s: No House",
                "hint": "Assign a Housing Permit so this family has shelter & storage.",
                "action_label": "Assign House",
                "action_type": "OPEN_HOUSEHOLD",
                "target_id": fam.id,
            })

        possessions = get_household_possessions(
            fam, furniture_manager, stockpile_manager, servant_manager
        )
        wallet = {
            canonical_denomination(k): v
            for k, v in possessions.items()
            if canonical_denomination(k)
        }
        total_copper = to_copper(wallet)

        # B. Out of Coins (0c)
        if total_copper <= 0:
            alerts.append({
                "id": f"no_coins:{fam.id}",
                "severity": "warning",
                "category": "currency",
                "title": f"The {fam.surname}s: Out of Coins",
                "hint": "0 Copper remaining. Send a Royal Grant so they can buy food/tools.",
                "action_label": "Send Grant",
                "action_type": "OPEN_GRANT",
                "target_id": fam.id,
            })

        # C. No Food in Household Storage / Inventory
        food_stk = fam.get_food_stock(furniture_manager, stockpile_manager) if hasattr(fam, "get_food_stock") else 0
        if food_stk <= 0:
            alerts.append({
                "id": f"no_food:{fam.id}",
                "severity": "critical",
                "category": "food",
                "title": f"The {fam.surname}s: No Food",
                "hint": "0 Food at home. Send Grant food or ensure Farm & Market have supply.",
                "action_label": "Send Grant",
                "action_type": "OPEN_GRANT",
                "target_id": fam.id,
            })

        water_stk = fam.get_water_stock(furniture_manager, stockpile_manager) if hasattr(fam, "get_water_stock") else 0
        total_household_water += water_stk

        # D. Workers Missing Job Tools (not in pocket AND not in household storage)
        missing_tool_names = []
        for m in living_members:
            job = getattr(m, "job", None)
            if job in _IDLE_JOBS:
                continue
            for raw_tool, _qty in get_missing_tools_for_worker(m):
                canon = canonical_item_name(raw_tool)
                if possessions.get(canon, 0) <= 0 and possessions.get(raw_tool, 0) <= 0:
                    if canon not in missing_tool_names:
                        missing_tool_names.append(canon)
        if missing_tool_names:
            preview = ", ".join(missing_tool_names[:2])
            if len(missing_tool_names) > 2:
                preview += f" +{len(missing_tool_names) - 2}"
            alerts.append({
                "id": f"no_tools:{fam.id}",
                "severity": "warning",
                "category": "tools",
                "title": f"The {fam.surname}s: Need {preview}",
                "hint": "Workers lack tools. Stock Market, appoint Toolmaker, or send Grant.",
                "action_label": "Inspect",
                "action_type": "OPEN_HOUSEHOLD",
                "target_id": fam.id,
            })

    # 4. Village-wide water check
    if total_living > 0:
        has_well = any(
            getattr(b, "building_type", "") == "well" and getattr(b, "is_available_for_use", True)
            for b in (getattr(building_manager, "buildings", []) if building_manager else [])
        )
        if not has_well and total_household_water <= 0:
            alerts.append({
                "id": "no_well",
                "severity": "critical",
                "category": "water",
                "title": "Village: No Well Built",
                "hint": "Build a Well from Building > Civic/Public so settlers can fetch water.",
                "action_label": "Build Well",
                "action_type": "BUILD_WELL",
                "target_id": None,
            })

    # 5. Unemployed settlers
    all_vils = villager_manager.get_all_villagers() if villager_manager else []
    idle_count = sum(
        1 for v in all_vils
        if getattr(v, "is_alive", True) and getattr(v, "job", "") in _IDLE_JOBS
    )
    if idle_count > 0:
        alerts.append({
            "id": "unemployed_settlers",
            "severity": "info",
            "category": "jobs",
            "title": f"{idle_count} Unemployed Settler(s)",
            "hint": "Assign workers in Jobs tab so they produce resources & pay taxes.",
            "action_label": "Assign Job",
            "action_type": "OPEN_JOBS",
            "target_id": None,
        })

    alerts.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 9), a["title"]))
    return alerts
