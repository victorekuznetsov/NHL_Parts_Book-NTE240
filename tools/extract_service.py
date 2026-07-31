#!/usr/bin/env python3
"""
Convert the repair / service manual (NTE240_Service_book) — a folder of per-
section Word files (.doc / .docx), each named with a catalog section code
(NNN-NNNN) — into browsable HTML pages organised BY CATALOG SECTION and linked
from the catalog.

Binary .doc is read directly (olefile piece table for text, signature scan of
the Data stream for PNG/JPEG images) because LibreOffice cannot load these
files here. .docx is read from its XML.

Outputs:
  catalog/service/<code>.html      — one repair page per catalog section
  catalog/service/index.html       — index of all repair pages, by chapter
  catalog/service_media/*          — images
  catalog/data/service.js          — window.SERVICE = { "<code>": "title", ... }

Usage:
  python3 tools/extract_service.py [path/to/NTE240_Service_book_dir]
  (default: sources/active/NTE240_Service_book/ , else reconstruct from
   sources/active/NTE240_Service_book*.zip.0*)

Dependencies: olefile.
"""
import os
import re
import sys
import glob
import html
import struct
import shutil
import zipfile
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import olefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources", "active")
OUT_DIR = os.path.join(ROOT, "catalog", "service")
OUT_MEDIA = os.path.join(ROOT, "catalog", "service_media")
OUT_MANIFEST = os.path.join(ROOT, "catalog", "data", "service.js")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
V = "{urn:schemas-microsoft-com:vml}"
CODE_RE = re.compile(r"(\d{3}-\d{4})")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

CHAPTER_NAMES = {
    "000": "Общие сведения", "020": "Несущие конструкции", "030": "Электрооборудование",
    "040": "Двигатель / силовая установка", "050": "Гидросистема", "070": "Ходовая часть",
    "080": "Тормозная система", "090": "Кабина", "100": "Вспомогательные системы",
    "150": "Шины и диски", "200": "Опции", "260": "Опции",
}


# ---------- source discovery ----------
def service_dir(arg):
    if arg and os.path.isdir(arg):
        return arg
    d = glob.glob(os.path.join(SRC, "NTE240_Service_book*"))
    d = [p for p in d if os.path.isdir(p)]
    if d:
        return d[0]
    parts = sorted(glob.glob(os.path.join(SRC, "NTE240_Service_book*.zip.0*")))
    if not parts:
        raise SystemExit("service book not found (dir or split zip)")
    work = tempfile.mkdtemp(prefix="svc_")
    combined = os.path.join(work, "c.zip")
    with open(combined, "wb") as out:
        for p in parts:
            with open(p, "rb") as fh:
                shutil.copyfileobj(fh, out)
    # unzip returns a non-zero warning code on the book's mojibake filenames but
    # still extracts every file — so don't fail on it; verify by the result.
    subprocess.run(["unzip", "-o", combined, "-d", work],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not [p for p in glob.glob(os.path.join(work, "**", "*"), recursive=True)
            if p.lower().endswith((".doc", ".docx"))]:
        raise SystemExit("failed to extract service book from zip")
    return work


# ---------- binary .doc ----------
def doc_text(wd, tbl):
    flags = struct.unpack("<H", wd[0x0A:0x0C])[0]
    fcClx = struct.unpack("<I", wd[0x01A2:0x01A6])[0]
    lcbClx = struct.unpack("<I", wd[0x01A6:0x01AA])[0]
    clx = tbl[fcClx:fcClx + lcbClx]
    i = 0
    while i < len(clx) and clx[i] == 0x01:                 # skip Prc property runs
        ln = struct.unpack("<H", clx[i + 1:i + 3])[0]
        i += 3 + ln
    if i >= len(clx) or clx[i] != 0x02:                    # no piece table
        fcMin = struct.unpack("<I", wd[0x18:0x1C])[0]
        fcMac = struct.unpack("<I", wd[0x1C:0x20])[0]
        return wd[fcMin:fcMac].decode("utf-16-le", "ignore")
    lcbPlc = struct.unpack("<I", clx[i + 1:i + 5])[0]
    i += 5
    plc = clx[i:i + lcbPlc]
    n = (lcbPlc - 4) // 12
    cps = [struct.unpack("<I", plc[j * 4:j * 4 + 4])[0] for j in range(n + 1)]
    out = []
    for k in range(n):
        pcd = plc[(n + 1) * 4 + k * 8:(n + 1) * 4 + k * 8 + 8]
        fc = struct.unpack("<I", pcd[2:6])[0]
        nch = cps[k + 1] - cps[k]
        if fc & 0x40000000:
            off = (fc & ~0x40000000) // 2
            out.append(wd[off:off + nch].decode("cp1251", "ignore"))
        else:
            out.append(wd[fc:fc + nch * 2].decode("utf-16-le", "ignore"))
    return "".join(out)


def scan_images(blob):
    imgs = []
    i = 0
    while True:
        p = blob.find(b"\x89PNG\r\n\x1a\n", i)
        j = blob.find(b"\xff\xd8\xff", i)
        if p < 0 and j < 0:
            break
        if p >= 0 and (j < 0 or p < j):
            end = blob.find(b"IEND\xaeB`\x82", p)
            if end < 0:
                break
            imgs.append(("png", blob[p:end + 8]))
            i = end + 8
        else:
            end = blob.find(b"\xff\xd9", j)
            if end < 0:
                break
            imgs.append(("jpg", blob[j:end + 2]))
            i = end + 2
    return imgs


def parse_doc(path):
    ole = olefile.OleFileIO(path)
    wd = ole.openstream("WordDocument").read()
    flags = struct.unpack("<H", wd[0x0A:0x0C])[0]
    tblname = "1Table" if (flags >> 9) & 1 else "0Table"
    tbl = ole.openstream(tblname).read() if ole.exists(tblname) else b""
    text = doc_text(wd, tbl)
    data = ole.openstream("Data").read() if ole.exists("Data") else b""
    imgs = scan_images(data) or scan_images(wd)
    return text, imgs


# ---------- .docx ----------
def parse_docx(path):
    z = zipfile.ZipFile(path)
    rels = {}
    if "word/_rels/document.xml.rels" in z.namelist():
        for rel in ET.fromstring(z.read("word/_rels/document.xml.rels")):
            tgt = rel.get("Target") or ""
            if "media/" in tgt:
                rels[rel.get("Id")] = "word/" + tgt.lstrip("/") if not tgt.startswith("word/") else tgt
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    paras = []
    imgs = []
    seen = set()
    for p in body.iter(W + "p"):
        txt = "".join(t.text or "" for t in p.iter(W + "t")).strip()
        if txt:
            paras.append(txt)
        for ref in list(p.iter(V + "imagedata")) + list(p.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")):
            rid = ref.get(R + "id") or ref.get(R + "embed")
            path_in = rels.get(rid)
            if path_in and path_in in z.namelist() and path_in not in seen:
                seen.add(path_in)
                ext = "png" if path_in.lower().endswith("png") else "jpg"
                imgs.append((ext, z.read(path_in)))
    return "\n".join(paras), imgs


# ---------- text -> paragraphs ----------
def clean_paragraphs(text):
    text = re.sub(r"\x13[^\x14\x15]*[\x14\x15]", "", text)   # drop field instructions
    text = text.replace("\x01", "").replace("\x14", "").replace("\x15", "")
    out = []
    for raw in re.split(r"[\r\n]", text):
        line = CTRL.sub("", raw).replace("\x07", "  ").strip()
        line = re.sub(r"\s{3,}", "  ", line)
        if line:
            out.append(line)
    return out


PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Ремонт и обслуживание</title>
<style>
:root{{--ink:#2a3138;--muted:#80868b;--line:#e2e5e8;--accent:#3ef0af;--accent-ink:#0b7d59;--bg:#eef0f2}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.6 Calibri,"Segoe UI",Arial,sans-serif;color:var(--ink);background:var(--bg)}}
.top{{background:var(--ink);color:#fff;display:flex;align-items:center;gap:14px;padding:12px 18px;position:sticky;top:0;z-index:10;border-bottom:2px solid var(--accent)}}
.top .mark{{width:34px;height:34px;border-radius:8px;background:#222a30;display:grid;place-items:center}}
.top .mark svg path{{fill:var(--accent)}}
.top .t1{{font-weight:700}}.top .t2{{color:#b9c0c6;font-size:12px}}
.top a{{color:var(--accent);font-weight:700;text-decoration:none;white-space:nowrap}} .top a:hover{{color:#fff}}
.top .sp{{margin-left:auto;display:flex;gap:16px}}
main{{max-width:1000px;margin:16px auto;background:#fff;padding:26px 34px 80px;border:1px solid var(--line);border-radius:10px}}
main h1{{font-size:22px;margin:0 0 4px}} .code{{color:var(--muted);font-size:13px;margin-bottom:16px}}
.search{{margin:0 0 16px}} .search input{{width:100%;height:38px;border:1px solid #cfd4d9;border-radius:8px;padding:0 12px;font-size:14px}}
p{{margin:7px 0}} figure{{margin:16px 0;text-align:center}} figure img{{max-width:100%;border:1px solid var(--line);border-radius:6px}}
.imgs h2{{font-size:16px;border-top:2px solid var(--accent);padding-top:10px;margin-top:26px}}
mark{{background:#d6fbee}}
</style></head><body>
<div class="top">
  <span class="mark"><svg viewBox="0 0 196 196" width="26" height="26"><path d="M63.5941 165.078 114.786 64.5721 99.6758 31 83.5127 31 16 165.078 63.5941 165.078Z"/><path d="M107.608 118.291 152.342 118.291 179.684 64.5721 164.574 31 119.559 31 134.669 64.5721 107.608 118.291Z"/></svg></span>
  <div><div class="t1">Развитие · Ремонт и обслуживание</div><div class="t2">{title}</div></div>
  <div class="sp">{catlink}<a href="index.html">Все инструкции</a></div>
</div>
<main>
  <h1>{title}</h1><div class="code">{codeline}</div>
  <div class="search"><input id="q" type="search" placeholder="Поиск по тексту раздела…"></div>
  <div id="doc">{body}</div>
</main>
<script>
(function(){{var q=document.getElementById('q'),d=document.getElementById('doc');
var bs=[].slice.call(d.querySelectorAll('p')),o=bs.map(function(b){{return b.innerHTML;}});
q.addEventListener('input',function(){{var v=q.value.trim();bs.forEach(function(b,i){{b.innerHTML=o[i];}});
if(v.length<2)return;var re=new RegExp('('+v.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')+')','gi');
bs.forEach(function(b,i){{if(re.test(b.textContent))b.innerHTML=o[i].replace(re,'<mark>$1</mark>');}});}});}})();
</script></body></html>"""


def main():
    d = service_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    files = [p for p in glob.glob(os.path.join(d, "**", "*"), recursive=True)
             if p.lower().endswith((".doc", ".docx"))]
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    if os.path.isdir(OUT_MEDIA):
        shutil.rmtree(OUT_MEDIA)
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(OUT_MEDIA, exist_ok=True)

    # catalog section names (the repair page is titled by its catalog section)
    cat_name = {}
    try:
        import json
        raw = open(os.path.join(ROOT, "catalog", "data", "parts.js"), encoding="utf-8").read()
        cat = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        for s in cat["sections"]:
            nm = " · ".join(x for x in (s.get("zh"), s.get("en")) if x)
            cat_name[s["code"]] = nm or s["code"]
    except Exception:
        pass

    # group by section code (a section may have >1 file)
    by_code = {}
    for p in sorted(files):
        m = CODE_RE.search(os.path.basename(p))
        code = m.group(1) if m else "000-9999"
        by_code.setdefault(code, []).append(p)

    manifest = {}
    for code, paths in sorted(by_code.items()):
        paras, images = [], []
        for p in paths:
            try:
                text, imgs = parse_docx(p) if p.lower().endswith("docx") else parse_doc(p)
            except Exception as e:
                print("  ! %s: %s" % (os.path.basename(p), e))
                continue
            paras += clean_paragraphs(text) if not p.lower().endswith("docx") else \
                [l for l in text.split("\n") if l.strip()]
            images += imgs
        if not paras and not images:
            continue
        title = cat_name.get(code) or \
            next((x for x in paras if len(x) > 3 and not x[0].isdigit()), code)
        title = title[:90]
        # write images
        img_html = ""
        for n, (ext, blob) in enumerate(images, 1):
            if len(blob) < 900:      # skip tiny icons/bullets
                continue
            fn = "%s_%d.%s" % (code, n, ext)
            with open(os.path.join(OUT_MEDIA, fn), "wb") as fh:
                fh.write(blob)
            img_html += '<figure><img loading="lazy" src="../service_media/%s" alt=""></figure>' % fn
        body = "".join("<p>%s</p>" % html.escape(x) for x in paras)
        if img_html:
            body += '<div class="imgs"><h2>Иллюстрации</h2>%s</div>' % img_html
        catlink = ('<a href="index.html#/s/%s">← Раздел каталога %s</a>' % (code, code)
                   if code[:3] in CHAPTER_NAMES and code[:3] != "000" else "")
        page = PAGE.format(title=html.escape(title), codeline=html.escape(title),
                           code=code, catlink=catlink.replace("index.html", "../index.html"),
                           body=body)
        with open(os.path.join(OUT_DIR, code + ".html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        manifest[code] = title

    # index page grouped by chapter
    idx = ['<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>Инструкции по ремонту и обслуживанию</title>',
           '<style>body{font:15px/1.6 Calibri,"Segoe UI",Arial,sans-serif;color:#2a3138;background:#eef0f2;margin:0}'
           '.top{background:#2a3138;color:#fff;padding:14px 20px;border-bottom:2px solid #3ef0af;display:flex;gap:16px;align-items:center}'
           '.top a{color:#3ef0af;text-decoration:none;margin-left:auto;font-weight:700}'
           'main{max-width:900px;margin:18px auto;background:#fff;border:1px solid #e2e5e8;border-radius:10px;padding:24px 30px 60px}'
           'h2{font-size:17px;border-top:2px solid #3ef0af;padding-top:10px;margin-top:24px}'
           'a.sec{display:block;padding:7px 10px;color:#2a3138;text-decoration:none;border-radius:6px}'
           'a.sec:hover{background:#f0fdf8}.c{color:#80868b;font-variant-numeric:tabular-nums;margin-right:8px}</style></head><body>',
           '<div class="top"><b>Развитие · Инструкции по ремонту и обслуживанию NTE240</b>'
           '<a href="index.html">← К каталогу запчастей</a></div><main>']
    last = None
    for code in sorted(manifest):
        ch = code[:3]
        if ch != last:
            idx.append("<h2>%s · %s</h2>" % (ch, html.escape(CHAPTER_NAMES.get(ch, ch))))
            last = ch
        idx.append('<a class="sec" href="service/%s.html"><span class="c">%s</span>%s</a>'
                   % (code, code, html.escape(manifest[code])))
    idx.append("</main></body></html>")
    with open(os.path.join(ROOT, "catalog", "service.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(idx))

    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        import json
        fh.write("window.SERVICE = ")
        json.dump(manifest, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\n")

    print("Service: %d sections, %d images -> catalog/service/ + service.html"
          % (len(manifest), len(os.listdir(OUT_MEDIA))))


if __name__ == "__main__":
    main()
