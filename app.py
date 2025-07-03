from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import hashlib
import os

# テンプレートフォルダのパスを 'public' に変更
app = Flask(__name__, template_folder='public')

# データベース設定 (例: SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデルの定義 ---
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(25), nullable=False)
    message = db.Column(db.String(100), nullable=False)
    # seed_hash を追加。元のseedは保存しない（セキュリティのため）
    seed_hash = db.Column(db.String(64), nullable=False) # SHA-256は64文字
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f"Post('{self.id}', '{self.name}', '{self.message}', '{self.seed_hash[:7]}')"

# ユーザー情報 (権限管理のため) - 今後、認証機能や権限管理の実装で利用します
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128)) # パスワードはハッシュ化して保存
    role = db.Column(db.String(20), default='青ID') # 権限レベル (青ID, マネージャーなど)
    is_banned = db.Column(db.Boolean, default=False)
    # 他にもIPアドレスや規制情報などを追加

    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"

# NGワードテーブル - 投稿規制機能で利用します
class NgWord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"NgWord('{self.word}')"


# --- ルーティング ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 投稿フォームからのデータを受け取る
        name = request.form['name']
        message = request.form['message']
        seed = request.form['seed'] # ユーザーが入力したシード値

        # シード値をSHA-256でハッシュ化
        # 必ずUTF-8でエンコードしてからハッシュ化する
        seed_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()

        # ここでNGワードチェックなどのバリデーションを行う
        ng_words = [ng.word for ng in db.session.query(NgWord).all()]
        for word in ng_words:
            if word in message or word in name:
                # NGワードが含まれていたらエラーメッセージなどを返す
                # 現時点では単純にエラーを返す
                return "NGワードが含まれています！", 400


        # 新しい投稿を作成し、データベースに追加
        # seed_hash を保存
        new_post = Post(name=name, message=message, seed_hash=seed_hash)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index')) # 投稿後にトップページにリダイレクト

    # GETリクエストの場合、投稿一覧を表示
    posts = Post.query.order_by(Post.id.desc()).all() # 新しい投稿が上に来るように
    return render_template('index.html', posts=posts)

# データベースの初期化
# アプリケーション初回起動時などに一度だけ実行
with app.app_context():
    db.create_all()
    # 必要に応じて、初期データ（NGワードなど）をここに追加することも可能です
    # 例:
    # if not NgWord.query.first():
    #     db.session.add(NgWord(word="テストNGワード"))
    #     db.session.commit()

if __name__ == '__main__':
    # debug=True は開発用です。本番環境では False にしてください
    app.run(debug=True)
