"""Adapt the separate eHIJING checkout's documentation for MyST."""

from pathlib import Path
import argparse
import re
import shutil
import subprocess


def write_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text, encoding="utf-8")


def myst_text(text: str) -> str:
    text = re.sub(
        r"^\\dot[ \t]*\n(.*?)^\\enddot[ \t]*$",
        lambda match: (
            "```{graphviz}\n:align: center\n"
            ":alt: eHIJING event flow with generation, medium processing, hadronization, output and retry paths.\n\n"
            + match[1].strip() + "\n```"
        ),
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    text = re.sub(r"\\f\$(.*?)\\f\$", r"$\1$", text, flags=re.DOTALL)
    text = text.replace(r"\f[", "$$").replace(r"\f]", "$$")
    text = text.replace(r"\[", "$$").replace(r"\]", "$$")
    text = text.replace("# Unit conventions {#unit_conventions}", "(unit-conventions)=\n# Unit conventions")
    text = text.replace(
        "# Physical assumptions and open questions {#physics_assumptions}",
        "(physics-assumptions)=\n# Physical assumptions and open questions",
    )
    text = text.replace("@ref unit_conventions", "[unit conventions](units.md)")
    text = text.replace("(docs/units.md)", "(units.md)")
    text = text.replace("(mainpage.md", "(ehijing.md")
    return text


def prepare_sources(root: Path, docs: Path) -> None:
    source = root / "src" / "ehijing"
    if not (source / "docs" / "units.md").is_file():
        raise RuntimeError(
            "Missing src/ehijing documentation checkout. "
            "See docs/README.md for the component checkout instructions."
        )
    readme = (source / "README.md").read_text(encoding="utf-8")
    sections = [
        ("nuclear-target", "Shared nuclear target and recoil", "Diagnostic spacetime history"),
        ("history", "Diagnostic spacetime history", "Hadronization spacetime trace"),
        ("fragmentation", "Hadronization spacetime trace", "Generating documentation"),
    ]
    destination = docs / "_generated"
    for name, start, end in sections:
        text = readme.split(f"## {start}\n", 1)[1].split(f"## {end}\n", 1)[0]
        # Promote section headings while retaining the component's text.
        text = re.sub(r"^(#{2,}) ", lambda match: match[1][1:] + " ", text, flags=re.MULTILINE)
        write_if_changed(destination / f"{name}.md", myst_text(f"# {start}\n" + text))
    write_if_changed(destination / "units.md", myst_text((source / "docs" / "units.md").read_text()))
    overview = (source / "docs" / "mainpage.md").read_text().split("## Generating The HTML", 1)[0]
    write_if_changed(destination / "ehijing.md", myst_text(overview))
    assumptions = source / "docs" / "assumptions.md"
    if assumptions.is_file():
        assumptions_text = myst_text(assumptions.read_text(encoding="utf-8"))
    else:
        # Older component checkouts do not contain the audit page.
        assumptions_text = """# Physical assumptions and open questions

This checked-out eHIJING revision does not include the assumptions review.
See the [component manual](ehijing.md) and [unit conventions](units.md) for
the documentation supplied by that revision. The full review becomes available
when the component checkout includes `docs/assumptions.md`; CI uses the revision
selected by `docs/ehijing-revision.txt`.
"""
    write_if_changed(destination / "assumptions.md", assumptions_text)
    from electra.cli import build_parser

    parser = build_parser()
    help_sections = ["# CLI help\n\nGenerated from `electra.cli.build_parser()` without running simulations.\n"]

    def collect_help(current: argparse.ArgumentParser) -> None:
        help_sections.append(f"## {current.prog}\n\n```text\n{current.format_help()}```\n")
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    collect_help(child)

    collect_help(parser)
    write_if_changed(destination / "cli-help.txt", "\n".join(help_sections))
    write_if_changed(destination / "cpp-api.md", """# C++ API reference

The eHIJING application is documented in its C++ headers and sources.
Build with `-t cpp-api` and Doxygen installed to embed that reference here.
See [building documentation](../development/documentation.md).
""")


def prepare_cpp_api(root: Path, docs: Path) -> Path:
    executable = shutil.which("doxygen")
    if executable is None:
        raise RuntimeError("The cpp-api build requires Doxygen on PATH. See docs/README.md.")
    output = docs / "_build" / "doxygen"
    # This runs while Sphinx loads conf.py, before Sphinx creates _build.
    # Doxygen versions used in CI require the parent directory to exist.
    output.mkdir(parents=True, exist_ok=True)
    # XML only; exclude third-party sources and component Markdown pages.
    config = f'''PROJECT_NAME = eHIJING
OUTPUT_DIRECTORY = "{output}"
INPUT = "{root / 'src/ehijing/include'}"
RECURSIVE = YES
FILE_PATTERNS = *.hpp *.cpp
EXTRACT_ALL = YES
EXTRACT_PRIVATE = NO
EXTRACT_STATIC = NO
GENERATE_HTML = NO
GENERATE_LATEX = NO
GENERATE_XML = YES
XML_PROGRAMLISTING = NO
QUIET = YES
WARN_IF_UNDOCUMENTED = NO
PREDEFINED = __cplusplus=201703L
ALIASES = "configkey=@par Config key^^"
'''
    subprocess.run([executable, "-"], input=config, text=True, check=True, cwd=root)
    if not (output / "xml" / "index.xml").is_file():
        raise RuntimeError("Doxygen did not produce its XML index.")
    write_if_changed(docs / "_generated" / "cpp-api.md", """# C++ API reference

Generated from eHIJING's public application headers through Doxygen and Breathe.
Third-party implementations are excluded.

```{doxygenindex}
```
""")
    return output / "xml"
