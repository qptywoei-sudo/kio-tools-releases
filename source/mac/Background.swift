import AppKit

/// A per-user login item. Only GalaxyControl's own job is touched.
enum GalaxyStartup {
    static let label = "local.galaxycontrol.login"
    static var url: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(label).plist") }
    static var enabled: Bool {
        guard let data = try? Data(contentsOf: url),
              let value = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
              value["Label"] as? String == label,
              let arguments = value["ProgramArguments"] as? [String],
              let index = arguments.firstIndex(of: "-a"), arguments.indices.contains(index + 1) else { return false }
        return URL(fileURLWithPath: arguments[index + 1]).standardizedFileURL.resolvingSymlinksInPath() == Bundle.main.bundleURL.standardizedFileURL.resolvingSymlinksInPath()
    }
    static var domain: String { "gui/\(getuid())" }
    static func run(_ arguments: [String]) -> (Int32, String) {
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/bin/launchctl"); process.arguments = arguments
        let output = Pipe(); process.standardOutput = output; process.standardError = output; process.standardInput = FileHandle.nullDevice
        do { try process.run(); let data = output.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit(); return (process.terminationStatus, String(data: data, encoding: .utf8) ?? "") }
        catch { return (-1, error.localizedDescription) }
    }
    static func configure(_ enabled: Bool, appURL: URL = Bundle.main.bundleURL) throws {
        // open exits after launching, so an explicit Quit remains a real quit.
        if enabled {
            let job: [String: Any] = ["Label": label, "ProgramArguments": ["/usr/bin/open", "-g", "-j", "-a", appURL.path, "--args", "--background"], "RunAtLoad": true, "LimitLoadToSessionType": "Aqua", "ProcessType": "Background"]
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try PropertyListSerialization.data(fromPropertyList: job, format: .xml, options: 0)
            // Refuse an unexpected file occupying the job name.
            if FileManager.default.fileExists(atPath: url.path), !enabledFileBelongsToApp() { throw NSError(domain: "GalaxyControl", code: 1, userInfo: [NSLocalizedDescriptionKey: L("자동 실행 설정을 저장하지 못했습니다.")]) }
            let previousData = try? Data(contentsOf: url)
            try data.write(to: url, options: .atomic)
            _ = run(["bootout", "\(domain)/\(label)"])
            _ = run(["enable", "\(domain)/\(label)"])
            let result = run(["bootstrap", domain, url.path])
            guard result.0 == 0 else {
                // A failed change must restore this app's previous login item.
                _ = run(["bootout", "\(domain)/\(label)"])
                if let previousData = previousData { try previousData.write(to: url, options: .atomic); _ = run(["bootstrap", domain, url.path]) }
                else { try? FileManager.default.removeItem(at: url) }
                throw NSError(domain: "GalaxyControl", code: Int(result.0), userInfo: [NSLocalizedDescriptionKey: result.1])
            }
        } else if enabledFileBelongsToApp() {
            _ = run(["bootout", "\(domain)/\(label)"])
            try FileManager.default.removeItem(at: url)
        }
    }
    private static func enabledFileBelongsToApp() -> Bool {
        guard let data = try? Data(contentsOf: url), let value = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] else { return false }
        return value["Label"] as? String == label
    }
}

final class GalaxyNavigationButton: NSButton {
    override func draw(_ dirtyRect: NSRect) {
        if state == .on {
            BogoTheme.selection.setFill()
            NSBezierPath(roundedRect: bounds.insetBy(dx: 1, dy: 1), xRadius: 9, yRadius: 9).fill()
        }
        super.draw(dirtyRect)
    }
}

extension GalaxyController {
    func prepareBackgroundControls() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem?.button {
            button.image = NSImage(named: "KIOTools") ?? NSImage(systemSymbolName: "rectangle.stack", accessibilityDescription: "Bogo Tools")
            button.image?.size = NSSize(width: 20, height: 20)
            button.image?.isTemplate = false; button.toolTip = "Bogo Tools"
        }
        updateStatusMenu()
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in self?.updateStatusMenu(); self?.refreshSettings() }
        pasteMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self = self, event.window === self.window,
                  event.charactersIgnoringModifiers?.lowercased() == "v" else { return event }
            let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask).subtracting([.capsLock, .numericPad, .function])
            guard modifiers == .command || modifiers == .control else { return event }
            if let text = self.window.firstResponder as? NSTextView, text.isEditable {
                if modifiers == .control { text.paste(nil); return nil }
                return event
            }
            let handled = self.selectedFeature == 0 ? self.imageTools.pasteFromClipboard() : self.selectedFeature == 1 ? self.documentTools.pasteFromClipboard() : false
            return handled ? nil : event
        }
    }
    func updateStatusMenu() {
        let menu = NSMenu()
        for (title, action) in [("Bogo Tools 열기", #selector(showMain)), ("캡처 시작", #selector(captureFromMenu)), ("저장 폴더 열기", #selector(revealCaptureFolder))] {
            let item = NSMenuItem(title: L(title), action: action, keyEquivalent: ""); item.target = self; menu.addItem(item)
        }
        menu.addItem(.separator())
        let setting = NSMenuItem(title: L("설정"), action: #selector(showSettings), keyEquivalent: ""); setting.target = self; menu.addItem(setting)
        let quit = NSMenuItem(title: L("Bogo Tools 종료"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: ""); menu.addItem(quit)
        statusItem?.menu = menu
    }
    @objc func showMain() { if let agentHost = agentHost { agentHost.show() } else { showNativeTool(selectedFeature) } }
    @objc func captureFromMenu() { if agentHost?.shortcut("areaCapture") != true { captureHub.beginCapture() } }
    @objc func revealCaptureFolder() { NSWorkspace.shared.open(captureHub.saveDirectory) }
    @objc func showSettings() {
        if let host = agentHost { host.navigate("settings"); return }
        if settingsWindow == nil {
            let panel = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 540, height: 260), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            panel.title = "설정"; panel.isReleasedWhenClosed = false; panel.appearance = NSAppearance(named: .aqua); panel.backgroundColor = BogoTheme.background; panel.center()
            let title = label("언제든 바로 캡처", size: 20, bold: true)
            startupSwitch = NSButton(checkboxWithTitle: "컴퓨터 로그인 시 자동 실행", target: self, action: #selector(toggleStartup))
            let detail = label("자동 실행할 때는 창을 띄우지 않습니다. 창을 닫아도 캡처 단축키는 계속 사용할 수 있습니다. 메뉴 막대 아이콘에서 앱을 다시 열거나 완전히 종료하세요.")
            detail.textColor = .secondaryLabelColor
            let shortcut = NSButton(title: "캡처 단축키와 저장 폴더", target: self, action: #selector(showCapturePreferences)); shortcut.bezelStyle = .rounded
            let stack = NSStackView(views: [title, startupSwitch!, detail, shortcut]); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 18
            stack.translatesAutoresizingMaskIntoConstraints = false; panel.contentView!.addSubview(stack)
            NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: panel.contentView!.leadingAnchor, constant: 24), stack.trailingAnchor.constraint(equalTo: panel.contentView!.trailingAnchor, constant: -24), stack.topAnchor.constraint(equalTo: panel.contentView!.topAnchor, constant: 24), detail.widthAnchor.constraint(equalTo: stack.widthAnchor)])
            settingsWindow = panel
        }
        refreshSettings(); settingsWindow?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func refreshSettings() { startupSwitch?.state = GalaxyStartup.enabled ? .on : .off }
    @objc func toggleStartup() {
        do { try GalaxyStartup.configure(startupSwitch?.state == .on) }
        catch { notice("자동 실행 설정 확인", error.localizedDescription) }
        refreshSettings()
    }
    @objc func showCapturePreferences() { settingsWindow?.orderOut(nil); if let host = agentHost { host.navigate("settings") } else { showNativeTool(2) } }
}

func fullAppHelp() -> String { L(appHelp) + "\n\n" + L("가벼운 사용법: 편집창 위의 아이콘에 마우스를 올리면 설명이 보입니다. 자르기·모자이크·도형·글자는 상단 아이콘을 사용하고, 더보기에서 회전과 세부 설정을 찾을 수 있습니다. 이미지·PDF에 파일을 끌어 놓거나 Ctrl/⌘V로 사진과 파일을 추가하세요. 글자 입력칸에서는 평소처럼 글자가 붙습니다. 설정에서 자동 실행을 켜면 로그인 후 창 없이 시작하며, 메뉴 막대 아이콘에서 열기·캡처·종료를 선택할 수 있습니다.") }
