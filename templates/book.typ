// Pandoc template for the Typst writer. The export command fills the variables, and the Typst
// compiler turns the result into the PDF of one mirrored book.
//
// Variables: title, subtitle, author, translator, edition, unofficial, lang, and body come from
// the book's assembled Markdown. pdf-author is a Typst string literal and cjk-font is a list of
// family names, and the export command passes both.

// The first family of each list ships inside the Typst compiler, so Latin text looks the same on
// every machine. The CJK families are tried in order after it, and Typst skips a family that is
// not installed.
#let body-fonts = ("Libertinus Serif", $for(cjk-font)$"$cjk-font$", $endfor$)
#let code-fonts = ("DejaVu Sans Mono", $for(cjk-font)$"$cjk-font$", $endfor$)
#let accent = rgb("#a34a00")
#let rule-color = luma(185)

// The document carries no date, so the same input compiles to the same file.
#set document(title: [$title$], author: $pdf-author$, date: none)
#set page(paper: "a4", margin: (x: 2.5cm, top: 2.5cm, bottom: 2.8cm), numbering: "1")
#set text(font: body-fonts, size: 11pt, lang: "$lang$")
#set par(justify: true, leading: 0.72em, spacing: 1.15em)
// The chapters are a copy, so quotation marks stay the characters the canonical files hold.
#set smartquote(enabled: false)

#set heading(numbering: "1.1")
#show heading: set text(hyphenate: false)
#show heading: set par(justify: false)
#show heading.where(level: 1): set text(size: 21pt)
#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(below: 1.3em, it)
}
#show heading.where(level: 2): set text(size: 14pt)
#show heading.where(level: 2): set block(above: 1.7em, below: 0.9em)

#show link: set text(fill: accent)

#show raw: set text(font: code-fonts, size: 8.5pt)
#show raw.where(block: true): it => block(
  width: 100%,
  fill: luma(245),
  stroke: (left: 2pt + accent),
  inset: (x: 10pt, y: 9pt),
  it,
)
#show raw.where(block: false): box.with(
  fill: luma(240),
  inset: (x: 2.5pt),
  outset: (y: 2.5pt),
  radius: 2pt,
)

#show quote.where(block: true): it => block(
  width: 100%,
  stroke: (left: 2pt + rule-color),
  inset: (left: 1em, right: 0.5em, y: 0.45em),
  it.body,
)

// Pandoc wraps each table in a centered figure. A figure does not break across pages unless it
// is told to, and a long table must.
#show figure.where(kind: table): set block(breakable: true)
#set table(
  inset: (x: 6pt, y: 5.5pt),
  stroke: (x, y) => (bottom: 0.5pt + rule-color),
)
#show table: set text(size: 9.5pt)
#show table: set par(justify: false)
#show table: set align(left)
#show table.cell.where(y: 0): strong

#page(numbering: none)[
  #set align(center)
  #set par(justify: false)
  #v(20%)
  #text(size: 28pt, weight: "bold")[$title$]
$if(subtitle)$

  #v(0.2em)
  #text(size: 15pt)[$subtitle$]
$endif$

  #v(2em)
  #text(size: 15pt)[$for(author)$$author$$sep$, $endfor$]
$if(translator)$

  #text(size: 12pt)[Translated by $translator$]
$endif$

  #v(1fr)
  #text(size: 12pt)[$edition$]

  #v(0.4em)
  #block(width: 78%, text(size: 10pt)[$unofficial$])
  #v(6%)
]

#outline(depth: 2)

$body$
