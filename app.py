from flask import Flask, render_template, request, redirect, url_for, jsonify # jsonify をインポート
from flask_sqlalchemy import SQLAlchemy
import hashlib
import os
import datetime

app = Flask(__name__, template_folder='public')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- データベースモデルの定義 (変更なし) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seed_hash_id = db.Column(db.String(64), unique=True, nullable=False)
    display_color = db.Column(db.String(20), default='black')
    additional_info = db.Column(db.String(100), default='')
    role = db.Column(db.String(20), default='青ID')
    posts = db.relationship('Post', backref='author', lazy=True)

    def __repr__(self):
        return f"User('{self.seed_hash_id[:7]}', '{self.display_color}', '{self.additional_info}')"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(25), nullable=False)
    message = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

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
        input_name = request.form['name']
        message = request.form['message']
        seed = request.form['seed']

        seed_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()

        user = User.query.filter_by(seed_hash_id=seed_hash).first()

        if not user:
            user = User(seed_hash_id=seed_hash, display_color='red', additional_info='') # 初期ユーザーを赤色に設定
            db.session.add(user)
            db.session.commit()

        ng_words = [ng.word for ng in NgWord.query.all()]
        for word in ng_words:
            if word in message or word in input_name:
                return "NGワードが含まれています！", 400

        new_post = Post(name=input_name, message=message, user_id=user.id)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))

    # GETリクエストの場合、最初にHTMLページをレンダリングする
    # JavaScriptからデータを取得するためのエンドポイントは別に用意する
    return render_template('index.html')

# 投稿データをJSON形式で返す新しいエンドポイント
@app.route('/api/posts', methods=['GET'])
def get_posts():
    # タイムスタンプの昇順（古いものが先頭）で取得
    posts = Post.query.join(User).order_by(Post.timestamp.asc()).all()
    
    posts_data = []
    for i, post in enumerate(posts):
        posts_data.append({
            'id': i, # ここで0から始まるインデックスを付与
            'name': post.name,
            'message': post.message,
            'display_color': post.author.display_color,
            'seed_hash_display': post.author.seed_hash_id[:7] if post.author.seed_hash_id else '',
            'additional_info': post.author.additional_info
        })
    return jsonify(posts_data)


# データベースの初期化と初期データ投入
with app.app_context():
    db.create_all()

    if not Post.query.first():
        kalpas_seed = "kalpas_foundation_seed"
        kalpas_hash = hashlib.sha256(kalpas_seed.encode('utf-8')).hexdigest()
        kalpas_user = User.query.filter_by(seed_hash_id=kalpas_hash).first()

        if not kalpas_user:
            kalpas_user = User(
                seed_hash_id=kalpas_hash,
                display_color='red', # 「カルパス財団」の色を赤に設定
                additional_info=''
            )
            db.session.add(kalpas_user)
            db.session.commit()

        initial_message = "ｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽ"
        initial_post = Post(
            name="カルパス財団",
            message=initial_message,
            user_id=kalpas_user.id,
            timestamp=datetime.datetime(2025, 1, 1, 0, 0, 0) # 確実に一番古いタイムスタンプを設定
        )
        db.session.add(initial_post)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
