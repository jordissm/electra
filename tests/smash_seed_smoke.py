"""Opt-in fresh-process SMASH seed/replay check with synthetic pion input.

  python3 tests/smash_seed_smoke.py --executable /path/to/smash
"""
import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=300,
                        help="Per-process timeout, including resonance-integral initialization")
    args = parser.parse_args()
    executable = args.executable.resolve()
    repo = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, PATH=str(executable.parent) + os.pathsep + os.environ["PATH"],
                       PYTHONPATH=str(repo / "python"))
    with tempfile.TemporaryDirectory(prefix="electra-smash-seed-") as temporary:
        root = Path(temporary).resolve()
        tabulations = root / "tabulations"
        tabulations.mkdir()
        settings = root / "config.yaml"
        settings.write_text("""Logging:
  default: INFO
General:
  Modus: List
  Time_Step_Mode: Fixed
  Delta_Time: 0.1
  End_Time: 2.0
  Randomseed: -1
Modi:
  List:
    Optional_Quantities: [ID, charge, prod_time, form_time, xsecfac, prod_time_status]
Output:
  Output_Interval: 2.0
  Particles:
    Format: [Oscar2013]
    Extended: true
Collision_Term:
  Cross_Section_Formation_Scaling:
    Profile:
      Formation_Time: 1.0
""")
        profile = root / "profile.dat"
        profile.write_text("0 1\n1 1\n")
        index = root / "profiles.jsonl"
        index.write_text(json.dumps({"id": "synthetic", "relpath": profile.name}) + "\n")

        def generate(name, seed, task_mode):
            run_dir = root / name
            shard = run_dir / "smash/events/events_00000000-00000999"
            shard.mkdir(parents=True)
            (shard / "tabulations").symlink_to(tabulations, target_is_directory=True)
            event_dir = run_dir / "ehijing" / "events"
            event_dir.mkdir(parents=True)
            event = event_dir / "event_00000007.oscar"
            energy = math.sqrt(.4**2 + .138**2)
            event.write_text(
                "#!OSCAR2013 particle_lists t x y z mass p0 px py pz pdg ID charge prod_time form_time xsecfac prod_time_status\n"
                "# Units: fm fm fm fm GeV GeV GeV GeV GeV none none none fm fm none none\n"
                "# event 7 out 2\n"
                f"0 -0.2 0 0 0.138 {energy:.17g} 0.4 0 0 211 0 1 0 0 1 1\n"
                f"0 0.2 0 0 0.138 {energy:.17g} -0.4 0 0 -211 1 -1 0 0 1 1\n"
                "# event 7 end 0\n")
            command = [sys.executable, "-m", "electra.cli", "smash", "run",
                       "--run-dir", str(run_dir), "--config-file", str(settings),
                       "--profiles-index", str(index), "--nevents", "1", "--nreplicas", "2",
                       "--seed", seed, "--task-mode", task_mode]
            if task_mode == "one":
                command += ["--task-id", "0"]
            logfile = root / f"{name}.log"
            with logfile.open("w") as log:
                process = subprocess.Popen(command, env=environment, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    # Terminate the test's wrapper and its SMASH child together.
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise AssertionError("SMASH timeout:\n" + logfile.read_text()[-6000:])
            if code:
                raise AssertionError(logfile.read_text()[-6000:])
            output = next((run_dir / "smash").rglob("seed_provenance.json")).parent
            particles = {path.name: path.read_bytes() for path in output.glob("*.oscar")}
            assert particles, "No SMASH particle records"
            text = logfile.read_text()
            seeds = re.findall(r"random number seed:\s*(\d+)", text)
            provenance = json.loads((output / "seed_provenance.json").read_text())["request"]
            assert len(seeds) == 2 and int(seeds[0]) == provenance["smash_seed"]
            return particles, seeds

        first = generate("first", "18446744073709551615", "all")
        replay = generate("replay", "18446744073709551615", "one")
        assert first == replay, "SMASH records or replica seeds differ across fresh processes/task modes"
        changed = generate("changed", "12345", "all")
        assert first[1] != changed[1], "Changed master did not change SMASH replica seeds"
        assert first[0] != changed[0], "Changed master did not change stochastic transport records"
        print("PASS: SMASH complete particle replay, task-mode invariance, replica seeds and changed master")


if __name__ == "__main__":
    main()
