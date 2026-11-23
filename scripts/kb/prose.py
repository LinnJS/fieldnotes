"""The text of a chapter, written so that a renderer shows it and never runs it.

A chapter is the author's text. The site renders it with Python-Markdown and the exports
render it with Pandoc, and both read more than words in it: a tag, an attribute list in
braces, a link to a script, an image on another host. This module rewrites those so the
reader sees the characters the chapter holds. It uses only what both renderers honor, which
is a backslash in front of a mark, a character reference for an angle bracket, and a
percent-encoded link destination. The canonical chapter file is never changed.

The rewrite has to tell code from prose, and the two renderers do not agree with each other
on every edge. So it takes for code only what both take for code, and it escapes every
backtick it did not pair, which leaves a renderer nothing to pair in another way.
``kb.site_check`` reads the built pages of the site afterwards and stops the build when one
still holds markup.
"""

import html
import re
from collections.abc import Sequence
from urllib.parse import quote

__all__ = ["link_address", "shown_as_written"]

_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
# A character of chapter prose that Python-Markdown reads as the start of an HTML tag or of an
# attribute list, a run of backticks it could read as the edge of a code span, or the mark
# that makes a link an image, with the backslashes in front of it.
_LIVE_MARK = re.compile(r"(?P<slashes>\\*)(?P<mark>[<{}]|`+|!(?=\[))")
_AUTOLINK = re.compile(r"<https?://[^<>\s]*>")
# The opening line of a fenced block as the ingest writer writes it: the fence and at most one
# word. The renderer accepts more, and whatever this pattern leaves out is treated as prose.
_FENCE_OPENING = re.compile(r"(?P<indent> *)(?P<fence>`{3,}|~{3,})[ \t]*[\w+#.-]*[ \t]*")
# A run of backticks with the backslashes in front of it.
_TICK_RUN = re.compile(r"(?P<slashes>\\*)(?P<ticks>`+)")
# Where the renderer could start reading a link destination: after the ``](`` of an inline
# link, or after the label of a reference definition.
_DESTINATION_START = re.compile(
    r"(?P<slashes>\\*)(?P<inline>\]\()|^ {0,3}(?P<definition>\[)[^\]\n]*\]:", re.MULTILINE
)
# A whole inline link whose destination is written in angle brackets.
_ANGLE_LINK = re.compile(
    r"(?<!\\)\[(?:\\.|[^\]\\\n])*\]\(<(?P<address>[^<>\n]*)>(?:[ \t]+\"[^\"\n]*\")?\)"
)
# What a destination keeps when it is percent-encoded: the characters a URL is built from,
# and the percent sign of an encoding it already has.
_DESTINATION_SAFE = "/:?#[]@!$&'*+,;=%~"
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_NOT_SHOWN = re.compile(r"[\x00-\x20\x7f]")
# The schemes a link of a chapter may have. A destination with no scheme is a path.
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
# A whole inline link whose opening bracket is not escaped. Group ``destination`` is the one
# part of it that is an address and not prose.
_INLINE_LINK = re.compile(
    r"(?<!\\)\[(?:\\.|[^\]\\\n])*\]"
    r"\((?P<destination>[^\s()<>]*(?:\([^\s()<>]*\)[^\s()<>]*)*)"
    r"(?:[ \t]+\"[^\"\n]*\")?\)"
)


def link_address(url: str) -> str:
    """Write a URL of a record as the destination of a Markdown link.

    A record is data, and a URL in it may hold a parenthesis or an angle bracket. Written as
    it stands, a closing parenthesis ends the link and whatever follows it is read as markup.
    Every character that is not part of a URL's own syntax is percent-encoded, which leaves
    an ordinary address unchanged.

    Args:
        url: The URL as the record holds it.

    Returns:
        The destination.
    """
    return quote(url, safe=_DESTINATION_SAFE)


def _closing_fence(lines: Sequence[str], opening: int) -> int | None:
    """Find the line that closes the fenced block a line opens.

    Args:
        lines: The lines of the text.
        opening: Index of the line to read as an opening fence.

    Returns:
        The index of the closing line, or ``None`` when the line opens no block or the block
        never closes. The closing line is the same fence at the same indentation and nothing
        else, which is the one shape every fence extension of the renderer agrees on.
    """
    opened = _FENCE_OPENING.fullmatch(lines[opening])
    if opened is None:
        return None
    closing = opened["indent"] + opened["fence"]
    for index in range(opening + 1, len(lines)):
        if lines[index].rstrip(" \t") == closing:
            return index
    return None


def _code_spans(line: str) -> list[tuple[int, int]]:
    """Find the inline code of one line that every version of the renderer agrees on.

    A span opens at a run of backticks that no backslash escapes and closes at the next run
    of exactly as many. Python-Markdown has paired a run that finds no such partner in more
    than one way over its versions, so a run with no partner on its own line opens nothing
    here, and ``shown_as_written`` escapes it so that it opens nothing in the renderer.

    Args:
        line: One line of Markdown outside a fenced block.

    Returns:
        The start and the end of each span, backticks included.
    """
    runs = [
        (run.start("ticks"), run.end("ticks"), len(run["slashes"]) % 2 == 1)
        for run in _TICK_RUN.finditer(line)
    ]
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(runs):
        start, end, escaped = runs[index]
        closing = next(
            (
                later
                for later in range(index + 1, len(runs))
                if runs[later][1] - runs[later][0] == end - start
            ),
            None,
        )
        if escaped or closing is None:
            index += 1
        else:
            spans.append((start, runs[closing][1]))
            index = closing + 1
    return spans


def _mask_rendered_code(text: str) -> str:
    """Blank out what the site's renderer takes for code, keeping every offset and line break.

    ``mask_code`` serves the citation checker, where taking prose for code only skips a token.
    Here the same mistake leaves a tag of the prose unescaped, and the renderer runs it. So
    this mask may take less for code than the renderer does and must never take more. A fenced
    block counts only when its opening line is the plain one the ingest writer writes and a
    matching line closes it. An inline span counts only inside one line, because where a
    paragraph ends is the renderer's to decide.

    Text that the renderer takes for code and this mask does not is escaped once too often, and
    the page then shows ``&lt;`` where the chapter has ``<``. That is wrong on the page and
    safe. The check of the built pages in ``kb.site_check`` catches the opposite mistake.

    Args:
        text: The Markdown.

    Returns:
        The text with every character of such code replaced by a space.
    """
    lines = text.split("\n")
    masked: list[str] = []
    index = 0
    while index < len(lines):
        closing = _closing_fence(lines, index)
        if closing is None:
            line = lines[index]
            for start, end in _code_spans(line):
                line = line[:start] + " " * (end - start) + line[end:]
            masked.append(line)
            index += 1
        else:
            masked.extend(" " * len(line) for line in lines[index : closing + 1])
            index = closing + 1
    return "\n".join(masked)


def _runs_on_click(destination: str) -> bool:
    """Say whether a link destination has a scheme other than a web address or a mail address.

    A browser reads the scheme after it has decoded character references and dropped white
    space and control characters, so ``java&#9;script:`` is read the same way here.

    Args:
        destination: The text that follows the opening of a link destination.

    Returns:
        True for a destination such as ``javascript:`` or ``data:``. A destination with no
        scheme is a path and is fine.
    """
    shown = _NOT_SHOWN.sub("", html.unescape(destination)).lstrip("<")
    scheme = _URL_SCHEME.match(shown)
    return scheme is not None and scheme[0][:-1].lower() not in _LINK_SCHEMES


def _with_plain_destinations(text: str) -> str:
    """Rewrite the link destinations of a chapter that the page must not carry as written.

    A destination with a scheme that runs code on a click is taken out of service: the ``](``
    in front of it, or the label of its reference definition, gets a backslash, so the renderer
    shows the link as the text it is. The destination of a whole link that is written in angle
    brackets is written without them and percent-encoded instead, so that no angle bracket of
    a chapter is left for the renderer to read as a tag when it pairs the square brackets
    around it in another way.

    Args:
        text: The Markdown body of a chapter.

    Returns:
        The body with those destinations rewritten. Code is left as written.
    """
    parts: list[str] = []
    end = 0
    for start in _DESTINATION_START.finditer(_mask_rendered_code(text)):
        if start.start() < end or (start["inline"] and len(start["slashes"]) % 2 == 1):
            continue
        paragraph_end = _BLANK_LINE.search(text, start.end())
        destination = text[start.end() : paragraph_end.start() if paragraph_end else len(text)]
        if _runs_on_click(destination):
            marker, shown = ("[", "\\[") if start["definition"] else ("](", "\\]\\(")
            written = text[start.start() : start.end()]
            parts += [text[end : start.start()], written.replace(marker, shown, 1)]
            end = start.end()
    text = "".join([*parts, text[end:]])

    parts, end = [], 0
    for link in _ANGLE_LINK.finditer(_mask_rendered_code(text)):
        address = text[link.start("address") : link.end("address")]
        parts += [text[end : link.start("address") - 1], quote(address, safe=_DESTINATION_SAFE)]
        end = link.end("address") + 1
    return "".join([*parts, text[end:]])


def shown_as_written(text: str) -> str:
    """Keep the prose of a chapter from being rendered as HTML or as an attribute list.

    A chapter is the author's text, and the page must show it and never run it. The ingest
    writer puts a backslash in front of an angle bracket, which Pandoc honors and
    Python-Markdown does not, so a tag the source prints would become a live element. A brace
    at the end of a heading or after a link would set attributes on it, because the site turns
    on ``attr_list``. Outside code, an angle bracket becomes an entity and a brace gets a
    backslash, which Python-Markdown does honor. A backtick outside code gets a backslash as
    well, so the renderer cannot pair two of them around a tag and take the tag for code that
    this function took for prose. An ``http`` or ``https`` autolink and the destination of an
    inline link stay live, so links keep working. Parentheses that only look like a link's are
    prose, and nothing in them is left alone. A link whose destination is not a web address is
    shown as the text it is, and a destination in angle brackets is percent-encoded instead.
    An image is shown as a link to it, because the library carries no image of a book and a
    page must not fetch one from another host.

    Args:
        text: The Markdown body of a chapter.

    Returns:
        The body for the staged page. The canonical chapter file is not changed.
    """
    text = _with_plain_destinations(text)
    links = [link.span("destination") for link in _INLINE_LINK.finditer(_mask_rendered_code(text))]

    def show(match: re.Match[str]) -> str:
        slashes, mark = match["slashes"], match["mark"]
        escaped = len(slashes) % 2 == 1
        start = match.start("mark")
        if mark.startswith("`"):
            # Every backtick of the run gets its own backslash, because the renderer opens a
            # span at the second backtick of a run whose first one is escaped.
            return slashes[: len(slashes) - escaped] + "\\`" * len(mark)
        if mark == "!":
            return match[0] if escaped else f"{slashes}\\!"
        if any(first <= start < last for first, last in links):
            return match[0]
        if mark == "<":
            if not escaped and _AUTOLINK.match(match.string, start):
                return match[0]
            return slashes[: len(slashes) - escaped] + "&lt;"
        return match[0] if escaped else f"{slashes}\\{mark}"

    parts: list[str] = []
    end = 0
    # The mask keeps every offset, so a match in it sits at the same place in the text.
    for match in _LIVE_MARK.finditer(_mask_rendered_code(text)):
        parts += [text[end : match.start()], show(match)]
        end = match.end()
    return "".join([*parts, text[end:]])
