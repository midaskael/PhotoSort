# PhotoSort - macOS 照片整理与去重系统

[English](README.md)

工业级照片/视频整理工具，支持 10 万+ 文件批量处理。

## 你是否遇到过这些问题？

📱 **手机换了好几部**，照片散落在各个备份文件夹里，不知道哪些是重复的？

💻 **iCloud、Google Photos、本地硬盘** 都有照片，想合并但怕弄丢或重复？

📁 **照片命名乱七八糟**，IMG_0001、IMG_0002... 完全不知道是什么时候拍的？

🎞️ **Live Photo 导出后变成两个文件**（HEIC + MOV），整理时总是对不上号？

⏰ **想按拍摄时间整理**，但手动一个个改文件夹要改到天荒地老？

---

**PhotoSort 就是为解决这些问题而生的！**

只需一行命令，即可将散落各处的照片自动整理到 `2024/01/`、`2024/02/` 这样的目录，自动去重，Live Photo 自动配对，原有的 iOS 编辑记录也不会丢失。

## 功能特性

- ✅ **按拍摄时间归档**：自动读取 EXIF 信息，按 `YYYY/MM/` 目录结构整理
- ✅ **智能去重**：基于文件大小 + MD5 的高效去重（支持大文件尾部采样 + 二次确认）
- ✅ **Live Photo 支持**：HEIC/JPG + MOV 配对跟随移动
- ✅ **AAE Sidecar 跟随**：iOS 编辑信息文件自动跟随主文件
- ✅ **断点续跑**：SQLite 记录处理状态，中断后可继续
- ✅ **运行报告**：每次运行生成详细 CSV/JSON 报告
- ✅ **并行处理**：多线程 Hash 计算，提升大文件处理速度
- ✅ **未识别文件处理**：自动移动到二次确认目录

## 工作流程

```
┌─────────────┐
│   待整理    │  (源目录)
└─────┬───────┘
      │ ./start.sh run
      ▼
┌─────────────────────────────────────┐
│         PhotoSort 自动整理           │
├─────────────┬───────────┬───────────┤
│ 已识别+新   │ 已识别+重复│ 未识别    │
└─────┬───────┴─────┬─────┴─────┬─────┘
      ▼             ▼           ▼
┌───────────┐  ┌─────────┐  ┌─────────┐
│ 照片整理  │  │ 待删除  │  │二次确认 │
│ YYYY/MM/  │  │         │  │         │
└───────────┘  └────┬────┘  └────┬────┘
                    │            │
                    ▼            ▼
              ┌─────────────────────┐
              │     人工确认后删除   │
              └─────────────────────┘
```

**三步走：**
1. **自动整理** — `./start.sh run -s <源目录>`
2. **二次确认** — 人工检查 `待删除/` 和 `二次确认/` 目录
3. **手动删除** — 确认无误后删除

## 环境要求

> [!NOTE]
> 本程序仅在 **macOS 26** 上测试通过，其他版本请自行验证。

- macOS
- Python 3.9+
- ExifTool

### 安装依赖

```bash
# 安装 Homebrew（如未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python 3
brew install python

# 安装 ExifTool
brew install exiftool
```

## 快速开始

```bash
cd /path/to/PhotoSort

# 1. 初始化环境
./start.sh init

# 2. 编辑配置文件
vim config.yaml

# 3. 建立 MD5 索引（首次运行必须）
./start.sh build-index

# 4. 预演模式（不实际移动文件）
./start.sh dry-run                    # 使用 config.yaml 中的 source
./start.sh dry-run -s /path/to/photos # 或通过 -s 指定源目录

# 5. 正式运行
./start.sh run                        # 使用 config.yaml 中的 source
./start.sh run -s /path/to/photos     # 或通过 -s 指定源目录
```

## 使用方法

### 启动脚本

```bash
./start.sh <命令> [--source <目录>]

命令:
  init          初始化环境（创建虚拟环境、安装依赖）
  run           运行照片整理（正常模式）
  dry-run       预演模式（只显示操作，不移动文件）
  build-index   仅建立目标目录的 MD5 索引
  status        显示当前状态和统计
  help          显示帮助信息

选项:
  --source, -s  指定源目录（覆盖 config.yaml 中的 source）
```

### 示例

```bash
# 使用配置文件中的默认源目录
./start.sh run

# 指定源目录（覆盖配置文件）
./start.sh run --source /Users/xxx/Photos/2024

# 预演指定目录
./start.sh dry-run -s ~/Pictures/新照片
```

### 查看运行状态

```bash
./start.sh status
```

## 辅助工具

### check_files.py - 检查并移动文件

将目录中的文件移动到二次确认目录：

```bash
python check_files.py /path/to/directory --dry-run  # 预览
python check_files.py /path/to/directory            # 执行
```

## 报告文件

运行完成后，报告保存在 `<dest>/.photox/reports/run-XXXXXX/`：

| 文件 | 说明 |
|------|------|
| `summary.json` | 运行汇总统计 |
| `moved.csv` | 归档文件明细 |
| `duplicate.csv` | 重复文件明细 |
| `dest_duplicate.csv` | 建库时发现的重复文件 |
| `error.csv` | 错误明细 |
| `orphan_aae.csv` | 孤立 AAE 明细 |

## 项目结构

```
PhotoSort/
├── .venv/                     # Python 虚拟环境
├── photo_organizer/           # 主模块
│   ├── config.py              # 配置管理
│   ├── database.py            # SQLite 操作
│   ├── exif.py                # EXIF 时间提取
│   ├── hasher.py              # Hash 计算（并行）
│   ├── media.py               # 文件扫描与绑定
│   ├── organizer.py           # 核心整理逻辑
│   ├── report.py              # 报告生成
│   └── utils.py               # 工具函数
├── main.py                    # Python 入口
├── start.sh                   # 启动脚本
├── check_files.py             # 文件检查移动工具
├── config.yaml                # 你的配置
├── config.example.yaml        # 配置示例
└── requirements.txt           # Python 依赖
```

## 目录结构

```
Photo/
├── 待整理/              # 源目录（可通过 --source 指定）
├── 照片整理/            # 归档目录
│   ├── .photox/         # 数据目录
│   │   ├── photo_md5.sqlite3   # MD5 数据库
│   │   ├── run_history.json    # 运行历史
│   │   └── reports/            # 报告目录
│   ├── 2024/            # 归档照片
│   ├── 2025/
│   └── ...
├── 待删除/              # 重复文件（待人工确认后删除）
│   └── AAE_孤立/        # 孤立 AAE 文件
└── 二次确认/            # 未识别文件（待人工确认）
```

## 配置说明

### 路径配置

| 配置项 | 说明 |
|--------|------|
| `source` | 默认源目录，可通过 `--source` 覆盖 |
| `dest` | 归档目标目录 |
| `data_dir` | 数据目录（默认 `<dest>/.photox`） |
| `dup_dir` | 重复文件目录（默认 `<dest>/待删除`） |
| `orphan_aae_dir` | 孤立 AAE 目录 |
| `second_check_dir` | 二次确认目录（未识别文件） |

### 性能配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `exiftool_chunk_size` | 800 | ExifTool 批量处理大小 |
| `hash_workers` | 4 | 并行 Hash 线程数 |
| `hash_threshold_mb` | 10 | 大于此值使用尾部采样 |

## 注意事项

1. **首次运行务必使用 `--dry-run`**，确认行为正确
2. **重复文件不会直接删除**，移动到 `待删除/` 目录后请人工确认再清理
3. **未识别文件会移到 `二次确认/`**，请人工检查处理
4. **定期备份数据库**（`.photox/photo_md5.sqlite3`）
5. 运行期间避免其他程序修改源目录

## License

MIT
