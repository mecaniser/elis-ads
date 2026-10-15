import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('mac_supervisor', Path(__file__).with_name('supervisor.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class MacIsolation(unittest.TestCase):
    def test_only_owned_worker_can_be_destroyed(self):
        for name in (s.BASE, 'default', s.WORKER + '/../../base'):
            with patch.object(s, 'command') as run:
                with self.assertRaises(ValueError):
                    s.destroy(name)
                run.assert_not_called()

    def test_failed_cleanup_prevents_clone(self):
        with patch.object(s, 'destroy', side_effect=RuntimeError('busy')), patch.object(s, 'command') as run:
            with self.assertRaises(RuntimeError):
                s.cycle()
            run.assert_not_called()

    def test_failed_preflight_prevents_registration(self):
        with patch.object(s, 'guest', side_effect=RuntimeError('unsafe')), patch.object(s, 'api') as api:
            with self.assertRaises(RuntimeError):
                s.register('192.168.64.4')
            api.assert_not_called()

    def test_token_stdin_and_ephemeral_nonadmin_registration(self):
        with patch.object(s, 'guest') as guest, patch.object(s, 'api', return_value={'token': 'secret-canary'}):
            s.register('192.168.64.4')
            call = guest.call_args_list[1]
            self.assertNotIn('secret-canary', str(call.args))
            self.assertEqual(call.kwargs['data'], 'secret-canary')
            self.assertIn('--ephemeral', call.args[1])
            self.assertIn('sudo -u admin', call.args[1])

    def test_management_ssh_pins_base_identity(self):
        with patch.object(s, 'command') as run:
            s.guest('192.168.64.4', 'true')
            args = run.call_args.args[0]
            self.assertIn('StrictHostKeyChecking=yes', args)
            self.assertIn('IdentitiesOnly=yes', args)
            self.assertIn('HostKeyAlias=' + s.BASE, args)
            self.assertNotIn('-A', args)


if __name__ == '__main__':
    unittest.main()
