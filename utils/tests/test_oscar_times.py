"""Integration checks for cluster time processing and local YODA-only plotting."""

import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLOT_DIR = ROOT / "analysis/scripts/cross_section_profile_comparison/times_vs_zh"
sys.path.insert(0, str(PLOT_DIR))
from plot_times_vs_zh import BASE, load_sample, plot_samples, read_profiles

COLUMNS = "t x y z mass p0 px py pz pdg ID charge prod_time form_time xsecfac prod_time_status"


class OscarTimesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="electra-times-build-")
        cls.executable = Path(cls.build.name) / "analyze_oscar_output"
        subprocess.run(["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-pedantic",
                        str(ROOT / "utils/analyze_oscar_output.cpp"), "-o", str(cls.executable)],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-times-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.events = self.root / "ehijing/events"
        self.events.mkdir(parents=True)
        self.meta = self.root / "metadata.jsonl"
        self.oscar = self.events / "charged.oscar"
        self.output = self.root / "multiplicities.yoda"
        self.record = {"event": 0, "Z": 54, "A": 131, "xB": 0.1, "Q2": 2, "y": 0.5, "nu": 10,
                       "P4": [0, 0, 0, 1], "q4": [0, 0, math.sqrt(102), 10]}

    def particle(self, pdg=211, zh=0.25, production=1, formation=5, status=1, backward=False):
        energy = zh * self.record["nu"]
        mass = {211: 0.139, 321: 0.494, 2212: 0.938}.get(abs(pdg), 0.139)
        pz = math.sqrt(energy**2 - mass**2) * (-1 if backward else 1)
        return f"0 0 0 0 {mass} {energy:.17g} 0 0 {pz:.17g} {pdg} 0 1 {production} {formation} 0 {status}"

    def fixture(self, events):
        metadata, blocks = [], [f"#!OSCAR2013 particle_lists {COLUMNS}\n"]
        for event, rows in enumerate(events):
            metadata.append(json.dumps(dict(self.record, event=event)))
            blocks.append(f"# event {event} out {len(rows)}\n" + "\n".join(rows) + f"\n# event {event} end 0\n")
        self.meta.write_text("\n".join(metadata))
        self.oscar.write_text("".join(blocks))

    def execute(self, *options, success=True):
        result = subprocess.run([str(self.executable), "--meta", str(self.meta),
                                 "--out", str(self.output), *options, str(self.oscar)],
                                capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_pooled_unit_hadron_weights_and_native_raw_moments(self):
        first = [self.particle(production=0, formation=2)]
        second = [self.particle(pdg, production=t, formation=t + 2)
                  for pdg, t in zip((-211, 321, -321, 2212, -2212), (2, 4, 6, 8, 10))]
        second += [self.particle(111, production=100), self.particle(status=0, production=100),
                   self.particle(2212, status=2, production=100)]
        self.fixture([first, second, []])
        self.execute()
        rows, annotations = load_sample(self.output)
        self.assertEqual(rows[1]["count"], 6)
        self.assertEqual(rows[1]["production_mean_fm_c"], 5)
        self.assertEqual(rows[1]["formation_mean_fm_c"], 7)
        self.assertTrue(math.isnan(rows[0]["production_mean_fm_c"]))
        profiles = read_profiles(self.output)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(self.output.read_text().count("BEGIN YODA_HISTO1D_V2 "), 150)
        raw = profiles[f"{BASE}/production_time_charged"]["bins"][1]
        self.assertEqual(raw, (0.2, 0.3, 6, 6, 1.5, 0.375, 30, 220, 6))
        self.assertEqual(annotations["UnavailableProduction"], "1")
        self.assertEqual(annotations["ExcludedSpectators"], "1")
        self.assertEqual(annotations["EventsSeen"], "3")

    def test_boundaries_signed_times_and_native_flows(self):
        self.fixture([[self.particle(zh=0.3, production=-2, formation=0),
                       self.particle(zh=1.2), self.particle(zh=1.3)]])
        self.execute()
        rows, _ = load_sample(self.output)
        self.assertEqual(rows[2]["count"], 1)
        self.assertEqual(rows[2]["production_mean_fm_c"], -2)
        self.assertEqual(rows[2]["formation_mean_fm_c"], 0)
        self.assertEqual(rows[-1]["count"], 1)
        self.assertIn("Overflow\tOverflow\t1.00000000000000000e+00", self.output.read_text())

    def test_named_columns_and_parent_event_id(self):
        self.record["event"] = 42
        self.fixture([[self.particle()]])
        self.meta.write_text(json.dumps(self.record, indent=2))
        directory = self.events / "event_00000042"
        directory.mkdir()
        destination = directory / "particle_lists.oscar"
        self.oscar.rename(destination)
        self.oscar = destination
        self.oscar.write_text(self.oscar.read_text().replace("# event 0 out", "# event 0 ensemble 0 out")
                              .replace("# event 0 end", "# event 0 ensemble 0 end"))
        self.execute()
        self.assertEqual(load_sample(self.output)[0][1]["count"], 1)
        self.oscar.write_text("#!OSCAR2013 particle_lists t x y z mass p0 px py pz pdg ID charge form_time prod_time prod_time_status\n"
                              "# event 0 out 1\n0 0 0 0 0.139 2.5 0 0 2.49 211 0 1 7 0 1\n# event 0 end 0\n")
        self.execute()
        self.assertEqual(load_sample(self.output)[0][1]["formation_mean_fm_c"], 7)

    def test_invalid_times_headers_events_and_duplicate_metadata(self):
        self.fixture([[self.particle(production="nan")]])
        self.assertIn("Non-finite available", self.execute(success=False).stderr)
        self.fixture([[self.particle()]])
        source = self.oscar.read_text()
        for bad, message in ((source.replace("end 0", "out 0"), "Multiple out blocks"),
                             (source.replace("out 1", "out 2"), "particle count"),
                             (source.replace("# event 0 end 0", ""), "Unterminated")):
            self.oscar.write_text(bad)
            self.assertIn(message, self.execute(success=False).stderr)
        self.oscar.write_text(source)
        self.meta.write_text(self.meta.read_text() + "\n" + self.meta.read_text())
        self.assertIn("Duplicate metadata", self.execute(success=False).stderr)

    def test_source_protection_and_duplicate_inputs(self):
        self.fixture([[self.particle()]])
        self.assertIn("Duplicate OSCAR", self.execute(str(self.oscar), success=False).stderr)
        self.output = self.oscar
        self.assertIn("not overwrite", self.execute(success=False).stderr)

    def test_legacy_and_smash_columns_still_write_all_objects(self):
        self.fixture([[self.particle()]])
        source = self.oscar.read_text()
        # A named SMASH profile start must not be interpreted as a known production reference.
        self.oscar.write_text(source.replace("prod_time ", "begin_form_time ")
                              .replace("prod_time_status", "missing_status"))
        self.execute()
        self.assertEqual(self.output.read_text().count("BEGIN YODA_HISTO1D_V2 "), 150)
        profiles = read_profiles(self.output)
        profile = profiles[f"{BASE}/production_time_charged"]
        self.assertEqual(profile["annotations"]["TimeColumns"], "unavailable")
        self.assertTrue(all(row[2] == 0 for row in profile["bins"]))
        with self.assertRaisesRegex(ValueError, "unavailable or partial"):
            load_sample(self.output)
        # Original twelve-column, headerless files remain valid for multiplicities.
        self.oscar.write_text("# event 0 out 1\n" + " ".join(self.particle().split()[:12]) + "\n# event 0 end 0\n")
        self.execute()
        self.assertEqual(self.output.read_text().count("BEGIN YODA_PROFILE1D_V2 "), 2)

    def test_partial_time_columns_are_explicit_and_not_plotted(self):
        self.fixture([[self.particle()], [self.particle(production=3)]])
        source = self.oscar.read_text()
        marker = "# event 1 out"
        first, second = source.split(marker)
        legacy_header = "#!OSCAR2013 particle_lists " + COLUMNS.replace("prod_time_status", "unknown_status") + "\n"
        self.oscar.write_text(first + legacy_header + marker + second)
        self.execute()
        profile = read_profiles(self.output)[f"{BASE}/production_time_charged"]
        self.assertEqual(profile["annotations"]["TimeColumns"], "partial")
        self.assertEqual(profile["annotations"]["TimeColumnsAvailableEvents"], "1")
        self.assertEqual(profile["annotations"]["TimeColumnsMissingEvents"], "1")
        self.assertEqual(profile["bins"][1][2], 1)
        with self.assertRaisesRegex(ValueError, "unavailable or partial"):
            load_sample(self.output)

    def test_existing_hermes_selections_match_bin_by_bin(self):
        self.fixture([[self.particle(pdg, zh=z, backward=backward)
                       for pdg in (211, -211, 321, -321, 2212, -2212)
                       for z in (0.15, 0.25, 0.35, 0.75, 1.2) for backward in (False, True)]])
        self.execute()
        time_counts = [row["count"] for row in load_sample(self.output)[0]]
        usual = self.root / "multiplicities.yoda"
        subprocess.run([str(self.executable), "--meta", str(self.meta), "--out", str(usual), str(self.oscar)],
                       check=True, capture_output=True)
        counts = [0.0] * 9
        selected = False
        index = 0
        for line in usual.read_text().splitlines():
            if line.startswith("BEGIN "):
                selected = "/HERMES_2007/zh/counts_" in line and not line.endswith("_pi0")
                index = 0
            elif selected and line and line[0].isdigit():
                counts[index] += float(line.split()[2])
                index += 1
        self.assertEqual(time_counts, counts)

    def test_dis_momentum_acceptance_and_target_selection(self):
        self.fixture([[self.particle(), self.particle(backward=True), self.particle(zh=0.15)]])
        self.execute()
        self.assertEqual(sum(row["count"] for row in load_sample(self.output)[0]), 1)
        self.record.update(Z=1, A=2)
        self.fixture([[self.particle()]])
        self.execute()
        self.assertEqual(load_sample(self.output)[0][1]["count"], 1)
        self.execute("--hermes-acceptance", "rectangular")
        self.assertEqual(sum(row["count"] for row in load_sample(self.output)[0]), 0)
        for key, value in (("Q2", 1), ("y", 0), ("y", 0.85), ("nu", 6)):
            record = dict(self.record, **{key: value})
            self.meta.write_text(json.dumps(record))
            self.execute()
            self.assertEqual(sum(row["count"] for row in load_sample(self.output)[0]), 0)

    def test_slurm_combined_output_and_uniform_axis(self):
        self.fixture([[self.particle()]])
        manifest = self.root / "files.txt"
        manifest.write_text(str(self.oscar) + "\n")
        batch = self.root / "batch.sh"
        sbatch = self.root / "sbatch"
        sbatch.write_text('#!/bin/bash\ncat > "$CAPTURE_BATCH"\necho 123\n')
        sbatch.chmod(0o755)
        env = {key: value for key, value in os.environ.items() if not key.startswith("ZH_")}
        env.update(PATH=f"{self.root}:{env['PATH']}", CAPTURE_BATCH=str(batch),
                   SLURM_CONFIG=str(self.root / "no-cluster.env"))
        args = ["bash", str(ROOT / "slurm-scripts/analysis_submit.sh"), "RUN_ID=test",
                f"RUN_DIR={self.root}", f"ANALYZER={self.executable}",
                f"META_FILE={self.meta}", f"SLURM_CONFIG={self.root}/no-cluster.env",
                "--skip-indexing", f"FILE_LIST={manifest}", "ZH_NBINS=2"]
        submitted = subprocess.run(args, env=env, capture_output=True, text=True)
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        executed = subprocess.run(["bash", str(batch)], env=env, capture_output=True, text=True)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        combined = self.root / "ehijing/analysis/multiplicities.yoda"
        rows, _ = load_sample(combined)
        self.assertEqual(combined.read_text().count("BEGIN YODA_HISTO1D_V2 "), 150)
        self.assertEqual(len(rows), 2)
        for row, (low, high) in zip(rows, [(0.05, 0.5), (0.5, 0.95)]):
            self.assertAlmostEqual(row["zh_low"], low)
            self.assertAlmostEqual(row["zh_high"], high)

    def test_mismatched_annotations_and_missing_profiles_fail(self):
        self.fixture([[self.particle()]])
        self.execute()
        other = self.root / "other.yoda"
        other.write_text(self.output.read_text().replace("Acceptance: none", "Acceptance: rectangular"))
        with self.assertRaisesRegex(ValueError, "different Acceptance"):
            plot_samples([self.output, other], ["one", "two"], self.root)
        other.write_text("BEGIN YODA_HISTO1D_V2 /old\nEND YODA_HISTO1D_V2\n")
        with self.assertRaisesRegex(ValueError, "missing"):
            load_sample(other)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Matplotlib required for rendered output checks")
    def test_plot_wrapper_needs_only_yoda(self):
        self.fixture([[self.particle(), self.particle(zh=0.35, production=3)]])
        self.execute()
        self.oscar.unlink()
        self.meta.unlink()
        config = self.root / "plots.json"
        config.write_text(json.dumps({"samples": [{"label": "Source", "yoda": self.output.name}]}))
        output = self.root / "plots"
        env = dict(os.environ, PYTHON=sys.executable, MPLCONFIGDIR=str(self.root / "mpl-cache"))
        result = subprocess.run(["bash", str(ROOT / "analysis/run_cross_section_profile_comparison_times_vs_zh.sh"),
                                 "--config", str(config), "--output-dir", str(output)],
                                cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output / "charged_hadron_times_vs_zh.pdf").read_bytes().startswith(b"%PDF"))
        self.assertTrue((output / "charged_hadron_times_vs_zh.png").read_bytes().startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
