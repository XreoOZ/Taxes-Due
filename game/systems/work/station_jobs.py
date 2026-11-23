"""Production-station jobs: Woodsman (forest felling) and Miner (ore mining).

Both jobs share the same workstation flow:

    work schedule -> equip tools (generic job-tool system) -> produce into
    the personal inventory -> deposit into the assigned workstation's
    filtered inventory -> once the daily quota is reached, carry output to
    the worker's own household chest -> haul leftover workstation stock to
    the chest as a low-priority chore -> back to any activities.

Workstation leftovers are never urgent: they are only collected during
WORK/ANY schedule slots or explicit idle hauling, and villager needs keep
priority through the normal need-task flow.
"""
import math
import random

from game.data.config import (
    DEDICATED_JOBS,
    TILE_SIZE,
    WOODSMAN_CUT_INGAME_HOURS,
    WOODSMAN_PLANT_INGAME_HOURS,
    TREE_WOOD_YIELD_MIN,
    TREE_WOOD_YIELD_MAX,
    AI_CRITICAL_NEED_THRESHOLD,
)
from game.world.natural_resources import (
    TREE_STATE_MATURE,
    NaturalResourceManager,
    get_natural_resources,
)

JOB_IDS = ("Woodsman", "Miner")


class StationJobSystem:
    """Shared work-loop for furniture-based production jobs."""

    # ------------------------------------------------------------------
    # Workplace lookup
    # ------------------------------------------------------------------
    @staticmethod
    def find_station(villager, job_id, furniture_manager):
        job_cfg = DEDICATED_JOBS.get(job_id, {})
        furniture_type = job_cfg.get("workplace_furniture_type")
        if not furniture_type or furniture_manager is None:
            return None
        for f in getattr(furniture_manager, "furnitures", []):
            if f.furniture_type != furniture_type:
                continue
            if f.is_dropped or f.stored_in_id is not None or f.is_broken:
                continue
            if not getattr(f, "is_available_for_use", False):
                continue
            if str(villager.id) not in [str(w) for w in getattr(f, "assigned_workers", [])]:
                continue
            return f
        return None

    @staticmethod
    def _current_day(day_cycle):
        if day_cycle is None:
            return 1.0
        try:
            return float(day_cycle.day_number) + float(day_cycle.get_time_ratio())
        except Exception:
            return float(getattr(day_cycle, "day_number", 1) or 1)

    @staticmethod
    def _reset_quota_if_new_day(station, day_number):
        if int(getattr(station, "station_quota_day", -1)) != int(day_number):
            station.station_quota_today = 0
            station.station_quota_day = int(day_number)

    @staticmethod
    def quota_state(station, day_number):
        StationJobSystem._reset_quota_if_new_day(station, day_number)
        quota_daily = int(getattr(station, "station_quota_daily", 0) or 0)
        produced = int(getattr(station, "station_quota_today", 0) or 0)
        quota_left = (quota_daily - produced) if quota_daily > 0 else 10 ** 9
        return quota_daily, produced, quota_left

    @staticmethod
    def accepted_items(station):
        try:
            return station.station_accepted_items() or set()
        except Exception:
            return set()

    @staticmethod
    def carried_products(villager, accepted):
        return {item: int(amt) for item, amt in villager.inventory.items()
                if item in accepted and int(amt) > 0}

    @staticmethod
    def station_point(station, villager, all_entities, building_manager):
        point = station.get_approach_point(
            villager.x, villager.y, villager.id, all_entities,
            TILE_SIZE, building_manager,
        )
        return point or station.get_world_pos(TILE_SIZE)

    @staticmethod
    def chest_for(villager, furniture_manager):
        if furniture_manager is None:
            return None
        return furniture_manager.get_storage_for_family(villager.family_id)

    # ------------------------------------------------------------------
    # Bagi hasil (production sharing) — same rule as farm harvest
    # ------------------------------------------------------------------
    @classmethod
    def _split_household_shares(cls, villager, station, items,
                                furniture_manager, stockpile_manager,
                                permit_manager, villager_manager, day_cycle):
        """Split produced items among the station's participating workers'
        households, proportional to each household's worker count — the same
        ProductionDistributionSystem rule farming uses. Other households'
        shares are deposited into their own storage immediately; returns the
        dict of items belonging to the villager's own household."""
        if villager_manager is None:
            # Without the manager we cannot resolve worker IDs to households;
            # keep the legacy behavior (everything to the worker's own chest).
            return {item: int(amt) for item, amt in items.items() if int(amt) > 0}
        from game.systems.economy.production_distribution import ProductionDistributionSystem
        ps = ProductionDistributionSystem.get_instance()
        workers = list(getattr(station, "assigned_workers", None) or [villager.id])
        day_number = day_cycle.day_number if day_cycle else 1
        own = {}
        my_fam = str(getattr(villager, "family_id", ""))
        for item, amt in items.items():
            amt = int(amt)
            if amt <= 0:
                continue
            res = ps.distribute_production(
                resource_name=item,
                amount=amt,
                participating_workers=workers,
                furniture_manager=furniture_manager,
                stockpile_manager=stockpile_manager,
                permit_manager=permit_manager,
                villager_manager=villager_manager,
                workplace_id=getattr(station, "id", "station"),
                day_number=day_number,
                auto_deposit=False,
            )
            for h, qty in (res.get("distribution") or {}).items():
                if qty <= 0:
                    continue
                if str(h) == my_fam:
                    own[item] = own.get(item, 0) + qty
                else:
                    ps.deposit_to_household_storage(
                        h, item, qty,
                        furniture_manager=furniture_manager,
                        stockpile_manager=stockpile_manager,
                        permit_manager=permit_manager,
                        villager_manager=villager_manager,
                    )
        return own

    # ------------------------------------------------------------------
    # Deposit flows
    # ------------------------------------------------------------------
    @classmethod
    def _deposit_carried(cls, villager, dt, station, accepted, quota_left,
                         to_station, all_entities, player, building_manager,
                         furniture_manager, stockpile_manager=None,
                         permit_manager=None, villager_manager=None,
                         day_cycle=None):
        """Carry accepted products to the workstation (quota remains) or the
        household chest (quota exhausted)."""
        carried = cls.carried_products(villager, accepted)
        if not carried:
            return False

        if to_station:
            dest = cls.station_point(station, villager, all_entities, building_manager)
            task = "STATION_DEPOSIT_STATION"
        else:
            chest = cls.chest_for(villager, furniture_manager)
            if chest is None:
                return False
            dest = chest.get_approach_point(
                villager.x, villager.y, villager.id, all_entities,
                TILE_SIZE, building_manager,
            ) or chest.get_world_pos(TILE_SIZE)
            task = "STATION_DEPOSIT_CHEST"

        villager.task = task
        villager.active_tool = None
        dom_item, dom_amt = max(carried.items(), key=lambda kv: kv[1])
        villager.carrying_res = dom_item
        villager.carrying_amount = dom_amt
        villager._station_carry_active = True
        arrived = villager._move_towards(
            dest[0], dest[1], dt, arrival_dist=24,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=station if to_station else chest,
        )
        if not arrived:
            return True

        if to_station:
            for item, amt in carried.items():
                stored = station.store_item(item, amt)
                if stored > 0:
                    villager.inventory[item] = villager.inventory.get(item, 0) - stored
                    if villager.inventory[item] <= 0:
                        del villager.inventory[item]
            villager.say("Deposited output into the workstation.", duration=1.5)
        else:
            chest = cls.chest_for(villager, furniture_manager)
            if chest is not None:
                # Bagi hasil: only the villager's own household share lands in
                # their chest; co-workers' households are deposited directly.
                own_share = cls._split_household_shares(
                    villager, station, carried, furniture_manager,
                    stockpile_manager, permit_manager, villager_manager,
                    day_cycle,
                )
                for item, amt in carried.items():
                    villager.inventory[item] = villager.inventory.get(item, 0) - amt
                    if villager.inventory[item] <= 0:
                        villager.inventory.pop(item, None)
                for item, amt in own_share.items():
                    chest.store_item(item, amt)
                villager.say("Deposited output into the household chest.", duration=1.5)
        villager.station_work_timer = 0.0
        villager.carrying_res = None
        villager.carrying_amount = 0
        villager._station_carry_active = False
        return True

    # ------------------------------------------------------------------
    # Workstation leftover hauling (low priority, needs keep precedence)
    # ------------------------------------------------------------------
    @classmethod
    def _fetch_leftovers(cls, villager, dt, station, accepted,
                         all_entities, player, building_manager, furniture_manager,
                         stockpile_manager=None, permit_manager=None,
                         villager_manager=None, day_cycle=None):
        carry = getattr(villager, "station_carry", None)
        if not isinstance(carry, dict):
            carry = {}
            villager.station_carry = carry
        leftovers = {item: int(amt) for item, amt in station.inventory.items()
                     if item in accepted and int(amt) > 0}
        if not leftovers:
            villager.station_carry = {}
            return False

        room = villager.get_inventory_room() - sum(carry.values())
        if room <= 0:
            return cls._deliver_leftovers(villager, dt, station, accepted,
                                          all_entities, player, building_manager,
                                          furniture_manager, stockpile_manager,
                                          permit_manager, villager_manager,
                                          day_cycle)

        dest = cls.station_point(station, villager, all_entities, building_manager)
        villager.task = "STATION_LEFTOVER_FETCH"
        villager.active_tool = None
        arrived = villager._move_towards(
            dest[0], dest[1], dt, arrival_dist=24,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=station,
        )
        if not arrived:
            return True

        for item in list(leftovers):
            if room <= 0:
                break
            avail = int(station.inventory.get(item, 0))
            take = min(avail, room)
            if take <= 0:
                continue
            got = station.take_item(item, take)
            if got > 0:
                carry[item] = carry.get(item, 0) + got
                room -= got
        if not carry:
            villager.task = "IDLE"
            return True
        return cls._deliver_leftovers(villager, dt, station, accepted,
                                      all_entities, player, building_manager,
                                      furniture_manager, stockpile_manager,
                                      permit_manager, villager_manager,
                                      day_cycle)

    @classmethod
    def _deliver_leftovers(cls, villager, dt, station, accepted,
                           all_entities, player, building_manager, furniture_manager,
                           stockpile_manager=None, permit_manager=None,
                           villager_manager=None, day_cycle=None):
        carry = getattr(villager, "station_carry", None) or {}
        carry = {item: amt for item, amt in carry.items() if amt > 0}
        if not carry:
            villager.station_carry = {}
            return False
        dom_item, dom_amt = max(carry.items(), key=lambda kv: kv[1])
        villager.carrying_res = dom_item
        villager.carrying_amount = dom_amt
        villager._station_carry_active = True

        chest = cls.chest_for(villager, furniture_manager)
        if chest is None:
            return False
        dest = chest.get_approach_point(
            villager.x, villager.y, villager.id, all_entities,
            TILE_SIZE, building_manager,
        ) or chest.get_world_pos(TILE_SIZE)
        villager.task = "STATION_LEFTOVER_DELIVER"
        villager.active_tool = None
        arrived = villager._move_towards(
            dest[0], dest[1], dt, arrival_dist=24,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=chest,
        )
        if not arrived:
            return True
        # Bagi hasil: workstation leftovers hauled home are split among the
        # station's participating workers' households like farm harvest.
        own_share = cls._split_household_shares(
            villager, station, carry, furniture_manager,
            stockpile_manager, permit_manager, villager_manager, day_cycle,
        )
        for item, amt in own_share.items():
            chest.store_item(item, amt)
        villager.station_carry = {}
        villager.carrying_res = None
        villager.carrying_amount = 0
        villager._station_carry_active = False
        villager.say("Moved leftover workstation stock to the household chest.", duration=1.8)
        return True

    @classmethod
    def haul_leftovers_if_idle(cls, villager, dt, job_id, furniture_manager,
                               all_entities, player, building_manager,
                               stockpile_manager=None, permit_manager=None,
                               villager_manager=None, day_cycle=None):
        """Free-time entry point: collect workstation leftovers only when all
        needs are comfortably satisfied (needs always keep priority)."""
        if job_id not in JOB_IDS:
            return False
        for attr in ("hunger", "thirst", "need_toilet"):
            if float(getattr(villager, attr, 100.0)) <= AI_CRITICAL_NEED_THRESHOLD:
                return False
        station = cls.find_station(villager, job_id, furniture_manager)
        if station is None:
            return False
        accepted = cls.accepted_items(station)
        if not any(int(amt) > 0 for item, amt in station.inventory.items() if item in accepted):
            return False
        return cls._fetch_leftovers(villager, dt, station, accepted,
                                    all_entities, player, building_manager,
                                    furniture_manager, stockpile_manager,
                                    permit_manager, villager_manager,
                                    day_cycle)

    # ------------------------------------------------------------------
    # Work selection helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _reset_work_state(villager):
        villager.station_work_timer = 0.0
        villager.station_target_tile = None
        villager.station_phase = None
        villager.active_tool = None

    @staticmethod
    def reset_worker_state(villager):
        """Full cleanup on job change / unassign: release tree claims and
        drop any in-progress station work or leftover carry."""
        get_natural_resources().release_tree_claims(villager.id)
        StationJobSystem._reset_work_state(villager)
        villager.station_carry = {}
        if getattr(villager, "_station_carry_active", False):
            villager.carrying_res = None
            villager.carrying_amount = 0
            villager._station_carry_active = False

    # ------------------------------------------------------------------
    # Woodsman
    # ------------------------------------------------------------------
    @classmethod
    def _woodsman_work(cls, villager, dt, station, nr, day_cycle,
                       one_game_hour, current_day, quota_left,
                       all_entities, player, building_manager, furniture_manager):
        accepted = cls.accepted_items(station)
        plant_on = bool(getattr(station, "plant_tree_enabled", False))

        # --- state continuation -------------------------------------
        target = villager.station_target_tile
        phase = getattr(villager, "station_phase", None)

        if target is None:
            # Choose next action: nearest mature tree, else replant tile.
            tree = nr.nearest_tree(villager.x, villager.y, current_day,
                                   exclude_worker_id=villager.id)
            if tree is not None:
                nr.claim_tree(tree[0], tree[1], villager.id)
                target = tree
                phase = "cut"
            elif plant_on:
                tile = nr.nearest_replantable_tile(villager.x, villager.y,
                                                   exclude_worker_id=villager.id)
                if tile is None:
                    cls._reset_work_state(villager)
                    return False
                nr.claim_tree(tile[0], tile[1], villager.id)
                target = tile
                phase = "plant"
            else:
                cls._reset_work_state(villager)
                return False
            villager.station_target_tile = target
            villager.station_phase = phase
            villager.station_work_timer = 0.0

        tx = (target[0] + 0.5) * TILE_SIZE
        ty = (target[1] + 0.5) * TILE_SIZE
        arrived = villager._move_towards(
            tx, ty, dt, arrival_dist=26,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            exclusive_target=True,
        )
        if not arrived:
            villager.task = "STATION_WORK"
            return True

        if phase == "cut":
            # Re-validate: tree may have been cut by someone else.
            if not nr.is_tree_mature(target[0], target[1], current_day):
                nr.release_tree_claims(villager.id)
                cls._reset_work_state(villager)
                return True
            villager.task = "STATION_WORK"
            villager.active_tool = "Felling_Axe"
            villager.station_work_timer += dt
            needed = one_game_hour * WOODSMAN_CUT_INGAME_HOURS
            villager._activity_total = needed
            if villager.station_work_timer >= needed:
                if nr.cut_tree(target[0], target[1]):
                    yield_amt = random.randint(TREE_WOOD_YIELD_MIN, TREE_WOOD_YIELD_MAX)
                    room = villager.get_inventory_room()
                    stored = min(yield_amt, max(0, room))
                    if stored > 0:
                        villager.inventory["Wood"] = villager.inventory.get("Wood", 0) + stored
                    station.station_quota_today = int(
                        getattr(station, "station_quota_today", 0)) + stored
                    villager.say(f"Felled a tree for {stored} Wood!", duration=2.0)
                # Next phase: replant on the same tile when enabled.
                if plant_on and nr.tree_state(target[0], target[1], current_day) == "empty":
                    villager.station_phase = "plant"
                    villager.station_work_timer = 0.0
                else:
                    nr.release_tree_claims(villager.id)
                    cls._reset_work_state(villager)
            return True

        # phase == "plant"
        if nr.tree_state(target[0], target[1], current_day) != "empty":
            nr.release_tree_claims(villager.id)
            cls._reset_work_state(villager)
            return True
        villager.task = "STATION_WORK"
        villager.active_tool = "Spade"
        villager.station_work_timer += dt
        needed = one_game_hour * WOODSMAN_PLANT_INGAME_HOURS
        villager._activity_total = needed
        if villager.station_work_timer >= needed:
            if nr.plant_tree(target[0], target[1], current_day):
                villager.say("Replanted a sapling. It will mature in 10 days.", duration=2.0)
            nr.release_tree_claims(villager.id)
            cls._reset_work_state(villager)
        return True

    # ------------------------------------------------------------------
    # Miner
    # ------------------------------------------------------------------
    @classmethod
    def _miner_work(cls, villager, dt, station, nr, day_cycle,
                    one_game_hour, current_day, quota_left,
                    all_entities, player, building_manager, furniture_manager):
        mine = next((m for m in nr.mines if m.get("id") == getattr(station, "bound_mine_id", None)), None)
        if mine is None:
            cls._reset_work_state(villager)
            return False

        output_item = NaturalResourceManager.mine_output_item(mine)
        lo, hi = NaturalResourceManager.mine_yield_range(mine)

        # Miner works at the workstation approach point — the station sits
        # exactly on the 5x5 mine footprint.
        dest = cls.station_point(station, villager, all_entities, building_manager)
        arrived = villager._move_towards(
            dest[0], dest[1], dt, arrival_dist=30,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            interaction_target=station,
        )
        if not arrived:
            villager.task = "STATION_WORK"
            return True

        villager.task = "STATION_WORK"
        villager.active_tool = "Pickaxe"
        room = villager.get_inventory_room()
        if room <= 0:
            villager.station_work_timer = 0.0
            return True  # inventory full -> deposit flow handles next tick

        villager.station_work_timer += dt
        villager._activity_total = one_game_hour
        quota_daily = int(getattr(station, "station_quota_daily", 0) or 0)
        while villager.station_work_timer >= one_game_hour:
            produced = int(getattr(station, "station_quota_today", 0) or 0)
            quota_remaining = (quota_daily - produced) if quota_daily > 0 else 10 ** 9
            if quota_remaining <= 0:
                break
            villager.station_work_timer -= one_game_hour
            yield_amt = random.randint(lo, hi)
            stored = min(yield_amt, max(0, villager.get_inventory_room()), quota_remaining)
            if stored <= 0:
                break
            villager.inventory[output_item] = villager.inventory.get(output_item, 0) + stored
            station.station_quota_today = produced + stored
            villager.say(f"Mined {stored} {output_item}.", duration=1.6)
        return True

    # ------------------------------------------------------------------
    # Entry point — called from Villager.update() inside WORK/ANY slots
    # ------------------------------------------------------------------
    @classmethod
    def update(cls, villager, dt, job_id, building_manager, furniture_manager,
               villager_manager, all_entities, player, day_cycle,
               stockpile_manager=None, permit_manager=None):
        if job_id not in JOB_IDS:
            return False
        station = cls.find_station(villager, job_id, furniture_manager)
        if station is None:
            cls._reset_work_state(villager)
            return False

        nr = get_natural_resources()
        one_game_hour = (day_cycle.day_length_seconds / 24.0) if day_cycle else 50.0
        current_day = cls._current_day(day_cycle)
        day_number = day_cycle.day_number if day_cycle else 1
        _, _, quota_left = cls.quota_state(station, day_number)
        accepted = cls.accepted_items(station)

        # Mid-haul of workstation leftovers always finishes first.
        if getattr(villager, "station_carry", None):
            return cls._deliver_leftovers(villager, dt, station, accepted,
                                          all_entities, player, building_manager,
                                          furniture_manager, stockpile_manager,
                                          permit_manager, villager_manager,
                                          day_cycle)

        # Carrying fresh output: workstation while quota remains, chest after.
        # *** ESTABLISHED — DO NOT REGRESS ***
        # _station_carry_active guards carrying_res/amount cleanup: without it a
        # stale carry box renders forever after deposits finish or tasks abort.
        carried = cls.carried_products(villager, accepted)
        if (not carried and not getattr(villager, "station_carry", None)
                and getattr(villager, "_station_carry_active", False)):
            villager.carrying_res = None
            villager.carrying_amount = 0
            villager._station_carry_active = False
        if carried and (quota_left <= 0 or villager.get_inventory_room() <= 0):
            return cls._deposit_carried(villager, dt, station, accepted, quota_left,
                                        quota_left > 0, all_entities, player,
                                        building_manager, furniture_manager,
                                        stockpile_manager, permit_manager,
                                        villager_manager, day_cycle)

        # Quota exhausted: stop production, drain leftovers to the chest.
        if quota_left <= 0:
            leftovers = {item: int(amt) for item, amt in station.inventory.items()
                         if item in accepted and int(amt) > 0}
            if leftovers and villager.get_inventory_room() > 0:
                return cls._fetch_leftovers(villager, dt, station, accepted,
                                            all_entities, player, building_manager,
                                            furniture_manager, stockpile_manager,
                                            permit_manager, villager_manager,
                                            day_cycle)
            return False

        if job_id == "Woodsman":
            return cls._woodsman_work(villager, dt, station, nr, day_cycle,
                                      one_game_hour, current_day, quota_left,
                                      all_entities, player, building_manager,
                                      furniture_manager)
        return cls._miner_work(villager, dt, station, nr, day_cycle,
                               one_game_hour, current_day, quota_left,
                               all_entities, player, building_manager,
                               furniture_manager)

    @staticmethod
    def has_work(villager, job_id, furniture_manager, day_cycle=None):
        """Cheap probe for schedule/UI: is there anything this station worker
        could still do today (produce, deposit, or haul leftovers)?"""
        if job_id not in JOB_IDS:
            return False
        station = StationJobSystem.find_station(villager, job_id, furniture_manager)
        if station is None:
            return False
        accepted = StationJobSystem.accepted_items(station)
        if StationJobSystem.carried_products(villager, accepted):
            return True
        if any(int(amt) > 0 for item, amt in station.inventory.items() if item in accepted):
            return True
        day_number = day_cycle.day_number if day_cycle else 1
        _, _, quota_left = StationJobSystem.quota_state(station, day_number)
        if quota_left <= 0:
            return False
        if job_id == "Woodsman":
            nr = get_natural_resources()
            current_day = StationJobSystem._current_day(day_cycle)
            if nr.mature_tree_count() > 0:
                return True
            return bool(getattr(station, "plant_tree_enabled", False)
                        and nr.plantable_tile_count() > 0)
        # Miner: only real work while the workstation is bound to a live mine.
        nr = get_natural_resources()
        bound_id = getattr(station, "bound_mine_id", None)
        return any(m.get("id") == bound_id for m in nr.mines)
