# -*- coding: utf-8 -*-
import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# =====================================================================
# 【管理員初始化設定】
# 請在此處輸入您的 LINE User ID，系統啟動時會自動將其加入 `admins` 資料表。
# 方便您在首次登入時，能順利進入管理員設定後台。
# =====================================================================
INIT_ADMIN_ID = "admin_test_123"  # <-- 請手動替換為您真實的 LINE User ID

DATABASE_URL = os.environ.get('DATABASE_URL')

# 定義相容的唯一性衝突例外
try:
    import psycopg2
    import psycopg2.extras
    DBIntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError)
except ImportError:
    DBIntegrityError = (sqlite3.IntegrityError,)

class DBConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self, *args, **kwargs):
        cursor = self.conn.cursor(*args, **kwargs)
        return DBCursorWrapper(cursor)

    def commit(self):
        return self.conn.commit()

    def close(self):
        return self.conn.close()

    def __getattr__(self, name):
        return getattr(self.conn, name)

class DBCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=()):
        if DATABASE_URL:
            # PostgreSQL 佔位符替換
            sql = sql.replace('?', '%s')
            if "INSERT OR IGNORE" in sql:
                sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
                if "ON CONFLICT" not in sql:
                    sql = sql + " ON CONFLICT DO NOTHING"
        self.cursor.execute(sql, params)
        return self

    def executemany(self, sql, seq_of_params):
        if DATABASE_URL:
            sql = sql.replace('?', '%s')
            if "INSERT OR IGNORE" in sql:
                sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
                if "ON CONFLICT" not in sql:
                    sql = sql + " ON CONFLICT DO NOTHING"
        self.cursor.executemany(sql, seq_of_params)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __getattr__(self, name):
        return getattr(self.cursor, name)

def get_db_connection():
    if DATABASE_URL:
        # 使用 PostgreSQL
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        return DBConnectionWrapper(conn)
    else:
        # 使用 SQLite
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")  # 啟用外鍵約束
        return conn

def add_project_id_column_if_not_exists(cursor, conn, table_name):
    if DATABASE_URL:
        # PostgreSQL: 檢查 column 是否存在
        cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}' AND column_name='project_id'")
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE")
    else:
        # SQLite: 檢查 column 是否存在
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [row[1] for row in cursor.fetchall()]
        if 'project_id' not in cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if not DATABASE_URL:
        cursor.execute("PRAGMA foreign_keys = OFF;")
    
    if DATABASE_URL:
        # PostgreSQL 建立資料表 (使用 SERIAL 自增與 VARCHAR 類型)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                UNIQUE(project_id, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS floors (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                UNIQUE(project_id, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_items (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                category VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                UNIQUE(project_id, category, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id SERIAL PRIMARY KEY,
                block_id INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
                floor_id INTEGER NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
                work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
                status INTEGER NOT NULL DEFAULT 0,
                updated_by VARCHAR(255),
                updated_at VARCHAR(255),
                UNIQUE(block_id, floor_id, work_item_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                line_user_id VARCHAR(255) UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                id SERIAL PRIMARY KEY,
                line_user_id VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_permissions (
                id SERIAL PRIMARY KEY,
                allowed_user_id INTEGER NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(allowed_user_id, project_id)
            )
        ''')
    else:
        # SQLite 建立資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(project_id, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS floors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                UNIQUE(project_id, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(project_id, category, name)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_id INTEGER NOT NULL,
                floor_id INTEGER NOT NULL,
                work_item_id INTEGER NOT NULL,
                status INTEGER NOT NULL DEFAULT 0,
                updated_by TEXT,
                updated_at TEXT,
                FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
                FOREIGN KEY (floor_id) REFERENCES floors(id) ON DELETE CASCADE,
                FOREIGN KEY (work_item_id) REFERENCES work_items(id) ON DELETE CASCADE,
                UNIQUE(block_id, floor_id, work_item_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_user_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                allowed_user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                FOREIGN KEY (allowed_user_id) REFERENCES allowed_users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(allowed_user_id, project_id)
            )
        ''')

    # === 自動數據結構遷移 (Migration) ===
    # 寫入預設專案
    cursor.execute("SELECT COUNT(*) FROM projects")
    if cursor.fetchone()[0] == 0:
        if DATABASE_URL:
            # PostgreSQL
            cursor.execute("INSERT INTO projects (id, name) VALUES (1, '預設建案') ON CONFLICT DO NOTHING")
            # 重設序列起點
            try:
                cursor.execute("SELECT setval('projects_id_seq', 1)")
            except Exception:
                pass
        else:
            cursor.execute("INSERT OR IGNORE INTO projects (id, name) VALUES (1, '預設建案')")

    # 為現有表新增 project_id 欄位
    add_project_id_column_if_not_exists(cursor, conn, "blocks")
    add_project_id_column_if_not_exists(cursor, conn, "floors")
    add_project_id_column_if_not_exists(cursor, conn, "work_items")

    # 將現有的 null 欄位更新為 1 (預設建案)
    cursor.execute("UPDATE blocks SET project_id = 1 WHERE project_id IS NULL")
    cursor.execute("UPDATE floors SET project_id = 1 WHERE project_id IS NULL")
    cursor.execute("UPDATE work_items SET project_id = 1 WHERE project_id IS NULL")

    # 執行約束遷移（自適應資料庫引擎）
    if not DATABASE_URL:
        # SQLite Constraint Migration
        # 檢查 blocks 是否需要更新約束
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='blocks'")
        sql_blocks = cursor.fetchone()[0]
        if "UNIQUE(project_id" not in sql_blocks and "UNIQUE (project_id" not in sql_blocks:
            cursor.execute("ALTER TABLE blocks RENAME TO old_blocks")
            cursor.execute('''
                CREATE TABLE blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    UNIQUE(project_id, name)
                )
            ''')
            cursor.execute("INSERT INTO blocks (id, project_id, name) SELECT id, COALESCE(project_id, 1), name FROM old_blocks")
            cursor.execute("DROP TABLE old_blocks")

        # 檢查 floors 是否需要更新約束
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='floors'")
        sql_floors = cursor.fetchone()[0]
        if "UNIQUE(project_id" not in sql_floors and "UNIQUE (project_id" not in sql_floors:
            cursor.execute("ALTER TABLE floors RENAME TO old_floors")
            cursor.execute('''
                CREATE TABLE floors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    UNIQUE(project_id, name)
                )
            ''')
            cursor.execute("INSERT INTO floors (id, project_id, name) SELECT id, COALESCE(project_id, 1), name FROM old_floors")
            cursor.execute("DROP TABLE old_floors")

        # 檢查 work_items 是否需要更新約束
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='work_items'")
        sql_work = cursor.fetchone()[0]
        if "UNIQUE(project_id" not in sql_work and "UNIQUE (project_id" not in sql_work:
            cursor.execute("ALTER TABLE work_items RENAME TO old_work_items")
            cursor.execute('''
                CREATE TABLE work_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(project_id, category, name)
                )
            ''')
            cursor.execute("INSERT INTO work_items (id, project_id, category, name) SELECT id, COALESCE(project_id, 1), category, name FROM old_work_items")
            cursor.execute("DROP TABLE old_work_items")
    else:
        # PostgreSQL Constraint Migration
        # 變更 blocks 唯一約束
        cursor.execute('''
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name='blocks' AND constraint_name='blocks_project_id_name_key'
        ''')
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE blocks DROP CONSTRAINT IF EXISTS blocks_name_key")
            cursor.execute("ALTER TABLE blocks ADD CONSTRAINT blocks_project_id_name_key UNIQUE (project_id, name)")

        # 變更 floors 唯一約束
        cursor.execute('''
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name='floors' AND constraint_name='floors_project_id_name_key'
        ''')
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE floors DROP CONSTRAINT IF EXISTS floors_name_key")
            cursor.execute("ALTER TABLE floors ADD CONSTRAINT floors_project_id_name_key UNIQUE (project_id, name)")

        # 變更 work_items 唯一約束
        cursor.execute('''
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name='work_items' AND constraint_name='work_items_project_id_category_name_key'
        ''')
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE work_items DROP CONSTRAINT IF EXISTS work_items_category_name_key")
            cursor.execute("ALTER TABLE work_items ADD CONSTRAINT work_items_project_id_category_name_key UNIQUE (project_id, category, name)")

    # 定義新版工項清單 (分類與項目名稱均比對圖片，並已去除浴室、外牆重複項目)
    new_default_work_items = [
        ("結構", "灌漿"),
        ("壁磚", "主浴30*60"),
        ("壁磚", "次浴30*60"),
        ("壁磚", "次浴15*75"),
        ("壁磚", "廊道30*60"),
        ("壁磚", "梯廳60*60"),
        ("壁磚", "二丁黑"),
        ("壁磚", "二丁白"),
        ("地磚", "廁所30*30"),
        ("地磚", "樓梯20*20"),
        ("地磚", "樓梯20*27"),
        ("地磚", "導盲20*20"),
        ("地磚", "陽台25*25"),
        ("地磚", "陽台15*45"),
        ("地磚", "拋光60*60"),
        ("地磚", "拋光80*80"),
        ("門檻", "樓梯"),
        ("門檻", "玄關"),
        ("門檻", "崁縫"),
        ("門檻", "打石"),
        ("門檻", "打底"),
        ("門檻", "粉光"),
        ("浴室", "清潔"),
        ("浴室", "防水"),
        ("浴室", "試水"),
        ("浴室", "貼面磚"),
        ("浴室", "抹縫"),
        ("浴室", "地磚"),
        ("外牆", "層縫"),
        ("外牆", "貼條"),
        ("外牆", "打石"),
        ("外牆", "打底"),
        ("外牆", "貼磚"),
        ("隔間", "骨架"),
        ("隔間", "單板"),
        ("隔間", "水電"),
        ("隔間", "封版"),
        ("隔間", "灌漿"),
        ("隔間", "擊釘"),
        ("隔間", "批土"),
        ("門窗", "拉線"),
        ("門窗", "立窗"),
        ("門窗", "崁縫"),
        ("門窗", "防水"),
        ("內牆", "貼條"),
        ("內牆", "立門"),
        ("內牆", "崁縫"),
        ("內牆", "打石"),
        ("內牆", "打底"),
        ("內牆", "粉光")
    ]

    # === 自動數據結構遷移 (判斷是否需要載入預設項目) ===
    # 檢查是否需要更新工項結構 (如果舊的 '油漆' 或 '鋼筋綁紮' 存在，則重設工項與進度)
    try:
        cursor.execute("SELECT COUNT(*) FROM work_items WHERE category = '油漆' OR name = '鋼筋綁紮'")
        has_old_data = cursor.fetchone()[0] > 0
    except Exception:
        has_old_data = False
        conn.commit()
        cursor = conn.cursor()
        
    if has_old_data:
        cursor.execute("DROP TABLE IF EXISTS progress")
        cursor.execute("DROP TABLE IF EXISTS work_items")
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_items (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    category VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    UNIQUE(project_id, category, name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS progress (
                    id SERIAL PRIMARY KEY,
                    block_id INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
                    floor_id INTEGER NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
                    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
                    status INTEGER NOT NULL DEFAULT 0,
                    updated_by VARCHAR(255),
                    updated_at VARCHAR(255),
                    UNIQUE(block_id, floor_id, work_item_id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(project_id, category, name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    block_id INTEGER NOT NULL,
                    floor_id INTEGER NOT NULL,
                    work_item_id INTEGER NOT NULL,
                    status INTEGER NOT NULL DEFAULT 0,
                    updated_by TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
                    FOREIGN KEY (floor_id) REFERENCES floors(id) ON DELETE CASCADE,
                    FOREIGN KEY (work_item_id) REFERENCES work_items(id) ON DELETE CASCADE,
                    UNIQUE(block_id, floor_id, work_item_id)
                )
            ''')
        # 直接填充新版工項 (綁定為專案 1)
        for cat, name in new_default_work_items:
            cursor.execute("INSERT INTO work_items (project_id, category, name) VALUES (1, ?, ?)", (cat, name))
    
    # 寫入第一個預設管理員（方便測試）
    if INIT_ADMIN_ID:
        cursor.execute('''
            INSERT OR IGNORE INTO admins (line_user_id) 
            VALUES (?)
        ''', (INIT_ADMIN_ID,))
        
    # 將現有所有工程師預設開放預設建案 (id = 1) 的權限
    if DATABASE_URL:
        cursor.execute('''
            INSERT INTO project_permissions (allowed_user_id, project_id)
            SELECT id, 1 FROM allowed_users
            ON CONFLICT DO NOTHING
        ''')
    else:
        cursor.execute('''
            INSERT OR IGNORE INTO project_permissions (allowed_user_id, project_id)
            SELECT id, 1 FROM allowed_users
        ''')
    
    # 寫入預設測試資料 (若 blocks 為空，通常是首次初始化)
    cursor.execute("SELECT COUNT(*) FROM blocks")
    if cursor.fetchone()[0] == 0:
        # 新增預設棟別
        default_blocks = [("A棟",), ("B棟",)]
        for b in default_blocks:
            cursor.execute("INSERT INTO blocks (project_id, name) VALUES (1, ?)", b)
        
        # 新增預設樓層
        default_floors = [("1F",), ("2F",), ("3F",), ("4F",), ("5F",)]
        for f in default_floors:
            cursor.execute("INSERT INTO floors (project_id, name) VALUES (1, ?)", f)
        
        # 新增預設工項
        for cat, name in new_default_work_items:
            cursor.execute("INSERT INTO work_items (project_id, category, name) VALUES (1, ?, ?)", (cat, name))
        
    if not DATABASE_URL:
        cursor.execute("PRAGMA foreign_keys = ON;")
        
    conn.commit()
    conn.close()

# 初始化資料庫
init_db()

# =====================================================================
# 權限驗證裝飾器/輔助函式
# =====================================================================
def is_admin_user(line_user_id):
    if not line_user_id:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE line_user_id = ?", (line_user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def is_allowed_user(line_user_id):
    if not line_user_id:
        return False
    # 管理員預設擁有使用者權限
    if is_admin_user(line_user_id):
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM allowed_users WHERE line_user_id = ?", (line_user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def is_user_allowed_project(line_user_id, project_id):
    if not line_user_id:
        return False
    if is_admin_user(line_user_id):
        return True
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # 檢查該使用者是否在 allowed_users，且擁有該 project_id 的權限
    cursor.execute('''
        SELECT 1 FROM allowed_users u
        JOIN project_permissions p ON u.id = p.allowed_user_id
        WHERE u.line_user_id = ? AND p.project_id = ?
    ''', (line_user_id, project_id))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_user_allowed_projects(line_user_id):
    if not line_user_id:
        return []
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_admin_user(line_user_id):
        # 管理員有權限看所有專案
        cursor.execute("SELECT id, name FROM projects ORDER BY id")
        projects = [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    else:
        # 一般工程師只能看被分配的專案
        cursor.execute('''
            SELECT p.id, p.name FROM projects p
            JOIN project_permissions perm ON p.id = perm.project_id
            JOIN allowed_users u ON perm.allowed_user_id = u.id
            WHERE u.line_user_id = ?
            ORDER BY p.id
        ''', (line_user_id,))
        projects = [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
        
    conn.close()
    return projects

# =====================================================================
# 頁面路由
# =====================================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# =====================================================================
# 前端 API 路由
# =====================================================================

# 1-1. 驗證是否為已授權工程師或管理員 (首頁白名單安全鎖)
@app.route('/api/is_allowed', methods=['GET'])
def check_allowed():
    user_id = request.args.get('userId')
    is_allowed = is_allowed_user(user_id)
    return jsonify({"is_allowed": is_allowed})

# 1. 驗證是否為管理員
@app.route('/api/is_admin', methods=['GET'])
def check_admin():
    user_id = request.args.get('userId')
    is_admin = is_admin_user(user_id)
    return jsonify({"is_admin": is_admin})

# 2. 獲取首頁初始化資料（棟別、樓層、工項及進度表）
@app.route('/api/init_data', methods=['GET'])
def get_init_data():
    user_id = request.args.get('userId')
    project_id = request.args.get('projectId')
    
    if not user_id:
        return jsonify({"error": "缺少使用者ID"}), 400
        
    # 1. 取得該使用者有權限存取的所有專案
    allowed_projects = get_user_allowed_projects(user_id)
    if not allowed_projects:
        return jsonify({
            "error": "您尚未被分配到任何建案，請聯絡管理員。",
            "blocks": [],
            "floors": [],
            "work_items": [],
            "progress": {},
            "allowed_projects": [],
            "current_project_id": None
        }), 200
        
    # 2. 決定當前載入的專案
    current_project_id = None
    if project_id:
        # 如果前端指定了專案，驗證是否有權限
        if is_user_allowed_project(user_id, int(project_id)):
            current_project_id = int(project_id)
            
    if not current_project_id:
        # 預設為該使用者被授權的第一個專案
        current_project_id = allowed_projects[0]["id"]
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 取得當前專案的棟別
    blocks_rows = cursor.execute("SELECT id, name FROM blocks WHERE project_id = ? ORDER BY id", (current_project_id,)).fetchall()
    blocks = [{"id": r["id"], "name": r["name"]} for r in blocks_rows]
    
    # 取得當前專案的樓層
    floors_rows = cursor.execute("SELECT id, name FROM floors WHERE project_id = ? ORDER BY id", (current_project_id,)).fetchall()
    floors = [{"id": r["id"], "name": r["name"]} for r in floors_rows]
    
    # 取得當前專案的工項
    work_items_rows = cursor.execute("SELECT id, category, name FROM work_items WHERE project_id = ? ORDER BY id", (current_project_id,)).fetchall()
    work_items = [{"id": r["id"], "category": r["category"], "name": r["name"]} for r in work_items_rows]
    
    # 取得當前專案下所有進度 (當 progress 的 block_id 關聯到屬於此專案的 blocks)
    progress_rows = cursor.execute('''
        SELECT p.block_id, p.floor_id, p.work_item_id, p.status, p.updated_by, p.updated_at 
        FROM progress p
        JOIN blocks b ON p.block_id = b.id
        WHERE b.project_id = ?
    ''', (current_project_id,)).fetchall()
    
    # 格式化進度資料為字典
    progress_map = {}
    for r in progress_rows:
        key = f"{r['block_id']}_{r['floor_id']}_{r['work_item_id']}"
        progress_map[key] = {
            "status": r["status"],
            "updated_by": r["updated_by"],
            "updated_at": r["updated_at"]
        }
        
    conn.close()
    
    return jsonify({
        "blocks": blocks,
        "floors": floors,
        "work_items": work_items,
        "progress": progress_map,
        "allowed_projects": allowed_projects,
        "current_project_id": current_project_id
    })

# 3. 切換儲存格狀態 (0 <-> 1)
@app.route('/api/progress/toggle', methods=['POST'])
def toggle_progress():
    data = request.get_json()
    if not data:
        return jsonify({"error": "缺少請求資料"}), 400
        
    block_id = data.get('block_id')
    floor_id = data.get('floor_id')
    work_item_id = data.get('work_item_id')
    user_id = data.get('user_id')
    user_name = data.get('user_name', '未命名')
    
    if not all([block_id, floor_id, work_item_id, user_id]):
        return jsonify({"error": "參數不完整"}), 400
        
    # 驗證使用者對該 block 所屬專案是否有權限
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT project_id FROM blocks WHERE id = ?", (block_id,))
    block_row = cursor.fetchone()
    if not block_row:
        conn.close()
        return jsonify({"error": "該棟別不存在"}), 400
        
    project_id = block_row[0]
    if not is_user_allowed_project(user_id, project_id):
        conn.close()
        return jsonify({"error": "您沒有此建案的登記權限"}), 403
        
    # 查詢現有狀態
    cursor.execute('''
        SELECT status FROM progress 
        WHERE block_id = ? AND floor_id = ? AND work_item_id = ?
    ''', (block_id, floor_id, work_item_id))
    row = cursor.fetchone()
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if row is None:
        # 原本無資料，直接設為已完成 (1)
        cursor.execute('''
            INSERT INTO progress (block_id, floor_id, work_item_id, status, updated_by, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (block_id, floor_id, work_item_id, user_name, now_str))
        new_status = 1
    else:
        # 原本有資料，切換狀態 (1 -> 0, 0 -> 1)
        new_status = 0 if row[0] == 1 else 1
        cursor.execute('''
            UPDATE progress 
            SET status = ?, updated_by = ?, updated_at = ?
            WHERE block_id = ? AND floor_id = ? AND work_item_id = ?
        ''', (new_status, user_name, now_str, block_id, floor_id, work_item_id))
        
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True, 
        "status": new_status,
        "updated_by": user_name,
        "updated_at": now_str
    })

# =====================================================================
# 管理員後台專屬 API 路由 (均做權限比對)
# =====================================================================

# 1. 取得後台管理的完整設定清單
@app.route('/api/admin/config', methods=['GET'])
def get_admin_config():
    user_id = request.args.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足，拒絕存取"}), 403
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 獲取專案清單
    projects = [{"id": r[0], "name": r[1]} for r in cursor.execute("SELECT id, name FROM projects ORDER BY id").fetchall()]
    
    # 獲取各專案底下的棟別、樓層、工項
    blocks = [{"id": r["id"], "project_id": r["project_id"], "name": r["name"]} for r in cursor.execute("SELECT id, project_id, name FROM blocks ORDER BY id").fetchall()]
    floors = [{"id": r["id"], "project_id": r["project_id"], "name": r["name"]} for r in cursor.execute("SELECT id, project_id, name FROM floors ORDER BY id").fetchall()]
    work_items = [{"id": r["id"], "project_id": r["project_id"], "category": r["category"], "name": r["name"]} for r in cursor.execute("SELECT id, project_id, category, name FROM work_items ORDER BY id").fetchall()]
    admins = [{"id": r["id"], "line_user_id": r["line_user_id"]} for r in cursor.execute("SELECT id, line_user_id FROM admins ORDER BY id").fetchall()]
    
    # 獲取所有工程師對應的開放專案關聯
    cursor.execute("SELECT allowed_user_id, project_id FROM project_permissions")
    perms = cursor.fetchall()
    user_projects_map = {}
    for user_id_val, proj_id in perms:
        if user_id_val not in user_projects_map:
            user_projects_map[user_id_val] = []
        user_projects_map[user_id_val].append(proj_id)
        
    allowed_users = []
    allowed_users_rows = cursor.execute("SELECT id, line_user_id, name FROM allowed_users ORDER BY id").fetchall()
    for r in allowed_users_rows:
        allowed_users.append({
            "id": r["id"],
            "line_user_id": r["line_user_id"],
            "name": r["name"],
            "project_ids": user_projects_map.get(r["id"], [])
        })
    
    conn.close()
    return jsonify({
        "projects": projects,
        "blocks": blocks,
        "floors": floors,
        "work_items": work_items,
        "admins": admins,
        "allowed_users": allowed_users
    })

# 1-2. 新增建案
@app.route('/api/admin/add_project', methods=['POST'])
def add_project():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    name = data.get('name', '').strip()
    copy_from_project_id = data.get('copyFromProjectId')
    
    if not name:
        return jsonify({"error": "建案名稱不能為空"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. 插入新專案
        cursor.execute("INSERT INTO projects (name) VALUES (?)", (name,))
        
        # 2. 獲取新專案的 ID
        if DATABASE_URL:
            cursor.execute("SELECT LASTVAL()")
            new_project_id = cursor.fetchone()[0]
        else:
            new_project_id = cursor.lastrowid
            
        # 3. 如果需要複製既有建案的配置
        if copy_from_project_id:
            copy_from_id = int(copy_from_project_id)
            
            # A. 複製「棟別」
            cursor.execute("SELECT name FROM blocks WHERE project_id = ?", (copy_from_id,))
            blocks_to_copy = cursor.fetchall()
            for b in blocks_to_copy:
                cursor.execute("INSERT INTO blocks (project_id, name) VALUES (?, ?)", (new_project_id, b[0]))
                
            # B. 複製「樓層」
            cursor.execute("SELECT name FROM floors WHERE project_id = ?", (copy_from_id,))
            floors_to_copy = cursor.fetchall()
            for f in floors_to_copy:
                cursor.execute("INSERT INTO floors (project_id, name) VALUES (?, ?)", (new_project_id, f[0]))
                
            # C. 複製「施工工項與分類」
            cursor.execute("SELECT category, name FROM work_items WHERE project_id = ?", (copy_from_id,))
            items_to_copy = cursor.fetchall()
            for item in items_to_copy:
                cursor.execute("INSERT INTO work_items (project_id, category, name) VALUES (?, ?, ?)", (new_project_id, item[0], item[1]))
                
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        conn.close()
        return jsonify({"error": "該建案名稱已存在"}), 400
    except Exception as e:
        conn.close()
        return jsonify({"error": f"建立失敗: {str(e)}"}), 500

# 1-4. 編輯建案名稱
@app.route('/api/admin/edit_project', methods=['POST'])
def edit_project():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    project_id = data.get('id')
    name = data.get('name', '').strip()
    
    if not project_id or not name:
        return jsonify({"error": "參數不完整"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "建案名稱已存在"}), 400

# 2-1. 編輯棟別名稱
@app.route('/api/admin/edit_block', methods=['POST'])
def edit_block():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    block_id = data.get('id')
    name = data.get('name', '').strip()
    
    if not block_id or not name:
        return jsonify({"error": "參數不完整"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 取得當前棟別的專案 ID
        cursor.execute("SELECT project_id FROM blocks WHERE id = ?", (block_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "找不到此棟別"}), 404
        project_id = row[0]
        
        cursor.execute("UPDATE blocks SET name = ? WHERE id = ?", (name, block_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案中已存在相同名稱的棟別"}), 400

# 4-1. 編輯樓層名稱
@app.route('/api/admin/edit_floor', methods=['POST'])
def edit_floor():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    floor_id = data.get('id')
    name = data.get('name', '').strip()
    
    if not floor_id or not name:
        return jsonify({"error": "參數不完整"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 取得當前樓層的專案 ID
        cursor.execute("SELECT project_id FROM floors WHERE id = ?", (floor_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "找不到此樓層"}), 404
        project_id = row[0]
        
        cursor.execute("UPDATE floors SET name = ? WHERE id = ?", (name, floor_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案中已存在相同名稱的樓層"}), 400

# 6-1. 編輯工項與分類名稱
@app.route('/api/admin/edit_work_item', methods=['POST'])
def edit_work_item():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    work_item_id = data.get('id')
    category = data.get('category', '').strip()
    name = data.get('name', '').strip()
    
    if not work_item_id or not category or not name:
        return jsonify({"error": "參數不完整"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 取得當前工項的專案 ID
        cursor.execute("SELECT project_id FROM work_items WHERE id = ?", (work_item_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "找不到此工項"}), 404
        project_id = row[0]
        
        cursor.execute("UPDATE work_items SET category = ?, name = ? WHERE id = ?", (category, name, work_item_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案此分類中已存在相同名稱的工項"}), 400

# 1-3. 刪除建案
@app.route('/api/admin/delete_project', methods=['POST'])
def delete_project():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    project_id = data.get('id')
    if not project_id:
        return jsonify({"error": "缺少建案 ID"}), 400
        
    if int(project_id) == 1:
        return jsonify({"error": "預設建案為系統保留，無法刪除"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 2. 新增棟別
@app.route('/api/admin/add_block', methods=['POST'])
def add_block():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    name = data.get('name', '').strip()
    project_id = data.get('projectId')
    
    if not name or not project_id:
        return jsonify({"error": "棟別名稱與專案 ID 不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO blocks (project_id, name) VALUES (?, ?)", (project_id, name))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案中已存在此棟別"}), 400

# 3. 刪除棟別
@app.route('/api/admin/delete_block', methods=['POST'])
def delete_block():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    block_id = data.get('id')
    if not block_id:
        return jsonify({"error": "缺少棟別 ID"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 4. 新增樓層
@app.route('/api/admin/add_floor', methods=['POST'])
def add_floor():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    name = data.get('name', '').strip()
    project_id = data.get('projectId')
    
    if not name or not project_id:
        return jsonify({"error": "樓層名稱與專案 ID 不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO floors (project_id, name) VALUES (?, ?)", (project_id, name))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案中已存在此樓層"}), 400

# 5. 刪除樓層
@app.route('/api/admin/delete_floor', methods=['POST'])
def delete_floor():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    floor_id = data.get('id')
    if not floor_id:
        return jsonify({"error": "缺少樓層 ID"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM floors WHERE id = ?", (floor_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 6. 新增工項
@app.route('/api/admin/add_work_item', methods=['POST'])
def add_work_item():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    category = data.get('category', '').strip()
    name = data.get('name', '').strip()
    project_id = data.get('projectId')
    
    if not category or not name or not project_id:
        return jsonify({"error": "工種分類、工項名稱與專案 ID 均不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO work_items (project_id, category, name) VALUES (?, ?, ?)", (project_id, category, name))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該建案此分類中已存在此工項"}), 400

# 7. 刪除工項
@app.route('/api/admin/delete_work_item', methods=['POST'])
def delete_work_item():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    work_item_id = data.get('id')
    if not work_item_id:
        return jsonify({"error": "缺少工項 ID"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM work_items WHERE id = ?", (work_item_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 8. 新增管理員
@app.route('/api/admin/add_admin', methods=['POST'])
def add_admin():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    line_user_id = data.get('line_user_id', '').strip()
    if not line_user_id:
        return jsonify({"error": "LINE User ID 不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admins (line_user_id) VALUES (?)", (line_user_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該管理員已在名單中"}), 400

# 9. 刪除管理員
@app.route('/api/admin/delete_admin', methods=['POST'])
def delete_admin():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    admin_id = data.get('id')
    if not admin_id:
        return jsonify({"error": "缺少管理員 ID"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 確保不會刪除當前操作的管理員自己，防止鎖死
    cursor.execute("SELECT line_user_id FROM admins WHERE id = ?", (admin_id,))
    row = cursor.fetchone()
    if row and row['line_user_id'] == user_id:
        return jsonify({"error": "無法刪除自己"}), 400
        
    cursor.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# 10. 新增/修改 授權工程師 (白名單)
@app.route('/api/admin/add_allowed_user', methods=['POST'])
def add_allowed_user():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    line_user_id = data.get('line_user_id', '').strip()
    name = data.get('name', '').strip()
    project_ids = data.get('project_ids', [])
    
    if not line_user_id or not name:
        return jsonify({"error": "LINE User ID 與工程師姓名均不能為空"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. 檢查是否已存在該使用者
        cursor.execute("SELECT id FROM allowed_users WHERE line_user_id = ?", (line_user_id,))
        user_row = cursor.fetchone()
        
        if user_row:
            allowed_user_id = user_row[0]
            cursor.execute("UPDATE allowed_users SET name = ? WHERE id = ?", (name, allowed_user_id))
        else:
            cursor.execute("INSERT INTO allowed_users (line_user_id, name) VALUES (?, ?)", (line_user_id, name))
            if DATABASE_URL:
                cursor.execute("SELECT LASTVAL()")
                allowed_user_id = cursor.fetchone()[0]
            else:
                allowed_user_id = cursor.lastrowid
                
        # 2. 更新專案權限
        cursor.execute("DELETE FROM project_permissions WHERE allowed_user_id = ?", (allowed_user_id,))
        for p_id in project_ids:
            cursor.execute("INSERT INTO project_permissions (allowed_user_id, project_id) VALUES (?, ?)", (allowed_user_id, p_id))
            
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        conn.close()
        return jsonify({"error": f"資料庫寫入失敗: {str(e)}"}), 500

# 11. 刪除授權工程師 (白名單)
@app.route('/api/admin/delete_allowed_user', methods=['POST'])
def delete_allowed_user():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    allowed_id = data.get('id')
    if not allowed_id:
        return jsonify({"error": "缺少授權 ID"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM allowed_users WHERE id = ?", (allowed_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
