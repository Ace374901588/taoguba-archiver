# Project Context for the Next Codex Session

## Product intent

Taoguba Archiver is a standalone, local-first CLI and browser workspace for archiving a few
explicitly supplied Taoguba article URLs. It exports portable bundles and has no dependency on
StockVault, Obsidian or any private knowledge-base layout.

## Implemented

- Strict HTTPS allow-list for `tgb.cn` and `www.tgb.cn`; no discovery or user traversal.
- Dedicated, platform-native Chrome Profile and manual login flow.
- Main post and body images by default; author replies remain explicit opt-in.
- Versioned export schema with raw response, rendered DOM, metadata, hashes and image manifest.
- Independent, additive HTML and Markdown outputs.
- CLI entry point plus a local browser workspace bound only to `127.0.0.1`.
- Browser-side progress, cancellation and login confirmation backed by background Python threads.
- Settings persist without cookies, tokens or profile data.

## Verification baseline

- Unit tests cover core parsing, CLI, exports, settings, service behavior and loopback Web APIs.
- CLI and browser-workspace help commands are part of CI.
- Repository scans reject credential material and local absolute user paths in changes.

## Remaining external confirmations

- Run the connected GitHub Actions workflow to prove Windows/macOS CLI and browser-workspace tests.
- User must choose the final public product/repository name and open-source license.
- User must choose any future hosting or distribution channel before release automation is added.
