#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  fix_smash_hepmc_vertices.sh /path/to/run_or_output_dir

This searches recursively for files named:
  SMASH_HepMC_collisions.asciiv3

And writes next to each one:
  SMASH_HepMC_collisions_fixed.asciiv3

Edits performed (vertex barcode shift fix):
  - E: 2nd number (nVertices) -= 1
  - V: 1st number (vertex id) += 1
  - P: 2nd number (production vertex id) += 1, except if it is 0
  - A: 1st number (id) += 1, except for "A 0 GenHeavyIon ..."
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

root="$1"
if [[ ! -d "$root" ]]; then
  echo "ERROR: '$root' is not a directory" >&2
  exit 2
fi

found=0

while IFS= read -r -d '' f; do
  found=1
  out_dir="$(dirname "$f")"
  out="${out_dir}/SMASH_HepMC_collisions_fixed.asciiv3"

  awk '
    BEGIN { OFS=" " }

    # Event header: E <evt> <nVertices> <nParticles>
    $1=="E" {
      $3 = $3 - 1
      print
      next
    }

    # Vertex: V <vtx_id> ...
    $1=="V" {
      $2 = $2 + 1
      print
      next
    }

    # Particle: P <pid> <prod_vtx> ...
    # Keep initial particles with prod_vtx == 0 unchanged.
    $1=="P" {
      if ($3 != 0) $3 = $3 + 1
      print
      next
    }

    # Attribute: A <id> <name> ...
    # Do NOT touch the GenHeavyIon line (usually: A 0 GenHeavyIon ...)
    $1=="A" {
      if ($3 != "GenHeavyIon") $2 = $2 + 1
      print
      next
    }

    # Everything else unchanged
    { print }
  ' "$f" > "$out"

  echo "Wrote: $out"
done < <(find "$root" -type f -name 'SMASH_HepMC_collisions.asciiv3' -print0)

if [[ $found -eq 0 ]]; then
  echo "No SMASH_HepMC_collisions.asciiv3 files found under: $root" >&2
  exit 3
fi
