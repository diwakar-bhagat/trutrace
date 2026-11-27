---
version: alpha
name: TruTrace
description: A merged design system for the TruTrace demo, built from the best of Apple and Nike. Nike supplies the discipline: ink black (#111111) and pure white carry the chrome, one soft cloud gray stages content, every interactive element is a pill, there are no drop shadows anywhere, and a single towering uppercase display lockup opens the page. Apple supplies the reading experience: a calm, precise type hierarchy, generous whitespace, quiet neutral grays, and hairline dividers that let dense technical content — scorecard tables, evidence spans, JSON output — stay legible. Color exists only as signal: green means verified, red means conflicting, gray means unconfirmed. Nothing else in the chrome is chromatic.

colors:
  primary: "#111111"
  on-primary: "#ffffff"
  canvas: "#ffffff"
  soft-cloud: "#f5f5f5"
  ink: "#111111"
  charcoal: "#39393b"
  ash: "#4b4b4d"
  mute: "#707072"
  stone: "#9e9ea0"
  hairline: "#cacacb"
  hairline-soft: "#e5e5e5"
  verified: "#007d48"
  conflicting: "#d30005"
  unconfirmed: "#707072"

typography:
  display-campaign:
    fontFamily: "Anton, Bebas Neue, Inter, system-ui, sans-serif"
    fontSize: 96px
    fontWeight: 400
    lineHeight: 0.9
    letterSpacing: 0
    textTransform: uppercase
  heading-xl:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 32px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  heading-lg:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 24px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0
  heading-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  lead:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 20px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  body:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-strong:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  button-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  button-sm:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  caption-md:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  caption-sm:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: 0
  fine-print:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  code-md:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: 0

rounded:
  none: 0px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 80px

components:
  hero-lockup:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    typography: "{typography.display-campaign}"
    rounded: "{rounded.none}"
    padding: 80px 24px
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: 16px 32px
    height: 48px
  button-primary-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
  button-secondary:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.ink}"
    typography: "{typography.button-md}"
    rounded: "{rounded.full}"
    padding: 16px 32px
    height: 48px
  state-chip-verified:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.verified}"
    typography: "{typography.caption-sm}"
    rounded: "{rounded.full}"
    padding: 4px 12px
  state-chip-unconfirmed:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.unconfirmed}"
    typography: "{typography.caption-sm}"
    rounded: "{rounded.full}"
    padding: 4px 12px
  state-chip-conflicting:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.conflicting}"
    typography: "{typography.caption-sm}"
    rounded: "{rounded.full}"
    padding: 4px 12px
  transcript-panel:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 24px
  answer-field-row:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 16px 0px
  evidence-span:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.charcoal}"
    typography: "{typography.code-md}"
    rounded: "{rounded.none}"
    padding: 8px 12px
  scorecard-table:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 0px
  scorecard-table-header:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.ink}"
    typography: "{typography.caption-md}"
    rounded: "{rounded.none}"
    padding: 12px 16px
  metric-card:
    backgroundColor: "{colors.soft-cloud}"
    textColor: "{colors.ink}"
    typography: "{typography.heading-lg}"
    rounded: "{rounded.none}"
    padding: 24px
  footer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.mute}"
    typography: "{typography.caption-md}"
    rounded: "{rounded.none}"
    padding: 48px 24px
---

## Overview

TruTrace is a technical demo for engineers: it shows seller-call transcripts being turned into structured answers, field by field, with the evidence for every value kept visible. The design problem is trust. The page has to feel as disciplined as the system it demonstrates, so the chrome never shouts over the data — with exactly one exception, the hero.

The merge takes its discipline from Nike and its manners from Apple. From Nike: `{colors.ink}` and `{colors.canvas}` carry roughly 95% of the surface, `{colors.soft-cloud}` stages panels and chips, every interactive element is a pill at `{rounded.full}`, cards and panels are square at `{rounded.none}`, there are no drop shadows anywhere, and the page opens with a single uppercase display lockup at `{typography.display-campaign}` burned into a full-bleed ink band. From Apple: a calm type hierarchy with clear heading steps, generous whitespace on an 8px grid with `{spacing.section}` (80px) between major blocks, quiet neutral grays for secondary text, and 1px hairlines instead of borders or elevation, so scorecard tables, evidence spans, and JSON output read like a well-made product page rather than a dashboard.

Color is signal, never decoration. There are exactly three chromatic tokens in the system and each one is a field state: `{colors.verified}` (green) means a value is backed by evidence in the transcript, `{colors.conflicting}` (red) means two statements in the call disagree, and `{colors.unconfirmed}` (gray) means the call never settled the field. If a color appears anywhere else, it is a bug.

**Key Characteristics:**
- One loud moment per page: the `{component.hero-lockup}` — uppercase display type on `{colors.ink}`, nothing else competes with it.
- Ink, canvas, and soft cloud carry the chrome; the three signal colors appear only inside `{component.state-chip-verified}`, `{component.state-chip-unconfirmed}`, and `{component.state-chip-conflicting}` and in state text within answer rows.
- Two shapes only: pills (`{rounded.full}`) for anything interactive or state-bearing, square (`{rounded.none}`) for every container.
- Zero drop shadows. Depth comes from surface change (canvas ↔ soft cloud ↔ ink) and 1px hairlines.
- Apple-style reading rhythm: 16px body at 1.5 line-height, headings at 500 weight, `{spacing.section}` of air between major blocks.
- Evidence is typeset, not decorated: transcript spans and JSON render in `{typography.code-md}` on `{colors.soft-cloud}` via `{component.evidence-span}`.

## Colors

> **Sources:** Nike's retail chrome palette (ink, canvas, soft cloud, text grays, hairlines, sale red, success green) and Apple's neutral text and hairline discipline. Apple's Action Blue and Nike's category accents were deliberately dropped — see Known Gaps.

### Brand & Surface
- **Ink** (`{colors.ink}` — #111111): The system's only brand color, from Nike, and the value carried by `{colors.primary}`. Primary pill CTAs, headlines, body text, the hero band. When TruTrace asserts anything structural, it goes ink.
- **Canvas** (`{colors.canvas}` — #ffffff): The page background and panel surface. Equal partner to ink.
- **On Primary** (`{colors.on-primary}` — #ffffff): Text on ink surfaces — the hero lockup and the primary pill.
- **Soft Cloud** (`{colors.soft-cloud}` — #f5f5f5): Nike's staging gray. Metric cards, state chips, evidence spans, table headers. Apple's near-identical parchment (#f5f5f7) was folded into this token rather than kept as a second gray.

### Text
- **Charcoal** (`{colors.charcoal}` — #39393b): Softer body text where ink is too heavy; evidence span text.
- **Ash** (`{colors.ash}` — #4b4b4d): Low-emphasis utility text and disabled labels.
- **Mute** (`{colors.mute}` — #707072): Secondary metadata, field labels, footer text. Also the hex behind the unconfirmed state.
- **Stone** (`{colors.stone}` — #9e9ea0): Lowest-emphasis text; secondary copy on the ink hero band.

### Hairlines & Borders
- **Hairline** (`{colors.hairline}` — #cacacb): The 1px divider between answer field rows, table rows, and panel edges. This is the system's only border weight.
- **Hairline Soft** (`{colors.hairline-soft}` — #e5e5e5): The inset 1px bottom line under sticky bars, inherited from Nike. The closest thing to a shadow the system allows.

### Signal (field states — the only chromatic color in chrome)
- **Verified** (`{colors.verified}` — #007d48): Nike's success green. A field value backed by a supporting span in the transcript. Used in `{component.state-chip-verified}` and nowhere decorative.
- **Conflicting** (`{colors.conflicting}` — #d30005): Nike's sale red, repurposed. Two statements in the same call disagree about this field. Used in `{component.state-chip-conflicting}` and nowhere else — it never marks prices, sales, or errors of the page itself.
- **Unconfirmed** (`{colors.unconfirmed}` — #707072): A neutral gray, deliberately the same hex as `{colors.mute}`. The seller never confirmed this field. The absence of color is the signal.

## Typography

### Font Family
- **Display**: `Anton, Bebas Neue, Inter, system-ui, sans-serif` — the open substitutes for Nike's proprietary Futura ND, used for exactly one tier (`{typography.display-campaign}`) and nothing else. Anton ships at weight 400 only, so the tier is specified at 400 rather than Nike's 500.
- **Text and UI**: `Inter, system-ui, -apple-system, sans-serif` — the shared open substitute for both SF Pro and Helvetica Now. Weights 400 and 500 only, following Apple's ladder discipline and Nike's two-weight UI practice.
- **Mono**: `ui-monospace, SF Mono, Menlo, Consolas, monospace` — a TruTrace addition neither source needed. Transcripts, evidence spans, and JSON output are data, and data is set in mono.

### Hierarchy

| Token | Size | Weight | Line Height | Use |
|---|---|---|---|---|
| `{typography.display-campaign}` | 96px | 400 | 0.9 | The hero lockup only, uppercase |
| `{typography.heading-xl}` | 32px | 500 | 1.2 | Section headers |
| `{typography.heading-lg}` | 24px | 500 | 1.2 | Panel titles, metric values |
| `{typography.heading-md}` | 16px | 500 | 1.5 | Card titles, table group labels |
| `{typography.lead}` | 20px | 400 | 1.4 | Hero subcopy, section introductions |
| `{typography.body}` | 16px | 400 | 1.5 | Body copy, transcript text, table cells |
| `{typography.body-strong}` | 16px | 500 | 1.5 | Field names, emphasized values, nav links |
| `{typography.button-md}` | 16px | 500 | 1.5 | Standard pill CTAs |
| `{typography.button-sm}` | 14px | 500 | 1.5 | Compact pill CTAs |
| `{typography.caption-md}` | 14px | 500 | 1.5 | Table headers, footer links, metadata |
| `{typography.caption-sm}` | 12px | 500 | 1.5 | State chips, counts, badges |
| `{typography.fine-print}` | 12px | 400 | 1.5 | Footer legal row, disclaimers |
| `{typography.code-md}` | 13px | 400 | 1.6 | Evidence spans, JSON, transcript excerpts |

### Principles
- **One display tier, used once.** `{typography.display-campaign}` appears in the hero lockup and nowhere else. Everything below it follows the Apple-style ladder: clear steps, 500-weight headings, calm 16px body. Apple's 17px body was considered and set aside — 16px is the shared size both sources' UI tiers converge on, and it keeps tables denser and more scannable.
- **Weight discipline.** 400 for reading, 500 for emphasis and UI. No 600 or 700 in text tiers; the display tier gets its force from size and uppercase, not weight.
- **Letter-spacing stays at 0** outside the display tier, matching Nike's practice. The Apple negative-tracking headline feel is not carried over — Inter at these sizes reads cleanly without it, and the demo's headlines are working labels, not product poetry.
- **Numbers are data.** Scorecard figures use `{typography.body}` or `{typography.heading-lg}` with tabular figures (`font-variant-numeric: tabular-nums`) so columns align.

### Note on Font Substitutes
SF Pro, Helvetica Now, and Nike Futura ND are all proprietary and unavailable to this project. The substitutes are stated in the stacks themselves: Anton or Bebas Neue for the display tier (tighten letter-spacing roughly -0.5% on Bebas Neue to approximate Futura ND's optical weight), Inter for everything else. On Apple devices, `system-ui` fallbacks resolve to the real SF Pro where Inter is absent.

## Layout

### Spacing System
- **Base unit:** 8px, shared by both sources. Sub-base values (`{spacing.xxs}` 2px, `{spacing.xs}` 4px) exist for tight typographic adjustments only.
- **Tokens:** `{spacing.xxs}` 2px · `{spacing.xs}` 4px · `{spacing.sm}` 8px · `{spacing.md}` 16px · `{spacing.lg}` 24px · `{spacing.xl}` 32px · `{spacing.xxl}` 48px · `{spacing.section}` 80px.
- **Section rhythm:** `{spacing.section}` (80px, Apple's tile padding) separates major blocks — hero → transcript demo → scorecard → metrics → footer. Nike's tighter 48px section rhythm was dropped in favor of Apple's air; a demo that asks engineers to read evidence needs the pedestal.
- **Panel padding:** `{spacing.lg}` (24px) inside panels and metric cards. **Row padding:** answer field rows breathe at 16px vertical (`{spacing.md}`).

### Grid & Container
- **Max content width:** ~1080px for reading sections (transcript, scorecard), full-bleed for the hero band.
- **Column patterns:** the demo section pairs `{component.transcript-panel}` and the answer column side by side at desktop (roughly 5/7 split), stacking at narrow widths. Metric cards run 3-up or 4-up in a single row.
- **Gutters:** `{spacing.lg}` (24px) between cards and columns.

### Whitespace Philosophy
Apple governs: whitespace is the pedestal the evidence sits on. The transcript and its answer rows are never crowded; the nearest unrelated content is at least `{spacing.xl}` away. Nike's edge-to-edge density survives only inside the hero band and the scorecard table, where density is the point.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 — Flat | No shadow, no border | Default for sections, cards, buttons |
| 1 — Hairline divider | 1px solid `{colors.hairline}` | Answer row separators, table rows, panel edges |
| 2 — Inset bottom line | `box-shadow: inset 0 -1px 0 {colors.hairline-soft}` | Sticky bar bottom edge only |

**Shadow philosophy.** Zero drop shadows, full stop — Nike's rule, kept over Apple's single product shadow because TruTrace has no product photography for a shadow to serve. Depth comes from surface change alone: canvas → soft cloud → ink.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | Every container: hero band, panels, cards, table, evidence spans, footer |
| `{rounded.full}` | 9999px | Every interactive or state-bearing element: pill CTAs, state chips |

Two radii is the entire vocabulary, taken from Nike's two-shape discipline (pill or square) with Apple's intermediate card radii (8px, 11px, 18px) deliberately dropped. If an element is a container it is square; if a person can act on it or it carries a state, it is a pill.

## Components

> **No hover states documented**, per both sources' policy. Each spec covers Default and Active/Pressed only; variants live as separate `components:` entries in the front matter.

### Hero

**`hero-lockup`** — the page's single loud moment
- Full-bleed band on `{colors.ink}`, rounded `{rounded.none}`, padding `{spacing.section}` vertical.
- The headline in `{typography.display-campaign}` (uppercase, 96px, line-height 0.9) in `{colors.on-primary}`. One lockup per page, at the top, never repeated at scale elsewhere.
- Subcopy below in `{typography.lead}` at `{colors.stone}`-to-white range, and at most one `{component.button-primary}` inverted for the dark surface (canvas background, ink text — the Nike on-image pill grammar) or one `{component.button-secondary}`.
- There is no imagery requirement: unlike Nike's campaign tile, the TruTrace hero is type on ink. The words are the photograph.

### Buttons

**`button-primary`** — the universal action
- Background `{colors.ink}`, text `{colors.on-primary}`, type `{typography.button-md}`, rounded `{rounded.full}`, padding 16px × 32px, height 48px.
- One primary action per viewport. On the ink hero it inverts (canvas background, ink text) rather than disappearing into the band.
- Pressed state lives in `{component.button-primary-active}` — same colors, surface scales down slightly (the shared Apple/Nike press micro-interaction).

**`button-secondary`** — the soft alternative
- Background `{colors.soft-cloud}`, text `{colors.ink}`, type `{typography.button-md}`, rounded `{rounded.full}`, padding 16px × 32px, height 48px.
- Used only alongside a primary, never as the page's sole call to action.

### State Chips

The demo's signature component. Each chip is a pill at `{rounded.full}` on `{colors.soft-cloud}` with `{typography.caption-sm}` text; only the text color changes between states, so the three read as one family at a glance.

**`state-chip-verified`** — text `{colors.verified}`. Copy pattern: "Verified". The field's value is backed by an evidence span.
**`state-chip-unconfirmed`** — text `{colors.unconfirmed}`. Copy pattern: "Unconfirmed". The call never settled this field; the answer row shows no value, or shows it struck through per the data, never as fact.
**`state-chip-conflicting`** — text `{colors.conflicting}`. Copy pattern: "Conflicting". Two spans in the transcript disagree; both are shown.

Chips sit at the right end of each `{component.answer-field-row}`, aligned in a column so a reader can scan the state of every field in one vertical pass.

### Demo Panels

**`transcript-panel`** — the raw call
- Background `{colors.canvas}`, text `{colors.ink}`, rounded `{rounded.none}`, padding `{spacing.lg}`, 1px `{colors.hairline}` border.
- Speaker turns in `{typography.body}`; quoted evidence within the transcript is highlighted by the pairing with `{component.evidence-span}`, not by color inside the panel. The panel itself uses no signal color — the transcript is evidence, not verdict.

**`answer-field-row`** — one extracted field
- Background `{colors.canvas}`, rounded `{rounded.none}`, padding 16px vertical, 1px `{colors.hairline}` divider below each row (the Nike disclosure-row pattern, kept).
- Layout, left to right: field name in `{typography.body-strong}`, extracted value in `{typography.body}`, the field's state chip at the right edge.
- Below the value, where evidence exists: one `{component.evidence-span}`.

**`evidence-span`** — the proof
- Background `{colors.soft-cloud}`, text `{colors.charcoal}`, type `{typography.code-md}`, rounded `{rounded.none}`, padding 8px × 12px.
- Contains the verbatim transcript quote supporting the field's value. For conflicting fields, two evidence spans stack, one per claim. An unconfirmed field has no evidence span — its absence is part of the design.

### Scorecard & Metrics

**`scorecard-table`** (`{component.scorecard-table}`) — baseline vs. current, model by model
- Background `{colors.canvas}`, text `{colors.ink}` in `{typography.body}`, rounded `{rounded.none}`.
- Header row is `{component.scorecard-table-header}`: `{colors.soft-cloud}` background, `{typography.caption-md}` labels, padding 12px × 16px.
- Body rows separated by 1px `{colors.hairline}` dividers; numeric cells right-aligned with tabular figures. Metric values never carry signal color unless the cell itself reports a field-state count, in which case the state token applies.
- The table is the Apple reading experience at its most literal: quiet chrome, precise alignment, nothing between the engineer and the numbers.

**`metric-card`** (`{component.metric-card}`) — one headline number
- Background `{colors.soft-cloud}`, text `{colors.ink}`, rounded `{rounded.none}`, padding `{spacing.lg}`.
- The value in `{typography.heading-lg}`; the label above or below it in `{typography.caption-md}` at `{colors.mute}`. Cards sit flat — no shadow, no border beyond the surface change.

### Footer

**`footer`** (`{component.footer}`)
- Background `{colors.canvas}` with a single 1px `{colors.hairline}` top divider, text `{colors.mute}` in `{typography.caption-md}`, padding `{spacing.xxl}` vertical.
- Links and credits in `{typography.caption-md}`; the legal and methodology row at the bottom in `{typography.fine-print}`.

## Do's and Don'ts

### Do
- Open with exactly one `{component.hero-lockup}` and let `{typography.display-campaign}` appear nowhere else on the page.
- Use `{component.button-primary}` as the single primary action per viewport; pair it at most with `{component.button-secondary}`.
- Give every extracted field a state chip, and let `{colors.verified}`, `{colors.conflicting}`, and `{colors.unconfirmed}` appear only as state signal.
- Set body copy at `{typography.body}` (16px / 400 / 1.5) and headings at 500 weight; keep letter-spacing at 0.
- Separate rows, panels, and sections with 1px `{colors.hairline}` dividers and `{spacing.section}` of air — never with shadows or boxes inside boxes.
- Show the evidence span for every verified value, both spans for every conflicting value, and none for unconfirmed values.

### Don't
- Don't use a signal color decoratively — no green headings, no red links, no gray "accents" that are not the unconfirmed state.
- Don't add drop shadows to anything. There is no product photography here for Apple's single product shadow to serve, so the shadow budget is zero.
- Don't introduce a third shape. Containers are `{rounded.none}`; interactive and state elements are `{rounded.full}`.
- Don't add a brand accent color. Ink is the brand; blue (Apple's or Nike's info) is deliberately absent.
- Don't set the display tier at any size other than the hero lockup, and don't set it in sentence case.
- Don't hide an unconfirmed field. An explicit unconfirmed row with its chip is the product's honesty made visible.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Wide desktop | ≥ 1441px | Content locks at ~1080px; hero band stays full-bleed |
| Desktop | 1024–1440px | Full layout; transcript and answer columns side by side |
| Tablet | 641–1023px | Demo columns stack; metric cards go 2-up |
| Phone | ≤ 640px | Single column; metric cards 1-up; hero type downscales |

### Collapsing Strategy
- **Hero lockup:** `{typography.display-campaign}` downscales 96px → 64px at tablet → 48px at phone; line-height stays 0.9 at every size (Nike's rule).
- **Demo columns:** transcript panel above the answer rows at narrow widths — evidence before verdict, in reading order.
- **Scorecard table:** keeps its columns at tablet; at phone it scrolls horizontally inside its panel rather than reflowing numbers into prose.
- **Section spacing:** `{spacing.section}` 80px desktop → 48px tablet → 32px phone, so the Apple air compresses without disappearing.

### Touch Targets
- Pill CTAs sit at 48px height with 32px horizontal padding, meeting the 44px minimum both sources assume.
- State chips are labels, not targets; where a chip toggles evidence visibility, its hit area extends to 44px while the visible pill stays at `{typography.caption-sm}` size.

## Iteration Guide

1. Focus on ONE component at a time. Reference its YAML key directly (`{component.answer-field-row}`, `{component.evidence-span}`).
2. Variants of an existing component (`-active`, the three state chips) live as separate entries in `components:`.
3. Use token references everywhere — never inline a hex that has a token.
4. Never document hover. Default and Active/Pressed states only.
5. Before adding a token, ask whether the need is a state (three tokens exist), a surface (three exist), or text emphasis (the gray ladder exists). The answer is almost always already in the file.
6. If a new chromatic color seems necessary, the design is wrong, not the palette. Restate the element in ink, a gray, or one of the three state tokens.

## Known Gaps

- **Proprietary font substitutions.** SF Pro and Helvetica Now (Apple and Nike text faces) and Nike Futura ND (Nike display face) are proprietary and unavailable. The system substitutes Inter for all text tiers and Anton / Bebas Neue for the display tier, and states the substitutes inside the font stacks. Anton ships only at weight 400, so `{typography.display-campaign}` is specified at 400 where Nike's original is 500.
- **Dropped from Apple:** the Action Blue accent (`#0066cc`) and its focus and on-dark variants — TruTrace has no brand link color; ink and the state tokens carry all signaling. The dark product-tile system and alternating light/dark tile rhythm (the demo has one ink band, the hero, not a tile stack). The single product drop-shadow — dropped with the photography it served. Parchment `#f5f5f7` as a separate surface — folded into `{colors.soft-cloud}`. The 17px body size and negative letter-spacing on headlines — 16px and 0 tracking adopted instead. The intermediate radii (5px, 8px, 11px, 18px) — the two-shape vocabulary replaces them.
- **Dropped from Nike:** the six category accent colors (pinks, purples, teal) — editorial color has no job in a verification demo. The info blues (`#1151ff`, `#0034e3`) — no informational accent exists alongside the state tokens. The bright and deep semantic variants (`success-bright`, `sale-deep`) — each state has exactly one hex, on light and dark surfaces alike. The commerce components (product card, swatch dots, campaign tile, filter sidebar, search pill) — TruTrace has no products to sell; the campaign tile's lockup survives, abstracted into `{component.hero-lockup}` without photography. The 48px section rhythm — Apple's 80px governs.
- **Added by TruTrace:** `{typography.code-md}` and `{component.evidence-span}` — neither source typesets data as a first-class citizen; a verification demo must. The three state chips are Nike's semantic restraint mapped onto TruTrace's field states, not components either source shipped.
- **Hover states not documented**, following both sources' policy.
- **Responsive behavior is synthesized** from the two sources' breakpoint patterns, not captured from a shipped TruTrace build; verify against the real demo when it is built.
- **Dark mode is not specified.** The demo is a light-canvas page with one ink hero band, following Nike's light-dominant chrome; a full dark theme was out of scope for the merge.
