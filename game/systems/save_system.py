"""
Save & Load Game System
Handles serialization and deserialization of complete game world state across save slots.
"""

import os
import json
import time

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
            "tile_crops": serialized_tile_crops
        })

    # 4. Buildings & Construction Sites
    buildings_data = []
    for b in building_manager.buildings:
        buildings_data.append({
            "building_type": b.building_type,
            "tiles": [[gx, gy] for gx, gy in b.tiles],
            "door_pos": list(b.door_pos) if b.door_pos else None,
            "door_side": getattr(b, "door_side", "bottom"),
            "owner": getattr(b, "owner", "landlord"),
            "inventory": dict(getattr(b, "inventory", {})),
            "currency": dict(getattr(b, "currency", {})),
            "prices": dict(getattr(b, "prices", {}))
        })

    sites_data = []
    for s in building_manager.construction_sites:
        sites_data.append({
            "building_type": s.building_type,
            "tiles": [[gx, gy] for gx, gy in s.tiles],
            "door_pos": list(s.door_pos) if s.door_pos else None,
            "door_side": getattr(s, "door_side", "bottom"),
            "build_progress": getattr(s, "build_progress", 0.0),
            "delivered_cost": dict(getattr(s, "delivered_cost", {})),
            "required_cost": dict(getattr(s, "required_cost", {}))
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
            "permit_id": f.permit_id,
            "family_id": f.family_id,
            "assigned_villager_id": getattr(f, "assigned_villager_id", None),
            "is_dropped": getattr(f, "is_dropped", False),
            "designated_target": desig_target,
            "carrier_id": getattr(f, "carrier_id", None),
            "condition": getattr(f, "condition", 1.0),
            "inventory": dict(getattr(f, "inventory", {}))
        })

    # 7. Villagers & Families
    families_data = []
    for fam in villager_manager.families:
        families_data.append({
            "id": fam.id,
            "surname": fam.surname,
            "assigned_permit_id": fam.assigned_permit_id,
            "generations_present": fam.generations_present,
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
                    "daily_food_consumed": getattr(m, "daily_food_consumed", 0),
                    "daily_water_consumed": getattr(m, "daily_water_consumed", 0),
                    "is_alive": getattr(m, "is_alive", True),
                    "status": getattr(m, "status", "ALIVE"),
                    "death_reason": getattr(m, "death_reason", None),
                    "death_day": getattr(m, "death_day", None)
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
            "carrying_furniture_id": getattr(s.carrying_furniture, "id", None) if getattr(s, "carrying_furniture", None) else None
        })

    # 9. Schedules
    schedules_data = {}
    if schedule_manager:
        schedules_data = {job_id: list(sched) for job_id, sched in schedule_manager.job_schedules.items()}

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

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        "day_number": day_cycle.day_number,
        "time_str": day_data["time_str"],
        "population": total_pop,
        "resources": dict(resources),
        "day_cycle": day_data,
        "player": player_data,
        "permits": permits_data,
        "buildings": buildings_data,
        "construction_sites": sites_data,
        "stockpile": stacks_data,
        "furniture": furniture_data,
        "families": families_data,
        "servants": servants_data,
        "schedules": schedules_data,
        "production_records": serialized_prod
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

def load_from_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager):
    path = get_slot_path(slot_id)
    if not os.path.exists(path):
        return False, f"Slot {slot_id} save file not found!"

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, f"Failed to read slot {slot_id}: {e}"

    from game.world.permits import AreaPermit
    from game.buildings.buildings import Building, ConstructionSite
    from game.world.stockpile import ResourceStack
    from game.buildings.furniture import Furniture
    from game.entities.villagers import Family, Villager

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

        permit_manager.permits.append(p)

    # 5. Buildings & Construction Sites
    building_manager.buildings.clear()
    for b_d in data.get("buildings", []):
        tiles = {(t[0], t[1]) for t in b_d.get("tiles", [])}
        door_pos = tuple(b_d["door_pos"]) if b_d.get("door_pos") else None
        b = Building(b_d["building_type"], tiles, door_pos=door_pos, door_side=b_d.get("door_side", "bottom"))
        if "owner" in b_d:
            b.owner = b_d["owner"]
        if "inventory" in b_d:
            b.inventory = dict(b_d["inventory"])
        if "currency" in b_d:
            b.currency = dict(b_d["currency"])
        if "prices" in b_d:
            b.prices = dict(b_d["prices"])
        building_manager.buildings.append(b)

    building_manager.construction_sites.clear()
    for s_d in data.get("construction_sites", []):
        tiles = {(t[0], t[1]) for t in s_d.get("tiles", [])}
        door_pos = tuple(s_d["door_pos"]) if s_d.get("door_pos") else None
        s = ConstructionSite(s_d["building_type"], tiles, door_pos=door_pos, door_side=s_d.get("door_side", "bottom"))
        s.build_progress = s_d.get("build_progress", 0.0)
        s.delivered_cost = dict(s_d.get("delivered_cost", {}))
        s.required_cost = dict(s_d.get("required_cost", {}))
        building_manager.construction_sites.append(s)

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
            assigned_villager_id=f_d.get("assigned_villager_id", None)
        )
        f.inventory = dict(f_d.get("inventory", {}))
        f.is_dropped = f_d.get("is_dropped", False)
        f.designated_target = tuple(f_d["designated_target"]) if f_d.get("designated_target") else None
        f.carrier_id = f_d.get("carrier_id", None)
        f.condition = f_d.get("condition", 1.0)
        furniture_manager.furnitures.append(f)
    if hasattr(furniture_manager, "invalidate_cache"):
        furniture_manager.invalidate_cache()

    # 8. Villagers & Families
    villager_manager.families.clear()
    for fam_d in data.get("families", []):
        fam = Family(fam_d["id"], fam_d["surname"])
        fam.assigned_permit_id = fam_d.get("assigned_permit_id", None)
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
            v.task = m_d.get("task", "IDLE")
            v.carrying_crop = m_d.get("carrying_crop", 0)
            v.inventory = dict(m_d.get("inventory", {}))
            v.active_tool = m_d.get("active_tool", None)
            v.has_water = m_d.get("has_water", False)
            v.water_day = m_d.get("water_day", -1)
            v.water_charges = m_d.get("water_charges", 0)
            v.assigned_bed_id = m_d.get("assigned_bed_id", None)
            v.watering_timer = m_d.get("watering_timer", 0.0)
            v.tilling_timer = m_d.get("tilling_timer", 0.0)
            v.hunger = float(m_d.get("hunger", 100.0))
            v.thirst = float(m_d.get("thirst", 100.0))
            v.daily_food_consumed = int(m_d.get("daily_food_consumed", 0))
            v.daily_water_consumed = int(m_d.get("daily_water_consumed", 0))
            v.is_alive = bool(m_d.get("is_alive", True))
            v.status = str(m_d.get("status", "ALIVE"))
            v.death_reason = m_d.get("death_reason", None)
            v.death_day = m_d.get("death_day", None)
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

    # 9. Servants - reset tasks to clean IDLE state so no dangling references exist
    for s_d in data.get("servants", []):
        for s in servant_manager.servants:
            if s.id == s_d["id"]:
                s.x = s_d.get("x", s.x)
                s.y = s_d.get("y", s.y)
                if "work_priorities" in s_d:
                    s.work_priorities = dict(s_d["work_priorities"])
                
                # Reconnect carrying furniture if applicable
                scf_id = s_d.get("carrying_furniture_id", None)
                if scf_id:
                    s.carrying_furniture = furniture_manager.get_furniture_by_id(scf_id)
                else:
                    s.carrying_furniture = None
                
                # Reset any in-progress tasks to prevent stale references
                if not s.carrying_furniture:
                    s.state = "IDLE"
                    s.carried_res = None
                    s.carried_amount = 0
                    s.target_site = None
                    s.target_stack = None

    # 10. Schedules
    if schedule_manager and "schedules" in data:
        for job_id, sched in data["schedules"].items():
            schedule_manager.job_schedules[job_id] = list(sched)

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
    max_p = max([int(p.id.split("_")[-1]) for p in permit_manager.permits if "_" in p.id and p.id.split("_")[-1].isdigit()] + [0])
    permit_manager.permit_counter = max_p + 1

    max_f = max([int(f.id.split("_")[-1]) for f in furniture_manager.furnitures if "_" in f.id and f.id.split("_")[-1].isdigit()] + [0])
    furniture_manager.counter = max_f + 1

    max_fam = max([int(f.id.split("_")[-1]) for f in villager_manager.families if "_" in f.id and f.id.split("_")[-1].isdigit()] + [0])
    villager_manager.family_counter = max_fam + 1

    all_vils = villager_manager.get_all_villagers()
    max_vil = max([int(v.id.split("_")[-1]) for v in all_vils if "_" in v.id and v.id.split("_")[-1].isdigit()] + [0])
    villager_manager.villager_counter = max_vil + 1

    # 12. Refresh spatial caches & Reset Global Path Registry so stale route reservations from prior session are cleared
    if hasattr(building_manager, "rebuild_tile_cache"):
        building_manager.rebuild_tile_cache()
    if hasattr(furniture_manager, "invalidate_cache"):
        furniture_manager.invalidate_cache()

    from game.world.pathfinding import GlobalPathRegistry
    GlobalPathRegistry.get_instance().reset()

    return True, f"Loaded Slot {slot_id} successfully!"
