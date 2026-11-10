CREATE TABLE wave_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange TEXT NOT NULL, symbol TEXT NOT NULL, tf TEXT NOT NULL, bar_ts INTEGER NOT NULL,
        logged_at INTEGER NOT NULL, logged_by TEXT NOT NULL, structure_version TEXT NOT NULL,
        close REAL, atr_now REAL,
        top1_id TEXT, top1_kind TEXT, top1_direction TEXT, top1_in_wave TEXT, top1_fit REAL,
        top1_n_guidelines INTEGER, top1_hard_pass TEXT,
        ambiguous INTEGER, none_valid INTEGER, n_valid INTEGER, n_unverifiable INTEGER,
        inv_price REAL, target_label TEXT, target_price REAL, d_inv REAL, d_tgt REAL, p_ref REAL,
        alt_id TEXT, alt_inv_price REAL, alt_fit REAL, alternates_json TEXT,
        dow_state TEXT, dow_scale TEXT, eff_ratio REAL, regime TEXT,
        grid_json TEXT, churn_30 REAL,
        UNIQUE(exchange, symbol, tf, bar_ts));
CREATE TABLE chart_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_family TEXT NOT NULL, exchange TEXT NOT NULL, symbol TEXT NOT NULL, tf TEXT NOT NULL, event_key TEXT NOT NULL,
        t0_bar_ts INTEGER, payload_json TEXT NOT NULL,
        logged_at INTEGER NOT NULL, logged_by TEXT NOT NULL, chart_version TEXT NOT NULL, structure_version TEXT NOT NULL,
        judge INTEGER NOT NULL DEFAULT 0,
        UNIQUE(event_family, exchange, symbol, tf, event_key));
CREATE TABLE wave_log_quarantine (
        wave_id INTEGER PRIMARY KEY, reason TEXT NOT NULL, evidence TEXT, quarantined_at INTEGER NOT NULL);
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
