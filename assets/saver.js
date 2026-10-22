/* Study Hub auto-save for practice pages.
 * Injected by build.py as <script src="/assets/saver.js" data-module=".." data-page="<chapter>/<file>">.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var MODULE = me && me.getAttribute("data-module");
  var PAGE = me && me.getAttribute("data-page");
  if (!MODULE || !PAGE) return;

  var API = "/api/answers";
  var SKIP_TYPES = { button: 1, submit: 1, reset: 1, hidden: 1, file: 1, password: 1, image: 1 };
  var DEBOUNCE_MS = 400;

  var saved = {};          // key -> value as last known on the server
  var timers = {};         // key -> debounce timer
  var pending = {};        // key -> value waiting to be sent
  var inflight = 0, failed = false;
  var restoring = false;
  var applied = typeof WeakSet === "function" ? new WeakSet() : null;

  // ---- field helpers -------------------------------------------------

  function isField(el) {
    if (!el || !el.tagName) return false;
    var tag = el.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea" && tag !== "select") return false;
    if (tag === "input" && SKIP_TYPES[(el.type || "").toLowerCase()]) return false;
    if (el.closest("[data-no-save]")) return false;
    return true;
  }

  function allFields() {
    var list = document.querySelectorAll("input, textarea, select");
    var out = [];
    for (var i = 0; i < list.length; i++) if (isField(list[i])) out.push(list[i]);
    return out;
  }

  function keyOf(el) {
    var type = (el.type || "").toLowerCase();
    if (type === "radio") return el.name ? "r:" + el.name : null;
    if (type === "checkbox") {
      if (el.id) return "c:" + el.id;
      if (el.name) return "c:" + el.name + ":" + el.value;
      return null;
    }
    if (el.id) return "v:" + el.id;
    if (el.name) return "v:" + el.name;
    return "v:#" + allFields().indexOf(el);
  }

  function valueOf(el) {
    var type = (el.type || "").toLowerCase();
    if (type === "radio") {
      var group = document.querySelectorAll('input[type="radio"]');
      for (var i = 0; i < group.length; i++) {
        if (group[i].name === el.name && group[i].checked && isField(group[i])) return group[i].value;
      }
      return "";
    }
    if (type === "checkbox") return el.checked ? (el.value || "on") : "";
    if (el.tagName.toLowerCase() === "select" && el.multiple) {
      var vals = [];
      for (var j = 0; j < el.options.length; j++) if (el.options[j].selected) vals.push(el.options[j].value);
      return vals.length ? JSON.stringify(vals) : "";
    }
    return el.value;
  }

  function apply(el, value) {
    var type = (el.type || "").toLowerCase();
    var changed = false;
    if (type === "radio") {
      if (el.value === value && !el.checked) { el.checked = true; changed = true; }
    } else if (type === "checkbox") {
      if (!el.checked) { el.checked = true; changed = true; }
    } else if (el.tagName.toLowerCase() === "select" && el.multiple) {
      var vals = [];
      try { vals = JSON.parse(value); } catch (e) { vals = [value]; }
      for (var i = 0; i < el.options.length; i++) el.options[i].selected = vals.indexOf(el.options[i].value) >= 0;
      changed = true;
    } else if (el.value !== value) {
      el.value = value; changed = true;
    }
    if (!changed) return false;
    restoring = true;
    try {
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } finally {
      restoring = false;
    }
    return true;
  }

  // Restore saved values into the given fields; returns the number of keys restored.
  function restoreInto(fields) {
    var keys = {};
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (applied && applied.has(el)) continue;
      var k = keyOf(el);
      if (!k) continue;
      if (Object.prototype.hasOwnProperty.call(saved, k)) {
        var t = (el.type || "").toLowerCase();
        if (t === "radio" && el.value !== saved[k]) continue;
        apply(el, saved[k]);
        keys[k] = 1;
      }
      if (applied) applied.add(el);
    }
    return Object.keys(keys).length;
  }

  // ---- network -------------------------------------------------------

  function send(key, value, keepalive) {
    inflight++;
    setStatus("saving");
    return fetch(API, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: MODULE, page: PAGE, key: key, value: value }),
      credentials: "same-origin",
      keepalive: !!keepalive
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      if (value === "") delete saved[key]; else saved[key] = value;
    }).catch(function () {
      failed = true;
    }).then(function () {
      inflight--;
      if (inflight === 0 && !Object.keys(pending).length) {
        setStatus(failed ? "error" : "saved");
        failed = false;
      }
    });
  }

  function schedule(key, value) {
    pending[key] = value;
    setStatus("saving");
    clearTimeout(timers[key]);
    timers[key] = setTimeout(function () {
      delete timers[key];
      var v = pending[key];
      delete pending[key];
      send(key, v);
    }, DEBOUNCE_MS);
  }

  function flush() {
    for (var k in pending) {
      clearTimeout(timers[k]);
      send(k, pending[k], true);
    }
    pending = {}; timers = {};
  }

  function onEdit(e) {
    if (restoring || !isField(e.target)) return;
    var key = keyOf(e.target);
    if (key) schedule(key, valueOf(e.target));
  }

  // ---- status pill ---------------------------------------------------

  var pill, label;
  function buildPill() {
    pill = document.createElement("div");
    pill.id = "studyhub-saver";
    pill.setAttribute("data-no-save", "");
    pill.setAttribute("role", "status");
    pill.style.cssText = "position:fixed;right:14px;bottom:14px;z-index:2147483000;display:flex;" +
      "align-items:center;gap:8px;padding:6px 6px 6px 12px;border-radius:999px;background:#1f2937;" +
      "color:#fff;font:500 13px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif;" +
      "box-shadow:0 2px 8px rgba(0,0,0,.25);opacity:.92";
    label = document.createElement("span");
    label.textContent = "Loading…";
    var reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = "Reset";
    reset.title = "Delete all saved answers on this page";
    reset.style.cssText = "border:0;border-radius:999px;padding:4px 10px;background:#374151;" +
      "color:#fff;font:inherit;cursor:pointer";
    reset.addEventListener("click", function () {
      if (!confirm("Delete all saved answers on this page?")) return;
      pending = {};
      for (var k in timers) clearTimeout(timers[k]);
      timers = {};
      fetch(API + "?module=" + encodeURIComponent(MODULE) + "&page=" + encodeURIComponent(PAGE), {
        method: "DELETE", credentials: "same-origin"
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        location.reload();
      }).catch(function () { setStatus("error"); });
    });
    pill.appendChild(label);
    pill.appendChild(reset);
    document.body.appendChild(pill);
  }

  function setStatus(state, n) {
    if (!label) return;
    var text = {
      saving: "Saving…",
      saved: "Saved ✓",
      restored: "Restored " + n + " answer" + (n === 1 ? "" : "s"),
      ready: "Answers auto-save",
      error: "Not saved ⚠"
    }[state];
    label.textContent = text;
    pill.style.background = state === "error" ? "#b91c1c" : "#1f2937";
    pill.setAttribute("data-state", state);
  }

  // ---- start ---------------------------------------------------------

  function start() {
    buildPill();
    document.addEventListener("input", onEdit, true);
    document.addEventListener("change", onEdit, true);
    window.addEventListener("pagehide", flush);

    fetch(API + "?module=" + encodeURIComponent(MODULE) + "&page=" + encodeURIComponent(PAGE), {
      credentials: "same-origin", cache: "no-store"
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      saved = data || {};
      var n = restoreInto(allFields());
      setStatus(n ? "restored" : "ready", n);
      // let page scripts react (e.g. re-check restored answers)
      document.dispatchEvent(new CustomEvent("studyhub:restored", { detail: { count: n } }));
      new MutationObserver(function (muts) {
        var added = false;
        for (var i = 0; i < muts.length && !added; i++) if (muts[i].addedNodes.length) added = true;
        if (added) restoreInto(allFields());
      }).observe(document.body, { childList: true, subtree: true });
    }).catch(function () {
      setStatus("error");
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
