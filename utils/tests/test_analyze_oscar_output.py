"""OSCAR analyzer integration checks; run with python3 -m unittest discover -s utils/tests."""

import json
import importlib.util
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/scripts"))
from hermes2007 import load_ratio, spectrum
# Independent reference from HEPData 10.17182/hepdata.13387.v1, Tables 4, 1, 8.
REFERENCE_EDGES = {
    "zh": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.3],
    "nu": [4, 6, 8, 10, 12, 14, 16, 18, 20, 23.5],
    "Q2": [1, 1.5, 2, 3, 4, 5, 6, 8, 25],
}


def read_histograms(path):
    histograms = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("BEGIN YODA_HISTO1D_V2 "):
            current = {"bins": []}
            histograms[line.split()[2]] = current
        elif line.startswith(("BEGIN ", "END ")):
            current = None
        elif current is not None and line and line[0].isdigit():
            current["bins"].append(tuple(map(float, line.split())))
        elif current is not None and line.startswith(("Underflow", "Overflow")):
            current[line.split()[0]] = tuple(map(float, line.split()[2:]))
    return histograms


class OscarAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="electra-oscar-build-")
        cls.executable = Path(cls.build.name) / "analyze_oscar_output"
        subprocess.run(
            ["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-pedantic",
             str(ROOT / "utils/analyze_oscar_output.cpp"), "-o", str(cls.executable)],
            check=True, capture_output=True, text=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-oscar-test-")
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        self.events = self.run_dir / "ehijing/events"
        self.events.mkdir(parents=True)
        self.meta = self.run_dir / "ehijing/DISKinematics.meta.jsonl"
        self.oscar = self.events / "sample.oscar"
        self.output = self.run_dir / "output.yoda"

    def fixture(self, events):
        """Each tuple specifies (nu, Q2, list of z_h values) for a hand-written event."""
        metadata, blocks = [], []
        for event, (nu, q2, zs) in enumerate(events):
            metadata.append(json.dumps({
                "event": event, "Z": 1, "A": 1, "xB": 0.1, "Q2": q2,
                "y": 0.5, "nu": nu, "P4": [0, 0, 0, 1],
                "q4": [0, 0, math.sqrt(nu * nu + q2), nu],
            }))
            blocks.append(f"# event {event} out {len(zs)}\n")
            for z in zs:
                blocks.append(f"0 0 0 0 0.139 {z * nu:.17g} 0.2 0 0 211 0 1\n")
            blocks.append(f"# event {event} end 0\n")
        self.meta.write_text("\n".join(metadata) + "\n")
        self.oscar.write_text("".join(blocks))

    def analyze(self, *options):
        subprocess.run(
            [str(self.executable), "--meta", str(self.meta), "--frame", "LAB",
             "--out", str(self.output), *options, str(self.oscar)],
            check=True, capture_output=True, text=True,
        )
        return read_histograms(self.output)

    def test_reference_edges_and_density_in_each_variable_width_bin(self):
        for variable, histogram in (
            ("zh", "/ELECTRA_MC_2026_DNDZ/dN_dz_pip"),
            ("nu", "/ELECTRA_MC_2026_DNDNU/dN_dnu_pip"),
            ("Q2", "/ELECTRA_MC_2026_DNDQ2/dN_dQ2_pip"),
        ):
            with self.subTest(variable=variable):
                edges = REFERENCE_EDGES[variable]
                centers = [(lo + hi) / 2 for lo, hi in zip(edges, edges[1:])]
                events = [(x if variable == "nu" else 10,
                           x if variable == "Q2" else 2,
                           [x if variable == "zh" else 0.25]) for x in centers]
                events.append((10, 2, []))  # Empty matched events still normalize all spectra.
                self.fixture(events)
                histograms = self.analyze()
                self.assertEqual(len(histograms), 150)
                bins = histograms[histogram]["bins"]
                self.assertEqual([(b[0], b[1]) for b in bins], list(zip(edges, edges[1:])))
                for row in bins:
                    density = 1 / (len(events) * (row[1] - row[0]))
                    self.assertAlmostEqual(row[2] / density, 1, places=5)
                    self.assertAlmostEqual(row[3] / density**2, 1, places=5)
                    self.assertEqual(row[6], 1)
                if variable == "Q2":
                    sliced = histograms["/ELECTRA_MC_2026_DNDQ2DZ/dN_dQ2dz_pip_zh0p2_0p3"]["bins"]
                    for inclusive, sliced_bin in zip(bins, sliced):
                        self.assertAlmostEqual(sliced_bin[2] / inclusive[2], 10, places=4)

    def test_boundaries_flows_and_inclusive_fills_outside_fixed_slices(self):
        self.fixture([(4, 1, [0.1]), (20, 8, [0.9]), (23.5, 25, [1.3]), (3, 0.5, [0.05])])
        histograms = self.analyze("--pt-max", "0.1")  # pT overflows must not veto inclusive fills.
        for name in ("/ELECTRA_MC_2026_DNDZ/dN_dz_pip",
                     "/ELECTRA_MC_2026_DNDNU/dN_dnu_pip",
                     "/ELECTRA_MC_2026_DNDQ2/dN_dQ2_pip"):
            hist = histograms[name]
            self.assertEqual(hist["bins"][0][6], 1)
            self.assertEqual(hist["bins"][-1][6], 1)
            self.assertEqual(hist["Underflow"][-1], 1)
            self.assertEqual(hist["Overflow"][-1], 1)
            self.assertEqual(hist["Underflow"][0], 0.25)
            self.assertEqual(hist["Overflow"][0], 0.25)

    def test_uniform_cli_override_and_slurm_defaults(self):
        self.fixture([(10, 2, [0.25])])
        bins = self.analyze("--zh-min", "0", "--zh-max", "1", "--zh-nbins", "2")["/ELECTRA_MC_2026_DNDZ/dN_dz_pip"]["bins"]
        self.assertEqual([(b[0], b[1]) for b in bins], [(0, 0.5), (0.5, 1)])
        self.assertEqual(bins[0][2:4], (2, 4))

        manifest = self.run_dir / "manifest.txt"
        manifest.write_text(str(self.oscar) + "\n")
        batch = self.run_dir / "batch.sh"
        sbatch = self.run_dir / "sbatch"
        sbatch.write_text('#!/bin/bash\ncat > "$CAPTURE_BATCH"\necho 123\n')
        sbatch.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith("ZH_")}
        env.update(PATH=f"{self.run_dir}:{env['PATH']}", CAPTURE_BATCH=str(batch),
                   SLURM_CONFIG=str(self.run_dir / "no-cluster.env"))
        args = ["bash", str(ROOT / "slurm-scripts/analysis_submit.sh"), "RUN_ID=test",
                f"RUN_DIR={self.run_dir}", f"ANALYZER={self.executable}",
                f"SLURM_CONFIG={self.run_dir}/no-cluster.env", "--skip-indexing",
                f"FILE_LIST={manifest}", f"OUT={self.output}"]
        for options in ([], ["ZH_NBINS=2"]):
            with self.subTest(slurm_options=options):
                submitted = subprocess.run(args + options, env=env, capture_output=True, text=True)
                self.assertEqual(submitted.returncode, 0, submitted.stdout + submitted.stderr)
                executed = subprocess.run(["bash", str(batch)], env=env, capture_output=True, text=True)
                self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
                bins = read_histograms(self.output)["/ELECTRA_MC_2026_DNDZ/dN_dz_pip"]["bins"]
                if options:
                    self.assertEqual([(b[0], b[1]) for b in bins], [(0.05, 0.5), (0.5, 0.95)])
                else:
                    edges = REFERENCE_EDGES["zh"]
                    self.assertEqual([(b[0], b[1]) for b in bins], list(zip(edges, edges[1:])))

    def hermes_fixture(self, events, direction=-1):
        """Physical on-shell hadrons; event tuples are (nu, Q2, y, [particle specs])."""
        records, lines = [], []
        for event, (nu, q2, y, particles) in enumerate(events):
            beam = 27.6
            transverse2 = q2 * (1 - nu / beam) - q2**2 / (4 * beam**2)
            q = [0, -math.sqrt(max(0, transverse2)), direction * (nu + q2 / (2 * beam)), nu]
            records.append(json.dumps({"event": event, "Z": 1, "A": 1,
                "xB": q2 / (2 * 0.938 * nu), "Q2": q2, "y": y, "nu": nu,
                "P4": [0, 0, 0, 0.938], "q4": q}))
            lines.append(f"# event {event} out {len(particles)}\n")
            for spec in particles:
                pdg, momentum, angle = spec
                mass = 0.938 if abs(pdg) == 2212 else 0.494 if abs(pdg) == 321 else 0.139
                energy = math.sqrt(momentum**2 + mass**2)
                py = momentum * math.sin(angle)
                pz = direction * momentum * math.cos(angle)
                lines.append(f"0 0 0 0 {mass} {energy:.17g} 0 {py:.17g} {pz:.17g} {pdg} 0 1\n")
            lines.append(f"# event {event} end 0\n")
        self.meta.write_text("\n".join(records) + "\n")
        self.oscar.write_text("".join(lines))

    def test_hermes_column_selections_and_empty_dis_denominators(self):
        pion = (211, 2.8, 0.08)
        self.hermes_fixture([(5, 2, 0.2, [pion, pion]), (7, 2, 0.3, [pion]),
                             (7.5, 2, 0.3, [])])
        hist = self.analyze()
        self.assertEqual(hist["/HERMES_2007/nu/DIS"]["bins"][0][2], 1)
        self.assertEqual(hist["/HERMES_2007/nu/DIS"]["bins"][1][2], 2)
        nu = hist["/HERMES_2007/nu/multiplicity_pip"]["bins"]
        self.assertEqual(nu[0][2], 2)
        self.assertEqual(nu[1][2], 0.5)
        self.assertEqual(nu[1][3], 0.25)  # SEM of event counts [1, 0].
        q2 = hist["/HERMES_2007/Q2/multiplicity_pip"]["bins"]
        self.assertEqual(q2[2][2], 0.5)  # nu=5 does not enter this sample.
        self.assertTrue(all(b[2] == 2 for b in hist["/HERMES_2007/zh/DIS"]["bins"]))
        self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/zh/counts_pip"]["bins"]), 1)

    def test_hermes_momentum_xf_and_dis_cuts(self):
        particles = [(211, 2, 0), (211, 15, 0), (2212, 1.9, 0),
                     (211, 3, math.pi), (211, 3, 0), (321, 3, 0), (2212, 3, 0)]
        self.hermes_fixture([(10, 2, 0.4, particles), (10, 1, 0.4, particles),
                             (10, 2, 0.85, particles), (10, 16, 0.4, particles)])
        hist = self.analyze()
        self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/nu/DIS"]["bins"]), 1)
        for species in ("pip", "kp", "p"):
            self.assertEqual(sum(b[2] for b in hist[f"/HERMES_2007/nu/counts_{species}"]["bins"]), 1)

    def test_hermes_low_z_only_enters_zh_and_acceptance_is_optional(self):
        self.hermes_fixture([(20, 2, 0.75, [(211, 2.8, 0)])])
        hist = self.analyze()
        self.assertEqual(hist["/HERMES_2007/zh/counts_pip"]["bins"][0][2], 1)
        self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/nu/counts_pip"]["bins"]), 0)
        hist = self.analyze("--hermes-acceptance", "rectangular")
        self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/zh/counts_pip"]["bins"]), 0)
        for direction in (-1, 1):
            self.hermes_fixture([(10, 2, 0.4, [(211, 3, 0.08)]),
                                 (10, 12, 0.4, [(211, 3, 0.08)])], direction)
            hist = self.analyze("--hermes-acceptance", "rectangular",
                                "--hermes-beam-direction", "-z" if direction < 0 else "+z")
            self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/nu/DIS"]["bins"]), 1)
            self.assertEqual(sum(b[2] for b in hist["/HERMES_2007/nu/counts_pip"]["bins"]), 1)

    def test_hermes_ratio_loader_uses_bin_denominators_and_preserves_zero_yields(self):
        pion = (211, 3, 0.08)
        self.hermes_fixture([(10, 2, 0.4, [pion, pion]), (10, 2, 0.4, []),
                             (5, 2, 0.2, [pion])])
        self.analyze()
        deuterium = self.run_dir / "deuterium.yoda"
        deuterium.write_text(self.output.read_text())
        self.hermes_fixture([(10, 2, 0.4, [pion]), (10, 2, 0.4, [pion]), (5, 2, 0.2, [])])
        self.analyze()
        x, ratio, error = load_ratio(self.output, deuterium, "nu", "pip")
        self.assertEqual(x, [5, 11])
        self.assertEqual(ratio, [0, 1])
        self.assertAlmostEqual(error[1], 1)
        selected, _ = spectrum(self.output, "nu", "pip")
        self.assertTrue(math.isnan(selected[-1][2]))  # Empty DIS bins remain undefined.
        old_file = self.run_dir / "old.yoda"
        old_file.write_text("BEGIN YODA_HISTO1D_V2 /old\nEND YODA_HISTO1D_V2\n")
        with self.assertRaisesRegex(ValueError, "rerun"):
            load_ratio(old_file, deuterium, "nu", "pip")

    def test_rejects_intermediate_snapshots_and_unterminated_events(self):
        self.fixture([(10, 2, [0.3])])
        for text in ("# event 0 out 0\n# event 0 out 0\n# event 0 end 0\n",
                     "# event 0 out 0\n"):
            self.oscar.write_text(text)
            result = subprocess.run([str(self.executable), "--meta", str(self.meta),
                "--out", str(self.output), str(self.oscar)], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_ratio_loader_rejects_different_selections_and_bin_edges(self):
        self.hermes_fixture([(10, 2, 0.4, [(211, 3, 0.08)])] * 2)
        self.analyze()
        other = self.run_dir / "other.yoda"
        other.write_text(self.output.read_text().replace("Acceptance: none", "Acceptance: rectangular"))
        with self.assertRaisesRegex(ValueError, "metadata differ"):
            load_ratio(other, self.output, "nu", "pip")
        lines = []
        nu_block = False
        for line in self.output.read_text().splitlines():
            if line.startswith("BEGIN "):
                nu_block = "/HERMES_2007/nu/" in line
            if nu_block and line and line[0].isdigit():
                row = line.split()
                if float(row[0]) == 4:
                    row[1] = "5.5"
                    line = "\t".join(row)
            lines.append(line)
        other.write_text("\n".join(lines))
        with self.assertRaisesRegex(ValueError, "bin edges"):
            load_ratio(other, self.output, "nu", "pip")

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Matplotlib is required for rendering")
    def test_fig2_plot_cli_renders_selected_counts(self):
        self.hermes_fixture([(10, 2, 0.4, [(211, 3, 0.08)])] * 2)
        self.analyze()
        config = self.run_dir / "plots.json"
        config.write_text(json.dumps({"nuclei": ["He"], "scenarios": [{"label": "Fixture",
            "deuterium": str(self.output), "nuclei": {"He": str(self.output)}}]}))
        env = dict(os.environ, MPLBACKEND="Agg", MPLCONFIGDIR=str(self.run_dir / "mpl"),
                   XDG_CACHE_HOME=str(self.run_dir / "cache"))
        result = subprocess.run([sys.executable, str(ROOT / "analysis/scripts/plot_hermes_fig2.py"),
            "--config", str(config), "--particles", "pip", "--no-exp",
            "--output-dir", str(self.run_dir / "plots")], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for extension in ("pdf", "png"):
            self.assertGreater((self.run_dir / "plots" / f"RA_fig2.{extension}").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
