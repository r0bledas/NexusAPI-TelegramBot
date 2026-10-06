using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace NexusManager
{
    public class PyService
    {
        public string Name;
        public string Role;
        public string ExePath;
        public string Arguments;
        public bool IsProcess;
        public Process Proc;
        public DateTime StartTime;
        public int RespawnCount = 0;

        // UI controls
        public Panel Card;
        public Label DotLabel;
        public Label NameLabel;
        public Label InfoLabel;
    }

    public class MainForm : Form
    {
        private readonly string workDir;
        private readonly List<PyService> services = new List<PyService>();
        private RichTextBox terminalBox;
        private Label headerStatusLabel;
        private System.Windows.Forms.Timer watchdogTimer;
        private Process guardianProc;
        private bool allowExit = false;
        private Mutex singleInstanceMutex;

        public MainForm(string dir, Mutex mutex)
        {
            this.workDir = dir;
            this.singleInstanceMutex = mutex;

            this.Text = "Nexus UANL — Protected Python Instance Manager (@NexusEsGayBot)";
            this.Size = new Size(760, 540);
            this.MinimumSize = new Size(640, 440);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(15, 23, 42);
            this.ForeColor = Color.FromArgb(226, 232, 240);
            this.Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);
            this.KeyPreview = true;

            BuildUI();
            this.Shown += (s, e) =>
            {
                this.WindowState = FormWindowState.Normal;
                this.TopMost = true;
                this.Activate();
                this.BringToFront();
                this.TopMost = false;
            };
            InitServices();
            StartWatchdog();
        }

        private void BuildUI()
        {
            // Top Header Panel
            Panel header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 52,
                BackColor = Color.FromArgb(30, 41, 59),
                Padding = new Padding(14, 8, 14, 8)
            };

            Label titleLbl = new Label
            {
                Text = "🛡️ NEXUS UANL — PYTHON INSTANCE MONITOR",
                Font = new Font("Segoe UI", 11.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(56, 189, 248),
                AutoSize = true,
                Location = new Point(14, 8)
            };

            headerStatusLabel = new Label
            {
                Text = "WATCHDOG ACTIVE • CLOSE LOCKED • AUTO-RESPAWN ON",
                Font = new Font("Consolas", 8.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(74, 222, 128),
                AutoSize = true,
                Location = new Point(16, 30)
            };

            header.Controls.Add(titleLbl);
            header.Controls.Add(headerStatusLabel);

            // Services Status Panel (4 cards for the 4 .py files)
            TableLayoutPanel grid = new TableLayoutPanel
            {
                Dock = DockStyle.Top,
                Height = 136,
                ColumnCount = 2,
                RowCount = 2,
                Padding = new Padding(10, 8, 10, 4),
                BackColor = Color.FromArgb(15, 23, 42)
            };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 50f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 50f));

            string pyExe = Path.Combine(workDir, @".venv\Scripts\python.exe");

            services.Add(CreateServiceCard("telegram_bot.py", "Telegram Bot (@NexusEsGayBot)", pyExe, "-u telegram_bot.py", true));
            services.Add(CreateServiceCard("main.py", "FastAPI Server (127.0.0.1:8000)", pyExe, "-u -m uvicorn main:app --host 127.0.0.1 --port 8000", true));
            services.Add(CreateServiceCard("tokens.py", "SIASE HTMLToken & SSO Auth", "", "", false));
            services.Add(CreateServiceCard("requests_utils.py", "Nexus WebApi Client & Parser", "", "", false));

            grid.Controls.Add(services[0].Card, 0, 0);
            grid.Controls.Add(services[1].Card, 1, 0);
            grid.Controls.Add(services[2].Card, 0, 1);
            grid.Controls.Add(services[3].Card, 1, 1);

            // Terminal Header Label
            Panel termHeader = new Panel
            {
                Dock = DockStyle.Top,
                Height = 26,
                BackColor = Color.FromArgb(15, 23, 42),
                Padding = new Padding(12, 4, 12, 0)
            };
            Label termTitle = new Label
            {
                Text = "📟 LIVE BOT I/O TERMINAL LOG (MESSAGES IN & OUT)",
                Font = new Font("Consolas", 9f, FontStyle.Bold),
                ForeColor = Color.FromArgb(148, 163, 184),
                AutoSize = true,
                Location = new Point(12, 5)
            };
            termHeader.Controls.Add(termTitle);

            // Terminal Log Box
            Panel termContainer = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(12, 2, 12, 12),
                BackColor = Color.FromArgb(15, 23, 42)
            };

            terminalBox = new RichTextBox
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(9, 13, 22),
                ForeColor = Color.FromArgb(203, 213, 225),
                Font = new Font("Consolas", 9.5f, FontStyle.Regular),
                ReadOnly = true,
                BorderStyle = BorderStyle.None,
                ScrollBars = RichTextBoxScrollBars.Vertical,
                WordWrap = true,
                DetectUrls = false
            };

            termContainer.Controls.Add(terminalBox);

            this.Controls.Add(termContainer);
            this.Controls.Add(termHeader);
            this.Controls.Add(grid);
            this.Controls.Add(header);
        }

        private PyService CreateServiceCard(string name, string role, string exe, string args, bool isProc)
        {
            Panel card = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(30, 41, 59),
                Margin = new Padding(4),
                Padding = new Padding(8, 6, 8, 6)
            };

            Label dot = new Label
            {
                Text = "●",
                Font = new Font("Segoe UI", 12f, FontStyle.Bold),
                ForeColor = Color.FromArgb(74, 222, 128),
                AutoSize = true,
                Location = new Point(8, 6)
            };

            Label nameLbl = new Label
            {
                Text = name + "  —  " + role,
                Font = new Font("Segoe UI", 9f, FontStyle.Bold),
                ForeColor = Color.FromArgb(241, 245, 249),
                AutoSize = true,
                Location = new Point(28, 7)
            };

            Label infoLbl = new Label
            {
                Text = isProc ? "Starting protected daemon..." : "Loaded by active daemons • Ready",
                Font = new Font("Consolas", 8.25f, FontStyle.Regular),
                ForeColor = Color.FromArgb(148, 163, 184),
                AutoSize = true,
                Location = new Point(30, 28)
            };

            card.Controls.Add(dot);
            card.Controls.Add(nameLbl);
            card.Controls.Add(infoLbl);

            return new PyService
            {
                Name = name,
                Role = role,
                ExePath = exe,
                Arguments = args,
                IsProcess = isProc,
                Card = card,
                DotLabel = dot,
                NameLabel = nameLbl,
                InfoLabel = infoLbl,
                StartTime = DateTime.Now
            };
        }

        private void CleanupOrphanedPyProcesses()
        {
            string venvPy = Path.Combine(workDir, @".venv\Scripts\python.exe").ToLowerInvariant();
            foreach (var p in Process.GetProcessesByName("python"))
            {
                try
                {
                    if (p.MainModule != null && p.MainModule.FileName.ToLowerInvariant() == venvPy)
                    {
                        p.Kill();
                    }
                }
                catch { }
            }
        }

        private void InitServices()
        {
            CleanupOrphanedPyProcesses();
            AppendLog("[GUARDIAN] Initializing protected Python instances outside sandbox...", Color.FromArgb(56, 189, 248));
            foreach (var svc in services)
            {
                if (svc.IsProcess)
                {
                    StartPyProcess(svc, false);
                }
            }
            EnsureGuardianProcess();
        }

        private void StartPyProcess(PyService svc, bool isRespawn)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = svc.ExePath,
                    Arguments = svc.Arguments,
                    WorkingDirectory = workDir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8
                };
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUTF8"] = "1";

                Process p = new Process { StartInfo = psi, EnableRaisingEvents = true };
                p.OutputDataReceived += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(e.Data))
                        OnProcessLog(svc, e.Data, false);
                };
                p.ErrorDataReceived += (s, e) =>
                {
                    if (!string.IsNullOrEmpty(e.Data))
                        OnProcessLog(svc, e.Data, true);
                };

                p.Start();
                try { p.PriorityClass = ProcessPriorityClass.High; } catch { }
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();

                svc.Proc = p;
                svc.StartTime = DateTime.Now;
                if (isRespawn)
                {
                    svc.RespawnCount++;
                    AppendLog(string.Format("[WATCHDOG] Respawned {0} (PID: {1}, Respawns: {2})", svc.Name, p.Id, svc.RespawnCount), Color.FromArgb(250, 204, 21));
                }
                else
                {
                    AppendLog(string.Format("[SYSTEM] Started {0} (PID: {1})", svc.Name, p.Id), Color.FromArgb(74, 222, 128));
                }
            }
            catch (Exception ex)
            {
                AppendLog(string.Format("[ERROR] Failed to start {0}: {1}", svc.Name, ex.Message), Color.FromArgb(248, 113, 113));
            }
        }

        private void EnsureGuardianProcess()
        {
            try
            {
                if (guardianProc != null && !guardianProc.HasExited)
                    return;

                string selfExe = Application.ExecutablePath;
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = selfExe,
                    Arguments = "--guardian " + Process.GetCurrentProcess().Id,
                    WorkingDirectory = workDir,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                guardianProc = Process.Start(psi);
                try { guardianProc.PriorityClass = ProcessPriorityClass.High; } catch { }
            }
            catch { }
        }

        private void StartWatchdog()
        {
            watchdogTimer = new System.Windows.Forms.Timer { Interval = 400 };
            watchdogTimer.Tick += (s, e) =>
            {
                if (allowExit) return;

                EnsureGuardianProcess();

                foreach (var svc in services)
                {
                    if (!svc.IsProcess)
                    {
                        bool botUp = services[0].Proc != null && !services[0].Proc.HasExited;
                        bool apiUp = services[1].Proc != null && !services[1].Proc.HasExited;
                        svc.DotLabel.ForeColor = (botUp && apiUp) ? Color.FromArgb(56, 189, 248) : Color.FromArgb(250, 204, 21);
                        svc.InfoLabel.Text = string.Format("ACTIVE MODULE • Imported by PID {0} & {1}",
                            botUp ? services[0].Proc.Id.ToString() : "-",
                            apiUp ? services[1].Proc.Id.ToString() : "-");
                        continue;
                    }

                    if (svc.Proc == null || svc.Proc.HasExited)
                    {
                        svc.DotLabel.ForeColor = Color.FromArgb(248, 113, 113);
                        svc.InfoLabel.Text = "PROCESS TERMINATED — RESPAWNING NOW...";
                        StartPyProcess(svc, true);
                    }
                    else
                    {
                        TimeSpan up = DateTime.Now - svc.StartTime;
                        svc.DotLabel.ForeColor = Color.FromArgb(74, 222, 128);
                        svc.InfoLabel.Text = string.Format("RUNNING • PID: {0} • Uptime: {1:D2}:{2:D2}:{3:D2} • Respawns: {4}",
                            svc.Proc.Id, (int)up.TotalHours, up.Minutes, up.Seconds, svc.RespawnCount);
                    }
                }
            };
            watchdogTimer.Start();
        }

        private void OnProcessLog(PyService svc, string line, bool isErr)
        {
            if (svc.Name == "main.py")
            {
                // Only show interesting FastAPI requests or startup lines to keep bot log clean
                if (line.Contains("POST /") || line.Contains("GET /") || line.Contains("Uvicorn running"))
                {
                    AppendLog("[API] " + line, Color.FromArgb(148, 163, 184));
                }
                return;
            }

            Color c = Color.FromArgb(203, 213, 225);
            if (line.Contains("[USER -> IN"))
                c = Color.FromArgb(56, 189, 248); // Cyan for incoming user messages
            else if (line.Contains("[BOT -> OUT]"))
                c = Color.FromArgb(74, 222, 128); // Green for outgoing bot replies
            else if (line.Contains("[SYS]"))
                c = Color.FromArgb(250, 204, 21); // Amber for system events
            else if (isErr || line.Contains("Error") || line.Contains("error"))
                c = Color.FromArgb(248, 113, 113);

            AppendLog(line, c);
        }

        private void AppendLog(string text, Color color)
        {
            if (this.IsDisposed) return;
            if (this.InvokeRequired)
            {
                try { this.BeginInvoke(new Action(() => AppendLog(text, color))); } catch { }
                return;
            }

            if (terminalBox.TextLength > 60000)
            {
                terminalBox.Clear();
            }

            terminalBox.SelectionStart = terminalBox.TextLength;
            terminalBox.SelectionLength = 0;
            terminalBox.SelectionColor = color;
            terminalBox.AppendText(text + Environment.NewLine);
            terminalBox.SelectionColor = terminalBox.ForeColor;
            terminalBox.ScrollToCaret();
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            // Secret emergency owner shutdown hotkey: Ctrl + Shift + Alt + K
            if (e.Control && e.Shift && e.Alt && e.KeyCode == Keys.K)
            {
                allowExit = true;
                watchdogTimer.Stop();
                try
                {
                    if (guardianProc != null && !guardianProc.HasExited)
                        guardianProc.Kill();
                }
                catch { }
                foreach (var svc in services)
                {
                    try
                    {
                        if (svc.Proc != null && !svc.Proc.HasExited)
                            svc.Proc.Kill();
                    }
                    catch { }
                }
                Application.Exit();
                return;
            }
            base.OnKeyDown(e);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!allowExit && e.CloseReason != CloseReason.WindowsShutDown)
            {
                e.Cancel = true;
                this.WindowState = FormWindowState.Normal;
                AppendLog("[GUARDIAN] Window close blocked! Instances are protected.", Color.FromArgb(250, 204, 21));
                return;
            }
            base.OnFormClosing(e);
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            string workDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');

            // Guardian mode: watches the main UI process and immediately relaunches it if killed in Task Manager
            if (args.Length >= 2 && args[0] == "--guardian")
            {
                int targetPid;
                if (int.TryParse(args[1], out targetPid))
                {
                    try
                    {
                        Process target = Process.GetProcessById(targetPid);
                        target.WaitForExit();
                    }
                    catch { }

                    // Respawn main UI manager immediately
                    try
                    {
                        Process.Start(new ProcessStartInfo
                        {
                            FileName = Application.ExecutablePath,
                            WorkingDirectory = workDir,
                            UseShellExecute = false
                        });
                    }
                    catch { }
                }
                return;
            }

            bool createdNew;
            Mutex mutex = new Mutex(true, "Global\\NexusUANLProtectedManagerMutex", out createdNew);
            if (!createdNew)
            {
                return;
            }

            try { Process.GetCurrentProcess().PriorityClass = ProcessPriorityClass.High; } catch { }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(workDir, mutex));
        }
    }
}
