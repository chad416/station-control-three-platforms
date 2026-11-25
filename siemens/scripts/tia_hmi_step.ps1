<#
  One HMI import per TIA Portal session, into the project tia_hmi.ps1 built and saved.

  A refused Openness import disposes the TIA Portal session (results/tia_hmi_build_attempts.txt), so
  every import gets its own session: open the saved project, import one file, save, compile the
  panel, close. Each run appends its record to results/tia_hmi_steps.txt.

  Usage:
    powershell -ExecutionPolicy Bypass -File siemens\scripts\tia_hmi_step.ps1 -Kind connection -File siemens\hmi\xml\connection.xml
    ... -Kind tags -File siemens\hmi\xml\tags_Station.xml        ({DB} is replaced by the number of DB_HMI)
    ... -Kind screen -File siemens\hmi\xml\screen_Station.xml
    ... -Kind start -Name Station                                 (start screen)
    ... -Kind compile                                             (compile panel and PLC only)
#>
param(
    [Parameter(Mandatory = $true)][string]$Kind,
    [string]$File = "",
    [string]$Name = "",
    [string]$Project = "C:\TIA_build\station39_hmi\station39_hmi.ap18"
)
$File = (($File -split ";") | ForEach-Object { if ($_ -ne "" -and -not [System.IO.Path]::IsPathRooted($_)) { Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) $_ } else { $_ } }) -join ";"
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$result = Join-Path $root "results\tia_hmi_steps.txt"
$api = "C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.dll"
$apiHmi = "C:\Program Files\Siemens\Automation\Portal V18\PublicAPI\V18\Siemens.Engineering.Hmi.dll"
$resolver = @"
using System; using System.IO; using System.Reflection;
public static class OpnResolveStep {
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
[OpnResolveStep]::Init(@((Split-Path -Parent $api), "$portal\Bin\PublicAPI", "$portal\Bin"))
[void][System.Reflection.Assembly]::LoadFrom($api)
[void][System.Reflection.Assembly]::LoadFrom($apiHmi)
$code = @"
using System; using System.IO; using System.Linq; using System.Text; using System.Collections.Generic;
using Siemens.Engineering; using Siemens.Engineering.HW; using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW; using Siemens.Engineering.SW.Blocks; using Siemens.Engineering.Compiler;
using Siemens.Engineering.Hmi; using Siemens.Engineering.Hmi.Screen; using Siemens.Engineering.Hmi.Tag;
using Siemens.Engineering.Hmi.Communication;
public static class HmiStep {
    static StringBuilder sb = new StringBuilder();
    static void Log(string s) { sb.AppendLine(s); }
    static string Msg(Exception ex) { return (ex.InnerException ?? ex).Message.Replace(Environment.NewLine, " ").Replace("\n", " "); }
    static void Walk(CompilerResultMessage m, int d) {
        Log(new string(' ', 2 * d) + m.State + "  " + m.Path + "  " + m.Description);
        foreach (var c in m.Messages) Walk(c, d + 1);
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
    static void Compile(IEngineeringServiceProvider t, string what) {
        var r = t.GetService<ICompilable>().Compile();
        Log("COMPILE " + what + " " + r.State + "  errors=" + r.ErrorCount + "  warnings=" + r.WarningCount);
        foreach (var m in r.Messages) Walk(m, 1);
    }
    public static string Run(string projectPath, string kind, string file, string name) {
        try {
            using (var tia = new TiaPortal(TiaPortalMode.WithoutUserInterface)) {
                var project = tia.Projects.Open(new FileInfo(projectPath));
                var hmiDev = project.Devices.Find("HMI_1");
                var plcDev = project.Devices.Find("PLC_1");
                var hmi = Soft<HmiTarget>(hmiDev);
                var plc = Soft<PlcSoftware>(plcDev);
                try {
                    if (kind == "connection") {
                        hmi.Connections.Import(new FileInfo(file), ImportOptions.Override);
                    } else if (kind == "tags") {
                        var db = plc.BlockGroup.Blocks.Find("DB_HMI");
                        var tmp = Path.Combine(Path.GetTempPath(), "station39_tags.xml");
                        File.WriteAllText(tmp, File.ReadAllText(file).Replace("{DB}", db.Number.ToString()));
                        hmi.TagFolder.TagTables.Import(new FileInfo(tmp), ImportOptions.Override);
                    } else if (kind == "screen") {
                        foreach (var f in file.Split(';')) {   // several screens of the same form in one session
                            hmi.ScreenFolder.Screens.Import(new FileInfo(f), ImportOptions.Override);
                            Log("  imported " + Path.GetFileName(f));
                        }
                    } else if (kind == "start") {
                        hmi.SetAttribute("StartScreen", hmi.ScreenFolder.Screens.Find(name));
                    }
                    if (kind != "compile") Log("IMPORT ok   " + kind + " " + Path.GetFileName(file) + name);
                } catch (Exception ex) {
                    Log("IMPORT FAIL " + kind + " " + Path.GetFileName(file) + name + ": " + Msg(ex));
                    return sb.ToString();
                }
                project.Save();
                foreach (Connection c in hmi.Connections) Log("  connection " + c.Name);
                foreach (TagTable t in hmi.TagFolder.TagTables) Log("  tag table " + t.Name + ": " + t.Tags.Count + " tags");
                foreach (Screen s in hmi.ScreenFolder.Screens) Log("  screen " + s.Name);
                Compile(hmi, "HMI");
                Compile(plc, "PLC");
                project.Save();
                project.Close();
            }
        } catch (Exception ex) { Log("STOPPED: " + Msg(ex)); }
        return sb.ToString();
    }
}
"@
Add-Type -TypeDefinition $code -ReferencedAssemblies @($api, $apiHmi)
$text = "---- " + (Get-Date -Format "yyyy-MM-dd HH:mm") + "  step " + $Kind + " " + (Split-Path -Leaf $File) + $Name + "`r`n" + [HmiStep]::Run($Project, $Kind, $File, $Name)
$text
$text | Out-File -Append -Encoding utf8 $result
