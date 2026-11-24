"""Sections become chapter files: fixed frontmatter and a Markdown body."""

from dataclasses import replace
from pathlib import Path

from kb.blocks import Block, CodeBlock, Run, Section, Table, TextBlock
from kb.catalog import Resource, Role, load_resource
from kb.frontmatter import (
    Chapter,
    ChapterSource,
    ExtractionStatus,
    PageRange,
    load_chapter,
)
from kb.markdown import UNASSIGNED_PART, draft_chapters, propose_slug, render_body

MIRRORED = "fixture-mirrored-book"


def text_block(role: Role, text: str) -> TextBlock:
    return TextBlock(role=role, runs=(Run(text),))


def cell(text: str) -> tuple[Run, ...]:
    return (Run(text),)


def make_section(
    *blocks: Block,
    title: str = "Folding the Hull",
    label: str = "§01",
    first_page: int = 3,
    last_page: int = 4,
) -> Section:
    return Section(
        label=label, title=title, first_page=first_page, last_page=last_page, blocks=blocks
    )


def body_of(*blocks: Block) -> str:
    """Render blocks under a fixed title and return the Markdown below the title."""
    rendered = render_body(make_section(*blocks, title="T"))
    assert rendered.startswith("# T\n\n")
    return rendered.removeprefix("# T\n\n")


def mirrored_book(fixture_library_root: Path) -> Resource:
    return load_resource(fixture_library_root, MIRRORED)


def test_the_body_opens_with_the_title_and_renders_each_kind_of_block() -> None:
    section = make_section(
        text_block(Role.KICKER, "A boat is a promise."),
        text_block(Role.LEDE, "A paper boat begins as a rectangle."),
        text_block(Role.HEADING, "Start with a dry sheet"),
        text_block(Role.BODY, "Choose a sheet with no creases."),
        text_block(Role.QUOTE, "A boat that dries flat will fold again."),
        Table(
            header=(cell("Pond"), cell("Depth"), cell("Wind")),
            rows=(
                (cell("Garden basin"), cell("Two spans"), cell("Still")),
                (cell("Mill pond"), cell("Nine spans"), cell("Gusty")),
            ),
        ),
        CodeBlock(lines=("check hull dry", "  check wind", "", "launch")),
    )

    assert render_body(section) == (
        "# Folding the Hull\n"
        "\n"
        "*A boat is a promise.*\n"
        "\n"
        "A paper boat begins as a rectangle.\n"
        "\n"
        "## Start with a dry sheet\n"
        "\n"
        "Choose a sheet with no creases.\n"
        "\n"
        "> A boat that dries flat will fold again.\n"
        "\n"
        "| Pond | Depth | Wind |\n"
        "| --- | --- | --- |\n"
        "| Garden basin | Two spans | Still |\n"
        "| Mill pond | Nine spans | Gusty |\n"
        "\n"
        "```text\n"
        "check hull dry\n"
        "  check wind\n"
        "\n"
        "launch\n"
        "```\n"
    )


def test_a_link_and_inline_code_are_written_inside_their_paragraph() -> None:
    paragraph = TextBlock(
        role=Role.BODY,
        runs=(
            Run("Refold as described in "),
            Run("Folding the Hull", link="01-folding-the-hull.md"),
            Run(", then run "),
            Run("launch --lee", code=True),
            Run("."),
        ),
    )

    assert body_of(paragraph) == (
        "Refold as described in [Folding the Hull](01-folding-the-hull.md), "
        "then run `launch --lee`.\n"
    )


def test_inline_code_that_holds_a_backtick_gets_a_longer_fence() -> None:
    paragraph = TextBlock(role=Role.BODY, runs=(Run("echo `date`", code=True),))

    assert body_of(paragraph) == "`` echo `date` ``\n"


def test_characters_that_markdown_would_read_as_markup_are_escaped() -> None:
    assert body_of(text_block(Role.BODY, "Use 2 * 3, a `tick`, an [index], and a <tag>.")) == (
        "Use 2 \\* 3, a \\`tick\\`, an \\[index\\], and a \\<tag>.\n"
    )
    assert body_of(text_block(Role.BODY, "Set HULL_DRY=1 and read _notes_ first.")) == (
        "Set HULL_DRY=1 and read \\_notes\\_ first.\n"
    )
    assert body_of(text_block(Role.KICKER, "Fold * and stop")) == "*Fold \\* and stop*\n"


def test_a_paragraph_that_starts_like_a_list_a_heading_or_a_quote_stays_a_paragraph() -> None:
    assert body_of(text_block(Role.BODY, "1. Fold the sheet in half.")) == (
        "1\\. Fold the sheet in half.\n"
    )
    assert body_of(text_block(Role.BODY, "# of folds is three.")) == "\\# of folds is three.\n"
    assert body_of(text_block(Role.BODY, "> three folds.")) == "\\> three folds.\n"
    assert body_of(text_block(Role.BODY, "- a dash opens this line.")) == (
        "\\- a dash opens this line.\n"
    )
    assert body_of(text_block(Role.HEADING, "2. Choosing a pond")) == "## 2. Choosing a pond\n"


def test_a_pipe_in_a_table_cell_is_escaped_and_an_empty_cell_stays_in_place() -> None:
    table = Table(
        header=((), cell("Wet"), cell("Dry")),
        rows=((cell("Hemp | jute"), (), (Run("coil", code=True), Run(" it"))),),
    )

    assert body_of(table) == (
        "|  | Wet | Dry |\n| --- | --- | --- |\n| Hemp \\| jute |  | `coil` it |\n"
    )


def test_a_table_without_a_header_row_gets_an_empty_one() -> None:
    table = Table(header=None, rows=((cell("Hemp"), cell("Swells")),))

    assert body_of(table) == "|  |  |\n| --- | --- |\n| Hemp | Swells |\n"


def test_a_code_block_that_holds_a_fence_gets_a_longer_fence() -> None:
    assert body_of(CodeBlock(lines=("```", "nested", "```"))) == (
        "````text\n```\nnested\n```\n````\n"
    )


def test_a_slug_is_proposed_from_a_title() -> None:
    assert propose_slug("Naming the Boat") == "naming-the-boat"
    assert propose_slug("The Costs: Debt, Rot & Blowout") == "the-costs-debt-rot-blowout"
    assert propose_slug("Why an AI Can't Grade Its Own Code") == (
        "why-an-ai-cant-grade-its-own-code"
    )
    assert propose_slug("  Café  Déjà Vu  ") == "cafe-deja-vu"


def test_a_chapter_file_has_frontmatter_in_a_fixed_order_and_then_the_body(
    fixture_library_root: Path,
) -> None:
    section = make_section(text_block(Role.BODY, "Choose a sheet with no creases."))

    [draft] = draft_chapters(mirrored_book(fixture_library_root), [section])

    assert draft.file_name == "01-folding-the-hull.md"
    assert draft.chapter_id == "fixture-mirrored-book/folding-the-hull"
    assert draft.slug_is_proposed is False
    assert draft.text == (
        "---\n"
        "id: fixture-mirrored-book/folding-the-hull\n"
        "resource: fixture-mirrored-book\n"
        "title: Folding the Hull\n"
        'part: "Part One: Paper"\n'
        "order: 1\n"
        'section_label: "§01"\n'
        "language: en\n"
        "edition: v1.0.0\n"
        "source:\n"
        "  repository: fixture-author/fixture-mirrored-book\n"
        "  revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  path: Paper-Boat-Engineering-v1.0.0.pdf\n"
        "  pages:\n"
        "    first: 3\n"
        "    last: 4\n"
        "extraction_status: machine-extracted\n"
        "---\n"
        "\n"
        "# Folding the Hull\n"
        "\n"
        "Choose a sheet with no creases.\n"
    )


def test_frontmatter_values_that_yaml_would_misread_are_quoted_and_load_back(
    fixture_library_root: Path, tmp_path: Path
) -> None:
    book = mirrored_book(fixture_library_root)
    assert book.pinned_source is not None
    # A commit of digits alone would load as a number, and a title with a colon as a mapping.
    all_digits = "1234567890" * 4
    book = replace(book, pinned_source=replace(book.pinned_source, commit=all_digits))
    section = make_section(
        text_block(Role.BODY, "Text."),
        title='Choosing a Pond: "Still" or Gusty',
        label="No",
        first_page=11,
        last_page=12,
    )

    [draft] = draft_chapters(book, [section])
    path = tmp_path / draft.file_name
    path.write_text(draft.text, encoding="utf-8")
    chapter, body = load_chapter(path)

    assert f'  revision: "{all_digits}"\n' in draft.text
    assert chapter == Chapter(
        id="fixture-mirrored-book/choosing-a-pond-still-or-gusty",
        resource="fixture-mirrored-book",
        title='Choosing a Pond: "Still" or Gusty',
        part=UNASSIGNED_PART,
        order=1,
        section_label="No",
        language="en",
        edition="v1.0.0",
        source=ChapterSource(
            repository="fixture-author/fixture-mirrored-book",
            revision=all_digits,
            path="Paper-Boat-Engineering-v1.0.0.pdf",
            pages=PageRange(first=11, last=12),
        ),
        extraction_status=ExtractionStatus.MACHINE_EXTRACTED,
        errata=(),
    )
    assert body == '# Choosing a Pond: "Still" or Gusty\n\nText.\n'


def test_slugs_come_from_the_profile_and_order_from_the_position_in_the_source(
    fixture_library_root: Path,
) -> None:
    sections = [
        make_section(title="Choosing a Pond", label="§01"),
        make_section(title="Naming the Boat", label="§02"),
        make_section(title="Folding the Hull", label="§03"),
    ]

    drafts = draft_chapters(mirrored_book(fixture_library_root), sections)

    assert [
        (draft.file_name, draft.chapter_id, draft.order, draft.slug_is_proposed) for draft in drafts
    ] == [
        ("01-choosing-a-pond.md", "fixture-mirrored-book/choosing-a-pond", 1, False),
        ("02-naming-the-boat.md", "fixture-mirrored-book/naming-the-boat", 2, True),
        ("03-folding-the-hull.md", "fixture-mirrored-book/folding-the-hull", 3, False),
    ]
    assert "\norder: 3\n" in drafts[2].text
    assert f"\npart: {UNASSIGNED_PART}\n" in drafts[1].text
    assert '\npart: "Part One: Paper"\n' in drafts[0].text
