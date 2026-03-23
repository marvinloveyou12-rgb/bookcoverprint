from flask import Flask, request, jsonify, send_from_directory, Response
import sqlite3
import requests
import os
import urllib.parse

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'users.db')

NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID',     'rz8M1F7jEGGpakTwC0ys')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '2d5o89fCCt')

ALLOWED_IMG_HOSTS = (
    'https://books.google',
    'https://shopping-phinf.pstatic.net',
    'https://bookthumb-phinf.pstatic.net',
)


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


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/books.html')
def books():
    return send_from_directory(BASE_DIR, 'books.html')


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
        return jsonify(success=False, message='이미 사용 중인 ' + field + '입니다.'), 400
    except Exception:
        return jsonify(success=False, message='서버 오류가 발생했습니다.'), 500


@app.route('/api/users')
def users():
    db   = get_db()
    rows = db.execute('SELECT id, name, gender, birth, user_id, email, created_at FROM users').fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/image-proxy')
def image_proxy():
    url = request.args.get('url', '')
    if not url or not any(url.startswith(h) for h in ALLOWED_IMG_HOSTS):
        return 'Not allowed', 400
    try:
        resp = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if not resp.ok:
            return 'Error', 502
        return Response(
            resp.content,
            content_type=resp.headers.get('content-type', 'image/jpeg'),
            headers={'Cache-Control': 'public, max-age=86400'}
        )
    except Exception:
        return 'Proxy error', 500


@app.route('/api/naver-books')
def naver_books():
    q       = request.args.get('q', '').strip()
    start   = request.args.get('start', '1')
    display = request.args.get('display', '40')
    sort    = request.args.get('sort', 'date')

    if not q:
        return jsonify(error='q parameter required'), 400

    api_url = (
        'https://openapi.naver.com/v1/search/book.json'
        '?query=' + urllib.parse.quote(q) +
        '&start=' + start +
        '&display=' + display +
        '&sort=' + sort
    )
    try:
        resp = requests.get(api_url, headers={
            'X-Naver-Client-Id':     NAVER_CLIENT_ID,
            'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
        }, timeout=10)
        return Response(resp.content, status=resp.status_code, content_type='application/json')
    except Exception:
        return jsonify(error='Naver API error'), 500


if __name__ == '__main__':
    app.run(debug=True)
