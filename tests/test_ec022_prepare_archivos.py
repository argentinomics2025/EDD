import hashlib
import unittest
from unittest.mock import patch
from scripts.ec022_prepare_archivos import manifest

class SourceManifestTests(unittest.TestCase):
    def test_ipc_level_and_missing_change_are_distinct(self):
        raw=b'fixture'
        data={'source':'https://www.indec.gob.ar/test','sha256':hashlib.sha256(raw).hexdigest(),
              'observations':[{'date':'2020-01-01','index':'100','monthly_percent':None},
                              {'date':'2020-02-01','index':'102','monthly_percent':'2'}]}
        with patch('scripts.ec022_prepare_archivos.parse_ipc',return_value=data):
            out=manifest('ipc',raw,'2020-03-01T10:00:00+00:00')
        self.assertEqual(len(out['observations']),3)
        self.assertEqual(out['observations'][-1]['series'],'indec_ipc_nacional_variacion_mensual')
        self.assertIsNone(out['publication_date'])

    def test_does_not_accept_unknown_kind(self):
        with self.assertRaises(ValueError): manifest('unknown',b'','2020-03-01T10:00:00+00:00')

    def test_rejects_future_retrieval(self):
        with self.assertRaises(ValueError): manifest('ipc',b'','9999-03-01T10:00:00+00:00')
