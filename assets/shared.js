/* Cahier: what every page shares. The quiet offline note, keeping a PDF on this device, and
 * announcing check results to screen readers. Loaded on hub pages, remakes and the PDF viewer. */
(function () {
  "use strict";
  var PINNED = "cahier-pinned";

  // ---- desktop sidebar: open, or collapsed to one button. This runs in <head>, so the page never
  // flashes the wrong state. Lessons and sheets always open collapsed. Hub pages remember my choice,
  // and in small windows they start collapsed until I choose. ------------------------------------
  var root = document.documentElement, SIDE = "cahier-side", stored = null, animTimer = null;
  var remake = root.hasAttribute("data-remake");
  try { stored = localStorage.getItem(SIDE); } catch (e) {}
  if (remake || stored === "closed" || (!stored && window.innerWidth < 1000)) root.setAttribute("data-side", "closed");

  function syncSide() {
    var btn = document.getElementById("cahier-side-btn");
    if (!btn) return;
    var closed = root.getAttribute("data-side") === "closed", label = closed ? "Open sidebar" : "Collapse sidebar";
    btn.setAttribute("aria-label", label);
    btn.setAttribute("aria-expanded", closed ? "false" : "true");
    btn.title = label;
  }
  function toggleSide() {
    var closed = root.getAttribute("data-side") === "closed";
    root.setAttribute("data-side-anim", "");
    clearTimeout(animTimer);
    animTimer = setTimeout(function () { root.removeAttribute("data-side-anim"); }, 400);
    if (closed) root.removeAttribute("data-side"); else root.setAttribute("data-side", "closed");
    if (!remake) try { localStorage.setItem(SIDE, closed ? "open" : "closed"); } catch (e) {}
    syncSide();
  }
  document.addEventListener("click", function (e) {
    var el = e.target.closest ? e.target.closest("#cahier-side-btn,#cahier-side-theme") : null;
    if (!el) return;
    if (el.id === "cahier-side-btn") { toggleSide(); return; }
    var theme = document.getElementById("theme-toggle");  // on a remake, the page's own (hidden) toggle
    if (theme) theme.click();
  });
  document.addEventListener("DOMContentLoaded", syncSide);

  // ---- offline note: muted, never blocks reading ----------------------
  var note = document.createElement("div");
  note.textContent = "Offline · progress saved on this device";
  note.setAttribute("role", "status");
  note.setAttribute("data-no-save", "");
  note.id = "cahier-offline";
  note.style.cssText = "position:fixed;left:50%;transform:translateX(-50%);bottom:calc(68px + env(safe-area-inset-bottom,0px));z-index:40;" +
    "padding:4px 12px;border-radius:var(--radius-md,8px);border:1px solid var(--border,#E2D8C6);background:var(--surface-2,#EFE6D6);" +
    "color:var(--text-muted,#5C6475);font:400 var(--text-xs,13px)/1.3 var(--font-body,system-ui,sans-serif);white-space:nowrap;display:none";
  function update() { note.style.display = navigator.onLine ? "none" : "block"; }
  function mount() {
    document.body.appendChild(note);
    update();
    document.querySelectorAll(".fb").forEach(function (f) { f.setAttribute("aria-live", "polite"); });
  }
  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);

  // ---- "Available offline": a PDF kept in its own untrimmed cache -----
  var RIBBON = '<polygon points="20,4 44,4 44,156 32,142 20,156"/>';
  function ribbonSvg(filled) {
    return '<svg class="ribbon' + (filled ? "" : " outline") + '" viewBox="0 0 64 160" aria-hidden="true">' + RIBBON + "</svg>";
  }
  function isKept(url) {
    if (!("caches" in window)) return Promise.resolve(false);
    return caches.open(PINNED).then(function (c) { return c.match(url); }).then(function (r) { return !!r; });
  }
  function setKept(url, keep) {
    return caches.open(PINNED).then(function (c) {
      if (!keep) return c.delete(url);
      return fetch(url, { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return c.put(url, r);
      });
    });
  }
  // A toggle button: outline ribbon, filled once the file is on this device.
  function bindKeep(btn, url) {
    if (!("caches" in window)) { btn.hidden = true; return; }
    function show(kept) {
      btn.innerHTML = ribbonSvg(kept);
      btn.setAttribute("aria-pressed", kept ? "true" : "false");
      btn.setAttribute("aria-label", kept ? "Available offline. Tap to remove" : "Make available offline");
      btn.title = kept ? "Available offline" : "Make available offline";
    }
    isKept(url).then(show);
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      isKept(url).then(function (kept) {
        btn.style.opacity = ".5";
        return setKept(url, !kept).then(function () { show(!kept); });
      }).catch(function () {}).then(function () { btn.style.opacity = ""; });
    });
  }

  // Which device saved a position: "From your laptop" needs a name and an id.
  function device() {
    var id = null;
    try {
      id = localStorage.getItem("cahier-device");
      if (!id) { id = Math.random().toString(36).slice(2, 10); localStorage.setItem("cahier-device", id); }
    } catch (e) { id = "unknown"; }
    return { id: id, name: matchMedia("(max-width:700px)").matches ? "phone" : "laptop" };
  }

  window.cahier = { bindKeep: bindKeep, ribbonSvg: ribbonSvg, device: device };
})();
