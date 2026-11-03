import unittest
from datetime import datetime, timedelta, timezone
from scripts.gate_calidad_bonos_ec0073 import BASE,TICKERS,evaluate,decimal_strict,InvalidQuote
T=datetime(2026,11,3,19,0,tzinfo=timezone.utc)

def row(t):
    return {'ticker':t,'currency':'USD' if t.endswith('D') else 'ARS',
            'unit':'per_100_vno','precio':'53.3700', 'var_dia':'-0.07',
            'var_mes':'-0.41', 'var_ano':'18.37',
            'source_asof':T,'source_record_id':t+'-20261103'}

def check(rows=None,**kwargs):
    args=dict(source='Rava',source_timestamp=T,ingested_at=T+timedelta(minutes=3),
              market_status='TRADING',coverage_policy_approved=True,
              contract_schedule_verified=True,redistribution_permission_verified=True,
              settlement_verified=True,currency_conversion_verified=True)
    args.update(kwargs)
    return evaluate([row(x) for x in TICKERS] if rows is None else rows,**args)

class QualityGateTests(unittest.TestCase):
    def test_full_lot_never_authorizes_write_without_dec003(self):
        x=check();self.assertEqual(x.status,'QUARANTINE');self.assertFalse(x.eligible_for_write)
        self.assertEqual(x.quote_count,18);self.assertIn('dec003_historical_write_policy_pending',x.reasons)
    def test_18_distinct(self):self.assertEqual(len(TICKERS),18)
    def test_one_ticker_not_accepted(self):self.assertIn('full_coverage_not_demonstrated',check([row('AL30D')]).reasons)
    def test_partial_still_quarantined(self):self.assertFalse(check([row(x) for x in list(TICKERS)[:17]]).eligible_for_write)
    def test_duplicate(self):self.assertIn('duplicate_ticker',check([row('AL30D'),row('AL30D')]).reasons)
    def test_extra_ticker(self):self.assertIn('unknown_ticker',check([row('XYZ')]).reasons)
    def test_empty_trading(self):self.assertIn('empty_not_evidence_of_holiday',check([]).reasons)
    def test_empty_unknown(self):self.assertIn('empty_not_evidence_of_holiday',check([],market_status='UNVERIFIED').reasons)
    def test_empty_holiday_with_evidence(self):
        x=check([],market_status='NO_TRADING',market_calendar_evidence=True)
        self.assertEqual(x.status,'NO_TRADING_DOCUMENTED');self.assertFalse(x.eligible_for_write)
    def test_empty_holiday_without_evidence(self):self.assertIn('missing_official_calendar_evidence',check([],market_status='NO_TRADING').reasons)
    def test_quotes_on_holiday(self):self.assertIn('quotes_on_verified_non_trading_day',check([row('AL30D')],market_status='NO_TRADING',market_calendar_evidence=True).reasons)
    def test_ambiguous_thousands(self):
        bad=row('AL30D');bad['precio']='53,370';self.assertIn('precio_numeric_format_unverified',check([bad]).reasons)
    def test_ambiguous_ARS(self):
        bad=row('AL30');bad['precio']='83.140,00';self.assertIn('precio_numeric_format_unverified',check([bad]).reasons)
    def test_non_positive(self):
        bad=row('AL30D');bad['precio']='0';self.assertIn('non_positive_price',check([bad]).reasons)
    def test_wrong_currency(self):
        bad=row('AL30');bad['currency']='USD';self.assertIn('currency_mismatch',check([bad]).reasons)
    def test_wrong_unit(self):
        bad=row('AL30D');bad['unit']='per_vno';self.assertIn('unit_not_declared',check([bad]).reasons)
    def test_missing_source_id(self):
        bad=row('AL30D');bad.pop('source_record_id');self.assertIn('missing_source_record_id',check([bad]).reasons)
    def test_missing_asof(self):
        bad=row('AL30D');bad.pop('source_asof');self.assertIn('per_quote_source_time_not_verified',check([bad]).reasons)
    def test_naive_source_timestamp(self):self.assertIn('source_timestamp_missing_or_naive',check(source_timestamp=T.replace(tzinfo=None)).reasons)
    def test_future_source_timestamp(self):self.assertIn('source_timestamp_in_future',check(source_timestamp=T+timedelta(days=1)).reasons)
    def test_old_timestamp(self):self.assertIn('unverified_stale_quote',check(ingested_at=T+timedelta(days=2)).reasons)
    def test_unverified_analytics(self):
        bad=row('AL30D');bad['tir']='11.95';self.assertIn('unverified_analytics_present',check([bad]).reasons)
    def test_missing_redistribution_permission(self):self.assertIn('permission_not_verified',check(redistribution_permission_verified=False).reasons)
    def test_unapproved_coverage_policy(self):self.assertIn('coverage_policy_not_approved',check(coverage_policy_approved=False).reasons)
    def test_missing_contract_schedule(self):self.assertIn('cashflows_not_verified_for_all_instruments',check(contract_schedule_verified=False).reasons)
    def test_unverified_settlement(self):self.assertIn('settlement_convention_not_verified',check(settlement_verified=False).reasons)
    def test_missing_fx(self):self.assertIn('ars_usd_valuation_not_verified',check(currency_conversion_verified=False).reasons)
    def test_pure_decimal(self):self.assertEqual(decimal_strict('53.3700'),decimal_strict('53.37'))
    def test_bad_number(self):
        for x in ('','NaN','1,000','1.000,50','$50','50%','1e4'):
            with self.subTest(value=x),self.assertRaises(InvalidQuote):decimal_strict(x)

if __name__=='__main__':unittest.main()