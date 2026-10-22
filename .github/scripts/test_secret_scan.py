"""Exercise the workflow's scan scope without credentials or scanner output."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / "workflows/secret-scanning.yml"
SCRIPT = textwrap.dedent(
    WORKFLOW.read_text().split("python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
)


class ScanScopeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Scan fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repository / "fixture.txt").write_text("first\n")
        self.git("add", ".")
        self.git("commit", "-qm", "first")
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.repository / "fixture.txt").write_text("second\n")
        self.git("commit", "-qam", "second")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        scanner = self.bin / "infisical"
        scanner.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
            "report = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--report-path='))\n"
            "pathlib.Path(report).write_text('[]')\n"
        )
        scanner.chmod(0o755)

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def run_scan(self, event, base):
        capture = self.root / "arguments.json"
        environment = {
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "RUNNER_TEMP": str(self.root),
            "GITHUB_STEP_SUMMARY": str(self.root / "summary.md"),
            "SCAN_EVENT": event,
            "SCAN_HEAD": self.head,
            "SCAN_BASE": base,
            "SCAN_FULL_HISTORY": "false",
            "CAPTURE": str(capture),
        }
        result = subprocess.run(
            ["python3", "-c", SCRIPT],
            cwd=self.repository,
            env=environment,
            capture_output=True,
            text=True,
        )
        arguments = json.loads(capture.read_text()) if capture.exists() else []
        return result, arguments

    def test_normal_push_keeps_the_changed_commit_range(self):
        result, arguments = self.run_scan("push", self.base)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--log-opts=" + self.base + ".." + self.head, arguments)

    def test_rewritten_push_with_missing_base_scans_all_current_history(self):
        result, arguments = self.run_scan("push", "1" * 40)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--log-opts=" + self.head, arguments)
        self.assertNotIn("--no-git", arguments)

    def test_pull_request_missing_base_still_fails_closed(self):
        result, arguments = self.run_scan("pull_request", "1" * 40)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(arguments, [])

    def test_invalid_revision_still_fails_closed(self):
        result, arguments = self.run_scan("push", "--all")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(arguments, [])

    def test_nonancestor_push_scans_all_current_history(self):
        self.git("checkout", "--orphan", "rewritten-fixture")
        self.git("commit", "-qm", "rewritten")
        previous = self.head
        self.head = self.git("rev-parse", "HEAD").strip()
        result, arguments = self.run_scan("push", previous)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--log-opts=" + self.head, arguments)


if __name__ == "__main__":
    unittest.main()
