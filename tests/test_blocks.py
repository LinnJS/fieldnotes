"""Spans of extracted text become sections of headings, paragraphs, quotes, tables, and code."""

from kb.blocks import CodeBlock, Run, Section, Table, TextBlock, build_sections, section_text
from kb.catalog import ExtractionProfile, Role, RoleRule
from kb.pdf_spans import Span

MARGIN = 40.0
QUOTE_INDENT = 100.0

LABEL = 24.0
TITLE = 26.7
LEDE = 15.3
HEADING = 17.3
BODY = 14.0
SMALL = 13.3
TABLE_HEADER = 11.3
TABLE_CELL = 12.7
CODE = 12.0


def rule(
    role: Role, size: float, *, min_indent: float | None = None, max_indent: float | None = None
) -> RoleRule:
    return RoleRule(role=role, font_size=size, min_indent=min_indent, max_indent=max_indent)


def make_profile(*, excluded_pages: tuple[int, ...] = ()) -> ExtractionProfile:
    return ExtractionProfile(
        roles=(
            rule(Role.SECTION_LABEL, LABEL),
            rule(Role.SECTION_TITLE, TITLE),
            rule(Role.LEDE, LEDE),
            rule(Role.HEADING, HEADING),
            rule(Role.BODY, BODY),
            rule(Role.KICKER, SMALL, max_indent=80.0),
            rule(Role.QUOTE, SMALL, min_indent=80.0),
            rule(Role.TABLE_HEADER, TABLE_HEADER),
            rule(Role.TABLE_CELL, TABLE_CELL),
            rule(Role.CODE, CODE),
        ),
        section_start=r"^§\d{2}$",
        excluded_pages=excluded_pages,
        sections=(),
        accepted_differences=(),
        accepted_reorders=(),
    )


def span(
    text: str,
    size: float,
    y: float,
    *,
    x: float = MARGIN,
    page: int = 1,
    link: str | None = None,
) -> Span:
    return Span(page=page, x=x, y=y, size=size, text=text, link=link)


def opening(
    page: int = 1, y: float = 700.0, label: str = "§01", title: str = "Knots"
) -> list[Span]:
    """Return the label and title spans that open a section, which share one baseline."""
    return [
        span(label, LABEL, y, page=page),
        span(f" {title}", TITLE, y, x=75.0, page=page),
    ]


def only_section(spans: list[Span], profile: ExtractionProfile | None = None) -> Section:
    extraction = build_sections(spans, profile or make_profile())
    assert extraction.unmatched == ()
    [section] = extraction.sections
    return section


def body(text: str) -> TextBlock:
    return TextBlock(role=Role.BODY, runs=(Run(text),))


def test_heading_spans_become_a_heading_and_the_body_below_becomes_one_paragraph() -> None:
    section = only_section(
        [
            *opening(),
            span("Tie the bowline", HEADING, 650.0),
            span("Make a loop near the end of the rope.", BODY, 625.0),
        ]
    )

    assert section.blocks == (
        TextBlock(role=Role.HEADING, runs=(Run("Tie the bowline"),)),
        body("Make a loop near the end of the rope."),
    )


def test_three_wrapped_body_lines_become_one_paragraph_with_single_spaces() -> None:
    section = only_section(
        [
            *opening(),
            span("Make a loop near the end ", BODY, 650.0),
            span("of the rope, pass the end", BODY, 631.0),
            span("  through it, and pull tight.", BODY, 612.0),
        ]
    )

    assert section.blocks == (
        body("Make a loop near the end of the rope, pass the end through it, and pull tight."),
    )


def test_a_larger_gap_between_body_lines_starts_a_new_paragraph() -> None:
    section = only_section(
        [
            *opening(),
            span("The first paragraph wraps", BODY, 650.0),
            span("onto a second line.", BODY, 631.0),
            span("The second paragraph is short.", BODY, 603.0),
        ]
    )

    assert section.blocks == (
        body("The first paragraph wraps onto a second line."),
        body("The second paragraph is short."),
    )


def test_a_bold_span_in_the_middle_of_a_line_stays_in_reading_position() -> None:
    # The bold run is a span of its own. It is listed last here, as a renderer that draws bold
    # text in a second pass would emit it, and its x position puts it back in the middle.
    section = only_section(
        [
            *opening(),
            span("Pull the ", BODY, 650.0),
            span(" until the knot seats.", BODY, 650.0, x=190.0),
            span("standing part", BODY, 650.0, x=96.0),
        ]
    )

    assert section.blocks == (body("Pull the standing part until the knot seats."),)


def test_a_section_title_that_wraps_to_a_second_line_becomes_one_title() -> None:
    section = only_section(
        [
            span("§04", LABEL, 700.0),
            span(" Splicing Three Strands", TITLE, 700.0, x=75.0),
            span("Without a Fid", TITLE, 668.0),
            span("A splice keeps most of the strength of the rope.", LEDE, 630.0),
        ]
    )

    assert section.label == "§04"
    assert section.title == "Splicing Three Strands Without a Fid"
    assert section.blocks == (
        TextBlock(role=Role.LEDE, runs=(Run("A splice keeps most of the strength of the rope."),)),
    )


def test_one_size_at_two_indents_gets_the_two_roles_the_profile_assigns() -> None:
    section = only_section(
        [
            *opening(),
            span("A knot is a decision.", SMALL, 672.0),
            span("Measure twice and tie once.", BODY, 640.0),
            span("A rope remembers every knot.", SMALL, 600.0, x=QUOTE_INDENT),
        ]
    )

    assert section.blocks == (
        TextBlock(role=Role.KICKER, runs=(Run("A knot is a decision."),)),
        body("Measure twice and tie once."),
        TextBlock(role=Role.QUOTE, runs=(Run("A rope remembers every knot."),)),
    )


def test_the_indent_of_a_line_is_its_left_edge_and_not_the_position_of_each_word() -> None:
    # A renderer may emit a kicker word by word. Only the first word sits at the body margin.
    section = only_section(
        [
            *opening(),
            span("A", SMALL, 672.0),
            span(" ", SMALL, 672.0, x=48.0),
            span("knot", SMALL, 672.0, x=51.0),
            span(" ", SMALL, 672.0, x=90.0),
            span("holds", SMALL, 672.0, x=93.0),
        ]
    )

    assert section.blocks == (TextBlock(role=Role.KICKER, runs=(Run("A knot holds"),)),)


def test_the_first_matching_rule_wins_when_two_rules_fit_a_span() -> None:
    profile = make_profile()
    # The kicker and quote rules both include an indent of exactly 80 points.
    section = only_section([*opening(), span("On the boundary.", SMALL, 672.0, x=80.0)], profile)

    assert section.blocks == (TextBlock(role=Role.KICKER, runs=(Run("On the boundary."),)),)


def test_a_font_size_is_matched_with_a_small_tolerance() -> None:
    section = only_section(
        [
            span("§01", 24.0, 700.0),
            span(" Knots", 26.66, 700.0, x=75.0),
            span("Reported as 13.33 and recorded as 13.3.", 13.33, 672.0),
        ]
    )

    assert section.title == "Knots"
    assert section.blocks == (
        TextBlock(role=Role.KICKER, runs=(Run("Reported as 13.33 and recorded as 13.3."),)),
    )


def test_a_header_row_and_two_cell_rows_become_a_table_with_three_columns() -> None:
    section = only_section(
        [
            *opening(),
            span("Knot", TABLE_HEADER, 650.0),
            span(" Use", TABLE_HEADER, 650.0, x=150.0),
            span(" Strength", TABLE_HEADER, 650.0, x=280.0),
            span("Bowline", TABLE_CELL, 620.0),
            span(" Rescue loop", TABLE_CELL, 620.0, x=150.0),
            span(" Two thirds", TABLE_CELL, 620.0, x=280.0),
            span("Sheet bend", TABLE_CELL, 590.0),
            span(" Joining ropes", TABLE_CELL, 590.0, x=150.0),
            span(" Half", TABLE_CELL, 590.0, x=280.0),
        ]
    )

    assert section.blocks == (
        Table(
            header=((Run("Knot"),), (Run("Use"),), (Run("Strength"),)),
            rows=(
                ((Run("Bowline"),), (Run("Rescue loop"),), (Run("Two thirds"),)),
                ((Run("Sheet bend"),), (Run("Joining ropes"),), (Run("Half"),)),
            ),
        ),
    )


def test_a_table_cell_that_wraps_stays_in_its_row_and_column() -> None:
    section = only_section(
        [
            *opening(),
            span("Knot", TABLE_HEADER, 650.0),
            span(" Use", TABLE_HEADER, 650.0, x=150.0),
            span("Double sheet", TABLE_CELL, 620.0),
            span("bend", TABLE_CELL, 603.0),
            span(" Joining ropes of", TABLE_CELL, 620.0, x=150.0),
            span("unequal size", TABLE_CELL, 603.0, x=150.0),
            span("Reef knot", TABLE_CELL, 572.0),
            span(" Tying a parcel", TABLE_CELL, 572.0, x=150.0),
        ]
    )

    assert section.blocks == (
        Table(
            header=((Run("Knot"),), (Run("Use"),)),
            rows=(
                ((Run("Double sheet bend"),), (Run("Joining ropes of unequal size"),)),
                ((Run("Reef knot"),), (Run("Tying a parcel"),)),
            ),
        ),
    )


def test_a_table_whose_first_header_cell_is_empty_keeps_its_first_column() -> None:
    section = only_section(
        [
            *opening(),
            span("Wet", TABLE_HEADER, 650.0, x=150.0),
            span(" Dry", TABLE_HEADER, 650.0, x=280.0),
            span("Hemp", TABLE_CELL, 620.0),
            span(" Swells", TABLE_CELL, 620.0, x=150.0),
            span(" Holds", TABLE_CELL, 620.0, x=280.0),
        ]
    )

    assert section.blocks == (
        Table(
            header=((), (Run("Wet"),), (Run("Dry"),)),
            rows=(((Run("Hemp"),), (Run("Swells"),), (Run("Holds"),)),),
        ),
    )


def test_lines_at_the_code_size_become_one_code_block_with_line_breaks_kept() -> None:
    section = only_section(
        [
            *opening(),
            span("for strand in rope:", CODE, 650.0),
            span("    tuck(strand)", CODE, 633.0),
            span("trim()", CODE, 616.0),
        ]
    )

    assert section.blocks == (
        CodeBlock(lines=("for strand in rope:", "    tuck(strand)", "trim()")),
    )


def test_a_wider_gap_inside_a_code_block_is_kept_as_one_empty_line() -> None:
    section = only_section(
        [
            *opening(),
            span("coil()", CODE, 650.0),
            span("stow()", CODE, 616.0),
        ]
    )

    assert section.blocks == (CodeBlock(lines=("coil()", "", "stow()")),)


def test_a_code_size_span_inside_a_body_line_is_inline_code() -> None:
    section = only_section(
        [
            *opening(),
            span("Run ", BODY, 650.0),
            span("coil --left", CODE, 650.0, x=70.0),
            span("  before stowing the rope.", BODY, 650.0, x=160.0),
        ]
    )

    assert section.blocks == (
        TextBlock(
            role=Role.BODY,
            runs=(Run("Run "), Run("coil --left", code=True), Run(" before stowing the rope.")),
        ),
    )


def test_a_linked_span_keeps_its_target_and_joins_across_a_wrapped_line() -> None:
    target = "https://example.invalid/knots"
    section = only_section(
        [
            *opening(),
            span("Read ", BODY, 650.0),
            span("the knot ", BODY, 650.0, x=75.0, link=target),
            span("index", BODY, 631.0, link=target),
            span(" first.", BODY, 631.0, x=75.0),
        ]
    )

    assert section.blocks == (
        TextBlock(
            role=Role.BODY,
            runs=(Run("Read "), Run("the knot index", link=target), Run(" first.")),
        ),
    )


def test_a_line_that_ends_in_a_hyphen_joins_the_next_line_without_a_space() -> None:
    section = only_section(
        [
            *opening(),
            span("A splice beats every anti-", BODY, 650.0),
            span("slip knot there is.", BODY, 631.0),
        ]
    )

    assert section.blocks == (body("A splice beats every anti-slip knot there is."),)


def test_a_paragraph_cut_by_a_page_break_is_joined_and_a_finished_one_is_not() -> None:
    section = only_section(
        [
            *opening(),
            span("Whip the end of the rope,", BODY, 80.0),
            span("and seal it with wax.", BODY, 760.0, page=2),
            span("Then coil it.", BODY, 741.0, page=2),
            span("Stow the coil dry.", BODY, 60.0, page=2),
            span("A new paragraph opens the next page.", BODY, 760.0, page=3),
        ]
    )

    assert section.blocks == (
        body("Whip the end of the rope, and seal it with wax. Then coil it."),
        body("Stow the coil dry."),
        body("A new paragraph opens the next page."),
    )


def test_a_section_that_starts_and_ends_mid_page_gets_its_first_and_last_page() -> None:
    extraction = build_sections(
        [
            *opening(page=3, y=700.0, label="§01", title="Knots"),
            span("The first section runs onto the next page.", BODY, 650.0, page=3),
            span("It ends above the middle of the page.", BODY, 700.0, page=4),
            *opening(page=4, y=400.0, label="§02", title="Splices"),
            span("The second section starts mid-page.", BODY, 350.0, page=4),
            span("It ends mid-page two pages on.", BODY, 500.0, page=6),
            *opening(page=7, y=700.0, label="§03", title="Whippings"),
            span("The third section fits on one page.", BODY, 650.0, page=7),
        ],
        make_profile(),
    )

    assert [
        (section.label, section.title, section.first_page, section.last_page)
        for section in extraction.sections
    ] == [("§01", "Knots", 3, 4), ("§02", "Splices", 4, 6), ("§03", "Whippings", 7, 7)]
    assert extraction.sections[0].blocks == (
        body("The first section runs onto the next page."),
        body("It ends above the middle of the page."),
    )


def test_pages_listed_as_left_out_contribute_no_blocks() -> None:
    spans = [
        span("§09", LABEL, 700.0, page=1),
        span(" A Contents Entry", TITLE, 700.0, x=75.0, page=1),
        span("Cover text at the body size.", BODY, 600.0, page=1),
        *opening(page=2),
        span("The only kept paragraph.", BODY, 650.0, page=2),
        span("Back cover text at the body size.", BODY, 650.0, page=3),
    ]

    extraction = build_sections(spans, make_profile(excluded_pages=(1, 3)))

    assert extraction.unmatched == ()
    [section] = extraction.sections
    assert (section.label, section.first_page, section.last_page) == ("§01", 2, 2)
    assert section.blocks == (body("The only kept paragraph."),)


def test_a_span_whose_size_matches_no_rule_is_reported_and_left_out() -> None:
    footer = span("Page 7 of 30", 9.0, 30.0)

    extraction = build_sections(
        [*opening(), span("A paragraph.", BODY, 650.0), footer], make_profile()
    )

    assert extraction.unmatched == (footer,)
    assert extraction.sections[0].blocks == (body("A paragraph."),)


def test_a_label_size_span_that_is_not_a_section_start_is_reported() -> None:
    stray = span("Appendix", LABEL, 500.0)

    extraction = build_sections(
        [*opening(), span("A paragraph.", BODY, 650.0), stray], make_profile()
    )

    assert extraction.unmatched == (stray,)
    assert len(extraction.sections) == 1


def test_text_before_the_first_section_is_reported() -> None:
    preface = span("A note that belongs to no section.", BODY, 760.0)

    extraction = build_sections([preface, *opening()], make_profile())

    assert extraction.unmatched == (preface,)
    assert extraction.sections[0].blocks == ()


def test_section_text_is_the_title_and_every_block_in_reading_order() -> None:
    section = only_section(
        [
            *opening(),
            span("Tie the bowline", HEADING, 650.0),
            span("Run ", BODY, 625.0),
            span("coil", CODE, 625.0, x=70.0),
            span(" first.", BODY, 625.0, x=100.0),
            span("Knot", TABLE_HEADER, 590.0),
            span(" Use", TABLE_HEADER, 590.0, x=150.0),
            span("Bowline", TABLE_CELL, 560.0),
            span(" Rescue loop", TABLE_CELL, 560.0, x=150.0),
            span("trim()", CODE, 520.0),
        ]
    )

    assert section_text(section).split("\n") == [
        "Knots",
        "Tie the bowline",
        "Run coil first.",
        "Knot Use",
        "Bowline Rescue loop",
        "trim()",
    ]
