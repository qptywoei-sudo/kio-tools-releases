# Standalone desktop UI QA

From `work/desktop-ui`, with this package's existing dependencies available, run:

```sh
node --test qa/*.test.cjs
```

The Node test runner and the package's existing TypeScript compiler load only this
standalone app's `src` tree. There are no ADMIN source imports, external repository
paths, network requests, installed-app changes, real clipboard reads, or screen
capture requests. The static render suite supplies inert browser storage.

- `editor.test.cjs`: Ctrl/Cmd+C/S/Z/Shift+Z/Y, text copy priority, tall/wide fit,
  copy/save mutual exclusion, receipt-before-close, failure retry, stale editor
  callbacks, and browser clipboard user activation. Clipboard receipts are explicit
  test doubles; these checks do not establish OS clipboard permission.
- `events.test.cjs`: validated native menu messages, listener cleanup, shortcut
  repeat/debounce handling, capture session lifecycle, and native text copy receipts.
  The native message transport is mocked; no native app receives these messages.
- `workspace.test.cjs`: scaled original-pixel coordinates, stroke geometry, rotated
  selection, crop translation, page ordering, image layer fitting, saved preferences,
  search input validation, batch filters, QR/media options, and five-language static
  rendering of the eleven tool cards, capture toolbar and disconnected phone screen.
  Static rendering does not prove live phone operation or toolbar screen position.

Real multi-monitor capture, system picker cancellation, visible toolbar layout,
Cmd/Ctrl copy/save, disk output, and connected-phone interaction still require
native/manual checks. The separate `work/mac/native-capture-tests.py` performs real
policy, geometry, cancellation and private diagnostic-file checks (bounded fields,
0600 permissions and symlink protection) and compiles arm64/x86_64 for macOS 11
without reading screen content. `work/integration-tests/capture_target_tests.py`
checks the real local HTTP capture contract with an explicitly mocked native image.
