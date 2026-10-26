import AppKit
import WebKit
import Darwin

/// Health discovery cannot follow a redirect to another origin or service.
private final class GalaxyAgentRedirectGuard: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) { completionHandler(.cancelAuthenticationChallenge, nil) }
}
/// These ports belong to the Local Agent only; other ADMIN services are never stopped.
enum GalaxyAgentEndpoint {
    static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false; configuration.httpCookieStorage = nil; configuration.urlCredentialStorage = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration, delegate: GalaxyAgentRedirectGuard(), delegateQueue: nil)
    }()
    static let ports = [4323, 4324, 4325, 4321]
    static func origin(_ port: Int) -> String { "http://127.0.0.1:\(port)" }
    static func allowsToolsNavigation(_ url: URL, port: Int) -> Bool {
        guard ports.contains(port), url.scheme == "http", url.host == "127.0.0.1", url.port == port else { return false }
        // Foundation removes a directory URL's trailing slash from URL.path.
        // Accept the tools directory itself as well as descendants, never sibling paths.
        return url.path == "/tools" || url.path.hasPrefix("/tools/")
    }
    static func validHealth(_ json: [String: Any], expectedDevice: String? = nil) -> Bool {
        guard json["version"] as? String == "4.6.23",
              let connected = json["connected"] as? NSNumber, CFGetTypeID(connected) == CFBooleanGetTypeID(), connected.boolValue,
              let device = json["deviceId"] as? String, UUID(uuidString: device) != nil,
              json["os"] as? String == "macOS",
              let ready = json["nativeReady"] as? NSNumber, CFGetTypeID(ready) == CFBooleanGetTypeID(),
              let operations = json["operations"] as? [String],
              operations.contains("image_process"), operations.contains("code_generate"),
              operations.allSatisfy({ !$0.isEmpty && $0.count <= 80 && $0.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_") }) }) else { return false }
        if let expected = expectedDevice, device != expected { return false }
        return true
    }
    static func available(_ port: Int) -> Bool {
        let handle = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard handle >= 0 else { return false }; defer { Darwin.close(handle) }
        var address = sockaddr_in(); address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET); address.sin_port = in_port_t(port).bigEndian
        address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        return withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(handle, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
    }
    static func select(candidates: [Int], expectedDevice: String?, available: (Int) -> Bool, health: (Int) -> [String: Any]?) -> (port: Int, reuse: Bool)? {
        var freePorts = [Int]()
        for port in candidates {
            if available(port) { freePorts.append(port); continue }
            if let expected = expectedDevice, let response = health(port), validHealth(response, expectedDevice: expected) { return (port, true) }
        }
        return freePorts.first.map { ($0, false) }
    }
    /// Called on a worker queue, never the AppKit main thread.
    static func health(_ port: Int) -> [String: Any]? {
        var request = URLRequest(url: URL(string: origin(port) + "/health")!)
        request.timeoutInterval = 0.8; request.setValue(origin(port), forHTTPHeaderField: "Origin")
        let semaphore = DispatchSemaphore(value: 0), lock = NSLock(); var result: [String: Any]?
        let task = GalaxyAgentEndpoint.session.dataTask(with: request) { data, response, _ in
            if let data = data, data.count <= 131_072, (response as? HTTPURLResponse)?.statusCode == 200, let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] { lock.lock(); result = value; lock.unlock() }
            semaphore.signal()
        }
        task.resume(); _ = semaphore.wait(timeout: .now() + 1); task.cancel()
        lock.lock(); defer { lock.unlock() }; return result
    }
    static func selfCheck() -> Bool {
        let navigationFixtures: [(String, Int, Bool)] = [
            ("http://127.0.0.1:4323/tools/",4323,true),
            ("http://127.0.0.1:4323/tools/?language=ko",4323,true),
            ("http://127.0.0.1:4323/tools",4323,true),
            ("http://127.0.0.1:4324/tools/assets/example.js",4324,true),
            ("http://127.0.0.1:4323/tools-evil/",4323,false),
            ("http://127.0.0.1:4323/tools2/",4323,false),
            ("http://127.0.0.1:4323/private/",4323,false),
            ("http://127.0.0.1:4324/tools/",4323,false),
            ("http://localhost:4323/tools/",4323,false),
            ("http://example.com:4323/tools/",4323,false),
            ("https://127.0.0.1:4323/tools/",4323,false),
            ("file:///tools/",4323,false),
            ("http://127.0.0.1:9999/tools/",9999,false)
        ]
        guard navigationFixtures.allSatisfy({ value in
            guard let url = URL(string:value.0) else { return false }
            return allowsToolsNavigation(url,port:value.1) == value.2
        }) else { return false }
        let device = "63f32dd5-cd38-4473-9dbe-3bde1b8857b3"
        let fixture: [String: Any] = ["version": "4.6.23", "connected": true, "deviceId": device, "os": "macOS", "nativeReady": true, "operations": ["image_process", "code_generate", "capture"]]
        let unrelated: [String: Any] = ["busy": false, "autoPolling": true, "storyRoute": "ADMIN"]
        guard validHealth(fixture), !validHealth(unrelated), !validHealth(fixture, expectedDevice: UUID().uuidString.lowercased()),
              select(candidates: ports, expectedDevice: device, available: { $0 == 4324 }, health: { _ in unrelated })?.port == 4324,
              select(candidates: ports, expectedDevice: device, available: { _ in false }, health: { $0 == 4321 ? fixture : unrelated })?.reuse == true,
              select(candidates: ports, expectedDevice: nil, available: { _ in false }, health: { _ in fixture }) == nil,
              select(candidates: ports, expectedDevice: device, available: { _ in false }, health: { _ in unrelated }) == nil else { return false }
        for key in ["deviceId", "os", "nativeReady", "operations"] { var missing = fixture; missing.removeValue(forKey: key); if validHealth(missing) { return false } }
        var wrong = fixture; wrong["nativeReady"] = 1; if validHealth(wrong) { return false }; wrong = fixture; wrong["connected"] = 1; if validHealth(wrong) { return false }
        // A real disposable listening socket must be skipped without being closed by the selector.
        let handle = Darwin.socket(AF_INET, SOCK_STREAM, 0); guard handle >= 0 else { return false }; defer { Darwin.close(handle) }
        var address = sockaddr_in(); address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size); address.sin_family = sa_family_t(AF_INET); address.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))
        let bound = withUnsafeMutablePointer(to: &address) { pointer in pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(handle, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 } }
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &address) { pointer in pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(handle, $0, &length) == 0 } }
        guard bound, named, Darwin.listen(handle, 1) == 0, !available(Int(in_port_t(bigEndian: address.sin_port))),
              select(candidates: ports, expectedDevice: device, available: { $0 == 4323 }, health: { $0 == 4321 ? fixture : unrelated })?.port == 4321 else { return false }
        return origin(4324) == "http://127.0.0.1:4324" && ports == [4323, 4324, 4325, 4321]
    }
}

/// One desktop window backed by the app's private local processing engine.
final class GalaxyAgentHost: NSObject, WKNavigationDelegate, WKScriptMessageHandler, NSWindowDelegate {
    weak var owner: GalaxyController?
    let window: NSWindow
    private let web: WKWebView
    private let status = NSTextField(labelWithString: L("로컬 도구를 준비하는 중…"))
    private var process: Process?
    private var logPipe: Pipe?
    private var pendingLog = Data()
    private let logQueue = DispatchQueue(label: "GalaxyControl.agent-log")
    private var healthTimer: Timer?
    private var attempts = 0
    private var loaded = false
    private var quitting = false
    private var polling = false
    private var selecting = false
    private var activePort = GalaxyAgentEndpoint.ports[0]
    private var failedPorts = Set<Int>()
    private var healthFailures = 0
    private var healthGeneration = 0
    private var recoveryAttempts = 0
    private var navigationFailed = false
    private var uiReady = false
    private var pendingNavigation: String?
    private var pendingShortcut: String?
    private var desktopToken = ""
    private var routingShortcut = false
    private var capturePreviousVisibility: Bool?
    private var capturePreviousLevel: NSWindow.Level?
    private var capturePreviousFrame: NSRect?
    private var lastShortcutAt = Date.distantPast
    private var preparingCapture = false
    private var toolbar: NSStackView!
    private var toolbarHeight: NSLayoutConstraint!
    private(set) var activeJobs = 0
    private var lastHealthPoll = Date.distantPast
    private let stateDirectory: URL
    var bridge: GalaxyNativeBridge?

    init(owner: GalaxyController, startWorker: Bool = true) {
        self.owner = owner
        stateDirectory = GalaxyNativeBridge.defaultStateDirectory
        let configuration = WKWebViewConfiguration()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        web = WKWebView(frame: .zero, configuration: configuration)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1150, height: 820), styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Bogo Tools"; window.appearance = NSAppearance(named: .aqua); window.backgroundColor = BogoTheme.header; window.minSize = NSSize(width: 680, height: 560); window.isReleasedWhenClosed = false; window.center()
        window.delegate = self
        web.navigationDelegate = self
        web.configuration.userContentController.add(self, name: "galaxycontrol")
        let retry = NSButton(image: NSImage(systemSymbolName: "arrow.clockwise", accessibilityDescription: L("다시 연결"))!, target: self, action: #selector(retryAgent))
        retry.bezelStyle = .inline; retry.contentTintColor = BogoTheme.accent; retry.toolTip = L("다시 연결"); retry.setAccessibilityLabel(L("다시 연결"))
        toolbar = NSStackView(views: [status, retry]); toolbar.spacing = 8; toolbar.orientation = .horizontal; toolbar.alignment = .centerY
        status.font = NSFont.systemFont(ofSize: 11); status.textColor = BogoTheme.ink
        status.setContentHuggingPriority(.defaultLow, for: .horizontal)
        status.setContentCompressionResistancePriority(.defaultLow, for: .horizontal); status.lineBreakMode = .byTruncatingTail; status.maximumNumberOfLines = 1
        let root = NSView(); root.wantsLayer = true; root.layer?.backgroundColor = BogoTheme.header.cgColor; window.contentView = root
        for view: NSView in [toolbar!, web] { view.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(view) }
        toolbarHeight = toolbar.heightAnchor.constraint(equalToConstant: 22)
        NSLayoutConstraint.activate([toolbar.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 10), toolbar.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -10), toolbar.topAnchor.constraint(equalTo: root.topAnchor), toolbarHeight, retry.widthAnchor.constraint(equalToConstant: 26), web.leadingAnchor.constraint(equalTo: root.leadingAnchor), web.trailingAnchor.constraint(equalTo: root.trailingAnchor), web.topAnchor.constraint(equalTo: toolbar.bottomAnchor), web.bottomAnchor.constraint(equalTo: root.bottomAnchor)])
        if startWorker {
            do { bridge = try GalaxyNativeBridge(owner: owner, stateDirectory: stateDirectory) }
            catch { status.stringValue = L("프로그램 폴더를 준비하지 못했습니다. 다시 실행하세요.") }
            startAgent()
        }
    }
    static func layoutSelfCheck() -> Bool {
        _ = NSApplication.shared
        let owner = GalaxyController()
        let host = GalaxyAgentHost(owner: owner, startWorker: false)
        // No server, permission request or visible window is created during this check.
        defer { host.shutdown(); host.window.close() }
        for size in [NSSize(width:900,height:640),NSSize(width:1150,height:820)] {
            host.window.setContentSize(size); host.window.contentView?.layoutSubtreeIfNeeded()
            guard host.web.frame.width >= size.width - 1, host.web.frame.height >= size.height - 52,
                  host.web.frame.maxX <= size.width + 1, host.web.frame.maxY <= size.height + 1 else { return false }
        }
        return true
    }
    func show() { if owner?.captureHub.capturing == true { bridge?.cancelActiveCapture() }; window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        window.orderOut(nil)
        if capturePreviousVisibility != nil { windowWillClose(Notification(name:NSWindow.willCloseNotification,object:sender)) }
        return false
    }
    func aiSelected() {
        if capturePreviousLevel == nil { capturePreviousLevel = window.level }
        show();window.makeFirstResponder(web)
        dispatch("galaxycontrol:ai-selected",detail:["stage":"uploading"])
    }
    func windowWillClose(_ notification: Notification) {
        guard capturePreviousVisibility != nil else { return }
        resetCaptureWindow()
        if pendingShortcut == "areaCapture" || pendingShortcut == "fullCapture" || pendingShortcut == "webCapture" { pendingShortcut = nil }
        dispatch("galaxycontrol:navigate",detail:["category":"capture"])
    }
    private func resetCaptureWindow() {
        if let level = capturePreviousLevel { window.level = level }
        if let frame = capturePreviousFrame { window.setFrame(frame,display:false) }
        capturePreviousFrame = nil;window.minSize = NSSize(width:680,height:560)
        capturePreviousLevel = nil; capturePreviousVisibility = nil
        window.title = "Bogo Tools"
    }
    private func dispatch(_ name: String, detail: [String:Any]) {
        guard uiReady, let data = try? JSONSerialization.data(withJSONObject: ["name":name,"detail":detail], options:.sortedKeys), let json = String(data:data,encoding:.utf8) else { return }
        web.evaluateJavaScript("(()=>{const e=\(json);window.dispatchEvent(new CustomEvent(e.name,{detail:e.detail}));})()", completionHandler:nil)
    }
    func navigate(_ category: String) {
        guard ["home","image","pdf","signature","capture","record","web","codes","files","organize","media","phone","settings","ai"].contains(category) else { return }
        show()
        if uiReady { dispatch("galaxycontrol:navigate",detail:["category":category]) } else { pendingNavigation = category }
    }
    @discardableResult func shortcut(_ name: String) -> Bool {
        guard ["areaCapture","fullCapture","webCapture","recordToggle","toggleRecording","recordArea","aiTranslate"].contains(name) else { return false }
        guard Date().timeIntervalSince(lastShortcutAt) >= 0.4 else { return true }
        lastShortcutAt = Date()
        guard !preparingCapture, !routingShortcut, owner?.captureHub.capturing != true else { return true }
        guard !desktopToken.isEmpty else { show(); return true }
        routingShortcut = true
        var request = URLRequest(url:URL(string:GalaxyAgentEndpoint.origin(activePort)+"/desktop/dispatch")!)
        request.httpMethod = "POST"; request.timeoutInterval = 8
        request.setValue(GalaxyAgentEndpoint.origin(activePort),forHTTPHeaderField:"Origin")
        request.setValue(desktopToken,forHTTPHeaderField:"X-Local-Agent-Token")
        request.setValue("application/json",forHTTPHeaderField:"Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject:["action":name])
        GalaxyAgentEndpoint.session.dataTask(with:request) { [weak self] data,response,_ in
            let payload = data.flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] }
            let destination = (response as? HTTPURLResponse)?.statusCode == 200 ? payload?["destination"] as? String : nil
            DispatchQueue.main.async {
                guard let self = self else { return }; self.routingShortcut = false
                if destination == "desktop" { self.localShortcut(name) }
                else if destination != "web" { self.show() }
            }
        }.resume()
        return true
    }
    private func localShortcut(_ name:String) {
        let captures = ["areaCapture", "fullCapture", "aiTranslate"].contains(name)
        let deliver = { [weak self] in
            guard let self = self else { return }
            self.preparingCapture = false
            if captures && self.capturePreviousVisibility == nil { self.capturePreviousVisibility = self.window.isVisible }
            // evaluateJavaScript delivers to a hidden WKWebView; showing it first
            // changes the very screen the user asked us to capture.
            if captures { self.window.orderOut(nil) }
            if self.uiReady { self.dispatch("galaxycontrol:shortcut",detail:["name":name]) }
            else { self.pendingShortcut = name }
        }
        if captures && NSApp.isActive && window.isVisible && uiReady {
            preparingCapture = true
            GalaxyCaptureBackdrop.prepare { success in
                if success { deliver() }
                else { self.preparingCapture = false; NSSound.beep() }
            }
        } else { GalaxyCaptureBackdrop.clear(); deliver() }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        let origin = message.frameInfo.securityOrigin
        let webMatch = message.webView === web
        let mainFrame = message.frameInfo.isMainFrame
        let originMatch = origin.protocol == "http" && origin.host == "127.0.0.1" && origin.port == activePort
        let urlMatch = message.frameInfo.request.url.map { GalaxyAgentEndpoint.allowsToolsNavigation($0,port:activePort) } ?? false
        guard let body = message.body as? [String:Any], let action = body["action"] as? String else { return }
        if body.count == 1, ["desktopReady","captureStarted","captureReady","captureClosed","captureCancelled"].contains(action) {
            bridge?.recordHostDiagnostic(["action":action,"trusted":webMatch && mainFrame && originMatch && urlMatch,
                                          "webMatch":webMatch,"mainFrame":mainFrame,"originMatch":originMatch,"urlMatch":urlMatch])
        }
        guard webMatch, mainFrame, originMatch, urlMatch else { return }
        if action == "copyText" {
            guard body.count == 3, let text = body["text"] as? String, text.count <= 12000, text.utf8.count <= 48000,
                  let requestId = body["requestId"] as? String, UUID(uuidString:requestId) != nil else { return }
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            let copied = pasteboard.writeObjects([text as NSString])
            dispatch("galaxycontrol:clipboard-result",detail:["requestId":requestId,"copied":copied])
            return
        }
        if action == "aiPin", body.count == 2, let enabled = body["enabled"] as? NSNumber, CFGetTypeID(enabled) == CFBooleanGetTypeID() {
            window.level = enabled.boolValue ? .floating : .normal;return
        }
        if action == "captureFit", body.count == 4, capturePreviousVisibility != nil,
           let width = body["width"] as? Double, let height = body["height"] as? Double, let chrome = body["chromeHeight"] as? Double,
           width.isFinite, height.isFinite, chrome.isFinite, width > 0, height > 0, width <= 64000, height <= 64000, width*height <= 64000000, chrome >= 0, chrome <= 600,
           let screen = window.screen ?? NSScreen.main {
            if capturePreviousFrame == nil { capturePreviousFrame = window.frame }
            let area = screen.visibleFrame.insetBy(dx:16,dy:16)
            let scale = min(1,min((area.width-24)/width,(area.height-chrome-30)/height))
            let size = NSSize(width:min(area.width,max(420,width*scale+24)),height:min(area.height,max(260,height*scale+chrome+30)))
            window.minSize = NSSize(width:420,height:260)
            window.setFrame(NSRect(x:area.midX-size.width/2,y:area.midY-size.height/2,width:size.width,height:size.height),display:true);return
        }
        guard body.count == 1 else { return }
        if ["desktopReady","captureStarted","captureReady","captureClosed","captureCancelled"].contains(action) { NSLog("[GalaxyHost] lifecycle=%@",action) }
        switch action {
        case "driveConnected":
            show(); window.makeFirstResponder(web)
        case "desktopReady":
            uiReady = true
            if let category = pendingNavigation { pendingNavigation = nil; dispatch("galaxycontrol:navigate",detail:["category":category]) }
            if let shortcut = pendingShortcut { pendingShortcut = nil; dispatch("galaxycontrol:shortcut",detail:["name":shortcut]) }
        case "captureStarted":
            if capturePreviousVisibility == nil { capturePreviousVisibility = window.isVisible }
            window.orderOut(nil)
        case "captureReady":
            if capturePreviousLevel == nil { capturePreviousLevel = window.level }
            window.level = .floating; window.title = L("캡처 편집")
            show(); window.makeFirstResponder(web)
        case "captureClosed":
            window.orderOut(nil); resetCaptureWindow()
        case "captureCancelled":
            let wasVisible = capturePreviousVisibility
            resetCaptureWindow()
            if wasVisible == true { show() } else if wasVisible == false { window.orderOut(nil) }
        default: break
        }
    }
    private func installDesktopSession() -> Bool {
        web.configuration.userContentController.removeAllUserScripts()
        let url = stateDirectory.appendingPathComponent("desktop-session.json")
        let fd = Darwin.open(url.path,O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { return false }
        defer { Darwin.close(fd) }
        var info = stat()
        guard fstat(fd,&info) == 0, info.st_uid == getuid(), info.st_mode & S_IFMT == S_IFREG,
              info.st_mode & 0o077 == 0, info.st_nlink == 1, info.st_size > 0, info.st_size <= 4096 else { return false }
        var bytes = [UInt8](repeating:0,count:Int(info.st_size))
        let length = bytes.count
        let count = bytes.withUnsafeMutableBytes { Darwin.read(fd,$0.baseAddress,length) }
        guard count == Int(info.st_size), let session = (try? JSONSerialization.jsonObject(with:Data(bytes))) as? [String:Any],
              Set(session.keys) == Set(["token","deviceId","origin","ownerId","clientName","version"]),
              session["version"] as? String == "4.6.23",
              session["origin"] as? String == GalaxyAgentEndpoint.origin(activePort), session["ownerId"] as? String == "desktop",
              session["clientName"] as? String == "GalaxyControl", let token = session["token"] as? String,
              (32...256).contains(token.utf8.count), token.utf8.allSatisfy({ (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }),
              let device = session["deviceId"] as? String, UUID(uuidString:device) != nil, device == expectedDevice,
              let safe = try? JSONSerialization.data(withJSONObject:session,options:.sortedKeys), let json = String(data:safe,encoding:.utf8) else { return false }
        desktopToken = token
        let script = "(()=>{const s=\(json);if(window.top===window&&location.origin===s.origin&&/^\\/tools(?:\\/|$)/.test(location.pathname)){Object.defineProperty(globalThis,'__galaxyDesktopSession',{value:Object.freeze(s),writable:false,configurable:false});}})()"
        web.configuration.userContentController.addUserScript(WKUserScript(source:script,injectionTime:.atDocumentStart,forMainFrameOnly:true))
        return true
    }
    @objc private func retryAgent() {
        navigationFailed = false
        uiReady = false
        failedPorts.removeAll(); recoveryAttempts = 0; loaded = false; attempts = 0; lastHealthPoll = .distantPast
        if process?.isRunning != true { startAgent() } else { pollHealth() }
    }
    private var expectedDevice: String? {
        let url = stateDirectory.appendingPathComponent("device.json")
        guard (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) == nil,
              let data = try? Data(contentsOf: url), data.count <= 4096,
              let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let id = value["deviceId"] as? String, UUID(uuidString: id) != nil else { return nil }
        return id
    }
    private func resource(_ suffix: String) -> URL { Bundle.main.resourceURL!.appendingPathComponent(suffix) }
    private func startAgent() {
        guard !quitting, !selecting, process?.isRunning != true else { return }
        navigationFailed = false
        selecting = true; healthGeneration += 1; loaded = false; uiReady = false; polling = false; attempts = 0; healthFailures = 0
        healthTimer?.invalidate(); healthTimer = nil
        let candidates = GalaxyAgentEndpoint.ports.filter { !failedPorts.contains($0) }, device = expectedDevice
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let selected = GalaxyAgentEndpoint.select(candidates: candidates, expectedDevice: device, available: GalaxyAgentEndpoint.available, health: GalaxyAgentEndpoint.health)
            DispatchQueue.main.async {
                guard let self = self else { return }; self.selecting = false
                guard !self.quitting else { return }
                guard let selected = selected else { self.status.stringValue = L("로컬 처리를 시작하지 못했습니다. 다시 연결하세요."); return }
                self.activePort = selected.port
                if selected.reuse { self.beginHealthPolling() } else { self.launchAgent(port: selected.port) }
            }
        }
    }
    private func beginHealthPolling() {
        healthTimer?.invalidate(); healthTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in self?.pollHealth() }
        pollHealth()
    }
    private func launchAgent(port: Int) {
        guard !quitting, process?.isRunning != true else { return }
        let pythonCandidates = [resource("engine/runtimes/\(machine)/python/bin/python3"), resource("tools/python/\(machine)/bin/python3")]
        let scriptCandidates = [resource("engine/agent/server.py"), resource("tools/engine/agent/server.py")]
        guard let python = pythonCandidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }),
              let script = scriptCandidates.first(where: { FileManager.default.fileExists(atPath: $0.path) }) else {
            status.stringValue = L("처리 구성요소가 없습니다. 프로그램 폴더 전체를 다시 설치하세요."); return
        }
        let ui = resource("tools-ui")
        guard ["index.html","local-tools-standalone.html"].contains(where: { FileManager.default.isReadableFile(atPath:ui.appendingPathComponent($0).path) }) else {
            status.stringValue = L("처리 구성요소가 없습니다. 프로그램 폴더 전체를 다시 설치하세요."); return
        }
        let task = Process(); task.executableURL = python
        task.arguments = ["-I", "-B", script.path, "--state-dir", stateDirectory.path, "--ui-dir", ui.path, "--port", String(port), "--native-pid", String(ProcessInfo.processInfo.processIdentifier)]
        task.standardInput = FileHandle.nullDevice
        let pipe = Pipe(); task.standardOutput = pipe; task.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let bytes = handle.availableData
            guard !bytes.isEmpty else { handle.readabilityHandler = nil; return }
            self?.logQueue.async { [weak self] in self?.appendLog(bytes) }
        }
        task.terminationHandler = { [weak self] ended in DispatchQueue.main.async {
            guard let self = self, !self.quitting, self.process === ended else { return }
            self.process = nil; self.logPipe?.fileHandleForReading.readabilityHandler = nil; self.logPipe = nil
            if !self.loaded { self.failedPorts.insert(port) } else { self.failedPorts.removeAll() }
            self.loaded = false; self.activeJobs = 0; self.recoveryAttempts += 1
            self.status.stringValue = L("처리가 중단되었습니다. 다시 연결하세요.")
            if self.recoveryAttempts <= GalaxyAgentEndpoint.ports.count { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in self?.startAgent() } }
        } }
        do {
            try task.run(); process = task; logPipe = pipe
            beginHealthPolling()
        } catch { status.stringValue = L("로컬 처리를 시작하지 못했습니다. 다시 연결하세요.") }
    }
    private func appendLog(_ bytes: Data) {
        // Bounded private diagnostic log; never send this file to a browser or remote service.
        pendingLog.append(bytes); if pendingLog.count > 131_072 { pendingLog.removeFirst(pendingLog.count - 131_072) }
        let url = stateDirectory.appendingPathComponent("native-agent.log")
        guard (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) == nil else { return }
        do { try pendingLog.write(to: url, options: .atomic); try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path) } catch {}
    }
    private func pollHealth() {
        guard !quitting, !selecting, !polling, !loaded || Date().timeIntervalSince(lastHealthPoll) >= 2 else { return }
        lastHealthPoll = Date(); polling = true; attempts += 1
        let port = activePort, device = expectedDevice, generation = healthGeneration
        var request = URLRequest(url: URL(string: GalaxyAgentEndpoint.origin(port) + "/health")!)
        request.timeoutInterval = 1; request.setValue(GalaxyAgentEndpoint.origin(port), forHTTPHeaderField: "Origin")
        GalaxyAgentEndpoint.session.dataTask(with: request) { [weak self] data, response, _ in
            let json = data.flatMap { $0.count <= 131_072 ? (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any] : nil }
            let valid = (response as? HTTPURLResponse)?.statusCode == 200 && json.map { GalaxyAgentEndpoint.validHealth($0, expectedDevice: device) } == true
            DispatchQueue.main.async {
                guard let self = self, !self.quitting, self.activePort == port, self.healthGeneration == generation else { return }
                self.polling = false
                guard valid, let json = json else {
                    self.healthFailures += 1
                    // A previously attached worker may exit. Find another free port without touching its former occupant.
                    if self.loaded && self.healthFailures >= 3 && self.process?.isRunning != true {
                        self.loaded = false; self.activeJobs = 0; self.failedPorts.insert(port); self.startAgent()
                    }
                    return
                }
                self.healthFailures = 0
                self.activeJobs = max(0, json["activeJobs"] as? Int ?? 0)
                if !self.navigationFailed { self.status.stringValue = L("이 Mac에서 안전하게 처리합니다.") }
                if !self.loaded {
                    guard self.installDesktopSession() else { self.status.stringValue = L("프로그램을 준비하는 중입니다. 잠시 기다려 주세요."); return }
                    self.loaded = true
                    self.uiReady = false
                    self.web.load(URLRequest(url: URL(string: GalaxyAgentEndpoint.origin(port) + "/tools/?language=\(AppLanguage.shared.code)")!))
                }
            }
        }.resume()
        if attempts > 30 && !loaded { status.stringValue = L("프로그램을 준비하는 중입니다. 잠시 기다려 주세요.") }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if GalaxyAgentEndpoint.allowsToolsNavigation(url,port:activePort) { decisionHandler(.allow); return }
        decisionHandler(.cancel)
        if navigationAction.navigationType == .linkActivated, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
    }
    private func navigationFailure(_ event: String, error: Error? = nil) {
        navigationFailed = true
        uiReady = false; toolbar.isHidden = false; toolbarHeight.constant = 22
        status.stringValue = L("화면을 열지 못했습니다. 다시 연결하세요.")
        // Only fixed event names and error domain/code; no URLs, page data or secrets.
        var fields: [String:Any] = ["event":event]
        if let error = error as NSError? { fields["domain"] = [NSURLErrorDomain,WKErrorDomain,NSCocoaErrorDomain].contains(error.domain) ? error.domain : "other";fields["code"] = error.code }
        if let json = try? JSONSerialization.data(withJSONObject:fields,options:.sortedKeys),json.count <= 1024 {
            var bytes = Data("[WK] ".utf8);bytes.append(json);bytes.append(0x0a)
            logQueue.async { [weak self] in self?.appendLog(bytes) }
        }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        navigationFailed = false; toolbar.isHidden = true; toolbarHeight.constant = 0
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { navigationFailure("provisional-failed",error:error) }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { navigationFailure("committed-failed",error:error) }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { navigationFailure("content-process-terminated") }
    func prepareForQuit() -> Bool {
        guard loaded || process?.isRunning == true else { return true }
        let semaphore = DispatchSemaphore(value: 0), lock = NSLock()
        var jobs = activeJobs
        let device = expectedDevice
        var request = URLRequest(url: URL(string: GalaxyAgentEndpoint.origin(activePort) + "/health")!); request.timeoutInterval = 1; request.setValue(GalaxyAgentEndpoint.origin(activePort), forHTTPHeaderField: "Origin")
        let task = GalaxyAgentEndpoint.session.dataTask(with: request) { data, _, _ in
            if let data = data, let json = (try? JSONSerialization.jsonObject(with: data)) as? [String:Any], GalaxyAgentEndpoint.validHealth(json, expectedDevice: device) { lock.lock(); jobs = max(0, json["activeJobs"] as? Int ?? 0); lock.unlock() }
            semaphore.signal()
        }
        task.resume(); _ = semaphore.wait(timeout: .now() + 1.2); task.cancel()
        lock.lock(); let count = jobs; lock.unlock()
        if count > 0 { owner?.notice("작업 진행 중", "진행 중인 작업이 끝난 뒤 종료하세요."); return false }
        return true
    }
    func shutdown() {
        quitting = true; healthTimer?.invalidate(); healthTimer = nil; bridge?.shutdown()
        web.configuration.userContentController.removeScriptMessageHandler(forName:"galaxycontrol")
        web.configuration.userContentController.removeAllUserScripts()
        logPipe?.fileHandleForReading.readabilityHandler = nil
        if process?.isRunning == true { process?.terminate() }
    }
}
