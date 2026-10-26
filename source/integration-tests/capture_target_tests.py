"""Disposable API tests for capture target selection and cancellation.

The real local API, job queue, validation and artifact registration run against
temporary state. Native screen capture is explicitly mocked; no real screen,
permission, installed app, clipboard or approved user file is accessed.
"""
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_tests as reviewed
from common import AgentError
from PIL import Image


class CaptureNativeMock(reviewed.ApprovalFixture):
    def __init__(self, image):
        self.image = image
        self.calls = []
        self.cancelled = False
        self.started = threading.Event()
        self.release = None

    def call(self, operation, args=None, timeout=90, cancel=None):
        self.calls.append((operation, dict(args or {})))
        if operation != "capture.start":
            raise AgentError("unsupported")
        self.started.set()
        if self.release is not None:
            self.release.wait(3)
        if self.cancelled:
            raise AgentError("cancelled")
        # Each real capture produces a fresh output; storage may move that output.
        fresh=self.image.with_name('capture-'+str(len(self.calls))+'.png');fresh.write_bytes(self.image.read_bytes())
        return {"paths": [str(fresh)]}


class CaptureTargetTests(unittest.TestCase):
    request = reviewed.ReviewAPITests.request

    def setUp(self):
        reviewed.ReviewAPITests.setUp(self)
        self.image = self.path / "mock-capture.png"
        Image.new("RGBA", (24, 16), "white").save(self.image)
        self.original = self.image.read_bytes()
        self.native = CaptureNativeMock(self.image)
        self.native.root = self.agent.bridge.root
        self.agent.bridge = self.native

    def tearDown(self):
        if self.native.release is not None:
            self.native.release.set()
        reviewed.ReviewAPITests.tearDown(self)

    def start(self, options):
        return self.request("POST", "/jobs", {"operation": "capture", "inputs": [], "options": options})

    def finished(self, ident):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            status, answer = self.request("GET", "/jobs/" + ident)
            self.assertEqual(status, 200, answer)
            if answer["job"]["status"] not in ("queued", "running"):
                return answer["job"]
            time.sleep(0.01)
        self.fail("Temporary capture job did not finish")

    def test_ask_target_is_forwarded_for_area_full_and_window(self):
        for mode in ("area", "full", "window"):
            with self.subTest(mode=mode):
                status, answer = self.start({"mode": mode, "monitor": -1})
                self.assertEqual(status, 202, answer)
                job = self.finished(answer["job"]["id"])
                self.assertEqual(job["status"], "complete", job)
                self.assertEqual(self.native.calls[-1], ("capture.start", {"mode": mode, "monitor": -1}))
                self.assertEqual(len(job["result"]["files"]), 1)
        self.assertEqual(self.image.read_bytes(), self.original)

    def test_explicit_secondary_monitor_is_preserved(self):
        status, answer = self.start({"mode": "full", "monitor": 2})
        self.assertEqual(status, 202, answer)
        self.assertEqual(self.finished(answer["job"]["id"])["status"], "complete")
        self.assertEqual(self.native.calls, [("capture.start", {"mode": "full", "monitor": 2})])

    def test_omitted_monitor_never_forces_monitor_zero(self):
        status, answer = self.start({"mode": "full"})
        self.assertEqual(status, 202, answer)
        self.assertEqual(self.finished(answer["job"]["id"])["status"], "complete")
        self.assertEqual(self.native.calls[0][1].get("monitor", -1), -1)

    def test_invalid_monitor_never_reaches_native_mock(self):
        for value in (-2, -1.5, 0.5, True, False, "-1", None, [], {}, 10_000):
            with self.subTest(monitor=value):
                status, answer = self.start({"mode": "full", "monitor": value})
                if status == 202:
                    job = self.finished(answer["job"]["id"])
                    self.assertEqual(job["status"], "failed", job)
                    self.assertEqual(job["errorCode"], "invalidRequest", job)
                else:
                    self.assertEqual(status, 400, answer)
                    self.assertEqual(answer["errorCode"], "invalidRequest", answer)
        self.assertEqual(self.native.calls, [])

    def test_cancelled_picker_does_not_register_an_image(self):
        self.native.cancelled = True
        before = set(self.agent.files)
        status, answer = self.start({"mode": "full", "monitor": -1})
        self.assertEqual(status, 202, answer)
        job = self.finished(answer["job"]["id"])
        self.assertEqual(job["status"], "cancelled", job)
        self.assertIsNone(job["result"])
        self.assertEqual(set(self.agent.files), before)
        self.assertEqual(self.image.read_bytes(), self.original)

    def test_late_native_completion_after_cancel_never_registers_image(self):
        self.native.release = threading.Event()
        before = set(self.agent.files)
        status, answer = self.start({"mode": "full", "monitor": -1})
        self.assertEqual(status, 202, answer)
        ident = answer["job"]["id"]
        self.assertTrue(self.native.started.wait(2))
        self.assertEqual(self.request("POST", "/jobs/" + ident + "/cancel", {})[0], 200)
        self.native.release.set()
        until = time.monotonic() + 3
        while self.agent.jobs_limit._value < 8 and time.monotonic() < until:
            time.sleep(0.01)
        self.assertEqual(self.agent.jobs[ident]["status"], "cancelled")
        self.assertIsNone(self.agent.jobs[ident]["result"])
        self.assertEqual(set(self.agent.files), before)
        self.assertEqual(self.image.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
