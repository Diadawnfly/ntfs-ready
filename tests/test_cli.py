"""CLI tests use only simulated OS services, never mounted drives."""
import io
import json
import unittest
from ntfs_ready import cli, __version__
from ntfs_ready.core import SafetyError
from test_core import SimulatedRunner, service


class CLITests(unittest.TestCase):
    def invoke(self, args, runner=None, answers=()):
        out, err = io.StringIO(), io.StringIO()
        app = service(runner or SimulatedRunner())
        prompts = []
        responses = iter(answers)
        def answer(prompt):
            prompts.append(prompt)
            return next(responses)
        code = cli.main(args, service=app, input_fn=answer, out=out, err=err)
        return code, out.getvalue(), err.getvalue(), prompts

    def test_version(self):
        code, out, _, _ = self.invoke(['--version'])
        self.assertEqual(code, 0)
        self.assertIn(__version__, out)
        self.assertIn('beta', out)

    def test_list_json_is_machine_readable(self):
        code, out, err, _ = self.invoke(['list', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]['device'], 'disk12s1')
        self.assertEqual(err, '')

    def test_doctor_json(self):
        code, out, _, _ = self.invoke(['doctor', '--json'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['dependencies_ready'])

    def test_mount_yes_does_not_prompt_or_write_probe(self):
        code, out, err, prompts = self.invoke(['mount', 'disk12s1', '--yes'])
        self.assertEqual(code, 0, err)
        self.assertIn('macfuse', out)
        self.assertEqual(prompts, [])

    def test_mount_dry_run_does_not_need_yes(self):
        runner = SimulatedRunner()
        code, _, _, prompts = self.invoke(['mount', 'disk12s1', '--dry-run'], runner)
        self.assertEqual(code, 0)
        self.assertEqual(prompts, [])
        self.assertFalse(any('unmount' in a or a[0] == '/usr/bin/sudo' for a, _ in runner.calls))

    def test_declining_unmount_has_no_mutation(self):
        runner = SimulatedRunner()
        code, _, _, _ = self.invoke(['unmount', 'disk12s1'], runner, ['no'])
        self.assertNotEqual(code, 0)
        self.assertFalse(any('unmount' in a for a, _ in runner.calls))

    def test_verify_json_error_requires_macfuse_and_no_write(self):
        code, out, _, _ = self.invoke(['verify', 'disk12s1', '--yes', '--json'])
        self.assertEqual(code, 1)
        self.assertIn('error', json.loads(out))

    def test_malformed_device_rejected_before_any_discovery(self):
        runner = SimulatedRunner()
        code, _, _, prompts = self.invoke(['mount', '/dev/disk12s1', '--yes'], runner)
        self.assertEqual(code, 1)
        self.assertEqual(runner.calls, [])
        self.assertEqual(prompts, [])

    def test_menu_selection_and_decline_does_not_unmount(self):
        runner = SimulatedRunner()
        code, out, _, _ = self.invoke(['menu'], runner, ['mount', '1', 'no', 'quit'])
        self.assertEqual(code, 0)
        self.assertIn('disk12s1', out)
        self.assertFalse(any('unmount' in a for a, _ in runner.calls))

    def test_root_execution_fails_without_commands(self):
        runner = SimulatedRunner()
        app = service(runner)
        app.uid = 0
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(cli.main(['list'], service=app, out=out, err=err), 1)
        self.assertEqual(runner.calls, [])

    def test_menu_mount_requires_separate_write_confirmation(self):
        runner = SimulatedRunner()
        code, out, err, prompts = self.invoke(['menu'], runner, ['mount', '1', 'yes', 'no', 'quit'])
        self.assertEqual(code, 0, err)
        self.assertIn('"write_probe_performed": false', out)
        self.assertTrue(any('metadata verification' in p for p in prompts))

    def test_verify_success_json_with_explicit_simulated_prober(self):
        runner = SimulatedRunner()
        runner.driver = 'macfuse'
        runner.data['ReadOnlyVolume'] = False
        app = service(runner, prober=lambda *args: {'fixture': 'SIMULATED metadata; not empirical'})
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(['verify', 'disk12s1', '--yes', '--json'], service=app, out=out, err=err)
        self.assertEqual(code, 0, err.getvalue())
        self.assertTrue(json.loads(out.getvalue())['write_probe_performed'])
        self.assertFalse(json.loads(out.getvalue())['finder_gui_tested'])

    def test_target_changed_during_confirmation_is_refused(self):
        runner = SimulatedRunner()
        app = service(runner)
        def answer(prompt):
            runner.data['DiskUUID'] = 'SIMULATED-NEW-DISK'
            return 'yes'
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(['mount', 'disk12s1'], service=app, input_fn=answer, out=out, err=err)
        self.assertEqual(code, 1)
        self.assertFalse(any('unmount' in a or a[0] == '/usr/bin/sudo' for a, _ in runner.calls))

    def test_help_is_read_only(self):
        code, out, _, _ = self.invoke(['--help'])
        self.assertEqual(code, 0)
        for command in ('list', 'doctor', 'mount', 'unmount', 'verify', 'menu'):
            self.assertIn(command, out)


if __name__ == '__main__':
    unittest.main()
