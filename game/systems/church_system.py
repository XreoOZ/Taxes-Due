"""
Church, Priest, Prayer Time & Church Tax System (Agent 3)

Coordinates gameplay logic for:
1. Church Permit & Single-Priest enforcement (max 1 Priest per Church).
2. Dynamic Prayer Time detection from the Priest's schedule (indivisible contiguous block).
3. Household church attendance, capacity checking (no outside waiting / door blocking).
4. Daily Church Tax payment (1 representative per household, partial / full payment, denomination breaking).
5. Priest workflow: collecting tithes during prayer, depositing all coins into household chest after prayer,
   and preaching around village infrastructure during work hours.
"""

import math
import random
from game.config import (
    TILE_SIZE,
    DEFAULT_CHURCH_TAX,
    EXCHANGE_RATES
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
        """Returns the assigned Priest villager for the Church."""
        if not permit_manager or not villager_manager:
            return None
        church = cls.get_church_permit(permit_manager)
        if not church or not getattr(church, "assigned_workers", None):
            return None
        priest_id = church.assigned_workers[0]
        all_vils = villager_manager.get_all_villagers() if hasattr(villager_manager, "get_all_villagers") else getattr(villager_manager, "villagers", [])
        return next((v for v in all_vils if str(v.id) == str(priest_id) and getattr(v, "is_alive", True)), None)

    @classmethod
    def get_prayer_time_interval(cls, schedule_manager):
        """
        Discovers the indivisible contiguous Prayer Time block from the Priest's schedule.
        Returns: (start_hour, end_hour) as floats, e.g. (9.0, 11.0), or None if no prayer scheduled.
        """
        if not schedule_manager:
            return (9.0, 11.0)  # Default fallback
        sched = schedule_manager.get_schedule("Priest")
        prayer_hours = [h for h, act in enumerate(sched) if act == "PRAYER"]
        if not prayer_hours:
            return None
        return float(min(prayer_hours)), float(max(prayer_hours) + 1.0)

    @classmethod
    def is_prayer_time(cls, current_hour, schedule_manager):
        """Returns True if the current hour falls within the Priest's Prayer Time."""
        interval = cls.get_prayer_time_interval(schedule_manager)
        if not interval:
            return False
        h = float(current_hour) % 24.0
        return interval[0] <= h < interval[1]

    @classmethod
    def get_configured_tax_amount(cls, church_permit=None):
        """
        Returns the daily church tax configuration in Copper.
        Default: 0 Gold, 0 Silver, 1 Copper = 1 Copper per household.
        """
        if church_permit:
            g = getattr(church_permit, "tax_gold", DEFAULT_CHURCH_TAX.get("Gold", 0))
            s = getattr(church_permit, "tax_silver", DEFAULT_CHURCH_TAX.get("Silver", 0))
            c = getattr(church_permit, "tax_copper", DEFAULT_CHURCH_TAX.get("Copper", 1))
            return to_copper({"Gold": g, "Silver": s, "Copper": c})
        return to_copper(DEFAULT_CHURCH_TAX)

    @classmethod
    def has_household_paid_tax(cls, family_id, church_permit=None):
        """Checks whether the household has paid church tax today."""
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
        """Resets daily tax payment tracking at midnight transition."""
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
        """
        Selects one eligible adult representative to pay church tax on behalf of the household.
        If selected representative is unavailable or deceased, falls back to another surviving adult.
        """
        if not family or not getattr(family, "members", []):
            return None
        alive_members = [m for m in family.members if getattr(m, "is_alive", True)]
        if not alive_members:
            return None
        # Prioritize head or oldest member
        adults = [m for m in alive_members if getattr(m, "age", 20) >= 16]
        return adults[0] if adults else alive_members[0]

    @classmethod
    def process_church_tax_payment(cls, representative, priest, church_permit, furniture_manager=None):
        """
        Processes Church Tax payment:
        - Retrieves up to configured tax from household chest (or representative pocket).
        - Pays whatever amount is available (no negative balance, no free coins created).
        - Coins enter Priest's personal inventory/currency.
        - Marks household as paid for today.
        """
        if not representative or not priest or not church_permit:
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
        if available_copper <= 0:
            # No coins at all: pay nothing, household marked paid for today without penalty
            cls.mark_tax_paid(fam_id, church_permit)
            representative.say("We have no coins for Church Tax today, Father.", duration=2.0)
            return 0

        pay_copper = min(target_copper, available_copper)
        can_pay, payment, change, _ = calculate_payment_and_change(wallet, pay_copper)
        if not can_pay:
            cls.mark_tax_paid(fam_id, church_permit)
            return 0

        if not hasattr(priest, "currency") or not isinstance(priest.currency, dict):
            priest.currency = {"Copper": 0, "Silver": 0, "Gold": 0}

        transfer_success, new_s, new_r, _ = execute_currency_transfer(source, priest.currency, payment, change)

        if transfer_success:
            cls.mark_tax_paid(fam_id, church_permit)
            representative.say(f"Paid {pay_copper} Copper Church Tax.", duration=2.0)
            priest.say(f"Blessings upon your household.", duration=2.0)
            return pay_copper

        return 0

    @classmethod
    def get_church_walkable_tiles(cls, church_permit, building_manager):
        """
        Discovers available walkable tiles inside the Church structure built on the Church permit.
        If no structure is built, uses the open permit tiles.
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
        After Prayer Time ends:
        Priest deposits ALL collected tithes and coins from personal currency
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

        priest.say(f"Deposited {total_deposited_copper}c tithes into household chest.", duration=2.2)
        return total_deposited_copper

    @classmethod
    def execute_priest_preaching(cls, priest, dt, building_manager, all_entities=None):
        """
        During Work Time outside Prayer Time:
        Priest wanders around village infrastructure (roads, market, well) and preaches.
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
