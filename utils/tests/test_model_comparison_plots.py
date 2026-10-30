"""Exercise model configs, output routing, launchers and missing-input behavior."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ModelComparisonPlotsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-model-plots-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        shutil.copytree(ROOT / "analysis/scripts", self.analysis / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for path in (ROOT / "analysis").glob("*.sh"):
            shutil.copy2(path, self.analysis / path.name)
        self.env = dict(os.environ, PYTHON=sys.executable, MPLBACKEND="Agg")

    def execute(self, launcher, *args):
        result = subprocess.run(["bash", str(self.analysis / launcher), *map(str, args)],
                                cwd=self.root, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def populate_models(self, experiment):
        config = self.analysis / f"scripts/{experiment}/model_comparison/R_A/RA_vs_zh_inputs.yaml"
        entries = json.loads(config.read_text())["scenarios"]
        paths = set()
        for entry in entries:
            if experiment == "CLAS":
                paths.update([entry["deuterium"], *entry["nuclei"].values()])
            else:
                for sample in entry["samples"]:
                    paths.update((sample["deuterium"], sample["nuclear"]))
        for value in paths:
            path = (config.parent / value).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.yoda(experiment))

    @staticmethod
    def yoda(experiment):
        blocks = ["# YAML | synthetic shared model test selection"]
        histograms = [("zh", None, None)]
        if experiment == "CLAS":
            histograms += [("zh_Q2_nu", iq, inu) for iq in range(3) for inu in range(3)]
        q2_edges = (1.0, 1.3, 1.8, 4.1)
        nu_edges = (2.2, 3.2, 3.7, 4.2)
        for name, iq, inu in histograms:
            for species in (("pip", "pim") if experiment == "CLAS" else ("charged",)):
                analysis = "CLAS_2021" if experiment == "CLAS" else "EMC_100"
                base = f"/{analysis}/{name}"
                if iq is not None:
                    base += f"/Q2_bin{iq}/nu_bin{inu}"
                blocks += [
                    f"BEGIN YODA_HISTO1D_V2 {base}/multiplicity_{species}",
                    f"Analysis: {analysis}", f"Selection: YAML_V1_{name}", "Axis: zh",
                    f"Dimensions: {3 if iq is not None else 1}", "Normalization: per_DIS",
                    "Uncertainty: EventRatioStandardError", "Frame: TRF", "Weighting: unit",
                    f"BeamEnergyGeV: {5.014 if experiment == 'CLAS' else 100}",
                    f"BeamMassGeV: {0.000511 if experiment == 'CLAS' else 0.1056583755}",
                    "BeamDirection: -z", "DensityAxes: zh",
                ]
                if iq is not None:
                    blocks += [f"Slice1: Q2 {q2_edges[iq]} {q2_edges[iq + 1]}",
                               f"Slice2: nu {nu_edges[inu]} {nu_edges[inu + 1]}"]
                blocks += ["# xlow xhigh sumw sumw2 sumwx sumwx2 numEntries",
                           "0.2 0.3 1 0.01 0 0 10", "END YODA_HISTO1D_V2"]
        return "\n".join(blocks) + "\n"

    def test_clas_launcher_uses_model_defaults_for_all_three_figures(self):
        self.populate_models("CLAS")
        self.execute("run_CLAS_model_comparison_plot_scripts_R_A.sh", "--no-exp")
        output = self.analysis / "output/plots/CLAS/model_comparison/R_A"
        for name in ("RA_vs_zh", "RA_vs_zh_binned_Q2_nu_pip", "RA_vs_zh_binned_Q2_nu_pim"):
            for extension in ("pdf", "png"):
                self.assertGreater((output / f"{name}.{extension}").stat().st_size, 1000)
        self.assertFalse((self.analysis / "output/plots/CLAS/cross_section_profile_comparison").exists())

    def test_emc_launcher_uses_model_defaults_and_skips_missing_experiment(self):
        self.populate_models("EMC")
        result = self.execute("run_EMC_model_comparison_plot_scripts_R_A.sh")
        self.assertIn("Missing EMC data", result.stderr)
        output = self.analysis / "output/plots/EMC/model_comparison/R_A"
        self.assertTrue((output / "RA_vs_zh.pdf").read_bytes().startswith(b"%PDF"))
        self.assertTrue((output / "RA_vs_zh.png").read_bytes().startswith(b"\x89PNG"))

    def test_absent_model_inputs_skip_successfully(self):
        for experiment in ("CLAS", "EMC"):
            with self.subTest(experiment=experiment):
                result = self.execute(f"run_{experiment}_model_comparison_plot_scripts_R_A.sh", "--no-exp")
                self.assertIn("No available data", result.stderr)
                output = self.analysis / f"output/plots/{experiment}/model_comparison/R_A"
                self.assertFalse(list(output.glob("*.png")))

    def test_emc_aggregate_keeps_data_only_figures_in_each_comparison(self):
        data = self.root / "experiment.csv"
        data.write_text("nucleus,z,R,error\nC,0.25,0.9,0.1\n")
        self.execute("run_EMC_plot_scripts.sh", "--data-only", "--data-file", data)
        for comparison in ("model_comparison", "cross_section_profile_comparison"):
            self.assertTrue((self.analysis / f"output/plots/EMC/{comparison}/R_A/RA_vs_zh.pdf").is_file())

    def test_all_runner_dispatches_nine_workflows_and_model_overrides(self):
        result = self.execute("run_all_plot_scripts.sh", "--dry-run",
                              "--clas-model-config", "custom-clas.json",
                              "--emc-model-config", "custom-emc.json")
        self.assertEqual(result.stdout.count("[run]"), 9)
        self.assertIn("run_CLAS_model_comparison_plot_scripts_R_A.sh --config custom-clas.json", result.stdout)
        self.assertIn("run_EMC_model_comparison_plot_scripts_R_A.sh --config custom-emc.json", result.stdout)
        result = self.execute("run_all_plot_scripts.sh", "--dry-run", "--clas-data-only", "--emc-data-only")
        self.assertIn("run_CLAS_model_comparison_plot_scripts_R_A.sh --data-only", result.stdout)
        self.assertIn("run_EMC_model_comparison_plot_scripts_R_A.sh --data-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
