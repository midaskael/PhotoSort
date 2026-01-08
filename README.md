# PhotoSort - Photo Organization & Deduplication System

[中文文档](README.zh-CN.md)

An industrial-grade photo/video organization tool for macOS, capable of batch processing 100,000+ files.

## Common Problems This Solves

📱 **Switched phones multiple times** and have photos scattered across various backup folders with no idea which are duplicates?

💻 **Photos on iCloud, Google Photos, and local drives** that you want to merge without losing any or creating duplicates?

📁 **Messy file names** like IMG_0001, IMG_0002... with no clue when they were actually taken?

🎞️ **Live Photos exported as two files** (HEIC + MOV) that are hard to keep together when organizing?

⏰ **Want to organize by date taken** but manually moving files into folders would take forever?

---

**PhotoSort solves all of these!**

With a single command, it automatically organizes scattered photos into dated folders like `2024/01/`, `2024/02/`, removes duplicates, pairs Live Photos, and preserves iOS editing history.

## Features

- ✅ **Time-based Archiving**: Automatically reads EXIF data and organizes files into `YYYY/MM/` directory structure
- ✅ **Smart Deduplication**: Efficient MD5-based deduplication with large file tail sampling and two-phase verification
- ✅ **Live Photo Support**: HEIC/JPG + MOV pairing, moves together
- ✅ **AAE Sidecar Following**: iOS editing files automatically follow master files
- ✅ **Resumable Processing**: SQLite-based state tracking, can resume after interruption
- ✅ **Detailed Reports**: Generates CSV/JSON reports for each run
- ✅ **Parallel Processing**: Multi-threaded hash computation for faster large file processing
- ✅ **Unrecognized File Handling**: Automatically moves to second-check directory

## Workflow

```
┌─────────────┐
│   Source    │  (unsorted photos)
└─────┬───────┘
      │ ./start.sh run
      ▼
┌─────────────────────────────────────┐
│         PhotoSort Processing         │
├─────────────┬───────────┬───────────┤
│ New Files   │ Duplicates │Unrecognized│
└─────┬───────┴─────┬─────┴─────┬─────┘
      ▼             ▼           ▼
┌───────────┐  ┌─────────┐  ┌─────────┐
│  Archive  │  │ Pending │  │ Second  │
│ YYYY/MM/  │  │ Delete  │  │ Check   │
└───────────┘  └────┬────┘  └────┬────┘
                    │            │
                    ▼            ▼
              ┌─────────────────────┐
              │   Manual Deletion    │
              └─────────────────────┘
```

**Three Steps:**
1. **Auto Sort** — `./start.sh run -s <source_dir>`
2. **Manual Review** — Check `Pending Delete/` and `Second Check/` directories
3. **Manual Delete** — Delete after confirmation

## Requirements

- macOS
- Python 3.9+
- ExifTool (`brew install exiftool`)

## Quick Start

```bash
cd /path/to/PhotoSort

# 1. Initialize environment
./start.sh init

# 2. Edit configuration
vim config.yaml

# 3. Build MD5 index (required for first run)
./start.sh build-index

# 4. Dry-run mode (no actual file moves)
./start.sh dry-run

# 5. Run for real
./start.sh run
```

## Usage

### Start Script

```bash
./start.sh <command> [--source <directory>]

Commands:
  init          Initialize environment (create venv, install dependencies)
  run           Run photo organization (normal mode)
  dry-run       Dry-run mode (show operations, don't move files)
  build-index   Only build MD5 index for destination directory
  status        Show current status and statistics
  help          Show help

Options:
  --source, -s  Specify source directory (overrides config.yaml)
```

### Examples

```bash
# Use default source from config
./start.sh run

# Specify source directory
./start.sh run --source /Users/xxx/Photos/2024

# Dry-run with specific directory
./start.sh dry-run -s ~/Pictures/NewPhotos
```

## Configuration

### Path Configuration

| Option | Description |
|--------|-------------|
| `source` | Default source directory (can be overridden with `--source`) |
| `dest` | Archive destination directory |
| `data_dir` | Data directory (default: `<dest>/.photox`) |
| `dup_dir` | Duplicate files directory |
| `orphan_aae_dir` | Orphan AAE directory |
| `second_check_dir` | Unrecognized files directory |

### Performance Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `exiftool_chunk_size` | 800 | ExifTool batch processing size |
| `hash_workers` | 4 | Parallel hash computation threads |
| `hash_threshold_mb` | 10 | Files larger than this use tail sampling |

## Project Structure

```
PhotoSort/
├── .venv/                     # Python virtual environment
├── photo_organizer/           # Main module
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite operations
│   ├── exif.py                # EXIF time extraction
│   ├── hasher.py              # Hash computation (parallel)
│   ├── media.py               # File scanning and binding
│   ├── organizer.py           # Core organization logic
│   ├── report.py              # Report generation
│   └── utils.py               # Utility functions
├── main.py                    # Python entry point
├── start.sh                   # Start script
├── check_files.py             # File check/move utility
├── config.yaml                # Your configuration
├── config.example.yaml        # Configuration example
└── requirements.txt           # Python dependencies
```

## Notes

1. **Always use `--dry-run` first** to confirm behavior
2. **Duplicates are not deleted** — moved to `Pending Delete/` for manual review
3. **Unrecognized files** are moved to `Second Check/` for manual handling
4. **Back up your database** regularly (`.photox/photo_md5.sqlite3`)
5. Don't modify source directory while processing

## License

MIT
