import AppKit
import PDFKit

private func documentToolsValidRange(_ value: String, count: Int) -> Bool {
    guard count > 0 else { return false }
    let text = value.trimmingCharacters(in: .whitespacesAndNewlines); if text.isEmpty { return count > 0 }
    let parts = text.split(whereSeparator: { $0 == "," || $0 == ";" || $0.isWhitespace })
    guard !parts.isEmpty else { return false }
    return parts.allSatisfy { part in
        let ends = part.split(separator: "-", omittingEmptySubsequences: false)
        guard (1...2).contains(ends.count), ends.allSatisfy({ !$0.isEmpty && $0.allSatisfy({ $0.isASCII && $0.isNumber }) }), let start = Int(ends[0]), (1...count).contains(start) else { return false }
        if ends.count == 1 { return true }; guard let end = Int(ends[1]) else { return false }; return start <= end && end <= count
    }
}

func documentToolsSelfCheck() -> Bool {
    documentToolsValidRange("1-3, 5; 8-12", count: 12) &&
    documentToolsValidRange("1\n3-4", count: 4) &&
    documentToolsValidRange("", count: 4) &&
    !documentToolsValidRange("0,2", count: 4) &&
    !documentToolsValidRange("2-1", count: 4) &&
    !documentToolsValidRange("1-5", count: 4) &&
    !documentToolsValidRange("-2", count: 4) &&
    !documentToolsValidRange("1.5", count: 4) &&
    !documentToolsValidRange("1--3", count: 4) &&
    documentMovedSelection(IndexSet([1, 2]), count: 5, delta: -1) == IndexSet([0, 1]) &&
    documentMovedSelection(IndexSet([1, 3]), count: 5, delta: 1) == IndexSet([2, 4]) &&
    documentMovedSelection(IndexSet([0, 1]), count: 5, delta: -1) == nil &&
    documentMovedSelection(IndexSet([3, 4]), count: 5, delta: 1) == nil &&
    documentMovedSelection(IndexSet(), count: 5, delta: 1) == nil &&
    documentMovedSelection(IndexSet([9]), count: 5, delta: 1) == nil
}

private struct DocumentInput {
    let url: URL
    var count: Int
}

private struct DocumentPage {
    let number: Int
    var rotation: Int = 0
}

/// A one-step move preserves every selected page and its relative order.
private func documentMovedSelection(_ selection: IndexSet, count: Int, delta: Int) -> IndexSet? {
    guard !selection.isEmpty, [-1, 1].contains(delta),
          selection.allSatisfy({ (0..<count).contains($0) }),
          let first = selection.first, let last = selection.last,
          (delta < 0 ? first > 0 : last < count - 1) else { return nil }
    return IndexSet(selection.map { $0 + delta })
}

private final class DocumentWorkspaceSplitView: NSSplitView {
    var preferredPageWidth: CGFloat = 292
    override func adjustSubviews() {
        guard subviews.count == 2, bounds.width > 0 else { super.adjustSubviews(); return }
        if subviews[0].isHidden { subviews[1].frame = bounds; return }
        let available = max(0, bounds.width - dividerThickness)
        let width = min(max(260, preferredPageWidth), max(260, available - 280))
        subviews[0].frame = NSRect(x: 0, y: 0, width: min(width, available), height: bounds.height)
        subviews[1].frame = NSRect(x: min(width, available) + dividerThickness, y: 0,
                                 width: max(0, available - width), height: bounds.height)
    }
}

/// Native PDF preview and page controls. Processing uses the bundled local engine.
final class DocumentToolsController: NSObject, NSTableViewDataSource, NSTableViewDelegate, NSSplitViewDelegate {
    private enum Mode: Int, CaseIterable {
        case merge, extract, manage, images, render, annotate
        var title: String {
            switch self {
            case .merge: return "PDF 합치기"
            case .extract: return "PDF 분리 · 페이지 추출"
            case .manage: return "PDF 페이지 관리"
            case .images: return "이미지 → PDF"
            case .render: return "PDF → 이미지"
            case .annotate: return "PDF 위에 내용 추가 / 서명 / 주석"
            }
        }
    }
    private let fileType = NSPasteboard.PasteboardType("local.galaxycontrol.document-files")
    private let pageType = NSPasteboard.PasteboardType("local.galaxycontrol.document-pages")
    private let workQueue = DispatchQueue(label: "local.galaxycontrol.pdf-thumbnails", qos: .userInitiated)
    private var rootView: NSView?
    private var files: [DocumentInput] = []
    private var pages: [DocumentPage] = []
    private var thumbnails: [String: NSImage] = [:]
    private var requestedThumbnails = Set<String>()
    private var thumbnailDocument: PDFDocument?
    private var thumbnailDocumentURL: URL?
    private var previewDocument: PDFDocument?
    private var currentSource: URL?
    private var annotationSource: URL?
    private var previewGeneration = 0
    private var editors: [CaptureEditorController] = []
    private var closeObservers: [NSObjectProtocol] = []
    private var lastFiles: [URL] = []
    private var busy = false
    private let modeMenu = NSPopUpButton()
    private let fileTable = NSTableView()
    private let pageTable = NSTableView()
    private let preview = PDFView()
    private let imagePreview = NSImageView()
    private let status = NSTextField(wrappingLabelWithString: "파일을 선택하거나 목록에 끌어 놓으세요. 원본을 유지하고 새 결과를 저장합니다.")
    private let folderLabel = NSTextField(labelWithString: "")
    private let range = NSTextField(string: "")
    private let format = NSPopUpButton()
    private let resolution = NSPopUpButton()
    private let paper = NSPopUpButton()
    private let orientation = NSPopUpButton()
    private let margin = NSTextField(string: "12")
    private var settingsRows: [NSView] = []
    private var pageButtons: [NSButton] = []
    private var runButton: NSButton!
    private var addButton: NSButton!
    private var pagePanel: NSStackView!
    private var instruction = NSTextField(wrappingLabelWithString: "")
    private var clipboardSources: [URL] = []
    private var intakeDropCard: GalaxyFileDropCard?
    private let workspace = DocumentWorkspaceSplitView()
    private let pageSummary = NSTextField(labelWithString: "")
    private let previewSummary = NSTextField(labelWithString: "미리보기")
    private var fileScroll: NSScrollView!
    private var fileHeight: NSLayoutConstraint!
    private var workspaceHeight: NSLayoutConstraint!
    private var pageActions: NSStackView!
    private var extractButton: NSButton!
    private var selectAllButton: NSButton!
    private var detailButton: NSButton!
    private var detailsPopover: NSPopover!
    private var languageObserver: NSObjectProtocol?
    private var refreshingTableSelection = false
    private var modeWasChosenByUser = false

    private var mode: Mode { Mode(rawValue: modeMenu.indexOfSelectedItem) ?? .merge }
    private var outputDirectory: URL {
        if let p = UserDefaults.standard.string(forKey: "document.outputDirectory"), !p.isEmpty { return URL(fileURLWithPath: p, isDirectory: true) }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/GalaxyControl", isDirectory: true)
    }
    private func label(_ text: String, bold: Bool = false) -> NSTextField {
        let v = NSTextField(labelWithString: text)
        v.font = .systemFont(ofSize: 13, weight: bold ? .semibold : .regular)
        return v
    }
    private func button(_ title: String, _ action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action); b.bezelStyle = .rounded; return b
    }
    private func iconButton(_ symbol: String, _ title: String, _ action: Selector) -> NSButton {
        let b = button("", action); b.image = NSImage(systemSymbolName: symbol, accessibilityDescription: L(title)); b.imagePosition = .imageOnly
        b.toolTip = L(title); b.setAccessibilityLabel(L(title)); b.widthAnchor.constraint(equalToConstant: 32).isActive = true; return b
    }
    private func row(_ items: [NSView]) -> NSStackView {
        let v = NSStackView(views: items); v.orientation = .horizontal; v.alignment = .centerY; v.spacing = 8; return v
    }
    private func tableScroll(_ table: NSTableView, id: String, title: String) -> NSScrollView {
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id)); column.title = title; column.width = 250
        table.addTableColumn(column); table.dataSource = self; table.delegate = self
        table.allowsMultipleSelection = true; table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        table.usesAlternatingRowBackgroundColors = true
        table.registerForDraggedTypes(GalaxyFileIntake.types + [fileType, pageType]); table.setDraggingSourceOperationMask(.move, forLocal: true)
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder; scroll.documentView = table
        return scroll
    }

    func makeView() -> NSView {
        if let view = rootView { return view }
        let root = GalaxyFileDropView(frame: .zero); rootView = root
        root.acceptPasteboard = { [weak self] board in self?.consumePasteboard(board) ?? false }; root.canAccept = { [weak self] in self?.busy == false }
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 12), stack.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -12), stack.topAnchor.constraint(equalTo: root.topAnchor, constant: 12), stack.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -12)])
        modeMenu.addItems(withTitles: Mode.allCases.map(\.title)); modeMenu.target = self; modeMenu.action = #selector(chooseMode)
        modeMenu.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        addButton = button("파일 선택…", #selector(chooseFiles)); runButton = button("새 결과 만들기", #selector(run))
        let top = row([modeMenu, addButton, button("붙여넣기", #selector(pasteButton)), iconButton("minus", "목록에서 삭제", #selector(removeFiles)), iconButton("arrow.up", "위로", #selector(fileUp)), iconButton("arrow.down", "아래로", #selector(fileDown))])
        stack.addArrangedSubview(top); top.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        let drop = GalaxyFileDropCard(symbolName: "doc.on.doc", detail: "PDF  /  이미지 → PDF: JPG · PNG · WebP  /  ⌘V 또는 Ctrl+V로 붙여넣기")
        drop.acceptPasteboard = root.acceptPasteboard; drop.canAccept = root.canAccept
        drop.chooseFiles = { [weak self] in self?.chooseFiles() }; drop.paste = { [weak self] in self?.pasteFromClipboard() ?? false }
        stack.addArrangedSubview(drop); drop.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true; intakeDropCard = drop
        instruction.font = .systemFont(ofSize: 11); instruction.textColor = .secondaryLabelColor; instruction.maximumNumberOfLines = 2
        stack.addArrangedSubview(instruction)
        fileScroll = tableScroll(fileTable, id: "file", title: "파일 · 끌어서 순서 변경")
        fileTable.rowHeight = 27; fileTable.headerView?.frame.size.height = 17
        stack.addArrangedSubview(fileScroll); fileScroll.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        fileHeight = fileScroll.heightAnchor.constraint(equalToConstant: 44); fileHeight.isActive = true

        workspace.isVertical = true; workspace.dividerStyle = .thin; workspace.delegate = self
        workspace.translatesAutoresizingMaskIntoConstraints = false
        workspace.setAccessibilityLabel(L("페이지 목록과 미리보기")); workspace.setAccessibilityHelp(L("가운데 분할선을 좌우로 끌어 목록과 미리보기의 폭을 조절하세요."))
        let pagesBox = NSView(frame: NSRect(x: 0, y: 0, width: 292, height: 420))
        let previewBox = NSView(frame: NSRect(x: 293, y: 0, width: 500, height: 420))
        workspace.addSubview(pagesBox); workspace.addSubview(previewBox)
        pagePanel = NSStackView(); pagePanel.orientation = .vertical; pagePanel.alignment = .leading; pagePanel.spacing = 6
        pagePanel.translatesAutoresizingMaskIntoConstraints = false; pagesBox.addSubview(pagePanel)
        NSLayoutConstraint.activate([pagePanel.leadingAnchor.constraint(equalTo: pagesBox.leadingAnchor, constant: 8), pagePanel.trailingAnchor.constraint(equalTo: pagesBox.trailingAnchor, constant: -10), pagePanel.topAnchor.constraint(equalTo: pagesBox.topAnchor, constant: 8), pagePanel.bottomAnchor.constraint(equalTo: pagesBox.bottomAnchor, constant: -8)])
        let pageTitle = label("페이지", bold: true); selectAllButton = button("전체 선택", #selector(selectAllPages)); selectAllButton.controlSize = .small; selectAllButton.font = .systemFont(ofSize: 11)
        let pageHeader = row([pageTitle, selectAllButton]); pagePanel.addArrangedSubview(pageHeader)
        pageSummary.font = .systemFont(ofSize: 11); pageSummary.textColor = .secondaryLabelColor; pageSummary.lineBreakMode = .byTruncatingTail
        pagePanel.addArrangedSubview(pageSummary)
        let pageScroll = tableScroll(pageTable, id: "page", title: "페이지")
        pageTable.rowHeight = 124; pageTable.headerView = nil; pageTable.selectionHighlightStyle = .regular
        pageTable.setAccessibilityLabel(L("PDF 페이지 목록")); pageTable.setAccessibilityHelp(L("페이지를 선택하거나 끌어서 순서를 바꾸세요. Shift 또는 ⌘ 키로 여러 페이지를 선택합니다."))
        pageScroll.setContentHuggingPriority(.defaultLow, for: .vertical)
        pagePanel.addArrangedSubview(pageScroll)
        for view in [pageHeader, pageSummary, pageScroll] { view.widthAnchor.constraint(equalTo: pagePanel.widthAnchor).isActive = true }
        func pageAction(_ symbol: String, _ title: String, _ action: Selector) -> NSButton {
            let b = button(title, action); b.image = NSImage(systemSymbolName: symbol, accessibilityDescription: L(title)); b.imagePosition = .imageAbove
            b.bezelStyle = .regularSquare; b.font = .systemFont(ofSize: 11); b.toolTip = L(title); b.setAccessibilityLabel(L(title))
            b.widthAnchor.constraint(equalToConstant: 53).isActive = true; b.heightAnchor.constraint(equalToConstant: 44).isActive = true; return b
        }
        let up = pageAction("arrow.up", "위로", #selector(pageUp)), down = pageAction("arrow.down", "아래로", #selector(pageDown)), rotate = pageAction("rotate.right", "회전", #selector(rotatePages)), delete = pageAction("trash", "삭제", #selector(removePages))
        rotate.toolTip = L("90° 회전")
        pageButtons = [up, down, rotate, delete]; pageActions = row(pageButtons); pageActions.spacing = 6; pagePanel.addArrangedSubview(pageActions)
        extractButton = button("선택 추출", #selector(extractSelection)); pagePanel.addArrangedSubview(extractButton)
        extractButton.widthAnchor.constraint(equalTo: pagePanel.widthAnchor).isActive = true

        preview.autoScales = true; preview.displayMode = .singlePage; preview.backgroundColor = .controlBackgroundColor
        previewSummary.font = .systemFont(ofSize: 12, weight: .semibold); previewSummary.lineBreakMode = .byTruncatingTail
        previewSummary.translatesAutoresizingMaskIntoConstraints = false; previewBox.addSubview(previewSummary)
        let canvas = NSView(); canvas.wantsLayer = true; canvas.layer?.cornerRadius = 8; canvas.layer?.backgroundColor = NSColor.controlBackgroundColor.cgColor
        for view in [preview, imagePreview] { view.translatesAutoresizingMaskIntoConstraints = false; canvas.addSubview(view); NSLayoutConstraint.activate([view.leadingAnchor.constraint(equalTo: canvas.leadingAnchor), view.trailingAnchor.constraint(equalTo: canvas.trailingAnchor), view.topAnchor.constraint(equalTo: canvas.topAnchor), view.bottomAnchor.constraint(equalTo: canvas.bottomAnchor)]) }
        imagePreview.imageScaling = .scaleProportionallyUpOrDown; imagePreview.isHidden = true
        canvas.translatesAutoresizingMaskIntoConstraints = false; previewBox.addSubview(canvas)
        NSLayoutConstraint.activate([previewSummary.leadingAnchor.constraint(equalTo: previewBox.leadingAnchor, constant: 10), previewSummary.trailingAnchor.constraint(equalTo: previewBox.trailingAnchor, constant: -8), previewSummary.topAnchor.constraint(equalTo: previewBox.topAnchor, constant: 8), previewSummary.heightAnchor.constraint(equalToConstant: 18), canvas.leadingAnchor.constraint(equalTo: previewBox.leadingAnchor, constant: 10), canvas.trailingAnchor.constraint(equalTo: previewBox.trailingAnchor, constant: -8), canvas.topAnchor.constraint(equalTo: previewSummary.bottomAnchor, constant: 6), canvas.bottomAnchor.constraint(equalTo: previewBox.bottomAnchor, constant: -8)])
        stack.addArrangedSubview(workspace); workspace.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        workspace.heightAnchor.constraint(greaterThanOrEqualToConstant: 300).isActive = true
        workspaceHeight = workspace.heightAnchor.constraint(greaterThanOrEqualToConstant: 420); workspaceHeight.priority = .defaultHigh; workspaceHeight.isActive = true
        workspace.setContentHuggingPriority(.defaultLow, for: .vertical)

        range.placeholderString = "비우면 전체 · 예: 1-3, 5, 8-12"; range.widthAnchor.constraint(equalToConstant: 270).isActive = true
        format.addItems(withTitles: ["PNG", "JPG"]); resolution.addItems(withTitles: ["72 dpi", "150 dpi", "300 dpi"]); resolution.selectItem(at: 1)
        paper.addItems(withTitles: ["A4", "이미지 크기에 맞춤"]); orientation.addItems(withTitles: ["세로", "가로"]); margin.widthAnchor.constraint(equalToConstant: 55).isActive = true
        settingsRows = [row([label("페이지 범위"), range]), row([label("출력 형식"), format, label("해상도"), resolution]), row([label("페이지 크기"), paper]), row([label("방향"), orientation, label("여백 (mm)"), margin])]
        let settings = NSStackView(views: settingsRows); settings.orientation = .vertical; settings.alignment = .leading; settings.spacing = 12; settings.translatesAutoresizingMaskIntoConstraints = false
        let settingsView = NSView(); settingsView.addSubview(settings)
        NSLayoutConstraint.activate([settings.leadingAnchor.constraint(equalTo: settingsView.leadingAnchor, constant: 16), settings.trailingAnchor.constraint(equalTo: settingsView.trailingAnchor, constant: -16), settings.topAnchor.constraint(equalTo: settingsView.topAnchor, constant: 16), settings.bottomAnchor.constraint(equalTo: settingsView.bottomAnchor, constant: -16)])
        let settingsController = NSViewController(); settingsController.view = settingsView
        detailsPopover = NSPopover(); detailsPopover.contentViewController = settingsController; detailsPopover.behavior = .transient
        detailButton = button("세부 설정", #selector(showDetails))
        folderLabel.stringValue = outputDirectory.path; folderLabel.lineBreakMode = .byTruncatingMiddle; folderLabel.font = .systemFont(ofSize: 11); folderLabel.textColor = .secondaryLabelColor
        folderLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal); folderLabel.toolTip = outputDirectory.path
        let actions = row([runButton, detailButton, button("저장 폴더…", #selector(chooseFolder)), iconButton("doc", "결과 열기", #selector(openResult)), iconButton("folder", "폴더 열기", #selector(openFolder)), folderLabel]); stack.addArrangedSubview(actions)
        actions.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        status.font = .systemFont(ofSize: 11); status.textColor = .secondaryLabelColor; status.maximumNumberOfLines = 2; stack.addArrangedSubview(status)
        for v in [instruction, status] { v.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true }
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            let fileSelection = self.fileTable.selectedRowIndexes, pageSelection = self.pageTable.selectedRowIndexes
            self.refreshingTableSelection = true
            self.fileTable.reloadData(); self.fileTable.selectRowIndexes(fileSelection, byExtendingSelection: false)
            self.pageTable.reloadData(); self.pageTable.selectRowIndexes(pageSelection, byExtendingSelection: false)
            self.refreshingTableSelection = false; self.refreshPageState()
            self.workspace.setAccessibilityLabel(L("페이지 목록과 미리보기")); self.workspace.setAccessibilityHelp(L("가운데 분할선을 좌우로 끌어 목록과 미리보기의 폭을 조절하세요."))
            self.pageTable.setAccessibilityLabel(L("PDF 페이지 목록")); self.pageTable.setAccessibilityHelp(L("페이지를 선택하거나 끌어서 순서를 바꾸세요. Shift 또는 ⌘ 키로 여러 페이지를 선택합니다."))
            self.localizeSettings(self.detailsPopover.contentViewController!.view)
        }
        modeChanged(); return root
    }

    @objc private func showDetails() {
        guard !busy else { return }
        localizeSettings(detailsPopover.contentViewController!.view)
        detailsPopover.contentSize = NSSize(width: 450, height: mode == .extract ? 64 : 104)
        detailsPopover.show(relativeTo: detailButton.bounds, of: detailButton, preferredEdge: .maxY)
    }

    private func localizeSettings(_ view: NSView) {
        if let text = view as? NSTextField {
            if !text.isEditable { text.stringValue = L(text.stringValue) }
            if let placeholder = text.placeholderString { text.placeholderString = L(placeholder) }
        }
        if let menu = view as? NSPopUpButton { menu.itemArray.forEach { $0.title = L($0.title) } }
        view.subviews.forEach { localizeSettings($0) }
    }

    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposedMinimumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { 260 }
    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposedMaximumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat { max(260, splitView.bounds.width - splitView.dividerThickness - 280) }
    func splitView(_ splitView: NSSplitView, additionalEffectiveRectOfDividerAt dividerIndex: Int) -> NSRect {
        guard let first = splitView.subviews.first else { return .zero }; return NSRect(x: first.frame.maxX - 4, y: 0, width: splitView.dividerThickness + 8, height: splitView.bounds.height)
    }
    func splitViewDidResizeSubviews(_ notification: Notification) {
        guard workspace.subviews.count == 2 else { return }; workspace.preferredPageWidth = workspace.subviews[0].frame.width
    }

    @objc private func chooseMode() { modeWasChosenByUser = true; modeChanged() }
    @objc private func modeChanged() {
        settingsRows[0].isHidden = !(mode == .extract || mode == .render)
        settingsRows[1].isHidden = mode != .render; settingsRows[2].isHidden = mode != .images; settingsRows[3].isHidden = mode != .images
        detailButton.isHidden = !(mode == .extract || mode == .render || mode == .images)
        detailsPopover.close()
        runButton.title = mode == .annotate ? "선택 페이지에 내용 추가…" : "새 결과 만들기"
        switch mode {
        case .merge: instruction.stringValue = "PDF 파일 목록을 끌어 순서를 바꾼 뒤 합치세요."
        case .extract: instruction.stringValue = "PDF 한 개를 선택하고 페이지 범위를 입력하세요. 쉼표·공백·줄바꿈으로 구분할 수 있습니다."
        case .manage: instruction.stringValue = "페이지를 끌어 순서를 바꾸거나 선택 후 삭제·회전하세요. 선택 추출은 별도 PDF를 만듭니다."
        case .images: instruction.stringValue = "JPG·PNG·WebP 이미지를 선택하세요. 목록 순서대로 한 PDF를 만들며 사진 비율을 유지합니다."
        case .render: instruction.stringValue = "PDF 한 개를 PNG/JPG로 변환합니다. 페이지 범위를 비우면 전체 페이지를 순서대로 저장합니다."
        case .annotate: instruction.stringValue = "기존 문장은 그대로 두고 글자·선·도형·체크·서명을 덧붙입니다. 편집창의 ‘주석 적용’으로 새 PDF를 만드세요."
        }
        if mode == .images && files.contains(where: { $0.url.pathExtension.lowercased() == "pdf" }) { clearFiles() }
        if mode != .images && files.contains(where: { $0.url.pathExtension.lowercased() != "pdf" }) { clearFiles() }
        loadSelection()
    }
    private func refreshPageState() {
        guard rootView != nil else { return }
        let selection = pageTable.selectedRowIndexes
        pageSummary.stringValue = pages.isEmpty ? L("페이지를 선택하면 크게 볼 수 있습니다.") : Lf("%d개 페이지 · %d개 선택", pages.count, selection.count)
        if let first = selection.first, pages.indices.contains(first) { previewSummary.stringValue = Lf("미리보기 · %d / %d페이지", first + 1, pages.count) }
        else { previewSummary.stringValue = L("미리보기") }
        let editable = !busy && mode == .manage && !selection.isEmpty
        pageButtons[0].isEnabled = editable && documentMovedSelection(selection, count: pages.count, delta: -1) != nil
        pageButtons[1].isEnabled = editable && documentMovedSelection(selection, count: pages.count, delta: 1) != nil
        pageButtons[2].isEnabled = editable
        pageButtons[3].isEnabled = editable && selection.count < pages.count
        pageActions.isHidden = mode != .manage
        selectAllButton.isEnabled = !busy && !pages.isEmpty
        extractButton.isEnabled = !busy && !selection.isEmpty
        extractButton.isHidden = mode == .images
        intakeDropCard?.isHidden = !files.isEmpty
        fileScroll.isHidden = files.isEmpty
        fileHeight.constant = mode == .merge || mode == .images ? 72 : 44
        workspaceHeight.constant = files.isEmpty ? 340 : 420
        if mode == .images {
            workspace.subviews.first?.isHidden = true
            if let pane = workspace.subviews.last { pane.frame = workspace.bounds }
        } else {
            workspace.subviews.first?.isHidden = false; workspace.adjustSubviews()
        }
    }
    @objc private func selectAllPages() { guard !busy else { return }; pageTable.selectAll(nil); refreshPageState() }
    private func clearFiles() { files.removeAll(); pages.removeAll(); fileTable.reloadData(); pageTable.reloadData(); preview.document = nil; imagePreview.image = nil; currentSource = nil; annotationSource = nil; refreshPageState() }
    private func setBusy(_ value: Bool) { busy = value; runButton.isEnabled = !value; addButton.isEnabled = !value; modeMenu.isEnabled = !value; detailButton.isEnabled = !value; refreshPageState() }
    private func updateAutomaticPDFMode(adding items: [DocumentInput]) -> Bool {
        guard !modeWasChosenByUser, items.contains(where: { $0.url.pathExtension.lowercased() == "pdf" }) else { return false }
        if mode == .merge && files.isEmpty && items.count == 1 {
            modeMenu.selectItem(at: Mode.manage.rawValue); return true
        }
        if mode == .manage && files.count + items.count > 1 {
            modeMenu.selectItem(at: Mode.merge.rawValue); return true
        }
        return false
    }
    @objc private func chooseFiles() {
        guard !busy else { return }; let panel = NSOpenPanel(); panel.allowsMultipleSelection = true
        panel.allowedFileTypes = mode == .images ? ["jpg", "jpeg", "png", "webp"] : ["pdf"]
        if panel.runModal() == .OK { addFiles(panel.urls) }
    }
    @discardableResult func pasteFromClipboard() -> Bool { _ = makeView(); return consumePasteboard(.general) }
    @objc private func pasteButton() {
        if !pasteFromClipboard() && !busy { status.stringValue = L("클립보드에 이미지나 파일이 없습니다. 파일을 놓거나 선택하세요.") }
    }
    private func consumePasteboard(_ board: NSPasteboard) -> Bool {
        guard !busy else { status.stringValue = L("현재 작업이 끝난 뒤 파일을 추가하세요."); return false }
        let urls = GalaxyFileIntake.files(from: board)
        if !urls.isEmpty { _ = addFiles(urls); return true }
        do {
            guard let source = try GalaxyFileIntake.imageSource(from: board) else { return false }
            if !files.isEmpty && mode != .images {
                try? FileManager.default.removeItem(at: source.deletingLastPathComponent())
                status.stringValue = L("PDF 목록은 그대로 두었습니다. 이미지를 넣으려면 ‘이미지 → PDF’를 선택하세요."); return true
            }
            clipboardSources.append(source); return addFiles([source])
        } catch { status.stringValue = Lf("클립보드 이미지를 준비하지 못했습니다: %@", error.localizedDescription); return true }
    }
    @discardableResult private func addFiles(_ urls: [URL]) -> Bool {
        guard !busy else { return false }
        let images = urls.filter { ["jpg", "jpeg", "png", "webp"].contains($0.pathExtension.lowercased()) }
        let pdfs = urls.filter { $0.pathExtension.lowercased() == "pdf" }
        if mode != .images && files.isEmpty && pdfs.isEmpty && !images.isEmpty { modeMenu.selectItem(at: Mode.images.rawValue); modeChanged() }
        if mode == .images && files.isEmpty && !pdfs.isEmpty && images.isEmpty { modeMenu.selectItem(at: Mode.merge.rawValue); modeChanged() }
        if mode != .images && !files.isEmpty && pdfs.isEmpty && !images.isEmpty { status.stringValue = L("PDF 목록은 그대로 두었습니다. 이미지를 넣으려면 ‘이미지 → PDF’를 선택하세요."); return true }
        let extensions = mode == .images ? ["jpg", "jpeg", "png", "webp"] : ["pdf"]
        let accepted = urls.filter {
            var directory: ObjCBool = false
            return $0.isFileURL && extensions.contains($0.pathExtension.lowercased()) && FileManager.default.fileExists(atPath: $0.path, isDirectory: &directory) && !directory.boolValue
        }
        guard !accepted.isEmpty else { status.stringValue = "현재 도구에서 지원하는 파일을 선택하세요."; return false }
        setBusy(true); status.stringValue = "파일 정보를 읽는 중…"
        workQueue.async { [weak self] in
            let items = accepted.compactMap { url -> DocumentInput? in
                if url.pathExtension.lowercased() == "pdf" { guard let doc = PDFDocument(url: url), !doc.isLocked, doc.pageCount > 0 else { return nil }; return DocumentInput(url: url, count: doc.pageCount) }
                return DocumentInput(url: url, count: 1)
            }
            DispatchQueue.main.async {
                guard let self = self else { return }
                let changedMode = self.updateAutomaticPDFMode(adding: items)
                self.files += items; self.fileTable.reloadData(); self.setBusy(false)
                if !items.isEmpty { self.fileTable.selectRowIndexes(IndexSet(integer: self.files.count - items.count), byExtendingSelection: false) }
                self.status.stringValue = items.count == accepted.count ? Lf("%@개 파일 · 원본은 유지됩니다.", String(describing: self.files.count)) : "읽을 수 없거나 비밀번호로 잠긴 PDF를 제외했습니다. 비밀번호 보호 PDF는 이번 도구에서 처리하지 않습니다."
                if changedMode { self.modeChanged() } else { self.loadSelection() }
            }
        }
        return true
    }
    @objc private func removeFiles() { guard !busy else { return }; for i in fileTable.selectedRowIndexes.reversed() { files.remove(at: i) }; fileTable.reloadData(); if !files.isEmpty { fileTable.selectRowIndexes(IndexSet(integer: min(max(0, fileTable.selectedRow), files.count - 1)), byExtendingSelection: false) }; loadSelection() }
    @objc private func fileUp() { moveSelectedFiles(-1) }
    @objc private func fileDown() { moveSelectedFiles(1) }
    private func moveSelectedFiles(_ delta: Int) {
        guard !busy, let first = fileTable.selectedRowIndexes.first else { return }
        let target = first + delta; guard files.indices.contains(target) else { return }
        files.swapAt(first, target); fileTable.reloadData(); fileTable.selectRowIndexes(IndexSet(integer: target), byExtendingSelection: false); loadSelection()
    }
    private func loadSelection() {
        guard let index = fileTable.selectedRowIndexes.first, files.indices.contains(index) else { previewGeneration += 1; preview.document = nil; previewDocument = nil; imagePreview.image = nil; pages = []; currentSource = nil; annotationSource = nil; pageTable.reloadData(); refreshPageState(); return }
        let input = files[index]
        if currentSource == input.url && !pages.isEmpty { showPage(); return }
        currentSource = input.url; annotationSource = nil; previewDocument = nil; previewGeneration += 1; let generation = previewGeneration
        pages = input.url.pathExtension.lowercased() == "pdf" ? (1...input.count).map { DocumentPage(number: $0) } : []
        pageTable.reloadData(); if !pages.isEmpty { pageTable.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false) }
        let isPDF = input.url.pathExtension.lowercased() == "pdf"; preview.isHidden = !isPDF; imagePreview.isHidden = isPDF
        refreshPageState()
        workQueue.async { [weak self] in
            let document = isPDF ? PDFDocument(url: input.url) : nil
            let image = isPDF ? nil : NSImage(contentsOf: input.url)
            DispatchQueue.main.async { guard let self = self, generation == self.previewGeneration else { return }; self.previewDocument = document; self.imagePreview.image = image; self.showPage() }
        }
    }
    private func showPage() {
        refreshPageState()
        guard let doc = previewDocument else { return }
        let index = max(0, pageTable.selectedRow)
        guard pages.indices.contains(index), let page = doc.page(at: pages[index].number - 1)?.copy() as? PDFPage else { return }
        page.rotation = (page.rotation + pages[index].rotation) % 360
        let one = PDFDocument(); one.insert(page, at: 0); preview.document = one; preview.autoScales = true
    }
    func numberOfRows(in tableView: NSTableView) -> Int { tableView === fileTable ? files.count : pages.count }
    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        if tableView === fileTable {
            guard files.indices.contains(row) else { return nil }
            let cell = NSTableCellView(); let text = NSTextField(labelWithString: "\(row + 1). \(files[row].url.lastPathComponent)")
            text.font = .systemFont(ofSize: 12); text.lineBreakMode = .byTruncatingMiddle; text.toolTip = files[row].url.path
            let count = NSTextField(labelWithString: files[row].url.pathExtension.lowercased() == "pdf" ? Lf("%d페이지", files[row].count) : L("이미지")); count.font = .systemFont(ofSize: 11); count.textColor = .secondaryLabelColor
            text.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
            for view in [text, count] { view.translatesAutoresizingMaskIntoConstraints = false; cell.addSubview(view) }
            NSLayoutConstraint.activate([text.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 7), text.trailingAnchor.constraint(equalTo: count.leadingAnchor, constant: -12), text.centerYAnchor.constraint(equalTo: cell.centerYAnchor), count.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -9), count.centerYAnchor.constraint(equalTo: cell.centerYAnchor)]); cell.textField = text; return cell
        }
        guard pages.indices.contains(row), let source = currentSource else { return nil }
        let item = pages[row], key = source.path + "#\(item.number)#\(item.rotation)"
        let cell = NSTableCellView(); let img = NSImageView(); img.imageScaling = .scaleProportionallyUpOrDown; img.image = thumbnails[key]
        let text = NSTextField(wrappingLabelWithString: Lf("%d번 페이지\n원본 %d페이지", row + 1, item.number) + (item.rotation == 0 ? "" : "\n↻ \(item.rotation)°")); text.font = .systemFont(ofSize: 12)
        for v in [img, text] { v.translatesAutoresizingMaskIntoConstraints = false; cell.addSubview(v) }
        NSLayoutConstraint.activate([img.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 8), img.centerYAnchor.constraint(equalTo: cell.centerYAnchor), img.widthAnchor.constraint(equalToConstant: 86), img.heightAnchor.constraint(equalToConstant: 112), text.leadingAnchor.constraint(equalTo: img.trailingAnchor, constant: 12), text.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -8), text.centerYAnchor.constraint(equalTo: cell.centerYAnchor)])
        cell.imageView = img; cell.textField = text
        if thumbnails[key] == nil && requestedThumbnails.insert(key).inserted {
            workQueue.async { [weak self] in
                guard let self = self else { return }
                if self.thumbnailDocumentURL != source { self.thumbnailDocument = PDFDocument(url: source); self.thumbnailDocumentURL = source }
                guard let page = self.thumbnailDocument?.page(at: item.number - 1)?.copy() as? PDFPage else { return }
                page.rotation = (page.rotation + item.rotation) % 360
                // PDFKit requires a document owner while drawing a copied page.
                let thumbnailOwner = PDFDocument(); thumbnailOwner.insert(page, at: 0)
                let thumbnail = withExtendedLifetime(thumbnailOwner) { page.thumbnail(of: NSSize(width: 200, height: 272), for: .mediaBox) }
                DispatchQueue.main.async { [weak self, weak img] in
                    guard let self = self else { return }; self.thumbnails[key] = thumbnail
                    if self.currentSource == source { img?.image = thumbnail }
                }
            }
        }
        return cell
    }
    func tableViewSelectionDidChange(_ notification: Notification) {
        guard !refreshingTableSelection else { return }
        if notification.object as? NSTableView === fileTable { loadSelection() } else { showPage() }
    }
    func tableView(_ tableView: NSTableView, pasteboardWriterForRow row: Int) -> NSPasteboardWriting? {
        let item = NSPasteboardItem(); item.setString(String(row), forType: tableView === fileTable ? fileType : pageType); return item
    }
    func tableView(_ tableView: NSTableView, validateDrop info: NSDraggingInfo, proposedRow row: Int, proposedDropOperation operation: NSTableView.DropOperation) -> NSDragOperation {
        guard !busy else { return [] }
        tableView.setDropRow(row, dropOperation: .above)
        if info.draggingSource as? NSTableView === tableView { return tableView === pageTable && mode != .manage ? [] : .move }
        return tableView === fileTable && GalaxyFileIntake.canRead(info.draggingPasteboard) ? .copy : []
    }
    func tableView(_ tableView: NSTableView, acceptDrop info: NSDraggingInfo, row: Int, dropOperation: NSTableView.DropOperation) -> Bool {
        guard !busy, tableView !== pageTable || mode == .manage else { return false }
        if info.draggingSource as? NSTableView !== tableView {
            return consumePasteboard(info.draggingPasteboard)
        }
        let type = tableView === fileTable ? fileType : pageType
        let indices = (info.draggingPasteboard.pasteboardItems ?? []).compactMap { $0.string(forType: type).flatMap(Int.init) }.sorted()
        guard !indices.isEmpty else { return false }
        let originalCount = tableView === fileTable ? files.count : pages.count
        guard indices.allSatisfy({ (0..<originalCount).contains($0) }) else { return false }
        let adjusted = row - indices.filter { $0 < row }.count
        if tableView === fileTable {
            let moved = indices.map { files[$0] }; for i in indices.reversed() { files.remove(at: i) }; let at = max(0, min(adjusted, files.count)); files.insert(contentsOf: moved, at: at); fileTable.reloadData(); fileTable.selectRowIndexes(IndexSet(integersIn: at..<(at + moved.count)), byExtendingSelection: false); loadSelection()
        } else {
            modeWasChosenByUser = true
            let moved = indices.map { pages[$0] }; for i in indices.reversed() { pages.remove(at: i) }; let at = max(0, min(adjusted, pages.count)); pages.insert(contentsOf: moved, at: at); pageTable.reloadData(); pageTable.selectRowIndexes(IndexSet(integersIn: at..<(at + moved.count)), byExtendingSelection: false); showPage()
        }
        return true
    }
    @objc private func pageUp() { movePage(-1) }
    @objc private func pageDown() { movePage(1) }
    private func movePage(_ delta: Int) {
        let selection = pageTable.selectedRowIndexes
        guard !busy, mode == .manage, let moved = documentMovedSelection(selection, count: pages.count, delta: delta) else { return }
        modeWasChosenByUser = true
        for index in delta < 0 ? Array(selection) : Array(selection.reversed()) { pages.swapAt(index, index + delta) }
        pageTable.reloadData(); pageTable.selectRowIndexes(moved, byExtendingSelection: false)
        if let first = moved.first { pageTable.scrollRowToVisible(first) }; showPage()
    }
    @objc private func rotatePages() {
        guard !busy, mode == .manage else { return }; let selection = pageTable.selectedRowIndexes
        if !selection.isEmpty { modeWasChosenByUser = true }
        for i in selection { pages[i].rotation = (pages[i].rotation + 90) % 360 }
        pageTable.reloadData(); pageTable.selectRowIndexes(selection, byExtendingSelection: false); showPage()
    }
    @objc private func removePages() {
        guard !busy, mode == .manage else { return }; let indices = pageTable.selectedRowIndexes
        guard indices.count < pages.count else { status.stringValue = "PDF에는 최소 한 페이지가 있어야 합니다."; return }
        if !indices.isEmpty { modeWasChosenByUser = true }
        let nearby = indices.first ?? 0
        for i in indices.reversed() { pages.remove(at: i) }; pageTable.reloadData(); if !pages.isEmpty { pageTable.selectRowIndexes(IndexSet(integer: min(nearby, pages.count - 1)), byExtendingSelection: false); pageTable.scrollRowToVisible(min(nearby, pages.count - 1)) }; showPage()
    }
    private func selectedPDF() -> URL? {
        guard let i = fileTable.selectedRowIndexes.first, files.indices.contains(i), files[i].url.pathExtension.lowercased() == "pdf" else { status.stringValue = "목록에서 PDF 한 개를 선택하세요."; return nil }; return files[i].url
    }
    private func validRange(_ value: String) -> Bool {
        guard !pages.isEmpty else { return false }
        let limit = files.first(where: { $0.url == currentSource })?.count ?? pages.count
        return documentToolsValidRange(value, count: limit)
    }
    @objc private func run() {
        guard !busy else { return }
        var job: [String: Any] = ["output_dir": outputDirectory.path]
        switch mode {
        case .merge:
            guard files.count >= 2 else { status.stringValue = "합칠 PDF를 두 개 이상 선택하세요."; return }; job["op"] = "pdf_merge"; job["paths"] = files.map { $0.url.path }
        case .images:
            guard !files.isEmpty, let number = Double(margin.stringValue), number.isFinite, number >= 0, number <= 100 else { status.stringValue = "이미지와 0~100mm 범위의 여백을 확인하세요."; return }
            job["op"] = "images_pdf"; job["paths"] = files.map { $0.url.path }; job["page_size"] = paper.indexOfSelectedItem == 0 ? "a4" : "image"; job["orientation"] = orientation.indexOfSelectedItem == 0 ? "portrait" : "landscape"; job["margin_mm"] = number
        case .extract, .render:
            guard let path = selectedPDF(), validRange(range.stringValue) else { status.stringValue = "페이지 범위를 확인하세요. 예: 1-3, 5, 8-12 · 실제 페이지 수 안에서 입력하세요."; return }
            job["op"] = mode == .extract ? "pdf_extract" : "pdf_render"; job["path"] = path.path; job["pages"] = range.stringValue
            if mode == .render { job["format"] = format.indexOfSelectedItem == 0 ? "png" : "jpg"; job["dpi"] = [72, 150, 300][resolution.indexOfSelectedItem] }
        case .manage:
            guard let path = selectedPDF(), !pages.isEmpty else { return }; job["op"] = "pdf_manage"; job["path"] = path.path; job["page_order"] = pages.map(\.number)
            job["rotations"] = Dictionary(uniqueKeysWithValues: pages.map { (String($0.number), $0.rotation) })
        case .annotate: openAnnotation(); return
        }
        perform(job)
    }
    @objc private func extractSelection() {
        guard !busy, let path = selectedPDF() else { return }; let selection = pageTable.selectedRowIndexes
        guard !selection.isEmpty else { status.stringValue = "추출할 페이지를 선택하세요."; return }
        let selected = selection.map { pages[$0] }
        perform(["op": "pdf_manage", "path": path.path, "page_order": selected.map(\.number), "rotations": Dictionary(uniqueKeysWithValues: selected.map { (String($0.number), $0.rotation) }), "output_dir": outputDirectory.path])
    }
    private func perform(_ job: [String: Any], after: ((EngineResult) -> Void)? = nil) {
        setBusy(true); status.stringValue = "컴퓨터에서 처리 중…"
        LocalEngine.run(job: job) { [weak self] result in
            guard let self = self else { return }; self.setBusy(false); self.status.stringValue = result.message
            if result.success { self.lastFiles = result.files; self.status.stringValue = Lf("%@ · %@개 결과 파일", String(describing: result.message), String(describing: result.files.count)) }
            after?(result)
        }
    }
    private func openAnnotation() {
        if let existing = editors.first(where: { $0.window?.isVisible == true }) {
            existing.showWindow(nil); status.stringValue = "열려 있는 주석 창에서 ‘주석 적용’을 누르고 닫은 뒤 다음 페이지를 선택하세요."; return
        }
        guard let path = selectedPDF(), let i = pageTable.selectedRowIndexes.first, pages.indices.contains(i) else { status.stringValue = "내용을 추가할 페이지를 선택하세요."; return }
        let page = pages[i].number, source = annotationSource ?? path
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("GalaxyControl-PDF-\(UUID().uuidString)", isDirectory: true)
        perform(["op": "pdf_render", "path": source.path, "pages": String(page), "format": "png", "dpi": 150, "output_dir": scratch.path]) { [weak self] result in
            guard let self = self, result.success, let image = result.files.first else { return }
            let editor = CaptureEditorController(imageURL: image, saveDirectory: scratch, annotationOnly: true, onSave: { [weak self] overlay in
                guard let self = self, !self.busy else { return }
                self.perform(["op": "pdf_annotate", "path": source.path, "page": page, "overlay_path": overlay.path, "output_dir": self.outputDirectory.path]) { [weak self] output in
                    guard let self = self, output.success, let file = output.files.first else { return }
                    if self.currentSource == path { self.annotationSource = file; self.previewDocument = PDFDocument(url: file); self.showPage() }
                }
            })
            self.editors.append(editor); editor.showWindow(nil)
            if let window = editor.window {
                self.closeObservers.append(NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: window, queue: .main) { [weak self, weak editor] _ in
                    guard let editor = editor else { return }; self?.editors.removeAll { $0 === editor }
                })
            }
            self.status.stringValue = "주석 편집창에서 내용을 추가하고 ‘주석 적용’을 누르세요. 원본 PDF는 유지됩니다."
        }
    }
    @objc private func chooseFolder() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true; panel.directoryURL = outputDirectory
        if panel.runModal() == .OK, let url = panel.url { UserDefaults.standard.set(url.path, forKey: "document.outputDirectory"); folderLabel.stringValue = url.path; folderLabel.toolTip = url.path }
    }
    @objc private func openFolder() { do { try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true); NSWorkspace.shared.open(outputDirectory) } catch { status.stringValue = Lf("폴더를 열 수 없습니다: %@", String(describing: error.localizedDescription)) } }
    @objc private func openResult() { if let file = lastFiles.first { NSWorkspace.shared.open(file) } else { status.stringValue = "먼저 새 결과를 만드세요." } }
    func prepareForQuit() -> Bool {
        if busy {
            let alert = NSAlert(); alert.messageText = "PDF 작업을 마치는 중입니다."; alert.informativeText = "결과가 저장될 때까지 기다린 뒤 앱을 종료하세요."; alert.addButton(withTitle: "확인"); alert.runModal(); return false
        }
        return CaptureEditorController.prepareForQuit(roots: editors)
    }
    deinit {
        if let languageObserver = languageObserver { NotificationCenter.default.removeObserver(languageObserver) }
        closeObservers.forEach { NotificationCenter.default.removeObserver($0) }
        clipboardSources.forEach { try? FileManager.default.removeItem(at: $0.deletingLastPathComponent()) }
    }
}
