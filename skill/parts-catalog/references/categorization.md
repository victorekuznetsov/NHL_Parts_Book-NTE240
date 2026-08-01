# Categorization reference — chapters, sections, and their display names

How the catalog is organized into a browsable tree, and — the part that bites —
how each section gets the **name** shown in the sidebar and search results. Read
this whenever you add a new book, or a section shows up in the tree as a bare
code / number instead of a human name.

## The two-level tree

The catalog is always **chapter → section**. Both live in `window.CATALOG`:

```
chapters:[{ code, zh, en }]                     // "700", "ENGINE CUMMINS QSK60"
sections:[{ code, chapter, zh, en, figures:[…] }]  // "700-0020", "Турбокомпрессор"
```

- **`code`** — the stable identifier. Real OEM books already carry `NNN-NNNN`
  section codes; use them verbatim. A book with no codes of its own (inverter,
  QSK60 options) gets **synthetic** codes: a fresh chapter number and
  `NNN-0010, NNN-0020, …` sections in source order.
- **`chapter`** on each section is the join key back to `chapters[].code`.
- `zh` / `en` are the two **display-name** slots (historically Chinese / English
  in the NHL books). They are just two name fields — what actually lands in each
  differs by book, which is the whole problem below.

The sidebar renders `code` + a name; search groups hits by section under the same
name. So the name must be **descriptive**, never a code.

## The naming pitfall (validated bug)

Different books fill `zh`/`en` differently, and the display code must not assume:

| Book / chapter | `zh` holds | `en` holds |
|---|---|---|
| Main PDF part book (020–210) | Chinese name (often empty) | English name, e.g. `FRONT BRAKES ASSY` |
| Inverter / drive system (600) | Chinese name + variant marker | English name, e.g. `OVH OHV INVERTER · 1` |
| **Cummins QSK60 (700)** | **Russian name**, e.g. `Турбокомпрессор` | **an option code**, e.g. `VC6715-02` — *not a name* |

The original sidebar showed `s.en || s.zh` (English-first, which is right for the
NHL books). For QSK60 that surfaced the **option code** (`VC6715-02`,
`WP6705-14`, …) as the section's "name" — the tree read as a column of
meaningless codes. The user caught it from a phone photo of the sidebar.

### The rule: a name has a space; a bare code does not

OEM option/part codes are a solid token — two letters, digits, a dash, **no
space** (`VC6715-02`, `PP6884-06`). Real names contain a space
(`FRONT BRAKES ASSY`, `Турбокомпрессор` is a single word but is the *only* name
present). So pick the name like this (in `app.js`, used by both the sidebar and
search results):

```js
// Human-readable section name. Some chapters put the descriptive name in `zh`
// and only an option code in `en`; others put the English name in `en`.
// A bare code (no space) is not a name: prefer a real phrase in `en`,
// else the `zh` name, else fall back to `en`.
function secName(s) {
  if (!s) return "";
  var en = s.en || "", zh = s.zh || "";
  if (en && /\s/.test(en)) return en;   // an English phrase name wins
  return zh || en;                       // else the zh name; else whatever en is
}
```

- QSK60: `en="PP6884-06"` (no space) → falls through to `zh="Турбокомпрессор"`. ✅
- NHL 080: `en="FRONT BRAKES ASSY"` (has space) → English name, unchanged. ✅
- Inverter 600: `en="OVH OHV INVERTER · 1"` (has space) → English, unchanged. ✅
- Both empty → `""`, and only the `code` shows (acceptable). ✅

Because the rule only changes the *code-in-`en`* case, it is a no-op for every
English-named chapter — exactly the safe, targeted behaviour you want. Use
`secName(s)` **everywhere a section is labelled** (sidebar list items, search
result headers). The section page `<h1>` already shows `zh` as the primary name
with `en` as a sub-line, so it was correct for QSK60 without change — but keep
the two consistent: if you ever change the primary name source, change both.

## When a section has no usable name at all

Some real sections carry only a code (both name slots empty). Options, best
first:
1. **Lift the name the source prints on the drawing/title page** — the parser
   already reads section identity from drawing pages; capture the title there.
2. **Inherit from a sibling with the same code stem** if the book repeats a name
   across split figures (e.g. `700-0170`/`700-0180` are both `Водяной насос`).
3. Leave it code-only. Do **not** invent a category — a wrong name is worse than
   a bare code, and the user will notice.

## Categorizing a newly added book into chapters

When a new equipment book becomes a chapter:
- Give the chapter a **descriptive `en`** (`ENGINE CUMMINS QSK60`), not just the
  number — the chapter header uses `ch.en || ch.zh`.
- If the book is one flat list, keep its own section granularity (one section per
  drawing/figure). Don't collapse distinct drawings into one section — the
  "one figure = one drawing + its own position list" rule depends on it.
- Fill whichever name slot matches how the book is written (Russian book → put
  the Russian name where `secName` will find it; the space rule then does the
  right thing automatically).
- After adding, load the new chapter in the browser and read the **sidebar**:
  every section must show a name, never a code. This is part of the smoke test,
  not an afterthought.
