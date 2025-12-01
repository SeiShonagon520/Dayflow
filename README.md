<div align="center">

# ⏱️ Dayflow for Windows

**智能时间追踪与生产力分析工具**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

*后台静默录屏 → AI 智能分析 → 可视化时间轴*

**中文** | [English](README_EN.md)

</div>

---

## 🎯 这是什么？

**Dayflow** 是一款基于 AI 的智能时间追踪工具。它在后台静默录制你的屏幕，通过视觉大模型自动识别你在做什么，然后生成一目了然的时间轴，帮你了解每天的时间都花在哪里了。

### 💡 为什么需要它？

- **不知道时间去哪了？** → Dayflow 自动记录，无需手动打卡
- **想提高工作效率？** → AI 分析你的工作模式，发现分心点
- **需要工作日志？** → 自动生成每日活动报告
- **远程办公考勤？** → 客观记录工作时长和内容

### 🏆 核心优势

| 优势 | 说明 |
|------|------|
| **零操作** | 开启即用，无需手动记录，AI 全自动识别 |
| **超低功耗** | 1 FPS 录制 + 智能压缩，CPU 占用 < 1% |
| **隐私优先** | 数据本地存储，视频分析后自动删除 |
| **智能分类** | AI 自动识别：工作/学习/娱乐/社交/休息 |
| **生产力评分** | 每段活动的效率打分，量化你的专注度 |

---

## ✨ 功能特性

| 功能 | 描述 |
|------|------|
| 🎥 **低功耗录屏** | 1 FPS 极低资源占用，后台静默运行 |
| 🤖 **AI 智能分析** | 视觉大模型识别屏幕活动，自动归类 |
| 📊 **时间轴可视化** | 直观展示每日时间分配，一目了然 |
| 💡 **生产力洞察** | AI 驱动的效率评估与改进建议 |
| 🔒 **隐私安全** | 数据本地存储，分析后自动清理视频 |

### 🆕 最新功能

| 功能 | 描述 |
|------|------|
| 📅 **日期切换** | 查看历史记录，支持前一天/后一天/今天快捷切换 |
| 📥 **CSV 导出** | 一键导出活动数据为 CSV 文件，便于分析和存档 |
| ⏸️ **暂停录制** | 处理隐私内容时可暂停，完成后继续录制 |
| 📊 **时间分布图** | 直观的柱状图展示各类别时间占比 |
| 🎨 **主题切换** | IDE 风格暗色/亮色主题，自动保存偏好 |
| 🔽 **最小化托盘** | 关闭窗口最小化到系统托盘，后台继续运行 |
| 📦 **EXE 打包** | 支持打包为独立可执行文件，无需 Python 环境 |
| ⭐ **GitHub 链接** | 侧边栏一键跳转项目主页 |

---

## 🖥️ 界面预览

### 主界面布局

```
┌─────────────────────────────────────────────────────────┐
│  Dayflow                                    ─  □  ✕    │
├────────┬────────────────────────────────────────────────┤
│        │                                                │
│   📊   │    ┌─────────────────────────────────────┐    │
│ 时间轴  │    │  09:00 - 10:30  ⚡ 85%              │    │
│        │    │  📁 工作 · VS Code 开发              │    │
│   ⚙️   │    │  Python 项目开发，编写核心模块       │    │
│  设置   │    └─────────────────────────────────────┘    │
│        │    ┌─────────────────────────────────────┐    │
│   ▶️   │    │  10:30 - 11:00  ⚡ 45%              │    │
│ 开始录制 │    │  🎮 娱乐 · Chrome 浏览器            │    │
│        │    │  浏览社交媒体，观看视频              │    │
│        │    └─────────────────────────────────────┘    │
│        │                                                │
└────────┴────────────────────────────────────────────────┘
```

### 界面说明

| 区域 | 功能 |
|------|------|
| **左侧边栏** | 导航菜单：时间轴、设置、录制控制 |
| **时间轴页面** | 显示今日所有活动卡片，按时间排序 |
| **活动卡片** | 显示时间段、类别、应用、摘要、生产力评分 |
| **设置页面** | 配置 API Key、测试连接、录制参数 |
| **系统托盘** | 最小化后在托盘运行，右键菜单控制 |

### 活动卡片详解

每张卡片包含：
- ⏰ **时间范围** - 活动的开始和结束时间
- 📁 **活动类别** - 工作/学习/编程/会议/娱乐/社交/休息
- 💻 **应用程序** - 使用的主要软件
- 📝 **活动摘要** - AI 生成的活动描述
- ⚡ **生产力评分** - 0-100% 的效率评估

---

## 🚀 快速开始

### 环境要求

- Windows 10/11 (64-bit)
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) (添加到系统 PATH)

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/yourusername/Dayflow.git
cd Dayflow

# 2. 创建 Conda 环境（推荐）
conda create -n dayflow python=3.11 -y
conda activate dayflow

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动应用
python main.py
```

### 打包为 EXE（可选）

如果想分发给其他人使用，无需安装 Python：

```bash
# 安装打包工具
pip install pyinstaller

# 运行打包脚本
python build.py

# 或直接双击 build.bat
```

打包完成后，`dist/Dayflow/` 目录可以直接复制给其他人使用。

---

## 📖 使用指南

### 1️⃣ 配置 API Key

1. 打开应用，点击左侧 **⚙️ 设置**
2. 输入你的心流 API Key
3. 点击 **测试连接** 验证
4. 点击 **保存**

> 💡 API 地址：`https://apis.iflow.cn/v1`

### 2️⃣ 开始录制

1. 点击 **▶ 开始录制**
2. 程序在后台以 1 FPS 静默录屏
3. 每 60 秒生成一个视频切片
4. 自动发送到云端 AI 分析

### 3️⃣ 查看时间轴

- 分析结果自动显示在首页时间轴
- 每张卡片代表一段活动时间
- 包含：活动类别、应用程序、生产力评分

### 4️⃣ 系统托盘

- 关闭窗口 → 最小化到托盘继续运行
- 双击托盘图标 → 打开主窗口
- 右键托盘 → 控制录制/退出

---

## 📁 项目结构

```
Dayflow/
├── 📄 main.py              # 启动入口
├── ⚙️ config.py            # 配置文件
├── 📦 requirements.txt     # 依赖清单
├── 🔨 build.py             # EXE 打包脚本
├── 🔨 build.bat            # 一键打包批处理
│
├── 🧠 core/                # 核心逻辑
│   ├── types.py            # 数据模型
│   ├── recorder.py         # 屏幕录制 (dxcam)
│   ├── llm_provider.py     # AI API 交互
│   └── analysis.py         # 分析调度器
│
├── 💾 database/            # 数据层
│   ├── schema.sql          # 表结构定义
│   └── storage.py          # SQLite 管理
│
├── 🎨 ui/                  # 界面层
│   ├── main_window.py      # 主窗口
│   ├── timeline_view.py    # 时间轴组件
│   └── themes.py           # 主题管理
│
└── 🖼️ assets/              # 资源文件
    └── icon.ico            # 应用图标
```

---

## ⚙️ 配置选项

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DAYFLOW_API_URL` | API 地址 | `https://apis.iflow.cn/v1` |
| `DAYFLOW_API_KEY` | API 密钥 | (空) |
| `DAYFLOW_API_MODEL` | AI 模型 | `qwen3-vl-plus` |

### 数据目录

```
%LOCALAPPDATA%\Dayflow\
├── dayflow.db      # 数据库
├── chunks/         # 视频切片（分析后自动删除）
└── dayflow.log     # 运行日志
```

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | PySide6 (Qt6) |
| 屏幕捕获 | dxcam (DirectX) |
| 视频处理 | OpenCV |
| 网络请求 | httpx (HTTP/2) |
| 数据存储 | SQLite |
| AI 分析 | 心流 API (OpenAI 兼容) |

---

## 灵感来源

本项目灵感源于 [Dayflow (macOS)](https://github.com/JerryZLiu/Dayflow) 开源项目。由于原项目仅支持 macOS 系统，因此我基于相同理念开发了这个 Windows 版本，让更多用户能够体验 AI 驱动的智能时间追踪。

感谢原作者的创意和开源精神！�

---

## 📄 许可证

[MIT License](LICENSE) © 2024-2025

---

<div align="center">

**如果觉得有用，请给个 ⭐ Star！**

</div>
