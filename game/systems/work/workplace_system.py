"""Shared workplace discovery and worker assignment helpers."""

import math

from game.data.config import DEDICATED_JOBS, TILE_SIZE

# Jobs a villager may hold while still counting as "available" for auto-sort,
# mirroring find_closest_unassigned_household_worker semantics.
AUTO_SORT_AVAILABLE_JOBS = ("Farmer", "Unassigned", "Unemployed", "Peasant", None, "")


def get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager=None):
    cfg = DEDICATED_JOBS.get(job_id, {})
    workplaces = []
    permit_type = cfg.get("workplace_permit")
    for permit in getattr(permit_manager, "permits", []):
        if permit_type and getattr(permit, "permit_type", None) == permit_type:
            workplaces.append(("permit", permit))
    furniture_type = cfg.get("workplace_furniture_type")
    for furniture in getattr(furniture_manager, "furnitures", []):
        furniture_cfg = getattr(furniture, "type_cfg", {})
        order = getattr(furniture, "construction_order", None)
        unfinished_workplace = (
            furniture_cfg.get("workplace_available_while_building", False)
            and order
            and order.get("status") != "COMPLETE"
        )
        if (furniture_type and furniture.furniture_type == furniture_type
                and not furniture.is_dropped and furniture.stored_in_id is None
                and not getattr(furniture, "is_broken", False)
                and (furniture.status == "INSTALLED" or unfinished_workplace)):
            workplaces.append(("furniture", furniture))
    building_type = cfg.get("workplace_building_type")
    for building in getattr(building_manager, "buildings", []):
        if (building_type and getattr(building, "building_type", None) == building_type
                and getattr(building, "is_available_for_use", True)):
            workplaces.append(("building", building))
    return workplaces


def assigned_ids(permit_manager, furniture_manager, building_manager=None):
    ids = set()
    for permit in getattr(permit_manager, "permits", []):
        ids.update(str(worker_id) for worker_id in getattr(permit, "assigned_workers", []))
    for furniture in getattr(furniture_manager, "furnitures", []):
        ids.update(str(worker_id) for worker_id in getattr(furniture, "assigned_workers", []))
    for building in getattr(building_manager, "buildings", []):
        ids.update(str(worker_id) for worker_id in getattr(building, "assigned_workers", []))
    return ids


def workplace_workers(workplace):
    kind, obj = workplace
    if not hasattr(obj, "assigned_workers"):
        obj.assigned_workers = []
    return obj.assigned_workers


def workplace_job_workers(workplace, job_id, villager_manager):
    all_villagers = villager_manager.get_all_villagers() if villager_manager else []
    worker_by_id = {str(v.id): v for v in all_villagers}
    return [worker_id for worker_id in workplace_workers(workplace)
            if str(getattr(worker_by_id.get(str(worker_id)), "job", "")) == str(job_id)]


def workplace_base_capacity(workplace):
    """Hard station limit for furniture/building workplaces; None for expandable permits."""
    kind, obj = workplace
    if kind == "permit":
        return None
    return max(0, int(getattr(obj, "type_cfg", {}).get("max_workers", 1)))


def workplace_capacity(workplace):
    """Effective worker capacity (respects lowered custom max_workers, capped at hardware limit)."""
    kind, obj = workplace
    if kind == "permit":
        from game.world.permits import permit_worker_cap
        return permit_worker_cap(obj)
    base_cap = workplace_base_capacity(workplace)
    custom_cap = getattr(obj, "max_workers", None)
    if custom_cap is None:
        return base_cap
    return max(0, min(base_cap, int(custom_cap)))


def set_workplace_max_workers(job_id, workplace, new_max, permit_manager=None, furniture_manager=None, villager_manager=None):
    """Adjust effective max workers for a workplace.

    Hardware-capped stations (furniture/buildings) can be reduced down to 0
    (e.g. 0/2 -> 0/1) but never raised above base_cap (0/2 cannot become 0/3).
    Excess assigned workers are cleanly released to Unassigned.
    """
    kind, obj = workplace
    if kind == "permit":
        cur = int(getattr(obj, "max_workers", 2))
        target = max(0, int(new_max))
        if permit_manager and target != cur:
            permit_manager.change_max_workers(
                obj.id, target - cur, villager_manager,
                furniture_manager=furniture_manager, auto_assign=False,
            )
        return target

    base_cap = workplace_base_capacity(workplace)
    clamped = max(0, min(base_cap, int(new_max)))
    obj.max_workers = clamped
    if villager_manager:
        workers = workplace_workers(workplace)
        while len(workplace_job_workers(workplace, job_id, villager_manager)) > clamped:
            job_workers = workplace_job_workers(workplace, job_id, villager_manager)
            if not job_workers:
                break
            wid = job_workers[-1]
            workers[:] = [item for item in workers if str(item) != str(wid)]
            worker = next((v for v in villager_manager.get_all_villagers() if str(v.id) == str(wid)), None)
            if worker:
                worker.set_job("Unassigned")
    return clamped


def set_job_worker_count(job_id, target_count, permit_manager, furniture_manager, villager_manager, building_manager=None):
    """Set total staffed workers for a job, filling topmost workplaces first.

    - Increasing fills workplaces[0] up to its capacity before moving to workplaces[1], etc.
    - Decreasing removes workers from the bottommost filled workplace first.
    - Never exceeds the combined capacity of existing workplaces.
    Returns the resulting assigned worker count.
    """
    if not villager_manager:
        return 0
    workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
    if not workplaces:
        return 0

    total_cap = sum((workplace_capacity(wp) or 0) for wp in workplaces)
    target = max(0, min(total_cap, int(target_count)))
    filled = sum(len(workplace_job_workers(wp, job_id, villager_manager)) for wp in workplaces)

    if target > filled:
        for wp in workplaces:
            cap = workplace_capacity(wp)
            while filled < target and (cap is None or len(workplace_workers(wp)) < cap):
                if not change_workplace_workers(
                    job_id, wp, 1, permit_manager, furniture_manager, villager_manager, building_manager
                ):
                    break
                filled += 1
            if filled >= target:
                break
    elif target < filled:
        for wp in reversed(workplaces):
            while filled > target and len(workplace_job_workers(wp, job_id, villager_manager)) > 0:
                if not change_workplace_workers(
                    job_id, wp, -1, permit_manager, furniture_manager, villager_manager, building_manager
                ):
                    break
                filled -= 1
            if filled <= target:
                break
    return filled


def change_workplace_workers(job_id, workplace, delta, permit_manager, furniture_manager, villager_manager, building_manager=None):
    from game.world.permits import find_closest_unassigned_household_worker, get_villager_home_position

    kind, obj = workplace
    workers = workplace_workers(workplace)
    if delta < 0:
        job_workers = workplace_job_workers(workplace, job_id, villager_manager)
        if not job_workers:
            return False
        worker_id = job_workers[-1]
        workers[:] = [item for item in workers if str(item) != str(worker_id)]
        worker = next((v for v in villager_manager.get_all_villagers() if str(v.id) == str(worker_id)), None)
        if worker:
            worker.set_job("Unassigned")
        return True

    capacity = workplace_capacity(workplace)
    if (capacity is not None and len(workers) >= capacity) or not villager_manager:
        return False
    if kind == "permit":
        x = (obj.grid_x + obj.tiles_w / 2.0) * TILE_SIZE
        y = (obj.grid_y + obj.tiles_h / 2.0) * TILE_SIZE
    else:
        x = (obj.grid_x + obj.type_cfg.get("width_tiles", 1) / 2.0) * TILE_SIZE
        y = (obj.grid_y + obj.type_cfg.get("height_tiles", 1) / 2.0) * TILE_SIZE
    chosen = find_closest_unassigned_household_worker(
        x, y, permit_manager=permit_manager, villager_manager=villager_manager,
        target_job=job_id, furniture_manager=furniture_manager,
        exclude_worker_ids=assigned_ids(permit_manager, furniture_manager, building_manager),
    )
    if not chosen:
        return False
    chosen.set_job(job_id)
    workers.append(chosen.id)
    return True


def unassign_workplace_worker(job_id, workplace, worker_id, villager_manager):
    workers = workplace_workers(workplace)
    workers[:] = [item for item in workers if str(item) != str(worker_id)]
    worker = next((v for v in villager_manager.get_all_villagers() if str(v.id) == str(worker_id)), None)
    if worker:
        worker.set_job("Unassigned")
    return worker is not None


def _workplace_center_px(kind, obj):
    """World-pixel center of any workplace kind (permit/furniture/building)."""
    w = getattr(obj, "tiles_w", getattr(obj, "type_cfg", {}).get("width_tiles", 1))
    h = getattr(obj, "tiles_h", getattr(obj, "type_cfg", {}).get("height_tiles", 1))
    return ((obj.grid_x + w / 2.0) * TILE_SIZE,
            (obj.grid_y + h / 2.0) * TILE_SIZE)


def auto_sort_all_workers(permit_manager, furniture_manager, villager_manager,
                          building_manager=None, job_filter=None):
    """Full workforce recalibration across every workplace kind (permits,
    furniture, buildings).

    Clears each dedicated-job workplace roster once (shared workplaces like
    construction permits serve several jobs), resets those workers to
    Unassigned, then greedily assigns the closest available villagers to the
    nearest vacancies. Returns the number of assignments made."""
    from game.world.permits import get_villager_home_position

    if not villager_manager:
        return 0
    all_villagers = villager_manager.get_all_villagers()
    villager_by_id = {str(v.id): v for v in all_villagers}

    jobs = [job_id for job_id, job_cfg in DEDICATED_JOBS.items()
            if job_id != "Unassigned"
            and job_cfg.get("auto_sortable", True)
            and (not job_filter or job_id == job_filter)]

    # Phase 1: gather workplaces per job and wipe each roster exactly once.
    workplaces_by_job = {}
    cleared = set()
    for job_id in jobs:
        workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
        workplaces_by_job[job_id] = workplaces
        for kind, obj in workplaces:
            key = (kind, id(obj))
            if key in cleared:
                continue
            cleared.add(key)
            workers = workplace_workers((kind, obj))
            for wid in list(workers):
                worker = villager_by_id.get(str(wid))
                if worker is not None:
                    worker.set_job("Unassigned")
            workers.clear()

    # Phase 2: global greedy fill — every (worker, workplace) candidate sorted
    # purely by home-to-workplace distance so the nearest villager wins.
    assigned_now = set()
    candidates = []
    for job_id in jobs:
        for kind, obj in workplaces_by_job[job_id]:
            capacity = workplace_capacity((kind, obj))
            if capacity is not None and capacity <= 0:
                continue
            cx, cy = _workplace_center_px(kind, obj)
            for v in all_villagers:
                if not getattr(v, "is_alive", True):
                    continue
                vid = str(v.id)
                if vid in assigned_now:
                    continue
                cur_job = getattr(v, "job", "Farmer")
                if cur_job not in AUTO_SORT_AVAILABLE_JOBS and cur_job != job_id:
                    continue
                hx, hy = get_villager_home_position(v, villager_manager, permit_manager, furniture_manager)
                candidates.append((math.hypot(cx - hx, cy - hy), vid, job_id, kind, obj))

    candidates.sort(key=lambda c: (c[0], c[1]))
    made = 0
    for _dist, vid, job_id, kind, obj in candidates:
        if vid in assigned_now:
            continue
        workers = workplace_workers((kind, obj))
        capacity = workplace_capacity((kind, obj))
        if capacity is not None and len(workers) >= capacity:
            continue
        worker = villager_by_id.get(vid)
        if worker is None:
            continue
        worker.set_job(job_id)
        workers.append(worker.id)
        assigned_now.add(vid)
        made += 1
    return made


def unassign_all_workers(permit_manager, furniture_manager, villager_manager,
                         building_manager=None):
    """Clears every dedicated-job workplace roster and marks those workers
    Unassigned, so a following auto-sort can recalibrate from scratch.
    Church permits are skipped (the Priest has a dedicated assignment flow).
    Returns the number of workers released."""
    if not villager_manager:
        return 0
    villager_by_id = {str(v.id): v for v in villager_manager.get_all_villagers()}
    released = 0
    seen = set()
    collections = [
        ("permit", getattr(permit_manager, "permits", [])),
        ("furniture", getattr(furniture_manager, "furnitures", [])),
        ("building", getattr(building_manager, "buildings", []) if building_manager else []),
    ]
    for kind, objects in collections:
        for obj in objects:
            if kind == "permit" and getattr(obj, "permit_type", "") == "church":
                continue
            workers = getattr(obj, "assigned_workers", None)
            if not workers:
                continue
            key = (kind, id(obj))
            if key in seen:
                continue
            seen.add(key)
            for wid in list(workers):
                worker = villager_by_id.get(str(wid))
                if worker is not None and getattr(worker, "job", "") in DEDICATED_JOBS:
                    worker.set_job("Unassigned")
                released += 1
            workers.clear()
    return released
