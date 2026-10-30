#!/usr/bin/env python3
"""Plot configured experimental setups from their YODA charged-hadron time profiles."""

import argparse
import json
from pathlib import Path
from plot_times_vs_zh import plot_samples


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
    parser.add_argument("--config", required=True, help="JSON plot config; YODA paths resolve beside it")
    parser.add_argument("--output-dir", required=True, help="PDF and PNG destination")
    args = parser.parse_args()
    run(args.config, args.output_dir)


if __name__ == "__main__":
    main()
