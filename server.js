const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');
const fetch = require('node-fetch');

const app = express();
const db = new Database('users.db');

const NAVER_CLIENT_ID     = process.env.NAVER_CLIENT_ID     || 'rz8M1F7jEGGpakTwC0ys';
const NAVER_CLIENT_SECRET = process.env.NAVER_CLIENT_SECRET || '2d5o89fCCt';

// 테이블 생성
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL,
    gender   TEXT NOT NULL,
    birth    TEXT NOT NULL,
    user_id  TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    email    TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
  )
`);

app.use(express.json());
app.use(express.static(path.join(__dirname)));

// ── 회원가입 ────────────────────────────────────────────
app.post('/api/register', (req, res) => {
  const { name, gender, birth, userId, password, email } = req.body;
  try {
    const stmt = db.prepare(`
      INSERT INTO users (name, gender, birth, user_id, password, email)
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    stmt.run(name, gender, birth, userId, password, email);
    res.json({ success: true, message: '회원가입이 완료되었습니다!' });
  } catch (err) {
    if (err.message.includes('UNIQUE')) {
      const field = err.message.includes('user_id') ? '아이디' : '이메일';
      res.status(400).json({ success: false, message: `이미 사용 중인 ${field}입니다.` });
    } else {
      res.status(500).json({ success: false, message: '서버 오류가 발생했습니다.' });
    }
  }
});

// ── 유저 목록 조회 ───────────────────────────────────────
app.get('/api/users', (req, res) => {
  const users = db.prepare('SELECT id, name, gender, birth, user_id, email, created_at FROM users').all();
  res.json(users);
});

// ── 이미지 프록시 (Google Books + 네이버 Pstatic) ────────
const ALLOWED_IMG_HOSTS = [
  'https://books.google',
  'https://shopping-phinf.pstatic.net',
  'https://bookthumb-phinf.pstatic.net',
  'https://thumbnail.image.rakuten.co.jp',
];

app.get('/api/image-proxy', async (req, res) => {
  const { url } = req.query;
  if (!url || !ALLOWED_IMG_HOSTS.some(h => url.startsWith(h))) {
    return res.status(400).send('허용되지 않는 URL입니다.');
  }
  try {
    const response = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      timeout: 10000,
    });
    if (!response.ok) return res.status(502).send('이미지를 가져올 수 없습니다.');
    const buffer = await response.buffer();
    const contentType = response.headers.get('content-type') || 'image/jpeg';
    res.set('Content-Type', contentType);
    res.set('Cache-Control', 'public, max-age=86400');
    res.send(buffer);
  } catch (e) {
    res.status(500).send('프록시 오류');
  }
});

// ── 네이버 도서 검색 프록시 ───────────────────────────────
app.get('/api/naver-books', async (req, res) => {
  const { q, start = 1, display = 40, sort = 'date' } = req.query;
  if (!q) return res.status(400).json({ error: 'q 파라미터 필요' });

  try {
    const apiUrl = `https://openapi.naver.com/v1/search/book.json`
      + `?query=${encodeURIComponent(q)}`
      + `&start=${start}`
      + `&display=${display}`
      + `&sort=${sort}`;

    const response = await fetch(apiUrl, {
      headers: {
        'X-Naver-Client-Id':     NAVER_CLIENT_ID,
        'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
      },
    });

    if (!response.ok) {
      const errText = await response.text();
      return res.status(response.status).json({ error: errText });
    }

    const data = await response.json();
    res.json(data);
  } catch (e) {
    res.status(500).json({ error: '네이버 API 연결 오류' });
  }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`서버 실행 중: http://localhost:${PORT}`);
});
