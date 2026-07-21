# Daily reply curation and standalone export

## Goal

Let readers remove low-value replies from a daily reply archive and download the
remaining material as a single portable HTML file.

## Automatic curation

Automatic curation runs while the daily archive is generated.  It removes only
high-confidence low-information replies:

- content that becomes empty after normalising whitespace, emoji, punctuation,
  and common decorative symbols;
- short acknowledgements and social fillers such as `收到`, `感谢`, `谢谢`,
  `哈哈`, `顶`, and their punctuation-only variants;
- an immediately adjacent duplicate of the same normalised reply text.

The filter is conservative.  It must keep a reply when it contains a concrete
viewpoint, a security name or code, price or market information, trading action,
strategy, time reference, causal explanation, or anything the heuristic cannot
classify confidently.  Automatically removed entries do not appear in the
initial archive HTML.

## Review controls

The archive header reports the original reply count, the automatic-filter count,
and the current retained count.  Every retained timeline item has a delete
control.  Deletion immediately removes the item from the reading view and
updates the retained count.  A single undo action restores the most recently
manually deleted item.

The controls only affect the open document until the reader exports it.  They
do not modify the source archive, browser profile, or any stored login state.

## Final export

The `下载精简 HTML` control creates a new, standalone HTML document from the
currently visible entries.  It omits the curation controls and filtered/deleted
items.  Images referenced by retained entries are embedded as data URLs so the
download remains usable after being moved independently of its original
`images/` directory.  If an image cannot be embedded, its visible image element
remains in the final export with its existing source and export still succeeds.

## Implementation boundaries

- Python owns conservative classification, metadata counts, and deterministic
  static HTML generation.
- Small inline JavaScript owns manual deletion, one-step undo, image embedding,
  and browser download of the final document.
- No new network access is introduced; the final export reads only images that
  belong to the already generated local archive.

## Verification

Tests cover high-confidence removal, preservation of uncertain/informative
replies, duplicate handling, count markup, delete/undo/export hooks, and the
absence of curation controls in the exported document template.  The complete
unit suite, linter, and a real reply-feed CLI smoke export must pass.
