/* Cahier loading splash: once the logo has put itself together and the page has its progress, the
 * logo flies to the real one in the header while the background fades, so there is no visible swap.
 * The markup and CSS are in hub_template.html; hub.js sets data-hub-ready when its data is in. */
(function () {
  "use strict";
  var MAX_WAIT_MS = 5000;  // never hang on a slow API; a CSS fallback covers this script failing
  var splash = document.getElementById("splash");
  if (!splash) return;
  if (document.documentElement.hasAttribute("data-no-splash")) { splash.remove(); return; }

  function sleep(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }
  function loading() { return !document.documentElement.hasAttribute("data-hub-ready") && performance.now() < MAX_WAIT_MS; }

  // The sidebar's logo on desktop, the top bar's on phones. A collapsed sidebar has none to land on.
  function landingRect() {
    var logos = document.querySelectorAll(".brand img");
    for (var i = 0; i < logos.length; i++) {
      var rect = logos[i].getBoundingClientRect();
      if (rect.width > 0 && getComputedStyle(logos[i]).visibility !== "hidden") return rect;
    }
    return null;
  }

  async function dismiss() {
    var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    await sleep(reduced ? 200 : 900);  // let the parts land
    while (loading()) await sleep(50);
    if (reduced) { splash.remove(); return; }

    // Leave at the end of a sway, when the ribbon hangs straight, so it doesn't jump.
    var sway = splash.querySelector(".splash-sway");
    await Promise.race([
      new Promise(function (resolve) { sway.addEventListener("animationiteration", resolve, { once: true }); }),
      sleep(700)
    ]);
    splash.classList.add("splash-leaving");

    var mark = splash.querySelector(".splash-mark"), from = mark.getBoundingClientRect(), to = landingRect();
    var timing = { duration: 450, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" };
    splash.querySelector(".splash-bg").animate([{ opacity: 1 }, { opacity: 0 }], timing);
    // rects are in screen px, transforms in the page's px (divided by the html zoom)
    var zoom = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
    var flight = to
      ? mark.animate([{ transform: "none" }, {
          transform: "translate(" + (to.left - from.left) / zoom + "px," + (to.top - from.top) / zoom + "px) scale(" + to.height / from.height + ")"
        }], timing)
      : mark.animate([{ opacity: 1 }, { opacity: 0 }], timing);
    await flight.finished;
    splash.remove();
  }

  dismiss().catch(function () { splash.remove(); });
})();
