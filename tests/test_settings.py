import tempfile
import unittest
from pathlib import Path

from taoguba_archiver.settings import AppSettings, SettingsStore


class SettingsTests(unittest.TestCase):
    def test_round_trips_non_sensitive_workspace_preferences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SettingsStore(Path(temp_dir) / "settings.json")
            settings = AppSettings(
                output_dir=str(Path(temp_dir) / "exports"),
                export_html=True,
                export_markdown=True,
                markdown_image_mode="relative",
                include_author_replies=True,
                login_confirmed=True,
            )
            store.save(settings)

            self.assertEqual(store.load(), settings)
            saved = (Path(temp_dir) / "settings.json").read_text(encoding="utf-8")
            self.assertNotIn("cookie", saved.lower())
            self.assertNotIn("token", saved.lower())

    def test_invalid_or_missing_file_falls_back_to_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            store = SettingsStore(path)
            self.assertEqual(store.load(), AppSettings())
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(store.load(), AppSettings())
