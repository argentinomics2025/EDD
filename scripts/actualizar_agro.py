"""EC-021: retired legacy Agro robot. Retained in Git history for audit.

The former script fetched unlicensed Yahoo grain futures, scraped unstructured
Rosario HTML, fabricated an FX rate of ARS 1050 when the source failed, used
today's date instead of a publication date, and performed destructive
DELETE+INSERT with shared database credentials.
Never invoke it to populate production. The archive in Git is the original.
"""

def run() -> None:
    raise RuntimeError(
        "EC021_AGRO_LEGACY_DISABLED: fuente y fechas no verificadas; "
        "fallback cambiario ficticio, credencial compartida y DELETE+INSERT inseguro. "
        "Datos historicos preservados; usar fuente oficial validada y escritor acotado."
    )


if __name__ == "__main__":
    run()
