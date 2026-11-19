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


class ScheduleManager:
    """Stores one 24-hour schedule per job; legacy ``day`` args are ignored."""

    def __init__(self):
        self.default_schedule = list(DEFAULT_JOB_SCHEDULE)
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
        if job_id not in self.job_schedules:
            self.job_schedules[job_id] = list(self.default_schedule)
        schedule = self.job_schedules[job_id]
        if isinstance(schedule, dict):
            schedule = schedule.get("Monday") or next(iter(schedule.values()), self.default_schedule)
            self.job_schedules[job_id] = list(schedule)
        return schedule

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

    def set_hour_activity(self, job_id, hour_idx, activity_type, day=None):
        if activity_type not in SCHEDULE_TYPES or not 0 <= hour_idx < 24:
            return False
        if activity_type == SCHEDULE_PRAYER:
            return False
        if self.is_prayer_hour(hour_idx):
            return False
        self.get_schedule(job_id)[hour_idx] = activity_type
        return True

    def set_activity(self, job_id, hour_idx, activity_type, day=None):
        return self.set_hour_activity(job_id, hour_idx, activity_type)

    def fill_all_hours(self, job_id, activity_type, day=None):
        if activity_type not in SCHEDULE_TYPES or activity_type == SCHEDULE_PRAYER:
            return False
        schedule = self.get_schedule(job_id)
        for hour in range(24):
            if self.is_prayer_hour(hour):
                continue
            schedule[hour] = activity_type
        return True

    def reset_to_default(self, job_id, day=None):
        self.job_schedules[job_id] = list(self.default_schedule)
        if job_id == "Priest":
            self._sync_priest_prayer_block()

    def to_dict(self):
        return {
            "prayer_start_hour": self.prayer_start_hour,
            "prayer_end_hour": self.prayer_end_hour,
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
