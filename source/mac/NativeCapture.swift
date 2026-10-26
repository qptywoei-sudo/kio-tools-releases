import AppKit
import CoreGraphics
import ScreenCaptureKit
import Darwin

protocol GalaxyCaptureOperation: AnyObject {
    func begin()
    func cancel()
}


// Keep native consent denial, deliberate cancellation and known storage failures truthful.
func galaxyCaptureErrorCode(_ error: Error) -> String {
    let native = error as NSError
    if native.domain == "GalaxyControl.NativeCapture", native.code == 2 { return "permissionRequired" }
    if #available(macOS 12.3, *), native.domain == SCStreamErrorDomain {
        switch native.code {
        case SCStreamError.Code.userDeclined.rawValue: return "permissionRequired"
        case SCStreamError.Code.userStopped.rawValue: return "cancelled"
        default: return "processingFailed"
        }
    }
    if native.domain == NSCocoaErrorDomain {
        switch native.code {
        case CocoaError.Code.fileWriteNoPermission.rawValue: return "permissionRequired"
        case CocoaError.Code.fileWriteOutOfSpace.rawValue: return "storageFull"
        case CocoaError.Code.userCancelled.rawValue: return "cancelled"
        default: return "processingFailed"
        }
    }
    if native.domain == NSPOSIXErrorDomain {
        switch native.code {
        case Int(EACCES), Int(EPERM): return "permissionRequired"
        case Int(ENOSPC): return "storageFull"
        default: return "processingFailed"
        }
    }
    return "processingFailed"
}

// A single private diagnostic record contains no selected-screen or document data.
private func withCaptureDiagnosticDirectory(_ supplied: URL?, action: (Int32) -> Void) {
    let directory = supplied ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("GalaxyControl/Agent", isDirectory: true)
    var ancestor = directory
    while ancestor.path != "/" {
        var metadata = stat()
        if lstat(ancestor.path, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFLNK { return }
        ancestor.deleteLastPathComponent()
    }
    do { try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: 0o700]) } catch { return }
    let fd = open(directory.path, O_RDONLY | O_NOFOLLOW)
    guard fd >= 0 else { return }; defer { close(fd) }
    var metadata = stat()
    guard fstat(fd, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFDIR,
          metadata.st_uid == getuid(), metadata.st_mode & 0o077 == 0 else { return }
    action(fd)
}

func galaxyClearCaptureDiagnostic(directory: URL? = nil) {
    withCaptureDiagnosticDirectory(directory) { fd in _ = unlinkat(fd, "capture-diagnostic.json", 0) }
}

func galaxyWriteCaptureDiagnostic(phase: String, error: Error, stage: String, directory: URL? = nil) {
    let native = error as NSError
    let characters = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
    let domain = String(native.domain.unicodeScalars.filter { characters.contains($0) }.prefix(96))
    let phases = Set(["idle", "acquiring", "picking", "capturing", "selecting", "preparing", "encoding", "persisting", "responding"])
    let stages = Set(["target", "selectionStyle", "selectionDisplay", "captureDimensions", "emptyImage", "invalidCrop", "external", "systemCapture", "saveDirectory", "bitmapEncoding", "writeCapture", "bridgeResponse"])
    let record: [String: Any] = ["phase": phases.contains(phase) ? phase : "unknown", "domain": domain.isEmpty ? "unknown" : domain,
                               "code": native.code, "stage": stages.contains(stage) ? stage : "unknown"]
    guard let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]), data.count <= 1024 else { return }
    withCaptureDiagnosticDirectory(directory) { directoryFD in
        let temporary = ".capture-diagnostic-" + UUID().uuidString
        let fd = openat(directoryFD, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { return }
        defer { close(fd); _ = unlinkat(directoryFD, temporary, 0) }
        let count = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard count == data.count, fsync(fd) == 0 else { return }
        _ = renameat(directoryFD, temporary, directoryFD, "capture-diagnostic.json")
    }
}

private enum NativeCaptureTargetPolicy: Equatable {
    case invalid, regionSelection, windowSelection, targetPicker, explicitDisplay(Int)
}

// Automatic area selection spans connected displays; it does not start a sharing session.
// A requested display is never silently replaced with the primary display.
private func nativeCaptureTargetPolicy(region: Bool, windowOnly: Bool, monitorIndex: Int,
                                      screenCount: Int) -> NativeCaptureTargetPolicy {
    guard screenCount > 0, monitorIndex >= -1,
          monitorIndex == -1 || monitorIndex < screenCount else { return .invalid }
    if windowOnly { return .windowSelection }
    if monitorIndex == -1 { return region ? .regionSelection : .targetPicker }
    return .explicitDisplay(monitorIndex)
}

private func nativeCaptureQuartzRect(screen: CGRect, primary: CGRect) -> CGRect? {
    guard [screen.minX, screen.minY, screen.width, screen.height, primary.maxY].allSatisfy({ $0.isFinite }),
          screen.width > 0, screen.height > 0 else { return nil }
    return CGRect(x: screen.minX, y: primary.maxY - screen.maxY, width: screen.width, height: screen.height)
}

// Older picker filters do not expose display IDs. Use an unambiguous geometry match only.
private func nativeCaptureMatchingScreen(contentRect: CGRect, frames: [CGRect]) -> Int? {
    guard let primary = frames.first, !contentRect.isNull, !contentRect.isInfinite,
          contentRect.width > 0, contentRect.height > 0 else { return nil }
    func same(_ lhs: CGRect, _ rhs: CGRect) -> Bool {
        abs(lhs.minX - rhs.minX) < 1 && abs(lhs.minY - rhs.minY) < 1 &&
        abs(lhs.width - rhs.width) < 1 && abs(lhs.height - rhs.height) < 1
    }
    let matches = frames.indices.filter { index in
        nativeCaptureQuartzRect(screen: frames[index], primary: primary).map { same(contentRect, $0) } == true
    }
    return matches.count == 1 ? matches[0] : nil
}

// View coordinates are local, flipped (top-left), and independent of screen origin.
private func nativeCaptureImageRect(pixels: CGSize, bounds: CGRect) -> CGRect {
    guard pixels.width > 0, pixels.height > 0, bounds.width > 0, bounds.height > 0 else { return .zero }
    let scale = min(bounds.width / pixels.width, bounds.height / pixels.height)
    let size = CGSize(width: pixels.width * scale, height: pixels.height * scale)
    return CGRect(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2,
                  width: size.width, height: size.height)
}

private func nativeCapturePixelRect(selection: CGRect, imageRect: CGRect, pixels: CGSize) -> CGRect? {
    guard selection.origin.x.isFinite, selection.origin.y.isFinite,
          selection.width.isFinite, selection.height.isFinite,
          imageRect.width > 0, imageRect.height > 0, pixels.width > 0, pixels.height > 0 else { return nil }
    let visible = selection.standardized.intersection(imageRect)
    guard !visible.isNull, visible.width > 0, visible.height > 0 else { return nil }
    let sx = pixels.width / imageRect.width, sy = pixels.height / imageRect.height
    // Include every covered pixel, while keeping the crop inside the CGImage.
    let x0 = max(0, floor((visible.minX - imageRect.minX) * sx))
    let y0 = max(0, floor((visible.minY - imageRect.minY) * sy))
    let x1 = min(pixels.width, ceil((visible.maxX - imageRect.minX) * sx))
    let y1 = min(pixels.height, ceil((visible.maxY - imageRect.minY) * sy))
    guard x1 > x0, y1 > y0 else { return nil }
    return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
}

// A deliberate drag must cover visible area in both dimensions, even on Retina.
private func nativeCaptureReleasedSelection(origin: CGPoint, end: CGPoint, imageRect: CGRect, pixels: CGSize) -> CGRect? {
    guard origin.x.isFinite, origin.y.isFinite, end.x.isFinite, end.y.isFinite,
          imageRect.contains(origin) else { return nil }
    let point = CGPoint(x: min(imageRect.maxX, max(imageRect.minX, end.x)),
                        y: min(imageRect.maxY, max(imageRect.minY, end.y)))
    let selection = CGRect(x: min(origin.x, point.x), y: min(origin.y, point.y),
                           width: abs(point.x - origin.x), height: abs(point.y - origin.y))
    guard selection.width >= 2, selection.height >= 2,
          let crop = nativeCapturePixelRect(selection: selection, imageRect: imageRect, pixels: pixels),
          crop.width >= 2, crop.height >= 2 else { return nil }
    return selection
}

private enum NativeSystemCaptureTarget: Equatable {
    case window, display(Int)
}

private func nativeSystemCaptureChoices(screenCount: Int) -> [NativeSystemCaptureTarget] {
    guard screenCount > 0 else { return [] }
    return [.window] + (0..<screenCount).map { .display($0) }
}

// The macOS screenshot selector supports region/window selection across all displays.
// This local chooser adds named whole displays without a screen-sharing confirmation.
private final class GalaxySystemCaptureTargetPicker: NSObject, NSWindowDelegate {
    private let window = NSPanel(contentRect: CGRect(x: 0, y: 0, width: 480, height: 170),
                                 styleMask: [.titled, .closable], backing: .buffered, defer: false)
    private let menu = NSPopUpButton()
    private let choices: [NativeSystemCaptureTarget]
    private var completion: ((NativeSystemCaptureTarget?) -> Void)?
    init(screens: [NSScreen], completion: @escaping (NativeSystemCaptureTarget?) -> Void) {
        choices = nativeSystemCaptureChoices(screenCount: screens.count)
        self.completion = completion
        super.init()
        window.title = L("캡처할 창 또는 모니터 선택")
        window.isReleasedWhenClosed = false
        window.level = .floating
        window.delegate = self
        let hint = NSTextField(labelWithString: L("창을 직접 선택하거나 캡처할 모니터를 고르세요."))
        hint.frame = CGRect(x: 22, y: 122, width: 436, height: 24)
        menu.frame = CGRect(x: 22, y: 77, width: 436, height: 32)
        menu.addItem(withTitle: L("창 선택"))
        for (index, screen) in screens.enumerated() {
            menu.addItem(withTitle: "\(L("모니터")) \(index + 1) — \(screen.localizedName)")
        }
        let capture = NSButton(title: L("선택하고 캡처"), target: self, action: #selector(accept))
        capture.frame = CGRect(x: 318, y: 22, width: 140, height: 32)
        capture.bezelStyle = .rounded; capture.keyEquivalent = "\r"
        let cancel = NSButton(title: L("취소"), target: self, action: #selector(cancel))
        cancel.frame = CGRect(x: 218, y: 22, width: 90, height: 32)
        cancel.bezelStyle = .rounded; cancel.keyEquivalent = "\u{1b}"
        [hint, menu, capture, cancel].forEach { window.contentView?.addSubview($0) }
    }
    func begin() {
        guard completion != nil else { return }
        NSApp.unhide(nil); NSApp.activate(ignoringOtherApps: true)
        window.center(); window.makeKeyAndOrderFront(nil)
    }
    @objc private func accept() {
        let index = menu.indexOfSelectedItem
        complete(choices.indices.contains(index) ? choices[index] : nil)
    }
    @objc func cancel() { complete(nil) }
    func windowWillClose(_ notification: Notification) { complete(nil) }
    private func complete(_ choice: NativeSystemCaptureTarget?) {
        guard let callback = completion else { return }
        completion = nil
        window.orderOut(nil); window.close()
        callback(choice)
    }
}

/// Wait for WindowServer's on-screen list to acknowledge removal. Capture only
/// after this fence; a fixed delay alone can include a slow-compositing window.
func galaxyHideCaptureWindows(completion: @escaping (Bool) -> Void) {
    let windows = NSApp.windows
    let ids = Set(windows.map { $0.windowNumber })
    windows.forEach { $0.orderOut(nil) }
    let deadline = Date().addingTimeInterval(2)
    func check() {
        guard let rows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String:Any]] else { completion(false); return }
        let visible = rows.contains { row in (row[kCGWindowNumber as String] as? Int).map { ids.contains($0) } ?? false }
        if !visible { DispatchQueue.main.async { completion(true) }; return }
        if Date() >= deadline { completion(false); return }
        DispatchQueue.main.asyncAfter(deadline:.now()+0.016,execute:check)
    }
    check()
}

/// Preserve intentional self-capture before React navigates away from a result.
/// Pixel buffers live only in memory after the system capture file is read.
// Modern captures run inside the signed app, so consent belongs to KIO Tools.
// CGPreflight can lag a System Settings change: let the capture API decide.
@available(macOS 14.0, *)
enum GalaxyScreenImage {
    static func captureWindow(completion: @escaping (CGImage?, Error?) -> Void) {
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { content, error in
            DispatchQueue.main.async {
                if let error = error { completion(nil,error); return }
                let windows = (content?.windows ?? []).filter {
                    $0.owningApplication?.processID != ProcessInfo.processInfo.processIdentifier && $0.frame.width >= 4 && $0.frame.height >= 4
                }
                guard !windows.isEmpty else { completion(nil,NSError(domain:"GalaxyControl.NativeCapture",code:1)); return }
                let menu = NSPopUpButton(frame:NSRect(x:0,y:0,width:450,height:28))
                for window in windows { menu.addItem(withTitle:(window.owningApplication?.applicationName ?? "") + " · " + (window.title?.isEmpty == false ? window.title! : L("제목 없는 창"))) }
                let alert = NSAlert(); alert.messageText = L("캡처할 창을 선택하세요."); alert.accessoryView = menu
                alert.addButton(withTitle:L("캡처")); alert.addButton(withTitle:L("취소"))
                guard alert.runModal() == .alertFirstButtonReturn, windows.indices.contains(menu.indexOfSelectedItem) else { completion(nil,nil); return }
                let window = windows[menu.indexOfSelectedItem]
                let filter = SCContentFilter(desktopIndependentWindow:window), config = SCStreamConfiguration()
                config.width = max(1,Int(window.frame.width * CGFloat(filter.pointPixelScale)))
                config.height = max(1,Int(window.frame.height * CGFloat(filter.pointPixelScale)))
                config.showsCursor = false
                SCScreenshotManager.captureImage(contentFilter:filter,configuration:config) { image, error in
                    DispatchQueue.main.async { completion(image,error ?? (image == nil ? NSError(domain:"GalaxyControl.NativeCapture",code:3) : nil)) }
                }
            }
        }
    }
    static func capture(screen: NSScreen, completion: @escaping (CGImage?, Error?) -> Void) {
        let id = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { content, error in
            DispatchQueue.main.async {
                if let error = error { completion(nil, error); return }
                guard let display = content?.displays.first(where: { $0.displayID == id }) else {
                    completion(nil, NSError(domain: "GalaxyControl.NativeCapture", code: 1)); return
                }
                let filter = SCContentFilter(display: display, excludingWindows: [])
                let config = SCStreamConfiguration()
                config.width = max(1, Int(screen.frame.width * screen.backingScaleFactor))
                config.height = max(1, Int(screen.frame.height * screen.backingScaleFactor))
                config.showsCursor = false
                SCScreenshotManager.captureImage(contentFilter: filter, configuration: config) { image, failure in
                    DispatchQueue.main.async { completion(image, failure) }
                }
            }
        }
    }
}

final class GalaxyCaptureBackdrop {
    static private var frames: [(NSScreen, CGImage)] = []
    static private var expires = Date.distantPast
    static func clear() { frames = []; expires = .distantPast }
    static func take() -> [(NSScreen, CGImage)] {
        let result = Date() < expires ? frames : []; clear(); return result
    }
    static func prepare(completion: @escaping (Bool) -> Void) {
        prepareResult { imageError in completion(imageError == nil) }
    }
    static func prepareResult(completion: @escaping (Error?) -> Void) {
        clear()
        guard let primary = NSScreen.screens.first else { completion(NSError(domain:"GalaxyControl.NativeCapture",code:3)); return }
        let screens = NSScreen.screens
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("KIO-self-capture-"+UUID().uuidString)
        do { try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700]) }
        catch { completion(NSError(domain:"GalaxyControl.NativeCapture",code:3)); return }
        var captured: [(NSScreen, CGImage)] = []
        func next(_ index: Int) {
            if index == screens.count {
                try? FileManager.default.removeItem(at:folder)
                frames = captured; expires = Date().addingTimeInterval(8)
                let expiry = expires
                DispatchQueue.main.asyncAfter(deadline:.now()+8) { if expires == expiry { clear() } }
                completion(captured.isEmpty ? NSError(domain:"GalaxyControl.NativeCapture",code:3) : nil); return
            }
            let screen = screens[index]
            if #available(macOS 14.0, *) {
                GalaxyScreenImage.capture(screen: screen) { image, error in
                    guard let image = image else { try? FileManager.default.removeItem(at:folder); completion(error ?? NSError(domain:"GalaxyControl.NativeCapture",code:3)); return }
                    captured.append((screen,image)); next(index+1)
                }
                return
            }
            guard let rect = nativeCaptureQuartzRect(screen:screen.frame,primary:primary.frame) else { completion(NSError(domain:"GalaxyControl.NativeCapture",code:3)); return }
            let output = folder.appendingPathComponent("frame.png")
            let process = Process(); process.executableURL = URL(fileURLWithPath:"/usr/sbin/screencapture")
            process.arguments = ["-x","-t","png","-R","\(Int(rect.minX)),\(Int(rect.minY)),\(Int(rect.width)),\(Int(rect.height))",output.path]
            process.standardInput = FileHandle.nullDevice; process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
            process.terminationHandler = { task in DispatchQueue.main.async {
                let image = NSImage(contentsOf:output)?.cgImage(forProposedRect:nil,context:nil,hints:nil)
                try? FileManager.default.removeItem(at:output)
                guard task.terminationStatus == 0, let image = image else { try? FileManager.default.removeItem(at:folder); completion(NSError(domain:"GalaxyControl.NativeCapture",code:3)); return }
                captured.append((screen,image)); next(index+1)
            } }
            do { try process.run() } catch { try? FileManager.default.removeItem(at:folder); completion(NSError(domain:"GalaxyControl.NativeCapture",code:3)) }
        }
        next(0)
    }
}

final class GalaxySystemCapture: NSObject, GalaxyCaptureOperation {
    private enum Phase { case idle, choosing, capturing, selecting, finished }
    private let region: Bool, windowOnly: Bool
    private let monitorIndex: Int
    private let delay: Double
    private var phase: Phase = .idle
    private var completion: ((CGImage?, Error?) -> Void)?
    private var chooser: GalaxySystemCaptureTargetPicker?
    private var process: Process?
    private var delayedCapture: DispatchWorkItem?
    private var overlay: NSWindow?
    private var extraOverlays: [NSWindow] = []
    private var backdrop: [(NSScreen, CGImage)] = []
    private var temporaryDirectory: URL?
    init(region: Bool, monitorIndex: Int, delay: Double = 0, windowOnly: Bool = false,
         completion: @escaping (CGImage?, Error?) -> Void) {
        self.region = region; self.monitorIndex = monitorIndex; self.windowOnly = windowOnly
        self.delay = delay.isFinite ? max(0, delay) : 0
        self.completion = completion
        super.init()
    }
    func begin() { onMain { [weak self] in self?.beginOnMain() } }
    func cancel() { onMain { [weak self] in self?.finish(nil, nil) } }
    private func onMain(_ action: @escaping () -> Void) {
        if Thread.isMainThread { action() } else { DispatchQueue.main.async(execute: action) }
    }
    private func captureError() -> Error {
        NSError(domain: "GalaxyControl.NativeCapture", code: 1,
                userInfo: [NSLocalizedDescriptionKey: L("캡처할 모니터를 찾지 못했습니다. 다시 선택해 주세요.")])
    }
    private func beginOnMain() {
        guard phase == .idle else { return }
        galaxyClearCaptureDiagnostic()
        backdrop = GalaxyCaptureBackdrop.take()
        let screens = NSScreen.screens
        let policy = nativeCaptureTargetPolicy(region: region, windowOnly: windowOnly,
                                              monitorIndex: monitorIndex, screenCount: screens.count)
        guard policy != .invalid else { finish(nil, captureError()); return }
        if region && monitorIndex == -1 && backdrop.isEmpty {
            phase = .capturing
            galaxyHideCaptureWindows { [weak self] hidden in
                guard let self = self, self.phase == .capturing else { return }
                guard hidden else { self.finish(nil,self.captureError()); return }
                GalaxyCaptureBackdrop.prepareResult { [weak self] error in
                    guard let self = self, self.phase == .capturing else { GalaxyCaptureBackdrop.clear(); return }
                    if let error = error { self.finish(nil,error); return }
                    self.backdrop = GalaxyCaptureBackdrop.take()
                    for item in self.backdrop { self.showRegionSelector(item.1,on:item.0) }
                }
            }
            return
        }
        if policy == .targetPicker {
            phase = .choosing
            let picker = GalaxySystemCaptureTargetPicker(screens: screens) { [weak self] choice in
                guard let self = self, self.phase == .choosing else { return }
                self.chooser = nil
                guard let choice = choice else { self.finish(nil, nil); return }
                switch choice {
                case .window: self.startCapture(screen: nil, window: true)
                case .display(let index):
                    // A disconnected display is an error; never replace it with the first screen.
                    let id = (screens[index].deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value
                    guard id != nil, NSScreen.screens.contains(where: {
                        ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value == id
                    }) else {
                        self.finish(nil, self.captureError()); return
                    }
                    self.startCapture(screen: screens[index], window: false)
                }
            }
            chooser = picker; picker.begin()
        } else {
            startCapture(screen: windowOnly || monitorIndex == -1 ? nil : screens[monitorIndex], window: windowOnly)
        }
    }
    private func startCapture(screen: NSScreen?, window: Bool) {
        guard phase != .finished else { return }
        if !backdrop.isEmpty && !window {
            if let screen = screen, let item = backdrop.first(where: { $0.0 == screen }) {
                if region { showRegionSelector(item.1,on:item.0) } else { finish(item.1,nil) }
            } else if region {
                for item in backdrop { showRegionSelector(item.1,on:item.0) }
            } else { finish(nil,captureError()) }
            return
        }
        if #available(macOS 14.0, *), window {
            phase = .capturing
            galaxyHideCaptureWindows { [weak self] hidden in
                guard let self = self, self.phase == .capturing else { return }
                guard hidden else { self.finish(nil,self.captureError()); return }
                let work = DispatchWorkItem { [weak self] in
                    guard let self = self, self.phase == .capturing else { return }
                    self.delayedCapture = nil
                    GalaxyScreenImage.captureWindow { [weak self] image, error in
                        guard let self = self, self.phase == .capturing else { return }
                        self.finish(image,error)
                    }
                }
                self.delayedCapture = work
                if self.delay > 0 { DispatchQueue.main.asyncAfter(deadline:.now()+self.delay,execute:work) }
                else { work.perform() }
            }
            return
        }
        if #available(macOS 14.0, *), let screen = screen, !window {
            phase = .capturing
            galaxyHideCaptureWindows { [weak self] hidden in
                guard let self = self, self.phase == .capturing else { return }
                guard hidden else { self.finish(nil,self.captureError()); return }
                let work = DispatchWorkItem { [weak self] in
                    guard let self = self, self.phase == .capturing else { return }
                    self.delayedCapture = nil
                    GalaxyScreenImage.capture(screen: screen) { [weak self] image, error in
                        guard let self = self, self.phase == .capturing else { return }
                        guard let image = image else { self.finish(nil,error ?? self.captureError()); return }
                        if self.region { self.showRegionSelector(image,on:screen) } else { self.finish(image,nil) }
                    }
                }
                self.delayedCapture = work
                if self.delay > 0 { DispatchQueue.main.asyncAfter(deadline:.now()+self.delay,execute:work) }
                else { work.perform() }
            }
            return
        }
        // Legacy/system window selector: try the actual operation even if preflight is stale.
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("GalaxyCapture-" + UUID().uuidString, isDirectory: true)
        do { try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        catch { finish(nil, error); return }
        temporaryDirectory = directory
        let file = directory.appendingPathComponent("capture.png")
        let operation = Process(); operation.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        if let screen = screen {
            guard let primary = NSScreen.screens.first,
                  let rect = nativeCaptureQuartzRect(screen: screen.frame, primary: primary.frame) else { finish(nil, captureError()); return }
            operation.arguments = ["-x", "-t", "png", "-R", "\(Int(rect.minX)),\(Int(rect.minY)),\(Int(rect.width)),\(Int(rect.height))", file.path]
        } else {
            operation.arguments = ["-i", window ? "-w" : "-s", "-x", "-t", "png", file.path]
        }
        let errors = Pipe()
        operation.standardInput = FileHandle.nullDevice
        operation.standardOutput = FileHandle.nullDevice
        operation.standardError = errors
        let clipboardRevision = NSPasteboard.general.changeCount
        operation.terminationHandler = { [weak self] completed in
            let errorData = errors.fileHandleForReading.readDataToEndOfFile()
            DispatchQueue.main.async {
                guard let self = self, self.phase == .capturing else { return }
                self.process = nil
                var captured = NSImage(contentsOf: file)
                // The system selector sends the image to the clipboard while Control is held.
                // Only a fresh image may be used; Escape must never resurrect an old image.
                if captured == nil, NSPasteboard.general.changeCount != clipboardRevision {
                    captured = NSImage(pasteboard: .general)
                }
                guard let image = captured?.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                    if completed.terminationStatus != 0 && !errorData.isEmpty && !CGPreflightScreenCaptureAccess() {
                        self.finish(nil, NSError(domain: "GalaxyControl.NativeCapture", code: 2,
                            userInfo: [NSLocalizedDescriptionKey: L("화면 기록 권한이 필요합니다.")]))
                    } else if !errorData.isEmpty || (screen != nil && completed.terminationStatus != 0) {
                        self.finish(nil, NSError(domain: "GalaxyControl.NativeCapture", code: 3,
                            userInfo: [NSLocalizedDescriptionKey: L("화면 이미지가 만들어지지 않았습니다. 다시 캡처해 주세요.")]))
                    } else { self.finish(nil, nil) }
                    return
                }
                if self.region, let screen = screen { self.showRegionSelector(image, on: screen) }
                else { self.finish(image, nil) }
            }
        }
        process = operation; phase = .capturing
        let work = DispatchWorkItem { [weak self] in
            guard let self = self, self.phase == .capturing else { return }
            self.delayedCapture = nil
            do { try operation.run() } catch { self.finish(nil, error) }
        }
        delayedCapture = work
        galaxyHideCaptureWindows { [weak self] hidden in
            guard let self = self, self.phase == .capturing else { return }
            guard hidden else { self.finish(nil,self.captureError()); return }
            if self.delay > 0 { DispatchQueue.main.asyncAfter(deadline:.now()+self.delay,execute:work) }
            else { work.perform() }
        }
    }
    private func showRegionSelector(_ image: CGImage, on screen: NSScreen) {
        phase = .selecting
        let window = GalaxyFrozenCaptureWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.level = .screenSaver
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.backgroundColor = .black; window.isOpaque = true; window.hasShadow = false
        window.cancelCapture = { [weak self] in self?.finish(nil, nil) }
        let view = GalaxyFrozenCaptureView(image: image, frame: CGRect(origin: .zero, size: screen.frame.size)) { [weak self] crop in
            guard let self = self, self.phase == .selecting else { return }
            guard let crop = crop else { self.finish(nil, nil); return }
            guard let selected = image.cropping(to: crop), selected.width > 0, selected.height > 0 else {
                self.finish(nil, self.captureError()); return
            }
            self.finish(selected, nil)
        }
        window.contentView = view
        if let previous = overlay { extraOverlays.append(previous) }; overlay = window
        NSApp.unhide(nil); NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil); window.makeFirstResponder(view)
    }
    private func finish(_ image: CGImage?, _ error: Error?) {
        guard phase != .finished else { return }
        if let error = error { galaxyWriteCaptureDiagnostic(phase: String(describing: phase), error: error, stage: "systemCapture") }
        phase = .finished
        delayedCapture?.cancel(); delayedCapture = nil
        chooser?.cancel(); chooser = nil
        if process?.isRunning == true { process?.terminate() }
        process = nil
        overlay?.orderOut(nil); overlay?.close(); overlay = nil
        extraOverlays.forEach { $0.orderOut(nil); $0.close() }; extraOverlays = []; backdrop = []
        if let directory = temporaryDirectory { try? FileManager.default.removeItem(at: directory) }
        temporaryDirectory = nil
        let callback = completion; completion = nil
        callback?(image, error)
    }
}

private final class GalaxyFrozenCaptureWindow: NSWindow {
    var cancelCapture: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.keyCode == 53 { cancelCapture?(); return true }
        return super.performKeyEquivalent(with: event)
    }
}

private final class GalaxyFrozenCaptureView: NSView {
    private enum DragMode { case create, move, resize(Int) }
    private let image: CGImage
    private let displayImage: NSImage
    private let completed: (CGRect?) -> Void
    private let confirm = NSButton()
    private let cancelButton = NSButton()
    private let hint = NSTextField(labelWithString: "")
    private let dimensions = NSTextField(labelWithString: "")
    private var selection: CGRect?
    private var dragMode: DragMode = .create
    private var dragActive = false
    private var dragOrigin = CGPoint.zero
    private var original = CGRect.zero
    private var didComplete = false
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    private var pixels: CGSize { CGSize(width: image.width, height: image.height) }
    private var fittedImage: CGRect { nativeCaptureImageRect(pixels: pixels, bounds: bounds) }

    init(image: CGImage, frame: CGRect, completed: @escaping (CGRect?) -> Void) {
        self.image = image
        self.displayImage = NSImage(cgImage: image, size: CGSize(width: image.width, height: image.height))
        self.completed = completed
        super.init(frame: frame)
        hint.stringValue = L("캡처할 영역을 드래그한 뒤 마우스를 놓으면 바로 캡처됩니다. Esc 취소")
        hint.textColor = .white; hint.font = .systemFont(ofSize: 13, weight: .medium)
        hint.wantsLayer = true; hint.layer?.backgroundColor = NSColor.black.withAlphaComponent(0.75).cgColor
        dimensions.textColor = .white; dimensions.font = .monospacedDigitSystemFont(ofSize: 12, weight: .medium)
        confirm.title = L("선택 영역 캡처"); confirm.target = self; confirm.action = #selector(acceptSelection)
        confirm.bezelStyle = .rounded; confirm.isEnabled = false
        cancelButton.title = L("취소"); cancelButton.target = self; cancelButton.action = #selector(cancelSelection)
        cancelButton.bezelStyle = .rounded
        [hint, dimensions, confirm, cancelButton].forEach { addSubview($0) }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layout() {
        super.layout()
        let maxWidth = max(100, bounds.width - 48)
        hint.frame = CGRect(x: 24, y: 22, width: min(maxWidth, hint.intrinsicContentSize.width + 8), height: 26)
        dimensions.frame = CGRect(x: 24, y: 58, width: maxWidth, height: 22)
        cancelButton.frame = CGRect(x: max(20, bounds.width - 104), y: max(0, bounds.height - 56), width: 84, height: 32)
        confirm.frame = CGRect(x: max(20, bounds.width - 264), y: max(0, bounds.height - 56), width: 152, height: 32)
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.setFill(); bounds.fill()
        displayImage.draw(in: fittedImage, from: .zero, operation: .copy, fraction: 1,
                          respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
        let shade = NSBezierPath(rect: bounds)
        if let rect = selection { shade.appendRect(rect) }
        shade.windingRule = .evenOdd
        NSColor.black.withAlphaComponent(0.42).setFill(); shade.fill()
        if let rect = selection {
            NSColor.white.setStroke()
            let outline = NSBezierPath(rect: rect); outline.lineWidth = 1.5; outline.stroke()
            for point in handles(rect) {
                let knob = NSBezierPath(rect: CGRect(x: point.x - 4, y: point.y - 4, width: 8, height: 8))
                NSColor.controlAccentColor.setFill(); knob.fill()
                NSColor.white.setStroke(); knob.stroke()
            }
        }
    }

    private func handles(_ rect: CGRect) -> [CGPoint] {
        [CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.midX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
         CGPoint(x: rect.maxX, y: rect.midY), CGPoint(x: rect.maxX, y: rect.maxY), CGPoint(x: rect.midX, y: rect.maxY),
         CGPoint(x: rect.minX, y: rect.maxY), CGPoint(x: rect.minX, y: rect.midY)]
    }

    private func clamped(_ point: CGPoint) -> CGPoint {
        let rect = fittedImage
        return CGPoint(x: min(rect.maxX, max(rect.minX, point.x)), y: min(rect.maxY, max(rect.minY, point.y)))
    }

    override func mouseDown(with event: NSEvent) {
        guard !didComplete else { return }
        dragActive = false
        window?.makeFirstResponder(self)
        let point = convert(event.locationInWindow, from: nil)
        guard fittedImage.contains(point) else { return }
        dragActive = true
        hint.stringValue = L("캡처할 영역을 드래그한 뒤 마우스를 놓으면 바로 캡처됩니다. Esc 취소")
        dragOrigin = clamped(point)
        original = selection ?? .zero
        if let selection = selection,
           let index = handles(selection).firstIndex(where: { hypot($0.x - point.x, $0.y - point.y) <= 10 }) {
            dragMode = .resize(index)
        } else if selection?.contains(point) == true {
            dragMode = .move
        } else {
            dragMode = .create
            selection = CGRect(origin: dragOrigin, size: .zero)
        }
        updateSelection()
    }

    override func mouseDragged(with event: NSEvent) {
        guard dragActive, !didComplete else { return }
        updateDrag(to: convert(event.locationInWindow, from: nil))
    }

    private func updateDrag(to location: CGPoint) {
        let point = clamped(location)
        switch dragMode {
        case .create:
            selection = CGRect(x: min(point.x, dragOrigin.x), y: min(point.y, dragOrigin.y),
                               width: abs(point.x - dragOrigin.x), height: abs(point.y - dragOrigin.y))
        case .move:
            let rect = fittedImage
            selection = CGRect(x: min(rect.maxX - original.width, max(rect.minX, original.minX + point.x - dragOrigin.x)),
                               y: min(rect.maxY - original.height, max(rect.minY, original.minY + point.y - dragOrigin.y)),
                               width: original.width, height: original.height)
        case .resize(let index):
            var x0 = original.minX, x1 = original.maxX, y0 = original.minY, y1 = original.maxY
            if [0, 6, 7].contains(index) { x0 = point.x }
            if [2, 3, 4].contains(index) { x1 = point.x }
            if [0, 1, 2].contains(index) { y0 = point.y }
            if [4, 5, 6].contains(index) { y1 = point.y }
            selection = CGRect(x: min(x0, x1), y: min(y0, y1), width: abs(x1 - x0), height: abs(y1 - y0))
        }
        updateSelection()
    }

    override func mouseUp(with event: NSEvent) {
        guard dragActive, !didComplete else { return }
        let point = convert(event.locationInWindow, from: nil)
        updateDrag(to: point)
        dragActive = false
        guard case .create = dragMode else { return }
        guard let rect = nativeCaptureReleasedSelection(origin: dragOrigin, end: point,
                                                        imageRect: fittedImage, pixels: pixels) else {
            selection = nil
            hint.stringValue = L("캡처 영역이 너무 작습니다. 영역을 다시 선택해 주세요.")
            updateSelection()
            return
        }
        selection = rect
        updateSelection()
        acceptSelection()
    }

    private func updateSelection() {
        let crop = selection.flatMap { nativeCapturePixelRect(selection: $0, imageRect: fittedImage, pixels: pixels) }
        confirm.isEnabled = (crop?.width ?? 0) >= 2 && (crop?.height ?? 0) >= 2
        dimensions.stringValue = crop.map { Lf("선택 영역: %d × %d 픽셀", Int($0.width), Int($0.height)) } ?? ""
        needsDisplay = true
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { cancelSelection() }
        else if event.keyCode == 36 || event.keyCode == 76 { acceptSelection() }
        else { super.keyDown(with: event) }
    }

    @objc private func acceptSelection() {
        guard !didComplete, confirm.isEnabled, let rect = selection,
              let crop = nativeCapturePixelRect(selection: rect, imageRect: fittedImage, pixels: pixels) else { return }
        dragActive = false
        didComplete = true; completed(crop)
    }

    @objc private func cancelSelection() {
        guard !didComplete else { return }
        dragActive = false
        didComplete = true; completed(nil)
    }
}

// Pure geometry and synthetic-image checks; never calls a capture or permission API.
func nativeCaptureSelfCheck() -> Bool {
    // Region hotkeys start selection immediately; full captures ask for a window/display.
    guard nativeCaptureTargetPolicy(region: false, windowOnly: false, monitorIndex: -1, screenCount: 3) == .targetPicker,
          nativeCaptureTargetPolicy(region: true, windowOnly: false, monitorIndex: -1, screenCount: 3) == .regionSelection,
          nativeCaptureTargetPolicy(region: false, windowOnly: true, monitorIndex: -1, screenCount: 3) == .windowSelection,
          nativeCaptureTargetPolicy(region: false, windowOnly: false, monitorIndex: 2, screenCount: 3) == .explicitDisplay(2),
          nativeCaptureTargetPolicy(region: true, windowOnly: false, monitorIndex: 1, screenCount: 3) == .explicitDisplay(1),
          nativeCaptureTargetPolicy(region: false, windowOnly: false, monitorIndex: 3, screenCount: 3) == .invalid,
          nativeCaptureTargetPolicy(region: false, windowOnly: false, monitorIndex: -2, screenCount: 3) == .invalid,
          nativeCaptureTargetPolicy(region: false, windowOnly: false, monitorIndex: -1, screenCount: 0) == .invalid,
          nativeSystemCaptureChoices(screenCount: 3) == [.window, .display(0), .display(1), .display(2)],
          nativeSystemCaptureChoices(screenCount: 0).isEmpty else { return false }
    let screenFrames = [CGRect(x: 0, y: 0, width: 1440, height: 900),
                        CGRect(x: -1920, y: 0, width: 1920, height: 1080),
                        CGRect(x: 0, y: 900, width: 1600, height: 1000)]
    guard nativeCaptureQuartzRect(screen: screenFrames[1], primary: screenFrames[0]) == CGRect(x: -1920, y: -180, width: 1920, height: 1080),
          nativeCaptureQuartzRect(screen: screenFrames[2], primary: screenFrames[0]) == CGRect(x: 0, y: -1000, width: 1600, height: 1000),
          nativeCaptureMatchingScreen(contentRect: CGRect(x: -1920, y: -180, width: 1920, height: 1080), frames: screenFrames) == 1,
          nativeCaptureMatchingScreen(contentRect: CGRect(x: 0, y: -1000, width: 1600, height: 1000), frames: screenFrames) == 2,
          nativeCaptureMatchingScreen(contentRect: CGRect(x: 0, y: 0, width: 1920, height: 1080), frames: screenFrames) == nil,
          nativeCaptureMatchingScreen(contentRect: .zero, frames: screenFrames) == nil,
          nativeCaptureMatchingScreen(contentRect: screenFrames[0], frames: [screenFrames[0], screenFrames[0]]) == nil else { return false }
    let retina = nativeCaptureImageRect(pixels: CGSize(width: 2000, height: 1000),
                                       bounds: CGRect(x: 0, y: 0, width: 1000, height: 800))
    guard retina == CGRect(x: 0, y: 150, width: 1000, height: 500),
          nativeCapturePixelRect(selection: CGRect(x: 100, y: 250, width: 300, height: 100), imageRect: retina,
                                 pixels: CGSize(width: 2000, height: 1000)) == CGRect(x: 200, y: 200, width: 600, height: 200),
          nativeCapturePixelRect(selection: CGRect(x: -30, y: 100, width: 60, height: 100), imageRect: retina,
                                 pixels: CGSize(width: 2000, height: 1000)) == CGRect(x: 0, y: 0, width: 60, height: 100),
          nativeCapturePixelRect(selection: CGRect(x: 20, y: 10, width: 40, height: 40), imageRect: retina,
                                 pixels: CGSize(width: 2000, height: 1000)) == nil else { return false }
    let shifted = CGRect(x: -1200, y: 80, width: 800, height: 600)
    guard nativeCapturePixelRect(selection: CGRect(x: -1199.75, y: 80.25, width: 10.25, height: 20.25), imageRect: shifted,
                                 pixels: CGSize(width: 1600, height: 1200)) == CGRect(x: 0, y: 0, width: 21, height: 41) else { return false }
    // Release contracts: clicks and thin drags stay open; direction and letterbox do not alter the crop.
    let dragBounds = CGRect(x: 0, y: 150, width: 1000, height: 500)
    let dragPixels = CGSize(width: 2000, height: 1000)
    let forward = nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 400, y: 350),
                                                  imageRect: dragBounds, pixels: dragPixels)
    let backward = nativeCaptureReleasedSelection(origin: CGPoint(x: 400, y: 350), end: CGPoint(x: 100, y: 250),
                                                   imageRect: dragBounds, pixels: dragPixels)
    guard forward == CGRect(x: 100, y: 250, width: 300, height: 100), backward == forward,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 100, y: 250),
                                           imageRect: dragBounds, pixels: dragPixels) == nil,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 101, y: 350),
                                           imageRect: dragBounds, pixels: dragPixels) == nil,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 101.999, y: 252),
                                           imageRect: dragBounds, pixels: dragPixels) == nil,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 102, y: 252),
                                           imageRect: dragBounds, pixels: dragPixels) == CGRect(x: 100, y: 250, width: 2, height: 2),
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 100), end: CGPoint(x: 400, y: 350),
                                           imageRect: dragBounds, pixels: dragPixels) == nil,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 2000, y: 900),
                                           imageRect: dragBounds, pixels: dragPixels) == CGRect(x: 100, y: 250, width: 900, height: 400),
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: 103, y: 253),
                                           imageRect: dragBounds, pixels: CGSize(width: 100, height: 50)) == nil,
          nativeCaptureReleasedSelection(origin: CGPoint(x: 100, y: 250), end: CGPoint(x: CGFloat.nan, y: 350),
                                           imageRect: dragBounds, pixels: dragPixels) == nil else { return false }
    var bytes = [UInt8](repeating: 0, count: 4 * 4 * 4)
    for row in 0..<4 { for column in 0..<4 {
        let offset = (row * 4 + column) * 4
        bytes[offset] = row == 0 ? 255 : 0
        bytes[offset + 2] = row == 3 ? 255 : 0
        bytes[offset + 3] = 255
    } }
    guard let provider = CGDataProvider(data: Data(bytes) as CFData),
          let image = CGImage(width: 4, height: 4, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 16,
                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
                              provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
          let top = image.cropping(to: CGRect(x: 0, y: 0, width: 4, height: 1)),
          let bottom = image.cropping(to: CGRect(x: 0, y: 3, width: 4, height: 1)),
          let topColor = NSBitmapImageRep(cgImage: top).colorAt(x: 0, y: 0)?.usingColorSpace(.deviceRGB),
          let bottomColor = NSBitmapImageRep(cgImage: bottom).colorAt(x: 0, y: 0)?.usingColorSpace(.deviceRGB),
          topColor.redComponent > 0.9, topColor.blueComponent < 0.1,
          bottomColor.blueComponent > 0.9, bottomColor.redComponent < 0.1 else { return false }
    return nativeCaptureErrorMappingSelfCheck() && nativeCaptureDiagnosticSelfCheck() && nativeCaptureCancellationSelfCheck()
}

// Cancelling before begin must be idempotent and must not open a picker or capture API.
func nativeCaptureCancellationSelfCheck() -> Bool {
    guard Thread.isMainThread else { return false }
    var calls = 0, emptyResults = true
    let complete: (CGImage?, Error?) -> Void = { image, error in
        calls += 1; emptyResults = emptyResults && image == nil && error == nil
    }
    let legacy = GalaxySystemCapture(region: false, monitorIndex: -1, windowOnly: false, completion: complete)
    legacy.cancel(); legacy.cancel(); legacy.begin(); legacy.cancel()
    guard calls == 1, emptyResults else { return false }
    return true
}


// The private diagnostic is bounded, excludes NSError userInfo, and replaces links without following them.
private func nativeCaptureDiagnosticSelfCheck() -> Bool {
    guard let resolved = realpath(FileManager.default.temporaryDirectory.path, nil) else { return false }
    let parent = URL(fileURLWithPath: String(cString: resolved), isDirectory: true); free(resolved)
    let directory = parent.appendingPathComponent("GalaxyCaptureDiagnosticCheck-" + UUID().uuidString, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let error = NSError(domain: String(repeating: "Fixture.Error", count: 20), code: -3800,
                        userInfo: [NSLocalizedDescriptionKey: "Do not persist this fixture text", "path": "/fixture/private"])
    galaxyWriteCaptureDiagnostic(phase: "picking", error: error, stage: "selectionDisplay", directory: directory)
    let file = directory.appendingPathComponent("capture-diagnostic.json")
    guard let data = try? Data(contentsOf: file), data.count <= 1024,
          let record = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          Set(record.keys) == Set(["phase", "domain", "code", "stage"]),
          record["phase"] as? String == "picking", record["stage"] as? String == "selectionDisplay",
          (record["domain"] as? String)?.count == 96, record["code"] as? Int == -3800,
          !String(decoding: data, as: UTF8.self).contains("fixture/private") else { return false }
    var metadata = stat()
    guard lstat(file.path, &metadata) == 0, metadata.st_mode & 0o777 == 0o600 else { return false }
    let victim = directory.appendingPathComponent("untouched-fixture")
    do {
        try Data("unchanged".utf8).write(to: victim)
        try FileManager.default.removeItem(at: file)
        try FileManager.default.createSymbolicLink(at: file, withDestinationURL: victim)
        galaxyWriteCaptureDiagnostic(phase: "capturing", error: error, stage: "external", directory: directory)
        guard (try Data(contentsOf: victim)) == Data("unchanged".utf8),
              lstat(file.path, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFREG else { return false }
        galaxyClearCaptureDiagnostic(directory: directory)
        guard !FileManager.default.fileExists(atPath: file.path) else { return false }
        let link = directory.appendingPathComponent("linked-directory")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: directory)
        galaxyWriteCaptureDiagnostic(phase: "picking", error: error, stage: "external", directory: link)
        return !FileManager.default.fileExists(atPath: file.path)
    } catch { return false }
}


private func nativeCaptureErrorMappingSelfCheck() -> Bool {
    let cases: [(String, Int, String)] = [
        ("GalaxyControl.NativeCapture", 2, "permissionRequired"),
        ("GalaxyControl.CaptureBridge", 2, "processingFailed"),
        ("Other.Error", -3801, "processingFailed"),
        (NSCocoaErrorDomain, CocoaError.Code.fileWriteNoPermission.rawValue, "permissionRequired"),
        (NSCocoaErrorDomain, CocoaError.Code.fileWriteOutOfSpace.rawValue, "storageFull"),
        (NSCocoaErrorDomain, CocoaError.Code.userCancelled.rawValue, "cancelled"),
        (NSPOSIXErrorDomain, Int(EACCES), "permissionRequired"),
        (NSPOSIXErrorDomain, Int(ENOSPC), "storageFull"),
        (NSPOSIXErrorDomain, Int(EIO), "processingFailed")
    ]
    for (domain, code, expected) in cases {
        guard galaxyCaptureErrorCode(NSError(domain: domain, code: code)) == expected else { return false }
    }
    if #available(macOS 12.3, *) {
        guard galaxyCaptureErrorCode(NSError(domain: SCStreamErrorDomain, code: SCStreamError.Code.userDeclined.rawValue)) == "permissionRequired",
              galaxyCaptureErrorCode(NSError(domain: SCStreamErrorDomain, code: SCStreamError.Code.userStopped.rawValue)) == "cancelled",
              galaxyCaptureErrorCode(NSError(domain: SCStreamErrorDomain, code: SCStreamError.Code.missingEntitlements.rawValue)) == "processingFailed" else { return false }
    }
    return true
}
