import unittest
from unittest.mock import patch
import hashlib
from scripts.ec022_prepare_uva import prepare_manifest, AMOUNT_SERIES, RATE_SERIES

class UvaManifestTests(unittest.TestCase):
    def test_derives_values_and_does_not_publish_missing_rate(self):
        raw=b'source'
        source={'source':'https://www.bcra.gob.ar/test','sha256':hashlib.sha256(raw).hexdigest(),
                'observations':[{'date':'2020-01-01','amount_thousand_ars':'0','annual_nominal_rate_percent':'0','zero_amount_rate_not_interpreted':True},
                                {'date':'2020-02-01','amount_thousand_ars':'12','annual_nominal_rate_percent':'4.5','zero_amount_rate_not_interpreted':False}]}
        with patch('scripts.ec022_prepare_uva.parse',return_value=source):
            out=prepare_manifest(raw,'2026-11-27T12:30:00-03:00')
        self.assertEqual([r['series'] for r in out['observations']],[AMOUNT_SERIES,AMOUNT_SERIES,RATE_SERIES])
        self.assertIsNone(out['publication_date'])

    def test_requires_real_timezone(self):
        with self.assertRaises(ValueError): prepare_manifest(b'source','2026-11-27T12:30:00')
