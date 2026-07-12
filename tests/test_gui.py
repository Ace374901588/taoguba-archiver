import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from taoguba_archiver.gui import MainWindow, UrlInput
from taoguba_archiver.settings import SettingsStore


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.window = MainWindow(
            settings_store=SettingsStore(Path(self.temp_dir.name) / "settings.json")
        )

    def tearDown(self):
        self.window.close()
        self.temp_dir.cleanup()

    def test_defaults_and_last_format_invariant(self):
        self.assertTrue(self.window.html_checkbox.isChecked())
        self.assertFalse(self.window.markdown_checkbox.isChecked())
        self.window.html_checkbox.click()
        self.assertTrue(self.window.html_checkbox.isChecked())
        self.assertIn("至少选择一种", self.window.format_help.text())

    def test_start_requires_valid_url_and_destination(self):
        self.window.url_input.setPlainText("https://www.tgb.cn/a/example")
        self.window.validate_inputs()
        self.assertFalse(self.window.start_button.isEnabled())
        self.window.destination_edit.setText(str(Path(self.temp_dir.name) / "exports"))
        self.window.validate_inputs()
        self.assertTrue(self.window.start_button.isEnabled())

    def test_markdown_requires_explicit_image_mode(self):
        self.window.markdown_checkbox.click()
        self.assertTrue(self.window.markdown_mode.isEnabled())
        self.assertEqual(self.window.markdown_mode.currentIndex(), 0)

    def test_url_input_loads_utf8_text_file_and_ignores_comments(self):
        path = Path(self.temp_dir.name) / "urls.txt"
        path.write_text(
            "# comment\nhttps://www.tgb.cn/a/one\n\nhttps://www.tgb.cn/a/two\n",
            encoding="utf-8-sig",
        )
        input_widget = UrlInput()
        input_widget.load_url_file(path)
        self.assertEqual(
            input_widget.toPlainText(),
            "https://www.tgb.cn/a/one\nhttps://www.tgb.cn/a/two",
        )

    def test_layout_stacks_without_horizontal_scroll_at_minimum_width(self):
        self.window.resize(860, 620)
        self.window.show()
        self.app.processEvents()
        left_position = self.window.content.getItemPosition(
            self.window.content.indexOf(self.window.left_panel)
        )
        right_position = self.window.content.getItemPosition(
            self.window.content.indexOf(self.window.right_panel)
        )
        self.assertEqual(left_position[:2], (0, 0))
        self.assertEqual(right_position[:2], (1, 0))
        self.assertEqual(
            self.window.content_scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff
        )


if __name__ == "__main__":
    unittest.main()
