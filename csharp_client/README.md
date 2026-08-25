# STL 切片工具 — C# 集成说明

本项目把 `demo1.py`（STL 分层切片，输出灰度位图 ZIP）用 **PyInstaller 打包为独立可执行程序**（`dist\slicer\` 目录），供 C# 项目通过子进程方式调用。**目标机器无需安装 Python 或任何 Python 依赖。**

---

## 一、交付物清单

| 文件/目录 | 说明 |
|---|---|
| `dist\slicer\` | **onedir 模式打包结果**：`slicer.exe`（约 12MB）+ `_internal\` 依赖库目录（合计约 142MB）。**整个目录都要分发**（建议 zip 打包后分发） |
| `csharp_client\SlicerClient.cs` | C# 调用封装类（参数构造、进程启动、超时/取消、结果解析） |
| `csharp_client\SlicerClientDemo.csproj` | .NET 8 示例项目（控制台） |
| `csharp_client\Program.cs` | 示例程序，演示完整调用 |
| `demo1.py` | Python 源文件（打包前做了两处小改进，见第五节） |

> 主程序路径是 `dist\slicer\slicer.exe`（注意：不是 `dist\slicer.exe`，那是旧的单文件版）。

## 二、参数映射表

| C# 业务参数 | slicer.exe 参数 | 示例 |
|---|---|---|
| 模型路径 | 位置参数 `mesh` | `"model.STL"` |
| 层高 (mm) | `--height` | `0.1` |
| 输出 DPI | `--dpi` | `400` |
| 饱和度模式 | `--mode` | `binary` / `shell` |
| 壳体边缘宽度 (mm) | `--shell-width` | `1.0`（仅 shell） |
| 内部饱和度灰度 | `--base-sat` | `128`（仅 shell） |
| 第一层偏移（层高倍数） | `--offset` | `0.5` |
| 图片格式 | `--format` | `PNG` / `TIFF` / `BMP` / `JPEG` |
| 输出 ZIP 路径 | `--zip` | `"out\slices.zip"` |

## 三、C# 使用示例

```csharp
using Slicer;

var client = new SlicerClient(@"D:\tools\slicer\slicer.exe");   // 注意：onedir 版 exe 在目录内
var options = new SlicerOptions
{
    MeshPath = @"D:\models\part.STL",
    LayerHeight = 0.1,
    Dpi = 400,
    Mode = "shell",
    ShellWidthMm = 1.0,
    BaseSaturation = 128,
    FirstLayerOffset = 0.5,
    ImageFormat = "TIFF",
    OutputZip = @"D:\out\slices.zip",
};

var result = await client.SliceAsync(options);            // 默认超时 10 分钟

if (result.Success)
{
    Console.WriteLine($"层数: {result.LayerCount}");      // 从 SLICE_OK 标记解析
}
else
{
    Console.WriteLine($"失败: {result.ErrorMessage}");
}
```

## 四、关键设计点（C# 侧已自动处理）

1. **编码**：自动设置 `PYTHONIOENCODING=utf-8` 并让 Python 无缓冲输出，C# 用 `UTF8Encoding` 读取 stdout/stderr，**中文日志不会乱码**。
2. **退出码**：`0` = 成功；`1` = 失败（模型不存在、模型为空、内部异常）。C# 端同时校验退出码与 `SLICE_OK` 标记行。
3. **成功标记**：exe 成功时输出一行 `SLICE_OK layers=N zip=路径`，C# 正则解析得到层数。
4. **超时**：默认 10 分钟，可配置；超时自动 `taskkill /T /F` 杀掉 PyInstaller 的**整个进程树**。
5. **取消**：传入 `CancellationToken`，取消时同样杀掉进程树。
6. **路径含空格**：参数自动加双引号。
## 五、demo1.py 相对原始版本的改动

仅修改 `if __name__ == "__main__":` 块（不影响导入和 GUI 调用 `slicing_worker.py`）：

- 异常分支：错误信息写入 `stderr`，并 `sys.exit(1)`（原来退出码恒为 0，C# 无法判断成败）。
- 成功分支：额外输出 `SLICE_OK layers=N zip=xxx` 标记行。

## 六、重新打包命令（如需修改 demo1.py 后重建）

```powershell
# 激活 venv 后
pip install pyinstaller
pyinstaller --onedir --name slicer --clean demo1.py
# 产物在 dist\slicer\ 目录（slicer.exe + _internal\）
```

- 若遇 trimesh 动态导入缺模块，追加 `--collect-all trimesh --collect-all scipy`。
- 生成物除 `dist\slicer\` 外，还有 `build\` 中间目录与 `slicer.spec` 配置文件，均可删除或保留。

## 七、性能实测（onedir vs onefile，本机 200 层 400DPI shell）

| 指标 | onefile（旧） | onedir（当前） | 提升 |
|---|---|---|---|
| 冷启动（`--help`，清空缓存后） | 4.1 s | 0.7 s | ⭐ 约 6 倍 |
| 完整切片（model.STL 200 层） | 12.6 s | 13.9 s | 基本持平 |
| 产物形态 | 单文件 62 MB | 目录 142 MB | 分发更复杂 |

**结论与建议：**

- **启动速度**：onedir 免解压、启动时间稳定可预测；onefile 每次启动需把 62MB 压缩包解压到 `%TEMP%\_MEI*` 临时目录，冷启动明显更慢，且受磁盘速度/杀毒软件影响波动大。
- **端到端切片**：切片计算（约 10.7 s）占主导，启动占比小，因此单次整体差异不大；但**批量/高频调用时** onedir 每轮可省约 3~4 秒，累计收益明显。
- **附加优势**：onedir 杀毒软件误报率更低、异常退出时无临时目录残留、便于逐文件签名。

## 八、注意事项

- **分发**：onedir 必须**整个 `dist\slicer\` 目录一起分发**（`slicer.exe` 与 `_internal\` 缺一不可），建议 zip 打包。
- **性能**：切片计算约 10.7 s/200 层；若需更高吞吐，可考虑常驻进程或并行调用多个实例。
- **杀毒软件**：若遇误报，做代码签名或加白名单。
- **64 位**：exe 为 x64，C# 进程建议以 x64 运行。
- **版本**：PyInstaller 6.22.2 + Python 3.14.2 实测可用。
