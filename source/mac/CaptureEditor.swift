import AppKit
import CoreImage
import ImageIO

private enum CaptureTool: Int, CaseIterable {
    case select, rectangle, ellipse, arrow, line, checkmark, pen, text, blur, pixelate, cover, region, polygon
    var label: String {
        switch self {
        case .select: return L("선택")
        case .rectangle: return L("사각형")
        case .ellipse: return L("원")
        case .arrow: return L("화살표")
        case .line: return L("선")
        case .checkmark: return L("체크 표시")
        case .pen: return L("펜")
        case .text: return L("텍스트")
        case .blur: return L("흐림")
        case .pixelate: return L("모자이크")
        case .cover: return L("가리기")
        case .region: return L("영역 선택")
        case .polygon: return L("다각형 오리기")
        }
    }
}

private enum CaptureNodeKind { case rectangle, ellipse, arrow, line, checkmark, pen, text, image, cover }

private final class CaptureInputField: NSTextField {
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask).subtracting([.capsLock, .numericPad, .function])
        guard mods == .control, let editor = currentEditor() as? NSTextView else { return super.performKeyEquivalent(with: event) }
        switch event.charactersIgnoringModifiers?.lowercased() {
        case "c": editor.copy(nil); return true
        case "v": editor.paste(nil); return true
        default: return super.performKeyEquivalent(with: event)
        }
    }
}

private struct CaptureNode {
    let id = UUID()
    var kind: CaptureNodeKind
    var rect: NSRect
    var points: [NSPoint] = []
    var color: NSColor = .systemRed
    var width: CGFloat = 4
    var text = ""
    var fontSize: CGFloat = 28
    var image: NSImage?
    var filled = false
    var fillColor: NSColor = .systemYellow
    var textBackground: NSColor?
}

private struct CaptureSnapshot {
    let base: NSImage
    let size: NSSize
    let nodes: [CaptureNode]
}

private func captureRect(_ a: NSPoint, _ b: NSPoint) -> NSRect {
    NSRect(x: min(a.x, b.x), y: min(a.y, b.y), width: abs(a.x - b.x), height: abs(a.y - b.y))
}

private func capturePixelSize(_ image: NSImage) -> NSSize {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return image.size }
    return NSSize(width: cg.width, height: cg.height)
}

func captureLoadImage(_ url: URL) -> NSImage? {
    if let source = CGImageSourceCreateWithURL(url as CFURL, nil), let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
       let width = properties[kCGImagePropertyPixelWidth] as? NSNumber, let height = properties[kCGImagePropertyPixelHeight] as? NSNumber {
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: max(width.intValue, height.intValue), kCGImageSourceShouldCacheImmediately: true]
        if let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) { return NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height)) }
    }
    return NSImage(contentsOf: url)
}

private func drawCaptureNode(_ node: CaptureNode) {
    node.color.setStroke()
    node.color.setFill()
    let path = NSBezierPath()
    path.lineWidth = node.width
    path.lineCapStyle = .round
    path.lineJoinStyle = .round
    switch node.kind {
    case .rectangle:
        let box = NSBezierPath(rect: node.rect)
        box.lineWidth = node.width
        if node.filled { node.fillColor.setFill(); box.fill() }
        box.stroke()
    case .ellipse:
        let oval = NSBezierPath(ovalIn: node.rect)
        oval.lineWidth = node.width
        if node.filled { node.fillColor.setFill(); oval.fill() }
        oval.stroke()
    case .cover:
        NSBezierPath(rect: node.rect).fill()
    case .arrow:
        guard node.points.count >= 2 else { return }
        let a = node.points[0], b = node.points[1]
        path.move(to: a)
        path.line(to: b)
        let angle = atan2(b.y - a.y, b.x - a.x)
        let length = max(14, node.width * 4)
        path.move(to: NSPoint(x: b.x - length * cos(angle - .pi / 6), y: b.y - length * sin(angle - .pi / 6)))
        path.line(to: b)
        path.line(to: NSPoint(x: b.x - length * cos(angle + .pi / 6), y: b.y - length * sin(angle + .pi / 6)))
        path.stroke()
    case .line:
        guard node.points.count >= 2 else { return }
        path.move(to: node.points[0]); path.line(to: node.points[1]); path.stroke()
    case .checkmark:
        path.move(to: NSPoint(x: node.rect.minX, y: node.rect.midY))
        path.line(to: NSPoint(x: node.rect.minX + node.rect.width * 0.35, y: node.rect.maxY))
        path.line(to: NSPoint(x: node.rect.maxX, y: node.rect.minY)); path.stroke()
    case .pen:
        guard let first = node.points.first else { return }
        path.move(to: first)
        for point in node.points.dropFirst() { path.line(to: point) }
        if node.points.count == 1 {
            NSBezierPath(ovalIn: NSRect(x: first.x - node.width / 2, y: first.y - node.width / 2, width: node.width, height: node.width)).fill()
        } else { path.stroke() }
    case .text:
        if let background = node.textBackground { background.setFill(); NSBezierPath(roundedRect: node.rect, xRadius: 3, yRadius: 3).fill() }
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: node.fontSize, weight: .semibold),
            .foregroundColor: node.color,
            .paragraphStyle: NSParagraphStyle.default
        ]
        NSString(string: node.text).draw(in: node.rect, withAttributes: attributes)
    case .image:
        node.image?.draw(in: node.rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
    }
}

private func renderCapture(_ base: NSImage, size: NSSize, nodes: [CaptureNode]) -> NSImage? {
    let width = max(1, Int(size.width.rounded())), height = max(1, Int(size.height.rounded()))
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
        let graphics = NSGraphicsContext(bitmapImageRep: bitmap) else { return nil }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = graphics
    let cg = graphics.cgContext
    cg.clear(CGRect(x: 0, y: 0, width: width, height: height))
    cg.translateBy(x: 0, y: CGFloat(height))
    cg.scaleBy(x: 1, y: -1)
    NSGraphicsContext.current = NSGraphicsContext(cgContext: cg, flipped: true)
    base.draw(in: NSRect(origin: .zero, size: size), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
    for node in nodes { drawCaptureNode(node) }
    graphics.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    let result = NSImage(size: size)
    result.addRepresentation(bitmap)
    return result
}

private func capturePNG(_ image: NSImage) -> Data? {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    return NSBitmapImageRep(cgImage: cg).representation(using: .png, properties: [:])
}

private func croppedCapture(_ image: NSImage, rect: NSRect) -> NSImage? {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
        let crop = cg.cropping(to: rect.integral.intersection(NSRect(x: 0, y: 0, width: cg.width, height: cg.height))),
        crop.width > 0, crop.height > 0 else { return nil }
    return NSImage(cgImage: crop, size: NSSize(width: crop.width, height: crop.height))
}

private func transparentCapture(_ size: NSSize) -> NSImage? {
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: max(1, Int(size.width)), pixelsHigh: max(1, Int(size.height)), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0), let bytes = bitmap.bitmapData else { return nil }
    bytes.initialize(repeating: 0, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
    let image = NSImage(size: size); image.addRepresentation(bitmap); return image
}

private func filteredCapture(_ image: NSImage, pixelate: Bool, width: CGFloat) -> NSImage? {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
    let input = CIImage(cgImage: cg)
    let output = pixelate
        ? input.applyingFilter("CIPixellate", parameters: [kCIInputScaleKey: max(10, width * 4), kCIInputCenterKey: CIVector(x: input.extent.midX, y: input.extent.midY)])
        : input.clampedToExtent().applyingFilter("CIGaussianBlur", parameters: [kCIInputRadiusKey: max(8, width * 3)]).cropped(to: input.extent)
    guard let result = CIContext().createCGImage(output, from: input.extent) else { return nil }
    return NSImage(cgImage: result, size: capturePixelSize(image))
}

private func transformedCapture(_ image: NSImage, clockwise: Bool = false, horizontal: Bool = false, vertical: Bool = false) -> NSImage? {
    let sourceSize = capturePixelSize(image)
    let size = clockwise ? NSSize(width: sourceSize.height, height: sourceSize.width) : sourceSize
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width), pixelsHigh: Int(size.height), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0), let graphics = NSGraphicsContext(bitmapImageRep: bitmap) else { return nil }
    NSGraphicsContext.saveGraphicsState()
    let cg = graphics.cgContext; cg.clear(CGRect(origin: .zero, size: size))
    cg.translateBy(x: 0, y: size.height); cg.scaleBy(x: 1, y: -1)
    if clockwise { cg.translateBy(x: size.width, y: 0); cg.rotate(by: .pi / 2) }
    if horizontal { cg.translateBy(x: sourceSize.width, y: 0); cg.scaleBy(x: -1, y: 1) }
    if vertical { cg.translateBy(x: 0, y: sourceSize.height); cg.scaleBy(x: 1, y: -1) }
    NSGraphicsContext.current = NSGraphicsContext(cgContext: cg, flipped: true)
    image.draw(in: NSRect(origin: .zero, size: sourceSize), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
    graphics.flushGraphics(); NSGraphicsContext.restoreGraphicsState()
    let result = NSImage(size: size); result.addRepresentation(bitmap); return result
}

private final class CaptureCanvas: NSView {
    private(set) var base: NSImage
    private(set) var imageSize: NSSize
    private let originalBase: NSImage
    private let originalSize: NSSize
    var annotationOnly = false
    var cropAspect: CGFloat?
    var nodes: [CaptureNode] = []
    var selectedID: UUID? { didSet { selectionChanged?() } }
    var selectedRegion: NSRect?
    var tool: CaptureTool = .select { didSet { polygonPoints = []; draft = nil; needsDisplay = true; toolChanged?(tool) } }
    var color: NSColor = .systemRed
    var strokeWidth: CGFloat = 4
    var fontSize: CGFloat = 28
    var shapeFilled = false
    var textBackgroundFilled = false
    var fillColor: NSColor = .systemYellow
    var selectionChanged: (() -> Void)?
    var zoom: CGFloat = 1 { didSet { frame.size = NSSize(width: imageSize.width * zoom, height: imageSize.height * zoom); needsDisplay = true } }
    var changed: (() -> Void)?
    var toolChanged: ((CaptureTool) -> Void)?
    var statusChanged: ((String) -> Void)?
    var imageCopied: (() -> Void)?
    private var copyingImage = false
    var makeCutout: ((NSImage, String) -> Void)?
    var undoHistory: [CaptureSnapshot] = []
    var redoHistory: [CaptureSnapshot] = []
    private var draft: CaptureNode?
    private var start = NSPoint.zero
    private var originalNode: CaptureNode?
    private var resizingCorner: Int?
    private var pendingHistory: [CaptureNode]?
    private var polygonPoints: [NSPoint] = []
    private var pointer = NSPoint.zero
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    init(image: NSImage) {
        base = image
        imageSize = capturePixelSize(image)
        originalBase = image
        originalSize = capturePixelSize(image)
        super.init(frame: NSRect(origin: .zero, size: imageSize))
        wantsLayer = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    func checkpoint() {
        undoHistory.append(snapshot())
        if undoHistory.count > 60 { undoHistory.removeFirst() }
        redoHistory.removeAll()
    }
    func didChange() {
        needsDisplay = true
        changed?()
    }
    private func snapshot() -> CaptureSnapshot { CaptureSnapshot(base: base, size: imageSize, nodes: nodes) }
    private func restore(_ snapshot: CaptureSnapshot) {
        base = snapshot.base; imageSize = snapshot.size; nodes = snapshot.nodes
        selectedID = nil; selectedRegion = nil; let currentZoom = zoom; zoom = currentZoom; didChange()
    }
    func undoEdit() {
        guard let previous = undoHistory.popLast() else { NSSound.beep(); return }
        redoHistory.append(snapshot()); restore(previous)
    }
    func redoEdit() {
        guard let next = redoHistory.popLast() else { NSSound.beep(); return }
        undoHistory.append(snapshot()); restore(next)
    }
    func deleteSelection() {
        guard let id = selectedID, nodes.contains(where: { $0.id == id }) else { return }
        checkpoint(); nodes.removeAll { $0.id == id }; selectedID = nil; didChange()
    }
    func composite() -> NSImage? { renderCapture(base, size: imageSize, nodes: nodes) }
    func exportImage() -> NSImage? {
        guard annotationOnly else { return composite() }
        guard let empty = transparentCapture(imageSize) else { return nil }
        return renderCapture(empty, size: imageSize, nodes: nodes)
    }
    func transform(clockwise: Bool = false, horizontal: Bool = false, vertical: Bool = false) {
        guard !annotationOnly, let image = composite(), let changedImage = transformedCapture(image, clockwise: clockwise, horizontal: horizontal, vertical: vertical) else { return }
        checkpoint(); restore(CaptureSnapshot(base: changedImage, size: capturePixelSize(changedImage), nodes: []))
    }
    func cropToRegion() {
        guard !annotationOnly, let region = selectedRegion, region.width >= 2, region.height >= 2, let image = composite(), let crop = croppedCapture(image, rect: region) else { statusChanged?(L("‘영역 선택’으로 자를 부분을 먼저 드래그하세요.")); return }
        checkpoint(); restore(CaptureSnapshot(base: crop, size: capturePixelSize(crop), nodes: []))
    }
    func resetOriginal() {
        checkpoint(); restore(CaptureSnapshot(base: originalBase, size: originalSize, nodes: []))
    }
    func addImage(_ image: NSImage, at point: NSPoint? = nil) {
        let size = capturePixelSize(image)
        guard size.width > 0, size.height > 0 else { return }
        let scale = min(1, min(imageSize.width * 0.65 / size.width, imageSize.height * 0.65 / size.height))
        let rect = NSRect(origin: point ?? NSPoint(x: imageSize.width * 0.15, y: imageSize.height * 0.15), size: NSSize(width: size.width * scale, height: size.height * scale))
        checkpoint()
        let node = CaptureNode(kind: .image, rect: rect, image: image)
        nodes.append(node); selectedID = node.id; tool = .select; didChange()
        statusChanged?(L("이미지를 추가했습니다. 모서리를 끌어 크기를 바꾸세요."))
    }
    func addText(_ value: String, at point: NSPoint? = nil) {
        guard !value.isEmpty else { return }
        let origin = point ?? NSPoint(x: imageSize.width * 0.12, y: imageSize.height * 0.12)
        let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: fontSize, weight: .semibold)]
        let measured = NSString(string: value).boundingRect(with: NSSize(width: max(100, imageSize.width - origin.x), height: imageSize.height), options: [.usesLineFragmentOrigin], attributes: attributes)
        let rect = NSRect(origin: origin, size: NSSize(width: max(40, measured.width + 10), height: max(fontSize * 1.4, measured.height + 10)))
        checkpoint()
        let node = CaptureNode(kind: .text, rect: rect, color: color, text: value, fontSize: fontSize, textBackground: textBackgroundFilled ? fillColor : nil)
        nodes.append(node); selectedID = node.id; tool = .select; didChange()
    }

    func fillContext() -> (isText: Bool, enabled: Bool)? {
        if let node = nodes.first(where: { $0.id == selectedID }) {
            if node.kind == .text { return (true, node.textBackground != nil) }
            if node.kind == .rectangle || node.kind == .ellipse { return (false, node.filled) }
        }
        if tool == .text { return (true, textBackgroundFilled) }
        if tool == .rectangle || tool == .ellipse { return (false, shapeFilled) }
        return nil
    }
    func applyFill(_ enabled: Bool, color: NSColor) {
        guard let context = fillContext() else { return }
        fillColor = color
        if context.isText { textBackgroundFilled = enabled } else { shapeFilled = enabled }
        guard let index = nodes.firstIndex(where: { $0.id == selectedID }) else { return }
        var node = nodes[index]
        if node.kind == .text {
            let next = enabled ? color : nil
            guard node.textBackground != next else { return }
            checkpoint(); node.textBackground = next
        } else if node.kind == .rectangle || node.kind == .ellipse {
            guard node.filled != enabled || (enabled && node.fillColor != color) else { return }
            checkpoint(); node.filled = enabled; node.fillColor = color
        } else { return }
        nodes[index] = node; didChange()
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill(); dirtyRect.fill()
        NSGraphicsContext.saveGraphicsState()
        let transform = AffineTransform(scale: zoom)
        (transform as NSAffineTransform).concat()
        // Checkerboard is a UI aid only; transparent exports never include it.
        let tile: CGFloat = 16
        for y in stride(from: CGFloat(0), to: imageSize.height, by: tile) {
            for x in stride(from: CGFloat(0), to: imageSize.width, by: tile) {
                ((Int(x / tile + y / tile) % 2 == 0) ? NSColor(white: 0.94, alpha: 1) : NSColor(white: 0.84, alpha: 1)).setFill()
                NSRect(x: x, y: y, width: tile, height: tile).fill()
            }
        }
        base.draw(in: NSRect(origin: .zero, size: imageSize), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
        for node in nodes { drawCaptureNode(node) }
        if let draft = draft { drawCaptureNode(draft) }
        NSColor.systemBlue.setStroke(); NSColor.white.setFill()
        if let node = nodes.first(where: { $0.id == selectedID }) {
            let outline = NSBezierPath(rect: node.rect.insetBy(dx: -2 / zoom, dy: -2 / zoom))
            outline.lineWidth = 1 / zoom; outline.stroke()
            for handle in handles(node.rect) {
                let rect = NSRect(x: handle.x - 4 / zoom, y: handle.y - 4 / zoom, width: 8 / zoom, height: 8 / zoom)
                NSBezierPath(rect: rect).fill(); NSBezierPath(rect: rect).stroke()
            }
        }
        if let region = selectedRegion {
            let path = NSBezierPath(rect: region); path.lineWidth = 1.5 / zoom
            path.setLineDash([6 / zoom, 4 / zoom], count: 2, phase: 0); path.stroke()
        }
        if !polygonPoints.isEmpty {
            let path = NSBezierPath(); path.move(to: polygonPoints[0])
            for point in polygonPoints.dropFirst() { path.line(to: point) }
            path.line(to: pointer); path.lineWidth = 2 / zoom; path.stroke()
        }
        NSGraphicsContext.restoreGraphicsState()
    }

    private func point(_ event: NSEvent) -> NSPoint {
        let p = convert(event.locationInWindow, from: nil)
        return NSPoint(x: max(0, min(imageSize.width, p.x / zoom)), y: max(0, min(imageSize.height, p.y / zoom)))
    }
    private func handles(_ rect: NSRect) -> [NSPoint] {
        [NSPoint(x: rect.minX, y: rect.minY), NSPoint(x: rect.maxX, y: rect.minY), NSPoint(x: rect.maxX, y: rect.maxY), NSPoint(x: rect.minX, y: rect.maxY)]
    }
    private func editText(_ node: CaptureNode) {
        let alert = NSAlert(); alert.messageText = L("텍스트 수정")
        alert.addButton(withTitle: L("적용")); alert.addButton(withTitle: L("취소"))
        let field = CaptureInputField(string: node.text); field.frame = NSRect(x: 0, y: 0, width: 360, height: 60)
        alert.accessoryView = field
        guard alert.runModal() == .alertFirstButtonReturn, let index = nodes.firstIndex(where: { $0.id == node.id }) else { return }
        checkpoint(); nodes[index].text = field.stringValue; didChange()
    }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        start = point(event); pointer = start
        if tool == .polygon {
            if event.clickCount >= 2 { finishPolygon(); return }
            polygonPoints.append(start); needsDisplay = true
            statusChanged?(L("꼭짓점을 클릭하세요. 마지막 지점에서 더블클릭하면 오립니다. Esc: 취소"))
            return
        }
        if tool == .select {
            resizingCorner = nil; originalNode = nil; pendingHistory = nil
            if let node = nodes.first(where: { $0.id == selectedID }),
               let corner = handles(node.rect).firstIndex(where: { hypot($0.x - start.x, $0.y - start.y) < 10 / zoom }) {
                resizingCorner = corner; originalNode = node; pendingHistory = nodes; return
            }
            selectedID = nodes.last(where: { $0.rect.insetBy(dx: -6 / zoom, dy: -6 / zoom).contains(start) })?.id
            if let node = nodes.first(where: { $0.id == selectedID }) {
                if event.clickCount >= 2 && node.kind == .text { editText(node); return }
                originalNode = node; pendingHistory = nodes
            }
            needsDisplay = true; return
        }
        if tool == .region { selectedID = nil; selectedRegion = NSRect(origin: start, size: .zero); needsDisplay = true; return }
        if tool == .text {
            let alert = NSAlert(); alert.messageText = L("추가할 텍스트")
            alert.addButton(withTitle: L("추가")); alert.addButton(withTitle: L("취소"))
            let field = CaptureInputField(); field.placeholderString = L("텍스트를 입력하세요")
            field.frame = NSRect(x: 0, y: 0, width: 360, height: 60); alert.accessoryView = field
            if alert.runModal() == .alertFirstButtonReturn { addText(field.stringValue, at: start) }
            return
        }
        let kind: CaptureNodeKind
        switch tool {
        case .ellipse: kind = .ellipse
        case .arrow: kind = .arrow
        case .line: kind = .line
        case .checkmark: kind = .checkmark
        case .pen: kind = .pen
        case .cover, .blur, .pixelate: kind = .cover
        default: kind = .rectangle
        }
        draft = CaptureNode(kind: kind, rect: NSRect(origin: start, size: .zero), points: [start], color: tool == .blur || tool == .pixelate ? color.withAlphaComponent(0.25) : color, width: strokeWidth, filled: shapeFilled, fillColor: fillColor)
        selectedID = nil; needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        let p = point(event); pointer = p
        if tool == .select, let original = originalNode, let index = nodes.firstIndex(where: { $0.id == original.id }) {
            var rect = original.rect
            if let corner = resizingCorner {
                let opposite = handles(original.rect)[(corner + 2) % 4]
                rect = captureRect(opposite, p)
                rect.size.width = max(8, rect.size.width); rect.size.height = max(8, rect.size.height)
            } else { rect.origin.x += p.x - start.x; rect.origin.y += p.y - start.y }
            var node = original; node.rect = rect
            let sx = rect.width / max(1, original.rect.width), sy = rect.height / max(1, original.rect.height)
            node.points = original.points.map { NSPoint(x: rect.minX + ($0.x - original.rect.minX) * sx, y: rect.minY + ($0.y - original.rect.minY) * sy) }
            if resizingCorner != nil && node.kind == .text { node.fontSize = max(8, original.fontSize * sy) }
            nodes[index] = node; needsDisplay = true; return
        }
        if tool == .region {
            var endpoint = p
            if let ratio = cropAspect {
                let signX: CGFloat = p.x >= start.x ? 1 : -1, signY: CGFloat = p.y >= start.y ? 1 : -1
                var width = max(abs(p.x - start.x), abs(p.y - start.y) * ratio)
                var height = width / ratio
                let availableX = signX > 0 ? imageSize.width - start.x : start.x
                let availableY = signY > 0 ? imageSize.height - start.y : start.y
                let factor = min(1, min(availableX / max(1, width), availableY / max(1, height)))
                width *= factor; height *= factor
                endpoint = NSPoint(x: start.x + signX * width, y: start.y + signY * height)
            }
            selectedRegion = captureRect(start, endpoint); needsDisplay = true; return
        }
        guard var node = draft else { return }
        if tool == .pen {
            node.points.append(p)
            let xs = node.points.map(\.x), ys = node.points.map(\.y)
            node.rect = NSRect(x: xs.min()!, y: ys.min()!, width: max(1, xs.max()! - xs.min()!), height: max(1, ys.max()! - ys.min()!))
        } else {
            node.rect = captureRect(start, p)
            if tool == .arrow || tool == .line { node.points = [start, p] }
        }
        draft = node; needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        if tool == .select {
            if let before = pendingHistory, let original = originalNode, let node = nodes.first(where: { $0.id == original.id }), node.rect != original.rect {
                undoHistory.append(CaptureSnapshot(base: base, size: imageSize, nodes: before)); redoHistory.removeAll(); didChange()
            }
            originalNode = nil; pendingHistory = nil; resizingCorner = nil; return
        }
        if tool == .region {
            if let region = selectedRegion { statusChanged?(Lf("선택 영역: %d × %d · ‘자르기 적용’ 또는 ‘영역 오리기’를 누르세요.", Int(region.width), Int(region.height))) }
            return
        }
        guard var node = draft else { return }
        defer { draft = nil; needsDisplay = true }
        if tool == .pen { node.rect = node.rect.insetBy(dx: -node.width / 2, dy: -node.width / 2) }
        guard node.rect.width >= 2 || node.rect.height >= 2 else { return }
        if tool == .blur || tool == .pixelate {
            guard let composite = composite(), let region = croppedCapture(composite, rect: node.rect), let filtered = filteredCapture(region, pixelate: tool == .pixelate, width: strokeWidth) else { return }
            node.kind = .image; node.image = filtered
        }
        checkpoint(); nodes.append(node); selectedID = node.id; tool = .select; didChange()
    }

    override func mouseMoved(with event: NSEvent) { pointer = point(event); if tool == .polygon { needsDisplay = true } }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for area in trackingAreas { removeTrackingArea(area) }
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseMoved, .activeInKeyWindow, .inVisibleRect], owner: self, userInfo: nil))
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 51 || event.keyCode == 117 { deleteSelection(); return }
        if event.keyCode == 53 { polygonPoints = []; selectedRegion = nil; selectedID = nil; draft = nil; needsDisplay = true; return }
        super.keyDown(with: event)
    }
    func pasteClipboard() {
        if let image = NSImage(pasteboard: .general) { addImage(image); return }
        if let value = NSPasteboard.general.string(forType: .string), !value.isEmpty { addText(value); return }
        statusChanged?(L("클립보드에 이미지나 텍스트가 없습니다."))
    }
    @discardableResult func copyComposite() -> Bool {
        guard !copyingImage else { return false }
        copyingImage = true; defer { copyingImage = false }
        guard let image = exportImage() else {
            statusChanged?(L("클립보드에 이미지를 복사하지 못했습니다. 다시 복사하세요.")); return false
        }
        let copied = galaxyCopyImage(image)
        statusChanged?(copied ? L("편집한 이미지를 클립보드에 복사했습니다. ⌘V 또는 Ctrl+V로 붙여넣으세요.") : L("클립보드에 이미지를 복사하지 못했습니다. 다시 복사하세요."))
        if copied { imageCopied?() }
        return copied
    }
    @objc func copy(_ sender: Any?) { copyComposite() }
    @objc func paste(_ sender: Any?) { pasteClipboard() }
    func cutSelectedRegion() {
        guard let image = composite(), let region = selectedRegion, region.width >= 2, region.height >= 2,
            let crop = croppedCapture(image, rect: region) else {
            statusChanged?(L("‘영역 선택’으로 오릴 부분을 먼저 드래그하세요.")); return
        }
        makeCutout?(crop, "crop")
    }
    private func finishPolygon() {
        guard polygonPoints.count >= 3, let image = composite() else { NSSound.beep(); return }
        let xs = polygonPoints.map(\.x), ys = polygonPoints.map(\.y)
        let region = NSRect(x: xs.min()!, y: ys.min()!, width: xs.max()! - xs.min()!, height: ys.max()! - ys.min()!).integral
        guard region.width > 1, region.height > 1, let crop = croppedCapture(image, rect: region),
            let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(region.width), pixelsHigh: Int(region.height), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
            let graphics = NSGraphicsContext(bitmapImageRep: bitmap) else { return }
        NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = graphics
        graphics.cgContext.clear(CGRect(origin: .zero, size: region.size))
        graphics.cgContext.translateBy(x: 0, y: region.height); graphics.cgContext.scaleBy(x: 1, y: -1)
        NSGraphicsContext.current = NSGraphicsContext(cgContext: graphics.cgContext, flipped: true)
        let path = NSBezierPath()
        path.move(to: NSPoint(x: polygonPoints[0].x - region.minX, y: polygonPoints[0].y - region.minY))
        for p in polygonPoints.dropFirst() { path.line(to: NSPoint(x: p.x - region.minX, y: p.y - region.minY)) }
        path.close(); path.addClip()
        crop.draw(in: NSRect(origin: .zero, size: region.size), from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
        graphics.flushGraphics(); NSGraphicsContext.restoreGraphicsState()
        let result = NSImage(size: region.size); result.addRepresentation(bitmap)
        polygonPoints = []; needsDisplay = true; makeCutout?(result, "cutout")
    }
}

final class CaptureEditorController: NSWindowController, NSWindowDelegate {
    private static var detachedEditors: [CaptureEditorController] = []
    static func prepareForQuit(roots: [CaptureEditorController]) -> Bool {
        var seen = Set<ObjectIdentifier>()
        for editor in roots + detachedEditors {
            guard seen.insert(ObjectIdentifier(editor)).inserted, let window = editor.window else { continue }
            if !editor.windowShouldClose(window) { return false }
        }
        return true
    }
    private let imageURL: URL
    private let saveDirectory: URL
    private let editedURL: URL
    private let canvas: CaptureCanvas
    private let annotationOnly: Bool
    private let captureSession: Bool
    private var copyClosing = false
    private let onSave: ((URL) -> Void)?
    private let status = NSTextField(labelWithString: L("도구를 고르고 이미지 위에서 드래그하세요. ⌘/Ctrl+C: 복사 · ⌘/Ctrl+V: 이미지·텍스트 추가"))
    private let toolMenu = NSPopUpButton()
    private let colorWell = NSColorWell()
    private let widthMenu = NSPopUpButton()
    private let fontMenu = NSPopUpButton()
    private let aspectMenu = NSPopUpButton()
    private let scroll = NSScrollView()
    private let shapePopup = NSPopUpButton(frame: .zero, pullsDown: true)
    private let morePopup = NSPopUpButton(frame: .zero, pullsDown: true)
    private var shapeButton: NSButton!
    private var fillButton: NSButton!
    private var cropApplyButton: NSButton?
    private var undoButton: NSButton?
    private var redoButton: NSButton?
    private var deleteButton: NSButton?
    private let fillColorWell = NSColorWell()
    private var recentShape: CaptureTool = .rectangle
    private var toolButtons: [CaptureTool: NSButton] = [:]
    private var toolItems: [CaptureTool: [NSMenuItem]] = [:]
    private var widthItems: [NSMenuItem] = []
    private var fontItems: [NSMenuItem] = []
    private var aspectItems: [NSMenuItem] = []
    private var tooltipControls: [(NSControl, String)] = []
    private var languageObserver: NSObjectProtocol?
    private var offeredTools = CaptureTool.allCases
    private var saveTimer: Timer?
    private var eventMonitor: Any?
    private var dirty = false

    init(imageURL: URL, saveDirectory: URL, annotationOnly: Bool = false, captureSession: Bool = false, onSave: ((URL) -> Void)? = nil) {
        self.imageURL = imageURL
        self.saveDirectory = saveDirectory
        self.annotationOnly = annotationOnly
        self.captureSession = captureSession
        self.onSave = onSave
        editedURL = saveDirectory.appendingPathComponent(imageURL.deletingPathExtension().lastPathComponent + "-edited-" + UUID().uuidString.prefix(6) + ".png")
        let image = captureLoadImage(imageURL) ?? NSImage(size: NSSize(width: 960, height: 600))
        canvas = CaptureCanvas(image: image)
        canvas.annotationOnly = annotationOnly
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1160, height: 780), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init(window: window)
        window.title = annotationOnly ? Lf("PDF 위에 내용 추가 / 서명 / 주석 · %@", imageURL.lastPathComponent) : Lf("이미지·캡처 편집 · %@", imageURL.lastPathComponent)
        window.appearance = NSAppearance(named: .aqua); window.backgroundColor = BogoTheme.background
        window.minSize = NSSize(width: 720, height: 480)
        window.delegate = self; window.isReleasedWhenClosed = false
        window.center()
        buildUI()
        canvas.changed = { [weak self] in self?.scheduleSave(); self?.refreshToolbarState() }
        canvas.imageCopied = { [weak self] in
            guard let self = self, self.captureSession, !self.copyClosing,
                  UserDefaults.standard.object(forKey: "capture.closeAfterCopy") as? Bool ?? true else { return }
            self.copyClosing = true
            self.saveTimer?.invalidate(); self.saveTimer = nil
            // Clipboard copy is not a file save. Close only this editor without a save confirmation.
            self.window?.close()
        }
        canvas.toolChanged = { [weak self] tool in guard let self = self, let index = self.offeredTools.firstIndex(of: tool) else { return }; self.toolMenu.selectItem(at: index); self.refreshToolbarState() }
        canvas.statusChanged = { [weak self] message in self?.status.stringValue = message; self?.refreshToolbarState() }
        canvas.selectionChanged = { [weak self] in self?.refreshToolbarState() }
        canvas.makeCutout = { [weak self] image, suffix in self?.openCutout(image, suffix: suffix) }
        languageObserver = NotificationCenter.default.addObserver(forName: Notification.Name("GalaxyControlLanguageChanged"), object: nil, queue: .main) { [weak self] _ in self?.refreshToolbarState() }
        installShortcuts()
        DispatchQueue.main.async { [weak self] in self?.fitImage(); self?.window?.makeFirstResponder(self?.canvas) }
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    deinit { if let monitor = eventMonitor { NSEvent.removeMonitor(monitor) }; if let observer = languageObserver { NotificationCenter.default.removeObserver(observer) }; saveTimer?.invalidate() }
    override func showWindow(_ sender: Any?) {
        super.showWindow(sender); window?.makeKeyAndOrderFront(sender); NSApp.activate(ignoringOtherApps: true)
    }

    private func symbol(_ name: String, title: String) -> NSImage? {
        let image = NSImage(systemSymbolName: name, accessibilityDescription: L(title)) ?? NSImage(named: NSImage.actionTemplateName)
        image?.isTemplate = true
        return image
    }
    private func iconButton(_ title: String, symbol name: String, action: Selector, tool: CaptureTool? = nil) -> NSButton {
        let button = NSButton(title: "", target: self, action: action)
        button.image = symbol(name, title: title); button.imagePosition = .imageOnly
        button.bezelStyle = .texturedRounded; button.controlSize = .small; button.focusRingType = .none
        button.imageScaling = .scaleProportionallyDown
        button.wantsLayer = true; button.layer?.cornerRadius = 6
        button.widthAnchor.constraint(equalToConstant: 34).isActive = true
        button.heightAnchor.constraint(equalToConstant: 30).isActive = true
        button.setAccessibilityLabel(L(title)); button.toolTip = L(title)
        tooltipControls.append((button, title))
        if let tool = tool { button.setButtonType(.toggle); button.tag = tool.rawValue; toolButtons[tool] = button }
        return button
    }
    private func separator() -> NSView {
        let line = NSBox(); line.boxType = .separator
        line.widthAnchor.constraint(equalToConstant: 1).isActive = true
        line.heightAnchor.constraint(equalToConstant: 22).isActive = true
        return line
    }
    private func menuItem(_ title: String, action: Selector, symbol name: String? = nil, tag: Int = 0) -> NSMenuItem {
        let item = NSMenuItem(title: L(title), action: action, keyEquivalent: "")
        item.target = self; item.tag = tag
        if let name = name { item.image = symbol(name, title: title) }
        return item
    }
    private func toolSymbol(_ tool: CaptureTool) -> String {
        switch tool {
        case .select: return "cursorarrow"
        case .rectangle: return "rectangle"
        case .ellipse: return "circle"
        case .arrow: return "arrow.up.right"
        case .line: return "line.diagonal"
        case .checkmark: return "checkmark"
        case .pen: return "pencil.tip"
        case .text: return "textformat"
        case .blur: return "drop.halffull"
        case .pixelate: return "square.grid.3x3"
        case .cover: return "rectangle.fill"
        case .region: return "crop"
        case .polygon: return "lasso"
        }
    }
    private func addTool(_ tool: CaptureTool, to menu: NSMenu) {
        let item = menuItem(tool.label, action: #selector(pickTool(_:)), symbol: toolSymbol(tool), tag: tool.rawValue)
        menu.addItem(item); toolItems[tool, default: []].append(item)
    }
    private func submenu(_ title: String, in parent: NSMenu) -> NSMenu {
        let item = NSMenuItem(title: L(title), action: nil, keyEquivalent: "")
        let menu = NSMenu(title: L(title)); menu.autoenablesItems = false
        item.submenu = menu; parent.addItem(item); return menu
    }
    private func configurePopup(_ popup: NSPopUpButton, title: String, symbol name: String, width: CGFloat = 42) -> NSMenu {
        popup.bezelStyle = .texturedRounded; popup.controlSize = .small; popup.focusRingType = .none
        popup.imagePosition = .imageOnly; popup.imageScaling = .scaleProportionallyDown
        popup.widthAnchor.constraint(equalToConstant: width).isActive = true
        popup.heightAnchor.constraint(equalToConstant: 30).isActive = true
        let menu = NSMenu(); menu.autoenablesItems = false
        let header = NSMenuItem(title: L(title), action: nil, keyEquivalent: ""); header.image = symbol(name, title: title)
        menu.addItem(header); popup.menu = menu
        popup.toolTip = L(title); popup.setAccessibilityLabel(L(title)); tooltipControls.append((popup, title))
        return menu
    }
    private func buildMoreMenu() {
        let menu = configurePopup(morePopup, title: "더 보기", symbol: "ellipsis")
        let tools = submenu("그리기 도구", in: menu)
        for tool in offeredTools { addTool(tool, to: tools) }
        let styles = submenu("선 및 글자", in: menu)
        let widths = submenu("선 두께", in: styles)
        for (index, label) in ["2 px", "4 px", "6 px", "10 px", "16 px", "24 px"].enumerated() {
            let item = menuItem(label, action: #selector(pickWidth(_:)), tag: index); widths.addItem(item); widthItems.append(item)
        }
        let fonts = submenu("글자 크기", in: styles)
        for (index, label) in ["18 pt", "28 pt", "40 pt", "56 pt", "80 pt"].enumerated() {
            let item = menuItem(label, action: #selector(pickFont(_:)), tag: index); fonts.addItem(item); fontItems.append(item)
        }
        menu.addItem(.separator())
        menu.addItem(menuItem(annotationOnly ? "서명 이미지 추가…" : "이미지 추가…", action: #selector(importImage), symbol: "photo"))
        menu.addItem(menuItem("붙여넣기", action: #selector(pasteAction), symbol: "doc.on.clipboard"))
        menu.addItem(menuItem("삭제", action: #selector(deleteAction), symbol: "trash"))
        if !annotationOnly {
            let crop = submenu("자르기와 오리기", in: menu)
            crop.addItem(menuItem("자를 영역 선택", action: #selector(selectCrop), symbol: "crop"))
            crop.addItem(menuItem("자르기 적용", action: #selector(cropImage)))
            let ratios = submenu("자르기 비율", in: crop)
            for (index, label) in [L("자유"), "1:1", "4:3", "16:9"].enumerated() {
                let item = menuItem(label, action: #selector(pickAspect(_:)), tag: index); ratios.addItem(item); aspectItems.append(item)
            }
            crop.addItem(.separator()); crop.addItem(menuItem("영역 오리기", action: #selector(cutRegion), symbol: "scissors"))
            let image = submenu("회전 및 원본", in: menu)
            image.addItem(menuItem("90° 회전", action: #selector(rotateImage), symbol: "rotate.right"))
            image.addItem(menuItem("좌우 반전", action: #selector(flipHorizontal), symbol: "arrow.left.and.right"))
            image.addItem(menuItem("상하 반전", action: #selector(flipVertical), symbol: "arrow.up.and.down"))
            image.addItem(.separator()); image.addItem(menuItem("원본으로 되돌리기", action: #selector(resetOriginal), symbol: "arrow.counterclockwise"))
        }
        let view = submenu("보기", in: menu)
        view.addItem(menuItem("화면에 맞춤", action: #selector(fitImage), symbol: "arrow.up.left.and.arrow.down.right"))
        view.addItem(menuItem("100%", action: #selector(actualSize), symbol: "magnifyingglass"))
        menu.addItem(.separator())
        menu.addItem(menuItem("편집 저장", action: #selector(saveNow), symbol: "square.and.arrow.down"))
        menu.addItem(menuItem("편집 도움말", action: #selector(showEditingHelp), symbol: "questionmark.circle"))
    }
    private func refreshToolbarState() {
        undoButton?.isEnabled = !canvas.undoHistory.isEmpty
        redoButton?.isEnabled = !canvas.redoHistory.isEmpty
        for (tool, button) in toolButtons {
            button.state = canvas.tool == tool ? .on : .off
            button.contentTintColor = canvas.tool == tool ? BogoTheme.accent : BogoTheme.ink
            button.layer?.backgroundColor = canvas.tool == tool ? BogoTheme.selection.cgColor : NSColor.clear.cgColor
        }
        for (tool, items) in toolItems { for item in items { item.state = canvas.tool == tool ? .on : .off } }
        let shapeTools: [CaptureTool] = annotationOnly ? [.rectangle, .line, .checkmark] : [.rectangle, .ellipse, .line, .checkmark]
        let shape = shapeTools.contains(canvas.tool)
        shapePopup.contentTintColor = shape ? BogoTheme.accent : BogoTheme.ink
        shapeButton?.image = symbol(toolSymbol(recentShape), title: "도형")
        shapeButton?.contentTintColor = shape ? BogoTheme.accent : BogoTheme.ink
        shapeButton?.state = shape ? .on : .off
        shapeButton?.layer?.backgroundColor = shape ? BogoTheme.selection.cgColor : NSColor.clear.cgColor
        let fill = canvas.fillContext()
        fillButton?.isEnabled = fill != nil
        fillButton?.state = fill?.enabled == true ? .on : .off
        fillButton?.image = symbol(fill?.enabled == true ? "square.fill" : "square", title: fill?.isText == true ? "글자 배경" : "도형 채우기")
        fillButton?.contentTintColor = fill?.enabled == true ? BogoTheme.accent : BogoTheme.ink
        fillButton?.layer?.backgroundColor = fill?.enabled == true ? BogoTheme.selection.cgColor : NSColor.clear.cgColor
        fillColorWell.isHidden = fill?.enabled != true
        if let selected = canvas.nodes.first(where: { $0.id == canvas.selectedID }) {
            if let background = selected.textBackground { fillColorWell.color = background }
            else if selected.filled { fillColorWell.color = selected.fillColor }
        }
        deleteButton?.isEnabled = canvas.nodes.contains(where: { $0.id == canvas.selectedID })
        cropApplyButton?.isHidden = canvas.tool != .region
        cropApplyButton?.isEnabled = canvas.selectedRegion != nil
        let rare = !toolButtons.keys.contains(canvas.tool) && !shape
        morePopup.contentTintColor = rare ? BogoTheme.accent : BogoTheme.ink
        for (index, item) in widthItems.enumerated() { item.state = widthMenu.indexOfSelectedItem == index ? .on : .off }
        for (index, item) in fontItems.enumerated() { item.state = fontMenu.indexOfSelectedItem == index ? .on : .off }
        for (index, item) in aspectItems.enumerated() { item.state = aspectMenu.indexOfSelectedItem == index ? .on : .off }
        for (control, title) in tooltipControls { control.toolTip = L(title); control.setAccessibilityLabel(L(title)) }
        shapeButton?.toolTip = L("도형") + " · " + L(recentShape.label); shapeButton?.setAccessibilityLabel(shapeButton?.toolTip)
        let fillLabel: String
        if let fill = fill {
            fillLabel = fill.isText ? (fill.enabled ? "글자 배경 해제" : "글자 배경 채우기") : (fill.enabled ? "도형 채우기 해제" : "도형 채우기")
        } else { fillLabel = "도형/텍스트를 선택해 채우기 설정" }
        fillButton?.toolTip = L(fillLabel); fillButton?.setAccessibilityLabel(L(fillLabel))
        if rare { morePopup.toolTip = L("더 보기") + " · " + canvas.tool.label; morePopup.setAccessibilityLabel(morePopup.toolTip) }
    }
    private func buildUI() {
        guard let content = window?.contentView else { return }
        content.wantsLayer = true; content.layer?.backgroundColor = BogoTheme.background.cgColor
        let vertical = NSStackView(); vertical.orientation = .vertical; vertical.spacing = 10; vertical.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 10, right: 12)
        vertical.translatesAutoresizingMaskIntoConstraints = false; content.addSubview(vertical)
        NSLayoutConstraint.activate([vertical.leadingAnchor.constraint(equalTo: content.leadingAnchor), vertical.trailingAnchor.constraint(equalTo: content.trailingAnchor), vertical.topAnchor.constraint(equalTo: content.topAnchor), vertical.bottomAnchor.constraint(equalTo: content.bottomAnchor)])
        if annotationOnly { offeredTools = [.select, .rectangle, .line, .checkmark, .pen, .text] }
        // Hidden value selectors retain the same style/crop behavior behind the compact menu.
        toolMenu.addItems(withTitles: offeredTools.map(\.label))
        widthMenu.addItems(withTitles: ["2 px", "4 px", "6 px", "10 px", "16 px", "24 px"]); widthMenu.selectItem(at: 1)
        fontMenu.addItems(withTitles: ["18 pt", "28 pt", "40 pt", "56 pt", "80 pt"]); fontMenu.selectItem(at: 1)
        aspectMenu.addItems(withTitles: [L("자유"), "1:1", "4:3", "16:9"])
        let allowedShapes: [CaptureTool] = annotationOnly ? [.rectangle, .line, .checkmark] : [.rectangle, .ellipse, .line, .checkmark]
        let savedShape = UserDefaults.standard.integer(forKey: "capture.editor.lastShape")
        if let saved = CaptureTool(rawValue: savedShape), allowedShapes.contains(saved) { recentShape = saved }
        var tools: [NSView] = [iconButton("선택", symbol: "cursorarrow", action: #selector(pickTool(_:)), tool: .select)]
        if !annotationOnly {
            tools.append(iconButton("자르기", symbol: "crop", action: #selector(selectCrop), tool: .region))
            let applyCrop = iconButton("자르기 적용", symbol: "checkmark", action: #selector(cropImage))
            cropApplyButton = applyCrop; tools.append(applyCrop)
            tools.append(iconButton("모자이크", symbol: "square.grid.3x3", action: #selector(pickTool(_:)), tool: .pixelate))
        }
        shapeButton = iconButton("도형", symbol: toolSymbol(recentShape), action: #selector(pickRecentShape))
        shapeButton.setButtonType(.toggle); tools.append(shapeButton)
        let shapeMenu = configurePopup(shapePopup, title: "도형 선택", symbol: "chevron.down", width: 22)
        for tool in allowedShapes { addTool(tool, to: shapeMenu) }
        tools.append(shapePopup)
        tools.append(iconButton("텍스트", symbol: "textformat", action: #selector(pickTool(_:)), tool: .text))
        if annotationOnly { tools.append(iconButton("펜", symbol: "pencil.tip", action: #selector(pickTool(_:)), tool: .pen)) }
        else {
            tools.append(iconButton("화살표", symbol: "arrow.up.right", action: #selector(pickTool(_:)), tool: .arrow))
            tools.append(iconButton("흐림", symbol: "drop.halffull", action: #selector(pickTool(_:)), tool: .blur))
        }
        colorWell.color = .systemRed; colorWell.target = self; colorWell.action = #selector(changeStyle)
        colorWell.widthAnchor.constraint(equalToConstant: 30).isActive = true; colorWell.heightAnchor.constraint(equalToConstant: 28).isActive = true
        if #available(macOS 13.0, *) { colorWell.colorWellStyle = .minimal }
        colorWell.toolTip = L("선·글자 색상"); colorWell.setAccessibilityLabel(L("선·글자 색상")); tooltipControls.append((colorWell, "선·글자 색상"))
        fillButton = iconButton("도형 채우기", symbol: "square", action: #selector(toggleFill))
        fillButton.setButtonType(.toggle)
        fillColorWell.color = .systemYellow; fillColorWell.target = self; fillColorWell.action = #selector(changeFillColor)
        fillColorWell.widthAnchor.constraint(equalToConstant: 24).isActive = true; fillColorWell.heightAnchor.constraint(equalToConstant: 26).isActive = true
        if #available(macOS 13.0, *) { fillColorWell.colorWellStyle = .minimal }
        fillColorWell.toolTip = L("채우기 색상"); fillColorWell.setAccessibilityLabel(L("채우기 색상")); tooltipControls.append((fillColorWell, "채우기 색상"))
        tools += [separator(), colorWell, fillButton, fillColorWell]
        let spacer = NSView(); spacer.setContentHuggingPriority(.defaultLow, for: .horizontal); spacer.widthAnchor.constraint(greaterThanOrEqualToConstant: 12).isActive = true
        let undo = iconButton("실행 취소", symbol: "arrow.uturn.backward", action: #selector(undoAction))
        let redo = iconButton("다시 실행", symbol: "arrow.uturn.forward", action: #selector(redoAction))
        undoButton = undo; redoButton = redo
        let delete = iconButton("삭제", symbol: "trash", action: #selector(deleteAction)); deleteButton = delete
        tools += [spacer, undo, redo, delete, separator(), iconButton("복사", symbol: "doc.on.doc", action: #selector(copyAction)), iconButton(annotationOnly ? "주석 적용" : "PNG 내보내기…", symbol: annotationOnly ? "checkmark.circle" : "square.and.arrow.down", action: annotationOnly ? #selector(commitAnnotations) : #selector(exportPNG))]
        buildMoreMenu(); tools.append(morePopup)
        let toolbar = NSStackView(views: tools); toolbar.orientation = .horizontal; toolbar.alignment = .centerY; toolbar.spacing = 5
        let bar = NSView(); bar.wantsLayer = true; bar.layer?.cornerRadius = 10; bar.layer?.backgroundColor = BogoTheme.header.cgColor
        toolbar.translatesAutoresizingMaskIntoConstraints = false; bar.addSubview(toolbar); vertical.addArrangedSubview(bar)
        NSLayoutConstraint.activate([toolbar.leadingAnchor.constraint(equalTo: bar.leadingAnchor, constant: 9), toolbar.trailingAnchor.constraint(equalTo: bar.trailingAnchor, constant: -9), toolbar.topAnchor.constraint(equalTo: bar.topAnchor, constant: 7), toolbar.bottomAnchor.constraint(equalTo: bar.bottomAnchor, constant: -7), bar.widthAnchor.constraint(equalTo: vertical.widthAnchor, constant: -24)])
        bar.setContentHuggingPriority(.required, for: .vertical)
        if annotationOnly { status.stringValue = L("기존 PDF 문장은 그대로 두고 새 내용만 추가합니다. ‘주석 적용’ 전에 미리보기를 확인하세요.") }
        scroll.hasVerticalScroller = true; scroll.hasHorizontalScroller = true; scroll.autohidesScrollers = true; scroll.borderType = .noBorder
        scroll.backgroundColor = .controlBackgroundColor; scroll.documentView = canvas
        scroll.wantsLayer = true; scroll.layer?.cornerRadius = 10; scroll.layer?.masksToBounds = true
        scroll.translatesAutoresizingMaskIntoConstraints = false; vertical.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: vertical.widthAnchor, constant: -24).isActive = true
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 300).isActive = true
        status.font = NSFont.systemFont(ofSize: 11); status.textColor = .secondaryLabelColor; status.lineBreakMode = .byTruncatingMiddle
        vertical.addArrangedSubview(status); status.widthAnchor.constraint(equalTo: scroll.widthAnchor).isActive = true
        status.setContentHuggingPriority(.required, for: .vertical)
        refreshToolbarState()
    }
    @objc private func pickTool(_ sender: Any) {
        let tag = (sender as? NSControl)?.tag ?? (sender as? NSMenuItem)?.tag ?? -1
        guard let tool = CaptureTool(rawValue: tag), let index = offeredTools.firstIndex(of: tool) else { return }
        if tool != .select { canvas.selectedID = nil }
        if [.rectangle, .ellipse, .line, .checkmark].contains(tool) {
            recentShape = tool; UserDefaults.standard.set(tool.rawValue, forKey: "capture.editor.lastShape")
        }
        toolMenu.selectItem(at: index); changeTool()
    }
    @objc private func pickRecentShape() {
        let item = NSMenuItem(); item.tag = recentShape.rawValue; pickTool(item)
    }
    @objc private func toggleFill() {
        guard let fill = canvas.fillContext() else { return }
        canvas.applyFill(!fill.enabled, color: fillColorWell.color); refreshToolbarState(); window?.makeFirstResponder(canvas)
    }
    @objc private func changeFillColor() {
        canvas.fillColor = fillColorWell.color
        if let fill = canvas.fillContext(), fill.enabled { canvas.applyFill(true, color: fillColorWell.color) }
        refreshToolbarState(); window?.makeFirstResponder(canvas)
    }
    @objc private func pickWidth(_ sender: NSMenuItem) { widthMenu.selectItem(at: sender.tag); changeStyle() }
    @objc private func pickFont(_ sender: NSMenuItem) { fontMenu.selectItem(at: sender.tag); changeStyle() }
    @objc private func pickAspect(_ sender: NSMenuItem) { aspectMenu.selectItem(at: sender.tag); changeAspect(); refreshToolbarState() }
    @objc private func showEditingHelp() {
        let alert = NSAlert(); alert.messageText = L("편집 도움말")
        alert.informativeText = L("선택: 위치 이동 / 모서리: 크기 변경 / Delete: 삭제 / 텍스트 더블클릭: 수정 / ⌘·Ctrl+Z: 실행 취소 / ⌘·Ctrl+C·V: 이미지 복사·붙여넣기") + "\n\n" + L("위쪽 아이콘으로 자르기·모자이크·도형·텍스트를 바로 고릅니다. 도형 옆 화살표로 종류를 바꾸면 다음 실행에도 기억합니다. 채우기 아이콘으로 도형 채우기나 글자 배경을 켜고, 옆 색상에서 배경색을 고르세요. 선 두께와 글자 크기는 ‘더 보기 → 선 및 글자’에서 바꿉니다. 자를 영역을 드래그한 뒤 위쪽 체크 아이콘으로 적용하세요. 다른 도구와 회전·보기 설정은 ‘더 보기’에 있으며 편집 내용은 자동 저장됩니다.")
        alert.addButton(withTitle: L("확인")); if let window = window { alert.beginSheetModal(for: window) }
    }
    private func installShortcuts() {
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self = self, event.window === self.window else { return event }
            if self.window?.firstResponder is NSTextView { return event }
            let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            if (event.keyCode == 51 || event.keyCode == 117), mods.intersection([.command, .control, .option, .shift]).isEmpty, self.canvas.selectedID != nil { self.deleteAction(); return nil }
            guard !mods.contains(.option), mods.contains(.command) != mods.contains(.control), let key = event.charactersIgnoringModifiers?.lowercased() else { return event }
            switch key {
            case "c": if mods.contains(.shift) { return event }; self.copyAction(); return nil
            case "v": if mods.contains(.shift) { return event }; self.pasteAction(); return nil
            case "z": if mods.contains(.shift) { self.redoAction() } else { self.undoAction() }; return nil
            case "s": self.saveNow(); return nil
            default: return event
            }
        }
    }
    @objc private func changeTool() { canvas.tool = offeredTools[toolMenu.indexOfSelectedItem]; window?.makeFirstResponder(canvas) }
    @objc private func changeAspect() { canvas.cropAspect = [nil, CGFloat(1), CGFloat(4) / 3, CGFloat(16) / 9][aspectMenu.indexOfSelectedItem]; selectCrop() }
    @objc private func selectCrop() { canvas.selectedID = nil; canvas.selectedRegion = nil; canvas.tool = .region; window?.makeFirstResponder(canvas); status.stringValue = L("자를 영역을 드래그한 뒤 ‘자르기 적용’을 누르세요. 실행 취소로 복원할 수 있습니다.") }
    @objc private func cropImage() { canvas.cropToRegion(); fitImage() }
    @objc private func rotateImage() { canvas.transform(clockwise: true); fitImage() }
    @objc private func flipHorizontal() { canvas.transform(horizontal: true) }
    @objc private func flipVertical() { canvas.transform(vertical: true) }
    @objc private func resetOriginal() { canvas.resetOriginal(); fitImage() }
    @objc private func commitAnnotations() { if saveEdits() { onSave?(editedURL) } }
    func annotationPNG() -> Data? { canvas.exportImage().flatMap(capturePNG) }
    @objc private func changeStyle() {
        canvas.color = colorWell.color
        canvas.strokeWidth = [CGFloat(2), 4, 6, 10, 16, 24][widthMenu.indexOfSelectedItem]
        canvas.fontSize = [CGFloat(18), 28, 40, 56, 80][fontMenu.indexOfSelectedItem]
        refreshToolbarState()
        window?.makeFirstResponder(canvas)
    }
    @objc private func undoAction() { canvas.undoEdit() }
    @objc private func redoAction() { canvas.redoEdit() }
    @objc private func deleteAction() { canvas.deleteSelection(); window?.makeFirstResponder(canvas) }
    @objc private func copyAction() { canvas.copyComposite() }
    @objc private func pasteAction() { canvas.pasteClipboard(); toolMenu.selectItem(at: 0); window?.makeFirstResponder(canvas) }
    @objc private func cutRegion() { canvas.cutSelectedRegion() }
    @objc private func fitImage() {
        let size = scroll.contentSize
        canvas.zoom = max(0.05, min(1, min((size.width - 8) / canvas.imageSize.width, (size.height - 8) / canvas.imageSize.height)))
    }
    @objc private func actualSize() { canvas.zoom = 1 }
    @objc private func importImage() {
        let panel = NSOpenPanel(); panel.allowedFileTypes = ["png", "jpg", "jpeg"]; panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: window!) { [weak self] result in
            guard result == .OK, let url = panel.url, let image = captureLoadImage(url), let self = self else { return }
            self.canvas.addImage(image); self.toolMenu.selectItem(at: 0); self.refreshToolbarState(); self.window?.makeFirstResponder(self.canvas)
        }
    }
    private func scheduleSave() {
        dirty = true
        saveTimer?.invalidate()
        guard !captureSession else { return }
        saveTimer = Timer.scheduledTimer(withTimeInterval: 0.55, repeats: false) { [weak self] _ in self?.saveNow() }
    }
    @objc private func saveNow() { _ = saveEdits() }
    @discardableResult private func saveEdits() -> Bool {
        saveTimer?.invalidate(); saveTimer = nil
        guard let image = canvas.exportImage(), let data = capturePNG(image) else { status.stringValue = L("이미지를 저장하지 못했습니다."); return false }
        do {
            try FileManager.default.createDirectory(at: saveDirectory, withIntermediateDirectories: true)
            try data.write(to: editedURL, options: .atomic)
            dirty = false
            status.stringValue = Lf("자동 저장됨 · %@ · 원본은 유지됩니다.", editedURL.lastPathComponent)
            return true
        } catch { status.stringValue = Lf("저장 실패: %@", error.localizedDescription); return false }
    }
    @objc private func exportPNG() {
        let panel = NSSavePanel(); panel.allowedFileTypes = ["png"]; panel.directoryURL = saveDirectory; panel.nameFieldStringValue = editedURL.lastPathComponent
        panel.beginSheetModal(for: window!) { [weak self] result in
            guard result == .OK, let url = panel.url, let self = self, let image = self.canvas.exportImage(), let png = capturePNG(image) else { return }
            guard url.standardizedFileURL.resolvingSymlinksInPath() != self.imageURL.standardizedFileURL.resolvingSymlinksInPath() else { self.status.stringValue = L("원본 파일을 덮어쓰지 않습니다. 다른 이름으로 저장하세요."); return }
            do { try png.write(to: url, options: .atomic); self.status.stringValue = Lf("저장됨 · %@", url.lastPathComponent) }
            catch { self.status.stringValue = Lf("저장 실패: %@", error.localizedDescription) }
        }
    }
    private func openCutout(_ image: NSImage, suffix: String) {
        guard let data = capturePNG(image) else { return }
        let basename = imageURL.deletingPathExtension().lastPathComponent
        let url = saveDirectory.appendingPathComponent("\(basename)-\(suffix)-\(UUID().uuidString.prefix(6)).png")
        do {
            try FileManager.default.createDirectory(at: saveDirectory, withIntermediateDirectories: true)
            try data.write(to: url, options: .atomic)
            let child = CaptureEditorController(imageURL: url, saveDirectory: saveDirectory)
            CaptureEditorController.detachedEditors.append(child); child.showWindow(nil)
            status.stringValue = L("오린 이미지를 새 편집 창으로 열었습니다. 투명 영역은 PNG에 유지됩니다.")
        } catch { status.stringValue = Lf("오린 이미지 저장 실패: %@", error.localizedDescription) }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard !copyClosing, dirty else { return true }
        if saveEdits() { return true }
        let alert = NSAlert(); alert.messageText = L("편집 내용을 저장하지 못했습니다.")
        alert.informativeText = status.stringValue
        alert.addButton(withTitle: L("닫기 취소")); alert.addButton(withTitle: L("저장하지 않고 닫기"))
        return alert.runModal() == .alertSecondButtonReturn
    }
    func windowWillClose(_ notification: Notification) {
        saveTimer?.invalidate(); saveTimer = nil
        if let monitor = eventMonitor { NSEvent.removeMonitor(monitor); eventMonitor = nil }
        CaptureEditorController.detachedEditors.removeAll { $0 === self }
    }
}

/// Checks real raster rendering, masking alpha, and PNG round-trip without a window or clipboard access.
func captureEditorSelfCheck() -> Bool {
    let size = NSSize(width: 64, height: 48)
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 64, pixelsHigh: 48, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return false }
    guard let pixels = bitmap.bitmapData else { return false }
    for y in 0..<48 { for x in 0..<64 {
        let offset = y * bitmap.bytesPerRow + x * 4
        pixels[offset] = UInt8(x * 255 / 63); pixels[offset + 1] = UInt8(y * 255 / 47)
        pixels[offset + 2] = 64; pixels[offset + 3] = 255
    } }
    let base = NSImage(size: size); base.addRepresentation(bitmap)
    let cover = CaptureNode(kind: .cover, rect: NSRect(x: 8, y: 6, width: 12, height: 10), color: .black)
    guard let rendered = renderCapture(base, size: size, nodes: [cover]), let png = capturePNG(rendered), let check = NSBitmapImageRep(data: png), check.pixelsWide == 64, check.pixelsHigh == 48,
        let black = check.colorAt(x: 12, y: 10)?.usingColorSpace(.deviceRGB),
        black.redComponent < 0.03, black.greenComponent < 0.03, black.blueComponent < 0.03,
        let untouched = check.colorAt(x: 40, y: 20)?.usingColorSpace(.deviceRGB), untouched.redComponent > 0.5,
        let top = check.colorAt(x: 40, y: 1)?.usingColorSpace(.deviceRGB), top.greenComponent < 0.25,
        let bottom = check.colorAt(x: 40, y: 46)?.usingColorSpace(.deviceRGB), bottom.greenComponent > 0.85,
        let cropped = croppedCapture(rendered, rect: NSRect(x: 10, y: 10, width: 16, height: 12)), capturePixelSize(cropped) == NSSize(width: 16, height: 12) else { return false }
    guard let transparent = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 64, pixelsHigh: 48, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0), let bytes = transparent.bitmapData else { return false }
    bytes.initialize(repeating: 0, count: transparent.bytesPerRow * transparent.pixelsHigh)
    let empty = NSImage(size: size); empty.addRepresentation(transparent)
    guard let alphaImage = renderCapture(empty, size: size, nodes: [cover]), let alphaPNG = capturePNG(alphaImage), let alpha = NSBitmapImageRep(data: alphaPNG),
          let outside = alpha.colorAt(x: 40, y: 20), outside.alphaComponent < 0.01,
          let inside = alpha.colorAt(x: 12, y: 10), inside.alphaComponent > 0.99 else { return false }
    guard let rotated = transformedCapture(base, clockwise: true), capturePixelSize(rotated) == NSSize(width: 48, height: 64), let rotatePNG = capturePNG(rotated), let rotatedRep = NSBitmapImageRep(data: rotatePNG),
          let upper = rotatedRep.colorAt(x: 1, y: 1)?.usingColorSpace(.deviceRGB), upper.greenComponent > 0.8, upper.redComponent < 0.3,
          let horizontal = transformedCapture(base, horizontal: true), let horizontalPNG = capturePNG(horizontal), let horizontalRep = NSBitmapImageRep(data: horizontalPNG),
          let hColor = horizontalRep.colorAt(x: 1, y: 1)?.usingColorSpace(.deviceRGB), hColor.redComponent > 0.8, hColor.greenComponent < 0.3,
          let vertical = transformedCapture(base, vertical: true), let verticalPNG = capturePNG(vertical), let verticalRep = NSBitmapImageRep(data: verticalPNG),
          let vColor = verticalRep.colorAt(x: 1, y: 1)?.usingColorSpace(.deviceRGB), vColor.greenComponent > 0.8 else { return false }
    guard let croppedRep = croppedCapture(base, rect: NSRect(x: 8, y: 2, width: 20, height: 20)).flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)),
          let cropTop = croppedRep.colorAt(x: 5, y: 0)?.usingColorSpace(.deviceRGB), let cropBottom = croppedRep.colorAt(x: 5, y: 19)?.usingColorSpace(.deviceRGB), cropBottom.greenComponent > cropTop.greenComponent + 0.2 else { return false }
    for y in 0..<48 { for x in 0..<64 { let offset = y * bitmap.bytesPerRow + x * 4; let shade: UInt8 = (x + y) % 2 == 0 ? 0 : 255; pixels[offset] = shade; pixels[offset + 1] = shade; pixels[offset + 2] = shade; pixels[offset + 3] = 255 } }
    let checker = NSImage(size: size); checker.addRepresentation(bitmap)
    guard let blurred = filteredCapture(checker, pixelate: false, width: 4).flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), let blurColor = blurred.colorAt(x: 30, y: 24)?.usingColorSpace(.deviceRGB), blurColor.redComponent > 0.15, blurColor.redComponent < 0.85,
          let mosaic = filteredCapture(checker, pixelate: true, width: 4).flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), let blockA = mosaic.colorAt(x: 30, y: 24)?.usingColorSpace(.deviceRGB), let blockB = mosaic.colorAt(x: 31, y: 24)?.usingColorSpace(.deviceRGB), abs(blockA.redComponent - blockB.redComponent) < 0.02 else { return false }
    let canvas = CaptureCanvas(image: checker); canvas.annotationOnly = true
    canvas.addText("한글 주석", at: NSPoint(x: 4, y: 4))
    guard let overlay = canvas.exportImage().flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), overlay.colorAt(x: 62, y: 46)?.alphaComponent == 0 else { return false }
    canvas.undoEdit(); guard canvas.nodes.isEmpty else { return false }
    canvas.redoEdit(); guard canvas.nodes.count == 1 else { return false }
    canvas.annotationOnly = false; canvas.selectedRegion = NSRect(x: 4, y: 4, width: 24, height: 16)
    canvas.cropToRegion(); guard canvas.imageSize == NSSize(width: 24, height: 16), canvas.nodes.isEmpty else { return false }
    canvas.undoEdit(); guard canvas.imageSize == size, canvas.nodes.count == 1 else { return false }
    canvas.transform(clockwise: true); guard canvas.imageSize == NSSize(width: 48, height: 64), canvas.nodes.isEmpty else { return false }
    canvas.undoEdit(); canvas.resetOriginal(); guard canvas.imageSize == size, canvas.nodes.isEmpty else { return false }
    canvas.undoEdit(); guard canvas.nodes.count == 1 else { return false }
    let outline = CaptureNode(kind: .rectangle, rect: NSRect(x: 8, y: 6, width: 28, height: 24), color: .red, width: 2)
    let filled = CaptureNode(kind: .ellipse, rect: NSRect(x: 8, y: 6, width: 28, height: 24), color: .red, width: 2, filled: true, fillColor: .yellow)
    guard let outlinePixels = renderCapture(empty, size: size, nodes: [outline]).flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), outlinePixels.colorAt(x: 22, y: 18)?.alphaComponent == 0,
        let filledPixels = renderCapture(empty, size: size, nodes: [filled]).flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), let fillPixel = filledPixels.colorAt(x: 22, y: 18)?.usingColorSpace(.deviceRGB), fillPixel.redComponent > 0.95, fillPixel.greenComponent > 0.95, fillPixel.alphaComponent > 0.99 else { return false }
    let fillCanvas = CaptureCanvas(image: empty); fillCanvas.nodes = [outline]; fillCanvas.selectedID = outline.id
    fillCanvas.applyFill(true, color: .yellow); guard fillCanvas.nodes.first?.filled == true else { return false }
    fillCanvas.undoEdit(); guard fillCanvas.nodes.first?.filled == false else { return false }
    fillCanvas.redoEdit(); guard fillCanvas.nodes.first?.filled == true else { return false }
    let deleteCanvas = CaptureCanvas(image: empty)
    deleteCanvas.nodes = [outline, cover]; deleteCanvas.selectedID = outline.id
    deleteCanvas.deleteSelection()
    guard deleteCanvas.nodes.count == 1, deleteCanvas.nodes[0].id == cover.id, deleteCanvas.selectedID == nil else { return false }
    deleteCanvas.undoEdit()
    guard deleteCanvas.nodes.count == 2, deleteCanvas.nodes[0].id == outline.id else { return false }
    deleteCanvas.redoEdit()
    guard deleteCanvas.nodes.count == 1, deleteCanvas.nodes[0].id == cover.id else { return false }
    fillCanvas.nodes = []; fillCanvas.selectedID = nil
    fillCanvas.textBackgroundFilled = true; fillCanvas.fillColor = .yellow; fillCanvas.color = .black; fillCanvas.fontSize = 12
    fillCanvas.addText("A", at: NSPoint(x: 2, y: 2))
    guard fillCanvas.nodes.last?.textBackground == NSColor.yellow,
        let textPixels = fillCanvas.exportImage().flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), let textBackground = textPixels.colorAt(x: 35, y: 7)?.usingColorSpace(.deviceRGB), textBackground.redComponent > 0.95, textBackground.greenComponent > 0.95 else { return false }
    fillCanvas.applyFill(false, color: .yellow); guard fillCanvas.nodes.last?.textBackground == nil,
        let unfilledTextPixels = fillCanvas.exportImage().flatMap(capturePNG).flatMap(NSBitmapImageRep.init(data:)), unfilledTextPixels.colorAt(x: 35, y: 7)?.alphaComponent == 0 else { return false }
    fillCanvas.undoEdit(); guard fillCanvas.nodes.last?.textBackground == NSColor.yellow else { return false }
    fillCanvas.redoEdit(); guard fillCanvas.nodes.last?.textBackground == nil else { return false }
    return true
}

/// Native glyph/signature fixture for verifying transparent annotations after a PDF save and render.
func captureEditorWriteAnnotationFixture(to url: URL) -> Bool {
    let size = NSSize(width: 600, height: 800)
    guard let base = transparentCapture(size), let signatureBase = transparentCapture(NSSize(width: 200, height: 70)) else { return false }
    let strokes = CaptureNode(kind: .pen, rect: NSRect(x: 5, y: 8, width: 190, height: 55), points: [NSPoint(x: 8, y: 52), NSPoint(x: 35, y: 16), NSPoint(x: 27, y: 57), NSPoint(x: 67, y: 31), NSPoint(x: 84, y: 54), NSPoint(x: 118, y: 18), NSPoint(x: 104, y: 55), NSPoint(x: 172, y: 36), NSPoint(x: 187, y: 43)], color: .black, width: 3)
    guard let signature = renderCapture(signatureBase, size: signatureBase.size, nodes: [strokes]),
        let overlay = renderCapture(base, size: size, nodes: [CaptureNode(kind: .text, rect: NSRect(x: 40, y: 70, width: 520, height: 70), color: .black, text: "한글 주석 / 서명", fontSize: 34), CaptureNode(kind: .checkmark, rect: NSRect(x: 55, y: 180, width: 50, height: 45), color: .systemRed, width: 5), CaptureNode(kind: .image, rect: NSRect(x: 50, y: 260, width: 240, height: 84), image: signature)]), let data = capturePNG(overlay), let pixels = NSBitmapImageRep(data: data), pixels.colorAt(x: 590, y: 790)?.alphaComponent == 0 else { return false }
    var ink = 0
    for y in 70..<130 { for x in 40..<550 { if (pixels.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.5 { ink += 1 } } }
    guard ink > 300 else { return false }
    do { try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true); try data.write(to: url, options: .atomic); return true }
    catch { return false }
}

@discardableResult func galaxyCopyImage(_ image: NSImage) -> Bool {
    guard let png = capturePNG(image), !png.isEmpty else { return false }
    let board = NSPasteboard.general
    board.clearContents()
    guard board.setData(png, forType: .png), board.data(forType: .png) == png else { return false }
    if let tiff = image.tiffRepresentation { _ = board.setData(tiff, forType: .tiff) }
    return true
}

func galaxyCopyPNGFile(_ url: URL) -> Bool {
    var info = stat()
    guard lstat(url.path, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
          info.st_size > 8, info.st_size <= 268_435_456,
          let bytes = try? Data(contentsOf: url, options: .mappedIfSafe),
          bytes.prefix(8) == Data([137,80,78,71,13,10,26,10]),
          let source = CGImageSourceCreateWithData(bytes as CFData, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString:Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int,
          width > 0, height > 0, width <= 32768, height <= 32768,
          width <= 64_000_000 / height,
          let raster = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately:true] as CFDictionary) else { return false }
    return galaxyCopyImage(NSImage(cgImage: raster, size: NSSize(width: width, height: height)))
}
