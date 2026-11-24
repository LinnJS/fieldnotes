"""The check of the built site: every served file is read whole against what the library writes.

The pages these tests change come from a real build of the fixture library with the pinned
theme, so a test holds only the one change it names.
"""

import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest
from conftest import FIXTURE_LIBRARY_ROOT
from kb.catalog import load_library
from kb.site import CONFIG_FILE, SITE_DIR, STAGING_DIR, run_mkdocs, stage, write_config
from kb.site_check import Problem, SiteAddresses, page_base, page_problems, site_problems
from site_hooks.outside_text import render

ADDRESSES = SiteAddresses(
    "https://example.invalid/fixture-library/",
    "https://example.invalid/fixture-owner/fixture-library",
)
CHAPTER_PAGE = "books/fixture-mirrored-book/chapters/01-folding-the-hull/index.html"
TOPIC_PAGE = "topics/paper-craft/index.html"
_ARTICLE = re.compile(r"(<article\b[^>]*>)(.*)(</article>)", re.DOTALL)


@pytest.fixture(scope="session")
def built_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a copy of the fixture library with the pinned theme, once for this module."""
    root = tmp_path_factory.mktemp("site-check") / "library"
    shutil.copytree(FIXTURE_LIBRARY_ROOT, root, ignore=shutil.ignore_patterns("build", "dist"))
    library = load_library(root)
    navigation = stage(library, root / STAGING_DIR)
    write_config(
        library,
        navigation,
        root / CONFIG_FILE,
        docs_dir=root / STAGING_DIR,
        site_dir=root / SITE_DIR,
    )
    run_mkdocs(root / CONFIG_FILE)
    return root / SITE_DIR


@pytest.fixture(scope="session")
def chapter_page(built_site: Path) -> str:
    return (built_site / CHAPTER_PAGE).read_text(encoding="utf-8")


@pytest.fixture
def site_copy(built_site: Path, tmp_path: Path) -> Path:
    """Return a copy of the built site that a test may change."""
    copy = tmp_path / "site"
    shutil.copytree(built_site, copy)
    return copy


def problems_of(page: str) -> list[Problem]:
    return page_problems(page, ADDRESSES, page_base(CHAPTER_PAGE, ADDRESSES))


def with_content(page: str, content: str) -> str:
    """Put content in the article of a real built page in place of what it holds."""
    found = _ARTICLE.search(page)
    assert found is not None
    return page[: found.start(2)] + content + page[found.end(2) :]


def changed(page: str, old: str, new: str) -> str:
    assert old in page
    return page.replace(old, new, 1)


def named(problems: list[Problem], *words: str) -> bool:
    return any(all(word in str(problem) for word in words) for problem in problems)


def test_a_built_page_of_the_fixture_copy_has_no_problem(built_site: Path) -> None:
    assert site_problems(built_site, ADDRESSES) == []


EARLY_CLOSE = [
    ('<p>x</p></article><div onclick="alert(1)">y</div><style>', "style element"),
    ('<p>x</p></article><div onclick="alert(1)">y</div><script>', "6 script elements"),
]


@pytest.mark.parametrize(("content", "word"), EARLY_CLOSE)
def test_an_early_close_of_the_article_then_an_open_raw_text_element_is_a_problem(
    content: str, word: str, chapter_page: str
) -> None:
    problems = problems_of(with_content(chapter_page, content))

    assert named(problems, "closing <article>")
    assert named(problems, "onclick")
    assert named(problems, word)


def test_the_parser_reads_script_and_style_as_raw_text_to_their_end_tag() -> None:
    # The structure rules guard against this: what the parser reads as the text of a script
    # or a style, up to the end of the input, is never checked as markup.
    class Events(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[tuple[str, str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.events.append(("start", tag))

        def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.events.append(("empty", tag))

        def handle_data(self, data: str) -> None:
            # A parser may hand raw text over in several pieces, which are one text here.
            if self.events and self.events[-1][0] == "data":
                self.events[-1] = ("data", self.events[-1][1] + data)
            else:
                self.events.append(("data", data))

    for tag in ("script", "style"):
        parser = Events()
        parser.feed(f'<{tag}><p onclick="x"></article>')
        parser.close()
        assert parser.events == [("start", tag), ("data", '<p onclick="x"></article>')]

    parser = Events()
    parser.feed("<script/>alert(1)</script>")
    parser.close()
    assert parser.events[:2] == [("empty", "script"), ("data", "alert(1)")]


def test_a_page_with_two_articles_or_none_is_a_problem(chapter_page: str) -> None:
    two = with_content(chapter_page, "<p>x</p></article><article><p>y</p>")
    none = chapter_page.replace("<article", "<div", 1).replace("</article>", "</div>", 1)

    assert named(problems_of(two), "2 opening and 2 closing <article>")
    assert named(problems_of(none), "0 opening and 0 closing <article>")


EARLY_TITLE = [
    '</title><link rel="icon" href="../favicon.png">',
    "</title><form>",
    "</title><div>",
    "</title><script/>alert(1)</script>",
]


@pytest.mark.parametrize("injected", EARLY_TITLE)
def test_markup_after_an_early_close_of_the_title_is_a_problem(
    injected: str, chapter_page: str
) -> None:
    page = changed(chapter_page, "</title>", f"{injected}</title>")

    assert named(problems_of(page), "closing <title>")


def test_a_self_closed_script_in_the_head_is_a_problem(chapter_page: str) -> None:
    # The parser reads <script/> as empty and closed, and a browser opens a script there.
    page = changed(chapter_page, "</head>", "<script/>alert(1)</script></head>")

    problems = problems_of(page)

    assert named(problems, "self-closing tag <script/>")
    assert named(problems, "6 script elements")


@pytest.mark.parametrize("element", ["<title>y</title>", "<body>"])
def test_a_second_title_or_body_is_a_problem(element: str, chapter_page: str) -> None:
    page = changed(chapter_page, "</head>", f"{element}</head>")

    assert named(problems_of(page), "2 opening")


HEAD_ADDITIONS = [
    ("<script>alert(1)</script>", "script elements"),
    ('<meta http-equiv="refresh" content="0;url=https://example.invalid">', "meta"),
    ('<base href="https://example.invalid/">', "<base>"),
    ('<link rel="stylesheet" href="https://example.invalid/a.css">', "link"),
    ('<link rel="stylesheet" href="//example.invalid/a.css">', "link"),
    ('<meta name="description" content="x" onload="alert(1)">', "meta"),
]


@pytest.mark.parametrize(("element", "word"), HEAD_ADDITIONS)
def test_an_element_the_theme_does_not_write_in_the_head_is_a_problem(
    element: str, word: str, chapter_page: str
) -> None:
    page = changed(chapter_page, "</head>", f"{element}</head>")

    assert named(problems_of(page), word)


def test_a_repeated_attribute_is_a_problem(chapter_page: str) -> None:
    page = with_content(chapter_page, '<p><a href="#a" href="javascript:alert(1)">x</a></p>')

    assert named(problems_of(page), "the attribute href 2 times")


COMMENTS = [
    ("<p>a</p><!-- note --><p>b</p>", "comment"),
    ("<p>a<!-->b</p>", "comment"),
    ("<![CDATA[><script>alert(1)</script>]]>", "CDATA"),
    ("<?php x ?>", "processing instruction"),
]


@pytest.mark.parametrize(("content", "word"), COMMENTS)
def test_a_comment_cdata_or_instruction_in_the_content_is_a_problem(
    content: str, word: str, chapter_page: str
) -> None:
    assert named(problems_of(with_content(chapter_page, content)), word)


def test_a_comment_that_differs_from_the_theme_icon_comment_is_a_problem(
    chapter_page: str,
) -> None:
    page = changed(chapter_page, "Fonticons, Inc.-->", "Fonticons, Inc!-->")

    assert named(problems_of(page), "comment other than the theme's icon comment")


def test_the_theme_icon_comment_inside_the_article_is_a_problem(chapter_page: str) -> None:
    comment = re.search(r"<!--! Font Awesome.*?-->", chapter_page)
    assert comment is not None
    page = with_content(chapter_page.replace(comment[0], "", 1), f"<p>{comment[0]}</p>")

    assert named(problems_of(page), "icon comment inside the article")


FENCES = [
    ("```{.text #__config .mermaid}\nx\n```", "__config"),
    ("```{.text .mermaid}\nx\n```", "mermaid"),
    ('```{.text title="a.txt"}\nx\n```', "filename"),
]


@pytest.mark.parametrize(("fence", "word"), FENCES)
def test_what_a_fence_option_writes_is_a_problem(fence: str, word: str, chapter_page: str) -> None:
    rendered = render(fence)
    assert word in rendered

    assert named(problems_of(with_content(chapter_page, rendered)), word)


def test_a_second_config_id_is_a_problem_even_on_a_heading(chapter_page: str) -> None:
    page = with_content(chapter_page, '<h2 id="__config">x</h2>')

    problems = problems_of(page)

    assert named(problems, "id", "__config")
    assert named(problems, "the id '__config' 2 times")


def test_what_markdown_writes_for_a_page_passes(chapter_page: str) -> None:
    plain = (
        '<h1 id="a">A</h1><p>Text &lt;b&gt; &amp; <em>more</em> <strong>x</strong></p>'
        '<div class="highlight"><pre><span></span><code><span class="k">x</span> &lt;y&gt;\n'
        "</code></pre></div>"
        "<blockquote><p>q</p></blockquote><ul><li>a</li></ul><ol><li>b</li></ol><hr />"
        '<table><thead><tr><th style="text-align: left;">h</th></tr></thead><tbody><tr>'
        '<td style="text-align: right;">c</td></tr></tbody></table>'
        '<p><a href="https://example.invalid/a">a</a> '
        '<a href="../b/#c" title="cite:fixture-mirrored-book/folding-the-hull@v1.0.0">b</a> '
        '<a class="headerlink" href="#a" title="Permanent link">&para;</a> '
        '<a href="mailto:a@example.invalid">m</a><br />x</p>'
        '<div class="library-card library-card--eligible"><h3 id="b">B</h3></div>'
        '<div class="admonition note"><p class="admonition-title">N</p></div>'
        + render("```python\nx = 1\n```")
    )

    assert problems_of(with_content(chapter_page, plain)) == []


LIVE = [
    ("<img src=x onerror=alert(1)>", "img"),
    ("<script>alert(1)</script>", "script"),
    ("<svg/onload=alert(1)>", "svg"),
    ("<iframe src=https://example.invalid></iframe>", "iframe"),
    ('<p onclick="alert(1)">x</p>', "onclick"),
    ("<p/onclick=alert(1)>x</p>", "onclick"),
    ('<a href="javascript:alert(1)">x</a>', "javascript"),
    ('<a href=" JaVaScRiPt:alert(1)">x</a>', "javascript"),
    ('<a href="java&#9;script:alert(1)">x</a>', "javascript"),
    ('<a href="java\nscript:alert(1)">x</a>', "javascript"),
    ('<a href="data:text/html,x">x</a>', "data"),
    ('<a href="//example.invalid/x">x</a>', "another host"),
    ('<a href="\\\\example.invalid/x">x</a>', "another host"),
    ('<a href="/\\example.invalid/x">x</a>', "another host"),
    ('<p style="background:url(https://example.invalid)">x</p>', "style"),
    ('<td style="text-align: left; position: fixed">x</td>', "style"),
    ('<form action="https://example.invalid"><input name=a></form>', "form"),
    ("<p>a < b</p>", "<"),
    ('<p id="x">x</p>', "id"),
    ('<h2 id="__drawer">x</h2>', "__drawer"),
    ('<h2 id="__x">x</h2>', "__x"),
    ('<div class="md-sidebar">x</div>', "md-sidebar"),
    ('<span class="k">x</span>', "class"),
    ('<p title="Permanent link">x</p>', "title"),
    ('<a href="#a" title="x">x</a>', "title"),
    ("<p>x<br/>y</p><p/>z", "self-closing"),
]


@pytest.mark.parametrize(("content", "word"), LIVE)
def test_anything_else_in_the_content_of_a_page_is_a_problem(
    content: str, word: str, chapter_page: str
) -> None:
    assert named(problems_of(with_content(chapter_page, content)), word)


CHROME = [
    (
        'href="https://example.invalid/fixture-owner/fixture-library"',
        'href="https://example.invalid/other"',
        "href",
    ),
    (
        '<form class="md-search__form"',
        '<form action="https://example.invalid" class="md-x"',
        "action",
    ),
    ('type="text"', 'type="hidden"', "type"),
    (
        '<header class="md-header"',
        '<header onmouseover="alert(1)" class="md-header"',
        "onmouseover",
    ),
    ('<header class="md-header"', '<header class="md-header" style="x"', "style"),
    ('<header class="md-header"', '<header class="md-header" id="x"', "id"),
    ('<header class="md-header"', '<marquee></marquee><header class="md-header"', "marquee"),
]


@pytest.mark.parametrize(("old", "new", "word"), CHROME)
def test_a_change_to_the_theme_markup_is_a_problem(
    old: str, new: str, word: str, chapter_page: str
) -> None:
    assert named(problems_of(changed(chapter_page, old, new)), word)


def test_the_pinned_scripts_pass_at_their_base_and_not_with_another_host(
    built_site: Path,
) -> None:
    page = (built_site / TOPIC_PAGE).read_text(encoding="utf-8")
    base = page_base(TOPIC_PAGE, ADDRESSES)
    other = changed(page, 'new URL("../..",location)', 'new URL("https://example.org/",location)')

    assert base == "../.."
    assert page_problems(page, ADDRESSES, base) == []
    assert named(page_problems(other, ADDRESSES, base), "theme script")
    assert page_base("404.html", ADDRESSES) == "/fixture-library/"
    assert page_base("index.html", ADDRESSES) == "."


def test_every_page_and_file_of_a_built_site_is_read(site_copy: Path) -> None:
    page = (site_copy / CHAPTER_PAGE).read_text(encoding="utf-8")
    (site_copy / CHAPTER_PAGE).write_text(with_content(page, "<img src=x>"), encoding="utf-8")
    (site_copy / "books" / "notes.txt").write_text("<img src=x>", encoding="utf-8")

    problems = site_problems(site_copy, ADDRESSES)

    assert [problem.path for problem in problems] == [CHAPTER_PAGE]
    assert named(problems, "img")


@pytest.mark.parametrize(
    "name", ["books/x.svg", "books/x.htm", "books/x.xhtml", "books/x.js", "x.png", "x.xml"]
)
def test_a_file_of_another_kind_is_a_problem(name: str, site_copy: Path) -> None:
    (site_copy / name).write_text("<svg onload=alert(1)>", encoding="utf-8")

    problems = site_problems(site_copy, ADDRESSES)

    assert [(problem.kind, problem.path) for problem in problems] == [("served file", name)]


def test_a_canonical_file_that_ends_in_html_gets_the_page_check(site_copy: Path) -> None:
    (site_copy / "books" / "notes.HTML").write_text("<p>x</p>", encoding="utf-8")

    problems = site_problems(site_copy, ADDRESSES)

    assert {problem.path for problem in problems} == {"books/notes.HTML"}
    assert named(problems, "closing <article>")


SEARCH_ENTRIES = [
    {"location": "a/", "title": "A", "text": "<p>x<img src=x onerror=alert(1)></p>"},
    {"location": "a/", "title": "<b onclick=alert(1)>A</b>", "text": "<p>x</p>"},
    {"location": "javascript:alert(1)", "title": "A", "text": "<p>x</p>"},
    {"location": "a/", "title": "A", "text": "<p>x</p><!-- y -->"},
    {"location": "a/", "title": "A", "text": "<p>x</p>", "tags": ["y"]},
]


@pytest.mark.parametrize("entry", SEARCH_ENTRIES)
def test_a_search_index_entry_off_the_content_rules_is_a_problem(
    entry: dict[str, object], site_copy: Path
) -> None:
    path = site_copy / "search" / "search_index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    index["docs"].append(entry)
    path.write_text(json.dumps(index), encoding="utf-8")

    problems = site_problems(site_copy, ADDRESSES)

    assert problems
    assert {problem.kind for problem in problems} == {"search index"}


def test_another_installed_theme_version_is_one_problem(
    built_site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kb.site_check._installed_theme_version", lambda: "9.9.0")

    problems = site_problems(built_site, ADDRESSES)

    assert [problem.kind for problem in problems] == ["theme version"]
    assert "9.9.0" in str(problems[0])
