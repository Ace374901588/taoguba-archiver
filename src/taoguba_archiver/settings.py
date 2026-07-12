from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_config_dir


@dataclass(frozen=True)
class AppSettings:
    output_dir: str | None = None
    export_html: bool = True
    export_markdown: bool = False
    markdown_image_mode: str | None = None
    include_author_replies: bool = False
    login_confirmed: bool = False


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (
            path or Path(user_config_dir("TaogubaArchiver", appauthor=False)) / "settings.json"
        )

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {field for field in AppSettings.__dataclass_fields__}
            clean = {key: value for key, value in data.items() if key in allowed}
            settings = AppSettings(**clean)
            if settings.markdown_image_mode not in {None, "relative", "source", "embed"}:
                return AppSettings()
            if not settings.export_html and not settings.export_markdown:
                return AppSettings()
            return settings
        except (OSError, ValueError, TypeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
