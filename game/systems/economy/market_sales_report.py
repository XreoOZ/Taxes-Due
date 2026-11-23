"""Rolling fixed-length sales summaries stored on each individual market stall."""

from game.data.config import MARKET_SALES_REPORT_PERIOD_DAYS


class MarketSalesReportSystem:
    @staticmethod
    def _period(day_number):
        days = max(1, int(MARKET_SALES_REPORT_PERIOD_DAYS))
        day = max(1, int(day_number or 1))
        return (day - 1) // days

    @classmethod
    def _ensure_period(cls, market, day_number):
        period = cls._period(day_number)
        if getattr(market, "sales_report_period", None) != period:
            market.sales_report_period = period
            market.sales_report_by_item = {}
        elif not isinstance(getattr(market, "sales_report_by_item", None), dict):
            market.sales_report_by_item = {}
        return period

    @classmethod
    def record_sale(cls, market, item_name, quantity, unit_price_copper, day_number=None):
        if not market or int(quantity) <= 0:
            return
        day = day_number if day_number is not None else getattr(
            market, "current_day_number", getattr(market, "sales_report_last_day", 1)
        )
        cls._ensure_period(market, day)
        market.sales_report_last_day = max(1, int(day))
        item = market.sales_report_by_item.setdefault(str(item_name), {
            "quantity": 0,
            "revenue_copper": 0,
        })
        item["quantity"] = max(0, int(item.get("quantity", 0))) + int(quantity)
        item["revenue_copper"] = max(0, int(item.get("revenue_copper", 0))) + int(quantity) * max(0, int(unit_price_copper))

    @classmethod
    def record_household_income(cls, villager_manager, family_id, source, amount_copper, day_number=1):
        """Record external coin income on the owning household's rolling report."""
        amount = max(0, int(amount_copper or 0))
        family = (villager_manager.get_family_by_id(family_id)
                  if villager_manager and family_id is not None else None)
        if not family or amount <= 0:
            return False
        period = cls._period(day_number)
        if getattr(family, "income_report_period", None) != period:
            family.income_report_period = period
            family.income_report_by_source = {}
        if not isinstance(getattr(family, "income_report_by_source", None), dict):
            family.income_report_by_source = {}
        source_key = str(source or "Other")
        family.income_report_by_source[source_key] = max(
            0, int(family.income_report_by_source.get(source_key, 0))
        ) + amount
        family.income_report_last_day = max(1, int(day_number or 1))
        return True

    @classmethod
    def get_report(cls, market, day_number=1):
        period = cls._ensure_period(market, day_number)
        days = max(1, int(MARKET_SALES_REPORT_PERIOD_DAYS))
        return {
            "period": period,
            "start_day": period * days + 1,
            "end_day": (period + 1) * days,
            "items": dict(getattr(market, "sales_report_by_item", {})),
        }

    @classmethod
    def get_household_report(cls, building_manager, family_id, day_number=1, villager_manager=None):
        """Aggregate market sales and other recorded income in the current household period."""
        days = max(1, int(MARKET_SALES_REPORT_PERIOD_DAYS))
        period = cls._period(day_number)
        report = {
            "period": period,
            "start_day": period * days + 1,
            "end_day": (period + 1) * days,
            "revenue_copper": 0,
            "items": {},
        }
        if not building_manager or family_id is None:
            return report

        family_key = str(family_id)
        for market in getattr(building_manager, "buildings", []):
            if getattr(market, "building_type", None) != "market":
                continue
            assigned_family = (getattr(market, "assigned_household_id", None)
                               or getattr(market, "assigned_family_id", None))
            if str(assigned_family) != family_key:
                continue
            stall_report = cls.get_report(market, day_number)
            for item_name, item_sales in stall_report["items"].items():
                item = report["items"].setdefault(item_name, {"quantity": 0, "revenue_copper": 0})
                item["quantity"] += int(item_sales.get("quantity", 0))
                item["revenue_copper"] += int(item_sales.get("revenue_copper", 0))
                report["revenue_copper"] += int(item_sales.get("revenue_copper", 0))
        family = (villager_manager.get_family_by_id(family_id)
                  if villager_manager else None)
        if family:
            if getattr(family, "income_report_period", None) != period:
                family.income_report_period = period
                family.income_report_by_source = {}
            for source, amount in getattr(family, "income_report_by_source", {}).items():
                value = max(0, int(amount))
                report["revenue_copper"] += value
                report["items"][source] = {
                    "quantity": 0,
                    "revenue_copper": value,
                }
        return report
