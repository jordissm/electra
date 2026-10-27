"""Check model defaults and overrides without generating simulation events."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from electra import cli


ROOT = Path(__file__).resolve().parents[1]


class MediumModeTest(unittest.TestCase):
    def test_cli_default_and_explicit_ht_are_forwarded(self):
        settings = ROOT / "input/ehijing/experiments/hermes"
        with tempfile.TemporaryDirectory() as temporary:
            arguments = ["ehijing", "run", "--run-path", str(Path(temporary) / "run"),
                         "--number-of-events", "1", "--chunk-size", "1",
                         "--hard-process-config", str(settings / "hard_process.setting"),
                         "--hadronization-config", str(settings / "hadronization.setting"),
                         "--dis-cuts-config", str(settings / "dis_cuts.setting")]
            for override, expected in (([], 1), (["--medium-modification-mode", "0"], 0)):
                with self.subTest(override=override), patch.object(cli, "ehijing_task") as task:
                    args = cli.build_parser().parse_args(arguments + override)
                    cli.cmd_ehijing(args)
                    self.assertEqual(task.call_args.kwargs["mode"], expected)

    def test_slurm_default_and_override_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary_dir = root / "bin"
            binary_dir.mkdir()
            sbatch = binary_dir / "sbatch"
            sbatch.write_text('#!/bin/sh\ncat >> "$CAPTURE"\nprintf "12345\\n"\n')
            sbatch.chmod(0o755)
            capture = root / "submitted.sh"
            config = root / "cluster.env"
            environment = {
                "PATH": str(binary_dir) + os.pathsep + os.environ["PATH"], "USER": "testuser",
                "PROJECT_ROOT": str(ROOT), "EXPERIMENT": "hermes", "SLURM_CONFIG": str(config),
                "OUTPUT_HOST": str(root / "output"), "CAPTURE": str(capture),
            }
            cases = [
                ("", {}, [], 1),
                ("", {"MED_MODIF_MODE": "0"}, [], 0),
                ("MED_MODIF_MODE=0\n", {}, [], 0),
                ("MED_MODIF_MODE=0\n", {}, ["MED_MODIF_MODE=1"], 1),
                ("MED_MODIF_MODE=1\n", {}, ["MED_MODIF_MODE=0"], 0),
            ]
            for content, variables, overrides, expected in cases:
                with self.subTest(config=content, variables=variables, overrides=overrides):
                    config.write_text(content)
                    capture.write_text("")
                    result = subprocess.run(["bash", str(ROOT / "slurm-scripts/ehijing_submit.sh"), *overrides],
                                            env={**environment, **variables}, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    submitted = capture.read_text()
                    self.assertIn(f'MED_MODIF_MODE="{expected}"', submitted)
                    self.assertIn("--medium-modification-mode ${MED_MODIF_MODE}", submitted)


if __name__ == "__main__":
    unittest.main()
