"""Item Distribution reporting for the Taxes tab.

Two read-only views over the live village state:

- ``production_last_days`` — aggregates ProductionDistributionSystem
  household history into per-item per-day totals for the trailing
  window (default 10 days). Only villager-produced output is tracked
  here; market purchases and starting stock are not production.
- ``village_item_census`` — physical item census: every item currently
  held anywhere in the village (ground stacks, storage chests, work
  stations, market stalls, lord treasury, carried inventories) grouped
  by item with owner/location breakdown.
"""


def _family_label(villager_manager, family_id):
    if family_id is None:
        return None
    fam = villager_manager.get_family_by_id(str(family_id)) if villager_manager else None
    if fam is None:
        return f"Family {family_id}"
    return f"The {fam.surname} Household"


def production_last_days(ps, current_day, window=10):
    """Return {item_name: {day_offset: qty, 'total': qty}} for the last
    ``window`` days ending at ``current_day`` (inclusive)."""
    start_day = max(1, int(current_day) - window + 1)
    out = {}
    for rec in getattr(ps, "household_records", {}).values():
        for entry in rec.get("history", []):
            day = int(entry.get("day", 0))
            if day < start_day or day > current_day:
                continue
            item = entry.get("resource")
            qty = int(entry.get("amount", 0))
            if not item or qty <= 0:
                continue
            slot = out.setdefault(item, {})
            slot[day] = slot.get(day, 0) + qty
            slot["total"] = slot.get("total", 0) + qty
    # Normalize: ensure every day key exists for stable charting
    for item, slot in out.items():
        for d in range(start_day, int(current_day) + 1):
            slot.setdefault(d, 0)
    return out


def _add(out, item, qty, owner, where):
    if qty <= 0:
        return
    entry = out.setdefault(item, {"total": 0, "owners": []})
    entry["total"] += qty
    # Merge identical owner+location rows
    for o in entry["owners"]:
        if o["owner"] == owner and o["where"] == where:
            o["qty"] += qty
            return
    entry["owners"].append({"owner": owner, "where": where, "qty": qty})


def village_item_census(villager_manager, furniture_manager,
                        building_manager, stockpile_manager,
                        servant_manager=None):
    """Census every physical item in the village.

    Returns {item_name: {"total": int, "owners": [{owner, where, qty}]}}.
    """
    out = {}

    # 1. Loose ground stacks
    if stockpile_manager:
        for s in getattr(stockpile_manager, "stacks", []):
            qty = int(getattr(s, "amount", 0))
            if qty <= 0:
                continue
            otype = getattr(s, "owner_type", "landlord")
            oid = getattr(s, "owner_id", None)
            if otype == "villager" and oid:
                owner = _family_label(villager_manager, oid) or f"Family {oid}"
            elif otype == "landlord":
                owner = "Lord"
            else:
                owner = str(otype)
            _add(out, s.resource_type, qty, owner,
                 f"Ground ({s.grid_x}, {s.grid_y})")

    # 2. Furniture inventories (household chests, lord treasury, workstations)
    if furniture_manager:
        for f in getattr(furniture_manager, "furnitures", []):
            inv = getattr(f, "inventory", None) or {}
            if not inv:
                continue
            ftype = getattr(f, "furniture_type", "")
            fam_id = getattr(f, "family_id", None)
            if ftype == "lord_treasury_chest":
                owner = "Lord"
            elif ftype == "household_storage":
                owner = _family_label(villager_manager, fam_id) or "Unassigned Household"
            else:
                owner = getattr(f, "name", None) or ftype.replace("_", " ").title()
            for item, qty in inv.items():
                _add(out, item, int(qty), owner, f"{owner} — {ftype.replace('_', ' ')}")

    # 3. Building inventories (market stalls etc.)
    if building_manager:
        for b in getattr(building_manager, "buildings", []):
            inv = getattr(b, "inventory", None) or {}
            if not inv:
                continue
            fam_id = getattr(b, "assigned_family_id", None)
            owner = _family_label(villager_manager, fam_id) or "Lord"
            bname = getattr(b, "name", None) or getattr(b, "building_type", "Building")
            for item, qty in inv.items():
                _add(out, item, int(qty), owner, f"{bname}")

    # 4. Carried inventories (villagers + servants)
    if villager_manager:
        for fam in getattr(villager_manager, "families", []):
            for m in getattr(fam, "members", []):
                if not getattr(m, "is_alive", True):
                    continue
                inv = getattr(m, "inventory", None) or {}
                if not inv:
                    continue
                owner = f"{getattr(m, 'name', 'Villager')} ({fam.surname})"
                for item, qty in inv.items():
                    _add(out, item, int(qty), owner, "Carried")
    for sv in getattr(servant_manager, "servants", []) or []:
        inv = getattr(sv, "inventory", None) or {}
        if not inv:
            continue
        owner = getattr(sv, "name", None) or "Servant"
        for item, qty in inv.items():
            _add(out, item, int(qty), owner, "Carried")

    # Sort owners by qty desc for readability
    for entry in out.values():
        entry["owners"].sort(key=lambda o: -o["qty"])
    return out
