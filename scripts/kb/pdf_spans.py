"""Read a PDF into spans of text, each with a font size and a position on its page.

This is the only module of the ingestion pipeline that touches a PDF. It reports what pypdf
sees and decides nothing about what a span means. The stages that follow take the spans as plain
data, so they run and are tested without a PDF.

A span is one run of text that the PDF draws in one font at one size. A renderer starts a new
span at each line, at each change of font, and at each link. Positions are in points, with the
origin at the bottom left corner of the page, as the PDF itself counts them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

__all__ = ["PdfError", "PdfText", "Span", "clean_text", "read_pdf"]

type _Matrix = Sequence[float]

_IDENTITY: _Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# A font that draws a ligature as one glyph may report the ligature's own code point.
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
_REPLACEMENTS = str.maketrans({**_LIGATURES, "\u00ad": "", "\n": " ", "\r": " "})

# A link's rectangle starts exactly where its text starts and ends exactly where the next span
# starts. The margin lets rounding move the first start a hair outside, and keeps the span after
# the link from counting as inside.
_LINK_MARGIN = 0.5


class PdfError(Exception):
    """A PDF could not be opened or its text could not be read.

    Attributes:
        path: The file that failed.
        reason: Why it failed, without the file name.
    """

    def __init__(self, path: Path, reason: str) -> None:
        """Build the error and its one-line description.

        Args:
            path: The file that failed.
            reason: Why it failed, without the file name.
        """
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


@dataclass(frozen=True)
class Span:
    """One run of text as the PDF draws it.

    Attributes:
        page: Page the span is on, counted from 1 in the file's own page index.
        x: Left end of the span's baseline, in points from the left edge of the page.
        y: Height of the span's baseline, in points from the bottom edge of the page.
        size: Font size as pypdf reports it. A PDF that scales its page content reports the
            size before scaling, so the number identifies a kind of text and is not a measure.
        text: The text, with any leading and trailing spaces the PDF holds.
        link: Target of the link annotation that covers the start of the span, or ``None``.
    """

    page: int
    x: float
    y: float
    size: float
    text: str
    link: str | None = None


@dataclass(frozen=True)
class PdfText:
    """Everything read from one PDF.

    Attributes:
        page_count: Number of pages in the file.
        spans: Every span, by page and then in the order the page draws them.
    """

    page_count: int
    spans: tuple[Span, ...]


def clean_text(text: str) -> str:
    """Replace the characters a PDF uses for typesetting with the text they stand for.

    Args:
        text: Text as pypdf reports it.

    Returns:
        The text with ligature characters spelled out, soft hyphens removed, and line breaks
        turned into spaces.
    """
    return text.translate(_REPLACEMENTS)


def read_pdf(path: Path) -> PdfText:
    """Read every span of text in a PDF.

    A link annotation is attached to each span that starts inside its rectangle. Only links to
    a URI are read. A link that covers the middle of a span is not attached, because pypdf does
    not report where a span ends.

    Args:
        path: The PDF file.

    Returns:
        The page count and the spans.

    Raises:
        PdfError: The file cannot be read or is not a PDF that pypdf can parse.
    """
    try:
        reader = PdfReader(path)
        spans: list[Span] = []
        for index, page in enumerate(reader.pages):
            collector = _PageCollector(index + 1, _links(page))
            page.extract_text(
                visitor_operand_before=collector.before_operator,
                visitor_operand_after=collector.after_operator,
                visitor_text=collector.text,
            )
            spans.extend(collector.spans)
        return PdfText(page_count=len(reader.pages), spans=tuple(spans))
    except (OSError, PyPdfError) as error:
        raise PdfError(path, str(error) or type(error).__name__) from error


@dataclass(frozen=True)
class _Link:
    left: float
    bottom: float
    right: float
    top: float
    target: str

    def covers(self, x: float, y: float) -> bool:
        return (
            self.left - _LINK_MARGIN <= x < self.right - _LINK_MARGIN
            and self.bottom - _LINK_MARGIN <= y <= self.top + _LINK_MARGIN
        )


def _links(page: Any) -> list[_Link]:
    links: list[_Link] = []
    for reference in page.get("/Annots") or ():
        annotation = reference.get_object()
        if annotation.get("/Subtype") != "/Link" or "/A" not in annotation:
            continue
        action = annotation["/A"].get_object()
        if action.get("/S") != "/URI" or "/URI" not in action:
            continue
        x0, y0, x1, y1 = (float(value) for value in annotation["/Rect"])
        links.append(
            _Link(
                left=min(x0, x1),
                bottom=min(y0, y1),
                right=max(x0, x1),
                top=max(y0, y1),
                target=str(action["/URI"]),
            )
        )
    return links


def _concatenate(first: _Matrix, second: _Matrix) -> _Matrix:
    """Return the transform that applies ``first`` and then ``second``."""
    a1, b1, c1, d1, e1, f1 = first
    a2, b2, c2, d2, e2, f2 = second
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


class _PageCollector:
    """Collects the spans of one page from pypdf's visitor callbacks.

    pypdf reads a form XObject, such as the transparency group a browser draws faded text in,
    with a fresh transform and never applies the transform that was in force where the form is
    drawn. Text inside a form would land at a wrong place on the page. The collector therefore
    keeps the transform of every form that is open and applies it itself.

    pypdf announces the operator that draws a form before it reads the form, and reports that
    operator as finished after it. In between it first hands over the text that precedes the
    form, which still belongs to the outer content. The transform of a form therefore takes
    effect only when the first operator inside the form arrives.
    """

    def __init__(self, page: int, links: list[_Link]) -> None:
        self.spans: list[Span] = []
        self._page = page
        self._links = links
        self._open_forms: list[_Matrix] = []
        self._drawn_at: _Matrix | None = None

    def before_operator(self, operator: Any, operands: Any, cm: Any, tm: Any) -> None:
        if self._drawn_at is not None:
            self._open_forms.append(_concatenate(self._drawn_at, self._outer()))
            self._drawn_at = None
        if operator == b"Do":
            self._drawn_at = tuple(float(value) for value in cm)

    def after_operator(self, operator: Any, operands: Any, cm: Any, tm: Any) -> None:
        if operator != b"Do":
            return
        if self._drawn_at is not None:
            # Nothing inside was read: the object is an image or an empty form.
            self._drawn_at = None
        elif self._open_forms:
            self._open_forms.pop()

    def text(self, text: Any, cm: Any, tm: Any, font: Any, size: Any) -> None:
        cleaned = clean_text(str(text))
        # pypdf reports each line break as a span of its own, at no position of its own.
        if not cleaned.strip() and (not cleaned or "\n" in str(text)):
            return
        # The last two numbers of a transform are where it puts the origin, and a span's origin
        # is the left end of its baseline.
        x, y = _concatenate(_concatenate(tm, cm), self._outer())[4:]
        link = next((link.target for link in self._links if link.covers(x, y)), None)
        self.spans.append(
            Span(page=self._page, x=x, y=y, size=float(size), text=cleaned, link=link)
        )

    def _outer(self) -> _Matrix:
        return self._open_forms[-1] if self._open_forms else _IDENTITY
