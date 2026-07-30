# `.doc`→PDF linear-text part books (`extract_inverter_catalog.py`)

Source shape: a book converted from a binary Word `.doc` to PDF. The parts
tables are a **linear text stream** — one field per line — not positioned
columns, so coordinate parsing does not apply. Sections are **named subsystems**
(逆变器/INVERTER, 接触器/CONTACTOR, 电动轮/MOTORIZED WHEEL, 交流发电机/ALTERNATOR …)
with no `NNN-NNNN` code, so assign synthetic codes (`600-00N0`) under a new
chapter. Row shape: `[NC] REF [QTY] PART-NO ZH-name EN-name`.

Each item was a validated bug — read before touching the parser.

## Detect a row by its signature, not by blank lines
Some pages separate rows with a blank line, others do not (the `.doc` export is
inconsistent). Splitting on blank lines merges whole runs of rows into one row's
name and drops every part but the first. Instead detect a row **start** by the
signature `REF [NC] QTY [PART-NO]`, and read the name up to the next row start —
scanning from *after* the consumed REF/QTY/PART-NO so a row's own QTY line is
never mistaken for the REF of a phantom row.

## Date-shaped part numbers must NOT be rejected by value
Many real catalog numbers (`20040401`, `20040502`, …) are valid `YYYYMMDD`
dates. A date filter on the part-number test silently drops those rows (they get
swallowed into the previous row's name). The only true date in the source is the
header revision date, which never sits in a REF/QTY row context — so use
**context** (a QTY line precedes the number), not the value, to keep it out.

## Quirks in the leading columns
- **NC note letter** between REF and QTY (`225 A 1 20048136`) — consume a lone
  `[A-Z]` only when a QTY or PART-NO follows, so a name word is never eaten.
- **`AR` split across two lines** (`A` then `R`) — treat the pair as `AR`.
- **`#N/A` placeholder positions** — a real listed position with no catalog
  number; keep it (empty pn) so the list matches the drawing callouts.

## Source-duplicated pages
The `.doc`→PDF export doubles the text of some table pages (the whole row block
appears twice). De-duplicate within a figure by `(REF, PART-NO)` — a numbered
position that recurs with the same number is an export artifact, not a real
second listing.

## Sections and variants
Group adjacent pages that share a subsystem title into a section. A subsystem
often has several independent **configurations**, each a drawing set + its own
`1..N` list restarting at 1 — make **each such figure its own section**
(numbered · 1, · 2 …) rather than one section with an unrelated second figure.

## Names that mix scripts
A single name line can mix CJK and Latin (`交流逆变器II AC INVERTEX II PANEL`).
Split per line: CJK chars → zh, Latin words → en.

## Binary `.doc` (not yet exported to PDF)
If you get the raw `.doc`, read the OLE2 file with `olefile` (LibreOffice fails
on these here): parse the FIB piece table in `WordDocument` (`fcClx/lcbClx` →
CLX in `0Table`/`1Table`), decode each piece (compressed = CP1252 at fc/2, else
UTF-16LE), preserve `\r` (paragraph) and `\x07` (cell) marks. Images are PNG
blobs in the `Data` stream; map them to sections by counting the `\x01` inline
anchors per section. The same leading-token rules above apply.
