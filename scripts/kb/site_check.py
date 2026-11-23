"""The last check of the site: what a built page holds in its content area.

A page of the site shows text that other people wrote. The staging step writes that text so
the renderer shows it and does not run it, and that step has to guess what the renderer will
take for code. This module does not guess. It reads the HTML that MkDocs wrote and refuses
everything Markdown itself does not write for a page: an element outside a short list, an
attribute outside a shorter one, a link that is not a web address, a comment, or a stray angle
bracket. A page with any of those is not published, whatever route it took to get there.

Only the content area is read, which is the one ``article`` element the theme writes on every
page. The theme's own scripts and icons around it are the theme's.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

__all__ = ["page_problems", "site_problems"]

# The element the theme wraps the content of a page in.
_CONTENT_ELEMENT = "article"

# Every element the site's Markdown extensions write for a page of this library. An image is
# left out on purpose, because no page holds one and an image fetched from another host tells
# that host who reads the page.
_ELEMENTS = frozenset(
    {
        "a",
        "blockquote",
        "br",
        "code",
        "del",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_ATTRIBUTES = frozenset({"class", "id", "title"})
# The one style the renderer writes, for the alignment of a table column.
_CELL_STYLE = re.compile(r"text-align: (?:left|right|center);?")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*(?=:)")
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
_NOT_SHOWN = re.compile(r"[\x00-\x20\x7f]")


class _Content(HTMLParser):
    """Collect what the content area of one page holds that Markdown does not write."""

    def __init__(self) -> None:
        # Character references stay apart from text, so an angle bracket that reaches
        # ``handle_data`` is one the page holds raw.
        super().__init__(convert_charrefs=False)
        self.problems: list[str] = []
        self.opened = 0
        self.closed = 0

    @property
    def _inside(self) -> bool:
        return self.opened > self.closed

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == _CONTENT_ELEMENT:
            self.opened += 1
            return
        if not self._inside:
            return
        if tag not in _ELEMENTS:
            self.problems.append(f"the element <{tag}>")
            return
        for name, value in attrs:
            problem = _attribute_problem(tag, name, value or "")
            if problem:
                self.problems.append(problem)

    def handle_endtag(self, tag: str) -> None:
        if tag == _CONTENT_ELEMENT:
            self.closed += 1

    def handle_data(self, data: str) -> None:
        if self._inside and "<" in data:
            self.problems.append(f"a raw < in the text {_excerpt(data)}")

    def handle_comment(self, data: str) -> None:
        if self._inside:
            self.problems.append(f"the comment {_excerpt(data)}")

    def handle_decl(self, decl: str) -> None:
        if self._inside:
            self.problems.append(f"the declaration {_excerpt(decl)}")

    def unknown_decl(self, data: str) -> None:
        if self._inside:
            self.problems.append(f"the declaration {_excerpt(data)}")

    def handle_pi(self, data: str) -> None:
        if self._inside:
            self.problems.append(f"the processing instruction {_excerpt(data)}")


def _excerpt(text: str) -> str:
    shown = " ".join(text.split())
    return repr(shown if len(shown) <= 60 else f"{shown[:60]}...")


def _attribute_problem(tag: str, name: str, value: str) -> str | None:
    """Say what is wrong with one attribute of an allowed element, or ``None``."""
    if name in _ATTRIBUTES:
        return None
    if name == "href" and tag == "a":
        # A browser drops a tab or a line break inside a scheme, so ``java<tab>script:``
        # runs. The scheme is read with every such character taken out.
        scheme = _SCHEME.match(_NOT_SHOWN.sub("", value))
        if scheme and scheme[0].lower() not in _LINK_SCHEMES:
            return f"the href {_excerpt(value)}, whose scheme is {scheme[0].lower()}"
        return None
    if name == "style" and tag in {"td", "th"} and _CELL_STYLE.fullmatch(value):
        return None
    return f"the attribute {name} on <{tag}>, with the value {_excerpt(value)}"


def page_problems(html: str) -> list[str]:
    """List what the content area of one built page holds that Markdown does not write.

    Args:
        html: The whole HTML of the page, as MkDocs wrote it.

    Returns:
        One line per problem, in the order found. The list is empty for a page that holds
        only the elements and attributes the site's Markdown writes, links to web addresses,
        and text. A page that does not have exactly one content area is a problem too,
        because text that closed the area early would put what follows out of this check.
    """
    parser = _Content()
    parser.feed(html)
    parser.close()
    problems = list(parser.problems)
    if parser.opened != 1 or parser.closed != 1:
        problems.append(
            f"{parser.opened} opening and {parser.closed} closing <{_CONTENT_ELEMENT}> tags, "
            "where a page has one of each around its content"
        )
    return problems


def site_problems(site_dir: Path) -> list[str]:
    """List the problems of every HTML page of a built site.

    Args:
        site_dir: The directory MkDocs wrote the site into.

    Returns:
        One line per problem, each starting with the page's path from ``site_dir``. Pages are
        read in the order of their paths.
    """
    problems: list[str] = []
    for page in sorted(site_dir.rglob("*.html")):
        name = page.relative_to(site_dir).as_posix()
        text = page.read_text(encoding="utf-8")
        problems.extend(f"{name}: {problem}" for problem in page_problems(text))
    return problems
