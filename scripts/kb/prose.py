"""The destination of a Markdown link that the library writes for a URL of a record.

The site and the exports write a record's URL into the library's own Markdown, such as the
author's address in a notice. A record is data, so the URL is percent-encoded before it becomes
the destination of a link. Chapter text is not rewritten here: the site turns renderer features
off for it in ``site_hooks.outside_text``, and the exports clean its parsed form in
``kb.export_document``.
"""

from urllib.parse import quote

__all__ = ["link_address"]

# What a destination keeps when it is percent-encoded: the characters a URL is built from,
# and the percent sign of an encoding it already has.
_DESTINATION_SAFE = "/:?#[]@!$&'*+,;=%~"


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
