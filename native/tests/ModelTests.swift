import Foundation

@main struct ModelTests {
    static func main() throws {
        let data = Data(#"{"device":"/dev/disk9s1","name":"Archive","size":1000,"uuid":"u","mounted":true,"mountpoint":"/Volumes/Archive","status":"writable","identity":["/dev/disk9s1",1000,"u","Archive"]}"#.utf8)
        let disk = try JSONDecoder().decode(DeviceModel.self, from: data)
        precondition(!disk.canWrite, "Missing readonly must never imply writable")
        print("PASS missing-readonly does not imply write readiness")
        precondition(disk.usageFraction == nil, "Missing capacity must not invent usage")
        var object = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        object["capacityBytes"] = 1000
        object["freeBytes"] = 1100
        let invalid = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(invalid.usageFraction == nil, "Invalid capacity must not invent usage")
        object["freeBytes"] = 250
        let measured = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(measured.usageFraction == 0.75)
        print("PASS usage only uses valid measured capacity")
        object["name"] = "Archive\"; $(touch nope)\n中文"
        object["identity"] = ["/dev/disk9s1", Int64(1000), "u", "Archive\"; $(touch nope)\n中文"] as [Any]
        let quoted = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        let identity = try JSONSerialization.jsonObject(with: Data(try quoted.identityJSON().utf8)) as! [Any]
        precondition(identity[0] as? String == "/dev/disk9s1")
        precondition((identity[1] as? NSNumber)?.int64Value == 1000)
        precondition(identity[3] as? String == "Archive\"; $(touch nope)\n中文")
        object["identity"] = ["/dev/disk9s1", "1000", "u", "Archive"]
        let malformed = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        do { _ = try malformed.identityJSON(); preconditionFailure("Malformed identity allowed") }
        catch { print("PASS typed identity validates and preserves JSON escaping") }
        let empty = try JSONDecoder().decode(Snapshot.self, from: Data(#"{"schema":1,"version":"0.1","devices":[],"unsupported":[],"doctor":{"dependencies_ready":false,"kernel_loaded":false,"kernel_check_error":true,"macfuse_helper":false,"platform":"Darwin"},"warnings":[]}"#.utf8))
        precondition(empty.devices.isEmpty && !empty.doctor.writePrerequisitesReady)
        precondition(ByteFormatting.string(nil) == "未知")
        precondition(ByteFormatting.string(-1) == "未知")
        precondition(ByteFormatting.string(0) != "未知")
        print("PASS empty snapshot and missing measurements stay honest")
        let root = URL(fileURLWithPath: "/Users/test/Library/Caches/NTFSReadyDesktop/actions")
        precondition(ActionSecurity.isContained(URL(fileURLWithPath: root.path + "/job/result.json"), in: root))
        precondition(!ActionSecurity.isContained(URL(fileURLWithPath: root.path + "-evil/result.json"), in: root))
        precondition(!ActionSecurity.isContained(URL(fileURLWithPath: root.path + "/../secret.json"), in: root))
        let reply = try JSONDecoder().decode(ActionResult.self, from: Data(#"{"schema":1,"nonce":"abc","ok":true,"action":"verify","device":"/dev/disk9s1","message":"verified","result":{}}"#.utf8))
        precondition(reply.matches(nonce: "abc", action: .verify, device: "/dev/disk9s1"))
        precondition(!reply.matches(nonce: "evil", action: .verify, device: "/dev/disk9s1"))
        precondition(!reply.matches(nonce: "abc", action: .unmount, device: "/dev/disk9s1"))
        print("PASS callback containment and result binding")
        let prepared = try JSONDecoder().decode(PreparedAction.self, from: Data(#"{"schema":1,"nonce":"0123456789abcdef0123456789abcdef","command_path":"/Users/test/Library/Caches/NTFSReadyDesktop/actions/0123456789abcdef0123456789abcdef/action.command","result_path":"/Users/test/Library/Caches/NTFSReadyDesktop/actions/0123456789abcdef0123456789abcdef/result.json"}"#.utf8))
        precondition(prepared.matchesCacheLayout(root: root))
        precondition(!prepared.matchesCacheLayout(root: root.appendingPathComponent("other")))
        print("PASS authorization paths bind exact filenames to nonce directory")
        object["readonly"] = false
        object["status"] = "writable"
        let writable = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(writable.canWrite)
        object["mounted"] = false
        let unmounted = try JSONDecoder().decode(DeviceModel.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(!unmounted.canWrite)
        print("PASS write status requires affirmative readonly flag and active mount")
        let runtimeArguments = BackendRuntimePolicy.arguments(["snapshot"])
        precondition(runtimeArguments == ["-B", "-s", "-m", "ntfs_ready.gui_bridge", "snapshot"], "Backend must not write Python bytecode into the signed app")
        print("PASS signed-bundle runtime disables bytecode and user-site imports")
        let cleanEnvironment = BackendRuntimePolicy.environment(["PYTHONHOME": "/untrusted", "PYTHONSTARTUP": "/untrusted", "PYTHONINSPECT": "1", "PYTHONUSERBASE": "/untrusted", "PYTHONPYCACHEPREFIX": "/untrusted", "PYTHONPATH": "/untrusted", "PATH": "/usr/bin"], backendPath: "/trusted backend")
        precondition(["PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONUSERBASE", "PYTHONPYCACHEPREFIX"].allSatisfy { cleanEnvironment[$0] == nil })
        precondition(cleanEnvironment["PYTHONPATH"] == "/trusted backend" && cleanEnvironment["PATH"] == "/usr/bin")
        precondition(cleanEnvironment["PYTHONDONTWRITEBYTECODE"] == "1" && cleanEnvironment["PYTHONNOUSERSITE"] == "1" && cleanEnvironment["PYTHONUNBUFFERED"] == "1")
        print("PASS inherited Python configuration cannot redirect the backend runtime")
        let candidates = BackendRuntimePolicy.pythonCandidates
        precondition(candidates.firstIndex(of: "/Library/Developer/CommandLineTools/usr/bin/python3")! < candidates.firstIndex(of: "/usr/bin/python3")!, "Use installed CLT Python before the active-Xcode shim")
        print("PASS installed CLT runtime precedes the active-Xcode Python shim")
        if CommandLine.arguments.count == 2 {
            let live = try JSONDecoder().decode(Snapshot.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
            precondition(live.schema == 1)
            print("PASS live backend snapshot: \(live.devices.count) NTFS devices, \(live.unsupported.count) unsupported volumes; dependencies_ready=\(live.doctor.dependencies_ready)")
        }
    }
}
