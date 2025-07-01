const express = require("express");
const fs = require("fs");
const path = require("path");
const bodyParser = require("body-parser");
const crypto = require("crypto");
const cookieParser = require('cookie-parser'); // <--- 追加

const app = express();
const PORT = process.env.PORT || 3000;
const DATA_FILE = path.join(__dirname, "data.json");
const ID_FILE = path.join(__dirname, "ID.json");

// 静的ファイルの配信設定
app.use(express.static(path.join(__dirname, "public")));
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(cookieParser()); // <--- 追加: cookie-parserミドルウェアを有効にする

// 投稿制限のための変数: シードごとの最終投稿時間を記録
const requestTimestamps = {};

// --- ファイルの初期化（変更なし） ---
if (!fs.existsSync(DATA_FILE)) {
  const defaultData = {
    topic: "初見さんいらっしゃい　",
    posts: [],
  };
  fs.writeFileSync(DATA_FILE, JSON.stringify(defaultData, null, 2));
}

if (!fs.existsSync(ID_FILE)) {
  const defaultIdData = {
    admin: "@e0e0a1b", // **ここに実際の管理者IDを設定**
  };
  fs.writeFileSync(ID_FILE, JSON.stringify(defaultIdData, null, 2));
}

// --- ヘルパー関数（変更なし） ---
function prunePosts(jsonData) {
  return new Promise((resolve, reject) => {
    jsonData.posts = jsonData.posts.slice(0, 3);
    fs.writeFile(DATA_FILE, JSON.stringify(jsonData, null, 2), (err) => {
      if (err) {
        console.error("投稿の整理に失敗しました:", err);
        return reject(new Error("整理されたデータの保存に失敗しました。"));
      }
      console.log("投稿は正常に整理され、最新の3件のみが保持されました。");
      resolve(jsonData);
    });
  });
}

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

async function isAdmin(hashedId) {
    try {
        const idDataRaw = await fs.promises.readFile(ID_FILE, "utf8");
        const idJsonData = JSON.parse(idDataRaw);
        return Object.values(idJsonData).includes(hashedId);
    } catch (error) {
        console.error("ID.json の読み込みまたは解析に失敗しました:", error);
        return false;
    }
}

// --- APIエンドポイント ---

// GET /api: 投稿一覧と現在のトピックを返す
app.get("/api", (req, res) => {
  fs.readFile(DATA_FILE, "utf8", (err, data) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ error: "データの読み込みに失敗しました。" });
    }
    res.json(JSON.parse(data));
  });
});

// POST /api: 新規投稿
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

  // <--- 追加: 成功した投稿者のIDをクッキーに保存 ---
  res.cookie('last_posted_id', hashedId, {
      httpOnly: true, // JavaScriptからアクセス不可にする (セキュリティ)
      maxAge: 3600000 * 24 * 7, // 1週間有効 (ミリ秒)
      // secure: true, // HTTPSの場合のみ送信 (本番環境では推奨)
      // sameSite: 'Lax' // CSRF対策 (本番環境では推奨)
  });
  // ----------------------------------------------------

  try {
    let data = await fs.promises.readFile(DATA_FILE, "utf8");
    let jsonData = JSON.parse(data);

    if (content === "/clear") {
      if (await isAdmin(hashedId)) {
        await prunePosts(jsonData);
        return res.status(200).json({ message: "掲示板がクリアされました。" });
      } else {
        console.log("'/clear' が投稿されましたが、管理者ではありません。通常の投稿として扱います。");
      }
    }

    const newPost = {
      name: name,
      content: content,
      id: hashedId,
      time: new Date().toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }),
      no: -1,
    };

    jsonData.posts.unshift(newPost);

    if (jsonData.posts.length > 200) {
      console.log("投稿数が200件を超えました。投稿を整理します。");
      await prunePosts(jsonData);
    } else {
      await fs.promises.writeFile(DATA_FILE, JSON.stringify(jsonData, null, 2));
    }

    res.status(200).json({ message: "投稿が成功しました。", post: newPost });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "データの処理に失敗しました。" });
  }
});

// POST /topic: トピック変更API (管理者IDまたはクッキーのIDで認証)
app.post("/topic", async (req, res) => {
  const { topic, pass } = req.body; // passはオプションにする

  let providedHashedId = null;

  // 1. req.body.pass (明示的に入力されたシード) をチェック
  if (pass) {
    providedHashedId = generateHashedId(pass);
  } else {
  // 2. クッキーに保存されたIDをチェック
    providedHashedId = req.cookies.last_posted_id; // <--- 追加: クッキーからIDを取得
  }

  if (!topic) {
    return res.status(400).json({ error: "トピックを入力してください。" });
  }

  // providedHashedId が存在し、それが管理者であるかをチェック
  if (!providedHashedId || !(await isAdmin(providedHashedId))) {
    return res.status(403).json({ error: "権限がありません。管理者シードが正しくないか、ログインしていません。" });
  }

  try {
    let data = await fs.promises.readFile(DATA_FILE, "utf8");
    let jsonData = JSON.parse(data);
    jsonData.topic = topic;

    await fs.promises.writeFile(DATA_FILE, JSON.stringify(jsonData, null, 2));
    res.status(200).json({ message: "トピックが更新されました。" });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "トピックの更新に失敗しました。" });
  }
});

// GET /id: ID.json の内容を返す (デバッグ用などに利用可能)
app.get("/id", (req, res) => {
  fs.readFile(ID_FILE, "utf8", (err, data) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ error: "IDデータの読み込みに失敗しました。" });
    }
    res.json(JSON.parse(data));
  });
});

// サーバー起動
app.listen(PORT, () => {
  console.log(`サーバーがポート ${PORT} で起動しました。`);
});
