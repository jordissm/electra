# Nuclear geometry database

[`woods_saxon.yaml`](../input/ehijing/woods_saxon.yaml) contains only nucleus entries under
`nuclei`. It covers target options for CLAS, EMC and HERMES, their deuterium
baseline (`d`), and additional Au-197 and U-238 entries.

Keys use the element symbol followed by its mass number (for example,
`He4` and `C12`), with `d` as the special case for deuterium. Entries
are sorted by increasing Z, then A.

## Fields and conventions

| Field | Meaning |
| --- | --- |
| `Z`, `A` | Integer proton and nucleon counts passed to eHIJING |
| `distribution` | `woods_saxon` or `hulthen`, identifying the position distribution |
| `nucleon_width_fm` | Species-specific Gaussian nucleon width in fm |
| `nuclear_radius_fm` | Woods–Saxon radius R in fm; present for Woods–Saxon entries |
| `nuclear_surface_fm` | Woods–Saxon diffuseness a in fm; present for Woods–Saxon entries |
| `hulthen_alpha_fm_inv`, `hulthen_beta_fm_inv` | Hulthén inverse lengths in fm^-1; present for deuterium |

Each species has its own `nucleon_width_fm`; there is no shared defaults
section. All entries initially preserve the existing benchmark width of 0.5 fm.
These widths are independently editable, not species-specific fits. The
Gaussian width is distinct from the Woods–Saxon diffuseness.

For Woods–Saxon entries, the centre density is proportional to
`1 / (1 + exp((r - R)/a))`. Radial sampling includes the volume Jacobian,
`r^2 / (1 + exp((r - R)/a))`, with cutoff `R + 10*a`. R is not an RMS radius.
The explicit target contains exactly A nucleons, with normalized Gaussian
densities, so no separate central density parameter is required.

Coordinates and lengths supplied in fm are converted to GeV^-1 internally.
The current implementation has no deformations, minimum-distance correlations
or recentering for Woods–Saxon entries. The estimates have not been fitted or
deconvolved for the Gaussian nucleon profile. See the
[unit conventions](_generated/units.md).

## Deuterium

The `d` entry has A=2, Z=1 and uses eHIJING's existing Hulthén prescription:

```text
psi(s) proportional to (exp(-alpha*s) - exp(-beta*s)) / s
alpha = 0.228 fm^-1
beta  = 1.18 fm^-1
```

Here s is the proton–neutron separation. Its radial probability is proportional
to `(exp(-alpha*s) - exp(-beta*s))^2`; nucleons are placed at opposite
half-separations about their centre of mass. No Woods–Saxon radius or
diffuseness applies.

These values are loaded from the selected YAML entry into
[`NuclearTarget.h`](../src/ehijing/external/pythia8/include/eHIJING/NuclearTarget.h).
For comparison, the pinned TRENTo implementation samples the radius of one
nucleon about the centre of mass and uses inverse lengths `0.457` and `2.35`
fm^-1. Dividing those by two gives separation-convention parameters `0.2285`
and `1.175` fm^-1. eHIJING's existing rounded constants are retained here.

## Target selection and provenance

The comparison groups are CLAS: C, Fe, Pb; EMC: C, Cu, Sn; and HERMES:
He, Ne, Kr, Xe. Deuterium is the reference target. Integer masses represent
single targets, not natural-isotope mixtures. Choose the intended mass
explicitly, for example `NUCLEUS=Xe129` in
[`slurm-scripts/ehijing_submit.sh`](../slurm-scripts/ehijing_submit.sh).
The representative EMC choices Cu-64 and Sn-119 remain provisional.

| YAML key | Target | Status | Parameter origin |
| --- | --- | --- | --- |
| `d` | deuterium-2 | Existing Hulthén model | Current eHIJING separation parameters above |
| `He4` | helium-4 | Estimate | Hand-selected R=1.30 fm, a=0.30 fm |
| `C12` | carbon-12 | Estimate | Hand-selected R=2.30 fm, a=0.40 fm |
| `Ne20` | neon-20 | Estimate | Empirical mass formula below |
| `Fe56` | iron-56 | Estimate | Empirical mass formula below |
| `Cu63` | copper-63 | TRENTo alternative | Direct spherical parameters |
| `Cu64` | copper-64 | Scaled estimate | TRENTo Cu-63 R multiplied by `(64/63)^(1/3)`; a unchanged |
| `Kr84` | krypton-84 | Estimate | Empirical mass formula below |
| `Sn119` | tin-119 | Estimate | Empirical mass formula below |
| `Xe129` | xenon-129 | TRENTo alternative | Direct spherical parameters |
| `Au197` | gold-197 | TRENTo | Direct spherical parameters |
| `Pb208` | lead-208 | TRENTo | Direct spherical parameters |
| `U238` | uranium-238 | Spherical approximation | TRENTo U radius and diffuseness; deformation omitted |

He-4 and C-12 are provisional spherical surrogates, not measured fits. Review
these first: clustering and realistic few-body configurations are absent.
The Ne estimate also omits possible deformation and clustering. Cu-64 is an
adaptation, not a TRENTo fit for that mass. The current YAML selects Xe-129;
it contains no Xe-131 entry. U-238 uses the spherical distribution specified
in the YAML rather than TRENTo's deformed U prescription.

### TRENTo source

Retrieved on 2026-10-30 from [Duke-QCD/trento](https://github.com/Duke-QCD/trento),
commit `7ef92367c51d2ef1a8946973d17a90fdd3c31f5e`:

- [Nuclear parameters and sampling](https://github.com/Duke-QCD/trento/blob/7ef92367c51d2ef1a8946973d17a90fdd3c31f5e/src/nucleus.cxx)
- [Deuteron constructor defaults](https://github.com/Duke-QCD/trento/blob/7ef92367c51d2ef1a8946973d17a90fdd3c31f5e/src/nucleus.h)
- [Conventions and Gaussian nucleon profile](https://github.com/Duke-QCD/trento/blob/7ef92367c51d2ef1a8946973d17a90fdd3c31f5e/doc/usage.rst)

This version directly provides spherical Cu-63, Xe-129, Au-197 and Pb-208
parameters, and R/a values for deformed U-238, but no He, Ne, Kr, C, Sn or Fe
Woods–Saxon sets. The database uses spherical Cu and Xe, rather than the
deformed Cu2 and Xe2 alternatives. Its initial
0.5 fm Gaussian width also matches TRENTo's default.

### Empirical fallback

Ne, Kr, Sn and Fe use the generic density prescription

```text
R = 1.12*A^(1/3) - 0.86*A^(-1/3) fm
a = 0.54 fm
```

R is rounded to four decimal places. See
[Sollfrank, Huovinen and Ruuskanen, equations (3)–(4), page 4](https://arxiv.org/pdf/nucl-th/9706012).
These are starting estimates, not TRENTo tabulated values or experimental fits
for the selected nuclei. The heavy-nucleus formula is avoided for He and C.

## Using the catalogue

Select a target by its YAML key, alongside the other required run arguments:

```text
ehijing --nucleus C12 ...
electra ehijing run --nucleus C12 ...
```

The C++ executable loads A, Z, the Gaussian width and distribution parameters
from that entry. Deuterium is selected with `--nucleus d`. The Python wrapper
defaults to `d` when neither a name nor legacy A/Z arguments are supplied.
`--nucleus-database PATH` selects a different YAML file. Default lookup checks:

- `ELECTRA_NUCLEUS_DATABASE`, if set;
- `input/ehijing/woods_saxon.yaml` relative to the working directory;
- `../share/electra/ehijing/woods_saxon.yaml` relative to the executable;
- the source and installation paths configured at build time.

An explicit path or environment override must exist; it does not fall back to
a different file on failure. Unknown names, missing fields, unsupported
distributions, nonpositive/nonfinite parameters and invalid compositions are
rejected before event generation. Inspect the resolved parameters without
initializing PYTHIA or generating events:

```bash
ehijing --nucleus C12 --describe-nucleus
```

The distribution must be `hulthen` for A=2, Z=1 or `woods_saxon` for A>2.
Hulthén inverse lengths are read from YAML and must satisfy `0 < alpha < beta`.
Explicit `--nucleon-width-fm`, `--nuclear-radius-fm` and `--nuclear-surface-fm`
options override the corresponding YAML values; Woods–Saxon overrides are
rejected for Hulthén entries. Legacy `--Z` and `--A` remain supported instead
of `--nucleus`, but cannot be mixed with a name or database option.

Named-target event metadata and the Python manifest include the resolved
parameters and database SHA-256. The Python wrapper checks these against the
request and includes them in resume protection. Editing the YAML therefore
requires a new run directory for overlapping completed chunks.

`--nuclear-target` is a separate runtime switch, not a nucleus parameter. The
current ELECTRA executable defaults to `on`, enabling the explicit geometry
described here. `--nuclear-target off` selects the legacy continuous-medium
implementation, which bypasses these explicit-target geometry parameters.

On SLURM, use `NUCLEUS=C12` (default `d`) and optional
`NUCLEUS_DATABASE=/absolute/host/path/nuclei.yaml`. The submit script binds the
selected file read-only into the container. `NUCLEON_WIDTH_FM`,
`NUCLEAR_RADIUS_FM` and `NUCLEAR_SURFACE_FM` optionally override the YAML values;
omit the last two for deuterium. `NUCLEAR_TARGET=on|off` controls the runtime
switch independently. See the
[configuration guide](configuration.md).

## Build and installation

The C++ build now requires yaml-cpp. CMake installs the selected database
under `share/electra/ehijing`. For an independent eHIJING checkout, set
`-DEHIJING_NUCLEUS_DATABASE=/path/to/woods_saxon.yaml` during configuration.
Rebuild the modified PYTHIA library, application and XML settings together;
the target ABI version is 2. The container recipe builds the local
`src/ehijing` checkout and includes the database; CI checks out that repository
before preparing the build context. No Python YAML dependency is required:
the wrapper queries the executable's reader via `--describe-nucleus`.
