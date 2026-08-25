using System;
using System.IO;
using System.Threading.Tasks;

namespace Slicer
{
    /// <summary>
    /// 演示如何从 C# 调用 slicer.exe 完成 STL 切片。
    /// 用法：
    ///   dotnet run -- <slicerExe路径> <STL路径> <输出ZIP路径>
    /// 例如：
    ///   dotnet run -- "D:\CodeFiles\Python_work\slicingTest\dist\slicer\slicer.exe" "D:\CodeFiles\Python_work\slicingTest\model.STL" "D:\temp\slices.zip"
    /// </summary>
    internal static class Program
    {
        private static async Task<int> Main(string[] args)
        {
            var slicerExe = args.Length > 0
                ? args[0]
                : @"D:\CodeFiles\Python_work\slicingTest\dist\slicer\slicer.exe";
            var stlPath = args.Length > 1
                ? args[1]
                : @"D:\CodeFiles\Python_work\slicingTest\model.STL";
            var outZip = args.Length > 2
                ? args[2]
                : Path.Combine(Path.GetTempPath(), "slices_demo.zip");

            var client = new SlicerClient(slicerExe);
            var options = new SlicerOptions
            {
                MeshPath = stlPath,
                LayerHeight = 0.1,
                Dpi = 400,
                Mode = "shell",
                ShellWidthMm = 1.0,
                BaseSaturation = 128,
                FirstLayerOffset = 0.5,
                ImageFormat = "TIFF",
                OutputZip = outZip,
            };

            Console.WriteLine("开始切片...");
            Console.WriteLine("命令行: " + options.BuildArguments());

            var result = await client.SliceAsync(options);
            if (result.Success)
            {
                Console.WriteLine($"切片成功！层数={result.LayerCount}，输出={result.OutputZip}");
                Console.WriteLine("--- 日志末尾 ---");
                foreach (var line in result.StandardOutput.Split('\n'))
                {
                    var t = line.TrimEnd('\r');
                    if (t.Length > 0) Console.WriteLine(t);
                }
                return 0;
            }

            Console.WriteLine($"切片失败：{result.ErrorMessage}");
            Console.WriteLine("--- stderr ---");
            Console.WriteLine(result.StandardError);
            return 1;
        }
    }
}


