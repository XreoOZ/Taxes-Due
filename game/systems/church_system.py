"""
Church, Priest, Prayer Time & Church Tax System (AGENT 2)
Coordinates gameplay logic for:
1. Church Permit & Building Construction (Wooden/Stone Structure inside Church Permit).
2. Priest Job Assignment: dynamically selects closest available household member with no other active job, changes title to Priest, and handles worker release via [- Number of Workers +].
3. Prayer Time Schedule: one indivisible daily block shared by every job.
4. Household Prayer & Church Tax Flow: the first household member to arrive pays the configured tax, or all remaining coins when short.
5. Church Tax Settings: configurable in Taxes menu with Gold, Silver, Copper coin stepper controls.
6. Priest Workflow: travels to Church, receives tithes, remains until prayer ends, deposits coins into household chest, and preaches near village infrastructure during work hours.
7. Prayer Time Priority: halts normal job activity during prayer time; resumes normal activity afterwards.
Zero hardcoding, config-driven.
"""

import math
import random
from game.config import (
    TILE_SIZE,
    DEFAULT_CHURCH_TAX
)
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    transfer_exact_value,
)
from game.systems.wealth_system import VillageWealthSystem


class ChurchSystem:
    _instance = None

    def __init__(self):
        self.tax_paid_households_today = set()  # set of family_ids that paid tax today
        self.last_tax_day = 1
        self.occupied_prayer_tiles = {}         # (gx, gy) -> villager_id
        self.prayer_tile_by_villager = {}       # villager_id -> (gx, gy), for constant-time lookup/release
        self.church_walkable_cache = {}         # permit_id -> (layout signature, walkable tiles)
        self.church_permit_by_manager = {}      # manager id -> (permit list signature, church permit)
        self.priest_by_villager_manager = {}    # manager id -> (priest object or None, cache valid)
        # *** ESTABLISHED FEATURE — DO NOT REMOVE/REVERT ***
        # WARNING (FPS-critical, user-verified): has_church_building() is
        # evaluated per villager per frame during prayer routines. Without
        # this cache it loops every church permit x every building x
        # tile-overlap check each call, which caused a massive frame spike
        # when the congregation exits prayer simultaneously (user confirmed
        # the fix: 30+ AI leaving church stays smooth). The signature only
        # changes when the permit/building collections themselves change, so
        # the result stays correct. DO NOT remove this cache or call
        # overlaps_building() per-villager.
        self.church_building_cache = None        # (signature, has_building)
        self.configured_tax = {"Gold": 0, "Silver": 0, "Copper": 1}
        self.tax_enabled = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ChurchSystem()
        return cls._instance

    @classmethod
    def get_church_permit(cls, permit_manager):
        """Returns the first active Church permit."""
        if not permit_manager:
            return None
        inst = cls.get_instance()
        manager_key = id(permit_manager)
        permits = getattr(permit_manager, "permits", [])
        signature = (id(permits), len(permits))
        cached = inst.church_permit_by_manager.get(manager_key)
        if cached and cached[0] == signature:
            return cached[1]
        for p in getattr(permit_manager, "permits", []):
            if getattr(p, "permit_type", "") == "church":
                inst.church_permit_by_manager[manager_key] = (signature, p)
                return p
        inst.church_permit_by_manager[manager_key] = (signature, None)
        return None

    @classmethod
    def get_all_church_permits(cls, permit_manager):
        if not permit_manager:
            return []
        return [p for p in getattr(permit_manager, "permits", []) if getattr(p, "permit_type", "") == "church"]

    @classmethod
    def has_church_building(cls, permit_manager, building_manager):
        """True only when a physical structure overlaps a church permit (permit alone does not count).

        *** ESTABLISHED — DO NOT REMOVE ***
        PERF: result is cached per permit/building collection signature — see
        the church_building_cache warning in __init__. This runs per villager
        per frame during prayer; do not bypass the cache."""
        buildings = getattr(building_manager, "buildings", []) if building_manager else []
        all_permits = getattr(permit_manager, "permits", []) if permit_manager else []
        permits = [p for p in all_permits if getattr(p, "permit_type", "") == "church"]
        signature = (id(all_permits), len(all_permits), id(buildings), len(buildings))
        inst = cls.get_instance()
        cached = getattr(inst, "church_building_cache", None)
        if cached and cached[0] == signature:
            return cached[1]
        result = any(
            permit.overlaps_building(b)
            for permit in permits for b in buildings
        )
        inst.church_building_cache = (signature, result)
        return result

    @classmethod
    def get_assigned_priest(cls, permit_manager, villager_manager):
        """
        Returns the assigned Priest villager.
        Checks church permit assigned_workers first, then any active villager with job == 'Priest'.
        """
        if not villager_manager:
            return None
        inst = cls.get_instance()
        manager_key = id(villager_manager)
        cached = inst.priest_by_villager_manager.get(manager_key)
        if cached and cached[1]:
            priest = cached[0]
            if priest is None or (getattr(priest, "is_alive", True) and getattr(priest, "job", "") == "Priest"):
                return priest
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])
        
        # 1. From active Church permit
        church = cls.get_church_permit(permit_manager)
        if church and getattr(church, "assigned_workers", None):
            priest_id = church.assigned_workers[0]
            p_vil = next((v for v in all_vils if str(v.id) == str(priest_id) and getattr(v, "is_alive", True)), None)
            if p_vil:
                inst.priest_by_villager_manager[manager_key] = (p_vil, True)
                return p_vil

        # 2. Any active villager with Priest job
        priest = next((v for v in all_vils if getattr(v, "job", "") == "Priest" and getattr(v, "is_alive", True)), None)
        inst.priest_by_villager_manager[manager_key] = (priest, True)
        return priest

    @classmethod
    def assign_priest(cls, permit_manager, villager_manager, target_permit=None, furniture_manager=None):
        """
        Assigns the closest available household member without an active job as Priest.
        Distance is measured from their household residence so moving households dynamically updates assignments.
        Changes their title to Priest and registers them to the church permit.
        Returns (success: bool, villager or error message).
        """
        if not villager_manager:
            return False, "Villager manager unavailable."

        if cls.get_assigned_priest(permit_manager, villager_manager):
            return False, "The Church already has its one assigned Priest."

        church = target_permit or cls.get_church_permit(permit_manager)

        # Reference location: center of church permit or origin
        if church:
            cx = (church.grid_x + church.tiles_w / 2.0) * TILE_SIZE
            cy = (church.grid_y + church.tiles_h / 2.0) * TILE_SIZE
        else:
            cx, cy = 0.0, 0.0

        from game.world.permits import find_closest_unassigned_household_worker
        chosen = find_closest_unassigned_household_worker(
            cx, cy,
            permit_manager=permit_manager,
            villager_manager=villager_manager,
            target_job="Priest",
            furniture_manager=furniture_manager
        )

        if not chosen:
            return False, "No available household member without an active job."

        # Assign job and title
        chosen.set_job("Priest")
        chosen.title = "Village Priest"
        cls.get_instance().priest_by_villager_manager[id(villager_manager)] = (chosen, True)

        if church:
            if not hasattr(church, "assigned_workers"):
                church.assigned_workers = []
            if chosen.id not in church.assigned_workers:
                church.assigned_workers.append(chosen.id)
            church.max_workers = max(1, len(church.assigned_workers))

        chosen.say("I have taken holy vows as Village Priest.", duration=3.0)
        return True, chosen

    @classmethod
    def release_priest(cls, permit_manager, villager_manager, target_permit=None):
        """
        Releases an assigned Priest, restoring them to normal household member status.
        """
        if not villager_manager:
            return False, "Villager manager unavailable."

        church = target_permit or cls.get_church_permit(permit_manager)
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])

        released_vil = None
        if church and getattr(church, "assigned_workers", None):
            pid = church.assigned_workers.pop()
            church.max_workers = max(0, getattr(church, "max_workers", 1) - 1)
            released_vil = next((v for v in all_vils if str(v.id) == str(pid)), None)

        if not released_vil:
            # Fallback: find any villager with Priest job
            released_vil = next((v for v in all_vils if getattr(v, "job", "") == "Priest"), None)

        if released_vil:
            if hasattr(released_vil, "set_job"):
                released_vil.set_job("Unassigned")
            else:
                released_vil.job = "Unassigned"
                released_vil.title = "Peasant Farmer"
            released_vil.say("I have stepped down from the priesthood.", duration=2.5)
            cls.get_instance().priest_by_villager_manager[id(villager_manager)] = (None, True)
            return True, released_vil

        return False, "No Priest currently assigned."

    @classmethod
    def get_prayer_time_interval(cls, schedule_manager):
        """
        Returns the contiguous (start_hour, end_hour) of the Priest's Prayer Time block.
        """
        if not schedule_manager:
            return (12.0, 14.0)
        s, e = schedule_manager.get_prayer_hours()
        return (float(s), float(e))

    @classmethod
    def is_prayer_time(cls, current_hour, schedule_manager):
        """Returns True if the current hour falls within the Priest's Prayer Time."""
        interval = cls.get_prayer_time_interval(schedule_manager)
        if not interval:
            return False
        h = float(current_hour) % 24.0
        return interval[0] <= h < interval[1]

    @classmethod
    def set_tax_settings(cls, gold, silver, copper, permit_manager=None):
        """Sets the configured church tax denominations and synchronizes across church permits."""
        inst = cls.get_instance()
        inst.configured_tax = {
            "Gold": max(0, int(gold)),
            "Silver": max(0, int(silver)),
            "Copper": max(0, int(copper))
        }
        if permit_manager:
            for p in cls.get_all_church_permits(permit_manager):
                p.church_tax = dict(inst.configured_tax)
                p.tax_gold = inst.configured_tax["Gold"]
                p.tax_silver = inst.configured_tax["Silver"]
                p.tax_copper = inst.configured_tax["Copper"]

    @classmethod
    def set_tax_enabled(cls, enabled):
        cls.get_instance().tax_enabled = bool(enabled)
        VillageWealthSystem.mark_dirty()

    @classmethod
    def is_tax_enabled(cls):
        return bool(getattr(cls.get_instance(), "tax_enabled", False))

    @classmethod
    def get_tax_settings(cls, church_permit=None):
        """Returns configured church tax dictionary: {'Gold': g, 'Silver': s, 'Copper': c}."""
        if church_permit:
            g = getattr(church_permit, "tax_gold", getattr(church_permit, "church_tax", {}).get("Gold", 0))
            s = getattr(church_permit, "tax_silver", getattr(church_permit, "church_tax", {}).get("Silver", 0))
            c = getattr(church_permit, "tax_copper", getattr(church_permit, "church_tax", {}).get("Copper", 1))
            return {"Gold": g, "Silver": s, "Copper": c}
        return dict(cls.get_instance().configured_tax)

    @classmethod
    def get_configured_tax_amount(cls, church_permit=None):
        """Returns the daily church tax configuration in Copper."""
        settings = cls.get_tax_settings(church_permit)
        return to_copper(settings)

    @classmethod
    def has_household_paid_tax(cls, family_id, church_permit=None):
        fam_str = str(family_id)
        inst = cls.get_instance()
        return fam_str in inst.tax_paid_households_today

    @classmethod
    def mark_tax_paid(cls, family_id, church_permit=None):
        fam_str = str(family_id)
        inst = cls.get_instance()
        inst.tax_paid_households_today.add(fam_str)

    @classmethod
    def _apply_church_tax_unhappiness(cls, family_id, church_permit, villager_manager, day_number):
        from game.systems.taxation_system import TaxationSystem
        TaxationSystem.apply_tax_unhappiness(
            family_id, "tax_church",
            TaxationSystem.church_tax_happiness_amount(church_permit),
            villager_manager, day_number,
        )

    @classmethod
    def prepare_church_tax_payment(cls, representative, church_permit, furniture_manager,
                                   day_number=1):
        """Have the household representative take today's tithe from their chest before prayer."""
        if not representative or not cls.is_tax_enabled():
            return 0
        fam_id = getattr(representative, "family_id", None)
        day = max(1, int(day_number or 1))
        if not fam_id or cls.has_household_paid_tax(fam_id, church_permit):
            return 0
        if getattr(representative, "church_tax_prepared_day", None) == day:
            return int(getattr(representative, "church_tax_prepared_amount", 0))
        due = cls.get_configured_tax_amount(church_permit)
        if due <= 0:
            representative.church_tax_prepared_day = day
            representative.church_tax_prepared_amount = 0
            return 0
        chest = furniture_manager.get_storage_for_family(fam_id) if furniture_manager else None
        source = getattr(chest, "inventory", None) if chest else None
        available = to_copper(normalize_wallet(source))
        amount = min(due, available)
        if amount > 0:
            if not isinstance(getattr(representative, "inventory", None), dict):
                representative.inventory = {}
            success, _ = transfer_exact_value(source, representative.inventory, amount)
            if not success:
                amount = 0
        representative.church_tax_prepared_day = day
        representative.church_tax_prepared_amount = amount
        if amount > 0:
            VillageWealthSystem.mark_dirty()
        return amount

    @classmethod
    def reset_daily_taxes(cls, current_day, permit_manager=None):
        inst = cls.get_instance()
        inst.tax_paid_households_today.clear()
        inst.last_tax_day = current_day
        inst.occupied_prayer_tiles.clear()
        inst.prayer_tile_by_villager.clear()
        inst.church_walkable_cache.clear()
        inst.church_permit_by_manager.clear()
        inst.priest_by_villager_manager.clear()
        if permit_manager:
            for p in cls.get_all_church_permits(permit_manager):
                if hasattr(p, "tax_paid_households_today"):
                    p.tax_paid_households_today.clear()

    @classmethod
    def select_household_representative(cls, family, villager_manager=None):
        """Selects exactly 1 representative adult member for the household to pay tax."""
        if not family or not getattr(family, "members", []):
            return None
        alive_members = [m for m in family.members if getattr(m, "is_alive", True)]
        if not alive_members:
            return None
        adults = [m for m in alive_members if getattr(m, "age", 20) >= 16]
        return adults[0] if adults else alive_members[0]

    @classmethod
    def process_church_tax_payment(cls, representative, priest, church_permit,
                                  furniture_manager=None, villager_manager=None,
                                  day_number=1):
        """
        Payment rules:
        - If household has enough coins: collects the configured amount.
        - If household has insufficient coins: collect all remaining coins as partial payment.
        - If household has no coins: does not pay.
        - Collected coins transferred directly into Priest's personal inventory.
        - Marked paid once per household per day.
        """
        if not representative or not priest or not cls.is_tax_enabled():
            return 0

        fam_id = getattr(representative, "family_id", None)
        if not fam_id or cls.has_household_paid_tax(fam_id, church_permit):
            return 0

        target_copper = cls.get_configured_tax_amount(church_permit)
        if target_copper <= 0:
            cls.mark_tax_paid(fam_id, church_permit)
            return 0

        day = max(1, int(day_number or 1))
        if getattr(representative, "church_tax_prepared_day", None) != day:
            cls.prepare_church_tax_payment(representative, church_permit, furniture_manager, day)
        prepared = max(0, int(getattr(representative, "church_tax_prepared_amount", 0)))
        paid_copper = min(target_copper, prepared)

        if paid_copper <= 0:
            cls.mark_tax_paid(fam_id, church_permit)
            cls._apply_church_tax_unhappiness(fam_id, church_permit, villager_manager, day)
            representative.say("Our household has no coins for today's church tithe, Father.", duration=2.2)
            return 0

        if not isinstance(getattr(priest, "inventory", None), dict):
            priest.inventory = {}
        transfer_success, _ = transfer_exact_value(representative.inventory, priest.inventory, paid_copper)

        if transfer_success:
            VillageWealthSystem.mark_dirty()
            representative.church_tax_prepared_amount = 0
            cls.mark_tax_paid(fam_id, church_permit)
            cls._apply_church_tax_unhappiness(fam_id, church_permit, villager_manager, day)
            from game.systems.market_sales_report import MarketSalesReportSystem
            if str(getattr(priest, "family_id", "")) != str(fam_id):
                MarketSalesReportSystem.record_household_income(
                    villager_manager, getattr(priest, "family_id", None),
                    "Church Tax", paid_copper, day_number,
                )
            representative.say(f"Paid {paid_copper}c Church Tax on behalf of our household.", duration=2.2)
            priest.say("Blessings upon your household.", duration=2.2)
            return paid_copper

        return 0

    @classmethod
    def refund_unpaid_church_tax(cls, representative, furniture_manager):
        amount = max(0, int(getattr(representative, "church_tax_prepared_amount", 0)))
        if amount <= 0:
            return 0
        fam_id = getattr(representative, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        if not chest:
            return 0
        success, _ = transfer_exact_value(representative.inventory, chest.inventory, amount)
        if not success:
            return 0
        representative.church_tax_prepared_amount = 0
        VillageWealthSystem.mark_dirty()
        return amount

    @classmethod
    def get_church_walkable_tiles(cls, church_permit, building_manager):
        """
        Discovers walkable tiles inside the church structure built on church permit,
        or open permit tiles if no building constructed yet.
        """
        if not church_permit:
            return []
        if not hasattr(church_permit, "tiles"):
            return []
        buildings = getattr(building_manager, "buildings", []) if building_manager else []
        permit_id = str(getattr(church_permit, "id", id(church_permit)))
        signature = (
            len(church_permit.tiles),
            id(church_permit.tiles),
            len(buildings),
            id(getattr(building_manager, "_tile_to_building", None)),
        )
        inst = cls.get_instance()
        cached = inst.church_walkable_cache.get(permit_id)
        if cached and cached[0] == signature:
            return cached[1]
        church_blds = [b for b in buildings if church_permit.overlaps_building(b)]
        if church_blds:
            tiles = set()
            for b in church_blds:
                tiles.update(b.tiles)
            walkable = sorted(tiles)
        else:
            walkable = sorted(church_permit.tiles)
        inst.church_walkable_cache[permit_id] = (signature, walkable, set(walkable))
        return walkable

    @classmethod
    def find_free_church_tile(cls, villager, church_permit, building_manager):
        """
        Finds an available tile inside the church for prayer.
        If Church is full, returns None.
        """
        tiles = cls.get_church_walkable_tiles(church_permit, building_manager)
        inst = cls.get_instance()
        vid_str = str(villager.id)

        permit_id = str(getattr(church_permit, "id", id(church_permit)))
        cached_walkable = inst.church_walkable_cache.get(permit_id)
        walkable_set = cached_walkable[2] if cached_walkable and len(cached_walkable) > 2 else set(tiles)
        assigned = inst.prayer_tile_by_villager.get(vid_str)
        if assigned in walkable_set and inst.occupied_prayer_tiles.get(assigned) == vid_str:
            return assigned
        if assigned is not None:
            if inst.occupied_prayer_tiles.get(assigned) == vid_str:
                del inst.occupied_prayer_tiles[assigned]
            inst.prayer_tile_by_villager.pop(vid_str, None)

        for t in tiles:
            occupant = inst.occupied_prayer_tiles.get(t)
            if occupant is None or occupant == vid_str:
                inst.occupied_prayer_tiles[t] = vid_str
                inst.prayer_tile_by_villager[vid_str] = t
                return t
        return None

    @classmethod
    def release_church_tile(cls, villager):
        inst = cls.get_instance()
        vid_str = str(villager.id)
        tile = inst.prayer_tile_by_villager.pop(vid_str, None)
        if tile is not None and inst.occupied_prayer_tiles.get(tile) == vid_str:
            del inst.occupied_prayer_tiles[tile]

    @classmethod
    def priest_deposit_tithes_home(cls, priest, furniture_manager):
        """
        Deposits all collected tithes from priest's personal currency
        into their assigned household chest.
        """
        if not priest or not isinstance(getattr(priest, "inventory", None), dict):
            return 0

        fam_id = getattr(priest, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        if not chest:
            return 0

        from game.systems.currency import canonical_denomination
        inventory_wallet = normalize_wallet(priest.inventory)
        legacy_wallet = normalize_wallet(getattr(priest, "currency", {}))
        combined_wallet = {
            denomination: inventory_wallet[denomination] + legacy_wallet[denomination]
            for denomination in ("Copper", "Silver", "Gold")
        }
        total_deposited_copper = to_copper(combined_wallet)
        if total_deposited_copper <= 0:
            return 0

        for wallet in (priest.inventory, getattr(priest, "currency", {})):
            for key in list(wallet):
                if canonical_denomination(key):
                    del wallet[key]
        priest.inventory.update({den: count for den, count in combined_wallet.items() if count > 0})
        transfer_exact_value(priest.inventory, chest.inventory, total_deposited_copper)

        priest.say(f"Deposited {total_deposited_copper}c tithes into household chest.", duration=2.5)
        return total_deposited_copper

    @classmethod
    def execute_priest_preaching(cls, priest, dt, building_manager, all_entities=None):
        """
        During Work Time outside Prayer Time:
        Priest walks around village near existing infrastructure and preaches.
        Does not wander excessively far from village.
        """
        priest.active_tool = None
        priest.task = "PREACHING"
        priest.preach_timer = getattr(priest, "preach_timer", 0.0) + dt

        if priest.preach_timer >= 6.0:
            priest.preach_timer = 0.0
            sermons = [
                "Walk in righteousness and peace, good villagers!",
                "May the Lord bless our village harvest and labor.",
                "Give thanks for the bounty of our land.",
                "Faith, diligence, and unity bind our settlement together.",
                "Peace be upon every household and humble hearth."
            ]
            priest.say(random.choice(sermons), duration=3.0)
