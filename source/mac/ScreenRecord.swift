import AppKit
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import CoreVideo
import AudioToolbox

private enum RecordingPhase { case idle, preparing, recording, paused, stopping }

private struct RecordingOptions {
    var fps = 30
    var microphone = false
    var systemAudio = false
    var width = 0
    var scalePercent = 100
    var isValid: Bool { (5...60).contains(fps) && (width == 0 || (2...7680).contains(width)) && (10...100).contains(scalePercent) }
}

private struct RecordingTimeline {
    private(set) var paused = false
    private var pauseStart: CMTime?
    private(set) var offset = CMTime.zero
    mutating func pause(at time: CMTime) { guard !paused else { return }; paused = true; pauseStart = time }
    mutating func resume(at time: CMTime) {
        guard paused, let start = pauseStart else { return }
        let gap = CMTimeSubtract(time, start)
        if gap.isValid && CMTimeCompare(gap, .zero) > 0 { offset = CMTimeAdd(offset, gap) }
        paused = false; pauseStart = nil
    }
}

private func recordingOutputSize(rect: CGRect, scale: CGFloat, options: RecordingOptions) -> (Int, Int) {
    let native = recordingPixelSize(rect: rect, scale: scale)
    let factor = options.width > 0 ? min(1, Double(options.width) / Double(native.0)) : Double(options.scalePercent) / 100
    return (max(2, Int(Double(native.0) * factor) / 2 * 2), max(2, Int(Double(native.1) * factor) / 2 * 2))
}

private func recordingRetimedSample(_ sample: CMSampleBuffer, removing offset: CMTime) -> CMSampleBuffer? {
    if CMTimeCompare(offset, .zero) == 0 { return sample }
    var count = 0
    guard CMSampleBufferGetSampleTimingInfoArray(sample, entryCount: 0, arrayToFill: nil, entriesNeededOut: &count) == noErr, count > 0 else { return nil }
    var timing = Array(repeating: CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: .invalid, decodeTimeStamp: .invalid), count: count)
    guard CMSampleBufferGetSampleTimingInfoArray(sample, entryCount: count, arrayToFill: &timing, entriesNeededOut: &count) == noErr else { return nil }
    for index in timing.indices {
        if timing[index].presentationTimeStamp.isValid { timing[index].presentationTimeStamp = CMTimeSubtract(timing[index].presentationTimeStamp, offset) }
        if timing[index].decodeTimeStamp.isValid { timing[index].decodeTimeStamp = CMTimeSubtract(timing[index].decodeTimeStamp, offset) }
    }
    var result: CMSampleBuffer?
    guard CMSampleBufferCreateCopyWithNewTiming(allocator: kCFAllocatorDefault, sampleBuffer: sample, sampleTimingEntryCount: count, sampleTimingArray: &timing, sampleBufferOut: &result) == noErr else { return nil }
    return result
}

// Two independent AAC tracks do not reliably play together in ordinary MP4 players.
// Export a mix only when both sources delivered samples; keep the original on failure.
private func recordingMixAudioTracks(source: URL, output: URL, completion: @escaping (Error?) -> Void) {
    do {
        let asset = AVURLAsset(url: source), composition = AVMutableComposition()
        let fullRange = CMTimeRange(start: .zero, duration: asset.duration)
        for original in asset.tracks(withMediaType: .video) {
            guard let track = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else { throw NSError(domain: "LocalTools.Record", code: 6) }
            try track.insertTimeRange(fullRange, of: original, at: .zero); track.preferredTransform = original.preferredTransform
        }
        var parameters: [AVAudioMixInputParameters] = []
        for original in asset.tracks(withMediaType: .audio) {
            guard let track = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else { throw NSError(domain: "LocalTools.Record", code: 7) }
            let range = CMTimeRangeGetIntersection(fullRange, otherRange: original.timeRange)
            try track.insertTimeRange(range, of: original, at: range.start)
            let parameter = AVMutableAudioMixInputParameters(track: track); parameter.setVolume(0.5, at: .zero); parameters.append(parameter)
        }
        guard parameters.count >= 2, let exporter = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality), exporter.supportedFileTypes.contains(.mp4) else { throw NSError(domain: "LocalTools.Record", code: 8) }
        let mix = AVMutableAudioMix(); mix.inputParameters = parameters
        exporter.audioMix = mix; exporter.outputURL = output; exporter.outputFileType = .mp4
        exporter.exportAsynchronously { completion(exporter.status == .completed ? nil : exporter.error ?? NSError(domain: "LocalTools.Record", code: 9)) }
    } catch { completion(error) }
}

private final class RecordingBorderView: NSView {
    var paused = false { didSet { needsDisplay = true } }
    override func draw(_ dirtyRect: NSRect) {
        (paused ? NSColor.systemOrange : NSColor.systemRed).setStroke()
        let path = NSBezierPath(rect:bounds.insetBy(dx:2,dy:2)); path.lineWidth = 3; path.stroke()
        let label = paused ? "Ⅱ " + L("일시정지") : "● " + L("녹화 중")
        NSString(string:label).draw(at:NSPoint(x:10,y:bounds.height-25),withAttributes:[.font:NSFont.systemFont(ofSize:14,weight:.semibold),.foregroundColor:NSColor.white,.backgroundColor:NSColor.black.withAlphaComponent(0.75)])
    }
}

private final class RecordingRegionWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private final class RecordingRegionView: NSView {
    var completion: ((NSRect?) -> Void)?
    private var origin: NSPoint?
    private var region: NSRect?
    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.withAlphaComponent(0.35).setFill(); bounds.fill()
        if let region = region {
            NSColor.clear.setFill(); region.fill(using: .copy)
            NSColor.white.setStroke(); let path = NSBezierPath(rect: region); path.lineWidth = 2; path.stroke()
            let size = recordingPixelSize(rect: region, scale: window?.backingScaleFactor ?? 1)
            let caption = "\(size.0) × \(size.1) px"
            NSString(string: caption).draw(at: NSPoint(x: region.minX + 8, y: max(8, region.minY - 28)), withAttributes: [.font: NSFont.systemFont(ofSize: 17, weight: .semibold), .foregroundColor: NSColor.white])
        }
        NSString(string: L("녹화할 영역을 드래그하세요. Esc: 취소")).draw(at: NSPoint(x: 24, y: 24), withAttributes: [.font: NSFont.systemFont(ofSize: 22, weight: .semibold), .foregroundColor: NSColor.white])
    }
    private func position(_ event: NSEvent) -> NSPoint {
        let value = convert(event.locationInWindow, from: nil)
        return NSPoint(x: max(0, min(bounds.width, value.x)), y: max(0, min(bounds.height, value.y)))
    }
    override func mouseDown(with event: NSEvent) { origin = position(event); region = NSRect(origin: origin!, size: .zero); needsDisplay = true }
    override func mouseDragged(with event: NSEvent) {
        guard let origin = origin else { return }; let point = position(event)
        region = NSRect(x: min(origin.x, point.x), y: min(origin.y, point.y), width: abs(origin.x - point.x), height: abs(origin.y - point.y)); needsDisplay = true
    }
    override func mouseUp(with event: NSEvent) {
        guard let region = region, region.width >= 10, region.height >= 10 else { NSSound.beep(); return }
        completion?(region.integral)
    }
    override func keyDown(with event: NSEvent) { if event.keyCode == 53 { completion?(nil) } else { super.keyDown(with: event) } }
}

private func recordingPixelSize(rect: CGRect, scale: CGFloat) -> (Int, Int) {
    // H.264 requires even pixel dimensions; the sampled region itself remains unchanged.
    (max(2, Int((rect.width * scale).rounded()) / 2 * 2), max(2, Int((rect.height * scale).rounded()) / 2 * 2))
}

@available(macOS 13.0, *)
private final class NativeRecordingSession: NSObject, SCStreamOutput, SCStreamDelegate {
    private let queue = DispatchQueue(label: "LocalTools.screen-record.writer", qos: .userInitiated)
    private let writer: AVAssetWriter
    private let video: AVAssetWriterInput
    private let systemAudio: AVAssetWriterInput?
    private let microphone: AVAssetWriterInput?
    private let options: RecordingOptions
    private let temporaryURL: URL
    private let finalURL: URL
    private var stream: SCStream!
    private var firstTime: CMTime?
    private var lastTime: CMTime?
    private var lastEndTime: CMTime?
    private var lastMediaTimes: [String: CMTime] = [:]
    private var timeline = RecordingTimeline()
    private var audioSampleCounts = ["system": 0, "microphone": 0]
    private var ending = false
    private var finished = false
    private var appendError: Error?
    var started: ((Error?) -> Void)?
    var completed: ((URL?, String) -> Void)?

    init(display: SCDisplay, applications: [SCRunningApplication], window: SCWindow? = nil, rect: CGRect, scale: CGFloat, options: RecordingOptions, outputDirectory: URL) throws {
        self.options = options
        let id = UUID().uuidString
        let formatter = DateFormatter(); formatter.dateFormat = "yyyyMMdd-HHmmss"
        finalURL = outputDirectory.appendingPathComponent("Recording-\(formatter.string(from: Date()))-\(id.prefix(8)).mp4")
        temporaryURL = outputDirectory.appendingPathComponent(".Recording-\(id).partial.mp4")
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        writer = try AVAssetWriter(outputURL: temporaryURL, fileType: .mp4)
        let (width, height) = recordingOutputSize(rect: rect, scale: scale, options: options)
        video = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height, AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: min(36_000_000, max(2_000_000, width * height * max(1, options.fps / 6))), AVVideoExpectedSourceFrameRateKey: options.fps, AVVideoMaxKeyFrameIntervalKey: options.fps * 2]])
        video.expectsMediaDataInRealTime = true
        func audioInput(channels: Int) -> AVAssetWriterInput {
            let input = AVAssetWriterInput(mediaType: .audio, outputSettings: [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: channels, AVEncoderBitRateKey: channels * 64000])
            input.expectsMediaDataInRealTime = true
            return input
        }
        systemAudio = options.systemAudio ? audioInput(channels: 2) : nil
        microphone = options.microphone ? audioInput(channels: 1) : nil
        super.init()
        guard writer.canAdd(video) else { throw NSError(domain: "LocalTools.Record", code: 1, userInfo: [NSLocalizedDescriptionKey: L("이 화면 크기로 MP4를 생성할 수 없습니다. 더 작은 영역을 선택하세요.")]) }
        writer.add(video)
        for input in [systemAudio, microphone].compactMap({ $0 }) {
            guard writer.canAdd(input) else { throw NSError(domain: "LocalTools.Record", code: 4, userInfo: [NSLocalizedDescriptionKey: L("오디오를 MP4에 저장할 수 없습니다.")]) }
            writer.add(input)
        }
        let config = SCStreamConfiguration()
        config.width = width; config.height = height; config.sourceRect = rect
        config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(options.fps))
        config.queueDepth = 5; config.pixelFormat = kCVPixelFormatType_32BGRA
        config.showsCursor = true; config.capturesAudio = options.systemAudio
        config.excludesCurrentProcessAudio = true; config.sampleRate = 48000; config.channelCount = 2
        if #available(macOS 15.0, *) { config.captureMicrophone = options.microphone }
        let ownApps = applications.filter { $0.processID == ProcessInfo.processInfo.processIdentifier }
        let filter = window.map { SCContentFilter(desktopIndependentWindow: $0) } ?? SCContentFilter(display: display, excludingApplications: ownApps, exceptingWindows: [])
        stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        if options.systemAudio { try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue) }
        if #available(macOS 15.0, *), options.microphone { try stream.addStreamOutput(self, type: .microphone, sampleHandlerQueue: queue) }
    }
    func begin() {
        queue.async {
            guard self.writer.startWriting() else { self.failBeforeStart(self.writer.error); return }
            self.stream.startCapture { [weak self] error in
                guard let self = self else { return }
                if let error = error { self.queue.async { self.failBeforeStart(error) } }
                else { DispatchQueue.main.async { self.started?(nil) } }
            }
        }
    }
    private func failBeforeStart(_ error: Error?) {
        guard !finished else { return }; finished = true; writer.cancelWriting()
        try? FileManager.default.removeItem(at: temporaryURL)
        DispatchQueue.main.async { self.started?(error ?? NSError(domain: "LocalTools.Record", code: 2, userInfo: [NSLocalizedDescriptionKey: L("녹화를 시작하지 못했습니다.")])) }
    }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard !ending, !finished, !timeline.paused, CMSampleBufferDataIsReady(sampleBuffer) else { return }
        var input: AVAssetWriterInput?, key = ""
        if type == .screen { input = video; key = "video" }
        else if type == .audio { input = systemAudio; key = "system" }
        else if #available(macOS 15.0, *), type == .microphone { input = microphone; key = "microphone" }
        guard let input = input else { return }
        if type == .screen, let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
           let status = attachments.first?[.status] as? Int, status != SCFrameStatus.complete.rawValue { return }
        guard let sample = recordingRetimedSample(sampleBuffer, removing: timeline.offset) else { appendError = NSError(domain: "LocalTools.Record", code: 5, userInfo: [NSLocalizedDescriptionKey: L("녹화 시간을 조정하지 못했습니다.")]); stop(); return }
        let time = CMSampleBufferGetPresentationTimeStamp(sample)
        guard time.isValid, !time.isIndefinite else { return }
        if firstTime == nil { guard type == .screen else { return }; firstTime = time; writer.startSession(atSourceTime: time) }
        guard let firstTime = firstTime, CMTimeCompare(time, firstTime) >= 0 else { return }
        if let previous = lastMediaTimes[key], CMTimeCompare(time, previous) <= 0 { return }
        if input.isReadyForMoreMediaData {
            if input.append(sample) {
                lastMediaTimes[key] = time
                if type == .screen { lastTime = time } else { audioSampleCounts[key, default: 0] += 1 }
                let duration = CMSampleBufferGetDuration(sample), end = CMTimeAdd(time, duration.isValid && CMTimeCompare(duration, .zero) > 0 ? duration : CMTime(value: 1, timescale: CMTimeScale(options.fps)))
                if lastEndTime == nil || CMTimeCompare(end, lastEndTime!) > 0 { lastEndTime = end }
            } else { appendError = writer.error ?? NSError(domain: "LocalTools.Record", code: 3, userInfo: [NSLocalizedDescriptionKey: L("영상 또는 오디오를 저장하지 못했습니다.")]); stop() }
        }
    }
    func setPaused(_ paused: Bool, completion: @escaping (Bool) -> Void) {
        queue.async {
            guard !self.ending, !self.finished, self.timeline.paused != paused else { DispatchQueue.main.async { completion(false) }; return }
            let now = CMClockGetTime(CMClockGetHostTimeClock())
            if paused { self.timeline.pause(at: now) } else { self.timeline.resume(at: now) }
            DispatchQueue.main.async { completion(true) }
        }
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) { queue.async { self.appendError = error; self.finish() } }
    func stop() {
        queue.async {
            guard !self.ending, !self.finished else { return }; self.ending = true
            self.stream.stopCapture { [weak self] error in
                guard let self = self else { return }
                self.queue.async { if let error = error, self.appendError == nil { self.appendError = error }; self.finish() }
            }
        }
    }
    private func finish() {
        guard !finished else { return }; finished = true; ending = true
        guard let lastTime = lastTime else { writer.cancelWriting(); try? FileManager.default.removeItem(at: temporaryURL); report(nil, L("영상 프레임이 없어 녹화 파일을 만들지 못했습니다. 화면 기록 권한을 확인하세요.")); return }
        writer.endSession(atSourceTime: lastEndTime ?? CMTimeAdd(lastTime, CMTime(value: 1, timescale: CMTimeScale(options.fps))))
        video.markAsFinished()
        systemAudio?.markAsFinished(); microphone?.markAsFinished()
        writer.finishWriting {
            self.queue.async {
                guard self.writer.status == .completed else { self.report(nil, Lf("영상 저장 실패: %@", self.writer.error?.localizedDescription ?? L("파일을 완료하지 못했습니다."))); return }
                if self.audioSampleCounts["system", default: 0] > 0 && self.audioSampleCounts["microphone", default: 0] > 0 {
                    let mixed = self.temporaryURL.deletingPathExtension().appendingPathExtension("mixed.mp4")
                    recordingMixAudioTracks(source: self.temporaryURL, output: mixed) { error in
                        self.queue.async {
                            if let error = error { self.report(nil, Lf("마이크와 시스템 오디오를 합치지 못했습니다. 원본 임시 파일을 보존했습니다: %@", error.localizedDescription)) }
                            else { self.publish(mixed); if FileManager.default.fileExists(atPath: self.finalURL.path) { try? FileManager.default.removeItem(at: self.temporaryURL) } }
                        }
                    }
                } else { self.publish(self.temporaryURL) }
            }
        }
    }
    private func publish(_ source: URL) {
        let asset = AVURLAsset(url: source), seconds = CMTimeGetSeconds(asset.duration)
        guard seconds.isFinite, seconds > 0, let track = asset.tracks(withMediaType: .video).first, track.naturalSize.width > 0, track.naturalSize.height > 0 else { report(nil, Lf("녹화 파일을 검증하지 못했습니다. 임시 파일: %@", source.lastPathComponent)); return }
        if (options.systemAudio && audioSampleCounts["system", default: 0] == 0) || (options.microphone && audioSampleCounts["microphone", default: 0] == 0) { report(nil, L("요청한 오디오 샘플을 받지 못했습니다. 원본 임시 파일을 보존했습니다.")); return }
        do {
            try FileManager.default.moveItem(at: source, to: finalURL)
            let note = appendError.map { Lf(" · 연결 종료: %@", $0.localizedDescription) } ?? ""
            report(finalURL, Lf("녹화 저장 완료 · %.1f초%@", seconds, note))
        } catch { report(nil, Lf("검증한 영상의 저장 위치를 바꾸지 못했습니다: %@", error.localizedDescription)) }
    }
    private func report(_ url: URL?, _ message: String) { DispatchQueue.main.async { self.completed?(url, message) } }
}

final class ScreenRecordController: NSObject {
    private let displayMenu = NSPopUpButton()
    private let modeMenu = NSPopUpButton()
    private let fpsField = NSTextField(string: "30")
    private let resolutionMenu = NSPopUpButton()
    private let scaleField = NSTextField(string: "100")
    private let microphoneCheck = NSButton(checkboxWithTitle: L("마이크"), target: nil, action: nil)
    private let systemAudioCheck = NSButton(checkboxWithTitle: L("시스템 오디오"), target: nil, action: nil)
    private let destination = NSTextField(labelWithString: "")
    private let status = NSTextField(wrappingLabelWithString: L("모니터와 녹화 범위를 선택하세요. MP4 영상과 선택한 오디오를 저장합니다."))
    private let elapsed = NSTextField(labelWithString: "00:00")
    private let spinner = NSProgressIndicator()
    private var startButton: NSButton!
    private var stopButton: NSButton!
    private var pauseButton: NSButton!
    private var controls: [NSControl] = []
    private var screens: [NSScreen] = []
    private var phase: RecordingPhase = .idle
    private var nativeSession: AnyObject?
    private var timer: Timer?
    private var startTime: Date?
    private var pauseStarted: Date?
    private var pausedSeconds: TimeInterval = 0
    private var options = RecordingOptions()
    private var regionWindow: NSWindow?
    private var borderWindow: NSWindow?
    private var outputDirectory: URL
    private var lastFile: URL?
    private var cachedView: NSView?
    private var nativeStartCompletion: ((String) -> Void)?
    private var nativeStopCompletion: ((URL?, String) -> Void)?
    var isRecording: Bool { phase != .idle }
    var isPaused: Bool { phase == .paused }

    init(saveDirectory: URL? = nil) {
        let previous = UserDefaults.standard.string(forKey: "record.saveDirectory").map { URL(fileURLWithPath: $0, isDirectory: true) }
        outputDirectory = saveDirectory ?? previous ?? (FileManager.default.urls(for: .moviesDirectory, in: .userDomainMask).first ?? FileManager.default.temporaryDirectory).appendingPathComponent("LocalTools", isDirectory: true)
        super.init()
    }
    func useSaveDirectory(_ url: URL) {
        outputDirectory = url; destination.stringValue = url.path
        UserDefaults.standard.set(url.path, forKey: "record.saveDirectory")
    }
    func makeView() -> NSView {
        if let cachedView = cachedView { return cachedView }
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 920, height: 650))
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 18
        stack.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 24), stack.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -24), stack.topAnchor.constraint(equalTo: root.topAnchor, constant: 24)])
        let title = NSTextField(labelWithString: L("화면 녹화")); title.font = NSFont.systemFont(ofSize: 24, weight: .semibold); stack.addArrangedSubview(title)
        modeMenu.addItems(withTitles: [L("선택한 모니터 전체"), L("선택한 모니터의 사각 영역"), L("선택한 창")])
        controls += [displayMenu, modeMenu, fpsField, resolutionMenu, scaleField, microphoneCheck, systemAudioCheck]
        let row = NSStackView(views: [NSTextField(labelWithString: L("모니터")), displayMenu, button(L("목록 새로고침"), #selector(refreshDisplays))]); row.spacing = 10; stack.addArrangedSubview(row)
        stack.addArrangedSubview(modeMenu)
        resolutionMenu.addItem(withTitle: L("원본 해상도")); resolutionMenu.lastItem?.tag = 0
        for width in [1920, 1280, 960, 640] { resolutionMenu.addItem(withTitle: "\(width) px"); resolutionMenu.lastItem?.tag = width }
        fpsField.widthAnchor.constraint(equalToConstant: 56).isActive = true; scaleField.widthAnchor.constraint(equalToConstant: 56).isActive = true
        let quality = NSStackView(views: [NSTextField(labelWithString: "FPS (5–60)"), fpsField, NSTextField(labelWithString: L("해상도")), resolutionMenu, NSTextField(labelWithString: L("원본 배율 (%)")), scaleField]); quality.spacing = 10; stack.addArrangedSubview(quality)
        let audio = NSStackView(views: [systemAudioCheck, microphoneCheck]); audio.spacing = 18; stack.addArrangedSubview(audio)
        if #available(macOS 15.0, *) {} else { microphoneCheck.isEnabled = false; microphoneCheck.toolTip = L("마이크 녹화는 macOS 15 이상에서 지원됩니다.") }
        let note = NSTextField(wrappingLabelWithString: L("MP4 (H.264), 5–60fps. 원본보다 크게 확대하지 않습니다. 시스템 오디오는 앱 단위로 캡처하며 이 앱의 창과 소리는 제외됩니다. 마이크는 macOS 15 이상에서 지원됩니다."))
        note.textColor = .secondaryLabelColor; stack.addArrangedSubview(note); note.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        destination.stringValue = outputDirectory.path; destination.lineBreakMode = .byTruncatingMiddle
        let folder = NSStackView(views: [button(L("저장 위치…"), #selector(pickDestination)), destination]); folder.spacing = 10; stack.addArrangedSubview(folder)
        startButton = button(L("녹화 시작"), #selector(beginRecording)); stopButton = NSButton(title: L("녹화 중지"), target: self, action: #selector(stop)); stopButton.bezelStyle = .rounded; stopButton.isEnabled = false
        pauseButton = NSButton(title: L("일시정지"), target: self, action: #selector(togglePause)); pauseButton.bezelStyle = .rounded; pauseButton.isEnabled = false
        elapsed.font = NSFont.monospacedDigitSystemFont(ofSize: 25, weight: .medium)
        spinner.style = .spinning; spinner.controlSize = .small; spinner.isDisplayedWhenStopped = false
        let actions = NSStackView(views: [startButton, pauseButton, stopButton, elapsed, spinner]); actions.spacing = 14; stack.addArrangedSubview(actions)
        let results = NSStackView(views: [button(L("마지막 영상 열기"), #selector(openLastVideo)), button(L("저장 폴더 열기"), #selector(openFolder)), button(L("화면 기록 권한 설정 열기"), #selector(openPermissionSettings))]); results.spacing = 10; stack.addArrangedSubview(results)
        let permissionHelp = NSTextField(wrappingLabelWithString: L("권한이 없으면 ‘화면 기록 권한 설정 열기’에서 이 앱을 허용하세요. 허용 후 앱을 다시 열어야 할 수 있습니다."))
        permissionHelp.font = NSFont.systemFont(ofSize: 11); permissionHelp.textColor = .secondaryLabelColor
        stack.addArrangedSubview(permissionHelp); permissionHelp.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        stack.addArrangedSubview(status); status.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        cachedView = root; refreshDisplays()
        if #available(macOS 13.0, *) {} else { startButton.isEnabled = false; modeMenu.isEnabled = false; status.stringValue = L("화면 녹화는 macOS 13 이상에서 사용할 수 있습니다. 현재 시스템에서는 화면 캡처를 사용하세요.") }
        return root
    }
    private func button(_ title: String, _ action: Selector) -> NSButton { let value = NSButton(title: title, target: self, action: action); value.bezelStyle = .rounded; controls.append(value); return value }
    @objc private func refreshDisplays() {
        guard phase == .idle else { return }
        screens = NSScreen.screens; displayMenu.removeAllItems()
        for (index, screen) in screens.enumerated() { displayMenu.addItem(withTitle: "\(index + 1). \(screen.localizedName) · \(Int(screen.frame.width)) × \(Int(screen.frame.height))") }
        if screens.isEmpty { status.stringValue = L("사용할 모니터를 찾지 못했습니다."); startButton?.isEnabled = false }
    }
    @objc private func pickDestination() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true; panel.directoryURL = outputDirectory
        if panel.runModal() == .OK, let url = panel.url { useSaveDirectory(url) }
    }
    private func updatePhase(_ value: RecordingPhase) {
        if value == .idle || value == .stopping { borderWindow?.orderOut(nil); borderWindow?.close(); borderWindow = nil }
        (borderWindow?.contentView as? RecordingBorderView)?.paused = value == .paused
        phase = value; controls.forEach { $0.isEnabled = value == .idle }
        stopButton?.isEnabled = value == .recording || value == .paused
        pauseButton?.isEnabled = value == .recording || value == .paused
        pauseButton?.title = L(value == .paused ? "녹화 재개" : "일시정지")
        if #available(macOS 15.0, *) {} else { microphoneCheck.isEnabled = false }
        if value == .preparing || value == .stopping { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }
        if #available(macOS 13.0, *) {} else { startButton?.isEnabled = false }
    }
    /// Native broker replies only after SCStream actually starts; completion runs on the main queue.
    func startNative(mode: String, monitor: Int, fps: Int = 30, microphone: Bool = false, systemAudio: Bool = false, width: Int = 0, scalePercent: Int = 100, format: String = "mp4", completion: @escaping (String) -> Void) {
        guard #available(macOS 13.0, *) else { completion("unsupported"); return }
        guard phase == .idle else { completion("conflict"); return }
        _ = makeView(); refreshDisplays()
        let requested = RecordingOptions(fps: fps, microphone: microphone, systemAudio: systemAudio, width: width, scalePercent: scalePercent)
        guard ["full", "area", "window"].contains(mode), screens.indices.contains(monitor), requested.isValid, format == "mp4" else { completion("invalidRequest"); return }
        if microphone { guard #available(macOS 15.0, *) else { completion("unsupported"); return } }
        displayMenu.selectItem(at: monitor); modeMenu.selectItem(at: mode == "area" ? 1 : mode == "window" ? 2 : 0)
        fpsField.integerValue = fps; scaleField.integerValue = scalePercent
        if resolutionMenu.itemArray.first(where: { $0.tag == width }) == nil { resolutionMenu.addItem(withTitle: "\(width) px"); resolutionMenu.lastItem?.tag = width }
        resolutionMenu.selectItem(withTag: width); microphoneCheck.state = microphone ? .on : .off; systemAudioCheck.state = systemAudio ? .on : .off
        nativeStartCompletion = completion
        beginRecording()
    }
    func stopNative(completion: @escaping (URL?, String) -> Void) {
        guard (phase == .recording || phase == .paused), nativeStopCompletion == nil else { completion(nil, "conflict"); return }
        nativeStopCompletion = completion; stop()
    }
    private func completeNativeStart(_ error: String) { let callback = nativeStartCompletion; nativeStartCompletion = nil; callback?(error) }
    func pauseNative(completion: @escaping (String) -> Void) { setPaused(true, completion: completion) }
    func resumeNative(completion: @escaping (String) -> Void) { setPaused(false, completion: completion) }
    @objc private func togglePause() { setPaused(phase != .paused) { [weak self] error in if !error.isEmpty { self?.status.stringValue = L("녹화 상태를 변경하지 못했습니다.") } } }
    private func setPaused(_ paused: Bool, completion: @escaping (String) -> Void) {
        guard #available(macOS 13.0, *), phase == (paused ? .recording : .paused), let session = nativeSession as? NativeRecordingSession else { completion("conflict"); return }
        pauseButton?.isEnabled = false
        session.setPaused(paused) { [weak self, weak session] success in
            guard let self = self, let session = session, self.nativeSession === session, self.phase == (paused ? .recording : .paused) else { completion("conflict"); return }
            guard success else { self.updatePhase(self.phase); completion("conflict"); return }
            if paused { self.pauseStarted = Date() }
            else { if let start = self.pauseStarted { self.pausedSeconds += Date().timeIntervalSince(start) }; self.pauseStarted = nil }
            self.updatePhase(paused ? .paused : .recording); self.updateElapsed(); self.status.stringValue = L(paused ? "녹화 일시정지 · 정지 구간은 저장 영상에서 제외됩니다." : "● 녹화 재개"); completion("")
        }
    }
    @objc private func beginRecording() {
        guard #available(macOS 13.0, *), phase == .idle, screens.indices.contains(displayMenu.indexOfSelectedItem) else { return }
        options = RecordingOptions(fps: fpsField.integerValue, microphone: microphoneCheck.state == .on, systemAudio: systemAudioCheck.state == .on, width: resolutionMenu.selectedItem?.tag ?? 0, scalePercent: scaleField.integerValue)
        guard options.isValid else { status.stringValue = L("FPS는 5–60, 배율은 10–100% 범위로 입력하세요."); completeNativeStart("invalidRequest"); return }
        if options.microphone {
            guard #available(macOS 15.0, *) else { status.stringValue = L("마이크 녹화는 macOS 15 이상에서 지원됩니다."); completeNativeStart("unsupported"); return }
            switch AVCaptureDevice.authorizationStatus(for: .audio) {
            case .authorized: break
            case .notDetermined:
                guard Bundle.main.object(forInfoDictionaryKey: "NSMicrophoneUsageDescription") is String else { status.stringValue = L("앱에 마이크 권한 설명이 없습니다. 업데이트한 앱을 사용하세요."); completeNativeStart("unsupported"); return }
                updatePhase(.preparing)
                AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in DispatchQueue.main.async { guard let self = self else { return }; self.updatePhase(.idle); if granted { self.beginRecording() } else { self.status.stringValue = L("마이크 권한이 필요합니다."); self.completeNativeStart("permissionRequired") } } }
                return
            default: status.stringValue = L("마이크 권한이 필요합니다."); completeNativeStart("permissionRequired"); return
            }
        }
        // SCShareableContent requests/checks consent for the actual running app.
        let screen = screens[displayMenu.indexOfSelectedItem]
        let displayID = (screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0
        updatePhase(.preparing); status.stringValue = L("녹화할 화면을 준비하는 중…")
        SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { [weak self] content, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard let content = content, let display = content.displays.first(where: { $0.displayID == displayID }) else { self.updatePhase(.idle); self.status.stringValue = Lf("화면을 가져오지 못했습니다. 화면 기록 권한을 확인하세요. %@", error?.localizedDescription ?? L("모니터 정보가 변경되었습니다.")); self.completeNativeStart(error.map(galaxyCaptureErrorCode) ?? "recordMonitorMissing"); return }
                let full = CGRect(x: 0, y: 0, width: display.frame.width, height: display.frame.height)
                if self.modeMenu.indexOfSelectedItem == 1 {
                    self.chooseRegion(on: screen) { [weak self] rect in
                        guard let self = self else { return }
                        guard let rect = rect else { self.updatePhase(.idle); self.status.stringValue = L("영역 선택을 취소했습니다."); self.completeNativeStart("cancelled"); return }
                        self.startSession(display: display, applications: content.applications, rect: rect.intersection(full), scale: screen.backingScaleFactor)
                    }
                } else if self.modeMenu.indexOfSelectedItem == 2 {
                    guard let window = self.chooseWindow(content.windows.filter { $0.frame.intersects(display.frame) && $0.owningApplication?.processID != ProcessInfo.processInfo.processIdentifier && $0.frame.width >= 4 && $0.frame.height >= 4 }) else { self.updatePhase(.idle); self.status.stringValue = L("창 선택을 취소했습니다."); self.completeNativeStart("cancelled"); return }
                    self.startSession(display: display, applications: content.applications, window: window, rect: CGRect(origin: .zero, size: window.frame.size), scale: screen.backingScaleFactor)
                } else { self.startSession(display: display, applications: content.applications, rect: full, scale: screen.backingScaleFactor) }
            }
        }
    }
    @available(macOS 13.0, *) private func chooseWindow(_ windows: [SCWindow]) -> SCWindow? {
        guard !windows.isEmpty else { return nil }
        let menu = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 450, height: 28))
        for window in windows { menu.addItem(withTitle: (window.owningApplication?.applicationName ?? "") + " · " + (window.title?.isEmpty == false ? window.title! : L("제목 없는 창"))) }
        let alert = NSAlert(); alert.messageText = L("녹화할 창을 선택하세요."); alert.informativeText = L("선택한 창만 MP4로 저장합니다. 시스템 오디오를 켜면 해당 앱의 소리가 포함됩니다."); alert.accessoryView = menu
        alert.addButton(withTitle: L("녹화 시작")); alert.addButton(withTitle: L("취소"))
        guard alert.runModal() == .alertFirstButtonReturn, windows.indices.contains(menu.indexOfSelectedItem) else { return nil }
        return windows[menu.indexOfSelectedItem]
    }
    private func chooseRegion(on screen: NSScreen, completion: @escaping (CGRect?) -> Void) {
        let window = RecordingRegionWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false, screen: screen)
        window.isOpaque = false; window.backgroundColor = .clear; window.level = .screenSaver
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]; window.isReleasedWhenClosed = false
        let view = RecordingRegionView(frame: NSRect(origin: .zero, size: screen.frame.size)); window.contentView = view
        let visible = NSApp.windows.filter { $0.isVisible }
        let previousKeyWindow = NSApp.keyWindow
        view.completion = { [weak self, weak window] rect in
            window?.orderOut(nil); window?.close(); self?.regionWindow = nil
            visible.forEach { $0.orderFront(nil) }; previousKeyWindow?.makeKeyAndOrderFront(nil); completion(rect)
        }
        regionWindow = window
        galaxyHideCaptureWindows { [weak self, weak window] hidden in
            guard let self = self, let window = window, self.regionWindow === window else { return }
            guard hidden else { view.completion?(nil); return }
            window.makeKeyAndOrderFront(nil); window.makeFirstResponder(view); NSApp.activate(ignoringOtherApps:true)
        }
        status.stringValue = L("선택한 모니터에서 녹화할 영역을 드래그하세요. Esc로 취소할 수 있습니다.")
    }
    @available(macOS 13.0, *) private func startSession(display: SCDisplay, applications: [SCRunningApplication], window: SCWindow? = nil, rect: CGRect, scale: CGFloat) {
        do {
            let session = try NativeRecordingSession(display: display, applications: applications, window: window, rect: rect, scale: scale, options: options, outputDirectory: outputDirectory)
            session.started = { [weak self, weak session] error in
                guard let self = self, let session = session, self.nativeSession === session, self.phase == .preparing else { return }
                if let error = error { self.nativeSession = nil; self.updatePhase(.idle); self.status.stringValue = Lf("녹화 시작 실패: %@", error.localizedDescription); self.completeNativeStart("processingFailed"); return }
                self.startTime = Date(); self.pauseStarted = nil; self.pausedSeconds = 0; self.elapsed.stringValue = "00:00"; self.updatePhase(.recording); self.completeNativeStart("")
                if let screen = NSScreen.screens.first(where: { ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value == display.displayID }) {
                    let global = window?.frame ?? CGRect(x:display.frame.minX+rect.minX,y:display.frame.minY+rect.minY,width:rect.width,height:rect.height)
                    let frame = CGRect(x:screen.frame.minX+global.minX-display.frame.minX,y:screen.frame.maxY-(global.minY-display.frame.minY)-global.height,width:global.width,height:global.height)
                    let border = NSPanel(contentRect:frame,styleMask:.borderless,backing:.buffered,defer:false)
                    border.isReleasedWhenClosed = false; border.isOpaque = false; border.backgroundColor = .clear
                    border.ignoresMouseEvents = true; border.hasShadow = false; border.level = .floating
                    border.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary]
                    border.contentView = RecordingBorderView(frame:CGRect(origin:.zero,size:frame.size)); self.borderWindow = border; border.orderFrontRegardless()
                }
                let size = recordingOutputSize(rect: rect, scale: scale, options: self.options)
                self.status.stringValue = Lf("● 녹화 중 · %d × %d 픽셀 · %d fps", size.0, size.1, self.options.fps)
                self.timer?.invalidate(); self.timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.updateElapsed() }
            }
            session.completed = { [weak self, weak session] url, message in
                guard let self = self, let session = session, self.nativeSession === session else { return }; self.timer?.invalidate(); self.timer = nil
                self.nativeSession = nil; self.lastFile = url; self.updatePhase(.idle); self.completeNativeStart("processingFailed"); self.status.stringValue = url.map { message + " · " + $0.lastPathComponent } ?? message
                let callback = self.nativeStopCompletion; self.nativeStopCompletion = nil; callback?(url, url == nil ? "processingFailed" : "")
            }
            nativeSession = session; session.begin()
        } catch { nativeSession = nil; updatePhase(.idle); status.stringValue = Lf("녹화 준비 실패: %@", error.localizedDescription); completeNativeStart("processingFailed") }
    }
    private func updateElapsed() { guard let startTime = startTime else { return }; let seconds = max(0, Int((pauseStarted ?? Date()).timeIntervalSince(startTime) - pausedSeconds)); elapsed.stringValue = String(format: "%02d:%02d", seconds / 60, seconds % 60) }
    @objc func stop() {
        guard #available(macOS 13.0, *), (phase == .recording || phase == .paused), let session = nativeSession as? NativeRecordingSession else { return }
        updatePhase(.stopping); timer?.invalidate(); timer = nil; status.stringValue = L("녹화를 중지하고 MP4를 완료·검증하는 중…"); session.stop()
    }
    func prepareForQuit() -> Bool {
        guard !isRecording else {
            let alert = NSAlert(); alert.messageText = L("화면 녹화를 먼저 중지하세요.")
            alert.informativeText = L("녹화 중지 후 영상 저장이 완료되면 앱을 종료할 수 있습니다."); alert.addButton(withTitle: L("확인")); alert.runModal(); return false
        }
        return true
    }
    @objc private func openLastVideo() { if let url = lastFile { NSWorkspace.shared.open(url) } else { status.stringValue = L("녹화를 마친 뒤 영상을 열 수 있습니다.") } }
    @objc private func openFolder() {
        do { try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true); NSWorkspace.shared.open(outputDirectory) }
        catch { status.stringValue = Lf("폴더 열기 실패: %@", error.localizedDescription) }
    }
    @objc private func openPermissionSettings() { if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") { NSWorkspace.shared.open(url) } }
}

/// Writes actual H.264 MP4 frames, reopens and decodes the video, and checks selected-region Retina geometry.
func screenRecordSelfCheck() -> Bool {
    guard recordingOptionsAndTimingSelfCheck() else { return false }
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("LocalTools-RecordingCheck-" + UUID().uuidString, isDirectory: true)
    let url = directory.appendingPathComponent("fixture.mp4")
    defer { try? FileManager.default.removeItem(at: directory) }
    do {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 320, AVVideoHeightKey: 180])
        let audioInputs = (0..<2).map { _ in AVAssetWriterInput(mediaType: .audio, outputSettings: [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 64000]) }
        guard writer.canAdd(input) else { return false }; writer.add(input)
        for audio in audioInputs { guard writer.canAdd(audio) else { return false }; writer.add(audio) }
        guard writer.startWriting() else { return false }; writer.startSession(atSourceTime: .zero)
        for frame in 0..<12 {
            let deadline = Date().addingTimeInterval(3)
            while !input.isReadyForMoreMediaData && Date() < deadline { Thread.sleep(forTimeInterval: 0.005) }
            var optional: CVPixelBuffer?
            guard CVPixelBufferCreate(kCFAllocatorDefault, 320, 180, kCVPixelFormatType_32BGRA, [kCVPixelBufferCGImageCompatibilityKey: true, kCVPixelBufferCGBitmapContextCompatibilityKey: true] as CFDictionary, &optional) == kCVReturnSuccess, let buffer = optional else { return false }
            CVPixelBufferLockBaseAddress(buffer, [])
            if let base = CVPixelBufferGetBaseAddress(buffer) {
                let bytes = base.assumingMemoryBound(to: UInt8.self); let stride = CVPixelBufferGetBytesPerRow(buffer)
                for y in 0..<180 { for x in 0..<320 { let o = y * stride + x * 4; bytes[o] = UInt8(x * 255 / 319); bytes[o + 1] = UInt8(y * 255 / 179); bytes[o + 2] = UInt8(frame * 20); bytes[o + 3] = 255 } }
            }
            CVPixelBufferUnlockBaseAddress(buffer, [])
            let offset = frame >= 6 ? CMTime(seconds: 2, preferredTimescale: 48000) : .zero
            guard let rawVideo = recordingVideoFixture(buffer: buffer, time: CMTimeAdd(CMTime(value: Int64(frame), timescale: 30), offset)), let videoSample = recordingRetimedSample(rawVideo, removing: offset), input.append(videoSample) else { return false }
            for (index, audio) in audioInputs.enumerated() {
                let deadline = Date().addingTimeInterval(3)
                while !audio.isReadyForMoreMediaData && Date() < deadline { Thread.sleep(forTimeInterval: 0.005) }
                guard let raw = recordingPCMFixture(time: CMTimeAdd(CMTime(value: Int64(frame), timescale: 30), offset), frequency: index == 0 ? 440 : 880), let sample = recordingRetimedSample(raw, removing: offset), audio.isReadyForMoreMediaData, audio.append(sample) else { return false }
            }
        }
        writer.endSession(atSourceTime: CMTime(value: 12, timescale: 30)); input.markAsFinished(); audioInputs.forEach { $0.markAsFinished() }
        let sem = DispatchSemaphore(value: 0); writer.finishWriting { sem.signal() }
        guard sem.wait(timeout: .now() + 15) == .success, writer.status == .completed else { return false }
        let mixedURL = directory.appendingPathComponent("mixed.mp4"), mixed = DispatchSemaphore(value: 0); var mixError: Error?
        recordingMixAudioTracks(source: url, output: mixedURL) { error in mixError = error; mixed.signal() }
        guard mixed.wait(timeout: .now() + 30) == .success, mixError == nil else { return false }
        let asset = AVURLAsset(url: mixedURL)
        guard CMTimeGetSeconds(asset.duration) > 0.3, let track = asset.tracks(withMediaType: .video).first, track.naturalSize == CGSize(width: 320, height: 180) else { return false }
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        reader.add(output); guard reader.startReading(), output.copyNextSampleBuffer() != nil else { return false }; reader.cancelReading()
        guard asset.tracks(withMediaType: .audio).count == 1, let audioTrack = asset.tracks(withMediaType: .audio).first else { return false }
        let audioReader = try AVAssetReader(asset: asset), audioOutput = AVAssetReaderTrackOutput(track: audioTrack, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false])
        audioReader.add(audioOutput); guard audioReader.startReading(), audioOutput.copyNextSampleBuffer() != nil else { return false }; audioReader.cancelReading()
        let geometry = recordingPixelSize(rect: CGRect(x: 11, y: 25, width: 160, height: 90), scale: 2)
        return geometry.0 == 320 && geometry.1 == 180
    } catch { return false }
}

// These deterministic fixtures exercise timestamp adjustment and real AAC/mixed MP4
// encoding. They do not claim permissioned screen, system-audio, or microphone capture.
private func recordingPCMFixture(time: CMTime, frequency: Double) -> CMSampleBuffer? {
    let count = 1600, sampleRate = 48000.0
    let samples = (0..<count).map { Int16(sin(2 * Double.pi * frequency * Double($0) / sampleRate) * 8000) }
    var description = AudioStreamBasicDescription(mSampleRate: sampleRate, mFormatID: kAudioFormatLinearPCM, mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked, mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2, mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0)
    var format: CMAudioFormatDescription?
    guard CMAudioFormatDescriptionCreate(allocator: kCFAllocatorDefault, asbd: &description, layoutSize: 0, layout: nil, magicCookieSize: 0, magicCookie: nil, extensions: nil, formatDescriptionOut: &format) == noErr, let format = format else { return nil }
    var block: CMBlockBuffer?
    guard CMBlockBufferCreateWithMemoryBlock(allocator: kCFAllocatorDefault, memoryBlock: nil, blockLength: count * 2, blockAllocator: kCFAllocatorDefault, customBlockSource: nil, offsetToData: 0, dataLength: count * 2, flags: 0, blockBufferOut: &block) == noErr, let block = block else { return nil }
    let copied = samples.withUnsafeBytes { CMBlockBufferReplaceDataBytes(with: $0.baseAddress!, blockBuffer: block, offsetIntoDestination: 0, dataLength: count * 2) }
    guard copied == noErr else { return nil }
    var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: 48000), presentationTimeStamp: time, decodeTimeStamp: .invalid), bytesPerSample = 2
    var result: CMSampleBuffer?
    guard CMSampleBufferCreateReady(allocator: kCFAllocatorDefault, dataBuffer: block, formatDescription: format, sampleCount: count, sampleTimingEntryCount: 1, sampleTimingArray: &timing, sampleSizeEntryCount: 1, sampleSizeArray: &bytesPerSample, sampleBufferOut: &result) == noErr else { return nil }
    return result
}

private func recordingVideoFixture(buffer: CVPixelBuffer, time: CMTime) -> CMSampleBuffer? {
    var format: CMVideoFormatDescription?
    guard CMVideoFormatDescriptionCreateForImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: buffer, formatDescriptionOut: &format) == noErr, let format = format else { return nil }
    var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: 30), presentationTimeStamp: time, decodeTimeStamp: .invalid), result: CMSampleBuffer?
    guard CMSampleBufferCreateReadyWithImageBuffer(allocator: kCFAllocatorDefault, imageBuffer: buffer, formatDescription: format, sampleTiming: &timing, sampleBufferOut: &result) == noErr else { return nil }
    return result
}

private func recordingOptionsAndTimingSelfCheck() -> Bool {
    guard !RecordingOptions(fps: 4).isValid, RecordingOptions(fps: 5).isValid, RecordingOptions(fps: 60).isValid, !RecordingOptions(fps: 61).isValid,
          !RecordingOptions(width: 1).isValid, RecordingOptions(width: 7680).isValid, !RecordingOptions(width: 7681).isValid,
          RecordingOptions(scalePercent: 10).isValid, !RecordingOptions(scalePercent: 9).isValid, !RecordingOptions(scalePercent: 101).isValid else { return false }
    let rect = CGRect(x: 0, y: 0, width: 640, height: 360)
    let down = recordingOutputSize(rect: rect, scale: 2, options: RecordingOptions(width: 640)), noUpscale = recordingOutputSize(rect: rect, scale: 2, options: RecordingOptions(width: 1920)), percent = recordingOutputSize(rect: rect, scale: 2, options: RecordingOptions(scalePercent: 25))
    guard down.0 == 640, down.1 == 360, noUpscale.0 == 1280, noUpscale.1 == 720, percent.0 == 320, percent.1 == 180 else { return false }
    var timeline = RecordingTimeline()
    timeline.pause(at: CMTime(seconds: 1, preferredTimescale: 48000)); timeline.pause(at: CMTime(seconds: 2, preferredTimescale: 48000))
    guard timeline.paused else { return false }
    timeline.resume(at: CMTime(seconds: 6, preferredTimescale: 48000)); timeline.resume(at: CMTime(seconds: 8, preferredTimescale: 48000))
    guard !timeline.paused, CMTimeCompare(timeline.offset, CMTime(seconds: 5, preferredTimescale: 48000)) == 0 else { return false }
    timeline.pause(at: CMTime(seconds: 9, preferredTimescale: 48000)); timeline.resume(at: CMTime(seconds: 11, preferredTimescale: 48000))
    guard let original = recordingPCMFixture(time: CMTime(seconds: 12, preferredTimescale: 48000), frequency: 440), let retimed = recordingRetimedSample(original, removing: timeline.offset) else { return false }
    return CMTimeCompare(CMSampleBufferGetPresentationTimeStamp(original), CMTime(seconds: 12, preferredTimescale: 48000)) == 0 && CMTimeCompare(CMSampleBufferGetPresentationTimeStamp(retimed), CMTime(seconds: 5, preferredTimescale: 48000)) == 0 && CMSampleBufferGetNumSamples(retimed) == CMSampleBufferGetNumSamples(original) && CMTimeCompare(CMSampleBufferGetDuration(retimed), CMSampleBufferGetDuration(original)) == 0
}
