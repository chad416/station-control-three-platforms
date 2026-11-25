<#
  Build the station project with a panel in TIA Portal V18 through Openness, without user interface.

  S7-1513 with FB_CurveEval, FB_HandleStation, FB_StationAlarms, DB_HMI and OB1 (siemens/scl),
  a KTP700 Basic, both on one PROFINET subnet, then the HMI connection, tag table and four screens
  imported from siemens/hmi/xml (python siemens/hmi/make_hmi_xml.py). PLC and HMI are compiled.
  The record goes to results/tia_hmi_build.txt; what TIA made of the imports is exported to
  siemens/hmi/export/.

  Needs: TIA Portal V18 with STEP 7 Professional and WinCC, Openness, Windows PowerShell 5.1.
  Usage:  powershell -ExecutionPolicy Bypass -File siemens\scripts\tia_hmi.ps1 [-OutDir C:\TIA_build]
  The pattern (TiaPortalMode.WithoutUserInterface, assembly resolver) is the one of tia_build.ps1 in
  the door-handle project.
#>
param(
    [string]$OutDir = "C:\TIA_build",
    [string]$ProjectName = "station39_hmi",
    [string]$Cpu = "OrderNumber:6ES7 513-1AL02-0AB0/V2.9",
    [string]$Hmi = "OrderNumber:6AV2 123-2GB03-0AX0/17.0.0.0",
    [switch]$TryImports   # the HMI imports: every route failed (results/tia_hmi_build_attempts.txt)
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$scl = Join-Path $root "siemens\scl"
$xml = Join-Path $root "siemens\hmi\xml"
$export = Join-Path $root "siemens\hmi\export"
$result = Join-Path $root "results\tia_hmi_build.txt"
$api = "C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll"
$apiHmi = "C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.Hmi.dll"
$old = Join-Path $OutDir $ProjectName
if ((Test-Path $old) -and (Get-ChildItem $old -Filter "*.ap*" -File)) { Remove-Item -Recurse -Force $old }
New-Item -ItemType Directory -Force $OutDir, $export | Out-Null

$resolver = @"
using System; using System.IO; using System.Reflection;
public static class OpnResolveHmi {
    static string[] dirs;
    public static void Init(string[] d) {
        dirs = d;
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) => {
            var n = new AssemblyName(e.Name).Name;
            if (n.EndsWith(".resources")) return null;
            foreach (var dir in dirs) { var p = Path.Combine(dir, n + ".dll"); if (File.Exists(p)) return Assembly.LoadFrom(p); }
            return null;
        };
    }
}
"@
Add-Type -TypeDefinition $resolver
$portal = "C:\Program Files\Siemens\Automation\Portal V18"
[OpnResolveHmi]::Init(@((Split-Path -Parent $api), "$portal\Bin\PublicAPI", "$portal\Bin"))
[void][System.Reflection.Assembly]::LoadFrom($api)
[void][System.Reflection.Assembly]::LoadFrom($apiHmi)

$code = @"
using System; using System.IO; using System.Linq; using System.Text; using System.Collections.Generic;
using Siemens.Engineering; using Siemens.Engineering.HW; using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW; using Siemens.Engineering.SW.Blocks; using Siemens.Engineering.SW.ExternalSources;
using Siemens.Engineering.Compiler;
using Siemens.Engineering.Hmi; using Siemens.Engineering.Hmi.Screen; using Siemens.Engineering.Hmi.Tag;
using Siemens.Engineering.Hmi.Communication;

public static class HmiBuild {
    static StringBuilder sb = new StringBuilder();
    static void Log(string s) { sb.AppendLine(s); }
    static string Msg(Exception ex) { return (ex.InnerException ?? ex).Message.Replace("\r", " ").Replace("\n", " "); }
    static void Walk(CompilerResultMessage m, int depth) {
        Log(new string(' ', 2 * depth) + m.State + "  " + m.Path + "  " + m.Description);
        foreach (var c in m.Messages) Walk(c, depth + 1);
    }
    static IEnumerable<DeviceItem> All(IEnumerable<DeviceItem> items) {
        foreach (var d in items) { yield return d; foreach (var c in All(d.DeviceItems)) yield return c; }
    }
    static T Soft<T>(Device dev) where T : class {
        foreach (var d in All(dev.DeviceItems)) {
            var sc = d.GetService<SoftwareContainer>();
            if (sc != null && sc.Software is T) return (T)(object)sc.Software;
        }
        return null;
    }
    static Node FirstNode(Device dev) {
        foreach (var d in All(dev.DeviceItems)) {
            var ni = d.GetService<NetworkInterface>();
            if (ni != null && ni.Nodes.Count > 0) return ni.Nodes[0];
        }
        return null;
    }
    static void Compile(IEngineeringServiceProvider target, string what) {
        var c = target.GetService<ICompilable>();
        if (c == null) { Log("COMPILE " + what + ": no compile service"); return; }
        var r = c.Compile();
        Log("COMPILE " + what + " " + r.State + "  errors=" + r.ErrorCount + "  warnings=" + r.WarningCount);
        foreach (var m in r.Messages) Walk(m, 1);
    }
    static TiaPortal tiaS; static Project projS; static string projPath;
    static bool Import(Action a, string what) {
        try { a(); Log("IMPORT ok   " + what); projS.Save(); return true; }
        catch (Exception ex) {
            Log("IMPORT FAIL " + what + ": " + Msg(ex));
            // a failed import disposes the project object: open the last saved state again
            try { projS.Close(); } catch (Exception) { }
            projS = tiaS.Projects.Open(new FileInfo(projPath));
            Log("  project opened again from its last saved state");
            return false;
        }
    }

    public static bool tryImports;
    public static string Run(string outDir, string name, string cpu, string hmiType, string scl, string xml, string export) {
        try { Inner(outDir, name, cpu, hmiType, scl, xml, export); }
        catch (Exception ex) { Log("STOPPED: " + Msg(ex) + " | " + (ex.StackTrace ?? "").Replace(Environment.NewLine, " ")); }
        return sb.ToString();
    }
    static void Inner(string outDir, string name, string cpu, string hmiType, string scl, string xml, string export) {
        using (var tia = new TiaPortal(TiaPortalMode.WithoutUserInterface)) {
            var project = tia.Projects.Create(new DirectoryInfo(outDir), name);
            tiaS = tia; projS = project; projPath = Path.Combine(outDir, name, name + ".ap18");
            var plcDev = project.Devices.CreateWithItem(cpu, "PLC_1", "PLC_1");
            var hmiDev = project.Devices.CreateWithItem(hmiType, "HMI_1", "HMI_1");
            Log("devices: " + cpu + " / " + hmiType);
            var plc = Soft<PlcSoftware>(plcDev);
            var hmi = Soft<HmiTarget>(hmiDev);
            foreach (var entry in new[] { "FB_CurveEval", "FB_HandleStation", "hmi\\FB_StationAlarms", "hmi\\DB_HMI", "hmi\\OB_Station" }) {
                var n = Path.GetFileName(entry);
                try {
                    plc.ExternalSourceGroup.ExternalSources.CreateFromFile(n, Path.Combine(scl, entry + ".scl")).GenerateBlocksFromSource();
                    Log("generated " + n);
                } catch (Exception ex) { Log("GENERATE FAILED " + n + ": " + Msg(ex)); }
            }
            Log("step: compile PLC");
            Compile(plc, "PLC");
            var db = plc.BlockGroup.Blocks.Find("DB_HMI");
            int dbNo = db != null ? db.Number : -1;
            Log("DB_HMI number " + dbNo);
            foreach (PlcBlock b in plc.BlockGroup.Blocks) Log("  block " + b.Name + "  " + b.GetType().Name + " " + b.Number + "  consistent=" + b.IsConsistent);

            try {
                var pn = FirstNode(plcDev); var hn = FirstNode(hmiDev);
                var subnet = pn.CreateAndConnectToSubnet("PN/IE_1");
                hn.ConnectToSubnet(subnet);
                Log("network: " + pn.Name + " and " + hn.Name + " on " + subnet.Name
                    + "  PLC " + pn.GetAttribute("Address") + "  HMI " + hn.GetAttribute("Address"));
            } catch (Exception ex) { Log("NETWORK FAILED: " + Msg(ex)); }
            project.Save();
            hmi = Soft<HmiTarget>(hmiDev);   // the HMI target object is replaced when the device is networked
            plc = Soft<PlcSoftware>(plcDev);

            // a failed import disposes the HMI target object: it is fetched again after every import
            if (!tryImports) {
                Log("HMI imports SKIPPED: connection, tags and screens could not be imported (results/tia_hmi_build_attempts.txt).");
                Log("  A failed Openness import disposed the HMI target, then the device, then the project, then the TIA Portal session.");
                hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev);
                Compile(hmi, "HMI (device with no connection, tags or screens)");
                plcDev = projS.Devices.Find("PLC_1"); plc = Soft<PlcSoftware>(plcDev);
                Compile(plc, "PLC (again, after the network)");
                projS.Save(); projS.Close();
                return;
            }
            // The connection import was refused in two runs: "The value 'SIMATIC S7 1500' for the attribute
            // 'Driver' is not supported"; the second run stopped there because a failed import disposes the
            // HMI device object (results/tia_hmi_build_attempts.txt). Fallback: no connection; the tags are
            // HMI-internal, so tags and screens can still be imported and compiled.
            bool conn = false;
            Log("connection: NOT created (fallback, see the attempts record)");
            var tagsFile = Path.Combine(outDir, "tags_Station.xml");
            File.WriteAllText(tagsFile, File.ReadAllText(Path.Combine(xml, conn ? "tags_Station.xml" : "tags_Station_internal.xml")).Replace("{DB}", dbNo.ToString()));
            Import(() => hmi.TagFolder.TagTables.Import(new FileInfo(tagsFile), ImportOptions.Override),
                conn ? "tag table Station, absolute into DB_HMI = DB" + dbNo : "tag table Station as HMI-INTERNAL tags (no connection)");
            hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev);
            foreach (var s in new[] { "Station", "Measurement", "Alarms", "Setup" }) {
                var ok = Import(() => hmi.ScreenFolder.Screens.Import(new FileInfo(Path.Combine(xml, "screen_" + s + ".xml")), ImportOptions.Override), "screen " + s + " with navigation buttons");
                hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev);
                if (!ok) {
                    Import(() => hmi.ScreenFolder.Screens.Import(new FileInfo(Path.Combine(xml, "screen_" + s + "_nonav.xml")), ImportOptions.Override), "screen " + s + " WITHOUT navigation buttons");
                    hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev);
                }
            }
            try { hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev); hmi.SetAttribute("StartScreen", hmi.ScreenFolder.Screens.Find("Station")); Log("start screen set"); }
            catch (Exception ex) { Log("start screen not set: " + Msg(ex)); }
            hmiDev = projS.Devices.Find("HMI_1"); hmi = Soft<HmiTarget>(hmiDev);
            plcDev = projS.Devices.Find("PLC_1"); plc = Soft<PlcSoftware>(plcDev);
            Compile(hmi, "HMI");
            Compile(plc, "PLC (again, after the network)");

            foreach (Screen s in hmi.ScreenFolder.Screens) {
                try { s.Export(new FileInfo(Path.Combine(export, "screen_" + s.Name + ".xml")), ExportOptions.WithDefaults); Log("exported screen " + s.Name); }
                catch (Exception ex) { Log("export screen " + s.Name + " failed: " + Msg(ex)); }
            }
            foreach (TagTable t in hmi.TagFolder.TagTables) {
                try { t.Export(new FileInfo(Path.Combine(export, "tags_" + t.Name.Replace(" ", "_") + ".xml")), ExportOptions.WithDefaults); Log("exported tag table " + t.Name + " (" + t.Tags.Count + " tags)"); }
                catch (Exception ex) { Log("export tags failed: " + Msg(ex)); }
            }
            foreach (Connection c in hmi.Connections) {
                try { c.Export(new FileInfo(Path.Combine(export, "connection_" + c.Name + ".xml")), ExportOptions.WithDefaults); Log("exported connection " + c.Name); }
                catch (Exception ex) { Log("export connection failed: " + Msg(ex)); }
            }
            projS.Save();
            projS.Close();
        }
    }
}
"@
Add-Type -TypeDefinition $code -ReferencedAssemblies @($api, $apiHmi)
[HmiBuild]::tryImports = [bool]$TryImports
$text = "TIA Portal V18 Openness, no user interface, " + (Get-Date -Format "yyyy-MM-dd HH:mm") + "`r`n" + [HmiBuild]::Run($OutDir, $ProjectName, $Cpu, $Hmi, $scl, $xml, $export)
$text
$text | Out-File -Encoding utf8 $result
