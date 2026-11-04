import unittest
from datetime import date
from decimal import Decimal
from scripts.motor_flujos_bonos_ec0073 import Flow,calculate,present_value

AT=date(2026,11,3)
AL30=[Flow(date(y,m,d),Decimal(str(a))) for y,m,d,a in [
(2027,1,9,8.24),(2027,7,9,8.21),(2028,1,9,8.42),(2028,7,9,8.35),
(2029,1,9,8.28),(2029,7,9,8.21),(2030,1,9,8.14),(2030,7,9,8.07)]]

class MotorTests(unittest.TestCase):
    def calc(self,flows=AL30,settlement=AT,price="53.37",**kw):
        return calculate(flows,settlement,price,schedule_verified=True,**kw)
    def test_price(self):self.assertLess(abs(self.calc().present_value-Decimal("53.37")),Decimal("1e-8"))
    def test_tir_range(self):self.assertTrue(Decimal(".119")<self.calc().ytm_annual_effective<Decimal(".123"))
    def test_duration_range(self):self.assertTrue(Decimal("1.57")<self.calc().modified_years<Decimal("1.60"))
    def test_larueda_same_cut_yield(self):
        self.assertLess(abs(self.calc(settlement=date(2026,11,2),price="53.41").ytm_annual_effective*100-Decimal("12.04")),Decimal(".03"))
    def test_larueda_same_cut_duration(self):
        self.assertLess(abs(self.calc(settlement=date(2026,11,2),price="53.41").modified_years-Decimal("1.59")),Decimal(".01"))
    def test_modified_identity(self):
        r=self.calc();self.assertLess(abs(r.modified_years*(1+r.ytm_annual_effective)-r.macaulay_years),Decimal("1e-8"))
    def test_higher_price_lower_yield(self):self.assertLess(self.calc(price="55").ytm_annual_effective,self.calc().ytm_annual_effective)
    def test_zero_coupon(self):
        r=self.calc(flows=[Flow(date(2027,11,3),Decimal("100"))],price="90")
        self.assertLess(abs(r.ytm_annual_effective-Decimal("100")/90+1),Decimal(".0005"))
    def test_negative_yield(self):self.assertLess(self.calc(flows=[Flow(date(2027,11,3),Decimal("100"))],price="110").ytm_annual_effective,0)
    def test_requires_contract(self):
        with self.assertRaises(ValueError):calculate(AL30,AT,"53.37")
    def test_reject_clean(self):
        with self.assertRaises(ValueError):self.calc(price_basis="clean")
    def test_reject_mismatch(self):
        with self.assertRaises(ValueError):self.calc(price_currency="ARS")
    def test_reject_zero(self):
        with self.assertRaises(ValueError):self.calc(price="0")
    def test_reject_nan(self):
        with self.assertRaises(ValueError):self.calc(price="NaN")
    def test_missing_flows(self):
        with self.assertRaises(ValueError):self.calc(flows=[])
    def test_expired(self):
        with self.assertRaises(ValueError):self.calc(flows=[Flow(AT,Decimal("10"))])
    def test_duplicate(self):
        with self.assertRaises(ValueError):self.calc(flows=[AL30[0],AL30[0]])
    def test_bad_flow(self):
        with self.assertRaises(ValueError):self.calc(flows=[Flow(date(2027,1,9),Decimal("-1"))])
    def test_rate_domain(self):
        with self.assertRaises(ValueError):present_value(AL30,AT,"-1")
if __name__=="__main__":unittest.main()
