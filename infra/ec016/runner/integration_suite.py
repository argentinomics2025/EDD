"""Future real PostgreSQL/PostgREST tests. NOT part of default local discovery.

Never import publication robots or patch their unconditional write lock.
The explicit opt-in runs only inside compose's private lab network.
"""
from concurrent.futures import ThreadPoolExecutor
import time
import unittest

from .lab_guard import (TABLES, MARKER, runtime_context, admin_connection, api_client)
from . import policy

KEYS={'datos_comex':'fecha','socios_comerciales':'fecha_informe,pais',
      'comex_rubros':'fecha_informe,tipo_flujo,rubro_principal,subrubro'}


def payload(table, value=10, fresh=False):
    if table=='datos_comex':
        return {'fecha':'2010-02-01' if fresh else '2010-01-01',
                'exportaciones_usd_millions':value,'importaciones_usd_millions':2,
                'saldo_usd_millions':value-2}
    if table=='socios_comerciales':
        return {'fecha_informe':'Febrero 2010' if fresh else 'Enero 2010','pais':'Brasil',
                'exportaciones':value,'importaciones':2,'saldo_comercial':value-2}
    return {'fecha_informe':'Febrero 2010' if fresh else 'Enero 2010','tipo_flujo':'Importacion',
            'rubro_principal':'Resto','subrubro':'TOTAL','valor_usd':value}


def insert(client,table,rows):
    # Intended robot HTTP contract, invoked directly through the real test SDK.
    # This does not call or unlock ica_common.persist/publish.
    return client.from_(table).upsert(rows,on_conflict=KEYS[table],ignore_duplicates=True).execute()


class DisposableIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest=runtime_context()
        last=None
        for attempt in range(30):
            try:
                connection=admin_connection();connection.close()
                client,_=api_client(anonymous=True)
                try:
                    rows=client.from_('ec016_metadata').select('*').execute().data
                    if len(rows)!=1:raise RuntimeError('Wrong API identity')
                    policy.validate_marker_payload({'scope':rows[0]['value'],'run_id':rows[0]['run_id'],
                                                   'owner_token':rows[0]['owner_token']},manifest)
                finally:client.session.close()
                return
            except Exception as exc:
                last=exc
                time.sleep(1)
        raise RuntimeError('Disposable services did not become ready') from last

    def setUp(self):
        self.admin=admin_connection();self.addCleanup(self.admin.close)
        # Constant table list, fixed DB and marker checked on this connection.
        self.admin.execute('TRUNCATE api.datos_comex,api.socios_comerciales,api.comex_rubros,api.no_unique_fixture,lab_private.audit_log RESTART IDENTITY')
        self.client,self.transport=api_client();self.addCleanup(self.client.session.close)

    def assert_api_code(self, code, category=None):
        from contextlib import contextmanager
        from postgrest.exceptions import APIError
        @contextmanager
        def expected():
            with self.assertRaises(APIError) as caught:
                yield
            policy.require_error_code(caught.exception,code,category)
        return expected()

    def snapshot(self):
        # Text JSON from PostgreSQL preserves numeric spelling without Python floats.
        return {table:self.admin.execute('SELECT to_jsonb(t)::text FROM '+table+' t ORDER BY to_jsonb(t)::text').fetchall()
                for table in (*('api.'+t for t in TABLES),'api.no_unique_fixture','lab_private.audit_log')}

    def test_history_replay_and_omitted_columns(self):
        for table in TABLES:
            row=payload(table);row['review_note']='non-default-original-history'
            insert(self.client,table,[row])
        before=self.snapshot()
        for table in TABLES:
            insert(self.client,table,[payload(table,999)])
        self.assertEqual(self.snapshot(),before)
        for table in TABLES:
            self.assertEqual(self.admin.execute('SELECT review_note FROM api.'+table).fetchone()[0],'non-default-original-history')
            insert(self.client,table,[payload(table,10,True)])
            self.assertEqual(self.admin.execute('SELECT count(*) FROM api.'+table).fetchone()[0],2)

    def test_atomic_failure_and_audit_rollback(self):
        from postgrest.exceptions import APIError
        for table in TABLES:
            before=self.snapshot()
            valid=payload(table)
            invalid=payload(table,-1,True)
            with self.assert_api_code('23514'):insert(self.client,table,[valid,invalid])
            self.assertEqual(self.snapshot(),before)

    def test_missing_unique_target_is_error_not_delete(self):
        from postgrest.exceptions import APIError
        before=self.snapshot()
        with self.assert_api_code('42P10'):
            self.client.from_('no_unique_fixture').upsert([{'fecha':'2010-01-01','value':3}],on_conflict='fecha',ignore_duplicates=True).execute()
        self.assertEqual(self.snapshot(),before)

    def test_null_keys_and_partial_country_are_rejected(self):
        from postgrest.exceptions import APIError
        for table in TABLES:
            row=payload(table);row[KEYS[table].split(',')[0]]=None
            before=self.snapshot()
            with self.assert_api_code('23502'):insert(self.client,table,[row])
            self.assertEqual(self.snapshot(),before)
        row=payload('socios_comerciales');del row['importaciones'];del row['saldo_comercial']
        before=self.snapshot()
        with self.assert_api_code('23502'):insert(self.client,'socios_comerciales',[row])
        self.assertEqual(self.snapshot(),before)

    def test_normalized_collision_aborts_request(self):
        from postgrest.exceptions import APIError
        insert(self.client,'socios_comerciales',[payload('socios_comerciales')])
        row=payload('socios_comerciales');row['pais']=' BRÁSIL '
        before=self.snapshot()
        with self.assert_api_code('23505'):insert(self.client,'socios_comerciales',[row])
        self.assertEqual(self.snapshot(),before)

    def test_rls_scope_reader_and_mutation_denials(self):
        from postgrest.exceptions import APIError
        for role,scope,anonymous in [('ec016_writer','wrong',False),('ec016_reader','synthetic',False),('ec016_reader','synthetic',True)]:
            client,_=api_client(role,scope,anonymous)
            try:
                before=self.snapshot()
                with self.assert_api_code('42501','rls' if role=='ec016_writer' else 'permission'):insert(client,'datos_comex',[payload('datos_comex')])
                self.assertEqual(self.snapshot(),before)
            finally:client.session.close()
        insert(self.client,'datos_comex',[payload('datos_comex')]);before=self.snapshot()
        with self.assert_api_code('42501','permission'):self.client.from_('datos_comex').update({'saldo_usd_millions':999}).eq('fecha','2010-01-01').execute()
        with self.assert_api_code('42501','permission'):self.client.from_('datos_comex').delete().eq('fecha','2010-01-01').execute()
        self.assertEqual(self.snapshot(),before)

    def test_response_lost_after_commit_is_idempotent(self):
        import httpx
        for table in TABLES:
            self.transport.drop_next_post_response=True
            with self.assertRaises(httpx.ReadTimeout):insert(self.client,table,[payload(table)])
            after_commit=self.snapshot()
            insert(self.client,table,[payload(table)])
            self.assertEqual(self.snapshot(),after_commit)
            self.assertEqual(self.admin.execute('SELECT count(*) FROM api.'+table).fetchone()[0],1)

    def test_concurrent_competing_payloads_first_insert_wins(self):
        def worker(table,value):
            client,_=api_client()
            try:insert(client,table,[payload(table,value)])
            finally:client.session.close()
        for table in TABLES:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures=[workers.submit(worker,table,value) for value in [10,20]]
                for future in futures:future.result()
            self.assertEqual(self.admin.execute('SELECT count(*) FROM api.'+table).fetchone()[0],1)
            field='valor_usd' if table=='comex_rubros' else ('exportaciones' if table=='socios_comerciales' else 'exportaciones_usd_millions')
            self.assertIn(self.admin.execute('SELECT '+field+' FROM api.'+table).fetchone()[0],(10,20))
        self.assertEqual(self.admin.execute('SELECT count(*) FROM lab_private.audit_log').fetchone()[0],3)

    def test_numeric_roundtrip_and_trigger_transaction(self):
        from decimal import Decimal
        row=payload('comex_rubros');row['valor_usd']=10.12345678
        insert(self.client,'comex_rubros',[row])
        actual=self.admin.execute('SELECT valor_usd::text FROM api.comex_rubros').fetchone()[0]
        self.assertEqual(Decimal(actual),Decimal(str(row['valor_usd'])))
        before=self.snapshot()
        import psycopg
        with self.assertRaises(psycopg.Error) as caught:
            self.admin.execute("UPDATE api.comex_rubros SET valor_usd=100")
        self.assertEqual(caught.exception.sqlstate,'P0001')
        self.assertIn('EC016 history is append-only',str(caught.exception))
        self.assertEqual(self.snapshot(),before)

    def test_identity_algorithm_corpus(self):
        corpus={' BRÁSIL ':'brasil', '\tBrasil\t':'brasil', 'Viet Nam':'vietnam',
                'Estados Unidos de América':'estados unidos', 'Estados   Unidos':'estados unidos',
                'Países Bajos':'paises bajos', 'Congo':'congo',
                'República Democrática del Congo':'republica democratica del congo'}
        for source,expected in corpus.items():
            actual=self.admin.execute('SELECT lab_private.country_key(%s)',(source,)).fetchone()[0]
            self.assertEqual(actual,expected)

    def test_exact_concurrent_payload(self):
        for table in TABLES:
            def worker():
                client,_=api_client()
                try:insert(client,table,[payload(table)])
                finally:client.session.close()
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures=[workers.submit(worker) for _ in range(2)]
                for future in futures:future.result()
            self.assertEqual(self.admin.execute('SELECT count(*) FROM api.'+table).fetchone()[0],1)
        self.assertEqual(self.admin.execute('SELECT count(*) FROM lab_private.audit_log').fetchone()[0],3)


if __name__=='__main__':unittest.main()
