/* Cahier PDF viewer: PDF.js, self-hosted. Remembers the last page per PDF with the same ribbon logic as
 * lessons: a chip offers to resume, nothing jumps on its own. URL: /viewer/?f=<path>&t=<title>&b=<back>.
 * The page is stored like an answer: module + "<chapter>/pdfs", key p:pdf:<cours|td>/<file>. */
import * as pdfjs from "/assets/pdfjs/pdf.min.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = "/assets/pdfjs/pdf.worker.min.mjs";

const params = new URLSearchParams(location.search);
const file = params.get("f") || "";
const parts = file.split("/").filter(Boolean);
const $ = (id) => document.getElementById(id);

function fail(message) {
  $("status").textContent = message;
  $("status").hidden = false;
}

const valid = /^\/[^/]/.test(file) && /\.pdf$/i.test(file) && parts.length === 4 && !parts.includes("..");
const back = params.get("b") || (valid ? `/${parts[0]}/#${parts[1]}` : "/");
$("back").href = /^\/[^/]/.test(back) ? back : "/";
$("title").textContent = params.get("t") || parts[parts.length - 1] || "PDF";
document.title = `${$("title").textContent} · Cahier`;

if (!valid) {
  fail("This link doesn't point to a course PDF.");
} else {
  const [module, chapter, kind, name] = parts;
  const page = `${chapter}/pdfs`;
  const key = `p:pdf:${kind}/${name}`;
  const store = `studyhub-pdf:${file}`;
  $("open").href = file;
  window.cahier.bindKeep($("keep"), file);

  let current = 1, ready = false, moved = false, timer = null, sent = 0;
  const holders = [];

  function save() {
    if (!ready || !moved || current === sent) return;  // opening and leaving must not lose the saved page
    sent = current;
    const value = JSON.stringify({ p: current, t: Date.now() });
    try { localStorage.setItem(store, value); } catch (e) {}
    fetch("/api/answers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module, page, key, value }),
      credentials: "same-origin",
      keepalive: true,
    }).catch(() => { sent = 0; });
  }

  async function saved() {
    let local = null, remote = null;
    try { local = JSON.parse(localStorage.getItem(store)); } catch (e) {}
    try {
      const r = await fetch(`/api/answers?module=${encodeURIComponent(module)}&page=${encodeURIComponent(page)}`,
        { credentials: "same-origin", cache: "no-store" });
      if (r.ok) { const d = await r.json(); if (d[key]) remote = JSON.parse(d[key]); }
    } catch (e) {}
    if (!local) return remote;
    if (!remote) return local;
    return (local.t || 0) > (remote.t || 0) ? local : remote;
  }

  async function render(n, doc) {
    const holder = holders[n - 1];
    if (holder.dataset.done) return;
    holder.dataset.done = "1";
    const pdfPage = await doc.getPage(n);
    const box = holder.getBoundingClientRect();
    const base = pdfPage.getViewport({ scale: 1 });
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const viewport = pdfPage.getViewport({ scale: (box.width / base.width) * ratio });
    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    holder.appendChild(canvas);
    await pdfPage.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  }

  (async () => {
    try {
      // whole file, no range requests, so the service worker can keep it for offline
      const doc = await pdfjs.getDocument({ url: file, disableRange: true, disableStream: true, isEvalSupported: false }).promise;
      const first = (await doc.getPage(1)).getViewport({ scale: 1 });
      const pagesEl = $("pages");
      for (let n = 1; n <= doc.numPages; n++) {
        const holder = document.createElement("div");
        holder.className = "pdf-page";
        holder.dataset.page = String(n);
        holder.style.aspectRatio = `${first.width} / ${first.height}`;
        pagesEl.appendChild(holder);
        holders.push(holder);
      }
      $("status").hidden = true;
      $("count").textContent = `1 / ${doc.numPages}`;

      const painter = new IntersectionObserver((entries) => {
        entries.forEach((e) => { if (e.isIntersecting) render(+e.target.dataset.page, doc); });
      }, { rootMargin: "800px 0px" });
      holders.forEach((h) => painter.observe(h));

      const onScroll = () => {
        if (ready) moved = true;
        const mid = window.innerHeight / 2;
        for (const h of holders) {
          const r = h.getBoundingClientRect();
          if (r.top <= mid && r.bottom >= mid) { current = +h.dataset.page; break; }
        }
        $("count").textContent = `${current} / ${doc.numPages}`;
        clearTimeout(timer);
        timer = setTimeout(save, 1500);
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("pagehide", save);
      document.addEventListener("visibilitychange", () => { if (document.hidden) save(); });

      const last = await saved();
      if (last && last.p > 1 && last.p <= doc.numPages) {
        sent = last.p;
        const chip = $("resume");
        chip.lastChild.textContent = `Resume at page ${last.p}`;
        chip.hidden = false;
        chip.addEventListener("click", () => {
          holders[last.p - 1].scrollIntoView({ block: "start" });
          chip.hidden = true;
        });
      }
      ready = true;
    } catch (e) {
      fail(navigator.onLine ? "This PDF couldn't be opened." : "This PDF isn't saved on this device yet.");
    }
  })();
}
