import Foundation

// Keep runtime policy testable without launching an application or drive action.
enum BackendRuntimePolicy {
    static let pythonCandidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/Library/Developer/CommandLineTools/usr/bin/python3", "/usr/bin/python3"]
    static func arguments(_ bridgeArguments: [String]) -> [String] {
        ["-B", "-s", "-m", "ntfs_ready.gui_bridge"] + bridgeArguments
    }
    static func environment(_ inherited: [String: String], backendPath: String) -> [String: String] {
        var environment = inherited
        for key in ["PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONUSERBASE", "PYTHONPYCACHEPREFIX"] {
            environment.removeValue(forKey: key)
        }
        environment["PYTHONPATH"] = backendPath
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return environment
    }
}

struct Snapshot: Decodable {
    let schema: Int
    let version: String
    let devices: [DeviceModel]
    let unsupported: [UnsupportedModel]
    let doctor: DoctorModel
    let warnings: [String]
}

struct UnsupportedModel: Decodable {
    let device: String?
    let name: String?
    let reason: String?
}

struct DoctorModel: Decodable {
    let dependencies_ready: Bool
    let kernel_loaded: Bool
    let kernel_check_error: Bool
    let ntfs_3g: String?
    let probe: String?
    let macfuse_helper: Bool
    let platform: String
    var writePrerequisitesReady: Bool {
        dependencies_ready && kernel_loaded && !kernel_check_error && macfuse_helper
    }
}

enum DiskAction: String, Identifiable {
    case mount, verify, unmount
    var id: String { rawValue }
    var title: String {
        switch self { case .mount: return "启用写入"; case .verify: return "验证写入"; case .unmount: return "安全卸载" }
    }
    var explanation: String {
        switch self {
        case .mount: return "将重新挂载此磁盘以尝试启用 NTFS 写入。请先关闭正在使用磁盘的文件。"
        case .verify: return "将在此磁盘创建、读取并删除一个临时 4 KB 测试文件。不会修改已有文件。"
        case .unmount: return "将卸载此磁盘。请先保存文件并关闭正在使用它的应用。"
        }
    }
}

struct PreparedAction: Decodable {
    let schema: Int
    let nonce: String
    let command_path: String
    let result_path: String
    func matchesCacheLayout(root: URL = ActionSecurity.cacheRoot) -> Bool {
        guard schema == 1, nonce.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil else { return false }
        let directory = root.appendingPathComponent(nonce, isDirectory: true)
        return command_path == directory.appendingPathComponent("action.command").path
            && result_path == directory.appendingPathComponent("result.json").path
    }
}

struct ActionResult: Decodable {
    let schema: Int
    let nonce: String
    let ok: Bool
    let action: String
    let device: String
    let message: String
    let error: String?
    func matches(nonce: String, action: DiskAction, device: String) -> Bool {
        schema == 1 && self.nonce == nonce && self.action == action.rawValue && self.device == device
    }
}

enum ActionSecurity {
    static var cacheRoot: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/NTFS Ready Desktop/actions", isDirectory: true)
    }
    static func isContained(_ file: URL, in root: URL) -> Bool {
        let base = root.standardizedFileURL.resolvingSymlinksInPath().path
        let path = file.standardizedFileURL.resolvingSymlinksInPath().path
        return path.hasPrefix(base + "/")
    }
}

enum ByteFormatting {
    static func string(_ bytes: Int64?) -> String {
        guard let bytes = bytes, bytes >= 0 else { return "未知" }
        return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }
}

enum BridgeError: LocalizedError {
    case invalidIdentity
    case invalidReply
    case unsafePath
    case unavailable(String)
    var errorDescription: String? {
        switch self {
        case .invalidIdentity: return "磁盘身份信息不完整。请刷新后重试。"
        case .invalidReply: return "后端返回了无法验证的响应。"
        case .unsafePath: return "授权文件不在本应用的私有缓存目录内。"
        case .unavailable(let message): return message
        }
    }
}

struct DeviceModel: Decodable, Identifiable {
    let device: String
    let name: String
    let size: Int64
    let uuid: String
    let mounted: Bool
    let mountpoint: String
    let readonly: Bool?
    let driver: String?
    let status: String
    let identity: [IdentityValue]
    let freeBytes: Int64?
    let capacityBytes: Int64?
    var id: String { device }
    func identityJSON() throws -> String {
        guard identity.count == 4,
              case .text(let id) = identity[0], id == device,
              case .integer(let bytes) = identity[1], bytes == size,
              case .text(let token) = identity[2], token == uuid,
              case .text(let label) = identity[3], label == name else {
            throw BridgeError.invalidIdentity
        }
        let values: [Any] = identity.map {
            switch $0 { case .text(let value): return value; case .integer(let value): return value }
        }
        let encoded = try JSONSerialization.data(withJSONObject: values, options: [.sortedKeys])
        return String(decoding: encoded, as: UTF8.self)
    }
    var canWrite: Bool { mounted && readonly == false && status == "writable" }
    var usageFraction: Double? {
        guard let capacity = capacityBytes, let free = freeBytes,
              capacity > 0, free >= 0, free <= capacity else { return nil }
        return Double(capacity - free) / Double(capacity)
    }
}

enum IdentityValue: Codable, Equatable {
    case text(String)
    case integer(Int64)
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(Int64.self) { self = .integer(value) }
        else { self = .text(try container.decode(String.self)) }
    }
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .text(let value): try container.encode(value)
        case .integer(let value): try container.encode(value)
        }
    }
}
