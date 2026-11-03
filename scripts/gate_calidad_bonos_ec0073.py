"""EC-007.3. Control OFFLINE de calidad y procedencia de cotizaciones de bonos.

No tiene credenciales, llamadas HTTP ni persistencia. Decisión por defecto: CUARENTENA.
No calcula TIR/duration; sus valores productivos no están homologados.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Iterable
import re

BASE = ('AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41')
TICKERS = frozenset(BASE + tuple(x+'D' for x in BASE))
FIELDS = ('precio', 'var_dia', 'var_mes', 'var_ano')

@dataclass(frozen=True)
class GateResult:
    status: str
    reasons: tuple[str, ...]
    observed_tickers: tuple[str, ...]
    absent_tickers: tuple[str, ...]
    quote_count: int
    eligible_for_write: bool = False

class InvalidQuote(ValueError):
    pass

def decimal_strict(raw):
    """Sólo decimal sin separadores de miles; signo opcional, hasta 4 decimales.

    El adaptador de fuente debe declarar unidad, locale y normalizar antes de llamar.
    """
    if not isinstance(raw, str) or not re.fullmatch(r'[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?', raw):
        raise InvalidQuote('numeric_format_unverified')
    try:
        x = Decimal(raw)
    except InvalidOperation as e:
        raise InvalidQuote('numeric_format_unverified') from e
    if not x.is_finite():
        raise InvalidQuote('non_finite_value')
    return x

def evaluate(rows: Iterable[Mapping], *, source, source_timestamp, ingested_at,
             coverage_policy_approved=False, contract_schedule_verified=False,
             market_status='UNVERIFIED', market_calendar_evidence=False,
             redistribution_permission_verified=False, settlement_verified=False,
             currency_conversion_verified=False):
    """Diagnóstico únicamente; la salida NUNCA da permiso de escritura.

    Mercado: TRADING, NO_TRADING, LIMITED, UNVERIFIED. La condición NO_TRADING
    sólo es válida con evidencia de calendario; una página sin datos no prueba feriado.
    """
    reasons = set()
    rows = list(rows)
    if source != 'Rava':
        reasons.add('source_not_in_inventory')
    if not redistribution_permission_verified:
        reasons.add('permission_not_verified')
    if not coverage_policy_approved:
        reasons.add('coverage_policy_not_approved')
    if not contract_schedule_verified:
        reasons.add('cashflows_not_verified_for_all_instruments')
    if not settlement_verified:
        reasons.add('settlement_convention_not_verified')
    if not currency_conversion_verified:
        reasons.add('ars_usd_valuation_not_verified')

    if not isinstance(source_timestamp, datetime) or source_timestamp.tzinfo is None:
        reasons.add('source_timestamp_missing_or_naive')
    if not isinstance(ingested_at, datetime) or ingested_at.tzinfo is None:
        reasons.add('ingestion_timestamp_missing_or_naive')
    if (isinstance(source_timestamp, datetime) and source_timestamp.tzinfo is not None
        and isinstance(ingested_at, datetime) and ingested_at.tzinfo is not None):
        if source_timestamp > ingested_at:
            reasons.add('source_timestamp_in_future')
        if (ingested_at-source_timestamp).total_seconds() > 24*3600:
            reasons.add('unverified_stale_quote')

    if market_status not in ('TRADING', 'NO_TRADING', 'LIMITED', 'UNVERIFIED'):
        reasons.add('invalid_market_status')
    if market_status in ('NO_TRADING','LIMITED') and not market_calendar_evidence:
        reasons.add('missing_official_calendar_evidence')
    if market_status == 'UNVERIFIED':
        reasons.add('market_status_unverified')
    if market_status == 'NO_TRADING' and rows:
        reasons.add('quotes_on_verified_non_trading_day')
    if not rows and market_status != 'NO_TRADING':
        reasons.add('empty_not_evidence_of_holiday')

    tickers=[]
    for row in rows:
        ticker = str(row.get('ticker', '')).strip().upper()
        if ticker not in TICKERS:
            reasons.add('unknown_ticker')
            continue
        if ticker in tickers:
            reasons.add('duplicate_ticker')
        tickers.append(ticker)
        expected_currency = 'USD' if ticker.endswith('D') else 'ARS'
        if row.get('currency') != expected_currency:
            reasons.add('currency_mismatch')
        if row.get('unit') != 'per_100_vno':
            reasons.add('unit_not_declared')
        if row.get('source_asof') is None or row.get('source_asof') != source_timestamp:
            reasons.add('per_quote_source_time_not_verified')
        if not row.get('source_record_id'):
            reasons.add('missing_source_record_id')
        for field in FIELDS:
            try:
                n = decimal_strict(row.get(field))
                if field == 'precio' and n <= 0:
                    reasons.add('non_positive_price')
            except InvalidQuote as e:
                reasons.add(f'{field}_{e}')
        if row.get('tir') is not None or row.get('duration') is not None:
            reasons.add('unverified_analytics_present')
    missing=TICKERS.difference(tickers)
    if missing:
        reasons.add('missing_quotes_require_per_instrument_evidence')
    if len(tickers)!=len(TICKERS):
        reasons.add('full_coverage_not_demonstrated')
    if market_status == 'NO_TRADING' and not rows and market_calendar_evidence:
        status='NO_TRADING_DOCUMENTED'
    else:
        status='QUARANTINE'
    # Sin aprobación DEC-003 ni SDK de persistencia, ninguna escritura automática.
    reasons.add('dec003_historical_write_policy_pending')
    return GateResult(status,tuple(sorted(reasons)),tuple(sorted(set(tickers))),tuple(sorted(missing)),len(rows),False)