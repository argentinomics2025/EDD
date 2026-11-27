import hashlib
import unittest
from scripts.ec022_writer_draft import prepare

class WriterPreparationTests(unittest.TestCase):
    def manifest(self):
        return {'source_url':'https://www.indec.gob.ar/test', 'source_sha256':hashlib.sha256(b'official').hexdigest(),
                'retrieved_at':'2026-11-27T10:00:00Z','publication_date':None,
                'observations':[{'series':'IPC','period':'2026-10-01','value':'2.2'}]}
    def test_prepares_verified_hash(self):
        self.assertEqual(len(prepare(self.manifest(),b'official')),1)
    def test_rejects_changed_source(self):
        with self.assertRaises(ValueError): prepare(self.manifest(),b'different')
    def test_rejects_nonofficial_host(self):
        m=self.manifest();m['source_url']='https://example.test/file'
        with self.assertRaises(ValueError): prepare(m,b'official')
    def test_rejects_duplicate(self):
        m=self.manifest();m['observations'].append(dict(m['observations'][0]))
        with self.assertRaises(ValueError): prepare(m,b'official')
