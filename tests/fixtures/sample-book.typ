// Test fixture. This book does not exist, and all of its text is invented.
//
// This file renders the source PDF of the fixture library's mirrored book. The compiled copy is
// committed at tests/fixtures/library/books/fixture-mirrored-book/source/, and a test recompiles
// this file and compares what is extracted from the two.
//
// The font sizes, the left margin, and the indent of the quote callout are the ones the book's
// extraction_profile records. Change them in both places, compile again, and update the
// SHA-256 in the book's metadata.
//
// Only the fonts embedded in the Typst compiler are used. Compile with the input edition=2 to
// get a later edition that inserts a section before the last one.

#let edition = sys.inputs.at("edition", default: "1")

#set document(title: "Paper Boat Engineering (Test Fixture)", author: "Fixture Author", date: none)
#set page(width: 380pt, height: 520pt, margin: (x: 40pt, y: 44pt))
#set text(font: "Libertinus Serif", size: 14pt, lang: "en", hyphenate: false)
#set par(leading: 0.65em, spacing: 1.4em, justify: false)

#let section(label, title) = block(below: 1.2em)[
  #text(size: 24pt)[#label]#text(size: 26.7pt)[ #title]
]
#let kicker(body) = text(size: 13.3pt, style: "italic", body)
#let lede(body) = text(size: 15.3pt, body)
#let subsection(body) = block(above: 1.6em, below: 1em, text(size: 17.3pt, body))
#let callout(body) = pad(left: 60pt, text(size: 13.3pt, body))
#let head-cell(body) = text(size: 11.3pt, weight: "bold", body)
#let cell(body) = text(size: 12.7pt, body)
#let listing(code) = raw(code, block: true)
#show raw: set text(font: "DejaVu Sans Mono", size: 12pt)
#let fixture-notice = kicker[
  Test fixture. This text is invented for automated tests and comes from no published book.
]

// Page 1: the cover.
#v(90pt)
#text(size: 34pt)[Paper Boat Engineering]

#text(size: 19pt)[A Test Fixture]

#text(size: 10pt)[Edition v1.0.0. This book does not exist.]

#pagebreak()

// Page 2: the contents.
#text(size: 29pt)[Contents]

§01 Folding the Hull

§02 Choosing a Pond

§03 Recovering a Sunk Boat

#pagebreak()

// Page 3: the first section starts at the top of a page.
#section[§01][Folding the Hull]

#fixture-notice

#lede[A paper boat begins as a rectangle and ends as a promise that it will float.]

#subsection[Start with a dry sheet]

Choose a sheet with no creases. A damp sheet folds into a soft hull, and a soft hull takes on water before it leaves the bank.

#subsection[Make three folds and stop]

Fold the sheet in half, fold the corners to the center,

#pagebreak()

// Page 4: the paragraph above continues here, and the second section starts mid-page.
and fold the brim up on both sides. A *fourth fold* adds weight and no strength.

#v(30pt)

#section[§02][Choosing a Pond]

#fixture-notice

#lede[The pond decides more than the boat does.]

#subsection[Three ponds compared]

#table(
  columns: (120pt, 100pt, 80pt),
  stroke: none,
  inset: (x: 0pt, y: 9pt),
  table.header(head-cell[Pond], head-cell[Depth], head-cell[Wind]),
  cell[Garden basin], cell[Two spans], cell[Still],
  cell[Mill pond], cell[Nine spans], cell[Gusty],
  cell[Rain barrel], cell[One span], cell[None],
)

#pagebreak()

// Page 5: the second section ends mid-page.
#subsection[A launch checklist]

Read the checklist aloud before each launch.

#listing("check hull dry\ncheck wind below gusty\nlaunch from the lee bank")

#if edition == "2" [
  #pagebreak()

  #section[§03][Naming the Boat]

  #fixture-notice

  #lede[A boat with a name is harder to leave at the bottom of a pond.]

  #subsection[Write the name in pencil]

  Ink runs when the hull gets wet, and pencil stays where it was put.
]

#pagebreak()

// The last section starts a page. Its title is too long for one line.
#section[#if edition == "2" [§04] else [§03]][Recovering a Sunk Boat]

#fixture-notice

#lede[Every boat sinks once, and the second launch is the one that teaches.]

#subsection[Lift, drain, and dry]

Lift the boat by its keel fold and never by the brim. Let it drain bow down, then dry it flat under a book.

#callout[A boat that dries flat will fold again. A boat that dries crumpled is a paper ball.]

#subsection[Fold it again]

Refold along the old creases as described in #link("01-folding-the-hull.md")[Folding the Hull]. Old creases remember their shape, and new ones weaken the sheet.

#pagebreak()

// The back cover.
#v(120pt)
#align(center, text(size: 19pt)[Paper Boat Engineering])

#align(center, text(size: 10pt)[A test fixture. Every word in it is invented.])
