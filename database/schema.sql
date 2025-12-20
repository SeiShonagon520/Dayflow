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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES analysis_batches(id)
);

-- 用户设置表
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_start_time ON chunks(start_time);
CREATE INDEX IF NOT EXISTS idx_batches_status ON analysis_batches(status);
CREATE INDEX IF NOT EXISTS idx_cards_start_time ON timeline_cards(start_time);
CREATE INDEX IF NOT EXISTS idx_cards_category ON timeline_cards(category);


-- 邮件发送记录表
CREATE TABLE IF NOT EXISTS email_send_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,  -- 'noon', 'night', 或自定义时间标识
    send_time TIMESTAMP NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_send_log_period ON email_send_log(period);
CREATE INDEX IF NOT EXISTS idx_email_send_log_time ON email_send_log(send_time);
