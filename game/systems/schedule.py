"""
RimWorld-Style 24-Hour Activity Schedule System
Manages daily hourly routines (Work, Leisure, Sleep, Anything, Prayer) across 7 Days of the Week for dedicated village jobs.
Supports Priest Prayer Time block: an indivisible contiguous block where all jobs follow prayer.
"""

from game.config import (
    SCHEDULE_TYPES,
    DEFAULT_JOB_SCHEDULE,
    DEDICATED_JOBS,
    SCHEDULE_WORK,
    SCHEDULE_LEISURE,
    SCHEDULE_SLEEP,
    SCHEDULE_ANY,
    SCHEDULE_PRAYER,
    DAYS_OF_WEEK
)


class ScheduleManager:
    def __init__(self):
        self.default_schedule = list(DEFAULT_JOB_SCHEDULE)
        self.prayer_start_hour = 12
        self.prayer_end_hour = 14
        self.prayer_override_all = False

        # Schedules dictionary: job_id -> day_name -> 24-hour list
        self.job_schedules = {}
        for job_id in DEDICATED_JOBS:
            self.job_schedules[job_id] = {}
            for day in DAYS_OF_WEEK:
                self.job_schedules[job_id][day] = list(DEFAULT_JOB_SCHEDULE)

        # Apply initial Priest prayer block to Priest schedule
        self._sync_priest_prayer_block()

    def _sync_priest_prayer_block(self):
        """Applies contiguous prayer block to Priest across all days"""
        if "Priest" in self.job_schedules:
            for day in DAYS_OF_WEEK:
                sched = self.job_schedules["Priest"][day]
                for h in range(24):
                    if self.prayer_start_hour <= h < self.prayer_end_hour:
                        sched[h] = SCHEDULE_PRAYER
                    elif sched[h] == SCHEDULE_PRAYER:
                        sched[h] = SCHEDULE_WORK

    def get_prayer_hours(self):
        """Returns the contiguous (start_hour, end_hour) of the Priest prayer block"""
        return self.prayer_start_hour, self.prayer_end_hour

    def set_prayer_time(self, start_hour, end_hour):
        """
        Sets the indivisible contiguous Prayer Time block (0 to 24).
        Ensures start_hour < end_hour and clamped to valid bounds.
        """
        s = max(0, min(23, int(start_hour)))
        e = max(s + 1, min(24, int(end_hour)))
        self.prayer_start_hour = s
        self.prayer_end_hour = e
        self.prayer_override_all = True
        self._sync_priest_prayer_block()

    def get_schedule(self, job_id, day="Monday"):
        """Returns the 24-hour schedule list for a given job and day of week"""
        if day not in DAYS_OF_WEEK:
            day = "Monday"
        if job_id not in self.job_schedules:
            self.job_schedules[job_id] = {d: list(self.default_schedule) for d in DAYS_OF_WEEK}
        if day not in self.job_schedules[job_id]:
            self.job_schedules[job_id][day] = list(self.default_schedule)
        return self.job_schedules[job_id][day]

    def get_current_activity(self, job_id, current_hour, day="Monday"):
        """
        Returns the schedule activity for a job at the specified hour and day.
        Priest prayer hours are enforced for Priest and, when decreed by the landlord/priest, across all jobs.
        """
        h = int(current_hour) % 24
        if (job_id == "Priest" or getattr(self, "prayer_override_all", False)) and self.prayer_start_hour <= h < self.prayer_end_hour:
            return SCHEDULE_PRAYER
        sched = self.get_schedule(job_id, day)
        return sched[h]

    def set_hour_activity(self, job_id, hour_idx, activity_type, day="Monday"):
        """Sets the activity for a specific hour of a specific day"""
        if activity_type not in SCHEDULE_TYPES:
            return False
        if not (0 <= hour_idx < 24):
            return False

        # Priest prayer hours cannot be modified individually (indivisible block)
        if job_id == "Priest" and self.prayer_start_hour <= hour_idx < self.prayer_end_hour:
            return False

        sched = self.get_schedule(job_id, day)
        sched[hour_idx] = activity_type
        return True

    def set_activity(self, job_id, hour_idx, activity_type, day="Monday"):
        """Alias for set_hour_activity"""
        return self.set_hour_activity(job_id, hour_idx, activity_type, day=day)

    def fill_all_hours(self, job_id, activity_type, day="Monday"):
        """Fills all 24 hours of a specific day with an activity (preserving prayer hours for Priest)"""
        if activity_type not in SCHEDULE_TYPES:
            return False
        sched = self.get_schedule(job_id, day)
        for i in range(24):
            if job_id == "Priest" and self.prayer_start_hour <= i < self.prayer_end_hour:
                continue
            sched[i] = activity_type
        return True

    def reset_to_default(self, job_id, day=None):
        """Resets schedule to default for one day or all days"""
        days = [day] if day in DAYS_OF_WEEK else DAYS_OF_WEEK
        for d in days:
            self.job_schedules.setdefault(job_id, {})[d] = list(self.default_schedule)
        if job_id == "Priest":
            self._sync_priest_prayer_block()

    def to_dict(self):
        """Serializes schedule state for game saving"""
        return {
            "prayer_start_hour": self.prayer_start_hour,
            "prayer_end_hour": self.prayer_end_hour,
            "job_schedules": {
                j_id: {d: list(s) for d, s in day_map.items()}
                for j_id, day_map in self.job_schedules.items()
            }
        }

    def load_from_dict(self, data):
        """Safely restores schedule state from saved dictionary"""
        if not data or not isinstance(data, dict):
            return
        self.prayer_start_hour = int(data.get("prayer_start_hour", 12))
        self.prayer_end_hour = int(data.get("prayer_end_hour", 14))

        saved_jobs = data.get("job_schedules", {})
        for j_id, day_map in saved_jobs.items():
            if isinstance(day_map, dict):
                self.job_schedules.setdefault(j_id, {})
                for d, s in day_map.items():
                    if d in DAYS_OF_WEEK and isinstance(s, list) and len(s) == 24:
                        self.job_schedules[j_id][d] = list(s)
            elif isinstance(day_map, list) and len(day_map) == 24:
                # Legacy single-day format compatibility
                self.job_schedules.setdefault(j_id, {})
                for d in DAYS_OF_WEEK:
                    self.job_schedules[j_id][d] = list(day_map)

        self._sync_priest_prayer_block()
