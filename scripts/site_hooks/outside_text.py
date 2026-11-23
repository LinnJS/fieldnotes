"""The MkDocs hook that keeps the site's renderer from running text the library did not write.

A page of the site holds other people's text: a chapter, a license, a record field. The site
promises to show that text and never run it. This hook does not guess which characters the
renderer will read as markup. It turns the features off instead, for every page, so that no
pairing of characters can reach them:

- Raw HTML, inline and as a block, is not read. A tag is shown as the characters it is, and an
  angle bracket that the ingest writer escaped keeps its backslash.
- Images and reference definitions are not read. Both are shown as text.
- A link whose address has a scheme other than ``http``, ``https``, or ``mailto``, or that
  starts like an address on another host without one, is replaced with its text.
- A heading id is made without the leading underscores of its slug, so a heading cannot take
  an id from the theme's ``__`` namespace.

The library's own boxes, such as the facts box and the notices, come from one block that only
staging writes. It opens on a line that starts with ``MARKER`` and closes on ``CLOSE``.
Staging refuses outside text that holds the marker, so outside text cannot open a box.

MkDocs loads this file from its path, so it imports only Python-Markdown and the standard
library. ``kb.site`` imports ``MARKER`` and ``CLOSE`` from here, which keeps one copy of each.
"""

import html
import re
from collections.abc import MutableMapping, MutableSequence
from typing import Any
from xml.etree.ElementTree import Element, SubElement

import markdown
from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension
from markdown.extensions.toc import slugify as toc_slugify
from markdown.treeprocessors import Treeprocessor
from markdown.util import AMP_SUBSTITUTE

__all__ = [
    "CLOSE",
    "EXTENSIONS",
    "EXTENSION_CONFIGS",
    "MARKER",
    "OutsideTextExtension",
    "on_config",
    "render",
    "slugify",
]

MARKER = "@@library"
"""The start of a line that opens a library box. No outside text may hold it."""

CLOSE = f"{MARKER}-end"
"""The line that closes a library box."""

EXTENSIONS = ("tables", "pymdownx.highlight", "pymdownx.superfences", "toc")
"""The Markdown extensions of every page, as ``mkdocs.yml`` lists them."""

EXTENSION_CONFIGS: dict[str, dict[str, Any]] = {"toc": {"permalink": True, "marker": ""}}
"""The settings of those extensions, as ``mkdocs.yml`` gives them."""

# An open line names the box's classes, then an optional id for its title, then an optional
# title in double quotes that runs to the end of the line. Only staging writes it, so the
# classes and the id keep to the characters the library uses for them.
_OPEN = re.compile(
    rf"{re.escape(MARKER)} (?P<classes>[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)*)"
    r"(?: #(?P<id>[a-z0-9][a-z0-9-]*))?"
    r'(?: "(?P<title>.*)")?'
)
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_NOT_SHOWN = re.compile(r"[\x00-\x20\x7f]")
# Raw HTML, images, and reference definitions. Each is a rule of Python-Markdown that has no
# setting to turn it off.
_PREPROCESSORS = ("html_block",)
_BLOCK_PROCESSORS = ("reference",)
_INLINE_PATTERNS = ("html", "image_link", "image_reference", "short_image_ref")


def slugify(value: str, separator: str) -> str:
    """Make a heading id the way the ``toc`` extension does, without leading underscores.

    The theme keeps ids that start with ``__`` for its own elements, such as ``__config``.
    The rewrite never refuses a heading, because a faithful chapter may have one such as
    ``__init__``.

    Args:
        value: The text of the heading.
        separator: The character that takes the place of white space.

    Returns:
        The id. The ``toc`` extension makes it unique on the page afterwards.
    """
    return toc_slugify(value, separator).lstrip("_")


def _address_is_allowed(href: str) -> bool:
    """Say whether a link may keep its address.

    A browser decodes character references and drops white space and control characters
    before it reads a scheme, so ``java&#9;script:`` is read here the same way. An address
    stays only when it has no scheme and does not start like an address on another host, or
    when its scheme is one of the three.
    """
    shown = _NOT_SHOWN.sub("", html.unescape(href.replace(AMP_SUBSTITUTE, "&")))
    scheme = _URL_SCHEME.match(shown)
    if scheme is not None:
        return scheme[0][:-1].lower() in _LINK_SCHEMES
    return not re.match(r"[/\\]{2}|\\", shown)


def _unwrap(parent: Element, element: Element) -> None:
    """Put an element's text and children in its place in its parent, and drop the element."""
    index = list(parent).index(element)
    text = element.text or ""
    children = list(element)
    tail = element.tail or ""
    parent.remove(element)
    for offset, child in enumerate(children):
        parent.insert(index + offset, child)
    if index == 0:
        parent.text = (parent.text or "") + text
    else:
        before = parent[index - 1]
        before.tail = (before.tail or "") + text
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + tail
    elif index == 0:
        parent.text = (parent.text or "") + tail
    else:
        before = parent[index - 1]
        before.tail = (before.tail or "") + tail


class _LinkFilter(Treeprocessor):
    """Replace each link whose address is not allowed with its text."""

    def run(self, root: Element) -> None:
        refused = [
            (parent, child)
            for parent in root.iter()
            for child in parent
            if child.tag == "a" and not _address_is_allowed(child.get("href", ""))
        ]
        # A link inside another is unwrapped first, so its parent is still where it was found.
        for parent, child in reversed(refused):
            _unwrap(parent, child)


class _LibraryBlock(BlockProcessor):
    """Read a library box: an open line, the box's Markdown, and the close line.

    The box takes its content only from between the two lines. A box inside a box closes on
    its own close line first. Nothing after the close line joins the box, so an indented
    paragraph that follows it is read on its own. A title with an id is a third-level heading
    with that id, and a title without one is the title line of a notice.
    """

    def test(self, parent: Element, block: str) -> bool:
        return _OPEN.fullmatch(block.split("\n", 1)[0]) is not None

    def run(self, parent: Element, blocks: list[str]) -> None:
        lines = "\n\n".join(blocks).split("\n")
        del blocks[:]
        opened = _OPEN.fullmatch(lines[0])
        assert opened is not None
        depth = 1
        end = len(lines)
        for index in range(1, len(lines)):
            if lines[index] == CLOSE:
                depth -= 1
                if depth == 0:
                    end = index
                    break
            elif _OPEN.fullmatch(lines[index]):
                depth += 1

        box = SubElement(parent, "div", {"class": opened["classes"]})
        title = opened["title"]
        if title is not None and opened["id"] is not None:
            SubElement(box, "h3", {"id": opened["id"]}).text = title
        elif title is not None:
            SubElement(box, "p", {"class": "admonition-title"}).text = title
        self.parser.parseChunk(box, "\n".join(lines[1:end]).strip("\n"))

        rest = "\n".join(lines[end + 1 :]).lstrip("\n")
        if rest:
            blocks.extend(rest.split("\n\n"))


class OutsideTextExtension(Extension):
    """Turn off the renderer features that outside text could use, and read library boxes."""

    def __init__(self) -> None:
        """Build the extension, which has no settings."""
        # The base class's constructor has no annotations, so the strict type check refuses a
        # call to it. All it does is store settings, and this extension has none.
        self.setConfigs({})

    def extendMarkdown(self, md: markdown.Markdown) -> None:  # noqa: N802
        """Change the renderer of one page.

        Args:
            md: The renderer.
        """
        for name in _PREPROCESSORS:
            md.preprocessors.deregister(name)
        for name in _BLOCK_PROCESSORS:
            md.parser.blockprocessors.deregister(name)
        for name in _INLINE_PATTERNS:
            md.inlinePatterns.deregister(name)
        # The ingest writer puts a backslash in front of an angle bracket of the source, and the
        # site shows that backslash. Adding "<" to the escapable characters would hide it, but
        # the table of contents then holds the bare bracket, and the theme prints that entry
        # without escaping it.
        md.parser.blockprocessors.register(_LibraryBlock(md.parser), "library_block", 105)
        # Below the step that restores escaped characters in attributes, so the address is read
        # as the page will hold it.
        md.treeprocessors.register(_LinkFilter(md), "outside_text_links", -10)


def _configure(extensions: MutableSequence[Any], configs: MutableMapping[str, Any]) -> None:
    """Add this module's extension and heading ids to a list of extensions and its settings."""
    extensions.append(OutsideTextExtension())
    configs.setdefault("toc", {})["slugify"] = slugify


def render(text: str) -> str:
    """Render Markdown with the features every page of the site is built with.

    Args:
        text: The Markdown of a page, without its front matter.

    Returns:
        The HTML that the renderer of a page writes for it, before the theme wraps it.
    """
    extensions: list[Any] = list(EXTENSIONS)
    configs = {name: dict(settings) for name, settings in EXTENSION_CONFIGS.items()}
    _configure(extensions, configs)
    return markdown.markdown(text, extensions=extensions, extension_configs=configs)


def on_config(config: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Add this module's changes to the renderer of every page, when MkDocs loads the config.

    Args:
        config: The MkDocs configuration.

    Returns:
        The same configuration.
    """
    _configure(config["markdown_extensions"], config["mdx_configs"])
    return config
