"""Compile and run real capture policy/geometry/cancellation/diagnostic checks without screen access.

Only disposable build and synthetic diagnostic fixture files are written. No app is installed, no permission is requested,
and neither screen content nor the user's clipboard is read. The non-host architecture
is compile-checked for the app's macOS 11 deployment target, not runtime-validated.
"""
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativeCaptureTests(unittest.TestCase):
    def test_policy_geometry_cancellation_and_universal_compile(self):
        source = Path(__file__).resolve().with_name("NativeCapture.swift")
        main = """import AppKit
import Foundation
func L(_ text: String) -> String { text }
func Lf(_ text: String, _ args: CVarArg...) -> String { String(format: text, arguments: args) }
guard nativeCaptureSelfCheck() else { print("Capture policy/geometry/cancellation FAILED"); exit(1) }
print("Capture policy/geometry/cancellation PASS (no screen access)")
"""
        host = "arm64" if platform.machine() == "arm64" else "x86_64"
        with tempfile.TemporaryDirectory(prefix="galaxy-capture-check-") as folder:
            root = Path(folder)
            entry = root / "main.swift"
            entry.write_text(main)
            binaries = {}
            for arch in ("arm64", "x86_64"):
                output = root / ("capture-check-" + arch)
                result = subprocess.run(
                    ["xcrun", "swiftc", "-target", arch + "-apple-macos11", str(entry), str(source),
                     "-framework", "AppKit", "-framework", "CoreGraphics", "-framework", "ScreenCaptureKit",
                     "-o", str(output)], capture_output=True, text=True, timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                binaries[arch] = output
            result = subprocess.run([str(binaries[host])], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("PASS (no screen access)", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
