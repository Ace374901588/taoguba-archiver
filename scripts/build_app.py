from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the native Taoguba Archiver desktop app")
    parser.add_argument("--clean", action="store_true", help="Remove previous build output first")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    if args.clean:
        for directory in (project_root / "build" / "pyinstaller", project_root / "dist"):
            if directory.exists():
                shutil.rmtree(directory)

    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            "Install build dependencies first: python -m pip install -e '.[build]'"
        ) from exc

    PyInstaller.__main__.run(
        [
            str(project_root / "scripts" / "gui_entry.py"),
            "--name=TaogubaArchiver",
            "--noconfirm",
            "--windowed",
            "--onedir",
            f"--distpath={project_root / 'dist'}",
            f"--workpath={project_root / 'build' / 'pyinstaller'}",
            f"--specpath={project_root / 'build'}",
            "--collect-all=playwright",
            "--collect-data=taoguba_archiver",
            "--hidden-import=playwright.sync_api",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
