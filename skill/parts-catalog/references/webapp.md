# Web-app reference — interactive catalog

A dependency-free static site (vanilla JS, no build). Opens from `index.html`
via `file://`, so data is delivered as JS globals, not `fetch()`ed JSON. The
`catalog/` folder is self-contained and downloadable on its own.

## Files
```
catalog/
  index.html            markup + <script> tags
  styles.css            theme via CSS variables (client brand: charcoal + mint)
  app.js                all logic
  data/parts.js         window.CATALOG = {...}
  data/prices.js        window.PRICES = {...}
  data/all_part_numbers.csv
  drawings/*.jpg        one file per drawing page
  manual.html           the service manual (see references/manual.md)
  manual_media/*        the manual's images
```

## Data schema (`window.CATALOG`)
```
{ title_zh, title_en, maker,
  chapters:[{code,zh,en}],
  sections:[{ code, chapter, zh, en,
    figures:[{ images:[path...], parts:[{nc,ref,qty,pn,zh,en,lvl}] }] }],
  stats:{sections,parts} }
```
Store parts inside `figures` only (one source of truth); flatten in JS when a
whole-section list is needed. `window.PRICES` is
`{ pn: {p:price, g:group, x:xref, n:ru_name} }`. Multiple books share one
`window.CATALOG`, each as its own chapter (`020`…`210`, `600`, `700`, …).

`zh`/`en` are the section's two **display-name** slots, but different books fill
them differently (a Russian book puts the name in `zh` and only an option code in
`en`). Never label a section straight from `s.en` — a bare code leaks into the
tree. Use the `secName()` rule (a name has a space, a code does not) for the
sidebar and search results. See `references/categorization.md`.

## UI
- **Chapter → section tree** in the sidebar; full-text search over every part
  number and name (中文 / English / Russian-from-price).
- **Figure = drawing(s) + its own position list**, side by side (drawing sticky,
  list scrolls). Several drawings in one figure → a carousel with counter, not a
  tall stack. Header "Рисунок N / M · позиции a–b".
- **Parts table**: № | Номер детали | Наименование | Цена | Кол-во | Нужно | ＋.
  Show the RU name from the price list, the interchangeable article under the
  number, and the group as a chip. **Positions are sorted ascending** per figure
  (ref-less kit sub-items stay under their parent).
- **Нужно** = per-row required-quantity input (default = on-scheme qty); ＋ adds
  that amount. Positions without a part number show `—` and no ＋.
- **Cart** (localStorage): editable qty, machine serial, per-line `price×qty`
  and an order total.
- **Exports**: order and all-unique-numbers as **real .xlsx** (see
  references/price-list.md — leading zeros preserved). Print sheet with prices.
- **Update prices locally**: a button reads a new `.xlsx`/`.csv` price list in
  the browser and layers it over `data/prices.js` (localStorage overlay + a
  downloadable regenerated `prices.js`), no rebuild — see references/price-list.md.
- **Availability check by list**: paste or upload a list of part numbers; report
  which are in the catalog (directly and via the interchangeable article) with
  every attribute the catalog holds — RU/EN/ZH name, price, group, xref,
  on-scheme qty, sections — and export the result to `.xlsx`. Build a
  `pn → {name,qty,sections}` index once (invalidate it when prices change) plus a
  reverse `interchangeable-article → pn` map; reuse the same `.xlsx`/`.csv`
  readers as the price loader. Note: these books/price lists carry **no weight**,
  so there is no weight column — output only attributes that exist.
- **Manual** button in the header; catalog⇄manual cross-references (references/manual.md).
- **Branding**: theme via CSS variables so a client palette + logo swap cleanly;
  a pinned top contact bar is an expected touch.

## Rendering gotchas (each cost real debugging time)
- **Sticky `<thead>` + `border-collapse` hides the first row** — the header
  paints over row 001. Do **not** make the table header sticky.
- **Scroll anchoring** shifts the view when a drawing loads async, pushing the
  first row out. Set `html{overflow-anchor:none}`.
- Zero-pad numeric positions for a consistent № column (`1` → `001`).
- Building HTML by string concat: one mismatched quote breaks the whole file.
  Run `node --check app.js` after edits.
- Theme both fills and text: a bright brand color works as a button fill but is
  unreadable as link text — keep a separate darker "ink" variable.
- A variable-height contact bar breaks sticky offsets — let it scroll away and
  stick only the header at `top:0`.

## Always smoke-test in the real browser
Chromium + Playwright are preinstalled
(`executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome'`). Load
several sections across chapters and assert: first visible row is the true first
position, **positions ascending within each figure**, no row overlaps the
header, drawings load (`naturalWidth>0`), add-to-cart updates totals, search
returns rows, both export files download and re-open cleanly, catalog⇄manual
cross-references navigate both ways, **every section in the sidebar shows a name
(not a bare option code)**, and `pageerror`/console-error count is 0.
