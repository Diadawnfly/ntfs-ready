import AppKit
import SwiftUI

@main struct NTFSReadyApp: App {
    @StateObject private var model = DesktopModel()
    var body: some Scene {
        Window("NTFS Ready", id: "main") {
            MainView(model: model)
                .frame(minWidth: 880, minHeight: 580)
                .tint(Palette.accent)
                .task { model.start() }
        }
        .defaultSize(width: 1100, height: 730)
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandGroup(after: .toolbar) {
                Button("刷新磁盘状态") { Task { await model.refresh() } }
                    .keyboardShortcut("r", modifiers: .command)
                    .disabled(model.loading || model.busy)
            }
        }
        MenuBarExtra("NTFS Ready", systemImage: "externaldrive") {
            MenuContent(model: model)
        }
    }
}

struct MenuContent: View {
    @ObservedObject var model: DesktopModel
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Text("NTFS Ready")
        if model.error != nil { Text("状态检查未完成") }
        else if model.snapshot == nil { Text("正在检查磁盘…") }
        else { Text("\(model.devices.count) 个 NTFS 磁盘 · \(model.devices.filter(\.canWrite).count) 个可写") }
        Divider()
        Button("打开磁盘工作台") {
            openWindow(id: "main")
            NSApplication.shared.activate(ignoringOtherApps: true)
        }
        Button("刷新状态") { Task { await model.refresh() } }
            .disabled(model.loading || model.busy)
        Divider()
        Button("退出 NTFS Ready") { NSApplication.shared.terminate(nil) }
            .keyboardShortcut("q")
    }
}
