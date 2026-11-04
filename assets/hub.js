/* Cahier hub pages: the Continue card, progress and statuses, course tabs, search.
 * Reads /api/progress and fills in from this device's copies, so it also works offline. */
(function () {
  "use strict";

  // ---- progress data, server first, then anything newer on this device ----
  function localData(data) {
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i), m;
        if ((m = /^studyhub-read:(.+)$/.exec(k))) {
          var v = JSON.parse(localStorage.getItem(k));
          var e = data[m[1]] = data[m[1]] || {};
          if (v && (!e.pos || (v.t || 0) > (e.pos.t || 0))) { e.pos = v; e.read = Math.max(e.read || 0, v.m || 0); }
        } else if ((m = /^studyhub-answers:(.+)$/.exec(k))) {
          var a = JSON.parse(localStorage.getItem(k)) || {};
          if (a["p:progress"]) (data[m[1]] = data[m[1]] || {}).done = a["p:progress"];
        }
      }
    } catch (e) {}
    return data;
  }

  function sheet(data, key, fallback) {
    var m = /^(\d+)\/(\d+)$/.exec((data[key] || {}).done || "");
    return m ? [+m[1], +m[2]] : [0, fallback];
  }

  var CHECK = '<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

  function statusOf(el, state) {
    var s = el.querySelector(".status");
    if (!s) return;
    if (state === "done") { s.className = "status done"; s.innerHTML = CHECK; s.setAttribute("aria-label", "Done"); }
    else if (state === "going") { s.innerHTML = window.cahier.ribbonSvg(true); s.setAttribute("aria-label", "In progress"); }
  }

  function ago(t) {
    var s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
    if (s < 86400) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  }

  function renderContinue(data) {
    var box = document.getElementById("continue"), cat = document.getElementById("catalog");
    if (!box || !cat) return;
    var pages = JSON.parse(cat.textContent), best = null;
    Object.keys(data).forEach(function (k) {
      var p = data[k].pos;
      if (p && pages[k] && (!best || (p.t || 0) > (best.pos.t || 0))) best = { key: k, pos: p };
    });
    if (!best) return;
    var info = pages[best.key], p = best.pos, me = window.cahier.device();
    var a = document.createElement("a");
    a.className = "continue";
    a.href = info.href + "?resume=1";
    var main = document.createElement("div");
    main.className = "continue-main";
    function line(cls, text, tag) { var x = document.createElement(tag || "span"); x.className = cls; x.textContent = text; main.appendChild(x); }
    line("label", "Continue");
    line("", info.course, "h2");
    line("", info.chapter);
    if (p.h || p.n) line("sec-title", (p.n ? "§" + p.n + " · " : "") + p.h);
    var pg = document.createElement("div");
    pg.className = "pg";
    pg.innerHTML = '<span class="pg-track"><span class="pg-fill"></span></span><span></span>';
    pg.querySelector(".pg-fill").style.width = (p.m || 0) + "%";
    pg.lastChild.textContent = (p.m || 0) + "%";
    main.appendChild(pg);
    if (p.i && p.i !== me.id) line("from", "From your " + (p.d || "other device") + " · " + ago(p.t));
    a.innerHTML = window.cahier.ribbonSvg(true);
    a.appendChild(main);
    box.innerHTML = "";
    box.appendChild(a);
  }

  function renderProgress(data) {
    document.querySelectorAll("[data-pages]").forEach(function (el) {
      var pages = JSON.parse(el.getAttribute("data-pages")), n = 0, of = 0;
      Object.keys(pages).forEach(function (k) { var s = sheet(data, k, pages[k]); n += s[0]; of += s[1]; });
      if (!of) return;
      el.hidden = false;
      el.querySelector(".pg-fill").style.width = (100 * n / of) + "%";
      el.querySelector(".pg-txt").textContent = n + " / " + of + " done";
    });
    document.querySelectorAll("[data-key]").forEach(function (a) {
      var key = a.getAttribute("data-key"), d = data[key] || {}, meta = a.querySelector(".row-meta");
      if (a.getAttribute("data-kind") === "practice") {
        var s = sheet(data, key, +a.getAttribute("data-total"));
        if (d.done) {
          if (meta) meta.textContent = s[0] + " / " + s[1];
          statusOf(a, s[0] >= s[1] ? "done" : "going");
        } else if (d.saved && meta) { meta.textContent = d.saved + " saved"; statusOf(a, "going"); }
      } else if (d.read) {
        if (d.read >= 95) { statusOf(a, "done"); if (meta) meta.textContent = "Done"; }
        else { statusOf(a, "going"); if (meta) meta.textContent = d.read + "%"; }
      }
    });
  }

  function apply(data) {
    data = localData(data || {});
    renderContinue(data);
    renderProgress(data);
  }

  fetch("/api/progress", { cache: "no-store", credentials: "same-origin" })
    .then(function (r) { if (!r.ok) throw 0; return r.json(); })
    .then(apply, function () { apply({}); });

  // ---- "Available offline" on PDF rows ---------------------------------
  document.querySelectorAll("[data-keep]").forEach(function (b) {
    window.cahier.bindKeep(b, b.getAttribute("data-keep"));
  });

  // ---- course page tabs ------------------------------------------------
  var bar = document.querySelector(".tabbar");
  if (bar) {
    var tabs = [].slice.call(bar.querySelectorAll("button"));
    var pick = function (name, push) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("data-tab") === name;
        t.setAttribute("aria-selected", on ? "true" : "false");
        document.getElementById("tab-" + t.getAttribute("data-tab")).hidden = !on;
      });
      if (push) history.replaceState(null, "", "#" + name);
    };
    tabs.forEach(function (t) { t.addEventListener("click", function () { pick(t.getAttribute("data-tab"), true); }); });
    var wanted = location.hash.slice(1);
    pick(tabs.some(function (t) { return t.getAttribute("data-tab") === wanted; }) ? wanted : bar.getAttribute("data-default"));
  }

  // ---- search: the index comes from the build, so it works offline ------
  var box = document.getElementById("search-box");
  if (box) {
    var results = document.getElementById("search-results"), index = null;
    var fold = function (s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };
    var run = function () {
      var q = fold(box.value.trim());
      results.innerHTML = "";
      if (q.length < 2 || !index) return;
      var words = q.split(/\s+/), hits = [];
      index.forEach(function (e) {
        var head = fold(e.h + " " + e.c), body = fold(e.x), hay = head + " " + body, score = 0;
        if (!words.every(function (w) { return hay.indexOf(w) >= 0; })) return;
        words.forEach(function (w) { if (head.indexOf(w) >= 0) score += 10; });
        hits.push({ e: e, score: score, at: body.indexOf(words[0]) });
      });
      hits.sort(function (a, b) { return b.score - a.score; });
      if (!hits.length) {
        var none = document.createElement("div");
        none.className = "none";
        none.textContent = "Nothing found for “" + box.value.trim() + "”.";
        results.appendChild(none);
        return;
      }
      var list = document.createElement("div");
      list.className = "rows";
      hits.slice(0, 40).forEach(function (h) {
        var a = document.createElement("a");
        a.className = "hit";
        a.href = h.e.u;
        var title = document.createElement("b");
        title.textContent = h.e.h;
        var meta = document.createElement("span");
        meta.className = "code";
        meta.textContent = "  " + h.e.c;
        a.appendChild(title);
        a.appendChild(meta);
        if (h.at >= 0 && h.e.x) {
          var snip = document.createElement("span");
          snip.className = "snip";
          var from = Math.max(0, h.at - 50);
          snip.textContent = (from ? "…" : "") + h.e.x.substr(from, 150) + "…";
          a.appendChild(snip);
        }
        list.appendChild(a);
      });
      results.appendChild(list);
    };
    fetch("/search.json").then(function (r) { return r.json(); }).then(function (d) { index = d; run(); });
    box.addEventListener("input", run);
    box.focus();
  }
})();
