---
name: Winlog
description: "A personal success diary, warm but focused, in plum and peach."
colors:
  plum: "#7a2e68"
  plum-dark: "#e7a3cf"
  on-plum: "#ffffff"
  on-plum-dark: "#2a0f23"
  peach: "#f9d9cb"
  peach-dark: "#3e2433"
  on-peach: "#5e2150"
  on-peach-dark: "#f6c2a9"
  saved-peach: "#fce3d6"
  saved-peach-dark: "#3a2330"
  on-saved-peach: "#5e2150"
  on-saved-peach-dark: "#f6c2a9"
  achievement-background: "#fbe0cf"
  achievement-background-dark: "#3d2618"
  achievement-text: "#7a3412"
  achievement-text-dark: "#f4be9a"
  achievement-dot: "#c76a3a"
  learning-background: "#e8e0f6"
  learning-background-dark: "#2d2542"
  learning-text: "#4b3684"
  learning-text-dark: "#cdbef0"
  learning-dot: "#7b66b8"
  feedback-background: "#f8dce2"
  feedback-background-dark: "#3f1e29"
  feedback-text: "#8a2440"
  feedback-text-dark: "#f2afc0"
  feedback-dot: "#c25570"
  side-project-background: "#ddede0"
  side-project-background-dark: "#1e3326"
  side-project-text: "#2e5a3a"
  side-project-text-dark: "#a9d7b3"
  side-project-dot: "#5e9468"
  blush-white: "#fffaf7"
  blush-white-dark: "#1a1519"
  peach-wash: "#fff1ea"
  peach-wash-dark: "#241d23"
  paper-white: "#ffffff"
  paper-white-dark: "#241d23"
  aubergine-ink: "#2a1f2a"
  aubergine-ink-dark: "#f3e9ee"
  muted-plum-grey: "#6a5966"
  muted-plum-grey-dark: "#b9a8b3"
  hairline: "#f0dcd2"
  hairline-dark: "#3a2f38"
  field-border: "#e8d3c9"
  field-border-dark: "#3a2f38"
  error: "#a8253b"
  error-dark: "#f4a3b0"
  plum-hover: "color-mix(in srgb, #7a2e68 88%, black)"
  plum-hover-dark: "color-mix(in srgb, #e7a3cf 88%, black)"
  secondary-hover: "#fff1ea"
  secondary-hover-dark: "#1a1519"
typography:
  display:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 2.5rem
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: -0.03em
  headline:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 2rem
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.03em
  headline-panel:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 1.625rem
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.03em
  title:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 1.25rem
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 1rem
    lineHeight: 1.5
  body-small:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 0.9375rem
    lineHeight: 1.5
  label:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 0.9375rem
  label-small:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 0.8125rem
  button:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 1rem
  button-large:
    fontFamily: "'Figtree Variable', system-ui, sans-serif"
    fontSize: 1.0625rem
  wordmark:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 1.5rem
    fontWeight: 800
    letterSpacing: -0.03em
  wordmark-laptop:
    fontFamily: "'Bricolage Grotesque Variable', 'Figtree Variable', system-ui, sans-serif"
    fontSize: 1.875rem
    fontWeight: 800
    letterSpacing: -0.03em
rounded:
  pill: 22px
  button: 14px
  button-large: 16px
  field: 14px
  panel: 14px
  label: 10px
  message: 12px
  dialog: 18px
spacing:
  space-4: 4px
  space-8: 8px
  space-12: 12px
  space-16: 16px
  space-20: 20px
  space-24: 24px
  space-32: 32px
  space-40: 40px
  space-48: 48px
  measure: 68ch
  content-max: 64rem
  sidebar-width: 232px
  tap-target: 44px
  control-height: 48px
  control-height-large: 54px
---

# Design System: Winlog

This is the visual design system for Winlog, chosen by the product owner on 11 November 2026 ("Plum & Peach v2"). Product facts live in `PRODUCT.md` and `docs/product-spec.md`. The approved mock-ups are the "Plum & Peach v2" boards (phone capture and laptop review) on the design canvas: https://claude.ai/artifact/4ivGiFFqkHwBBjDfm76ZBg

The values below were chosen and contrast-checked during that work. They are built as CSS custom properties in `frontend/src/index.css`, and the frontmatter at the top of this file lists them with the same values.

## Overview

**Creative North Star: "The Pocket Applause"**

Winlog is where a professional quietly keeps the moments they did well, so that at review time they can bring them out. The interface is warm the way a good colleague is warm: it notices a win, says so briefly, and gets out of the way. It is calm, never pushy. There are no streaks, no progress pressure and no "you missed a day".

Two devices, two moods. On the phone, capturing an entry is the shortest path in the app: one text, one category, Save. On the laptop, reviewing is roomier: filters, entries grouped by month, and an editable summary side by side.

Plum carries action, peach carries the good moments, and each category has its own soft tint. One typeface with character, Bricolage Grotesque, gives the name and headings their voice. Everything else is set in a calm sans so reading and typing stay effortless.

**Key Characteristics:**
- Warm but focused: blush-white grounds, plum actions, peach highlights.
- One expressive element: Bricolage Grotesque headings. Everything else stays quiet.
- Lists are rows with a fixed date column, not stacks of identical cards.
- Category is always shown with its tint, so a long list can be scanned by colour.
- AI text always appears as an editable draft, never as finished output.
- Icons, colour blocks and illustrations only where they help someone find or understand something.

## Colors

Restrained but warm: tinted neutrals from the plum–peach family, one action colour, and four category tints. Light and dark themes follow the device setting.

### Primary
- **Plum** (light #7A2E68, dark #E7A3CF; text on it: light #FFFFFF, dark #2A0F23): primary buttons, the focus ring, links, the Winlog wordmark. Nothing decorative.

### Secondary
- **Peach** (light #F9D9CB, dark #3E2433; text on it: light #5E2150, dark #F6C2A9): the current page in navigation, selected states, highlights.
- **Saved peach** (light #FCE3D6, dark #3A2330; text on it: light #5E2150, dark #F6C2A9): the "Entry saved." message and other success messages, with a plum check icon.

### Tertiary: category tints
Each pair is background and text. They appear on category labels, chips and filters, never as large page backgrounds.
- **Achievement, apricot** (light #FBE0CF / #7A3412, dark #3D2618 / #F4BE9A; dot #C76A3A)
- **Learning, lilac** (light #E8E0F6 / #4B3684, dark #2D2542 / #CDBEF0; dot #7B66B8)
- **Feedback, rose** (light #F8DCE2 / #8A2440, dark #3F1E29 / #F2AFC0; dot #C25570)
- **Side project, sage** (light #DDEDE0 / #2E5A3A, dark #1E3326 / #A9D7B3; dot #5E9468)

### Neutral
- **Blush white** (light #FFFAF7, dark #1A1519): page ground.
- **Peach wash** (light #FFF1EA, dark #241D23): header, sidebar, quiet surfaces.
- **Paper white** (light #FFFFFF): input fields and the summary panel in light mode; dark mode uses Peach wash.
- **Aubergine ink** (light #2A1F2A, dark #F3E9EE): body text and headings.
- **Muted plum-grey** (light #6A5966, dark #B9A8B3): secondary text, hints, dates in muted contexts.
- **Hairline** (light #F0DCD2, dark #3A2F38): row dividers and panel borders.
- **Field border** (light #E8D3C9, dark #3A2F38): unselected inputs, chips and secondary buttons.
- **Error** (light #A8253B, dark #F4A3B0): error text and the error border. It always comes with a message that says what to fix.

All text and background pairs above meet a contrast of at least 4.5:1 (checked on 11 November 2026).

### Named Rules
**The One Action Rule.** Plum marks what you can do. On any screen, the main action (Save entry, Save summary) is the only filled plum element.

**The Good Moment Rule.** Peach is for moments worth noticing: where you are, what you selected, what you just saved. It is never decoration.

**The Tint Stays Small Rule.** Category tints colour labels, chips and filter buttons. They never fill a page, a panel or a whole row.

## Typography

**Display Font:** Bricolage Grotesque (with Figtree, system-ui, sans-serif)
**Body Font:** Figtree (with system-ui, sans-serif)

**Character:** Bricolage Grotesque has a hand-made warmth and slightly irregular details, so the name and headings feel personal. Figtree is plain and friendly, so entries and forms read without effort. Both are on Google Fonts and are self-hosted from the project. Both are under the SIL Open Font License 1.1; the self-hosted packages are `@fontsource-variable/bricolage-grotesque` and `@fontsource-variable/figtree`.

### Hierarchy
- **Display** (Bricolage Grotesque 700, 40px, line-height 1.05, letter-spacing -0.03em): page titles on laptop ("Review").
- **Headline** (Bricolage Grotesque 700, 32px on phone, 26px for panel titles, line-height 1.05–1.15, letter-spacing -0.03em to -0.02em): page titles on phone, panel titles on laptop.
- **Title** (Bricolage Grotesque 700, 20px, line-height 1.2): group headings such as "November 2026".
- **Body** (Figtree 400, 15–16px, line-height 1.45–1.55): entry text, summaries, form input. Lines no longer than about 68 characters.
- **Label** (Figtree 600–700, 13–15px, sentence case): field labels, buttons, category labels, dates.
- **Wordmark** (Bricolage Grotesque 800, 24px on phone, 30px on laptop, letter-spacing -0.03em, plum).

Dates and numbers use tabular figures so columns line up.

### Named Rules
**The One Voice Rule.** Bricolage Grotesque is only for the wordmark and headings. Never for body text, buttons or labels.

**The Sentence Case Rule.** All text is in sentence case. No ALL-CAPS labels and no small labels above headings.

## Layout

Mobile first, from 360px wide.

- **Phone** (below 48rem): a header with the wordmark and navigation, then one column with 20px side padding. On the capture screen the order is: saved message (when there is one), page title, text field, category, date and "Add tags and result", Save entry, then "Just saved".
- **Laptop** (48rem and up): a left sidebar (about 232px) with the wordmark, navigation and a "New entry" button that is always within reach. The content area holds the work. On the review screen, the filters and list sit in the middle and the summary panel sits on the right (320–400px). When the window gets narrower, the panel moves below the list.
- **Lists:** entries are rows grouped by month, with a fixed date column (about 64px), a category label column (about 120px) and the text. Rows are separated by hairlines.
- **Spacing:** a 4px base, using 4, 8, 12, 16, 20, 24, 32, 40 and 48px. Related items sit close together (8–12px). Separate groups get more space (20–32px). There is always more space above a heading than below it.
- **Tap targets:** every button and form control is at least 44×44px.

## Elevation & Depth

Mostly flat. Depth comes from tonal layers (blush-white ground, peach-wash surfaces, white fields) and hairlines, not shadows.

### Shadow Vocabulary
- **Action lift** (`box-shadow: 0 4px 12px rgba(122, 46, 104, 0.25)` in light mode, `0 4px 12px rgba(231, 163, 207, 0.25)` in dark mode): only under the primary plum button.
- **Focus glow** (`box-shadow: 0 0 0 3px #F6DDEB` in light mode, `0 0 0 3px rgba(231, 163, 207, 0.3)` in dark mode, plus a plum border): the focused text field.

### Named Rules
**The Flat Rows Rule.** Entry rows and panels have no shadows. Only the main action is lifted.

## Shapes

Soft, rounded and consistent by role, not one radius everywhere:
- **Pills** (22px radius, fully round ends): category chips and the current navigation item on the phone.
- **Buttons** (14–16px).
- **Fields and panels** (14px).
- **Small labels and messages** (10–12px).
- **Device-sized panels** such as dialogs (16–20px).

Borders are 1px hairlines for structure and 1.5px for interactive controls.

## Components

### Buttons
- **Primary:** plum fill, white text, Figtree 700 at 16–17px, at least 48px tall (54px on the phone's Save entry), with the Action lift shadow. Labels name the action: "Save entry", "Save summary".
- **Secondary:** white or transparent fill, plum text, 1.5px Field-border outline. Used for "Draft again", "New entry" in the sidebar, "Cancel".
- **Hover / focus:** hover darkens the fill slightly. Focus shows a visible 2px plum outline with offset. Disabled buttons use muted text and no shadow.

### Chips (category)
- **Style:** pill shape, 44px tall, with a 10px dot in the category's dot colour before the label.
- **Selected:** the category's tint background and text colour, a 1.5px border in the text colour, bold label.
- **Unselected:** white background, Aubergine ink text, Field-border outline.
- **In filters:** the same chips, with a check icon on each selected one.

### Category labels
A small rounded label (10px radius) in the category tint, Figtree 700 at 13px. Shown on every entry, everywhere.

### Inputs / Fields
- **Style:** white fill, 1.5px Field-border outline, 14px radius, Figtree 16px, a visible label above every field.
- **Focus:** plum border plus the Focus glow.
- **Error:** Error-colour border and a message below the field that says what to fix, for example "Write what happened, then save."

### Navigation
- **Phone:** header with the wordmark on the left and links on the right (Entries, Review, More). The current page sits in a peach pill.
- **Laptop:** sidebar with Entries, Review, Summaries and Settings as 44px rows. The current page has a peach background and bold plum text.

### Saved message
A peach band with a plum check icon and the text "Entry saved." It appears at the top of the capture screen after saving and fades away after a few seconds. This is the app's one authored motion moment. With reduced motion, it appears and disappears without animation.

### Entry row
Date (tabular, bold) | category label | entry text, with "Result: …" below in muted text when there is one. Hairline above. No card, no shadow.

### Summary panel
White panel (Peach wash in dark mode) with the title "Summary", one line saying which entries it was drafted from, the editable summary text, then Save summary and Draft again. It always says it is a draft the user can edit. Limits are stated calmly, for example "You can draft 1 more summary today."

### Icons
One consistent outline icon set at 1.5–2px stroke, 16–24px, in the current text colour. The icons are Lucide (`lucide-react`), under the ISC licence; the icons that come from Feather are under the MIT licence. Icons appear only where they help:
- next to navigation items on the laptop sidebar;
- the check in the saved message and in selected filter chips;
- small actions on entries and summaries: edit, delete, copy, download;
- the AI suggestion and draft buttons, so AI features are recognisable;
- empty states and messages (information, error).

Never emoji, and never an icon without a text label or an accessible name.

### Colour blocks and illustrations
Colour blocks are the peach surfaces and category tints described above, used where they group or highlight something.

Illustrations appear in at most three places, where a screen would otherwise feel empty:
- the empty entries list on first use;
- the login and registration screens;
- a review with no matching entries.

They use one style: simple flat shapes in plum, peach and the category tints, with no gradients, no photographs and no stock images. Each one sits next to a sentence and a button that say what to do next.

## Do's and Don'ts

### Do:
- **Do** keep capturing the shortest path: text, category, Save. Date defaults to today; tags and result stay folded under "Add tags and result" (Hick's law).
- **Do** give every screen a clear empty, loading and error state, each with one next step.
- **Do** name buttons by their action and keep the name through the flow: "Save entry" leads to "Entry saved."
- **Do** show category tints everywhere an entry appears, so entries can be scanned by colour (law of similarity).
- **Do** group entries by month on the review screen (chunking) and keep the date column fixed.
- **Do** mark AI text as a draft and keep it editable; keep AI buttons secondary (selective attention).
- **Do** use standard controls people already know: selects, buttons, text fields (Jakob's law).
- **Do** keep every tap target at least 44×44px on the phone (Fitts's law).
- **Do** follow the device's light or dark setting and respect reduced motion.

### Don't:
- **Don't** add streaks, progress bars, daily goals or "you missed a day" messages.
- **Don't** make it look like a grey corporate HR tool or a generic template.
- **Don't** use emoji as icons, ALL-CAPS labels, small labels above headings, or gradients.
- **Don't** use more than one filled plum button on a screen.
- **Don't** wrap entries in identical cards with shadows.
- **Don't** use stock photos, or illustrations outside the three places named above.
