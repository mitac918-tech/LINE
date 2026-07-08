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

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL 建立資料表 (使用 SERIAL 自增與 VARCHAR 類型)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS floors (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_items (
                id SERIAL PRIMARY KEY,
                category VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                UNIQUE(category, name)
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
    else:
        # SQLite 建立資料表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS floors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(category, name)
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

    # === 自動數據結構遷移 ===
    # 檢查是否需要更新工項結構 (如果舊的 '油漆' 或 '鋼筋綁紮' 存在，則重設工項與進度)
    # 由於 work_items 在新庫第一次啟動時可能尚未被建立（尤其是在 PostgreSQL 中），我們先確認該表是否存在，再進行查詢
    try:
        cursor.execute("SELECT COUNT(*) FROM work_items WHERE category = '油漆' OR name = '鋼筋綁紮'")
        has_old_data = cursor.fetchone()[0] > 0
    except Exception:
        has_old_data = False
        # 如果發生例外（代表 work_items 尚未建立，或資料庫為全新），我們藉由 commit 重置交易狀態
        conn.commit()
        cursor = conn.cursor()
        
    if has_old_data:
        cursor.execute("DROP TABLE IF EXISTS progress")
        cursor.execute("DROP TABLE IF EXISTS work_items")
        if DATABASE_URL:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS work_items (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    UNIQUE(category, name)
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
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(category, name)
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
        # 直接填充新版工項
        cursor.executemany("INSERT INTO work_items (category, name) VALUES (?, ?)", new_default_work_items)
    
    # 寫入第一個預設管理員（方便測試）
    if INIT_ADMIN_ID:
        cursor.execute('''
            INSERT OR IGNORE INTO admins (line_user_id) 
            VALUES (?)
        ''', (INIT_ADMIN_ID,))
    
    # 寫入預設測試資料 (若 blocks 為空，通常是首次初始化)
    cursor.execute("SELECT COUNT(*) FROM blocks")
    if cursor.fetchone()[0] == 0:
        # 新增預設棟別
        default_blocks = [("A棟",), ("B棟",)]
        cursor.executemany("INSERT INTO blocks (name) VALUES (?)", default_blocks)
        
        # 新增預設樓層
        default_floors = [("1F",), ("2F",), ("3F",), ("4F",), ("5F",)]
        cursor.executemany("INSERT INTO floors (name) VALUES (?)", default_floors)
        
        # 新增預設工項
        cursor.executemany("INSERT INTO work_items (category, name) VALUES (?, ?)", new_default_work_items)
        
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
    # 管理員預設擁有使用者權限，無須重複加白名單
    if is_admin_user(line_user_id):
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM allowed_users WHERE line_user_id = ?", (line_user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 取得棟別
    blocks_rows = cursor.execute("SELECT id, name FROM blocks ORDER BY id").fetchall()
    blocks = [{"id": r["id"], "name": r["name"]} for r in blocks_rows]
    
    # 取得樓層
    floors_rows = cursor.execute("SELECT id, name FROM floors ORDER BY id").fetchall()
    floors = [{"id": r["id"], "name": r["name"]} for r in floors_rows]
    
    # 取得工項 (變更為 ORDER BY id，以遵循資料庫寫入順序，確保結構置頂與正確排序)
    work_items_rows = cursor.execute("SELECT id, category, name FROM work_items ORDER BY id").fetchall()
    work_items = [{"id": r["id"], "category": r["category"], "name": r["name"]} for r in work_items_rows]
    
    # 取得所有進度
    progress_rows = cursor.execute("SELECT block_id, floor_id, work_item_id, status, updated_by, updated_at FROM progress").fetchall()
    
    # 格式化進度資料為字典，便於前端以 "block_id_floor_id_work_item_id" 鍵值快速查找
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
        "progress": progress_map
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
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
        new_status = 0 if row['status'] == 1 else 1
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
    
    blocks = [{"id": r["id"], "name": r["name"]} for r in cursor.execute("SELECT id, name FROM blocks ORDER BY id").fetchall()]
    floors = [{"id": r["id"], "name": r["name"]} for r in cursor.execute("SELECT id, name FROM floors ORDER BY id").fetchall()]
    work_items = [{"id": r["id"], "category": r["category"], "name": r["name"]} for r in cursor.execute("SELECT id, category, name FROM work_items ORDER BY id").fetchall()]
    admins = [{"id": r["id"], "line_user_id": r["line_user_id"]} for r in cursor.execute("SELECT id, line_user_id FROM admins ORDER BY id").fetchall()]
    allowed_users = [{"id": r["id"], "line_user_id": r["line_user_id"], "name": r["name"]} for r in cursor.execute("SELECT id, line_user_id, name FROM allowed_users ORDER BY id").fetchall()]
    
    conn.close()
    return jsonify({
        "blocks": blocks,
        "floors": floors,
        "work_items": work_items,
        "admins": admins,
        "allowed_users": allowed_users
    })

# 2. 新增棟別
@app.route('/api/admin/add_block', methods=['POST'])
def add_block():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "棟別名稱不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO blocks (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該棟別已存在"}), 400

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
    if not name:
        return jsonify({"error": "樓層名稱不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO floors (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該樓層已存在"}), 400

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
    if not category or not name:
        return jsonify({"error": "工種分類與工項名稱均不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO work_items (category, name) VALUES (?, ?)", (category, name))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該工項已存在於此分類中"}), 400

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

# 10. 新增授權工程師 (白名單)
@app.route('/api/admin/add_allowed_user', methods=['POST'])
def add_allowed_user():
    data = request.get_json()
    user_id = data.get('userId')
    if not is_admin_user(user_id):
        return jsonify({"error": "權限不足"}), 403
        
    line_user_id = data.get('line_user_id', '').strip()
    name = data.get('name', '').strip()
    if not line_user_id or not name:
        return jsonify({"error": "LINE User ID 與工程師姓名均不能為空"}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO allowed_users (line_user_id, name) VALUES (?, ?)", (line_user_id, name))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except DBIntegrityError:
        return jsonify({"error": "該 User ID 已在授權名單中"}), 400

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
