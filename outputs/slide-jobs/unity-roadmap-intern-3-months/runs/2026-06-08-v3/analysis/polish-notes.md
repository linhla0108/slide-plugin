# Redesign Notes: v3

## Goal

Create a more creative, better-balanced variant using Option A: Neon Game HUD. The deck stays at 8 slides, preserves the Unity intern roadmap source, and folds in the 8 requested idea directions.

## Changes From v2

- Slide 2 becomes a skill tree overview instead of a three-card timeline.
- Slide 3 becomes a Month 1 mission board with boss mission, XP progress, badge unlocks, and four training rows.
- Slide 4 becomes a production pipeline: GDD, Asset, Code, Test, Optimize, Merge.
- Slide 5 becomes a Feature Ownership launch pad from Planning to Graduation.
- Slide 6 becomes a support radar with Intern at the center and five support roles around it.
- Slide 7 becomes a Definition of Done checkpoint slide.
- Slide 8 combines thank-you, completion state, Dio, and Q&A hooks.
- XP, boss mission, badge, unlock, and HUD motifs now recur across the deck.

## Final Polish Pass

- Slide 2: replaced rotated div connectors with SVG paths, node ports, endpoint pins, and stronger glow so the skill-tree links attach cleanly to each node.
- Slide 4: rebuilt the production pipeline as a 3x2 task grid plus implementation hub console to avoid the previous two-row horizontal card layout.
- Slide 6: rebuilt the support view as a radar map with dashed beams and a right-side ask protocol panel so the UI reads as one system.
- Slide 7: replaced the flat six-card grid with a graduation gate and compact checklist panel for a stronger final checkpoint.

## Preserved

- Same source authority: `input/Prompt.md`.
- Same 8-slide limit and Vietnamese source intent.
- Same local assets and SUN.STUDIO resource usage.
- Same HTML-only export contract.

## Remaining Limitations

- No real Unity 3D model asset is provided; CSS geometry and local icons remain the cover visual solution.
- PPTX/PDF export is still out of scope for this v3 HTML run.