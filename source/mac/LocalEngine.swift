import AppKit

struct EngineResult {
    let success: Bool
    let message: String
    let files: [URL]
    let data: [String: Any]
}

enum LocalEngine {
    private static let lock = NSLock()
    private static var jobs = 0
    static var activeJobs: Int { lock.lock(); defer { lock.unlock() }; return jobs }
    static var pythonURL: URL {
        #if arch(arm64)
        let arch = "arm64"
        #else
        let arch = "x86_64"
        #endif
        let current = Bundle.main.resourceURL!.appendingPathComponent("engine/runtimes/\(arch)/python/bin/python3")
        if FileManager.default.isExecutableFile(atPath: current.path) { return current }
        return Bundle.main.resourceURL!.appendingPathComponent("tools/python/\(arch)/bin/python3")
    }
    static var scriptURL: URL {
        let current = Bundle.main.resourceURL!.appendingPathComponent("engine/engine.py")
        return FileManager.default.fileExists(atPath: current.path) ? current : Bundle.main.resourceURL!.appendingPathComponent("tools/engine/engine.py")
    }
    static func run(job: [String: Any], completion: @escaping (EngineResult) -> Void) {
        var localizedJob = job
        localizedJob["language"] = AppLanguage.shared.code
        lock.lock(); jobs += 1; lock.unlock()
        DispatchQueue.global(qos: .userInitiated).async {
            let fm = FileManager.default
            let temporary = fm.temporaryDirectory.appendingPathComponent("GalaxyControl-job-"+UUID().uuidString,isDirectory:true)
            defer { try? fm.removeItem(at: temporary) }
            let result: EngineResult
            do {
                try fm.createDirectory(at: temporary, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
                let input = temporary.appendingPathComponent("job.json")
                let output = temporary.appendingPathComponent("result.json")
                try JSONSerialization.data(withJSONObject: localizedJob).write(to: input, options: .atomic)
                try fm.setAttributes([.posixPermissions: 0o600],ofItemAtPath:input.path)
                let process = Process()
                process.executableURL = pythonURL
                process.arguments = ["-I","-B",scriptURL.path,"--job",input.path,"--result",output.path]
                process.standardOutput = FileHandle.nullDevice
                process.standardError = FileHandle.nullDevice
                process.standardInput = FileHandle.nullDevice
                try process.run()
                process.waitUntilExit()
                let payload = try Data(contentsOf: output)
                guard let json = try JSONSerialization.jsonObject(with: payload) as? [String: Any] else { throw NSError(domain:"GalaxyControl",code:2) }
                let files = (json["files"] as? [String] ?? []).map { URL(fileURLWithPath:$0) }
                result = EngineResult(success:json["success"] as? Bool ?? false,message:json["message"] as? String ?? "처리 결과를 확인하세요.",files:files,data:json["data"] as? [String:Any] ?? [:])
            } catch {
                result = EngineResult(success:false,message:Lf("로컬 처리 도구 실행 확인: %@", String(describing: error.localizedDescription)),files:[],data:[:])
            }
            lock.lock(); jobs -= 1; lock.unlock()
            DispatchQueue.main.async { completion(EngineResult(success: result.success, message: L(result.message), files: result.files, data: result.data)) }
        }
    }
}
