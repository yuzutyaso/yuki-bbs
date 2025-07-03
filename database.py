import sqlite3

DATABASE = 'board.db' # データベースファイル名

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # posts テーブルを作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            hashed_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            topic TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # user_roles テーブルを作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            hashed_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 管理者ID（admin）の初期データを挿入 (例: シード 'my_admin_seed' から生成されたハッシュID)
    # ここにあなたの管理者シードから生成したhashed_idと、ロール'admin'を設定してください。
    # 例: '@e0e0a1b' は generate_hashed_id('my_admin_seed') の結果です。
    admin_hashed_id = '@e0e0a1b' # <--- ここにあなたの管理者ハッシュIDを設定
    admin_role = 'admin' # <--- ここに管理者のロールを設定 ('admin', 'manager', 'moderator'など)

    try:
        cursor.execute("INSERT INTO user_roles (hashed_id, role) VALUES (?, ?)", (admin_hashed_id, admin_role))
        print(f"初期管理者 {admin_hashed_id} ({admin_role}) をuser_rolesに追加しました。")
    except sqlite3.IntegrityError:
        print(f"管理者 {admin_hashed_id} は既にuser_rolesに存在します。")
    except Exception as e:
        print(f"管理者データの挿入中にエラーが発生しました: {e}")

    conn.commit()
    conn.close()
    print(f"データベース {DATABASE} が初期化されました。")

if __name__ == '__main__':
    init_db()
