"""YAML analyzer integration tests with hand-written events, never event generation."""

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def read_yoda(path):
    objects = {}
    current = None
    table = False
    for line in path.read_text().splitlines():
        if line.startswith("BEGIN "):
            current = {"bins": [], "annotations": {}}
            objects[line.split()[2]] = current
            table = False
        elif line.startswith("END "):
            current = None
        elif current is not None:
            if line.startswith("# xlow"):
                table = True
            elif line.startswith(("Underflow", "Overflow")):
                current[line.split()[0]] = tuple(map(float, line.split()[2:]))
            elif table and line and not line.startswith("#"):
                current["bins"].append(tuple(map(float, line.split())))
            elif not table and ":" in line:
                key, value = line.split(":", 1)
                current["annotations"][key] = value.strip()
    return objects


class YamlOscarAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="electra-yaml-tests-")
        cls.addClassCleanup(cls.build.cleanup)
        # Model a standalone deployment: there is no sibling src/smash checkout.
        source = Path(cls.build.name) / "installed utils"
        source.mkdir()
        for filename in ("CMakeLists.txt", "analyze_oscar_output.cpp", "oscar_analysis.hpp", "build_analysis.sh"):
            shutil.copy2(ROOT / "utils" / filename, source / filename)
        shutil.copytree(ROOT / "utils/cmake", source / "cmake")
        cls.source = source
        cls.executable = source / "analyze_oscar_output"
        cls.dependency_args = []
        if os.environ.get("ELECTRA_YAML_CPP_ARCHIVE"):
            cls.dependency_args = ["--yaml-cpp-archive", os.environ["ELECTRA_YAML_CPP_ARCHIVE"]]
        elif os.environ.get("ELECTRA_YAML_CPP_PREFIX"):
            cls.dependency_args = ["--yaml-cpp-prefix", os.environ["ELECTRA_YAML_CPP_PREFIX"]]
        subprocess.run(["bash", str(source / "build_analysis.sh"), "--jobs", "2", *cls.dependency_args],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-yaml-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.meta = self.root / "metadata.jsonl"
        self.oscar = self.root / "sample.oscar"
        self.output = self.root / "result.yoda"
        self.input = self.root / "analysis.yaml"
        self.config = {
            "version": 1, "name": "CUSTOM", "beam": {"energy": 27.6, "mass": 0.00051099895, "direction": "+z"},
            "frame": "TRF", "species": {"pip": [211]},
            "histograms": [{"name": "zh", "axes": [{"variable": "zh", "edges": [0, 0.5, 1], "density": True}]}],
        }

    def fixture(self, events, times=False):
        """events: (nu, [z or particle overrides], optional metadata overrides)."""
        metadata, lines = [], []
        if times:
            lines += ["#!OSCAR2013 particle_lists t x y z mass p0 px py pz pdg ID charge prod_time form_time prod_time_status\n",
                      "# Units: fm fm fm fm GeV GeV GeV GeV GeV none none none fm/c fm/c none\n"]
        for event, spec in enumerate(events):
            nu, particles, *overrides = spec
            record = {"event": event, "Z": 1, "A": 2, "xB": 0.1, "Q2": 2,
                      "y": nu / 27.6, "nu": nu, "P4": [0, 0, 0, 1], "q4": [0, 0, math.sqrt(nu**2 + 2), nu]}
            if overrides:
                record.update(overrides[0])
            metadata.append(json.dumps(record))
            lines.append(f"# event {event} out {len(particles)}\n")
            for values in particles:
                p = values if isinstance(values, dict) else {"z": values}
                energy = p.get("z", 0.25) * nu
                px = p.get("px", 0)
                pz = math.sqrt(energy**2 - 0.139**2 - px**2)
                lines.append(f"0 0 0 0 0.139 {energy:.17g} {px:.17g} 0 {pz:.17g} "
                             f"{p.get('pdg', 211)} 0 {p.get('charge', 1)}")
                if times:
                    lines.append(f" {p.get('production', 1)} {p.get('formation', 5)} {p.get('status', 1)}")
                lines.append("\n")
            lines.append(f"# event {event} end 0\n")
        self.meta.write_text("\n".join(metadata))
        self.oscar.write_text("".join(lines))

    def run_analysis(self, success=True, config_path=None, extra=()):
        if config_path is None:
            self.input.write_text(json.dumps(self.config))  # JSON is also valid YAML.
            config_path = self.input
        result = subprocess.run([str(self.executable), "--analysis", str(config_path), "--meta", str(self.meta),
                                 "--out", str(self.output), *extra, str(self.oscar)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return read_yoda(self.output) if success else result.stderr

    def test_variable_width_density_zero_hadron_events_and_sem(self):
        self.fixture([(8, [0.25, 0.25, 0.75]), (8, []), (8, [0.25])])
        hist = self.run_analysis()
        dis = hist["/CUSTOM/zh/DIS"]["bins"]
        self.assertEqual([b[2] for b in dis], [3, 3])
        counts = hist["/CUSTOM/zh/counts_pip"]["bins"]
        self.assertEqual([b[2] for b in counts], [3, 1])
        self.assertEqual([b[3] for b in counts], [5, 1])
        multiplicity = hist["/CUSTOM/zh/multiplicity_pip"]["bins"]
        self.assertAlmostEqual(multiplicity[0][2], 2)
        self.assertAlmostEqual(multiplicity[0][3], 4 / 3)
        self.assertAlmostEqual(multiplicity[1][2], 2 / 3)
        self.assertAlmostEqual(multiplicity[1][3], 4 / 9)
        self.assertEqual(hist["/CUSTOM/zh/DIS"]["annotations"]["TargetA"], "2")
        self.assertIn("# YAML |", self.output.read_text())
        self.assertNotIn("HERMES_2007", self.output.read_text())

    def test_three_dimensions_condition_only_on_event_axes(self):
        self.fixture([(5, [0.25, 0.25, 0.75]), (7, []), (7, [0.25]), (9, [0.75])])
        self.config["histograms"][0]["axes"] += [
            {"variable": "nu", "edges": [4, 8, 10]}, {"variable": "pT2", "edges": [0, 0.5, 2], "density": True}]
        hist = self.run_analysis()
        first = "/CUSTOM/zh/nu_bin0/pT2_bin0"
        second = "/CUSTOM/zh/nu_bin1/pT2_bin0"
        self.assertEqual([b[2] for b in hist[first + "/DIS"]["bins"]], [3, 3])
        self.assertEqual([b[2] for b in hist[second + "/DIS"]["bins"]], [1, 1])
        self.assertEqual([b[2] for b in hist[first + "/counts_pip"]["bins"]], [3, 1])
        self.assertEqual(hist[first + "/multiplicity_pip"]["bins"][0][2], 4)
        # Hadron slice without any hadrons still uses all eligible DIS events.
        self.assertEqual(hist["/CUSTOM/zh/nu_bin0/pT2_bin1/DIS"]["bins"][0][2], 3)
        self.assertEqual(hist["/CUSTOM/zh/nu_bin0/pT2_bin1/multiplicity_pip"]["bins"][0][2], 0)
        self.assertEqual(hist[first + "/DIS"]["annotations"]["Slice1"], "nu 4 8")

    def test_event_axis_first_and_multiple_event_axes(self):
        self.fixture([(5, [0.25]), (7, [0.75]), (7, [])])
        self.config["histograms"][0]["axes"] = [
            {"variable": "nu", "edges": [4, 6, 8]}, {"variable": "Q2", "edges": [1, 3, 4]},
            {"variable": "zh", "edges": [0, 0.5, 1]}]
        hist = self.run_analysis()
        for z in (0, 1):
            self.assertEqual([b[2] for b in hist[f"/CUSTOM/zh/Q2_bin0/zh_bin{z}/DIS"]["bins"]], [1, 2])
        self.assertEqual([b[2] for b in hist["/CUSTOM/zh/Q2_bin0/zh_bin1/multiplicity_pip"]["bins"]], [0, 0.5])
        self.assertTrue(math.isnan(hist["/CUSTOM/zh/Q2_bin1/zh_bin0/multiplicity_pip"]["bins"][0][2]))

    def test_cut_overrides_removal_and_strict_bounds(self):
        self.fixture([(5, [0.25]), (6, [0.25]), (7, [0.25]), (8, [0.25])])
        self.config["event_cuts"] = {"nu": {"min": 6, "max": 8}, "Q2": {"min": 2, "min_inclusive": True}}
        self.config["hadron_cuts"] = {"zh": {"min": 0.25}}
        self.config["histograms"] += [{"name": "override", "event_cuts": {"nu": None},
                                       "hadron_cuts": {"zh": {"min": 0.25, "min_inclusive": True}},
                                       "axes": [{"variable": "nu", "min": 4, "max": 10, "bins": 3}]}]
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/DIS"]["bins"][0][2], 1)
        self.assertEqual(hist["/CUSTOM/zh/counts_pip"]["bins"][0][2], 0)
        self.assertEqual([b[2] for b in hist["/CUSTOM/override/counts_pip"]["bins"]], [1, 2, 1])

    def test_weighted_ratio_error_and_weight_opt_in(self):
        self.fixture([(8, [0.25, 0.25], {"weight": 2}), (8, [], {"weight": 1})])
        self.assertIn("weighting: metadata", self.run_analysis(success=False))
        self.config["weighting"] = "metadata"
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/DIS"]["bins"][0][2:4], (3, 5))
        self.assertEqual(hist["/CUSTOM/zh/counts_pip"]["bins"][0][2:4], (4, 16))
        self.assertEqual(hist["/CUSTOM/zh/sum_w2_n_pip"]["bins"][0][2], 8)
        self.assertAlmostEqual(hist["/CUSTOM/zh/multiplicity_pip"]["bins"][0][2], 8 / 3)
        self.assertAlmostEqual(hist["/CUSTOM/zh/multiplicity_pip"]["bins"][0][3], 256 / 81)

    def test_native_profiles_times_status_and_momentum(self):
        self.fixture([(8, [{"z": 0.25, "production": 0, "formation": 2, "px": 0.5},
                           {"z": 0.25, "production": 4, "formation": 8, "px": 1},
                           {"z": 0.25, "status": 0}, {"z": 0.25, "status": 2}])], times=True)
        self.config["histograms"] = [
            {"name": q, "kind": "profile", "quantity": q, "axes": [{"variable": "zh", "edges": [0, 0.5, 1]}]}
            for q in ("prod_time", "form_time", "formation_interval", "pT2")]
        hist = self.run_analysis()
        production = hist["/CUSTOM/prod_time/mean_prod_time_pip"]
        self.assertEqual(production["bins"][0][2:], (2, 2, 0.5, 0.125, 4, 16, 2))
        self.assertEqual(production["annotations"]["UnavailableTimes"], "2")
        self.assertEqual(hist["/CUSTOM/form_time/mean_form_time_pip"]["bins"][0][6], 10)
        self.assertEqual(hist["/CUSTOM/formation_interval/mean_formation_interval_pip"]["bins"][0][6], 6)
        self.assertEqual(hist["/CUSTOM/pT2/mean_pT2_pip"]["bins"][0][6], 1.25)
        self.fixture([(8, [0.25])])
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/prod_time/mean_prod_time_pip"]["bins"][0][2], 0)
        self.assertEqual(hist["/CUSTOM/prod_time/mean_prod_time_pip"]["annotations"]["MissingTimeEvents"], "1")

    def test_species_and_inclusive_charged_hadrons(self):
        self.fixture([(8, [{"pdg": 211}, {"pdg": -211, "charge": -1}, {"pdg": 11, "charge": -1},
                           {"pdg": 111, "charge": 0}, {"pdg": 1000010020, "charge": 1}, {"pdg": 3222}])])
        self.config["species"] = {"charged": {"charge": "nonzero"}, "positive": {"charge": "positive"}, "sigma": [3222]}
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/counts_charged"]["bins"][0][2], 3)
        self.assertEqual(hist["/CUSTOM/zh/counts_positive"]["bins"][0][2], 2)
        self.assertEqual(hist["/CUSTOM/zh/counts_sigma"]["bins"][0][2], 1)

    def test_flows_exact_bin_edges_and_nonuniform_density(self):
        self.fixture([(8, [0.1, 0.25, 0.5, 0.75, 1])])
        self.config["histograms"][0]["axes"] = [{"variable": "zh", "edges": [0.25, 0.5, 1], "density": True}]
        hist = self.run_analysis()
        raw = hist["/CUSTOM/zh/counts_pip"]
        self.assertEqual([b[2] for b in raw["bins"]], [1, 2])
        self.assertEqual(raw["Underflow"][0], 1)
        self.assertEqual(raw["Overflow"][0], 1)
        self.assertEqual([b[2] for b in hist["/CUSTOM/zh/multiplicity_pip"]["bins"]], [4, 4])

    def test_yaml_anchors_and_all_supplied_configs_load(self):
        self.fixture([(10, [0.25]), (10, [])])
        for path in sorted((ROOT / "analysis/configs").glob("*_analysis_input.yaml")):
            with self.subTest(path=path.name):
                self.assertTrue(self.run_analysis(config_path=path))

    def test_rebuild_script_picks_up_source_changes(self):
        source = self.source / "analyze_oscar_output.cpp"
        source.write_text(source.read_text().replace("YAML-defined analysis", "Rebuilt YAML-defined analysis", 1))
        # Older make versions compare whole seconds. Model an edit after the
        # previous compile without a timing-dependent sleep in this test.
        for compiled in (self.source / "build/analysis").rglob("analyze_oscar_output.cpp.o"):
            previous = compiled.stat()
            os.utime(compiled, (previous.st_atime, previous.st_mtime - 2))
        subprocess.run(["bash", str(self.source / "build_analysis.sh"), "--jobs", "2", *self.dependency_args],
                       cwd=self.root, check=True, capture_output=True, text=True)
        help_result = subprocess.run([str(self.executable), "--help"], capture_output=True, text=True, check=True)
        self.assertIn("Rebuilt YAML-defined analysis", help_result.stderr)

    def test_cached_dependency_rebuild_works_without_archive(self):
        if self.dependency_args and self.dependency_args[0] == "--yaml-cpp-prefix":
            self.skipTest("Explicit existing-prefix mode does not populate a source cache")
        env = {key: value for key, value in os.environ.items()
               if key not in ("ELECTRA_YAML_CPP_ARCHIVE", "ELECTRA_YAML_CPP_PREFIX")}
        result = subprocess.run(["bash", str(self.source / "build_analysis.sh"), "--jobs", "2"],
                                cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Downloading yaml-cpp", result.stdout)

    def test_clas_published_slices_keep_separate_dis_denominators(self):
        events = []
        for nu in (2.8, 3.4, 3.9):
            for q2 in (1.1, 1.5, 2.5):
                metadata = {"Q2": q2, "y": nu / 5.014,
                            "q4": [0, 0, math.sqrt(nu**2 + q2), nu]}
                events.extend([(nu, [.25], metadata), (nu, [], metadata)])
        events.append((4.23, [.25]))  # Inside the global nu cut, outside all published nu slices.
        self.fixture(events)
        hist = self.run_analysis(config_path=ROOT / "analysis/configs/clas_2021_analysis_input.yaml")
        for iq in range(3):
            for inu in range(3):
                base = f"/CLAS_2021/zh_Q2_nu/Q2_bin{iq}/nu_bin{inu}"
                dis = hist[base + "/DIS"]["bins"]
                self.assertEqual([bin_[2] for bin_ in dis], [2] * 10)
                counts = hist[base + "/counts_pip"]["bins"]
                self.assertEqual(sum(bin_[2] for bin_ in counts), 1)
                multiplicity = hist[base + "/multiplicity_pip"]["bins"][2]
                self.assertAlmostEqual(multiplicity[2], 5)
                self.assertAlmostEqual(multiplicity[3], 25)

    def test_hermes_counts_match_legacy_on_common_phase_space(self):
        self.fixture([(5, [0.6]), (7, [0.3, 0.4, 0.8]), (10, []), (18, [0.2, 0.5])])
        yaml_hist = self.run_analysis(config_path=ROOT / "analysis/configs/hermes_2007_analysis_input.yaml")
        result = subprocess.run([str(self.executable), "--meta", str(self.meta), "--out", str(self.output),
                                 str(self.oscar)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        legacy = read_yoda(self.output)
        for axis in ("zh", "nu", "Q2"):
            for quantity in ("DIS", "counts_pip"):
                path = f"/HERMES_2007/{axis}/{quantity}"
                with self.subTest(path=path):
                    self.assertEqual([b[:4] for b in yaml_hist[path]["bins"]], [b[:4] for b in legacy[path]["bins"]])

    def test_optional_lepton_and_hadron_angular_cuts(self):
        self.fixture([(8, [{"z": 0.5}, {"z": 0.5, "px": 1}]), (8, [])])
        self.config["hadron_cuts"] = {"theta": {"max": 0.05}}
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/counts_pip"]["bins"][1][2], 1)
        self.config["event_cuts"] = {"lepton_abs_theta_y": {"min": 0.04}}
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/DIS"]["bins"][1][2], 0)
        # A massive muon beam uses the configured mass, with the opposite axis.
        self.config["beam"] = {"energy": 100, "mass": 0.1056583755, "direction": "-z"}
        self.config["event_cuts"] = {"lepton_E": {"min": 90, "max": 94}}
        hist = self.run_analysis()
        self.assertEqual(hist["/CUSTOM/zh/DIS"]["bins"][1][2], 2)

    def test_trf_kinematics_are_invariant_under_longitudinal_input_boost(self):
        self.fixture([(8, [{"z": 0.5, "px": 1}]), (8, [])])
        self.config["hadron_cuts"] = {"p": {"min": 3, "max": 4.5}, "xF": {"min": 0}}
        self.config["histograms"] += [{"name": "pt", "axes": [{"variable": "pT2", "edges": [0, 0.5, 2]}]}]
        original = self.run_analysis()
        def boost(p):
            px, py, pz, energy = p
            return [px, py, 1.25 * (pz + 0.6 * energy), 1.25 * (energy + 0.6 * pz)]
        records = [json.loads(line) for line in self.meta.read_text().splitlines()]
        for record in records:
            record["P4"] = boost(record["P4"])
            record["q4"] = boost(record["q4"])
        self.meta.write_text("\n".join(map(json.dumps, records)))
        lines = []
        for line in self.oscar.read_text().splitlines():
            if not line.startswith("#"):
                row = line.split()
                p = boost([float(row[i]) for i in (6, 7, 8, 5)])
                for i, v in zip((6, 7, 8, 5), p):
                    row[i] = f"{v:.17g}"
                line = " ".join(row)
            lines.append(line)
        self.oscar.write_text("\n".join(lines))
        transformed = self.run_analysis()
        for path in ("/CUSTOM/zh/counts_pip", "/CUSTOM/pt/counts_pip"):
            self.assertEqual([b[2:4] for b in original[path]["bins"]], [b[2:4] for b in transformed[path]["bins"]])

    def test_validation_and_protection_against_input_overwrite(self):
        self.fixture([(8, [0.25])])
        base = json.dumps(self.config)
        for change, message in (
            (lambda c: c.update(typo=True), "unknown key"),
            (lambda c: c.update(event_cuts={"zh": {"min": 0.2}}), "event variable"),
            (lambda c: c["histograms"][0]["axes"][0].update(edges=[0, 0]), "strictly increasing"),
            (lambda c: c["histograms"][0].update(species=["missing"]), "Unknown or duplicate species"),
            (lambda c: c["histograms"][0].update(kind="unknown"), "kind must"),
            (lambda c: c["histograms"][0]["axes"][0].update(edges=[0, float("nan")]), "finite"),
        ):
            self.config = json.loads(base)
            change(self.config)
            with self.subTest(message=message):
                self.assertIn(message, self.run_analysis(success=False))
        self.config = json.loads(base)
        self.assertIn("omit legacy", self.run_analysis(success=False, extra=["--frame", "LAB"]))
        self.assertIn("must not overwrite analysis YAML", self.run_analysis(success=False, extra=["--out", str(self.input)]))
        self.input.write_text("version: 1\nversion: 1\n")
        self.assertIn("duplicate key", self.run_analysis(success=False, config_path=self.input))

    def test_missing_metadata_and_mixed_targets_fail(self):
        self.fixture([(8, [0.25]), (8, [0.25])])
        self.meta.write_text(self.meta.read_text().splitlines()[0])
        self.assertIn("Missing DIS metadata", self.run_analysis(success=False))
        self.fixture([(8, []), (8, [], {"A": 12, "Z": 6})])
        self.assertIn("Multiple targets", self.run_analysis(success=False))

    def test_slurm_yaml_forwarding_ignores_legacy_defaults(self):
        self.fixture([(8, [0.25])])
        self.input.write_text(json.dumps(self.config))
        events = self.root / "ehijing/events"
        events.mkdir(parents=True)
        manifest = self.root / "manifest.txt"
        manifest.write_text(str(self.oscar) + "\n")
        batch = self.root / "batch.sh"
        sbatch = self.root / "sbatch"
        sbatch.write_text('#!/bin/bash\ncat > "$CAPTURE_BATCH"\necho 123\n')
        sbatch.chmod(0o755)
        env = dict(os.environ, PATH=f"{self.root}:{os.environ['PATH']}", CAPTURE_BATCH=str(batch))
        submitted = subprocess.run(["bash", str(ROOT / "slurm-scripts/analysis_submit.sh"), "RUN_ID=test",
                                    f"RUN_DIR={self.root}", f"ANALYZER={self.executable}", f"META_FILE={self.meta}",
                                    f"ANALYSIS_INPUT={self.input}", f"FILE_LIST={manifest}", f"OUT={self.output}",
                                    f"SLURM_CONFIG={self.root}/missing.env", "--skip-indexing"],
                                   env=env, capture_output=True, text=True)
        self.assertEqual(submitted.returncode, 0, submitted.stdout + submitted.stderr)
        executed = subprocess.run(["bash", str(batch)], env=env, capture_output=True, text=True)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertIn("/CUSTOM/zh/DIS", read_yoda(self.output))


if __name__ == "__main__":
    unittest.main()
