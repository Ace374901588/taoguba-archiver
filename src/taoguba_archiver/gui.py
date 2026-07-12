from __future__ import annotations

import argparse
import os
import sys
import tempfile
from importlib.resources import as_file, files
from pathlib import Path

from platformdirs import user_data_dir
from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .core import validate_article_url
from . import __version__
from .service import ArchiveOptions, ArchiveService
from .settings import AppSettings, SettingsStore
from .worker import ArchiveWorker, LoginWorker


LIGHT_STYLE = """
QWidget { color: #18212F; font-size: 14px; }
QMainWindow, QWidget#root { background: #F4F6F8; }
QFrame[card="true"] { background: #FFFFFF; border: 1px solid #DCE2E8; border-radius: 10px; }
QLabel[muted="true"] { color: #5E6B7A; font-size: 12px; }
QLabel[error="true"] { color: #B42318; font-size: 12px; }
QPlainTextEdit, QLineEdit, QComboBox, QListWidget { background: #FFFFFF; border: 1px solid #B8C2CE; border-radius: 6px; padding: 7px; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #2563EB; }
QPushButton { min-height: 36px; padding: 0 14px; border: 1px solid #B8C2CE; border-radius: 6px; background: #FFFFFF; }
QPushButton:hover { background: #F8FAFC; }
QPushButton:focus { border: 2px solid #2563EB; }
QPushButton#primary { color: white; background: #2563EB; border-color: #2563EB; font-weight: 600; }
QPushButton#primary:hover { background: #1D4ED8; }
QPushButton:disabled { color: #8B96A5; background: #EEF1F4; }
QProgressBar { border: 1px solid #DCE2E8; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #2563EB; }
"""

DARK_STYLE = """
QWidget { color: #F3F6FA; font-size: 14px; }
QMainWindow, QWidget#root { background: #0F1722; }
QFrame[card="true"] { background: #172131; border: 1px solid #344154; border-radius: 10px; }
QLabel[muted="true"] { color: #AAB5C3; font-size: 12px; }
QLabel[error="true"] { color: #FB7185; font-size: 12px; }
QPlainTextEdit, QLineEdit, QComboBox, QListWidget { background: #1C2839; border: 1px solid #536278; border-radius: 6px; padding: 7px; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #60A5FA; }
QPushButton { min-height: 36px; padding: 0 14px; border: 1px solid #536278; border-radius: 6px; background: #1C2839; }
QPushButton:hover { background: #25354A; }
QPushButton:focus { border: 2px solid #60A5FA; }
QPushButton#primary { color: #0F1722; background: #60A5FA; border-color: #60A5FA; font-weight: 600; }
QPushButton#primary:hover { background: #93C5FD; }
QPushButton:disabled { color: #718096; background: #202B3B; }
QProgressBar { border: 1px solid #344154; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #60A5FA; }
"""


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(8)
    label = QLabel(title)
    label.setStyleSheet("font-weight: 600;")
    layout.addWidget(label)
    return frame, layout


class UrlInput(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def load_url_file(self, path: Path) -> None:
        if path.suffix.lower() != ".txt":
            raise ValueError("只支持拖入 .txt 文本文件")
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if lines:
            existing = self.toPlainText().strip()
            self.setPlainText("\n".join(part for part in (existing, "\n".join(lines)) if part))

    def dragEnterEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if len(paths) == 1 and paths[0].suffix.lower() == ".txt":
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if len(paths) == 1:
            try:
                self.load_url_file(paths[0])
            except (OSError, UnicodeError, ValueError):
                event.ignore()
                return
            event.acceptProposedAction()
            return
        event.ignore()


def _ensure_cjk_ui_font() -> None:
    app = QApplication.instance()
    available = set(QFontDatabase.families())
    for family in ("Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC"):
        if family in available:
            font = QFont(app.font())
            font.setFamily(family)
            app.setFont(font)
            return


class MainWindow(QMainWindow):
    def __init__(self, *, settings_store: SettingsStore | None = None, service=None) -> None:
        super().__init__()
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.service = service or ArchiveService()
        self.worker = None
        self.worker_thread = None
        self.login_worker = None
        self.login_thread = None
        self._resume_urls: list[str] = []
        self._wide_layout = True
        _ensure_cjk_ui_font()
        self._build_ui()
        self._apply_settings()
        self._apply_theme()
        self.validate_inputs(show_errors=False)

    def _build_ui(self) -> None:
        self.setWindowTitle("淘股吧文章归档器")
        icon_resource = files("taoguba_archiver").joinpath("assets/app-icon.svg")
        with as_file(icon_resource) as icon_path:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1040, 720)
        self.setMinimumSize(860, 620)
        root = QWidget(objectName="root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("淘股吧文章归档器")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()
        self.login_status = QLabel("未登录")
        self.login_status.setAccessibleName("淘股吧登录状态")
        header.addWidget(self.login_status)
        self.settings_button = QPushButton("设置")
        self.settings_button.setToolTip("当前版本的常用设置位于主窗口")
        self.settings_button.clicked.connect(self.show_settings_info)
        header.addWidget(self.settings_button)
        outer.addLayout(header)

        content_widget = QWidget()
        self.content = QGridLayout(content_widget)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        self.left_panel = self._build_left_panel()
        self.right_panel = self._build_right_panel()
        self.content.addWidget(self.left_panel, 0, 0)
        self.content.addWidget(self.right_panel, 0, 1)
        self.content.setColumnStretch(0, 2)
        self.content.setColumnStretch(1, 1)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content_scroll.setWidget(content_widget)
        outer.addWidget(self.content_scroll, 1)

        footer = QHBoxLayout()
        self.global_status = QLabel("准备就绪")
        self.global_status.setAccessibleName("归档状态")
        footer.addWidget(self.global_status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        footer.addWidget(self.progress_bar)
        footer.addStretch()
        self.stop_button = QPushButton("停止")
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.stop_archive)
        footer.addWidget(self.stop_button)
        self.start_button = QPushButton("开始归档", objectName="primary")
        self.start_button.clicked.connect(self.start_archive)
        footer.addWidget(self.start_button)
        outer.addLayout(footer)
        self.setCentralWidget(root)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_archive)
        QShortcut(QKeySequence("Meta+Return"), self, activated=self.start_archive)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.stop_archive)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        composer, card = _card("文章链接")
        self.url_input = UrlInput()
        self.url_input.setPlaceholderText("https://www.tgb.cn/a/ARTICLE_ID\n每行一个链接")
        self.url_input.setAccessibleName("淘股吧文章链接，每行一个")
        self.url_input.setMinimumHeight(150)
        self.url_input.textChanged.connect(lambda: self.validate_inputs(show_errors=False))
        card.addWidget(self.url_input)
        helper = QLabel("只解析主帖正文和正文图片，不获取评论")
        helper.setProperty("muted", True)
        card.addWidget(helper)
        self.url_error = QLabel("")
        self.url_error.setProperty("error", True)
        self.url_error.setWordWrap(True)
        card.addWidget(self.url_error)
        layout.addWidget(composer)

        queue_card, queue_layout = _card("任务队列")
        self.queue = QListWidget()
        self.queue.setAccessibleName("归档任务队列")
        self.queue.addItem("输入文章链接后，任务会显示在这里")
        queue_layout.addWidget(self.queue)
        layout.addWidget(queue_card, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        session, box = _card("登录状态")
        self.login_help = QLabel("使用应用专用 Chrome Profile，不读取日常浏览器资料。")
        self.login_help.setProperty("muted", True)
        self.login_help.setWordWrap(True)
        box.addWidget(self.login_help)
        self.login_button = QPushButton("登录淘股吧")
        self.login_button.clicked.connect(self.start_login)
        box.addWidget(self.login_button)
        layout.addWidget(session)

        destination, box = _card("保存位置")
        row = QHBoxLayout()
        self.destination_edit = QLineEdit()
        self.destination_edit.setReadOnly(True)
        self.destination_edit.setPlaceholderText("请选择导出目录")
        self.destination_edit.textChanged.connect(lambda: self.validate_inputs(show_errors=False))
        row.addWidget(self.destination_edit, 1)
        choose = QPushButton("选择")
        choose.clicked.connect(self.choose_destination)
        row.addWidget(choose)
        box.addLayout(row)
        self.open_folder_button = QPushButton("打开目录")
        self.open_folder_button.clicked.connect(self.open_destination)
        box.addWidget(self.open_folder_button)
        layout.addWidget(destination)

        scope, box = _card("内容范围")
        label = QLabel("主帖正文 + 正文图片")
        box.addWidget(label)
        self.replies_checkbox = QCheckBox("包含楼主跟帖（高级）")
        self.replies_checkbox.toggled.connect(self.save_settings)
        box.addWidget(self.replies_checkbox)
        layout.addWidget(scope)

        formats, box = _card("输出格式")
        self.html_checkbox = QCheckBox("HTML 原文")
        self.markdown_checkbox = QCheckBox("Markdown 副本")
        self.html_checkbox.toggled.connect(self._format_changed)
        self.markdown_checkbox.toggled.connect(self._format_changed)
        box.addWidget(self.html_checkbox)
        box.addWidget(self.markdown_checkbox)
        self.markdown_mode = QComboBox()
        self.markdown_mode.addItem("选择 Markdown 图片方式…", None)
        self.markdown_mode.addItem("相对路径（便于随导出包移动）", "relative")
        self.markdown_mode.addItem("保留原图 URL", "source")
        self.markdown_mode.addItem("内嵌图片（文件较大）", "embed")
        self.markdown_mode.currentIndexChanged.connect(self.save_settings)
        box.addWidget(self.markdown_mode)
        self.format_help = QLabel("")
        self.format_help.setProperty("muted", True)
        self.format_help.setWordWrap(True)
        box.addWidget(self.format_help)
        layout.addWidget(formats)
        layout.addStretch()
        return panel

    def _apply_settings(self) -> None:
        self.html_checkbox.setChecked(self.settings.export_html)
        self.markdown_checkbox.setChecked(self.settings.export_markdown)
        self.replies_checkbox.setChecked(self.settings.include_author_replies)
        if self.settings.output_dir:
            self.destination_edit.setText(self.settings.output_dir)
        mode_index = self.markdown_mode.findData(self.settings.markdown_image_mode)
        self.markdown_mode.setCurrentIndex(max(mode_index, 0))
        self.login_status.setText("已登录" if self.settings.login_confirmed else "未登录")
        self.login_button.setText("重新登录" if self.settings.login_confirmed else "登录淘股吧")
        self._format_changed()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        dark = app.palette().window().color().lightness() < 128
        self.setStyleSheet(DARK_STYLE if dark else LIGHT_STYLE)

    def _format_changed(self) -> None:
        sender = self.sender()
        if not self.html_checkbox.isChecked() and not self.markdown_checkbox.isChecked():
            if sender is self.markdown_checkbox:
                self.markdown_checkbox.setChecked(True)
            else:
                self.html_checkbox.setChecked(True)
            self.format_help.setText("HTML 和 Markdown 至少选择一种输出格式")
        elif self.html_checkbox.isChecked() and self.markdown_checkbox.isChecked():
            self.format_help.setText("每篇文章将同时生成 HTML 和 Markdown 文件")
        else:
            self.format_help.setText("")
        self.markdown_mode.setEnabled(self.markdown_checkbox.isChecked())
        self.save_settings()
        self.validate_inputs(show_errors=False)

    def _urls(self) -> list[str]:
        return [line.strip() for line in self.url_input.toPlainText().splitlines() if line.strip()]

    def validate_inputs(self, *, show_errors: bool = True) -> bool:
        urls = self._urls()
        error = ""
        if urls:
            for line_number, url in enumerate(urls, 1):
                try:
                    validate_article_url(url)
                except ValueError as exc:
                    error = f"第 {line_number} 行：{exc}"
                    break
        if show_errors:
            self.url_error.setText(error)
        markdown_ready = (
            not self.markdown_checkbox.isChecked() or self.markdown_mode.currentData() is not None
        )
        ready = bool(urls) and not error and bool(self.destination_edit.text()) and markdown_ready
        self.start_button.setEnabled(ready and self.worker is None)
        self.open_folder_button.setEnabled(
            Path(self.destination_edit.text()).is_dir() if self.destination_edit.text() else False
        )
        return ready

    def choose_destination(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择导出目录", self.destination_edit.text()
        )
        if selected:
            self.destination_edit.setText(selected)
            self.save_settings()

    def open_destination(self) -> None:
        from PySide6.QtCore import QUrl

        path = self.destination_edit.text()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def save_settings(self) -> None:
        if not hasattr(self, "html_checkbox"):
            return
        settings = AppSettings(
            output_dir=self.destination_edit.text() or None,
            export_html=self.html_checkbox.isChecked(),
            export_markdown=self.markdown_checkbox.isChecked(),
            markdown_image_mode=self.markdown_mode.currentData(),
            include_author_replies=self.replies_checkbox.isChecked(),
            login_confirmed=self.login_status.text() == "已登录",
        )
        self.settings = settings
        self.settings_store.save(settings)

    def show_settings_info(self) -> None:
        profile = Path(user_data_dir("TaogubaArchiver", appauthor=False)) / "chrome-profile"
        QMessageBox.information(
            self,
            "设置",
            f"常用设置已显示在主窗口并自动保存。\n\n专用登录 Profile：\n{profile}\n\n"
            "程序不会显示或导出 Cookie。",
        )

    def _options(self) -> ArchiveOptions:
        profile = Path(user_data_dir("TaogubaArchiver", appauthor=False)) / "chrome-profile"
        return ArchiveOptions(
            profile_dir=profile,
            output_dir=Path(self.destination_edit.text()),
            include_author_replies=self.replies_checkbox.isChecked(),
            export_html=self.html_checkbox.isChecked(),
            export_markdown=self.markdown_checkbox.isChecked(),
            markdown_image_mode=self.markdown_mode.currentData(),
        )

    def start_archive(self) -> None:
        if self.worker is not None or not self.validate_inputs(show_errors=True):
            return
        self._begin_archive(list(dict.fromkeys(self._urls())))

    def _begin_archive(self, urls: list[str]) -> None:
        self.queue.clear()
        for url in urls:
            self.queue.addItem(f"等待归档  ·  {url}")
        if urls:
            self.queue.item(0).setText(f"正在获取  ·  {urls[0]}")
        self.progress_bar.setRange(0, len(urls))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.stop_button.setVisible(True)
        self.url_input.setReadOnly(True)
        self.worker_thread = QThread(self)
        self.worker = ArchiveWorker(self.service, urls, self._options())
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.global_status.setText("正在归档")
        self.worker_thread.start()

    def stop_archive(self) -> None:
        if self.worker is not None:
            self.worker.request_cancel()
            self.global_status.setText("正在安全停止；当前页面处理完成后生效")
            self.stop_button.setEnabled(False)

    def _on_progress(self, event) -> None:
        self.progress_bar.setValue(event.completed)
        state = "完成" if event.complete else "正文不完整（已保存现场）"
        self.queue.item(event.completed - 1).setText(f"{state}  ·  {event.url}")
        if event.completed < event.total:
            next_item = self.queue.item(event.completed)
            next_url = next_item.text().split("  ·  ", 1)[-1]
            next_item.setText(f"正在获取  ·  {next_url}")
        self.start_button.setText(f"正在归档 {event.completed} / {event.total}")

    def _on_finished(self, result) -> None:
        if result.cancelled:
            self.global_status.setText("任务已取消；已完成的归档保留")
            for index in range(len(result.items), self.queue.count()):
                item = self.queue.item(index)
                url = item.text().split("  ·  ", 1)[-1]
                item.setText(f"已取消  ·  {url}")
        elif result.had_incomplete:
            login_items = [item for item in result.items if item.login_required]
            if login_items:
                self._resume_urls = [item.url for item in login_items]
                self.login_status.setText("登录失效")
                self.login_button.setText("重新登录")
                self.login_button.setFocus()
                self.global_status.setText("登录已失效；已保存现场，重新登录后将继续未完成项目")
                self.save_settings()
            else:
                self.global_status.setText("部分文章正文不完整；已保存现场，可检查网络后重试")
        else:
            self.global_status.setText("归档完成")

    def _on_failed(self, message: str) -> None:
        self.global_status.setText(f"归档失败：{message}。请检查链接、网络或登录状态后重试")
        for index in range(self.queue.count()):
            item = self.queue.item(index)
            if item.text().startswith("正在获取"):
                url = item.text().split("  ·  ", 1)[-1]
                item.setText(f"失败（可重试）  ·  {url}")
                break

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self.url_input.setReadOnly(False)
        self.stop_button.setVisible(False)
        self.stop_button.setEnabled(True)
        self.start_button.setText("开始归档")
        self.validate_inputs(show_errors=False)

    def start_login(self) -> None:
        if self.login_worker is not None:
            return
        answer = QMessageBox.information(
            self,
            "登录淘股吧",
            "程序将打开应用专用 Chrome 窗口。完成登录后回到这里确认。",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if answer != QMessageBox.Ok:
            return
        self.login_thread = QThread(self)
        self.login_worker = LoginWorker(self.service, self._options())
        self.login_worker.moveToThread(self.login_thread)
        self.login_thread.started.connect(self.login_worker.run)
        self.login_worker.browser_opened.connect(self._confirm_login)
        self.login_worker.finished.connect(self._login_finished)
        self.login_worker.failed.connect(self._login_failed)
        self.login_worker.finished.connect(self.login_thread.quit)
        self.login_worker.failed.connect(self.login_thread.quit)
        self.login_thread.finished.connect(self._cleanup_login)
        self.login_button.setEnabled(False)
        self.login_thread.start()

    def _confirm_login(self) -> None:
        answer = QMessageBox.question(
            self,
            "确认登录",
            "请在 Chrome 中完成登录，然后点击“是”。",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.login_worker.confirm()
        else:
            self.login_worker.cancel()

    def _login_finished(self, _success: bool) -> None:
        self.login_status.setText("已登录")
        self.login_button.setText("重新登录")
        self.global_status.setText("登录状态已保存，可以开始归档")
        self.save_settings()
        if self._resume_urls and self.worker is None:
            resume_urls = self._resume_urls
            self._resume_urls = []
            self._begin_archive(resume_urls)

    def _login_failed(self, message: str) -> None:
        self.global_status.setText(f"登录未完成：{message}")

    def _cleanup_login(self) -> None:
        if self.login_worker is not None:
            self.login_worker.deleteLater()
        if self.login_thread is not None:
            self.login_thread.deleteLater()
        self.login_worker = None
        self.login_thread = None
        self.login_button.setEnabled(True)

    def resizeEvent(self, event) -> None:
        wide = self.width() >= 900
        if wide != self._wide_layout:
            self.content.removeWidget(self.left_panel)
            self.content.removeWidget(self.right_panel)
            if wide:
                self.content.addWidget(self.left_panel, 0, 0)
                self.content.addWidget(self.right_panel, 0, 1)
                self.content.setColumnStretch(0, 2)
                self.content.setColumnStretch(1, 1)
            else:
                self.content.addWidget(self.left_panel, 0, 0)
                self.content.addWidget(self.right_panel, 1, 0)
                self.content.setColumnStretch(0, 1)
                self.content.setColumnStretch(1, 0)
            self._wide_layout = wide
        super().resizeEvent(event)

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.request_cancel()
            event.ignore()
            self.global_status.setText("请等待当前页面安全停止后再关闭")
            return
        if self.login_worker is not None:
            self.login_worker.cancel()
            event.ignore()
            return
        self.save_settings()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="淘股吧文章归档器桌面界面")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--browser-smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.browser_smoke_test:
        from .browser import TaogubaBrowser

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            browser = TaogubaBrowser(root / "profile", root / "exports", headless=True)
            manager, context = browser._launch()
            context.close()
            manager.stop()
        return 0
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Taoguba Archiver")
    app.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
