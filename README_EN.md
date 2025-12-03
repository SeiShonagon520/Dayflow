<div align="center">

# ⏱️ Dayflow for Windows

**Intelligent Time Tracking & Productivity Analysis Tool**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

*Silent Background Recording → AI Analysis → Visual Timeline*

[中文](README.md) | **English**

</div>

---

## 🎯 What is Dayflow?

**Dayflow** is an AI-powered intelligent time tracking tool. It silently records your screen in the background, uses vision AI to automatically identify what you're doing, and generates an intuitive timeline to help you understand where your time goes every day.

### 💡 Why Do You Need It?

- **Don't know where your time went?** → Dayflow auto-records, no manual tracking needed
- **Want to boost productivity?** → AI analyzes your work patterns, identifies distractions
- **Need a work log?** → Auto-generates daily activity reports
- **Remote work attendance?** → Objectively records work hours and content

### 🏆 Key Advantages

| Advantage | Description |
|-----------|-------------|
| **Zero Effort** | Set and forget, AI fully automates activity recognition |
| **Ultra Low Power** | 1 FPS recording + smart compression, < 1% CPU usage |
| **Privacy First** | Local data storage, videos auto-deleted after analysis |
| **Smart Categories** | AI auto-identifies: Work/Study/Entertainment/Social/Rest |
| **Productivity Score** | Efficiency rating for each activity, quantify your focus |

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎥 **Low-Power Recording** | 1 FPS ultra-low resource usage, runs silently in background |
| 🤖 **AI-Powered Analysis** | Vision LLM identifies screen activities and auto-categorizes |
| 📊 **Timeline Visualization** | Intuitive daily time allocation view at a glance |
| 💡 **Productivity Insights** | AI-driven efficiency assessment and improvement suggestions |
| 🔒 **Privacy First** | Local data storage, auto-cleanup after analysis |

### 🆕 Latest Features

| Feature | Description |
|---------|-------------|
| 📧 **Email Reports** | Auto-send productivity reports to your email at 12:00 and 22:00 daily |
| 🤖 **AI Comments** | AI-generated personalized daily summary with friendly encouragement |
| 📊 **Statistics Panel** | New stats page with time distribution and productivity trends |
| 📅 **Date Navigation** | View history with previous/next day and quick "Today" buttons |
| 📥 **CSV Export** | One-click export activity data to CSV for analysis and archiving |
| ⏸️ **Pause Recording** | Pause when handling private content, resume when done |
| 📊 **Time Distribution** | Visual bar chart showing time allocation by category |
| 🎨 **Theme Switching** | IDE-style dark/light themes with auto-saved preferences |
| 🔽 **System Tray** | Minimize to tray on close, keeps running in background |
| 📦 **EXE Packaging** | Build standalone executable, no Python required |
| ⭐ **GitHub Link** | Quick link to project page in sidebar |

---

## 🖥️ UI Preview

### Timeline Page

![Dayflow Timeline](assets/Dayflow_index.png)

*Timeline: Displays daily activity cards with time range, app, summary, and productivity score*

### Statistics Page

![Dayflow Statistics](assets/Dayflow_Statistics.png)

*Statistics: View weekly/monthly time distribution and productivity trends*

### 📧 Email Report Feature

#### Settings Panel

![Email Settings](assets/Dayflow_Email_Settings.png)

*Email Push Settings: Configure QQ email address and authorization code, with test send support*

#### Email Report Examples

<div align="center">
<img src="assets/Dayflow_Email_Report_1.png" width="45%" alt="Report Example 1"/>
<img src="assets/Dayflow_Email_Report_2.png" width="45%" alt="Report Example 2"/>
</div>

*Daily Productivity Report: Time statistics, category distribution, and AI personalized feedback (different scenarios)*

#### Feature Highlights

| Feature | Description |
|---------|-------------|
| ⏰ **Scheduled Push** | Auto-send reports at 12:00 and 22:00 daily |
| 📊 **Data Summary** | Total tracked time and efficiency score at a glance |
| 📈 **Category Stats** | Visual breakdown of time spent by category |
| 🤖 **AI Feedback** | Personalized suggestions based on daily performance |
| 💬 **Friendly Tone** | Warm encouragement, like a friend caring about your productivity |

### Interface Guide

| Area | Function |
|------|----------|
| **Left Sidebar** | Navigation: Timeline, Settings, Recording Control |
| **Timeline Page** | Displays all activity cards for today, sorted by time |
| **Activity Cards** | Shows time range, category, app, summary, productivity score |
| **Settings Page** | Configure API Key, test connection, recording parameters |
| **System Tray** | Runs in tray when minimized, right-click menu for control |

### Activity Card Details

Each card contains:
- ⏰ **Time Range** - Start and end time of the activity
- 📁 **Category** - Work/Study/Coding/Meeting/Entertainment/Social/Rest
- 💻 **Application** - Main software used
- 📝 **Summary** - AI-generated activity description
- ⚡ **Productivity Score** - 0-100% efficiency rating

---

## 🚀 Quick Start

### Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) (added to system PATH)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/SeiShonagon520/Dayflow.git
cd Dayflow

# 2. Create Conda environment (recommended)
conda create -n dayflow python=3.11 -y
conda activate dayflow

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the app
python main.py
```

### Build as EXE (Optional)

To distribute to others without requiring Python installation:

```bash
# Install packaging tool
pip install pyinstaller

# Run build script
python build.py

# Or double-click build.bat
```

After building, the `dist/Dayflow/` folder can be copied and shared directly.

---

## 📖 User Guide

### 1️⃣ Configure API Key

1. Open the app, click **⚙️ Settings** on the left sidebar
2. Enter your API Key
3. Click **Test Connection** to verify
4. Click **Save**

> 💡 API Endpoint: `https://apis.iflow.cn/v1`

### 2️⃣ Start Recording

1. Click **▶ Start Recording**
2. The app records your screen at 1 FPS in the background
3. Video chunks are saved every 60 seconds
4. Automatically sent to cloud AI for analysis

### 3️⃣ View Timeline

- Analysis results appear on the home timeline
- Each card represents an activity period
- Includes: category, applications used, productivity score

### 4️⃣ Email Reports (Optional)

1. Go to **Settings** → **Email Push**
2. Enter your QQ email address and authorization code
3. Click **Save Config**
4. Click **Test Send** to verify

> 💡 Get auth code: QQ Mail → Settings → Account → POP3/SMTP Service → Generate Authorization Code

**Email Content**:
- 📊 Daily time statistics (total duration, efficiency score)
- 📈 Time distribution by category
- 💬 AI-generated personalized feedback and suggestions

### 5️⃣ System Tray

- Close window → Minimizes to tray, keeps running
- Double-click tray icon → Open main window
- Right-click tray → Control recording / Exit

---

## 📁 Project Structure

```
Dayflow/
├── 📄 main.py              # Entry point
├── ⚙️ config.py            # Configuration
├── 📦 requirements.txt     # Dependencies
├── 🔨 build.py             # EXE build script
├── 🔨 build.bat            # One-click build batch
│
├── 🧠 core/                # Core logic
│   ├── types.py            # Data models
│   ├── recorder.py         # Screen capture (dxcam)
│   ├── llm_provider.py     # AI API integration
│   ├── analysis.py         # Analysis scheduler
│   └── email_service.py    # Email report service
│
├── 💾 database/            # Data layer
│   ├── schema.sql          # Table definitions
│   └── storage.py          # SQLite management
│
├── 🎨 ui/                  # UI layer
│   ├── main_window.py      # Main window
│   ├── timeline_view.py    # Timeline component
│   └── themes.py           # Theme management
│
└── 🖼️ assets/              # Resources
    └── icon.ico            # App icon
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DAYFLOW_API_URL` | API endpoint | `https://apis.iflow.cn/v1` |
| `DAYFLOW_API_KEY` | API key | (empty) |
| `DAYFLOW_API_MODEL` | AI model | `qwen3-vl-plus` |

### Data Directory

```
%LOCALAPPDATA%\Dayflow\
├── dayflow.db      # Database
├── chunks/         # Video chunks (auto-deleted after analysis)
└── dayflow.log     # Runtime logs
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| GUI Framework | PySide6 (Qt6) |
| Screen Capture | dxcam (DirectX) |
| Video Processing | OpenCV |
| HTTP Client | httpx (HTTP/2) |
| Database | SQLite |
| AI Analysis | OpenAI-compatible API |

---

## 🔐 Security & Privacy

Dayflow takes user privacy seriously with multiple layers of protection:

### Data Storage

| Data Type | Location | Description |
|-----------|----------|-------------|
| Video Chunks | Local `%LOCALAPPDATA%\Dayflow\chunks\` | Temporary storage only |
| Analysis Results | Local `dayflow.db` | SQLite database |
| User Settings | Local database | API Key, email config, etc. |

### Privacy Protection Measures

| Measure | Description |
|---------|-------------|
| 📍 **Local First** | All raw screen recordings are stored locally only, full videos are never uploaded |
| 🗑️ **Auto Cleanup** | Video chunks are automatically deleted after AI analysis, saving disk space |
| 🖼️ **Minimal Transfer** | Only key frames (max 8 per chunk) are extracted and sent for AI analysis |
| ⏸️ **Pause Feature** | Pause recording anytime when handling sensitive content, resume when done |
| 🔒 **Local Database** | Analysis results are stored in local SQLite, never uploaded to cloud |

### Recommendations

- When handling banking, passwords, or sensitive information, click the **⏸️ Pause** button
- Click **▶ Resume** to continue recording when done
- Periodically check `%LOCALAPPDATA%\Dayflow\` to confirm data cleanup is working properly

> 💡 **Note**: Dayflow's design philosophy is "local recording + cloud analysis + local storage". Raw videos never leave your computer.

---

## 💡 Inspiration

This project is inspired by [Dayflow (macOS)](https://github.com/JerryZLiu/Dayflow). Since the original project only supports macOS, I developed this Windows version based on the same concept, allowing more users to experience AI-powered intelligent time tracking.

Thanks to the original author for the creativity and open-source spirit! 🙏

---

## 📄 License

[CC BY-NC-SA 4.0](LICENSE) © 2024-2025

This project is licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0**.
- ✅ Free to learn, modify, and share
- ✅ Please credit the original author when using or modifying
- ❌ Commercial use prohibited

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

**If you find this useful, please give it a ⭐ Star!**

</div>
