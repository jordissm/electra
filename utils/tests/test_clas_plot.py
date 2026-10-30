"""CLAS ratio checks using synthetic normalized bins, without event generation."""

import importlib.util
import json
import math
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "analysis/scripts/CLAS"
sys.path.insert(0, str(SCRIPT_DIR))
from clas2021 import NU_BINS, Q2_BINS, load_ratio


class ClasRatioTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def write(self, filename, bins, provenance="selection: same",
              histogram_path="/CLAS_2021/zh/multiplicity_pip", **overrides):
        annotations = {
            "Analysis": "CLAS_2021", "Selection": "YAML_V1_zh", "Axis": "zh",
            "Dimensions": "1", "Normalization": "per_DIS", "Uncertainty": "EventRatioStandardError",
            "Frame": "TRF", "Weighting": "unit", "BeamEnergyGeV": "5.014",
            "BeamMassGeV": "0.000511", "BeamDirection": "-z", "DensityAxes": "zh",
        }
        annotations.update(overrides)
        lines = [f"# YAML | {provenance}", f"BEGIN YODA_HISTO1D_V2 {histogram_path}"]
        lines += [f"{key}: {value}" for key, value in annotations.items()]
        lines += ["# xlow xhigh sumw sumw2 sumwx sumwx2 numEntries"]
        lines += [" ".join(map(str, (*bin_, 0, 0, 100))) for bin_ in bins]
        lines += ["END YODA_HISTO1D_V2"]
        path = self.directory / filename
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_normalized_ratios_and_zero_yield(self):
        n = self.write("n.yoda", [(0, .1, 0, .04), (.1, .2, 2, .09), (.2, .3, 1, .01)])
        d = self.write("d.yoda", [(0, .1, 2, .01), (.1, .2, 4, .16), (.2, .3, 0, 0)])
        x, y, errors = load_ratio(n, d, "pip")
        self.assertEqual(y, [0, .5])
        self.assertEqual(len(x), 2)
        self.assertAlmostEqual(errors[0], .1)
        self.assertAlmostEqual(errors[1], math.hypot(.3 / 4, 2 * .4 / 16))

    def test_incompatible_inputs_are_rejected(self):
        d = self.write("d.yoda", [(0, .1, 2, .01)])
        for changes in ({"provenance": "selection: different"}, {"Frame": "LAB"},
                        {"BeamEnergyGeV": "27.6"}, {"Normalization": "raw_hadrons"}):
            with self.subTest(changes=changes):
                n = self.write("n.yoda", [(0, .1, 1, .01)], **changes)
                with self.assertRaises(ValueError):
                    load_ratio(n, d, "pip")
        n = self.write("n.yoda", [(0, .2, 1, .01)])
        with self.assertRaisesRegex(ValueError, "bin edges differ"):
            load_ratio(n, d, "pip")

    def test_publication_bins(self):
        path = SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh.py"
        spec = importlib.util.spec_from_file_location("clas_plot", path)
        plot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plot)
        points = plot.load_experiment(ROOT / "analysis/experimental_data/CLAS/R_A/TableII.csv")
        self.assertEqual(sum(map(len, points.values())), 54)
        self.assertEqual(len(points["pip", "C"]), 10)
        self.assertEqual(len(points["pim", "Pb"]), 8)
        self.assertEqual(points["pip", "Pb"][-1], (.9, 1, .270, .004, .014))
        self.assertEqual(points["pim", "Pb"][-1], (.7, .8, .444, .015, .021))
        self.assertEqual(plot.ANALYSIS_DIR, ROOT / "analysis")

    def test_profile_discovery_and_overlay_cli(self):
        for target in ("d", "C", "Fe", "Pb"):
            directory = self.directory / target
            directory.mkdir()
            fixture = self.write("fixture.yoda", [(0, .1, 2 if target == "d" else 1, .01),
                                                  (.1, .2, 3, .04)])
            text = fixture.read_text()
            second = "\n".join(text.splitlines()[1:]).replace("multiplicity_pip", "multiplicity_pim")
            (directory / "profile_000004.yoda").write_text(text + second + "\n")
        config = self.directory / "config.json"
        config.write_text(json.dumps({"profile_directory": "."}))
        output = self.directory / "plots"
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh.py"),
             "--config", str(config), "--no-exp", "--output-dir", str(output)],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for extension in ("pdf", "png"):
            self.assertGreater((output / f"RA_vs_zh.{extension}").stat().st_size, 1000)

    def write_slice(self, filename, iq, inu, **overrides):
        annotations = {"Selection": "YAML_V1_zh_Q2_nu", "Dimensions": "3",
                       "Slice1": f"Q2 {Q2_BINS[iq][0]} {Q2_BINS[iq][1]}",
                       "Slice2": f"nu {NU_BINS[inu][0]} {NU_BINS[inu][1]}"}
        annotations.update(overrides)
        return self.write(filename, [(.05, .1, 0, .04), (.1, .2, 2, .09)],
                          histogram_path=f"/CLAS_2021/zh_Q2_nu/Q2_bin{iq}/nu_bin{inu}/multiplicity_pip",
                          **annotations)

    def test_slice_ratios_and_published_bounds(self):
        n = self.write_slice("n.yoda", 2, 1)
        d = self.write_slice("d.yoda", 2, 1)
        x, y, errors = load_ratio(n, d, "pip", q2_bin=2, nu_bin=1)
        self.assertEqual(y, [1])  # The zero deuterium-yield bin is undefined.
        self.assertAlmostEqual(x[0], .15)
        self.assertAlmostEqual(errors[0], math.sqrt(2) * .3 / 2)
        for overrides in ({"Slice1": "Q2 1.8 4.0"}, {"Slice2": "nu 3.2 3.8"}, {"Slice1": "nu 1.8 4.1"}):
            with self.subTest(overrides=overrides):
                n = self.write_slice("n.yoda", 2, 1, **overrides)
                d = self.write_slice("d.yoda", 2, 1, **overrides)
                with self.assertRaisesRegex(ValueError, "published"):
                    load_ratio(n, d, "pip", q2_bin=2, nu_bin=1)
        with self.assertRaises(ValueError):
            load_ratio(n, d, "pip", q2_bin=1)
        with self.assertRaisesRegex(ValueError, "missing"):
            load_ratio(n, d, "pip", q2_bin=0, nu_bin=0)

    def test_binned_publication_data_and_legend_layout(self):
        path = SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py"
        spec = importlib.util.spec_from_file_location("clas_binned_plot", path)
        plot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plot)
        points = plot.load_experiment(ROOT / "analysis/experimental_data/CLAS/R_A/TablesIII_VIII.csv")
        self.assertEqual(sum(len(v) for key, v in points.items() if key[0] == "pip"), 270)
        self.assertEqual(sum(len(v) for key, v in points.items() if key[0] == "pim"), 213)
        self.assertEqual(points["pip", "C", 0, 0][0], (.05, .1, 1.180, .013, .026))
        self.assertEqual(points["pim", "C", 1, 2][-1], (.7, .8, 1.777, .690, .077))
        self.assertEqual(points["pim", "Pb", 0, 2][-1][:2], (.6, .7))
        args = SimpleNamespace(ylim=None, xlim=(0, 1.05), figsize=(7.2, 8.4),
                               no_errorbars=False, frame_linewidth=.3, title="")
        fig = plot.create_figure("pim", points, [], args)
        self.addCleanup(plot.plt.close, fig)
        self.assertEqual(len(fig.axes), 9)
        self.assertIsNotNone(fig.axes[0].get_legend())
        self.assertTrue(all(ax.get_legend() is None for ax in fig.axes[1:]))
        self.assertEqual(len(fig.axes[0].get_legend().get_texts()), 3)
        self.assertGreaterEqual(fig.axes[6].get_ylim()[1], 1.777 + .690)

    def test_binned_overlay_cli_writes_both_charges(self):
        scenarios = {"deuterium": "d.yoda", "nuclei": {n: n + ".yoda" for n in ("C", "Fe", "Pb")}}
        for target in ("d", "C", "Fe", "Pb"):
            blocks = []
            for iq in range(3):
                for inu in range(3):
                    text = self.write_slice("slice.yoda", iq, inu).read_text()
                    blocks.append("\n".join(text.splitlines()[1:]))
                    blocks.append(blocks[-1].replace("multiplicity_pip", "multiplicity_pim"))
            (self.directory / f"{target}.yoda").write_text("# YAML | selection: same\n" + "\n".join(blocks))
        config = self.directory / "config.json"
        config.write_text(json.dumps({"scenarios": [scenarios]}))
        output = self.directory / "plots"
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py"),
             "--config", str(config), "--no-exp", "--output-dir", str(output)],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for particle in ("pip", "pim"):
            for extension in ("pdf", "png"):
                self.assertGreater((output / f"RA_vs_zh_binned_Q2_nu_{particle}.{extension}").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
