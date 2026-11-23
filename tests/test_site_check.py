"""The check of the built pages: only what Markdown itself writes may reach a reader."""

from pathlib import Path

import pytest
from kb.site_check import page_problems, site_problems


def page(content: str) -> str:
    return (
        "<!doctype html><html><head><script>theme()</script></head><body>"
        f'<nav><svg onload="theme()"></svg></nav><article class="md-content__inner">{content}'
        "</article><script>theme()</script></body></html>"
    )


PLAIN = (
    '<h1 id="a">A</h1><p class="lead">Text &lt;b&gt; &amp; <em>more</em> <strong>x</strong></p>'
    '<div class="highlight"><pre><span></span><code><span class="k">x</span> &lt;y&gt;\n</code>'
    "</pre></div><blockquote><p>q</p></blockquote><ul><li>a</li></ul><ol><li>b</li></ol><hr />"
    '<table><thead><tr><th style="text-align: left;">h</th></tr></thead><tbody><tr>'
    '<td style="text-align: right;">c</td></tr></tbody></table>'
    '<p><a href="https://example.invalid/a">a</a> <a href="../b/#c" title="t">b</a> '
    '<a class="headerlink" href="#a" title="Permanent link">&para;</a> '
    '<a href="mailto:a@example.invalid">m</a><br />x</p>'
)


def test_what_markdown_writes_for_a_page_passes() -> None:
    assert page_problems(page(PLAIN)) == []


LIVE = [
    ("<img src=x onerror=alert(1)>", "img"),
    ("<script>alert(1)</script>", "script"),
    ("<svg/onload=alert(1)>", "svg"),
    ("<iframe src=https://example.invalid></iframe>", "iframe"),
    ('<p onclick="alert(1)">x</p>', "onclick"),
    ("<p/onclick=alert(1)>x</p>", "onclick"),
    ('<a href="javascript:alert(1)">x</a>', "javascript"),
    ('<a href=" JaVaScRiPt:alert(1)">x</a>', "javascript"),
    ('<a href="java&#9;script:alert(1)">x</a>', "href"),
    ('<a href="data:text/html,x">x</a>', "data"),
    ('<p style="background:url(https://example.invalid)">x</p>', "style"),
    ('<td style="text-align: left; position: fixed">x</td>', "style"),
    ('<form action="https://example.invalid"><input name=a></form>', "form"),
    ("<p>a</p><!-- note --><p>b</p>", "comment"),
    ("<![CDATA[><script>alert(1)</script>]]>", "declaration"),
    ("<?php x ?>", "instruction"),
    ("<p>a < b</p>", "<"),
    ("<p>x</p></article><script>alert(1)</script><article>", "article"),
    ("<article><p>x</p></article>", "article"),
]


@pytest.mark.parametrize(("content", "named"), LIVE)
def test_anything_else_in_the_content_of_a_page_is_a_problem(content: str, named: str) -> None:
    problems = page_problems(page(content))

    assert problems
    assert any(named in problem for problem in problems)


def test_a_page_with_no_content_area_is_a_problem() -> None:
    assert page_problems("<html><body><p>x</p></body></html>")


def test_every_page_of_a_built_site_is_read(tmp_path: Path) -> None:
    (tmp_path / "books").mkdir()
    (tmp_path / "index.html").write_text(page(PLAIN), encoding="utf-8")
    (tmp_path / "books" / "index.html").write_text(page("<img src=x>"), encoding="utf-8")
    (tmp_path / "books" / "notes.txt").write_text("<img src=x>", encoding="utf-8")

    problems = site_problems(tmp_path)

    assert len(problems) == 1
    assert problems[0].startswith("books/index.html: ")
    assert "img" in problems[0]
