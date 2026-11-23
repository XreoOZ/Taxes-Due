"""Headless tests for the artisan commission FIFO queue + death refunds."""
import unittest
from types import SimpleNamespace

from game.systems.work.builder_system import BuilderSystem


def make_order(**kw):
    base = {
        "id": "o1", "order_type": "BUILD", "status": "PAID",
        "builder_id": "c1", "artisan_job": "Builder",
        "commission_paid": True, "paid_amount_copper": 50,
        "paid_by_id": "v_payer", "paid_by_family_id": "fam_payer",
        "payer_family_id": "fam_payer", "payer_type": "household",
        "price_copper": 50,
    }
    base.update(kw)
    return base


def make_subject(order, sid="f1"):
    return SimpleNamespace(id=sid, construction_order=order)


def make_villager(vid, job="Builder", alive=True, family="fam_c", **kw):
    v = SimpleNamespace(
        id=vid, job=job, is_alive=alive, family_id=family,
        task="IDLE", x=0.0, y=0.0, inventory={},
        pending_commission_tasks=[], pending_commission_task=None,
        pending_commission_data={}, speech_text=None,
        builder_payment_order_id=None,
        builder_refund_from_family=None, builder_refund_to_family=None,
        builder_refund_amount=0, builder_refund_phase=None,
    )
    v.say = lambda *a, **k: None
    v._resume_or_idle_after_need = lambda: None
    for k, val in kw.items():
        setattr(v, k, val)
    return v


def make_managers(villagers, families=None, furn_orders=None):
    furn_orders = furn_orders or []
    furniture_manager = SimpleNamespace(
        furnitures=[make_subject(o, f"f{i}") for i, o in enumerate(furn_orders)],
        get_storage_for_family=lambda fid: None,
    )
    building_manager = SimpleNamespace(construction_sites=[], buildings=[])
    fam_map = families or {}
    villager_manager = SimpleNamespace(
        get_all_villagers=lambda: villagers,
        get_family_by_id=lambda fid: fam_map.get(fid),
    )
    return furniture_manager, building_manager, villager_manager


class TestPaidSeqFIFO(unittest.TestCase):
    def test_ensure_paid_seq_stamps_in_order(self):
        o1 = make_order(id="a")
        o2 = make_order(id="b")
        fm, bm, vm = make_managers([], furn_orders=[o1, o2])
        BuilderSystem._paid_seq_floor = 0
        BuilderSystem._ensure_paid_seq(o1, fm, bm)
        BuilderSystem._ensure_paid_seq(o2, fm, bm)
        self.assertEqual(o1["paid_seq"], 1)
        self.assertEqual(o2["paid_seq"], 2)
        # second call does not restamp
        BuilderSystem._ensure_paid_seq(o1, fm, bm)
        self.assertEqual(o1["paid_seq"], 1)

    def test_queue_length_counts_active_orders(self):
        orders = [
            make_order(id="a", status="PAID"),
            make_order(id="b", status="PAYMENT_TRAVELING"),
            make_order(id="c", status="COMPLETE"),
            make_order(id="d", status="AWAITING_PAYMENT", builder_id=None),
            make_order(id="e", builder_id="c2"),
        ]
        fm, bm, vm = make_managers([], furn_orders=orders)
        # PAID + PAYMENT_TRAVELING count; COMPLETE/AWAITING_PAYMENT/other builder don't
        self.assertEqual(BuilderSystem._queue_length("c1", fm, bm), 2)
        self.assertEqual(BuilderSystem._queue_length("c2", fm, bm), 1)


class TestSweepDeadArtisan(unittest.TestCase):
    def test_paid_order_refunded_and_reset(self):
        dead = make_villager("c1", alive=False)
        payer = make_villager("v_payer", job="Farmer", family="fam_payer")
        family = SimpleNamespace(members=[payer])
        order = make_order()
        fm, bm, vm = make_managers(
            [dead, payer], families={"fam_payer": family}, furn_orders=[order])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm)
        self.assertTrue(order.get("refund_issued"))
        self.assertEqual(order["status"], "AWAITING_PAYMENT")
        self.assertIsNone(order["builder_id"])
        self.assertFalse(order["commission_paid"])
        self.assertNotIn("paid_seq", order)
        # household rep got the refund errand queued
        self.assertTrue(any(e.get("task") == "COMMISSION_REFUND_COLLECT"
                            for e in payer.pending_commission_tasks))

    def test_landlord_paid_order_uses_servant(self):
        dead = make_villager("c1", alive=False)
        order = make_order(paid_by_id="landlord", payer_type="landlord",
                           payer_id="landlord", paid_by_family_id=None)
        fm, bm, vm = make_managers([dead], furn_orders=[order])
        servant = SimpleNamespace(is_alive=True, state="IDLE", say=lambda *a, **k: None,
                                  inventory={})
        sm = SimpleNamespace(servants=[servant])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm, servant_manager=sm)
        self.assertTrue(order.get("refund_issued"))
        self.assertEqual(order["status"], "LANDLORD_PAYMENT_PENDING")
        self.assertEqual(servant.state, "COMMISSION_REFUND_COLLECT")
        self.assertEqual(servant.builder_refund_amount, 50)

    def test_non_paid_order_only_releases_slot(self):
        dead = make_villager("c1", alive=False)
        order = make_order(status="AWAITING_MATERIAL", commission_paid=True,
                           paid_amount_copper=50)
        fm, bm, vm = make_managers([dead], furn_orders=[order])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm)
        self.assertIsNone(order["builder_id"])
        self.assertFalse(order.get("refund_issued"))
        self.assertEqual(order["status"], "AWAITING_MATERIAL")

    def test_alive_builder_untouched(self):
        alive = make_villager("c1", alive=True)
        order = make_order()
        fm, bm, vm = make_managers([alive], furn_orders=[order])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm)
        self.assertEqual(order["builder_id"], "c1")
        self.assertEqual(order["status"], "PAID")
        self.assertFalse(order.get("refund_issued"))

    def test_artisan_job_mismatch_not_swept(self):
        # Order belongs to a Blacksmith; the dead villager was a Builder.
        dead_carp = make_villager("c1", job="Builder", alive=False)
        smith = make_villager("s1", job="Blacksmith", alive=True)
        order = make_order(builder_id="s1", artisan_job="Blacksmith")
        fm, bm, vm = make_managers([dead_carp, smith], furn_orders=[order])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm)
        self.assertEqual(order["builder_id"], "s1")
        self.assertEqual(order["status"], "PAID")

    def test_zero_fee_order_no_refund(self):
        dead = make_villager("c1", alive=False)
        order = make_order(paid_amount_copper=0, price_copper=0,
                           paid_by_id="household")
        fm, bm, vm = make_managers([dead], furn_orders=[order])
        BuilderSystem.sweep_dead_commission_orders(bm, fm, vm)
        self.assertEqual(order["status"], "AWAITING_PAYMENT")
        self.assertFalse(order.get("refund_issued"))


if __name__ == "__main__":
    unittest.main()
