"""Shared free-time handoff for household commission errands."""

from game.data.config import FREE_TIME_SCHEDULE_ACTIVITIES


class CommissionScheduleSystem:
    @staticmethod
    def queue(villager, task, **task_data):
        if not villager or not task:
            return False
        queue = getattr(villager, "pending_commission_tasks", None)
        if not isinstance(queue, list):
            queue = []
            villager.pending_commission_tasks = queue
        task_name = str(task)
        if not any(entry.get("task") == task_name and entry.get("data") == task_data for entry in queue):
            queue.append({"task": task_name, "data": dict(task_data)})
        CommissionScheduleSystem._sync_legacy_fields(villager)
        return True

    @staticmethod
    def is_queued(villager, task, data_key=None, data_value=None):
        for entry in getattr(villager, "pending_commission_tasks", []) or []:
            if entry.get("task") != task:
                continue
            if data_key is None or str(entry.get("data", {}).get(data_key)) == str(data_value):
                return True
        return False

    @staticmethod
    def _sync_legacy_fields(villager):
        queue = getattr(villager, "pending_commission_tasks", []) or []
        head = queue[0] if queue else {}
        villager.pending_commission_task = head.get("task")
        villager.pending_commission_data = dict(head.get("data", {}))

    @staticmethod
    def _errand_in_flight(villager):
        """True while a previously activated commission errand is still
        executing on this villager.

        Every commission errand payload marks the villager with a tracking
        attribute (``builder_payment_order_id`` for builder-fee and refund
        errands, ``burial_payment_target_corpse_id`` for burial fees), and
        each completion/abort path clears it — so a set attribute reliably
        means "errand in flight" without hardcoding task names here.
        """
        return (
            getattr(villager, "builder_payment_order_id", None) not in (None, "")
            or getattr(villager, "burial_payment_target_corpse_id", None) not in (None, "")
        )

    @staticmethod
    def activate(villager, schedule_activity):
        queue = getattr(villager, "pending_commission_tasks", None)
        if not isinstance(queue, list):
            legacy_task = getattr(villager, "pending_commission_task", None)
            queue = ([{"task": legacy_task,
                       "data": dict(getattr(villager, "pending_commission_data", {}) or {})}]
                     if legacy_task else [])
            villager.pending_commission_tasks = queue
        elif not queue and getattr(villager, "pending_commission_task", None):
            queue = [{
                "task": villager.pending_commission_task,
                "data": dict(getattr(villager, "pending_commission_data", {}) or {}),
            }]
            villager.pending_commission_tasks = queue
        if not queue:
            return False
        # An errand activated earlier must run to completion (coins retrieved
        # -> delivered -> order PAID) before the next queued commission is
        # popped. Without this guard the representative re-targets a new
        # errand every tick and oscillates between orders.
        if CommissionScheduleSystem._errand_in_flight(villager):
            return False
        head_task = str(queue[0].get("task", ""))
        work_errand = schedule_activity == "WORK" and (
            head_task.startswith("BUILDER_FEE_")
            or head_task == "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE"
        )
        if schedule_activity not in FREE_TIME_SCHEDULE_ACTIVITIES and not work_errand:
            return False
        entry = queue.pop(0)
        task = entry.get("task")
        if getattr(villager, "interrupted_task_state", None) is None:
            villager.interrupt_task("COMMISSION", activity_label="Handling a household commission")
        for key, value in entry.get("data", {}).items():
            setattr(villager, key, value)
        CommissionScheduleSystem._sync_legacy_fields(villager)
        villager.task = task
        return True
