"""EC-007.3: safety regression. Even perfect synthetic coverage NEVER enables writes."""
import unittest
from datetime import datetime, timezone, timedelta
from scripts.gate_calidad_bonos_ec0073 import TICKERS, evaluate
NOW = datetime(2026, 11, 4, 14, tzinfo=timezone.utc)

def valid(t):
    return dict(ticker=t, currency="USD" if t.endswith("D") else "ARS",
                unit="per_100_vno", precio="53.37", var_dia="0.25",
                var_mes="2.00", var_ano="3.00", source_asof=NOW,
                source_record_id="fixture-"+t)

def diagnose(rows, **overrides):
    k=dict(source="Rava",source_timestamp=NOW,ingested_at=NOW+timedelta(minutes=1),
           coverage_policy_approved=True,contract_schedule_verified=True,
           market_status="TRADING",market_calendar_evidence=True,
           redistribution_permission_verified=True,settlement_verified=True,
           currency_conversion_verified=True)
    k.update(overrides)
    return evaluate(rows, **k)

class EditorialSafetyTests(unittest.TestCase):
    def test_full_coverage_and_all_claimed_approvals_cannot_write(self):
        result=diagnose([valid(t) for t in sorted(TICKERS)])
        self.assertEqual(result.quote_count,18)
        self.assertFalse(result.absent_tickers)
        self.assertFalse(result.eligible_for_write)
        self.assertEqual(result.status,"QUARANTINE")
        self.assertIn("dec003_historical_write_policy_pending",result.reasons)

    def test_verified_holiday_never_authorizes_storage(self):
        r=diagnose([],market_status="NO_TRADING")
        self.assertEqual(r.status,"NO_TRADING_DOCUMENTED")
        self.assertFalse(r.eligible_for_write)

    def test_incorrect_currency_and_unknown_unit_fail_closed(self):
        row=valid("AL30D")
        row.update(currency="ARS",unit="unknown")
        r=diagnose([row])
        self.assertFalse(r.eligible_for_write)
        self.assertIn("currency_mismatch",r.reasons)
        self.assertIn("unit_not_declared",r.reasons)

    def test_supplied_tir_and_duration_cannot_bypass_gate(self):
        row=valid("AL30D")
        row.update(tir="12.04",duration="1.59")
        r=diagnose([row])
        self.assertFalse(r.eligible_for_write)
        self.assertIn("unverified_analytics_present",r.reasons)

if __name__=="__main__":
    unittest.main()
