```bash
CREATE TABLE IF NOT EXISTS pod_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace   TEXT NOT NULL,
    pod_name    TEXT NOT NULL,
    issue_type  TEXT NOT NULL,
    severity    TEXT NOT NULL,
    first_seen  TEXT NOT NULL,      -- iso‑string
    last_seen   TEXT,               -- NULL ⇒ ongoing
    source      TEXT DEFAULT 'kubernetes',  -- 'kubernetes' or 'prometheus'
    UNIQUE (namespace, pod_name, issue_type, first_seen, source)
);
```

Why this shape?

    One row per episode (continuous failure window).

    When the pod recovers you simply UPDATE … SET last_seen = now().

    Later you can aggregate: “Total CrashLoopBackOff minutes per day”, “MTTR by service”, etc.
