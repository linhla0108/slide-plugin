# Slide Build Approval

## Requirements

- Job: `unity-roadmap-intern-3-months`
- Title: `LEVEL UP: UNITY ROADMAP`
- Source: `input/Prompt.md`
- Source checksum: `48fb72080a24c04eee3b0a48a935e1d61df52d3d7c4f7a75cdd50d600e10fb50`
- Audience: Unity interns and mentor team
- Slide count: 8 slides
- Language: Vietnamese, preserving the user-provided roadmap content
- Output for this run: static editable HTML deck at 1920x1080

## Capability Result

- Status: ready
- Available tools: node, python
- Blockers: none
- Warning: no real Unity 3D model asset was provided, so the cover will use local Unity/gamepad iconography plus CSS isometric geometry.

## Content And Slide Plan

1. `LEVEL UP: UNITY ROADMAP` — cover, gamified training tone.
2. `Lộ trình 3 tháng` — three-month LEARN / INTEGRATE / OWN overview.
3. `Tháng 1: Onboarding & Training` — four-week onboarding and badge grid.
4. `Tháng 2: Thực chiến & Tích hợp` — collaboration workflow plus weekly missions.
5. `Tháng 3: Làm chủ tính năng` — ownership staircase from planning to graduation.
6. `Ma trận phối hợp & hỗ trợ` — role profile cards for mentor, GD, artist, QA, PM and HR.
7. `Q & A` — discussion slide.
8. `THANK YOU!` — closing slide.

## Visual Plan

- Direction: modern dark-mode game UI with neon month accents.
- Background: `#121214`; cards: `#1E1E24`.
- Month accents: January `#00F5D4`, February `#FF007F`, March `#7B2CBF`.
- Typography: local SUN.STUDIO Proxima Nova, shaped toward the prompt's Space Grotesk / Inter recommendation.
- Local assets: SUN.STUDIO logo, Dio character, local Unity/gamepad/badge SVG icon resources.
- Selected published visual items:
  - `sun.component.phase-timeline` for slide 2, score 100.0, reuse.
  - `sun.component.value-grid` for slide 3, score 85.0, reuse.
  - `sun.component.swimlane` for slide 4, score 89.17, reuse.
  - `sun.component.chevron-flow` for slide 5, score 93.0, reuse with staircase adaptation.
  - `sun.component.value-grid` for slide 6, score 70.83, slide-local adaptation.
- Rejected items: staging/qa items are not used; only published resources are selected.
- Extraction recommendation: a reusable vertical neon staircase component may be useful later, but no extraction will be triggered by this job.

## Export Contract

- Requested/approved first delivery: HTML.
- Text: editable static HTML leaf elements.
- Foreground structures: CSS/SVG shapes editable in source.
- Backgrounds: hybrid CSS effects, raster fallback allowed later if exporting PPTX/PDF.
- PPTX/PDF note: not included in this run because the user did not explicitly request them and the capability registry does not currently advertise a ready PPTX/PDF renderer.

## Approval

- Status: Approved
- Approved by: user
- Approved at: 2026-06-08T12:05:00+07:00
- Overrides:
  - Use dark-neon game UI visual direction instead of the default light SUN.STUDIO look while retaining SUN.STUDIO resources and local fonts.