const express = require("express");
const path = require("path");
const bodyParser = require("body-parser");
const crypto = require("crypto");
const cookieParser = require('cookie-parser');
require('dotenv').config(); // .env ファイルを読み込む
const { Pool } = require('pg'); // PostgreSQL クライアント

const app = express();
const PORT = process.env.PORT || 3000;

// --- Supabase (PostgreSQL) への接続設定 ---
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    // 本番環境ではSSL証明書の設定が推奨されます。
    // HerokuやVercelなど多くのPaaSでは自動的に設定されますが、
    // ローカル環境でのテストや特定のデプロイ環境では 'rejectUnauthorized: false' が必要になる場合があります。
    // セキュリティリスクを理解した上で設定してください。
    rejectUnauthorized: false
  }
});

// データベース接続テスト (サーバー起動時に実行)
pool.connect()
  .then(client => {
    console.log('PostgreSQL (Supabase) に接続しました。');
    client.release(); // クライアントをプールに戻す
  })
  .catch(err => {
    console.error('PostgreSQL (Supabase) への接続に失敗しました:', err.message);
    process.exit(1); // 接続できない場合はサーバーを終了
  });

// --- Express ミドルウェア ---
app.use(express.static(path.join(__dirname, "public"))); // 静的ファイル配信
app.use(bodyParser.urlencoded({ extended: true })); // URLエンコードされたボディを解析
app.use(bodyParser.json()); // JSON形式のボディを解析
app.use(cookieParser()); // クッキーの解析

// 投稿制限のための変数: シードごとの最終投稿時間を記録
const requestTimestamps = {};

// --- 権限レベルの定義 ---
// 権限の文字列と階層を定義します。
const ROLES = {
    BLUE: 'blue',        // 青ID (デフォルト)
    SPEAKER: 'speaker',  // スピーカー
    MANAGER: 'manager',  // マネージャー
    MODERATOR: 'moderator', // モデレーター
    SUMMIT: 'summit',    // サミット
    ADMIN: 'admin'       // 運営
};

// 権限の階層（数値が大きいほど高権限）
const ROLE_HIERARCHY = {
    [ROLES.BLUE]: 0,
    [ROLES.SPEAKER]: 10,
    [ROLES.MANAGER]: 20,
    [ROLES.MODERATOR]: 30,
    [ROLES.SUMMIT]: 40,
    [ROLES.ADMIN]: 50
};

// --- ヘルパー関数 ---

/**
 * シードをSHA-256でハッシュ化し、先頭7文字に'@'を付けたIDを生成します。
 */
function generateHashedId(seed) {
  return (
    "@" +
    crypto
      .createHash("sha256")
      .update(seed)
      .digest("hex")
      .substring(0, 7)
  );
}

/**
 * ユーザーの権限レベルを取得します。
 * user_roles テーブルから取得し、存在しなければ 'blue' (青ID) を返します。
 */
async function getUserRole(hashedId) {
    const client = await pool.connect();
    try {
        const res = await client.query('SELECT role FROM user_roles WHERE hashed_id = $1', [hashedId]);
        if (res.rows.length > 0) {
            return res.rows[0].role;
        }
        return ROLES.BLUE; // デフォルトは青ID
    } catch (error) {
        console.error(`ユーザー権限の取得に失敗しました (ID: ${hashedId}):`, error.message);
        return ROLES.BLUE;
    } finally {
        client.release();
    }
}

/**
 * 指定されたハッシュ化IDが管理者IDテーブルに存在するかをチェックします。
 * これは 'id_admins' テーブルを使用する場合の互換性関数です。
 * 権限システムと統合するなら、'hasPermission(hashedId, ROLES.MANAGER)' のように使用します。
 */
async function isAdmin(hashedId) {
    const client = await pool.connect();
    try {
        const res = await client.query('SELECT COUNT(*) FROM id_admins WHERE admin_hashed_id = $1', [hashedId]);
        return res.rows[0].count > 0;
    } catch (error) {
        console.error("管理者IDのチェックに失敗しました:", error.message);
        return false;
    } finally {
        client.release();
    }
}

/**
 * 指定されたhashedIdのユーザーが、要求されたrole以上の権限を持っているかチェックします。
 */
async function hasPermission(hashedId, requiredRole) {
    const userRole = await getUserRole(hashedId);
    return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}

/**
 * 投稿を整理し、最新の3件のみを残します。
 * (データベース操作)
 */
async function prunePosts() {
  const client = await pool.connect();
  try {
    // 最新の3件のIDを取得し、それ以外の投稿を削除します。
    // より効率的な方法も可能ですが、ここではシンプルに実装。
    await client.query(`
        DELETE FROM posts
        WHERE id NOT IN (SELECT id FROM posts ORDER BY created_at DESC LIMIT 3)
    `);
    console.log("投稿が整理され、最新の3件のみが保持されました。");
  } catch (err) {
    console.error("投稿の整理に失敗しました:", err.message);
    throw new Error("投稿の整理に失敗しました。");
  } finally {
    client.release();
  }
}

// --- APIエンドポイント ---

// GET /api: 投稿一覧と現在のトピックを返す
app.get("/api", async (req, res) => {
  const client = await pool.connect();
  try {
    // 最新の投稿から順に取得
    const postsRes = await client.query('SELECT id, name, content, hashed_id, time, topic FROM posts ORDER BY created_at DESC');
    const posts = postsRes.rows.map(row => ({
        // DBのカラム名と既存のJSオブジェクト名を合わせる
        no: -1, // フロントエンドで付与されるためダミー値
        name: row.name,
        content: row.content,
        id: row.hashed_id, // hashed_id を id として返す
        time: new Date(row.time).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }), // DBのtimestampを整形
        topic: row.topic // データベースの 'topic' カラムから取得
    }));

    // トピックは最新の投稿から取得するか、別途設定が必要。
    // 今回は最新の投稿のトピックを「今の話題」として表示する
    const currentTopic = posts.length > 0 ? posts[0].topic : "トピックが設定されていません";

    res.json({ topic: currentTopic, posts: posts });
  } catch (err) {
    console.error("データの読み込みに失敗しました:", err.message);
    res.status(500).json({ error: "データの読み込みに失敗しました。" });
  } finally {
    client.release();
  }
});

// POST /api: 新規投稿およびコマンド処理
app.post("/api", async (req, res) => {
  const { name, pass, content } = req.body;

  if (!name || !pass || !content) {
    return res.status(400).json({ error: "すべてのフィールドを入力してください。" });
  }

  const now = Date.now();
  if (requestTimestamps[pass] && now - requestTimestamps[pass] < 1000) {
    return res.status(429).json({ error: "同じシードからの投稿は1秒に1回までです。" });
  }
  requestTimestamps[pass] = now;

  const hashedId = generateHashedId(pass);

  // 成功した投稿者のIDをクッキーに保存
  res.cookie('last_posted_id', hashedId, {
      httpOnly: true,
      maxAge: 3600000 * 24 * 7, // 1週間有効 (ミリ秒)
      // secure: process.env.NODE_ENV === 'production', // 本番環境ではHTTPSを強制
      // sameSite: 'Lax'
  });

  const client = await pool.connect();
  try {
    // 現在のトピックを取得 (簡易化のため、最新の投稿のトピックを使用)
    const latestPostRes = await client.query('SELECT topic FROM posts ORDER BY created_at DESC LIMIT 1');
    const currentTopic = latestPostRes.rows.length > 0 ? latestPostRes.rows[0].topic : "初見さんいらっしゃい　"; // デフォルト値

    // --- コマンド処理の分岐 ---
    if (content.startsWith('/')) {
        const commandParts = content.split(/\s+/); // スペースで分割
        const command = commandParts[0]; // 例: /del
        const args = commandParts.slice(1); // 例: ["1", "2"]

        switch (command) {
            case '/clear':
                // /clear: 全ての投稿を削除。モデレーター以上。
                if (!(await hasPermission(hashedId, ROLES.MODERATOR))) {
                    return res.status(403).json({ error: "権限がありません。モデレーター以上が必要です。" });
                }
                await client.query('TRUNCATE TABLE posts RESTART IDENTITY'); // 全削除し、IDシーケンスをリセット
                return res.status(200).json({ message: "全ての投稿を削除し、投稿番号をリセットしました。" });

            case '/del':
                // /del (投稿番号): 指定番号の投稿を削除。マネージャー以上。
                if (!(await hasPermission(hashedId, ROLES.MANAGER))) {
                    return res.status(403).json({ error: "権限がありません。マネージャー以上が必要です。" });
                }
                if (args.length === 0) {
                    return res.status(400).json({ error: "/delコマンドには投稿番号が必要です。" });
                }

                const postNumbersToDelete = args.map(Number).filter(num => !isNaN(num) && num > 0);
                if (postNumbersToDelete.length === 0) {
                    return res.status(400).json({ error: "有効な投稿番号が指定されませんでした。" });
                }

                const allPostsResForDel = await client.query('SELECT id FROM posts ORDER BY created_at DESC');
                const allPostIds = allPostsResForDel.rows.map(row => row.id);

                const idsToDelete = [];
                for (const num of postNumbersToDelete) {
                    if (num <= allPostIds.length) {
                        idsToDelete.push(allPostIds[num - 1]); // 投稿番号は1始まり、配列インデックスは0始まり
                    }
                }

                if (idsToDelete.length > 0) {
                    await client.query('DELETE FROM posts WHERE id = ANY($1::uuid[])', [idsToDelete]);
                    return res.status(200).json({ message: `投稿番号 ${postNumbersToDelete.join(', ')} の投稿を削除しました。` });
                } else {
                    return res.status(404).json({ error: "指定された投稿番号が見つかりませんでした。" });
                }

            case '/destroy':
                // /destroy (文字): 特定の文字やIDが含まれる投稿を一括削除。モデレーター以上。
                if (!(await hasPermission(hashedId, ROLES.MODERATOR))) {
                    return res.status(403).json({ error: "権限がありません。モデレーター以上が必要です。" });
                }
                if (args.length === 0) {
                    return res.status(400).json({ error: "/destroyコマンドには削除条件が必要です。" });
                }

                const query = args.join(' '); // 削除条件文字列
                let deleteCondition = '';
                let queryParams = [];

                // (color)オプションの処理は、別途ユーザーの色をDBに保存する仕組みが必要。
                // 現状の実装では複雑になるため、ここでは content または hashed_id で検索するシンプルな例を示します。
                if (query.startsWith('(color)')) {
                    return res.status(400).json({ error: "現在、(color)による削除は未実装です。特定の文字またはIDで削除してください。" });
                } else {
                    deleteCondition = 'content ILIKE $1 OR hashed_id ILIKE $1'; // 大文字小文字を区別しないLIKE
                    queryParams.push(`%${query}%`);
                }

                if (deleteCondition) {
                    await client.query(`DELETE FROM posts WHERE ${deleteCondition}`, queryParams);
                    return res.status(200).json({ message: `"${query}"を含む投稿を一括削除しました。` });
                } else {
                    return res.status(400).json({ error: "削除条件が指定されませんでした。" });
                }

            // --- その他のコマンド（今後追加していく部分） ---
            // case '/NG': ...
            // case '/prevent': ...
            // case '/restrict': ...
            // case '/ban': ...
            // etc.

            default:
                // 未知のコマンドは通常の投稿として扱わない
                return res.status(400).json({ error: `不明なコマンドです: ${command}` });
        }
    }

    // --- コマンドではない場合は通常の投稿として処理 ---
    const insertRes = await client.query(
      'INSERT INTO posts(name, content, hashed_id, time, topic) VALUES($1, $2, $3, $4, $5) RETURNING id, name, content, hashed_id, time, topic',
      [name, content, hashedId, new Date(), currentTopic] // created_at はDBで自動生成
    );
    const newPostFromDb = insertRes.rows[0];

    // 投稿数が200件を超えたら自動的に整理
    const countRes = await client.query('SELECT COUNT(*) FROM posts');
    if (countRes.rows[0].count > 200) {
      console.log("投稿数が200件を超えました。投稿を整理します。");
      await prunePosts();
    }

    res.status(200).json({
        message: "投稿が成功しました。",
        post: {
            no: -1, // フロントエンドで処理
            name: newPostFromDb.name,
            content: newPostFromDb.content,
            id: newPostFromDb.hashed_id,
            time: new Date(newPostFromDb.time).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }),
            topic: newPostFromDb.topic
        }
    });
  } catch (err) {
    console.error("データの処理に失敗しました:", err.message);
    res.status(500).json({ error: "データの処理に失敗しました。" });
  } finally {
    client.release();
  }
});

// POST /topic: トピック変更API (管理者IDまたはクッキーのIDで認証)
app.post("/topic", async (req, res) => {
  const { topic, pass } = req.body;

  let providedHashedId = null;
  if (pass) {
    providedHashedId = generateHashedId(pass);
  } else {
    providedHashedId = req.cookies.last_posted_id;
  }

  if (!topic) {
    return res.status(400).json({ error: "トピックを入力してください。" });
  }

  // マネージャー以上の権限が必要
  if (!providedHashedId || !(await hasPermission(providedHashedId, ROLES.MANAGER))) {
    return res.status(403).json({ error: "権限がありません。マネージャー以上が必要です。" });
  }

  const client = await pool.connect();
  try {
    // 既存のすべての投稿のトピックを更新
    await client.query('UPDATE posts SET topic = $1', [topic]);
    res.status(200).json({ message: "トピックが更新されました。" });
  } catch (err) {
    console.error("トピックの更新に失敗しました:", err.message);
    res.status(500).json({ error: "トピックの更新に失敗しました。" });
  } finally {
    client.release();
  }
});

// GET /id: 管理者ID一覧を返す (デバッグ用)
app.get("/id", async (req, res) => {
    const client = await pool.connect();
    try {
        const resDb = await client.query('SELECT admin_hashed_id FROM id_admins');
        const adminIds = resDb.rows.map(row => row.admin_hashed_id);
        res.json({ adminIds: adminIds });
    } catch (err) {
        console.error("管理者IDの取得に失敗しました:", err.message);
        res.status(500).json({ error: "管理者IDデータの読み込みに失敗しました。" });
    } finally {
        client.release();
    }
});

// GET /roles: ユーザーロール一覧を返す (デバッグ用)
app.get("/roles", async (req, res) => {
    const client = await pool.connect();
    try {
        const resDb = await client.query('SELECT hashed_id, role FROM user_roles');
        res.json(resDb.rows);
    } catch (err) {
        console.error("ユーザーロールの取得に失敗しました:", err.message);
        res.status(500).json({ error: "ユーザーロールデータの読み込みに失敗しました。" });
    } finally {
        client.release();
    }
});

// サーバー起動
app.listen(PORT, () => {
  console.log(`サーバーがポート ${PORT} で起動しました。`);
});
