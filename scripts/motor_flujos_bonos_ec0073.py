"""Motor EC-007.3 offline de TIR y duration. No aporta cronogramas ni precios reales.
Sólo ejecuta si el llamador acredita el calendario contractual y el precio dirty,
en moneda de pago y a fecha de liquidación validada. No conecta a Supabase.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

BASE = Decimal("365")

@dataclass(frozen=True)
class Flow:
    date: date
    amount: Decimal

@dataclass(frozen=True)
class Result:
    ytm_annual_effective: Decimal
    macaulay_years: Decimal
    modified_years: Decimal
    present_value: Decimal
    method: str = "annual_effective_ACT_365_dirty"

def dec(v):
    if isinstance(v, bool):
        raise ValueError("boolean_as_amount")
    try:
        x = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_decimal") from exc
    if not x.is_finite():
        raise ValueError("nonfinite_decimal")
    return x

def present_value(flows, settlement, annual_rate):
    rate = dec(annual_rate)
    if rate <= Decimal("-1"):
        raise ValueError("rate_outside_domain")
    return sum((dec(f.amount)/(1+rate)**(Decimal((f.date-settlement).days)/BASE)
                for f in flows), Decimal(0))

def calculate(flows, settlement, dirty_price, *, schedule_verified=False,
              denomination="USD", price_currency="USD", price_basis="dirty"):
    if not schedule_verified:
        raise ValueError("unverified_contract_schedule")
    if price_basis != "dirty":
        raise ValueError("clean_price_requires_accrued_interest")
    if denomination != price_currency:
        raise ValueError("mismatched_cashflow_and_price_currency")
    p = dec(dirty_price)
    if p <= 0:
        raise ValueError("nonpositive_price")
    if not isinstance(settlement,date):
        raise ValueError("settlement_required")
    if not flows:
        raise ValueError("missing_cashflows")
    prev = settlement
    for f in flows:
        if not isinstance(f.date, date) or f.date <= prev:
            raise ValueError("flow_dates_not_strictly_increasing_after_settlement")
        if dec(f.amount) <= 0:
            raise ValueError("nonpositive_flow")
        prev = f.date
    low, high = Decimal("-0.999"), Decimal("1")
    for _ in range(20):
        if present_value(flows, settlement, low) >= p:
            break
        low = (low-1)/2
    else:
        raise ValueError("rate_not_bracketed_below")
    for _ in range(20):
        if present_value(flows, settlement, high) <= p:
            break
        high = high*2+1
    else:
        raise ValueError("rate_not_bracketed_above")
    for _ in range(100):
        mid=(low+high)/2
        if present_value(flows,settlement,mid)>p:
            low=mid
        else:
            high=mid
    ytm=(low+high)/2
    terms=[(Decimal((f.date-settlement).days)/BASE,
            dec(f.amount)/(1+ytm)**(Decimal((f.date-settlement).days)/BASE))
           for f in flows]
    pv=sum((v for _,v in terms),Decimal(0))
    macaulay=sum((t*v for t,v in terms),Decimal(0))/pv
    return Result(ytm,macaulay,macaulay/(1+ytm),pv)
