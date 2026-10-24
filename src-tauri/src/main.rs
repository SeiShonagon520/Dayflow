// Dayflow Tauri 外壳
//
// 职责很窄：
//   1. 启动 Python bridge 子进程（录屏、AI 分析都在那边）
//   2. 提供前端需要的原生能力（保存文件、托盘、最小化到托盘）
//   3. 退出时干净地关掉子进程
//
// 不做业务逻辑 —— 那些在 core/ 里。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

#[cfg(windows)]
use windows_sys::Win32::Foundation::HANDLE;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager,
};

/// bridge 子进程句柄。存进 Tauri state，退出时统一 kill。
///
/// PyInstaller onefile 会先起一个 bootloader 进程再 fork 出真正的
/// Python 子进程。只 kill 直接子进程可能留下真正在跑的那个，
/// 于是端口一直被占、下次启动失败。这里用 job object 兜底：
/// 父进程一死，整棵进程树跟着走。
struct BridgeProcess {
    child: Mutex<Option<Child>>,
    #[allow(dead_code)]
    job: JobHandle,
}

/// Windows Job Object：保证子进程树随父进程一起结束
#[cfg(windows)]
struct JobHandle {
    handle: HANDLE,
}

// HANDLE 是裸指针，跨线程要显式声明 —— Tauri 的 State 是 Send+Sync。
// 句柄本身是可跨线程使用的内核对象，Send/Sync 是安全的。
#[cfg(windows)]
unsafe impl Send for JobHandle {}
#[cfg(windows)]
unsafe impl Sync for JobHandle {}

#[cfg(windows)]
impl JobHandle {
    fn new() -> Self {
        use windows_sys::Win32::System::JobObjects::*;

        unsafe {
            // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return JobHandle { handle: std::ptr::null_mut() };
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            );
            JobHandle { handle: job }
        }
    }

    fn assign(&self, pid: u32) {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::JobObjects::*;
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
        };

        if self.handle.is_null() {
            return;
        }
        unsafe {
            let h = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
            if !h.is_null() {
                AssignProcessToJobObject(self.handle, h);
                CloseHandle(h);
            }
        }
    }
}

#[cfg(windows)]
impl Drop for JobHandle {
    fn drop(&mut self) {
        use windows_sys::Win32::Foundation::CloseHandle;
        unsafe {
            if !self.handle.is_null() {
                CloseHandle(self.handle);
            }
        }
    }
}

#[cfg(not(windows))]
struct JobHandle;

#[cfg(not(windows))]
impl JobHandle {
    fn new() -> Self {
        JobHandle
    }
    fn assign(&self, _pid: u32) {}
}

/// 8899 与 src/lib/api.ts 里的 BASE 必须一致。
#[allow(dead_code)]
const BRIDGE_PORT: u16 = 8899;

#[tauri::command]
fn save_text_file(app: AppHandle, default_name: String, content: String, ext: String) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;

    let path = app
        .dialog()
        .file()
        .set_file_name(&default_name)
        // Tauri 2 的 add_filter 第一个参数是 &str，不是 String
        .add_filter(&ext, &[&ext])
        .blocking_save_file()?;

    let p = path.to_string();
    if std::fs::write(&p, content).is_ok() {
        Some(p)
    } else {
        None
    }
}

/// 查找随包携带的 Python bridge。Tauri externalBin 在不同安装布局
/// 下可能放在主程序旁边或 resources/ 子目录里。
fn bundled_bridge_path(exe_dir: &Path) -> Option<PathBuf> {
    [
        exe_dir.join("python-bridge.exe"),
        exe_dir.join("resources").join("python-bridge.exe"),
    ]
    .into_iter()
    .find(|path| path.is_file())
}

/// 返回随包 bridge；开发时则用系统 Python。
#[allow(dead_code)]
fn python_command() -> Command {
    let exe = std::env::current_exe().unwrap_or_default();
    let dir = exe.parent().unwrap_or(std::path::Path::new("."));

    if let Some(bundled) = bundled_bridge_path(dir) {
        let mut c = Command::new(bundled);
        c.current_dir(exe.parent().unwrap_or(dir));
        return c;
    }

    // 开发布局：直接用 PATH 里的 python
    let mut c = Command::new("python");
    c.current_dir(dir);
    c
}

/// 开发模式下寻找项目根目录（包含 bridge/entry.py 的目录）
fn find_project_root(start_dir: &Path) -> PathBuf {
    let mut curr = start_dir.to_path_buf();
    loop {
        if curr.join("bridge").join("entry.py").is_file() {
            return curr;
        }
        if !curr.pop() {
            break;
        }
    }
    start_dir.to_path_buf()
}

/// 启动 bridge，失败时返回错误信息而不是 panic —— 用户应该看到
/// 「后台起不来」，而不是应用直接闪退。
fn spawn_bridge() -> Result<Child, String> {
    let exe_dir = exe_dir();
    let bundled = bundled_bridge_path(&exe_dir);

    let (mut cmd, work_dir) = if let Some(ref path) = bundled {
        (Command::new(path), exe_dir.clone())
    } else {
        let repo_root = find_project_root(&exe_dir);
        let mut c = Command::new("python");
        c.arg("bridge/entry.py");
        (c, repo_root)
    };

    let project_root = std::env::var("DAYFLOW_ROOT")
        .unwrap_or_else(|_| work_dir.to_string_lossy().to_string());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.current_dir(&work_dir)
        .env("DAYFLOW_ROOT", &project_root)
        .env("PYTHONPATH", &project_root)
        // bridge 日志混进 GUI 进程会污染 stdout，单独收走。
        // 需要排查时把 null 换成 Stdio::inherit()。
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

    cmd.spawn()
        .map_err(|e| format!("无法启动后台服务（{}）: {}", project_root, e))
}

fn exe_dir() -> std::path::PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|x| x.to_path_buf()))
        .unwrap_or_else(|| std::path::PathBuf::from("."))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![save_text_file])
        .setup(|app| {
            // ── 启动 Python bridge ──────────────────────────
            let job = JobHandle::new();
            let state = BridgeProcess {
                child: Mutex::new(None),
                job,
            };
            match spawn_bridge() {
                Ok(child) => {
                    // 把 sidecar 挂进 job object：应用退出时整棵进程树跟着走，
                    // 不会留下占着 8899 的孤儿进程
                    state.job.assign(child.id());
                    *state.child.lock().unwrap() = Some(child);
                }
                Err(e) => {
                    // 起不来也要让窗口显示，用户能在界面上看到问题
                    eprintln!("[dayflow] bridge 启动失败: {}", e);
                }
            }
            app.manage(state);

            // ── 托盘 ────────────────────────────────────────
            let show = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
            let start = MenuItem::with_id(app, "start", "开始录制", true, None::<&str>)?;
            let stop = MenuItem::with_id(app, "stop", "停止录制", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let sep = tauri::menu::PredefinedMenuItem::separator(app)?;

            // 分隔符要先 bind 成变量：直接内联在数组里会因为
            // 借用生命周期对不上而编译失败。
            let menu = Menu::with_items(app, &[&show, &start, &stop, &sep, &quit])?;

            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().cloned().unwrap())
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_window(app),
                    "start" => emit_to_frontend(app, "tray", "start"),
                    "stop" => emit_to_frontend(app, "tray", "stop"),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    // Tauri 2 里 DoubleClick 是结构体变体，不是元组变体
                    if let tauri::tray::TrayIconEvent::DoubleClick { .. } = event {
                        show_window(tray.app_handle());
                    }
                })
                .build(app)?;

            // 关闭按钮 → 最小化到托盘，而不是退出。
            // 录屏工具关掉就白开了，用户点 X 大概率是想让它后台继续跑。
            if let Some(win) = app.get_webview_window("main") {
                let handle = app.handle().clone();
                win.on_window_event(move |e| {
                    if let tauri::WindowEvent::CloseRequested { api, .. } = e {
                        if let Some(w) = handle.get_webview_window("main") {
                            let _ = w.hide();
                        }
                        api.prevent_close();
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // 窗口真正销毁时收掉子进程。job object 会在 state drop 时
            // 连带杀掉整个进程树，所以这里 kill 直接子进程只是快速路径。
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<BridgeProcess>() {
                    if let Some(mut child) = state.child.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("启动 Dayflow 失败");
}

fn emit_to_frontend(app: &AppHandle, kind: &str, action: &str) {
    use tauri::Emitter;
    let _ = app.emit("tray-action", (kind, action));
}

/// 从托盘恢复主窗口
fn show_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}
