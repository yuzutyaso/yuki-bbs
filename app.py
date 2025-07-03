from flask import Flask, request, jsonify, render_template, make_response
import sqlite3
import hashlib
import time
import os
import json # JSONファイルを直接読み書きしないが、互換性のため

# .env ファイルの読み込み (今回は使わないが、将来の外部サービス連携時に便利)
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, static_folder='static')
DATABASE = 'board.db' # データベースファイル名

# 投稿制限のための変数: シードごとの最終投稿時間を記録
request_timestamps = {}

# --- 権限レベルの定義 ---
ROLES = {
    'BLUE': 'blue',
    'SPEAKER': 'speaker',
    'MANAGER': 'manager',
    'MODERATOR': 'moderator',
    'SUMMIT': 'summit',
    'ADMIN': 'admin'
}

ROLE_HIERARCHY = {
    ROLES['BLUE']: 0,
    ROLES['SPEAKER']: 10,
    ROLES['MANAGER']: 20,
    ROLES['MODERATOR']: 30,
    ROLES['SUMMIT']: 40,
    ROLES['ADMIN']: 50
}

# --- ヘルパー関数 ---

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row # これにより、辞書形式で結果を取得できる
    return conn

def generate_hashed_id(seed):
    """シードをSHA-256でハッシュ化し、先頭7文字に'@'を付けたIDを生成します。"""
    sha256 = hashlib.sha256()
    sha256.update(seed.encode('utf-8'))
    return '@' + sha256.hexdigest()[:7]

async def get_user_role(hashed_id):
    """ユーザーの権限レベルを取得します。user_roles テーブルから取得し、存在しなければ 'blue' (青ID) を返します。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT role FROM user_roles WHERE hashed_id = ?', (hashed_id,))
        result = cursor.fetchone()
        if result:
            return result['role']
        return ROLES['BLUE'] # デフォルトは青ID
    except Exception as e:
        print(f"ユーザー権限の取得に失敗しました (ID: {hashed_id}): {e}")
        return ROLES['BLUE']
    finally:
        conn.close()

async def has_permission(hashed_id, required_role):
    """指定されたhashed_idのユーザーが、要求されたrole以上の権限を持っているかチェックします。"""
    user_role = await get_user_role(hashed_id)
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)

def prune_posts():
    """投稿を整理し、最新の3件のみを残します。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 最新の3件のIDを取得し、それ以外の投稿を削除します。
        cursor.execute("SELECT id FROM posts ORDER BY created_at DESC LIMIT 3")
        latest_ids = [row['id'] for row in cursor.fetchall()]

        if latest_ids:
            # SQLのIN句に渡すためのプレースホルダーを生成
            placeholders = ','.join('?' for _ in latest_ids)
            cursor.execute(f"DELETE FROM posts WHERE id NOT IN ({placeholders})", latest_ids)
            conn.commit()
            print("投稿が整理され、最新の3件のみが保持されました。")
        else:
            print("投稿がありません。整理の必要はありません。")
    except Exception as e:
        print(f"投稿の整理に失敗しました: {e}")
    finally:
        conn.close()

# --- ルーティング ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api', methods=['GET'])
async def get_posts():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, name, content, hashed_id, timestamp, topic, created_at FROM posts ORDER BY created_at DESC')
        posts_data = cursor.fetchall()
        
        posts = []
        current_topic = "トピックが設定されていません"
        
        for i, row in enumerate(posts_data):
            # NoはPython側では付与せず、フロントエンドで処理
            posts.append({
                'no': -1, # フロントエンドで付与するためダミー値
                'name': row['name'],
                'content': row['content'],
                'id': row['hashed_id'], # hashed_id を id として返す
                'time': row['timestamp'],
                'topic': row['topic']
            })
            if i == 0: # 最新の投稿からトピックを取得
                current_topic = row['topic'] if row['topic'] else current_topic

        return jsonify({'topic': current_topic, 'posts': posts})
    except Exception as e:
        print(f"データの読み込みに失敗しました: {e}")
        return jsonify({'error': "データの読み込みに失敗しました。"})
    finally:
        conn.close()

@app.route('/api', methods=['POST'])
async def post_message():
    data = request.json
    name = data.get('name')
    _pass = data.get('pass') # 'pass' は予約語なので '_pass' に変更
    content = data.get('content')

    if not all([name, _pass, content]):
        return jsonify({'error': "すべてのフィールドを入力してください。"}), 400

    current_time_ms = int(time.time() * 1000)
    if _pass in request_timestamps and (current_time_ms - request_timestamps[_pass] < 1000):
        return jsonify({'error': "同じシードからの投稿は1秒に1回までです。"}), 429
    request_timestamps[_pass] = current_time_ms

    hashed_id = generate_hashed_id(_pass)

    # クッキーに最終投稿IDを保存
    resp = make_response(jsonify({'message': "投稿が成功しました。", 'post': {}})) # 初期レスポンス作成
    resp.set_cookie('last_posted_id', hashed_id, max_age=3600 * 24 * 7) # 1週間有効
    # secure=True, httponly=True, samesite='Lax' は本番環境向け

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 現在のトピックを取得 (簡易化のため、最新の投稿のトピックを使用)
        cursor.execute('SELECT topic FROM posts ORDER BY created_at DESC LIMIT 1')
        latest_topic_row = cursor.fetchone()
        current_topic = latest_topic_row['topic'] if latest_topic_row and latest_topic_row['topic'] else "初見さんいらっしゃい　"
        
        # --- コマンド処理の分岐 ---
        if content.startswith('/'):
            command_parts = content.split(None, 1) # 最初のスペースで分割
            command = command_parts[0]
            args = command_parts[1].split() if len(command_parts) > 1 else []

            if command == '/clear':
                if not (await has_permission(hashed_id, ROLES['MODERATOR'])):
                    return jsonify({'error': "権限がありません。モデレーター以上が必要です。"}), 403
                cursor.execute('DELETE FROM posts') # SQLiteのTRUNCATEはDELETE
                conn.commit()
                return jsonify({'message': "全ての投稿を削除し、投稿番号をリセットしました。"}), 200

            elif command == '/del':
                if not (await has_permission(hashed_id, ROLES['MANAGER'])):
                    return jsonify({'error': "権限がありません。マネージャー以上が必要です。"}), 403
                if not args:
                    return jsonify({'error': "/delコマンドには投稿番号が必要です。"}), 400

                post_numbers_to_delete = [int(arg) for arg in args if arg.isdigit()]
                if not post_numbers_to_delete:
                    return jsonify({'error': "有効な投稿番号が指定されませんでした。"}), 400

                cursor.execute('SELECT id FROM posts ORDER BY created_at DESC')
                all_post_ids = [row['id'] for row in cursor.fetchall()]

                ids_to_delete = []
                for num in post_numbers_to_delete:
                    if 1 <= num <= len(all_post_ids):
                        ids_to_delete.append(all_post_ids[num - 1]) # 投稿番号は1始まり、リストインデックスは0始まり

                if ids_to_delete:
                    # SQLITEはUUIDをTEXTとして保存するため、TEXTとして比較
                    placeholders = ','.join('?' for _ in ids_to_delete)
                    cursor.execute(f"DELETE FROM posts WHERE id IN ({placeholders})", ids_to_delete)
                    conn.commit()
                    return jsonify({'message': f"投稿番号 {', '.join(map(str, post_numbers_to_delete))} の投稿を削除しました。"}), 200
                else:
                    return jsonify({'error': "指定された投稿番号が見つかりませんでした。"}), 404

            elif command == '/destroy':
                if not (await has_permission(hashed_id, ROLES['MODERATOR'])):
                    return jsonify({'error': "権限がありません。モデレーター以上が必要です。"}), 403
                if not args:
                    return jsonify({'error': "/destroyコマンドには削除条件が必要です。"}), 400

                query = ' '.join(args)
                
                # (color)オプションは現在未実装
                if query.startswith('(color)'):
                    return jsonify({'error': "現在、(color)による削除は未実装です。特定の文字またはIDで削除してください。"}), 400
                else:
                    cursor.execute("DELETE FROM posts WHERE content LIKE ? OR hashed_id LIKE ?", (f'%{query}%', f'%{query}%'))
                    conn.commit()
                    return jsonify({'message': f'"{query}"を含む投稿を一括削除しました。'}), 200
            
            else:
                return jsonify({'error': f"不明なコマンドです: {command}"}), 400

        # --- コマンドではない場合は通常の投稿として処理 ---
        new_post_id = generate_hashed_id(str(time.time())) # ユニークなIDを生成
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()) # 現在時刻をフォーマット
        
        cursor.execute(
            'INSERT INTO posts(id, name, content, hashed_id, timestamp, topic) VALUES(?, ?, ?, ?, ?, ?)',
            (new_post_id, name, content, hashed_id, now_str, current_topic)
        )
        conn.commit()

        # 投稿数が200件を超えたら自動的に整理
        cursor.execute('SELECT COUNT(*) FROM posts')
        count = cursor.fetchone()[0]
        if count > 200:
            print("投稿数が200件を超えました。投稿を整理します。")
            prune_posts()

        return jsonify({
            'message': "投稿が成功しました。",
            'post': {
                'no': -1,
                'name': name,
                'content': content,
                'id': hashed_id,
                'time': now_str,
                'topic': current_topic
            }
        }), 200

    except Exception as e:
        print(f"データの処理に失敗しました: {e}")
        return jsonify({'error': "データの処理に失敗しました。"}, 500)
    finally:
        conn.close()

@app.route('/topic', methods=['POST'])
async def update_topic():
    data = request.json
    topic = data.get('topic')
    _pass = data.get('pass')

    provided_hashed_id = None
    if _pass:
        provided_hashed_id = generate_hashed_id(_pass)
    else:
        # クッキーから取得
        provided_hashed_id = request.cookies.get('last_posted_id')

    if not topic:
        return jsonify({'error': "トピックを入力してください。"}), 400

    if not provided_hashed_id or not (await has_permission(provided_hashed_id, ROLES['MANAGER'])):
        return jsonify({'error': "権限がありません。マネージャー以上が必要です。"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE posts SET topic = ?', (topic,))
        conn.commit()
        return jsonify({'message': "トピックが更新されました。"}), 200
    except Exception as e:
        print(f"トピックの更新に失敗しました: {e}")
        return jsonify({'error': "トピックの更新に失敗しました。"}), 500
    finally:
        conn.close()

@app.route('/id', methods=['GET'])
async def get_admin_ids():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # id_admins テーブルは user_roles に統合されたので、user_roles から取得
        cursor.execute("SELECT hashed_id FROM user_roles WHERE role = ?", (ROLES['ADMIN'],))
        admin_ids = [row['hashed_id'] for row in cursor.fetchall()]
        return jsonify({'adminIds': admin_ids}), 200
    except Exception as e:
        print(f"管理者IDの取得に失敗しました: {e}")
        return jsonify({'error': "管理者IDデータの読み込みに失敗しました。"}), 500
    finally:
        conn.close()

@app.route('/roles', methods=['GET'])
async def get_user_roles_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hashed_id, role FROM user_roles")
        roles_data = [dict(row) for row in cursor.fetchall()] # Rowオブジェクトを辞書に変換
        return jsonify(roles_data), 200
    except Exception as e:
        print(f"ユーザーロールの取得に失敗しました: {e}")
        return jsonify({'error': "ユーザーロールデータの読み込みに失敗しました。"}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    # 開発サーバーの起動 (本番環境では gunicorn などを利用)
    app.run(debug=True, port=5000) # デフォルトポートは5000。デバッグモードで変更を自動反映
