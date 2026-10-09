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
        public Label BadgeLabel;
        public Label NameLabel;
        public Label InfoLabel;
    }

    public class MainForm : Form
    {
        private readonly string workDir;
        private readonly List<PyService> services = new List<PyService>();
        private RichTextBox terminalBox;
        private ToolStripStatusLabel statusInstancesLabel;
        private ToolStripStatusLabel statusWatchdogLabel;
        private System.Windows.Forms.Timer watchdogTimer;
        private Process guardianProc;
        private bool allowExit = false;
        private Mutex singleInstanceMutex;

        public MainForm(string dir, Mutex mutex)
        {
            this.workDir = dir;
            this.singleInstanceMutex = mutex;

            this.Text = "Nexus UANL - Python Instance Manager (@NexusEsGayBot)";
            this.Size = new Size(760, 530);
            this.MinimumSize = new Size(640, 440);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = SystemColors.Control;
            this.ForeColor = SystemColors.ControlText;
            this.Font = new Font("Tahoma", 8.25f, FontStyle.Regular);
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
            // Bottom StatusStrip
            StatusStrip statusStrip = new StatusStrip();
            statusInstancesLabel = new ToolStripStatusLabel("Instances: Initializing...");
            statusWatchdogLabel = new ToolStripStatusLabel("Watchdog: Active (400ms) | Exit: Ctrl+Shift+Alt+K")
            {
                Spring = true,
                TextAlign = ContentAlignment.MiddleRight
            };
            statusStrip.Items.Add(statusInstancesLabel);
            statusStrip.Items.Add(statusWatchdogLabel);

            // Top Header Panel
            Panel header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 44,
                BackColor = SystemColors.Control,
                Padding = new Padding(10, 6, 10, 4)
            };

            Label titleLbl = new Label
            {
                Text = "NEXUS UANL - PYTHON INSTANCE MONITOR",
                Font = new Font("Tahoma", 9.5f, FontStyle.Bold),
                ForeColor = SystemColors.ControlText,
                AutoSize = true,
                Location = new Point(8, 6)
            };

            Label subLbl = new Label
            {
                Text = "Watchdog: Active | Protection: Locked | Auto-Respawn: Enabled",
                Font = new Font("Tahoma", 8.25f, FontStyle.Regular),
                ForeColor = Color.FromArgb(70, 70, 70),
                AutoSize = true,
                Location = new Point(9, 24)
            };

            header.Controls.Add(titleLbl);
            header.Controls.Add(subLbl);

            // Services GroupBox
            GroupBox servicesGroup = new GroupBox
            {
                Text = "Managed Python Services and Modules",
                Dock = DockStyle.Top,
                Height = 154,
                Padding = new Padding(8, 10, 8, 8),
                BackColor = SystemColors.Control
            };

            TableLayoutPanel grid = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 2,
                RowCount = 2,
                Padding = new Padding(2)
            };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 50f));
            grid.RowStyles.Add(new RowStyle(SizeType.Percent, 50f));

            string pyExe = Path.Combine(workDir, @".venv\Scripts\python.exe");

            services.Add(CreateServiceCard("telegram_bot.py", "Telegram Bot (@NexusEsGayBot)", pyExe, "-u telegram_bot.py", true));
            services.Add(CreateServiceCard("main.py", "FastAPI Server (127.0.0.1:8000)", pyExe, "-u -m uvicorn main:app --host 127.0.0.1 --port 8000", true));
            services.Add(CreateServiceCard("tokens.py", "SIASE HTMLToken and SSO Auth", "", "", false));
            services.Add(CreateServiceCard("requests_utils.py", "Nexus WebApi Client and Parser", "", "", false));

            grid.Controls.Add(services[0].Card, 0, 0);
            grid.Controls.Add(services[1].Card, 1, 0);
            grid.Controls.Add(services[2].Card, 0, 1);
            grid.Controls.Add(services[3].Card, 1, 1);
            servicesGroup.Controls.Add(grid);

            // Terminal GroupBox
            GroupBox terminalGroup = new GroupBox
            {
                Text = "Console Activity Log (Messages In and Out)",
                Dock = DockStyle.Fill,
                Padding = new Padding(8, 8, 8, 8),
                BackColor = SystemColors.Control
            };

            terminalBox = new RichTextBox
            {
                Dock = DockStyle.Fill,
                BackColor = Color.Black,
                ForeColor = Color.Gainsboro,
                Font = new Font("Consolas", 9f, FontStyle.Regular),
                ReadOnly = true,
                BorderStyle = BorderStyle.Fixed3D,
                ScrollBars = RichTextBoxScrollBars.Vertical,
                WordWrap = true,
                DetectUrls = false
            };

            terminalGroup.Controls.Add(terminalBox);

            // Add controls (Dock ordering: Fill must be added before Top to layout properly in WinForms)
            this.Controls.Add(terminalGroup);
            this.Controls.Add(servicesGroup);
            this.Controls.Add(header);
            this.Controls.Add(statusStrip);
        }

        private PyService CreateServiceCard(string name, string role, string exe, string args, bool isProc)
        {
            Panel card = new Panel
            {
                Dock = DockStyle.Fill,
                BorderStyle = BorderStyle.FixedSingle,
                BackColor = SystemColors.Window,
                Margin = new Padding(3),
                Padding = new Padding(6, 4, 6, 4)
            };

            Label badge = new Label
            {
                Text = isProc ? "[ STARTING ]" : "[ MODULE ]",
                Font = new Font("Tahoma", 7.5f, FontStyle.Bold),
                ForeColor = isProc ? Color.DarkGoldenrod : Color.DarkBlue,
                AutoSize = true,
                Location = new Point(6, 6)
            };

            Label nameLbl = new Label
            {
                Text = name + " : " + role,
                Font = new Font("Tahoma", 8.25f, FontStyle.Bold),
                ForeColor = Color.Black,
                AutoSize = true,
                Location = new Point(88, 6)
            };

            Label infoLbl = new Label
            {
                Text = isProc ? "Starting process..." : "Active module (imported by active instances)",
                Font = new Font("Consolas", 8.25f, FontStyle.Regular),
                ForeColor = Color.FromArgb(70, 70, 70),
                AutoSize = true,
                Location = new Point(8, 25)
            };

            card.Controls.Add(badge);
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
                BadgeLabel = badge,
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
            AppendLog("[GUARDIAN] Initializing protected Python instances...", Color.LightSkyBlue);
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
                    AppendLog(string.Format("[WATCHDOG] Respawned {0} (PID: {1}, Respawns: {2})", svc.Name, p.Id, svc.RespawnCount), Color.Khaki);
                }
                else
                {
                    AppendLog(string.Format("[SYSTEM] Started {0} (PID: {1})", svc.Name, p.Id), Color.LightGreen);
                }
            }
            catch (Exception ex)
            {
                AppendLog(string.Format("[ERROR] Failed to start {0}: {1}", svc.Name, ex.Message), Color.Salmon);
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

                int activeCount = 0;
                foreach (var svc in services)
                {
                    if (!svc.IsProcess)
                    {
                        bool botUp = services[0].Proc != null && !services[0].Proc.HasExited;
                        bool apiUp = services[1].Proc != null && !services[1].Proc.HasExited;
                        svc.BadgeLabel.Text = "[ MODULE ]";
                        svc.BadgeLabel.ForeColor = (botUp && apiUp) ? Color.DarkBlue : Color.DarkOrange;
                        svc.InfoLabel.Text = string.Format("Active module : Imported by PID {0} and {1}",
                            botUp ? services[0].Proc.Id.ToString() : "-",
                            apiUp ? services[1].Proc.Id.ToString() : "-");
                        continue;
                    }

                    if (svc.Proc == null || svc.Proc.HasExited)
                    {
                        svc.BadgeLabel.Text = "[ STOPPED ]";
                        svc.BadgeLabel.ForeColor = Color.DarkRed;
                        svc.InfoLabel.Text = "Process terminated : Respawning immediately...";
                        StartPyProcess(svc, true);
                    }
                    else
                    {
                        activeCount++;
                        TimeSpan up = DateTime.Now - svc.StartTime;
                        svc.BadgeLabel.Text = "[ RUNNING ]";
                        svc.BadgeLabel.ForeColor = Color.DarkGreen;
                        svc.InfoLabel.Text = string.Format("PID: {0} | Uptime: {1:D2}:{2:D2}:{3:D2} | Respawns: {4}",
                            svc.Proc.Id, (int)up.TotalHours, up.Minutes, up.Seconds, svc.RespawnCount);
                    }
                }

                if (statusInstancesLabel != null)
                {
                    statusInstancesLabel.Text = string.Format("Instances: {0} active, {1} modules", activeCount, services.Count - activeCount);
                }
            };
            watchdogTimer.Start();
        }

        private void OnProcessLog(PyService svc, string line, bool isErr)
        {
            if (svc.Name == "main.py")
            {
                if (line.Contains("POST /") || line.Contains("GET /") || line.Contains("Uvicorn running"))
                {
                    AppendLog("[API] " + line, Color.FromArgb(160, 160, 160));
                }
                return;
            }

            Color c = Color.Gainsboro;
            if (line.Contains("[USER -> IN"))
                c = Color.LightSkyBlue;
            else if (line.Contains("[BOT -> OUT]"))
                c = Color.LightGreen;
            else if (line.Contains("[SYS]"))
                c = Color.Khaki;
            else if (isErr || line.Contains("Error") || line.Contains("error"))
                c = Color.Salmon;

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
                AppendLog("[GUARDIAN] Window close blocked. Instances are protected.", Color.Khaki);
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
