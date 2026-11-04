"""EC-007.3 immutable local fixture archive; NOT a market scraper or production storage.

Accepts explicit HTML file snapshots for OFFLINE analysis only. Stores a content-addressed
JSON manifest and normalized observations with quarantine status. Does not use network,
Supabase, credentials, or user market data unless a user explicitly supplies the file.

Important: a manually provided source_asof is NOT provider verification.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.captura_rava_aislada import read_snapshot, diagnose, parse_aware
except ModuleNotFoundError:
    from captura_rava_aislada import read_snapshot, diagnose, parse_aware


class ArchiveError(ValueError):
    pass


def archive_fixture(html, *, source_asof, captured_at, archive_dir, fixture_label):
    """Create immutable fixture JSON, or verify idempotent retry, without writing market DB.

    Returns (path, created). Fails closed before writing on unknown schema, conflicts,
    non-UTC-aware timestamps, invalid fixture ID or missing archive directory.
    """
    if not isinstance(html, str) or not isinstance(fixture_label, str):
        raise ArchiveError("invalid_fixture")
    if not fixture_label or len(fixture_label) > 80 or not all(
        x.isascii() and (x.isalnum() or x in "_-") for x in fixture_label
    ):
        raise ArchiveError("invalid_fixture_label")
    if not isinstance(source_asof, datetime) or source_asof.tzinfo is None:
        raise ArchiveError("source_timestamp_required")
    if not isinstance(captured_at, datetime) or captured_at.tzinfo is None:
        raise ArchiveError("capture_timestamp_required")
    if captured_at < source_asof:
        raise ArchiveError("capture_precedes_source")

    # Do not assume this data is licensed, accurate, or proven to originate from Rava.
    rows = read_snapshot(html, source_asof=source_asof)
    status = diagnose(html, source_asof=source_asof, captured_at=captured_at)
    if status["quality_status"] != "QUARANTINE" or status["eligible_for_write"]:
        raise ArchiveError("unexpected_gate_decision")
    observations = [{**r, "source_asof": r["source_asof"].astimezone(timezone.utc).isoformat()}
                    for r in rows]
    observations.sort(key=lambda r: (r["ticker"], r["source_record_id"]))
    html_sha256 = hashlib.sha256(html.encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "ec0073-fixture-v1",
        "fixture_label": fixture_label,
        "provider_claim": "Rava (unverified synthetic fixture)",
        "source_asof_claimed_utc": source_asof.astimezone(timezone.utc).isoformat(),
        "captured_at_utc": captured_at.astimezone(timezone.utc).isoformat(),
        "source_html_sha256": html_sha256,
        "source_html_stored": False,
        "license_verified": False,
        "source_timestamp_provider_verified": False,
        "unit_provider_verified": False,
        "currency_provider_verified": False,
        "publication_authorized": False,
        "eligible_for_write": False,
        "quality_status": status["quality_status"],
        "quality_reasons": status["quality_reasons"],
        "observations": observations,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    digest = hashlib.sha256(canonical).hexdigest()
    directory = Path(archive_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise ArchiveError("existing_nonsymlink_archive_directory_required")
    destination = directory / ("ec0073-" + digest + ".json")
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if destination.is_symlink() or destination.read_bytes() != canonical:
            raise ArchiveError("immutable_snapshot_conflict")
        return destination, False
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(canonical)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    return destination, True


def main(argv=None):
    p = argparse.ArgumentParser(description="Fixture-only immutable archive; no network or database")
    p.add_argument("--html-file", type=Path, required=True)
    p.add_argument("--source-asof", type=parse_aware, required=True)
    p.add_argument("--captured-at", type=parse_aware, required=True)
    p.add_argument("--archive-dir", type=Path, required=True)
    p.add_argument("--fixture-label", required=True)
    args = p.parse_args(argv)
    path, created = archive_fixture(args.html_file.read_text(encoding="utf-8"),
                                    source_asof=args.source_asof, captured_at=args.captured_at,
                                    archive_dir=args.archive_dir, fixture_label=args.fixture_label)
    print(json.dumps({"artifact_path": str(path), "created": created,
                      "publication_authorized": False, "eligible_for_write": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
