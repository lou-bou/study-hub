/* Cahier reading progress for lesson pages: a thin amber bar, and a ribbon chip to resume where I stopped.
 * Injected by build.py as <script src="/assets/reading.js" data-module=".." data-page="<chapter>/<file>">.
 * Stored like an answer under the key p:read as {s, f, m, t, h, n, d, i}: section id, fraction through it,
 * furthest percent, time, section heading and number, device name and id. A section plus a fraction
 * survives the different phone and desktop layouts. It never jumps on its own: the chip asks first, and
 * only the Continue card (?resume=1) lands straight at the spot.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var MODULE = me && me.getAttribute("data-module");
  var PAGE = me && me.getAttribute("data-page");
  if (!MODULE || !PAGE) return;

  var API = "/api/answers", KEY = "p:read", STORE = "studyhub-read:" + MODULE + "/" + PAGE;
  var SAVE_MS = 2000, MIN_RESUME = 3;
  var furthest = 0, timer = null, ready = false, sent = "", chip = null, known = null, moved = false, startY = 0;
  var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    if (!cur) return { s: "", f: 0, h: "", n: "" };
    var r = cur.getBoundingClientRect(), h2 = cur.querySelector("h2"), num = cur.querySelector(".num"), head = "";
    if (h2) {
      var copy = h2.cloneNode(true);
      copy.querySelectorAll(".fr").forEach(function (x) { x.remove(); });
      head = copy.textContent.trim();
    }
    return {
      s: cur.id, f: r.height > 0 ? Math.round(-r.top / r.height * 1000) / 1000 : 0,
      h: head, n: num ? num.textContent.trim() : ""
    };
  }

  function readLocal() {
    try { return JSON.parse(localStorage.getItem(STORE)); } catch (e) { return null; }
  }

  function save(keepalive) {
    clearTimeout(timer); timer = null;
    if (!ready || !moved) return;  // opening a lesson and leaving must not lose the saved place
    var p = spot();
    if (!p.s && known && known.s) p = { s: known.s, f: known.f, h: known.h, n: known.n };  // back at the top keeps it
    var dev = window.cahier ? window.cahier.device() : { id: "", name: "" };
    var v = { s: p.s, f: p.f, m: Math.round(furthest), t: Date.now(), h: p.h, n: p.n, d: dev.name, i: dev.id };
    known = v;
    var mark = v.s + ":" + v.f + ":" + v.m;
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
  bar.style.cssText = "position:fixed;top:0;left:0;height:3px;width:0;z-index:30;pointer-events:none;background:var(--accent,#D9952B)";
  document.body.appendChild(bar);

  function onScroll() {
    var p = percent();
    bar.style.width = p + "%";
    if (p > furthest) furthest = p;
    if (ready && Math.abs(window.scrollY - startY) > 40) moved = true;
    if (ready && moved && !timer) timer = setTimeout(save, SAVE_MS);
  }

  function target(v) {
    var sec = v.s && document.getElementById(v.s);
    if (!sec) return null;
    var r = sec.getBoundingClientRect();
    return r.top + window.scrollY + (v.f || 0) * r.height;
  }

  function go(v, smooth) {
    if (chip) { chip.remove(); chip = null; }  // first: it takes up height above the target
    var y = target(v);
    if (y !== null) window.scrollTo({ top: y, behavior: smooth && !reduced ? "smooth" : "instant" });
  }

  function offerResume(v) {
    var y = target(v);
    if (y === null) return;
    if (y / Math.max(1, document.documentElement.getBoundingClientRect().height) * 100 < MIN_RESUME) return;
    var hero = document.querySelector(".hero");
    if (!hero) return;
    chip = document.createElement("button");
    chip.type = "button";
    chip.className = "resume-chip";
    chip.setAttribute("data-no-save", "");
    var label = "Resume at " + (v.n ? "§" + v.n : "your place") + (v.h ? " · " + v.h : "");
    chip.innerHTML = '<svg viewBox="0 0 64 160" aria-hidden="true" fill="var(--accent,#D9952B)"><polygon points="20,0 44,0 44,160 32,146 20,160"/></svg>';
    chip.appendChild(document.createTextNode(label));
    chip.addEventListener("click", function () { go(v, true); });
    hero.parentNode.insertBefore(chip, hero.nextSibling);
  }

  function start(remote) {
    var local = readLocal();
    var best = !remote ? local : !local ? remote : (local.t || 0) > (remote.t || 0) ? local : remote;
    known = best;
    if (best) {
      if (typeof best.m === "number" && best.m > furthest) furthest = best.m;
      var wants = /[?&]resume=1\b/.test(location.search);
      if (wants && window.scrollY < 50) go(best, false);
      else if (!location.hash && window.scrollY <= 50) offerResume(best);
    }
    startY = window.scrollY;
    ready = true;
    onScroll();
    // a newer spot from this device that never reached the server goes up now
    if (local && (!remote || (local.t || 0) > (remote.t || 0))) { sent = ""; pushLocal(local); }
  }

  function pushLocal(v) {
    fetch(API, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: MODULE, page: PAGE, key: KEY, value: JSON.stringify(v) }),
      credentials: "same-origin"
    }).catch(function () {});
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

  // fonts change the page height, so wait for them before measuring
  var fonts = document.fonts && document.fonts.ready;
  function whenLoaded() { if (fonts) fonts.then(load, load); else load(); }
  if (document.readyState === "complete") whenLoaded();
  else window.addEventListener("load", whenLoaded);
})();
