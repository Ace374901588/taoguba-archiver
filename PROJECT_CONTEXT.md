# Project Context for the Next Codex Session

## Product intent

Taoguba Archiver is a standalone Windows/macOS desktop utility for archiving a few Taoguba article
URLs explicitly supplied by the user. It exports neutral, portable bundles and has no dependency on
StockVault, Obsidian or any private knowledge-base layout.

## Implemented

- Strict HTTPS allow-list for `tgb.cn` and `www.tgb.cn`; no discovery or user traversal.
- Dedicated, platform-native Chrome Profile and manual login flow.
- Main post and body images by default; author replies remain explicit opt-in.
- Versioned export schema with raw response, rendered DOM, metadata, hashes and image manifest.
- Independent, additive HTML and Markdown outputs.
- Markdown image modes: relative files, source URLs and embedded data URIs; callers choose explicitly.
- CLI/GUI-neutral `ArchiveService` with structured results, progress and cancellation token.
- PySide6 desktop GUI based on `gui_design/`, including settings persistence through `platformdirs`.
- Playwright construction, use and shutdown inside a worker thread for GUI archive/login flows.
- Item progress, cooperative cancellation, login-expiry detection and resume after login.
- Shared PyInstaller build command and Windows/macOS CI test/build workflow.
- Runtime SVG application icon and version metadata.

## Verification completed on Windows

- 30 unit tests pass on Python 3.11.
- Ruff lint and format checks pass.
- CLI help and source GUI smoke tests pass.
- Source Playwright smoke test launches installed Chrome with a temporary dedicated Profile.
- GUI smoke paths pass at 100%, 125% and 150% scale factors.
- PyInstaller produces `dist/TaogubaArchiver/`; packaged GUI and packaged Chrome smoke tests exit 0.
- Export tests prove HTML/Markdown coexistence, relative image rewriting and omission of `Set-Cookie`.
- Repository scans found no credential material or local absolute user paths.

## Remaining external confirmations

- Configure Git author name/email, then create the prepared initial commit.
- Run the connected GitHub Actions workflow to prove macOS tests, Retina behavior and packaging.
- User must choose the final public product/repository name and open-source license.
- User must choose publishing account, signing certificates and update service before public release.
- Public macOS distribution requires Developer ID signing and notarization.

Do not mark the full public-release roadmap complete until these confirmations are evidenced.
