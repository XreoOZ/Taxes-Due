"""
RimWorld-Style 24-Hour Activity Schedule System
Manages daily hourly routines (Work, Leisure, Sleep, Anything) for dedicated village jobs.
"""

from game.config import (
    SCHEDULE_TYPES,
    DEFAULT_JOB_SCHEDULE,
    DEDICATED_JOBS,
    SCHEDULE_WORK,
    SCHEDULE_LEISURE,
    SCHEDULE_SLEEP,
    SCHEDULE_ANY
)

class ScheduleManager:
    def __init__(self):
        # 24-hour schedule list per job ID
        self.job_schedules = {}
        for job_id in DEDICATED_JOBS:
            self.job_schedules[job_id] = list(DEFAULT_JOB_SCHEDULE)
        # Default fallback schedule
        self.default_schedule = list(DEFAULT_JOB_SCHEDULE)

    def get_schedule(self, job_id):
        if job_id not in self.job_schedules:
            self.job_schedules[job_id] = list(self.default_schedule)
        return self.job_schedules[job_id]

    def get_current_activity(self, job_id, current_hour):
        """Returns the schedule activity for a job at the specified hour (0.0 to 23.99)"""
        hour_idx = int(current_hour) % 24
        sched = self.get_schedule(job_id)
        return sched[hour_idx]

    def set_hour_activity(self, job_id, hour_idx, activity_type):
        if activity_type not in SCHEDULE_TYPES:
            return False
        sched = self.get_schedule(job_id)
        if 0 <= hour_idx < 24:
            sched[hour_idx] = activity_type
            return True
        return False

    def fill_all_hours(self, job_id, activity_type):
        if activity_type not in SCHEDULE_TYPES:
            return False
        sched = self.get_schedule(job_id)
        for i in range(24):
            sched[i] = activity_type
        return True

    def reset_to_default(self, job_id):
        self.job_schedules[job_id] = list(self.default_schedule)
