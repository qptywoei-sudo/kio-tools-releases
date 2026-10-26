"""Real AI-free image outputs using disposable fixtures and bundled CPython/Pillow.

These tests check pixels and original-file preservation. They do not invoke a
model, a remote API, production state, a physical clipboard or OS permissions.
"""
from __future__ import annotations

import builtins
import ast
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "agent")]
import engine_extra as extra
from server import Agent
from PIL import Image


class ManualImageToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="galaxy-manual-image-")
        self.folder = Path(self.temp.name).resolve()
        self.output = self.folder / "results"
        self.source = self.folder / "original.png"
        image = Image.new("RGBA", (16, 12), (160, 40, 20, 128))
        image.putpixel((8, 6), (160, 40, 20, 0))
        image.putpixel((9, 6), (160, 40, 20, 37))
        image.save(self.source)
        self.original_sha = hashlib.sha256(self.source.read_bytes()).digest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), self.original_sha)
        self.temp.cleanup()

    def background(self, **options):
        return extra.OPS["image_background"]({
            "inputs": [str(self.source)], "output_dir": str(self.output), **options
        })

    def image_result(self, result):
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["files"]), 1)
        target = Path(result["files"][0])
        self.assertNotEqual(target, self.source)
        self.assertEqual(target.parent, self.output)
        with Image.open(target) as image:
            return image.convert("RGBA")

    def pattern(self):
        target = self.folder / "pattern.png"
        image = Image.new("RGBA", (24, 20))
        image.putdata([
            ((x * 41 + y * 17) % 256, (x * 13 + y * 59) % 256,
             (x * 73 + y * 19) % 256, 255)
            for y in range(image.height) for x in range(image.width)
        ])
        image.save(target)
        return target, image

    def mosaic(self, source, regions, **options):
        return extra.OPS["image_mosaic"]({
            "path": str(source), "regions": regions,
            "output_dir": str(self.output), **options
        })

    def test_transparent_background_preserves_rgba_when_no_erase_is_requested(self):
        result = self.image_result(self.background())
        with Image.open(self.source) as original:
            self.assertEqual(result.tobytes(), original.convert("RGBA").tobytes())

    def test_erase_and_restore_preserve_original_transparency(self):
        result = self.image_result(self.background(strokes=[
            {"points": [[8, 6]], "radius": 3},
            {"points": [[8, 6]], "radius": 1, "restore": True},
        ]))
        self.assertEqual(result.getpixel((8, 6))[3], 0)
        self.assertEqual(result.getpixel((9, 6))[3], 37)
        self.assertEqual(result.getpixel((7, 6))[3], 128)
        self.assertEqual(result.getpixel((6, 6))[3], 0)
        self.assertEqual(result.getpixel((0, 0)), (160, 40, 20, 128))

    def test_later_erase_takes_priority_over_restore(self):
        result = self.image_result(self.background(strokes=[
            {"points": [[8, 6]], "radius": 3},
            {"points": [[8, 6]], "radius": 3, "restore": True},
            {"points": [[8, 6]], "radius": 1},
        ]))
        self.assertEqual(result.getpixel((9, 6))[3], 0)
        self.assertEqual(result.getpixel((6, 6))[3], 128)

    def test_solid_background_fills_erased_and_original_transparent_pixels(self):
        result = self.image_result(self.background(
            background="solid", color="#123456",
            strokes=[{"points": [[6, 6]], "radius": 1}],
        ))
        self.assertEqual(result.getpixel((6, 6)), (18, 52, 86, 255))
        self.assertEqual(result.getpixel((8, 6)), (18, 52, 86, 255))
        expected = Image.new("RGBA", (1, 1), (18, 52, 86, 255))
        expected.alpha_composite(Image.new("RGBA", (1, 1), (160, 40, 20, 128)))
        self.assertEqual(result.getpixel((0, 0)), expected.getpixel((0, 0)))

    def test_gradient_replaces_background_with_correct_endpoints(self):
        transparent = self.folder / "transparent.png"
        Image.new("RGBA", (7, 5), (0, 0, 0, 0)).save(transparent)
        result = self.image_result(self.background(
            inputs=[str(transparent)], background="gradient", color="#ff0000", color2="#0000ff"
        ))
        self.assertEqual(result.getpixel((3, 0)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((3, 2)), (128, 0, 128, 255))
        self.assertEqual(result.getpixel((3, 4)), (0, 0, 255, 255))

    def test_image_background_fits_canvas_and_preserves_visible_foreground(self):
        front = self.folder / "foreground.png"
        foreground = Image.new("RGBA", (7, 5), (0, 0, 0, 0))
        foreground.putpixel((3, 2), (200, 40, 80, 255))
        foreground.save(front)
        back = self.folder / "replacement.png"
        Image.new("RGBA", (13, 19), (12, 190, 70, 255)).save(back)
        before = back.read_bytes()
        result = self.image_result(self.background(
            inputs=[str(front), str(back)], background="image", backgroundInput=1
        ))
        self.assertEqual(result.size, (7, 5))
        self.assertEqual(result.getpixel((0, 0)), (12, 190, 70, 255))
        self.assertEqual(result.getpixel((3, 2)), (200, 40, 80, 255))
        self.assertEqual(back.read_bytes(), before)

    def test_missing_replacement_is_reported_without_result_file(self):
        with self.assertRaisesRegex(ValueError, "inputMissing"):
            self.background(background="image", backgroundInput=1)
        self.assertFalse(self.output.exists())

    def test_manual_pixel_mosaic_changes_only_selected_rectangle(self):
        path, original = self.pattern()
        before = path.read_bytes()
        result = self.image_result(self.mosaic(path, [{
            "x": 4, "y": 3, "width": 12, "height": 10, "strength": 5, "mode": "pixel"
        }]))
        self.assertNotEqual(result.crop((4, 3, 16, 13)).tobytes(), original.crop((4, 3, 16, 13)).tobytes())
        for y in range(original.height):
            for x in range(original.width):
                if not (4 <= x < 16 and 3 <= y < 13):
                    self.assertEqual(result.getpixel((x, y)), original.getpixel((x, y)))
        self.assertEqual(path.read_bytes(), before)

    def test_ellipse_mosaic_keeps_rectangle_corners_intact(self):
        path, original = self.pattern()
        result = self.image_result(self.mosaic(path, [{
            "x": 4, "y": 3, "width": 12, "height": 12, "strength": 6,
            "mode": "pixel", "shape": "ellipse"
        }]))
        self.assertEqual(result.getpixel((4, 3)), original.getpixel((4, 3)))
        self.assertEqual(result.getpixel((15, 14)), original.getpixel((15, 14)))
        self.assertNotEqual(result.getpixel((10, 9)), original.getpixel((10, 9)))

    def test_blur_and_random_mosaic_work_without_face_detection(self):
        path, original = self.pattern()
        region = {"x": 3, "y": 3, "width": 14, "height": 12, "strength": 4}
        blur = self.image_result(self.mosaic(path, [{**region, "mode": "blur"}]))
        self.assertNotEqual(blur.crop((3, 3, 17, 15)).tobytes(), original.crop((3, 3, 17, 15)).tobytes())
        first = self.image_result(self.mosaic(path, [{**region, "mode": "random"}]))
        second = self.image_result(self.mosaic(path, [{**region, "mode": "random"}]))
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertNotEqual(first.tobytes(), original.tobytes())

    def test_face_detection_request_is_explicitly_unsupported(self):
        path, _ = self.pattern()
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.mosaic(path, [{"x": 1, "y": 1, "width": 10, "height": 10}], faces=True)
        self.assertFalse(self.output.exists())

    def test_mosaic_requires_manual_selection(self):
        path, _ = self.pattern()
        with self.assertRaisesRegex(ValueError, "inputMissing"):
            self.mosaic(path, [], faces=False)
        self.assertFalse(self.output.exists())

    def test_manual_processing_succeeds_with_model_and_detector_imports_blocked(self):
        original_import = builtins.__import__
        forbidden = {"onnxruntime", "torch", "tensorflow", "rembg", "transformers", "cv2"}
        def model_free_import(name, *args, **kwargs):
            if name.split(".")[0] in forbidden:
                raise AssertionError("AI model or detector import attempted")
            return original_import(name, *args, **kwargs)
        path, _ = self.pattern()
        with patch("builtins.__import__", side_effect=model_free_import):
            self.image_result(self.background(strokes=[{"points": [[5, 5]], "radius": 2}]))
            self.image_result(self.mosaic(path, [{
                "x": 2, "y": 2, "width": 12, "height": 10, "strength": 4, "mode": "random"
            }]))

    def test_manual_background_stays_available_on_older_macos(self):
        # An isolated version fixture checks discovery, not actual macOS 12 hardware.
        agent = Agent.__new__(Agent)
        agent.bridge = SimpleNamespace(ready=lambda: False)
        with patch("server.sys.platform", "darwin"), \
             patch("server.platform.mac_ver", return_value=("12.7.6", ("", "", ""), "")), \
             patch("server.platform.machine", return_value="arm64"):
            operations = agent.operations()
        self.assertIn("image_background", operations)
        self.assertIn("image_mosaic", operations)
        self.assertNotIn("video_gif", operations)


class AIFreeSourceClosureTests(unittest.TestCase):
    def parse(self, name):
        return ast.parse((ROOT / "agent" / name).read_text(encoding="utf-8"))

    def test_dependency_fetcher_preserves_other_versions_without_model_runtime(self):
        tree = self.parse("fetch_dependencies.py")
        packages = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "packages"
                                for target in node.targets))
        self.assertEqual(packages, {
            "numpy": "2.5.3", "watchdog": "6.0.0", "imageio-ffmpeg": "0.6.0",
            "opencv-python-headless": "4.13.0.92", "flatbuffers": "", "packaging": "",
            "protobuf": "", "sympy": "", "mpmath": "", "coloredlogs": "",
            "humanfriendly": "", "python-pptx": "", "lxml": "", "XlsxWriter": "",
            # Already required by the existing signed account/Drive authentication.
            "PyJWT": "2.15.1", "cryptography": "50.0.2", "cffi": "2.1.1", "pycparser": "3.11",
        })
        strings = [node.value.lower() for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertFalse(any(any(word in value for word in ("onnx", "u2net", "rembg"))
                             for value in strings))
        # The helper retains verified wheel downloads; no executable network calls here.
        self.assertIn("https://pypi.org/pypi/", strings)
        self.assertFalse(any(value.startswith("https://github.com/") for value in strings))

    def test_dependency_probe_only_inspects_required_non_model_packages(self):
        tree = self.parse("dependency_probe.py")
        names = next(ast.literal_eval(node.iter) for node in tree.body if isinstance(node, ast.For))
        self.assertEqual(names, ["opencv-python-headless", "numpy", "watchdog", "imageio-ffmpeg"])

    def test_image_tool_dispatch_has_no_automatic_model_or_face_detector_calls(self):
        tree = ast.parse((ROOT / "engine" / "engine_extra.py").read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertNotIn("foreground_mask", functions)
        for name in ("image_background", "image_mosaic"):
            calls = [node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                     for node in ast.walk(functions[name])
                     if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))]
            self.assertFalse(set(calls) & {"InferenceSession", "CascadeClassifier", "detectMultiScale", "foreground_mask"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
