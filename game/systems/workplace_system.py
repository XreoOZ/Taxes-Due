"""Shared workplace discovery and worker assignment helpers."""

from game.data.config import DEDICATED_JOBS, TILE_SIZE


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


def workplace_capacity(workplace):
    """Worker capacity of a workplace (permit max_workers or furniture/building max_workers)."""
    kind, obj = workplace
    if kind == "permit":
        from game.world.permits import permit_worker_cap
        return permit_worker_cap(obj)
    return max(0, int(getattr(obj, "type_cfg", {}).get("max_workers", 1)))


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
