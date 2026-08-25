using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Slicer
{
    /// <summary>
    /// 切片参数（对应 slicer.exe 的命令行参数）。
    /// 参数映射：
    ///   MeshPath          -> 位置参数 mesh
    ///   LayerHeight       -> --height
    ///   Dpi               -> --dpi
    ///   Mode              -> --mode {binary,shell}
    ///   ShellWidthMm      -> --shell-width （仅 shell 模式）
    ///   BaseSaturation    -> --base-sat   （仅 shell 模式）
    ///   FirstLayerOffset  -> --offset
    ///   ImageFormat       -> --format {PNG,TIFF,BMP,JPEG}
    ///   OutputZip         -> --zip
    /// </summary>
    public sealed class SlicerOptions
    {
        public string MeshPath { get; set; } = "";            // 模型文件路径（必填）
        public double LayerHeight { get; set; } = 0.1;        // 层高，单位 mm
        public int Dpi { get; set; } = 400;                   // 输出 DPI
        public string Mode { get; set; } = "shell";           // binary 或 shell
        public double ShellWidthMm { get; set; } = 1.0;       // 壳体边缘宽度，单位 mm
        public int BaseSaturation { get; set; } = 128;        // 内部饱和度灰度 0~255
        public double FirstLayerOffset { get; set; } = 0.5;   // 第一层高度偏移（层高倍数）
        public string ImageFormat { get; set; } = "TIFF";     // PNG / TIFF / BMP / JPEG
        public string OutputZip { get; set; } = "slices.zip"; // 输出 ZIP 路径

        /// <summary>构造命令行参数字符串（小数用不变量格式，避免中文系统逗号问题）</summary>
        public string BuildArguments()
        {
            var inv = CultureInfo.InvariantCulture;
            var a = new StringBuilder();
            a.Append(Quote(MeshPath));
            a.Append(" --height ").Append(LayerHeight.ToString("0.####", inv));
            a.Append(" --dpi ").Append(Dpi);
            a.Append(" --mode ").Append(Mode);
            if (Mode.Equals("shell", StringComparison.OrdinalIgnoreCase))
            {
                a.Append(" --shell-width ").Append(ShellWidthMm.ToString("0.####", inv));
                a.Append(" --base-sat ").Append(BaseSaturation);
            }
            a.Append(" --offset ").Append(FirstLayerOffset.ToString("0.####", inv));
            a.Append(" --format ").Append(ImageFormat);
            a.Append(" --zip ").Append(Quote(OutputZip));
            return a.ToString();
        }

        private static string Quote(string s)
        {
            // 简单路径加双引号；若路径本身含双引号则先转义
            return "\"" + s.Replace("\"", "\\\"") + "\"";
        }
    }

    /// <summary>切片执行结果</summary>
    public sealed class SlicerResult
    {
        public bool Success { get; set; }
        public int ExitCode { get; set; }
        public int LayerCount { get; set; }
        public string OutputZip { get; set; } = "";
        public string StandardOutput { get; set; } = "";
        public string StandardError { get; set; } = "";
        public string ErrorMessage { get; set; } = "";
    }

    /// <summary>
    /// slicer.exe 子进程调用封装。
    /// 要求：.NET 5.0+（使用 WaitForExitAsync / Kill(entireProcessTree)）。
    /// 使用方式：
    ///   var client = new SlicerClient(@"D:\tools\slicer\slicer.exe");
    ///   var result = await client.SliceAsync(options);
    /// </summary>
    public sealed class SlicerClient
    {
        private readonly string _exePath;

        public SlicerClient(string slicerExePath)
        {
            if (string.IsNullOrWhiteSpace(slicerExePath))
                throw new ArgumentNullException(nameof(slicerExePath));
            if (!File.Exists(slicerExePath))
                throw new FileNotFoundException("找不到 slicer.exe", slicerExePath);
            _exePath = Path.GetFullPath(slicerExePath);
        }

        /// <summary>
        /// 执行切片。默认超时 10 分钟，可用 timeout 调整；ct 用于主动取消。
        /// </summary>
        public async Task<SlicerResult> SliceAsync(
            SlicerOptions options,
            TimeSpan? timeout = null,
            CancellationToken ct = default)
        {
            if (options == null) throw new ArgumentNullException(nameof(options));
            timeout ??= TimeSpan.FromMinutes(10);

            var psi = new ProcessStartInfo
            {
                FileName = _exePath,
                Arguments = options.BuildArguments(),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetDirectoryName(_exePath) ?? Environment.CurrentDirectory,
            };

            // 关键：强制 Python 输出 UTF-8，避免中文日志在 C# 侧乱码
            psi.Environment["PYTHONIOENCODING"] = "utf-8";
            psi.Environment["PYTHONUNBUFFERED"] = "1";
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            psi.StandardErrorEncoding = new UTF8Encoding(false);

            var stdout = new StringBuilder();
            var stderr = new StringBuilder();
            var result = new SlicerResult();

            using var proc = new Process { StartInfo = psi };
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
            proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };

            if (!proc.Start())
            {
                result.Success = false;
                result.ErrorMessage = "无法启动 slicer.exe";
                return result;
            }
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
            linked.CancelAfter(timeout.Value);
            try
            {
                await proc.WaitForExitAsync(linked.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                KillProcessTree(proc.Id);
                result.Success = false;
                result.ErrorMessage = $"切片超时（超过 {timeout.Value.TotalSeconds:0} 秒）";
                return result;
            }
            catch (OperationCanceledException)
            {
                KillProcessTree(proc.Id);
                result.Success = false;
                result.ErrorMessage = "切片已取消";
                return result;
            }

            // 确保异步输出读完整
            proc.WaitForExit();

            result.StandardOutput = stdout.ToString();
            result.StandardError = stderr.ToString();
            result.ExitCode = proc.ExitCode;

            // 解析成功标记：demo1.py 成功时输出 SLICE_OK layers=N zip=xxx
            var m = Regex.Match(result.StandardOutput,
                @"SLICE_OK\s+layers=(\d+)\s+zip=(\S+)", RegexOptions.Multiline);
            if (m.Success)
            {
                result.Success = true;
                result.LayerCount = int.Parse(m.Groups[1].Value);
                result.OutputZip = m.Groups[2].Value.Trim();
            }
            else if (proc.ExitCode == 0 && File.Exists(options.OutputZip))
            {
                // 兜底：无 SLICE_OK 标记的旧版本 exe
                result.Success = true;
            }

            if (!result.Success)
            {
                result.ErrorMessage = stderr.ToString().Trim();
                if (string.IsNullOrEmpty(result.ErrorMessage))
                    result.ErrorMessage = $"切片失败（退出码 {proc.ExitCode}）";
            }
            return result;
        }

        /// <summary>
        /// 杀掉整个进程树（PyInstaller onefile 是 bootloader + 实际运行子进程，必须连子进程一起杀）。
        /// </summary>
        private static void KillProcessTree(int pid)
        {
            try
            {
                using var p = Process.Start(new ProcessStartInfo
                {
                    FileName = "taskkill",
                    Arguments = $"/PID {pid} /T /F",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                });
                p?.WaitForExit(5000);
            }
            catch { /* 忽略清理失败 */ }
        }
    }
}
