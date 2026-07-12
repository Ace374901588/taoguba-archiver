# Roadmap

## Milestone 0 — Local-first baseline

- [x] Standalone project structure and neutral `exports/` default.
- [x] URL validation and dedicated Chrome Profile.
- [x] Main-body HTML and image archive.
- [x] Metadata, integrity hashes and incomplete-page detection.
- [x] CLI and unit tests.

## Milestone 1 — Export formats

- [x] Define and version the stable export schema.
- [x] Implement additive HTML and Markdown exports.
- [x] Support relative, source-URL and embedded Markdown images.

## Milestone 2 — Local browser workspace

- [x] Run a loopback-only browser workspace without a desktop GUI bundle.
- [x] Persist non-sensitive browser-workspace preferences with `platformdirs`.
- [x] Support dedicated-Profile login, background archival, cancellation and progress events.
- [x] Keep the browser interface responsive while Playwright runs in background threads.

## Milestone 3 — Open-source readiness

- [x] Add cross-platform CLI/Web test workflow.
- [ ] Confirm macOS browser-workspace tests in a connected GitHub repository.
- [ ] Decide license and contribution policy.
- [ ] Add release automation only if a distribution channel is later needed.
