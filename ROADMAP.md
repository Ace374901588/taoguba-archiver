# Roadmap

## Milestone 0 — Standalone baseline

- [x] Separate project structure and neutral `exports/` default.
- [x] URL validation and dedicated Chrome Profile.
- [x] Main-body HTML and image archive.
- [x] Metadata, integrity hashes and incomplete-page detection.
- [x] CLI and unit tests.

## Milestone 1 — Export formats

- [x] Define the stable export schema and version it.
- [x] Implement Markdown conversion.
- [x] Support HTML and Markdown simultaneously.
- [x] Implement selectable relative, source-URL and embedded image behavior.
- [x] Add export-format tests.

## Milestone 2 — Desktop GUI

- [x] Extract a CLI/GUI-neutral service layer.
- [x] Implement the PySide6 main window from `gui_design/`.
- [x] Add background worker, progress, cancellation and resume after login.
- [x] Persist non-sensitive settings with `platformdirs`.
- [x] Validate Windows 100%, 125% and 150% display scaling smoke paths.
- [ ] Validate macOS Retina behavior on macOS hardware/runner.

## Milestone 3 — Distribution

- [x] Add a shared, reproducible PyInstaller build command for Windows and macOS.
- [x] Add a scalable runtime application icon and application version metadata.
- [x] Add source and packaged GUI/Chrome smoke commands to both CI operating systems.
- [ ] Confirm macOS smoke results in a connected GitHub repository.
- [ ] Decide license and contribution policy.
- [x] Add cross-platform test/build GitHub Actions workflow.
- [ ] Add GitHub Actions release workflow after repository and release identity are confirmed.
- [ ] Add code signing and macOS notarization for public releases.
