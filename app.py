from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import hashlib
import os
import datetime # datetimeモジュールをインポート

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

# --- ルーティング (変更なし) ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        input_name = request.form['name']
        message = request.form['message']
        seed = request.form['seed']

        seed_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()

        user = User.query.filter_by(seed_hash_id=seed_hash).first()

        if not user:
            user = User(seed_hash_id=seed_hash, display_color='black', additional_info='')
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

    posts = Post.query.join(User).order_by(Post.id.desc()).all()
    return render_template('index.html', posts=posts)

# データベースの初期化と初期データ投入
with app.app_context():
    db.create_all()

    # 初期投稿のチェックと投入
    # Postテーブルが空の場合にのみ実行
    if not Post.query.first():
        # 「カルパス財団」ユーザーが存在しない場合は作成
        kalpas_seed = "kalpas_foundation_seed" # 特定のシード値
        kalpas_hash = hashlib.sha256(kalpas_seed.encode('utf-8')).hexdigest()
        kalpas_user = User.query.filter_by(seed_hash_id=kalpas_hash).first()

        if not kalpas_user:
            kalpas_user = User(
                seed_hash_id=kalpas_hash,
                display_color='red', # 「System」の色に合わせて赤に設定
                additional_info=''
            )
            db.session.add(kalpas_user)
            db.session.commit()

        # メッセージ番号0の投稿を作成
        # SQLiteのAUTOINCREMENTは通常1から始まるため、ID=0を直接挿入するのは難しい場合がある。
        # 代わりに、一番古い投稿として表示されるように工夫するか、
        # IDを明示的に指定して挿入を試みる。
        # SQLAlchemyでは通常、主キーは自動生成されるため、
        # Postテーブルが空のときに最初の投稿として挿入されれば、
        # IDが1になることが多いが、表示上は「0」としたい場合は、
        # 投稿取得時に表示順を操作するか、IDを格納するカラムとは別に表示用のNoを管理する必要がある。
        # ここでは単純にPostを挿入し、IDはDBの自動採番に任せます。
        # そして、一番古い投稿として確実に「0」と表示されるように、
        # HTMLの表示部分を工夫する必要があります。
        # まずは、DBに投入するだけ。HTMLでの表示は後続で調整します。

        # 既存のPostテーブルにデータがない場合のみ初期投稿を挿入
        initial_message = "ｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽ"
        initial_post = Post(
            name="カルパス財団",
            message=initial_message,
            user_id=kalpas_user.id,
            timestamp=datetime.datetime(2025, 7, 3, 0, 0, 0) # 確実に一番古いタイムスタンプを設定
        )
        db.session.add(initial_post)
        db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)
