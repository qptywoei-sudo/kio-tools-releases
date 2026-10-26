import AppKit

func L(_ key: String) -> String { AppLanguage.shared.translate(key) }
func Lf(_ key: String, _ args: CVarArg...) -> String { String(format: L(key), arguments: args) }

final class AppLanguage {
    static let shared = AppLanguage()
    let codes = ["vi", "en", "ko", "ja", "zh-TW", "zh-CN"]
    let names = ["Tiếng Việt", "English", "한국어", "日本語", "繁體中文", "简体中文"]
    static func normalize(_ raw: String?) -> String? {
        guard let raw = raw else { return nil }
        let parts = raw.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "_", with: "-").lowercased().split(separator: "-").map(String.init)
        guard let base = parts.first else { return nil }
        if ["vi","en","ko","ja"].contains(base) { return base }
        guard base == "zh" else { return nil }
        if parts.contains("hant") { return "zh-TW" }
        if parts.contains("hans") { return "zh-CN" }
        return parts.contains(where: { ["tw","hk","mo"].contains($0) }) ? "zh-TW" : "zh-CN"
    }
    private var savedCode: String? {
        let url = GalaxyNativeBridge.defaultStateDirectory.appendingPathComponent("language-preference.json")
        if let data = try? Data(contentsOf: url), let saved = (try? JSONSerialization.jsonObject(with: data)) as? [String:Any], saved["source"] as? String == "user", let value = Self.normalize(saved["language"] as? String) { return value }
        return Self.normalize(UserDefaults.standard.string(forKey: "app.language"))
    }
    var source: String { savedCode == nil ? "system" : "user" }
    var code: String { savedCode ?? Self.normalize(Locale.preferredLanguages.first) ?? "en" }
    private var catalog: [String: [String: String]] = [:]
    private var reverse: [String: String] = [:]
    private var templates: [(NSRegularExpression, [String], String)] = []
    private var prefixes: [String] = []
    private var translatedCache: [String: String] = [:]
    private var cachedLanguage = ""
    private let cacheLock = NSLock()
    private let originals = NSMapTable<AnyObject, NSMutableDictionary>.weakToStrongObjects()
    private var timer: Timer?
    private init() {
        if let url = Bundle.main.resourceURL?.appendingPathComponent("tools/i18n/locales.json"), let data = try? Data(contentsOf: url), let values = try? JSONDecoder().decode([String: [String: String]].self, from: data) { catalog = values }
        let placeholder = try! NSRegularExpression(pattern: #"\{([A-Za-z_]+)\}|%(?:[0-9]+\$)?[-+0-9.]*l*[diuf@]"#)
        for (key, values) in catalog {
            for value in values.values { reverse[value] = key }
            for form in [key] + Array(values.values) {
                let ns = form as NSString; let matches = placeholder.matches(in: form, range: NSRange(location:0,length:ns.length))
                guard !matches.isEmpty else { continue }
                var pattern = "^"; var last = 0; var fields: [String] = []
                for m in matches { pattern += NSRegularExpression.escapedPattern(for:ns.substring(with:NSRange(location:last,length:m.range.location-last))) + "(.*?)"; fields.append(ns.substring(with:m.range)); last = m.range.location+m.range.length }
                pattern += NSRegularExpression.escapedPattern(for:ns.substring(from:last)) + "$"
                if let regex = try? NSRegularExpression(pattern:pattern,options:[.dotMatchesLineSeparators]) { templates.append((regex,fields,key)) }
            }
        }
        prefixes = catalog.keys.filter { $0.hasSuffix(": ") || $0.hasSuffix("\n\n") }.sorted { $0.count > $1.count }
    }
    func translate(_ raw: String) -> String {
        cacheLock.lock(); defer { cacheLock.unlock() }
        let language = code
        if language != cachedLanguage { translatedCache.removeAll(keepingCapacity: true); cachedLanguage = language }
        if let cached = translatedCache[raw] { return cached }
        let result = resolve(raw, language: language)
        if translatedCache.count >= 2048 { translatedCache.removeAll(keepingCapacity: true) }
        translatedCache[raw] = result
        return result
    }
    private func resolve(_ raw: String, language: String) -> String {
        let key = reverse[raw] ?? raw
        if let entry = catalog[key] { return entry[language] ?? entry["en"] ?? key }
        for (regex, fields, template) in templates {
            let ns = key as NSString
            if let match = regex.firstMatch(in: key, range: NSRange(location: 0, length: ns.length)) {
                var output = catalog[template]?[language] ?? catalog[template]?["en"] ?? template
                let token = try! NSRegularExpression(pattern: #"\{([A-Za-z_]+)\}|%(?:[0-9]+\$)?[-+0-9.]*l*[diuf@]"#)
                let destination = output as NSString
                let outputFields = token.matches(in: output,range:NSRange(location:0,length:destination.length)).map { destination.substring(with:$0.range) }
                if fields.first?.hasPrefix("{") == true {
                    for i in 0..<fields.count { output = output.replacingOccurrences(of:fields[i],with:ns.substring(with:match.range(at:i+1))) }
                } else {
                    for i in 0..<min(outputFields.count, fields.count) { if let range = output.range(of:outputFields[i]) { output.replaceSubrange(range,with:ns.substring(with:match.range(at:i+1))) } }
                }
                return output
            }
        }
        for prefix in prefixes where key.hasPrefix(prefix) {
            return (catalog[prefix]?[language] ?? catalog[prefix]?["en"] ?? prefix) + key.dropFirst(prefix.count)
        }
        return key
    }
    func select(_ index: Int) {
        guard codes.indices.contains(index) else { return }
        let language = codes[index]
        let url = GalaxyNativeBridge.defaultStateDirectory.appendingPathComponent("language-preference.json")
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: ["schemaVersion":1,"language":language,"source":"user"])
            try data.write(to: url, options: .atomic)
        } catch { NSLog("KIO i18n: preferenceWriteFailed") }
        UserDefaults.standard.set(language, forKey: "app.language")
        applyAll(); NotificationCenter.default.post(name: Notification.Name("GalaxyControlLanguageChanged"),object:nil)
    }
    func start() { applyAll(); timer = Timer.scheduledTimer(withTimeInterval: 0.35, repeats: true) { [weak self] _ in self?.applyAll(visibleOnly: true) } }
    private func value(_ object: AnyObject, _ slot: String, _ current: String) -> String {
        let slots = originals.object(forKey: object) ?? NSMutableDictionary()
        let prior = slots[slot+".translated"] as? String
        if prior != current { slots[slot+".original"] = reverse[current] ?? current }
        let output = translate(slots[slot+".original"] as? String ?? current)
        slots[slot+".translated"] = output; originals.setObject(slots, forKey: object); return output
    }
    func applyAll(visibleOnly: Bool = false) {
        for w in NSApp.windows where !visibleOnly || w.isVisible { w.title = value(w, "title", w.title); if let content = w.contentView { apply(content) } }
        if !visibleOnly, let menu = NSApp.mainMenu { applyMenu(menu) }
    }
    private func applyMenu(_ menu: NSMenu) {
        menu.title = value(menu, "title", menu.title)
        for item in menu.items where item.tag != 997 { item.title = value(item, "title", item.title); if let child = item.submenu { applyMenu(child) } }
    }
    private func apply(_ view: NSView) {
        if let hint = view.toolTip { view.toolTip = value(view, "tooltip", hint) }
        if let button = view as? NSButton, let hint = button.accessibilityLabel() { button.setAccessibilityLabel(value(button, "accessibilityLabel", hint)) }
        if let table = view as? NSTableView { for column in table.tableColumns { column.title = value(column, "title", column.title) }; return }
        if view is NSTextView { return }
        if let field = view as? NSTextField {
            if !field.isEditable { field.stringValue = value(field, "text", field.stringValue) }
            if let placeholder = field.placeholderString { field.placeholderString = value(field, "placeholder", placeholder) }
        }
        if let button = view as? NSPopUpButton { if let menu = button.menu { applyMenu(menu) } }
        else if let button = view as? NSButton { button.title = value(button, "title", button.title) }
        if let box = view as? NSBox { box.title = value(box, "title", box.title) }
        for child in view.subviews { apply(child) }
    }
}
