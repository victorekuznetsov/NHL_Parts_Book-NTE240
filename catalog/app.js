/* ============================================================
   Interactive NTE240 parts catalog — vanilla JS, no build step.
   Data arrives as globals: window.CATALOG, window.PRICES.
   Opens directly from index.html over file://.
   ============================================================ */
(function () {
  "use strict";

  var CAT = window.CATALOG || { chapters: [], sections: [] };
  var PRICES = window.PRICES || {};
  var CURRENCY = "CNY";

  // ---- helpers ----------------------------------------------------------
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var el = function (tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  };
  function pad(ref) {
    if (ref == null || ref === "") return "";
    return /^\d+$/.test(ref) ? ("00" + ref).slice(-3) : ref;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fmt(n) {
    return (Math.round(n * 100) / 100).toLocaleString("ru-RU",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  // required-quantity default from the on-scheme QTY ("AR"/blank -> 1)
  function defNeed(qty) {
    var m = /^\d+$/.test(qty) ? parseInt(qty, 10) : 1;
    return m > 0 ? m : 1;
  }
  function priceOf(pn) { return PRICES[pn] || null; }

  var sectionByCode = {};
  CAT.sections.forEach(function (s) { sectionByCode[s.code] = s; });
  var chapterName = {};
  CAT.chapters.forEach(function (c) { chapterName[c.code] = c; });

  // flatten a section's parts (single source of truth is figures[].parts)
  function sectionParts(s) {
    var out = [];
    (s.figures || []).forEach(function (f) { (f.parts || []).forEach(function (p) { out.push(p); }); });
    return out;
  }

  // ---- cart (localStorage) ---------------------------------------------
  var CART_KEY = "nte240_cart_v1";
  var SERIAL_KEY = "nte240_serial_v1";
  var cart = load();
  function load() {
    try { return JSON.parse(localStorage.getItem(CART_KEY)) || {}; }
    catch (e) { return {}; }
  }
  function save() {
    try { localStorage.setItem(CART_KEY, JSON.stringify(cart)); } catch (e) {}
    renderCartCount();
  }
  function addToCart(pn, qty, meta) {
    if (!pn) return;
    if (!cart[pn]) cart[pn] = { qty: 0, zh: meta.zh || "", en: meta.en || "" };
    cart[pn].qty += qty;
    if (meta.zh) cart[pn].zh = meta.zh;
    if (meta.en) cart[pn].en = meta.en;
    save();
    toast("Добавлено в заказ: " + pn + " × " + qty);
  }

  // ---- sidebar ----------------------------------------------------------
  function renderSidebar() {
    var root = $("#chapters");
    root.innerHTML = "";
    CAT.chapters.forEach(function (ch) {
      var secs = CAT.sections.filter(function (s) { return s.chapter === ch.code; });
      if (!secs.length) return;
      var wrap = el("div", "chapter collapsed");
      wrap.dataset.code = ch.code;
      var h = el("div", "chap-h");
      h.innerHTML = '<span class="code">' + esc(ch.code) + '</span>' +
        '<span>' + esc(ch.en || ch.zh) + '</span>' +
        '<span class="caret">▾</span>';
      h.addEventListener("click", function () { wrap.classList.toggle("collapsed"); });
      wrap.appendChild(h);
      var ul = el("ul", "sec-list");
      secs.forEach(function (s) {
        var li = el("li");
        li.dataset.code = s.code;
        li.innerHTML = '<span class="code">' + esc(s.code) + '</span>' +
          '<span>' + esc(s.en || s.zh || "") + '</span>';
        li.addEventListener("click", function () { location.hash = "#/s/" + s.code; });
        ul.appendChild(li);
      });
      wrap.appendChild(ul);
      root.appendChild(wrap);
    });
  }
  function highlightSidebar(code) {
    var prev = $(".sec-list li.active");
    if (prev) prev.classList.remove("active");
    if (!code) return;
    var li = $('.sec-list li[data-code="' + code + '"]');
    if (li) {
      li.classList.add("active");
      var chap = li.closest(".chapter");
      if (chap) chap.classList.remove("collapsed");
      li.scrollIntoView({ block: "nearest" });
    }
  }

  // ---- section view -----------------------------------------------------
  function renderSection(code) {
    var s = sectionByCode[code];
    var content = $("#content");
    content.innerHTML = "";
    if (!s) { content.appendChild(el("p", null, "Раздел не найден.")); return; }

    var ch = chapterName[s.chapter] || { code: s.chapter, en: "" };
    var head = el("div", "sec-head");
    var count = sectionParts(s).filter(function (p) { return p.pn; }).length;
    head.innerHTML =
      '<div class="crumb">' + esc(ch.code) + " · " + esc(ch.en || ch.zh || "") + "</div>" +
      "<h1>" + esc(s.code) + " " + esc(s.zh || "") +
      ' <span class="en">' + esc(s.en || "") + "</span></h1>" +
      '<div class="meta">' + (s.figures || []).length + " рис. · " +
      count + " позиц. с номером детали</div>";
    content.appendChild(head);

    var figs = s.figures || [];
    figs.forEach(function (f, i) { content.appendChild(renderFigure(s, f, i, figs.length)); });
    window.scrollTo(0, 0);
  }

  function refRange(parts) {
    var nums = parts.map(function (p) { return parseInt(p.ref, 10); })
      .filter(function (n) { return !isNaN(n); });
    if (!nums.length) return "";
    var lo = Math.min.apply(null, nums), hi = Math.max.apply(null, nums);
    return " · позиции " + pad("" + lo) + "–" + pad("" + hi);
  }

  function renderFigure(s, f, idx, total) {
    var wrap = el("div", "figure");
    var head = el("div", "fig-head");
    head.innerHTML = '<span class="n">Рисунок ' + (idx + 1) + " / " + total + "</span>" +
      '<span class="sub">' + esc(s.code) + refRange(f.parts || []) + "</span>";
    wrap.appendChild(head);

    var body = el("div", "fig-body");
    body.appendChild(renderDrawing(f.images || []));
    body.appendChild(renderParts(f.parts || []));
    wrap.appendChild(body);
    return wrap;
  }

  function renderDrawing(images) {
    var dw = el("div", "drawing-wrap");
    if (!images.length) {
      dw.appendChild(el("div", "no-drawing", "Чертёж не приводится"));
      return dw;
    }
    var idx = 0;
    var car = el("div", "carousel");
    var stage = el("div", "stage");
    var img = el("img");
    img.alt = "Чертёж";
    img.addEventListener("click", function () { openLightbox(img.src); });
    stage.appendChild(img);
    car.appendChild(stage);

    var nav = el("div", "nav");
    var prev = el("button", null, "‹");
    var counter = el("span", "counter");
    var next = el("button", null, "›");
    nav.appendChild(prev); nav.appendChild(counter); nav.appendChild(next);
    car.appendChild(nav);

    function show() {
      img.src = images[idx];
      counter.textContent = (idx + 1) + " / " + images.length;
      prev.disabled = idx === 0;
      next.disabled = idx === images.length - 1;
    }
    prev.addEventListener("click", function () { if (idx > 0) { idx--; show(); } });
    next.addEventListener("click", function () { if (idx < images.length - 1) { idx++; show(); } });
    if (images.length === 1) nav.style.display = "none";
    show();
    dw.appendChild(car);
    return dw;
  }

  // order rows by position number (№). Rows without their own number inherit
  // the previous position so kit sub-items / wrapped names stay under their
  // parent; ties keep the original book order.
  function sortByPos(parts) {
    var last = -1;
    var keyed = parts.map(function (p, i) {
      var m = /^(\d+)/.exec(p.ref || "");
      var own = m ? parseInt(m[1], 10) : null;
      if (own !== null) last = own;
      return { p: p, i: i, n: own !== null ? own : last, refless: own === null ? 1 : 0, s: p.ref || "" };
    });
    keyed.sort(function (a, b) {
      return (a.n - b.n) || (a.refless - b.refless) ||
        (a.s < b.s ? -1 : a.s > b.s ? 1 : 0) || (a.i - b.i);
    });
    return keyed.map(function (k) { return k.p; });
  }

  function renderParts(parts) {
    parts = sortByPos(parts);
    var pw = el("div", "parts-wrap");
    var table = el("table", "parts");
    table.innerHTML =
      "<thead><tr>" +
      '<th class="num">№</th>' +
      "<th>Номер детали</th>" +
      "<th>Наименование</th>" +
      '<th class="price" style="text-align:right">Цена, ' + CURRENCY + "</th>" +
      '<th class="qty">Кол-во</th>' +
      "<th>Нужно</th>" +
      "<th></th>" +
      "</tr></thead>";
    var tb = el("tbody");
    parts.forEach(function (p) { tb.appendChild(renderRow(p)); });
    table.appendChild(tb);
    pw.appendChild(table);
    return pw;
  }

  function renderRow(p) {
    var tr = el("tr", p.lvl ? "lvl" + Math.min(p.lvl, 2) : "");
    var pr = p.pn ? priceOf(p.pn) : null;

    // № + part number
    var pnCell;
    if (p.pn) {
      var xref = pr && pr.x ? '<span class="xref">↔ ' + esc(pr.x) + "</span>" : "";
      pnCell = '<span class="code">' + esc(p.pn) + "</span>" + xref;
    } else {
      tr.classList.add("no-order");
      pnCell = '<span class="muted">—</span>';
    }

    // name: ZH / EN, plus RU from price list when it adds info, plus group chip
    var nameHtml = "";
    if (p.zh) nameHtml += '<div class="zh">' + esc(p.zh) + "</div>";
    if (p.en) nameHtml += '<div class="en">' + esc(p.en) + "</div>";
    if (pr && pr.n) nameHtml += '<div class="ru">' + esc(pr.n) + "</div>";
    if (pr && pr.g) nameHtml += '<span class="grp">' + esc(pr.g) + "</span>";
    if (!nameHtml) nameHtml = '<span class="en">—</span>';

    var priceHtml = pr && pr.p != null ? fmt(pr.p) : '<span class="muted">—</span>';
    var need = defNeed(p.qty);

    tr.innerHTML =
      '<td class="num">' + esc(pad(p.ref)) + "</td>" +
      '<td class="pn">' + pnCell + "</td>" +
      '<td class="name">' + nameHtml + "</td>" +
      '<td class="price">' + priceHtml + "</td>" +
      '<td class="qty">' + esc(p.qty || "") + "</td>";

    if (p.pn) {
      var needTd = el("td");
      var inp = el("input", "need");
      inp.type = "number"; inp.min = "1"; inp.value = need;
      needTd.appendChild(inp);
      tr.appendChild(needTd);
      var addTd = el("td");
      var btn = el("button", "add", "+");
      btn.title = "Добавить в заказ";
      btn.addEventListener("click", function () {
        var q = parseInt(inp.value, 10);
        if (!q || q < 1) q = 1;
        addToCart(p.pn, q, { zh: p.zh, en: p.en });
      });
      addTd.appendChild(btn);
      tr.appendChild(addTd);
    } else {
      tr.appendChild(el("td", "dash", "—"));
      tr.appendChild(el("td", "dash", ""));
    }
    return tr;
  }

  // ---- search -----------------------------------------------------------
  var searchIndex = null;
  function buildIndex() {
    if (searchIndex) return searchIndex;
    searchIndex = [];
    CAT.sections.forEach(function (s) {
      sectionParts(s).forEach(function (p) {
        var pr = p.pn ? priceOf(p.pn) : null;
        searchIndex.push({
          sec: s.code, secEn: s.en || "", p: p,
          hay: [p.pn, p.zh, p.en, pr && pr.n, pr && pr.x].join(" ").toLowerCase()
        });
      });
    });
    return searchIndex;
  }
  function renderSearch(q) {
    var content = $("#content");
    content.innerHTML = "";
    var query = q.trim().toLowerCase();
    var head = el("div", "results-head");
    if (query.length < 2) {
      head.innerHTML = "<h1>Поиск</h1><div class='sub'>Введите минимум 2 символа — номер детали или название.</div>";
      content.appendChild(head);
      return;
    }
    var terms = query.split(/\s+/);
    var hits = buildIndex().filter(function (r) {
      return terms.every(function (t) { return r.hay.indexOf(t) >= 0; });
    });
    head.innerHTML = "<h1>Результаты поиска</h1><div class='sub'>«" + esc(q) + "» — найдено позиций: " +
      hits.length + "</div>";
    content.appendChild(head);

    var bySec = {};
    hits.slice(0, 600).forEach(function (r) { (bySec[r.sec] = bySec[r.sec] || []).push(r.p); });
    Object.keys(bySec).forEach(function (code) {
      var s = sectionByCode[code];
      var block = el("div", "result-sec");
      var rsh = el("div", "rsh", esc(code) + " · " + esc(s ? (s.en || s.zh) : ""));
      rsh.addEventListener("click", function () { location.hash = "#/s/" + code; });
      block.appendChild(rsh);
      block.appendChild(renderParts(bySec[code]));
      content.appendChild(block);
    });
    if (hits.length > 600) content.appendChild(el("p", "sub", "Показаны первые 600 из " + hits.length + " — уточните запрос."));
    window.scrollTo(0, 0);
  }

  // ---- cart UI ----------------------------------------------------------
  function renderCartCount() {
    var n = Object.keys(cart).reduce(function (a, pn) { return a + (cart[pn].qty > 0 ? 1 : 0); }, 0);
    $("#cartCount").textContent = n;
  }
  function renderCart() {
    var box = $("#cartLines");
    box.innerHTML = "";
    var pns = Object.keys(cart).filter(function (pn) { return cart[pn].qty > 0; });
    var total = 0, priced = 0, unpriced = 0;
    if (!pns.length) {
      box.appendChild(el("div", "cart-empty", "Заказ пуст.<br>Добавляйте позиции кнопкой «+» в таблице."));
    }
    pns.forEach(function (pn) {
      var it = cart[pn];
      var pr = priceOf(pn);
      var line = el("div", "cline");
      var each = pr && pr.p != null ? pr.p : null;
      var sum = each != null ? each * it.qty : null;
      if (sum != null) { total += sum; priced++; } else { unpriced++; }
      var nm = (pr && pr.n) || it.en || it.zh || "";
      line.innerHTML =
        '<div class="info"><div class="pn">' + esc(pn) + "</div>" +
        '<div class="nm">' + esc(nm) + "</div>" +
        '<div class="ctrls"><input type="number" min="1" value="' + it.qty + '" data-pn="' + esc(pn) + '">' +
        '<button class="rm" data-pn="' + esc(pn) + '">удалить</button></div></div>' +
        '<div class="sum">' + (sum != null ? fmt(sum) + " " + CURRENCY : "—") +
        (each != null ? '<div class="each">' + fmt(each) + " × " + it.qty + "</div>" : '<div class="each">нет цены</div>') +
        "</div>";
      box.appendChild(line);
    });
    box.querySelectorAll(".cline input").forEach(function (inp) {
      inp.addEventListener("change", function () {
        var q = parseInt(inp.value, 10);
        var pn = inp.dataset.pn;
        if (!q || q < 1) q = 1;
        cart[pn].qty = q; save(); renderCart();
      });
    });
    box.querySelectorAll(".cline .rm").forEach(function (b) {
      b.addEventListener("click", function () { delete cart[b.dataset.pn]; save(); renderCart(); });
    });
    $("#cartTotal").textContent = fmt(total) + " " + CURRENCY;
    var note = priced + " позиц. с ценой";
    if (unpriced) note += " · " + unpriced + " без цены (уточняется)";
    $("#cartNote").textContent = note;
  }
  function openCart() { renderCart(); $("#cart").classList.add("open"); $("#overlay").classList.add("open"); }
  function closeCart() { $("#cart").classList.remove("open"); $("#overlay").classList.remove("open"); }

  // ---- exports ----------------------------------------------------------
  function download(name, text, mime) {
    var blob = new Blob(["﻿" + text], { type: (mime || "text/csv") + ";charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = el("a"); a.href = url; a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 500);
  }
  function csvCell(v) {
    v = v == null ? "" : String(v);
    return /[",;\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }
  function csvRow(arr) { return arr.map(csvCell).join(";"); }

  function exportOrderCsv() {
    var pns = Object.keys(cart).filter(function (pn) { return cart[pn].qty > 0; });
    if (!pns.length) { toast("Заказ пуст"); return; }
    var serial = $("#serial").value.trim();
    var rows = [csvRow(["Номер детали", "Наименование", "Взаимозам. артикул", "Цена, " + CURRENCY,
      "Кол-во", "Сумма, " + CURRENCY, "Группа"])];
    var total = 0;
    pns.forEach(function (pn) {
      var it = cart[pn], pr = priceOf(pn) || {};
      var each = pr.p != null ? pr.p : null;
      var sum = each != null ? each * it.qty : null;
      if (sum != null) total += sum;
      rows.push(csvRow([pn, pr.n || it.en || it.zh || "", pr.x || "",
        each != null ? each : "", it.qty, sum != null ? Math.round(sum * 100) / 100 : "", pr.g || ""]));
    });
    rows.push(csvRow(["", "", "", "", "ИТОГО", Math.round(total * 100) / 100, ""]));
    var head = "Заказ-спецификация NTE240" + (serial ? " · машина " + serial : "") +
      " · " + new Date().toLocaleDateString("ru-RU") + "\n";
    download("NTE240_заказ.csv", head + rows.join("\n"));
  }

  function exportAllNumbers() {
    var rows = [csvRow(["Артикул (Part No.)", "Наименование (RU)", "Description (EN)", "Описание (ZH)",
      "Цена, " + CURRENCY, "Группа", "Взаимозаменяемый артикул", "Разделы"])];
    var uniq = {};
    CAT.sections.forEach(function (s) {
      sectionParts(s).forEach(function (p) {
        if (!p.pn) return;
        var u = uniq[p.pn] || (uniq[p.pn] = { en: p.en || "", zh: p.zh || "", secs: {} });
        u.secs[s.code] = 1;
        if (!u.en && p.en) u.en = p.en;
        if (!u.zh && p.zh) u.zh = p.zh;
      });
    });
    Object.keys(uniq).sort().forEach(function (pn) {
      var u = uniq[pn], pr = priceOf(pn) || {};
      rows.push(csvRow([pn, pr.n || "", u.en, u.zh, pr.p != null ? pr.p : "", pr.g || "", pr.x || "",
        Object.keys(u.secs).sort().join(" ")]));
    });
    download("NTE240_все_номера.csv", rows.join("\n"));
    toast("Экспортировано номеров: " + Object.keys(uniq).length);
  }

  function printOrder() {
    var pns = Object.keys(cart).filter(function (pn) { return cart[pn].qty > 0; });
    if (!pns.length) { toast("Заказ пуст"); return; }
    var serial = $("#serial").value.trim();
    var total = 0, body = "";
    pns.forEach(function (pn, i) {
      var it = cart[pn], pr = priceOf(pn) || {};
      var each = pr.p != null ? pr.p : null, sum = each != null ? each * it.qty : null;
      if (sum != null) total += sum;
      body += "<tr><td>" + (i + 1) + "</td><td>" + esc(pn) + "</td><td>" +
        esc(pr.n || it.en || it.zh || "") + "</td><td style='text-align:right'>" +
        (each != null ? fmt(each) : "—") + "</td><td style='text-align:center'>" + it.qty +
        "</td><td style='text-align:right'>" + (sum != null ? fmt(sum) : "—") + "</td></tr>";
    });
    var w = window.open("", "_blank");
    w.document.write(
      "<html><head><meta charset='utf-8'><title>Заказ NTE240</title><style>" +
      "body{font:13px Arial,sans-serif;padding:24px;color:#2a3138}h1{font-size:18px}" +
      "table{border-collapse:collapse;width:100%;margin-top:12px}th,td{border:1px solid #ccc;padding:6px 8px}" +
      "th{background:#f2f4f5;text-align:left}tfoot td{font-weight:bold}</style></head><body>" +
      "<h1>Заказ-спецификация · NTE240 Mining Truck</h1>" +
      "<div>" + (serial ? "Машина: <b>" + esc(serial) + "</b> · " : "") +
      "Дата: " + new Date().toLocaleDateString("ru-RU") + "</div>" +
      "<table><thead><tr><th>№</th><th>Номер детали</th><th>Наименование</th>" +
      "<th>Цена, " + CURRENCY + "</th><th>Кол-во</th><th>Сумма, " + CURRENCY + "</th></tr></thead><tbody>" +
      body + "</tbody><tfoot><tr><td colspan='5' style='text-align:right'>ИТОГО, " + CURRENCY +
      "</td><td style='text-align:right'>" + fmt(total) + "</td></tr></tfoot></table>" +
      "<p style='margin-top:18px;color:#80868b;font-size:11px'>Цены без НДС. Позиции без цены уточняются отдельно.</p>" +
      "</body></html>");
    w.document.close(); w.focus(); w.print();
  }

  // ---- lightbox + toast -------------------------------------------------
  function openLightbox(src) { $("#lbImg").src = src; $("#lightbox").classList.add("open"); }
  function closeLightbox() { $("#lightbox").classList.remove("open"); }
  var toastT;
  function toast(msg) {
    var t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  // ---- routing ----------------------------------------------------------
  function route() {
    var h = location.hash || "";
    if (h.indexOf("#/s/") === 0) {
      var code = decodeURIComponent(h.slice(4));
      highlightSidebar(code);
      renderSection(code);
      $("#search").value = "";
    } else if (h.indexOf("#/q/") === 0) {
      var q = decodeURIComponent(h.slice(4));
      highlightSidebar(null);
      $("#search").value = q;
      renderSearch(q);
    } else {
      var first = CAT.sections[0];
      if (first) { location.hash = "#/s/" + first.code; return; }
    }
    if (window.innerWidth <= 900) $("#sidebar").classList.remove("open");
  }

  // ---- wire up ----------------------------------------------------------
  function init() {
    renderSidebar();
    renderCartCount();

    var searchT;
    $("#search").addEventListener("input", function () {
      var v = this.value;
      clearTimeout(searchT);
      searchT = setTimeout(function () {
        if (v.trim().length >= 2) location.hash = "#/q/" + encodeURIComponent(v);
        else if (!v.trim() && location.hash.indexOf("#/q/") === 0) history.back();
      }, 220);
    });

    $("#cartBtn").addEventListener("click", openCart);
    $("#cartClose").addEventListener("click", closeCart);
    $("#overlay").addEventListener("click", closeCart);
    $("#clearCart").addEventListener("click", function () {
      if (confirm("Очистить заказ?")) { cart = {}; save(); renderCart(); }
    });
    $("#exportCsv").addEventListener("click", exportOrderCsv);
    $("#printOrder").addEventListener("click", printOrder);
    $("#exportAll").addEventListener("click", exportAllNumbers);

    var serial = $("#serial");
    serial.value = localStorage.getItem(SERIAL_KEY) || "";
    serial.addEventListener("input", function () {
      try { localStorage.setItem(SERIAL_KEY, serial.value); } catch (e) {}
    });

    $("#lbClose").addEventListener("click", closeLightbox);
    $("#lightbox").addEventListener("click", function (e) { if (e.target.id === "lightbox") closeLightbox(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeLightbox(); closeCart(); }
    });
    $("#menuBtn").addEventListener("click", function () { $("#sidebar").classList.toggle("open"); });

    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
