-- schema.sql – SQLite schema for HostelCare AI

PRAGMA foreign_keys = ON;

-- Departments table (e.g., Plumbing, Electrical)
CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- Authorities hierarchy (technician, supervisor, warden, director)
CREATE TABLE IF NOT EXISTS authorities (
    authority_id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    level INTEGER NOT NULL,               -- lower number = lower in hierarchy
    department_id INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

-- Complaints / tickets
CREATE TABLE IF NOT EXISTS complaints (
    ticket_id TEXT PRIMARY KEY,            -- UUID or short hash
    user_id TEXT,                          -- Student ID who created the ticket
    description TEXT NOT NULL,
    category TEXT NOT NULL,                -- water, electrical, etc.
    block TEXT NOT NULL,
    priority TEXT NOT NULL,                -- Low, Medium, High, Critical
    status TEXT NOT NULL,                  -- Open, Assigned, In Progress, Resolved
    assigned_role TEXT,                    -- role name of current authority
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- History of complaint updates and status changes
CREATE TABLE IF NOT EXISTS complaint_updates (
    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    updated_by TEXT,
    old_status TEXT,
    new_status TEXT,
    update_note TEXT,
    timestamp TEXT NOT NULL,

    FOREIGN KEY (ticket_id)
        REFERENCES complaints(ticket_id),
    FOREIGN KEY (updated_by)
        REFERENCES users(user_id)
);


-- Action log for audit / escalation history
CREATE TABLE IF NOT EXISTS action_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    action TEXT NOT NULL,                  -- Created, Assigned, Escalated, Updated
    from_role TEXT,
    to_role TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES complaints(ticket_id)
);

-- Seed sample data (departments & authorities)
INSERT OR IGNORE INTO departments (name) VALUES ('Plumbing'), ('Electrical'), ('Housekeeping'), ('Security');

INSERT OR IGNORE INTO authorities (role, level, department_id) VALUES
    ('Technician', 1, (SELECT department_id FROM departments WHERE name='Plumbing')),
    ('Supervisor', 2, (SELECT department_id FROM departments WHERE name='Plumbing')),
    ('Warden', 3, (SELECT department_id FROM departments WHERE name='Plumbing')),
    ('Director', 4, (SELECT department_id FROM departments WHERE name='Plumbing')),
    ('Technician', 1, (SELECT department_id FROM departments WHERE name='Electrical')),
    ('Supervisor', 2, (SELECT department_id FROM departments WHERE name='Electrical')),
    ('Warden', 3, (SELECT department_id FROM departments WHERE name='Electrical')),
    ('Director', 4, (SELECT department_id FROM departments WHERE name='Electrical'));

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL                    -- 'Student' or 'Warden'
);

-- Seed initial accounts
INSERT OR IGNORE INTO users (user_id, name, password, role) VALUES
    ('STU101', 'Alex Kumar', 'student123', 'Student'),
    ('STU102', 'Rohan Sharma', 'student123', 'Student'),
    ('WARDEN01', 'Chief Warden Verma', 'admin123', 'Warden');

