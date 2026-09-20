"""Commitment review never turns a reminder click into a completion."""
import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest import mock

try:
    import sia_test_home  # noqa: F401; isolate runtime paths before imports
except ModuleNotFoundError:
    from tests import sia_test_home  # noqa: F401

from tests.test_cli import _load_script, sia
import siatakes

REPO = os.path.dirname(os.path.dirname(__file__))
review = _load_script('sia_intent_review_test', os.path.join(REPO, 'bin/sia-intent-review'))
IID = '5e1a06cc61'
ROW = dict(id=IID, text='Review ' + 'the supporting record ' * 8,
           due='2026-09-08', holder='sia', created='2026-08-29T16:58:03Z')


def result(code=0, stdout=''):
    return subprocess.CompletedProcess([], code, stdout, '')


class IntentReview(unittest.TestCase):
    def test_list_exposes_identity_usable_by_show(self):
        output = io.StringIO()
        with mock.patch.object(siatakes, 'open_intents', return_value=[dict(ROW, days_left=-12)]), contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_intend(['--list']), 0)
        self.assertIn(IID, output.getvalue())

    def test_show_full_task_without_internal_paths(self):
        output = io.StringIO()
        with mock.patch.object(siatakes, 'open_intents', return_value=[dict(ROW, path='/private', days_left=-12)]), contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_intend(['--show', IID]), 0)
        self.assertEqual(json.loads(output.getvalue()), ROW)

    def test_show_rejects_missing_and_ambiguous(self):
        for rows in ([], [ROW, ROW]):
            with mock.patch.object(siatakes, 'open_intents', return_value=rows), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sia.cmd_intend(['--show', IID]), 1)

    def test_show_rejects_option_and_shell_shaped_identity(self):
        for iid in ('--help', '$(touch /tmp/no)', IID[:6]):
            with mock.patch.object(siatakes, 'open_intents') as read, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sia.cmd_intend(['--show', iid]), 2)
                read.assert_not_called()

    def run_review(self, answers, responses=None):
        output = io.StringIO()
        with mock.patch.object(review, 'run_cli', side_effect=responses or [result(stdout=json.dumps(ROW))]) as run, mock.patch('builtins.input', side_effect=answers), contextlib.redirect_stdout(output):
            code = review.review(IID)
        return code, run.call_args_list, output.getvalue()

    def test_cancel_empty_outcome_and_final_cancel_never_write(self):
        for answers in ([''], ['done', ''], ['done', 'x' * 201], ['done', 'Reviewed evidence', 'no']):
            _, calls, _ = self.run_review(answers)
            self.assertEqual(calls, [mock.call(['--show', IID])])

    def test_close_requires_outcome_and_explicit_confirmation(self):
        code, calls, output = self.run_review(['done', 'Checked retained records', 'close'], [result(stdout=json.dumps(ROW)), result(stdout='done')])
        self.assertEqual(code, 0)
        self.assertEqual(calls[-1], mock.call(['--done', IID, 'Checked retained records']))
        self.assertIn('next successful publication', output)

    def test_stale_close_never_reports_success(self):
        code, _, output = self.run_review(['done', 'Reviewed', 'close'], [result(stdout=json.dumps(ROW)), result(1, 'no unique open intent')])
        self.assertEqual(code, 1)
        self.assertNotIn('Closed.', output)

    def test_failed_read_never_prompts_or_writes(self):
        code, calls, _ = self.run_review([], [result(1, 'not ready')])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [mock.call(['--show', IID])])

    def test_response_identity_mismatch_refuses(self):
        with self.assertRaises(ValueError):
            self.run_review([], [result(stdout=json.dumps(dict(ROW, id='aaaaaaaaaa')))])

    def test_terminal_control_codes_removed(self):
        self.assertNotIn('\x1b', review.display('\x1b[31mred\ntext'))

    def test_noninteractive_review_never_calls_cli(self):
        with mock.patch.object(review.sys.stdin, 'isatty', return_value=False), mock.patch.object(review, 'run_cli') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(review.main([IID]), 2)
            run.assert_not_called()

    def test_full_text_status_contract_matches_qml(self):
        self.assertTrue(sia.sialib._status_intents_shape([dict(id=IID, text='x' * 300, due='2026-09-08', days_left=-12)]))
        self.assertFalse(sia.sialib._status_intents_shape([dict(id=IID, text='x' * 301, due='2026-09-08', days_left=-12)]))
        script = "const fs=require('fs'),vm=require('vm');let s=fs.readFileSync('Model.js','utf8').replace(/^\\.pragma.*$/mg,'');let c={};vm.createContext(c);vm.runInContext(s,c);for(let n of [300,301])console.log(c.residentIntentShape([{id:'5e1a06cc61',text:'x'.repeat(n),due:'2026-09-08',days_left:-12}]));"
        run = subprocess.run(['node', '-e', script], cwd=REPO, capture_output=True, text=True, check=True)
        self.assertEqual(run.stdout.splitlines(), ['true', 'false'])


if __name__ == '__main__':
    unittest.main()
