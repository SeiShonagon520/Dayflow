<div align="center">

# ⏱️ Dayflow for Windows

**AI 驱动的智能时间追踪与生产力分析工具**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![GUI](https://img.shields.io/badge/GUI-Tauri_2.0_%7C_React_18-61DAFB?logo=react&logoColor=white)](https://tauri.app/)
[![Core](https://img.shields.io/badge/Core-Rust_%7C_Python-DEA584?logo=rust&logoColor=white)](https://www.rust-lang.org/)
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
   截图分析会优先保留窗口切换附近的画面，每个切片最多向所配置的模型发送 4 帧。本机计时只保存应用名和用时。

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

## v1.8.0

Dayflow Windows 版使用 Tauri + React。安装新版后会继续读取 `%LOCALAPPDATA%\Dayflow\dayflow.db`，已有的活动、日报和设置可直接使用。旧版 JSON 备份可以从「设置 → 数据导入与导出」合并。

| 任务 | 入口 |
| --- | --- |
| 开始、暂停、继续、停止记录 | 主界面或系统托盘 |
| 切换本机计时与截图分析 | 设置 → 活动记录 |
| 查看本机总结、核对活动与补充日报 | 日报 |
| 选择显示器、空闲设置、切片目录和容量 | 设置 → 活动记录 |
| 定时发送日报和发送测试邮件 | 设置 → 邮件日报 |
| 导出 HTML、CSV、JSON 或合并数据 | 设置 → 数据导入与导出 |
| 登录后自动在托盘启动并开始记录 | 设置 → 系统 |
| 下载、校验并安装更新 | 设置 → 系统 |
| 查阅日志并打开日志目录 | 设置 → 诊断日志 |

### 安装

从 [GitHub Releases](https://github.com/SeiShonagon520/Dayflow/releases) 下载最新的 `Dayflow_<版本>_x64-setup.exe`。支持 Windows 10/11 x64。首次打开即可开始本机计时。需要截图分析或 AI 补充日报时，可在设置中配置模型，识图测试使用生成的样图。登录自启沿用已设置的 Dayflow 启动项。

### 开发和构建

需要 Node.js 22、Rust stable（MSVC）、Visual Studio C++ Build Tools、Windows SDK、Python 3.10 或 3.11。

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt -r bridge/requirements.txt pyinstaller
npm ci
.\start.bat
```

运行 `python -m pytest -q` 检查后端逻辑，运行 `npm run lint && npm test && npm run build` 检查 React Hooks、前端组件测试、TypeScript 与前端产物。运行 `.\build.bat` 会重新构建 Python sidecar 和 Windows NSIS 安装包。

安装包位于 `src-tauri\target\release\bundle\nsis\`。发布时将对应版本的 `Dayflow_<版本>_x64-setup.exe` 附到对应 GitHub Release。Windows CI 在测试通过后构建同一份安装包。

### 目录

| 路径 | 用途 |
| --- | --- |
| `src/` | React 界面和交互 |
| `src-tauri/` | Windows 宿主、托盘、原生文件对话框和安装包 |
| `bridge/` | 本地 API、定时日报、备份和设置 |
| `core/` | 录制、分析、HTML 报告和更新 |
| `database/` | SQLite 存储及旧数据库迁移 |
| `templates/` | HTML 仪表盘和邮件模板 |

### 常见问题

- 未生成活动时，检查已选显示器与视觉模型连接。切换录制路径前先停止录制。
- 邮件发送失败时，确认已为 QQ 邮箱开启 SMTP 并使用授权码。保存后可以先发送测试邮件。
- 自启动显示指向旧路径时，点击「修复路径」。应用的诊断日志也可在设置页查看。

## 💡 灵感来源

本项目灵感源于 [Dayflow (macOS)](https://github.com/JerryZLiu/Dayflow) 开源项目。由于原项目仅支持 macOS，因此我基于相同理念开发了这个 Windows 版本，让更多用户能够体验 AI 驱动的智能时间追踪。

感谢原作者的创意和开源精神！🙏

---

## 📄 许可证

[CC BY-NC-SA 4.0](LICENSE) © 2024-2026

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
