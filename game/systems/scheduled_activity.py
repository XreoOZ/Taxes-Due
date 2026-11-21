"""Pause villager tasks at schedule boundaries and resume them in their slot."""

from game.data.config import (
    SCHEDULE_ACTIVITY_CANCEL_ON_BOUNDARY,
    SCHEDULE_ACTIVITY_NEUTRAL_TASKS,
    SCHEDULE_ACTIVITY_STRICT_TASKS,
    SCHEDULE_ACTIVITY_STRICT_TASK_PREFIXES,
    SCHEDULE_ACTIVITY_STRICT_TASK_PREFIX_EXEMPTIONS,
    SCHEDULE_ACTIVITY_TASK_PREFIXES,
    SCHEDULE_ACTIVITY_TASKS,
    SCHEDULE_ACTIVITY_TASK_STATE_FIELDS,
)
from game.world.pathfinding import GlobalPathRegistry


class ScheduledActivitySystem:
    @staticmethod
    def task_schedule(task):
        if not task or task in SCHEDULE_ACTIVITY_NEUTRAL_TASKS:
            return None
        for schedule, tasks in SCHEDULE_ACTIVITY_TASKS.items():
            if task in tasks:
                return schedule
        for prefix, schedule in SCHEDULE_ACTIVITY_TASK_PREFIXES:
            if task.startswith(prefix):
                return schedule
        return "WORK"

    @classmethod
    def task_is_allowed(cls, task, schedule_activity):
        required_schedule = cls.task_schedule(task)
        if required_schedule is None or schedule_activity is None:
            return True
        strict_prefix = any(task.startswith(prefix) for prefix in SCHEDULE_ACTIVITY_STRICT_TASK_PREFIXES)
        exempt_prefix = any(task.startswith(prefix) for prefix in SCHEDULE_ACTIVITY_STRICT_TASK_PREFIX_EXEMPTIONS)
        if task in SCHEDULE_ACTIVITY_STRICT_TASKS or (strict_prefix and not exempt_prefix):
            return schedule_activity == "WORK"
        if schedule_activity == "ANY":
            return True
        if task in SCHEDULE_ACTIVITY_TASKS.get(schedule_activity, ()):
            return True
        for prefix, task_schedule in SCHEDULE_ACTIVITY_TASK_PREFIXES:
            if task.startswith(prefix):
                return task_schedule == schedule_activity
        return schedule_activity == required_schedule

    @staticmethod
    def _capture_task_state(villager):
        return {
            field: getattr(villager, field, None)
            for field in SCHEDULE_ACTIVITY_TASK_STATE_FIELDS
        }

    @staticmethod
    def _restore_task_state(villager, state):
        for field in SCHEDULE_ACTIVITY_TASK_STATE_FIELDS:
            if field not in state:
                continue
            value = state[field]
            if field == "current_work_tile" and isinstance(value, list):
                value = tuple(value)
            setattr(villager, field, value)

    @classmethod
    def _queue_task(cls, villager, task, state=None):
        schedule = cls.task_schedule(task)
        if schedule is None:
            return
        queue = getattr(villager, "pending_schedule_tasks", None)
        if not isinstance(queue, list):
            queue = []
            villager.pending_schedule_tasks = queue
        if any(entry.get("task") == task and entry.get("schedule") == schedule
               for entry in queue if isinstance(entry, dict)):
            return
        queue.append({
            "task": task,
            "schedule": schedule,
            "state": dict(state) if isinstance(state, dict) else cls._capture_task_state(villager),
        })

    @classmethod
    def _resume_task(cls, villager, schedule_activity):
        queue = getattr(villager, "pending_schedule_tasks", None)
        if not isinstance(queue, list) or not queue:
            return False
        eligible_index = next(
            (index for index, entry in enumerate(queue)
             if isinstance(entry, dict)
             and cls.task_is_allowed(entry.get("task"), schedule_activity)),
            None,
        )
        if eligible_index is None:
            return False
        entry = queue.pop(eligible_index)
        cls._restore_task_state(villager, entry.get("state", {}))
        villager.task = entry.get("task", "IDLE")
        return True

    @classmethod
    def reconcile(cls, villager, schedule_activity, permit_manager=None):
        villager.current_schedule_activity = schedule_activity
        task = getattr(villager, "task", "IDLE")
        required_schedule = cls.task_schedule(task)
        if required_schedule and not cls.task_is_allowed(task, schedule_activity):
            if task not in SCHEDULE_ACTIVITY_CANCEL_ON_BOUNDARY:
                cls._queue_task(villager, task)
            if task == "SEEKING_TOILET":
                from game.systems.toilet_system import ToiletSystem
                target = getattr(villager, "target_toilet", None)
                if target is not None:
                    ToiletSystem.release_toilet(villager, target)
                villager.target_toilet = None
                villager.toilet_target_building = None
                villager.toilet_use_timer = 0.0
            if task in ("LEADING_PRAYER", "ATTENDING_PRAYER", "PRAYING"):
                from game.systems.church_system import ChurchSystem
                ChurchSystem.release_church_tile(villager)
            if getattr(villager, "current_work_tile", None) and permit_manager:
                farm = next(
                    (permit for permit in permit_manager.permits
                     if permit.permit_type == "farm"
                     and villager.id in getattr(permit, "assigned_workers", [])),
                    None,
                )
                if farm:
                    farm.release_worker_reservations(villager.id)
            GlobalPathRegistry.get_instance().release_reservation(villager.id)
            villager.current_path = []
            villager.path_index = 0
            villager.path_target = None
            villager.path_target_tile = None
            villager.target_x = None
            villager.target_y = None
            villager.is_moving = False
            villager.is_waiting_for_path = False
            villager.task = "IDLE"

        if getattr(villager, "task", "IDLE") in ("IDLE", "LEISURE", "STROLLING"):
            cls._resume_task(villager, schedule_activity)
