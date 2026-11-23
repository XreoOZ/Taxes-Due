import unittest
from types import SimpleNamespace

from game.systems.economy.taxation_system import TaxationSystem
from game.systems.economy.currency import to_copper


class TestSocageTaxReport(unittest.TestCase):
    def setUp(self):
        self.original_state = TaxationSystem.to_dict()
        TaxationSystem._socage_report_period = None
        TaxationSystem._socage_report_collected_copper = 0
        TaxationSystem.set_socage_percent(10)

    def tearDown(self):
        TaxationSystem.load_dict(self.original_state)

    def test_report_sums_collections_and_rolls_over_each_ten_day_period(self):
        TaxationSystem.record_socage_tax_collected(15, 2)
        TaxationSystem.record_socage_tax_collected(25, 10)

        report = TaxationSystem.get_socage_tax_report(10)
        self.assertEqual(report["start_day"], 1)
        self.assertEqual(report["end_day"], 10)
        self.assertEqual(report["through_day"], 10)
        self.assertEqual(report["collected_copper"], 40)

        saved_state = TaxationSystem.to_dict()
        TaxationSystem._socage_report_period = None
        TaxationSystem._socage_report_collected_copper = 0
        TaxationSystem.load_dict(saved_state)
        self.assertEqual(
            TaxationSystem.get_socage_tax_report(10)["collected_copper"],
            40,
        )

        next_report = TaxationSystem.get_socage_tax_report(11)
        self.assertEqual(next_report["start_day"], 11)
        self.assertEqual(next_report["end_day"], 20)
        self.assertEqual(next_report["collected_copper"], 0)

    def test_successful_household_tax_transfer_is_recorded(self):
        collector = SimpleNamespace(
            id="collector",
            job="Tax Collector",
            is_alive=True,
            family_id="tax-family",
            socage_tax_round={
                "cycle": 1,
                "status": "MEET",
                "target_family_id": "payer-family",
            },
            inventory={},
            x=0.0,
            y=0.0,
            radius=20.0,
            task="WAITING_FOR_HOUSEHOLD_TAX",
            say=lambda *_args, **_kwargs: None,
        )
        representative = SimpleNamespace(
            id="payer",
            family_id="payer-family",
            age=30,
            is_alive=True,
            inventory={},
            x=0.0,
            y=0.0,
            radius=20.0,
            task="IDLE",
            happiness_status="happy",
            socage_tax_prepared_cycle=None,
            socage_tax_prepared_amount=0,
            _move_towards=lambda *_args, **_kwargs: True,
            _resume_or_idle_after_need=lambda: None,
            say=lambda *_args, **_kwargs: None,
        )
        family = SimpleNamespace(id="payer-family", members=[representative])
        manager = SimpleNamespace(
            families=[family],
            get_all_villagers=lambda: [collector, representative],
            get_family_by_id=lambda family_id: family if family_id == family.id else None,
        )
        chest = SimpleNamespace(inventory={"Copper": 100})
        furniture_manager = SimpleNamespace(
            get_storage_for_family=lambda _family_id: chest,
        )

        # Universal physical flow: tick 1 = representative collects coins
        # from household storage, tick 2 = delivers payment to collector.
        handled = False
        for _ in range(3):
            handled = TaxationSystem.update_household_representative(
                representative, 0.1, manager, None, None, furniture_manager,
                [collector, representative], None, day_number=4,
                collector_activity="WORK", villager_activity="WORK",
            )
            if to_copper(collector.inventory) >= 10:
                break

        self.assertTrue(handled)
        self.assertEqual(to_copper(collector.inventory), 10)
        self.assertEqual(
            TaxationSystem.get_socage_tax_report(4)["collected_copper"],
            10,
        )


if __name__ == "__main__":
    unittest.main()
