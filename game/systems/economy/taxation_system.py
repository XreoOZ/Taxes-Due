"""Church tithe and household socage policy, collection, and collector routing."""

import math
import random

from game.data.config import (
    DEFAULT_SOCAGE_TAX_ENABLED,
    DEFAULT_SOCAGE_TAX_PERCENT,
    SOCAGE_TAX_INTERVAL_DAYS,
    SOCAGE_TAX_HAPPINESS_TIERS,
    CHURCH_TAX_HAPPINESS_TIERS_COPPER,
    NO_CHURCH_TAX_HAPPINESS_BONUS,
    MARKET_SALES_REPORT_PERIOD_DAYS,
    TAX_COLLECTOR_STATION_ARRIVAL_DISTANCE,
    SOCAGE_TAX_GREETING_LINES,
    SOCAGE_TAX_HAPPINESS_REPLIES,
    SCHEDULE_WORK,
)
from game.systems.economy.currency import normalize_wallet, to_copper, transfer_exact_value
from game.world.navigation.navigation import distance_to_object


class TaxationSystem:
    _socage_enabled = DEFAULT_SOCAGE_TAX_ENABLED
    _socage_percent = DEFAULT_SOCAGE_TAX_PERCENT
    _socage_report_period = None
    _socage_report_collected_copper = 0

    @classmethod
    def _ensure_socage_report_period(cls, day_number):
        days = max(1, int(MARKET_SALES_REPORT_PERIOD_DAYS))
        day = max(1, int(day_number or 1))
        period = (day - 1) // days
        if cls._socage_report_period != period:
            cls._socage_report_period = period
            cls._socage_report_collected_copper = 0
        return period

    @classmethod
    def record_socage_tax_collected(cls, amount_copper, day_number):
        amount = max(0, int(amount_copper or 0))
        if amount <= 0:
            return
        cls._ensure_socage_report_period(day_number)
        cls._socage_report_collected_copper += amount

    @classmethod
    def get_socage_tax_report(cls, day_number):
        days = max(1, int(MARKET_SALES_REPORT_PERIOD_DAYS))
        day = max(1, int(day_number or 1))
        period = cls._ensure_socage_report_period(day)
        return {
            "period": period,
            "start_day": period * days + 1,
            "end_day": (period + 1) * days,
            "through_day": min(day, (period + 1) * days),
            "collected_copper": max(0, int(cls._socage_report_collected_copper)),
        }

    @classmethod
    def set_socage_enabled(cls, enabled):
        cls._socage_enabled = bool(enabled)

    @classmethod
    def is_socage_enabled(cls):
        return bool(cls._socage_enabled)

    @classmethod
    def set_socage_percent(cls, percent):
        cls._socage_percent = max(1, min(100, int(percent)))

    @classmethod
    def get_socage_percent(cls):
        return max(1, min(100, int(cls._socage_percent)))

    @classmethod
    def next_collection_day(cls, current_day, villager_manager=None):
        interval = max(1, int(SOCAGE_TAX_INTERVAL_DAYS))
        day = max(1, int(current_day or 1))
        cycle = day // interval
        if day % interval == 0:
            collectors = [
                villager for villager in (villager_manager.get_all_villagers() if villager_manager else [])
                if getattr(villager, "job", None) == "Tax Collector"
            ]
            if any((getattr(villager, "socage_tax_round", None) or {}).get("day") == day
                   for villager in collectors):
                return day
            collected_or_started = any(
                getattr(villager, "socage_tax_last_cycle", None) == cycle for villager in collectors
            )
            if not collected_or_started:
                return day
        return (day // interval + 1) * interval

    @classmethod
    def to_dict(cls):
        from game.systems.village_life.church_system import ChurchSystem
        church_state = ChurchSystem.get_instance()
        return {
            "church_enabled": ChurchSystem.is_tax_enabled(),
            "church_tax": ChurchSystem.get_tax_settings(),
            "church_tax_paid_households_today": sorted(church_state.tax_paid_households_today),
            "church_tax_last_day": int(church_state.last_tax_day),
            "socage_enabled": cls.is_socage_enabled(),
            "socage_percent": cls.get_socage_percent(),
            "socage_report_period": cls._socage_report_period,
            "socage_report_collected_copper": cls._socage_report_collected_copper,
        }

    @classmethod
    def load_dict(cls, data, permit_manager=None):
        if not isinstance(data, dict):
            return
        from game.systems.village_life.church_system import ChurchSystem
        ChurchSystem.set_tax_enabled(data.get("church_enabled", False))
        church_state = ChurchSystem.get_instance()
        church_state.tax_paid_households_today = set(
            str(family_id) for family_id in data.get("church_tax_paid_households_today", [])
        )
        church_state.last_tax_day = int(data.get("church_tax_last_day", 1))
        tax = data.get("church_tax")
        if isinstance(tax, dict):
            ChurchSystem.set_tax_settings(
                tax.get("Gold", 0), tax.get("Silver", 0), tax.get("Copper", 1),
                permit_manager,
            )
        cls.set_socage_enabled(data.get("socage_enabled", DEFAULT_SOCAGE_TAX_ENABLED))
        cls.set_socage_percent(data.get("socage_percent", DEFAULT_SOCAGE_TAX_PERCENT))
        report_period = data.get("socage_report_period")
        cls._socage_report_period = int(report_period) if report_period is not None else None
        cls._socage_report_collected_copper = max(
            0, int(data.get("socage_report_collected_copper", 0) or 0)
        )

    @staticmethod
    def _tier_value(value, tiers):
        value = float(value)
        for lower, upper, penalty in tiers:
            if value >= float(lower) and (upper is None or value <= float(upper)):
                return float(penalty)
        return 0.0

    @classmethod
    def church_tax_happiness_amount(cls, church_permit=None):
        from game.systems.village_life.church_system import ChurchSystem
        amount = ChurchSystem.get_configured_tax_amount(church_permit)
        return cls._tier_value(amount, CHURCH_TAX_HAPPINESS_TIERS_COPPER)

    @classmethod
    def church_happiness_effect(cls):
        from game.systems.village_life.church_system import ChurchSystem
        if not ChurchSystem.is_tax_enabled():
            return float(NO_CHURCH_TAX_HAPPINESS_BONUS)
        return cls.church_tax_happiness_amount()

    @classmethod
    def socage_happiness_effect(cls):
        if not cls.is_socage_enabled():
            return 0.0
        return cls._tier_value(cls.get_socage_percent(), SOCAGE_TAX_HAPPINESS_TIERS)

    @classmethod
    def apply_tax_unhappiness(cls, family_id, effect_id, amount, villager_manager, day_number):
        """Give every living member of a taxed household the timed unhappiness effect.

        *** ESTABLISHED — USER-CONFIRMED, DO NOT REGRESS ***
        Tax unhappiness is EVENT-DRIVEN, not always-on — it is applied only
        when tax is actually collected (socage rounds and church tithes),
        lasts TAX_UNHAPPINESS_DURATION_DAYS (10) via HAPPINESS_MODIFIERS
        durations, and shows remaining days in the happiness breakdown.
        Persistent factors display "Indefinite". Do not restore permanent
        always-on tax penalties in HappinessSystem."""
        from game.systems.village_life.happiness_system import HappinessSystem
        amount = float(amount or 0.0)
        if amount == 0.0:
            return
        family = villager_manager.get_family_by_id(family_id) if villager_manager else None
        for member in getattr(family, "members", []) or []:
            if getattr(member, "is_alive", True):
                HappinessSystem.record_event(member, effect_id, day_number, amount=amount)

    @classmethod
    def household_chest_wallet(cls, furniture_manager, family_id):
        chest = furniture_manager.get_storage_for_family(family_id) if furniture_manager else None
        if not chest:
            return None, {"Gold": 0, "Silver": 0, "Copper": 0}
        return chest, normalize_wallet(getattr(chest, "inventory", {}))

    @classmethod
    def socage_due_for_household(cls, furniture_manager, family_id):
        _, wallet = cls.household_chest_wallet(furniture_manager, family_id)
        wealth = to_copper(wallet)
        return wealth * cls.get_socage_percent() // 100

    @staticmethod
    def _family_home_building(family, permit_manager, building_manager):
        permit_id = getattr(family, "assigned_permit_id", None)
        permit = next((p for p in getattr(permit_manager, "permits", [])
                       if str(getattr(p, "id", "")) == str(permit_id)), None)
        if permit:
            return next((building for building in getattr(building_manager, "buildings", [])
                         if getattr(building, "building_type", "") in ("wooden_structure", "stone_structure")
                         and permit.overlaps_building(building)), None)
        return None

    @classmethod
    def _family_meeting_point(cls, family, permit_manager, building_manager, tile_size,
                              reference_position, all_entities, worker_id):
        permit_id = getattr(family, "assigned_permit_id", None)
        permit = next((p for p in getattr(permit_manager, "permits", [])
                       if str(getattr(p, "id", "")) == str(permit_id)), None)
        if permit:
            home = cls._family_home_building(family, permit_manager, building_manager)
            if home and getattr(home, "door_pos", None):
                return home.get_approach_point(
                    reference_position[0], reference_position[1], worker_id=worker_id,
                    all_entities=all_entities, tile_size=tile_size, bm=building_manager,
                )
            if permit.tiles:
                gx, gy = min(permit.tiles, key=lambda tile: (tile[1], tile[0]))
                return ((gx + 0.5) * tile_size, (gy + 0.5) * tile_size)
        members = [member for member in getattr(family, "members", [])
                   if getattr(member, "is_alive", True)]
        if members:
            return members[0].x, members[0].y
        return None

    @classmethod
    def _assigned_tax_office(cls, collector, building_manager):
        for building in getattr(building_manager, "buildings", []):
            if getattr(building, "building_type", None) != "tax_house":
                continue
            if not getattr(building, "is_available_for_use", False):
                continue
            if str(collector.id) in {str(worker_id) for worker_id in getattr(building, "assigned_workers", [])}:
                return building
        return None

    @classmethod
    def _station_at_tax_office(cls, collector, dt, building_manager, all_entities, player,
                              furniture_manager):
        office = cls._assigned_tax_office(collector, building_manager)
        if not office:
            collector.tax_office_station_key = None
            collector.tax_office_station_target = None
            return False
        from game.data.config import TILE_SIZE
        station_key = (
            str(getattr(office, "id", "")),
            str(getattr(office, "building_type", "")),
            tuple(sorted(getattr(office, "tiles", ()))),
            int(getattr(office, "grid_x", 0)),
            int(getattr(office, "grid_y", 0)),
        )
        if (getattr(collector, "tax_office_station_key", None) != station_key
                or getattr(collector, "tax_office_station_target", None) is None):
            collector.tax_office_station_key = station_key
            collector.tax_office_station_target = office.get_approach_point(
                collector.x, collector.y, worker_id=collector.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
        station_x, station_y = collector.tax_office_station_target
        arrived = collector._move_towards(
            station_x, station_y, dt,
            arrival_dist=TAX_COLLECTOR_STATION_ARRIVAL_DISTANCE,
            all_entities=all_entities, player=player,
            building_manager=building_manager, furniture_manager=furniture_manager,
            exclusive_target=False,
            recover_blocked_routes=True,
            interaction_target=office,
        )
        if arrived or math.hypot(collector.x - station_x, collector.y - station_y) <= TAX_COLLECTOR_STATION_ARRIVAL_DISTANCE:
            collector.task = "STATIONED_AT_TAX_OFFICE"
        else:
            collector.task = "GOING_TO_TAX_OFFICE"
        return True

    @classmethod
    def _active_collector(cls, villager_manager):
        for villager in (villager_manager.get_all_villagers() if villager_manager else []):
            if (getattr(villager, "job", None) == "Tax Collector"
                    and getattr(villager, "is_alive", True)
                    and isinstance(getattr(villager, "socage_tax_round", None), dict)):
                return villager
        return None

    @classmethod
    def _refresh_household_queue(cls, round_state, villager_manager):
        queued_ids = round_state.setdefault("family_ids", [])
        known_ids = {str(family_id) for family_id in queued_ids}
        families = [
            family for family in getattr(villager_manager, "families", [])
            if any(getattr(member, "is_alive", True)
                   for member in getattr(family, "members", []))
        ]
        families.sort(key=lambda family: str(getattr(family, "id", "")))
        for family in families:
            family_id = str(getattr(family, "id", ""))
            if family_id and family_id not in known_ids:
                queued_ids.append(family_id)
                known_ids.add(family_id)

    @classmethod
    def _start_round(cls, collector, day_number, villager_manager, building_manager,
                     furniture_manager, permit_manager):
        from game.data.config import TILE_SIZE
        cycle = int(day_number) // max(1, int(SOCAGE_TAX_INTERVAL_DAYS))
        if (not cls.is_socage_enabled() or int(day_number) % max(1, int(SOCAGE_TAX_INTERVAL_DAYS))
                or getattr(collector, "socage_tax_last_cycle", None) == cycle):
            return False
        office = cls._assigned_tax_office(collector, building_manager)
        if not office or not furniture_manager:
            return False
        families = [family for family in getattr(villager_manager, "families", [])
                    if any(getattr(member, "is_alive", True) for member in getattr(family, "members", []))]
        families.sort(key=lambda family: str(getattr(family, "id", "")))
        collector.socage_tax_round = {
            "cycle": cycle,
            "day": int(day_number),
            "family_ids": [str(family.id) for family in families],
            "index": 0,
            "status": "TRAVEL",
            "target_family_id": None,
        }
        collector.socage_tax_last_cycle = cycle
        collector.say(random.choice(SOCAGE_TAX_GREETING_LINES), duration=2.6)
        return True

    @classmethod
    def update_collector(cls, collector, dt, current_activity, day_cycle, permit_manager,
                         villager_manager, building_manager, furniture_manager,
                         all_entities, player):
        if getattr(collector, "job", None) != "Tax Collector" or not getattr(collector, "is_alive", True):
            return False
        from game.data.config import TILE_SIZE, INTERACTION_CONTACT_RADIUS
        from game.systems.economy.lord_treasury import LordTreasurySystem

        collector.tax_collection_activity = current_activity
        if current_activity != SCHEDULE_WORK:
            return False

        day_number = int(getattr(day_cycle, "day_number", 1))
        round_state = getattr(collector, "socage_tax_round", None)
        if isinstance(round_state, dict) and not cls.is_socage_enabled():
            round_state["status"] = "RETURN"
            round_state["return_message"] = "The tax round has ended; I am returning the collected coin."
        if not isinstance(round_state, dict):
            other_collector = cls._active_collector(villager_manager)
            if other_collector and other_collector is not collector:
                if current_activity in ("WORK", "ANY"):
                    return cls._station_at_tax_office(
                        collector, dt, building_manager, all_entities, player,
                        furniture_manager,
                    )
                return False
            if not cls._start_round(collector, day_number, villager_manager, building_manager,
                                    furniture_manager, permit_manager):
                if current_activity in ("WORK", "ANY"):
                    return cls._station_at_tax_office(
                        collector, dt, building_manager, all_entities, player,
                        furniture_manager,
                    )
                return False
            round_state = collector.socage_tax_round

        if round_state.get("status") != "RETURN":
            cls._refresh_household_queue(round_state, villager_manager)

        office = cls._assigned_tax_office(collector, building_manager)
        if not office and round_state.get("status") != "RETURN":
            round_state["status"] = "RETURN"
            round_state["return_message"] = "I cannot continue without the Tax Office; I am returning the collected coin."

        if round_state.get("status") == "RETURN":
            treasury = LordTreasurySystem.get_chest(furniture_manager)
            if not treasury:
                collector.task = "RETURNING_TAX_TO_TREASURY"
                return True
            approach_x, approach_y = treasury.get_approach_point(
                collector.x, collector.y, worker_id=collector.id,
                all_entities=all_entities, tile_size=TILE_SIZE, bm=building_manager,
            )
            arrived = collector._move_towards(
                approach_x, approach_y, dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player,
                building_manager=building_manager, furniture_manager=furniture_manager,
                exclusive_target=False,
                interaction_target=treasury,
            )
            if arrived or distance_to_object(treasury, collector.x, collector.y, TILE_SIZE) <= TILE_SIZE:
                LordTreasurySystem.deposit_all(furniture_manager, collector.inventory)
                collector.socage_tax_round = None
                collector.task = "IDLE"
                collector.say(round_state.get("return_message", "I have deposited the collected coin in the Lord's Treasury."), duration=3.0)
            else:
                collector.task = "RETURNING_TAX_TO_TREASURY"
            return True

        ids = round_state.get("family_ids", [])
        index = max(0, int(round_state.get("index", 0)))
        if index >= len(ids):
            round_state["status"] = "RETURN"
            round_state["return_message"] = "The village tax round is complete; I have returned the collected coin."
            return True

        family_id = ids[index]
        family = villager_manager.get_family_by_id(family_id) if villager_manager else None
        if not family or not any(getattr(member, "is_alive", True) for member in family.members):
            round_state["index"] = index + 1
            round_state["status"] = "TRAVEL"
            return True
        if round_state.get("household_paid"):
            round_state["index"] = index + 1
            round_state["status"] = "TRAVEL"
            round_state.pop("household_paid", None)
            return True

        point = cls._family_meeting_point(
            family, permit_manager, building_manager, TILE_SIZE,
            (collector.x, collector.y), all_entities, collector.id,
        )
        if not point:
            round_state["status"] = "WAITING_FOR_HOUSEHOLD_LOCATION"
            collector.task = "WAITING_FOR_HOUSEHOLD_TAX"
            return True

        round_state["target_family_id"] = str(family.id)
        if round_state.get("status") != "MEET":
            collector.task = "VISITING_HOUSEHOLD_FOR_TAX"
            home = cls._family_home_building(family, permit_manager, building_manager)
            arrived = collector._move_towards(
                point[0], point[1], dt, arrival_dist=INTERACTION_CONTACT_RADIUS,
                all_entities=all_entities, player=player, building_manager=building_manager,
                furniture_manager=furniture_manager, exclusive_target=False,
                interaction_target=home,
            )
            if arrived or (home and distance_to_object(home, collector.x, collector.y, TILE_SIZE) <= TILE_SIZE):
                round_state["status"] = "MEET"
                collector.task = "WAITING_FOR_HOUSEHOLD_TAX"
                collector.say("Pay your household taxes, please.", duration=2.5)
                family_reps = [member for member in family.members
                               if getattr(member, "is_alive", True)
                               and str(member.id) != str(collector.id)]
                if (str(family.id) == str(getattr(collector, "family_id", ""))
                        and not family_reps):
                    chest, wallet = cls.household_chest_wallet(furniture_manager, family.id)
                    due = to_copper(wallet) * cls.get_socage_percent() // 100
                    success = due <= 0 or bool(
                        chest and transfer_exact_value(chest.inventory, collector.inventory, due)[0]
                    )
                    if success:
                        round_state["household_paid"] = True
                        cls.record_socage_tax_collected(due, day_number)
                        cls.apply_tax_unhappiness(
                            family.id, "tax_socage", cls.socage_happiness_effect(),
                            villager_manager, day_number,
                        )
                        collector.say("I have recorded my own household's tax payment.", duration=2.5)
                        from game.systems.economy.wealth_system import VillageWealthSystem
                        VillageWealthSystem.mark_dirty()
            return True

        return True

    @classmethod
    def update_household_representative(cls, villager, dt, villager_manager, permit_manager,
                                        building_manager, furniture_manager, all_entities, player,
                                        day_number, collector_activity=None,
                                        villager_activity=None):
        if not getattr(villager, "is_alive", True) or not villager_manager:
            return False
        if villager_activity not in (None, "WORK", "ANY"):
            return False
        collector = cls._active_collector(villager_manager)
        state = getattr(collector, "socage_tax_round", None) if collector else None
        if collector_activity is None:
            collector_activity = getattr(collector, "tax_collection_activity", None)
        if collector_activity != SCHEDULE_WORK:
            return False
        if (not isinstance(state, dict) or state.get("status") != "MEET"
                or str(state.get("target_family_id")) != str(getattr(villager, "family_id", ""))):
            prepared = max(0, int(getattr(villager, "socage_tax_prepared_amount", 0)))
            if prepared:
                chest, _ = cls.household_chest_wallet(furniture_manager, villager.family_id)
                if chest:
                    refunded, _ = transfer_exact_value(villager.inventory, chest.inventory, prepared)
                    if refunded:
                        villager.socage_tax_prepared_amount = 0
                        villager.socage_tax_prepared_cycle = None
                        from game.systems.economy.wealth_system import VillageWealthSystem
                        VillageWealthSystem.mark_dirty()
            if getattr(villager, "task", None) == "PAYING_SOCAGE_TAX":
                villager.task = "IDLE"
                villager._resume_or_idle_after_need()
            return False
        family = villager_manager.get_family_by_id(villager.family_id)
        representative = None
        if family:
            alive = [member for member in family.members if getattr(member, "is_alive", True)]
            if str(family.id) == str(getattr(collector, "family_id", "")):
                alive = [member for member in alive if str(member.id) != str(collector.id)]
            adults = [member for member in alive if getattr(member, "age", 20) >= 16]
            representative = (adults or alive or [None])[0]
        if representative is not villager:
            return False
        if villager.task not in ("PAYING_SOCAGE_TAX", "IDLE", "LEISURE", "STROLLING", "ATTENDING_PRAYER"):
            villager.interrupt_task("SOCAGE_TAX")
        villager.task = "PAYING_SOCAGE_TAX"
        cycle = int(state.get("cycle", 0))
        if getattr(villager, "socage_tax_prepared_cycle", None) != cycle:
            chest, wallet = cls.household_chest_wallet(furniture_manager, villager.family_id)
            due = to_copper(wallet) * cls.get_socage_percent() // 100
            prepared = 0
            if chest and due > 0:
                if not isinstance(getattr(villager, "inventory", None), dict):
                    villager.inventory = {}
                success, _ = transfer_exact_value(chest.inventory, villager.inventory, due)
                if success:
                    prepared = due
                    from game.systems.economy.wealth_system import VillageWealthSystem
                    VillageWealthSystem.mark_dirty()
            villager.socage_tax_prepared_cycle = cycle
            villager.socage_tax_prepared_amount = prepared
        contact = max(1.0, float(getattr(villager, "radius", 20))
                      + float(getattr(collector, "radius", 20)) + 8.0)
        arrived = villager._move_towards(
            collector.x, collector.y, dt, arrival_dist=contact,
            all_entities=all_entities, player=player, building_manager=building_manager,
            furniture_manager=furniture_manager, exclusive_target=False,
        )
        if arrived or math.hypot(villager.x - collector.x, villager.y - collector.y) <= contact:
            due = max(0, int(getattr(villager, "socage_tax_prepared_amount", 0)))
            success = due <= 0 or bool(
                transfer_exact_value(villager.inventory, collector.inventory, due)[0]
            )
            if success:
                state["household_paid"] = True
                villager.socage_tax_prepared_amount = 0
                villager.socage_tax_prepared_cycle = None
                cls.record_socage_tax_collected(due, day_number)
                cls.apply_tax_unhappiness(
                    villager.family_id, "tax_socage", cls.socage_happiness_effect(),
                    villager_manager, day_number,
                )
                from game.systems.economy.wealth_system import VillageWealthSystem
                VillageWealthSystem.mark_dirty()
                replies = SOCAGE_TAX_HAPPINESS_REPLIES.get(
                    getattr(villager, "happiness_status", "happy"), SOCAGE_TAX_HAPPINESS_REPLIES["happy"]
                )
                villager.say(random.choice(replies) if due else "Our household chest has no coin to tax.", duration=2.8)
                collector.say(f"Collected {due}c from the household chest.", duration=2.5)
            villager.task = "IDLE"
            villager._resume_or_idle_after_need()
        return True
