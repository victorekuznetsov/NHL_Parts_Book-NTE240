#!/usr/bin/env python3
"""
Extract an interactive catalog (data + drawing images) from the NTE240 Parts Book PDF.

The source PDF ships in the repository as a split zip archive
(``NTE240 Part Book-Polyus.zip.001`` .. ``.00N``). This script reconstructs the
PDF from those parts (via the system ``unzip`` — the archive uses the deflate64
method, which Python's ``zipfile`` cannot decompress) when a plain PDF path is
not supplied.

Outputs:
  catalog/data/parts.js            -> ``window.CATALOG = {...}`` (works from file://)
  catalog/drawings/<code>-<n>.jpg  -> one rendered image per drawing page

Usage:
  python3 tools/extract_pdf_catalog.py [path/to/catalog.pdf]

Dependencies: PyMuPDF (``pip install pymupdf``).
"""
import os
import re
import glob
import json
import sys
import shutil
import subprocess
import tempfile

import fitz  # PyMuPDF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources", "active")  # active source books
OUT_DATA = os.path.join(ROOT, "catalog", "data", "parts.js")
OUT_DRAW = os.path.join(ROOT, "catalog", "drawings")

RENDER_SCALE = 1.7      # ~120 DPI, good for line drawings
JPEG_QUALITY = 82

# Major chapter names (code prefix -> [zh, en]); from the Table of Contents.
CHAPTERS = {
    "020": ["结构件", "STRUCTURE"],
    "030": ["电气系统", "ELECTRICAL SYSTEM"],
    "040": ["动力系统", "POWER SYSTEM"],
    "050": ["液压系统", "HYDRAULIC SYSTEM"],
    "070": ["行走系统", "RUNNING SYSTEM"],
    "080": ["制动系统", "BRAKE SYSTEM"],
    "090": ["驾驶室", "CAB"],
    "100": ["附属系统", "SUBSIDIARY SYSTEM"],
    "150": ["轮胎和轮辋", "TIRES AND RIMS"],
    "210": ["选装", "OPTIONAL"],
    "220": ["选装", "OPTIONAL"],
}

SEC_RE = re.compile(r"^\s*(\d{3}-\d{4})\b(.*)")
CJK_RE = re.compile(r"[一-鿿]")


def reconstruct_pdf():
    """Rebuild the PDF from split zip parts in the repo root, return a path.

    The archive is stored split (``*.zip.001`` ..) and compressed with
    deflate64; concatenate the parts and let the system ``unzip`` expand it.
    """
    parts = sorted(glob.glob(os.path.join(SRC, "*Part Book*.zip.0*")))
    if not parts:
        raise SystemExit("No PDF given and no split zip parts (*.zip.0*) found.")
    workdir = tempfile.mkdtemp(prefix="nte240_")
    combined = os.path.join(workdir, "combined.zip")
    with open(combined, "wb") as out:
        for p in parts:
            with open(p, "rb") as fh:
                shutil.copyfileobj(fh, out)
    subprocess.run(["unzip", "-o", combined, "-d", workdir],
                   check=True, stdout=subprocess.DEVNULL)
    pdfs = glob.glob(os.path.join(workdir, "*.pdf"))
    if not pdfs:
        raise SystemExit("no .pdf found inside the split zip archive")
    return pdfs[0]


# ---- table parsing -------------------------------------------------------

# Fallback column x-anchors per side (used if a page's header row is missing).
_DEFAULT = {
    "L": [("nc", 51), ("ref", 78), ("qty", 109), ("pn", 144), ("zh", 225), ("en", 331)],
    "R": [("nc", 433), ("ref", 461), ("qty", 493), ("pn", 528), ("zh", 609), ("en", 715)],
}
_HDR = {"NC": "nc", "REF": "ref", "QTY": "qty", "PART": "pn", "ZH.": "zh", "EN.": "en"}


def _detect_anchors(page):
    """Per-side column x-anchors AND the y below which that side's table body
    begins: ``{"L": (anchors, body_top), "R": (anchors, body_top)}``.

    Tables shift both horizontally and *vertically* page to page (the amount of
    running-header matter above the table varies), and the two columns can even
    carry their headers at different heights — so anchors and body-top are read
    from each side's own header row independently. A side with no detectable
    header falls back to the default anchors and body-top."""
    labels = [(_HDR[w[4]], w[0], w[1]) for w in page.get_text("words")
              if w[4] in _HDR and w[1] < 260]
    out = {}
    for side in ("L", "R"):
        sl = [(k, x, y) for (k, x, y) in labels if (x < 431 if side == "L" else x >= 431)]
        if len({k for k, _, _ in sl}) >= 4:
            header_y = max(y for _, _, y in sl)   # english band sits below CJK band
            d = {}
            for k, x, y in sl:
                if abs(y - header_y) < 8:
                    d.setdefault(k, x)
            anchors = [(k, d[k]) for k in ("nc", "ref", "qty", "pn", "zh", "en") if k in d]
            if len(anchors) >= 4:
                out[side] = (anchors, header_y + 6)
                continue
        out[side] = (_DEFAULT[side], DEFAULT_BODY_TOP)
    return out


_HDR_TOKENS = {"NC", "REF", "QTY", "PART", "NO.", "ZH.", "EN.", "DESC.",
               "注", "序号", "数量", "件号", "中文名称", "英文名称",
               "序", "号", "数", "量"}
_CJK = re.compile(r"[一-鿿]")

# fallback body-top for continuation table pages that carry no header band
# (their first data row can sit as high as y~70)
DEFAULT_BODY_TOP = 65

# a 7-8 digit / UR-prefixed catalog number sitting in a part-number column
_PN_COL = re.compile(r"\d{7,8}|UR[0-9A-Z]{3,}|9[0-9]{5}")


# A catalog number in this book is a 7-8 digit code, a 6-digit ``9xxxxx`` code,
# or a ``UR`` code (optionally hyphenated). This whitelist was validated to
# match every part number physically printed in the parts-table columns while
# rejecting running-header noise — drawing/scheme IDs (``PMnnnnnnnn``), revision
# + date ECN codes (``A20190923``), the model name (``NTE240``) and section
# codes (``090-0100``) — which otherwise leak in as phantom rows.
_PN_RE = re.compile(r"\d{7,8}|9\d{5}|UR[0-9A-Z][0-9A-Z\-]{2,}")


def _is_pn(s):
    return bool(_PN_RE.fullmatch(s.rstrip(".,;")))


# A running-header title block (revision letter + date + ECN code + drawing
# number, e.g. "A 20190313 NHK007 PM00001468") lands on a headerless
# continuation page as a phantom row: no position number, no Chinese name, and
# an "English name" made only of drawing/ECN codes. To drop it without touching
# a real part we require BOTH: an unmistakable drawing/ECN signature (a PMnnnn
# scheme number or an NHxxx ECN code), and that every name token is code-like.
# A real part row (a genuine word, or even a stray revision letter) is kept.
_NOISE_SIG = re.compile(r"PM\d{4,}|NH[A-Z]{1,4}\d")
_NOISE_TOK = re.compile(r"PM\d{4,}|NH[A-Z0-9]+|S-\d+|[A-Z]|\d{3,}")


def _is_header_noise(ref, zh, en):
    if ref or zh or not en or not _NOISE_SIG.search(en):
        return False
    return all(_NOISE_TOK.fullmatch(t) for t in en.split())


# A chapter-divider / contents block (the section-title list plus the ECN
# summary table "涉及序列号 手册号 版本 修改号 …") bleeds onto a chapter's first
# table page as one long pn-less phantom row. Its Chinese carries divider-table
# headers a real part name never uses.
_DIVIDER = re.compile(r"手册号|修改号|涉及序列号|版本$|版本\s")


def _is_divider_row(pn, zh, en):
    if pn:
        return False
    if zh.startswith("章") or _DIVIDER.search(zh):   # 章 = chapter-contents sheet
        return True
    return len(en.split()) > 2 and len(re.findall(r"PM\d{4,}", en)) >= 2


# Running-header captions and ECN/scheme codes that bleed into a name from the
# band just above the table. These are stripped for display; the real name
# words (Chinese, and English words) are kept.
_NAME_NOISE = re.compile(
    r"日期DATE[:：]?\s*\d+|DATE[:：]\s*\d*|日期|涉及序列号|手册号|版本|修改号"
    r"|自系列号?|FROM\s+SERIAL(\s+NO\.?)?|SERIAL\s+NO\.?|PM\s+NO\.?|Ver\.?|ECN"
    r"|PM\d{4,}|NH[A-Z0-9]+(?:-\d+)?|(?<![0-9])[A-Z]?\d{8}(?![0-9])",
    re.IGNORECASE)


def _clean_name(s):
    if not s:
        return s
    s = _NAME_NOISE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ·•,.-")
    return s


def _cluster_rows(ws):
    clusters = []
    for w in sorted(ws, key=lambda w: (w[1], w[0])):
        for c in clusters:
            if abs(c["y"] - w[1]) < 7:
                c["ws"].append(w)
                c["y"] = (c["y"] * c["n"] + w[1]) / (c["n"] + 1)
                c["n"] += 1
                break
        else:
            clusters.append({"y": w[1], "n": 1, "ws": [w]})
    return [sorted(c["ws"], key=lambda w: w[0]) for c in sorted(clusters, key=lambda c: c["y"])]


def _parse_side(words, side, anchors, body_top):
    """Value-based row parsing: locate the part-number token, then read REF/QTY
    to its left and the ZH/EN names to its right. Robust to columns that are
    shifted relative to their header labels."""
    amap = dict(anchors)
    nc_a, ref_a, qty_a, pn_a = amap.get("nc"), amap.get("ref"), amap.get("qty"), amap.get("pn")
    ws = [w for w in words if (w[0] < 431 if side == "L" else w[0] >= 431)]
    ws = [w for w in ws if w[1] > body_top and w[4] not in _HDR_TOKENS]

    rows = []
    for toks in _cluster_rows(ws):
        # pick the part-number token: prefer one sitting in the PART-NO column
        cands = [w for w in toks if _is_pn(w[4])]
        if pn_a is not None and cands:
            pn_w = min(cands, key=lambda w: abs(w[0] - pn_a))
        else:
            pn_w = cands[0] if cands else None

        if pn_w is None:
            # No part number on this row. If it still starts with a position
            # number (REF) it is a real listed position without an orderable
            # catalog number (e.g. a kit sub-component) — keep it so the list
            # matches the drawing callouts. Otherwise it is a wrapped name.
            nums = [w for w in toks if re.fullmatch(r"\d{1,3}", w[4])]
            if nums and ref_a is not None and abs(nums[0][0] - ref_a) < 24:
                ref = nums[0][4]
                qty = ""
                if len(nums) >= 2 and qty_a is not None and abs(nums[1][0] - qty_a) < 24:
                    qty = nums[1][4]
                used = {id(w) for w in nums[:2]}
                nc = "".join(w[4] for w in toks if re.fullmatch(r"[A-Z]\d?\d?", w[4]) and w[0] < (ref_a - 8))
                name = [w for w in toks if id(w) not in used and not re.fullmatch(r"[A-Z]\d?\d?", w[4])]
                zh = " ".join(w[4] for w in name if _CJK.search(w[4]))
                en = " ".join(w[4] for w in name if re.search(r"[A-Za-z]", w[4]) and not _CJK.search(w[4]))
                if zh or en:
                    rows.append({"nc": nc, "ref": ref, "qty": qty, "pn": "", "zh": zh, "en": en})
                    continue
            rows.append({"cont": " ".join(w[4] for w in toks)})
            continue

        left = [w for w in toks if w[0] < pn_w[0]]
        right = [w for w in toks if w[0] > pn_w[0]]
        # REF (序号) is the drawing position; QTY (数量) is the count. Both sit in
        # the NC/REF/QTY block left of the part number. Data columns often sit a
        # dozen-plus px LEFT of their own header labels, so a raw nearest-anchor
        # test picks the wrong column and swaps position with quantity. Correct
        # the drift with the part number's own offset from the PART-NO anchor,
        # then match each number to the nearest *shifted* anchor.
        nums = [w for w in left if re.fullmatch(r"\d{1,4}", w[4])]
        shift = (pn_a - pn_w[0]) if pn_a is not None else 0

        def _d(x, a):
            return abs(x - (a - shift)) if a is not None else 1e9

        ref = qty = ""
        if len(nums) >= 2:
            ref_w = min(nums, key=lambda w: _d(w[0], ref_a))
            qty_w = min(nums, key=lambda w: _d(w[0], qty_a))
            if ref_w is qty_w:
                # anchors could not separate them — fall back to left-to-right
                # order (NC REF QTY): drop a leading NC note number if present
                ordered = sorted(nums, key=lambda w: w[0])
                if len(ordered) >= 3 and nc_a is not None and \
                        _d(ordered[0][0], nc_a) < _d(ordered[0][0], ref_a):
                    ordered = ordered[1:]
                ref, qty = ordered[0][4], ordered[1][4]
            else:
                ref, qty = ref_w[4], qty_w[4]
        elif len(nums) == 1:
            # a lone count is the position (REF) unless it clearly sits under QTY
            if _d(nums[0][0], ref_a) <= _d(nums[0][0], qty_a):
                ref = nums[0][4]
            else:
                qty = nums[0][4]
        if not qty:
            ar = [w for w in left if re.fullmatch(r"AR|A/R", w[4])]
            if ar:
                qty = ar[0][4]
        nc = "".join(w[4] for w in left if re.fullmatch(r"[A-Z]", w[4]))
        zh = " ".join(w[4] for w in right if _CJK.search(w[4]))
        en = " ".join(w[4] for w in right if re.search(r"[A-Za-z]", w[4]) and not _CJK.search(w[4]))
        rows.append({"nc": nc, "ref": ref, "qty": qty, "pn": pn_w[4], "zh": zh, "en": en})
    return rows


def parse_parts(page):
    words = page.get_text("words")
    anchors = _detect_anchors(page)
    rows = (_parse_side(words, "L", anchors["L"][0], anchors["L"][1])
            + _parse_side(words, "R", anchors["R"][0], anchors["R"][1]))
    parts = []
    for r in rows:
        if "cont" in r:
            # wrapped name continuation of the previous part
            txt = r["cont"].strip()
            if parts and txt:
                if _CJK.search(txt):
                    parts[-1]["zh"] = (parts[-1]["zh"] + " " + "".join(
                        ch for ch in txt if _CJK.search(ch) or ch in "·• ")).strip()
                lat = " ".join(t for t in txt.split() if re.search(r"[A-Za-z]", t))
                if lat:
                    parts[-1]["en"] = (parts[-1]["en"] + " " + lat).strip()
            continue
        if not r["pn"] and not r["ref"]:
            continue  # nothing identifiable
        zh, en = r["zh"].strip(), r["en"].strip()
        if _is_header_noise(r["ref"], zh, en):
            continue  # running-header block (date + ECN/drawing codes), not a part
        lvl = len(re.match(r"[·•\s]*", (zh or en)).group(0).replace(" ", ""))
        parts.append({
            "nc": r["nc"],
            "ref": r["ref"] if re.fullmatch(r"\d{1,3}", r["ref"]) else "",
            "qty": r["qty"],
            "pn": r["pn"].strip(".,;"),
            "zh": zh.lstrip("·• ").strip(),
            "en": en.lstrip("·• ").strip(),
            "lvl": lvl,
        })
    # final pass: drop divider/header-noise phantom rows (a noise name can be
    # appended by the wrapped-name continuation branch *after* a row was first
    # accepted, so re-check here), and scrub running-header bleed from names.
    out = []
    for p in parts:
        if _is_divider_row(p["pn"], p["zh"], p["en"]):
            continue
        if _is_header_noise(p["ref"], p["zh"], p["en"]):
            continue
        p["zh"] = _clean_name(p["zh"])
        p["en"] = _clean_name(p["en"])
        if not (p["pn"] or p["ref"] or p["zh"] or p["en"]):
            continue
        out.append(p)
    return out


def parse_header(page):
    """Return (code, zh_title, en_title) from a section page header.

    On this book the section-code line is not always the page's first line
    (continuation table pages may lead with data rows), so scan every line for
    the first ``NNN-NNNN`` header and read the titles from it."""
    for line in page.get_text().splitlines():
        m = SEC_RE.match(line.strip())
        if not m:
            continue
        code = m.group(1)
        rest = m.group(2)
        # strip trailing version/date/ECN tokens
        rest = re.split(r"\s{2,}[A-Z]?\s?\d{8}", rest)[0]
        zh = "".join(re.findall(r"[一-鿿（）()0-9．\.、/\-]+", rest)).strip()
        en_m = re.search(r"[A-Za-z].*", rest)
        en = en_m.group(0).strip() if en_m else ""
        en = re.sub(r"\s*[A-Z]?\d{6,}.*$", "", en).strip()
        en = en.strip(" .")
        return code, zh, en
    return None, "", ""


# ---- main ----------------------------------------------------------------

def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else reconstruct_pdf()
    doc = fitz.open(pdf)
    os.makedirs(OUT_DRAW, exist_ok=True)

    # Classify each page, then assign parts to sections in document order.
    #
    # Critical to this book: a parts-TABLE page's own title block is unreliable —
    # it prints the code of the *following* section, not the parts on it (e.g.
    # the dump-body liner rows 001–010 sit on a page stamped "100-0180", and
    # weight-system row 071 sits on a page stamped "100-0160"). Only DRAWING
    # sheets and section-TITLE sheets name their section correctly. So section
    # identity is taken solely from those non-table pages, and every table's
    # rows are attributed to the most recent such section — never to the code
    # printed on the table page itself.
    #
    # Page kinds: an embedded illustration -> "D" (drawing, rendered; never holds
    # table rows here). An image-free page with parseable rows -> "T" (table,
    # possibly a continuation that omits the repeated header). An image-free page
    # with a section code but no rows -> "H" (section-title sheet: sets the
    # section, nothing to render). Anything else is front matter and skipped.
    entries = []
    for i in range(doc.page_count):
        page = doc[i]
        if page.get_images():
            code, zh, en = parse_header(page)
            entries.append(("D", i, code, zh, en, []))
        else:
            parsed = parse_parts(page)
            if parsed:
                entries.append(("T", i, None, "", "", parsed))
            else:
                code, zh, en = parse_header(page)
                if code:
                    entries.append(("H", i, code, zh, en, []))

    sections = []
    cur_sec = cur_fig = None
    for kind, pno, code, zh, en, parsed in entries:
        if kind == "T":
            if cur_sec is None:
                continue  # a table before any section (front matter) — unexpected
            if cur_fig is None:
                cur_fig = {"draw": [], "parts": [], "seen_tab": False}
                cur_sec["figures"].append(cur_fig)
            cur_fig["parts"].extend(parsed)
            cur_fig["seen_tab"] = True
            continue
        # kind D or H: a page that names its own section reliably
        c = code or (cur_sec["code"] if cur_sec else None)
        if c is None:
            continue  # front matter before any coded section
        if cur_sec is None or cur_sec["code"] != c:
            cur_sec = {"code": c, "chapter": c[:3], "zh": zh, "en": en, "figures": []}
            sections.append(cur_sec)
            cur_fig = None
        else:
            if not cur_sec["zh"] and zh:
                cur_sec["zh"] = zh
            if not cur_sec["en"] and en:
                cur_sec["en"] = en
        if kind == "D":
            # a new drawing after a completed figure (drawing + its table) starts
            # a new figure; consecutive drawings with no table between them share
            # one figure (a multi-sheet illustration -> carousel)
            if cur_fig is None or cur_fig["seen_tab"]:
                cur_fig = {"draw": [], "parts": [], "seen_tab": False}
                cur_sec["figures"].append(cur_fig)
            cur_fig["draw"].append(pno)

    out_sections = []
    total_parts = 0
    for s in sections:
        code = s["code"]
        figures = []
        img_n = 0
        for fig in s["figures"]:
            images = []
            for pno in fig["draw"]:
                img_n += 1
                pix = doc[pno].get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))
                fname = "%s-%d.jpg" % (code, img_n)
                pix.save(os.path.join(OUT_DRAW, fname), jpg_quality=JPEG_QUALITY)
                images.append("drawings/" + fname)
            parts = fig["parts"]
            total_parts += len(parts)
            figures.append({"images": images, "parts": parts})
        # drop empty figures that carry neither a drawing nor a part
        figures = [f for f in figures if f["images"] or f["parts"]]
        out_sections.append({
            "code": code, "chapter": s["chapter"], "zh": s["zh"], "en": s["en"],
            "figures": figures,
        })
        np = sum(len(f["parts"]) for f in figures)
        print("  %-9s %-32s figures=%d draws=%d parts=%d" %
              (code, s["en"][:30], len(figures), img_n, np))

    chapter_list = []
    seen = set()
    for s in out_sections:
        c = s["chapter"]
        if c not in seen:
            seen.add(c)
            names = CHAPTERS.get(c, [c, c])
            chapter_list.append({"code": c, "zh": names[0], "en": names[1]})

    data = {
        "title_zh": "NTE240 矿用自卸车 零部件手册",
        "title_en": "NTE240 Mining Truck — Parts Book",
        "maker": "Inner Mongolia North Hauler Joint Stock Co., Ltd (NHL)",
        "chapters": chapter_list,
        "sections": out_sections,
        "stats": {"sections": len(out_sections), "parts": total_parts},
    }

    os.makedirs(os.path.dirname(OUT_DATA), exist_ok=True)
    with open(OUT_DATA, "w", encoding="utf-8") as fh:
        fh.write("window.CATALOG = ")
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    ndraw = sum(len(f["images"]) for s in out_sections for f in s["figures"])
    print("\nSections: %d  Parts: %d  Drawings: %d" %
          (len(out_sections), total_parts, ndraw))
    print("Wrote", OUT_DATA)


if __name__ == "__main__":
    main()
