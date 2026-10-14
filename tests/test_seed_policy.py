"""Seed propagation and resume protection; no simulation subprocesses."""
import argparse
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from electra import cli


class SeedPolicyTest(unittest.TestCase):
    def test_master_seed_boundaries(self):
        for value in ["0", "1", "900000000", "18446744073709551615"]:
            self.assertEqual(cli.master_seed(value), int(value))
        for value in ["-1", "+1", "1x", "1.0", " 1", "", "18446744073709551616", "١"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                cli.master_seed(value)

    def test_structured_hash(self):
        self.assertNotEqual(cli.hash_seed(1, 23, 4), cli.hash_seed(12, 3, 4))
        self.assertNotEqual(cli.hash_seed("1"), cli.hash_seed(1))
        self.assertNotEqual(cli.hash_seed("smash", 1), cli.hash_seed("ehijing", 1))
        self.assertEqual(cli.hash_seed("smash", 123, "event_00000007", "profile"),
                         3384440288479404782)
        self.assertLess(cli.hash_seed("smash", (1 << 64)-1, "event", "profile"), 1 << 63)

    def test_optional_ght_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Qs.dat").write_text("Qs")
            self.assertEqual(set(cli.table_digests(root, 1)), {"Qs.dat"})
            (root / "GHT.dat").write_text("GHT")
            self.assertEqual(set(cli.table_digests(root, 1)), {"Qs.dat", "GHT.dat"})
            self.assertEqual(set(cli.table_digests(root, 0)), {"Qs.dat"})

    def test_ehijing_forwarding_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = root / "settings"
            settings.write_text("fixture")
            tables = root / "tables"
            tables.mkdir()
            (tables / "Qs.dat").write_text("fixture table")
            args = dict(run_dir=root, first_event_id=7, nevents=2, chunk_size=None,
                        base_seed=(1 << 64)-1, Z=1, A=2, mode=0, K=4,
                        table_path=tables, config_file=settings,
                        hadronization_config_file=settings, dis_cuts_config_file=settings)

            def generated(cmd):
                self.assertEqual(cmd[cmd.index("--seed")+1], str(args["base_seed"]))
                self.assertEqual(cmd[cmd.index("--first-event-id")+1], "7")
                (root / "events" / "event_00000007.meta.json").write_text(json.dumps({
                    "reproducibility": {"policy": cli.SEED_POLICY,
                        "master_seed": str(args["base_seed"]), "first_event_id": 7,
                        "streams": {"hard_pythia": 123}}}))

            with patch.object(cli, "run", side_effect=generated) as run, \
                 patch.object(cli, "executable_digest", return_value="binary1"):
                cli.ehijing_task(**args)
                cli.ehijing_task(**args)
                self.assertEqual(run.call_count, 1)
                record = json.loads((root / "manifest.jsonl").read_text())
                self.assertEqual(record["effective_seeds"]["hard_pythia"], 123)
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.ehijing_task(**{**args, "base_seed": 42})
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.ehijing_task(**{**args, "nevents": 3, "base_seed": 42})
                settings.write_text("changed")
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.ehijing_task(**args)
                settings.write_text("fixture")
                (tables / "Qs.dat").write_text("changed table")
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.ehijing_task(**args)

    def test_legacy_marker_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / ".done"
            marker.write_text("ok")
            with self.assertRaisesRegex(ValueError, "no seed provenance"):
                cli.completed_request(marker, root / "missing.json", {})

    def test_smash_seed_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "event_00000007.oscar"
            settings, profile = root / "config.yaml", root / "profile.dat"
            for file in [event, settings, profile]:
                file.write_text("fixture")
            args = dict(run_dir=root, event_file=event, cfg_path=settings,
                        profile_rec={"id": "p", "relpath": "profile.dat"}, profiles_root=root,
                        nreplicas=2, base_seed=(1 << 64)-1)
            with patch.object(cli, "run") as run, \
                 patch.object(cli, "executable_digest", return_value="binary1"):
                cli.smash_physical_event_task(**args)
                cmd = run.call_args.args[0]
                expected = cli.hash_seed("smash", args["base_seed"], "event_00000007", "p")
                self.assertIn(f"General: {{ Randomseed: {expected}, Nevents: 2 }}", cmd)
                cli.smash_physical_event_task(**args)
                self.assertEqual(run.call_count, 1)
                with self.assertRaisesRegex(ValueError, "different seeds"):
                    cli.smash_physical_event_task(**{**args, "nreplicas": 3})

    def test_slurm_seed_forwarding(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_dir = root / "bin"
            binary_dir.mkdir()
            sbatch = binary_dir / "sbatch"
            sbatch.write_text('#!/bin/sh\ncat >> "$CAPTURE"\nprintf "12345\\n"\n')
            sbatch.chmod(0o755)
            capture = root / "submitted.sh"
            environment = {"PATH": str(binary_dir) + os.pathsep + os.environ["PATH"],
                           "USER": "testuser", "PROJECT_ROOT": str(repo), "EXPERIMENT": "hermes",
                           "SLURM_CONFIG": str(root / "no-cluster-config"),
                           "OUTPUT_HOST": str(root / "output"), "RUN_DIR_HOST": str(root / "output"),
                           "RUN_DIR": str(root / "run"), "CAPTURE": str(capture),
                           "SEED": "00018446744073709551615"}
            for name in ["ehijing_submit.sh", "smash_submit.sh"]:
                script = repo / "slurm-scripts" / name
                capture.write_text("")
                result = subprocess.run(["bash", str(script)], env=environment, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                submitted = capture.read_text()
                self.assertIn("--seed 18446744073709551615", submitted)
                for invalid in ["-1", "18446744073709551616"]:
                    result = subprocess.run(["bash", str(script)],
                        env={**environment, "SEED": invalid}, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(capture.read_text(), submitted, "Invalid seed submitted a job")


if __name__ == "__main__":
    unittest.main()
