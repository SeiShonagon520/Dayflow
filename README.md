# Dayflow for Windows

智能时间追踪与生产力分析工具 - Windows 原生版本

## 功能特性

- **后台低功耗录屏** - 1 FPS 极低功耗屏幕录制
- **云端智能分析** - 通过 Dayflow API 进行视频转录与活动识别
- **时间轴展示** - 直观的活动时间轴，了解每日时间分配
- **生产力评估** - AI 驱动的生产力分析与建议

## 系统要求

- Windows 10/11 (64-bit)
- Python 3.10+
- FFmpeg (用于视频编码)

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/Dayflow.git
cd Dayflow
```

### 2. 创建虚拟环境

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 FFmpeg

下载 FFmpeg 并添加到系统 PATH:
- https://ffmpeg.org/download.html

## 运行

```bash
python main.py
```

## 使用说明

1. **配置 API Token**
   - 首次启动后，进入「设置」页面
   - 输入您的 Dayflow API Token
   - 点击「保存」

2. **开始录制**
   - 点击侧边栏的「开始录制」按钮
   - 程序将在后台以 1 FPS 录制屏幕
   - 每 60 秒自动保存一个视频切片

3. **查看时间轴**
   - 录制的视频会自动上传分析
   - 分析结果将显示在时间轴页面
   - 点击卡片可查看详情

4. **最小化到托盘**
   - 关闭窗口时，程序会最小化到系统托盘
   - 双击托盘图标可重新打开窗口
   - 右键托盘图标可控制录制或退出

## 项目结构

```
Dayflow/
├── main.py                # 启动入口
├── config.py              # 配置文件
├── requirements.txt       # Python 依赖
├── core/
│   ├── types.py           # 数据模型定义
│   ├── recorder.py        # 屏幕录制模块 (dxcam)
│   ├── llm_provider.py    # API 交互层
│   └── analysis.py        # 分析调度器
├── database/
│   ├── schema.sql         # 数据库结构
│   └── storage.py         # SQLite 存储管理
└── ui/
    ├── main_window.py     # 主窗口
    └── timeline_view.py   # 时间轴组件
```

## 数据存储

应用数据存储在 `%LOCALAPPDATA%\Dayflow\` 目录:

- `dayflow.db` - SQLite 数据库
- `chunks/` - 视频切片文件
- `dayflow.log` - 日志文件

## 技术栈

- **GUI**: PySide6 (Qt for Python)
- **录屏**: dxcam (DirectX 高性能截图)
- **视频编码**: OpenCV + FFmpeg
- **网络**: httpx (异步 HTTP/2)
- **数据库**: SQLite

## 配置选项

环境变量:

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DAYFLOW_API_URL` | API 服务地址 | `https://api.dayflow.app` |
| `DAYFLOW_API_TOKEN` | API 认证令牌 | (空) |

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行
python main.py
```

## 许可证

MIT License
