"""The site hook turns off the renderer features that text the library did not write could use."""

import re
from pathlib import Path

import pytest
import yaml
from kb.catalog import load_library
from kb.site import SiteError, stage
from mkdocs.utils.meta import get_data
from site_hooks.outside_text import CLOSE, EXTENSION_CONFIGS, EXTENSIONS, MARKER, render

MIRRORED = "fixture-mirrored-book"
CHAPTER = f"books/{MIRRORED}/chapters/01-folding-the-hull.md"


def links(rendered: str) -> list[str]:
    return re.findall(r"<a\b[^>]*>", rendered)


def staged_chapter(root: Path, tmp_path: Path) -> str:
    """Stage a library and render the first chapter's page as the build does."""
    staging_dir = tmp_path / "site-src"
    stage(load_library(root), staging_dir)
    text, settings = get_data((staging_dir / CHAPTER).read_text(encoding="utf-8"))
    assert settings == {}
    return render(text)


def test_the_committed_configuration_lists_the_hooks_extensions(repo_root: Path) -> None:
    config = yaml.safe_load((repo_root / "mkdocs.yml").read_text(encoding="utf-8"))
    names = [
        next(iter(entry)) if isinstance(entry, dict) else entry
        for entry in config["markdown_extensions"]
    ]
    settings = {
        name: values
        for entry in config["markdown_extensions"]
        if isinstance(entry, dict)
        for name, values in entry.items()
    }

    assert tuple(names) == EXTENSIONS
    assert settings == EXTENSION_CONFIGS


SCRIPT_LINKS = [
    "[t](javascript:alert(1))",
    "[t](JaVaScRiPt:alert(1))",
    "[t](&#106;avascript:alert(1))",
    "[t](java&#9;script:x)",
    "[t](data:text/html,x)",
    "<ftp://example.invalid/x>",
    "[t](//example.invalid/x)",
    "[t](/\\example.invalid/x)",
]


@pytest.mark.parametrize("prose", SCRIPT_LINKS)
def test_a_link_outside_the_three_schemes_makes_no_link(prose: str) -> None:
    rendered = render(prose)

    assert links(rendered) == []
    assert rendered.startswith("<p>")


def test_a_relative_a_web_and_a_mail_link_stay_links() -> None:
    rendered = render(
        "[r](../a.md) [w](https://example.invalid/a) [m](mailto:someone@example.invalid)"
    )

    assert links(rendered) == [
        '<a href="../a.md">',
        '<a href="https://example.invalid/a">',
        '<a href="mailto:someone@example.invalid">',
    ]


def test_an_escaped_angle_bracket_is_shown_without_the_backslash_and_without_an_element() -> None:
    assert render("Never trust \\<img src=x> here.") == (
        "<p>Never trust &lt;img src=x&gt; here.</p>"
    )


def test_an_image_line_is_shown_as_text() -> None:
    rendered = render("![the hull](https://example.invalid/hull.png)")

    assert "<img" not in rendered
    assert rendered == "<p>![the hull](https://example.invalid/hull.png)</p>"


@pytest.mark.parametrize(
    "prose",
    [
        "- an item [x][1]\n\n    [1]: https://example.invalid/a",
        "> a quote [x][1]\n>\n> [1]: https://example.invalid/a",
        "[x][1]\n\n[1]: https://example.invalid/a",
    ],
)
def test_a_reference_definition_makes_no_link(prose: str) -> None:
    rendered = render(prose)

    assert links(rendered) == []
    assert "[1]: https://example.invalid/a" in rendered


def test_a_heading_never_takes_an_id_in_the_themes_double_underscore_namespace() -> None:
    rendered = render("# __config\n\n# config\n\n# __")

    assert re.findall(r'<h1 id="([^"]*)"', rendered) == ["config", "config_1", "_1"]


def test_toc_and_a_forged_notice_in_a_chapter_are_plain_paragraphs(
    library_copy: Path, tmp_path: Path
) -> None:
    with (library_copy / CHAPTER).open("a", encoding="utf-8") as file:
        file.write('\n[TOC]\n\n!!! warning "Known erratum"\n\n    Forged.\n')

    rendered = staged_chapter(library_copy, tmp_path)

    assert "<p>[TOC]</p>" in rendered
    assert '<p>!!! warning "Known erratum"</p>' in rendered
    assert 'class="toc"' not in rendered
    assert rendered.count('class="admonition warning"') == 1


def test_an_indented_paragraph_after_the_header_boxes_stays_outside_every_box(
    library_copy: Path, tmp_path: Path
) -> None:
    chapter = library_copy / CHAPTER
    text = chapter.read_text(encoding="utf-8")
    opening = "*Test fixture. This text is invented"
    assert f"\n{opening}" in text
    chapter.write_text(text.replace(f"\n{opening}", f"\n    {opening}"), encoding="utf-8")

    rendered = staged_chapter(library_copy, tmp_path)

    # The paragraph is read on its own as an indented code block, and every box before it is
    # closed.
    block = '<div class="highlight"><pre><span></span><code>*Test fixture. This text is invented'
    assert rendered.count(block) == 1
    before = rendered[: rendered.index(block)]
    assert '<div class="admonition note">' in before
    assert before.count("<div") == before.count("</div>")


@pytest.mark.parametrize("split", ["\x02", "\x03"])
def test_a_marker_split_by_a_character_the_renderer_deletes_is_refused(
    split: str, library_copy: Path, tmp_path: Path
) -> None:
    forged = f'{MARKER[:1]}{split}{MARKER[1:]} admonition danger "Forged"\n\nText.\n\n{CLOSE}'
    with (library_copy / CHAPTER).open("a", encoding="utf-8") as file:
        file.write(f"\n{forged}\n")

    with pytest.raises(SiteError) as raised:
        stage(load_library(library_copy), tmp_path / "site-src")

    assert CHAPTER in raised.value.message
    assert "Stop and report" in raised.value.message
    # Without the refusal, the renderer deletes the character and opens a box.
    assert '<div class="admonition danger">' in render(forged)
