"""Daily hourly activity schedules with one shared Prayer Time block."""

from game.config import (
    SCHEDULE_TYPES,
    DEFAULT_JOB_SCHEDULE,
    DEDICATED_JOBS,
    SCHEDULE_PRAYER,
    SCHEDULE_WORK,
    DEFAULT_PRAYER_START_HOUR,
    DEFAULT_PRAYER_END_HOUR,
)

UNIVERSAL_SCHEDULE_ID = "__UNIVERSAL__"


class ScheduleManager:
    """Stores one 24-hour schedule per job; legacy ``day`` args are ignored."""

    def __init__(self):
        self.default_schedule = list(DEFAULT_JOB_SCHEDULE)
        self.universal_schedule = list(self.default_schedule)
        self.universal_schedule_enabled = False
        self.prayer_start_hour = DEFAULT_PRAYER_START_HOUR
        self.prayer_end_hour = DEFAULT_PRAYER_END_HOUR
        self.prayer_override_all = True
        self.job_schedules = {
            job_id: list(self.default_schedule) for job_id in DEDICATED_JOBS
        }
        self._sync_priest_prayer_block()

    def _sync_priest_prayer_block(self):
        schedule = self.job_schedules.get("Priest")
        if schedule is None:
            return
        for hour in range(24):
            if self.prayer_start_hour <= hour < self.prayer_end_hour:
                schedule[hour] = SCHEDULE_PRAYER
            elif schedule[hour] == SCHEDULE_PRAYER:
                schedule[hour] = SCHEDULE_WORK

    def get_prayer_hours(self):
        return self.prayer_start_hour, self.prayer_end_hour

    def is_prayer_hour(self, hour):
        hour = int(hour) % 24
        return self.prayer_start_hour <= hour < self.prayer_end_hour

    def set_prayer_time(self, start_hour, end_hour):
        start = max(0, min(23, int(start_hour)))
        end = max(start + 1, min(24, int(end_hour)))
        self.prayer_start_hour = start
        self.prayer_end_hour = end
        self.prayer_override_all = True
        self._sync_priest_prayer_block()

    def get_schedule(self, job_id, day=None):
        """Return the job's single daily schedule (``day`` is legacy only)."""
        if job_id == UNIVERSAL_SCHEDULE_ID:
            return self.universal_schedule if self.universal_schedule_enabled else self.get_schedule("Unassigned")
        if job_id not in self.job_schedules:
            base_schedule = self.universal_schedule if self.universal_schedule_enabled else self.default_schedule
            self.job_schedules[job_id] = list(base_schedule)
        schedule = self.job_schedules[job_id]
        if isinstance(schedule, dict):
            schedule = schedule.get("Monday") or next(iter(schedule.values()), self.default_schedule)
            self.job_schedules[job_id] = list(schedule)
        return schedule

    def activate_universal_schedule(self):
        """Seed the shared schedule from the current Unassigned schedule, then apply it to every job."""
        if not self.universal_schedule_enabled:
            self.universal_schedule = list(self.get_schedule("Unassigned"))
        self.universal_schedule_enabled = True
        for job_id in list(self.job_schedules):
            self.job_schedules[job_id] = list(self.universal_schedule)
        self._sync_priest_prayer_block()

    def get_schedule_view(self, job_id):
        """Return a display copy with the enforced Prayer Time block applied."""
        schedule = list(self.get_schedule(job_id))
        for hour in range(len(schedule)):
            if self.is_prayer_hour(hour):
                schedule[hour] = SCHEDULE_PRAYER
        return schedule

    def get_current_activity(self, job_id, current_hour, day=None):
        hour = int(current_hour) % 24
        if self.is_prayer_hour(hour):
            return SCHEDULE_PRAYER
        return self.get_scheduled_activity(job_id, current_hour)

    def get_scheduled_activity(self, job_id, current_hour):
        """Return a job's own activity without applying the shared prayer override."""
        schedule = self.get_schedule(job_id)
        hour = int(current_hour) % len(schedule)
        return schedule[hour]

    def paint_hour_activity(self, job_id, hour_idx, activity_type):
        """Paint one hour slot while strictly enforcing a single contiguous Prayer block (>= 1 hour).

        Returns ``(success: bool, message: str)``.
        Rules:
        - Painting PRAYER only expands adjacent boundaries (start - 1 or end). Non-adjacent cells
          are rejected so the prayer block cannot be split.
        - Painting another activity over an existing PRAYER cell only removes outer edge hours
          (start or end - 1) and only when current prayer duration >= 2 hours (minimum 1 hour
          must always remain). Interior prayer hours cannot be erased because that splits the block.
        """
        if activity_type not in SCHEDULE_TYPES or not 0 <= hour_idx < 24:
            return False, "Invalid hour or activity."

        s, e = self.prayer_start_hour, self.prayer_end_hour

        if activity_type == SCHEDULE_PRAYER:
            if s <= hour_idx < e:
                return True, f"Prayer Time: {s:02d}:00 - {e:02d}:00 ({e - s}h)"
            if hour_idx == s - 1:
                self.set_prayer_time(s - 1, e)
                ns, ne = self.prayer_start_hour, self.prayer_end_hour
                return True, f"Prayer Time expanded: {ns:02d}:00 - {ne:02d}:00 ({ne - ns}h)"
            if hour_idx == e:
                self.set_prayer_time(s, e + 1)
                ns, ne = self.prayer_start_hour, self.prayer_end_hour
                return True, f"Prayer Time expanded: {ns:02d}:00 - {ne:02d}:00 ({ne - ns}h)"
            return False, f"Cannot split Prayer Time! Paint an adjacent hour ({max(0, s - 1):02d}:00 or {min(23, e):02d}:00)."

        # Non-PRAYER brush over a current PRAYER hour -> shrink from edge only if duration >= 2h
        if self.is_prayer_hour(hour_idx):
            duration = e - s
            if duration <= 1:
                return False, "Cannot remove: Prayer Time requires a minimum of 1 contiguous hour."
            if hour_idx == s:
                self.set_prayer_time(s + 1, e)
            elif hour_idx == e - 1:
                self.set_prayer_time(s, e - 1)
            else:
                return False, "Cannot erase middle Prayer hour! It would split the Prayer block."

        if job_id == UNIVERSAL_SCHEDULE_ID:
            self.universal_schedule[hour_idx] = activity_type
            self.universal_schedule_enabled = True
            for existing_job_id in list(self.job_schedules):
                self.job_schedules[existing_job_id] = list(self.universal_schedule)
            self._sync_priest_prayer_block()
            return True, ""
        self.get_schedule(job_id)[hour_idx] = activity_type
        return True, ""

    def set_hour_activity(self, job_id, hour_idx, activity_type, day=None):
        ok, _msg = self.paint_hour_activity(job_id, hour_idx, activity_type)
        return ok

    def set_activity(self, job_id, hour_idx, activity_type, day=None):
        return self.set_hour_activity(job_id, hour_idx, activity_type)

    def fill_all_hours(self, job_id, activity_type, day=None):
        if activity_type not in SCHEDULE_TYPES or activity_type == SCHEDULE_PRAYER:
            return False
        if job_id == UNIVERSAL_SCHEDULE_ID:
            self.universal_schedule_enabled = True
            schedules = [self.universal_schedule] + list(self.job_schedules.values())
        else:
            schedules = [self.get_schedule(job_id)]
        for hour in range(24):
            if self.is_prayer_hour(hour):
                continue
            for schedule in schedules:
                schedule[hour] = activity_type
        return True

    def reset_to_default(self, job_id, day=None):
        if job_id == UNIVERSAL_SCHEDULE_ID:
            self.universal_schedule = list(self.default_schedule)
            self.universal_schedule_enabled = True
            for existing_job_id in list(self.job_schedules):
                self.job_schedules[existing_job_id] = list(self.default_schedule)
            self._sync_priest_prayer_block()
            return
        self.job_schedules[job_id] = list(self.default_schedule)
        if job_id == "Priest":
            self._sync_priest_prayer_block()

    def to_dict(self):
        return {
            "prayer_start_hour": self.prayer_start_hour,
            "prayer_end_hour": self.prayer_end_hour,
            "universal_schedule": list(self.universal_schedule),
            "universal_schedule_enabled": self.universal_schedule_enabled,
            "job_schedules": {
                job_id: list(self.get_schedule(job_id))
                for job_id in self.job_schedules
            },
        }

    def load_from_dict(self, data):
        if not isinstance(data, dict):
            return
        self.prayer_start_hour = int(data.get("prayer_start_hour", self.prayer_start_hour))
        self.prayer_end_hour = int(data.get("prayer_end_hour", self.prayer_end_hour))
        self.set_prayer_time(self.prayer_start_hour, self.prayer_end_hour)

        saved_universal = data.get("universal_schedule")
        if isinstance(saved_universal, list) and len(saved_universal) == 24:
            self.universal_schedule = list(saved_universal)
        self.universal_schedule_enabled = bool(data.get("universal_schedule_enabled", False))

        saved_jobs = data.get("job_schedules", data)
        for job_id, schedule in saved_jobs.items():
            if job_id in ("prayer_start_hour", "prayer_end_hour"):
                continue
            # Migrate old weekday maps by keeping their Monday schedule.
            if isinstance(schedule, dict):
                schedule = schedule.get("Monday") or next(iter(schedule.values()), None)
            if isinstance(schedule, list) and len(schedule) == 24:
                restored = list(schedule)
                for hour, activity in enumerate(restored):
                    if activity == SCHEDULE_PRAYER and not (
                        job_id == "Priest" and self.prayer_start_hour <= hour < self.prayer_end_hour
                    ):
                        restored[hour] = SCHEDULE_WORK
                self.job_schedules[job_id] = restored
        self._sync_priest_prayer_block()
        if self.universal_schedule_enabled:
            for job_id in list(self.job_schedules):
                self.job_schedules[job_id] = list(self.universal_schedule)
            self._sync_priest_prayer_block()
