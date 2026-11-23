"""
Generic Work Tool Management & Job Workflow System
Architecture Rules applied:
- MODULAR & PLUG-AND-PLAY: Independent component with generic functions usable by any worker entity.
- ZERO HARDCODE & CONFIG-DRIVEN: Dynamically reads required tools from DEDICATED_JOBS data configuration.
- LEAN CODE: Clean, single responsibility principle, agile & fast.
"""

import math
from game.data.config import (
    TILE_SIZE,
    DEDICATED_JOBS,
    TOOL_TYPES,
    CHEST_INTERACTION_RADIUS,
    TOOL_STOW_ARRIVAL_DIST
)

def get_job_config(job_id):
    """Mendapatkan konfigurasi data untuk suatu pekerjaan/profesi"""
    return DEDICATED_JOBS.get(job_id, {})

def get_job_required_tools(job_id):
    """
    Menghasilkan dictionary {tool_name: required_count} untuk suatu pekerjaan.
    Secara generik membaca dari DEDICATED_JOBS[job_id]['required_tools'].
    Jika list, default count adalah 1 untuk setiap alat.
    """
    job_cfg = get_job_config(job_id)
    raw_tools = job_cfg.get("required_tools", [])
    if isinstance(raw_tools, dict):
        return dict(raw_tools)
    elif isinstance(raw_tools, (list, tuple, set)):
        return {tool: 1 for tool in raw_tools}
    return {}

def is_tool_item(item_name):
    """Mengecek apakah item merupakan alat kerja terdaftar"""
    return item_name in TOOL_TYPES

def get_missing_tools_for_worker(worker):
    """
    Mengidentifikasi alat-alat yang belum dimiliki oleh worker untuk pekerjaannya saat ini.
    Mengembalikan daftar tuple: [(tool_name, missing_count), ...]
    """
    job_id = getattr(worker, "job", None)
    if not job_id:
        return []
    required = get_job_required_tools(job_id)
    inv = getattr(worker, "inventory", {})
    missing = []
    for tool, req_count in required.items():
        cur_count = inv.get(tool, 0)
        if cur_count < req_count:
            missing.append((tool, req_count - cur_count))
    return missing

def get_irrelevant_tools_in_inventory(worker):
    """
    Mengidentifikasi alat-alat di inventory worker yang TIDAK LAGI RELEVAN dengan pekerjaannya saat ini
    (misalnya setelah berganti job) atau merupakan alat berlebih (excess duplicates).
    HANYA mengevaluasi alat kerja terdaftar (is_tool_item), TIDAK menyentuh komoditas/resource normal.
    Mengembalikan daftar tuple: [(tool_name, excess_or_irrelevant_count), ...]
    """
    job_id = getattr(worker, "job", None)
    required = get_job_required_tools(job_id) if job_id else {}
    inv = getattr(worker, "inventory", {})
    irrelevant = []

    for item_name, count in inv.items():
        if count <= 0:
            continue
        if not is_tool_item(item_name):
            continue  # Bukan alat kerja (misal: Potato, Wood, Stone)

        req_count = required.get(item_name, 0)
        excess = count - req_count
        if excess > 0:
            irrelevant.append((item_name, excess))

    return irrelevant

def collect_all_job_tools(worker, furniture_manager, stockpile_manager):
    """
    Mengambil seluruh alat kerja yang dibutuhkan untuk pekerjaan saat ini dari penyimpanan keluarga/desa
    ke dalam inventory worker dalam satu kali kunjungan.
    Mengembalikan daftar nama alat yang berhasil dikumpulkan.
    """
    missing = get_missing_tools_for_worker(worker)
    collected = []
    for tool_name, count in missing:
        for _ in range(count):
            if hasattr(worker, "_equip_family_tool"):
                success = worker._equip_family_tool(tool_name, furniture_manager, stockpile_manager)
                if success:
                    collected.append(tool_name)
    return collected

def deposit_irrelevant_tools(worker, furniture_manager, stockpile_manager):
    """
    Mengembalikan seluruh alat kerja yang tidak lagi relevan atau berlebih ke penyimpanan
    (misalnya setelah berpindah pekerjaan).
    Mengembalikan daftar tuple: [(tool_name, deposited_count), ...]
    """
    irrelevant = get_irrelevant_tools_in_inventory(worker)
    deposited = []
    fam_str = str(getattr(worker, "family_id", ""))
    chest = furniture_manager.get_storage_for_family(fam_str) if furniture_manager and fam_str else None

    for tool_name, count in irrelevant:
        actual = min(count, worker.inventory.get(tool_name, 0))
        if actual <= 0:
            continue
        if chest:
            chest.store_item(tool_name, actual)
            worker.inventory[tool_name] -= actual
            if worker.inventory[tool_name] <= 0:
                del worker.inventory[tool_name]
            deposited.append((tool_name, actual))
        elif stockpile_manager:
            cur_gx = int(math.floor(worker.x / TILE_SIZE))
            cur_gy = int(math.floor(worker.y / TILE_SIZE))
            stockpile_manager.drop_resource(tool_name, actual, cur_gx, cur_gy, owner_type="villager", owner_id=fam_str)
            worker.inventory[tool_name] -= actual
            if worker.inventory[tool_name] <= 0:
                del worker.inventory[tool_name]
            deposited.append((tool_name, actual))

    if getattr(worker, "active_tool", None) not in getattr(worker, "inventory", {}):
        worker.active_tool = None
    return deposited


def assign_job_worker(job_id, permit_manager, villager_manager, furniture_manager=None):
    """
    Universally assigns a worker to any job in DEDICATED_JOBS.
    1. Selects closest available household member without another dedicated active job.
       Distance is measured from their household residence so moving households dynamically updates assignments.
    2. Updates their job and title immediately.
    3. If the job has an associated workplace permit, assigns them to that permit.
    Returns (success: bool, villager or error message).
    """
    if not villager_manager:
        return False, "Villager manager unavailable."

    if job_id == "Priest":
        from game.systems.village_life.church_system import ChurchSystem
        return ChurchSystem.assign_priest(permit_manager, villager_manager, furniture_manager=furniture_manager)
    elif job_id == "Gravedigger":
        from game.systems.village_life.cemetery_system import CemeterySystem
        return CemeterySystem.assign_gravedigger(permit_manager, villager_manager, furniture_manager=furniture_manager)

    job_cfg = DEDICATED_JOBS.get(job_id, {})
    wp_type = job_cfg.get("workplace_permit")

    target_permit = None
    if permit_manager and hasattr(permit_manager, "permits") and wp_type:
        for p in permit_manager.permits:
            if getattr(p, "permit_type", "") == wp_type:
                target_permit = p
                break

    ref_x, ref_y = 0.0, 0.0
    if target_permit and hasattr(target_permit, "grid_x"):
        ref_x = (target_permit.grid_x + target_permit.tiles_w / 2.0) * TILE_SIZE
        ref_y = (target_permit.grid_y + target_permit.tiles_h / 2.0) * TILE_SIZE

    from game.world.permits import find_closest_unassigned_household_worker
    chosen = find_closest_unassigned_household_worker(
        ref_x, ref_y,
        permit_manager=permit_manager,
        villager_manager=villager_manager,
        target_job=job_id,
        furniture_manager=furniture_manager
    )

    if not chosen:
        return False, f"No available household member to assign to {job_id}."

    chosen.set_job(job_id)
    job_name = job_cfg.get("name", job_id)
    chosen.say(f"I am now assigned as {job_name}.", duration=2.5)

    if target_permit and permit_manager:
        if not hasattr(target_permit, "assigned_workers"):
            target_permit.assigned_workers = []
        if str(chosen.id) not in [str(w) for w in target_permit.assigned_workers]:
            target_permit.assigned_workers.append(chosen.id)
        target_permit.max_workers = max(getattr(target_permit, "max_workers", 1), len(target_permit.assigned_workers))

    return True, chosen


def release_job_worker(job_id, permit_manager, villager_manager):
    """
    Universally releases a worker from any job in DEDICATED_JOBS.
    Restores the worker to Unassigned status.
    Returns (success: bool, villager or error message).
    """
    if not villager_manager:
        return False, "Villager manager unavailable."

    if job_id == "Priest":
        from game.systems.village_life.church_system import ChurchSystem
        return ChurchSystem.release_priest(permit_manager, villager_manager)
    elif job_id == "Gravedigger":
        from game.systems.village_life.cemetery_system import CemeterySystem
        return CemeterySystem.release_gravedigger(permit_manager, villager_manager)

    job_cfg = DEDICATED_JOBS.get(job_id, {})
    wp_type = job_cfg.get("workplace_permit")

    all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])

    released_vil = None
    if wp_type and permit_manager and hasattr(permit_manager, "permits"):
        for p in permit_manager.permits:
            if getattr(p, "permit_type", "") == wp_type and getattr(p, "assigned_workers", None):
                pid = p.assigned_workers.pop()
                p.max_workers = max(0, getattr(p, "max_workers", 1) - 1)
                released_vil = next((v for v in all_vils if str(v.id) == str(pid)), None)
                if released_vil:
                    break

    if not released_vil:
        released_vil = next((v for v in all_vils if getattr(v, "job", "") == job_id), None)

    if released_vil:
        released_vil.set_job("Unassigned")
        job_name = job_cfg.get("name", job_id)
        released_vil.say(f"I have stepped down from being a {job_name}.", duration=2.5)
        return True, released_vil

    return False, f"No active worker found for {job_id}."
