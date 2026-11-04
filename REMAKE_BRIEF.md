# Remake brief (for the claude.ai "Cahier remakes" project)

Put this file and `remake_template.html` in the project's knowledge. Every page you make
is dropped into my Cahier site, so it must follow the rules below exactly.

## Output
- Two standalone HTML files per chapter: `lesson.html` and `practice.html`. Give me each as one complete file.
- Start from `remake_template.html`. Copy its `<head>` as is: the `study-hub:theme` script and the whole
  `study-hub:base` `<style>` block, **verbatim, never edited**. Put anything page-specific (SVG classes) in the second
  `<style>` block, using the tokens only: `--text`, `--text-muted`, `--surface`, `--surface-2`, `--border`, `--correct`,
  `--wrong`, and for figures `--fig`, `--fig-soft`, `--c1` to `--c4` (dark text on those). Never use amber (`--accent`):
  it means "my place" only. No hardcoded colours, no external fonts. Keep the theme toggle button as the first element
  of `<body>`, and always close `</head>`.
- Don't add your own theme switcher, fonts, colour palette or progress storage. No `localStorage`.
- No external scripts or libraries. Inline SVG for every figure.

## Lesson page
- Hero: eyebrow `CODE · Chapter N · Lesson`, `h1`, `.lead`, a figure in `.herofig`.
- `nav.toc` with `.part` groups listing every section.
- Numbered `section.sec` with the `.sec-h` header (`.num`, `h2` + French in `.fr`, `↑ contents` link).
- In each section: `.plain` ("In plain words"), `.defs` (English term, French in parentheses), `figure.fig`
  with an inline SVG, and a `.calc` worked example. Use `.callout`, `.eq`, `table.t` as needed.
- End with `.note.errata`, tagged "Notes on the original course", listing errors found in the course text, then `.foot`.
- English, with the French term in parentheses next to key terms. At least one example per concept; redo the
  course's own examples. Concise, not dense. Check every number by running code before writing it in.

## Practice page
- Same hero, eyebrow `CODE · Chapter N · Practice`, with the `.prog` progress bar (ids `prog-txt`, `prog-bar`).
- Problems are `article.prob` cards: `.ph` header with `.pid` (e.g. `A1`) and a `.done` checkbox,
  `.pq` statement, `<details><summary>Show solution</summary><div class="sol">…</div></details>`.
- Visual aids (tables, alphabets, formulas) in `.aid` boxes. Keep problems simple: the goal is to get used
  to the method, not to compute by hand.
- Auto-checked answers are welcome: `.actions` with `.b` buttons, `.mc label.opt` for multiple choice.
- Keep the `study-hub:progress` script from the template.

## Saving rules (my site saves every practice answer; break these and answers get lost)
- Every `input`, `select` and `textarea` has a **unique, stable `id`**: `done-A1` for done boxes,
  `q-A1-1`, `q-A1-2`, ... for answers. Never renumber ids in later versions.
- Every radio has a `name` and a `value` (`value="0"`, `"1"`, ...).
- Anything that must not be saved goes inside an element with `data-no-save`.
- If a script clears fields (a Reset button), it must dispatch `input` (text) or `change` (checkbox, radio,
  select) on each cleared field, so the site deletes the saved value.
- To react to restored answers (e.g. re-run checking), listen for the `studyhub:restored` event on `document`.
