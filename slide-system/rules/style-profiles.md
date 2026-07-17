# Per-User Style Profiles & Design Precedence

A **style profile** lets one user record APPROVED personal design preferences so
generated decks lean toward their taste — without weakening the SUN.STUDIO brand,
readability, or component contracts. It is a small, versioned, project-local JSON
file, nothing more.

## Storage & selection

- Location: `slide-system/style-profiles/<profile-id>.json`.
- Schema: `slide-system/schemas/style-profile.schema.json`; validate with
  `slide-system/scripts/validate_style_profile.py`.
- Selection is **explicit**: a job names a `style_profile` id/path. One user's
  profile is never loaded implicitly for another. No home-directory memory, no
  cloud, no auto-learning from private decks, no inferred/tracked data.
- Example (not a default): `style-profiles/example-restrained.json`.

## What a profile MAY contain (whitelisted, enum-bounded)

Information density; heading/body hierarchy; spacing; visual rhythm; visual tone
(restrained↔expressive); media bias (image-led↔diagram-led); preferred layout
families; preferred and avoided **published** component intents; optional
language and tone. Nothing free-form.

## What a profile may NEVER contain

Arbitrary CSS/HTML/JS; raw private deck text; secrets; automatically inferred
user data. `validate_style_profile.py` rejects unknown keys, non-enum values, and
any value that looks like markup/CSS/a URL/script.

## Precedence (highest wins)

1. **Approved content / source authority** — wording, numbers, labels, order, and
   language are preserved (`rules/content-fidelity.md`, `rules/source-authority.md`).
2. **Brand pack + accessibility/layout safety** — SUN.STUDIO canonical tokens
   (colours, Proxima Nova, `1920×1080` canvas), contrast, no overlapping text,
   projection legibility (`brand-packs/sun-studio/`, `AGENTS.md`).
3. **Component contracts + fidelity** — published-only retrieval, slot contracts,
   geometry, and the render-aware fidelity gate
   (`rules/component-composition.md`, `validate_component_fidelity.py`).
4. **Explicit user style profile** — this file.
5. **Agent taste / defaults** — only where nothing above decides.

A higher layer always wins. A profile preference that would violate any layer
above it is **rejected with a reason**, never applied.

## What a profile MAY influence

Today the profile influences **exactly one thing**: how the agent composes a slide
the user has ALREADY approved as `custom-local`. Everything else it produces is a
recorded note, not behaviour.

- **Custom-local composition**: density, hierarchy emphasis, spacing rhythm, chosen
  layout family, media bias, and tone — for slides the user explicitly approved via
  `unresolved_policy: "custom-local"`.
- **Non-binding tie-break advisories**: `resolve_style_profile.py` may record, in the
  design plan, that an equally-scored candidate matches a preferred intent. This is
  advisory ONLY — `score_visual_items.py` does not read the profile and no selection
  changes because of it. Acting on an advisory means re-scoring with an explicit
  `component_id`.

## What a profile may NEVER do

- Force a component reuse the scorer did not select (it cannot cross the
  reuse / needs_component / custom-local thresholds or override
  `no_shape_match`/eligibility).
- Change any SUN.STUDIO canonical token, font, or the `1920×1080` canvas.
- Reduce contrast/readability, allow overlapping or clipped text, or bypass the
  fidelity gate.
- Edit approved source content, ordering, or language.

## Recording (design-plan artifact)

`slide-system/scripts/resolve_style_profile.py` reads the selected profile plus
the (scorer-owned, read-only) `selection-report.json` and writes a design-plan
artifact recording: the profile `id`/`version`/`sha256`, the **applied**
preferences, and the **rejected** preferences with reasons. It never mutates
`selection-report.json`.
