"""The ingestion command turns a pinned PDF into chapter drafts and never overwrites a chapter."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import ingest
import pytest
from kb.blocks import CodeBlock, Extraction, Run, Table, TextBlock, build_sections
from kb.catalog import Role, load_resource
from kb.checks import run_checks
from kb.frontmatter import ExtractionStatus, load_chapter, split_frontmatter
from kb.pdf_spans import clean_text, read_pdf

MIRRORED = "fixture-mirrored-book"
REFERENCE = "fixture-reference-book"

BOOK = Path("books") / MIRRORED
METADATA = BOOK / "metadata.yaml"
SOURCE = BOOK / "source" / "Paper-Boat-Engineering-v1.0.0.pdf"
CHAPTERS = BOOK / "chapters"
DRAFTS = Path("build") / "ingest" / MIRRORED

HULL = "01-folding-the-hull.md"
POND = "02-choosing-a-pond.md"
SUNK = "03-recovering-a-sunk-boat.md"

NOTICE = "Test fixture. This text is invented for automated tests and comes from no published book."


def run(root: Path, *flags: str, book: str = MIRRORED) -> int:
    return ingest.main(["--book", book, "--root", str(root), *flags])


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def file_bytes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.glob("*.md"))}


def extract(root: Path, pdf: Path) -> Extraction:
    profile = load_resource(root, MIRRORED).extraction_profile
    assert profile is not None
    return build_sections(read_pdf(pdf).spans, profile)


def install_second_edition(root: Path, pdf: Path) -> None:
    """Replace the book's source with the later edition and record its digest and back cover."""
    old_digest = hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()
    shutil.copyfile(pdf, root / SOURCE)
    new_digest = hashlib.sha256((root / SOURCE).read_bytes()).hexdigest()
    replace_in(root / METADATA, f"sha256: {old_digest}", f"sha256: {new_digest}")
    # The inserted section adds a page, so the back cover moves from page 7 to page 8.
    replace_in(root / METADATA, "    - 2\n    - 7\n", "    - 2\n    - 8\n")


def test_the_fixture_pdf_yields_the_sections_written_in_the_typst_source(
    fixture_library_root: Path,
) -> None:
    extraction = extract(fixture_library_root, fixture_library_root / SOURCE)

    assert extraction.unmatched == ()
    assert [
        (section.label, section.title, section.first_page, section.last_page)
        for section in extraction.sections
    ] == [
        ("§01", "Folding the Hull", 3, 4),
        ("§02", "Choosing a Pond", 4, 5),
        ("§03", "Recovering a Sunk Boat", 6, 6),
    ]


def test_the_fixture_pdf_yields_each_kind_of_block(fixture_library_root: Path) -> None:
    hull, pond, sunk = extract(fixture_library_root, fixture_library_root / SOURCE).sections

    assert hull.blocks == (
        TextBlock(Role.KICKER, (Run(NOTICE),)),
        TextBlock(
            Role.LEDE,
            (Run("A paper boat begins as a rectangle and ends as a promise that it will float."),),
        ),
        TextBlock(Role.HEADING, (Run("Start with a dry sheet"),)),
        TextBlock(
            Role.BODY,
            (
                Run(
                    "Choose a sheet with no creases. A damp sheet folds into a soft hull, and a "
                    "soft hull takes on water before it leaves the bank."
                ),
            ),
        ),
        TextBlock(Role.HEADING, (Run("Make three folds and stop"),)),
        # The source cuts this paragraph at a page break and sets two of its words in bold.
        TextBlock(
            Role.BODY,
            (
                Run(
                    "Fold the sheet in half, fold the corners to the center, and fold the brim "
                    "up on both sides. A fourth fold adds weight and no strength."
                ),
            ),
        ),
    )
    assert pond.blocks[3:] == (
        Table(
            header=((Run("Pond"),), (Run("Depth"),), (Run("Wind"),)),
            rows=(
                ((Run("Garden basin"),), (Run("Two spans"),), (Run("Still"),)),
                ((Run("Mill pond"),), (Run("Nine spans"),), (Run("Gusty"),)),
                ((Run("Rain barrel"),), (Run("One span"),), (Run("None"),)),
            ),
        ),
        TextBlock(Role.HEADING, (Run("A launch checklist"),)),
        TextBlock(Role.BODY, (Run("Read the checklist aloud before each launch."),)),
        CodeBlock(("check hull dry", "check wind below gusty", "launch from the lee bank")),
    )
    assert sunk.blocks[4] == TextBlock(
        Role.QUOTE,
        (
            Run(
                "A boat that dries flat will fold again. "
                "A boat that dries crumpled is a paper ball."
            ),
        ),
    )
    assert sunk.blocks[6] == TextBlock(
        Role.BODY,
        (
            Run("Refold along the old creases as described in "),
            Run("Folding the Hull", link="01-folding-the-hull.md"),
            Run(". Old creases remember their shape, and new ones weaken the sheet."),
        ),
    )


def test_the_committed_fixture_pdf_matches_a_fresh_compilation_of_its_source(
    fixture_library_root: Path, sample_book_pdf: Path
) -> None:
    committed = extract(fixture_library_root, fixture_library_root / SOURCE)
    fresh = extract(fixture_library_root, sample_book_pdf)

    assert fresh == committed
    assert read_pdf(sample_book_pdf).page_count == 7


def test_typesetting_characters_are_replaced_with_the_text_they_stand_for() -> None:
    assert (
        clean_text("e\ufb03cient \ufb01t, co\u00adoperate\nnow") == "efficient fit, cooperate now"
    )


def test_a_run_writes_drafts_and_prints_a_summary(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(library_copy)

    output = capsys.readouterr()
    assert code == 0
    assert output.err == ""
    assert output.out.splitlines() == [
        "ingest: fixture-mirrored-book, edition v1.0.0, language en",
        "Source: books/fixture-mirrored-book/source/Paper-Boat-Engineering-v1.0.0.pdf",
        "Pages: 7. Left out: 1, 2, 7.",
        "Sections found: 3",
        "  01  §01  Folding the Hull  pages 3-4  folding-the-hull",
        "  02  §02  Choosing a Pond  pages 4-5  choosing-a-pond",
        "  03  §03  Recovering a Sunk Boat  pages 6-6  recovering-a-sunk-boat",
        "Unmatched spans: 0",
        "Drafts written: build/ingest/fixture-mirrored-book/",
    ]
    assert sorted(file_bytes(library_copy / DRAFTS)) == [HULL, POND, SUNK]


def test_a_draft_is_machine_extracted_and_carries_the_source_page_range(library_copy: Path) -> None:
    run(library_copy)

    chapter, body = load_chapter(library_copy / DRAFTS / POND)

    assert chapter.id == "fixture-mirrored-book/choosing-a-pond"
    assert chapter.order == 2
    assert chapter.section_label == "§02"
    assert chapter.part == "Part One: Paper"
    assert (chapter.source.pages.first, chapter.source.pages.last) == (4, 5)
    assert chapter.extraction_status is ExtractionStatus.MACHINE_EXTRACTED
    assert chapter.errata == ()
    assert body.startswith(f"# Choosing a Pond\n\n*{NOTICE}*\n\nThe pond decides more than")
    assert "\n## Three ponds compared\n\n| Pond | Depth | Wind |\n| --- | --- | --- |\n" in body
    assert body.endswith(
        "```text\ncheck hull dry\ncheck wind below gusty\nlaunch from the lee bank\n```\n"
    )


def test_the_fixture_chapters_are_the_reviewed_drafts_of_the_fixture_pdf(
    library_copy: Path,
) -> None:
    run(library_copy)

    drafts = file_bytes(library_copy / DRAFTS)
    chapters = file_bytes(library_copy / CHAPTERS)

    # The first chapter is an untouched draft. The other two differ from their drafts only in
    # the frontmatter: one records an erratum and one was marked as reviewed.
    assert chapters[HULL] == drafts[HULL]
    for name in (POND, SUNK):
        assert chapters[name] != drafts[name]
        assert (
            split_frontmatter(chapters[name].decode("utf-8"))[1]
            == split_frontmatter(drafts[name].decode("utf-8"))[1]
        )


def test_running_ingestion_twice_produces_byte_identical_drafts(library_copy: Path) -> None:
    run(library_copy)
    first = file_bytes(library_copy / DRAFTS)
    (library_copy / DRAFTS / "09-left-by-an-earlier-run.md").write_text(
        "Stale.\n", encoding="utf-8"
    )

    run(library_copy)

    assert file_bytes(library_copy / DRAFTS) == first
    assert len(first) == 3


def test_chapters_written_from_the_drafts_pass_the_fidelity_check(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.rmtree(library_copy / CHAPTERS)

    assert run(library_copy, "--write") == 0
    capsys.readouterr()
    code = run(library_copy, "--check")

    output = capsys.readouterr()
    assert code == 0
    assert output.out.splitlines() == [
        "ingest: fixture-mirrored-book, edition v1.0.0, language en",
        "Source: books/fixture-mirrored-book/source/Paper-Boat-Engineering-v1.0.0.pdf",
        "  pass  fixture-mirrored-book/folding-the-hull  similarity 1.000",
        "  pass  fixture-mirrored-book/choosing-a-pond  similarity 1.000",
        "  pass  fixture-mirrored-book/recovering-a-sunk-boat  similarity 1.000",
        "Accepted differences: 0",
        "Chapters checked: 3. Failed: 0.",
    ]
    # A draft carries no erratum and no review status, so the committed chapter index no longer
    # matches the chapters, and that finding is not about fidelity.
    assert [finding for finding in run_checks(library_copy) if finding.rule != "index-stale"] == []


def test_write_creates_missing_chapters_and_leaves_an_existing_file_unchanged(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chapters = library_copy / CHAPTERS
    (chapters / HULL).unlink()
    replace_in(
        chapters / POND, "| Mill pond | Nine spans | Gusty |", "| Mill pond | Ten spans | Gusty |"
    )
    before = file_bytes(chapters)

    code = run(library_copy, "--write")

    output = capsys.readouterr().out
    after = file_bytes(chapters)
    assert code == 0
    assert after[HULL] == (library_copy / DRAFTS / HULL).read_bytes()
    assert {name: after[name] for name in (POND, SUNK)} == before
    assert "Created: books/fixture-mirrored-book/chapters/01-folding-the-hull.md" in output
    assert (
        "Differs from its draft and was left as it is: "
        "books/fixture-mirrored-book/chapters/02-choosing-a-pond.md"
    ) in output
    assert "--- books/fixture-mirrored-book/chapters/02-choosing-a-pond.md" in output
    assert "+++ build/ingest/fixture-mirrored-book/02-choosing-a-pond.md" in output
    assert "-| Mill pond | Ten spans | Gusty |" in output
    assert "+| Mill pond | Nine spans | Gusty |" in output


def test_write_reports_a_chapter_that_equals_its_draft_as_unchanged(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = file_bytes(library_copy / CHAPTERS)

    code = run(library_copy, "--write")

    output = capsys.readouterr().out
    assert code == 0
    assert file_bytes(library_copy / CHAPTERS) == before
    assert "Unchanged: books/fixture-mirrored-book/chapters/01-folding-the-hull.md" in output
    assert "Created:" not in output


def test_write_is_allowed_for_an_eligible_book(library_copy: Path) -> None:
    replace_in(library_copy / METADATA, "mirror_status: mirrored", "mirror_status: eligible")
    shutil.rmtree(library_copy / CHAPTERS)

    assert run(library_copy, "--write") == 0
    assert sorted(file_bytes(library_copy / CHAPTERS)) == [HULL, POND, SUNK]


def test_an_inserted_section_keeps_the_existing_ids_and_shifts_only_their_order(
    library_copy: Path, second_edition_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install_second_edition(library_copy, second_edition_pdf)

    code = run(library_copy)

    output = capsys.readouterr().out
    drafts = library_copy / DRAFTS
    assert code == 0
    assert [
        (path.name, load_chapter(path)[0].id, load_chapter(path)[0].order)
        for path in sorted(drafts.glob("*.md"))
    ] == [
        ("01-folding-the-hull.md", "fixture-mirrored-book/folding-the-hull", 1),
        ("02-choosing-a-pond.md", "fixture-mirrored-book/choosing-a-pond", 2),
        ("03-naming-the-boat.md", "fixture-mirrored-book/naming-the-boat", 3),
        ("04-recovering-a-sunk-boat.md", "fixture-mirrored-book/recovering-a-sunk-boat", 4),
    ]
    assert "  03  §03  Naming the Boat  pages 6-6  naming-the-boat (proposed slug)" in output
    assert "  04  §04  Recovering a Sunk Boat  pages 7-7  recovering-a-sunk-boat" in output
    assert "Proposed slugs: 1" in output
    assert "  naming-the-boat  for  Naming the Boat" in output
    assert output.count("(proposed slug)") == 1


def test_write_does_not_record_a_proposed_slug_or_duplicate_a_renumbered_chapter(
    library_copy: Path, second_edition_pdf: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install_second_edition(library_copy, second_edition_pdf)
    before = file_bytes(library_copy / CHAPTERS)

    code = run(library_copy, "--write")

    output = capsys.readouterr()
    assert code == 1
    assert file_bytes(library_copy / CHAPTERS) == before
    assert "Not written, because its slug is only proposed: 03-naming-the-boat.md" in output.out
    # The last chapter exists under its old number, so it gets a diff and not a second file.
    assert "--- books/fixture-mirrored-book/chapters/03-recovering-a-sunk-boat.md" in output.out
    assert "+++ build/ingest/fixture-mirrored-book/04-recovering-a-sunk-boat.md" in output.out
    assert "\n-order: 3\n" in output.out
    assert "\n+order: 4\n" in output.out
    assert "extraction_profile.sections" in output.err


@pytest.mark.parametrize("flags", [(), ("--write",), ("--check",)])
def test_a_book_the_gate_refuses_is_refused_before_any_file_is_read(
    library_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    def must_not_run(*arguments: object, **options: object) -> None:
        raise AssertionError("The source was touched before the gate refused the book.")

    replace_in(library_copy / METADATA, "redistribution: allowed", "redistribution: unclear")
    monkeypatch.setattr("kb.ingest.verify_source", must_not_run)
    monkeypatch.setattr("kb.ingest.read_pdf", must_not_run)
    monkeypatch.setattr("ingest.load_chapters", must_not_run)

    code = run(library_copy, *flags)

    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    assert (
        "The record says redistribution is unclear and adaptation is allowed. Both must be allowed."
    ) in output.err
    assert not (library_copy / "build").exists()


def test_a_reference_only_book_is_refused_with_the_gate_reason(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(library_copy, book=REFERENCE)

    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    assert "fixture-reference-book" in output.err
    assert "No license terms were found at any location checked." in output.err
    assert "\n  fix: " in output.err
    assert not (library_copy / "build").exists()


@pytest.mark.parametrize("flags", [(), ("--write",)])
def test_a_source_with_another_digest_aborts_before_any_write_and_prints_both_digests(
    library_copy: Path, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...]
) -> None:
    recorded = hashlib.sha256((library_copy / SOURCE).read_bytes()).hexdigest()
    with (library_copy / SOURCE).open("ab") as source:
        source.write(b"\n% one more line\n")
    actual = hashlib.sha256((library_copy / SOURCE).read_bytes()).hexdigest()
    (library_copy / CHAPTERS / HULL).unlink()

    code = run(library_copy, *flags)

    output = capsys.readouterr()
    assert code == 1
    assert actual != recorded
    assert recorded in output.err
    assert actual in output.err
    assert not (library_copy / "build").exists()
    assert not (library_copy / CHAPTERS / HULL).exists()


def test_text_that_fits_no_rule_is_printed_with_its_page_and_text(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # With the back cover no longer left out, its two lines have sizes that no rule names.
    replace_in(library_copy / METADATA, "    - 2\n    - 7\n", "    - 2\n")

    code = run(library_copy)

    output = capsys.readouterr().out
    assert code == 0
    assert "Unmatched spans: 2\n" in output
    assert "  page 7, size 19.0, indent 97.8: 'Paper Boat Engineering'\n" in output
    assert (
        "  page 7, size 10.0, indent 103.7: 'A test fixture. Every word in it is invented.'\n"
    ) in output
    assert "extraction_profile.roles" in output


def test_check_fails_and_names_a_chapter_that_was_reworded(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    replace_in(
        library_copy / CHAPTERS / SUNK,
        "Every boat sinks once, and the second launch is the one that teaches.",
        "All boats sink, and you learn from launching again.",
    )

    code = run(library_copy, "--check")

    output = capsys.readouterr()
    assert code == 1
    assert "  pass  fixture-mirrored-book/folding-the-hull  similarity 1.000\n" in output.out
    assert "  FAIL  fixture-mirrored-book/recovering-a-sunk-boat  similarity " in output.out
    assert "Words only in the chapter: All, boats, sink, you, learn, from, launching, again." in (
        output.out
    )
    assert "Chapters checked: 3. Failed: 1.\n" in output.out
    assert not (library_copy / "build").exists()


def test_check_prints_the_accepted_differences(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    replace_in(
        library_copy / CHAPTERS / POND,
        "| Rain barrel | One span |",
        "| Rain barrel | One short span |",
    )
    replace_in(
        library_copy / METADATA,
        "  accepted_differences: []\n",
        "  accepted_differences:\n"
        "    - chapter: fixture-mirrored-book/choosing-a-pond\n"
        "      words_removed: []\n"
        "      words_added: [short]\n"
        "      reason: The source page prints the word and the extraction drops it.\n",
    )

    code = run(library_copy, "--check")

    output = capsys.readouterr().out
    assert code == 0
    assert "Accepted differences: 1\n" in output
    assert (
        "  fixture-mirrored-book/choosing-a-pond  removed: none  added: short  "
        "reason: The source page prints the word and the extraction drops it.\n"
    ) in output


def test_a_book_the_catalog_does_not_list_is_an_error(
    library_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(library_copy, book="ghost-book")

    output = capsys.readouterr()
    assert code == 1
    assert "ghost-book" in output.err
    assert "catalog.yaml" in output.err


def test_the_command_runs_as_a_script(repo_root: Path, fixture_library_root: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "ingest.py"),
            "--book",
            MIRRORED,
            "--root",
            str(fixture_library_root),
            "--check",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines()[-1] == "Chapters checked: 3. Failed: 0."
    assert result.stderr == ""
