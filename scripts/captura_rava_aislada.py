"""EC-007.3: adapter for supplied Rava HTML snapshots. Offline-only.

NO network, Selenium, Supabase, API credentials, scheduling, or publication.
This is a fixture-contract prototype, not a certified parser for the live Rava DOM.
Source timestamp and data units must be confirmed outside this module.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path

try:
    from scripts.gate_calidad_bonos_ec0073 import TICKERS, evaluate
except ModuleNotFoundError:  # direct script invocation within scripts/
    from gate_calidad_bonos_ec0073 import TICKERS, evaluate

HEADERS = ("Especie", "Último", "Var Día", "Var Mes", "Var Año")


class SnapshotError(ValueError):
    pass


class TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._table = []
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if self._depth == 1 and tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            if self._depth == 1:
                self.tables.append(self._table)
                self._table = None
            self._depth -= 1


def normalize_number(raw, *, positive=False):
    """Normalize unambiguous es-AR decimals; never guess an ambiguous unit."""
    s = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    s = s.removeprefix("US$").removeprefix("$").removesuffix("%")
    if re.fullmatch(r"[+-]?\d{1,3}\.\d{3}", s):
        raise SnapshotError("numeric_format_ambiguous")
    if re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+,\d{1,4}", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[+-]?\d+,\d{1,4}", s):
        s = s.replace(",", ".")
    elif not re.fullmatch(r"[+-]?(?:0|[1-9]\d*)(?:\.\d{1,4})?", s):
        raise SnapshotError("numeric_format_ambiguous")
    try:
        n = Decimal(s)
    except InvalidOperation as exc:
        raise SnapshotError("numeric_invalid") from exc
    if not n.is_finite() or (positive and n <= 0):
        raise SnapshotError("numeric_not_finite_or_nonpositive")
    return format(n, "f")


def read_snapshot(html, *, source_asof):
    """Extract only a table matching an exact documented fixture header contract."""
    if not isinstance(source_asof, datetime) or source_asof.tzinfo is None:
        raise SnapshotError("source_timestamp_required")
    p = TableReader()
    p.feed(html)
    matching = [t for t in p.tables if t and tuple(t[0][:5]) == HEADERS]
    if len(matching) != 1:
        raise SnapshotError("fixture_table_header_not_verified")
    rows = []
    for cells in matching[0][1:]:
        if len(cells) < 5:
            raise SnapshotError("incomplete_table_row")
        ticker = cells[0].strip().upper().replace(" ", "")
        if ticker not in TICKERS:
            continue
        values = [normalize_number(raw, positive=(i == 0)) for i, raw in enumerate(cells[1:5])]
        raw_identity = "|".join([ticker, source_asof.isoformat(), *cells[1:5]])
        rows.append({
            "ticker": ticker,
            "currency": "USD" if ticker.endswith("D") else "ARS",  # hypothesis, not market-unit certification
            "unit": "per_100_vno",  # hypothesis, must be verified against provider
            "precio": values[0],
            "var_dia": values[1],
            "var_mes": values[2],
            "var_ano": values[3],
            "source_asof": source_asof,
            "source_record_id": hashlib.sha256(raw_identity.encode("utf-8")).hexdigest(),
        })
    return rows


def diagnose(html, *, source_asof, captured_at):
    if not isinstance(captured_at, datetime) or captured_at.tzinfo is None:
        raise SnapshotError("capture_timestamp_required")
    rows = read_snapshot(html, source_asof=source_asof)
    decision = evaluate(rows, source="Rava", source_timestamp=source_asof,
                        ingested_at=captured_at, market_status="UNVERIFIED",
                        coverage_policy_approved=False, contract_schedule_verified=False,
                        redistribution_permission_verified=False, settlement_verified=False,
                        currency_conversion_verified=False)
    return {"source": "Rava", "fixture_contract_only": True,
            "record_count": len(rows), "tickers": sorted(r["ticker"] for r in rows),
            "quality_status": decision.status,
            "quality_reasons": list(decision.reasons),
            "eligible_for_write": decision.eligible_for_write}


def parse_aware(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ISO datetime with timezone required") from exc


def main(argv=None):
    p = argparse.ArgumentParser(description="Offline Rava fixture checker; writes nothing")
    p.add_argument("--html-file", type=Path, required=True)
    p.add_argument("--source-asof", type=parse_aware, required=True)
    p.add_argument("--captured-at", type=parse_aware, required=True)
    args = p.parse_args(argv)
    outcome = diagnose(args.html_file.read_text(encoding="utf-8"),
                       source_asof=args.source_asof, captured_at=args.captured_at)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0 if outcome["quality_status"] == "QUARANTINE" and not outcome["eligible_for_write"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
