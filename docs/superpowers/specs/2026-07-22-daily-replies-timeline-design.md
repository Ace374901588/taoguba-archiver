# Daily replies timeline reading layout

## Goal

Make standalone `daily-replies.html` faster to scan on desktop without sacrificing readable long
replies or offline portability.

## Chosen layout

Each reply is a horizontal timeline row.

- The left rail is 88px wide and contains the `HH:MM` time, a circular node and a continuous
  vertical line.
- The right column uses the remaining width for the source-post label, reply body and optional
  associated-reply quotation.
- Desktop pages use a responsive maximum width of 1440px and compact row separators instead of
  large independent cards.
- The source-post label and original-post link remain available at the top of each entry.
- Associated replies remain visually subordinate using a muted quotation treatment.

## Responsive behavior

- At narrow widths, the time rail shrinks to 60px while retaining the time and node.
- Reply content remains a single reading column; no content is hidden or horizontally clipped.
- Local images remain fluid and retain their existing local-only references.

## Scope and safety

- Change only the generated daily-replies HTML structure and CSS.
- Keep existing metadata, source links, image sanitization and offline behavior unchanged.
- Regenerate the already exported 2026-07-21 file after the renderer is updated.

## Verification

- Rendering tests assert the timeline markup and responsive CSS hooks.
- Existing parser, export and CLI/Web tests continue to pass.
- The regenerated HTML is checked for 52 replies, associated-reply contexts, and local image paths.
