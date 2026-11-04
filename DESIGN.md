# Acorn design theme: soft fintech on a warm minimal base, tailored to study pages

Calm, friendly and precise. Warm stone neutrals, one marigold accent, thin borders instead of
shadows, rounded shapes, strong type hierarchy.

**Every value lives in one place:** the `/* tokens */` block of `remake_template.html`. Hub pages
get the same block through `%%TOKENS%%`, and the build swaps the current base styles into every
remake, so changing that block changes the whole site. Components only reference tokens.

## Colour
Role            | Token                | Light   | Dark
----------------|----------------------|---------|--------
Background      | `--bg`               | #f6f5f2 | #121211
Surface (cards) | `--surface`          | #ffffff | #1b1a18
Surface sunken  | `--sunken`           | #efede8 | #0e0e0d
Surface hover   | `--hover`            | #f2f0ec | #23221f
Border          | `--line`             | #e4e1da | #2c2a27
Border strong   | `--line-strong`      | #cdc9c0 | #3d3a35
Text            | `--ink`              | #1c1b19 | #f1efea
Text muted      | `--muted`            | #6b675f | #a39f96
Text faint      | `--faint`            | #9a958b | #75716a
Accent fill     | `--accent-fill`      | #f2a922 | #f5b13a
Accent hover    | `--accent-fill-hover`| #e39912 | #f8c160
Text on accent  | `--on-accent`        | #2a1d04 | #2a1d04
Accent as text  | `--accent`           | #8a5a00 | #f5b13a
Accent soft bg  | `--accent-soft`      | #fdf0d5 | #33270f
Positive        | `--ok`               | #1d8049 | #4cbd78
Positive soft   | `--ok-soft`          | #e2f2e8 | #142b1d
Negative        | `--hi`               | #c2413a | #ec6b61
Negative soft   | `--hi-soft`          | #f8e4e1 | #361816

- One accent. Fills use `--accent-fill` with `--on-accent` text. `--accent` is the readable form for
  text and strokes, kept under that name so every existing remake's figures stay legible.
- Green and red carry meaning only: right and wrong, plus the emphasis mark below.
- Neutrals are warm, never blue-grey. Light and dark follow the system, with a manual override.

### Tailored for teaching figures
Diagrams have to tell tasks and machines apart, so they may use more than one colour:
- `--c1` to `--c4`: a warm palette, with dark text on all of them (#f5c56a, #e9a88e, #a9d0a6, #d3c7b5).
- `--l0` to `--l4`: a marigold ramp for heatmaps and levels.
- `--hi` marks "this one" in a figure (the optimum, the critical path).
- Decoration never uses these. THOR chapter 1 keeps its own 10 task colours: a Gantt chart needs them.

## Type
- Body and UI: Inter. Display (wordmark, page, section and card titles): Nunito 800.
- Tailored: IBM Plex Mono only for code, ciphertext and `table.t.mono`, where characters must line
  up. Cambria Math for formulas. Labels and numbers are Inter, not mono.
- Scale (rem): 0.6875, 0.75, 0.875, 1, 1.125, 1.375, 1.75, 2.5.
- Line height: 1.15 for headings, 1.45 in the shell, 1.5 on reading pages. Headings use -0.02em.
- Small uppercase labels use +0.06em. Numbers use tabular figures.

## Shape, space, depth
- Spacing on a 4px base. Radius: 8, 12, 18, 24px and pill.
- Cards: surface, 1px border, 24px radius, 20px padding, no shadow. Figures and worked examples: 18px.
- No cards in cards: anything inside a card (solutions, aids, equations) is sunken, with no border.
- Worked examples keep their top bar, in the accent.
- Buttons and segmented controls: pills. Inputs: 12px radius.
- Controls: 44px on phones, 36px for small ones on desktop.
- Flat by default. Only floating layers (the save pill) get `--shadow`.

## Components
- Primary button: accent fill, dark text. Secondary: surface with a strong border. Delete: soft red.
- Segmented control: sunken track, the selected segment a raised surface pill.
- Selectable chips: outlined; when selected, inverted.
- Lists: rows separated by 1px borders.
- Icons: Lucide, 20px, stroke 1.75, inlined by `build.py` (`ICONS`). No emoji as icons.

## Layout
- Hub, module and manage pages are the app shell: a 15rem left sidebar on desktop (logo, Home, modules,
  Manage, Theme), and a 4rem bottom tab bar on phones (Home, Manage, Theme) where the active icon sits
  in a soft accent pill. Content max-width 46rem.
- Tailored: lessons and practice pages stay focused reading pages, with no sidebar or tabs. They get a
  round back button and theme button that park below the contents, and a 1040px width because they
  hold wide figures and two-column sections; prose is capped at 78ch.
- Tailored: edit forms open inline rather than as bottom sheets, since they are small and rarely used.

## Motion and touch
- 120ms for hover and press, 200ms base, 360ms for progress. Easing: cubic-bezier(.2,.8,.2,1).
- Hover styles only inside `@media (hover:hover)`. Real `:active` states: buttons scale to .97, rows tint.
- `-webkit-tap-highlight-color:transparent` and `touch-action:manipulation` on tappable elements.

## Logo
A small smiling acorn (`assets/logo.svg`): marigold nut, warm brown cap, so the logo and the theme are
one thing. Wordmark in Nunito 800. App icons sit on the soft accent background. They are PNGs rendered
once from the SVG; redo them if the SVG changes.

## Avoid
Purple or blue gradients, glassmorphism, cards nested in cards, shadows on everything, oversized heroes,
centred everything, stock illustrations, inconsistent padding, more than one accent colour.
