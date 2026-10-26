"""Fixed public diagnostic vocabulary. Never print exceptions or external data."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import subprocess

STAGES=frozenset(('CONTEXT','ENGINE','PREFLIGHT','SCAN','NETWORK','BOOTSTRAP','INTEGRATION','CLEANUP'))
CODES=frozenset(('START','OK','CHECK_FAILED','COMMAND_FAILED','COMMAND_TIMEOUT','REQUIRED_FILE',
    'INVALID_JSON','HOSTED_CONTEXT','ENDPOINT_OVERRIDE','CONNECTION_OVERRIDE','RUN_IDENTITY',
    'REPLAY_DENIED','WORKFLOW_SHA','WORKSPACE','TEMP_STORAGE','EVENT_READ','MANUAL_EVENT',
    'AUTHORIZED_SHA','CONTEXT_BINDING','BINDING_MISSING','ENGINE_ID','ENGINE_BINDING',
    'CHECKOUT_COMMAND','CHECKOUT_MISMATCH','HOST_OS','HOST_OS_READ','STATE_STORAGE',
    'ENGINE_INFO','ENGINE_PLATFORM','ENGINE_INVENTORY','ENGINE_NOT_EMPTY','COMPOSE_QUERY',
    'COMPOSE_VERSION','COMPOSE_SERVICE_OPTIONS','COMPOSE_SERVICE_IDENTITY','COMPOSE_NETWORK',
    'COMPOSE_MOUNTS','COMPOSE_BEHAVIOR','COMPOSE_BUILD','SOURCE_CHANGED','LOCK_INVALID',
    'IMAGE_PULL','IMAGE_BUILD','SCAN_REJECTED','SCAN_DATABASE','SCAN_INVENTORY',
    'COMPOSE_CREATE','ATTESTATION','NETWORK_GUARD','SECURITY_BINDING','SERVICE_INVENTORY',
    'BOOTSTRAP_STOPPED','BOOTSTRAP_TIMEOUT','INTEGRATION_EXIT','INTEGRATION_TIMEOUT',
    'INTEGRATION_REPORT','CLEANUP_FAILED','SCAN_SCANNER_PULL','SCAN_DB_DOWNLOAD',
    'SCAN_DB_VALIDATE','SCAN_IMAGE_INSPECT','SCAN_IMAGE_EXPORT','SCAN_IMAGE_RUN',
    'SCAN_REPORT_READ','SCAN_REPORT_CHECK','SCAN_PROOF_WRITE'))
SUBJECTS=frozenset(('VULN_DATABASE','POSTGRES','POSTGREST','LAB_RUNNER','PYTHON_BASE','SCANNER'))
REASONS=frozenset(('COMMAND_FAILED','COMMAND_TIMEOUT','KILLED_137','PERMISSION_DENIED',
    'READ_ONLY_FS','CLI_OPTION','REGISTRY_AUTH','RATE_LIMIT','NETWORK','TLS',
    'INVALID_JSON','REQUIRED_FILE','CHECK_FAILED'))
CURRENT_STAGE=ContextVar('ec016_stage',default='CONTEXT')

# Only exact, locally defined messages are classified, never echoed. Unrecognized
# text (including command stderr or poisoned values) gets CHECK_FAILED.
POLICY_CODES={
    'Unreviewed effective service option':'COMPOSE_SERVICE_OPTIONS',
    'Service identity/environment/entrypoint changed':'COMPOSE_SERVICE_IDENTITY',
    'Unexpected project or services':'COMPOSE_SERVICE_IDENTITY',
    'Network policy mismatch':'COMPOSE_NETWORK',
    'Unexpected network/IPAM':'COMPOSE_NETWORK',
    'Additional networks forbidden':'COMPOSE_NETWORK',
    'Wrong service network or IP':'COMPOSE_NETWORK',
    'Unapproved DNS destination':'COMPOSE_NETWORK',
    'Unapproved mount or writable bind':'COMPOSE_MOUNTS',
    'Wrong disposable storage':'COMPOSE_MOUNTS',
    'Effective service behavior changed':'COMPOSE_BEHAVIOR',
    'Unapproved build context or base':'COMPOSE_BUILD',
    'Prepared sources changed, added or removed; create a fresh run':'SOURCE_CHANGED',
    'Prepared source changed; create a fresh run':'SOURCE_CHANGED',
    'Image verification evidence inconsistent':'LOCK_INVALID',
    'Dependency lock missing or changed':'LOCK_INVALID',
    'Every dependency must be version and hash locked':'LOCK_INVALID',
    'Blocking image vulnerability; no SQL permitted':'SCAN_REJECTED',
    'Vulnerability database missing or stale':'SCAN_DATABASE',
    'Unsupported vulnerability database format':'SCAN_DATABASE',
    'No package inventory; empty scan is not clearance':'SCAN_INVENTORY',
}


class Failure(RuntimeError):
    def __init__(self,stage,code,*,subject=None,reason=None):
        validate_public(stage,code,subject,reason)
        self.stage=stage;self.code=code;self.subject=subject;self.reason=reason
        super().__init__('EC016_FAILED')


def validate_public(stage,code,subject=None,reason=None):
    if (stage not in STAGES or code not in CODES
            or (subject is not None and subject not in SUBJECTS)
            or (reason is not None and reason not in REASONS)):
        raise ValueError('Invalid public diagnostic')


def emit(stage,code,status,*,subject=None,reason=None):
    validate_public(stage,code,subject,reason)
    if status not in ('START','OK','FAILED'):raise ValueError('Invalid public diagnostic')
    record={'ec016_stage':stage,'status':status,'code':code}
    if subject is not None:record['subject']=subject
    if reason is not None:record['reason']=reason
    print(json.dumps(record,sort_keys=True),flush=True)


def fail(stage,code):
    raise Failure(stage,code) from None


def classify(stage,error):
    if isinstance(error,Failure):return error
    if isinstance(error,subprocess.TimeoutExpired):code='COMMAND_TIMEOUT'
    elif isinstance(error,subprocess.CalledProcessError):code='COMMAND_FAILED'
    elif isinstance(error,FileNotFoundError):code='REQUIRED_FILE'
    elif isinstance(error,json.JSONDecodeError):code='INVALID_JSON'
    elif isinstance(error,(ValueError,RuntimeError)) and len(error.args)==1 and type(error.args[0]) is str:
        code=POLICY_CODES.get(error.args[0],'CHECK_FAILED')
    else:code='CHECK_FAILED'
    return Failure(stage,code)


@contextmanager
def stage(name):
    if name not in STAGES:raise ValueError('Invalid public diagnostic')
    emit(name,'START','START');token=CURRENT_STAGE.set(name)
    try:
        yield
    except Exception as error:
        raise classify(name,error) from None
    else:emit(name,'OK','OK')
    finally:CURRENT_STAGE.reset(token)


def operation(code,function,*args,**kwargs):
    if code not in CODES:raise ValueError('Invalid public diagnostic')
    try:return function(*args,**kwargs)
    except Failure:raise
    except Exception as error:
        classified=classify(CURRENT_STAGE.get(),error)
        # Retain a specific, known local policy reason. Otherwise use the fixed
        # operation code so info/Compose/checkout failures are distinguishable.
        if classified.code in ('CHECK_FAILED','COMMAND_FAILED','REQUIRED_FILE','INVALID_JSON'):
            classified=Failure(CURRENT_STAGE.get(),code)
        raise classified from None
