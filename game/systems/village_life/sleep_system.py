"""Individual sleep need, forced rest, and sleep fatigue happiness effects."""

from game.data.config import (
    HAPPINESS_MODIFIERS,
    SLEEP_FULL_RECOVERY_INGAME_HOURS,
    SLEEP_HAPPINESS_PENALTIES,
    SLEEP_INITIAL_VALUE,
    SLEEP_MAX_VALUE,
    SLEEP_MIN_VALUE,
    SLEEP_NO_BED_RECOVERY_DURATION_MULTIPLIER,
    SLEEP_STATUS_BANDS,
    SLEEP_WAKE_DRAIN_INGAME_HOURS,
    SLEEP_FORCED_WAKE_THRESHOLD,
)


class SleepSystem:
    @staticmethod
    def initialize(villager):
        if not hasattr(villager, "sleep_need"):
            villager.sleep_need = float(SLEEP_INITIAL_VALUE)
        villager.sleep_need = max(float(SLEEP_MIN_VALUE), min(float(SLEEP_MAX_VALUE), float(villager.sleep_need)))
        if not hasattr(villager, "sleep_forced"):
            villager.sleep_forced = False
        if not hasattr(villager, "sleeping_recharge_active"):
            villager.sleeping_recharge_active = False
        if not hasattr(villager, "sleep_any_rest_active"):
            villager.sleep_any_rest_active = False

    @staticmethod
    def status_for(value):
        value = float(value)
        if value <= float(SLEEP_MIN_VALUE):
            return "zonked"
        for band in SLEEP_STATUS_BANDS[:-1]:
            if value >= float(band["min"]):
                return band["id"]
        return "half_asleep"

    @staticmethod
    def usable_bed(villager, furniture_manager):
        if not furniture_manager:
            return None
        bed = furniture_manager.get_bed_for_villager(villager.id, getattr(villager, "family_id", None))
        return bed if bed and getattr(bed, "is_available_for_use", False) else None

    @classmethod
    def advance(cls, villager, dt, day_length_seconds, sleeping_active, has_bed, day_number):
        cls.initialize(villager)
        day_length_seconds = max(1.0, float(day_length_seconds))
        in_game_hours = max(0.0, float(dt)) * 24.0 / day_length_seconds
        meter = float(villager.sleep_need)

        if bool(getattr(villager, "sleep_forced", False)) or sleeping_active:
            recovery_hours = float(SLEEP_FULL_RECOVERY_INGAME_HOURS)
            if not has_bed:
                recovery_hours *= float(SLEEP_NO_BED_RECOVERY_DURATION_MULTIPLIER)
            meter += float(SLEEP_MAX_VALUE) / max(0.001, recovery_hours) * in_game_hours
        else:
            meter -= float(SLEEP_MAX_VALUE) / max(0.001, float(SLEEP_WAKE_DRAIN_INGAME_HOURS)) * in_game_hours

        meter = max(float(SLEEP_MIN_VALUE), min(float(SLEEP_MAX_VALUE), meter))
        if meter <= float(SLEEP_MIN_VALUE):
            villager.sleep_forced = True
            villager.sleeping_recharge_active = True
        elif getattr(villager, "sleep_forced", False) and meter >= float(SLEEP_FORCED_WAKE_THRESHOLD):
            villager.sleep_forced = False
            villager.sleeping_recharge_active = False
        villager.sleep_need = meter
        villager.sleep_status = cls.status_for(meter)

        penalty = SLEEP_HAPPINESS_PENALTIES.get(villager.sleep_status)
        if penalty is not None:
            day = max(1, int(day_number or 1))
            effect = getattr(villager, "happiness_effects", {}).get("sleep_fatigue", {})
            amount = min(float(effect.get("amount", 0.0)), float(penalty)) if int(effect.get("expires_day", 0)) >= day else float(penalty)
            villager.happiness_effects["sleep_fatigue"] = {
                "amount": amount,
                "expires_day": day + int(HAPPINESS_MODIFIERS.get("sleep_fatigue", {}).get("duration_days", 1)) - 1,
            }
        return bool(villager.sleep_forced)
