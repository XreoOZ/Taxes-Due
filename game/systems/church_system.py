"""
Church, Priest, Prayer Time & Church Tax System (AGENT 2)
Coordinates gameplay logic for:
1. Church Permit & Building Construction (Wooden/Stone Structure inside Church Permit).
2. Priest Job Assignment: dynamically selects closest available household member with no other active job, changes title to Priest, and handles worker release via [- Number of Workers +].
3. Prayer Time Schedule: indivisible contiguous block on Priest schedule, forced onto all other jobs strictly during the prayer block.
4. Household Prayer & Church Tax Flow: 1 representative per household pays exact coin amount to Priest at church, no partial payment if insufficient, members wait on available church tiles.
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
    calculate_payment_and_change,
    execute_currency_transfer
)


class ChurchSystem:
    _instance = None

    def __init__(self):
        self.tax_paid_households_today = set()  # set of family_ids that paid tax today
        self.last_tax_day = 1
        self.occupied_prayer_tiles = {}         # (gx, gy) -> villager_id
        self.configured_tax = {"Gold": 0, "Silver": 0, "Copper": 1}

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
        for p in getattr(permit_manager, "permits", []):
            if getattr(p, "permit_type", "") == "church":
                return p
        return None

    @classmethod
    def get_all_church_permits(cls, permit_manager):
        if not permit_manager:
            return []
        return [p for p in getattr(permit_manager, "permits", []) if getattr(p, "permit_type", "") == "church"]

    @classmethod
    def get_assigned_priest(cls, permit_manager, villager_manager):
        """
        Returns the assigned Priest villager.
        Checks church permit assigned_workers first, then any active villager with job == 'Priest'.
        """
        if not villager_manager:
            return None
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])
        
        # 1. From active Church permit
        church = cls.get_church_permit(permit_manager)
        if church and getattr(church, "assigned_workers", None):
            priest_id = church.assigned_workers[0]
            p_vil = next((v for v in all_vils if str(v.id) == str(priest_id) and getattr(v, "is_alive", True)), None)
            if p_vil:
                return p_vil

        # 2. Any active villager with Priest job
        return next((v for v in all_vils if getattr(v, "job", "") == "Priest" and getattr(v, "is_alive", True)), None)

    @classmethod
    def assign_priest(cls, permit_manager, villager_manager, target_permit=None):
        """
        Assigns the closest available household member without an active job as Priest.
        Changes their title to Priest and registers them to the church permit.
        Returns (success: bool, villager or error message).
        """
        if not villager_manager:
            return False, "Villager manager unavailable."

        church = target_permit or cls.get_church_permit(permit_manager)
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])

        # Collect occupied worker IDs across all permits
        assigned_worker_ids = set()
        if permit_manager and hasattr(permit_manager, "permits"):
            for p in permit_manager.permits:
                for wid in getattr(p, "assigned_workers", []):
                    assigned_worker_ids.add(str(wid))

        # Eligible candidates: alive, part of a household, not assigned to another permit, not holding a dedicated non-farmer job
        candidates = []
        for v in all_vils:
            if not getattr(v, "is_alive", True):
                continue
            if not getattr(v, "family_id", None):
                continue
            if str(v.id) in assigned_worker_ids:
                continue
            if getattr(v, "job", "Farmer") not in ("Farmer", "Peasant", "Unemployed", None, ""):
                continue
            candidates.append(v)

        if not candidates:
            return False, "No available household member without an active job."

        # Reference location: center of church permit or origin
        if church:
            cx = (church.grid_x + church.tiles_w / 2.0) * TILE_SIZE
            cy = (church.grid_y + church.tiles_h / 2.0) * TILE_SIZE
        else:
            cx, cy = 0.0, 0.0

        candidates.sort(key=lambda v: math.hypot(v.x - cx, v.y - cy))
        chosen = candidates[0]

        # Assign job and title
        chosen.job = "Priest"
        chosen.title = "Village Priest"

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
        if church_permit and hasattr(church_permit, "tax_paid_households_today"):
            return fam_str in church_permit.tax_paid_households_today
        return fam_str in inst.tax_paid_households_today

    @classmethod
    def mark_tax_paid(cls, family_id, church_permit=None):
        fam_str = str(family_id)
        inst = cls.get_instance()
        inst.tax_paid_households_today.add(fam_str)
        if church_permit:
            if not hasattr(church_permit, "tax_paid_households_today"):
                church_permit.tax_paid_households_today = set()
            church_permit.tax_paid_households_today.add(fam_str)

    @classmethod
    def reset_daily_taxes(cls, current_day, permit_manager=None):
        inst = cls.get_instance()
        inst.tax_paid_households_today.clear()
        inst.last_tax_day = current_day
        inst.occupied_prayer_tiles.clear()
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
    def process_church_tax_payment(cls, representative, priest, church_permit, furniture_manager=None):
        """
        Payment rules:
        - If household has enough coins: collects the configured amount.
        - If household has insufficient coins: DO NOT collect partial payment.
        - If household has no coins: does not pay.
        - Collected coins transferred directly into Priest's personal inventory.
        - Marked paid once per household per day.
        """
        if not representative or not priest:
            return 0

        fam_id = getattr(representative, "family_id", None)
        if not fam_id or cls.has_household_paid_tax(fam_id, church_permit):
            return 0

        target_copper = cls.get_configured_tax_amount(church_permit)
        if target_copper <= 0:
            cls.mark_tax_paid(fam_id, church_permit)
            return 0

        # Retrieve funds from household chest or representative pocket
        chest = furniture_manager.get_storage_for_family(fam_id) if furniture_manager else None
        source = None
        wallet = {"Copper": 0, "Silver": 0, "Gold": 0}

        if chest and hasattr(chest, "currency"):
            wallet = normalize_wallet(chest.currency)
            source = chest.currency
        else:
            wallet = normalize_wallet(getattr(representative, "currency", {}))
            source = getattr(representative, "currency", None)

        available_copper = to_copper(wallet)

        # STRICT RULE: Insufficient or zero coins -> DO NOT collect partial payment!
        if available_copper < target_copper:
            cls.mark_tax_paid(fam_id, church_permit)
            if available_copper == 0:
                representative.say("We have no coins for Church Tax today, Father.", duration=2.2)
            else:
                representative.say(f"We cannot afford {target_copper}c Church Tax today, Father.", duration=2.2)
            return 0

        # Sufficient coins -> calculate payment and change using denomination breaking
        can_pay, payment, change, _ = calculate_payment_and_change(wallet, target_copper)
        if not can_pay:
            cls.mark_tax_paid(fam_id, church_permit)
            return 0

        if not hasattr(priest, "currency") or not isinstance(priest.currency, dict):
            priest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        transfer_success, _, _, _ = execute_currency_transfer(source, priest.currency, payment, change)

        if transfer_success:
            cls.mark_tax_paid(fam_id, church_permit)
            representative.say(f"Paid {target_copper}c Church Tax on behalf of our household.", duration=2.2)
            priest.say("Blessings upon your household.", duration=2.2)
            return target_copper

        return 0

    @classmethod
    def get_church_walkable_tiles(cls, church_permit, building_manager):
        """
        Discovers walkable tiles inside the church structure built on church permit,
        or open permit tiles if no building constructed yet.
        """
        if not church_permit:
            return []
        church_blds = [b for b in getattr(building_manager, "buildings", []) if church_permit.overlaps_building(b)]
        if church_blds:
            tiles = set()
            for b in church_blds:
                tiles.update(b.tiles)
            return sorted(list(tiles))
        return sorted(list(church_permit.tiles))

    @classmethod
    def find_free_church_tile(cls, villager, church_permit, building_manager):
        """
        Finds an available tile inside the church for prayer.
        If Church is full, returns None.
        """
        tiles = cls.get_church_walkable_tiles(church_permit, building_manager)
        inst = cls.get_instance()
        vid_str = str(villager.id)

        for t in tiles:
            occupant = inst.occupied_prayer_tiles.get(t)
            if occupant is None or occupant == vid_str:
                inst.occupied_prayer_tiles[t] = vid_str
                return t
        return None

    @classmethod
    def release_church_tile(cls, villager):
        inst = cls.get_instance()
        vid_str = str(villager.id)
        to_del = [t for t, occupant in inst.occupied_prayer_tiles.items() if occupant == vid_str]
        for t in to_del:
            del inst.occupied_prayer_tiles[t]

    @classmethod
    def priest_deposit_tithes_home(cls, priest, furniture_manager):
        """
        Deposits all collected tithes from priest's personal currency
        into their assigned household chest.
        """
        if not priest or not hasattr(priest, "currency"):
            return 0

        fam_id = getattr(priest, "family_id", None)
        chest = furniture_manager.get_storage_for_family(fam_id) if (furniture_manager and fam_id) else None
        if not chest:
            return 0

        total_deposited_copper = to_copper(priest.currency)
        if total_deposited_copper <= 0:
            return 0

        if not hasattr(chest, "currency"):
            chest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        for den in ("Copper", "Silver", "Gold"):
            amt = priest.currency.get(den, 0)
            if amt > 0:
                chest.currency[den] = chest.currency.get(den, 0) + amt
                priest.currency[den] = 0

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
