"""Release evidence must fail closed for absent tools and invalid reports."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_release
from tools.kicad_reports import load_report, require_version
from tools.run_kicad_checks import run_checks


class ReleaseVerificationTest(unittest.TestCase):
    def verify_without_hardware(self, extra_args=(), failure=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'summary.json'
            step = {'command': ['mock-software-check'], 'exit_code': int(failure)}
            with patch.object(verify_release, 'ROOT', root), \
                 patch.object(verify_release, 'run', return_value=step), \
                 patch.object(verify_release, 'resolve_kicad_cli', return_value=None), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = verify_release.main([*extra_args, '--output', str(output)])
            return code, json.loads(output.read_text())

    def test_missing_kicad_cannot_verify_release(self):
        code, result = self.verify_without_hardware()
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertTrue(result['software_verified'])
        self.assertFalse(result['verified'])
        self.assertFalse(result['hardware_checked'])

    def test_explicit_software_mode_succeeds_without_claiming_full_verification(self):
        code, result = self.verify_without_hardware(['--software-only'])
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'SOFTWARE_VERIFIED')
        self.assertFalse(result['verified'])

    def test_failed_software_gate_cannot_verify_either_scope(self):
        code, result = self.verify_without_hardware(['--software-only'], failure=True)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['software_verified'])
        self.assertFalse(result['verified'])

    def test_only_exact_pinned_kicad_version_is_accepted(self):
        require_version('10.0.5')
        require_version('10.0.5-1')
        for version in ('8.0.0', '10.0.50', '10.0.4', '', 'not-kicad'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                require_version(version)

    def test_empty_or_wrong_source_report_is_not_a_clean_report(self):
        source = Path(__file__).resolve().parents[1] / 'hardware/reports/circle-main-erc.json'
        valid = json.loads(source.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'erc.json'
            for data in ({}, {**valid, 'source':'other.sch'}, {**valid, 'sheets':[]},
                         {**valid, 'included_severities':['error']}):
                with self.subTest(data=data):
                    output.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        load_report(output, 'erc', '00_root.sch')

    def test_successful_exit_without_fresh_report_cannot_reuse_archived_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            stale = output / 'circle-main-erc.json'
            stale.write_text('archived evidence')
            responses = [subprocess.CompletedProcess([], 0, stdout='10.0.5'),
                         subprocess.CompletedProcess([], 0, stdout='')]
            with patch('tools.run_kicad_checks.subprocess.run', side_effect=responses):
                with self.assertRaisesRegex(ValueError, 'did not produce'):
                    run_checks(Path('/fake/kicad'), output)
            self.assertEqual(stale.read_text(), 'archived evidence')
