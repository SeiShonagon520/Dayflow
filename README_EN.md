<div align="center">

# ⏱️ Dayflow for Windows

**AI-powered time tracking and productivity analysis for Windows**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![GUI](https://img.shields.io/badge/GUI-Tauri_2.0_%7C_React_18-61DAFB?logo=react&logoColor=white)](https://tauri.app/)
[![Core](https://img.shields.io/badge/Core-Rust_%7C_Python-DEA584?logo=rust&logoColor=white)](https://www.rust-lang.org/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

*Silent background recording → AI analysis → visual timeline*

[![Download](https://img.shields.io/badge/⬇️_Download-EXE-brightgreen?style=for-the-badge)](https://github.com/SeiShonagon520/Dayflow/releases)

[中文](README.md) | **English**

</div>

---

## 🎯 What is Dayflow?

**Dayflow** is an AI-powered time tracking tool for Windows. It quietly captures low-frequency screen activity and window context in the background, uses a vision model to infer what you are doing, and turns the result into a timeline, statistics dashboard, and reports so you can understand where your time actually goes.

### 💡 Who is it for?

- People who want to know where their day went
- People who want to review focus time, distractions, and work patterns
- People who need automatic activity logs, daily reports, or weekly summaries
- People who prefer passive tracking over manual timers

### 🏆 Key advantages

| Advantage | Description |
|-----------|-------------|
| **Zero effort** | Start it and let AI handle activity recognition automatically |
| **Low overhead** | 1 FPS recording + smart compression to keep background usage low |
| **Local first** | Raw recordings stay on your machine and temporary chunks are cleaned up after analysis |
| **Smart categories** | Automatically detects work / study / entertainment / social / rest |
| **Visual review** | Timeline, statistics page, and HTML dashboard for different review styles |

---

## 🔐 Privacy, upfront

Dayflow is designed around **local recording + cloud analysis + local storage**.

### 5 things you should know

1. **Full videos are not uploaded**  
   Raw recording chunks stay on your local machine.

2. **Only a limited number of keyframes are sent for analysis**  
   Visual screenshot analysis prioritizes frames around window switches and sends at most 4 keyframes per chunk to the configured vision model. Local timing only stores app names and duration.

3. **Analysis results are stored locally**  
   Activities, settings, and statistics are saved in a local SQLite database.

4. **Temporary chunks are cleaned up automatically**  
   After analysis, temporary recording files are deleted to reduce disk usage.

5. **You can pause recording for sensitive moments**  
   Passwords, banking, private chats, or anything else sensitive can be handled by pausing recording first.

### Local data location

```text
%LOCALAPPDATA%\Dayflow\
├── dayflow.db      # activities, settings, stats
├── dayflow.log     # runtime logs
├── chunks\         # temporary recording chunks
└── updates\        # downloaded updates
```

> 💡 If privacy is your first concern, read this section before enabling continuous recording.

---

## ✨ Main features

| Feature | Description |
|---------|-------------|
| 🎥 **Low-power recording** | 1 FPS low-resource background capture |
| 🪟 **Window tracking** | Uses Windows API to capture real app names and window titles |
| 🤖 **AI analysis** | Vision LLM classifies screen activity automatically |
| 📊 **Timeline view** | Clear daily activity review at a glance |
| 📈 **Statistics dashboard** | Time distribution, productivity trends, week comparison |
| 📊 **Web dashboard export** | Beautiful self-contained HTML report with charts |
| 📧 **Email reports** | Automatic daily summaries and deeper analysis |
| 🔄 **Auto update** | Check, download, and install new versions |
| 🚀 **Auto start** | Launch on boot and minimize to tray |
| 📥 **CSV export** | Export activity data for further analysis |
| ⏸️ **Pause recording** | Pause when handling sensitive content |
| 🎨 **Theme switching** | Dark / light themes with saved preferences |

## v1.8.0

Dayflow for Windows uses Tauri and React. The installer continues to use `%LOCALAPPDATA%\Dayflow\dayflow.db`, so existing activity, reports, and settings carry over. You can merge legacy JSON backups from Settings → Data import and export.

Use the main window or system tray to start, pause, resume, or stop tracking. Settings covers local timing vs. visual capture, display selection, idle detection, chunk storage, scheduled and test email, HTML and CSV export, JSON backups, diagnostics, sign-in auto-start, and in-app installer updates.

### Install

Download the latest `Dayflow_<version>_x64-setup.exe` from [GitHub Releases](https://github.com/SeiShonagon520/Dayflow/releases). Dayflow supports Windows 10/11 x64. Start with local application timing. Configure a model only when you want screenshot analysis or AI report commentary.

### Develop and build

Install Node.js 22, stable Rust (MSVC), Visual Studio C++ Build Tools, the Windows SDK, and Python 3.10 or 3.11.

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt -r bridge/requirements.txt pyinstaller
npm ci
.\start.bat
```

Run `python -m pytest -q` for backend tests and `npm run lint && npm test && npm run build` for React Hooks lint, frontend component tests, TypeScript, and the production bundle. Run `.\build.bat` to rebuild the Python sidecar and the Tauri NSIS installer.

The installer is written to `src-tauri\target\release\bundle\nsis\`. Attach the matching `Dayflow_<version>_x64-setup.exe` to the GitHub Release. Windows CI builds the same installer after the test matrix passes.

| Path | Purpose |
| --- | --- |
| `src/` | React UI |
| `src-tauri/` | Windows host, tray, dialogs, and installer |
| `bridge/` | Local API, scheduling, preferences, and backups |
| `core/` | Recording, analysis, reports, and updates |
| `database/` | SQLite storage and migration |
| `templates/` | HTML dashboard and email templates |

## 💡 Inspiration

This project is inspired by [Dayflow (macOS)](https://github.com/JerryZLiu/Dayflow). The original project is macOS-only, so this repository brings a similar idea to Windows users.

Thanks to the original author for the creativity and open-source spirit.

---

## 📄 License

[CC BY-NC-SA 4.0](LICENSE) © 2024-2026

This project currently uses **Creative Commons Attribution-NonCommercial-ShareAlike 4.0**.
- ✅ You can learn from it, modify it, and share it
- ✅ Please credit the original author
- ❌ Commercial use is not allowed

> ℹ️ This is not a typical software license such as MIT or Apache-2.0. If you plan to redistribute or use the project commercially, read `LICENSE` carefully first.

---

## ⭐ Star History

<a href="https://star-history.com/#SeiShonagon520/Dayflow&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=SeiShonagon520/Dayflow&type=Date" />
 </picture>
</a>

---

<div align="center">

**If you find Dayflow useful, consider giving it a ⭐ Star!**

</div>
