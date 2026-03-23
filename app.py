from flask import Flask, request, jsonify, send_from_directory, Response
import sqlite3
import requests
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'users.db')

NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID',     'rz8M1F7jEGGpakTwC0ys')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '2d5o89fCCt')

ALLOWED_IMG_HOSTS = (
    'https://books.google',
    'https://shopping-phinf.pstatic.net',
    'https://bookthumb-phinf.pstatic.net',
    'https://thumbnail.image.rakuten.co.jp',
)

# ── DB 초기화 ───────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            gender     TEXT NOT NULL,
            birth      TEXT NOT NULL,
            user_id    TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            email      TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    db.commit()
    db.close()

init_db()

# ── 정적 파일 서빙 ──────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/books.html')
def books():
    return send_from_directory(BASE_DIR, 'books.html')

# ── 회원가입 ────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    data     = request.get_json()
    name     = data.get('name', '').strip()
    gender   = data.get('gender', '').strip()
    birth    = data.get('birth', '').strip()
    user_id  = data.get('userId', '').strip()
    password = data.get('password', '')
    email    = data.get('email', '').strip()

    if not all([name, gender, birth, user_id, password, email]):
        return jsonify(success=False, message='모든 항목을 입력해주세요.'), 400

    try:
        db = get_db()
        db.execute(
            'INSERT INTO users (name, gender, birth, user_id, password, email) VALUES (?,?,?,?,?,?)',
            (name, gender, birth, user_id, password, email)
        )
        db.commit()
        db.close()
        return jsonify(success=True, message='회원가입이 완료되었습니다!')
    except sqlite3.IntegrityError as e:
        field = '아이디' if 'user_id' in str(e) else '이메일'
        return jsonify(success=False, message=f'이미 사용 중인 {field}입니다.'), 400
    except Exception:
        return jsonify(success=False, message='서버 오류가 발생했습니다.'), 500

# ── 유저 목록 ────────────────────────────────────────────
@app.route('/api/users')
def users():
    db   = get_db()
    rows = db.execute('SELECT id, name, gender, birth, user_id, email, created_at FROM users').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

# ── 이미지 프록시 (Google Books + 네이버 Pstatic) ────────
@app.route('/api/image-proxy')
def image_proxy():
    url = request.args.get('url', '')
    if not url or not any(url.startswith(h) for h in ALLOWED_IMG_HOSTS):
        return '허용되지 않는 URL입니다.', 400
    try:
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if not resp.ok:
            return '이미지를 가져올 수 없습니다.', 502
        content_type = resp.headers.get('content-type', 'image/jpeg')
        return Response(
            resp.content,
            content_type=content_type,
            headers={'Cache-Control': 'public, max-age=86400'}
        )
    except Exception:
        return '프록시 오류', 500

# ── 네이버 도서 검색 프록시 ───────────────────────────────
@app.route('/api/naver-books')
def naver_books():
    q       = request.args.get('q', '').strip()
    start   = request.args.get('start', '1')
    display = request.args.get('display', '40')
    sort    = request.args.get('sort', 'date')

    if not q:
        return jsonify(error='q 파라미터 필요'), 400

    api_url = (
        f'https://openapi.naver.com/v1/search/book.json'
        f'?query={requests.utils.quote(q)}'
        f'&start={start}'
        f'&display={display}'
        f'&sort={sort}'
    )
    try:
        resp = requests.get(api_url, headers={
            'X-Naver-Client-Id':     NAVER_CLIENT_ID,
            'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
        }, timeout=10)
        return Response(resp.content, status=resp.status_code, content_type='application/json')
    except Exception:
        return jsonify(error='네이버 API 연결 오류'), 500

if __name__ == '__main__':
    app.run(debug=False)
