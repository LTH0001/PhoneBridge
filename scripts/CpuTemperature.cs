// PhoneBridge's isolated read-only CPU sampler. No remote endpoint or commands.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using LibreHardwareMonitor.Hardware;
using LibreHardwareMonitor.PawnIo;

internal static class CpuTemperature
{
    private static readonly string Cache = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "cpu.json");
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    private static bool Valid(float? value)
    {
        return value.HasValue && !float.IsNaN(value.Value) && !float.IsInfinity(value.Value)
            && value.Value > 0 && value.Value <= 150;
    }

    private static Dictionary<string, object> Read(Computer computer)
    {
        var data = new Dictionary<string, object> {
            {"schema", 1}, {"updated_at", (DateTime.UtcNow - new DateTime(1970,1,1)).TotalSeconds},
            {"sampler_pid", Process.GetCurrentProcess().Id}, {"temperature_c", null},
            {"temperature_source", ""}, {"temperature_note", "CPU sensors not available"},
            {"cores", new List<object>()}, {"backend", "LibreHardwareMonitor 0.9.6 / PawnIO"}
        };
        var cores = (List<object>)data["cores"];
        float? package = null, coreMax = null;
        foreach (IHardware hardware in computer.Hardware)
        {
            if (hardware.HardwareType != HardwareType.Cpu) continue;
            hardware.Update();
            data["name"] = hardware.Name;
            foreach (ISensor sensor in hardware.Sensors)
            {
                if (sensor.SensorType != SensorType.Temperature || !Valid(sensor.Value)
                    || sensor.Name.IndexOf("Distance", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                // Reject distance-to-TjMax and motherboard/ACPI temperatures.
                if (sensor.Name == "CPU Package") package = sensor.Value;
                else if (sensor.Name == "Core Max") coreMax = sensor.Value;
                else if (sensor.Name.StartsWith("P-Core #") || sensor.Name.StartsWith("E-Core #")
                         || sensor.Name.StartsWith("CPU Core #"))
                    cores.Add(new Dictionary<string, object> { {"name", sensor.Name}, {"temperature_c", sensor.Value} });
            }
        }
        if (package.HasValue || coreMax.HasValue)
        {
            data["temperature_c"] = package ?? coreMax;
            data["temperature_source"] = package.HasValue ? "CPU Package" : "Core Max";
            data["temperature_note"] = "";
        }
        return data;
    }

    private static void Publish(Dictionary<string, object> data)
    {
        string temporary = Cache + "." + Process.GetCurrentProcess().Id + ".tmp";
        File.WriteAllText(temporary, Json.Serialize(data), new UTF8Encoding(false));
        if (File.Exists(Cache)) File.Replace(temporary, Cache, null);
        else File.Move(temporary, Cache);
    }

    private static bool OwnerAlive(int pid, long started)
    {
        try {
            using (Process owner = Process.GetProcessById(pid))
                return !owner.HasExited && owner.StartTime.ToUniversalTime().Ticks == started
                    && owner.SessionId == Process.GetCurrentProcess().SessionId;
        } catch { return false; }
    }

    private static int Main(string[] args)
    {
        int ownerPid; long ownerStarted;
        if (args.Length != 2 || !int.TryParse(args[0], out ownerPid)
            || !long.TryParse(args[1], out ownerStarted) || !OwnerAlive(ownerPid, ownerStarted)) return 2;
        if (!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)) return 3;
        bool created;
        using (var mutex = new Mutex(true, "Local\\PhoneBridge.CpuTemperature." + Process.GetCurrentProcess().SessionId, out created))
        {
            if (!created) return 0;
            var computer = new Computer { IsCpuEnabled = true };
            try {
                if (!PawnIo.IsInstalled) return 4;
                computer.Open();
                while (OwnerAlive(ownerPid, ownerStarted))
                {
                    try { Publish(Read(computer)); }
                    catch (Exception error) {
                        Publish(new Dictionary<string, object> {
                            {"schema",1}, {"updated_at",(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds},
                            {"temperature_c",null}, {"temperature_source",""},
                            {"temperature_note",error.GetType().Name + ": " + error.Message}
                        });
                    }
                    Thread.Sleep(1000);
                }
            } finally { computer.Close(); }
        }
        return 0;
    }
}
