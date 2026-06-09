---
name: svg-extractor
description: Inspect and extract structure, geometry, text mode, styles, references, and reusable vector assets from SVG files. Use when SVG is an input source for slide reconstruction, component extraction, visual comparison, or PPTX planning.
---

# SVG Extractor

Use this skill to turn an input SVG into auditable structural evidence. It does
not replace the PPTX as the content authority or the PNG as the appearance
authority.

## Workflow

1. Validate the file:

   ```bash
   xmllint --noout input.svg
   ```

2. Extract a JSON manifest:

   ```bash
   python3 scripts/extract_svg.py input.svg --output svg-manifest.json
   ```

   The manifest is transient inspection output. Write it to a scratch path and
   read what you need — never commit `*-svg-manifest.json` into a component
   extraction's `evidence/` (or any deliverable). It can be several hundred KB
   per SVG and nothing downstream consumes it.

3. Open or serve the original SVG in a real browser and capture a preview.
   Compare that preview with the corresponding PNG. Do not assume successful XML
   parsing means successful rendering.

4. Report:
   - dimensions, viewBox, and aspect ratio;
   - element/tag counts and document-order nodes;
   - IDs, groups, transforms, and references;
   - text/tspan content and whether text appears converted to paths;
   - gradients, patterns, clip paths, masks, filters, markers, symbols, and use;
   - embedded and external images;
   - missing local references and unsupported or risky features.

5. Use SVG geometry only when its browser render agrees with the PNG. Keep PPTX
   text authoritative.

## Requirements

- Use `xml.etree.ElementTree`; no third-party Python package is required.
- Never expand base64 data URIs into JSON. Record media type and byte estimate.
- Preserve full path data in the manifest unless `--omit-path-data` is used.
- Treat document order as SVG paint order; later siblings normally paint above
  earlier siblings.
- Flag external URLs and missing local files.
- Flag probable text-as-path when paths exist but no `<text>`/`<tspan>` nodes do.
- Do not infer wording from vector paths.

The output schema is documented in `references/output-schema.md`.
