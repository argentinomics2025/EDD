import unittest
from scripts.ec022_ipc import parse

H='Codigo;Descripcion;Clasificador;Periodo;Indice_IPC;v_m_IPC;v_i_a_IPC;Region\n'
class IpcTests(unittest.TestCase):
    def test_separate_level_and_change(self):
        raw=(H+'0;NIVEL GENERAL;x;202001;100;NA;NA;Nacional\n0;NIVEL GENERAL;x;202002;102;2,0;NA;Nacional\n').encode('cp1252')
        self.assertEqual(parse(raw)['observations'][1]['monthly_percent'],'2.0')
    def test_inconsistent_change_rejected(self):
        raw=(H+'0;NIVEL GENERAL;x;202001;100;NA;NA;Nacional\n0;NIVEL GENERAL;x;202002;102;20;NA;Nacional\n').encode('cp1252')
        with self.assertRaises(ValueError): parse(raw)
