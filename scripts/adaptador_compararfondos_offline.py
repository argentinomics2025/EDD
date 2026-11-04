"""EC0073: contrato offline de lectura para /api/bonos de CompararFondos.

No realiza HTTP, no persiste, nunca autoriza publicar ni escribir.
Los campos están basados en documentación pública, NO en JSON real verificado.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

BASE = ('AL29','AL30','AL35','AE38','GD29','GD30','GD35','GD38','GD41')
TICKERS = frozenset(BASE+tuple(x+'D' for x in BASE))

@dataclass(frozen=True)
class Outcome:
    status: str
    observations: tuple
    reasons: tuple
    missing: tuple
    eligible_for_write: bool = False
    eligible_for_publication: bool = False

def numeric(val):
    if isinstance(val,bool) or val is None:
        raise ValueError('numeric_missing')
    try:
        d=Decimal(str(val))
    except (ValueError, InvalidOperation, TypeError) as e:
        raise ValueError('numeric_invalid') from e
    if not d.is_finite() or d <= 0:
        raise ValueError('numeric_not_positive')
    return format(d,'f')

def contract_check(payload):
    """Diagnóstico QUARANTINE: precioARS nativo, no conversión MEP inferida."""
    if not isinstance(payload,dict) or not isinstance(payload.get('bonds'),list):
        return Outcome('QUARANTINE',(),('invalid_payload_contract',),tuple(sorted(TICKERS)))
    reasons={'third_party_byma_redistribution_not_cleared','not_live_provider_verified',
             'dec003_production_write_policy_pending','no_publishing_approval'}
    wheel=payload.get('rueda')
    settlement=None
    asof=None
    if not isinstance(wheel,dict):
        reasons.add('missing_wheel')
    else:
        for key in ('fechaRueda','liquidacion'):
            try:
                raw=wheel[key]
                if not isinstance(raw,str):
                    raise ValueError()
                date.fromisoformat(raw)
                if key=='fechaRueda':
                    asof=raw
                else:
                    settlement=raw
            except (KeyError,ValueError,TypeError):
                reasons.add('missing_or_invalid_'+key)
        if wheel.get('abierta') not in (True,False):
            reasons.add('market_open_state_unknown')
    rows=[]
    seen=set()
    for bond in payload['bonds']:
        if not isinstance(bond,dict):
            reasons.add('malformed_bond')
            continue
        ticker=bond.get('ticker')
        if not isinstance(ticker,str) or ticker.strip().upper() not in TICKERS:
            continue
        ticker=ticker.strip().upper()
        if ticker in seen:
            reasons.add('duplicate_ticker')
            continue
        seen.add(ticker)
        expected_type='MEP' if ticker.endswith('D') else 'ARS'
        if bond.get('tcType')!=expected_type:
            reasons.add('unexpected_tc_type_'+ticker)
            continue
        if bond.get('precioStale') is not False or bond.get('operaciones')==0:
            reasons.add('stale_or_unverified_operations_'+ticker)
            continue
        raw=bond.get('precio') if expected_type=='MEP' else bond.get('precioARS')
        try:
            price=numeric(raw)
        except ValueError:
            reasons.add('missing_price_native_currency_'+ticker)
            continue
        if asof is None or settlement is None:
            reasons.add('date_context_incomplete_'+ticker)
            continue
        rows.append({'ticker':ticker,'source':'compararfondos.com.ar',
                     'source_market':'BYMA_via_data912_unlicensed',
                     'price':price,'price_currency':'USD' if expected_type=='MEP' else 'ARS',
                     'market_date':asof,'settlement_date':settlement,
                     'price_type':'UNVERIFIED_CLEAN_DIRTY',
                     'price_unit':'UNVERIFIED_PER_NOMINAL',
                     'quote_timestamp':'UNVERIFIED_INTRADAY',
                     'publication_permitted':False})
    missing=tuple(sorted(TICKERS-seen))
    if missing:
        reasons.add('incomplete_universe')
    if len(rows)!=len(TICKERS):
        reasons.add('incomplete_valid_observations')
    return Outcome('QUARANTINE',tuple(rows),tuple(sorted(reasons)),missing)
