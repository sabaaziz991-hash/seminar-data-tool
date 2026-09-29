// SeminarDataTool.exe - tiny launcher (C#, .NET Framework 4 which is part of Windows 10/11).
// 1. Checks that the whole ZIP was extracted (app\ and data\ next to this file). If not - e.g. the user
//    double-clicked the EXE inside the ZIP and Windows extracted only this file to a temp folder - it shows
//    a Hebrew message instead of a technical error.
// 2. Starts app\SeminarDataToolApp.exe (the real program) with the same arguments and exits.
// Build: csc /target:winexe /win32icon:app.ico /out:SeminarDataTool.exe /r:System.Windows.Forms.dll Launcher.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("SeminarDataTool")]
[assembly: AssemblyProduct("SeminarDataTool")]
[assembly: AssemblyVersion("1.1.0.0")]

static class Launcher
{
    const string Title = "כלי נתוני הסמינריון";
    const string ExtractMsg =
        "יש לחלץ את כל תוכן קובץ ה-ZIP לתיקייה (לחצן ימני ← חלץ הכל) ורק אז להפעיל.\n\n" +
        "נראה שהתוכנה הופעלה מתוך קובץ ה-ZIP, או שחסרים קבצים (התיקיות app או data).\n" +
        "לאחר החילוץ: היכנסו לתיקייה SeminarDataTool שחולצה ולחצו פעמיים על הקובץ „הפעלה” (או על SeminarDataTool).";

    static void Show(string text, MessageBoxIcon icon)
    {
        MessageBox.Show(text, Title, MessageBoxButtons.OK, icon, MessageBoxDefaultButton.Button1,
                        MessageBoxOptions.RtlReading | MessageBoxOptions.RightAlign);
    }

    static string Quote(string a)
    {
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return a;
        return "\"" + a.Replace("\"", "\\\"") + "\"";
    }

    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string app = Path.Combine(root, "app", "SeminarDataToolApp.exe");
        bool complete = File.Exists(app)
                        && Directory.Exists(Path.Combine(root, "app", "_internal"))
                        && File.Exists(Path.Combine(root, "data", "study_dataset_final.csv"));
        if (!complete)
        {
            Show(ExtractMsg, MessageBoxIcon.Warning);
            return 2;
        }
        var sb = new StringBuilder();
        foreach (string a in args) { if (sb.Length > 0) sb.Append(' '); sb.Append(Quote(a)); }
        try
        {
            var psi = new ProcessStartInfo(app, sb.ToString());
            psi.UseShellExecute = false;
            psi.WorkingDirectory = Path.GetDirectoryName(app);
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            Show("לא ניתן להפעיל את התוכנה.\n\n" + ex.Message +
                 "\n\nייתכן שתוכנת האנטי-וירוס חסמה את הקובץ app\\SeminarDataToolApp.exe.", MessageBoxIcon.Error);
            return 1;
        }
    }
}
