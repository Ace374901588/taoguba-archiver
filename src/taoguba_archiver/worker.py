from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from .service import ArchiveOptions, ArchiveService, CancellationToken


class ArchiveWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: ArchiveService, urls: list[str], options: ArchiveOptions) -> None:
        super().__init__()
        self._service = service
        self._urls = urls
        self._options = options
        self._cancellation = CancellationToken()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.archive(
                self._urls,
                self._options,
                on_progress=self.progress.emit,
                cancellation=self._cancellation,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)

    def request_cancel(self) -> None:
        self._cancellation.cancel()


class LoginWorker(QObject):
    browser_opened = Signal()
    finished = Signal(bool)
    failed = Signal(str)

    def __init__(self, service: ArchiveService, options: ArchiveOptions) -> None:
        super().__init__()
        self._service = service
        self._options = options
        self._decision = Event()
        self._confirmed = False

    def _wait_for_confirmation(self) -> None:
        self.browser_opened.emit()
        self._decision.wait()
        if not self._confirmed:
            raise RuntimeError("登录已取消")

    @Slot()
    def run(self) -> None:
        try:
            self._service.login(self._options, wait_for_confirmation=self._wait_for_confirmation)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(True)

    def confirm(self) -> None:
        self._confirmed = True
        self._decision.set()

    def cancel(self) -> None:
        self._decision.set()
