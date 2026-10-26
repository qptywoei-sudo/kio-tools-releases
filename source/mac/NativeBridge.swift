import AppKit
import Carbon
import CoreGraphics
import ApplicationServices
import Darwin

private let bridgeOperations: Set<String> = ["pair.approve", "folder.choose", "files.choose", "file.open", "file.reveal", "capture.start", "capture.cancel", "editor.open", "clipboard.copy", "record.start", "record.pause", "record.resume", "record.stop", "permissions.get", "permissions.open", "settings.apply", "phone.open", "phone.status", "phone.pair", "phone.connect", "phone.start", "phone.stop", "phone.keyboard", "native.tools", "app.quit"]
private let bridgeShortcutKeys = ["areaCapture", "fullCapture", "webCapture", "recordToggle", "recordArea", "aiTranslate"]
private struct BridgeRequest {
    let id: String, operation: String
    let args: [String: Any]
    let expires: Double
}
private struct NativeShortcut: Equatable {
    let key: UInt32, modifiers: UInt32, text: String
    static let codes: [String: UInt32] = ["A":0,"B":11,"C":8,"D":2,"E":14,"F":3,"G":5,"H":4,"I":34,"J":38,"K":40,"L":37,"M":46,"N":45,"O":31,"P":35,"Q":12,"R":15,"S":1,"T":17,"U":32,"V":9,"W":13,"X":7,"Y":16,"Z":6,"F1":122,"F2":120,"F3":99,"F4":118,"F5":96,"F6":97,"F7":98,"F8":100,"F9":101,"F10":109,"F11":103,"F12":111,"F13":105,"F14":107,"F15":113,"F16":106,"F17":64,"F18":79,"F19":80,"F20":90,"0":29,"1":18,"2":19,"3":20,"4":21,"5":23,"6":22,"7":26,"8":28,"9":25,"Space":49]
    static func parse(_ text: String) -> NativeShortcut? {
        let parts = text.split(separator: "+", omittingEmptySubsequences: false).map(String.init)
        guard parts.count >= 2, let code = codes[parts.last ?? ""], parts.count <= 5 else { return nil }
        let names = ["Command", "Control", "Option", "Shift"]
        let bits = [UInt32(cmdKey), UInt32(controlKey), UInt32(optionKey), UInt32(shiftKey)]
        var modifiers: UInt32 = 0, seen = Set<String>()
        for part in parts.dropLast() { guard let index = names.firstIndex(of: part), seen.insert(part).inserted else { return nil }; modifiers |= bits[index] }
        if (code == 8 || code == 9) && (modifiers == UInt32(cmdKey) || modifiers == UInt32(controlKey)) { return nil }
        let normalized = names.enumerated().compactMap { index, name in modifiers & bits[index] == 0 ? nil : name } + [parts.last!]
        return NativeShortcut(key: code, modifiers: modifiers, text: normalized.joined(separator: "+"))
    }
    static func text(key: UInt32, modifiers: UInt32) -> String? {
        guard let letter = codes.first(where: { $0.value == key })?.key else { return nil }
        let names = ["Command", "Control", "Option", "Shift"], bits = [UInt32(cmdKey),UInt32(controlKey),UInt32(optionKey),UInt32(shiftKey)]
        return (names.enumerated().compactMap { i,n in modifiers & bits[i] == 0 ? nil : n } + [letter]).joined(separator: "+")
    }
}

/// Owns only this app's six Carbon shortcuts. Any failed replacement restores the previous set.
private final class NativeShortcutSet {
    private var handles: [String: EventHotKeyRef] = [:]
    private var handler: EventHandlerRef?
    private(set) var values: [String: String] = [:]
    var action: ((String) -> Void)?
    init() throws {
        var event = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let code = InstallEventHandler(GetApplicationEventTarget(), { _, event, pointer in
            guard let pointer = pointer, let event = event else { return OSStatus(eventNotHandledErr) }
            var identifier = EventHotKeyID()
            guard GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &identifier) == noErr,
                  identifier.signature == 0x41444D4E, (1...UInt32(bridgeShortcutKeys.count)).contains(identifier.id) else { return OSStatus(eventNotHandledErr) }
            let object = Unmanaged<NativeShortcutSet>.fromOpaque(pointer).takeUnretainedValue()
            DispatchQueue.main.async { object.action?(bridgeShortcutKeys[Int(identifier.id) - 1]) }
            return noErr
        }, 1, &event, Unmanaged.passUnretained(self).toOpaque(), &handler)
        guard code == noErr else { throw NSError(domain: "GalaxyControl.Bridge", code: Int(code)) }
    }
    static func validated(_ input: [String: String]) -> [String: String]? {
        guard Set(input.keys).isSubset(of: Set(bridgeShortcutKeys)) else { return nil }
        var result: [String: String] = [:], combinations = Set<String>()
        for name in bridgeShortcutKeys {
            let text = input[name] ?? ""
            if text.isEmpty { result[name] = ""; continue }
            guard let shortcut = NativeShortcut.parse(text), combinations.insert(shortcut.text).inserted else { return nil }
            result[name] = shortcut.text
        }
        return result
    }
    @discardableResult func apply(_ proposal: [String: String]) -> Bool {
        guard handler != nil, let proposal = Self.validated(proposal) else { return false }
        if proposal == values && proposal.allSatisfy({ $0.value.isEmpty || handles[$0.key] != nil }) { return true }
        let old = values
        unregister()
        if register(proposal) { values = proposal; return true }
        unregister(); recover(old)
        return false
    }
    // A conflicting binding must not disable the remaining shortcuts on launch.
    func recover(_ proposal: [String: String]) {
        guard let proposal = Self.validated(proposal) else { return }
        values = proposal
        for (index, name) in bridgeShortcutKeys.enumerated() where handles[name] == nil {
            guard let text = proposal[name], !text.isEmpty, let shortcut = NativeShortcut.parse(text) else { continue }
            var reference: EventHotKeyRef?
            if RegisterEventHotKey(shortcut.key, shortcut.modifiers, EventHotKeyID(signature: 0x41444D4E, id: UInt32(index + 1)), GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &reference) == noErr,
               let reference = reference { handles[name] = reference }
        }
    }
    private func register(_ proposal: [String: String]) -> Bool {
        for (index, name) in bridgeShortcutKeys.enumerated() {
            guard let text = proposal[name], !text.isEmpty, let shortcut = NativeShortcut.parse(text) else { continue }
            var reference: EventHotKeyRef?
            let result = RegisterEventHotKey(shortcut.key, shortcut.modifiers, EventHotKeyID(signature: 0x41444D4E, id: UInt32(index + 1)), GetApplicationEventTarget(), OptionBits(kEventHotKeyExclusive), &reference)
            guard result == noErr, let reference = reference else { return false }; handles[name] = reference
        }
        return true
    }
    private func unregister() { handles.values.forEach { UnregisterEventHotKey($0) }; handles.removeAll() }
    func shutdown() { unregister(); if let handler = handler { RemoveEventHandler(handler) }; handler = nil }
    deinit { shutdown() }
}

final class GalaxyNativeBridge: NSObject {
    static var defaultStateDirectory: URL { FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("GalaxyControl/Agent", isDirectory: true) }
    private weak var owner: GalaxyController?
    private let stateDirectory: URL, bridgeDirectory: URL, requestsDirectory: URL, responsesDirectory: URL, signalsDirectory: URL
    private var pollTimer: Timer?, heartbeatTimer: Timer?
    private var active = Set<String>()
    private var interactiveID: String?
    private var shortcuts: NativeShortcutSet?
    private var shuttingDown = false
    private var capture: AnyObject?
    private var languageObserver: NSObjectProtocol?
    init(owner: GalaxyController, stateDirectory: URL, installShortcuts: Bool = true) throws {
        self.owner = owner; self.stateDirectory = stateDirectory
        bridgeDirectory = stateDirectory.appendingPathComponent("bridge/native-"+String(ProcessInfo.processInfo.processIdentifier), isDirectory: true)
        requestsDirectory = bridgeDirectory.appendingPathComponent("requests", isDirectory: true)
        responsesDirectory = bridgeDirectory.appendingPathComponent("responses", isDirectory: true)
        signalsDirectory = bridgeDirectory.appendingPathComponent("signals", isDirectory: true)
        super.init()
        for directory in [stateDirectory,bridgeDirectory,requestsDirectory,responsesDirectory,signalsDirectory] { try Self.privateDirectory(directory) }
        if installShortcuts, !CommandLine.arguments.contains("--layout-check"),
           UserDefaults.standard.object(forKey:"startup.initialized") == nil {
            let previous = Self.readPrivate(stateDirectory.appendingPathComponent("settings.json")).flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] }
            let shouldStart = previous?["autoStart"] as? Bool ?? true
            do {
                if shouldStart, !GalaxyStartup.enabled { try GalaxyStartup.configure(true) }
                UserDefaults.standard.set(true,forKey:"startup.initialized")
            } catch { /* Keep the app usable; settings can retry without changing existing preferences. */ }
        }
        if installShortcuts, let data = Self.readPrivate(stateDirectory.appendingPathComponent("settings.json")),
           let stored = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], let path = stored["saveFolder"] as? String, path.hasPrefix("/"), !path.utf8.contains(0) {
            useSaveDirectory(URL(fileURLWithPath:path,isDirectory:true))
        }
        if installShortcuts {
        let shortcutSet = try NativeShortcutSet()
        var saved = UserDefaults.standard.dictionary(forKey: "agent.shortcuts") as? [String: String] ?? [:]
        // Import the user's working capture binding; a fresh installation uses Control+Shift+A.
        if saved["areaCapture"] == nil {
            if let applied = owner.captureHub.applied { saved["areaCapture"] = NativeShortcut.text(key: applied.0, modifiers: applied.1) }
            else { saved["areaCapture"] = "Control+Shift+A" }
        }
        if saved["aiTranslate"] == nil { saved["aiTranslate"] = "Control+Shift+T" }
        let originalArea = owner.captureHub.applied.flatMap { NativeShortcut.text(key:$0.0,modifiers:$0.1) } ?? "Control+Shift+A"
        if let old = owner.captureHub.hotKey { UnregisterEventHotKey(old); owner.captureHub.hotKey = nil }
        let ready = NativeShortcutSet.validated(saved) != nil
        if ready { shortcutSet.recover(saved) } else { _ = shortcutSet.apply(["areaCapture":originalArea]) }
        if ready {
            shortcuts = shortcutSet
            shortcutSet.action = { [weak self] name in self?.shortcutPressed(name) }
            owner.captureHub.shortcutApply = { [weak self] key, mods in
                guard let self = self, let text = NativeShortcut.text(key: key, modifiers: mods), let shortcuts = self.shortcuts else { return false }
                var values = shortcuts.values; values["areaCapture"] = text
                guard shortcuts.apply(values) else { return false }; self.persistShortcuts(); return true
            }
            persistShortcuts()
        } else { shortcutSet.shutdown(); owner.captureHub.applied = nil; owner.captureHub.registerShortcut(showResult: false) }
        }
        pollTimer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in self?.poll() }
        heartbeatTimer = Timer(timeInterval: 2, repeats: true) { [weak self] _ in self?.heartbeat() }
        RunLoop.main.add(pollTimer!, forMode: .common); RunLoop.main.add(heartbeatTimer!, forMode: .common)
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in self?.heartbeat() }
        heartbeat()
    }
    private static func hostDiagnosticRecord(_ record: [String: Any]) -> [String: Any]? {
        let flags: Set<String> = ["trusted", "webMatch", "mainFrame", "originMatch", "urlMatch"]
        guard Set(record.keys).isSubset(of: flags.union(["action"])),
              let action = record["action"] as? String,
              Set(["desktopReady", "captureStarted", "captureReady", "captureClosed", "captureCancelled"]).contains(action) else { return nil }
        var safe: [String: Any] = ["action": action]
        for key in flags where record[key] != nil {
            guard let value = record[key] as? NSNumber, CFGetTypeID(value) == CFBooleanGetTypeID() else { return nil }
            safe[key] = value.boolValue
        }
        return safe
    }
    func recordHostDiagnostic(_ record: [String: Any]) {
        guard let safe = Self.hostDiagnosticRecord(record) else { return }
        try? Self.atomicJSON(safe, to: stateDirectory.appendingPathComponent("host-diagnostic.json"))
    }
    private static func privateDirectory(_ url: URL) throws {
        // Intermediate symlinks must not redirect the private spool outside its intended tree.
        var ancestor = url
        while ancestor.path != "/" {
            var item = stat()
            if lstat(ancestor.path, &item) == 0, (item.st_mode & S_IFMT) == S_IFLNK { throw NSError(domain: "GalaxyControl.Bridge", code: 1) }
            ancestor.deleteLastPathComponent()
        }
        var metadata = stat()
        if lstat(url.path, &metadata) == 0 {
            guard (metadata.st_mode & S_IFMT) == S_IFDIR, metadata.st_uid == getuid() else { throw NSError(domain: "GalaxyControl.Bridge", code: 1) }
        } else { try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions:0o700]) }
        try FileManager.default.setAttributes([.posixPermissions:0o700], ofItemAtPath: url.path)
    }
    private static func readPrivate(_ url: URL) -> Data? {
        let fd = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { return nil }; defer { close(fd) }
        var metadata = stat()
        guard fstat(fd, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFREG, metadata.st_uid == getuid(), metadata.st_nlink == 1,
              metadata.st_mode & 0o077 == 0, metadata.st_size > 0, metadata.st_size <= 65_536 else { return nil }
        var data = Data(count: Int(metadata.st_size))
        let count = data.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
        return count == data.count ? data : nil
    }
    private static func atomicJSON(_ json: [String: Any], to url: URL) throws {
        let data = try JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
        let temporary = url.deletingLastPathComponent().appendingPathComponent(".native-" + UUID().uuidString)
        let fd = open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw NSError(domain: "GalaxyControl.Bridge", code: Int(errno)) }
        defer { close(fd); unlink(temporary.path) }
        let count = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard count == data.count, fsync(fd) == 0, rename(temporary.path, url.path) == 0 else { throw NSError(domain: "GalaxyControl.Bridge", code: Int(errno)) }
    }
    private static func validArgs(_ operation: String, _ args: [String:Any]) -> Bool {
        let keys:[String:Set<String>] = [
            "pair.approve":["origin","clientName"], "folder.choose":["purpose"], "files.choose":["kind","multiple"],
            "file.open":["path"], "file.reveal":["path"], "editor.open":["path"], "clipboard.copy":["path"], "capture.start":["mode","monitor","format","ephemeral","aiJobId"], "capture.cancel":["requestId"],
            "record.start":["mode","monitor","fps","microphone","systemAudio","width","scale_percent","format"], "record.stop":[], "record.pause":[], "record.resume":[], "permissions.get":[], "app.quit":[],
            "permissions.open":["permission"], "settings.apply":["language","shortcuts","autoStart","saveFolderName","closeAfterCaptureCopy","openCaptureEditor","captureFormat"], "phone.open":[], "phone.status":[], "phone.pair":["address","code"], "phone.connect":["address"], "phone.start":["serial","keyboard","mouse","audio","clipboard"], "phone.stop":[], "phone.keyboard":["serial"], "native.tools":["tool"]
        ]
        guard let allowed = keys[operation], Set(args.keys).isSubset(of:allowed) else { return false }
        for key in ["ephemeral","multiple","autoStart","microphone","systemAudio","clipboard","closeAfterCaptureCopy","openCaptureEditor"] where args[key] != nil {
            guard let number = args[key] as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else { return false }
        }
        for key in ["monitor","fps","width","scale_percent"] where args[key] != nil {
            let minimum = operation == "capture.start" && key == "monitor" ? -1.0 : 0.0
            guard let number = args[key] as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(), number.doubleValue.isFinite,
                  number.doubleValue >= minimum, number.doubleValue < 10_000, floor(number.doubleValue) == number.doubleValue else { return false }
        }
        for key in ["origin","clientName","purpose","kind","path","mode","permission","language","saveFolderName","tool","serial","address","code","keyboard","mouse","audio","captureFormat","format"] where args[key] != nil {
            guard let value = args[key] as? String, value.utf8.count <= (key == "path" ? 16_384 : 500), !value.utf8.contains(0) else { return false }
        }
        if let format = args["captureFormat"] as? String, !["png","jpg"].contains(format) { return false }
        if operation == "capture.cancel" { guard let id = args["requestId"] as? String, UUID(uuidString:id)?.uuidString.lowercased() == id else { return false } }
        if operation == "capture.start" {
            if let format = args["format"] as? String, !["png","jpg"].contains(format) { return false }
            if args["ephemeral"] as? Bool == true {
                guard args["mode"] as? String == "area", args["format"] as? String == "png", let id = args["aiJobId"] as? String, UUID(uuidString:id)?.uuidString.lowercased() == id else { return false }
            } else if args["aiJobId"] != nil { return false }
        }
        if args["shortcuts"] != nil, !(args["shortcuts"] is [String:String]) { return false }
        if ["phone.pair","phone.connect"].contains(operation) { guard let address = args["address"] as? String, validPhoneLANEndpoint(address) else { return false } }
        if operation == "phone.pair" { guard let code = args["code"] as? String, code.count == 6, code.allSatisfy({ $0.isASCII && $0.isNumber }) else { return false } }
        if ["phone.start","phone.keyboard"].contains(operation) { guard let serial = args["serial"] as? String, phoneSerialValid(serial) else { return false } }
        if operation == "phone.start" {
            for (name,values) in [("keyboard",["uhid","sdk"]),("mouse",["sdk","uhid"]),("audio",["output","aac","off"])] { if let value = args[name] as? String, !values.contains(value) { return false } }
        }
        return true
    }
    private static func parse(_ data: Data, filename: String, now: Double) -> BridgeRequest? {
        guard let uuid = UUID(uuidString: filename), filename.lowercased() == uuid.uuidString.lowercased(),
              let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let id = value["id"] as? String, id == filename,
              let operation = value["operation"] as? String, bridgeOperations.contains(operation),
              let args = value["args"] as? [String: Any], validArgs(operation,args), let expires = value["expiresAt"] as? Double,
              expires.isFinite, expires > now, expires <= now + 600,
              Set(value.keys).isSubset(of: ["id","operation","args","expiresAt"]) else { return nil }
        return BridgeRequest(id: id, operation: operation, args: args, expires: expires)
    }
    private func poll() {
        guard !shuttingDown, let files = try? FileManager.default.contentsOfDirectory(at: requestsDirectory, includingPropertiesForKeys: nil) else { return }
        let now = Date().timeIntervalSince1970
        for file in files.prefix(32) where file.pathExtension == "json" {
            let id = file.deletingPathExtension().lastPathComponent
            guard UUID(uuidString: id) != nil, !active.contains(id) else { continue }
            guard let data = Self.readPrivate(file), let request = Self.parse(data, filename: id, now: now) else {
                // Removing a symlink here removes only that link; never follow it to another file.
                try? FileManager.default.removeItem(at: file)
                if UUID(uuidString: id) != nil { try? Self.atomicJSON(["id":id,"ok":false,"data":[:],"errorCode":"invalidRequest"], to: responsesDirectory.appendingPathComponent(id + ".json")) }
                continue
            }
            try? FileManager.default.removeItem(at: file); active.insert(id); execute(request)
        }
    }
    private func finish(_ request: BridgeRequest, _ data: [String: Any] = [:], error: String = "") {
        active.remove(request.id)
        if interactiveID == request.id { interactiveID = nil }
        guard !shuttingDown else { return }
        let expired = request.expires <= Date().timeIntervalSince1970
        do { try Self.atomicJSON(["id":request.id,"ok":error.isEmpty && !expired,"data":expired ? [:] : data,"errorCode":expired ? "cancelled" : error], to: responsesDirectory.appendingPathComponent(request.id + ".json")) }
        catch { if request.operation == "capture.start" { galaxyWriteCaptureDiagnostic(phase: "responding", error: error, stage: "bridgeResponse", directory: stateDirectory) } }
    }
    private func persistShortcuts() {
        guard let values = shortcuts?.values else { return }
        UserDefaults.standard.set(values, forKey: "agent.shortcuts")
        if let text = values["areaCapture"], let parsed = NativeShortcut.parse(text), let letter = NativeShortcut.codes.first(where: { $0.value == parsed.key })?.key, let hub = owner?.captureHub {
            hub.keyMenu.selectItem(withTitle: letter)
            hub.command.state = parsed.modifiers & UInt32(cmdKey) == 0 ? .off : .on; hub.control.state = parsed.modifiers & UInt32(controlKey) == 0 ? .off : .on
            hub.option.state = parsed.modifiers & UInt32(optionKey) == 0 ? .off : .on; hub.shift.state = parsed.modifiers & UInt32(shiftKey) == 0 ? .off : .on
            hub.applied = (parsed.key, parsed.modifiers)
            UserDefaults.standard.set(letter, forKey:"capture.hotkey.key"); UserDefaults.standard.set(Int(parsed.modifiers), forKey:"capture.hotkey.modifiers")
        }
        UserDefaults.standard.synchronize()
        heartbeat()
    }
    private func heartbeat() {
        guard !shuttingDown else { return }
        if let shortcuts = shortcuts { shortcuts.recover(shortcuts.values) }
        var settings: [String:Any] = ["languageSource":AppLanguage.shared.source,"language":AppLanguage.shared.code,"autoStart":GalaxyStartup.enabled,"saveFolderName":owner?.captureHub.saveDirectory.lastPathComponent ?? "GalaxyControl","saveFolder":owner?.captureHub.saveDirectory.path ?? ""]
        settings["closeAfterCaptureCopy"] = UserDefaults.standard.object(forKey:"capture.closeAfterCopy") as? Bool ?? true
        settings["openCaptureEditor"] = UserDefaults.standard.object(forKey:"capture.openEditor") as? Bool ?? true
        settings["captureFormat"] = UserDefaults.standard.string(forKey:"capture.format") == "jpg" ? "jpg" : "png"
        settings["shortcuts"] = shortcuts?.values ?? ["areaCapture":"Control+Shift+A","fullCapture":"","webCapture":"","recordToggle":"","recordArea":"","aiTranslate":""]
        let monitors: [[String:Any]] = NSScreen.screens.enumerated().map { index, screen in
            ["id":index,"name":screen.localizedName + " #" + String((screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0),"width":Int(screen.frame.width),"height":Int(screen.frame.height),"primary":index == 0]
        }
        let snapshot: [String:Any] = ["monitors":monitors,"version":1,"pid":ProcessInfo.processInfo.processIdentifier,"updatedAt":Date().timeIntervalSince1970,"os":"macOS","recording":owner?.recorder.isRecording ?? false,"paused":owner?.recorder.isPaused ?? false,"phoneControl":true,"settings":settings]
        try? Self.atomicJSON(snapshot, to:bridgeDirectory.appendingPathComponent("status.json"))
        // Older installed update helpers still observe this discovery-only heartbeat.
        try? Self.atomicJSON(snapshot, to:stateDirectory.appendingPathComponent("bridge/status.json"))
    }
    private func emit(_ operation: String) {
        guard ["web.capture","record.toggle"].contains(operation) else { return }
        let id = UUID().uuidString.lowercased()
        try? Self.atomicJSON(["id":id,"operation":operation,"args":[:],"createdAt":Date().timeIntervalSince1970], to:signalsDirectory.appendingPathComponent(id + ".json"))
    }
    private func shortcutPressed(_ name: String) {
        if owner?.agentHost?.shortcut(name) == true { return }
        switch name {
        case "areaCapture":
            if let hub = owner?.captureHub {
                let previous = hub.modeMenu.indexOfSelectedItem; hub.modeMenu.selectItem(at:0); hub.beginCapture()
                if previous >= 0 { hub.modeMenu.selectItem(at:previous) }
            }
        case "fullCapture": captureScreen(mode:"full", monitor:-1) { [weak self] url, _ in if let url = url { self?.owner?.captureHub.openEditor(url, captureSession:true) } }
        case "webCapture": emit("web.capture")
        case "recordToggle": emit("record.toggle")
        default: break
        }
    }
    private func parentWindow() -> NSWindow? { NSApp.keyWindow ?? owner?.agentHost?.window ?? owner?.window }
    private func execute(_ request: BridgeRequest) {
        guard request.expires > Date().timeIntervalSince1970, let owner = owner else { finish(request,error:"cancelled"); return }
        if ["pair.approve","folder.choose","files.choose","capture.start","record.start"].contains(request.operation) {
            guard interactiveID == nil, parentWindow()?.attachedSheet == nil else { finish(request,error:"conflict");return }
            interactiveID = request.id
        }
        let args = request.args
        switch request.operation {
        case "pair.approve":
            guard let origin = args["origin"] as? String, let url = URL(string:origin), ["http","https","chrome-extension"].contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil, url.query == nil, url.fragment == nil, url.path.isEmpty, origin.count <= 250 else { finish(request,error:"forbiddenOrigin"); return }
            let alert = NSAlert(); alert.messageText = L("브라우저 연결을 허용할까요?")
            alert.informativeText = L("아래 주소가 이 Mac의 로컬 도구와 선택한 파일을 사용할 수 있도록 허용합니다. 본인이 연 연결만 승인하세요.") + "\n\n" + origin
            alert.addButton(withTitle:L("연결 허용")); alert.addButton(withTitle:L("거절")); NSApp.activate(ignoringOtherApps:true)
            if let window = parentWindow() { window.makeKeyAndOrderFront(nil); alert.beginSheetModal(for:window) { [weak self] answer in self?.finish(request,["approved":answer == .alertFirstButtonReturn],error:answer == .alertFirstButtonReturn ? "" : "pairingDenied") } }
            else { finish(request,["approved":alert.runModal() == .alertFirstButtonReturn]) }
        case "folder.choose", "files.choose":
            let panel = NSOpenPanel(); panel.canChooseDirectories = request.operation == "folder.choose"; panel.canChooseFiles = !panel.canChooseDirectories; panel.canCreateDirectories = panel.canChooseDirectories
            panel.allowsMultipleSelection = !panel.canChooseDirectories && (args["multiple"] as? Bool ?? false)
            if !panel.canChooseDirectories {
                switch args["kind"] as? String ?? "any" { case "image":panel.allowedFileTypes = ["png","jpg","jpeg","webp","gif","tiff","heic","bmp"]; case "pdf":panel.allowedFileTypes = ["pdf"]; case "video":panel.allowedFileTypes = ["mp4","mov","mkv","webm","avi","gif"]; case "any":break; default:finish(request,error:"invalidRequest");return }
            } else if !["search","save"].contains(args["purpose"] as? String ?? "") { finish(request,error:"invalidRequest");return }
            NSApp.activate(ignoringOtherApps:true)
            let complete: (NSApplication.ModalResponse)->Void = { [weak self] answer in
                guard request.expires > Date().timeIntervalSince1970 else { self?.finish(request,error:"cancelled");return }
                if request.operation == "folder.choose" {
                    if answer == .OK, args["purpose"] as? String == "save", let directory = panel.url { self?.useSaveDirectory(directory) }
                    self?.finish(request,["path":answer == .OK ? panel.url?.path ?? "" : "","cancelled":answer != .OK]) }
                else { self?.finish(request,["paths":answer == .OK ? panel.urls.map(\.path) : [],"cancelled":answer != .OK]) }
            }
            if let window = parentWindow() { window.makeKeyAndOrderFront(nil); panel.beginSheetModal(for:window,completionHandler:complete) } else { panel.begin(completionHandler:complete) }
        case "file.open", "file.reveal", "editor.open", "clipboard.copy":
            guard let path = args["path"] as? String, path.hasPrefix("/"), !path.utf8.contains(0), FileManager.default.fileExists(atPath:path) else { finish(request,error:"inputMissing");return }
            let url = URL(fileURLWithPath:path).standardizedFileURL
            var metadata = stat()
            guard lstat(url.path, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFREG || request.operation == "file.reveal" else { finish(request,error:"inputMissing");return }
            if request.operation == "clipboard.copy" { let copied = galaxyCopyPNGFile(url); finish(request, ["copied":copied], error: copied ? "" : "processingFailed") }
            else if request.operation == "file.reveal" { NSWorkspace.shared.activateFileViewerSelecting([url]);finish(request) }
            else if request.operation == "editor.open" { guard NSImage(contentsOf:url)?.isValid == true else { finish(request,error:"unsupported");return };owner.captureHub.openEditor(url);finish(request) }
            else {
                let safe = ["png","jpg","jpeg","webp","gif","tiff","heic","bmp","pdf","mp4","mov","mkv","webm","avi","mp3","m4a","wav","docx","xlsx","pptx","txt","csv","zip"]
                guard !url.pathComponents.contains(where: { $0.lowercased().hasSuffix(".app") }), safe.contains(url.pathExtension.lowercased()) else { finish(request,error:"unsupported");return }
                finish(request,error:NSWorkspace.shared.open(url) ? "" : "processingFailed")
            }
        case "capture.start":
            let mode = args["mode"] as? String ?? "area", monitor = args["monitor"] as? Int ?? -1
            guard ["area","full","window"].contains(mode), monitor >= -1,
                  monitor == -1 || NSScreen.screens.indices.contains(monitor) else { finish(request,error:"invalidRequest");return }
            if args["ephemeral"] as? Bool == true { captureAI(request) }
            else { captureScreen(mode:mode,monitor:monitor) { [weak self] url,error in self?.finish(request,url.map { ["paths":[$0.path]] } ?? [:],error:error) } }
        case "capture.cancel":
            let matches = interactiveID == args["requestId"] as? String
            if matches {
                if let operation = capture as? GalaxyCaptureOperation { operation.cancel() }
            }
            finish(request,["cancelledCapture":matches])
        case "record.start":
            let mode = args["mode"] as? String ?? "full", monitor = args["monitor"] as? Int ?? 0
            guard ["full","area","window"].contains(mode), monitor >= 0 else { finish(request,error:"invalidRequest");return }
            let fps = args["fps"] as? Int ?? 30, width = args["width"] as? Int ?? 0, scale = args["scale_percent"] as? Int ?? 100
            guard (5...60).contains(fps), width == 0 || (2...7680).contains(width), (10...100).contains(scale), (args["format"] as? String ?? "mp4") == "mp4" else { finish(request,error:"invalidRequest");return }
            owner.recorder.startNative(mode:mode,monitor:monitor,fps:fps,microphone:args["microphone"] as? Bool ?? false,systemAudio:args["systemAudio"] as? Bool ?? false,width:width,scalePercent:scale,format:"mp4") { [weak self, weak owner] error in
                if error.isEmpty && request.expires <= Date().timeIntervalSince1970 { owner?.recorder.stop() }
                self?.heartbeat(); self?.finish(request,error.isEmpty ? ["recording":true,"paused":false] : [:],error:error)
            }
        case "record.pause": owner.recorder.pauseNative { [weak self] error in self?.heartbeat();self?.finish(request,error.isEmpty ? ["recording":true,"paused":true] : [:],error:error) }
        case "record.resume": owner.recorder.resumeNative { [weak self] error in self?.heartbeat();self?.finish(request,error.isEmpty ? ["recording":true,"paused":false] : [:],error:error) }
        case "record.stop": owner.recorder.stopNative { [weak self] url,error in self?.heartbeat(); self?.finish(request,url.map { ["paths":[$0.path],"recording":false,"paused":false] } ?? [:],error:error) }
        case "app.quit":
            finish(request,["quitting":true])
            DispatchQueue.main.asyncAfter(deadline:.now()+0.3) { NSApp.terminate(nil) }
        case "permissions.get":finish(request,["screenCapture":CGPreflightScreenCaptureAccess() ? "available" : "needsPermission","accessibility":AXIsProcessTrusted() ? "available" : "needsPermission","files":"available"])
        case "permissions.open":
            let permission = args["permission"] as? String ?? ""
            let section = ["screenCapture":"Privacy_ScreenCapture","accessibility":"Privacy_Accessibility","files":"Privacy_FilesAndFolders"]
            guard let suffix = section[permission], let url = URL(string:"x-apple.systempreferences:com.apple.preference.security?" + suffix) else { finish(request,error:"invalidRequest");return }
            NSWorkspace.shared.open(url);finish(request)
        case "settings.apply": applySettings(request)
        case "phone.open": owner.showNativeTool(5);finish(request)
        case "phone.status", "phone.pair", "phone.connect", "phone.start", "phone.stop", "phone.keyboard": executePhone(request)
        case "native.tools":
            guard let name = args["tool"] as? String, let index = ["image":0,"pdf":1,"capture":2,"record":3,"codes":4,"phone":5][name] else { finish(request,error:"invalidRequest");return }
            owner.showNativeTool(index);finish(request)
        default:finish(request,error:"unsupported")
        }
    }
    /// Reuses the controller's ADB helpers and single owned scrcpy process.
    private func executePhone(_ request: BridgeRequest) {
        guard let owner = owner else { finish(request,error:"nativeUnavailable");return }
        let args = request.args, operation = request.operation
        if operation == "phone.stop" { owner.stopMirror();finish(request,["success":true]);return }
        if owner.busy {
            if operation == "phone.status" { finish(request,owner.phoneNativeStatus()) } else { finish(request,error:"busy") }
            return
        }
        guard FileManager.default.isExecutableFile(atPath:adbURL.path) else { finish(request,error:"phoneUnavailable");return }
        var pairingCode = args["code"] as? String ?? ""
        let work: () -> ToolResult
        if operation == "phone.pair" {
            let address = args["address"] as! String, code = pairingCode; pairingCode.removeAll()
            work = { phonePairTool(address,code:code) }
        } else if operation == "phone.connect" { let address = args["address"] as! String;work = { phoneConnectTool(address) } }
        else if operation == "phone.keyboard" {
            let serial = args["serial"] as! String
            work = {
                let devices = tool(["devices","-l"])
                guard phones(devices.output).contains(where: { $0.serial == serial }) else { return ToolResult(status:-2,output:"") }
                return phoneKeyboardTool(serial)
            }
        } else { work = { tool(["devices","-l"]) } }
        owner.task("연결된 휴대폰을 찾는 중…",work) { [weak self,weak owner] result in
            guard let self = self, let owner = owner, request.expires > Date().timeIntervalSince1970 else { self?.finish(request,error:"cancelled");return }
            if operation == "phone.status" { self.finish(request,owner.phoneNativeStatus(result));return }
            if operation == "phone.pair" {
                self.finish(request,["success":result.status == 0 && result.output.contains("Successfully paired")],error:result.status == 0 && result.output.contains("Successfully paired") ? "" : "phonePairingFailed");return
            }
            if operation == "phone.connect" {
                if result.status == 0 { owner.updateDevices(result) }
                self.finish(request,["success":result.status == 0],error:result.status == 0 ? "" : "phoneConnectFailed");return
            }
            if operation == "phone.keyboard" { self.finish(request,["success":result.status == 0],error:result.status == 0 ? "" : result.status == -2 ? "phoneDeviceMissing" : "phoneStartFailed");return }
            guard result.status == 0 else { self.finish(request,error:"phoneUnavailable");return }
            let serial = args["serial"] as! String
            guard let phone = phones(result.output).first(where: { $0.serial == serial }) else {
                let blocked = phoneDeviceRows(result.output).contains(where: { $0["serial"] as? String == serial })
                self.finish(request,error:blocked ? "phoneUnauthorized" : "phoneDeviceMissing");return
            }
            let keyboard = args["keyboard"] as? String ?? "uhid", mouse = args["mouse"] as? String ?? "sdk", audio = args["audio"] as? String ?? "output", clipboard = args["clipboard"] as? Bool ?? true
            let audioMode = ["output","aac","off"].firstIndex(of:audio) ?? 0
            let error = owner.launchMirror(phone:phone,keyboard:keyboard,mouse:mouse,audioMode:audioMode,clipboard:clipboard,showErrors:false)
            if error.isEmpty {
                owner.keyboardMenu.selectItem(at:keyboard == "uhid" ? 0 : 1);owner.mouseMenu.selectItem(at:mouse == "sdk" ? 0 : 1);owner.audioMenu.selectItem(at:audioMode)
                UserDefaults.standard.set(audioMode,forKey:"phone.audioMode");owner.nativePhoneRows = phoneDeviceRows(result.output)
            }
            self.finish(request,["success":error.isEmpty],error:error)
        }
    }
    private func useSaveDirectory(_ url: URL) {
        guard let owner = owner else { return }
        UserDefaults.standard.set(url.path,forKey:"capture.saveDirectory")
        owner.captureHub.folderLabel.stringValue = url.path;owner.captureHub.folderLabel.toolTip = url.path
        owner.recorder.useSaveDirectory(url);heartbeat()
    }
    private func applySettings(_ request: BridgeRequest) {
        let args = request.args
        guard Set(args.keys).isSubset(of:["language","shortcuts","autoStart","saveFolderName","closeAfterCaptureCopy","openCaptureEditor","captureFormat"]), let shortcuts = shortcuts else { finish(request,error:"nativeUnavailable");return }
        if let language = args["language"] as? String, !AppLanguage.shared.codes.contains(language) { finish(request,error:"invalidRequest");return }
        if args["language"] != nil && !(args["language"] is String) { finish(request,error:"invalidRequest");return }
        if args["autoStart"] != nil && !(args["autoStart"] is Bool) { finish(request,error:"invalidRequest");return }
        var proposed = shortcuts.values
        if let supplied = args["shortcuts"] { guard let values = supplied as? [String:String], Set(values.keys).isSubset(of:Set(bridgeShortcutKeys)) else { finish(request,error:"invalidRequest");return };proposed.merge(values) { _,new in new } }
        let old = shortcuts.values
        guard shortcuts.apply(proposed) else { finish(request,error:"shortcutConflict");return }
        do { if let enabled = args["autoStart"] as? Bool { try GalaxyStartup.configure(enabled);UserDefaults.standard.set(true,forKey:"startup.initialized") } }
        catch { _ = shortcuts.apply(old);finish(request,error:"processingFailed");return }
        if let language = args["language"] as? String, let index = AppLanguage.shared.codes.firstIndex(of:language) { AppLanguage.shared.select(index);owner?.refreshLanguageMenu() }
        if let enabled = args["closeAfterCaptureCopy"] as? Bool { UserDefaults.standard.set(enabled,forKey:"capture.closeAfterCopy") }
        if let enabled = args["openCaptureEditor"] as? Bool { UserDefaults.standard.set(enabled,forKey:"capture.openEditor") }
        if let format = args["captureFormat"] as? String { UserDefaults.standard.set(format,forKey:"capture.format") }
        persistShortcuts();heartbeat();finish(request,["applied":true])
    }
    private func captureAI(_ request: BridgeRequest) {
        guard let hub = owner?.captureHub, !hub.capturing,
              let jobID = request.args["aiJobId"] as? String else { finish(request,error:"busy");return }
        hub.capturing = true
        let started = Date().timeIntervalSince1970 * 1000
        let operation = GalaxySystemCapture(region:true,monitorIndex:-1,windowOnly:false) { [weak self, weak hub] image,error in
            guard let self = self else { return }
            self.capture = nil;hub?.capturing = false
            if let error = error { self.finish(request,error:galaxyCaptureErrorCode(error));return }
            guard let image = image else { self.finish(request,error:"cancelled");return }
            let selected = Date().timeIntervalSince1970 * 1000
            self.owner?.agentHost?.aiSelected()
            // The selected image goes straight to the private loopback job, never a saved artifact.
            DispatchQueue.global(qos:.userInitiated).async { [weak self] in
                guard let self = self else { return }
                guard var bytes = NSBitmapImageRep(cgImage:image).representation(using:.png,properties:[:]), !bytes.isEmpty, bytes.count <= 16*1024*1024,
                      let sessionBytes = Self.readPrivate(self.stateDirectory.appendingPathComponent("desktop-session.json")),
                      let session = (try? JSONSerialization.jsonObject(with:sessionBytes)) as? [String:Any],
                      let origin = session["origin"] as? String, let url = URL(string:origin), url.scheme == "http", url.host == "127.0.0.1", let port = url.port, GalaxyAgentEndpoint.ports.contains(port),
                      let token = session["token"] as? String, token.count >= 32, token.count <= 256, token.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "-") }) else {
                    DispatchQueue.main.async { self.finish(request,error:"aiInvalidImage") };return
                }
                var upload = URLRequest(url:URL(string:GalaxyAgentEndpoint.origin(port)+"/ai/frame/"+jobID)!)
                upload.httpMethod = "POST";upload.timeoutInterval = 8
                upload.setValue("image/png",forHTTPHeaderField:"Content-Type");upload.setValue(origin,forHTTPHeaderField:"Origin");upload.setValue(token,forHTTPHeaderField:"X-Local-Agent-Token")
                upload.httpBody = bytes
                GalaxyAgentEndpoint.session.dataTask(with:upload) { _,response,_ in
                    let ok = (response as? HTTPURLResponse)?.statusCode == 200
                    DispatchQueue.main.async { self.finish(request,ok ? ["selectedAt":selected,"overlayShownAt":started] : [:],error:ok ? "" : "aiInvalidImage") }
                }.resume()
                bytes.resetBytes(in:0..<bytes.count)
            }
        }
        capture = operation;operation.begin()
    }
    private func captureScreen(mode:String,monitor:Int,completion:@escaping(URL?,String)->Void) {
        guard let hub = owner?.captureHub, !hub.capturing else { completion(nil,"conflict");return }
        galaxyClearCaptureDiagnostic(directory: stateDirectory)
        guard hub.readyDirectory() else {
            galaxyWriteCaptureDiagnostic(phase: "preparing", error: NSError(domain: "GalaxyControl.CaptureBridge", code: 1), stage: "saveDirectory", directory: stateDirectory)
            completion(nil,"processingFailed");return
        }
        let file = hub.captureFile();hub.capturing = true
        let done: (CGImage?,Error?)->Void = { [weak self, weak hub] image,error in
            self?.capture = nil;hub?.capturing = false
            if let error = error {
                completion(nil,galaxyCaptureErrorCode(error));return
            }
            guard let image = image else { completion(nil,"cancelled");return }
            guard let bytes = NSBitmapImageRep(cgImage:image).representation(using:file.pathExtension == "jpg" ? .jpeg : .png,properties:[.compressionFactor:0.92]) else {
                galaxyWriteCaptureDiagnostic(phase: "encoding", error: NSError(domain: "GalaxyControl.CaptureBridge", code: 2), stage: "bitmapEncoding", directory: self?.stateDirectory)
                completion(nil,"processingFailed");return
            }
            do { try bytes.write(to:file,options:.atomic);completion(file,"") }
            catch { galaxyWriteCaptureDiagnostic(phase: "persisting", error: error, stage: "writeCapture", directory: self?.stateDirectory);completion(nil,galaxyCaptureErrorCode(error)) }
        }
        let operation = GalaxySystemCapture(region: mode == "area", monitorIndex: monitor,
                                           windowOnly: mode == "window", completion: done)
        capture = operation
        operation.begin()
    }
    func cancelActiveCapture() { (capture as? GalaxyCaptureOperation)?.cancel() }
    func shutdown() {
        shuttingDown = true;pollTimer?.invalidate();heartbeatTimer?.invalidate();shortcuts?.shutdown()
        owner?.captureHub.shortcutApply = nil
        if let observer = languageObserver { NotificationCenter.default.removeObserver(observer) }
        if let capture = capture as? GalaxyCaptureOperation { capture.cancel() }
        for status in [bridgeDirectory.appendingPathComponent("status.json"),stateDirectory.appendingPathComponent("bridge/status.json")] {
            if let data = Self.readPrivate(status), let value = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], value["pid"] as? Int == Int(ProcessInfo.processInfo.processIdentifier) { try? FileManager.default.removeItem(at:status) }
        }
    }
    static func selfCheck() -> Bool {
        let aiID = UUID().uuidString.lowercased()
        guard validArgs("capture.start",["mode":"area","monitor":-1,"format":"png","ephemeral":true,"aiJobId":aiID]),
              !validArgs("capture.start",["mode":"area","ephemeral":true,"aiJobId":"bad"]),
              !validArgs("capture.start",["mode":"full","format":"png","ephemeral":true,"aiJobId":aiID]),
              NativeShortcutSet.validated(["aiTranslate":"Control+Shift+T"]) != nil else { return false }
        guard let resolved = realpath(FileManager.default.temporaryDirectory.path, nil) else { return false }
        let parent = URL(fileURLWithPath: String(cString: resolved), isDirectory: true); free(resolved)
        let directory = parent.appendingPathComponent("GalaxyBridgeCheck-" + UUID().uuidString,isDirectory:true)
        defer { try? FileManager.default.removeItem(at:directory) }
        do {
            try privateDirectory(directory)
            let id = UUID().uuidString.lowercased(),now = Date().timeIntervalSince1970,url = directory.appendingPathComponent("request.json")
            let request:[String:Any] = ["id":id,"operation":"permissions.get","args":[:],"expiresAt":now + 60]
            try atomicJSON(request,to:url)
            guard let data = readPrivate(url) else { print("Native bridge private-read check failed"); return false }
            guard parse(data,filename:id,now:now) != nil, parse(data,filename:"../escape",now:now) == nil, parse(data,filename:id,now:now + 90) == nil else { print("Native bridge request validation check failed"); return false }
            var bad = request;bad["operation"] = "shell.execute"
            guard parse(try JSONSerialization.data(withJSONObject:bad),filename:id,now:now) == nil else { return false }
            bad = request;bad["id"] = UUID().uuidString
            guard parse(try JSONSerialization.data(withJSONObject:bad),filename:id,now:now) == nil else { return false }
            bad = request;bad["args"] = ["unexpected"]
            guard parse(try JSONSerialization.data(withJSONObject:bad),filename:id,now:now) == nil, parse(Data("not-json".utf8),filename:id,now:now) == nil else { return false }
            guard !validArgs("files.choose",["multiple":1]), !validArgs("capture.start",["monitor":true]), !validArgs("capture.start",["monitor":1.5]), !validArgs("permissions.get",["shell":"arbitrary"]), validArgs("record.start",["fps":30,"microphone":false,"systemAudio":false]) else { return false }
            let hostRecord: [String: Any] = ["action": "captureStarted", "trusted": true, "webMatch": true, "mainFrame": false, "originMatch": true, "urlMatch": false]
            guard hostDiagnosticRecord(hostRecord)?.count == 6,
                  hostDiagnosticRecord(["action": "captureStarted", "trusted": 1]) == nil,
                  hostDiagnosticRecord(["action": "captureReady", "trusted": "true"]) == nil,
                  hostDiagnosticRecord(["action": "captureReady", "url": "https://fixture.invalid"]) == nil,
                  hostDiagnosticRecord(["action": "copyText", "trusted": true]) == nil,
                  hostDiagnosticRecord(["trusted": true]) == nil else { return false }
            guard validArgs("capture.start",["mode":"full","monitor":-1]),
                  validArgs("capture.start",["mode":"area","monitor":2]),
                  !validArgs("capture.start",["monitor":-2]), !validArgs("record.start",["monitor":-1]),
                  !validArgs("capture.start",["monitor":-1.5]) else { return false }
            bad = request;bad["expiresAt"] = now + 601
            guard parse(try JSONSerialization.data(withJSONObject:bad),filename:id,now:now) == nil else { return false }
            guard validArgs("phone.start",["serial":"USB1","keyboard":"uhid","mouse":"sdk","audio":"output","clipboard":true]),
                  !validArgs("phone.start",["serial":"USB1","clipboard":1]), !validArgs("phone.start",["serial":"USB1;command"]),
                  !validArgs("phone.start",["serial":"USB1","keyboard":"shell"]), !validArgs("phone.start",["serial":"USB1","command":"arbitrary"]),
                  validArgs("phone.pair",["address":"192.168.1.6:34323","code":"123456"]),
                  !validArgs("phone.pair",["address":"8.8.8.8:5555","code":"123456"]), !validArgs("phone.pair",["address":"192.168.1.6:34323","code":"12345"]) else { return false }
            let link = directory.appendingPathComponent("link.json");try FileManager.default.createSymbolicLink(at:link,withDestinationURL:url)
            guard readPrivate(link) == nil else { return false }
            try FileManager.default.setAttributes([.posixPermissions:0o644],ofItemAtPath:url.path)
            guard readPrivate(url) == nil else { return false }
            try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:url.path)
            let hard = directory.appendingPathComponent("hard.json");try FileManager.default.linkItem(at:url,to:hard)
            guard readPrivate(hard) == nil else { return false };try FileManager.default.removeItem(at:hard)
            let oversized = directory.appendingPathComponent("large.json");try Data(repeating:0,count:65_537).write(to:oversized);try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:oversized.path)
            guard readPrivate(oversized) == nil else { return false }
            return NativeShortcutSet.validated(["areaCapture":"Control+Shift+A","fullCapture":"Shift+Control+A"]) == nil && NativeShortcutSet.validated(["areaCapture":"Control+Shift+A","fullCapture":"Control+Shift+F9"]) != nil && NativeShortcut.parse("Command+C") == nil && NativeShortcut.parse("Control+Control+A") == nil
        } catch { print("Native bridge fixture error: \(error)"); return false }
    }
}
func nativeBridgeSelfCheck() -> Bool { GalaxyNativeBridge.selfCheck() }

/// Exercises the real poll/response/heartbeat loop using a disposable private spool, with no
/// permission request, file chooser, hotkey registration or persistent-setting mutation.
func nativeBridgeIntegrationCheck() -> Bool {
    guard let resolved = realpath(FileManager.default.temporaryDirectory.path,nil) else { return false }
    let parent = URL(fileURLWithPath:String(cString:resolved),isDirectory:true);free(resolved)
    let state = parent.appendingPathComponent("GalaxyNativeIntegration-" + UUID().uuidString,isDirectory:true)
    defer { try? FileManager.default.removeItem(at:state) }
    do {
        _ = NSApplication.shared
        let owner = GalaxyController()
        let broker = try GalaxyNativeBridge(owner:owner,stateDirectory:state,installShortcuts:false)
        defer { broker.shutdown() }
        let id = UUID().uuidString.lowercased(),request = state.appendingPathComponent("bridge/requests/" + id + ".json"),response = state.appendingPathComponent("bridge/responses/" + id + ".json")
        let json:[String:Any] = ["id":id,"operation":"permissions.get","args":[:],"expiresAt":Date().timeIntervalSince1970 + 5]
        try JSONSerialization.data(withJSONObject:json).write(to:request,options:.atomic);try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:request.path)
        let end = Date().addingTimeInterval(3)
        while !FileManager.default.fileExists(atPath:response.path), Date() < end { RunLoop.main.run(until:Date().addingTimeInterval(0.025)) }
        guard let bytes = try? Data(contentsOf:response), let result = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any], result["id"] as? String == id, result["ok"] as? Bool == true, let data = result["data"] as? [String:String], ["available","needsPermission"].contains(data["screenCapture"] ?? ""),data["files"] == "available",let statusBytes = try? Data(contentsOf:state.appendingPathComponent("bridge/status.json")),let heartbeat = (try? JSONSerialization.jsonObject(with:statusBytes)) as? [String:Any],heartbeat["pid"] as? Int == Int(ProcessInfo.processInfo.processIdentifier) else { return false }
        return !FileManager.default.fileExists(atPath:request.path)
    } catch { return false }
}

/// Reserves an unused test binding briefly, forces a real Carbon registration conflict,
/// and verifies both the previous value and its live registration survive the failed update.
func nativeBridgeShortcutRegistrationCheck() -> Bool {
    _ = NSApplication.shared
    do {
        var free: [String] = []
        for number in (1...12).reversed() {
            let text = "Command+Control+Option+Shift+F\(number)"
            let candidate = try NativeShortcutSet()
            if candidate.apply(["areaCapture":text]) { free.append(text) }
            candidate.shutdown()
            if free.count == 2 { break }
        }
        guard free.count == 2 else { return false }
        let original = try NativeShortcutSet(), occupied = try NativeShortcutSet(), verifier = try NativeShortcutSet()
        defer { original.shutdown(); occupied.shutdown(); verifier.shutdown() }
        guard original.apply(["areaCapture":free[0]]), occupied.apply(["fullCapture":free[1]]) else { return false }
        let before = original.values
        guard !original.apply(["areaCapture":free[1]]), original.values == before else { return false }
        guard !verifier.apply(["areaCapture":free[0]]) else { return false }
        original.shutdown()
        let recovered = try NativeShortcutSet()
        defer { recovered.shutdown() }
        recovered.recover(["areaCapture":free[1], "aiTranslate":free[0]])
        guard !verifier.apply(["areaCapture":free[0]]) else { return false }
        occupied.shutdown()
        recovered.recover(recovered.values)
        return !verifier.apply(["areaCapture":free[1]])
    } catch { return false }
}
