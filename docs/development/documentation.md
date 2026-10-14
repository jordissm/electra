# Building and writing documentation

## Build the manual

The documentation toolchain requires Python 3.11 or newer and Graphviz (`dot`
on `PATH`) for the flow diagrams. The runtime CLI
continues to support Python 3.10. From the repository root:

```bash
python3 -m venv docs/.venv
docs/.venv/bin/python -m pip install -r docs/requirements.txt
docs/.venv/bin/sphinx-build -b html -W --keep-going docs docs/_build/html
```

Open `docs/_build/html/index.html`. Install Doxygen and add `-t cpp-api` for
the embedded C++ reference:

```bash
docs/.venv/bin/sphinx-build -t cpp-api -b html -W --keep-going docs docs/_build/html
```

The full build generates XML under `docs/_build/doxygen` and includes it
through Breathe. It reads public application headers and excludes third-party
code. Neither build compiles the simulation executables or generates events.

The [build README](https://github.com/jordissm/electra/blob/main/docs/README.md)
has the pinned eHIJING checkout instructions for a fresh ELECTRA clone.

## Sources and maintenance

Write project guides in `docs/`. Add new pages to the toctree in `index.md`.
Keep the root README concise, with setup instructions and links to the manual.

The eHIJING physics and interface documentation remains authoritative in
`src/ehijing/README.md` and `src/ehijing/docs/`. During configuration,
`docs/_ext/project_docs.py` splits those pages into the ignored
`docs/_generated/` directory and converts Doxygen math delimiters to MyST.
Do not edit generated pages. Local builds use the existing component checkout;
CI uses `docs/ehijing-revision.txt`. When updating that pin, review the component
documentation and confirm it describes the executable version you intend to use.

The CLI help is generated from the actual argument parser. Python API entries
come from docstrings; C++ API entries come from Doxygen comments.

The eHIJING manual's flow diagram is authored as a Doxygen `\dot` / `\enddot`
block in `src/ehijing/docs/mainpage.md`. The adapter converts that block to a
MyST `graphviz` directive, so Sphinx and standalone Doxygen render the same
diagram. HTML uses scalable SVG; keep this single diagram source alongside
the physics text when the execution flow changes.

The assumptions review is maintained in `src/ehijing/docs/assumptions.md` and
adapted into its own manual page. For an older pinned component revision that
does not contain that file, the manual displays an availability notice rather
than presenting a review of a different implementation.

## LaTeX mathematics

MyST supports inline math such as `$Q^2$` and display math enclosed in `$$`.
Use a math directive for a labelled equation:

````markdown
```{math}
:label: unit-conversion

1\,\mathrm{fm} = 10^{-12}\,\mathrm{mm}
```

See equation {eq}`unit-conversion`.
````

The rendered example is:

```{math}
:label: unit-conversion

1\,\mathrm{fm} = 10^{-12}\,\mathrm{mm}
```

Equation {eq}`unit-conversion` uses the same conversion as the
[interface conventions](../_generated/units.md).
The `amsmath` extension also accepts AMS equation environments.
HTML uses MathJax, without a local TeX installation. By default its JavaScript
is loaded from a CDN, so viewing equations requires network access.
MathJax supports LaTeX math notation, rather than arbitrary LaTeX packages.

Sphinx can also produce a PDF manual with a suitable TeX installation:

```bash
docs/.venv/bin/sphinx-build -M latexpdf docs docs/_build
```

See the [MyST math guide](https://myst-parser.readthedocs.io/en/latest/syntax/optional.html#math-shortcuts)
and [Sphinx math support](https://www.sphinx-doc.org/en/master/usage/extensions/math.html).

## CI and GitHub Pages

The documentation workflow validates the full HTML build on pull requests and
pushes to `main`, and uploads it as an artifact. Publishing is a separate,
manual workflow option. To publish, configure the repository's Pages source
as **GitHub Actions**, then run the documentation workflow on `main` with
**Publish to GitHub Pages** enabled. It does not modify the image-build workflow.
