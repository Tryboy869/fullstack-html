const { Octokit } = require("@octokit/rest");
const crypto = require("crypto");

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const [REPO_OWNER, REPO_NAME] = (process.env.GITHUB_REPO || "").split("/");
const DB_FILE = "users.json";
const JWT_SECRET = "auth-demo-secret-2024";

const octokit = new Octokit({ auth: GITHUB_TOKEN });

// --- Minimal JWT (no lib needed) ---
function base64url(str) {
  return Buffer.from(str).toString("base64url");
}
function signJWT(payload) {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64url(JSON.stringify(payload));
  const sig = crypto
    .createHmac("sha256", JWT_SECRET)
    .update(`${header}.${body}`)
    .digest("base64url");
  return `${header}.${body}.${sig}`;
}
function verifyJWT(token) {
  try {
    const [header, body, sig] = token.split(".");
    const expected = crypto
      .createHmac("sha256", JWT_SECRET)
      .update(`${header}.${body}`)
      .digest("base64url");
    if (sig !== expected) return null;
    const payload = JSON.parse(Buffer.from(body, "base64url").toString());
    if (payload.exp && payload.exp < Date.now() / 1000) return null;
    return payload;
  } catch {
    return null;
  }
}

// --- GitHub DB helpers ---
async function readDB() {
  try {
    const { data } = await octokit.repos.getContent({
      owner: REPO_OWNER,
      repo: REPO_NAME,
      path: DB_FILE,
    });
    const content = Buffer.from(data.content, "base64").toString("utf-8");
    return { data: JSON.parse(content), sha: data.sha };
  } catch (e) {
    if (e.status === 404) return { data: { users: [] }, sha: null };
    throw e;
  }
}

async function writeDB(dbData, sha) {
  const content = Buffer.from(JSON.stringify(dbData, null, 2)).toString("base64");
  await octokit.repos.createOrUpdateFileContents({
    owner: REPO_OWNER,
    repo: REPO_NAME,
    path: DB_FILE,
    message: `db: update users [${new Date().toISOString()}]`,
    content,
    ...(sha ? { sha } : {}),
  });
}

function hashPassword(password) {
  return crypto.createHash("sha256").update(password + JWT_SECRET).digest("hex");
}

// --- Main handler ---
module.exports = async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") return res.status(200).end();

  const { action } = req.query;

  // --- VERIFY TOKEN ---
  if (req.method === "GET" && action === "verify") {
    const auth = req.headers.authorization?.replace("Bearer ", "");
    if (!auth) return res.status(401).json({ error: "No token" });
    const payload = verifyJWT(auth);
    if (!payload) return res.status(401).json({ error: "Invalid token" });
    return res.status(200).json({ ok: true, username: payload.username, created_at: payload.created_at });
  }

  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  const { username, password } = req.body || {};

  if (!username || !password) {
    return res.status(400).json({ error: "username and password required" });
  }
  if (username.length < 3 || username.length > 20) {
    return res.status(400).json({ error: "Username must be 3–20 characters" });
  }
  if (password.length < 6) {
    return res.status(400).json({ error: "Password must be at least 6 characters" });
  }

  const { data: db, sha } = await readDB();

  // --- REGISTER ---
  if (action === "register") {
    const exists = db.users.find((u) => u.username.toLowerCase() === username.toLowerCase());
    if (exists) return res.status(409).json({ error: "Username already taken" });

    const newUser = {
      username,
      password_hash: hashPassword(password),
      created_at: new Date().toISOString(),
    };
    db.users.push(newUser);
    await writeDB(db, sha);

    const token = signJWT({
      username,
      created_at: newUser.created_at,
      exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7, // 7 days
    });
    return res.status(201).json({ ok: true, token, username, created_at: newUser.created_at });
  }

  // --- LOGIN ---
  if (action === "login") {
    const user = db.users.find(
      (u) =>
        u.username.toLowerCase() === username.toLowerCase() &&
        u.password_hash === hashPassword(password)
    );
    if (!user) return res.status(401).json({ error: "Invalid username or password" });

    const token = signJWT({
      username: user.username,
      created_at: user.created_at,
      exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7,
    });
    return res.status(200).json({ ok: true, token, username: user.username, created_at: user.created_at });
  }

  return res.status(400).json({ error: "Unknown action" });
};
