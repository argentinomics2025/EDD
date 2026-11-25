"""EC-021 Etapa 3: automated risk-country ingestion remains DISABLED.

The displayed EMBI/J.P. Morgan values from third parties are not licensed for
automatic commercial redistribution in Economia Criolla. No DB write path.
"""
class RiskCountryLicenseBlocked(RuntimeError):
    pass


def run():
    raise RiskCountryLicenseBlocked(
        "NO APTO: verify commercial rights to EMBI/J.P. Morgan and official methodology "
        "before any automatic ingestion or historical change"
    )


if __name__ == "__main__":
    run()
