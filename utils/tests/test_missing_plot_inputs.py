"""Plotting CLIs keep available datasets and tolerate absent files/histograms."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "analysis/scripts"
sys.path.insert(0, str(SCRIPTS))
from plot_inputs import optional_data


class MissingPlotInputsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-missing-plots-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def run_plot(self, script, *args, output="plots", success=True):
        destination = self.directory / output
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, args),
             "--output-dir", str(destination)], cwd=self.directory,
            env=dict(os.environ, MPLBACKEND="Agg"), capture_output=True, text=True,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return destination, result

    def config(self, **values):
        path = self.directory / "config.json"
        path.write_text(json.dumps(values))
        return path

    def hermes_input(self, name="valid.yoda", selection="HERMES_2007_FIG2_V1"):
        path = self.directory / name
        blocks = []
        for axis in ("zh", "nu", "Q2"):
            for histogram in ("counts_pip", "DIS"):
                blocks += [
                    f"BEGIN YODA_HISTO1D_V2 /HERMES_2007/{axis}/{histogram}",
                    f"Selection: {selection}", "Acceptance: none",
                    "BeamEnergyGeV: 27.6", "BeamDirection: -z",
                    "# xlow xhigh sumw sumw2 sumwx sumwx2 numEntries",
                    "0.2 0.3 10 10 0 0 10", "END YODA_HISTO1D_V2",
                ]
        path.write_text("\n".join(blocks) + "\n")
        return path.name

    def test_hermes_keeps_valid_curve_and_skips_absent_histogram_or_file(self):
        self.hermes_input()
        (self.directory / "legacy.yoda").write_text("# No requested histograms\n")
        config = self.config(particles=["pip"], nuclei=["He"], scenarios=[
            {"label": label, "deuterium": filename, "nuclei": {"He": filename}}
            for label, filename in (("Available", "valid.yoda"),
                                    ("Legacy", "legacy.yoda"), ("Absent", "absent.yoda"))
        ])
        for comparison in ("model_comparison", "cross_section_profile_comparison"):
            with self.subTest(comparison=comparison):
                output, result = self.run_plot(
                    f"HERMES/{comparison}/R_A/plot_RA_vs_zh.py", "--config", config,
                    "--no-exp", output=comparison,
                )
                self.assertTrue((output / "RA_vs_zh.png").is_file())
                self.assertIn("missing /HERMES_2007/zh/counts_pip", result.stderr)

    def test_missing_hermes_simulation_still_plots_experimental_fig2(self):
        config = self.config(nuclei=["He"], scenarios=[
            {"deuterium": "absent.yoda", "nuclei": {"He": "absent.yoda"}}
        ])
        output, _ = self.run_plot("HERMES/plot_hermes_fig2.py", "--config", config,
                                  "--particles", "pip")
        self.assertTrue((output / "RA_fig2.png").is_file())

    def test_hermes_incompatible_metadata_still_fails(self):
        self.hermes_input(selection="invalid_selection")
        config = self.config(particles=["pip"], nuclei=["He"], scenarios=[
            {"deuterium": "valid.yoda", "nuclei": {"He": "valid.yoda"}}
        ])
        _, result = self.run_plot("HERMES/model_comparison/R_A/plot_RA_vs_zh.py",
                                  "--config", config, "--no-exp", success=False)
        self.assertIn("selection metadata", result.stderr)

    def test_clas_empty_profile_directory_falls_back_to_published_data(self):
        config = self.config(profile_directory="absent")
        for script, filename in (("plot_RA_vs_zh.py", "RA_vs_zh.png"),
                                 ("plot_RA_vs_zh_binned_Q2_nu.py", "RA_vs_zh_binned_Q2_nu_pip.png")):
            with self.subTest(script=script):
                output, result = self.run_plot(
                    f"CLAS/cross_section_profile_comparison/R_A/{script}",
                    "--config", config, output=script,
                )
                self.assertTrue((output / filename).is_file())
                self.assertIn("No nonempty", result.stderr)

    def test_clas_retains_available_nucleus_when_other_inputs_are_absent(self):
        blocks = []
        for particle in ("pip", "pim"):
            blocks += [
                "# YAML | synthetic shared selection",
                f"BEGIN YODA_HISTO1D_V2 /CLAS_2021/zh/multiplicity_{particle}",
                "Analysis: CLAS_2021", "Selection: YAML_V1_zh", "Axis: zh",
                "Dimensions: 1", "Normalization: per_DIS",
                "Uncertainty: EventRatioStandardError", "Frame: TRF",
                "Weighting: unit", "BeamEnergyGeV: 5.014", "BeamMassGeV: 0.000511",
                "BeamDirection: -z", "DensityAxes: zh",
                "# xlow xhigh sumw sumw2 sumwx sumwx2 numEntries",
                "0.2 0.3 1 0.01 0 0 10", "END YODA_HISTO1D_V2",
            ]
        for name in ("d.yoda", "C.yoda"):
            (self.directory / name).write_text("\n".join(blocks) + "\n")
        config = self.config(scenarios=[{
            "deuterium": "d.yoda", "nuclei": {"C": "C.yoda", "Fe": "absent.yoda"},
        }])
        output, result = self.run_plot("CLAS/cross_section_profile_comparison/R_A/plot_RA_vs_zh.py",
                                       "--config", config, "--no-exp")
        self.assertTrue((output / "RA_vs_zh.png").is_file())
        self.assertIn("absent.yoda", result.stderr)
        # The same inputs contain no Q2/nu histograms; skip those figures only.
        output, result = self.run_plot(
            "CLAS/cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py",
            "--config", config, "--no-exp", output="binned",
        )
        self.assertFalse(list(output.glob("*.png")))
        self.assertIn("missing /CLAS_2021/zh_Q2_nu", result.stderr)

    def test_emc_partial_measurements_plot_available_nucleus(self):
        data = self.directory / "partial.csv"
        data.write_text("nucleus,z,R,error\nC,0.25,0.9,0.1\n")
        output, result = self.run_plot("EMC/cross_section_profile_comparison/R_A/plot_RA_vs_zh.py",
                                       "--data-file", data)
        self.assertTrue((output / "RA_vs_zh.png").is_file())
        self.assertIn("No EMC measurements supplied for Cu", result.stderr)

    def test_no_available_data_skips_figure_successfully(self):
        config = self.config(profile_directory="absent", scenarios=[])
        for script, args in (
            ("EMC/cross_section_profile_comparison/R_A/plot_RA_vs_zh.py", []),
            ("CLAS/cross_section_profile_comparison/R_A/plot_RA_vs_zh.py", ["--no-exp"]),
            ("CLAS/cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py", ["--no-exp"]),
            ("HERMES/model_comparison/R_A/plot_RA_vs_zh.py", ["--no-exp"]),
            ("HERMES/cross_section_profile_comparison/R_A/plot_HP2026_poster.py", []),
            ("HERMES/plot_hermes_fig2.py", ["--no-exp"]),
        ):
            with self.subTest(script=script):
                output, result = self.run_plot(script, "--config", config, *args, output=Path(script).parent)
                self.assertFalse(list(output.glob("*.png")))
                self.assertIn("No available data", result.stderr)

    def test_deuterium_scripts_tolerate_missing_files_and_histograms(self):
        missing = self.directory / "profile_000000.yoda"
        legacy = self.directory / "legacy.yoda"
        legacy.write_text("# No spectra\n")
        for script in sorted((SCRIPTS / "HERMES").glob("*/e_d/plot_*.py")):
            args = (["--profile-files", missing] if "cross_section_profile_comparison" in str(script)
                    else ["--ehijing-decays", legacy, "--smash-decays-only", missing,
                          "--smash-decays-collisions", missing])
            with self.subTest(script=script):
                output, result = self.run_plot(script.relative_to(SCRIPTS), *args, "--no-exp",
                                                output=script.relative_to(SCRIPTS).with_suffix(""))
                self.assertFalse(list(output.glob("*.png")))
                self.assertIn("No available data", result.stderr)

    def test_missing_time_samples_skip_without_importing_matplotlib(self):
        config = self.config(samples=[{"label": "Absent", "yoda": "absent.yoda"}])
        output, result = self.run_plot(
            "experiment_comparison/hadronization_comparison/times_vs_zh/run_times_vs_zh.py",
            "--config", config,
        )
        self.assertFalse(output.exists())
        self.assertIn("No available data", result.stderr)

    def test_optional_data_preserves_validation_errors(self):
        def incompatible():
            raise ValueError("incompatible bin edges")

        with self.assertRaisesRegex(ValueError, "incompatible bin edges"):
            optional_data(incompatible)


if __name__ == "__main__":
    unittest.main()
