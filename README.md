<div align="center">

# ⏱️ Dayflow for Windows

**AI 驱动的智能时间追踪与生产力分析工具**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

*后台静默录屏 → AI 智能分析 → 可视化时间轴*

[![Download](https://img.shields.io/badge/⬇️_下载安装包-EXE-brightgreen?style=for-the-badge)](https://github.com/SeiShonagon520/Dayflow/releases)

**中文** | [English](README_EN.md)

</div>

---

## 🎯 这是什么？

**Dayflow** 是一款面向 Windows 的 AI 时间追踪工具。它在后台低频记录你的屏幕与窗口信息，通过视觉模型分析你正在做什么，并生成清晰的时间轴、统计面板与日报，帮你更客观地理解时间都花在了哪里。

### 💡 适合谁？

- 想知道自己一天时间到底花在哪的人
- 想复盘专注时段、分心模式、工作节奏的人
- 需要自动活动记录、日报、周报素材的人
- 希望用更低打扰方式做时间追踪的人

### 🏆 核心优势

| 优势 | 说明 |
|------|------|
| **零操作** | 开启即用，无需手动打卡，AI 自动分析活动 |
| **超低功耗** | 1 FPS 录制 + 智能压缩，尽量降低后台占用 |
| **本地优先** | 原始录屏数据保留在本机，分析后自动清理切片 |
| **智能分类** | 自动识别工作 / 学习 / 娱乐 / 社交 / 休息等活动 |
| **可视化复盘** | 时间轴、统计页、Web 仪表盘多种方式查看结果 |

---

## 🔐 隐私说明（重要）

Dayflow 的设计原则是：**本地录制 + 云端分析 + 本地存储**。

### 你需要知道的 5 件事

1. **不会上传完整视频**  
   原始录屏切片保存在本地，不会整段上传到云端。

2. **仅发送有限关键帧用于分析**  
   程序会从切片中提取少量关键帧（README 当前说明为每个切片最多 8 帧）发送给你配置的视觉模型服务。

3. **分析结果保存在本地**  
   活动记录、设置项、统计数据保存在本地 SQLite 数据库中。

4. **录屏切片会自动清理**  
   分析完成后，临时视频切片会自动删除，避免长期占用磁盘。

5. **敏感内容可以手动暂停**  
   遇到密码、银行、隐私聊天等敏感场景时，可以随时点击暂停录制。

### 数据存储位置

```text
%LOCALAPPDATA%\Dayflow\
├── dayflow.db      # 活动记录、设置、统计数据
├── dayflow.log     # 运行日志
├── chunks\         # 临时视频切片（分析后自动删除）
└── updates\        # 更新文件缓存
```

> 💡 如果你对隐私非常敏感，建议先阅读本节，再决定是否开启持续录制。

---

## ✨ 主要功能

| 功能 | 描述 |
|------|------|
| 🎥 **低功耗录屏** | 1 FPS 低资源占用，后台静默运行 |
| 🖥️ **多显示器录制** | 支持全屏拼接录制，多屏场景全覆盖 |
| 🪟 **窗口追踪** | 使用 Windows API 采集真实应用名称和窗口标题 |
| 🤖 **AI 智能分析** | 视觉大模型识别屏幕活动，自动归类 |
| 📊 **时间轴可视化** | 直观展示每日时间分配，一目了然 |
| 📈 **统计面板** | 查看时间分布、效率趋势、周对比等数据 |
| 📋 **日报缓存** | 自动生成并缓存日报，支持历史浏览与导出 |
| 📊 **Web 仪表盘** | 导出精美 HTML 报告，支持交互式图表 |
| 📧 **邮件日报** | 自动生成并发送日报与深度分析内容 |
| 🔄 **自动更新** | 检查新版本、后台下载、一键安装 |
| 🚀 **开机自启动** | 开机自动运行并最小化到系统托盘 |
| 📥 **CSV 导出** | 一键导出活动数据，便于二次分析 |
| ⏸️ **智能暂停录制** | 手动暂停 + 空闲自动暂停，保护隐私与节省资源 |
| 🎨 **主题切换** | 支持暗色 / 亮色主题，自动保存偏好 |

### 🆕 最近更新亮点

#### v1.6.0 (2026-05)

- **多显示器全屏录制**：支持 `output_idx=-1` 全屏拼接模式，自动识别并合并所有显示器画面
- **空闲自动暂停录制**：基于 Windows GetLastInputInfo 检测键盘/鼠标空闲，超时可自动暂停录制，恢复活动时自动继续
- **日报缓存与浏览**：日报内容持久化到 SQLite，支持左侧日期列表快速浏览历史日报，一键复制/导出 Markdown
- **切片存储自定义**：支持自定义视频切片目录与 5GB 存储上限，避免磁盘爆盘
- 新增 `run.bat` 一键启动脚本

#### v1.5.2 (2026-03)

- 统计页面全新设计：指标卡片、环形图、趋势图、热力图、周对比
- 支持编辑 / 删除活动卡片
- 视觉细节优化，整体界面更精致

#### v1.5.0 (2025-12)

- 新增 Windows API 窗口追踪，识别更精准
- UI 全面优化：效率指示条、深度工作徽章、实时录制时长等
- AI 提示词与数据处理逻辑优化

---

## 🖥️ 界面预览

### 时间轴页面

![Dayflow 时间轴](assets/Dayflow_index.png)

*展示每日活动卡片，包含时间段、应用程序、活动摘要和生产力评分。*

### 统计页面

![Dayflow 统计](assets/Dayflow_Statistics.png)

*仪表盘风格设计，包含指标卡片、类别分布、趋势图、热力图、周对比等。*

### Web 仪表盘

#### 日期选择

![仪表盘日期选择](assets/Dayflow_Dashboard_Dialog.png)

*支持今日、昨日、本周、上周、本月、自定义日期范围。*

#### 仪表盘报告

![Web 仪表盘](assets/Dayflow_Dashboard_Report.png)

*导出后的 HTML 报告可在浏览器中查看，也可以直接分享。*

### 邮件日报

#### 设置界面

![邮件设置](assets/Dayflow_Email_Settings.png)

#### 报告示例

<div align="center">
<img src="assets/Dayflow_Email_Report_1.png" width="45%" alt="报告示例1"/>
<img src="assets/Dayflow_Email_Report_2.png" width="45%" alt="报告示例2"/>
</div>

#### 深度分析报告

![深度分析报告](assets/Dayflow_Email_DeepAnalysis.png)

### 自动更新 / 开机自启动

![自动更新](assets/Dayflow_AutoUpdate.png)

![开机自启动](assets/Dayflow_AutoStart.png)

---

## 🚀 快速开始

### 环境要求

- Windows 10 / 11 (64-bit)
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html)（加入系统 PATH）

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/SeiShonagon520/Dayflow.git
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

```bash
# 安装打包工具
pip install pyinstaller

# 运行打包脚本
python build.py

# 或直接双击 build.bat
```

打包完成后，`dist/Dayflow/` 目录可以直接复制给其他人使用。

### 一键启动（开发环境）

如果你已配置好 `dayflow` Conda 环境，可以直接双击项目根目录的 `run.bat`，无需手动 `activate`：

```bash
run.bat
```

或在终端中：

```bash
conda run -n dayflow python main.py
```

### 下载预编译版本

如果你只是想直接使用，不想自己配置 Python 环境：

1. 打开 [Releases](https://github.com/SeiShonagon520/Dayflow/releases)
2. 下载最新版本安装包或压缩包
3. 解压后运行 `Dayflow.exe`

> 💡 首次运行建议先完成 API 配置，再开始录制。

---

## 📖 使用指南

### 1️⃣ 配置 API

1. 打开应用，点击左侧 **⚙️ 设置**
2. 配置以下信息：
   - **API 地址**：OpenAI 兼容接口地址
   - **API Key**：你的 API 密钥
   - **模型名称**：需支持视觉的模型
3. 点击 **测试连接** 验证
4. 点击 **保存配置**

> 💡 支持任意 OpenAI 兼容接口：OpenAI、DeepSeek、心流 API、本地模型（Ollama）等。

### 2️⃣ 开始录制

1. 点击 **▶ 开始录制**
2. 程序在后台以 1 FPS 静默录屏
3. 每 60 秒生成一个视频切片
4. 自动发送关键帧到你配置的模型服务进行分析

### 3️⃣ 查看时间轴

- 分析结果自动显示在首页时间轴
- 每张卡片代表一段活动时间
- 包含活动类别、应用程序、活动摘要、生产力评分等信息

### 4️⃣ 日报浏览与导出（可选）

1. 点击左侧 **📋 日报**
2. 选择左侧日期列表中的某一天
3. 右侧即可查看已生成的日报内容
4. 点击 **复制** 或 **导出** 可保存为 Markdown 文件

> 💡 日报内容自动缓存到本地数据库，无需重复生成。

### 5️⃣ 邮件日报（可选）

1. 打开 **设置** → **邮件推送**
2. 填写 QQ 邮箱地址和授权码
3. 自定义发送时间（默认 12:00 和 22:00）
4. 点击 **保存配置**
5. 点击 **测试发送** 验证

> 💡 授权码获取：QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 → 生成授权码。

### 6️⃣ 多显示器录制设置（可选）

1. 打开 **设置** → **录制设置**
2. 将 **显示器编号** 设为 `-1` 即可启用全屏拼接模式
3. 程序会自动识别所有显示器并合并录制

### 7️⃣ 智能暂停录制

- **手动暂停**：点击主界面暂停按钮，随时暂停/恢复录制
- **空闲自动暂停**：在 **设置** → **录制设置** 中可开启。当检测到键盘/鼠标空闲超过设定阈值（默认 10 分钟），录制自动暂停；恢复操作时自动继续

### 8️⃣ 开机自启动（可选）

1. 打开 **设置** → **开机启动**
2. 点击按钮启用 / 禁用
3. 启用后开机自动运行并最小化到托盘

### 9️⃣ 检查更新（可选）

1. 打开 **设置** → **软件更新**
2. 点击 **检查更新**
3. 发现新版本后点击 **下载更新**
4. 下载完成后点击 **立即安装**

### 🔟 系统托盘

- 点击标题栏 ↓ 按钮 → 最小化到托盘
- 点击关闭 × → 询问退出或最小化
- 双击托盘图标 → 打开主窗口
- 右键托盘 → 控制录制 / 退出

---

## 📁 项目结构

```text
Dayflow/
├── main.py                 # 启动入口（支持 --minimized 参数）
├── config.py               # 配置文件（含版本号）
├── requirements.txt        # 依赖清单
├── build.py                # EXE 打包脚本
├── build.bat               # 一键打包批处理
├── run.bat                 # 开发环境一键启动（自动走 conda 环境）
├── updater.py              # 独立更新程序
│
├── core/                   # 核心逻辑
│   ├── types.py
│   ├── recorder.py         # 屏幕录制 (dxcam)，支持多显示器与空闲自动暂停
│   ├── idle_detector.py    # 用户空闲检测 (Windows GetLastInputInfo)
│   ├── window_tracker.py   # 窗口追踪 (Windows API)
│   ├── llm_provider.py     # AI API 交互
│   ├── analysis.py         # 分析调度器
│   ├── email_service.py    # 邮件日报 + 深度分析 + 智能补发
│   ├── updater.py          # 版本检查 + 多源下载
│   ├── autostart.py        # 开机自启动管理
│   ├── config_manager.py   # 配置集中管理
│   ├── log_manager.py      # 日志轮转管理
│   ├── stats_collector.py  # 统计数据收集器
│   └── dashboard_exporter.py # Web 仪表盘导出
│
├── database/               # 数据层
│   ├── schema.sql          # 表结构定义
│   ├── storage.py          # SQLite 管理
│   └── connection_pool.py  # 数据库连接池
│
├── ui/                     # 界面层
│   ├── main_window.py      # 主窗口 + 设置面板
│   ├── timeline_view.py    # 时间轴组件
│   ├── stats_view.py       # 统计面板
│   ├── daily_report_view.py # 日报浏览与导出
│   ├── date_range_dialog.py # 日期范围选择对话框
│   └── themes.py           # 主题管理
│
├── templates/              # HTML 模板
│   └── dashboard.html      # Web 仪表盘模板
│
└── assets/                 # 资源文件
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

### 关键配置项（config.py）

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `IDLE_PAUSE_ENABLED` | 检测到空闲后自动暂停录制 | `True` |
| `IDLE_PAUSE_TIMEOUT_SECONDS` | 空闲超时阈值（秒） | `600`（10 分钟） |
| `CHUNKS_MAX_SIZE_GB` | 切片存储上限（GB），超限自动清理 | `5` |
| `CUSTOM_CHUNKS_DIR` | 自定义切片目录（空则使用默认） | `""` |

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | PySide6 (Qt6) |
| 屏幕捕获 | dxcam (DirectX) |
| 视频处理 | OpenCV |
| 网络请求 | httpx (HTTP/2) |
| 数据存储 | SQLite |
| AI 分析 | OpenAI 兼容接口 |

---

## 🗺️ Roadmap

### 近期计划

- [x] ~~多显示器全屏录制支持~~
- [x] ~~空闲自动暂停录制~~
- [x] ~~日报缓存与历史浏览~~
- [ ] 更细粒度的隐私控制与录制暂停体验
- [ ] 更准确的活动合并与时间线切分
- [ ] 更丰富的统计面板与趋势分析
- [ ] 更稳定的更新与安装体验
- [ ] 完善自动化测试与 CI

### 中期计划

- [ ] 更强的网站 / 应用识别能力
- [ ] 本地模型或混合分析模式
- [ ] 更智能的每日 / 每周行为洞察
- [ ] 更完善的数据导出与报告能力

---

## Known Limitations

- 当前仅支持 Windows 10 / 11
- 活动识别质量依赖你配置的视觉模型能力
- 某些应用的窗口标题可能无法稳定获取
- 全屏游戏、特殊渲染窗口、远程桌面等场景可能存在兼容性差异
- 若网络或模型服务不稳定，分析时延会受到影响

---

## 🧰 常见问题 / Troubleshooting

### 1. 启动后没有分析结果

可以优先检查：
- API 地址、Key、模型名是否填写正确
- 模型是否支持视觉输入
- 网络是否可以访问你的模型服务
- 日志中是否存在请求失败或超时

### 2. 录屏或窗口识别异常

可以优先检查：
- 是否运行在 Windows 10 / 11 环境
- 是否缺少 FFmpeg
- 是否有安全软件拦截录屏或窗口读取
- 是否处于全屏游戏、远程桌面或特殊渲染场景

### 3. 邮件日报发送失败

可以优先检查：
- QQ 邮箱 SMTP / 授权码是否配置正确
- 是否能通过“测试发送”正常发出
- 本机网络是否拦截邮件服务连接

### 4. 更新或启动项不生效

可以优先检查：
- 是否在打包后的 EXE 环境中运行
- EXE 路径是否被移动
- 当前系统权限或安全策略是否限制自启动 / 更新流程

---

## 💡 灵感来源

本项目灵感源于 [Dayflow (macOS)](https://github.com/JerryZLiu/Dayflow) 开源项目。由于原项目仅支持 macOS，因此我基于相同理念开发了这个 Windows 版本，让更多用户能够体验 AI 驱动的智能时间追踪。

感谢原作者的创意和开源精神！🙏

---

## 📄 许可证

[CC BY-NC-SA 4.0](LICENSE) © 2024-2025

本项目采用 **知识共享 署名-非商业性使用-相同方式共享 4.0** 协议。
- ✅ 可自由学习、修改、分享
- ✅ 修改或引用时请注明原作者
- ❌ 禁止商业使用

> ℹ️ 该仓库当前使用的是 CC BY-NC-SA 4.0，而不是常见的软件许可证（如 MIT / Apache-2.0）。如果你计划二次分发或用于商业场景，请先阅读 LICENSE。

---

## ⭐ Star 历史

<a href="https://star-history.com/#SeiShonagon520/Dayflow&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date" />
 </picture>
</a>

---

<div align="center">

**如果觉得有用，欢迎点个 ⭐ Star！**

</div>
