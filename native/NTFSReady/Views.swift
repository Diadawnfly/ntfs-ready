import AppKit
import SwiftUI

// Native semantic colors provide the same restrained hierarchy in both appearances.
enum Palette {
    static let accent = Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(red: 0.27, green: 0.72, blue: 0.62, alpha: 1)
            : NSColor(red: 0x13 / 255.0, green: 0x7D / 255.0, blue: 0x69 / 255.0, alpha: 1)
    })
    static let background = Color(nsColor: .windowBackgroundColor)
    static let sidebar = Color(nsColor: .underPageBackgroundColor)
    static let surface = Color(nsColor: .controlBackgroundColor)
    static let line = Color(nsColor: .separatorColor)
}

struct MainView: View {
    @ObservedObject var model: DesktopModel
    var body: some View {
        HStack(spacing: 0) {
            Sidebar(model: model).frame(width: 220)
            Rectangle().fill(Palette.line).frame(width: 1)
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        header
                        if let error = model.error {
                            Notice(title: "无法读取实时状态", message: error, isError: true)
                        }
                        if let banner = model.banner {
                            Notice(title: model.awaitingTerminal ? "终端授权" : "操作结果", message: banner, isError: model.bannerIsError, spinning: model.busy)
                        }
                        switch model.navigation {
                        case .drives:
                            if let disk = model.selectedDevice { DiskView(model: model, disk: disk) }
                            else { EmptyDrivesView(model: model) }
                        case .diagnostics: DiagnosticsView(model: model)
                        case .about: AboutView()
                        }
                    }
                    .padding(.horizontal, 36).padding(.top, 30).padding(.bottom, 24)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                footer
            }
            .background(Palette.background)
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button { Task { await model.refresh() } } label: {
                    Label("刷新", systemImage: "arrow.clockwise")
                }
                .help("刷新实时磁盘与驱动状态（⌘R）")
                .accessibilityIdentifier("refresh")
                .disabled(model.loading || model.busy)
            }
        }
        .sheet(item: $model.pendingConfirmation) { request in
            ConfirmationView(model: model, request: request)
        }
    }
    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("NTFS READY  /  \(sectionLabel)")
                .font(.system(size: 10, weight: .semibold)).tracking(1.7).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.system(size: 28, weight: .semibold))
                    .lineLimit(2).textSelection(.enabled)
                Spacer()
                if model.navigation == .drives, let disk = model.selectedDevice {
                    StatusBadge(disk: disk)
                }
            }
            Text(subtitle).font(.system(size: 12)).foregroundStyle(.secondary)
        }
    }
    private var sectionLabel: String {
        switch model.navigation { case .drives: return "磁盘工作台"; case .diagnostics: return "环境诊断"; case .about: return "关于与安全" }
    }
    private var title: String {
        switch model.navigation {
        case .drives: return model.selectedDevice?.name.isEmpty == false ? model.selectedDevice!.name : "磁盘"
        case .diagnostics: return "环境诊断"
        case .about: return "清楚掌控每一次写入"
        }
    }
    private var subtitle: String {
        switch model.navigation {
        case .drives: return model.selectedDevice?.device ?? "连接、查看与安全管理你的 NTFS 磁盘。"
        case .diagnostics: return "直接读取本机环境；未能确认的状态不会显示为就绪。"
        case .about: return "原生桌面界面 · 明确授权 · 不保存密码"
        }
    }
    private var footer: some View {
        VStack(spacing: 0) {
            Divider()
            HStack(spacing: 7) {
                if model.loading { ProgressView().controlSize(.mini); Text("正在读取状态…") }
                else if let date = model.lastRefresh {
                    Text("上次检查")
                    Text(date, style: .time).monospacedDigit()
                } else { Text("尚未取得实时状态") }
                Spacer()
                Text("Beta · 重要数据请先备份")
            }
            .font(.system(size: 10)).foregroundStyle(.secondary)
            .padding(.horizontal, 24).padding(.vertical, 11)
        }
    }
}

struct Sidebar: View {
    @ObservedObject var model: DesktopModel
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 9) {
                Image(systemName: "externaldrive").font(.system(size: 19, weight: .medium)).foregroundStyle(Palette.accent)
                Text("NTFS Ready").font(.system(size: 16, weight: .semibold))
            }.padding(.top, 30).padding(.bottom, 30).padding(.horizontal, 20)
            navButton("磁盘", symbol: "internaldrive", navigation: .drives, identifier: "navDrives")
            HStack {
                Text("NTFS 磁盘").font(.system(size: 10, weight: .semibold)).tracking(0.8)
                Spacer()
                if model.snapshot != nil { Text("\(model.devices.count)").font(.system(size: 10)).monospacedDigit() }
            }.foregroundStyle(.secondary).padding(.horizontal, 22).padding(.top, 27).padding(.bottom, 11)
            if model.devices.isEmpty {
                Text(model.loading && model.snapshot == nil ? "正在查找…" : "暂无磁盘")
                    .font(.system(size: 12)).foregroundStyle(.tertiary)
                    .padding(.horizontal, 23).padding(.vertical, 10)
            } else {
                ScrollView {
                    VStack(spacing: 4) {
                        ForEach(model.devices) { disk in
                            Button {
                                model.selection = disk.id; model.navigation = .drives
                            } label: {
                                HStack(spacing: 10) {
                                    Image(systemName: "externaldrive").font(.system(size: 17))
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(disk.name.isEmpty ? disk.device : disk.name).font(.system(size: 12, weight: .medium)).lineLimit(1)
                                        Text(statusLabel(disk)).font(.system(size: 10)).foregroundStyle(.secondary)
                                    }
                                    Spacer(minLength: 0)
                                }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(RoundedRectangle(cornerRadius: 7).fill(isSelected(disk) ? Palette.accent.opacity(0.09) : Color.clear))
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("disk-\(disk.device)")
                        }
                    }.padding(.horizontal, 12)
                }
            }
            Spacer(minLength: 24)
            Divider().padding(.horizontal, 20).padding(.bottom, 14)
            navButton("环境诊断", symbol: "slider.horizontal.3", navigation: .diagnostics, identifier: "navDiagnostics")
            navButton("关于与安全", symbol: "info.circle", navigation: .about, identifier: "navAbout")
            HStack(spacing: 5) { Text("本地运行"); Text("·"); Text("0.2.0 Beta") }
                .font(.system(size: 10)).foregroundStyle(.tertiary).padding(.horizontal, 22).padding(.top, 21).padding(.bottom, 20)
        }.background(Palette.sidebar)
    }
    private func isSelected(_ disk: DeviceModel) -> Bool { model.navigation == .drives && model.selectedDevice?.id == disk.id }
    private func navButton(_ name: String, symbol: String, navigation: Navigation, identifier: String) -> some View {
        Button { model.navigation = navigation } label: {
            HStack(spacing: 10) {
                Image(systemName: symbol).font(.system(size: 14)).frame(width: 20)
                Text(name).font(.system(size: 12, weight: model.navigation == navigation ? .semibold : .regular))
                Spacer()
            }.foregroundStyle(model.navigation == navigation ? Palette.accent : Color.primary)
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 7).fill(model.navigation == navigation ? Palette.accent.opacity(0.08) : Color.clear))
        }.buttonStyle(.plain).padding(.horizontal, 12).padding(.vertical, 2).accessibilityIdentifier(identifier)
    }
}

func statusLabel(_ disk: DeviceModel) -> String {
    if disk.canWrite { return "可读写" }
    if !disk.mounted && disk.status == "unmounted" { return "未挂载" }
    if disk.mounted && disk.readonly == true && disk.status == "readOnly" { return "只读" }
    return "状态待确认"
}

struct StatusBadge: View {
    let disk: DeviceModel
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(disk.canWrite ? Palette.accent : Color.secondary).frame(width: 5, height: 5)
            Text(statusLabel(disk)).font(.system(size: 11, weight: .medium))
        }.padding(.horizontal, 10).padding(.vertical, 5)
            .background(Capsule().fill(disk.canWrite ? Palette.accent.opacity(0.09) : Color.secondary.opacity(0.08)))
            .foregroundStyle(disk.canWrite ? Palette.accent : Color.secondary)
    }
}

struct EmptyDrivesView: View {
    @ObservedObject var model: DesktopModel
    var body: some View {
        VStack(spacing: 0) {
            Divider()
            VStack(spacing: 14) {
                Image(systemName: "externaldrive").font(.system(size: 48, weight: .ultraLight))
                    .foregroundStyle(Palette.accent).padding(.bottom, 10)
                Text(emptyTitle).font(.system(size: 21, weight: .medium))
                Text(emptyDescription).font(.system(size: 13)).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).lineSpacing(5).frame(maxWidth: 390)
                Button { Task { await model.refresh() } } label: { Label("重新检查", systemImage: "arrow.clockwise") }
                    .controlSize(.large).padding(.top, 9).disabled(model.loading || model.busy)
            }.frame(maxWidth: .infinity).padding(.vertical, 63)
            Divider()
            DriverReadiness(model: model)
            if let warnings = model.snapshot?.warnings, !warnings.isEmpty {
                Text(warnings.joined(separator: "\n")).font(.system(size: 11)).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 14).textSelection(.enabled)
            }
            if let unsupported = model.snapshot?.unsupported, !unsupported.isEmpty {
                Text("另有 \(unsupported.count) 个卷不在当前 NTFS 支持范围内。可在环境诊断查看原因。")
                    .font(.system(size: 11)).foregroundStyle(.secondary).padding(.top, 12)
            }
        }
    }
    private var emptyTitle: String {
        if model.snapshot == nil { return model.loading ? "正在检查磁盘" : "磁盘状态尚未取得" }
        return "未发现 NTFS 磁盘"
    }
    private var emptyDescription: String {
        if model.snapshot == nil { return "我们只显示本机实际检测到的磁盘。请完成环境检查后重试。" }
        return "连接一个 NTFS 磁盘，它就会出现在这里。\n其他格式的磁盘不会被更改。"
    }
}

struct DriverReadiness: View {
    @ObservedObject var model: DesktopModel
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.shield").font(.system(size: 18)).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 5) {
                Text("写入组件").font(.system(size: 12, weight: .medium))
                Text(readiness).font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            if model.snapshot?.doctor.writePrerequisitesReady != true {
                Button("安装组件") { model.confirmInstallation = true }.disabled(model.busy || model.awaitingTerminal)
                    .accessibilityIdentifier("installComponents")
            }
            Button("查看诊断") { model.navigation = .diagnostics }.buttonStyle(.link)
                .font(.system(size: 11))
        }.padding(.vertical, 20)
            .alert("在终端安装写入组件？", isPresented: $model.confirmInstallation) {
                Button("取消", role: .cancel) { }
                Button("打开终端") { Task { await model.openInstaller() } }
            } message: {
                Text("安装脚本将逐步检查依赖。授权将在系统终端完成，本应用不保存密码。系统可能要求批准 macFUSE 扩展并重新启动。")
            }
    }
    private var readiness: String {
        guard model.error == nil, let doctor = model.snapshot?.doctor else { return "尚未确认 · 需要实时环境检查" }
        if doctor.writePrerequisitesReady { return "依赖与内核检查通过 · 写入仍需逐盘授权" }
        if doctor.kernel_check_error { return "内核状态无法确认 · 请先查看诊断" }
        if !doctor.dependencies_ready { return "依赖尚未就绪 · 不影响只读磁盘查看" }
        return "内核或挂载助手尚未就绪 · 请查看诊断"
    }
}

struct DiskView: View {
    @ObservedObject var model: DesktopModel
    let disk: DeviceModel
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Divider()
            if let used = disk.usageFraction {
                VStack(alignment: .leading, spacing: 9) {
                    HStack {
                        Text("\(ByteFormatting.string(disk.freeBytes)) 可用").font(.system(size: 12, weight: .medium))
                        Spacer()
                        Text("共 \(ByteFormatting.string(disk.capacityBytes))").font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.secondary.opacity(0.12))
                            Capsule().fill(Palette.accent).frame(width: geo.size.width * used)
                        }
                    }.frame(height: 4).accessibilityLabel("已使用 \(Int(used * 100))%")
                }.padding(.vertical, 2)
            }
            HStack(spacing: 10) {
                if disk.canWrite {
                    Button { model.openFinder(disk) } label: { Label("在 Finder 中打开", systemImage: "folder") }
                        .buttonStyle(.borderedProminent).accessibilityIdentifier("openFinder")
                } else {
                    Button { model.request(.mount, for: disk) } label: { Label("启用写入", systemImage: "lock.open") }
                        .buttonStyle(.borderedProminent).accessibilityIdentifier("mount")
                        .disabled(model.actionsDisabled || model.snapshot?.doctor.writePrerequisitesReady != true)
                }
                Button { model.request(.unmount, for: disk) } label: { Label("安全卸载", systemImage: "eject") }
                    .accessibilityIdentifier("unmount").disabled(model.actionsDisabled || !disk.mounted)
                Button { model.request(.verify, for: disk) } label: { Label("验证写入", systemImage: "checkmark.circle") }
                    .accessibilityIdentifier("verify").disabled(model.actionsDisabled || !disk.canWrite)
            }.controlSize(.large)
            HStack(alignment: .top, spacing: 9) {
                Image(systemName: "info.circle").font(.system(size: 12)).padding(.top, 2)
                Text(disk.canWrite ? "已检测到可写挂载。验证写入会创建并删除一个临时测试文件；不会自动执行。" : "启用写入需要你的明确授权。授权将在系统终端完成，本应用不保存密码。")
                    .font(.system(size: 12)).lineSpacing(4)
            }.foregroundStyle(.secondary).padding(15)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.045)))
            VStack(alignment: .leading, spacing: 18) {
                Text("磁盘信息").font(.system(size: 13, weight: .semibold))
                Grid(alignment: .leading, horizontalSpacing: 36, verticalSpacing: 19) {
                    GridRow {
                        Detail(label: "设备", value: disk.device)
                        Detail(label: "格式", value: "NTFS")
                    }
                    GridRow {
                        Detail(label: "磁盘容量", value: ByteFormatting.string(disk.size > 0 ? disk.size : nil))
                        Detail(label: "当前驱动", value: disk.driver ?? "未知")
                    }
                    GridRow {
                        Detail(label: "挂载位置", value: disk.mounted && !disk.mountpoint.isEmpty ? disk.mountpoint : "未挂载")
                        Detail(label: "卷标识", value: disk.uuid.isEmpty ? "未知" : disk.uuid)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.padding(.top, 8)
            Divider()
            DriverReadiness(model: model)
        }
    }
}

struct Detail: View {
    let label: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 12)).textSelection(.enabled).lineLimit(3)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct Notice: View {
    let title: String
    let message: String
    var isError = false
    var spinning = false
    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            if spinning { ProgressView().controlSize(.small).padding(.top, 3) }
            else { Image(systemName: isError ? "exclamationmark.circle" : "info.circle").padding(.top, 2) }
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.system(size: 12, weight: .semibold))
                Text(message).font(.system(size: 11)).foregroundStyle(.secondary).lineSpacing(3).textSelection(.enabled)
            }
            Spacer(minLength: 0)
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.06)))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Palette.line.opacity(0.55), lineWidth: 0.5))
    }
}

struct DiagnosticsView: View {
    @ObservedObject var model: DesktopModel
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider().padding(.bottom, 8)
            if let doctor = model.snapshot?.doctor {
                DiagnosticRow(title: "依赖", detail: "dependencies_ready", value: doctor.dependencies_ready ? "已就绪" : "未就绪", ready: doctor.dependencies_ready)
                DiagnosticRow(title: "macFUSE 内核", detail: "kernel_loaded / kernel_check_error", value: doctor.kernel_check_error ? "检查发生错误" : (doctor.kernel_loaded ? "已加载" : "未加载"), ready: doctor.kernel_loaded && !doctor.kernel_check_error)
                DiagnosticRow(title: "挂载助手", detail: "macfuse_helper", value: doctor.macfuse_helper ? "已发现" : "未发现", ready: doctor.macfuse_helper)
                DiagnosticRow(title: "NTFS-3G", detail: doctor.ntfs_3g ?? "未发现可执行文件", value: doctor.ntfs_3g == nil ? "缺失" : "已发现", ready: doctor.ntfs_3g != nil)
                DiagnosticRow(title: "NTFS 探测器", detail: doctor.probe ?? "未发现可执行文件", value: doctor.probe == nil ? "缺失" : "已发现", ready: doctor.probe != nil)
                DiagnosticRow(title: "运行平台", detail: doctor.platform, value: "后端 \(model.snapshot?.version ?? "未知")", ready: false, neutral: true)
            } else {
                Text("尚未收到环境诊断。请刷新重试；上方会显示真实的后端错误。")
                    .font(.system(size: 13)).foregroundStyle(.secondary).padding(.vertical, 28)
            }
            DriverReadiness(model: model).padding(.top, 12)
            if let warnings = model.snapshot?.warnings, !warnings.isEmpty {
                Divider().padding(.bottom, 20)
                Text("检查提示").font(.system(size: 13, weight: .semibold)).padding(.bottom, 10)
                ForEach(Array(warnings.enumerated()), id: \.offset) { _, warning in
                    Text(warning).font(.system(size: 12)).foregroundStyle(.secondary).textSelection(.enabled).padding(.bottom, 8)
                }
            }
            if let unsupported = model.snapshot?.unsupported, !unsupported.isEmpty {
                Divider().padding(.vertical, 18)
                Text("未支持的卷").font(.system(size: 13, weight: .semibold)).padding(.bottom, 10)
                ForEach(Array(unsupported.enumerated()), id: \.offset) { _, item in
                    Text("\(item.name ?? item.device ?? "未命名卷") · \(item.reason ?? "当前不支持")")
                        .font(.system(size: 12)).foregroundStyle(.secondary).textSelection(.enabled).padding(.bottom, 8)
                }
            }
        }
    }
}

struct DiagnosticRow: View {
    let title: String
    let detail: String
    let value: String
    let ready: Bool
    var neutral = false
    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title).font(.system(size: 12, weight: .medium))
                    Text(detail).font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary).lineLimit(3).textSelection(.enabled)
                }
                Spacer(minLength: 16)
                Text(value).font(.system(size: 11)).foregroundStyle(ready ? Palette.accent : Color.secondary)
                Image(systemName: ready ? "checkmark.circle" : (neutral ? "minus.circle" : "circle.dashed"))
                    .foregroundStyle(ready ? Palette.accent : Color.secondary).frame(width: 15)
            }.padding(.vertical, 17)
            Divider()
        }
    }
}

struct AboutView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 25) {
            Divider()
            aboutSection("为操作而设计", text: "NTFS Ready 是独立的原生 macOS 工具。界面与开源 Python 后端采用原创设计，不包含 Paragon 品牌资产，也不是 Paragon 产品或其授权界面。")
            aboutSection("权限与密码", text: "刷新和诊断仅检查状态。启用写入、卸载与写入验证只在你确认后执行。授权将在系统终端完成，本应用不保存密码。")
            aboutSection("开源边界", text: "本项目的原创代码使用 MIT 许可证。macFUSE 与 NTFS-3G 为独立第三方组件，遵循各自许可证；macFUSE 包含闭源组件。本应用不会将第三方组件声明为原创或 MIT 开源。")
            aboutSection("Beta 使用提醒", text: "0.2.0 本地预览版 · 仅临时签名，未经过 Apple 公证。NTFS 写入存在数据风险，请先备份重要文件；本应用不提供格式化、修复或自动写入。")
            HStack(spacing: 22) {
                Link("GitHub 项目 ↗", destination: URL(string: "https://github.com/Diadawnfly/ntfs-ready")!)
                Link("问题反馈 ↗", destination: URL(string: "https://github.com/Diadawnfly/ntfs-ready/issues")!)
                Link("MIT 许可证 ↗", destination: URL(string: "https://github.com/Diadawnfly/ntfs-ready/blob/main/LICENSE")!)
            }.font(.system(size: 12))
            Divider()
            Text("macOS 13 或更高版本 · SwiftUI 原生界面")
                .font(.system(size: 11)).foregroundStyle(.secondary)
        }
    }
    private func aboutSection(_ title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(title).font(.system(size: 13, weight: .semibold))
            Text(text).font(.system(size: 12)).foregroundStyle(.secondary).lineSpacing(5).textSelection(.enabled)
        }
    }
}

struct ConfirmationView: View {
    @ObservedObject var model: DesktopModel
    let request: ActionRequest
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(request.action.title).font(.system(size: 21, weight: .semibold))
            Text(request.device.name.isEmpty ? request.device.device : request.device.name)
                .font(.system(size: 13, weight: .medium))
            Text(request.action.explanation).font(.system(size: 13)).foregroundStyle(.secondary).lineSpacing(4)
            Text("授权将在系统终端完成，本应用不保存密码。")
                .font(.system(size: 12)).foregroundStyle(.secondary)
            Divider()
            HStack {
                Spacer()
                Button("取消") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("继续并打开终端") {
                    dismiss()
                    Task { await model.execute(request) }
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                    .accessibilityIdentifier("confirmAction")
            }
        }.padding(28).frame(width: 430).tint(Palette.accent)
    }
}
