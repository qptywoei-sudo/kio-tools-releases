import AppKit
import CoreAudio

enum BogoTheme {
    static let header = NSColor(srgbRed: 255.0/255, green: 243.0/255, blue: 232.0/255, alpha: 1)
    static let background = NSColor(srgbRed: 255.0/255, green: 250.0/255, blue: 246.0/255, alpha: 1)
    static let selection = NSColor(srgbRed: 255.0/255, green: 231.0/255, blue: 212.0/255, alpha: 1)
    static let line = NSColor(srgbRed: 241.0/255, green: 211.0/255, blue: 189.0/255, alpha: 1)
    static let ink = NSColor(srgbRed: 52.0/255, green: 43.0/255, blue: 38.0/255, alpha: 1)
    static let accent = NSColor(srgbRed: 252.0/255, green: 117.0/255, blue: 1.0/255, alpha: 1)
}

/// Read the actual Mac output device; do not change the user's system selection.
func galaxyAudioOutputName() -> String {
    var device = AudioDeviceID(0), size = UInt32(MemoryLayout<AudioDeviceID>.size)
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultOutputDevice, mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device) == noErr, device != 0 else { return L("시스템 기본 출력") }
    address.mSelector = kAudioObjectPropertyName
    let name = UnsafeMutablePointer<Unmanaged<CFString>?>.allocate(capacity: 1)
    name.initialize(to: nil); defer { name.deinitialize(count: 1); name.deallocate() }
    size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    guard AudioObjectGetPropertyData(device, &address, 0, nil, &size, name) == noErr, let value = name.pointee else { return L("시스템 기본 출력") }
    return value.takeRetainedValue() as String
}

final class GalaxyScrollableContent: NSView { override var isFlipped: Bool { true } }

struct Phone {
    let serial: String
    let label: String
    let usb: Bool
}

func phoneDeviceRows(_ text: String) -> [[String:Any]] {
    text.components(separatedBy: .newlines).compactMap { line in
        let fields = line.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        guard fields.count > 1, ["device","unauthorized","offline"].contains(fields[1]),
              !fields[0].hasPrefix("emulator-"), phoneSerialValid(fields[0]) else { return nil }
        let model = fields.first(where: { $0.hasPrefix("model:") })?.dropFirst(6)
        let name = model.map { String($0).replacingOccurrences(of: "_", with: " ") } ?? "Galaxy"
        let wireless = fields[0].contains(":") || fields[0].contains("._adb-tls-connect._tcp")
        let usb = fields.contains(where: { $0.hasPrefix("usb:") }) || !wireless
        return ["serial":fields[0],"label":name,"transport":usb ? "usb" : "wifi","status":fields[1]]
    }
}
func phones(_ text: String) -> [Phone] {
    phoneDeviceRows(text).compactMap { row in
        guard row["status"] as? String == "device", let serial = row["serial"] as? String,
              let label = row["label"] as? String else { return nil }
        let usb = row["transport"] as? String == "usb"
        return Phone(serial:serial,label:"\(label) · \(usb ? "USB" : "Wi-Fi")",usb:usb)
    }
}
func phoneSerialValid(_ value: String) -> Bool {
    !value.isEmpty && value.utf8.count <= 200 && !value.hasPrefix("emulator-") && value.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || "_.:-".contains($0)) }
}
func validPhoneLANEndpoint(_ value: String) -> Bool {
    guard validEndpoint(value) else { return false }
    let host = value.split(separator:":")[0], octets = host.split(separator:".").compactMap { Int($0) }
    guard octets.count == 4, host.split(separator:".").allSatisfy({ $0.count == 1 || $0.first != "0" }) else { return false }
    return octets[0] == 10 || (octets[0] == 172 && (16...31).contains(octets[1])) ||
        (octets[0] == 192 && octets[1] == 168) || (octets[0] == 169 && octets[1] == 254) || octets == [127,0,0,1]
}

func validEndpoint(_ value: String) -> Bool {
    let parts = value.split(separator: ":", omittingEmptySubsequences: false)
    guard parts.count == 2, let port = Int(parts[1]), (1...65535).contains(port),
          parts[1].allSatisfy({ $0.isASCII && $0.isNumber }) else { return false }
    let octets = parts[0].split(separator: ".", omittingEmptySubsequences: false)
    return octets.count == 4 && octets.allSatisfy { item in
        !item.isEmpty && item.count <= 3 && item.allSatisfy({ $0.isASCII && $0.isNumber }) &&
        Int(item).map({ (0...255).contains($0) }) == true
    }
}

func phoneMirrorArguments(phone: Phone, keyboard: String, mouse: String, audioMode: Int, clipboard: Bool) -> [String]? {
    guard phoneSerialValid(phone.serial), ["uhid","sdk"].contains(keyboard), ["sdk","uhid"].contains(mouse), (0...2).contains(audioMode) else { return nil }
    var args = ["--serial=\(phone.serial)","--keyboard=\(keyboard)","--mouse=\(mouse)","--shortcut-mod=lsuper,rsuper","--max-size=1920","--max-fps=60","--window-title=Galaxy · \(phone.label)"]
    if !clipboard { args.append("--no-clipboard-autosync") }
    args += audioMode == 2 ? ["--no-audio"] : ["--audio-source=output","--require-audio"]
    if audioMode == 1 { args.append("--audio-codec=aac") }
    return args
}
func phoneControlSelfCheck() -> Bool {
    let fixture = "List of devices attached\nUSB1 device usb:1 model:Galaxy_Fold\nadb-phone._adb-tls-connect._tcp device model:Galaxy_Fold\nNEEDS_ALLOW unauthorized usb:2\nOFFLINE offline usb:3\nemulator-5554 device\nmalicious;command device\n"
    let rows = phoneDeviceRows(fixture), phones = phones(fixture)
    guard rows.count == 4, phones.count == 2, rows[2]["status"] as? String == "unauthorized", rows[3]["status"] as? String == "offline", phones[0].usb, !phones[1].usb,
          validPhoneLANEndpoint("192.168.1.6:37123"), validPhoneLANEndpoint("172.16.1.2:65535"), !validPhoneLANEndpoint("8.8.8.8:5555"), !validPhoneLANEndpoint("172.32.1.2:5555"), !validPhoneLANEndpoint("192.168.001.6:5555"), !validPhoneLANEndpoint("192.168.1.6:5555;command"), !phoneSerialValid("-s injected") else { return false }
    guard let direct = phoneMirrorArguments(phone:phones[0],keyboard:"uhid",mouse:"sdk",audioMode:0,clipboard:true), direct.contains("--keyboard=uhid"), direct.contains("--mouse=sdk"), direct.contains("--require-audio"), !direct.contains("--no-clipboard-autosync"),
          let compatible = phoneMirrorArguments(phone:phones[0],keyboard:"sdk",mouse:"uhid",audioMode:1,clipboard:false), compatible.contains("--audio-codec=aac"), compatible.contains("--no-clipboard-autosync"),
          let silent = phoneMirrorArguments(phone:phones[0],keyboard:"sdk",mouse:"sdk",audioMode:2,clipboard:true), silent.contains("--no-audio"), !silent.contains("--require-audio") else { return false }
    return phoneMirrorArguments(phone:phones[0],keyboard:"shell",mouse:"sdk",audioMode:0,clipboard:true) == nil
}

let resources = Bundle.main.resourceURL!
#if arch(arm64)
let machine = "arm64"
#else
let machine = "x86_64"
#endif
let adbURL = resources.appendingPathComponent("tools/platform-tools/adb")
let scrcpyURL = resources.appendingPathComponent("tools/\(machine)/scrcpy")
let serverURL = resources.appendingPathComponent("tools/\(machine)/scrcpy-server")

if CommandLine.arguments.contains("--self-check") {
    let fm = FileManager.default
    let fixture = "List of devices attached\nUSB1 device usb:1 model:Galaxy_Fold transport_id:1\nadb-phone._adb-tls-connect._tcp device model:Galaxy_Fold transport_id:2\nBAD unauthorized usb:2\nemulator-5554 device\n"
    let ok = fm.isExecutableFile(atPath: adbURL.path) && fm.isExecutableFile(atPath: scrcpyURL.path) &&
        fm.fileExists(atPath: serverURL.path) && phones(fixture).count == 2 &&
        phones(fixture).first?.usb == true && phones(fixture).last?.usb == false &&
        validEndpoint("192.168.1.6:34323") && !validEndpoint("192.168.1.6:99999") &&
        !validEndpoint("256.1.1.1:1234") && !validEndpoint("192.168.1.6;echo:1234") && captureEditorSelfCheck() && documentToolsSelfCheck() && codeToolsSelfCheck() && screenRecordSelfCheck() && nativeCaptureSelfCheck() && nativeBridgeSelfCheck()
    print("GalaxyControl \(machine): portable tools, device parsing, address validation \(ok ? "OK" : "FAILED")")
    exit(ok ? 0 : 1)
}

if CommandLine.arguments.contains("--phone-control-self-check") { let ok = phoneControlSelfCheck(); print("Existing phone parsing, typed ADB inputs and scrcpy keyboard/audio/clipboard arguments: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

if CommandLine.arguments.contains("--native-bridge-self-check") { let ok = nativeBridgeSelfCheck(); print("Native bridge security and shortcut validation: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

if CommandLine.arguments.contains("--native-bridge-integration-check") { let ok = nativeBridgeIntegrationCheck(); print("Native spool request, permission status and heartbeat: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

if CommandLine.arguments.contains("--native-shortcut-self-check") { let ok = nativeBridgeShortcutRegistrationCheck(); print("Native shortcut registration conflict rollback: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

if CommandLine.arguments.contains("--agent-endpoint-self-check") { let ok = GalaxyAgentEndpoint.selfCheck(); print("Local Agent port selection and health identity: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

if CommandLine.arguments.contains("--agent-host-layout-check") { let ok = GalaxyAgentHost.layoutSelfCheck(); print("Shared Mac host layout at 900×640 and 1150×820: \(ok ? "OK" : "FAILED")"); exit(ok ? 0 : 1) }

struct ToolResult {
    let status: Int32
    let output: String
}

func tool(_ args: [String], input: String? = nil, seconds: Double = 20) -> ToolResult {
    let p = Process()
    p.executableURL = adbURL
    p.arguments = args
    let output = Pipe()
    p.standardOutput = output
    p.standardError = output
    let incoming = Pipe()
    if input != nil { p.standardInput = incoming } else { p.standardInput = FileHandle.nullDevice }
    do {
        try p.run()
        if let input = input {
            incoming.fileHandleForWriting.write(Data(input.utf8))
            incoming.fileHandleForWriting.closeFile()
        }
        let timeout = DispatchWorkItem { if p.isRunning { p.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + seconds, execute: timeout)
        let data = output.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        timeout.cancel()
        return ToolResult(status: p.terminationStatus, output: String(data: data, encoding: .utf8) ?? "")
    } catch {
        return ToolResult(status: -1, output: Lf("설치된 연결 도구를 실행하지 못했습니다: %@", String(describing: error.localizedDescription)))
    }
}

func phonePairTool(_ address: String, code: String) -> ToolResult { tool(["pair",address],input:code + "\n") }
func phoneConnectTool(_ address: String) -> ToolResult {
    let connected = tool(["connect",address])
    if connected.status != 0 || connected.output.lowercased().contains("failed") || connected.output.lowercased().contains("cannot") { return connected }
    let state = tool(["-s",address,"get-state"])
    if state.status != 0 || state.output.trimmingCharacters(in:.whitespacesAndNewlines) != "device" { return ToolResult(status:-1,output:state.output) }
    return tool(["devices","-l"])
}
func phoneKeyboardTool(_ serial: String) -> ToolResult { tool(["-s",serial,"shell","am","start","-a","android.settings.HARD_KEYBOARD_SETTINGS"]) }

final class GalaxyController: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var agentHost: GalaxyAgentHost?
    let deviceMenu = NSPopUpButton()
    let keyboardMenu = NSPopUpButton()
    let mouseMenu = NSPopUpButton()
    let audioMenu = NSPopUpButton()
    let audioOutputLabel = NSTextField(wrappingLabelWithString: "")
    let status = NSTextField(wrappingLabelWithString: "연결 준비 중…")
    let pairAddress = NSTextField()
    let pairCode = NSSecureTextField()
    let connectAddress = NSTextField()
    let spinner = NSProgressIndicator()
    var controls: [NSControl] = []
    var devices: [Phone] = []
    var mirror: Process?
    var mirrorOutput = ""
    var mirrorSerial = ""
    var mirrorErrorCode = ""
    var mirrorOptions: [String:Any] = ["keyboard":"uhid","mouse":"uhid","audio":"output","clipboard":true]
    var nativePhoneRows: [[String:Any]] = []
    var shuttingDown = false
    var busy = false
    var stoppedMirrors = Set<ObjectIdentifier>()
    let captureHub = CaptureHubController()
    let imageTools = ImageToolsController()
    let documentTools = DocumentToolsController()
    let codeTools = CodeToolsController()
    let recorder = ScreenRecordController()
    let languageMenu = NSPopUpButton()
    let toolBody = NSView()
    var toolViews: [NSView] = []
    var navigation: [NSButton] = []
    var selectedFeature = 0
    var helpWindow: NSWindow?
    var helpText: NSTextView?
    var statusItem: NSStatusItem?
    var settingsWindow: NSWindow?
    var startupSwitch: NSButton?
    var pasteMonitor: Any?
    var languageObserver: NSObjectProtocol?

    func label(_ text: String, size: CGFloat = 13, bold: Bool = false) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: text)
        l.font = bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size)
        l.textColor = BogoTheme.ink
        return l
    }

    func button(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action)
        b.bezelStyle = .rounded; b.contentTintColor = BogoTheme.ink
        controls.append(b)
        return b
    }

    func row(_ views: [NSView]) -> NSStackView {
        let r = NSStackView(views: views)
        r.orientation = .horizontal
        r.alignment = .centerY
        r.spacing = 10
        return r
    }

    func section(_ title: String, _ views: [NSView]) -> NSBox {
        let stack = NSStackView(views: views)
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        let box = NSBox()
        box.title = title; box.boxType = .custom; box.borderColor = BogoTheme.line; box.fillColor = BogoTheme.background; box.cornerRadius = 8
        let container = NSView()
        box.contentView = container
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)
        for view in views where view is NSTextField {
            view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        }
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: container.bottomAnchor, constant: -12)
        ])
        return box
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let appItem = NSMenuItem()
        menu.addItem(appItem)
        let appMenu = NSMenu()
        let openItem = NSMenuItem(title: "Bogo Tools 열기", action: #selector(showMain), keyEquivalent: ""); openItem.target = self; appMenu.addItem(openItem)
        let settingsItem = NSMenuItem(title: "설정", action: #selector(showSettings), keyEquivalent: ","); settingsItem.target = self; appMenu.addItem(settingsItem)
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Bogo Tools 종료", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        let fileItem = NSMenuItem(title: "파일", action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: "파일")
        fileMenu.addItem(withTitle: "창 닫기", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileItem.submenu = fileMenu; menu.addItem(fileItem)
        let edit = NSMenuItem(title: "편집", action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: "편집")
        editMenu.addItem(withTitle: "잘라내기", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "복사", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "붙여넣기", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "모두 선택", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        edit.submenu = editMenu
        menu.addItem(edit)
        NSApp.mainMenu = menu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 850),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Bogo Tools"
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 1080, height: 740)
        if let frame = NSScreen.main?.visibleFrame {
            window.setContentSize(NSSize(width: min(1280, frame.width), height: min(850, frame.height - 28)))
        }
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.appearance = NSAppearance(named: .aqua)
        window.backgroundColor = BogoTheme.background
        window.center()

        let heading = label("Bogo Tools", size: 23, bold: true)
        let logo = NSImageView(image: NSImage(named: "KIOTools") ?? NSImage(systemSymbolName: "rectangle.stack.fill", accessibilityDescription: "Bogo Tools")!)
        logo.contentTintColor = BogoTheme.accent
        logo.widthAnchor.constraint(equalToConstant: 29).isActive = true
        logo.heightAnchor.constraint(equalToConstant: 29).isActive = true
        deviceMenu.addItem(withTitle: "갤럭시를 연결하고 새로고침하세요")
        deviceMenu.widthAnchor.constraint(equalToConstant: 420).isActive = true
        controls.append(deviceMenu)
        keyboardMenu.addItems(withTitles: ["직접 입력 · 한글/영문 (UHID)", "호환 입력 · 영문/붙여넣기 (SDK)"])
        mouseMenu.addItems(withTitles: ["자유 이동 · 창 밖으로 바로 나가기", "폰 커서 · ⌘ 키로 Mac에 돌아오기"])
        mouseMenu.selectItem(at: 1)
        audioMenu.addItems(withTitles: ["휴대폰 소리 켜기", "호환 오디오 · AAC", "소리 없이 화면만"])
        audioMenu.selectItem(at: min(2, max(0, UserDefaults.standard.integer(forKey: "phone.audioMode"))))
        audioMenu.target = self; audioMenu.action = #selector(audioSelectionChanged)
        audioMenu.widthAnchor.constraint(equalToConstant: 260).isActive = true
        audioOutputLabel.font = .systemFont(ofSize: 12); audioOutputLabel.textColor = .secondaryLabelColor
        audioOutputLabel.maximumNumberOfLines = 1; audioOutputLabel.lineBreakMode = .byTruncatingMiddle
        audioOutputLabel.widthAnchor.constraint(equalToConstant: 370).isActive = true
        refreshAudioOutput()
        controls.append(contentsOf: [keyboardMenu, mouseMenu, audioMenu])
        keyboardMenu.widthAnchor.constraint(equalToConstant: 290).isActive = true
        mouseMenu.widthAnchor.constraint(equalToConstant: 310).isActive = true
        let deviceSection = section("연결된 휴대폰", [
            row([deviceMenu, button("새로고침", #selector(refresh))]),
            row([button("USB 화면 열기", #selector(openUSB)), button("Wi-Fi 화면 열기", #selector(openWiFi)), button("화면 닫기", #selector(stopMirror))]),
            row([label("키보드"), keyboardMenu]), row([label("마우스"), mouseMenu]),
            row([label("소리"), audioMenu, button("소리가 안 날 때", #selector(audioHelp))]),
            row([audioOutputLabel, button("Mac 소리 설정", #selector(openAudioSettings))]),
            row([button("갤럭시 키보드 설정", #selector(keyboardSettings)), button("입력이 안 될 때", #selector(keyboardHelp))])
        ])
        deviceSection.heightAnchor.constraint(equalToConstant: 310).isActive = true

        connectAddress.placeholderString = "폰의 기본 화면 주소:포트 · 예 192.168.1.6:37123"
        connectAddress.widthAnchor.constraint(equalToConstant: 440).isActive = true
        pairAddress.placeholderString = "페어링 팝업의 IP 주소:포트"
        pairAddress.widthAnchor.constraint(equalToConstant: 330).isActive = true
        pairCode.placeholderString = "6자리 코드"
        pairCode.widthAnchor.constraint(equalToConstant: 130).isActive = true
        controls.append(contentsOf: [connectAddress, pairAddress, pairCode])
        let wifiSection = section("Wi-Fi 연결", [
            label("폰에서 개발자 옵션 → 무선 디버깅을 켜세요. Mac과 같은 네트워크를 사용합니다."),
            row([connectAddress, button("주소로 연결", #selector(connectWiFi))]),
            label("처음 연결하는 Mac이면 ‘페어링 코드로 기기 페어링’을 열어 아래에 입력하세요."),
            row([pairAddress, pairCode, button("처음 페어링", #selector(pairWiFi))]),
            label("페어링 포트와 연결용 포트는 다릅니다. 이후에는 새로고침으로 자동 검색합니다.", size: 12)
        ])
        wifiSection.heightAnchor.constraint(equalToConstant: 220).isActive = true

        let help = label("USB: 데이터 케이블 연결 → 폰의 USB 디버깅 허용\n입력: Mac의 갤럭시 창에서 입력칸을 클릭하세요. 한글 직접 입력은 폰의 실제 키보드 언어를 설정하세요.\n복사: Mac → 폰 ⌘V / 폰에서 복사 → Mac에서 ⌘V", size: 12)
        help.textColor = .secondaryLabelColor
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        status.maximumNumberOfLines = 3
        status.widthAnchor.constraint(equalToConstant: 625).isActive = true
        refreshLanguageMenu()
        languageMenu.target = self; languageMenu.action = #selector(changeLanguage)
        func headerIcon(_ symbol: String, _ title: String, _ action: Selector) -> NSButton {
            let b = NSButton(image: NSImage(systemSymbolName: symbol, accessibilityDescription: title)!, target: self, action: action)
            b.title = ""; b.imagePosition = .imageOnly
            b.bezelStyle = .texturedRounded; b.isBordered = false; b.toolTip = title; b.setAccessibilityLabel(title)
            b.widthAnchor.constraint(equalToConstant: 32).isActive = true; b.heightAnchor.constraint(equalToConstant: 32).isActive = true
            return b
        }
        let spacer = NSView(); spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        let top = row([logo, heading, spacer, languageMenu, headerIcon("questionmark.circle", "사용법 / 앱 정보", #selector(showHelp)), headerIcon("gearshape", "설정", #selector(showSettings))])
        top.spacing = 12; top.wantsLayer = true; top.layer?.backgroundColor = BogoTheme.header.cgColor; top.layer?.cornerRadius = 8
        let phoneContent = NSStackView(views: [deviceSection, wifiSection, help]); phoneContent.orientation = .vertical; phoneContent.alignment = .leading; phoneContent.spacing = 18
        for item in [deviceSection, wifiSection, help] { item.widthAnchor.constraint(equalTo: phoneContent.widthAnchor).isActive = true }
        let phoneWrapper = wrap(phoneContent)
        let captureWrapper = wrap(captureHub.makeView(owner: self))
        toolViews = [imageTools.makeView(), documentTools.makeView(), captureWrapper, recorder.makeView(), codeTools.makeView(), phoneWrapper]
        let side = NSStackView(); side.orientation = .vertical; side.alignment = .leading; side.spacing = 8
        let labels = ["이미지", "PDF", "캡처", "화면 녹화", "QR / 바코드", "휴대폰 연결"]
        let symbols = ["photo", "doc.richtext", "viewfinder", "record.circle", "qrcode", "iphone"]
        for (index, text) in labels.enumerated() {
            let b = GalaxyNavigationButton(title: text, target: self, action: #selector(chooseFeature(_:)))
            b.bezelStyle = .regularSquare; b.isBordered = false; b.tag = index; b.alignment = .left
            b.image = NSImage(systemSymbolName: symbols[index], accessibilityDescription: text); b.imagePosition = .imageLeading
            b.font = .systemFont(ofSize: 13, weight: .medium); b.imageHugsTitle = true
            b.widthAnchor.constraint(equalToConstant: 148).isActive = true; b.heightAnchor.constraint(equalToConstant: 42).isActive = true
            side.addArrangedSubview(b); navigation.append(b)
        }
        let divider = NSBox(); divider.boxType = .separator; divider.widthAnchor.constraint(equalToConstant: 148).isActive = true
        side.addArrangedSubview(divider)
        let local = label("내 컴퓨터에서 안전하게", size: 11)
        local.widthAnchor.constraint(equalToConstant: 148).isActive = true; local.textColor = .tertiaryLabelColor; side.addArrangedSubview(local)
        let body = NSStackView(views: [side, toolBody]); body.orientation = .horizontal; body.alignment = .top; body.distribution = .fill; body.spacing = 16
        toolBody.translatesAutoresizingMaskIntoConstraints = false
        side.widthAnchor.constraint(equalToConstant: 148).isActive = true
        toolBody.setContentHuggingPriority(.defaultLow, for: .horizontal)
        toolBody.widthAnchor.constraint(equalTo: body.widthAnchor, constant: -164).isActive = true
        side.heightAnchor.constraint(lessThanOrEqualTo: body.heightAnchor).isActive = true
        toolBody.heightAnchor.constraint(equalTo: body.heightAnchor).isActive = true
        for view in toolViews {
            view.translatesAutoresizingMaskIntoConstraints = false; toolBody.addSubview(view)
            NSLayoutConstraint.activate([view.leadingAnchor.constraint(equalTo: toolBody.leadingAnchor), view.trailingAnchor.constraint(equalTo: toolBody.trailingAnchor), view.topAnchor.constraint(equalTo: toolBody.topAnchor), view.bottomAnchor.constraint(equalTo: toolBody.bottomAnchor)])
        }
        let footer = row([spinner, status])
        let content = NSStackView(views: [top, body, footer]); content.orientation = .vertical; content.alignment = .leading; content.spacing = 16
        content.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 20), content.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -20),
            content.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 20), content.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor, constant: -16),
            body.widthAnchor.constraint(equalTo: content.widthAnchor), body.heightAnchor.constraint(greaterThanOrEqualToConstant: 500), top.widthAnchor.constraint(equalTo: content.widthAnchor)
        ])
        changeFeature()
        AppLanguage.shared.start()
        if !CommandLine.arguments.contains("--layout-check") {
            agentHost = GalaxyAgentHost(owner: self)
            prepareBackgroundControls()
            if !CommandLine.arguments.contains("--background") { showMain() }
        }
        status.stringValue = "창을 닫아도 캡처 단축키를 사용할 수 있습니다."
        if let flag = CommandLine.arguments.firstIndex(of: "--edit-image"), flag + 1 < CommandLine.arguments.count {
            let url = URL(fileURLWithPath: CommandLine.arguments[flag + 1])
            DispatchQueue.main.async { self.captureHub.openEditor(url) }
        }
        if let fixture = Bundle.main.object(forInfoDictionaryKey: "GalaxyControlPreviewImage") as? String {
            DispatchQueue.main.async { self.captureHub.openEditor(URL(fileURLWithPath: fixture)) }
        }
    }

    func wrap(_ content: NSView) -> NSView {
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true; scroll.drawsBackground = false
        let root = GalaxyScrollableContent(); scroll.documentView = root
        root.translatesAutoresizingMaskIntoConstraints = false; content.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(content)
        NSLayoutConstraint.activate([root.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor), content.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 16), content.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -16), content.topAnchor.constraint(equalTo: root.topAnchor, constant: 16), content.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -16)])
        return scroll
    }
    func refreshAudioOutput() {
        audioOutputLabel.stringValue = Lf("Mac 소리 출력: %@", galaxyAudioOutputName())
        audioOutputLabel.toolTip = audioOutputLabel.stringValue
    }
    func applicationDidBecomeActive(_ notification: Notification) { refreshAudioOutput() }
    @objc func audioSelectionChanged() {
        UserDefaults.standard.set(audioMenu.indexOfSelectedItem, forKey: "phone.audioMode")
        status.stringValue = L("소리 설정은 휴대폰 화면을 다시 열면 적용됩니다.")
    }
    @objc func openAudioSettings() {
        refreshAudioOutput()
        if let url = URL(string: "x-apple.systempreferences:com.apple.Sound-Settings.extension") { NSWorkspace.shared.open(url) }
    }
    @objc func audioHelp() {
        refreshAudioOutput()
        var message = Lf("Mac 소리 출력: %@", galaxyAudioOutputName()) + "\n\n" + L("Mac 소리 설정에서 사용할 스피커와 볼륨을 확인하세요. 휴대폰 소리 켜기를 선택하고 화면을 다시 여세요. 오디오 오류가 나오면 호환 오디오 · AAC로 다시 여세요. 일부 앱의 보호된 영상은 소리를 전달하지 않을 수 있습니다.")
        if !mirrorOutput.isEmpty { message += "\n\n" + L("최근 연결 기록:") + "\n" + String(mirrorOutput.suffix(1600)) }
        notice("휴대폰 소리 확인", message)
    }
    @objc func chooseFeature(_ sender: NSButton) { selectedFeature = sender.tag; changeFeature() }
    func changeFeature() {
        for (index, view) in toolViews.enumerated() { view.isHidden = index != selectedFeature }
        for (index, button) in navigation.enumerated() { button.state = index == selectedFeature ? .on : .off; button.contentTintColor = index == selectedFeature ? BogoTheme.accent : BogoTheme.ink; button.needsDisplay = true }
        if selectedFeature == 5 { refresh() }
    }
    func refreshLanguageMenu() {
        let language = AppLanguage.shared
        let selected = language.codes.firstIndex(of: language.code) ?? 1
        let order = [selected] + language.codes.indices.filter { $0 != selected }
        languageMenu.removeAllItems()
        for index in order {
            languageMenu.addItem(withTitle: (index == selected ? "🌐 " : "") + language.names[index])
            if let item = languageMenu.lastItem { item.tag = 997; item.representedObject = index; item.state = index == selected ? .on : .off }
        }
        languageMenu.selectItem(at: 0)
        languageMenu.setAccessibilityLabel(L("언어"))
    }
    @objc func changeLanguage() {
        guard let index = languageMenu.selectedItem?.representedObject as? Int else { return }
        AppLanguage.shared.select(index)
        refreshLanguageMenu()
        if let text = helpText { text.string = fullAppHelp() }
    }
    @objc func showHelp() {
        if helpWindow == nil {
            let panel = NSWindow(contentRect: NSRect(x:0,y:0,width:760,height:640),styleMask:[.titled,.closable,.resizable],backing:.buffered,defer:false)
            panel.title = "사용법 / 앱 정보"; panel.isReleasedWhenClosed = false; panel.appearance = NSAppearance(named: .aqua); panel.backgroundColor = BogoTheme.background; panel.center()
            let text = NSTextView(); text.backgroundColor = BogoTheme.background; text.textColor = BogoTheme.ink; text.isEditable = false; text.isSelectable = true; text.isRichText = false; text.font = .systemFont(ofSize:14); text.textContainerInset = NSSize(width:24,height:24)
            let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.autoresizingMask = [.width,.height]; scroll.documentView = text
            text.autoresizingMask = [.width]; text.isVerticallyResizable = true; text.isHorizontallyResizable = false; text.textContainer?.widthTracksTextView = true
            panel.contentView = scroll; helpText = text; helpWindow = panel
        }
        helpText?.string = fullAppHelp(); helpWindow?.makeKeyAndOrderFront(nil)
    }

    func selected(_ usb: Bool? = nil) -> Phone? {
        let i = deviceMenu.indexOfSelectedItem
        if i >= 0 && i < devices.count && (usb == nil || devices[i].usb == usb) { return devices[i] }
        let matching = devices.filter { usb == nil || $0.usb == usb }
        return matching.count == 1 ? matching[0] : nil
    }

    func showNativeTool(_ index: Int) {
        selectedFeature = max(0, min(5, index)); changeFeature(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    func notice(_ title: String, _ message: String) {
        let parent: NSWindow
        if window.isVisible { parent = window }
        else if let host = agentHost { host.show(); parent = host.window }
        else { showNativeTool(selectedFeature); parent = window }
        let alert = NSAlert()
        alert.messageText = L(title)
        alert.informativeText = L(message)
        alert.addButton(withTitle: L("확인"))
        alert.beginSheetModal(for: parent)
    }

    func task(_ message: String, _ work: @escaping () -> ToolResult, done: @escaping (ToolResult) -> Void) {
        guard !busy else { return }
        busy = true
        status.stringValue = message
        spinner.startAnimation(nil)
        controls.forEach { $0.isEnabled = false }
        DispatchQueue.global(qos: .userInitiated).async {
            let result = work()
            DispatchQueue.main.async {
                self.busy = false
                self.spinner.stopAnimation(nil)
                self.controls.forEach { $0.isEnabled = true }
                done(result)
            }
        }
    }

    func updateDevices(_ result: ToolResult) {
        let previous = selected()?.serial
        devices = phones(result.output); nativePhoneRows = phoneDeviceRows(result.output)
        deviceMenu.removeAllItems()
        if devices.isEmpty {
            deviceMenu.addItem(withTitle: "아직 연결된 갤럭시가 없습니다")
            status.stringValue = result.output.contains("unauthorized") ? "폰에서 이 컴퓨터의 USB 디버깅을 허용하세요." : "USB 케이블을 연결하거나 Wi-Fi 주소로 연결하세요."
        } else {
            deviceMenu.addItems(withTitles: devices.map { $0.label })
            if let previous = previous, let i = devices.firstIndex(where: { $0.serial == previous }) { deviceMenu.selectItem(at: i) }
            status.stringValue = Lf("%@대 연결됨. USB 또는 Wi-Fi 화면 열기를 누르세요.", String(describing: devices.count))
        }
        if result.status != 0 {
            status.stringValue = "연결 도구를 실행하지 못했습니다."
            notice("연결 확인", String(result.output.suffix(1400)))
        }
    }

    @objc func refresh() {
        task("연결된 휴대폰을 찾는 중…", { tool(["devices", "-l"]) }, done: updateDevices)
    }

    @objc func pairWiFi() {
        let address = pairAddress.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        var code = pairCode.stringValue
        guard validEndpoint(address), code.count == 6, code.allSatisfy({ $0.isASCII && $0.isNumber }) else {
            notice("페어링 정보 확인", "폰의 페어링 팝업에 있는 IP 주소:포트와 6자리 숫자를 입력하세요.")
            return
        }
        pairCode.stringValue = ""
        let pairingCode = code
        code.removeAll()
        task("폰과 페어링 중… 팝업을 열어두세요.", { phonePairTool(address, code: pairingCode) }) { result in
            if result.status == 0 && result.output.contains("Successfully paired") {
                self.status.stringValue = "페어링 완료. 폰 기본 화면의 연결용 주소로 연결하거나 새로고침하세요."
            } else {
                self.status.stringValue = "페어링이 완료되지 않았습니다."
                self.notice("페어링 확인", "새 페어링 코드와 포트를 확인하세요.\n\n" + String(result.output.suffix(1200)))
            }
        }
    }

    @objc func connectWiFi() {
        let address = connectAddress.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard validEndpoint(address) else {
            notice("연결 주소 확인", "무선 디버깅 기본 화면의 IP 주소:포트를 입력하세요. 페어링 팝업의 포트와 다를 수 있습니다.")
            return
        }
        task("무선 연결 중…", {
            phoneConnectTool(address)
        }) { result in
            if result.status == 0 && !phones(result.output).isEmpty {
                self.updateDevices(result)
                if let i = self.devices.firstIndex(where: { $0.serial == address }) { self.deviceMenu.selectItem(at: i) }
            } else {
                self.status.stringValue = "무선 연결을 확인하세요."
                self.notice("무선 연결 확인", "같은 네트워크, 현재 연결용 포트, 처음 페어링 여부를 확인하세요.\n\n" + String(result.output.suffix(1200)))
            }
        }
    }

    @objc func openUSB() { startMirror(usb: true) }
    @objc func openWiFi() { startMirror(usb: false) }

    func startMirror(usb: Bool) {
        guard let phone = selected(usb) else {
            notice("휴대폰을 먼저 연결하세요", usb ? "USB 케이블을 연결하고 폰에서 USB 디버깅을 허용한 뒤 새로고침하세요. 여러 대라면 기기를 선택하세요." : "새로고침하거나 Wi-Fi 주소로 연결한 뒤 기기를 선택하세요.")
            return
        }
        let error = launchMirror(phone:phone, keyboard:keyboardMenu.indexOfSelectedItem == 0 ? "uhid" : "sdk", mouse:mouseMenu.indexOfSelectedItem == 0 ? "sdk" : "uhid", audioMode:audioMenu.indexOfSelectedItem, clipboard:true)
        if !error.isEmpty { notice(error == "phoneAlreadyRunning" ? "이미 화면이 열려 있습니다" : "화면을 열지 못했습니다", error == "phoneAlreadyRunning" ? "입력 방식을 바꾸려면 ‘화면 닫기’를 누르고 다시 여세요." : "폰의 연결 상태를 확인하세요.") }
    }
    /// One native scrcpy engine is shared by the old panel and the authenticated web toolbox.
    func launchMirror(phone: Phone, keyboard: String, mouse: String, audioMode: Int, clipboard: Bool, showErrors: Bool = true) -> String {
        guard mirror?.isRunning != true else { return "phoneAlreadyRunning" }
        guard let arguments = phoneMirrorArguments(phone:phone,keyboard:keyboard,mouse:mouse,audioMode:audioMode,clipboard:clipboard) else { return "invalidRequest" }
        guard FileManager.default.isExecutableFile(atPath:scrcpyURL.path), FileManager.default.isExecutableFile(atPath:adbURL.path), FileManager.default.isReadableFile(atPath:serverURL.path) else { return "phoneUnavailable" }
        let p = Process()
        p.executableURL = scrcpyURL
        p.currentDirectoryURL = scrcpyURL.deletingLastPathComponent()
        p.arguments = arguments
        refreshAudioOutput()
        var env = ProcessInfo.processInfo.environment
        env["ADB"] = adbURL.path
        env["SCRCPY_SERVER_PATH"] = serverURL.path
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        let output = Pipe()
        p.standardOutput = output
        p.standardError = output
        mirrorOutput = ""; mirrorErrorCode = ""; mirrorSerial = phone.serial
        mirrorOptions = ["keyboard":keyboard,"mouse":mouse,"audio":["output","aac","off"][audioMode],"clipboard":clipboard]
        output.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            let text = String(data: data, encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                self.mirrorOutput = String((self.mirrorOutput + text).suffix(6000))
            }
        }
        p.terminationHandler = { proc in
            DispatchQueue.main.async {
                let requested = self.stoppedMirrors.remove(ObjectIdentifier(proc)) != nil
                guard self.mirror === proc else { return }
                self.mirror = nil; self.mirrorSerial = ""
                if !self.shuttingDown {
                    self.status.stringValue = "갤럭시 화면이 종료되었습니다. 다시 열 수 있습니다."
                    if proc.terminationStatus != 0 && !requested {
                        self.mirrorErrorCode = "phoneStartFailed"
                        guard showErrors else { return }
                        let log = self.mirrorOutput.lowercased()
                        if audioMode != 2 && log.contains("audio") && (log.contains("error") || log.contains("failed")) {
                            self.notice("휴대폰 소리 연결 확인", L("오디오 연결에 실패했습니다. 호환 오디오 · AAC로 다시 열거나 소리 없이 화면만을 선택하세요.") + "\n\n" + String(self.mirrorOutput.suffix(1400)))
                        } else {
                            self.notice("화면 연결 확인", "폰의 연결 상태를 확인하세요. 키보드만 안 되면 호환 입력 모드를 선택해 다시 여세요.\n\n" + String(self.mirrorOutput.suffix(1400)))
                        }
                    }
                }
            }
        }
        do {
            try p.run()
            mirror = p
            status.stringValue = mouse == "uhid" ? "폰 커서 모드. ⌘ 키를 눌렀다 떼면 Mac으로 돌아옵니다." : "갤럭시 창의 입력칸을 클릭하세요. 창 밖으로 마우스를 자유롭게 옮길 수 있습니다."
            return ""
        } catch {
            output.fileHandleForReading.readabilityHandler = nil; mirrorSerial = ""; mirrorErrorCode = "phoneStartFailed"
            return "phoneStartFailed"
        }
    }
    func phoneNativeStatus(_ result: ToolResult? = nil) -> [String:Any] {
        if let result = result { nativePhoneRows = phoneDeviceRows(result.output) }
        return ["devices":nativePhoneRows,"running":mirror?.isRunning == true,"activeSerial":mirror?.isRunning == true ? mirrorSerial : "", "options":mirrorOptions,"available":(result?.status ?? 0) == 0 && FileManager.default.isExecutableFile(atPath:scrcpyURL.path) && FileManager.default.isExecutableFile(atPath:adbURL.path) && FileManager.default.isReadableFile(atPath:serverURL.path),"errorCode":mirrorErrorCode]
    }

    @objc func stopMirror() {
        if let process = mirror, process.isRunning {
            stoppedMirrors.insert(ObjectIdentifier(process))
            process.terminate()
        }
        status.stringValue = "이 앱에서 연 화면을 닫는 중…"
    }

    @objc func keyboardSettings() {
        guard let phone = selected() else { notice("휴대폰 연결 필요", "기기를 연결한 뒤 다시 눌러주세요."); return }
        task("갤럭시의 실제 키보드 설정을 여는 중…", {
            phoneKeyboardTool(phone.serial)
        }) { result in
            self.status.stringValue = result.status == 0 ? "폰에서 scrcpy 키보드의 한국어/영어 레이아웃을 설정하세요. 화면이 열린 동안 설정할 수 있습니다." : "폰에서 설정 → 일반 → 실제 키보드를 확인하세요."
        }
    }

    @objc func keyboardHelp() {
        notice("갤럭시에 글자가 안 써질 때", "1. Mac에 뜬 갤럭시 창의 입력칸을 클릭하세요. 마우스 이동만으로는 키보드 초점이 옮겨지지 않습니다.\n\n2. Mac 입력 언어를 ABC/영어로 바꾸고 abc123을 입력해 보세요.\n\n3. 직접 입력 모드에서는 ‘갤럭시 키보드 설정’으로 한국어/영어 레이아웃을 설정하세요. 언어 전환은 폰 설정에 표시된 단축키를 사용하세요.\n\n4. 영문도 안 되면 화면을 닫고 ‘호환 입력’으로 바꿔 다시 여세요. 이 모드의 한글은 Mac에서 복사 → 갤럭시 창에서 ⌘V로 붙여넣으세요.")
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if LocalEngine.activeJobs > 0 || (agentHost?.activeJobs ?? 0) > 0 || busy || captureHub.capturing { notice("작업 진행 중", "진행 중인 작업이 끝난 뒤 종료하세요."); return .terminateCancel }
        guard agentHost?.prepareForQuit() ?? true, recorder.prepareForQuit(), documentTools.prepareForQuit(), imageTools.prepareForQuit(), CaptureEditorController.prepareForQuit(roots: captureHub.editors) else { return .terminateCancel }
        return .terminateNow
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { showMain() }
        return true
    }
    func applicationWillTerminate(_ notification: Notification) {
        agentHost?.shutdown()
        shuttingDown = true
        captureHub.shutdown()
        if let monitor = pasteMonitor { NSEvent.removeMonitor(monitor) }
        if let observer = languageObserver { NotificationCenter.default.removeObserver(observer) }
        if let item = statusItem { NSStatusBar.system.removeStatusItem(item) }
        mirror?.terminate()
    }
}

if CommandLine.arguments.contains("--enable-startup") {
    do { try GalaxyStartup.configure(true); print("GalaxyControl: login startup configured"); exit(0) }
    catch { print("GalaxyControl startup: \(error.localizedDescription)"); exit(1) }
}

let app = NSApplication.shared
let controller = GalaxyController()
app.delegate = controller
if CommandLine.arguments.contains("--layout-check") {
    controller.applicationDidFinishLaunching(Notification(name: NSApplication.didFinishLaunchingNotification))
    controller.window.contentView?.layoutSubtreeIfNeeded()
    print("layout: \(controller.window.contentView?.subviews.count ?? 0) roots, \(controller.toolViews.count) tools; \(controller.toolBody.frame)")
    controller.captureHub.shutdown()
    exit(controller.toolBody.frame.width > 800 ? 0 : 1)
}
app.run()
