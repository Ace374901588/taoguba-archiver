# Export schema v1

Each explicitly requested article is written to a new collision-safe directory. Existing
directories are never reused or overwritten.

## Files

- `response.html`: original HTTP response bytes when available; always preserved for traceability.
- `rendered.html`: rendered DOM after page loading; always preserved for traceability.
- `article-body.html`: parsed main-body HTML; present when HTML export is enabled.
- `article.md`: Markdown copy; present when Markdown export is enabled.
- `metadata.json`: provenance, completion state, integrity hashes, export choices and asset manifest.
- `images/`: successfully downloaded images referenced by the parsed article body.

HTML and Markdown are independent, additive outputs. At least one must be selected.

## Markdown image modes

- `relative`: references downloaded files under `images/`; missing downloads fall back to source URLs.
- `source`: keeps absolute source image URLs.
- `embed`: embeds successfully downloaded images as data URIs; missing downloads fall back to source URLs.

No mode is silently selected when Markdown is first enabled; the caller must choose one.

## Metadata invariants

- `schema_version` is the integer `1`.
- `status` is `complete` or `incomplete`.
- `incomplete_reason` explains incomplete exports and is `null` for complete exports.
- Only allow-listed response headers are stored. Cookie, `Set-Cookie`, authorization tokens and
  Chrome Profile contents are never exported.
- `exports` records whether HTML and Markdown were requested and the selected Markdown image mode.
- `assets` records source URL, portable local path, content type, byte size, SHA-256 and download error.
