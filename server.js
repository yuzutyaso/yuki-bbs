const express = require("express");
const fs = require("fs");
const path = require("path");
const bodyParser = require("body-parser");
const crypto = require("crypto");

const app = express();
const PORT = process.env.PORT || 3000;
const DATA_FILE = path.join(__dirname, "data.json");
const ID_FILE = path.join(__dirname, "ID.json"); // 管理者IDを保存するファイル

// 静的ファイルの配信設定
// HTML, CSS, クライアントサイドJavaScriptを'public'ディレクトリから配信します
app.use(express.static(path.join(__dirname, "public")));
app.use(bodyParser.urlencoded({ extended: true })); // URLエンコードされたボディを解析
app.use(bodyParser.json()); // JSON形式のボディを解析

// 投稿制限のための変数: シードごとの最終投稿時間を記録
const requestTimestamps = {};

// --- ファイルの初期化 ---
// data.json が存在しない場合は初期データを作成
if (!fs.existsSync(DATA_FILE)) {
  const defaultData = {
    topic: "初見さんいらっしゃい　",
    posts: [],
  };
  fs.writeFileSync(DATA_FILE, JSON.stringify(defaultData, null, 2));
}

// ID.json が存在しない場合は初期データを作成
// ここに管理者として許可するシードのハッシュ化されたIDを設定してください。
// 例: "your_admin_seed" をSHA-256ハッシュ化し、最初の7文字を使う
// 例: "e0e0a1b" (これは "myadminseed" のハッシュ化した例です)
if (!fs.existsSync(ID_FILE)) {
  const defaultIdData = {
    admin: "@e0e0a1b", // **ここに実際の管理者IDを設定**
  };
  fs.writeFileSync(ID_FILE, JSON.stringify(defaultIdData, null, 2));
}

// --- ヘルパー関数 ---

/**
 * 投稿配列を整理し、最新の3件のみを残します。
 * 新しい投稿が配列の先頭にあることを想定しています。
 * @param {object} jsonData - DATA_FILEからパースされたJSONデータ。
 * @returns {Promise<object>} - 更新されたjsonDataで解決されるPromise。
 */
function prunePosts(jsonData) {
  return new Promise((resolve, reject) => {
    jsonData.posts = jsonData.posts.slice(0, 3); // 配列の先頭から3件（最新の3件）を保持

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

/**
 * シードをSHA-256でハッシュ化し、先頭7文字に'@'を付けたIDを生成します。
 * @param {string} seed - ユーザーが入力したシード（パスワードに相当）。
 * @returns {string} - 生成されたハッシュ化ID（例: @abc1234）。
 */
function generateHashedId(seed) {
  return (
    "@" +
    crypto
      .createHash("sha256")
      .update(seed)
      .digest("hex")
      .substring(0, 7) // substrは非推奨なのでsubstringを使用
  );
}

/**
 * 指定されたハッシュ化IDがID.jsonに登録された管理者IDと一致するかをチェックします。
 * @param {string} hashedId - チェックするハッシュ化ID。
 * @returns {Promise<boolean>} - 管理者であればtrue、そうでなければfalse。
 */
async function isAdmin(hashedId) {
    try {
        const idDataRaw = await fs.promises.readFile(ID_FILE, "utf8");
        const idJsonData = JSON.parse(idDataRaw);
        // ID.json の値（管理者ID）が hashedId と一致するかを確認
        return Object.values(idJsonData).includes(hashedId);
    } catch (error) {
        console.error("ID.json の読み込みまたは解析に失敗しました:", error);
        return false; // エラー時は管理者ではないと判断
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
  // POSTリクエストではreq.bodyからデータを取得するのが一般的です
  const { name, pass, content } = req.body;

  if (!name || !pass || !content) {
    return res.status(400).json({ error: "すべてのフィールドを入力してください。" });
  }

  // 投稿制限チェック: 同じシードからの投稿は1秒に1回まで
  const now = Date.now();
  if (requestTimestamps[pass] && now - requestTimestamps[pass] < 1000) {
    return res.status(429).json({ error: "同じシードからの投稿は1秒に1回までです。" });
  }
  requestTimestamps[pass] = now; // タイムスタンプを記録

  const hashedId = generateHashedId(pass); // シードをハッシュ化してIDを生成

  try {
    let data = await fs.promises.readFile(DATA_FILE, "utf8");
    let jsonData = JSON.parse(data);

    // /clear コマンドの処理
    if (content === "/clear") {
      if (await isAdmin(hashedId)) { // 投稿者が管理者IDかチェック
        await prunePosts(jsonData); // 管理者なら掲示板を整理
        // /clearコマンド自体は投稿として記録しない
        return res.status(200).json({ message: "掲示板がクリアされました。" });
      } else {
        console.log("'/clear' が投稿されましたが、管理者ではありません。通常の投稿として扱います。");
        // 管理者でない場合は、'/clear' も通常のメッセージとして次の処理に進む
      }
    }

    const newPost = {
      name: name,
      content: content,
      id: hashedId,
      time: new Date().toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }), // JST固定の投稿時間
      no: -1, // フロントエンドで付与されることを想定。あるいはここでユニークな番号を付与
              // 例: Date.now() などを使ってユニークな番号にするか、別途カウンターを用意
    };

    jsonData.posts.unshift(newPost); // 新しい投稿は配列の先頭に追加 (新しいものが上に来るように)

    // 投稿数が200件を超えたら自動的に整理
    if (jsonData.posts.length > 200) {
      console.log("投稿数が200件を超えました。投稿を整理します。");
      await prunePosts(jsonData); // これによりjsonData.postsが更新され、ファイルが保存される
    } else {
      // 整理しない場合は、新しい投稿を保存
      await fs.promises.writeFile(DATA_FILE, JSON.stringify(jsonData, null, 2));
    }

    res.status(200).json({ message: "投稿が成功しました。", post: newPost });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "データの処理に失敗しました。" });
  }
});

// POST /topic: トピック変更API (管理者IDで認証)
app.post("/topic", async (req, res) => {
  const { topic, pass } = req.body; // 管理者パスワードではなく、シード 'pass' を受け取る

  if (!topic || !pass) {
    return res.status(400).json({ error: "トピックとシードを入力してください。" });
  }

  const hashedId = generateHashedId(pass); // シードをハッシュ化

  if (!(await isAdmin(hashedId))) { // シードから生成されたIDが管理者IDかチェック
    return res.status(403).json({ error: "権限がありません。管理者シードが正しくありません。" });
  }

  try {
    let data = await fs.promises.readFile(DATA_FILE, "utf8");
    let jsonData = JSON.parse(data);
    jsonData.topic = topic; // トピックを更新

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
