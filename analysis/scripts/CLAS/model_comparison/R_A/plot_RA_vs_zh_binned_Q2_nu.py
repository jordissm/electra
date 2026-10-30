#!/usr/bin/env python3
"""CLAS model comparison of pion multiplicity ratios in Q2 and nu bins."""

import importlib.util
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPT = SCRIPT_DIR.parents[1] / "cross_section_profile_comparison/R_A/plot_RA_vs_zh_binned_Q2_nu.py"
spec = importlib.util.spec_from_file_location("_clas_shared_plot_RA_vs_zh_binned_Q2_nu", SHARED_SCRIPT)
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


def main():
    plot.main(
        comparison="model_comparison", default_config=SCRIPT_DIR / "RA_vs_zh_inputs.yaml",
        description=__doc__,
    )


if __name__ == "__main__":
    main()
