/* Acorn reading progress for lesson pages: a thin bar, and resuming where you stopped, on any device.
 * Injected by build.py as <script src="/assets/reading.js" data-module=".." data-page="<chapter>/<file>">.
 * The spot is saved as a section plus a fraction of it, because phone and desktop layouts differ.
 * Stored like an answer under the key p:read as {s, f, m, t}: section id, fraction, furthest percent, time.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var MODULE = me && me.getAttribute("data-module");
  var PAGE = me && me.getAttribute("data-page");
  if (!MODULE || !PAGE) return;

  var API = "/api/answers", KEY = "p:read", STORE = "studyhub-read:" + MODULE + "/" + PAGE;
  var SAVE_MS = 2000, MIN_RESUME = 3;
  var furthest = 0, timer = null, ready = false, sent = "";

  function percent() {
    // rects stay right under the page zoom, in every browser
    var doc = document.documentElement.getBoundingClientRect();
    var range = doc.height - window.innerHeight;
    return range > 0 ? Math.max(0, Math.min(100, -doc.top / range * 100)) : 100;
  }

  function spot() {
    var secs = document.querySelectorAll(".sec[id]"), cur = null;
    for (var i = 0; i < secs.length; i++) {
      if (secs[i].getBoundingClientRect().top <= 1) cur = secs[i]; else break;
    }
    if (!cur) return { s: "", f: 0 };
    var r = cur.getBoundingClientRect();
    return { s: cur.id, f: r.height > 0 ? Math.round(-r.top / r.height * 1000) / 1000 : 0 };
  }

  function readLocal() {
    try { return JSON.parse(localStorage.getItem(STORE)); } catch (e) { return null; }
  }

  function current() {
    var p = spot();
    return { s: p.s, f: p.f, m: Math.round(furthest), t: Date.now() };
  }

  function save(keepalive) {
    clearTimeout(timer); timer = null;
    if (!ready) return;
    var v = current(), mark = v.s + ":" + v.f + ":" + v.m;
    if (mark === sent) return;
    sent = mark;
    var text = JSON.stringify(v);
    try { localStorage.setItem(STORE, text); } catch (e) {}
    fetch(API, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: MODULE, page: PAGE, key: KEY, value: text }),
      credentials: "same-origin",
      keepalive: !!keepalive
    }).catch(function () { sent = ""; });  // offline: the device copy holds it, the next scroll retries
  }

  var bar = document.createElement("div");
  bar.setAttribute("aria-hidden", "true");
  bar.setAttribute("data-no-save", "");
  bar.style.cssText = "position:fixed;top:0;left:0;height:3px;width:0;z-index:30;pointer-events:none;" +
    "background:var(--accent-fill,#f2a922);border-radius:0 2px 2px 0";
  document.body.appendChild(bar);

  function onScroll() {
    var p = percent();
    bar.style.width = p + "%";
    if (p > furthest) furthest = p;
    if (ready && !timer) timer = setTimeout(save, SAVE_MS);
  }

  function resume(v) {
    if (!v) return;
    if (typeof v.m === "number" && v.m > furthest) furthest = v.m;
    // a link to a section, or a page the reader already moved on, wins over the saved spot
    if (location.hash || window.scrollY > 50) return;
    var sec = v.s && document.getElementById(v.s);
    if (!sec) return;
    var r = sec.getBoundingClientRect();
    var y = r.top + window.scrollY + (v.f || 0) * r.height;
    if (y / Math.max(1, document.documentElement.getBoundingClientRect().height) * 100 < MIN_RESUME) return;
    window.scrollTo({ top: y, behavior: "instant" });
  }

  function start(remote) {
    var local = readLocal();
    var best = !remote ? local : !local ? remote : (local.t || 0) > (remote.t || 0) ? local : remote;
    resume(best);
    ready = true;
    onScroll();
    // a newer spot from this device that never reached the server goes up now
    if (local && (!remote || (local.t || 0) > (remote.t || 0))) save();
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  window.addEventListener("pagehide", function () { save(true); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) save(true); });
  onScroll();

  function load() {
    fetch(API + "?module=" + encodeURIComponent(MODULE) + "&page=" + encodeURIComponent(PAGE), {
      credentials: "same-origin", cache: "no-store"
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      var v = null;
      try { v = data[KEY] ? JSON.parse(data[KEY]) : null; } catch (e) {}
      start(v);
    }, function () { start(null); });
  }

  // fonts change the page height, so wait for them before jumping
  var fonts = document.fonts && document.fonts.ready;
  function whenLoaded() { if (fonts) fonts.then(load, load); else load(); }
  if (document.readyState === "complete") whenLoaded();
  else window.addEventListener("load", whenLoaded);
})();
