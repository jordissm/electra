"""Named-target forwarding and provenance checks without simulation events."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from electra import cli


ROOT = Path(__file__).resolve().parents[1]


class NucleusSelectionTest(unittest.TestCase):
    def test_cli_accepts_name_without_explicit_chunk_size(self):
        settings = ROOT / "input/ehijing/experiments/hermes_2007"
        with tempfile.TemporaryDirectory() as temporary, patch.object(cli, "ehijing_task") as task:
            args = cli.build_parser().parse_args(["ehijing", "run", "--nucleus", "C12",
                "--run-path", temporary, "--number-of-events", "1",
                "--hard-process-config", str(settings / "hard_process.setting"),
                "--hadronization-config", str(settings / "hadronization.setting"),
                "--dis-cuts-config", str(settings / "dis_cuts.setting")])
            cli.cmd_ehijing(args)
            self.assertEqual(task.call_args.kwargs["nucleus"], "C12")
            self.assertIsNone(task.call_args.args[3])

    def test_lookup_uses_executable_reader(self):
        with patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, '{"A":12,"Z":6}', "")) as query:
            self.assertEqual(cli.resolve_nucleus("C12", Path("custom.yaml"),
                nucleon_width_fm=.7, nuclear_radius_fm=None), {"A": 12, "Z": 6})
            self.assertEqual(query.call_args.args[0], ["ehijing", "--nucleus", "C12",
                "--describe-nucleus", "--nucleus-database", "custom.yaml", "--nucleon-width-fm", "0.7"])
        with patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 2, "", "Unknown nucleus 'C'")):
            with self.assertRaisesRegex(ValueError, "Unknown nucleus"):
                cli.resolve_nucleus("C")

    def test_named_target_forwarding_and_database_resume_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            settings = root / "settings"
            settings.write_text("fixture")
            database = root / "nuclei.yaml"
            database.write_text("nuclei: fixture\n")
            tables = root / "tables"
            tables.mkdir()
            (tables / "Qs.dat").write_text("fixture table")
            parameters = {"nucleus": "C12", "nucleus_database": str(database),
                          "distribution": "woods_saxon", "A": 12, "Z": 6,
                          "nucleon_width_fm": .5, "nuclear_radius_fm": 2.3, "nuclear_surface_fm": .4}
            arguments = dict(run_dir=root / "run", first_event_id=0, nevents=1, chunk_size=1,
                base_seed=123, nucleus="C12", nucleus_database=database, mode=0, K=4,
                table_path=tables, config_file=settings,
                hadronization_config_file=settings, dis_cuts_config_file=settings)

            def generated(command):
                self.assertEqual(command[command.index("--nucleus") + 1], "C12")
                self.assertEqual(command[command.index("--nucleus-database") + 1], str(database))
                self.assertNotIn("--A", command)
                self.assertNotIn("--Z", command)
                metadata = arguments["run_dir"] / "events/event_00000000.meta.json"
                metadata.write_text(json.dumps({"reproducibility": {
                    "policy": cli.SEED_POLICY, "master_seed": "123", "first_event_id": 0,
                    "streams": {"hard_pythia": 1}, "nucleus_parameters": parameters,
                    "inputs_sha256": {"nucleus_database": cli.file_sha256(database)}}}))

            with patch.object(cli, "resolve_nucleus", return_value=parameters), \
                 patch.object(cli, "run", side_effect=generated) as run, \
                 patch.object(cli, "executable_digest", return_value="binary"):
                cli.ehijing_task(**arguments)
                cli.ehijing_task(**arguments)
                self.assertEqual(run.call_count, 1)
                record = json.loads((arguments["run_dir"] / "manifest.jsonl").read_text())
                self.assertEqual((record["A"], record["Z"]), (12, 6))
                self.assertEqual(record["nucleus_parameters"]["nuclear_radius_fm"], 2.3)
                self.assertEqual(record["nucleus_database_sha256"], cli.file_sha256(database))
                database.write_text("changed database\n")
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.ehijing_task(**arguments)
                self.assertEqual(run.call_count, 1)

    def test_conflicting_target_arguments_fail_before_lookup(self):
        with patch.object(cli, "resolve_nucleus") as lookup:
            with self.assertRaisesRegex(ValueError, "not both"):
                cli.ehijing_task(Path("unused"), 0, 1, 1, 123,
                    nucleus="C12", A=12, Z=6, mode=0, K=4, table_path=Path("unused"),
                    config_file=Path("unused"), hadronization_config_file=Path("unused"),
                    dis_cuts_config_file=Path("unused"))
            lookup.assert_not_called()

    def test_slurm_forwards_name_and_custom_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            binary_dir = root / "bin"
            binary_dir.mkdir()
            capture = root / "submitted.sh"
            sbatch = binary_dir / "sbatch"
            sbatch.write_text('#!/bin/sh\ncat >> "$CAPTURE"\nprintf "12345\\n"\n')
            sbatch.chmod(0o755)
            database = root / "custom nuclei.yaml"
            database.write_text("nuclei: fixture\n")
            environment = {"PATH": str(binary_dir) + os.pathsep + os.environ["PATH"], "USER": "testuser",
                "PROJECT_ROOT": str(ROOT), "EXPERIMENT": "hermes_2007",
                "SLURM_CONFIG": str(root / "missing.env"), "OUTPUT_HOST": str(root / "output"),
                "CAPTURE": str(capture)}
            result = subprocess.run(["bash", str(ROOT / "slurm-scripts/ehijing_submit.sh"),
                "NUCLEUS=C12", f"NUCLEUS_DATABASE={database}"], env=environment,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            submitted = capture.read_text()
            self.assertIn('NUCLEUS="C12"', submitted)
            self.assertIn(f'NUCLEUS_DATABASE="{database}"', submitted)
            self.assertIn('--nucleus "${NUCLEUS}"', submitted)
            self.assertIn('--nucleus-database "${NUCLEUS_DATABASE}"', submitted)
            self.assertIn('--bind "${NUCLEUS_DATABASE}:${NUCLEUS_DATABASE}:ro"', submitted)
            self.assertNotIn("--Z ", submitted)
            self.assertNotIn("--A ", submitted)


if __name__ == "__main__":
    unittest.main()
