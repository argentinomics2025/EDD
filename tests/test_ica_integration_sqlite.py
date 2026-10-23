"""Local SQL adapter only; not a PostgreSQL/PostgREST integration test."""
import contextlib
import copy
from io import StringIO
import json
from pathlib import Path
import socket
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch
from scripts import ica_common as common, bot_ica_rubros as rubros, bot_ica as countries
import pandas as pd

TABLES = [
 ('datos_comex', ('fecha',), 'exportaciones_usd_millions', ('2026-01-01',)),
 ('socios_comerciales', ('fecha_informe','pais'), 'exportaciones', ('Enero 2026','Brasil')),
 ('comex_rubros', ('fecha_informe','tipo_flujo','rubro_principal','subrubro'), 'valor_usd', ('Enero 2026','Exportacion','PP','TOTAL')),
]
class SQLiteAdapter:
 def __init__(self, spec, unique=True):
  self.table_name,self.keys,self.amount,self.identity=spec
  self.db=sqlite3.connect(':memory:',isolation_level=None)
  cols=', '.join(f'"{k}" TEXT NOT NULL' for k in self.keys)
  constraint=', UNIQUE('+','.join(self.keys)+')' if unique else ''
  self.db.execute(f'CREATE TABLE {self.table_name} ({cols}, {self.amount} REAL CHECK ({self.amount}>=0), preserved TEXT DEFAULT \'keep\'{constraint})')
  self.fail_after_commit=False
 def table(self, name):
  assert name==self.table_name
  return self
 def upsert(self, rows, on_conflict, ignore_duplicates):
  assert ignore_duplicates is True
  self.rows=rows; self.conflict=on_conflict
  return self
 def execute(self):
  fields=list(self.rows[0]); assert all(set(r)==set(fields) for r in self.rows)
  columns=','.join(fields)
  values=','.join('('+','.join('?' for _ in fields)+')' for _ in self.rows)
  updates=','.join(f'{f}=excluded.{f}' for f in fields if f not in self.keys)
  sql=f'INSERT INTO {self.table_name} ({columns}) VALUES {values} ON CONFLICT ({self.conflict}) DO NOTHING'
  self.db.execute(sql,[r[f] for r in self.rows for f in fields])
  if self.fail_after_commit: raise TimeoutError('simulated lost response after commit')
 def snapshot(self):
  return self.db.execute(f'SELECT * FROM {self.table_name} ORDER BY '+','.join(self.keys)).fetchall()
 def row(self, value=10, identity=None):
  return dict(zip(self.keys,identity or self.identity)) | {self.amount:value}
 def close(self): self.db.close()

class Integration(unittest.TestCase):
 def setUp(self):
  gate=patch.object(common,'ensure_writes_verified');gate.start();self.addCleanup(gate.stop)
  self.net=patch('socket.socket.connect',side_effect=AssertionError('No network'));self.net.start();self.addCleanup(self.net.stop)
 def test_repeat_and_preserve(self):
  for spec in TABLES:
   with self.subTest(table=spec[0]):
    c=SQLiteAdapter(spec);self.addCleanup(c.close)
    common.persist(c,c.table_name,[c.row()],c.keys)
    snapshot=c.snapshot()
    common.persist(c,c.table_name,[c.row()],c.keys)
    self.assertEqual(c.snapshot(),snapshot)
    common.persist(c,c.table_name,[c.row(20)],c.keys)
    self.assertEqual(len(c.snapshot()),1);self.assertEqual(c.snapshot()[0][-1],'keep')
    self.assertEqual(c.snapshot()[0][-2],10)  # Existing history is not overwritten by 20.
 def test_constraint_failure_rolls_back_whole_statement(self):
  for spec in TABLES:
   with self.subTest(table=spec[0]):
    c=SQLiteAdapter(spec);self.addCleanup(c.close)
    common.persist(c,c.table_name,[c.row()],c.keys);snapshot=c.snapshot()
    other=list(c.identity);other[0]='2025-01-01' if c.keys[0]=='fecha' else 'Enero 2025'
    with self.assertRaises(sqlite3.IntegrityError):
     common.persist(c,c.table_name,[c.row(99,tuple(str(v)+'-new' for v in c.identity)),c.row(-1,other)],c.keys)
    self.assertEqual(c.snapshot(),snapshot)
 def test_other_period_preserved(self):
  for spec in TABLES:
   with self.subTest(table=spec[0]):
    c=SQLiteAdapter(spec);self.addCleanup(c.close)
    other=list(c.identity);other[0]='2025-01-01' if c.keys[0]=='fecha' else 'Enero 2025'
    common.persist(c,c.table_name,[c.row(7,other)],c.keys);old=c.snapshot()[0]
    common.persist(c,c.table_name,[c.row(10)],c.keys)
    self.assertIn(old,c.snapshot());self.assertEqual(len(c.snapshot()),2)
 def test_missing_unique_fails_without_change(self):
  for spec in TABLES:
   with self.subTest(table=spec[0]):
    c=SQLiteAdapter(spec,unique=False);self.addCleanup(c.close)
    row=c.row();cols=','.join(row);vals=','.join('?' for _ in row)
    c.db.execute(f'INSERT INTO {c.table_name} ({cols}) VALUES ({vals})',list(row.values()))
    snapshot=c.snapshot()
    with self.assertRaises(sqlite3.OperationalError): common.persist(c,c.table_name,[c.row(99)],c.keys)
    self.assertEqual(c.snapshot(),snapshot)
 def test_timeout_after_commit_replay(self):
  for spec in TABLES:
   with self.subTest(table=spec[0]):
    c=SQLiteAdapter(spec);self.addCleanup(c.close);c.fail_after_commit=True
    with self.assertRaises(TimeoutError): common.persist(c,c.table_name,[c.row()],c.keys)
    snapshot=c.snapshot();c.fail_after_commit=False
    common.persist(c,c.table_name,[c.row()],c.keys)
    self.assertEqual(c.snapshot(),snapshot);self.assertEqual(len(snapshot),1)
 def test_dry_run_never_uses_client(self):
  client=Mock()
  with contextlib.redirect_stdout(StringIO()):
   common.publish('datos_comex',[{'fecha':'2026-01-01','exportaciones_usd_millions':1}],('fecha',),client=client)
  self.assertEqual(client.mock_calls,[])
 def test_write_without_credentials_fails(self):
  with patch.dict('os.environ',{},clear=True):
   with self.assertRaises(ValueError): common.publish('datos_comex',[{'fecha':'2026-01-01'}],('fecha',),write=True, reviewed_sha256=common.payload_digest('datos_comex',[{'fecha':'2026-01-01'}],('fecha',)))

class SafetyRequirements(unittest.TestCase):
 def test_schedule_requires_explicit_authorization(self):
  text=(Path(__file__).resolve().parents[1] / '.github/workflows/bot_comex.yml').read_text()
  self.assertNotIn("github.event_name == 'schedule' || inputs.write",text,'Scheduled event unconditionally enables writes')
 def test_reject_incoherent_rubro(self):
  df=pd.DataFrame([
   ['Enero 2026 millones de dólares',None,None,'Enero 2026'],
   [None,'Productos primarios',None,10],
   [None,None,'Cereales',1000],
  ])
  with self.assertRaises(ValueError): rubros.extraer_datos_rubros(df,'Exportacion',{'productos primarios':'PP'},'2026-01')
 def test_reject_incomplete_country_observation(self):
  df=pd.DataFrame([
   ['Enero 2026 millones de dólares','Enero 2026',None,None,None,'Enero 2026'],
   [None]*6,[None]*6,[None]*6,[None]*6,
   ['Brasil',10,None,None,'Brasil',7],
   ['China',None,None,None,'China',None],
  ])
  with self.assertRaises(ValueError): countries.parse_countries(df,'2026-01')
