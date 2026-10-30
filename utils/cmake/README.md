# OSCAR analysis dependency setup

`prepare_yaml_cpp.cmake` downloads and prepares the yaml-cpp source release
used by `build_analysis.sh`. No third-party source files are vendored here.

- Upstream: https://github.com/jbeder/yaml-cpp
- Version/tag: `0.8.0`
- Source archive: https://github.com/jbeder/yaml-cpp/archive/refs/tags/0.8.0.tar.gz
- SHA-256: `fbe74bbdcee21d656715688706da3c8becfd946d92cd44705cc6098bb23b3a16`
- License: MIT, retained in the downloaded source and copied into the private
  installation's `share/licenses/yaml-cpp/LICENSE`.

The release URL and checksum are pinned in `prepare_yaml_cpp.cmake`.
Archives are verified before extraction, and successful source preparation is
cached under the chosen build directory. A failed download never replaces the
cached archive. `--yaml-cpp-archive` supports offline source builds;
`--yaml-cpp-prefix` uses an existing installation and bypasses this preparation.
