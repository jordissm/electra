# ELECTRA documentation build

The manual uses Sphinx, MyST Markdown, MathJax, Python autodoc and optional
Doxygen/Breathe C++ references. Run commands from the ELECTRA repository root.
Use Python 3.11 or newer for the documentation toolchain.

## Component checkout

`src/ehijing` is a separate repository, ignored by ELECTRA. If it is absent:

```bash
git clone https://github.com/jordissm/ehijing.git src/ehijing
git -C src/ehijing checkout "$(cat docs/ehijing-revision.txt)"
```

Do not reset an existing working checkout to build documentation. Local builds
use that checkout, including its documentation edits. CI checks out the revision
in `ehijing-revision.txt`. Update the pin deliberately when adopting component
changes; no SMASH/PYTHIA checkout or physics build is required for this manual.

## Build

```bash
python3 -m venv docs/.venv
docs/.venv/bin/python -m pip install -r docs/requirements.txt
docs/.venv/bin/sphinx-build -b html -W --keep-going docs docs/_build/html
```

With Doxygen available on PATH, include the C++ API:

```bash
docs/.venv/bin/sphinx-build -t cpp-api -b html -W --keep-going docs docs/_build/html
```

Open `docs/_build/html/index.html`, or serve it locally:

```bash
docs/.venv/bin/python -m http.server 8000 --directory docs/_build/html
```

Then visit <http://localhost:8000>. MathJax is loaded from a CDN by default.
The full HTML artifact is validated in CI; Pages deployment is manual.
See `development/documentation.md` for authoring and publishing instructions.

Build products and generated component pages are ignored by Git. Keep source
guides in this directory and physics/interface details in the component checkout.
