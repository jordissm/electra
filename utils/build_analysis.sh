#!/usr/bin/env bash
# Build the standalone OSCAR analyzer from a checkout or installed utilities.
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SOURCE_DIR/build/analysis"
OUTPUT="$SOURCE_DIR/analyze_oscar_output"
YAML_CPP_PREFIX="${ELECTRA_YAML_CPP_PREFIX:-}"
YAML_CPP_ARCHIVE="${ELECTRA_YAML_CPP_ARCHIVE:-}"
JOBS="${CMAKE_BUILD_PARALLEL_LEVEL:-}"
if [[ -z "$JOBS" ]]; then
    JOBS="$(nproc 2>/dev/null || true)"
    if [[ ! "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
        JOBS="$(sysctl -n hw.ncpu 2>/dev/null || true)"
    fi
    if [[ ! "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
        JOBS=2
    fi
fi
CMAKE_ARGS=()

usage() {
    cat <<EOF
Usage: bash $0 [options] [-- additional CMake configure arguments]

Builds the YAML-enabled analyzer on the current host. By default downloads,
verifies, and privately installs static yaml-cpp 0.8.0 under the build directory.
Run this script again after editing the installed C++ sources or headers.

Options:
  --jobs N           Parallel build jobs (default: $JOBS; CMake env, nproc, macOS CPU count, or 2)
  --build-dir PATH   CMake build directory (default: $BUILD_DIR)
  --output PATH      Executable destination (default: $OUTPUT)
  --yaml-cpp-prefix PATH  Use an existing yaml-cpp installation; skip dependency build
  --yaml-cpp-archive PATH Use the official 0.8.0 source archive for an offline build
  -h, --help         Show this help

ELECTRA_YAML_CPP_PREFIX and ELECTRA_YAML_CPP_ARCHIVE supply the same dependency
options when this script is called automatically by install.sh.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --jobs|--build-dir|--output|--yaml-cpp-prefix|--yaml-cpp-archive)
            if [[ $# -lt 2 || -z "$2" ]]; then
                echo "Error: $1 requires a value." >&2
                exit 1
            fi
            case "$1" in
                --jobs) JOBS="$2" ;;
                --build-dir) BUILD_DIR="$2" ;;
                --output) OUTPUT="$2" ;;
                --yaml-cpp-prefix) YAML_CPP_PREFIX="$2" ;;
                --yaml-cpp-archive) YAML_CPP_ARCHIVE="$2" ;;
            esac
            shift 2
            ;;
        --) shift; CMAKE_ARGS=("$@"); break ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Error: unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [[ ! "$JOBS" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: --jobs must be a positive integer." >&2
    exit 1
fi
if ! command -v cmake >/dev/null 2>&1; then
    echo "Error: building the analyzer requires CMake and a host C++17 compiler." >&2
    echo "Install/load those tools, then rerun: bash $SOURCE_DIR/build_analysis.sh" >&2
    exit 1
fi
if [[ ! -f "$SOURCE_DIR/CMakeLists.txt" || ! -f "$SOURCE_DIR/analyze_oscar_output.cpp" ||
      ! -f "$SOURCE_DIR/oscar_analysis.hpp" || ! -f "$SOURCE_DIR/cmake/prepare_yaml_cpp.cmake" ]]; then
    echo "Error: incomplete analysis sources in $SOURCE_DIR; deploy the complete utils directory including cmake." >&2
    exit 1
fi
if [[ -n "$YAML_CPP_PREFIX" && -n "$YAML_CPP_ARCHIVE" ]]; then
    echo "Error: choose --yaml-cpp-prefix or --yaml-cpp-archive, not both." >&2
    exit 1
fi

mkdir -p "$BUILD_DIR" "$(dirname "$OUTPUT")"
BUILD_DIR="$(cd "$BUILD_DIR" && pwd)"
OUTPUT="$(cd "$(dirname "$OUTPUT")" && pwd)/$(basename "$OUTPUT")"

if [[ -z "$YAML_CPP_PREFIX" ]]; then
    YAML_CPP_DEP_DIR="$BUILD_DIR/deps/yaml-cpp-0.8.0"
    cmake "-DELECTRA_YAML_CPP_DEP_DIR=$YAML_CPP_DEP_DIR" \
          "-DELECTRA_YAML_CPP_ARCHIVE=$YAML_CPP_ARCHIVE" -P "$SOURCE_DIR/cmake/prepare_yaml_cpp.cmake"
    YAML_CPP_SOURCE="$YAML_CPP_DEP_DIR/source/yaml-cpp-0.8.0"
    YAML_CPP_PREFIX="$YAML_CPP_DEP_DIR/install"
    cmake -S "$YAML_CPP_SOURCE" -B "$YAML_CPP_DEP_DIR/build" ${CMAKE_ARGS[@]+"${CMAKE_ARGS[@]}"} \
        -DCMAKE_BUILD_TYPE=Release "-DCMAKE_INSTALL_PREFIX=$YAML_CPP_PREFIX" -DCMAKE_INSTALL_LIBDIR=lib \
        -DYAML_CPP_BUILD_TESTS=OFF -DYAML_CPP_BUILD_TOOLS=OFF -DYAML_CPP_FORMAT_SOURCE=OFF \
        -DYAML_CPP_INSTALL=ON -DYAML_BUILD_SHARED_LIBS=OFF
    cmake --build "$YAML_CPP_DEP_DIR/build" --config Release --target yaml-cpp --parallel "$JOBS"
    cmake --install "$YAML_CPP_DEP_DIR/build" --config Release
    mkdir -p "$YAML_CPP_PREFIX/share/licenses/yaml-cpp"
    install -m 0644 "$YAML_CPP_SOURCE/LICENSE" "$YAML_CPP_PREFIX/share/licenses/yaml-cpp/LICENSE"
fi

YAML_CPP_CONFIG_DIR=""
for candidate in "$YAML_CPP_PREFIX/lib/cmake/yaml-cpp" "$YAML_CPP_PREFIX/lib64/cmake/yaml-cpp" \
                 "$YAML_CPP_PREFIX/share/cmake/yaml-cpp"; do
    if [[ -f "$candidate/yaml-cpp-config.cmake" || -f "$candidate/yaml-cppConfig.cmake" ]]; then
        YAML_CPP_CONFIG_DIR="$(cd "$candidate" && pwd)"
        break
    fi
done
if [[ -z "$YAML_CPP_CONFIG_DIR" ]]; then
    echo "Error: no yaml-cpp CMake package found under $YAML_CPP_PREFIX (expected lib[/64]/cmake/yaml-cpp)." >&2
    exit 1
fi

cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release ${CMAKE_ARGS[@]+"${CMAKE_ARGS[@]}"} "-Dyaml-cpp_DIR=$YAML_CPP_CONFIG_DIR"
cmake --build "$BUILD_DIR" --config Release --target analyze_oscar_output --parallel "$JOBS"

BINARY="$BUILD_DIR/analyze_oscar_output"
if [[ -x "$BUILD_DIR/Release/analyze_oscar_output" ]]; then
    BINARY="$BUILD_DIR/Release/analyze_oscar_output"
fi
if [[ ! -x "$BINARY" ]]; then
    echo "Error: build did not produce an executable: $BINARY" >&2
    exit 1
fi
if [[ "$BINARY" != "$OUTPUT" ]]; then
    # Preserve the last working executable if configuration or compilation fails.
    TEMP_EXECUTABLE="$(mktemp "$(dirname "$OUTPUT")/.analyze_oscar_output.XXXXXX")"
    trap 'rm -f "$TEMP_EXECUTABLE"' EXIT
    install -m 0755 "$BINARY" "$TEMP_EXECUTABLE"
    mv -f "$TEMP_EXECUTABLE" "$OUTPUT"
    trap - EXIT
fi
echo "Analyzer built: $OUTPUT"
