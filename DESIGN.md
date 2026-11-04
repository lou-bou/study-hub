# Cahier — design spec

Hand-off spec for building the Cahier UI. Read this fully before touching styles.
Stack: plain HTML, CSS and JavaScript (no framework), small Python + SQLite backend, self-hosted
behind a Cloudflare Tunnel. Website on desktop, installable PWA on phone, works offline. Single user.

## 1. Identity

- **Name:** Cahier (French: notebook). Always "Cahier" in UI text, `cahier` in code.
- **What it is:** my master's courses (Big Data Analytics, USTHB) in one place — interactive lessons,
  practice sheets and the original PDFs — with saved answers and resume-where-I-stopped on any device.
- **Personality:** "editorial paper". A well-made printed course notebook: calm, warm paper, ink text,
  one amber ribbon marking where I am. Reading comfort beats decoration every time.
- **The ribbon is the brand.** Amber = "my place / my progress". Use it for resume points, bookmarks and
  progress bars, and almost nothing else.

## 2. Files in this kit

| File | Use |
|---|---|
| `assets/tokens.css` | All colors, fonts, spacing, radii, motion. Link it first on every page. **Never hard-code a hex value** — add a token if one is missing. |
| `assets/logo.svg` | Full mark: navy notebook, tick, amber ribbon. Works on paper and on dark. |
| `assets/ribbon.svg` | Ribbon alone — use as a "resume here" marker, loading indicator, or tiny brand accent. |
| `assets/icons/favicon.svg` | Browser favicon (navy tile, tick + ribbon). |
| `assets/icons/cahier-icon.svg` | Full-bleed square, maskable-safe. Source for PWA icons. |
| `assets/icons/*.png` | Pre-rendered: `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` (180), `favicon-32.png`. |

**Wordmark:** live text, no file. Mark + "Cahier" in `--font-display` (Fraunces), weight 600,
optical size high (`font-variation-settings: "opsz" 72`), `letter-spacing: -0.01em`.

## 3. Color

Light ("paper") is the default; dark ("night ink") via the OS or the `data-theme` toggle on `<html>`.

| Role | Token | Light | Notes |
|---|---|---|---|
| Page | `--bg` | #F7F1E6 | warm paper, never pure white |
| Cards, lesson column | `--surface` | #FFFCF6 | |
| Inputs, code, hovered rows | `--surface-2` | #EFE6D6 | |
| Hairlines | `--border` | #E2D8C6 | |
| Body text / headings | `--text` | #1E2A44 ink navy | never pure black |
| Secondary text | `--text-muted` | #5C6475 | |
| Ribbon / progress fills | `--accent` | #D9952B amber | fills only |
| Amber as text | `--accent-text` | #8A5A12 | AA on paper |
| Links | `--link` | #1E4FA0 | underlined |
| Correct answer | `--correct` / `--correct-bg` | green | + check icon |
| Wrong answer | `--wrong` / `--wrong-bg` | brick red | + x icon |
| "In plain words", worked examples | `--note-bg` | #FBF0D9 | |

Rules: correct/wrong are never color-only (always icon + word). Amber is never used for errors or warnings.

## 4. Typography

Self-host all fonts (woff2 in `assets/fonts/`) and precache them — **no Google Fonts CDN**, the app must
work offline. Use the variable versions.

| Role | Font | Weight | Size |
|---|---|---|---|
| Lesson title (hero) | Fraunces | 600 | `--text-2xl` |
| Section headings (h2/h3) | Fraunces | 600 / 500 | `--text-xl` / `--text-lg` |
| Body, UI | Source Sans 3 | 400 / 600 | `--text-md`, line-height `--leading-body` |
| Code, formulas, cipher tables | JetBrains Mono | 400 | `--text-sm` |
| Small labels, metadata | Source Sans 3 | 600 | `--text-xs`, muted |

- Lesson text column max width `--measure` (68ch). Never let paragraphs run full-width on desktop.
- French terms in parentheses next to English key terms: render the French in italic, `--text-muted`
  — e.g. **Shortest path** *(plus court chemin)*.
- Math: KaTeX, self-hosted, inherits `--text`.

## 5. Space, shape, elevation

- 4px grid via `--space-*`. Generous vertical rhythm: `--space-7` between lesson sections.
- Quiet radii: `--radius-sm` inputs/buttons, `--radius-md` cards, `--radius-lg` sheets.
- No drop shadows; layer with `--surface` on `--bg` and 1px `--border`. Paper doesn't glow.

## 6. Structure & screens

Desktop: left sidebar (courses → lessons) + centered lesson column. Mobile: top bar + bottom nav
(Home · Courses · Practice · Search).

1. **Home ("Continue")** — the first thing is a single **Continue** card: course, lesson, section title,
   amber progress bar, and a ribbon icon. One tap lands at the exact saved scroll/section. Below it:
   courses grid (THOR, OPL, GBD, SSAD…) with per-course progress.
2. **Course page** — lessons list with status per lesson: not started (empty circle), in progress
   (amber ribbon + %), done (green check). Three tabs: Lessons · Practice · PDFs.
3. **Lesson page** — keep the existing remake format (it IS this design system):
   hero with a figure → contents grid → numbered sections, each with an **In plain words** box
   (`--note-bg`, left 3px amber border, radius 0 on that side), keyword definitions, SVG figures and a
   **Worked example** box → **Notes on the original course** box at the end (`--surface-2`, muted).
   A thin amber reading-progress bar sits at the very top of the viewport.
4. **Practice sheet** — one problem per card; aids (alphabet strip, lookup tables) shown above the input
   in mono on `--surface-2`. Check → card border + badge switch to correct/wrong colors with icon.
   "Show solution" is a ghost button. Answers autosave (small "Saved" in muted text, no toasts).
5. **PDF viewer** — embedded viewer on desktop; on mobile, open full-screen with a back bar.
   Remember last page per PDF (same ribbon logic).

### Resume behaviour (the core feature — design it carefully)

- Save position = course + lesson + section id + scroll offset, debounced, per device, synced to the
  backend when online.
- When opening a lesson with a saved position, show a ribbon chip under the hero:
  "Resume at §4 · Huffman coding" → tap scrolls there. Don't auto-jump without asking.
- If another device has a newer position, the Continue card shows "From your laptop · 2h ago".

## 7. Motion

Minimal. `--dur-fast` hovers, `--dur-med` sheets and the correct/wrong state change. Smooth scroll for
in-page jumps, disabled under `prefers-reduced-motion`. No celebratory animations — a finished lesson
gets a green check, nothing more.

## 8. PWA & offline

- `manifest.webmanifest`:
  ```json
  {
    "name": "Cahier",
    "short_name": "Cahier",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#F7F1E6",
    "theme_color": "#1E2A44",
    "icons": [
      { "src": "/assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
      { "src": "/assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
      { "src": "/assets/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
    ]
  }
  ```
- `<link rel="icon" href="/assets/icons/favicon.svg" type="image/svg+xml">` + `favicon-32.png` + `apple-touch-icon.png`.
- `<meta name="theme-color">` follows the theme (`#1E2A44` dark, `#F7F1E6` light).
- Each lesson/sheet/PDF gets an "Available offline" toggle (ribbon icon outline → filled when cached).
- Offline: a muted pill "Offline · progress saved on this device". Never block reading.

## 9. Accessibility

- Text contrast ≥ 4.5:1 in both themes; don't lighten `--text-muted`.
- Focus ring: `outline: 2px solid var(--focus); outline-offset: 2px`.
- Tap targets ≥ 44px. Practice inputs have real `<label>`s.
- SVG figures in lessons carry `role="img"` + `<title>`. Correct/wrong results announced via `aria-live`.

## 10. Don'ts

- No pure white backgrounds, no pure black text.
- No gradients, glass, shadows, emoji in UI chrome.
- No new accent colors per course — courses are distinguished by name and an optional mono code label,
  not a color each.
- Don't use amber for anything except progress / resume / bookmarks (and the ribbon in the logo).
- Don't break the existing lesson remake structure; new UI should wrap around it, not restyle it.

## 11. How this project applies the spec

The spec above is the brand kit, with paths adjusted to this repo. These are the decisions it left open or that differ.

**Gaps filled**
- Tokens: `assets/tokens.css` is the kit's file plus a clearly marked additions block. `remake_template.html` holds a copy so a page previews alone; the build warns if they drift and every page links the real file.
- Main buttons are ink (`--primary`), since amber is reserved for my place.
- Figures: amber can't be used, so lesson diagrams use `--fig` and `--fig-soft`, and `--c1`-`--c4` to tell things apart. `--wrong` also marks "this one" in a figure (the optimum, the critical path). The build turns `var(--accent)` in a page's own CSS into `var(--fig)`, so older or careless uploads can't paint figures amber. THOR chapter 1 keeps its own 10 task colours, because a Gantt chart needs them.
- Older pages' token names (`--ink`, `--line`, `--hi`...) are aliased in the additions block.
- Icons: Lucide at 20px, inlined by `build.py`.
- PDF viewer: PDF.js, vendored in `assets/pdfjs/`, is what makes "remember last page" and viewing on phones possible.
- Search: `/search/` runs in the browser over `search.json`, built from every section and PDF name, so it works offline. It doesn't search inside PDFs.
- Manage modules isn't in the spec's navigation. It sits at the bottom of the sidebar and as an icon in the phone top bar.
- Sidebar: collapsible on every desktop page (`assets/sidebar.css`), down to one panel button that stays in the same spot in both states. Lessons and sheets always open collapsed. Hub pages remember the choice per device (`localStorage` `cahier-side`), and windows under 1000px start collapsed until I choose. On lessons and sheets it replaces the floating back and theme buttons. The PDF viewer keeps its own back bar instead.
- Position sync: one position per lesson, the newest wins, labelled with the device that saved it.

**Deliberate differences**
- Navigation is Home and Search, plus Manage modules; the phone's bottom nav is Home · Search · Manage modules. The spec's Courses and Practice pages are gone because I didn't use them: Home already lists the courses.
- Course pages are organized by chapter, each a collapsible section holding its lesson, practice and PDFs, not the spec's Lessons · Practice · PDFs tabs.
- On phones, lessons and practice sheets have no bottom nav, only a back button and theme button that park after the contents, so reading keeps the whole screen.
- "Available offline" is only on PDFs. Lessons and sheets are always saved on install, so a toggle there would do nothing.
- Page zoom stays (125% / 150% on wide screens), because I asked for it.
- KaTeX isn't used: the remakes write maths as text and symbols, with no TeX to render. `--font-math` styles it.
- Internal `studyhub` ids, storage keys and the `studyhub:restored` event stay, because source pages and saved data depend on them. New code uses `cahier`.
- Practice inputs use `aria-label` and many lesson figures have `aria-label` rather than `<title>`; both come from the source pages, which the build doesn't edit.

