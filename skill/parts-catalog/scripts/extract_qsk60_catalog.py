#!/usr/bin/env python3
"""
Extract the Cummins QSK60 engine parts catalog and MERGE it into the catalog as
chapter 700.

Source: ``QSK60.zip.001``/``.002`` (split zip) holding one PDF per option
("Genuine Cummins Parts N.pdf"). Each PDF is one option/section: a drawing page
(illustration) plus a Russian parts table with columns
``№ · Номер по каталогу · Название · Кол-во · Dimensions``. Columns are read by
x-position (the table text has no reliable reading order).

Run AFTER extract_pdf_catalog.py / extract_inverter_catalog.py (it appends to
the parts.js they produced), then re-run extract_prices.py.

Outputs (merged / added):
  catalog/data/parts.js       -> chapter "700" + its sections appended
  catalog/drawings/700-*.jpg  -> one image per QSK60 drawing page

Usage:
  python3 tools/extract_qsk60_catalog.py [path/to/QSK60_dir_or_pdf_glob]

Dependencies: PyMuPDF.
"""
import os
import re
import sys
import json
import glob
import shutil
import subprocess
import tempfile

import fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources", "active")  # active source books
DATA_JS = os.path.join(ROOT, "catalog", "data", "parts.js")
OUT_DRAW = os.path.join(ROOT, "catalog", "drawings")

RENDER_SCALE = 1.7
JPEG_QUALITY = 82
CHAPTER = "700"
CHAPTER_ZH = "Двигатель Cummins QSK60"
CHAPTER_EN = "ENGINE CUMMINS QSK60"

CYR = re.compile(r"[А-Яа-яЁё]")
# a catalog number (5-7 digit, optional trailing letter) or a sub-assembly
# option reference (e.g. CM6726-07)
PN_RE = re.compile(r"\d{5,7}[A-Z]?$")
OPT_RE = re.compile(r"[A-Z]{2}\d+-\d+$")
OPTION_HDR = re.compile(
    r"(?:Option Detail|Подробная информация об опции|Дополнительная информация)"
    r"\s*[-—]\s*(\S+)")


def reconstruct_dir(arg):
    """Return a list of QSK60 option PDFs, rebuilding from the split zip if
    only the archive parts are present."""
    if arg:
        if os.path.isdir(arg):
            return sorted(glob.glob(os.path.join(arg, "*.pdf")))
        return sorted(glob.glob(arg))
    parts = sorted(glob.glob(os.path.join(SRC, "QSK60.zip.0*")))
    if not parts:
        raise SystemExit("no QSK60 pdf dir given and no QSK60.zip.0* parts found")
    workdir = tempfile.mkdtemp(prefix="qsk60_")
    combined = os.path.join(workdir, "combined.zip")
    with open(combined, "wb") as out:
        for p in parts:
            with open(p, "rb") as fh:
                shutil.copyfileobj(fh, out)
    subprocess.run(["unzip", "-o", combined, "-d", workdir],
                   check=True, stdout=subprocess.DEVNULL)
    return sorted(glob.glob(os.path.join(workdir, "**", "*.pdf"), recursive=True))


def sort_key(path):
    m = re.search(r"Parts\s*(\d+)(?:\.(\d+))?", os.path.basename(path))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (9999, 0)


def option_meta(doc):
    """(code, name) from the option-detail cover page."""
    txt = doc[0].get_text()
    m = OPTION_HDR.search(txt)
    code = m.group(1) if m else ""
    # the name is the block after the repeated code, before "Не предусмотрено"
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    name = ""
    if code and code in lines:
        rest = lines[lines.index(code) + 1:]
        buf = []
        for l in rest:
            if l.startswith("Не") or l in ("Option Notes", "Каталог деталей", "Дата") \
                    or re.fullmatch(r"\d{3}", l) or ord(l[0]) >= 0xE000:
                break
            buf.append(l)
        name = " ".join(buf)
    return code, name.strip()


def is_pn(s):
    return bool(PN_RE.match(s)) or bool(OPT_RE.match(s))


def parse_table_page(page):
    """Rows read by column x-position: №(≈67) · PART-NO(≈128) · NAME(≈247) ·
    QTY(≈381) · DIMENSIONS(≈443)."""
    ws = [w for w in page.get_text("words") if w[1] > 15]   # skip header band
    anchors = sorted([w for w in ws if 112 < w[0] < 160 and is_pn(w[4])],
                     key=lambda w: w[1])
    ys = [a[1] for a in anchors]
    rows = []
    for idx, a in enumerate(anchors):
        y0 = a[1]
        # a row's (multi-line) name is vertically centred on the part-number
        # line and can start above it, so bound each row by the midpoints to the
        # neighbouring anchors rather than by the anchor line itself.
        if idx > 0:
            lo = (ys[idx - 1] + y0) / 2
        elif len(ys) > 1:
            lo = y0 - (ys[1] - y0) / 2
        else:
            lo = y0 - 20
        if idx + 1 < len(ys):
            hi = (y0 + ys[idx + 1]) / 2
        elif idx > 0:
            hi = y0 + (y0 - ys[idx - 1]) / 2
        else:
            hi = y0 + 24
        band = [w for w in ws if lo <= w[1] < hi]
        num = [w for w in band if 52 < w[0] < 82 and re.fullmatch(r"\d{1,3}", w[4])]
        qty = [w for w in band if 360 < w[0] < 418 and re.fullmatch(r"\d{1,4}", w[4])]
        name = [w for w in band if 225 < w[0] < 360]
        dims = [w for w in band if w[0] >= 418 and w[4] not in ("",)]
        name.sort(key=lambda w: (round(w[1]), w[0]))
        dims.sort(key=lambda w: (round(w[1]), w[0]))
        nm = " ".join(w[4] for w in name if w[4] != "").strip()
        dm = " ".join(w[4] for w in dims).strip()
        ref = min(num, key=lambda w: abs(w[1] - y0))[4] if num else ""
        q = min(qty, key=lambda w: abs(w[1] - y0))[4] if qty else ""
        rows.append({
            "nc": "", "ref": ref, "qty": q,
            "pn": "" if OPT_RE.match(a[4]) else a[4],
            "zh": nm, "en": dm, "lvl": 0,
            "opt": a[4] if OPT_RE.match(a[4]) else "",
        })
    return rows


def main():
    pdfs = reconstruct_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    pdfs.sort(key=sort_key)
    os.makedirs(OUT_DRAW, exist_ok=True)

    out_sections = []
    total_parts = 0
    n = 0
    printed = set()
    captured = set()
    for path in pdfs:
        doc = fitz.open(path)
        if doc.page_count == 0:
            continue
        code, name = option_meta(doc)
        images, parts = [], []
        n += 1
        seccode = "%s-%04d" % (CHAPTER, n * 10)
        img_i = 0
        for pi in range(doc.page_count):
            page = doc[pi]
            t = page.get_text()
            words = page.get_text("words")
            # A table needs the column header or several *numeric* part numbers.
            # The cover page carries only the option code (BB67043-00) — an OPT
            # ref, not a number — so it is rendered as the drawing, not parsed.
            nnum = sum(1 for w in words if 112 < w[0] < 160
                       and PN_RE.match(w[4]) and not OPT_RE.match(w[4]))
            if "Номер по каталогу" in t or nnum >= 2:
                parts.extend(parse_table_page(page))
                for w in words:
                    if 112 < w[0] < 160 and PN_RE.match(w[4]) and not OPT_RE.match(w[4]):
                        printed.add(w[4])
            elif page.get_images():
                img_i += 1
                pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))
                fname = "%s-%d.jpg" % (seccode, img_i)
                pix.save(os.path.join(OUT_DRAW, fname), jpg_quality=JPEG_QUALITY)
                images.append("drawings/" + fname)
        for p in parts:
            if p["pn"]:
                captured.add(p["pn"])
        # option code carried in the section title; sub-assembly refs kept in name
        for p in parts:
            if p.get("opt") and not p["en"]:
                p["en"] = "см. " + p["opt"]
            p.pop("opt", None)
        if not parts and not images:
            continue   # a declaration / index page, not an option catalog
        out_sections.append({
            "code": seccode, "chapter": CHAPTER, "zh": name or code, "en": code,
            "figures": [{"images": images, "parts": parts}],
        })
        total_parts += len(parts)
        print("  %-9s %-40s draws=%d parts=%d" % (seccode, (name or code)[:38], len(images), len(parts)))

    # ---- merge ----
    raw = open(DATA_JS, encoding="utf-8").read()
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
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

    missing = printed - captured
    print("\nQSK60 sections: %d  parts: %d  drawings: %d" %
          (len(out_sections), total_parts,
           sum(len(f["images"]) for s in out_sections for f in s["figures"])))
    print("Part numbers printed: %d  captured: %d  missing: %d"
          % (len(printed), len(printed & captured), len(missing)))
    if missing:
        print("  MISSING:", sorted(missing)[:20])
    print("Merged into", os.path.relpath(DATA_JS, ROOT))


if __name__ == "__main__":
    main()
