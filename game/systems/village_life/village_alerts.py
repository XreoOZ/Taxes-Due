"""
Village Alerts & Notice Board Aggregator (Single Source of Truth).
Architecture:
- Reads live state from VillagerManager, PermitManager, BuildingManager,
  FurnitureManager, StockpileManager, and ImmigrationSystem.
- Consumed identically by both the in-game right-side Notice Board HUD
  and the Town Hall Action Center inside the Town Ledger.
"""

from game.data.config import DEDICATED_JOBS, TILE_SIZE, is_food_item
from game.systems.economy.currency import canonical_denomination, to_copper
from game.systems.economy.household_inventory import (
    canonical_item_name,
    get_household_possessions,
)
from game.systems.economy.market_service import MarketService
from game.systems.work.job_tool_system import get_missing_tools_for_worker


def _market_has_food_for_sale(building_manager):
    """Return True when at least one active market has food in stock for sale."""
    for mkt in MarketService.get_all_markets(building_manager):
        inv = getattr(mkt, "inventory", None) or {}
        for item_name, qty in inv.items():
            if is_food_item(item_name) and int(qty or 0) > 0 and MarketService.is_item_for_sale(mkt, item_name):
                return True
    return False


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
    from game.systems.village_life.immigration_system import (
        STATE_WAITING,
        get_immigration_system,
    )
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
    market_has_food = _market_has_food_for_sale(building_manager)
    any_hungry_with_coins = False

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
        # Suppress per-household "No Food" while the household still has coins
        # (they can buy food at the Market unless no Market has food stocked).
        food_stk = fam.get_food_stock(furniture_manager, stockpile_manager) if hasattr(fam, "get_food_stock") else 0
        if food_stk <= 0:
            if total_copper > 0:
                if not market_has_food:
                    any_hungry_with_coins = True
            else:
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

    # 4. Village-wide food/water checks
    if any_hungry_with_coins and not market_has_food:
        alerts.append({
            "id": "market_no_food",
            "severity": "critical",
            "category": "market_food",
            "title": "Market Has No Food",
            "hint": "Households have coins to buy food, but no Market has Food for sale.",
            "action_label": "Open Jobs",
            "action_type": "OPEN_JOBS",
            "target_id": None,
        })
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


_HOUSEHOLD_NEED_CATEGORIES = frozenset({"housing", "currency", "food", "tools"})


def alert_group_key(alert):
    """Map an individual alert's category to its high-level Notice Board summary group."""
    cat = alert.get("category", "")
    if cat in _HOUSEHOLD_NEED_CATEGORIES:
        return "household_need"
    if cat == "repair":
        return "repair"
    if cat in ("water", "jobs", "immigration", "market_food"):
        return cat
    return "other"


def filter_alerts_by_group(alerts, group_key):
    """Return only alerts matching a summary group key (or all alerts if 'all')."""
    if not group_key or group_key == "all":
        return list(alerts)
    return [a for a in alerts if alert_group_key(a) == group_key]


def group_village_alerts(alerts):
    """Collapse raw per-entity alerts into compact category summaries with counts.
    Clicking a grouped summary opens Town Hall filtered directly to those items."""
    if not alerts:
        return []

    buckets = {}
    for alert in alerts:
        gkey = alert_group_key(alert)
        bucket = buckets.setdefault(gkey, {"items": [], "severity": "info", "families": set()})
        bucket["items"].append(alert)
        if _SEVERITY_ORDER.get(alert["severity"], 9) < _SEVERITY_ORDER.get(bucket["severity"], 9):
            bucket["severity"] = alert["severity"]
        if gkey == "household_need" and alert.get("target_id") is not None:
            bucket["families"].add(str(alert["target_id"]))

    summaries = []
    for gkey, bucket in buckets.items():
        items = bucket["items"]
        sev = bucket["severity"]
        if gkey == "repair":
            count = len(items)
            summaries.append({
                "id": "group:repair",
                "group": "repair",
                "severity": sev,
                "count": count,
                "title": f"Needs Repair: {count}",
                "hint": f"{count} broken structure(s)/fixture(s) need Builder repair.",
                "action_label": "View Details",
                "action_type": "OPEN_TOWN_HALL",
                "target_id": "repair",
            })
        elif gkey == "household_need":
            hh_count = len(bucket["families"]) or len(items)
            summaries.append({
                "id": "group:household_need",
                "group": "household_need",
                "severity": sev,
                "count": hh_count,
                "title": f"Households in Need: {hh_count}",
                "hint": f"{hh_count} household(s) lack housing, coins, food, or tools ({len(items)} alert(s)).",
                "action_label": "View Details",
                "action_type": "OPEN_TOWN_HALL",
                "target_id": "household_need",
            })
        elif gkey in ("water", "jobs", "immigration", "market_food"):
            first = items[0]
            summaries.append({
                **first,
                "group": gkey,
                "count": len(items),
            })
        else:
            summaries.append({
                "id": f"group:{gkey}",
                "group": gkey,
                "severity": sev,
                "count": len(items),
                "title": f"Other Alerts: {len(items)}",
                "hint": "Click to inspect details in Town Hall.",
                "action_label": "View Details",
                "action_type": "OPEN_TOWN_HALL",
                "target_id": "all",
            })

    summaries.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 9), a["title"]))
    return summaries
