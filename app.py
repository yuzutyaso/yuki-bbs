from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# データベース設定 (例: SQLite)
# 'sqlite:///site.db' はプロジェクトルートに 'site.db' というファイルを作成します
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデルの定義 ---
# 投稿を保存するテーブル
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(25), nullable=False)
    message = db.Column(db.String(100), nullable=False)
    seed = db.Column(db.String(50), nullable=False) # シード値はパスワードのようなものとして扱う
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    # 権限情報やIPアドレス、削除フラグなどは後で追加

    def __repr__(self):
        return f"Post('{self.id}', '{self.name}', '{self.message}')"

# ユーザー情報 (権限管理のため)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128)) # パスワードはハッシュ化して保存
    role = db.Column(db.String(20), default='青ID') # 権限レベル (青ID, マネージャーなど)
    is_banned = db.Column(db.Boolean, default=False)
    # 他にもIPアドレスや規制情報などを追加

    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"

# NGワードテーブル
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
        seed = request.form['seed']

        # ここでNGワードチェックなどのバリデーションを行う
        ng_words = [ng.word for ng in NgWord.query.all()]
        for word in ng_words:
            if word in message or word in name:
                # NGワードが含まれていたらエラーメッセージなどを返す
                # 現時点では単純にリダイレクト
                return "NGワードが含まれています！", 400


        # 新しい投稿を作成し、データベースに追加
        new_post = Post(name=name, message=message, seed=seed)
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
    # 初期ユーザーやNGワードをここに追加することも可能

if __name__ == '__main__':
    app.run(debug=True) # debug=True は開発用、本番環境では False にする
