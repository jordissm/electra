"""EMC plotting checks with synthetic inputs, never experimental substitutes."""

import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "analysis/scripts/EMC"
sys.path.insert(0, str(SCRIPT_DIR))
from emc1991 import load_ratio

spec = importlib.util.spec_from_file_location("emc_plot", SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh.py")
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


class EmcPlotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-emc-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_yoda(self, path, beam=100, bins=None, provenance="same", **overrides):
        path.parent.mkdir(parents=True, exist_ok=True)
        bins = bins or [(.1, .2, 0, .04), (.2, .3, 2, .09)]
        metadata = {"Analysis": f"EMC_{beam}", "Selection": "YAML_V1_zh", "Frame": "TRF",
                    "Axis": "zh", "Dimensions": "1", "Normalization": "per_DIS",
                    "Uncertainty": "EventRatioStandardError", "Weighting": "unit",
                    "BeamEnergyGeV": str(beam), "BeamMassGeV": "0.1056583755",
                    "BeamDirection": "-z", "DensityAxes": "zh"}
        metadata.update(overrides)
        lines = [f"# YAML | {provenance}", f"BEGIN YODA_HISTO1D_V2 /EMC_{beam}/zh/multiplicity_charged"]
        lines += [f"{key}: {value}" for key, value in metadata.items()]
        lines += ["# xlow xhigh sumw sumw2 sumwx sumwx2 numEntries"]
        lines += [" ".join(map(str, (*bin_, 0, 0, 100))) for bin_ in bins]
        lines += ["END YODA_HISTO1D_V2"]
        path.write_text("\n".join(lines) + "\n")
        return path

    def write_csv(self, separate=False):
        path = self.root / "synthetic.csv"
        lines = ["# Synthetic test inputs; not EMC measurements."]
        if separate:
            lines += ["nucleus,z,z_low,z_high,R,stat,sys"]
            lines += [f"{n},0.15,0.1,0.2,0.95,0.02,0.03" for n in plot.NUCLEI]
        else:
            lines += ["nucleus,z,R,error"]
            lines += [f"{n},0.15,0.95,0.02" for n in plot.NUCLEI]
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_ratio_errors_zero_yield_and_cross_energy_rejection(self):
        n = self.write_yoda(self.root / "n.yoda")
        d = self.write_yoda(self.root / "d.yoda", bins=[(.1, .2, 2, .01), (.2, .3, 4, .16)])
        beam, x, y, errors = load_ratio(n, d)
        self.assertEqual(beam, 100)
        self.assertEqual(y, [0, .5])
        self.assertAlmostEqual(errors[0], .1)
        self.assertAlmostEqual(errors[1], math.hypot(.3 / 4, 2 * .4 / 16))
        d = self.write_yoda(self.root / "d280.yoda", beam=280)
        with self.assertRaisesRegex(ValueError, "combining energies is disabled"):
            load_ratio(n, d)

    def test_bad_metadata_bins_and_provenance_are_rejected(self):
        n = self.write_yoda(self.root / "n.yoda")
        for kwargs in ({"BeamMassGeV": "0.000511"}, {"provenance": "different"},
                       {"Normalization": "raw_hadrons"}, {"Frame": "BREIT"},
                       {"bins": [(.1, .3, 2, .04)]}):
            d = self.write_yoda(self.root / "d.yoda", **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                load_ratio(n, d)

    def test_data_schema_preserves_quoted_and_separate_errors(self):
        point = plot.load_experiment(self.write_csv())["C"][0]
        self.assertEqual(point, (.15, None, .95, .02, None, None))
        point = plot.load_experiment(self.write_csv(separate=True))["Sn"][0]
        self.assertEqual(point, (.15, (.1, .2), .95, .02, .03, None))
        with self.assertRaisesRegex(FileNotFoundError, "original EMC table"):
            plot.load_experiment(self.root / "missing.csv")
        with self.assertRaisesRegex(ValueError, "No EMC measurements"):
            plot.load_experiment(ROOT / "analysis/experimental_data/EMC/R_A/Fig4.example.csv")

    def test_profile_discovery_keeps_all_beam_pairs_separate(self):
        for beam in (100, 280):
            for nucleus in ("d", *plot.NUCLEI):
                self.write_yoda(self.root / "profiles" / str(beam) / nucleus / "profile_000004.yoda", beam)
        config = self.root / "config.json"
        config.write_text(json.dumps({"profile_directory": "profiles"}))
        scenarios = plot.load_scenarios(config)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["label"], "Mean")
        self.assertEqual(len(scenarios[0]["samples"]), 6)
        for sample in scenarios[0]["samples"]:
            beam, *_ = load_ratio(sample["nuclear"], sample["deuterium"])
            self.assertIn(str(beam), str(sample["deuterium"]))

    def test_layout_and_cli_render_with_synthetic_data(self):
        data = self.write_csv(separate=True)
        points = plot.load_experiment(data)
        args = SimpleNamespace(figsize=(7.2, 3.6), xlim=(.05, .85), ylim=(.65, 1.35),
                               frame_linewidth=.3, no_errorbars=False, title="Synthetic layout check")
        fig = plot.create_figure(points, [], args)
        self.addCleanup(plot.plt.close, fig)
        self.assertEqual(len(fig.axes), 3)
        self.assertIsNotNone(fig.axes[0].get_legend())
        self.assertTrue(all(ax.get_legend() is None for ax in fig.axes[1:]))
        self.assertTrue(fig.axes[0].texts)
        output = self.root / "plots"
        result = subprocess.run([sys.executable, str(SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh.py"),
                                 "--data-file", str(data), "--output-dir", str(output),
                                 "--title", "Synthetic layout check"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for extension in ("pdf", "png"):
            self.assertGreater((output / f"RA_vs_zh.{extension}").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
