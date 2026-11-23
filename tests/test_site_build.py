"""A real MkDocs build of a copy of the fixture library shows outside text and never runs it."""

import html
import re
from pathlib import Path

import pytest
import yaml
from conftest import write_root_files
from kb.catalog import load_library
from kb.readpath import source_label
from kb.site import (
    CONFIG_FILE,
    HOOK,
    SITE_DIR,
    STAGING_DIR,
    SiteError,
    build_site,
    run_mkdocs,
    stage,
    write_config,
)
from kb.site_check import site_problems
from site_hooks.outside_text import MARKER, render

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"
CHAPTER = f"books/{MIRRORED}/chapters/01-folding-the-hull.md"
TOPIC = "topics/paper-craft.md"
OVERVIEW = f"books/{MIRRORED}/index.md"
SOURCE_PATH = "Paper-Boat-Engineering-v1.0.0.pdf"
HOSTILE_PATH = "a/b.<img src=x onerror=alert(1)>"
RAW_HTML = 'Inline <b onclick="alert(1)">bold</b> here.\n\n<div onclick="alert(1)">block</div>'

_ARTICLE = re.compile(r"<article\b[^>]*>(?P<content>.*)</article>", re.DOTALL)


def build(root: Path) -> Path:
    """Stage a library, write its configuration, and run the strict MkDocs build."""
    library = load_library(root)
    staging_dir = root / STAGING_DIR
    config_file = root / CONFIG_FILE
    site_dir = root / SITE_DIR
    navigation = stage(library, staging_dir)
    write_config(library, navigation, config_file, docs_dir=staging_dir, site_dir=site_dir)
    run_mkdocs(config_file)
    return site_dir


def append(root: Path, canonical: str, text: str) -> None:
    with (root / canonical).open("a", encoding="utf-8") as file:
        file.write(f"\n{text}\n")


def replace(root: Path, canonical: str, old: str, new: str) -> None:
    path = root / canonical
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def built_page(site_dir: Path, canonical: str) -> str:
    page = canonical.removesuffix(".md").removesuffix("index")
    return (site_dir / page / "index.html").read_text(encoding="utf-8")


def article(page: str) -> str:
    found = _ARTICLE.search(page)
    assert found is not None
    return found["content"]


def test_chapter_text_cannot_set_an_id_on_a_link(library_copy: Path) -> None:
    append(library_copy, CHAPTER, "A link [x](https://h/\\(c){#__config}d) here.")

    content = article(built_page(build(library_copy), CHAPTER))

    links = re.findall(r"<a\b[^>]*>", content)
    assert [link for link in links if "__config" in link] == []
    assert "{#__config}d)" in html.unescape(content)


def test_markup_in_a_source_path_is_shown_as_text_on_the_overview_page(
    library_copy: Path,
) -> None:
    # Validation is not run, so the path reaches staging as the record holds it.
    replace(library_copy, CHAPTER, f"path: {SOURCE_PATH}", f'path: "{HOSTILE_PATH}"')

    content = article(built_page(build(library_copy), OVERVIEW))

    assert re.search(r"<img", content, re.IGNORECASE) is None
    assert "source <IMG SRC=X ONERROR=ALERT(1)> pp. 3-4" in html.unescape(content)


def test_the_raw_source_label_renders_as_text_without_the_display_escape() -> None:
    rendered = render(f"- [§01 Folding the Hull](x.md), {source_label(HOSTILE_PATH)} pp. 3-4")

    assert re.search(r"<img", rendered, re.IGNORECASE) is None
    assert "source &lt;IMG SRC=X ONERROR=ALERT(1)&gt; pp. 3-4" in rendered


@pytest.mark.parametrize("canonical", [CHAPTER, TOPIC])
def test_raw_html_inline_and_as_a_block_is_shown_as_text(
    canonical: str, library_copy: Path
) -> None:
    append(library_copy, canonical, RAW_HTML)

    content = article(built_page(build(library_copy), canonical))

    assert "<b " not in content
    assert "<div onclick" not in content
    shown = html.unescape(content)
    assert 'Inline <b onclick="alert(1)">bold</b> here.' in shown
    assert '<div onclick="alert(1)">block</div>' in shown


def test_a_topic_that_opens_with_settings_lines_keeps_its_template_and_title(
    library_copy: Path,
) -> None:
    replace(
        library_copy,
        TOPIC,
        "---\n\n# Paper Craft\n",
        "---\ntemplate: redirect.html\ntitle: X\n\n# Paper Craft\n",
    )

    page = built_page(build(library_copy), TOPIC)

    assert "window.location.replace" not in page
    assert re.search(r"<title>Paper Craft - Fixture Library</title>", page)
    assert "template: redirect.html" in article(page)


def test_a_catalog_card_heading_keeps_the_resource_id_that_a_topic_links_to(
    library_copy: Path,
) -> None:
    site_dir = build(library_copy)

    catalog = article(built_page(site_dir, "catalog.md"))
    topic = article(built_page(site_dir, TOPIC))
    assert re.search(
        rf'<div class="library-card library-card--reference-only">\s*<h3 id="{REFERENCE}">',
        catalog,
    )
    assert f'href="../../catalog/#{REFERENCE}"' in topic


def test_the_library_boxes_keep_the_class_names_the_stylesheet_and_theme_style(
    library_copy: Path,
) -> None:
    site_dir = build(library_copy)

    chapter = article(built_page(site_dir, CHAPTER))
    catalog = article(built_page(site_dir, "catalog.md"))
    assert re.search(r'<div class="library-facts">\s*<ul>', chapter)
    assert re.search(
        r'<div class="admonition note">\s*<p class="admonition-title">Machine-extracted</p>',
        chapter,
    )
    assert re.search(
        r'<div class="library-status library-status--mirrored">\s*<p>Mirrored</p>\s*</div>',
        catalog,
    )


def test_the_fixture_copy_builds_strictly_with_the_hook_from_the_generated_config(
    library_copy: Path,
) -> None:
    # Only the hook rewrites a heading id that starts with underscores.
    append(library_copy, CHAPTER, "## __config")

    site_dir = build(library_copy)

    config_file = library_copy / CONFIG_FILE
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert [(config_file.parent / hook).resolve() for hook in config["hooks"]] == [HOOK]
    assert '<h2 id="config">__config' in article(built_page(site_dir, CHAPTER))
    assert site_problems(site_dir) == []


MARKED = [
    (CHAPTER, None),
    (TOPIC, None),
    (f"books/{MIRRORED}/metadata.yaml", "notices:\n"),
    (f"books/{MIRRORED}/LICENSE", None),
]


@pytest.mark.parametrize(("canonical", "after"), MARKED)
def test_the_box_marker_in_outside_text_stops_the_build_before_any_page_is_written(
    canonical: str, after: str | None, library_copy: Path
) -> None:
    write_root_files(library_copy)
    if after is None:
        append(library_copy, canonical, f"{MARKER} admonition danger")
    else:
        replace(library_copy, canonical, after, f'{after}  - "{MARKER} admonition danger"\n')

    with pytest.raises(SiteError) as raised:
        build_site(load_library(library_copy))

    assert raised.value.step == "staging"
    assert canonical in raised.value.message
    assert "Stop and report" in raised.value.message
    assert not (library_copy / SITE_DIR).exists()
