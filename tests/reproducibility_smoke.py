"""Opt-in fresh-process replay checks using small runs in a temporary directory.

Run from the repository root:
  PYTHONPATH=python python3 tests/reproducibility_smoke.py --executable /path/to/ehijing
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def records(directory):
    return {path.name: path.read_bytes() for path in directory.rglob("event_*.*")}


def compare(left, right):
    if left != right:
        differences = [name for name in left.keys() | right.keys() if left.get(name) != right.get(name)]
        raise AssertionError(f"Event records differ: {differences}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    executable = args.executable.resolve()
    repo = Path(__file__).resolve().parents[1]
    bundle = repo / "input/ehijing/experiments/hermes_2007"
    with tempfile.TemporaryDirectory(prefix="electra-seed-replay-") as temporary:
        root = Path(temporary).resolve()
        hadronization = root / "hadronization.setting"
        hadronization.write_text((bundle / "hadronization.setting").read_text()
                                 + "\nHadronVertex:trace = off\n")
        tables = root / "tables"
        tables.mkdir()
        common = ["--nucleus", "d", "--nucleus-database", str(repo / "input/ehijing/woods_saxon.yaml"),
                  "--K", "4", "--first-event-id", "7",
                  "--hard-process-config", str(bundle / "hard_process.setting"),
                  "--hadronization-config", str(hadronization),
                  "--dis-cuts-config", str(bundle / "dis_cuts.setting"),
                  "--tabulation-path", str(tables)]

        def generate(name, mode, target, history="on", count=2, seed="18446744073709551615",
                     shard=2, config_alias=False):
            directory = root / name
            cmd = [str(executable), *common, "--run-path", str(directory),
                   "--number-of-events", str(count), "--chunk-size", str(shard),
                   "--medium-modification-mode", str(mode), "--nuclear-target", target,
                   "--history", history, "--seed", seed]
            if config_alias:
                cmd += ["--hadronization-config", str(tables / ".." / hadronization.name)]
            with (root / f"{name}.log").open("w") as log:
                result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            if result.returncode:
                raise AssertionError((root / f"{name}.log").read_text()[-6000:])
            found = records(directory)
            assert sum(name.endswith(".oscar") for name in found) == count
            for name, data in found.items():
                if name.endswith(".meta.json"):
                    provenance = json.loads(data)["reproducibility"]
                    assert provenance["master_seed"] == seed
                    assert provenance["attempt"] > 0
                    for table, digest in provenance["inputs_sha256"].items():
                        if table.endswith(".dat"):
                            assert hashlib.sha256((tables / table).read_bytes()).hexdigest() == digest
            return found

        for mode in [0, 1]:
            for target in ["on", "off"]:
                case = f"mode{mode}-target{target}"
                first = generate(case + "-first", mode, target)
                compare(first, generate(case + "-replay", mode, target))
                without_history = generate(case + "-no-history", mode, target, history="off")
                # With default trace=off, history collection also enables the
                # fragmentation observer. Turning both observers off must leave
                # the complete primary records and seed progression unchanged.
                compare({k: v for k, v in first.items()
                         if not k.endswith((".history", ".fragmentation"))}, without_history)
                print(f"PASS: {case}, fresh-process complete records and history on/off", flush=True)

        baseline = generate("prefix-first", 0, "on")
        compare(baseline, generate("configuration-alias", 0, "on", config_alias=True))
        extended = generate("prefix-extended", 0, "on", count=3, shard=17)
        compare(baseline, {k: extended[k] for k in baseline})
        changed = generate("changed-seed", 0, "on", seed="12345")
        assert any(baseline[k] != changed[k] for k in baseline if k.endswith(".oscar"))
        print("PASS: configuration aliases; unchanged prefix after event-count/shard changes; changed master changes events", flush=True)

        wrapper_dir = root / "wrapper"
        environment = dict(os.environ, PATH=str(executable.parent) + os.pathsep + os.environ["PATH"],
                           PYTHONPATH=str(repo / "python"))
        command = [sys.executable, "-m", "electra.cli", "ehijing", "run", *common,
                   "--run-path", str(wrapper_dir), "--number-of-events", "2", "--chunk-size", "2",
                   "--medium-modification-mode", "0", "--nuclear-target", "on", "--history", "on",
                   "--seed", "18446744073709551615"]
        with (root / "wrapper.log").open("w") as log:
            result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        if result.returncode:
            raise AssertionError((root / "wrapper.log").read_text()[-6000:])
        compare(baseline, records(wrapper_dir / "events"))
        result = subprocess.run(command, env=environment, capture_output=True, timeout=30)
        assert result.returncode == 0 and not result.stdout
        altered = command[:-1] + ["12345"]
        result = subprocess.run(altered, env=environment, capture_output=True, timeout=30)
        assert result.returncode != 0 and b"different seeds" in result.stderr
        print("PASS: direct/wrapper equality; identical resume skips; changed seed rejected", flush=True)

        for invalid in ["-1", "+1", "1x", "18446744073709551616"]:
            result = subprocess.run([str(executable), *common, "--run-path", str(root / "invalid"),
                "--number-of-events", "1", "--medium-modification-mode", "0", "--seed", invalid],
                capture_output=True, timeout=30)
            assert result.returncode == 2 and b"unsigned 64-bit" in result.stderr
        print("PASS: standalone seed validation", flush=True)


if __name__ == "__main__":
    main()
