#!/usr/bin/env python3
"""
Extract the inverter / driving-system spare-parts book and MERGE it into the
existing catalog as an extra chapter.

The source ``NHL240Invertex2驱动系统备件手册.doc.pdf`` was converted from a binary
Word .doc, so its parts tables are a linear text stream (one field per line,
rows separated by a blank line) rather than positioned columns — a different
parser from the main NTE240 PDF. Sections are named subsystems (逆变器/INVERTER,
接触器/CONTACTOR, 电动轮/MOTORIZED WHEEL …) with no NNN-NNNN code, so synthetic
codes ``600-00N0`` under a new chapter ``600`` are assigned in book order.

Run AFTER ``extract_pdf_catalog.py`` (it appends to the parts.js it produced),
then re-run ``extract_prices.py`` so the new numbers pick up prices.

Outputs (merged / added):
  catalog/data/parts.js               -> chapter "600" + its sections appended
  catalog/drawings/600-*.jpg          -> one image per inverter drawing page

Usage:
  python3 tools/extract_inverter_catalog.py [path/to/inverter.pdf]

Dependencies: PyMuPDF (``pip install pymupdf``).
"""
import os
import re
import sys
import json
import glob

import fitz  # PyMuPDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(ROOT, "catalog", "data", "parts.js")
OUT_DRAW = os.path.join(ROOT, "catalog", "drawings")

RENDER_SCALE = 1.7
JPEG_QUALITY = 82
CHAPTER = "600"
CHAPTER_ZH = "驱动系统（逆变器）"
CHAPTER_EN = "DRIVING SYSTEM (INVERTER)"

CJK = re.compile(r"[一-鿿]")
REF_RE = re.compile(r"\d{1,3}[A-Z]?$")
QTY_RE = re.compile(r"\d{1,3}$|AR$|A/R$")
PN_RE = re.compile(r"\d{6,8}$|UR[0-9A-Z\-]{3,}$")
DATE_RE = re.compile(r"(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")

# unambiguous column-header / running-header markers that never occur inside a
# real part name (unlike "逆变器/INVERTER", which is a genuine part name and must
# NOT be used as a marker)
_HDR_MARK = ("英文名称", "中文名称", "FROM SERIAL", "PART NO", "自系列号")


def default_pdf():
    cand = glob.glob(os.path.join(ROOT, "*[Ii]nverte*.pdf")) + \
        glob.glob(os.path.join(ROOT, "*驱动*.pdf"))
    if not cand:
        raise SystemExit("inverter PDF not found; pass its path")
    return cand[0]


def page_title(page):
    """(zh, en) subsystem name from a page's running-header line."""
    lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not lines:
        return "", ""
    t = lines[0]
    t = re.sub(r"\.{2,}", " ", t).strip()
    t = re.sub(r"\bMODEL\b|\bMODE\b|\bPART\b(?=\s*$)", "", t).strip()
    zh = "".join(re.findall(r"[一-鿿ⅠⅡⅢⅣ]+", t)).strip()
    en = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9/,\-\.]*", t)).strip()
    en = re.sub(r"\s+", " ", en).strip(" .,-")
    return zh, en


def norm_title(page):
    zh, en = page_title(page)
    return re.sub(r"[^0-9A-Za-z一-鿿]", "", (zh + en)).upper()


def _split_name(lines):
    """Split name lines into (zh, en); a single line may mix CJK and Latin."""
    zh_parts, en_parts = [], []
    for ln in lines:
        zh = "".join(re.findall(r"[一-鿿，、（）()·]+", ln)).strip()
        en = " ".join(re.findall(r"[A-Za-z0-9][A-Za-z0-9/,\.\-()]*", ln)).strip()
        if zh:
            zh_parts.append(zh)
        if en:
            en_parts.append(en)
    return " ".join(zh_parts).strip(), " ".join(en_parts).strip()


def _is_naa(s):
    """A ``#N/A`` placeholder — a real listed position with no catalog number."""
    return bool(re.fullmatch(r"#?N/?A", s))


def _is_pn(s):
    # NB: do NOT reject date-shaped tokens here — many real catalog numbers
    # (20040401, 20040502, …) are valid YYYYMMDD dates. The only date in the
    # source is the header revision date, which never sits in a REF/QTY row
    # context, so context (not value) is what keeps it out of the parts list.
    return bool(PN_RE.match(s)) and not s.startswith("PM")


def _qty_at(lines, i):
    """(qty, tokens_consumed) at line i. QTY is a count or "AR"; the .doc export
    sometimes splits "AR" across two lines ("A" then "R")."""
    if i < len(lines) and QTY_RE.match(lines[i]):
        return lines[i], 1
    if i + 1 < len(lines) and lines[i] == "A" and lines[i + 1] == "R":
        return "AR", 2
    return None, 0


def _nc_letter(lines, i):
    """A lone note letter (注/NC) sits between REF and QTY on some rows; consume
    it only when a QTY or PART-NO follows, so neither a name word nor the first
    half of a split "A R" quantity is eaten."""
    return (i < len(lines) and re.fullmatch(r"[A-Z]", lines[i]) and i + 1 < len(lines)
            and lines[i + 1] != "R"
            and (QTY_RE.match(lines[i + 1]) or _is_pn(lines[i + 1])))


def _row_start(lines, k):
    """True if a part row begins at line k. Rows are ``REF [NC] QTY [PART-NO]
    name``; detected by that signature so it works whether or not the .doc→PDF
    export put a blank line between rows (some pages have separators, some not)
    and whether or not a note letter sits in the NC column."""
    if k + 1 >= len(lines) or not REF_RE.match(lines[k]):
        return False
    i = k + 1
    if _nc_letter(lines, i):
        i += 1
    q, c = _qty_at(lines, i)
    if q is not None:
        after = lines[i + c] if i + c < len(lines) else ""
        # PART-NO, a kit sub-name, or a #N/A placeholder position
        return _is_pn(after) or _is_naa(after) or bool(CJK.search(after))
    return i < len(lines) and _is_pn(lines[i])            # REF then PART-NO (qty blank)


def parse_table(page):
    """Parse a linear-text parts table page into part rows."""
    lines = [l.strip() for l in page.get_text().splitlines()]
    n = len(lines)
    parts = []
    k = 0
    while k < n:
        if not (lines[k] and _row_start(lines, k)):
            k += 1
            continue
        ref = lines[k]
        i = k + 1
        nc = ""
        if _nc_letter(lines, i):
            nc = lines[i]
            i += 1
        qty, c = _qty_at(lines, i)
        qty = qty or ""
        i += c
        pn = ""
        if i < n and _is_pn(lines[i]):
            pn = lines[i]
            i += 1
        elif i < n and _is_naa(lines[i]):
            i += 1                         # #N/A placeholder position, no number
        # the name runs to the next row start; scanning from *after* the
        # consumed REF/QTY/PART-NO so a row's own QTY line is never mistaken for
        # the REF of a phantom row
        j = i
        while j < n and not (lines[j] and _row_start(lines, j)):
            j += 1
        zh, en = _split_name([l for l in lines[i:j] if l and not _is_naa(l)])
        parts.append({"nc": nc, "ref": ref, "qty": qty, "pn": pn,
                      "zh": zh, "en": en, "lvl": 0})
        k = j
    return parts


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else default_pdf()
    doc = fitz.open(pdf)
    os.makedirs(OUT_DRAW, exist_ok=True)

    # Group adjacent pages sharing a subsystem title into sections; a page with
    # an embedded image is a drawing, an image-free page with rows is a table.
    entries = []
    for i in range(doc.page_count):
        page = doc[i]
        title_key = norm_title(page)
        if not title_key or title_key.startswith("NTE240"):
            # cover / front matter
            if page.get_images():
                pass  # skip cover
            continue
        if page.get_images():
            entries.append(("D", i, title_key, page))
        else:
            parts = parse_table(page)
            if parts:
                entries.append(("T", i, title_key, page, parts))

    # split into sections on title change
    sections = []
    cur = None
    for e in entries:
        kind, i = e[0], e[1]
        key, page = e[2], e[3]
        if cur is None or cur["key"] != key:
            zh, en = page_title(page)
            cur = {"key": key, "zh": zh, "en": en, "pages": []}
            sections.append(cur)
        else:
            if not cur["zh"]:
                cur["zh"] = page_title(page)[0]
            if not cur["en"]:
                cur["en"] = page_title(page)[1]
        cur["pages"].append(e)

    def dedupe(parts):
        """Drop repeated rows within a figure. The .doc→PDF export doubles the
        text of some table pages (the whole row block appears twice), so a
        catalog-numbered position that recurs with the same number is a source
        artifact, not a real second listing."""
        out, seen = [], set()
        for p in parts:
            key = (p["ref"], p["pn"]) if p["pn"] else None
            if key is not None and key in seen:
                continue
            if key is not None:
                seen.add(key)
            out.append(p)
        return out

    def group_figures(pages):
        figs, fig = [], None
        for e in pages:
            kind = e[0]
            if kind == "D":
                if fig is None or fig["seen_tab"]:
                    fig = {"draw": [], "parts": [], "seen_tab": False}
                    figs.append(fig)
                fig["draw"].append(e[1])
            else:
                if fig is None:
                    fig = {"draw": [], "parts": [], "seen_tab": False}
                    figs.append(fig)
                fig["parts"].extend(e[4])
                fig["seen_tab"] = True
        for fig in figs:
            fig["parts"] = dedupe(fig["parts"])
        return figs

    # drop front-matter / drawing-only sections that carry no parts
    sections = [s for s in sections
                if sum(len(e[4]) for e in s["pages"] if e[0] == "T") > 0]

    # Each figure (a drawing set + its own 1..N position list) becomes its own
    # section — the driving-system book prints the same subsystem in several
    # independent configurations, and merging them under one section would put
    # unrelated position lists (each restarting at 1) behind one entry. When a
    # subsystem yields more than one figure the sections are numbered · 1, · 2 …
    out_sections = []
    total_parts = 0
    n = 0
    for s in sections:
        figs = [f for f in group_figures(s["pages"]) if f["draw"] or f["parts"]]
        multi = len(figs) > 1
        for vi, fig in enumerate(figs, 1):
            n += 1
            code = "%s-%04d" % (CHAPTER, n * 10)
            images = []
            for img_i, pno in enumerate(fig["draw"], 1):
                pix = doc[pno].get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))
                fname = "%s-%d.jpg" % (code, img_i)
                pix.save(os.path.join(OUT_DRAW, fname), jpg_quality=JPEG_QUALITY)
                images.append("drawings/" + fname)
            zh = s["zh"] + ("（вар. %d）" % vi if multi else "")
            en = s["en"] + (" · %d" % vi if multi else "")
            out_sections.append({
                "code": code, "chapter": CHAPTER, "zh": zh, "en": en,
                "figures": [{"images": images, "parts": fig["parts"]}],
            })
            total_parts += len(fig["parts"])
            print("  %-9s %-34s draws=%d parts=%d" %
                  (code, en[:32], len(images), len(fig["parts"])))

    # ---- merge into the existing catalog ----
    raw = open(DATA_JS, encoding="utf-8").read()
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    # idempotent: drop any previously-added inverter chapter/sections
    data["chapters"] = [c for c in data["chapters"] if c["code"] != CHAPTER]
    data["sections"] = [s for s in data["sections"] if s["chapter"] != CHAPTER]
    data["chapters"].append({"code": CHAPTER, "zh": CHAPTER_ZH, "en": CHAPTER_EN})
    data["sections"].extend(out_sections)
    data["stats"]["sections"] = len(data["sections"])
    data["stats"]["parts"] = sum(len(f["parts"]) for s in data["sections"] for f in s["figures"])

    with open(DATA_JS, "w", encoding="utf-8") as fh:
        fh.write("window.CATALOG = ")
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    # ---- completeness: every part number printed in a row must be captured ----
    printed = set()
    for i in range(doc.page_count):
        lines = [l.strip() for l in doc[i].get_text().splitlines()]
        for j, ln in enumerate(lines):
            # a real part number sits after a QTY (数量) line (a count, "AR", or a
            # split "A"/"R"); the header revision date is preceded by a revision
            # letter, so context — not the date-shaped value — separates them
            if _is_pn(ln) and j >= 1 and (QTY_RE.match(lines[j - 1]) or
                                          (lines[j - 1] == "R" and j >= 2 and lines[j - 2] == "A")):
                printed.add(ln)
    captured = {p["pn"] for s in out_sections for f in s["figures"] for p in f["parts"] if p["pn"]}
    missing = printed - captured
    print("\nInverter sections: %d  parts: %d  drawings: %d" %
          (len(out_sections), total_parts,
           sum(len(f["images"]) for s in out_sections for f in s["figures"])))
    print("Part numbers printed: %d  captured: %d  missing: %d"
          % (len(printed), len(printed & captured), len(missing)))
    if missing:
        print("  MISSING:", sorted(missing)[:20])
    print("Merged into", os.path.relpath(DATA_JS, ROOT))


if __name__ == "__main__":
    main()
