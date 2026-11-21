"""Data-driven individual happiness modifiers and activity pacing."""

from game.config import (
    HAPPINESS_ACTIVITY_MULTIPLIERS,
    HAPPINESS_INITIAL_VALUE,
    HAPPINESS_MAX_VALUE,
    HAPPINESS_MIN_VALUE,
    HAPPINESS_MODIFIERS,
    HAPPINESS_NEED_LABELS,
    HAPPINESS_STATUS_BANDS,
    HAPPINESS_WEALTH_DENOMINATION,
)
from game.systems.currency import normalize_wallet


class HappinessSystem:
    @staticmethod
    def _initialize(villager):
        if not hasattr(villager, "happiness"):
            villager.happiness = float(HAPPINESS_INITIAL_VALUE)
        if not isinstance(getattr(villager, "happiness_effects", None), dict):
            villager.happiness_effects = {}
        if not isinstance(getattr(villager, "happiness_trigger_days", None), dict):
            villager.happiness_trigger_days = {}
        if not isinstance(getattr(villager, "happiness_food_types", None), list):
            villager.happiness_food_types = []
        if not hasattr(villager, "happiness_food_day"):
            villager.happiness_food_day = None

    @staticmethod
    def status_for(value):
        value = float(value)
        for band in reversed(HAPPINESS_STATUS_BANDS):
            if value >= float(band["min"]):
                return band["id"]
        return HAPPINESS_STATUS_BANDS[0]["id"]

    @classmethod
    def activity_multiplier(cls, villager):
        cls._initialize(villager)
        return float(HAPPINESS_ACTIVITY_MULTIPLIERS.get(cls.status_for(villager.happiness), 1.0))

    @classmethod
    def record_event(cls, villager, effect_id, day_number, amount=None, accumulate=False):
        """Record or refresh one configured effect; repeated calls do not stack by default."""
        if villager is None:
            return False
        cls._initialize(villager)
        rule = HAPPINESS_MODIFIERS.get(effect_id)
        if not rule:
            return False
        day_number = max(1, int(day_number or 1))
        duration = max(1, int(rule.get("duration_days", 1)))
        effect = villager.happiness_effects.get(effect_id, {})
        value = float(amount if amount is not None else rule.get("amount", 0.0))
        if accumulate and int(effect.get("expires_day", 0)) >= day_number:
            value += float(effect.get("amount", 0.0))
        villager.happiness_effects[effect_id] = {
            "amount": value,
            "expires_day": day_number + duration - 1,
        }
        return True

    @classmethod
    def record_daily_event(cls, villager, effect_id, day_number, amount=None):
        cls._initialize(villager)
        day_number = max(1, int(day_number or 1))
        trigger_days = villager.happiness_trigger_days
        if trigger_days.get(effect_id) == day_number:
            return False
        trigger_days[effect_id] = day_number
        return cls.record_event(villager, effect_id, day_number, amount=amount)

    @staticmethod
    def _set_timed_effect(villager, effect_id, amount, day_number, duration_days):
        villager.happiness_effects[effect_id] = {
            "amount": float(amount),
            "expires_day": int(day_number) + max(1, int(duration_days)) - 1,
        }

    @classmethod
    def record_food_eaten(cls, villager, food_name, day_number):
        cls._initialize(villager)
        day_number = max(1, int(day_number or 1))
        if villager.happiness_food_day != day_number:
            villager.happiness_food_day = day_number
            villager.happiness_food_types = []
        if food_name and food_name not in villager.happiness_food_types:
            villager.happiness_food_types.append(food_name)
        required = int(HAPPINESS_MODIFIERS["ate_varied_food"].get("food_variety_required", 2))
        if len(villager.happiness_food_types) >= required:
            cls.record_daily_event(villager, "ate_varied_food", day_number)

    @classmethod
    def record_leisure(cls, villager, dt, day_number, day_length_seconds):
        rule = HAPPINESS_MODIFIERS["leisure_per_hour"]
        day_hours = max(1.0, float(day_length_seconds))
        in_game_hours = max(0.0, float(dt)) * 24.0 / day_hours
        if in_game_hours > 0.0:
            cls.record_event(
                villager, "leisure_per_hour", day_number,
                amount=float(rule["amount"]) * in_game_hours,
                accumulate=True,
            )

    @classmethod
    def record_bereavement(cls, deceased, family, day_number):
        if not family:
            return
        for member in getattr(family, "members", []):
            if member is not deceased and getattr(member, "is_alive", True):
                cls.record_event(member, "bereavement", day_number)

    @staticmethod
    def _home_building(villager, permit_manager, building_manager, villager_manager):
        if not permit_manager or not building_manager:
            return None
        family = (villager_manager.get_family_by_id(getattr(villager, "family_id", None))
                  if villager_manager and getattr(villager, "family_id", None) else None)
        permit_id = (getattr(villager, "assigned_permit_id", None)
                     or getattr(family, "assigned_permit_id", None))
        permit = next((p for p in permit_manager.permits
                       if str(getattr(p, "id", "")) == str(permit_id)), None) if permit_id else None
        if not permit:
            return None
        return next((building for building in building_manager.buildings
                     if getattr(building, "building_type", None) in ("wooden_structure", "stone_structure")
                     and getattr(building, "is_available_for_use", False)
                     and permit.overlaps_building(building)), None)

    @staticmethod
    def _owned_gold_coins(villager):
        personal_wallet = normalize_wallet(getattr(villager, "inventory", {}))
        return float(personal_wallet.get(HAPPINESS_WEALTH_DENOMINATION, 0))

    @classmethod
    def refresh(cls, villager, day_number, permit_manager=None, building_manager=None,
                furniture_manager=None, villager_manager=None):
        """Expire timed effects, refresh conditions, and compute the current score."""
        cls._initialize(villager)
        permit_manager = permit_manager or getattr(villager, "permit_manager", None)
        building_manager = building_manager or getattr(villager, "building_manager", None)
        furniture_manager = furniture_manager or getattr(villager, "furniture_manager", None)
        villager_manager = villager_manager or getattr(villager, "villager_manager", None)
        day_number = max(1, int(day_number or 1))
        villager.happiness_effects = {
            key: effect for key, effect in villager.happiness_effects.items()
            if isinstance(effect, dict) and int(effect.get("expires_day", day_number)) >= day_number
        }

        active = []
        breakdown = [{"label": "Starting happiness", "amount": float(HAPPINESS_INITIAL_VALUE), "duration": "Base"}]
        def add_factor(label, amount, duration="While active"):
            amount = float(amount)
            if amount:
                active.append(amount)
                breakdown.append({"label": label, "amount": amount, "duration": duration})
        need_values = {
            "hunger": float(getattr(villager, "hunger", 100.0)),
            "thirst": float(getattr(villager, "thirst", 100.0)),
            "toilet": float(getattr(villager, "need_toilet", 100.0)),
        }
        low_rule = HAPPINESS_MODIFIERS["need_low"]
        empty_rule = HAPPINESS_MODIFIERS["need_empty"]
        for need_name, need_value in need_values.items():
            low_id = f"need_low:{need_name}"
            empty_id = f"need_empty:{need_name}"
            if need_value <= float(empty_rule["threshold"]):
                villager.happiness_effects.pop(low_id, None)
                if villager.happiness_trigger_days.get(empty_id) != day_number:
                    villager.happiness_trigger_days[empty_id] = day_number
                    cls._set_timed_effect(villager, empty_id, empty_rule["amount"],
                                          day_number, empty_rule["duration_days"])
            elif need_value < float(low_rule["threshold"]):
                villager.happiness_effects.pop(empty_id, None)
                if villager.happiness_trigger_days.get(low_id) != day_number:
                    villager.happiness_trigger_days[low_id] = day_number
                    cls._set_timed_effect(villager, low_id, low_rule["amount"],
                                          day_number, low_rule["duration_days"])
            else:
                villager.happiness_effects.pop(low_id, None)
                villager.happiness_effects.pop(empty_id, None)

        needs_rule = HAPPINESS_MODIFIERS["needs_comfortable"]
        if all(value > float(needs_rule["threshold"]) for value in need_values.values()):
            cls.record_daily_event(villager, "needs_comfortable", day_number)

        home = cls._home_building(villager, permit_manager, building_manager, villager_manager)
        if home is None:
            add_factor("No usable home", HAPPINESS_MODIFIERS["no_home"]["amount"])
        elif len(getattr(home, "tiles", ())) <= int(HAPPINESS_MODIFIERS["small_home"]["max_tiles"]):
            add_factor("Small home", HAPPINESS_MODIFIERS["small_home"]["amount"])

        bed = (furniture_manager.get_bed_for_villager(villager.id, villager.family_id)
               if furniture_manager else None)
        bed_modifier = HAPPINESS_MODIFIERS["usable_bed"]
        if bed and getattr(bed, "is_available_for_use", False):
            add_factor("Usable bed", bed_modifier["amount"])
        else:
            add_factor("No usable bed", HAPPINESS_MODIFIERS["no_bed"]["amount"])

        job = getattr(villager, "job", "Unassigned")
        if not job or job in ("Unassigned", "Unemployed"):
            add_factor("Unassigned / unemployed", HAPPINESS_MODIFIERS["unemployed"]["amount"])

        from game.systems.taxation_system import TaxationSystem
        church_effect = TaxationSystem.church_happiness_effect()
        socage_effect = TaxationSystem.socage_happiness_effect()
        if church_effect:
            add_factor("Church tax" if church_effect < 0 else "No church tax", church_effect)
        if socage_effect:
            add_factor(f"Socage tax ({TaxationSystem.get_socage_percent()}%)", socage_effect)

        gold_rule = HAPPINESS_MODIFIERS["gold_coin"]
        gold_bonus = float(gold_rule["amount_per_coin"]) * cls._owned_gold_coins(villager)
        add_factor(gold_rule.get("label", "Gold coins"), gold_bonus)
        for effect_id, effect in villager.happiness_effects.items():
            amount = float(effect.get("amount", 0.0))
            remaining = max(0, int(effect.get("expires_day", day_number)) - day_number + 1)
            label = HAPPINESS_MODIFIERS.get(effect_id, {}).get("label")
            if effect_id.startswith("need_low:"):
                need_label = HAPPINESS_NEED_LABELS.get(effect_id.split(":", 1)[1], "Need")
                label = f"{need_label} below 20%"
            elif effect_id.startswith("need_empty:"):
                need_label = HAPPINESS_NEED_LABELS.get(effect_id.split(":", 1)[1], "Need")
                label = f"{need_label} reached 0%"
            if label:
                add_factor(label, amount, f"{remaining} day(s) remaining")
        score = float(HAPPINESS_INITIAL_VALUE) + sum(active)
        villager.happiness = max(float(HAPPINESS_MIN_VALUE), min(float(HAPPINESS_MAX_VALUE), score))
        villager.happiness_status = cls.status_for(villager.happiness)
        breakdown[1:] = sorted(breakdown[1:], key=lambda row: (row["amount"] >= 0, abs(row["amount"])), reverse=False)
        villager.happiness_breakdown = breakdown
        return villager.happiness

    @classmethod
    def get_breakdown(cls, villager):
        """Return the factors used in the latest happiness score calculation."""
        cls._initialize(villager)
        return list(getattr(villager, "happiness_breakdown", []) or [])
