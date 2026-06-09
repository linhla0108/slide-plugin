# SVG Manifest Schema

Top-level fields:

- `source`, `sha256`, `valid_xml`
- `width`, `height`, `viewBox`, `preserveAspectRatio`, `aspect_ratio`
- `tag_counts`, `id_count`, `text_mode`
- `texts`, `nodes`, `references`, `warnings`

Each node records document-order index, parent index, tag, ID, selected
attributes, resolved text, and optional path metadata. Image data URIs are
summarized rather than copied.

`text_mode` values:

- `native-text`: at least one text/tspan element exists.
- `probable-path-text`: paths exist without native text.
- `no-text-detected`: neither native text nor paths provide a text signal.

Reference records classify fragment, embedded-data, local-file, and external
URL targets, and state whether local references resolve.
