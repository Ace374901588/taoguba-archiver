import os
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QThread

from taoguba_archiver.service import ArchiveBatchResult, ArchiveOptions
from taoguba_archiver.worker import ArchiveWorker


class FakeService:
    def __init__(self, *, wait_for_cancel=False):
        self.thread_id = None
        self.wait_for_cancel = wait_for_cancel

    def archive(self, urls, options, *, on_progress, cancellation):
        self.thread_id = threading.get_ident()
        if self.wait_for_cancel:
            limit = time.monotonic() + 2
            while not cancellation.is_cancelled() and time.monotonic() < limit:
                time.sleep(0.005)
        return ArchiveBatchResult(items=[], cancelled=cancellation.is_cancelled())


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def _run_worker(self, service, *, cancel=False):
        options = ArchiveOptions(Path("profile"), Path("exports"))
        worker = ArchiveWorker(service, ["https://www.tgb.cn/a/example"], options)
        thread = QThread()
        worker.moveToThread(thread)
        results = []
        worker.finished.connect(results.append)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.start()
        if cancel:
            worker.request_cancel()
        deadline = time.monotonic() + 3
        while thread.isRunning() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        thread.wait(1000)
        self.app.processEvents()
        return worker, results

    def test_runs_service_outside_gui_thread(self):
        service = FakeService()
        _worker, results = self._run_worker(service)
        self.assertNotEqual(service.thread_id, threading.get_ident())
        self.assertEqual(len(results), 1)

    def test_cancel_request_is_visible_while_worker_is_busy(self):
        service = FakeService(wait_for_cancel=True)
        _worker, results = self._run_worker(service, cancel=True)
        self.assertTrue(results[0].cancelled)


if __name__ == "__main__":
    unittest.main()
