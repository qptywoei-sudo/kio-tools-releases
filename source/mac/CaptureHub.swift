import AppKit
import Carbon
import CoreGraphics

final class CaptureHubController: NSObject {
    weak var owner: GalaxyController?
    let folderLabel = NSTextField(wrappingLabelWithString: "")
    let keyMenu = NSPopUpButton()
    let modeMenu = NSPopUpButton()
    let monitorMenu = NSPopUpButton()
    let delayMenu = NSPopUpButton()
    let command = NSButton(checkboxWithTitle: "⌘", target: nil, action: nil)
    let control = NSButton(checkboxWithTitle: "Control", target: nil, action: nil)
    let option = NSButton(checkboxWithTitle: "Option", target: nil, action: nil)
    let shift = NSButton(checkboxWithTitle: "Shift", target: nil, action: nil)
    var shortcutApply: ((UInt32, UInt32) -> Bool)?
    var hotKey: EventHotKeyRef?
    var handler: EventHandlerRef?
    var applied: (UInt32, UInt32)?
    var capturing = false
    var editors: [CaptureEditorController] = []
    var closeObservers: [NSObjectProtocol] = []
    let preferences = UserDefaults.standard
    private var optionsStack: NSStackView?
    private var optionsHeight: NSLayoutConstraint?
    private var optionsButton: NSButton?
    private var nativeCapture: AnyObject?
    private var captureButton: NSButton?
    private var cancelCaptureButton: NSButton?

    let keyCodes: [(String, UInt32)] = [
        ("A", 0), ("B", 11), ("C", 8), ("D", 2), ("E", 14), ("F", 3),
        ("G", 5), ("H", 4), ("I", 34), ("J", 38), ("K", 40), ("L", 37),
        ("M", 46), ("N", 45), ("O", 31), ("P", 35), ("Q", 12), ("R", 15),
        ("S", 1), ("T", 17), ("U", 32), ("V", 9), ("W", 13), ("X", 7),
        ("Y", 16), ("Z", 6), ("F1", 122), ("F2", 120), ("F3", 99),
        ("F4", 118), ("F5", 96), ("F6", 97), ("F7", 98), ("F8", 100),
        ("F9", 101), ("F10", 109), ("F11", 103), ("F12", 111)
    ]

    var saveDirectory: URL {
        if let path = preferences.string(forKey: "capture.saveDirectory"), !path.isEmpty {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Pictures/GalaxyControl", isDirectory: true)
    }

    func button(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action)
        b.bezelStyle = .rounded
        return b
    }

    func makeView(owner: GalaxyController) -> NSBox {
        self.owner = owner
        modeMenu.addItems(withTitles: ["선택 영역", "전체 화면 · 선택 모니터"])
        refreshMonitors()
        delayMenu.addItems(withTitles: ["즉시", "3초 지연", "5초 지연"])
        keyMenu.addItems(withTitles: keyCodes.map { $0.0 })
        keyMenu.selectItem(withTitle: preferences.string(forKey: "capture.hotkey.key") ?? "A")
        if preferences.object(forKey: "capture.hotkey.modifiers") == nil {
            control.state = .on
            shift.state = .on
        } else {
            let bits = UInt32(preferences.integer(forKey: "capture.hotkey.modifiers"))
            command.state = bits & UInt32(cmdKey) != 0 ? .on : .off
            control.state = bits & UInt32(controlKey) != 0 ? .on : .off
            option.state = bits & UInt32(optionKey) != 0 ? .on : .off
            shift.state = bits & UInt32(shiftKey) != 0 ? .on : .off
        }
        keyMenu.widthAnchor.constraint(equalToConstant: 80).isActive = true
        folderLabel.font = .systemFont(ofSize: 12)
        folderLabel.textColor = .secondaryLabelColor
        folderLabel.stringValue = saveDirectory.path
        folderLabel.maximumNumberOfLines = 1; folderLabel.lineBreakMode = .byTruncatingMiddle
        folderLabel.toolTip = saveDirectory.path
        let capture = button("캡처 시작", #selector(beginCapture))
        captureButton = capture
        let cancel = button("취소", #selector(cancelNativeCapture)); cancel.isHidden = true; cancelCaptureButton = cancel
        capture.image = NSImage(systemSymbolName: "camera.viewfinder", accessibilityDescription: L("캡처 시작")); capture.imagePosition = .imageLeading
        capture.bezelColor = BogoTheme.accent; capture.contentTintColor = .white
        let photo = button("사진 열어 편집", #selector(openPhoto))
        photo.image = NSImage(systemSymbolName: "photo", accessibilityDescription: L("사진 열어 편집")); photo.imagePosition = .imageLeading
        let options = button("캡처 설정", #selector(toggleCaptureOptions))
        options.image = NSImage(systemSymbolName: "slider.horizontal.3", accessibilityDescription: L("캡처 설정")); options.imagePosition = .imageLeading
        optionsButton = options
        let advanced = NSStackView(views: [
            owner.label("캡처 단축키", bold: true),
            owner.row([command, control, option, shift, keyMenu, button("단축키 적용", #selector(applyShortcut))]),
            owner.row([button("폴더 지정", #selector(chooseFolder)), button("저장 폴더 열기", #selector(revealFolder))]),
            owner.label("단축키와 저장 폴더는 다음 실행에도 유지됩니다.", size: 11)
        ])
        advanced.orientation = .vertical; advanced.alignment = .leading; advanced.spacing = 10
        advanced.isHidden = true; optionsStack = advanced
        let view = owner.section("캡처", [
            owner.row([modeMenu, monitorMenu, delayMenu]),
            owner.row([capture, cancel, photo, options]),
            owner.label("캡처는 새 파일로 자동 저장되고 편집창이 바로 열립니다.", size: 12),
            folderLabel,
            advanced
        ])
        optionsHeight = view.heightAnchor.constraint(equalToConstant: 230); optionsHeight?.isActive = true
        installHandler()
        registerShortcut(showResult: false)
        return view
    }

    @objc private func toggleCaptureOptions() {
        guard let stack = optionsStack else { return }
        stack.isHidden.toggle(); optionsHeight?.constant = stack.isHidden ? 230 : 380
        optionsButton?.state = stack.isHidden ? .off : .on
    }

    func installHandler() {
        var event = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let pointer = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        let result = InstallEventHandler(GetApplicationEventTarget(), { _, event, data in
            guard let data = data, let event = event else { return OSStatus(eventNotHandledErr) }
            var identifier = EventHotKeyID()
            guard GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &identifier) == noErr, identifier.signature == 0x4743544C, identifier.id == 1 else { return OSStatus(eventNotHandledErr) }
            let hub = Unmanaged<CaptureHubController>.fromOpaque(data).takeUnretainedValue()
            DispatchQueue.main.async { if hub.owner?.agentHost?.shortcut("areaCapture") != true { hub.beginCapture() } }
            return noErr
        }, 1, &event, pointer, &handler)
        if result != noErr {
            owner?.status.stringValue = "캡처 단축키를 준비하지 못했습니다. ‘부분 캡처’ 버튼은 사용할 수 있습니다."
        }
    }

    func registerShortcut(showResult: Bool) {
        guard handler != nil else { return }
        guard let selected = keyMenu.titleOfSelectedItem, let code = keyCodes.first(where: { $0.0 == selected })?.1 else { return }
        var modifiers: UInt32 = 0
        if command.state == .on { modifiers |= UInt32(cmdKey) }
        if control.state == .on { modifiers |= UInt32(controlKey) }
        if option.state == .on { modifiers |= UInt32(optionKey) }
        if shift.state == .on { modifiers |= UInt32(shiftKey) }
        if modifiers == 0 || ((selected == "C" || selected == "V") && (modifiers == UInt32(cmdKey) || modifiers == UInt32(controlKey))) {
            owner?.notice("단축키 선택", "Control, Command, Option, Shift 중 하나 이상을 함께 선택하세요. 일반 복사/붙여넣기 단축키는 다른 조합으로 지정해 주세요.")
            return
        }
        if let apply = shortcutApply {
            if apply(code, modifiers) { if showResult { owner?.status.stringValue = L("새 캡처 단축키를 적용했습니다. Bogo Tools가 실행 중일 때 사용할 수 있습니다.") } }
            else if showResult { owner?.notice("단축키가 사용 중입니다", "선택한 조합을 다른 앱이 사용하거나 macOS가 예약했을 수 있습니다. 다른 조합을 선택해 주세요.") }
            return
        }
        if let old = applied, old.0 == code && old.1 == modifiers, hotKey != nil { return }
        var newKey: EventHotKeyRef?
        let result = RegisterEventHotKey(code, modifiers, EventHotKeyID(signature: 0x4743544C, id: 1),
                                        GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &newKey)
        if result != noErr {
            owner?.status.stringValue = "캡처 단축키를 등록하지 못했습니다. 다른 조합을 선택하세요."
            if showResult { owner?.notice("단축키가 사용 중입니다", "선택한 조합을 다른 앱이 사용하거나 macOS가 예약했을 수 있습니다. 다른 조합을 선택해 주세요.") }
            return
        }
        if let old = hotKey { UnregisterEventHotKey(old) }
        hotKey = newKey
        applied = (code, modifiers)
        preferences.set(selected, forKey: "capture.hotkey.key")
        preferences.set(Int(modifiers), forKey: "capture.hotkey.modifiers")
        if showResult { owner?.status.stringValue = "새 캡처 단축키를 적용했습니다. Bogo Tools가 실행 중일 때 사용할 수 있습니다." }
    }

    @objc func applyShortcut() { registerShortcut(showResult: true) }

    func readyDirectory() -> Bool {
        do {
            try FileManager.default.createDirectory(at: saveDirectory, withIntermediateDirectories: true, attributes: nil)
            guard FileManager.default.isWritableFile(atPath: saveDirectory.path) else { throw NSError(domain: "GalaxyControl", code: 1) }
            return true
        } catch {
            owner?.notice("저장 폴더 확인", "이 폴더에 저장할 수 없습니다. ‘폴더 지정’에서 쓸 수 있는 폴더를 선택하세요.")
            return false
        }
    }

    func refreshMonitors() {
        let selected = max(0, monitorMenu.indexOfSelectedItem)
        monitorMenu.removeAllItems()
        for (index, screen) in NSScreen.screens.enumerated() {
            let name = screen.localizedName.isEmpty ? Lf("모니터 %d", index + 1) : screen.localizedName
            monitorMenu.addItem(withTitle: "\(index + 1) · \(name)")
        }
        if monitorMenu.numberOfItems > 0 { monitorMenu.selectItem(at: min(selected, monitorMenu.numberOfItems - 1)) }
    }

    func captureFile() -> URL {
        let format = DateFormatter(); format.locale = Locale(identifier: "en_US_POSIX"); format.dateFormat = "yyyyMMdd-HHmmss"
        let suffix = preferences.string(forKey: "capture.format") == "jpg" ? "jpg" : "png"
        return saveDirectory.appendingPathComponent("Capture-\(format.string(from: Date()))-\(UUID().uuidString.prefix(6)).\(suffix)")
    }

    @objc func beginCapture() {
        guard !capturing, readyDirectory() else { return }
        refreshMonitors()
        capturing = true
        captureButton?.isEnabled = false; cancelCaptureButton?.isHidden = false
        let file = captureFile()
        let operation = GalaxySystemCapture(region: modeMenu.indexOfSelectedItem == 0,
            monitorIndex: max(0, monitorMenu.indexOfSelectedItem),
            delay: [0.0, 3.0, 5.0][max(0, delayMenu.indexOfSelectedItem)]) { [weak self] image, error in
            guard let self = self else { return }
            self.capturing = false; self.nativeCapture = nil
            self.captureButton?.isEnabled = true; self.cancelCaptureButton?.isHidden = true
            NSApp.unhide(nil); NSApp.activate(ignoringOtherApps: true)
            if let error = error {
                self.owner?.notice("캡처 실행 확인", error.localizedDescription)
            } else if let image = image {
                do {
                    guard let data = NSBitmapImageRep(cgImage: image).representation(using: file.pathExtension == "jpg" ? .jpeg : .png, properties: [.compressionFactor: 0.92]) else {
                        throw NSError(domain: "GalaxyControl", code: 2, userInfo: [NSLocalizedDescriptionKey: L("캡처 이미지를 저장할 수 없습니다.")])
                    }
                    try data.write(to: file, options: .atomic)
                    self.openEditor(file, captureSession: true)
                    self.owner?.status.stringValue = L("캡처를 자동 저장했습니다. 편집창에서 복사·붙여넣기와 주석을 사용할 수 있습니다.")
                } catch { self.owner?.notice("캡처 저장 확인", error.localizedDescription) }
            } else { self.owner?.status.stringValue = L("캡처를 취소했습니다.") }
        }
        nativeCapture = operation
        owner?.status.stringValue = L("캡처할 영역을 드래그하거나 원하는 창을 선택하세요.")
        operation.begin()
    }

    @objc private func cancelNativeCapture() {
        (nativeCapture as? GalaxyCaptureOperation)?.cancel()
    }

    @objc func openPhoto() {
        let panel = NSOpenPanel()
        panel.title = "편집할 사진 선택"
        panel.allowedFileTypes = ["png", "jpg", "jpeg", "heic", "tiff", "webp", "bmp", "gif"]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url, readyDirectory() { openEditor(url) }
    }

    func openEditor(_ imageURL: URL, captureSession: Bool = false) {
        if captureSession, preferences.object(forKey: "capture.openEditor") as? Bool == false { return }
        guard let image = NSImage(contentsOf: imageURL), image.isValid else {
            owner?.notice("사진 열기 확인", "이 파일을 이미지로 읽을 수 없습니다. PNG 또는 JPEG 등 지원되는 사진 파일을 선택하세요.")
            return
        }
        let editor = CaptureEditorController(imageURL: imageURL, saveDirectory: saveDirectory, captureSession: captureSession)
        editors.append(editor)
        editor.showWindow(nil)
        editor.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        if let editorWindow = editor.window {
            let observer = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: editorWindow, queue: .main) { [weak self, weak editor] _ in
                if let editor = editor { self?.editors.removeAll(where: { $0 === editor }) }
            }
            closeObservers.append(observer)
        }
    }

    @objc func chooseFolder() {
        let panel = NSOpenPanel()
        panel.title = "캡처가 자동 저장될 폴더"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.directoryURL = saveDirectory
        if panel.runModal() == .OK, let url = panel.url {
            preferences.set(url.path, forKey: "capture.saveDirectory")
            folderLabel.stringValue = url.path; folderLabel.toolTip = url.path
            owner?.status.stringValue = "다음 캡처부터 선택한 폴더에 저장됩니다. 열려 있는 편집창은 기존 저장 폴더를 사용합니다."
        }
    }

    @objc func revealFolder() {
        if readyDirectory() { NSWorkspace.shared.open(saveDirectory) }
    }

    func shutdown() {
        (nativeCapture as? GalaxyCaptureOperation)?.cancel()
        nativeCapture = nil
        if let key = hotKey { UnregisterEventHotKey(key) }
        if let handler = handler { RemoveEventHandler(handler) }
        closeObservers.forEach { NotificationCenter.default.removeObserver($0) }
        hotKey = nil
        handler = nil
    }
}
