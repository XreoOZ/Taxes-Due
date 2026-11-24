"""Headless regression test: household commission payments must serialize.

Bug: one household placing MULTIPLE builder/furniture commissions queued one
BUILDER_FEE_RETRIEVE errand per order on the same representative, and
CommissionScheduleSystem.activate popped the next queue head EVERY tick —
so the payer oscillated between orders and never finished one payment.

Run: python -m unittest tests.test_commission_payment_serialization
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.systems.work.commission_schedule import CommissionScheduleSystem
from game.systems.work.builder_system import BuilderSystem


def make_payer(vid="v_rep", family_id="fam_payer"):
    payer = SimpleNamespace(
        id=vid, family_id=family_id, is_alive=True,
        task="IDLE", x=0.0, y=0.0,
        inventory={},
        hunger=100.0, thirst=100.0, need_toilet=100.0,
        pending_commission_tasks=[], pending_commission_task=None,
        pending_commission_data={}, interrupted_task_state=None,
        builder_payment_order_id=None, builder_payment_builder_id=None,
        builder_fee_needed=None,
    )
    payer.say = lambda *a, **k: None
    payer.interrupt_task = lambda *a, **k: None
    payer._resume_or_idle_after_need = lambda: None
    return payer


def make_family(fid, members, purse=None):
    purse = {"copper": 500} if purse is None else purse
    fam = SimpleNamespace(id=fid, members=list(members), currency=dict(purse or {}))
    fam.get_available_recovery_representative = (
        lambda: next((m for m in fam.members
                      if getattr(m, "is_alive", True)
                      and getattr(m, "task", "") not in (
                          "SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET",
                          "RECOVER_DEATH_ITEMS")), None)
    )
    return fam


def make_order(oid, payer_family, builder_id="b_ext", price=50):
    return SimpleNamespace(construction_order={
        "id": oid, "status": "AWAITING_PAYMENT",
        "payer_family_id": payer_family, "builder_id": builder_id,
        "price_copper": price, "order_type": "FURNITURE",
        "artisan_job": "Builder",
    })


def make_furniture_manager():
    return SimpleNamespace(furnitures=[], get_storage_for_family=lambda fid: None)


def make_villager_manager(families, all_villagers):
    return SimpleNamespace(
        get_family_by_id=lambda fid: families.get(fid),
        get_all_villagers=lambda: all_villagers,
    )


class TestActivateDoesNotPreempt(unittest.TestCase):
    """Layer 1: activate() must not pop the next errand while one is running."""

    def _queued_payer(self):
        payer = make_payer()
        for oid in ("o1", "o2", "o3"):
            CommissionScheduleSystem.queue(
                payer, "BUILDER_FEE_RETRIEVE",
                builder_payment_order_id=oid,
                builder_payment_builder_id="b_ext",
            )
        return payer

    def test_single_activation_per_errand(self):
        payer = self._queued_payer()
        # First activation pops order o1 and marks the errand in flight.
        self.assertTrue(CommissionScheduleSystem.activate(payer, "LEISURE"))
        self.assertEqual(payer.task, "BUILDER_FEE_RETRIEVE")
        self.assertEqual(payer.builder_payment_order_id, "o1")
        self.assertEqual(len(payer.pending_commission_tasks), 2)

        # While o1's errand is in flight, activate must NOT preempt it with o2.
        for _ in range(5):
            self.assertFalse(CommissionScheduleSystem.activate(payer, "LEISURE"))
            self.assertEqual(payer.task, "BUILDER_FEE_RETRIEVE")
            self.assertEqual(payer.builder_payment_order_id, "o1")
        self.assertEqual(len(payer.pending_commission_tasks), 2)

        # Errand completes (retrieve -> deliver -> PAID clears the marker).
        payer.builder_payment_order_id = None
        payer.task = "IDLE"
        self.assertTrue(CommissionScheduleSystem.activate(payer, "LEISURE"))
        self.assertEqual(payer.builder_payment_order_id, "o2")

        payer.builder_payment_order_id = None
        payer.task = "IDLE"
        self.assertTrue(CommissionScheduleSystem.activate(payer, "LEISURE"))
        self.assertEqual(payer.builder_payment_order_id, "o3")
        self.assertEqual(len(payer.pending_commission_tasks), 0)

    def test_burial_marker_also_blocks(self):
        payer = make_payer()
        CommissionScheduleSystem.queue(
            payer, "BURIAL_PAYMENT_RETRIEVE",
            burial_payment_target_corpse_id="c9",
            burial_payment_gravedigger_id="g1",
        )
        CommissionScheduleSystem.queue(
            payer, "BUILDER_FEE_RETRIEVE",
            builder_payment_order_id="o1",
            builder_payment_builder_id="b_ext",
        )
        self.assertTrue(CommissionScheduleSystem.activate(payer, "LEISURE"))
        self.assertEqual(payer.task, "BURIAL_PAYMENT_RETRIEVE")
        self.assertFalse(CommissionScheduleSystem.activate(payer, "LEISURE"))
        self.assertEqual(payer.task, "BURIAL_PAYMENT_RETRIEVE")


class TestAssignPaymentSerialization(unittest.TestCase):
    """Layer 2: _assign_payment only schedules ONE errand per family at a time."""

    def _setup(self):
        rep = make_payer()
        fam = make_family("fam_payer", [rep])
        families = {"fam_payer": fam}
        vm = make_villager_manager(families, [rep])
        fm = make_furniture_manager()
        return rep, fam, vm, fm

    def test_three_orders_same_family_serialize(self):
        rep, fam, vm, fm = self._setup()
        orders = [make_order(f"o{i}", "fam_payer") for i in range(1, 4)]
        subjects = [make_order_subject(o, f"f{i}") for i, o in enumerate(orders)]

        # First order claims and queues its payment errand.
        self.assertTrue(BuilderSystem._assign_payment(subjects[0], vm, fm, None))
        self.assertEqual(orders[0].construction_order["status"], "PAYMENT_REQUESTED")
        fee_entries = [e for e in rep.pending_commission_tasks
                       if e["task"] == "BUILDER_FEE_RETRIEVE"]
        self.assertEqual(len(fee_entries), 1)
        self.assertEqual(fee_entries[0]["data"]["builder_payment_order_id"], "o1")

        # Simulate the errand being activated (in flight).
        CommissionScheduleSystem.activate(rep, "LEISURE")
        self.assertEqual(rep.task, "BUILDER_FEE_RETRIEVE")

        # Orders 2 and 3 must NOT queue their own errands while o1 is in flight.
        self.assertFalse(BuilderSystem._assign_payment(subjects[1], vm, fm, None))
        self.assertFalse(BuilderSystem._assign_payment(subjects[2], vm, fm, None))
        self.assertEqual(orders[1].construction_order["status"], "AWAITING_PAYMENT")
        self.assertEqual(orders[2].construction_order["status"], "AWAITING_PAYMENT")
        fee_entries = [e for e in rep.pending_commission_tasks
                       if e["task"] == "BUILDER_FEE_RETRIEVE"]
        self.assertEqual(len(fee_entries), 0)  # o1 already popped; nothing new queued

        # Complete o1's errand, then the next order may be scheduled.
        rep.builder_payment_order_id = None
        rep.builder_payment_builder_id = None
        rep.task = "IDLE"
        orders[0].construction_order["status"] = "PAID"
        self.assertTrue(BuilderSystem._assign_payment(subjects[1], vm, fm, None))
        self.assertEqual(orders[1].construction_order["status"], "PAYMENT_REQUESTED")
        fee_entries = [e for e in rep.pending_commission_tasks
                       if e["task"] == "BUILDER_FEE_RETRIEVE"]
        self.assertEqual(len(fee_entries), 1)
        self.assertEqual(fee_entries[0]["data"]["builder_payment_order_id"], "o2")

        # And o3 still waits behind o2.
        rep.task = "BUILDER_FEE_RETRIEVE"   # o2 errand activated/in flight
        rep.builder_payment_order_id = "o2"
        self.assertFalse(BuilderSystem._assign_payment(subjects[2], vm, fm, None))
        self.assertEqual(orders[2].construction_order["status"], "AWAITING_PAYMENT")

    def test_single_order_still_works(self):
        rep, fam, vm, fm = self._setup()
        order = make_order("solo", "fam_payer")
        subject = make_order_subject(order, "fs")
        self.assertTrue(BuilderSystem._assign_payment(subject, vm, fm, None))
        self.assertEqual(order.construction_order["status"], "PAYMENT_REQUESTED")
        self.assertEqual(order.construction_order["payer_id"], "v_rep")
        self.assertTrue(any(e["task"] == "BUILDER_FEE_RETRIEVE"
                            for e in rep.pending_commission_tasks))

    def test_other_family_unaffected(self):
        rep_a = make_payer("v_a", "fam_a")
        rep_b = make_payer("v_b", "fam_b")
        fam_a = make_family("fam_a", [rep_a])
        fam_b = make_family("fam_b", [rep_b])
        vm = make_villager_manager({"fam_a": fam_a, "fam_b": fam_b}, [rep_a, rep_b])
        fm = make_furniture_manager()

        # fam_a has an errand in flight.
        order_a = make_order("oa", "fam_a")
        self.assertTrue(BuilderSystem._assign_payment(
            make_order_subject(order_a, "fa"), vm, fm, None))
        CommissionScheduleSystem.activate(rep_a, "LEISURE")
        self.assertEqual(rep_a.task, "BUILDER_FEE_RETRIEVE")

        # fam_b's order must still be scheduled on ITS representative.
        order_b = make_order("ob", "fam_b")
        self.assertTrue(BuilderSystem._assign_payment(
            make_order_subject(order_b, "fb"), vm, fm, None))
        self.assertEqual(order_b.construction_order["status"], "PAYMENT_REQUESTED")
        self.assertEqual(order_b.construction_order["payer_id"], "v_b")
        self.assertTrue(any(e["task"] == "BUILDER_FEE_RETRIEVE"
                            for e in rep_b.pending_commission_tasks))
        self.assertEqual(len(rep_a.pending_commission_tasks), 0)

    def test_second_family_member_waits_for_first(self):
        """Single representative rule: a household serializes commission payments.
        A second order must wait in AWAITING_PAYMENT until the first errand finishes."""
        rep1 = make_payer("v1", "fam_p")
        rep2 = make_payer("v2", "fam_p")
        fam = make_family("fam_p", [rep1, rep2])
        vm = make_villager_manager({"fam_p": fam}, [rep1, rep2])
        fm = make_furniture_manager()

        o1 = make_order("m1", "fam_p")
        self.assertTrue(BuilderSystem._assign_payment(
            make_order_subject(o1, "fm1"), vm, fm, None))
        CommissionScheduleSystem.activate(rep1, "LEISURE")
        self.assertEqual(rep1.task, "BUILDER_FEE_RETRIEVE")

        # rep1 is busy on a fee errand — the second order must WAIT, not dispatch rep2
        o2 = make_order("m2", "fam_p")
        self.assertFalse(BuilderSystem._assign_payment(
            make_order_subject(o2, "fm2"), vm, fm, None))
        self.assertEqual(o2.construction_order["status"], "AWAITING_PAYMENT")

    def test_order_waits_when_all_members_busy(self):
        """With an active representative errand, subsequent orders stay
        AWAITING_PAYMENT instead of double-booking payers."""
        rep1 = make_payer("v1", "fam_p")
        rep2 = make_payer("v2", "fam_p")
        fam = make_family("fam_p", [rep1, rep2])
        vm = make_villager_manager({"fam_p": fam}, [rep1, rep2])
        fm = make_furniture_manager()

        o0 = make_order("m0", "fam_p")
        self.assertTrue(BuilderSystem._assign_payment(
            make_order_subject(o0, "fm0"), vm, fm, None))

        o1 = make_order("m1", "fam_p")
        self.assertFalse(BuilderSystem._assign_payment(
            make_order_subject(o1, "fm1"), vm, fm, None))
        self.assertEqual(o1.construction_order["status"], "AWAITING_PAYMENT")

        # Both members now have queued/in-flight fee errands.
        rep1.pending_commission_tasks.append({"task": "BUILDER_FEE_RETRIEVE"})
        rep2.pending_commission_tasks.append({"task": "BUILDER_FEE_RETRIEVE"})

        o3 = make_order("m3", "fam_p")
        self.assertFalse(BuilderSystem._assign_payment(
            make_order_subject(o3, "fm3"), vm, fm, None))
        self.assertEqual(o3.construction_order["status"], "AWAITING_PAYMENT")


def make_order_subject(order_ns, sid):
    return SimpleNamespace(id=sid, construction_order=order_ns.construction_order)


if __name__ == "__main__":
    unittest.main()
