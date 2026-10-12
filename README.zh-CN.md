# NTFS Ready

把 NTFS 写入配置整理成可复用工具：**双击安装入口、硬盘选择、安全挂载、Finder 元数据兼容验证**。

## 重要说明

- 我们自己的代码开源（MIT）。依赖的 NTFS-3G 和 macFUSE 由上游单独提供；现代 macFUSE 含闭源组件，所以**整套驱动栈不是完全开源**。
- 不复制、不打包、不镜像 Mounty，也不需要安装 Mounty。
- 这是早期 beta：不是自行开发的 NTFS 驱动，未证明性能或可靠性与 Paragon 相同。
- 一键安装指**统一的双击入口**，无法跳过 Apple 的授权、恢复模式操作和重启。

## 安装

从 [Releases](https://github.com/Diadawnfly/ntfs-ready/releases) 下载 ZIP，解压后双击 **Install.command**，按提示完成上游组件安装。

首次在 Apple Silicon 上使用内核模式，可能需要恢复模式中的“降低安全性”及“允许用户管理来自被认可开发者的内核扩展”，回到系统后批准 macFUSE 并重启。详情见 [授权步骤](docs/SECURITY_SETUP.md)。**不需要关闭 SIP 或 Gatekeeper。**

当前发行包未签名/公证。系统阻止脚本打开时，请先审查源码，再从解压目录的终端运行 `bash Install.command`，不要全局关闭安全保护。

安装后打开工具的 Launcher.command，按菜单选择硬盘。操作前取消复制、关闭该硬盘中的文件。拔线前正常推出。

## 核心安全策略

只处理已确认的外置 NTFS 分区；每次重新发现硬盘，不固定 disk 编号。普通卸载后再检查写入可行性；禁止强制修复、格式化、删除休眠文件或替换系统驱动。失败时尝试恢复只读挂载并明确报告结果。

保留了这次排查得到的关键参数 **auto_xattr**：只测试普通读写并不足以保证 Finder 复制正常，还必须测试扩展属性和保留元数据的复制。验证只创建并清理专用临时文件，不动用户现有文件。

## 验证范围

底层流程在 Apple Silicon / macOS 27.0.1 / macFUSE 5.4.0 / NTFS-3G 2026.9.28 上验证过真实硬盘读写及 Finder 复制。项目程序和安装器有独立测试记录，见 [VALIDATION](docs/VALIDATION.md)。其他系统、断电恢复、性能对照、Windows 完整性检查、干净机器全新安装没有因此得到验证。

当前没有后台自动挂载、原生菜单栏应用或直接 FSKit 实现。完全开源的用户空间驱动路线属于后续项目。

开发与命令行用法、第三方许可见 [英文 README](README.md) 和 [依赖说明](THIRD_PARTY_NOTICES.md)。
