# flaskモジュールから必要なものをインポート
from flask import Flask, render_template, request, redirect, url_for, jsonify
# Flask-SQLAlchemyからSQLAlchemyをインポート
from flask_sqlalchemy import SQLAlchemy
# hashlibモジュールをインポート（SHA-256ハッシュ化のため）
import hashlib
# osモジュールをインポート（環境変数を読み込むため）
import os
# datetimeモジュールをインポート（タイムスタンプのため）
import datetime

# Flaskアプリケーションの初期化
# テンプレートフォルダのパスを 'public' に設定
app = Flask(__name__, template_folder='public')

# データベース設定
# 環境変数 'DATABASE_URL' からデータベースURIを取得します。
# もし環境変数が設定されていない場合は、開発用に 'sqlite:///site.db' を使用します。
# Vercelのようなサーバーレス環境では、必ず外部データベース（例: PostgreSQL）を使用する必要があります。
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
# SQLAlchemyのイベント追跡機能を無効にします（パフォーマンス向上のため）
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# SQLAlchemyのDBオブジェクトを初期化
db = SQLAlchemy(app)

# --- データベースモデルの定義 ---

# Userモデル：掲示板のユーザー情報を管理します。
# シードハッシュ、表示色、追加情報などを保持します。
class User(db.Model):
    # プライマリキー（自動採番されるID）
    id = db.Column(db.Integer, primary_key=True)
    # ユーザーを一意に識別するためのSHA-256ハッシュ
    seed_hash_id = db.Column(db.String(64), unique=True, nullable=False)
    # ユーザー名の表示色（例: 'red', 'blue', 'black'など）
    display_color = db.Column(db.String(20), default='black')
    # 名前の後ろに表示される追加情報（格言や役職など）
    additional_info = db.Column(db.String(100), default='')
    # ユーザーの権限レベル（例: '青ID', 'マネージャー'など、現在は未使用だが将来のために保持）
    role = db.Column(db.String(20), default='青ID')
    # このユーザーが投稿したPostへのリレーションシップ
    posts = db.relationship('Post', backref='author', lazy=True)

    # オブジェクトの文字列表現
    def __repr__(self):
        return f"User('{self.seed_hash_id[:7]}', '{self.display_color}', '{self.additional_info}')"

# Postモデル：掲示板の投稿を管理します。
# 投稿内容、投稿者、タイムスタンプなどを保持します。
class Post(db.Model):
    # プライマリキー（自動採番されるID）
    id = db.Column(db.Integer, primary_key=True)
    # 投稿時に入力された名前
    name = db.Column(db.String(25), nullable=False)
    # 投稿メッセージの内容
    message = db.Column(db.String(100), nullable=False)
    # 投稿日時（デフォルトは現在のタイムスタンプ）
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    # 投稿者Userモデルへの外部キー
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # オブジェクトの文字列表現
    def __repr__(self):
        return f"Post('{self.id}', '{self.name}', '{self.message}')"

# NgWordモデル：禁止ワードを管理します。
class NgWord(db.Model):
    # プライマリキー
    id = db.Column(db.Integer, primary_key=True)
    # 禁止ワード
    word = db.Column(db.String(100), unique=True, nullable=False)

    # オブジェクトの文字列表現
    def __repr__(self):
        return f"NgWord('{self.word}')"

# --- ルーティング ---

# ルートURL ('/') の処理
# GETリクエストとPOSTリクエストの両方を処理します
@app.route('/', methods=['GET', 'POST'])
def index():
    # POSTリクエストの場合（フォーム送信時）
    if request.method == 'POST':
        # フォームからデータを取得
        input_name = request.form['name']
        message = request.form['message']
        seed = request.form['seed']

        # シード値をSHA-256でハッシュ化
        seed_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()

        # シードハッシュに対応するUserが存在するか確認
        user = User.query.filter_by(seed_hash_id=seed_hash).first()

        # Userが存在しない場合、新しいUserを作成
        if not user:
            # デフォルトの色を赤に設定（画像に合わせて）
            user = User(seed_hash_id=seed_hash, display_color='red', additional_info='')
            db.session.add(user)
            db.session.commit() # userオブジェクトがDBに保存され、idが付与される

        # NGワードチェック
        ng_words = [ng.word for ng in NgWord.query.all()]
        for word in ng_words:
            if word in message or word in input_name:
                # NGワードが含まれていたらエラーメッセージを返す
                return "NGワードが含まれています！", 400

        # 新しい投稿を作成し、データベースに追加
        # 投稿者のuser_idと、投稿時の名前（フォーム入力値）を保存
        new_post = Post(name=input_name, message=message, user_id=user.id)
        db.session.add(new_post)
        db.session.commit()
        # 投稿後にトップページにリダイレクト
        return redirect(url_for('index'))

    # GETリクエストの場合（ページ表示時）
    # まずはHTMLページをレンダリングします。
    # 投稿データはJavaScriptから '/api/posts' エンドポイント経由で取得されます。
    return render_template('index.html')

# APIエンドポイント：投稿データをJSON形式で返します
@app.route('/api/posts', methods=['GET'])
def get_posts():
    # 投稿をタイムスタンプの昇順（古いものが先頭）で取得し、関連するUser情報も結合
    posts = Post.query.join(User).order_by(Post.timestamp.asc()).all()
    
    posts_data = []
    # 取得した投稿データをループし、JSON形式に変換してリストに追加
    for i, post in enumerate(posts):
        posts_data.append({
            'id': i, # 0から始まる連番を付与
            'name': post.name,
            'message': post.message,
            'display_color': post.author.display_color, # 投稿者の表示色
            'seed_hash_display': post.author.seed_hash_id[:7] if post.author.seed_hash_id else '', # シードハッシュの最初の7文字
            'additional_info': post.author.additional_info # 投稿者の追加情報
        })
    # JSON形式でデータを返す
    return jsonify(posts_data)

# データベースの初期化と初期データ投入
# アプリケーションコンテキスト内で実行されます
with app.app_context():
    # データベーステーブルを全て作成（既に存在する場合はスキップ）
    db.create_all()

    # Postテーブルが空の場合にのみ初期投稿を投入
    if not Post.query.first():
        # 「カルパス財団」ユーザーのシードハッシュを生成
        kalpas_seed = "kalpas_foundation_seed"
        kalpas_hash = hashlib.sha256(kalpas_seed.encode('utf-8')).hexdigest()
        
        # 「カルパス財団」ユーザーが存在するか確認
        kalpas_user = User.query.filter_by(seed_hash_id=kalpas_hash).first()

        # 存在しない場合、新しい「カルパス財団」ユーザーを作成
        if not kalpas_user:
            kalpas_user = User(
                seed_hash_id=kalpas_hash,
                display_color='red', # 「カルパス財団」の色を赤に設定
                additional_info=''
            )
            db.session.add(kalpas_user)
            db.session.commit() # ユーザーをコミットしてIDを取得

        # 初期メッセージの内容
        initial_message = "ｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽｶﾙﾊﾟｽ"
        # 初期投稿を作成
        initial_post = Post(
            name="カルパス財団", # 投稿者の名前
            message=initial_message, # 投稿メッセージ
            user_id=kalpas_user.id, # 「カルパス財団」ユーザーのIDに紐付け
            # タイムスタンプを非常に古い日付に設定し、常に一番古い投稿として扱われるようにする
            timestamp=datetime.datetime(2020, 1, 1, 0, 0, 0) 
        )
        db.session.add(initial_post)
        db.session.commit()

# アプリケーションの実行
# debug=True は開発用です。本番環境では False に設定してください。
if __name__ == '__main__':
    app.run(debug=True)
