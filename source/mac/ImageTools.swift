import AppKit

private struct ImageToolItem {
    let input: URL
    let originalBytes: Int64
    var output: URL?
    var outputBytes: Int64?
    var result = L("대기")
}

enum GalaxyFileIntake {
    static let types: [NSPasteboard.PasteboardType] = [.fileURL, .png, .tiff]
    static func files(from board: NSPasteboard) -> [URL] {
        (board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL] ?? []).filter(\.isFileURL)
    }
    static func canRead(_ board: NSPasteboard) -> Bool {
        !files(from: board).isEmpty || board.availableType(from: [.png, .tiff]) != nil || board.canReadObject(forClasses: [NSImage.self], options: nil)
    }
    /// Clipboard pixels become a new, private temporary source; original files are never rewritten.
    static func imageSource(from board: NSPasteboard) throws -> URL? {
        guard files(from: board).isEmpty else { return nil }
        let data = board.data(forType: .png) ?? board.data(forType: .tiff) ?? NSImage(pasteboard: board)?.tiffRepresentation
        guard let data = data else { return nil }
        guard let bitmap = NSBitmapImageRep(data: data), bitmap.pixelsWide > 0, bitmap.pixelsHigh > 0,
              Int64(bitmap.pixelsWide) * Int64(bitmap.pixelsHigh) <= 40_000_000,
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw NSError(domain: "GalaxyFileIntake", code: 1, userInfo: [NSLocalizedDescriptionKey: L("클립보드 이미지를 읽을 수 없습니다. PNG 또는 JPG 파일을 선택하세요.")])
        }
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("GalaxyControl-Clipboard-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyyMMdd_HHmmss_SSS"
        let file = folder.appendingPathComponent("Clipboard_" + formatter.string(from: Date()) + ".png")
        do { try png.write(to: file, options: .withoutOverwriting); try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path) }
        catch { try? FileManager.default.removeItem(at: folder); throw error }
        return file
    }
}

class GalaxyFileDropView: NSView {
    var acceptPasteboard: ((NSPasteboard) -> Bool)?
    var canAccept: (() -> Bool)?
    override init(frame frameRect: NSRect) { super.init(frame: frameRect); registerForDraggedTypes(GalaxyFileIntake.types) }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        (canAccept?() ?? true) && GalaxyFileIntake.canRead(sender.draggingPasteboard) ? .copy : []
    }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool { acceptPasteboard?(sender.draggingPasteboard) ?? false }
}

final class GalaxyFileDropCard: GalaxyFileDropView {
    var chooseFiles: (() -> Void)?
    var paste: (() -> Bool)?
    private let symbol = NSImageView()
    private let titleLabel = NSTextField(labelWithString: L("여기에 파일을 놓으세요"))
    private let detailLabel = NSTextField(wrappingLabelWithString: "")
    private let detailSource: String
    private var languageObserver: NSObjectProtocol?
    init(symbolName: String, detail: String) {
        detailSource = detail
        super.init(frame: .zero)
        wantsLayer = true; layer?.cornerRadius = 14; layer?.borderWidth = 1
        layer?.borderColor = BogoTheme.line.cgColor; layer?.backgroundColor = BogoTheme.background.cgColor
        symbol.image = NSImage(systemSymbolName: symbolName, accessibilityDescription: L("파일 추가")); symbol.contentTintColor = BogoTheme.accent; symbol.setAccessibilityLabel(L("파일 추가"))
        titleLabel.font = .systemFont(ofSize: 14, weight: .semibold); detailLabel.stringValue = L(detail)
        detailLabel.font = .systemFont(ofSize: 11); detailLabel.textColor = .secondaryLabelColor
        let labels = NSStackView(views: [titleLabel, detailLabel]); labels.orientation = .vertical; labels.alignment = .leading; labels.spacing = 4
        let content = NSStackView(views: [symbol, labels]); content.orientation = .horizontal; content.spacing = 14; content.alignment = .centerY
        content.translatesAutoresizingMaskIntoConstraints = false; addSubview(content)
        NSLayoutConstraint.activate([content.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 16), content.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -16), content.topAnchor.constraint(equalTo: topAnchor, constant: 13), content.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -13), symbol.widthAnchor.constraint(equalToConstant: 30), symbol.heightAnchor.constraint(equalToConstant: 30)])
        heightAnchor.constraint(greaterThanOrEqualToConstant: 72).isActive = true
        setAccessibilityElement(true); setAccessibilityRole(.button); setAccessibilityLabel(L("파일 추가")); setAccessibilityHelp(L(detail))
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }; self.titleLabel.stringValue = L("여기에 파일을 놓으세요"); self.detailLabel.stringValue = L(self.detailSource)
            self.setAccessibilityLabel(L("파일 추가")); self.setAccessibilityHelp(L(self.detailSource)); self.symbol.setAccessibilityLabel(L("파일 추가"))
        }
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    deinit { if let languageObserver = languageObserver { NotificationCenter.default.removeObserver(languageObserver) } }
    override func accessibilityPerformPress() -> Bool { guard canAccept?() ?? true else { return false }; chooseFiles?(); return chooseFiles != nil }
    override var acceptsFirstResponder: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { !isHidden && bounds.contains(convert(point, from: superview)) ? self : nil }
    override func mouseDown(with event: NSEvent) { guard canAccept?() ?? true else { return }; window?.makeFirstResponder(self); chooseFiles?() }
    override func keyDown(with event: NSEvent) {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if event.charactersIgnoringModifiers?.lowercased() == "v", flags.contains(.command) || flags.contains(.control), paste?() == true { return }
        if event.keyCode == 36 || event.keyCode == 49 { chooseFiles?(); return }
        super.keyDown(with: event)
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        let result = super.draggingEntered(sender); layer?.borderColor = (result == .copy ? BogoTheme.accent : BogoTheme.line).cgColor; return result
    }
    override func draggingExited(_ sender: NSDraggingInfo?) { layer?.borderColor = BogoTheme.line.cgColor }
    override func concludeDragOperation(_ sender: NSDraggingInfo?) { layer?.borderColor = BogoTheme.line.cgColor }
}

final class ImageToolsController: NSObject, NSTableViewDataSource, NSTableViewDelegate {
    private var items: [ImageToolItem] = []
    private let table = NSTableView()
    private let preview = NSImageView()
    private let previewLabel = NSTextField(labelWithString: L("이미지를 선택하면 미리보기가 표시됩니다."))
    private let status = NSTextField(wrappingLabelWithString: L("JPG·PNG·WebP 파일을 선택하거나 이 화면에 여러 파일을 놓으세요."))
    private let format = NSPopUpButton()
    private let quality = NSSlider(value: 85, minValue: 1, maxValue: 100, target: nil, action: nil)
    private let qualityLabel = NSTextField(labelWithString: "85")
    private let width = NSTextField()
    private let height = NSTextField()
    private let ratio = NSButton(checkboxWithTitle: L("비율 유지"), target: nil, action: nil)
    private let upscale = NSButton(checkboxWithTitle: L("작은 이미지 확대 허용"), target: nil, action: nil)
    private let percent = NSPopUpButton()
    private let outputLabel = NSTextField(labelWithString: "")
    private let progress = NSProgressIndicator()
    private var controls: [NSControl] = []
    private var cachedView: NSView?
    private var editors: [CaptureEditorController] = []
    private var previewRequest = UUID()
    private var busy = false
    private var outputDirectory: URL
    private var languageObserver: NSObjectProtocol?
    private var clipboardSources: [URL] = []

    init(saveDirectory: URL? = nil) {
        outputDirectory = saveDirectory ?? (FileManager.default.urls(for: .picturesDirectory, in: .userDomainMask).first ?? FileManager.default.temporaryDirectory).appendingPathComponent("LocalTools", isDirectory: true)
        super.init()
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in self?.table.reloadData() }
    }
    deinit {
        if let languageObserver = languageObserver { NotificationCenter.default.removeObserver(languageObserver) }
        clipboardSources.forEach { try? FileManager.default.removeItem(at: $0.deletingLastPathComponent()) }
    }
    var activeEditors: [CaptureEditorController] { editors.filter { $0.window?.isVisible == true } }
    var isProcessing: Bool { busy }
    func prepareForQuit() -> Bool { CaptureEditorController.prepareForQuit(roots: editors) }

    func makeView() -> NSView {
        if let cachedView = cachedView { return cachedView }
        let root = GalaxyFileDropView(frame: NSRect(x: 0, y: 0, width: 930, height: 700))
        root.acceptPasteboard = { [weak self] board in self?.consumePasteboard(board) ?? false }
        root.canAccept = { [weak self] in self?.busy == false }
        let vertical = NSStackView(); vertical.orientation = .vertical; vertical.alignment = .leading; vertical.spacing = 10
        vertical.edgeInsets = NSEdgeInsets(top: 18, left: 18, bottom: 18, right: 18)
        vertical.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(vertical)
        NSLayoutConstraint.activate([vertical.leadingAnchor.constraint(equalTo: root.leadingAnchor), vertical.trailingAnchor.constraint(equalTo: root.trailingAnchor), vertical.topAnchor.constraint(equalTo: root.topAnchor), vertical.bottomAnchor.constraint(equalTo: root.bottomAnchor)])
        let title = NSTextField(labelWithString: L("이미지 변환 · 용량 줄이기 · 크기 변경"))
        title.font = NSFont.systemFont(ofSize: 22, weight: .semibold); vertical.addArrangedSubview(title)
        let drop = GalaxyFileDropCard(symbolName: "photo.on.rectangle.angled", detail: "JPG · PNG · WebP  /  클릭하여 선택  /  ⌘V 또는 Ctrl+V로 붙여넣기")
        drop.acceptPasteboard = root.acceptPasteboard; drop.canAccept = root.canAccept
        drop.chooseFiles = { [weak self] in self?.selectFiles() }; drop.paste = { [weak self] in self?.pasteFromClipboard() ?? false }
        vertical.addArrangedSubview(drop); drop.widthAnchor.constraint(equalTo: vertical.widthAnchor, constant: -36).isActive = true
        let files = NSStackView(views: [button(L("파일 선택…"), #selector(selectFiles)), button(L("붙여넣기"), #selector(pasteButton)), iconButton("minus", "선택 삭제", #selector(removeSelected)), iconButton("trash", "모두 비우기", #selector(clearFiles)), button(L("이미지 편집…"), #selector(editSelected))]); files.spacing = 8
        vertical.addArrangedSubview(files)
        for spec in [("file", L("파일"), CGFloat(265)), ("original", L("원본 용량"), CGFloat(95)), ("output", L("결과 용량"), CGFloat(95)), ("result", L("결과"), CGFloat(240))] {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(spec.0)); column.title = spec.1; column.width = spec.2
            table.addTableColumn(column)
        }
        table.delegate = self; table.dataSource = self; table.allowsMultipleSelection = true
        table.rowHeight = 28; table.usesAlternatingRowBackgroundColors = true
        table.target = self; table.doubleAction = #selector(openSelectedResult)
        table.registerForDraggedTypes(GalaxyFileIntake.types)
        let fileScroll = NSScrollView(); fileScroll.hasVerticalScroller = true; fileScroll.borderType = .bezelBorder; fileScroll.documentView = table
        fileScroll.heightAnchor.constraint(equalToConstant: 135).isActive = true
        vertical.addArrangedSubview(fileScroll)
        fileScroll.widthAnchor.constraint(equalTo: vertical.widthAnchor, constant: -36).isActive = true
        preview.imageScaling = .scaleProportionallyUpOrDown
        preview.wantsLayer = true; preview.layer?.backgroundColor = NSColor.controlBackgroundColor.cgColor
        preview.heightAnchor.constraint(greaterThanOrEqualToConstant: 80).isActive = true
        preview.heightAnchor.constraint(lessThanOrEqualToConstant: 175).isActive = true
        vertical.addArrangedSubview(preview)
        preview.widthAnchor.constraint(equalTo: fileScroll.widthAnchor).isActive = true
        previewLabel.font = NSFont.systemFont(ofSize: 11); previewLabel.textColor = .secondaryLabelColor; vertical.addArrangedSubview(previewLabel)
        format.addItems(withTitles: ["JPG", "PNG", "WebP"]); format.target = self; format.action = #selector(changeFormat)
        quality.target = self; quality.action = #selector(updateQuality); quality.widthAnchor.constraint(equalToConstant: 180).isActive = true
        qualityLabel.widthAnchor.constraint(equalToConstant: 32).isActive = true
        controls += [format, quality]
        let conversion = NSStackView(views: [NSTextField(labelWithString: L("출력 형식")), format, NSTextField(labelWithString: L("품질")), quality, qualityLabel]); conversion.spacing = 8
        vertical.addArrangedSubview(conversion)
        width.placeholderString = L("원본"); height.placeholderString = L("원본")
        for field in [width, height] { field.widthAnchor.constraint(equalToConstant: 86).isActive = true; controls.append(field) }
        ratio.state = .on; controls += [ratio, upscale]
        percent.addItems(withTitles: [L("크기 유지 / 직접 입력"), "25%", "50%", "75%"]); percent.target = self; percent.action = #selector(changePercent); controls.append(percent)
        let dimensions = NSStackView(views: [NSTextField(labelWithString: L("가로 px")), width, NSTextField(labelWithString: L("세로 px")), height, ratio, percent]); dimensions.spacing = 8
        vertical.addArrangedSubview(dimensions); vertical.addArrangedSubview(upscale)
        let explanation = NSTextField(wrappingLabelWithString: L("JPG로 바꾸면 투명 영역은 흰색 배경이 됩니다. PNG는 무손실이며 품질 설정은 JPG·WebP에 적용됩니다. 사진 회전 정보는 결과 픽셀에 반영합니다."))
        explanation.font = NSFont.systemFont(ofSize: 11); explanation.textColor = .secondaryLabelColor
        vertical.addArrangedSubview(explanation); explanation.widthAnchor.constraint(equalTo: fileScroll.widthAnchor).isActive = true
        outputLabel.stringValue = outputDirectory.path; outputLabel.lineBreakMode = .byTruncatingMiddle
        outputLabel.widthAnchor.constraint(lessThanOrEqualToConstant: 600).isActive = true
        let output = NSStackView(views: [button(L("저장 위치…"), #selector(pickOutputDirectory)), outputLabel]); output.spacing = 8; vertical.addArrangedSubview(output)
        progress.style = .spinning; progress.controlSize = .small; progress.isDisplayedWhenStopped = false
        let run = NSStackView(views: [button(L("변환 / 압축 / 크기 변경 실행"), #selector(processImages)), progress, button(L("결과 열기"), #selector(openSelectedResult)), button(L("저장 폴더 열기"), #selector(openOutputDirectory))]); run.spacing = 8; vertical.addArrangedSubview(run)
        status.font = NSFont.systemFont(ofSize: 12); vertical.addArrangedSubview(status); status.widthAnchor.constraint(equalTo: fileScroll.widthAnchor).isActive = true
        for row in [files, conversion, dimensions, output, run] { row.setContentHuggingPriority(.required, for: .vertical) }
        for label in [title, previewLabel, explanation, status] { label.setContentHuggingPriority(.required, for: .vertical) }
        cachedView = root
        return root
    }
    private func button(_ text: String, _ action: Selector) -> NSButton {
        let button = NSButton(title: text, target: self, action: action); button.bezelStyle = .rounded
        controls.append(button); return button
    }
    private func iconButton(_ symbol: String, _ label: String, _ action: Selector) -> NSButton {
        let b = button("", action); b.image = NSImage(systemSymbolName: symbol, accessibilityDescription: L(label)); b.imagePosition = .imageOnly
        b.toolTip = L(label); b.setAccessibilityLabel(L(label)); b.widthAnchor.constraint(equalToConstant: 32).isActive = true; return b
    }
    @discardableResult func pasteFromClipboard() -> Bool { _ = makeView(); return consumePasteboard(.general) }
    @objc private func pasteButton() {
        if !pasteFromClipboard() { status.stringValue = L("클립보드에 이미지나 파일이 없습니다. 파일을 놓거나 선택하세요.") }
    }
    private func consumePasteboard(_ board: NSPasteboard) -> Bool {
        guard !busy else { status.stringValue = L("현재 작업이 끝난 뒤 파일을 추가하세요."); return false }
        let urls = GalaxyFileIntake.files(from: board)
        if !urls.isEmpty { addFiles(urls); return true }
        do {
            guard let source = try GalaxyFileIntake.imageSource(from: board) else { return false }
            clipboardSources.append(source); addFiles([source]); status.stringValue = L("클립보드 이미지를 새 파일로 추가했습니다. 원본은 변경하지 않습니다."); return true
        } catch { status.stringValue = Lf("클립보드 이미지를 준비하지 못했습니다: %@", error.localizedDescription); return true }
    }
    func tableView(_ tableView: NSTableView, validateDrop info: NSDraggingInfo, proposedRow row: Int, proposedDropOperation operation: NSTableView.DropOperation) -> NSDragOperation {
        guard !busy, GalaxyFileIntake.canRead(info.draggingPasteboard) else { return [] }; tableView.setDropRow(-1, dropOperation: .on); return .copy
    }
    func tableView(_ tableView: NSTableView, acceptDrop info: NSDraggingInfo, row: Int, dropOperation: NSTableView.DropOperation) -> Bool { consumePasteboard(info.draggingPasteboard) }
    private func bytes(_ count: Int64) -> String { ByteCountFormatter.string(fromByteCount: count, countStyle: .file) }
    private func fileBytes(_ url: URL) -> Int64 { (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value ?? 0 }
    private func addFiles(_ urls: [URL]) {
        guard !busy else { status.stringValue = L("현재 작업이 끝난 뒤 파일을 추가하세요."); return }
        let supported = Set(["jpg", "jpeg", "png", "webp"])
        var added = 0
        for url in urls {
            let path = url.standardizedFileURL
            guard path.isFileURL, supported.contains(path.pathExtension.lowercased()), !items.contains(where: { $0.input == path }) else { continue }
            var directory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: path.path, isDirectory: &directory), !directory.boolValue else { continue }
            items.append(ImageToolItem(input: path, originalBytes: fileBytes(path))); added += 1
        }
        table.reloadData()
        if !items.isEmpty && table.selectedRow < 0 { table.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false); showPreview() }
        status.stringValue = added > 0 ? Lf("%d개 이미지 준비 · 원본은 유지하고 새 결과 파일을 만듭니다.", items.count) : L("JPG·PNG·WebP 이미지 파일을 선택하세요. 이미 추가한 파일은 중복으로 넣지 않습니다.")
    }
    @objc private func selectFiles() {
        guard !busy else { return }
        let panel = NSOpenPanel(); panel.allowedFileTypes = ["jpg", "jpeg", "png", "webp"]; panel.allowsMultipleSelection = true; panel.canChooseDirectories = false
        if panel.runModal() == .OK { addFiles(panel.urls) }
    }
    @objc private func removeSelected() {
        guard !busy else { return }
        for index in table.selectedRowIndexes.sorted(by: >) where items.indices.contains(index) { items.remove(at: index) }
        table.reloadData(); showPreview()
    }
    @objc private func clearFiles() { guard !busy else { return }; items.removeAll(); table.reloadData(); preview.image = nil; previewLabel.stringValue = L("이미지를 선택하면 미리보기가 표시됩니다."); status.stringValue = L("파일을 선택하거나 놓으세요.") }
    @objc private func changeFormat() { quality.isEnabled = !busy && format.indexOfSelectedItem != 1; qualityLabel.textColor = quality.isEnabled ? .labelColor : .secondaryLabelColor }
    @objc private func updateQuality() { qualityLabel.stringValue = String(quality.integerValue) }
    @objc private func changePercent() {
        let manual = percent.indexOfSelectedItem == 0
        width.isEnabled = !busy && manual; height.isEnabled = !busy && manual
        if !manual { width.stringValue = ""; height.stringValue = "" }
    }
    @objc private func pickOutputDirectory() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true; panel.directoryURL = outputDirectory
        if panel.runModal() == .OK, let url = panel.url { outputDirectory = url; outputLabel.stringValue = url.path }
    }
    private func setBusy(_ value: Bool) {
        busy = value; controls.forEach { $0.isEnabled = !value }
        if value { progress.startAnimation(nil) } else { progress.stopAnimation(nil); changeFormat(); changePercent() }
    }
    private func dimension(_ field: NSTextField) -> Int? {
        let value = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty { return 0 }
        guard value.allSatisfy({ $0.isASCII && $0.isNumber }), let number = Int(value), (1...30000).contains(number) else { return nil }
        return number
    }
    @objc private func processImages() {
        guard !busy, !items.isEmpty else { status.stringValue = L("처리할 이미지를 먼저 선택하세요."); return }
        guard let requestedWidth = dimension(width), let requestedHeight = dimension(height) else { status.stringValue = L("가로·세로에는 1~30000 픽셀을 입력하거나 빈칸으로 두세요."); return }
        if ratio.state == .off && (requestedWidth == 0) != (requestedHeight == 0) { status.stringValue = L("비율 유지 없이 크기를 바꾸려면 가로와 세로를 모두 입력하세요."); return }
        let selectedPercent = [100, 25, 50, 75][percent.indexOfSelectedItem]
        let job: [String: Any] = ["op": "image_process", "inputs": items.map { $0.input.path }, "output_dir": outputDirectory.path, "format": ["jpg", "png", "webp"][format.indexOfSelectedItem], "quality": quality.integerValue, "width": requestedWidth, "height": requestedHeight, "keep_ratio": ratio.state == .on, "no_upscale": upscale.state != .on, "scale_percent": selectedPercent]
        setBusy(true); status.stringValue = Lf("%d개 이미지를 이 컴퓨터에서 처리하는 중…", items.count)
        LocalEngine.run(job: job) { [weak self] result in
            guard let self = self else { return }
            self.setBusy(false)
            let results = result.data["results"] as? [[String: Any]] ?? []
            for row in results {
                guard let input = row["input"] as? String, let index = self.items.firstIndex(where: { $0.input.path == input }) else { continue }
                guard row["success"] as? Bool == true, let output = row["output"] as? String else { self.items[index].result = row["error"] as? String ?? L("처리 실패"); continue }
                let url = URL(fileURLWithPath: output)
                let original = (row["input_bytes"] as? NSNumber)?.int64Value ?? self.items[index].originalBytes
                let converted = (row["output_bytes"] as? NSNumber)?.int64Value ?? self.fileBytes(url)
                self.items[index].output = url; self.items[index].outputBytes = converted
                let saved = original - converted
                let percentage = original > 0 ? Double(abs(saved)) / Double(original) * 100 : 0
                self.items[index].result = saved > 0 ? Lf("%@ 감소 (%.1f%%)", self.bytes(saved), percentage) : saved < 0 ? Lf("%@ 증가 (+%.1f%%)", self.bytes(-saved), percentage) : L("용량 변화 없음")
            }
            self.table.reloadData(); self.showPreview()
            self.status.stringValue = results.isEmpty ? L(result.message) : Lf("%d개 중 %d개 처리 완료. 결과 용량은 실제 파일 기준입니다.", results.count, results.filter { $0["success"] as? Bool == true }.count)
            if result.success && results.isEmpty { self.status.stringValue = Lf("%d개 결과를 저장했습니다. %@", result.files.count, result.message) }
        }
    }
    @objc private func openOutputDirectory() {
        do { try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true); NSWorkspace.shared.open(outputDirectory) }
        catch { status.stringValue = Lf("폴더를 열지 못했습니다: %@", error.localizedDescription) }
    }
    @objc private func openSelectedResult() {
        guard items.indices.contains(table.selectedRow), let output = items[table.selectedRow].output else { status.stringValue = L("실행 후 결과 파일을 선택하세요."); return }
        NSWorkspace.shared.open(output)
    }
    @objc private func editSelected() {
        guard !busy, items.indices.contains(table.selectedRow) else { status.stringValue = L("편집할 이미지 한 장을 선택하세요."); return }
        let url = items[table.selectedRow].output ?? items[table.selectedRow].input
        if captureLoadImage(url) != nil { openEditor(url); return }
        // WebP decoding on older macOS uses the same bundled local converter as batch work.
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("LocalTools-ImagePreview", isDirectory: true)
        setBusy(true)
        LocalEngine.run(job: ["op": "image_process", "inputs": [url.path], "output_dir": temp.path, "format": "png", "quality": 100, "width": 0, "height": 0, "keep_ratio": true, "no_upscale": true, "scale_percent": 100]) { [weak self] result in
            guard let self = self else { return }; self.setBusy(false)
            if let png = result.files.first, result.success, captureLoadImage(png) != nil { self.openEditor(png) }
            else { self.status.stringValue = Lf("이미지를 열지 못했습니다. %@", result.message) }
        }
    }
    private func openEditor(_ url: URL) {
        let editor = CaptureEditorController(imageURL: url, saveDirectory: outputDirectory)
        editors.removeAll { $0.window?.isVisible == false }; editors.append(editor); editor.showWindow(nil)
    }
    func numberOfRows(in tableView: NSTableView) -> Int { items.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard items.indices.contains(row), let column = tableColumn else { return nil }
        let item = items[row]
        let text: String
        switch column.identifier.rawValue {
        case "file": text = item.input.lastPathComponent
        case "original": text = bytes(item.originalBytes)
        case "output": text = item.outputBytes.map(bytes) ?? "—"
        default: text = L(item.result)
        }
        let label = NSTextField(labelWithString: text); label.lineBreakMode = .byTruncatingMiddle; label.font = NSFont.systemFont(ofSize: 12)
        label.toolTip = column.identifier.rawValue == "file" ? item.input.path : L(item.result); return label
    }
    func tableViewSelectionDidChange(_ notification: Notification) { showPreview() }
    private func showPreview() {
        previewRequest = UUID(); let token = previewRequest
        guard items.indices.contains(table.selectedRow) else { preview.image = nil; previewLabel.stringValue = L("이미지를 선택하면 미리보기가 표시됩니다."); return }
        let item = items[table.selectedRow], url = items[table.selectedRow].output ?? items[table.selectedRow].input
        previewLabel.stringValue = "\(url.lastPathComponent) · \(bytes(item.outputBytes ?? item.originalBytes))"
        if let image = captureLoadImage(url) { preview.image = image; return }
        preview.image = nil
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("LocalTools-ImagePreview", isDirectory: true)
        LocalEngine.run(job: ["op": "image_process", "inputs": [url.path], "output_dir": temp.path, "format": "png", "quality": 100, "width": 720, "height": 480, "keep_ratio": true, "no_upscale": true, "scale_percent": 100]) { [weak self] result in
            guard let self = self, self.previewRequest == token else { return }
            if result.success, let file = result.files.first { self.preview.image = captureLoadImage(file) }
            if self.preview.image == nil { self.previewLabel.stringValue = Lf("미리보기를 표시할 수 없습니다. %@", result.message) }
        }
    }
}
