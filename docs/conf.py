"""Sphinx configuration for the ELECTRA manual and API reference."""

from pathlib import Path
import sys
import tomllib

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(DOCS / "_ext"))

from project_docs import prepare_sources, prepare_cpp_api

project = "ELECTRA"
author = "ELECTRA Collaboration"
release = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.mathjax",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
]
myst_enable_extensions = ["dollarmath", "amsmath", "colon_fence"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = ["_build", ".venv", "README.md"]
nitpicky = True
# External types are outside the application API documented here.
nitpick_ignore = [("py:class", "pathlib.Path"), ("py:class", "argparse.ArgumentParser")]
nitpick_ignore_regex = [
    ("cpp:identifier", r"(?:Pythia8|EHIJING|HepMC3)(?:::[\w:]+)?"),
    ("cpp:identifier", r"(?:Particle|Pythia|u?int(?:32|64)_t)"),
]
html_theme = "sphinx_rtd_theme"
html_theme_options = {"navigation_depth": 3}
html_title = "ELECTRA documentation"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
latex_documents = [("index", "electra.tex", "ELECTRA Documentation", author, "manual")]

# The component checkout is intentionally separate from the ELECTRA repository.
# Generate manual pages from its existing documentation, without editing it.
prepare_sources(ROOT, DOCS)
if tags.has("cpp-api"):
    extensions.append("breathe")
    breathe_projects = {"ehijing": str(prepare_cpp_api(ROOT, DOCS))}
    breathe_default_project = "ehijing"
