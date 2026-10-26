import AppKit

private func codeToolsValidBarcode(_ value: String, kind: String) -> Bool {
    if kind == "code128" { return !value.isEmpty && value.utf8.count <= 300 && value.unicodeScalars.allSatisfy { (32...126).contains(Int($0.value)) } }
    guard ["ean13", "ean8"].contains(kind) else { return false }
    let length = kind == "ean13" ? 13 : 8
    guard value.count == length - 1 || value.count == length, value.allSatisfy({ $0.isASCII && $0.isNumber }) else { return false }
    if value.count == length {
        let digits = value.compactMap { Int(String($0)) }, body = Array(value.dropLast()).reversed().compactMap { Int(String($0)) }
        let sum = body.enumerated().reduce(0) { $0 + $1.element * ($1.offset % 2 == 0 ? 3 : 1) }
        return digits.last == (10 - sum % 10) % 10
    }
    return true
}

func codeToolsSelfCheck() -> Bool {
    codeToolsValidBarcode("5901234123457", kind: "ean13") &&
    codeToolsValidBarcode("590123412345", kind: "ean13") &&
    !codeToolsValidBarcode("5901234123458", kind: "ean13") &&
    codeToolsValidBarcode("96385074", kind: "ean8") &&
    !codeToolsValidBarcode("96385075", kind: "ean8") &&
    !codeToolsValidBarcode("036000291452", kind: "upca") &&
    codeToolsValidBarcode("Galaxy-123", kind: "code128") &&
    !codeToolsValidBarcode("한글", kind: "code128") &&
    !codeToolsValidBarcode("12\n34", kind: "code128")
}

/// QR and barcode generation/reading uses only the bundled offline engine.
final class CodeToolsController: NSObject {
    private var rootView: NSView?
    private let family = NSPopUpButton()
    private let qrType = NSPopUpButton()
    private let security = NSPopUpButton()
    private let ssid = NSTextField(string: "")
    private let password = NSSecureTextField(string: "")
    private let text = NSTextView()
    private let preview = NSImageView()
    private let resultText = NSTextView()
    private let status = NSTextField(wrappingLabelWithString: "QR 또는 바코드를 만들거나 이미지에서 읽으세요. 모든 처리는 이 컴퓨터에서 실행됩니다.")
    private let folderLabel = NSTextField(labelWithString: "")
    private var textRow: NSView!
    private var wifiRow: NSView!
    private var generateButton: NSButton!
    private var readButton: NSButton!
    private var copyImageButton: NSButton!
    private var saveButton: NSButton!
    private var openURLButton: NSButton!
    private var generatedURL: URL?
    private var generatedImage: NSImage?
    private var decodedTexts: [String] = []
    private var selectedURL: URL?
    private var busy = false
    private let kinds = ["qr", "code128", "ean13", "ean8"]
    private var outputDirectory: URL {
        if let p = UserDefaults.standard.string(forKey: "codes.outputDirectory"), !p.isEmpty { return URL(fileURLWithPath: p, isDirectory: true) }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Pictures/GalaxyControl", isDirectory: true)
    }
    private func label(_ value: String) -> NSTextField { let l = NSTextField(labelWithString: value); l.font = .systemFont(ofSize: 13); return l }
    private func button(_ title: String, _ action: Selector) -> NSButton { let b = NSButton(title: title, target: self, action: action); b.bezelStyle = .rounded; return b }
    private func row(_ items: [NSView]) -> NSStackView { let s = NSStackView(views: items); s.orientation = .horizontal; s.alignment = .centerY; s.spacing = 8; return s }
    private func textScroll(_ view: NSTextView, editable: Bool) -> NSScrollView {
        view.isRichText = false; view.isEditable = editable; view.isSelectable = true
        view.font = .systemFont(ofSize: 14); view.textContainerInset = NSSize(width: 8, height: 8)
        view.isHorizontallyResizable = false; view.isVerticallyResizable = true; view.autoresizingMask = .width
        view.textContainer?.widthTracksTextView = true; view.textContainer?.containerSize = NSSize(width: 700, height: CGFloat.greatestFiniteMagnitude)
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder; scroll.documentView = view; return scroll
    }

    func makeView() -> NSView {
        if let existing = rootView { return existing }
        let root = NSView(); rootView = root
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 11
        stack.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 16), stack.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -16), stack.topAnchor.constraint(equalTo: root.topAnchor, constant: 16), stack.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -16)])
        let title = label("QR / 바코드"); title.font = .systemFont(ofSize: 23, weight: .semibold); stack.addArrangedSubview(title)
        family.addItems(withTitles: ["QR", "Code 128", "EAN-13", "EAN-8"]); family.target = self; family.action = #selector(kindChanged)
        qrType.addItems(withTitles: ["텍스트", "URL", "Wi-Fi 정보"]); qrType.target = self; qrType.action = #selector(kindChanged)
        security.addItems(withTitles: ["WPA / WPA2 / WPA3", "WEP", "비밀번호 없음"]); security.target = self; security.action = #selector(securityChanged)
        stack.addArrangedSubview(row([label("형식"), family, label("QR 내용"), qrType]))
        let input = textScroll(text, editable: true); input.heightAnchor.constraint(equalToConstant: 100).isActive = true
        textRow = input; stack.addArrangedSubview(input); input.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        ssid.placeholderString = "Wi-Fi 이름 (SSID)"; ssid.widthAnchor.constraint(equalToConstant: 230).isActive = true
        password.placeholderString = "Wi-Fi 비밀번호"; password.widthAnchor.constraint(equalToConstant: 230).isActive = true
        let wifi = NSStackView(); wifi.orientation = .vertical; wifi.alignment = .leading; wifi.spacing = 8
        wifi.addArrangedSubview(row([label("SSID"), ssid, label("보안"), security])); wifi.addArrangedSubview(row([label("비밀번호"), password]))
        wifiRow = wifi; stack.addArrangedSubview(wifi)
        generateButton = button("만들기", #selector(generate)); readButton = button("이미지에서 읽기…", #selector(readImage))
        copyImageButton = button("이미지 복사", #selector(copyImage)); saveButton = button("PNG 다른 이름 저장…", #selector(savePNG))
        stack.addArrangedSubview(row([generateButton, readButton, copyImageButton, saveButton]))
        preview.imageScaling = .scaleProportionallyUpOrDown
        preview.wantsLayer = true; preview.layer?.backgroundColor = NSColor.white.cgColor
        preview.translatesAutoresizingMaskIntoConstraints = false; preview.widthAnchor.constraint(equalToConstant: 285).isActive = true
        preview.heightAnchor.constraint(greaterThanOrEqualToConstant: 230).isActive = true
        let result = textScroll(resultText, editable: false); result.translatesAutoresizingMaskIntoConstraints = false
        let body = NSStackView(views: [preview, result]); body.orientation = .horizontal; body.alignment = .top; body.spacing = 14; body.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(body); body.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        body.heightAnchor.constraint(greaterThanOrEqualToConstant: 230).isActive = true
        preview.heightAnchor.constraint(equalTo: body.heightAnchor).isActive = true; result.heightAnchor.constraint(equalTo: body.heightAnchor).isActive = true
        openURLButton = button("확인한 URL 열기", #selector(openURL))
        stack.addArrangedSubview(row([button("결과 텍스트 복사", #selector(copyText)), openURLButton, button("저장 폴더…", #selector(chooseFolder)), button("폴더 열기", #selector(openFolder))]))
        folderLabel.stringValue = outputDirectory.path; folderLabel.font = .systemFont(ofSize: 11); folderLabel.lineBreakMode = .byTruncatingMiddle; folderLabel.textColor = .secondaryLabelColor
        stack.addArrangedSubview(folderLabel); status.font = .systemFont(ofSize: 12); status.textColor = .secondaryLabelColor; stack.addArrangedSubview(status)
        for view in [folderLabel, status] { view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true }
        kindChanged(); setBusy(false); return root
    }
    @objc private func kindChanged() {
        let isQR = family.indexOfSelectedItem == 0
        qrType.isEnabled = isQR; textRow.isHidden = isQR && qrType.indexOfSelectedItem == 2; wifiRow.isHidden = !(isQR && qrType.indexOfSelectedItem == 2)
        if isQR { status.stringValue = "생성한 QR은 PNG로 자동 저장됩니다. Wi-Fi 비밀번호는 QR에 포함되므로 공유할 내용을 확인하세요." }
        else {
            let descriptions = ["", "Code 128: 인쇄 가능한 영문·숫자·기호 (ASCII 32~126), 최대 300자", "EAN-13: 숫자 12자리 또는 올바른 검증 숫자를 포함한 13자리", "EAN-8: 숫자 7자리 또는 올바른 검증 숫자를 포함한 8자리"]
            status.stringValue = descriptions[max(0, family.indexOfSelectedItem)]
        }
        securityChanged()
    }
    @objc private func securityChanged() { password.isEnabled = security.indexOfSelectedItem != 2 }
    private func setBusy(_ value: Bool) {
        busy = value; generateButton.isEnabled = !value; readButton.isEnabled = !value
        copyImageButton.isEnabled = !value && generatedImage != nil; saveButton.isEnabled = !value && generatedURL != nil
        openURLButton.isEnabled = !value && selectedURL != nil
    }
    private func clearResult() {
        generatedURL = nil; generatedImage = nil; preview.image = nil
        decodedTexts = []; selectedURL = nil; resultText.string = ""
    }
    @objc private func generate() {
        guard !busy else { return }
        let kind = kinds[max(0, family.indexOfSelectedItem)], value = text.string
        var job: [String: Any] = ["op": "code_generate", "kind": kind, "text": value, "output_dir": outputDirectory.path]
        if kind == "qr" {
            job["qr_type"] = ["text", "url", "wifi"][qrType.indexOfSelectedItem]
            if qrType.indexOfSelectedItem == 2 {
                guard !ssid.stringValue.isEmpty else { status.stringValue = "Wi-Fi 이름 (SSID)을 입력하세요."; return }
                job["ssid"] = ssid.stringValue; job["password"] = security.indexOfSelectedItem == 2 ? "" : password.stringValue
                job["security"] = ["WPA", "WEP", "nopass"][security.indexOfSelectedItem]
            } else { guard !value.isEmpty else { status.stringValue = "QR에 넣을 내용을 입력하세요."; return } }
        } else {
            guard codeToolsValidBarcode(value, kind: kind) else { status.stringValue = "바코드의 글자·길이·검증 숫자를 확인하세요. " + (kind == "code128" ? "영문·숫자·기호만 사용할 수 있습니다." : "숫자만 입력하고, 마지막 검증 숫자가 있다면 올바른 값이어야 합니다."); return }
        }
        clearResult(); setBusy(true); status.stringValue = "컴퓨터에서 코드를 만드는 중…"
        LocalEngine.run(job: job) { [weak self] output in
            guard let self = self else { return }
            if output.success, let file = output.files.first, let image = NSImage(contentsOf: file) {
                self.generatedURL = file; self.generatedImage = image; self.preview.image = image
                let value = output.data["text"] as? String ?? value
                self.decodedTexts = [value]; self.resultText.string = value; self.updateOpenURL(value)
                self.status.stringValue = Lf("PNG 저장 완료: %@ · 이미지 복사 또는 다른 이름 저장을 사용할 수 있습니다.", String(describing: file.lastPathComponent))
            } else { self.status.stringValue = output.message }
            self.setBusy(false)
        }
    }
    @objc private func readImage() {
        guard !busy else { return }; let panel = NSOpenPanel(); panel.allowedFileTypes = ["jpg", "jpeg", "png", "webp"]; panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let file = panel.url else { return }
        clearResult(); setBusy(true); status.stringValue = "이미지에서 QR·바코드를 읽는 중…"
        LocalEngine.run(job: ["op": "code_read", "path": file.path]) { [weak self] output in
            guard let self = self else { return }
            self.preview.image = NSImage(contentsOf: file); self.generatedImage = nil; self.generatedURL = nil; self.selectedURL = nil; self.decodedTexts = []
            let results = output.data["results"] as? [[String: Any]] ?? []
            self.decodedTexts = results.compactMap { $0["text"] as? String }
            if output.success, !self.decodedTexts.isEmpty {
                self.resultText.string = results.map { "\($0["format"] as? String ?? "코드")\n\($0["text"] as? String ?? "")" }.joined(separator: "\n\n")
                if self.decodedTexts.count == 1 { self.updateOpenURL(self.decodedTexts[0]) }
                self.status.stringValue = Lf("%@개 코드를 읽었습니다. 결과를 확인한 뒤 복사하거나 URL을 여세요.", String(describing: self.decodedTexts.count))
            } else { self.resultText.string = ""; self.status.stringValue = output.message == "QR 코드를 인식할 수 없습니다." ? "QR 코드를 인식할 수 없습니다. 바코드도 찾지 못했습니다." : output.message }
            self.setBusy(false)
        }
    }
    private func updateOpenURL(_ text: String) {
        selectedURL = nil
        if let url = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)), let scheme = url.scheme?.lowercased(), ["http", "https"].contains(scheme), let host = url.host, !host.isEmpty { selectedURL = url }
    }
    @objc private func openURL() { if let url = selectedURL { NSWorkspace.shared.open(url) } }
    @objc private func copyText() {
        guard !decodedTexts.isEmpty else { status.stringValue = "먼저 코드를 만들거나 이미지에서 읽으세요."; return }
        let board = NSPasteboard.general; board.clearContents()
        status.stringValue = board.setString(decodedTexts.joined(separator: "\n"), forType: .string) ? "코드의 실제 내용을 복사했습니다." : "텍스트를 복사하지 못했습니다. 다시 시도하세요."
    }
    @objc private func copyImage() {
        guard let image = generatedImage, let file = generatedURL, let png = try? Data(contentsOf: file) else { return }
        let board = NSPasteboard.general; board.clearContents(); let copied = board.setData(png, forType: .png)
        if let tiff = image.tiffRepresentation { board.setData(tiff, forType: .tiff) }
        status.stringValue = copied ? "코드 이미지를 복사했습니다. 다른 앱에서 ⌘V로 붙여넣으세요." : "이미지를 복사하지 못했습니다. 다시 시도하세요."
    }
    @objc private func savePNG() {
        guard let file = generatedURL else { return }; let panel = NSSavePanel(); panel.allowedFileTypes = ["png"]; panel.directoryURL = outputDirectory; panel.nameFieldStringValue = file.lastPathComponent
        guard panel.runModal() == .OK, let target = panel.url else { return }
        do {
            if target.standardizedFileURL != file.standardizedFileURL { let data = try Data(contentsOf: file); try data.write(to: target, options: .atomic) }
            status.stringValue = Lf("저장됨: %@", String(describing: target.lastPathComponent))
        } catch { status.stringValue = Lf("저장 실패: %@", String(describing: error.localizedDescription)) }
    }
    @objc private func chooseFolder() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true; panel.directoryURL = outputDirectory
        if panel.runModal() == .OK, let folder = panel.url { UserDefaults.standard.set(folder.path, forKey: "codes.outputDirectory"); folderLabel.stringValue = folder.path }
    }
    @objc private func openFolder() { do { try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true); NSWorkspace.shared.open(outputDirectory) } catch { status.stringValue = Lf("폴더를 열 수 없습니다: %@", String(describing: error.localizedDescription)) } }
}
