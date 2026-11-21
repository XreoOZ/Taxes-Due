from game.data.config import AI_ACTIVITY_NEXT_STEPS, AI_ACTIVITY_PREVIEW_MAX_NEXT


class ActivityPreviewSystem:
    @staticmethod
    def _queued_tasks(villager, current_task):
        queued = []
        seen = {current_task} if current_task else set()
        for field in ("pending_commission_tasks", "pending_schedule_tasks"):
            entries = getattr(villager, field, None) or []
            for entry in entries:
                task = entry.get("task") if isinstance(entry, dict) else None
                if task and task not in seen:
                    task_name = str(task)
                    queued.append(task_name.replace("_", " ").title())
                    seen.add(task)

        legacy_task = getattr(villager, "pending_commission_task", None)
        if legacy_task and legacy_task not in seen:
            queued.append(str(legacy_task).replace("_", " ").title())
        return queued

    @classmethod
    def get_next_activities(cls, villager):
        if villager is None or not getattr(villager, "is_alive", True):
            return []

        current_task = getattr(villager, "task", None)
        activities = list(AI_ACTIVITY_NEXT_STEPS.get(current_task, ()))
        activities.extend(cls._queued_tasks(villager, current_task))

        unique = []
        for activity in activities:
            if activity and activity not in unique:
                unique.append(activity)
            if len(unique) >= AI_ACTIVITY_PREVIEW_MAX_NEXT:
                break
        return unique
