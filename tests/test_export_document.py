"""The pass over a parsed chapter and the check of the whole export document."""

import json
import subprocess
import unicodedata
from collections.abc import Iterator

import pytest
from kb.export import CHAPTER_FORMAT, find_pandoc
from kb.export_document import (
    ChapterBlocks,
    DocumentError,
    Json,
    check_document,
    clean_chapters,
)

ANCHOR = "chapter-01-first"
OTHER_ANCHOR = "chapter-02-second"
CHAPTER_LINKS = {"01-first.md": ANCHOR, "02-second.md": OTHER_ANCHOR}
LIBRARY_IDS = frozenset({"copy-notice", "copy-notice-license"})
EMPTY_ATTR: Json = ["", [], []]


def parse(text: str) -> list[Json]:
    """Parse chapter text the way the export reads a chapter, and return its blocks."""
    result = subprocess.run(
        [str(find_pandoc()), f"--from={CHAPTER_FORMAT}", "--to=json", "--sandbox"],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    blocks = json.loads(result.stdout)["blocks"]
    assert isinstance(blocks, list)
    return blocks


def clean(body: str) -> list[Json]:
    """Clean one chapter whose body follows its title, and return the title and the body."""
    book = clean_chapters(
        [ChapterBlocks(ANCHOR, parse(f"# First\n\n{body}"))], CHAPTER_LINKS, LIBRARY_IDS
    )
    [chapter] = book.chapters
    return [chapter.title, *chapter.body]


def nodes(tree: Json) -> Iterator[dict[str, Json]]:
    """Yield every node of a tree, the tree itself included."""
    if isinstance(tree, dict):
        if "t" in tree:
            yield tree
        for value in tree.values():
            yield from nodes(value)
    elif isinstance(tree, list):
        for value in tree:
            yield from nodes(value)


def types(tree: Json) -> set[str]:
    return {str(node["t"]) for node in nodes(tree)}


def text(tree: Json) -> str:
    """Return the words of a tree, with one space for each space or line break."""
    parts: list[str] = []
    for node in nodes(tree):
        if node["t"] == "Str":
            parts.append(str(node["c"]))
        elif node["t"] in ("Space", "SoftBreak", "LineBreak"):
            parts.append(" ")
    return "".join(parts)


def links(tree: Json) -> list[str]:
    found: list[str] = []
    for node in nodes(tree):
        if node["t"] == "Link":
            content = node["c"]
            assert isinstance(content, list) and isinstance(content[2], list)
            found.append(str(content[2][0]))
    return found


def attributes(tree: Json) -> list[Json]:
    """Return the attribute triple of every node that has one."""
    found: list[Json] = []
    for node in nodes(tree):
        content = node.get("c")
        if node["t"] in ("Link", "Image", "Code", "CodeBlock", "Span", "Div"):
            assert isinstance(content, list)
            found.append(content[0])
        elif node["t"] == "Header":
            assert isinstance(content, list)
            found.append(content[1])
    return found


def document(blocks: list[Json], meta: dict[str, Json] | None = None) -> Json:
    return {"pandoc-api-version": [1, 23, 1, 2], "meta": meta or {}, "blocks": blocks}


def header(identifier: str, *classes: str, level: int = 1) -> Json:
    return {"t": "Header", "c": [level, [identifier, list(classes), []], [str_("Title")]]}


def str_(value: str) -> Json:
    return {"t": "Str", "c": value}


def para(*inlines: Json) -> Json:
    return {"t": "Para", "c": list(inlines)}


def link(url: str) -> Json:
    return {"t": "Link", "c": [EMPTY_ATTR, [str_("here")], [url, ""]]}


def test_a_script_address_written_with_a_backslash_is_shown_as_text() -> None:
    cleaned = clean("A [script link](javascript\\:alert(1)) here.\n")

    assert links(cleaned) == []
    assert "A script link here." in text(cleaned)


def test_braces_after_a_link_set_no_attribute_and_are_shown_as_text() -> None:
    cleaned = clean("A [brace link](https://h/\\(c){onmouseover=x}d) here.\n")

    assert links(cleaned) == ["https://h/(c"]
    assert attributes(cleaned)[1:] == [EMPTY_ATTR]
    assert "brace link{onmouseover=x}d) here." in text(cleaned)


def test_a_reference_definition_in_a_list_item_or_a_block_quote_makes_no_link() -> None:
    cleaned = clean(
        "- [x]: javascript:alert(1)\n\n> [y]: javascript:alert(2)\n\nThen [x] and [y].\n"
    )

    assert links(cleaned) == []
    assert "Then x and y." in text(cleaned)


def test_raw_html_becomes_text_with_the_same_characters() -> None:
    cleaned = clean('An <b onclick="x">inline</b> tag.\n\n<script>alert(1)</script>\n')

    assert not types(cleaned) & {"RawInline", "RawBlock"}
    assert 'An <b onclick="x">inline</b> tag.' in text(cleaned)
    assert cleaned[-1] == para(str_("<script>alert(1)</script>"))


def test_text_that_spans_lines_becomes_words_on_one_line() -> None:
    cleaned = clean(
        "<div>\n= Raw heading\n- raw item\n</div>\n\n"
        "First line\u2028= Prose heading\x85and\u2029more.\n"
    )

    for node in nodes(cleaned):
        if node["t"] == "Str":
            assert not any(
                unicodedata.category(character) in ("Cc", "Zl", "Zp")
                for character in str(node["c"])
            ), node
    assert "<div> = Raw heading - raw item </div>" in text(cleaned)
    assert "First line = Prose heading and more." in text(cleaned)


@pytest.mark.parametrize(
    "character", ["\n", "\r", "\t", "\x0b", "\x0c", "\x00", "\x85", "\u2028", "\u2029"]
)
def test_the_check_refuses_a_line_break_or_a_control_character_in_a_word(character: str) -> None:
    with pytest.raises(DocumentError, match="character"):
        check_document(document([para(str_(f"a{character}= b"))]), set(), LIBRARY_IDS)


def test_an_image_becomes_its_text() -> None:
    cleaned = clean("See ![a *local* file](/etc/passwd) now.\n")

    assert "Image" not in types(cleaned)
    assert "Emph" in types(cleaned)
    assert "See a local file now." in text(cleaned)
    assert "/etc/passwd" not in json.dumps(cleaned)


def test_marks_of_the_extensions_that_are_off_are_shown_as_text() -> None:
    cleaned = clean(
        "Math $x$ and $$y$$, an emoji :smile:, ~~struck~~, a mark [^1], and https://a.example.\n\n"
        "- [ ] a box\n\n"
        "> [!NOTE]\n> an alert\n"
    )

    assert types(cleaned) <= {"Header", "Para", "Plain", "BulletList", "BlockQuote", "Str"} | {
        "Space",
        "SoftBreak",
    }
    words = text(cleaned)
    for mark in ("$x$", "$$y$$", ":smile:", "~~struck~~", "[^1]", "https://a.example."):
        assert mark in words
    assert "[ ] a box" in words
    assert "[!NOTE] an alert" in words


def test_a_fence_line_sets_no_attribute_and_keeps_a_plain_language_word() -> None:
    cleaned = clean(
        "```python {#i onclick=y}\nx\n```\n\n"
        "``` {#i onclick=y}\ny\n```\n\n"
        "~~~ {.c onmouseover=x}\nz\n"
    )

    code_blocks = [node for node in nodes(cleaned) if node["t"] == "CodeBlock"]
    assert [block["c"] for block in code_blocks] == [
        [["", ["python"], []], "x"],
        [EMPTY_ATTR, "y"],
        [EMPTY_ATTR, "z\n"],
    ]


def test_a_link_to_another_chapter_points_at_its_anchor_and_any_other_path_is_text() -> None:
    cleaned = clean(
        "As in [the second](02-second.md) and [its part](02-second.md#part), "
        "not [a note](notes.md), [a book](../other/01-first.md), or [a place](#part).\n"
    )

    assert links(cleaned) == [f"#{OTHER_ANCHOR}", f"#{OTHER_ANCHOR}"]
    assert "not a note, a book, or a place." in text(cleaned)


def test_the_title_takes_the_chapter_anchor_and_heading_ids_are_unique_in_the_book() -> None:
    book = clean_chapters(
        [
            ChapterBlocks(ANCHOR, parse("# First\n\n## Setup\n\n## Copy notice\n")),
            ChapterBlocks(OTHER_ANCHOR, parse("# Second\n\n## Setup\n")),
        ],
        CHAPTER_LINKS,
        LIBRARY_IDS,
    )

    first, second = book.chapters
    assert attributes(first.title) == [[ANCHOR, [], []]]
    assert attributes(second.title) == [[OTHER_ANCHOR, [], []]]
    assert attributes(first.body) == [["setup", [], []], ["copy-notice-1", [], []]]
    assert attributes(second.body) == [["setup-1", [], []]]
    assert book.ids == {ANCHOR, OTHER_ANCHOR, "setup", "copy-notice-1", "setup-1"}


def test_a_chapter_that_does_not_open_with_its_title_is_refused() -> None:
    with pytest.raises(DocumentError, match="level-one heading"):
        clean_chapters([ChapterBlocks(ANCHOR, parse("Text first.\n"))], CHAPTER_LINKS, LIBRARY_IDS)


def test_the_pass_refuses_a_node_type_it_does_not_know() -> None:
    blocks = [header(""), para({"t": "Note", "c": [para(str_("x"))]})]

    with pytest.raises(DocumentError, match="Note"):
        clean_chapters([ChapterBlocks(ANCHOR, blocks)], CHAPTER_LINKS, LIBRARY_IDS)


def test_a_cleaned_chapter_passes_the_document_check() -> None:
    body = (
        "A [web link](https://example.invalid/a) and [the second](02-second.md).\n\n"
        "| a | b |\n| --- | --- |\n| `c` | **d** |\n\n```text\ncode\n```\n\n1. one\n2. two\n"
    )
    book = clean_chapters(
        [
            ChapterBlocks(ANCHOR, parse(f"# First\n\n{body}")),
            ChapterBlocks(OTHER_ANCHOR, parse("# Second\n")),
        ],
        CHAPTER_LINKS,
        LIBRARY_IDS,
    )
    blocks: list[Json] = [header("copy-notice", "unnumbered")]
    for chapter in book.chapters:
        blocks += [chapter.title, *chapter.body]

    check_document(document(blocks), book.ids | LIBRARY_IDS, LIBRARY_IDS)


def test_the_check_refuses_a_node_type_it_does_not_know() -> None:
    with pytest.raises(DocumentError, match="Div"):
        check_document(document([{"t": "Div", "c": [EMPTY_ATTR, []]}]), set(), LIBRARY_IDS)


def test_the_check_refuses_a_raw_node_in_a_metadata_value() -> None:
    meta: dict[str, Json] = {
        "title": {"t": "MetaInlines", "c": [{"t": "RawInline", "c": ["html", "<script>"]}]}
    }

    with pytest.raises(DocumentError, match="RawInline"):
        check_document(document([], meta), set(), LIBRARY_IDS)


def test_the_check_refuses_an_image() -> None:
    image: Json = {"t": "Image", "c": [EMPTY_ATTR, [], ["a.png", ""]]}

    with pytest.raises(DocumentError, match="Image"):
        check_document(document([para(image)]), set(), LIBRARY_IDS)


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "data:text/html,x", "notes.md", "#nowhere", " https://a"]
)
def test_the_check_refuses_a_link_outside_the_three_schemes_and_the_known_ids(url: str) -> None:
    with pytest.raises(DocumentError, match="link"):
        check_document(document([header(ANCHOR), para(link(url))]), {ANCHOR}, LIBRARY_IDS)


@pytest.mark.parametrize(
    "url", ["https://example.invalid/a", "HTTP://example.invalid", "mailto:a@b", f"#{ANCHOR}"]
)
def test_the_check_accepts_a_web_or_mail_address_and_a_known_anchor(url: str) -> None:
    check_document(document([header(ANCHOR), para(link(url))]), {ANCHOR}, LIBRARY_IDS)


@pytest.mark.parametrize(
    ("blocks", "problem"),
    [
        ([header("__config")], "id"),
        ([header(ANCHOR), header(ANCHOR)], "id"),
        ([para({"t": "Code", "c": [["x", [], []], "c"]})], "id"),
        ([header(ANCHOR, "unnumbered")], "class"),
        ([header("copy-notice", "evil")], "class"),
        ([{"t": "CodeBlock", "c": [["", ["python", "x"], []], "c"]}], "class"),
        ([{"t": "CodeBlock", "c": [["", ["{#i"], []], "c"]}], "class"),
        ([{"t": "CodeBlock", "c": [["", [], [["onclick", "x"]]], "c"]}], "attribute"),
        ([para({"t": "Code", "c": [["", ["x"], []], "c"]})], "class"),
    ],
)
def test_the_check_refuses_an_id_a_class_or_an_attribute_the_library_did_not_compute(
    blocks: list[Json], problem: str
) -> None:
    with pytest.raises(DocumentError, match=problem):
        check_document(document(blocks), {ANCHOR} | LIBRARY_IDS, LIBRARY_IDS)


def test_a_link_title_is_cleared() -> None:
    cleaned = clean('A [titled link](https://example.invalid/a "A title") here.\n')

    targets: list[Json] = []
    for node in nodes(cleaned):
        if node["t"] == "Link":
            content = node["c"]
            assert isinstance(content, list)
            targets.append(content[2])
    assert targets == [["https://example.invalid/a", ""]]


def test_the_check_refuses_a_link_with_a_title() -> None:
    titled: Json = {"t": "Link", "c": [EMPTY_ATTR, [str_("here")], ["https://a", "A title"]]}

    with pytest.raises(DocumentError, match="title"):
        check_document(document([para(titled)]), set(), LIBRARY_IDS)
