import AppKit
import Foundation
import SwiftUI
import Darwin

private final class OutputBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()
    private var exceeded = false
    let limit: Int
    init(limit: Int) { self.limit = limit }
    func append(_ chunk: Data) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let remaining = max(0, limit - data.count)
        data.append(chunk.prefix(remaining))
        if chunk.count > remaining { exceeded = true }
        return exceeded
    }
    func value() -> (Data, Bool) {
        lock.lock(); defer { lock.unlock() }
        return (data, exceeded)
    }
}

enum BackendClient {
    static func run(_ arguments: [String]) async throws -> Data {
        try await Task.detached(priority: .userInitiated) { try runBlocking(arguments) }.value
    }
    private static func runBlocking(_ arguments: [String]) throws -> Data {
        let fm = FileManager.default
        guard let root = Bundle.main.resourceURL?.appendingPathComponent("backend", isDirectory: true),
              fm.fileExists(atPath: root.appendingPathComponent("ntfs_ready/gui_bridge.py").path) else {
            throw BridgeError.unavailable("应用内的 Python 后端缺失。请使用完整的 NTFS Ready.app 安装包。")
        }
        let candidates = BackendRuntimePolicy.pythonCandidates
        guard let python = candidates.first(where: { fm.isExecutableFile(atPath: $0) }) else {
            throw BridgeError.unavailable("未找到 Python 3。请安装 Python 后重新打开应用。")
        }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = BackendRuntimePolicy.arguments(arguments)
        process.currentDirectoryURL = root
        process.environment = BackendRuntimePolicy.environment(ProcessInfo.processInfo.environment, backendPath: root.path)
        let output = Pipe(), error = Pipe()
        process.standardOutput = output
        process.standardError = error
        process.standardInput = FileHandle.nullDevice
        let stdout = OutputBuffer(limit: 1_048_576), stderr = OutputBuffer(limit: 131_072)
        let exited = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in exited.signal() }
        try process.run()
        let readers = DispatchGroup()
        for (pipe, buffer) in [(output, stdout), (error, stderr)] {
            readers.enter()
            DispatchQueue.global(qos: .utility).async {
                defer { readers.leave() }
                while let chunk = try? pipe.fileHandleForReading.read(upToCount: 8192), !chunk.isEmpty {
                    if buffer.append(chunk), process.isRunning { process.terminate() }
                }
            }
        }
        let timedOut = exited.wait(timeout: .now() + 25) == .timedOut
        if timedOut {
            if process.isRunning { process.terminate() }
            if exited.wait(timeout: .now() + 2) == .timedOut, process.isRunning {
                kill(process.processIdentifier, SIGKILL)
                _ = exited.wait(timeout: .now() + 2)
            }
        }
        _ = readers.wait(timeout: .now() + 2)
        let (bytes, outputExceeded) = stdout.value()
        let (errors, errorExceeded) = stderr.value()
        guard !timedOut else { throw BridgeError.unavailable("后端检查超时。请刷新或打开诊断查看环境。") }
        guard !outputExceeded && !errorExceeded else { throw BridgeError.unavailable("后端响应超出安全大小限制。") }
        guard process.terminationStatus == 0 else {
            let details = String(decoding: errors.isEmpty ? bytes : errors, as: UTF8.self)
            throw BridgeError.unavailable("后端检查未完成（\(process.terminationStatus)）。\n\(String(details.prefix(3000)))")
        }
        return bytes
    }

    static func validateFile(_ url: URL, mustExist: Bool) throws {
        let fm = FileManager.default
        guard ActionSecurity.isContained(url, in: ActionSecurity.cacheRoot) else { throw BridgeError.unsafePath }
        // Only backend-created private, user-owned directories and ordinary files are accepted.
        let parent = url.deletingLastPathComponent()
        for directory in [ActionSecurity.cacheRoot, parent] {
            let attrs = try fm.attributesOfItem(atPath: directory.path)
            guard attrs[.type] as? FileAttributeType == .typeDirectory,
                  (attrs[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
                  let permissions = attrs[.posixPermissions] as? NSNumber,
                  permissions.intValue & 0o077 == 0 else { throw BridgeError.unsafePath }
        }
        if fm.fileExists(atPath: url.path) {
            let attrs = try fm.attributesOfItem(atPath: url.path)
            guard attrs[.type] as? FileAttributeType == .typeRegular,
                  (attrs[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
                  (attrs[.size] as? NSNumber)?.intValue ?? Int.max <= 1_048_576 else { throw BridgeError.unsafePath }
        } else if mustExist { throw BridgeError.unsafePath }
    }
}

enum Navigation: String { case drives, diagnostics, about }
struct ActionRequest: Identifiable {
    let id = UUID()
    let action: DiskAction
    let device: DeviceModel
}

@MainActor final class DesktopModel: ObservableObject {
    @Published var snapshot: Snapshot?
    @Published var selection: String?
    @Published var navigation: Navigation = .drives
    @Published var loading = false
    @Published var busy = false
    @Published var error: String?
    @Published var banner: String?
    @Published var bannerIsError = false
    @Published var pendingConfirmation: ActionRequest?
    @Published var lastRefresh: Date?
    @Published var awaitingTerminal = false
    @Published var confirmInstallation = false
    private var started = false
    private var observers: [NSObjectProtocol] = []
    private var polling: Task<Void, Never>?
    var devices: [DeviceModel] { snapshot?.devices ?? [] }
    var selectedDevice: DeviceModel? { devices.first { $0.id == selection } ?? devices.first }
    var actionsDisabled: Bool { busy || loading || error != nil || awaitingTerminal }

    func start() {
        guard !started else { return }
        started = true
        for event in [NSWorkspace.didMountNotification, NSWorkspace.didUnmountNotification] {
            observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in await self?.refresh() }
            })
        }
        polling = Task { [weak self] in
            await self?.refresh()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15_000_000_000)
                if Task.isCancelled { break }
                await self?.refresh()
            }
        }
    }

    func refresh() async {
        guard !loading && !busy else { return }
        loading = true
        defer { loading = false }
        do {
            let data = try await BackendClient.run(["snapshot"])
            let next = try JSONDecoder().decode(Snapshot.self, from: data)
            guard next.schema == 1 else { throw BridgeError.invalidReply }
            snapshot = next
            if !next.devices.contains(where: { $0.id == selection }) { selection = next.devices.first?.id }
            error = nil
            lastRefresh = Date()
        } catch { self.error = error.localizedDescription }
    }

    func request(_ action: DiskAction, for device: DeviceModel) {
        guard !actionsDisabled else { return }
        pendingConfirmation = ActionRequest(action: action, device: device)
    }

    func execute(_ request: ActionRequest) async {
        guard !actionsDisabled else { return }
        busy = true
        bannerIsError = false
        banner = "正在准备安全授权…"
        defer { busy = false }
        do {
            let args = ["prepare-action", "--action", request.action.rawValue, "--device", request.device.device,
                        "--identity-json", try request.device.identityJSON()]
            let data = try await BackendClient.run(args)
            let prepared = try JSONDecoder().decode(PreparedAction.self, from: data)
            guard prepared.matchesCacheLayout() else { throw BridgeError.invalidReply }
            let command = URL(fileURLWithPath: prepared.command_path)
            let result = URL(fileURLWithPath: prepared.result_path)
            guard command.pathExtension == "command", result.pathExtension == "json",
                  command.deletingLastPathComponent() == result.deletingLastPathComponent() else { throw BridgeError.unsafePath }
            try BackendClient.validateFile(command, mustExist: true)
            try BackendClient.validateFile(result, mustExist: false)
            let terminal = URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app")
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                NSWorkspace.shared.open([command], withApplicationAt: terminal, configuration: NSWorkspace.OpenConfiguration()) { _, error in
                    if let error = error { continuation.resume(throwing: error) }
                    else { continuation.resume() }
                }
            }
            awaitingTerminal = true
            banner = "等待终端授权。授权将在系统终端完成，本应用不保存密码。"
            let deadline = Date().addingTimeInterval(300)
            while Date() < deadline {
                if FileManager.default.fileExists(atPath: result.path) {
                    try BackendClient.validateFile(result, mustExist: true)
                    let data = try await Task.detached(priority: .utility) { try Data(contentsOf: result) }.value
                    let reply = try JSONDecoder().decode(ActionResult.self, from: data)
                    guard reply.matches(nonce: prepared.nonce, action: request.action, device: request.device.device) else { throw BridgeError.invalidReply }
                    awaitingTerminal = false
                    bannerIsError = !reply.ok
                    banner = reply.message + (reply.error.map { "\n" + $0 } ?? "")
                    busy = false
                    await refresh()
                    return
                }
                try await Task.sleep(nanoseconds: 1_000_000_000)
            }
            // Keep mutation locked: a Terminal command might still finish after the observation window.
            banner = "仍需终端授权 / 检查终端。尚未收到可验证的结果；不会自动重试。完成或取消终端命令后，请重新打开应用。"
        } catch {
            bannerIsError = true
            banner = error.localizedDescription
            busy = false
            await refresh()
        }
    }

    func openInstaller() async {
        guard !busy && !awaitingTerminal else { return }
        guard let command = Bundle.main.resourceURL?.appendingPathComponent("installer/Install.command"),
              FileManager.default.fileExists(atPath: command.path) else {
            bannerIsError = true; banner = "应用内的安装脚本缺失。请使用完整安装包。"; return
        }
        do {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                NSWorkspace.shared.open([command], withApplicationAt: URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app"), configuration: NSWorkspace.OpenConfiguration()) { _, error in
                    if let error = error { continuation.resume(throwing: error) } else { continuation.resume() }
                }
            }
            bannerIsError = false
            banner = "安装脚本已在终端打开。请阅读提示并自行授权；安装完成后刷新环境诊断。"
        } catch { bannerIsError = true; banner = error.localizedDescription }
    }

    func openFinder(_ disk: DeviceModel) {
        guard disk.mounted, !disk.mountpoint.isEmpty, disk.mountpoint.hasPrefix("/") else { return }
        let url = URL(fileURLWithPath: disk.mountpoint, isDirectory: true)
        if !NSWorkspace.shared.open(url) { bannerIsError = true; banner = "无法在 Finder 中打开此挂载点。请刷新磁盘状态。" }
    }
}
