-- Dayflow Windows - 数据库结构
-- SQLite 3

-- 视频切片表
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_seconds REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    batch_id INTEGER,
    window_records_path TEXT,  -- 窗口记录 JSON 文件路径
    retry_count INTEGER NOT NULL DEFAULT 0,
    retry_at REAL NOT NULL DEFAULT 0,
    analysis_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES analysis_batches(id)
);

-- 分析批次表
CREATE TABLE IF NOT EXISTS analysis_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_ids TEXT NOT NULL,  -- JSON array of chunk IDs
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    observations_json TEXT DEFAULT '[]',  -- 原始观察记录 JSON
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- 时间轴卡片表
CREATE TABLE IF NOT EXISTS timeline_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    app_sites_json TEXT DEFAULT '[]',  -- JSON array of AppSite objects
    distractions_json TEXT DEFAULT '[]',  -- JSON array of Distraction objects
    productivity_score REAL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'visual',  -- visual | local | local_refined | manual
    user_edited INTEGER NOT NULL DEFAULT 0,
    session_key TEXT,
    session_token TEXT,
    is_finalized INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    refinement_status TEXT NOT NULL DEFAULT 'none',  -- none | pending | claimed | refined | failed | skipped
    refinement_lease_id TEXT,
    refinement_lease_expires_at REAL NOT NULL DEFAULT 0,
    refinement_attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES analysis_batches(id)
);

-- 精确分段记账表（与 timeline_cards 同寿命，用于精确跨边界裁切和专注时长扣除）
CREATE TABLE IF NOT EXISTS card_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    app_name TEXT NOT NULL,
    is_distraction INTEGER NOT NULL DEFAULT 0
);

-- 本机结构化上下文明细表（不含 page_title；90 天滚动清理）
CREATE TABLE IF NOT EXISTS context_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    app_name TEXT NOT NULL,
    friendly_app TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '其他',
    domain TEXT,
    project_name TEXT,
    document_name TEXT,
    meeting_active INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'app_only',
    card_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 单行候选分心状态表（支撑 30s 缓冲期内的强杀崩溃恢复）
CREATE TABLE IF NOT EXISTS recorder_candidates (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    session_token TEXT NOT NULL,
    primary_card_id INTEGER NOT NULL,
    primary_session_key TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    app_name TEXT NOT NULL,
    friendly_app TEXT NOT NULL,
    category TEXT NOT NULL,
    context_json TEXT DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 服务端撤销删除快照表（完整保留 source / user_edited / card_segments，限制最新 20 条）
CREATE TABLE IF NOT EXISTS deleted_card_snapshots (
    undo_token TEXT PRIMARY KEY,
    card_id INTEGER NOT NULL,
    card_json TEXT NOT NULL,
    segments_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'visual',
    user_edited INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 纯文本精炼每日批次数硬额度表（重启不重置）
CREATE TABLE IF NOT EXISTS refinement_quota (
    quota_date TEXT PRIMARY KEY,
    batch_count INTEGER NOT NULL DEFAULT 0
);

-- 用户设置表
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 基础索引（依赖增量列的索引在 StorageManager._migrate_database() 中创建）
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_start_time ON chunks(start_time);
CREATE INDEX IF NOT EXISTS idx_batches_status ON analysis_batches(status);
CREATE INDEX IF NOT EXISTS idx_cards_start_time ON timeline_cards(start_time);
CREATE INDEX IF NOT EXISTS idx_cards_category ON timeline_cards(category);
CREATE INDEX IF NOT EXISTS idx_card_segments_card ON card_segments(card_id, start_time);
CREATE INDEX IF NOT EXISTS idx_context_events_time ON context_events(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_context_events_card ON context_events(card_id);
CREATE INDEX IF NOT EXISTS idx_deleted_snapshots_card ON deleted_card_snapshots(card_id, deleted_at);


-- 邮件发送记录表
CREATE TABLE IF NOT EXISTS email_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,  -- 'noon', 'night', 或自定义时间标识
    send_time TIMESTAMP NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,  -- legacy column kept for existing databases
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_send_log_period ON email_send_log(period);
CREATE INDEX IF NOT EXISTS idx_email_send_log_time ON email_send_log(send_time);

-- 日报缓存表
CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    source_key TEXT,
    previous_content TEXT,
    previous_source_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
