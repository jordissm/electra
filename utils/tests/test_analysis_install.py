"""Installer/build orchestration checks with local container and CMake stand-ins."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AnalysisInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electra-install-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.prefix = self.root / "prefix space"
        self.package = self.root / "packaged utils"
        self.package.mkdir()
        self.package_slurm = self.root / "packaged slurm"
        self.package_slurm.mkdir()
        shutil.copy2(ROOT / "slurm-scripts/analysis_submit.sh", self.package_slurm)
        for filename in ("CMakeLists.txt", "build_analysis.sh"):
            shutil.copy2(ROOT / "utils" / filename, self.package / filename)
        for filename in ("analyze_oscar_output.cpp", "oscar_analysis.hpp"):
            (self.package / filename).write_text("packaged source\n")
        shutil.copytree(ROOT / "utils/cmake", self.package / "cmake")
        self.yaml_prefix = self.root / "existing yaml-cpp"
        package_config = self.yaml_prefix / "lib/cmake/yaml-cpp"
        package_config.mkdir(parents=True)
        (package_config / "yaml-cpp-config.cmake").write_text("# existing yaml-cpp\n")
        self.input = self.root / "input"
        self.input.mkdir()
        (self.input / "existing.txt").write_text("preserve input\n")
        self.log = self.root / "cmake.jsonl"
        self.env = {key: value for key, value in os.environ.items()
                    if key not in ("SLURM_CLUSTER_NAME", "SLURM_JOB_ID", "CMAKE_BUILD_PARALLEL_LEVEL",
                                   "ELECTRA_YAML_CPP_ARCHIVE", "ELECTRA_YAML_CPP_PREFIX")}
        self.env.update(PATH=f"{self.bin}:{os.environ['PATH']}", USER=os.environ.get("USER", "test"),
                        FAKE_UTILS=str(self.package), FAKE_SLURM=str(self.package_slurm),
                        FAKE_CMAKE_LOG=str(self.log), ELECTRA_YAML_CPP_PREFIX=str(self.yaml_prefix))
        self.tool("docker", '''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys
args = sys.argv[1:]
if args[0] != "run":
    raise SystemExit("Unexpected docker operation")
host, target = args[args.index("-v") + 1].split(":", 1)
source = Path(os.environ["FAKE_UTILS"] if target.rstrip("/") == "/workspace/utils" else os.environ["FAKE_SLURM"])
for item in source.rglob("*"):
    destination = Path(host) / item.relative_to(source)
    if item.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
    elif not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
''')
        self.tool("cmake", '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
args = sys.argv[1:]
with open(os.environ["FAKE_CMAKE_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if "-P" in args:
    dependency = Path(next(arg.split("=", 1)[1] for arg in args if arg.startswith("-DELECTRA_YAML_CPP_DEP_DIR=")))
    source = dependency / "source/yaml-cpp-0.8.0"
    source.mkdir(parents=True, exist_ok=True)
    (source / "CMakeLists.txt").write_text("# downloaded yaml-cpp\\n")
    (source / "LICENSE").write_text("yaml-cpp license\\n")
if "-S" in args and any(arg.startswith("-DCMAKE_INSTALL_PREFIX=") for arg in args):
    build = Path(args[args.index("-B") + 1])
    build.mkdir(parents=True, exist_ok=True)
    prefix = next(arg.split("=", 1)[1] for arg in args if arg.startswith("-DCMAKE_INSTALL_PREFIX="))
    (build / "install-prefix.txt").write_text(prefix)
if "--install" in args:
    build = Path(args[args.index("--install") + 1])
    config = Path((build / "install-prefix.txt").read_text()) / "lib/cmake/yaml-cpp"
    config.mkdir(parents=True, exist_ok=True)
    (config / "yaml-cpp-config.cmake").write_text("# privately installed yaml-cpp\\n")
if "--build" in args:
    if os.environ.get("FAKE_CMAKE_FAIL"):
        raise SystemExit(1)
    binary = Path(args[args.index("--build") + 1]) / "analyze_oscar_output"
    binary.write_text("#!/bin/bash\\necho fake-analyzer\\n")
    binary.chmod(0o755)
''')

    def tool(self, name, source):
        path = self.bin / name
        path.write_text(source)
        path.chmod(0o755)

    def install(self, *args, success=True):
        result = subprocess.run(["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix),
                                 "--input", str(self.input), "--output", str(self.root / "output"),
                                 "--slurm-scripts", str(self.root / "slurm scripts"), *map(str, args)],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_default_install_builds_and_preserves_edited_source(self):
        utils = self.prefix / "utils"
        utils.mkdir(parents=True)
        source = utils / "analyze_oscar_output.cpp"
        source.write_text("user-edited source\n")
        self.install()
        self.assertEqual(source.read_text(), "user-edited source\n")
        self.assertTrue(os.access(utils / "analyze_oscar_output", os.X_OK))
        self.assertTrue(os.access(self.prefix / "electra-shell", os.X_OK))
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(calls[0][calls[0].index("-S") + 1], str(utils))
        self.assertEqual(calls[1][calls[1].index("--build") + 1], str(utils / "build/analysis"))
        self.install()  # Re-running installation invokes an incremental build.
        self.assertEqual(len(self.log.read_text().splitlines()), 4)
        self.assertEqual(source.read_text(), "user-edited source\n")

    def test_custom_utils_and_cluster_defaults(self):
        utils = self.root / "custom utilities"
        self.env["SLURM_CLUSTER_NAME"] = "test"
        self.install("--utils", utils)
        self.assertTrue(os.access(utils / "analyze_oscar_output", os.X_OK))
        script = self.root / "slurm scripts/analysis_submit.sh"
        assignments = "\n".join(line for line in script.read_text().splitlines()
                                if line.startswith(("PROJECT_ROOT=", "ANALYZER=")))
        # Execute the installed defaults to verify shell quoting and path capture.
        env = {key: value for key, value in self.env.items() if key not in ("PROJECT_ROOT", "ANALYZER")}
        result = subprocess.run(["bash", "-c", assignments + '\nprintf "%s\\n%s\\n" "$PROJECT_ROOT" "$ANALYZER"'],
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.splitlines(), [str(self.prefix), str(utils / "analyze_oscar_output")])
        env.update(PROJECT_ROOT="/override", ANALYZER="/custom/analyzer")
        overridden = subprocess.run(["bash", "-c", assignments + '\nprintf "%s\\n%s\\n" "$PROJECT_ROOT" "$ANALYZER"'],
                                    env=env, capture_output=True, text=True, check=True)
        self.assertEqual(overridden.stdout.splitlines(), ["/override", "/custom/analyzer"])
        # Submit and execute a generated batch to check quoting inside its heredoc
        # and the installer's captured --output directory, not just assignments.
        run = self.root / "output/runs/test"
        (run / "ehijing/events").mkdir(parents=True)
        (run / "ehijing/DISKinematics.meta.jsonl").write_text("{}\n")
        manifest = self.root / "manifest.txt"
        manifest.write_text("unused.oscar\n")
        batch = self.root / "batch.sh"
        self.tool("sbatch", '#!/bin/bash\ncat > "$CAPTURE_BATCH"\necho 123\n')
        env = {key: value for key, value in self.env.items()
               if key not in ("PROJECT_ROOT", "ANALYZER", "OUTPUT_HOST", "RUNS_DIR", "RUN_DIR")}
        env["CAPTURE_BATCH"] = str(batch)
        submitted = subprocess.run(["bash", str(script), "RUN_ID=test", "--skip-indexing",
                                    f"FILE_LIST={manifest}", f"SLURM_CONFIG={self.root}/missing.env"],
                                   env=env, capture_output=True, text=True)
        self.assertEqual(submitted.returncode, 0, submitted.stdout + submitted.stderr)
        executed = subprocess.run(["bash", str(batch)], env=env, capture_output=True, text=True)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertIn("fake-analyzer", executed.stdout)

    def test_defer_then_build_from_another_working_directory(self):
        self.install("--skip-analysis-build")
        utils = self.prefix / "utils"
        self.assertFalse(self.log.exists())
        self.assertFalse((utils / "analyze_oscar_output").exists())
        subprocess.run(["bash", str(utils / "build_analysis.sh"), "--jobs", "3",
                        "--build-dir", str(self.root / "custom build"),
                        "--output", str(self.root / "custom binary"), "--", "-DCMAKE_CXX_COMPILER=c++"],
                       cwd=self.root, env=self.env, capture_output=True, text=True, check=True)
        self.assertTrue(os.access(self.root / "custom binary", os.X_OK))
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertIn("-DCMAKE_CXX_COMPILER=c++", calls[0])
        self.assertEqual(calls[1][-2:], ["--parallel", "3"])

    def test_sif_install_also_builds_host_analyzer(self):
        self.tool("apptainer", (self.bin / "docker").read_text()
                  .replace('args[0] != "run"', 'args[0] != "exec"')
                  .replace('args.index("-v")', 'args.index("--bind")'))
        sif = self.root / "electra.sif"
        sif.write_text("local image stand-in\n")
        self.install("--sif", sif)
        self.assertTrue(os.access(self.prefix / "utils/analyze_oscar_output", os.X_OK))
        self.assertEqual(len(self.log.read_text().splitlines()), 2)

    def test_failed_build_preserves_existing_executable(self):
        self.install()
        binary = self.prefix / "utils/analyze_oscar_output"
        binary.write_text("previous working executable\n")
        self.env["FAKE_CMAKE_FAIL"] = "1"
        self.install(success=False)
        self.assertEqual(binary.read_text(), "previous working executable\n")

    def test_missing_build_script_is_actionable(self):
        (self.package / "build_analysis.sh").unlink()
        result = self.install(success=False)
        self.assertIn("analysis build script not found", result.stderr)
        self.assertIn("--skip-analysis-build", result.stderr)

    def test_invalid_jobs_fail_before_cmake(self):
        result = subprocess.run(["bash", str(ROOT / "utils/build_analysis.sh"), "--jobs", "0"],
                                env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive integer", result.stderr)
        self.assertFalse(self.log.exists())

    def test_default_install_privately_builds_dependency(self):
        del self.env["ELECTRA_YAML_CPP_PREFIX"]
        self.install()
        dependency = self.prefix / "utils/build/analysis/deps/yaml-cpp-0.8.0"
        self.assertTrue((dependency / "install/lib/cmake/yaml-cpp/yaml-cpp-config.cmake").exists())
        self.assertTrue((dependency / "install/share/licenses/yaml-cpp/LICENSE").exists())
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 6)
        self.assertIn("-P", calls[0])
        self.assertIn("-DYAML_BUILD_SHARED_LIBS=OFF", calls[1])
        self.assertIn("-DYAML_CPP_INSTALL=ON", calls[1])
        self.assertIn(f"-Dyaml-cpp_DIR={dependency}/install/lib/cmake/yaml-cpp", calls[-2])

    def test_offline_archive_is_forwarded_from_installer_environment(self):
        del self.env["ELECTRA_YAML_CPP_PREFIX"]
        self.env["ELECTRA_YAML_CPP_ARCHIVE"] = str(self.root / "local archive.tar.gz")
        self.install()
        prepare = json.loads(self.log.read_text().splitlines()[0])
        self.assertIn(f"-DELECTRA_YAML_CPP_ARCHIVE={self.env['ELECTRA_YAML_CPP_ARCHIVE']}", prepare)

    def test_bad_archive_is_rejected_before_extraction(self):
        archive = self.root / "bad.tar.gz"
        archive.write_text("not the pinned upstream archive\n")
        dependency = self.root / "dependency"
        result = subprocess.run([shutil.which("cmake"), f"-DELECTRA_YAML_CPP_DEP_DIR={dependency}",
                                 f"-DELECTRA_YAML_CPP_ARCHIVE={archive}",
                                 "-P", str(ROOT / "utils/cmake/prepare_yaml_cpp.cmake")],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertFalse((dependency / "source").exists())

    def test_verified_source_cache_needs_no_archive_or_download(self):
        dependency = self.root / "dependency"
        source = dependency / "source/yaml-cpp-0.8.0"
        source.mkdir(parents=True)
        (source / "CMakeLists.txt").write_text("# cached source\n")
        (dependency / "verified-source.sha256").write_text(
            "fbe74bbdcee21d656715688706da3c8becfd946d92cd44705cc6098bb23b3a16")
        result = subprocess.run([shutil.which("cmake"), f"-DELECTRA_YAML_CPP_DEP_DIR={dependency}",
                                 "-P", str(ROOT / "utils/cmake/prepare_yaml_cpp.cmake")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Downloading", result.stdout)
        self.assertFalse((dependency / "downloads").exists())


if __name__ == "__main__":
    unittest.main()
