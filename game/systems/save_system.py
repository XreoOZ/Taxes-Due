"""
Save & Load Game System
Handles serialization and deserialization of complete game world state across save slots.
"""

import os
import json
import random
import time
from game.data.config import MARKET_TRADEABLE_ITEMS, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT
from game.config import TILE_SIZE, HAPPINESS_INITIAL_VALUE, SLEEP_INITIAL_VALUE

SAVE_DIR = "saves"

def ensure_save_dir():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR, exist_ok=True)

def get_slot_path(slot_id):
    ensure_save_dir()
    return os.path.join(SAVE_DIR, f"save_slot_{slot_id}.json")

def get_slot_meta(slot_id):
    path = get_slot_path(slot_id)
    if not os.path.exists(path):
        return {"slot_id": slot_id, "is_empty": True}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "slot_id": slot_id,
            "is_empty": False,
            "timestamp": data.get("timestamp", "Unknown Date"),
            "day_number": data.get("day_number", 1),
            "time_str": data.get("time_str", "08:00"),
            "population": data.get("population", 0),
            "food": data.get("resources", {}).get("Food", 0),
            "wood": data.get("resources", {}).get("Wood", 0)
        }
    except Exception:
        return {"slot_id": slot_id, "is_empty": True}

def get_all_slots_meta():
    return [get_slot_meta(i) for i in (1, 2, 3)]

def serialize_game_state(day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager):
    """Gathers all dynamic game state into a clean JSON-serializable dictionary"""
    # 1. Day Cycle
    day_data = {
        "day_number": day_cycle.day_number,
        "time_seconds": day_cycle.time_seconds,
        "day_length_index": day_cycle.day_length_index,
        "time_str": f"{int(day_cycle.current_hour):02d}:{int((day_cycle.current_hour % 1.0) * 60):02d}"
    }

    # 2. Player
    player_data = {"x": player.x, "y": player.y}

    # 3. Permits
    permits_data = []
    for p in permit_manager.permits:
        # Convert tile_crops keys to string "gx,gy"
        serialized_tile_crops = {}
        for (gx, gy), tc in getattr(p, "tile_crops", {}).items():
            serialized_tile_crops[f"{gx},{gy}"] = dict(tc)

        # Convert tile_graves keys to string "gx,gy"
        serialized_tile_graves = {}
        for (gx, gy), g_data in getattr(p, "tile_graves", {}).items():
            serialized_tile_graves[f"{gx},{gy}"] = dict(g_data)

        batches_data = []
        if hasattr(p, "batches"):
            for b in p.batches.values():
                batches_data.append(b.to_dict())

        permits_data.append({
            "id": p.id,
            "name": p.name,
            "permit_type": p.permit_type,
            "tiles": [[gx, gy] for gx, gy in p.tiles],
            "max_workers": getattr(p, "max_workers", 2),
            "assigned_workers": list(getattr(p, "assigned_workers", [])),
            "crop": getattr(p, "crop", None),
            "growth_days": getattr(p, "growth_days", 0.0),
            "watered_today": getattr(p, "watered_today", False),
            "tile_crops": serialized_tile_crops,
            "tile_graves": serialized_tile_graves,
            "church_tax": getattr(p, "church_tax", {"Gold": 0, "Silver": 0, "Copper": 1}),
            "church_tax_paid_households": getattr(p, "church_tax_paid_households", {}),
            "tax_paid_households_today": list(getattr(p, "tax_paid_households_today", [])),
            "batches": batches_data,
            "active_batch_id": getattr(p, "active_batch_id", None),
            "batch_counter": getattr(p, "batch_counter", 0),
            "current_day_time": getattr(p, "current_day_time", 1.0)
        })

    # 4. Buildings & Construction Sites
    buildings_data = []
    for b in building_manager.buildings:
        buildings_data.append({
            "building_type": b.building_type,
            "tiles": [[gx, gy] for gx, gy in b.tiles],
            "door_pos": list(b.door_pos) if b.door_pos else None,
            "door_side": getattr(b, "door_side", "bottom"),
            "rotation": int(getattr(b, "_rotation", 0)),
                "condition": float(getattr(b, "condition", 1.0)),
                "construction_order": dict(getattr(b, "construction_order", {}) or {}),
                "construction_progress": float(getattr(b, "construction_progress", 0.0)),
            "assigned_workers": list(getattr(b, "assigned_workers", [])),
            "owner": getattr(b, "owner", "landlord"),
            "inventory": dict(getattr(b, "inventory", {})),
            "currency": dict(getattr(b, "currency", {})),
            "prices": dict(getattr(b, "prices", {})),
            "assigned_family_id": getattr(b, "assigned_family_id", None),
            "assigned_household_id": getattr(b, "assigned_household_id", None),
            "item_allocations": dict(getattr(b, "item_allocations", {})),
            "sale_items": list(getattr(b, "sale_items", [])),
            "sales_report_period": getattr(b, "sales_report_period", None),
            "sales_report_by_item": dict(getattr(b, "sales_report_by_item", {})),
            "sales_report_last_day": getattr(b, "sales_report_last_day", 1),
            "household_sale_percent": getattr(b, "household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT),
            "household_sale_limits": dict(getattr(b, "household_sale_limits", {})),
            "stall_requested_qty": dict(getattr(b, "_stall_requested_qty", {})),
            "auto_pricing": getattr(b, "auto_pricing", True)
        })

    sites_data = []
    for s in building_manager.construction_sites:
        sites_data.append({
            "building_type": s.building_type,
            "tiles": [[gx, gy] for gx, gy in s.tiles],
            "door_pos": list(s.door_pos) if s.door_pos else None,
            "door_side": getattr(s, "door_side", "bottom"),
            "rotation": int(getattr(s, "_rotation", 0)),
            "build_progress": getattr(s, "build_progress", 0.0),
            "delivered_cost": dict(getattr(s, "delivered_cost", {})),
            "required_cost": dict(getattr(s, "required_cost", {})),
            "construction_order": dict(getattr(s, "construction_order", {}) or {})
        })

    demolition_data = []
    for d in getattr(building_manager, "demolition_sites", []):
        b = d.building
        demolition_data.append({
            "progress": d.progress,
            "refund_wood": d.refund_wood,
            "refund_stone": d.refund_stone,
            "building": {
                "building_type": b.building_type,
                "tiles": [[gx, gy] for gx, gy in b.tiles],
                "door_pos": list(b.door_pos) if b.door_pos else None,
                "door_side": getattr(b, "door_side", "bottom"),
                "owner": getattr(b, "owner", "landlord"),
                "inventory": dict(getattr(b, "inventory", {})),
                "currency": dict(getattr(b, "currency", {})),
                "prices": dict(getattr(b, "prices", {})),
                "assigned_family_id": getattr(b, "assigned_family_id", None),
                "assigned_household_id": getattr(b, "assigned_household_id", None),
                "item_allocations": dict(getattr(b, "item_allocations", {})),
                "sale_items": list(getattr(b, "sale_items", [])),
                "household_sale_percent": getattr(b, "household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT),
                "household_sale_limits": dict(getattr(b, "household_sale_limits", {})),
                "stall_requested_qty": dict(getattr(b, "_stall_requested_qty", {})),
                "auto_pricing": getattr(b, "auto_pricing", True)
            }
        })

    # 5. Stockpile
    stacks_data = []
    for s in stockpile_manager.stacks:
        stacks_data.append({
            "resource_type": s.resource_type,
            "amount": s.amount,
            "grid_x": s.grid_x,
            "grid_y": s.grid_y,
            "owner_type": getattr(s, "owner_type", "landlord"),
            "owner_id": getattr(s, "owner_id", None)
        })

    # 6. Furniture
    furniture_data = []
    for f in furniture_manager.furnitures:
        desig_target = None
        if getattr(f, "designated_target", None):
            desig_target = list(f.designated_target)

        furniture_data.append({
            "id": f.id,
            "furniture_type": f.furniture_type,
            "gx": f.grid_x,
            "gy": f.grid_y,
            "rotation": getattr(f, "rotation", 0),
            "permit_id": f.permit_id,
            "family_id": f.family_id,
            "assigned_villager_id": getattr(f, "assigned_villager_id", None),
            "assigned_workers": list(getattr(f, "assigned_workers", [])),
            "is_dropped": getattr(f, "is_dropped", False),
            "stored_in_id": getattr(f, "stored_in_id", None),
            "construction_order": dict(getattr(f, "construction_order", {}) or {}),
            "construction_progress": getattr(f, "construction_progress", 0.0),
            "designated_target": desig_target,
            "carrier_id": getattr(f, "carrier_id", None),
            "condition": getattr(f, "condition", 1.0),
            "inventory": dict(getattr(f, "inventory", {})),
            "currency": dict(getattr(f, "currency", {})),
            "break_check_day": getattr(f, "break_check_day", 1),
            "break_check_hour": getattr(f, "break_check_hour", 0.0),
            "break_checked_today": getattr(f, "break_checked_today", False)
        })

    # 7. Villagers & Families
    families_data = []
    for fam in villager_manager.families:
        families_data.append({
            "id": fam.id,
            "surname": fam.surname,
            "assigned_permit_id": fam.assigned_permit_id,
            "generations_present": fam.generations_present,
            "pending_death_recovery": [dict(d) for d in getattr(fam, "pending_death_recovery", [])],
            "income_report_period": getattr(fam, "income_report_period", None),
            "income_report_by_source": dict(getattr(fam, "income_report_by_source", {}) or {}),
            "income_report_last_day": getattr(fam, "income_report_last_day", 1),
            "members": [
                {
                    "id": m.id,
                    "first_name": m.first_name,
                    "last_name": m.last_name,
                    "gender": m.gender,
                    "age": m.age,
                    "generation": m.generation,
                    "role": m.role,
                    "family_id": m.family_id,
                    "job": m.job,
                    "x": m.x,
                    "y": m.y,
                    "task": m.task,
                    "carrying_crop": getattr(m, "carrying_crop", 0),
                    "inventory": dict(getattr(m, "inventory", {})),
                    "currency": dict(getattr(m, "currency", {})),
                    "active_tool": getattr(m, "active_tool", None),
                    "has_water": getattr(m, "has_water", False),
                    "water_day": getattr(m, "water_day", -1),
                    "water_charges": getattr(m, "water_charges", 0),
                    "assigned_bed_id": getattr(m, "assigned_bed_id", None),
                    "carrying_furniture_id": getattr(m.carrying_furniture, "id", None) if getattr(m, "carrying_furniture", None) else None,
                    "watering_timer": getattr(m, "watering_timer", 0.0),
                    "tilling_timer": getattr(m, "tilling_timer", 0.0),
                    "hunger": getattr(m, "hunger", 100.0),
                    "thirst": getattr(m, "thirst", 100.0),
                    "need_toilet": getattr(m, "need_toilet", 100.0),
                    "faith": getattr(m, "faith", 100.0),
                    "sleep_need": getattr(m, "sleep_need", SLEEP_INITIAL_VALUE),
                    "sleep_forced": getattr(m, "sleep_forced", False),
                    "sleeping_recharge_active": getattr(m, "sleeping_recharge_active", False),
                    "sleep_any_rest_active": getattr(m, "sleep_any_rest_active", False),
                    "sleep_schedule_task_state": getattr(m, "sleep_schedule_task_state", None),
                    "pending_schedule_tasks": [
                        dict(entry) for entry in getattr(m, "pending_schedule_tasks", [])
                        if isinstance(entry, dict)
                    ],
                    "socage_tax_round": dict(getattr(m, "socage_tax_round", {}) or {}) or None,
                    "socage_tax_last_cycle": getattr(m, "socage_tax_last_cycle", None),
                    "socage_tax_prepared_cycle": getattr(m, "socage_tax_prepared_cycle", None),
                    "socage_tax_prepared_amount": getattr(m, "socage_tax_prepared_amount", 0),
                    "happiness": getattr(m, "happiness", HAPPINESS_INITIAL_VALUE),
                    "happiness_effects": dict(getattr(m, "happiness_effects", {}) or {}),
                    "happiness_trigger_days": dict(getattr(m, "happiness_trigger_days", {}) or {}),
                    "happiness_food_day": getattr(m, "happiness_food_day", None),
                    "happiness_food_types": list(getattr(m, "happiness_food_types", []) or []),
                    "last_faith_decay_day": getattr(m, "last_faith_decay_day", 1),
                    "prayer_attendance_day": getattr(m, "prayer_attendance_day", None),
                    "church_tax_prepared_day": getattr(m, "church_tax_prepared_day", None),
                    "church_tax_prepared_amount": getattr(m, "church_tax_prepared_amount", 0),
                    "last_faith_prayer_day": getattr(m, "last_faith_prayer_day", None),
                    "last_confession_day": getattr(m, "last_confession_day", None),
                    "pending_commission_task": getattr(m, "pending_commission_task", None),
                    "pending_commission_data": dict(getattr(m, "pending_commission_data", {}) or {}),
                    "pending_commission_tasks": [dict(entry) for entry in getattr(m, "pending_commission_tasks", [])],
                    "interrupted_task_state": getattr(m, "interrupted_task_state", None),
                    "activity_description": getattr(m, "activity_description", None),
                    "hunger_death_timer": getattr(m, "hunger_death_timer", None),
                    "thirst_death_timer": getattr(m, "thirst_death_timer", None),
                    "daily_food_consumed": getattr(m, "daily_food_consumed", 0),
                    "daily_water_consumed": getattr(m, "daily_water_consumed", 0),
                    "is_alive": getattr(m, "is_alive", True),
                    "status": getattr(m, "status", "ALIVE"),
                    "death_reason": getattr(m, "death_reason", None),
                    "death_day": getattr(m, "death_day", None),
                    "carrying_corpse_id": getattr(m, "carrying_corpse_id", None),
                    "burial_payment_target_corpse_id": getattr(m, "burial_payment_target_corpse_id", None),
                    "burial_payment_gravedigger_id": getattr(m, "burial_payment_gravedigger_id", None),
                    "carpenter_payment_order_id": getattr(m, "carpenter_payment_order_id", None),
                    "carpenter_payment_carpenter_id": getattr(m, "carpenter_payment_carpenter_id", None),
                    "is_buried": getattr(m, "is_buried", False),
                    "is_picked_up": getattr(m, "is_picked_up", False)
                } for m in fam.members
            ]
        })

    # 8. Servants
    servants_data = []
    for s in servant_manager.servants:
        servants_data.append({
            "id": s.id,
            "name": s.name,
            "x": s.x,
            "y": s.y,
            "work_priorities": dict(s.work_priorities),
            "carrying_furniture_id": getattr(s.carrying_furniture, "id", None) if getattr(s, "carrying_furniture", None) else None,
            "state": getattr(s, "state", "IDLE"),
            "inventory": dict(getattr(s, "inventory", {})),
            "carpenter_commission_order_id": getattr(s, "carpenter_commission_order_id", None),
            "carpenter_commission_carpenter_id": getattr(s, "carpenter_commission_carpenter_id", None),
            "carpenter_commission_fee_copper": getattr(s, "carpenter_commission_fee_copper", 0),
            "carpenter_commission_remaining_copper": getattr(s, "carpenter_commission_remaining_copper", 0),
            "carpenter_commission_storage_tile": getattr(s, "carpenter_commission_storage_tile", None),
            "carpenter_commission_treasury_id": getattr(s, "carpenter_commission_treasury_id", None)
        })

    # 9. Schedules
    schedules_data = {}
    if schedule_manager:
        schedules_data = schedule_manager.to_dict()

    all_vils = villager_manager.get_all_villagers()
    total_pop = len(all_vils) + len(servant_manager.servants)

    # 10. Production Distribution Records
    from game.systems.production_distribution import ProductionDistributionSystem
    ps = ProductionDistributionSystem.get_instance()
    serialized_prod = {}
    for fam_id, rec in ps.household_records.items():
        serialized_prod[str(fam_id)] = {
            "total_produced": dict(rec.get("total_produced", {})),
            "workplaces": list(rec.get("workplaces", [])),
            "history": list(rec.get("history", []))
        }

    from game.systems.cemetery_system import CemeterySystem
    burial_commissions = [
        {key: value for key, value in commission.items()
         if key in ("corpse_id", "corpse_name", "fee_paid", "fee_available", "payer_type", "payer_id", "gravedigger_id", "status")}
        for commission in CemeterySystem.get_instance().pending_commissions
    ]
    from game.systems.confession_system import ConfessionSystem
    confession_state = ConfessionSystem.get_instance().to_dict()
    from game.systems.taxation_system import TaxationSystem
    taxation_state = TaxationSystem.to_dict()
    from game.world.island import world_type, get_seed

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        "world": {"type": world_type(), "seed": get_seed()},
        "day_number": day_cycle.day_number,
        "time_str": day_data["time_str"],
        "population": total_pop,
        "resources": dict(resources),
        "day_cycle": day_data,
        "player": player_data,
        "permits": permits_data,
        "buildings": buildings_data,
        "construction_sites": sites_data,
        "demolition_sites": demolition_data,
        "stockpile": stacks_data,
        "furniture": furniture_data,
        "families": families_data,
        "servants": servants_data,
        "schedules": schedules_data,
        "production_records": serialized_prod,
        "burial_commissions": burial_commissions,
        "confession_state": confession_state,
        "taxation_state": taxation_state,
    }

def save_to_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager):
    try:
        ensure_save_dir()
        path = get_slot_path(slot_id)
        tmp_path = path + ".tmp"
        data = serialize_game_state(day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
        
        # Safe atomic write to temporary file first
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Retry loop for Windows file locking tolerance (e.g. anti-virus, quick read handles)
        replaced = False
        last_err = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, path)
                replaced = True
                break
            except Exception as e:
                last_err = e
                time.sleep(0.04)

        # Fallback: direct write if replace failed
        if not replaced:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                replaced = True
            except Exception as e2:
                return False, f"Save failed: {last_err or e2}"

        return True, f"Save Slot {slot_id} updated successfully!"
    except Exception as e:
        return False, f"Save failed: {e}"

def deserialize_game_state(data, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager):
    from game.world.permits import AreaPermit
    from game.buildings.building import Building
    from game.buildings.construction_site import ConstructionSite
    from game.world.stockpile import ResourceStack
    from game.buildings.furniture import Furniture
    from game.entities.villagers import Family, Villager
    from game.world.island import set_world

    # 0. World terrain (island seed / infinite) — must be active before entities load
    world_data = data.get("world") or {}
    set_world(world_data.get("type", "infinite"), seed=world_data.get("seed"))

    # 1. Day Cycle - set day length index FIRST so time_seconds is not re-scaled incorrectly
    dc_data = data.get("day_cycle", {})
    day_cycle.day_number = dc_data.get("day_number", 1)
    day_cycle.set_day_length_index(dc_data.get("day_length_index", 1))
    day_cycle.time_seconds = dc_data.get("time_seconds", 0.0)

    # 2. Resources
    resources.clear()
    resources.update(data.get("resources", {}))

    # 3. Player
    p_data = data.get("player", {})
    player.x = p_data.get("x", 0.0)
    player.y = p_data.get("y", 0.0)

    # 4. Permits
    permit_manager.permits.clear()
    for p_d in data.get("permits", []):
        tiles = {(t[0], t[1]) for t in p_d.get("tiles", [])}
        p = AreaPermit(p_d["id"], p_d["name"], p_d["permit_type"], tiles)
        p.max_workers = p_d.get("max_workers", 2)
        p.assigned_workers = list(p_d.get("assigned_workers", []))
        p.crop = p_d.get("crop", None)
        p.growth_days = p_d.get("growth_days", 0.0)
        p.watered_today = p_d.get("watered_today", False)

        p.tile_crops = {}
        for k, tc_val in p_d.get("tile_crops", {}).items():
            parts = k.split(",")
            gx, gy = int(parts[0]), int(parts[1])
            p.tile_crops[(gx, gy)] = dict(tc_val)

        from game.world.permits import FarmingBatch
        p.batches = {}
        for b_d in p_d.get("batches", []):
            batch = FarmingBatch.from_dict(b_d)
            p.batches[batch.id] = batch
        p.active_batch_id = p_d.get("active_batch_id", None)
        p.batch_counter = p_d.get("batch_counter", len(p.batches))
        p.current_day_time = float(p_d.get("current_day_time", 1.0))

        # Deserialize Cemetery & Church attributes (Agent 3)
        p.tile_graves = {}
        for k, g_val in p_d.get("tile_graves", {}).items():
            parts = k.split(",")
            gx, gy = int(parts[0]), int(parts[1])
            p.tile_graves[(gx, gy)] = dict(g_val)
        p.church_tax = dict(p_d.get("church_tax", {"Gold": 0, "Silver": 0, "Copper": 1}))
        p.church_tax_paid_households = dict(p_d.get("church_tax_paid_households", {}))
        p.tax_paid_households_today = set(p_d.get("tax_paid_households_today", []))

        permit_manager.permits.append(p)

    # 5. Buildings & Construction Sites
    building_manager.buildings.clear()
    for b_d in data.get("buildings", []):
        tiles = {(t[0], t[1]) for t in b_d.get("tiles", [])}
        door_pos = tuple(b_d["door_pos"]) if b_d.get("door_pos") else None
        b = Building(b_d["building_type"], tiles, door_pos=door_pos, door_side=b_d.get("door_side", "bottom"), rotation=b_d.get("rotation", 0))
        b.condition = float(b_d.get("condition", 1.0))
        b.construction_order = dict(b_d.get("construction_order", {}) or {}) or None
        b.construction_progress = float(b_d.get("construction_progress", 0.0))
        b.assigned_workers = list(b_d.get("assigned_workers", []))
        if "owner" in b_d:
            b.owner = b_d["owner"]
        if "inventory" in b_d:
            b.inventory = dict(b_d["inventory"])
        if "currency" in b_d:
            b.currency = dict(b_d["currency"])
        if "prices" in b_d:
            b.prices = dict(b_d["prices"])
        if "assigned_family_id" in b_d:
            b.assigned_family_id = b_d["assigned_family_id"]
        if "assigned_household_id" in b_d:
            b.assigned_household_id = b_d["assigned_household_id"]
        if "item_allocations" in b_d:
            b.item_allocations = dict(b_d["item_allocations"])
        b.sale_items = list(b_d.get("sale_items", [item for item in b.inventory if item in MARKET_TRADEABLE_ITEMS]))
        b.sales_report_period = b_d.get("sales_report_period")
        b.sales_report_by_item = dict(b_d.get("sales_report_by_item", {}))
        b.sales_report_last_day = int(b_d.get("sales_report_last_day", data.get("day_number", 1)))
        b.household_sale_percent = b_d.get("household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
        b.household_sale_limits = dict(b_d.get("household_sale_limits", {}))
        b._stall_requested_qty = dict(b_d.get("stall_requested_qty", {}))
        b.auto_pricing = bool(b.assigned_family_id)
        building_manager.buildings.append(b)

    building_manager.construction_sites.clear()
    for s_d in data.get("construction_sites", []):
        tiles = {(t[0], t[1]) for t in s_d.get("tiles", [])}
        door_pos = tuple(s_d["door_pos"]) if s_d.get("door_pos") else None
        s = ConstructionSite(s_d["building_type"], tiles, door_pos=door_pos, door_side=s_d.get("door_side", "bottom"), rotation=s_d.get("rotation", 0))
        s.build_progress = s_d.get("build_progress", 0.0)
        s.delivered_cost = dict(s_d.get("delivered_cost", {}))
        s.required_cost = dict(s_d.get("required_cost", {}))
        s.construction_order = dict(s_d.get("construction_order", {}) or {}) or s.construction_order
        building_manager.construction_sites.append(s)

    building_manager.demolition_sites.clear()
    for d_d in data.get("demolition_sites", []):
        b_d = d_d.get("building", {})
        tiles = {(t[0], t[1]) for t in b_d.get("tiles", [])}
        door_pos = tuple(b_d["door_pos"]) if b_d.get("door_pos") else None
        b = Building(b_d.get("building_type", "wooden_structure"), tiles, door_pos=door_pos, door_side=b_d.get("door_side", "bottom"))
        b.owner = b_d.get("owner", "landlord")
        b.inventory = dict(b_d.get("inventory", {}))
        b.currency = dict(b_d.get("currency", {}))
        b.prices = dict(b_d.get("prices", {}))
        b.assigned_family_id = b_d.get("assigned_family_id")
        b.assigned_household_id = b_d.get("assigned_household_id")
        b.item_allocations = dict(b_d.get("item_allocations", {}))
        b.sale_items = list(b_d.get("sale_items", [item for item in b.inventory if item in MARKET_TRADEABLE_ITEMS]))
        b.household_sale_percent = b_d.get("household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
        b.household_sale_limits = dict(b_d.get("household_sale_limits", {}))
        b._stall_requested_qty = dict(b_d.get("stall_requested_qty", {}))
        b.auto_pricing = bool(b.assigned_family_id)
        from game.buildings.demolition_site import DemolitionSite
        site = DemolitionSite(b)
        site.progress = d_d.get("progress", 0.0)
        site.refund_wood = d_d.get("refund_wood", site.refund_wood)
        site.refund_stone = d_d.get("refund_stone", site.refund_stone)
        building_manager.demolition_sites.append(site)

    # 6. Stockpile
    stockpile_manager.stacks.clear()
    for st_d in data.get("stockpile", []):
        s = ResourceStack(
            st_d["resource_type"],
            st_d["amount"],
            st_d["grid_x"],
            st_d["grid_y"],
            owner_type=st_d.get("owner_type", "landlord"),
            owner_id=st_d.get("owner_id", None)
        )
        stockpile_manager.stacks.append(s)
    stockpile_manager.mark_totals_dirty()

    # 7. Furniture
    furniture_manager.furnitures.clear()
    for f_d in data.get("furniture", []):
        f = Furniture(
            f_d["id"],
            f_d["furniture_type"],
            f_d["gx"],
            f_d["gy"],
            permit_id=f_d.get("permit_id", None),
            family_id=f_d.get("family_id", None),
            assigned_villager_id=f_d.get("assigned_villager_id", None),
            rotation=f_d.get("rotation", 0)
        )
        f.inventory = dict(f_d.get("inventory", {}))
        f.currency = dict(f_d.get("currency", {}))
        f.is_dropped = f_d.get("is_dropped", False)
        f.stored_in_id = f_d.get("stored_in_id", None)
        f.construction_order = dict(f_d.get("construction_order", {}) or {}) or None
        f.construction_progress = f_d.get("construction_progress", 0.0)
        f.designated_target = tuple(f_d["designated_target"]) if f_d.get("designated_target") else None
        f.carrier_id = f_d.get("carrier_id", None)
        f.condition = f_d.get("condition", 1.0)
        f.assigned_workers = list(f_d.get("assigned_workers", []))
        f.break_check_day = f_d.get("break_check_day", data.get("day_number", 1))
        f.break_check_hour = f_d.get("break_check_hour", random.uniform(0, 24))
        f.break_checked_today = f_d.get("break_checked_today", False)
        furniture_manager.furnitures.append(f)
    if hasattr(furniture_manager, "invalidate_cache"):
        furniture_manager.invalidate_cache()

    # 8. Villagers & Families
    villager_manager.families.clear()
    villager_manager.invalidate_villager_cache()
    for fam_d in data.get("families", []):
        fam = Family(fam_d["id"], fam_d["surname"])
        fam.assigned_permit_id = fam_d.get("assigned_permit_id", None)
        fam.pending_death_recovery = list(fam_d.get("pending_death_recovery", []))
        fam.income_report_period = fam_d.get("income_report_period")
        fam.income_report_by_source = dict(fam_d.get("income_report_by_source", {}) or {})
        fam.income_report_last_day = int(fam_d.get("income_report_last_day", 1))
        fam.members = []
        for m_d in fam_d.get("members", []):
            v = Villager(
                m_d["id"],
                m_d["first_name"],
                m_d["last_name"],
                m_d["gender"],
                m_d["age"],
                m_d["generation"],
                m_d["role"],
                m_d["family_id"],
                x=m_d.get("x", 0.0),
                y=m_d.get("y", 0.0)
            )
            v.job = m_d.get("job", "Farmer")
            v.profession = v.job
            v.task = m_d.get("task", "IDLE")
            v.carrying_crop = m_d.get("carrying_crop", 0)
            v.inventory = dict(m_d.get("inventory", {}))
            v.currency = dict(m_d.get("currency", {}))
            v.active_tool = m_d.get("active_tool", None)
            v.has_water = m_d.get("has_water", False)
            v.water_day = m_d.get("water_day", -1)
            v.water_charges = m_d.get("water_charges", 0)
            v.assigned_bed_id = m_d.get("assigned_bed_id", None)
            v.watering_timer = m_d.get("watering_timer", 0.0)
            v.tilling_timer = m_d.get("tilling_timer", 0.0)
            v.hunger = float(m_d.get("hunger", 100.0))
            v.thirst = float(m_d.get("thirst", 100.0))
            v.need_toilet = float(m_d.get("need_toilet", 100.0))
            v.faith = float(m_d.get("faith", 100.0))
            v.sleep_need = float(m_d.get("sleep_need", SLEEP_INITIAL_VALUE))
            v.sleep_forced = bool(m_d.get("sleep_forced", False))
            v.sleeping_recharge_active = bool(m_d.get("sleeping_recharge_active", False))
            v.sleep_any_rest_active = bool(m_d.get("sleep_any_rest_active", False))
            v.sleep_schedule_task_state = m_d.get("sleep_schedule_task_state")
            v.pending_schedule_tasks = [
                dict(entry) for entry in m_d.get("pending_schedule_tasks", [])
                if isinstance(entry, dict)
            ]
            v.socage_tax_round = dict(m_d.get("socage_tax_round", {}) or {}) or None
            v.socage_tax_last_cycle = m_d.get("socage_tax_last_cycle")
            v.socage_tax_prepared_cycle = m_d.get("socage_tax_prepared_cycle")
            v.socage_tax_prepared_amount = int(m_d.get("socage_tax_prepared_amount", 0))
            v.happiness = float(m_d.get("happiness", HAPPINESS_INITIAL_VALUE))
            v.happiness_effects = dict(m_d.get("happiness_effects", {}) or {})
            v.happiness_trigger_days = dict(m_d.get("happiness_trigger_days", {}) or {})
            v.happiness_food_day = m_d.get("happiness_food_day")
            v.happiness_food_types = list(m_d.get("happiness_food_types", []) or [])
            v.last_faith_decay_day = int(m_d.get("last_faith_decay_day", data.get("day_number", 1)))
            v.prayer_attendance_day = m_d.get("prayer_attendance_day", None)
            v.church_tax_prepared_day = m_d.get("church_tax_prepared_day", None)
            v.church_tax_prepared_amount = int(m_d.get("church_tax_prepared_amount", 0))
            v.last_faith_prayer_day = m_d.get("last_faith_prayer_day", None)
            v.last_confession_day = m_d.get("last_confession_day", None)
            v.pending_commission_task = m_d.get("pending_commission_task", None)
            v.pending_commission_data = dict(m_d.get("pending_commission_data", {}) or {})
            v.pending_commission_tasks = [dict(entry) for entry in m_d.get("pending_commission_tasks", []) if isinstance(entry, dict)]
            v.interrupted_task_state = m_d.get("interrupted_task_state", None)
            v.activity_description = m_d.get("activity_description", None)
            v.hunger_death_timer = float(m_d["hunger_death_timer"]) if m_d.get("hunger_death_timer") is not None else None
            v.thirst_death_timer = float(m_d["thirst_death_timer"]) if m_d.get("thirst_death_timer") is not None else None
            if "daily_food_consumed" in m_d:
                v.daily_food_consumed = int(m_d["daily_food_consumed"])
            else:
                v.daily_food_consumed = 1 if v.hunger >= 50.0 else 0

            if "daily_water_consumed" in m_d:
                v.daily_water_consumed = int(m_d["daily_water_consumed"])
            else:
                v.daily_water_consumed = 1 if v.thirst >= 50.0 else 0
            v.is_alive = bool(m_d.get("is_alive", True))
            v.status = str(m_d.get("status", "ALIVE"))
            v.death_reason = m_d.get("death_reason", None)
            v.death_day = m_d.get("death_day", None)
            v.carrying_corpse_id = m_d.get("carrying_corpse_id", None)
            v.burial_payment_target_corpse_id = m_d.get("burial_payment_target_corpse_id", None)
            v.burial_payment_gravedigger_id = m_d.get("burial_payment_gravedigger_id", None)
            v.carpenter_payment_order_id = m_d.get("carpenter_payment_order_id", None)
            v.carpenter_payment_carpenter_id = m_d.get("carpenter_payment_carpenter_id", None)
            v.is_buried = bool(m_d.get("is_buried", False))
            v.is_picked_up = bool(m_d.get("is_picked_up", False))
            v.assigned_permit_id = fam.assigned_permit_id
            
            # Reconnect carrying furniture if applicable
            cf_id = m_d.get("carrying_furniture_id", None)
            if cf_id:
                v.carrying_furniture = furniture_manager.get_furniture_by_id(cf_id)
            else:
                v.carrying_furniture = None

            fam.members.append(v)
        villager_manager.families.append(fam)

    villager_manager.ensure_unique_family_ids()
    villager_manager.invalidate_villager_cache()

    from game.systems.confession_system import ConfessionSystem
    ConfessionSystem.get_instance().load_dict(data.get("confession_state", {}))
    from game.systems.taxation_system import TaxationSystem
    TaxationSystem.load_dict(data.get("taxation_state", {}), permit_manager)

    from game.systems.cemetery_system import CemeterySystem
    cemetery_system = CemeterySystem.get_instance()
    corpse_by_id = {
        str(v.id): v for v in villager_manager.get_all_villagers()
        if not getattr(v, "is_alive", True)
    }
    cemetery_system.pending_commissions = []
    for saved_commission in data.get("burial_commissions", []):
        commission = dict(saved_commission)
        corpse = corpse_by_id.get(str(commission.get("corpse_id", "")))
        if corpse:
            commission["corpse_obj"] = corpse
            cemetery_system.pending_commissions.append(commission)

    # 9. Servants - reset tasks to clean IDLE state so no dangling references exist
    for s_d in data.get("servants", []):
        for s in servant_manager.servants:
            if s.id == s_d["id"]:
                s.x = s_d.get("x", s.x)
                s.y = s_d.get("y", s.y)
                if "work_priorities" in s_d:
                    s.work_priorities = dict(s_d["work_priorities"])
                s.inventory = dict(s_d.get("inventory", getattr(s, "inventory", {})))
                s.carpenter_commission_order_id = s_d.get("carpenter_commission_order_id")
                s.carpenter_commission_carpenter_id = s_d.get("carpenter_commission_carpenter_id")
                s.carpenter_commission_fee_copper = int(s_d.get("carpenter_commission_fee_copper", 0))
                s.carpenter_commission_remaining_copper = int(s_d.get("carpenter_commission_remaining_copper", 0))
                s.carpenter_commission_storage_tile = s_d.get("carpenter_commission_storage_tile")
                s.carpenter_commission_treasury_id = s_d.get("carpenter_commission_treasury_id")
                
                # Reconnect carrying furniture if applicable
                scf_id = s_d.get("carrying_furniture_id", None)
                if scf_id:
                    s.carrying_furniture = furniture_manager.get_furniture_by_id(scf_id)
                else:
                    s.carrying_furniture = None
                
                # Reconnect the public commission courier task by its stable order IDs.
                if s_d.get("state") in ("CARPENTER_COMMISSION_RETRIEVE", "CARPENTER_COMMISSION_DELIVER") and s.carpenter_commission_order_id:
                    s.state = s_d["state"]
                # Reset other in-progress tasks to prevent stale references.
                elif not s.carrying_furniture:
                    s.state = "IDLE"
                    s.carried_res = None
                    s.carried_amount = 0
                    s.target_site = None
                    s.target_stack = None

    # 10. Schedules
    if schedule_manager and "schedules" in data:
        schedule_manager.load_from_dict(data["schedules"])

    # 10.5. Production Distribution Records
    if "production_records" in data:
        from game.systems.production_distribution import ProductionDistributionSystem
        ps = ProductionDistributionSystem.get_instance()
        restored = {}
        for fam_id, rec in data["production_records"].items():
            restored[str(fam_id)] = {
                "total_produced": dict(rec.get("total_produced", {})),
                "workplaces": set(rec.get("workplaces", [])),
                "history": list(rec.get("history", []))
            }
        ps.household_records = restored

    # 11. Recalculate ID counters to prevent future ID collisions
    max_p = max([int(str(p.id).split("_")[-1]) for p in permit_manager.permits if "_" in str(p.id) and str(p.id).split("_")[-1].isdigit()] + [0])
    if hasattr(permit_manager, "permit_counter"):
        permit_manager.permit_counter = max_p + 1

    max_f = max([int(str(f.id).split("_")[-1]) for f in furniture_manager.furnitures if "_" in str(f.id) and str(f.id).split("_")[-1].isdigit()] + [0])
    if hasattr(furniture_manager, "counter"):
        furniture_manager.counter = max_f + 1

    max_fam = max([int(str(f.id).split("_")[-1]) for f in villager_manager.families if "_" in str(f.id) and str(f.id).split("_")[-1].isdigit()] + [0])
    if hasattr(villager_manager, "family_counter"):
        villager_manager.family_counter = max_fam + 1

    all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else []
    max_vil = max([int(str(v.id).split("_")[-1]) for v in all_vils if "_" in str(v.id) and str(v.id).split("_")[-1].isdigit()] + [0])
    if hasattr(villager_manager, "villager_counter"):
        villager_manager.villager_counter = max_vil + 1

    # 12. Refresh spatial caches & Reset Global Path Registry so stale route reservations from prior session are cleared
    if hasattr(building_manager, "rebuild_tile_cache"):
        building_manager.rebuild_tile_cache()
    if hasattr(furniture_manager, "invalidate_cache"):
        furniture_manager.invalidate_cache()

    from game.world.pathfinding import GlobalPathRegistry
    GlobalPathRegistry.get_instance().reset()

    from game.systems.wealth_system import VillageWealthSystem
    VillageWealthSystem.mark_dirty()
    return True

def load_from_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager):
    path = get_slot_path(slot_id)
    if not os.path.exists(path):
        return False, f"Slot {slot_id} save file not found!"

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to read slot {slot_id}: {e}"

    deserialize_game_state(data, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
    furniture_manager.ensure_lord_treasury_chest(
        permit_manager, villager_manager, building_manager, stockpile_manager,
        preferred_tile=(int(player.x // TILE_SIZE), int(player.y // TILE_SIZE)),
    )
    return True, f"Loaded Slot {slot_id} successfully!"
