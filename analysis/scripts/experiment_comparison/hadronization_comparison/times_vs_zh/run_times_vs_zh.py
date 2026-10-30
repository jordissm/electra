#!/usr/bin/env python3
"""Overlay CLAS, HERMES, and EMC production/formation times in one plot."""

import argparse
import json
from pathlib import Path
from plot_times_vs_zh import plot_samples


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR / "times_vs_zh_inputs.json"
if not DEFAULT_CONFIG.is_file():
    DEFAULT_CONFIG = SCRIPT_DIR / "times_vs_zh_inputs.example.json"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parents[3] / "output/plots/experiment_comparison/times_vs_zh"


def run(config_path, output_dir):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    root = config_path.parent
    samples = config["samples"]
    if not samples:
        raise ValueError("Config must contain at least one sample")
    paths, labels = [], []
    for sample in samples:
        if "yoda" not in sample:
            raise ValueError("Each plot sample needs a 'yoda' path from utils/analyze_oscar_output.cpp")
        path = root / sample["yoda"]
        paths.append(path)
        labels.append(sample.get("label", path.stem))
    return plot_samples(paths, labels, output_dir, title=config.get("title", ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="JSON plot config; defaults to the local config or the CLAS/HERMES/EMC example",
    )
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help="PDF and PNG destination (default: analysis/output/plots/experiment_comparison/times_vs_zh)",
    )
    args = parser.parse_args()
    run(args.config, args.output_dir)


if __name__ == "__main__":
    main()
