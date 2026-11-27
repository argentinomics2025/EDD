"""EC-021: legacy energy writer deliberately retired.

The former implementation scraped Yahoo Finance futures and deleted all
same-day records before inserting replacements using shared credentials.
This entry point must never mutate production, even when invoked manually.
Historical rows remain available for read-only publication.
"""

def run() -> None:
    raise RuntimeError(
        "EC-021 ENERGIA_LEGACY_DISABLED: "
        "fuente Yahoo sin permiso de redistribucion acreditado; "
        "escritura DELETE+INSERT no atomica y credencial compartida. "
        "Utilizar el nuevo proceso validado solo tras homologar fuente y rol exclusivo."
    )


if __name__ == "__main__":
    run()
