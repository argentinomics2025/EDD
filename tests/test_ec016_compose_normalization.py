"""Regression against actual Compose 2.40.3 output; no Docker or services in tests."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from infra.ec016.runner import policy

FIXTURE=Path(__file__).parent/'fixtures/ec016/compose-2.40.3-config.json'


class ComposeNormalizationTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect','subprocess.run'):
            block=patch(target,side_effect=AssertionError('No service/client invocation in unit tests'))
            block.start();self.addCleanup(block.stop)
        data=json.loads(FIXTURE.read_text())
        self.expected=data['expected'];self.actual=data['actual'];self.provenance=data['provenance']

    def test_captured_compose_output_reproduces_extra_keys_and_now_passes(self):
        for name,wanted in self.expected['services'].items():
            extra=set(self.actual['services'][name])-set(wanted)
            self.assertEqual(extra,set(self.provenance['additional_service_keys'][name]))
            self.assertTrue(all(self.actual['services'][name][key] is None for key in extra))
        self.assertTrue(policy.validate_effective(self.actual,self.expected))

    def test_nulls_mean_inherit_but_explicit_empty_or_commands_are_not_ignored(self):
        for key in ('command','entrypoint'):
            for value in ([], '', ['/bin/sh'], ['python','unreviewed.py']):
                actual=copy.deepcopy(self.actual);actual['services']['ec016-api'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    policy.validate_effective(actual,self.expected)

    def test_required_entrypoint_or_command_cannot_be_removed_by_null(self):
        for name,key in (('ec016-db','entrypoint'),('ec016-tests','command')):
            actual=copy.deepcopy(self.actual);actual['services'][name][key]=None
            with self.subTest(service=name,key=key),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)

    def test_false_bind_flag_is_omitted_in_captured_output(self):
        for name,wanted in self.expected['services'].items():
            for expected,actual in zip(wanted['volumes'],self.actual['services'][name]['volumes']):
                self.assertEqual(expected['bind'],{'create_host_path':False})
                self.assertEqual(actual['bind'],{})
                self.assertEqual({k:v for k,v in expected.items() if k!='bind'},
                                 {k:v for k,v in actual.items() if k!='bind'})

    def test_memory_byte_strings_preserve_exact_limits(self):
        for name,service in self.actual['services'].items():
            self.assertIsInstance(service['mem_limit'],str)
            self.assertRegex(service['mem_limit'],r'^[0-9]+$')
            self.assertEqual(policy.canonical_service(service)['mem_limit'],
                             policy.canonical_service(self.expected['services'][name])['mem_limit'])
        for memory in ('0','1','805306367','805306369','805306368.0','768g',''):
            actual=copy.deepcopy(self.actual);actual['services']['ec016-db']['mem_limit']=memory
            with self.subTest(memory=memory),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)

    def test_host_path_creation_and_other_bind_options_remain_forbidden(self):
        for options in ({'create_host_path':True},{'propagation':'rshared'},{'selinux':'Z'}):
            actual=copy.deepcopy(self.actual);actual['services']['ec016-db']['volumes'][0]['bind']=options
            with self.subTest(bind=options),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)
        actual=copy.deepcopy(self.actual);del actual['services']['ec016-db']['volumes'][0]['bind']
        with self.assertRaises(ValueError):policy.validate_effective(actual,self.expected)

    def test_dangerous_or_unknown_service_keys_are_never_normalized_away(self):
        for key,value in {'ports':['5432:5432'],'privileged':True,'cap_add':['ALL'],
                          'network_mode':'host','env_file':['.env'],'devices':['/dev/sda'],
                          'volumes_from':['foreign'],'pid':'host','ipc':'host',
                          'unreviewed_option':None,'ports_null':None}.items():
            actual=copy.deepcopy(self.actual)
            actual['services']['ec016-db']['ports' if key=='ports_null' else key]=value
            with self.subTest(option=key),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)

    def test_mounts_readonly_sources_targets_and_types_are_still_compared(self):
        for key,value in (('read_only',False),('source','/var/run/docker.sock'),
                          ('target','/host'),('type','volume')):
            actual=copy.deepcopy(self.actual);actual['services']['ec016-db']['volumes'][0][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)

    def test_network_privileges_and_environment_controls_remain_exact(self):
        for kind in ('network','dns','capabilities','environment','extra-mount'):
            actual=copy.deepcopy(self.actual);service=actual['services']['ec016-tests']
            if kind=='network':service['networks']['foreign']={}
            if kind=='dns':service['dns']=['8.8.8.8']
            if kind=='capabilities':service['cap_drop']=[]
            if kind=='environment':service['environment']['DATABASE_URL']='postgres://example.invalid/prod'
            if kind=='extra-mount':service['volumes'].append({'type':'bind','source':'/','target':'/host','read_only':True})
            with self.subTest(change=kind),self.assertRaises(ValueError):
                policy.validate_effective(actual,self.expected)


if __name__=='__main__':unittest.main()
