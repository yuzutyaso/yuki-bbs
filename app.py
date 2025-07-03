from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import hashlib
import os

app = Flask(__name__, template_folder='public')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデルの定義 ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # ユーザー名とシードハッシュを紐付ける
    # usernameはここではログイン機能での利用を想定、投稿時の名前とは別に考える
    # 投稿時の名前はPostモデルで持つ
    seed_hash_id = db.Column(db.String(64), unique=True, nullable=False) # ユーザーを一意に識別するハッシュ

    # ユーザーの表示情報
    display_color = db.Column(db.String(20), default='black') # 名前の色
    additional_info = db.Column(db.String(100), default='') # 名前の後ろにつける文字（格言など）
    role = db.Column(db.String(20), default='青ID') # 権限レベル (今は使わないが残す)

    # このユーザーが投稿したPostsを取得できるように
    posts = db.relationship('Post', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.seed_hash_id[:7]}', '{self.display_color}', '{self.additional_info}')"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(25), nullable=False) # 投稿時に入力される名前
    message = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Userモデルへの外部キー
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"Post('{self.id}', '{self.name}', '{self.message}')"

class NgWord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f"NgWord('{self.word}')"

# --- ルーティング ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        input_name = request.form['name'] # フォームで入力された名前
        message = request.form['message']
        seed = request.form['seed']

        # シード値をSHA-256でハッシュ化
        seed_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()

        # シードハッシュに対応するUserが存在するか確認
        user = User.query.filter_by(seed_hash_id=seed_hash).first()

        if not user:
            # 存在しなければ新しいUserを作成
            # 初期の色と追加情報を設定
            user = User(seed_hash_id=seed_hash, display_color='black', additional_info='') # デフォルトは黒と空白
            db.session.add(user)
            db.session.commit() # userオブジェクトがDBに保存され、idが付与される

        # NGワードチェック
        ng_words = [ng.word for ng in NgWord.query.all()]
        for word in ng_words:
            if word in message or word in input_name:
                return "NGワードが含まれています！", 400

        # 新しい投稿を作成し、データベースに追加
        # 投稿者のuser_idと、投稿時の名前（フォーム入力値）を保存
        new_post = Post(name=input_name, message=message, user_id=user.id)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))

    # GETリクエストの場合、投稿一覧を表示
    # 投稿と関連するUser情報を結合して取得
    posts = Post.query.join(User).order_by(Post.id.desc()).all()
    # Postオブジェクトのリストをテンプレートに渡す。各Postは author (User) オブジェクトを持っている。
    return render_template('index.html', posts=posts)

# データベースの初期化
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
