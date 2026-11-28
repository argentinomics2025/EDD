"""Only run against a disposable local cluster initialized by the test operator."""
import os,re,threading,time,psycopg
from psycopg.conninfo import conninfo_to_dict
if os.environ.get('EC022_DISPOSABLE_TEST_CLUSTER') != 'yes':
 raise SystemExit('Refusing to run without EC022_DISPOSABLE_TEST_CLUSTER=yes')
DSN=os.environ.get('EC022_TEST_DSN','')
SERIES=os.environ.get('EC022_TEST_SERIES','test')
if SERIES != 'test' and not re.fullmatch(r'ec022_test_[0-9a-f]{12}',SERIES):
 raise SystemExit('Unexpected test series name')
parts=conninfo_to_dict(DSN)
if parts.get('host') not in ('localhost','127.0.0.1','::1') or not parts.get('port'):
 raise SystemExit('Refusing non-local test database')
ready=threading.Event(); outcomes=[]
def one(value,wait):
 try:
  with psycopg.connect(DSN) as c:
   c.execute('set role ec022_ingestor')
   result=c.execute("select public.ec022_ingestar_observacion(%s,'2022-01-01',repeat('e',64),%s,'https://example.test','2020-03-01Z',null)",(SERIES,value)).fetchone()[0]
   if wait: ready.set(); time.sleep(1.5)
   outcomes.append(result)
 except psycopg.errors.UniqueViolation: outcomes.append('conflict')
a=threading.Thread(target=one,args=(7,True));a.start();assert ready.wait(5)
b=threading.Thread(target=one,args=(8,False));b.start();a.join();b.join()
assert sorted(outcomes)==['conflict','inserted'],outcomes
print('concurrent conflicting inserts:',outcomes)
