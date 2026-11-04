"""Pruebas offline del contrato de CompararFondos; sin HTTP ni permisos."""
import unittest
from scripts.adaptador_compararfondos_offline import contract_check,TICKERS

def payload():
    return {'rueda':{'fechaRueda':'2026-11-04','liquidacion':'2026-11-05','abierta':False},
            'bonds':[{'ticker':t,'tcType':'MEP' if t.endswith('D') else 'ARS',
                      'precio':55.5,'precioARS':110000.0,
                      'precioStale':False,'operaciones':1} for t in sorted(TICKERS)]}

class AdapterTests(unittest.TestCase):
    def test_full_coverage_quarantined(self):
        o=contract_check(payload())
        self.assertEqual(len(o.observations),18)
        self.assertEqual(o.status,'QUARANTINE')
        self.assertFalse(o.eligible_for_write)
        self.assertFalse(o.eligible_for_publication)
    def test_no_assumed_redistribution(self):
        self.assertIn('third_party_byma_redistribution_not_cleared',contract_check(payload()).reasons)
    def test_ars_uses_native_price(self):
        x=next(i for i in contract_check(payload()).observations if i['ticker']=='AL30')
        self.assertEqual((x['price'],x['price_currency']),('110000.0','ARS'))
    def test_dollar_uses_usd_price(self):
        x=next(i for i in contract_check(payload()).observations if i['ticker']=='AL30D')
        self.assertEqual((x['price'],x['price_currency']),('55.5','USD'))
    def test_zero_price_doesnt_pass(self):
        p=payload();next(x for x in p['bonds'] if x['ticker']=='AL30D')['precio']=0
        self.assertIn('missing_price_native_currency_AL30D',contract_check(p).reasons)
    def test_no_wheel(self):
        p=payload();del p['rueda']
        self.assertIn('missing_wheel',contract_check(p).reasons)
    def test_bad_settlement(self):
        p=payload();p['rueda']['liquidacion']='tomorrow'
        self.assertIn('missing_or_invalid_liquidacion',contract_check(p).reasons)
    def test_bad_date(self):
        p=payload();p['rueda']['fechaRueda']='2026-99-99'
        self.assertIn('missing_or_invalid_fechaRueda',contract_check(p).reasons)
    def test_missing_open_state(self):
        p=payload();del p['rueda']['abierta']
        self.assertIn('market_open_state_unknown',contract_check(p).reasons)
    def test_stale(self):
        p=payload();p['bonds'][0]['precioStale']=True
        self.assertIn('incomplete_valid_observations',contract_check(p).reasons)
    def test_zero_ops(self):
        p=payload();p['bonds'][0]['operaciones']=0
        self.assertIn('incomplete_valid_observations',contract_check(p).reasons)
    def test_missing_native_price(self):
        p=payload();next(x for x in p['bonds'] if x['ticker']=='AL30')['precioARS']=None
        self.assertIn('missing_price_native_currency_AL30',contract_check(p).reasons)
    def test_duplicate(self):
        p=payload();p['bonds'].append(p['bonds'][0].copy())
        self.assertIn('duplicate_ticker',contract_check(p).reasons)
    def test_wrong_tctype(self):
        p=payload();next(x for x in p['bonds'] if x['ticker']=='AL30')['tcType']='MEP'
        self.assertIn('unexpected_tc_type_AL30',contract_check(p).reasons)
    def test_missing_ticker(self):
        p=payload();p['bonds'].pop()
        self.assertEqual(len(contract_check(p).missing),1)
    def test_nan_price(self):
        p=payload();next(x for x in p['bonds'] if x['ticker']=='AL30D')['precio']=float('nan')
        self.assertIn('missing_price_native_currency_AL30D',contract_check(p).reasons)
    def test_invalid_contract(self):
        self.assertIn('invalid_payload_contract',contract_check({'bonds':{}}).reasons)

if __name__=='__main__':
    unittest.main()
