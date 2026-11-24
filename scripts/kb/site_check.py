"""The last check of the site: every file it serves, read whole against what the library writes.

A page of the site shows text that other people wrote, inside markup that the library's
Markdown and the pinned theme write around it. This module does not guess how that text could
turn into markup. It reads every file MkDocs wrote and every file copied in beside it, and it
refuses anything that is not on a list of what the library and the theme write. A site with
one problem is not published.

A page is read in three zones, each with its own list:

- The head holds only the meta, link, title, style, and script elements the theme writes, in
  their exact shapes, and only the inline script and style texts pinned here.
- The body outside the one ``article`` element is the theme's own markup: its elements, their
  attributes, its ids, and its addresses.
- The article is the content. It holds only what the library's Markdown writes for a page: a
  short list of elements, an id only on a heading, a class only from a short list, and a link
  only to a web or mail address or within the site.

Some rules do not trust the parser at all, because a browser and ``html.parser`` disagree about
where a script, a style, or a comment ends. Those rules count openings in the raw text: one
``html``, ``head``, ``title``, ``body``, and ``article`` each, only the pinned scripts, style,
and icon comment, and no CDATA section or processing instruction.

The search index is read too, because the theme inserts the title and text of each entry into
the page as markup and makes each location a link. Every other file must be of a kind that the
library or the theme serves.

The theme's markup was read from Material for MkDocs ``THEME_VERSION``. Another installed
version is reported as a problem of its own, because its markup must be read again.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from kb.catalog import MirrorStatus

__all__ = [
    "KINDS",
    "THEME_VERSION",
    "Problem",
    "SiteAddresses",
    "content_problems",
    "page_base",
    "page_problems",
    "search_index_problems",
    "site_problems",
]

THEME = "mkdocs-material"
"""The distribution of the theme whose markup the lists below hold."""

THEME_VERSION = "9.8.2"
"""The version of the theme the lists below were read from."""

KINDS = (
    "theme version",
    "page structure",
    "head",
    "theme markup",
    "content",
    "search index",
    "served file",
)
"""The kinds of problem, in the order a report lists them."""


@dataclass(frozen=True)
class Problem:
    """One thing a built file holds that the check does not allow.

    Attributes:
        kind: One of ``KINDS``.
        path: The file's path from the site directory, or empty for the site as a whole.
        detail: What the file holds, for a person to read.
    """

    kind: str
    path: str
    detail: str

    def __str__(self) -> str:
        """Return the problem as one line that starts with the file's path."""
        return f"{self.path}: {self.detail}" if self.path else self.detail


@dataclass(frozen=True)
class SiteAddresses:
    """The two addresses of a site that its theme markup links to.

    Attributes:
        base_url: The site's own address, ``library.base_url`` in ``catalog.yaml``.
        repository: The repository address, ``library.repository`` in ``catalog.yaml``.
    """

    base_url: str
    repository: str

    @property
    def root(self) -> str:
        """The site's address, with a final slash, so that no other host can start with it."""
        return self.base_url if self.base_url.endswith("/") else f"{self.base_url}/"

    @property
    def base_path(self) -> str:
        """The path of the site's address, with a final slash."""
        path = urlsplit(self.base_url).path or "/"
        return path if path.endswith("/") else f"{path}/"


# The page the theme writes for an address that is not found. It names the site's files by
# their absolute path, because it is served at any depth.
_NOT_FOUND_PAGE = "404.html"
_INDEX_PAGE = "index.html"

# Placeholders in the pinned texts. A page's base path takes the place of the first, and the
# prefix of an address in the site, which is empty at the root, takes the place of the second.
_BASE = "@BASE@"
_PREFIX = "@PREFIX@"

_HEAD_SCRIPT = (
    f'__md_scope=new URL("{_BASE}",location),'
    "__md_hash=e=>[...e].reduce(((e,_)=>(e<<5)-e+_.charCodeAt(0)),0),"
    '__md_get=(e,_=localStorage,t=__md_scope)=>JSON.parse(_.getItem(t.pathname+"."+e)),'
    "__md_set=(e,_,t=localStorage,a=__md_scope)=>"
    '{try{t.setItem(a.pathname+"."+e,JSON.stringify(_))}catch(e){}}'
)
_PALETTE_SCRIPT = (
    'var palette=__md_get("__palette");if(palette&&palette.color){'
    'if("(prefers-color-scheme)"===palette.color.media){'
    'var media=matchMedia("(prefers-color-scheme: light)"),'
    "input=document.querySelector(media.matches?"
    "\"[data-md-color-media='(prefers-color-scheme: light)']\":"
    "\"[data-md-color-media='(prefers-color-scheme: dark)']\");"
    'palette.color.media=input.getAttribute("data-md-color-media"),'
    'palette.color.scheme=input.getAttribute("data-md-color-scheme"),'
    'palette.color.primary=input.getAttribute("data-md-color-primary"),'
    'palette.color.accent=input.getAttribute("data-md-color-accent")}'
    "for(var[key,value]of Object.entries(palette.color))"
    'document.body.setAttribute("data-md-color-"+key,value)}'
)
_TARGET_SCRIPT = (
    "var target=document.getElementById(location.hash.slice(1));"
    'target&&target.name&&(target.checked=target.name.startsWith("__tabbed_"))'
)
_CONFIG_SCRIPT = (
    f'{{"annotate": null, "base": "{_BASE}", "features": ["navigation.tabs", '
    '"navigation.indexes", "navigation.footer", "content.code.copy"], '
    f'"search": "{_PREFIX}assets/javascripts/workers/search.a7633da7.min.js", "tags": null, '
    '"translations": {"clipboard.copied": "Copied to clipboard", '
    '"clipboard.copy": "Copy to clipboard", '
    '"search.result.more.one": "1 more on this page", '
    '"search.result.more.other": "# more on this page", '
    '"search.result.none": "No matching documents", '
    '"search.result.one": "1 matching document", '
    '"search.result.other": "# matching documents", '
    '"search.result.placeholder": "Type to start searching", '
    '"search.result.term.missing": "Missing", "select.version": "Select version"}, '
    '"version": null}'
)
# Every script element of a page, written out whole. Each is on every page exactly once.
_SCRIPTS = (
    f"<script>{_HEAD_SCRIPT}</script>",
    f"<script>{_PALETTE_SCRIPT}</script>",
    f"<script>{_TARGET_SCRIPT}</script>",
    f'<script id="__config" type="application/json">{_CONFIG_SCRIPT}</script>',
    f'<script src="{_PREFIX}assets/javascripts/bundle.a5f9d56c.min.js"></script>',
)
_STYLE = '<style>:root{--md-text-font:"Roboto";--md-code-font:"Roboto Mono"}</style>'
# The one comment the theme writes, inside the icon of the repository link.
_ICON_COMMENT = (
    "<!--! Font Awesome Free 7.1.0 by @fontawesome - https://fontawesome.com License - "
    "https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, "
    "Code: MIT License) Copyright 2025 Fonticons, Inc.-->"
)
_DOCTYPE = "<!doctype html>"

# The elements a page has exactly one of.
_ONCE = ("html", "head", "title", "body", "article")
_CONTENT_ELEMENT = "article"
# The elements HTML never opens, which are allowed or refused by the lists below.
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)

_HEAD_ELEMENTS = frozenset({"link", "meta", "script", "style", "title"})
_META_SHAPES = (
    (("charset", re.compile(r"utf-8")),),
    (
        ("name", re.compile(r"viewport")),
        ("content", re.compile(r"width=device-width,initial-scale=1")),
    ),
    (("name", re.compile(r"description")), ("content", re.compile(r".*", re.DOTALL))),
    (
        ("name", re.compile(r"generator")),
        ("content", re.compile(rf"mkdocs-\d+\.\d+\.\d+, {THEME}-{re.escape(THEME_VERSION)}")),
    ),
)
_FONT_STYLESHEET = "https://fonts.googleapis.com/css?"
_FONT_HOST = "https://fonts.gstatic.com"
_GENERATOR_ADDRESS = "https://squidfunk.github.io/mkdocs-material/"

# What the theme writes outside the article, read from a build of THEME_VERSION.
_CHROME_ATTRIBUTES: dict[str, frozenset[str]] = {
    "html": frozenset({"class", "lang"}),
    "head": frozenset(),
    "body": frozenset(
        {"dir", "data-md-color-scheme", "data-md-color-primary", "data-md-color-accent"}
    ),
    "header": frozenset({"class", "data-md-component"}),
    "nav": frozenset(
        {
            "class",
            "aria-label",
            "aria-labelledby",
            "aria-expanded",
            "data-md-component",
            "data-md-level",
        }
    ),
    "main": frozenset({"class", "data-md-component"}),
    "footer": frozenset({"class"}),
    "article": frozenset({"class"}),
    "div": frozenset(
        {"class", "data-md-component", "data-md-type", "data-md-scrollfix", "role", "tabindex"}
    ),
    "span": frozenset({"class"}),
    "ul": frozenset({"class", "data-md-component", "data-md-scrollfix"}),
    "ol": frozenset({"class", "role"}),
    "li": frozenset({"class"}),
    "a": frozenset({"href", "class", "title", "aria-label", "data-md-component", "target", "rel"}),
    "label": frozenset({"class", "for", "id", "title", "tabindex", "hidden"}),
    "input": frozenset(
        {
            "class",
            "type",
            "id",
            "name",
            "checked",
            "autocomplete",
            "aria-label",
            "placeholder",
            "autocapitalize",
            "autocorrect",
            "spellcheck",
            "required",
            "data-md-toggle",
            "data-md-component",
            "data-md-color-media",
            "data-md-color-scheme",
            "data-md-color-primary",
            "data-md-color-accent",
        }
    ),
    "form": frozenset({"class", "name", "data-md-component"}),
    "button": frozenset({"class", "type", "title", "aria-label", "tabindex"}),
    "svg": frozenset({"xmlns", "viewbox"}),
    "path": frozenset({"d"}),
    "script": frozenset({"id", "type", "src"}),
}
_CHROME_COMPONENTS = frozenset(
    {
        "announce",
        "container",
        "content",
        "dialog",
        "header",
        "header-title",
        "header-topic",
        "logo",
        "main",
        "palette",
        "search",
        "search-query",
        "search-result",
        "sidebar",
        "skip",
        "source",
        "tabs",
        "toc",
    }
)
_CHROME_CLASS = re.compile(r"md-[a-z0-9_-]+|no-js")
_CHROME_INPUT_TYPES = frozenset({"checkbox", "radio", "text"})
_THEME_ID = re.compile(r"__(?:config|drawer|search|toc|palette_\d+|nav_\d+(?:_\d+)*(?:_label)?)")
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_PATH_DATA = re.compile(r"[MmLlHhVvCcSsQqTtAaZz0-9 .,eE+-]*")

# Every element the site's Markdown extensions write for a page of this library. An image is
# left out, because no page holds one and an image fetched from another host tells that host
# who reads the page.
_CONTENT_ELEMENTS = frozenset(
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
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
# The classes the library writes, by element, as whole sets. The highlighter's token classes
# on a span inside preformatted text are read by ``_TOKEN_CLASS``.
_CONTENT_CLASSES: dict[str, frozenset[frozenset[str]]] = {
    "a": frozenset({frozenset({"headerlink"})}),
    "div": frozenset(
        {
            frozenset({"highlight"}),
            frozenset({"admonition", "note"}),
            frozenset({"admonition", "warning"}),
            frozenset({"library-facts"}),
            *(
                frozenset({box, f"{box}--{status.value}"})
                for box in ("library-card", "library-status")
                for status in MirrorStatus
            ),
        }
    ),
    "p": frozenset({frozenset({"admonition-title"})}),
}
_TOKEN_CLASS = re.compile(r"[a-z][a-z0-9]{0,2}")
_PERMALINK_TITLE = "Permanent link"
_CITATION_TITLE = re.compile(r"cite:[a-z0-9-]+(?:/[a-z0-9-]+)?(?:@[A-Za-z0-9._-]+)?")
# The one style the renderer writes, for the alignment of a table column.
_CELL_STYLE = re.compile(r"text-align: (?:left|right|center);?")

_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*(?=:)")
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
# A browser drops these from an address before it reads the scheme, so ``java<tab>script:``
# runs. Every address is read with them taken out.
_NOT_SHOWN = re.compile(r"[\x00-\x20\x7f]")
# An address that starts like this goes to another host whatever its scheme.
_OTHER_HOST = re.compile(r"[/\\]{2}|\\")

_SEARCH_INDEX = "search/search_index.json"
_SEARCH_ENTRY_KEYS = frozenset({"location", "text", "title"})
_SERVED_ANYWHERE = frozenset({".epub", ".json", ".jsonl", ".md", ".pdf", ".txt", ".yaml", ".zip"})
_SERVED_IN = {
    ".css": ("assets/stylesheets/", "stylesheets/"),
    ".js": ("assets/javascripts/",),
    ".map": ("assets/javascripts/", "assets/stylesheets/"),
    ".png": ("assets/images/",),
}
_SERVED_BY_NAME = frozenset({"sitemap.xml", "sitemap.xml.gz"})
_LICENSE_FILE = "LICENSE"


def _excerpt(text: str) -> str:
    shown = " ".join(text.split())
    return repr(shown if len(shown) <= 60 else f"{shown[:60]}...")


def _opening(tag: str) -> re.Pattern[str]:
    # A boundary after the name, so that ``<head`` does not count ``<header``.
    return re.compile(rf"<{tag}(?=[\s/>])", re.IGNORECASE)


def _closing(tag: str) -> re.Pattern[str]:
    return re.compile(rf"</{tag}(?=[\s/>])", re.IGNORECASE)


def _cleaned(address: str) -> str:
    return _NOT_SHOWN.sub("", address)


def _scheme(address: str) -> str | None:
    found = _SCHEME.match(_cleaned(address))
    return found[0].lower() if found else None


def _stays_on_host(address: str) -> bool:
    """Say whether an address has no scheme and does not lead to another host."""
    return _scheme(address) is None and not _OTHER_HOST.match(_cleaned(address))


def page_base(path: str, addresses: SiteAddresses) -> str:
    """Give the base path the theme writes into a page at a path of the site.

    Args:
        path: The page's path from the site directory, such as ``topics/index.html``.
        addresses: The site's addresses.

    Returns:
        ``.`` for a page at the root, a run of ``..`` segments for a page below it, and the
        path of the site's address for the not-found page.
    """
    if path == _NOT_FOUND_PAGE:
        return addresses.base_path
    depth = len(PurePosixPath(path).parts) - 1
    return "/".join([".."] * depth) if depth else "."


def _prefix(base: str) -> str:
    if base == ".":
        return ""
    return base if base.endswith("/") else f"{base}/"


def _pinned(text: str, base: str) -> str:
    return text.replace(_BASE, base).replace(_PREFIX, _prefix(base))


class _Reader(HTMLParser):
    """Read one page, or one fragment of content, and collect what is not on the lists."""

    def __init__(self, addresses: SiteAddresses | None) -> None:
        """Start a reader of a whole page, or of a fragment of content without ``addresses``."""
        # Character references stay apart from text, so an angle bracket that reaches
        # ``handle_data`` is one the page holds raw. Attribute values are decoded either way.
        super().__init__(convert_charrefs=False)
        self.addresses = addresses
        self.problems: list[tuple[str, str]] = []
        # The elements open at this point, as the markup itself nests them. A fragment of
        # content is read as if it were inside the article.
        self.stack: list[str] = [_CONTENT_ELEMENT] if addresses is None else []
        # No end tag in a fragment closes the article it is read inside.
        self.floor = len(self.stack)
        self.ids: Counter[str] = Counter()

    def _zone(self) -> str:
        if _CONTENT_ELEMENT in self.stack:
            return "content"
        if "head" in self.stack:
            return "head"
        return "theme markup"

    def _add(self, zone: str, detail: str) -> None:
        self.problems.append((zone, detail))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, closed=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, closed=True)

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool) -> None:
        zone = self._zone()
        parent = self.stack[-1] if self.stack else None
        values = {name: value or "" for name, value in attrs}
        names = [name for name, _ in attrs]
        for name, count in Counter(names).items():
            if count > 1:
                # A browser keeps the first value and a parser may keep the last.
                self._add(zone, f"the attribute {name} {count} times on one <{tag}>")
        if "id" in values:
            self.ids[values["id"]] += 1
        if "title" in self.stack:
            self._add("head", f"the element <{tag}> inside <title>")
        if tag in _VOID:
            pass
        elif closed:
            # A browser ignores the slash and opens the element, so the text after it is the
            # element's content, while a parser reads the element as empty and closed. Only
            # the theme's icons close an element this way, inside their own ``svg``.
            if not (tag == "path" and parent == "svg" and zone == "theme markup"):
                self._add(zone, f"the self-closing tag <{tag}/>")
        else:
            self.stack.append(tag)
        # A fragment never leaves the article it is read inside, so it is all content.
        if zone == "content" or self.addresses is None:
            self._content(tag, values, names, inside_pre="pre" in self.stack)
        elif zone == "head":
            self._head(tag, values, names, self.addresses)
        else:
            self._chrome(tag, values, self.addresses)

    def handle_endtag(self, tag: str) -> None:
        open_tags = self.stack[self.floor :]
        if open_tags and open_tags[-1] == tag:
            self.stack.pop()
            return
        self._add("page structure", f"the end tag </{tag}>, which closes no open element")
        # Close what it would close, so that the rest of the page is read in its zone.
        if tag in open_tags:
            while self.stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if "<" in data and self.stack[-1:] not in (["script"], ["style"]):
            self._add(self._zone(), f"a raw < in the text {_excerpt(data)}")

    def handle_comment(self, data: str) -> None:
        if self._zone() == "content" or f"<!--{data}-->" != _ICON_COMMENT:
            self._add(self._zone(), f"the comment {_excerpt(data)}")

    def handle_decl(self, decl: str) -> None:
        if decl.lower() != "doctype html" or self.stack:
            self._add(self._zone(), f"the declaration {_excerpt(decl)}")

    def unknown_decl(self, data: str) -> None:
        self._add(self._zone(), f"the declaration {_excerpt(data)}")

    def handle_pi(self, data: str) -> None:
        self._add(self._zone(), f"the processing instruction {_excerpt(data)}")

    def _content(
        self, tag: str, values: dict[str, str], names: list[str], *, inside_pre: bool
    ) -> None:
        if tag not in _CONTENT_ELEMENTS:
            self._add("content", f"the element <{tag}>")
            return
        for name in names:
            problem = _content_attribute(tag, name, values[name], inside_pre=inside_pre)
            if problem:
                self._add("content", problem)

    def _head(
        self, tag: str, values: dict[str, str], names: list[str], addresses: SiteAddresses
    ) -> None:
        if tag not in _HEAD_ELEMENTS:
            self._add("head", f"the element <{tag}>")
        elif tag == "meta":
            if not any(_meta_fits(shape, values, names) for shape in _META_SHAPES):
                self._add("head", f"a meta element with {_excerpt(_attributes(values))}")
        elif tag == "link":
            problem = _link_problem(values, names, addresses)
            if problem:
                self._add("head", problem)
        elif names:
            self._add("head", f"the attributes {_excerpt(_attributes(values))} on <{tag}>")

    def _chrome(self, tag: str, values: dict[str, str], addresses: SiteAddresses) -> None:
        allowed = _CHROME_ATTRIBUTES.get(tag)
        if allowed is None:
            self._add("theme markup", f"the element <{tag}>")
            return
        for name, value in values.items():
            problem = (
                f"the attribute {name} on <{tag}>, with the value {_excerpt(value)}"
                if name not in allowed
                else _chrome_value(tag, name, value, addresses)
            )
            if problem:
                self._add("theme markup", problem)


def _attributes(values: dict[str, str]) -> str:
    return " ".join(f'{name}="{value}"' for name, value in values.items())


def _meta_fits(
    shape: tuple[tuple[str, re.Pattern[str]], ...], values: dict[str, str], names: list[str]
) -> bool:
    if names != [name for name, _ in shape]:
        return False
    return all(pattern.fullmatch(values[name]) for name, pattern in shape)


def _in_site(address: str, addresses: SiteAddresses) -> bool:
    """Say whether an address of the theme's markup stays in the site."""
    cleaned = _cleaned(address)
    if cleaned.startswith(addresses.base_path) and not _OTHER_HOST.match(cleaned):
        return True
    if cleaned.startswith(addresses.root):
        return True
    return _stays_on_host(address) and not cleaned.startswith("/")


def _link_problem(values: dict[str, str], names: list[str], addresses: SiteAddresses) -> str | None:
    """Say what is wrong with one link element of the head, or ``None``."""
    rel = values.get("rel", "")
    href = values.get("href", "")
    shown = f"a link element with {_excerpt(_attributes(values))}"
    if rel == "preconnect":
        fits = names == ["rel", "href", "crossorigin"] and href == _FONT_HOST
        return None if fits and values["crossorigin"] == "" else shown
    if names != ["rel", "href"]:
        return shown
    if rel == "stylesheet":
        fits = href.startswith(_FONT_STYLESHEET) or (
            _in_site(href, addresses) and href.endswith(".css")
        )
    elif rel == "canonical":
        fits = href.startswith(addresses.root) and _stays_on_host(href[len(addresses.root) :])
    elif rel in {"icon", "next", "prev"}:
        fits = _in_site(href, addresses)
    else:
        fits = False
    return None if fits else shown


def _chrome_value(tag: str, name: str, value: str, addresses: SiteAddresses) -> str | None:
    """Say what is wrong with the value of one allowed attribute of the theme, or ``None``."""
    shown = f"the attribute {name} on <{tag}>, with the value {_excerpt(value)}"
    if name == "href":
        allowed = (
            value.startswith("#")
            or _in_site(value, addresses)
            or value in {addresses.repository, _GENERATOR_ADDRESS}
        )
        return None if allowed else shown
    if name == "class":
        return None if all(_CHROME_CLASS.fullmatch(token) for token in value.split()) else shown
    if name == "id":
        return None if _THEME_ID.fullmatch(value) else shown
    if name == "data-md-component":
        return None if value in _CHROME_COMPONENTS else shown
    checks = {
        ("input", "type"): value in _CHROME_INPUT_TYPES,
        ("a", "target"): value == "_blank",
        ("a", "rel"): value == "noopener",
        ("svg", "xmlns"): value == _SVG_NAMESPACE,
        ("path", "d"): _PATH_DATA.fullmatch(value) is not None,
        # Only the pinned scripts are allowed, and the raw text decides that. These keep an
        # attribute of a script to the shapes the pinned scripts have.
        ("script", "type"): value == "application/json",
        ("script", "id"): value == "__config",
        ("script", "src"): _in_site(value, addresses),
    }
    return None if checks.get((tag, name), True) else shown


def _content_attribute(tag: str, name: str, value: str, *, inside_pre: bool) -> str | None:
    """Say what is wrong with one attribute of an allowed content element, or ``None``."""
    shown = f"the attribute {name} on <{tag}>, with the value {_excerpt(value)}"
    if name == "id":
        # The theme keeps the ``__`` namespace for its own elements, such as ``__config``.
        return None if tag in _HEADINGS and not value.startswith("__") else shown
    if name == "class":
        tokens = frozenset(value.split())
        if tag == "span" and inside_pre and len(tokens) == 1:
            return None if all(_TOKEN_CLASS.fullmatch(token) for token in tokens) else shown
        return None if tokens in _CONTENT_CLASSES.get(tag, frozenset()) else shown
    if name == "title":
        allowed = value == _PERMALINK_TITLE or _CITATION_TITLE.fullmatch(value) is not None
        return None if tag == "a" and allowed else shown
    if name == "href" and tag == "a":
        scheme = _scheme(value)
        if scheme is not None:
            return None if scheme in _LINK_SCHEMES else f"{shown}, whose scheme is {scheme}"
        return None if not _OTHER_HOST.match(_cleaned(value)) else f"{shown}, on another host"
    if name == "style" and tag in {"td", "th"} and _CELL_STYLE.fullmatch(value):
        return None
    return shown


def _raw_problems(html: str, base: str) -> list[tuple[str, str]]:
    """Check the page as characters, where no parser decides where anything ends."""
    problems: list[str] = []
    for tag in _ONCE:
        opened = len(_opening(tag).findall(html))
        closed = len(_closing(tag).findall(html))
        if (opened, closed) != (1, 1):
            problems.append(f"{opened} opening and {closed} closing <{tag}> tags, not one of each")
    title = re.search(r"<title>(?P<text>.*?)</title", html, re.IGNORECASE | re.DOTALL)
    if title and "<" in title["text"]:
        problems.append("markup inside <title>")

    # Each pinned script and the pinned style once, and no other opening of either.
    scripts = [_pinned(script, base) for script in _SCRIPTS]
    for script in scripts:
        if html.count(script) != 1:
            problems.append(f"the theme script {_excerpt(script)} {html.count(script)} times")
    openings = len(_opening("script").findall(html))
    if openings != len(scripts):
        problems.append(f"{openings} script elements, where the theme writes {len(scripts)}")
    if html.count(_STYLE) != 1 or len(_opening("style").findall(html)) != 1:
        problems.append("a style element other than the one the theme writes")

    # The icon comment is the only comment, and it is never inside the article.
    icons = [found.start() for found in re.finditer(re.escape(_ICON_COMMENT), html)]
    if html.count("<!--") != len(icons):
        problems.append("a comment other than the theme's icon comment")
    article = _opening(_CONTENT_ELEMENT).search(html)
    article_end = _closing(_CONTENT_ELEMENT).search(html)
    if article and article_end and any(article.start() < at < article_end.end() for at in icons):
        problems.append("the theme's icon comment inside the article")
    declarations = html.count("<!") - html.count("<!--")
    if declarations != 1 or not html.lstrip().lower().startswith(_DOCTYPE):
        problems.append(f"{declarations} declarations, where a page has only {_DOCTYPE}")
    if "<![" in html:
        problems.append("a CDATA section")
    if "<?" in html:
        problems.append("a processing instruction")
    return [("page structure", problem) for problem in problems]


def page_problems(html: str, addresses: SiteAddresses, base: str) -> list[Problem]:
    """List what one built page holds that the library and the pinned theme do not write.

    Args:
        html: The whole HTML of the page, as MkDocs wrote it.
        addresses: The site's addresses.
        base: The base path the theme writes into this page, from ``page_base``.

    Returns:
        One problem per finding, in the order found, each with an empty path. The list is
        empty only for a page whose raw text, head, theme markup, and content are all on the
        lists.
    """
    problems = list(_raw_problems(html, base))
    reader = _Reader(addresses)
    reader.feed(html)
    reader.close()
    problems.extend(reader.problems)
    for tag in reader.stack:
        problems.append(("page structure", f"the element <{tag}>, which is never closed"))
    for value, count in reader.ids.items():
        if count > 1:
            problems.append(("page structure", f"the id {_excerpt(value)} {count} times"))
    return [Problem(kind, "", detail) for kind, detail in problems]


def content_problems(text: str) -> list[str]:
    """List what a fragment of content holds that the library's Markdown does not write.

    The fragment is read under the rules of the article of a page, as the Markdown of a page
    renders before the theme wraps it, or as an entry of the search index holds it.

    Args:
        text: The HTML of the fragment.

    Returns:
        One line per problem, in the order found. The list is empty for a fragment that holds
        only what the library's Markdown writes.
    """
    # A comment, a declaration, a CDATA section, and a processing instruction all start so.
    problems = [f"the raw text {marker}" for marker in ("<!", "<?") if marker in text]
    for tag in ("script", "style"):
        if _opening(tag).search(text):
            problems.append(f"a <{tag}> element")
    reader = _Reader(None)
    reader.feed(text)
    reader.close()
    problems.extend(detail for _, detail in reader.problems)
    problems.extend(
        f"the element <{tag}>, which is never closed" for tag in reader.stack[reader.floor :]
    )
    return problems


def search_index_problems(text: str) -> list[str]:
    """List what the search index holds that a page of the library does not.

    The theme makes each entry's location a link and inserts its title and text into the page
    as markup, so the title and the text are read under the rules of a page's content.

    Args:
        text: The text of ``search/search_index.json``.

    Returns:
        One line per problem, in the order found.
    """
    try:
        index = json.loads(text)
    except json.JSONDecodeError as error:
        return [f"the index is not JSON: {error}"]
    if not isinstance(index, dict) or set(index) != {"config", "docs"}:
        return ["the index is not an object with only config and docs"]
    docs = index["docs"]
    if not isinstance(docs, list):
        return ["the docs of the index are not a list"]
    problems: list[str] = []
    for number, entry in enumerate(docs):
        if not isinstance(entry, dict) or set(entry) != _SEARCH_ENTRY_KEYS:
            problems.append(f"entry {number} does not hold exactly {sorted(_SEARCH_ENTRY_KEYS)}")
            continue
        if not all(isinstance(entry[key], str) for key in _SEARCH_ENTRY_KEYS):
            problems.append(f"entry {number} holds a value that is not text")
            continue
        if not _stays_on_host(entry["location"]) or _cleaned(entry["location"]).startswith("/"):
            problems.append(f"entry {number} has the location {_excerpt(entry['location'])}")
        for key in ("title", "text"):
            problems.extend(
                f"entry {number} {key}: {problem}" for problem in content_problems(entry[key])
            )
    return problems


def _served_problem(path: str) -> str | None:
    """Say why a file that is not a page may not be served, or ``None``."""
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix
    if path in _SERVED_BY_NAME or name == _LICENSE_FILE or suffix in _SERVED_ANYWHERE:
        return None
    if any(path.startswith(directory) for directory in _SERVED_IN.get(suffix, ())):
        return None
    return "a file of a kind the library and the theme do not serve"


def _installed_theme_version() -> str:
    return version(THEME)


def site_problems(site_dir: Path, addresses: SiteAddresses) -> list[Problem]:
    """List the problems of every file a built site serves.

    Args:
        site_dir: The directory the site was built into, with the canonical files copied in.
        addresses: The site's addresses.

    Returns:
        Every problem, files in the order of their paths. A different installed theme version
        comes first, as one problem.
    """
    problems: list[Problem] = []
    installed = _installed_theme_version()
    if installed != THEME_VERSION:
        problems.append(
            Problem(
                "theme version",
                "",
                f"{THEME} {installed} is installed, and the lists of this check were read from "
                f"{THEME_VERSION}",
            )
        )
    for file in sorted(path for path in site_dir.rglob("*") if not path.is_dir()):
        name = file.relative_to(site_dir).as_posix()
        if file.suffix.lower() == ".html":
            text = file.read_text(encoding="utf-8")
            base = page_base(name, addresses)
            problems.extend(
                replace(found, path=name) for found in page_problems(text, addresses, base)
            )
        elif name == _SEARCH_INDEX:
            text = file.read_text(encoding="utf-8")
            problems.extend(
                Problem("search index", name, detail) for detail in search_index_problems(text)
            )
        else:
            problem = _served_problem(name)
            if problem:
                problems.append(Problem("served file", name, problem))
    return problems
