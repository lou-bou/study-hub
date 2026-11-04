/* Cahier auto-save for practice pages.
 * Injected by build.py as <script src="/assets/saver.js" data-module=".." data-page="<chapter>/<file>">.
 * Works offline: every edit waits in a device queue until the server confirms it, for any page,
 * and a snapshot of each page's answers lets it restore without a connection. Last write wins.
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

  var QUEUE = "studyhub-queue";                         // '["module","page","key"]' -> value, sent when possible
  var SNAPSHOT = "studyhub-answers:" + MODULE + "/" + PAGE;  // this page's answers, for offline loads
  var RETRY_MS = 30000;
  var PROGRESS = "p:progress";                          // not a field: the sheet's own "N/M", for the hub pages

  var saved = {};          // key -> value as last known here, local edits included
  var timers = {};         // key -> debounce timer
  var pending = {};        // key -> value waiting to be sent
  var inflight = 0, failed = false, deferred = false, flushing = false;
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

  function readStore(name) {
    try { return JSON.parse(localStorage.getItem(name)) || {}; } catch (e) { return {}; }
  }

  function writeStore(name, data) {
    try { localStorage.setItem(name, JSON.stringify(data)); return true; } catch (e) { return false; }
  }

  function queueId(module, page, key) { return JSON.stringify([module, page, key]); }

  // Removes the entry only if it still holds the sent value: a newer edit stays queued.
  function dequeue(id, value) {
    var q = readStore(QUEUE);
    if (q[id] === value) { delete q[id]; writeStore(QUEUE, q); }
  }

  function remember(key, value) {
    if (value === "") delete saved[key]; else saved[key] = value;
    writeStore(SNAPSHOT, saved);
  }

  function put(module, page, key, value, keepalive) {
    var id = queueId(module, page, key);
    return fetch(API, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: module, page: page, key: key, value: value }),
      credentials: "same-origin",
      keepalive: !!keepalive
    }).then(function (r) {
      // 4xx means the server will never accept it (too long, say): retrying can't help
      if (r.status >= 400 && r.status < 500) { dequeue(id, value); failed = true; return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      dequeue(id, value);
    }).catch(function () {
      deferred = true;
    });
  }

  function settle() {
    if (inflight === 0 && !Object.keys(pending).length) {
      setStatus(failed ? "error" : deferred ? "offline" : "saved");
      failed = false; deferred = false;
    }
  }

  function send(key, value, keepalive) {
    inflight++;
    setStatus("saving");
    return put(MODULE, PAGE, key, value, keepalive).then(function () {
      inflight--;
      settle();
    });
  }

  // Sends whatever is still queued, from this page or any other.
  function flushQueue() {
    var q = readStore(QUEUE), ids = Object.keys(q);
    if (flushing || !ids.length) return;
    flushing = true;
    inflight++;
    var chain = Promise.resolve();
    ids.forEach(function (id) {
      var p = JSON.parse(id);
      if (p[0] === MODULE && p[1] === PAGE && Object.prototype.hasOwnProperty.call(pending, p[2])) return;
      chain = chain.then(function () { return put(p[0], p[1], p[2], q[id]); });
    });
    chain.then(function () {
      flushing = false;
      inflight--;
      settle();
    });
  }

  function schedule(key, value) {
    pending[key] = value;
    remember(key, value);
    var q = readStore(QUEUE);
    q[queueId(MODULE, PAGE, key)] = value;
    if (!writeStore(QUEUE, q)) failed = true;
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
      "align-items:center;gap:8px;padding:3px 3px 3px 10px;border-radius:var(--radius-md,8px);background:var(--surface,#FFFCF6);" +
      "border:1px solid var(--border,#E2D8C6);color:var(--text-muted,#5C6475);font:400 var(--text-xs,13px)/1.2 var(--font-body,system-ui,sans-serif)";
    label = document.createElement("span");
    label.textContent = "Loading…";
    var reset = document.createElement("button");
    reset.type = "button";
    reset.textContent = "Reset";
    reset.title = "Delete all saved answers on this page";
    reset.style.cssText = "border:0;border-radius:var(--radius-sm,4px);padding:5px 9px;background:none;" +
      "color:var(--text-muted,#5C6475);font:inherit;cursor:pointer";
    reset.addEventListener("click", function () {
      if (!confirm("Delete all saved answers on this page?")) return;
      pending = {};
      for (var k in timers) clearTimeout(timers[k]);
      timers = {};
      fetch(API + "?module=" + encodeURIComponent(MODULE) + "&page=" + encodeURIComponent(PAGE), {
        method: "DELETE", credentials: "same-origin"
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        var q = readStore(QUEUE);
        Object.keys(q).forEach(function (id) {
          var p = JSON.parse(id);
          if (p[0] === MODULE && p[1] === PAGE) delete q[id];
        });
        writeStore(QUEUE, q);
        writeStore(SNAPSHOT, {});
        location.reload();
      }).catch(function () { alert("Reset needs a connection. Nothing was deleted."); });
    });
    pill.appendChild(label);
    pill.appendChild(reset);
    document.body.appendChild(pill);
  }

  function setStatus(state, n) {
    if (!label) return;
    var text = {
      saving: "Saving…",
      saved: "Saved",
      restored: "Restored " + n + " answer" + (n === 1 ? "" : "s"),
      ready: "Answers auto-save",
      offline: "Saved on this device",
      error: "Not saved ⚠"
    }[state];
    label.textContent = text;
    pill.style.background = state === "error" ? "var(--wrong-bg,#F6E2DF)" : "var(--surface,#FFFCF6)";
    pill.style.color = state === "error" ? "var(--wrong,#B4443A)" : "var(--text-muted,#5C6475)";
    pill.setAttribute("data-state", state);
  }

  // ---- start ---------------------------------------------------------

  function start() {
    buildPill();
    document.addEventListener("input", onEdit, true);
    document.addEventListener("change", onEdit, true);
    window.addEventListener("pagehide", flush);

    window.addEventListener("online", flushQueue);
    setInterval(flushQueue, RETRY_MS);

    function begin(data, offline) {
      saved = data || {};
      // edits still queued for this page are newer than anything the server sent
      var q = readStore(QUEUE);
      Object.keys(q).forEach(function (id) {
        var p = JSON.parse(id);
        if (p[0] !== MODULE || p[1] !== PAGE) return;
        if (q[id] === "") delete saved[p[2]]; else saved[p[2]] = q[id];
      });
      writeStore(SNAPSHOT, saved);
      var n = restoreInto(allFields());
      setStatus(offline ? "offline" : n ? "restored" : "ready", n);
      // let page scripts react (e.g. re-check restored answers)
      document.dispatchEvent(new CustomEvent("studyhub:restored", { detail: { count: n } }));
      new MutationObserver(function (muts) {
        var added = false;
        for (var i = 0; i < muts.length && !added; i++) if (muts[i].addedNodes.length) added = true;
        if (added) restoreInto(allFields());
      }).observe(document.body, { childList: true, subtree: true });
      if (!offline) flushQueue();
      // after page scripts have re-checked what was restored
      setTimeout(watchProgress, 300);
    }

    // Each sheet shows "N / M" in its own way (done boxes, correct answers); keep that for the hub pages.
    function watchProgress() {
      var el = document.getElementById("prog-txt");
      if (!el) return;
      function report() {
        var m = /(\d+)\s*\/\s*(\d+)/.exec(el.textContent || "");
        if (!m || m[2] === "0") return;
        var value = m[1] === "0" ? "" : m[1] + "/" + m[2];
        if (value !== (saved[PROGRESS] || "")) schedule(PROGRESS, value);
      }
      report();
      new MutationObserver(report).observe(el, { childList: true, characterData: true, subtree: true });
    }

    fetch(API + "?module=" + encodeURIComponent(MODULE) + "&page=" + encodeURIComponent(PAGE), {
      credentials: "same-origin", cache: "no-store"
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (data) {
      begin(data, false);
    }, function () {
      begin(readStore(SNAPSHOT), true);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
