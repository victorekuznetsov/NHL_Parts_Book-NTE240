#!/usr/bin/env python3
"""
Convert the operator / service manual (.docx) into a browsable, self-contained
HTML page inside the catalog, linked from the catalog header.

Source: ``Руководство_оператора_NTE240_Полюс.docx`` (Russian text + inline
images + tables). Output:
  catalog/manual.html          — styled, searchable document (matches the catalog)
  catalog/manual_media/*.png    — its images

Usage:
  python3 tools/extract_manual.py ["path/to/manual.docx"]
"""
import os
import re
import sys
import glob
import html
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_HTML = os.path.join(ROOT, "catalog", "manual.html")
OUT_MEDIA = os.path.join(ROOT, "catalog", "manual_media")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
V = "{urn:schemas-microsoft-com:vml}"


def default_docx():
    cand = glob.glob(os.path.join(ROOT, "*уковод*.docx")) + \
        glob.glob(os.path.join(ROOT, "*perator*.docx")) + glob.glob(os.path.join(ROOT, "*.docx"))
    if not cand:
        raise SystemExit("manual .docx not found; pass its path")
    return cand[0]


# Reverse cross-reference: a manual heading that mentions a system links to the
# matching catalog chapter. Order matters — most specific keyword first.
MANUAL_TO_CHAPTER = [
    ("тормоз", "080", "Тормозная система"),
    ("кондицион", "090", "Кабина"), ("сиден", "090", "Кабина"),
    ("зеркал", "090", "Кабина"), ("кабин", "090", "Кабина"),
    ("рулев", "050", "Гидросистема / рулевое"), ("руль", "050", "Гидросистема / рулевое"),
    ("гидравл", "050", "Гидросистема"),
    ("шина", "150", "Шины и диски"), ("обод", "150", "Шины и диски"),
    ("подвеск", "070", "Ходовая часть"), ("ступиц", "070", "Ходовая часть"),
    ("мост", "070", "Ходовая часть"),
    ("инвертор", "600", "Система привода (инвертор)"),
    ("контактор", "600", "Система привода (инвертор)"),
    ("электродвигател", "600", "Система привода (инвертор)"),
    ("турбо", "700", "Двигатель Cummins QSK60"),
    ("топлив", "700", "Двигатель Cummins QSK60"),
    ("cummins", "700", "Двигатель Cummins QSK60"),
    ("двигател", "700", "Двигатель Cummins QSK60"),
    ("генератор", "600", "Система привода (генератор)"),
    ("аккумулятор", "030", "Электрооборудование"),
    ("реле", "030", "Электрооборудование"), ("датчик", "030", "Электрооборудование"),
    ("фар", "030", "Электрооборудование"), ("свет", "030", "Электрооборудование"),
    ("электр", "030", "Электрооборудование"),
    ("смазк", "100", "Смазка / вспомогательные"),
    ("огнетуш", "100", "Вспомогательные системы"),
    ("взвешив", "100", "Вспомогательные системы"),
    ("платформ", "020", "Несущие конструкции"), ("кузов", "020", "Несущие конструкции"),
    ("лестниц", "020", "Несущие конструкции"), ("рама", "020", "Несущие конструкции"),
]


def catalog_link(heading):
    low = heading.lower()
    for kw, code, label in MANUAL_TO_CHAPTER:
        if kw in low:
            return ('<a class="cat-xref" href="index.html#/ch/%s">🔧 %s в каталоге →</a>'
                    % (code, html.escape(label)))
    return ""


def para_text(p):
    return "".join(t.text or "" for t in p.iter(W + "t"))


def para_style(p):
    ppr = p.find(W + "pPr")
    if ppr is None:
        return ""
    st = ppr.find(W + "pStyle")
    return st.get(W + "val") if st is not None else ""


def para_images(p, rels):
    out = []
    for img in p.iter(V + "imagedata"):
        rid = img.get(R + "id")
        if rid in rels:
            out.append(rels[rid])
    return out


def cell_text(tc):
    return " ".join(para_text(p) for p in tc.findall(W + "p")).strip()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else default_docx()
    z = zipfile.ZipFile(src)

    rels_xml = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    rels = {}
    for rel in rels_xml:
        tgt = rel.get("Target")
        if tgt and "media/" in tgt:
            rels[rel.get("Id")] = os.path.basename(tgt)

    # export images
    if os.path.isdir(OUT_MEDIA):
        shutil.rmtree(OUT_MEDIA)
    os.makedirs(OUT_MEDIA, exist_ok=True)
    used = set()
    for name in z.namelist():
        if name.startswith("word/media/"):
            base = os.path.basename(name)
            with z.open(name) as fh, open(os.path.join(OUT_MEDIA, base), "wb") as out:
                out.write(fh.read())

    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    parts = []
    headings = []           # (level, id, text) for the contents sidebar
    hid = 0
    title = "Руководство оператора NTE240"

    for el in body:
        if el.tag == W + "p":
            style = para_style(el)
            txt = para_text(el).strip()
            imgs = para_images(el, rels)
            for im in imgs:
                if im in used:
                    continue
                used.add(im)
                parts.append('<figure><img loading="lazy" src="manual_media/%s" alt=""></figure>' % im)
            if not txt:
                continue
            if style in ("1", "2"):               # heading 1 / heading 2
                hid += 1
                lvl = 2 if style == "1" else 3
                headings.append((lvl, "h%d" % hid, txt))
                parts.append('<h%d id="h%d">%s %s</h%d>'
                             % (lvl, hid, html.escape(txt), catalog_link(txt), lvl))
            elif style in ("10", "20"):           # table-of-contents entries — skip
                continue
            else:
                parts.append("<p>%s</p>" % html.escape(txt))
        elif el.tag == W + "tbl":
            rows = ""
            for tr in el.findall(W + "tr"):
                cells = tr.findall(W + "tc")
                tag = "td"
                rows += "<tr>" + "".join(
                    "<%s>%s</%s>" % (tag, html.escape(cell_text(tc)), tag) for tc in cells) + "</tr>"
            if rows:
                parts.append('<div class="tbl-wrap"><table>%s</table></div>' % rows)

    toc = "".join('<a class="lvl%d" href="#%s">%s</a>' % (l, i, html.escape(t)) for l, i, t in headings)
    doc_html = "\n".join(parts)

    page = MANUAL_TEMPLATE.replace("{{TITLE}}", html.escape(title)) \
        .replace("{{TOC}}", toc).replace("{{BODY}}", doc_html)
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(page)

    print("Manual: %d blocks, %d headings, %d images -> %s"
          % (len(parts), len(headings), len(os.listdir(OUT_MEDIA)),
             os.path.relpath(OUT_HTML, ROOT)))


MANUAL_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}} — Развитие</title>
<style>
:root{--ink:#2a3138;--muted:#80868b;--line:#e2e5e8;--accent:#3ef0af;--accent-ink:#0b7d59;--bg:#eef0f2}
*{box-sizing:border-box}
body{margin:0;font:15px/1.6 Calibri,"Segoe UI",Arial,sans-serif;color:var(--ink);background:var(--bg)}
.top{background:var(--ink);color:#fff;display:flex;align-items:center;gap:14px;padding:12px 18px;position:sticky;top:0;z-index:10;border-bottom:2px solid var(--accent)}
.top .mark{width:34px;height:34px;border-radius:8px;background:#222a30;display:grid;place-items:center}
.top .mark svg path{fill:var(--accent)}
.top a.back{margin-left:auto;color:var(--accent);font-weight:700;text-decoration:none}
.top a.back:hover{color:#fff}
.top .t1{font-weight:700}.top .t2{color:#b9c0c6;font-size:12px}
.wrap{display:flex;align-items:flex-start;max-width:1200px;margin:0 auto}
nav.toc{width:300px;flex:none;position:sticky;top:60px;height:calc(100vh - 60px);overflow:auto;padding:16px 10px;font-size:13px}
nav.toc a{display:block;color:var(--ink);text-decoration:none;padding:4px 8px;border-radius:6px;border-left:3px solid transparent}
nav.toc a:hover{background:#fff}
nav.toc a.lvl3{padding-left:22px;color:#5a626a;font-size:12.5px}
main{flex:1;min-width:0;background:#fff;margin:16px;padding:26px 34px 80px;border:1px solid var(--line);border-radius:10px}
main h1{font-size:24px;margin:0 0 18px}
main h2{font-size:20px;margin:30px 0 10px;padding-top:8px;border-top:2px solid var(--accent)}
main h3{font-size:16px;margin:20px 0 8px;color:#333}
.cat-xref{font-size:12px;font-weight:600;color:var(--accent-ink);text-decoration:none;
  border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-left:8px;white-space:nowrap;vertical-align:middle}
.cat-xref:hover{background:#f0fdf8;border-color:var(--accent)}
main p{margin:8px 0}
figure{margin:14px 0;text-align:center}
figure img{max-width:100%;border:1px solid var(--line);border-radius:6px}
.tbl-wrap{overflow-x:auto;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13px}
td{border:1px solid var(--line);padding:6px 9px;vertical-align:top}
tr:nth-child(odd) td{background:#fafcfb}
.search{margin:0 0 16px}
.search input{width:100%;height:38px;border:1px solid #cfd4d9;border-radius:8px;padding:0 12px;font-size:14px}
mark{background:#d6fbee}
@media(max-width:900px){nav.toc{display:none}}
</style>
</head>
<body>
<div class="top">
  <span class="mark"><svg viewBox="0 0 196 196" width="26" height="26"><path d="M63.5941 165.078 114.786 64.5721 99.6758 31 83.5127 31 16 165.078 63.5941 165.078Z"/><path d="M107.608 118.291 152.342 118.291 179.684 64.5721 164.574 31 119.559 31 134.669 64.5721 107.608 118.291Z"/></svg></span>
  <div><div class="t1">Развитие · Руководство по эксплуатации и обслуживанию</div><div class="t2">{{TITLE}}</div></div>
  <a class="back" id="backLink" href="index.html">← К каталогу запчастей</a>
</div>
<div class="wrap">
  <nav class="toc">{{TOC}}</nav>
  <main>
    <h1>{{TITLE}}</h1>
    <div class="search"><input id="q" type="search" placeholder="Поиск по тексту руководства…"></div>
    <div id="doc">{{BODY}}</div>
  </main>
</div>
<script>
(function(){
  var q=document.getElementById('q'), doc=document.getElementById('doc');
  var blocks=[].slice.call(doc.querySelectorAll('h2,h3,p,td'));
  var orig=blocks.map(function(b){return b.innerHTML;});
  function run(v){
    var first=null;
    blocks.forEach(function(b,i){ b.innerHTML=orig[i]; });
    if(v.length<2) return null;
    var re=new RegExp('('+v.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+')','gi');
    blocks.forEach(function(b,i){
      if(re.test(b.textContent)){ b.innerHTML=orig[i].replace(re,'<mark>$1</mark>'); if(!first) first=b; }
    });
    return first;
  }
  q.addEventListener('input',function(){ run(q.value.trim()); });
  // deep-link support: ?q=<topic> pre-searches, ?from=<section> shows a
  // "back to that catalog section" link for a clean round trip.
  var params=new URLSearchParams(location.search);
  var from=params.get('from');
  if(from){
    var bl=document.getElementById('backLink');
    bl.textContent='← Вернуться в раздел каталога '+from;
    bl.href='index.html#/s/'+encodeURIComponent(from);
  }
  var qp=params.get('q');
  if(qp){ q.value=qp; var f=run(qp.trim()); if(f) f.scrollIntoView({block:'center'}); }
})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
