from flask import Flask, request, jsonify, send_from_directory, Response, session, redirect
import sqlite3
import requests
import os
import urllib.parse
import hashlib
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'users.db')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin1234')

# 네이버 책 검색 API
NAVER_CLIENT_ID     = os.environ.get('NAVER_CLIENT_ID',     'rz8M1F7jEGGpakTwC0ys')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '2d5o89fCCt')

# Google OAuth
GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID',     '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Naver OAuth (책 검색과 별개)
NAVER_OAUTH_ID     = os.environ.get('NAVER_OAUTH_CLIENT_ID',     '')
NAVER_OAUTH_SECRET = os.environ.get('NAVER_OAUTH_CLIENT_SECRET', '')

# Kakao OAuth
KAKAO_CLIENT_ID     = os.environ.get('KAKAO_CLIENT_ID',     '')
KAKAO_CLIENT_SECRET = os.environ.get('KAKAO_CLIENT_SECRET', '')

ALLOWED_IMG_HOSTS = (
    'https://books.google',
    'https://shopping-phinf.pstatic.net',
    'https://bookthumb-phinf.pstatic.net',
)


# ── 비밀번호 해시 ─────────────────────────────────────────

def hash_password(password):
    salt = secrets.token_hex(16)
    key  = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ':' + key.hex()


def check_password(password, stored):
    if not stored:
        return False
    if ':' not in stored:          # 기존 평문 비밀번호 호환
        return password == stored
    salt, key_hex = stored.split(':', 1)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return key.hex() == key_hex


# ── DB ────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            gender         TEXT NOT NULL DEFAULT '',
            birth          TEXT NOT NULL DEFAULT '',
            user_id        TEXT NOT NULL UNIQUE,
            password       TEXT NOT NULL DEFAULT '',
            email          TEXT NOT NULL UNIQUE,
            oauth_provider TEXT,
            oauth_id       TEXT,
            created_at     TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_db_id INTEGER,
            user_login TEXT,
            login_type TEXT,
            ip         TEXT,
            user_agent TEXT,
            success    INTEGER,
            message    TEXT,
            logged_at  TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS print_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_db_id      INTEGER NOT NULL,
            user_login      TEXT,
            book_title      TEXT,
            book_author     TEXT,
            book_isbn       TEXT,
            book_publisher  TEXT,
            book_cover_url  TEXT,
            print_type      TEXT,
            printed_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    ''')
    # 기존 users 테이블에 oauth 컬럼이 없으면 추가
    cols = [r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()]
    if 'oauth_provider' not in cols:
        db.execute("ALTER TABLE users ADD COLUMN oauth_provider TEXT")
    if 'oauth_id' not in cols:
        db.execute("ALTER TABLE users ADD COLUMN oauth_id TEXT")
    db.commit()
    db.close()


def log_login(user_db_id, user_login, login_type, success, message=''):
    try:
        db = get_db()
        db.execute(
            '''INSERT INTO login_logs
               (user_db_id, user_login, login_type, ip, user_agent, success, message)
               VALUES (?,?,?,?,?,?,?)''',
            (user_db_id, user_login, login_type,
             request.remote_addr,
             request.headers.get('User-Agent', '')[:300],
             1 if success else 0,
             message)
        )
        db.commit()
        db.close()
    except Exception:
        pass


def get_current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    db.close()
    return user


def get_base_url():
    proto = request.headers.get('X-Forwarded-Proto', 'http')
    if 'localhost' in request.host or '127.0.0.1' in request.host:
        proto = 'http'
    return f'{proto}://{request.host}'


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify(error='관리자 권한이 필요합니다.'), 403
        return f(*args, **kwargs)
    return decorated


init_db()


# ── 정적 파일 ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/books.html')
def books():
    return send_from_directory(BASE_DIR, 'books.html')

@app.route('/admin')
def admin_page():
    return send_from_directory(BASE_DIR, 'admin.html')


# ── 인증 API ──────────────────────────────────────────────

@app.route('/api/me')
def me():
    user = get_current_user()
    if not user:
        return jsonify(logged_in=False)
    return jsonify(
        logged_in=True,
        id=user['id'],
        name=user['name'],
        user_id=user['user_id'],
        email=user['email'],
        oauth_provider=user['oauth_provider'] or 'local'
    )


@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json() or {}
    user_id  = data.get('userId', '').strip()
    password = data.get('password', '')

    if not user_id or not password:
        return jsonify(success=False, message='아이디와 비밀번호를 입력해주세요.'), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    db.close()

    if not user or not check_password(password, user['password']):
        log_login(None, user_id, 'local', False, '아이디 또는 비밀번호 오류')
        return jsonify(success=False, message='아이디 또는 비밀번호가 올바르지 않습니다.'), 401

    session['user_id']    = user['id']
    session['user_login'] = user['user_id']
    log_login(user['id'], user['user_id'], 'local', True)
    return jsonify(success=True, name=user['name'])


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify(success=True)


@app.route('/api/register', methods=['POST'])
def register():
    data     = request.get_json() or {}
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
            (name, gender, birth, user_id, hash_password(password), email)
        )
        db.commit()
        db.close()
        return jsonify(success=True, message='회원가입이 완료되었습니다!')
    except sqlite3.IntegrityError as e:
        field = '아이디' if 'user_id' in str(e) else '이메일'
        return jsonify(success=False, message='이미 사용 중인 ' + field + '입니다.'), 400
    except Exception:
        return jsonify(success=False, message='서버 오류가 발생했습니다.'), 500


# ── OAuth 공통 ────────────────────────────────────────────

def _oauth_finish(email, name, provider, oauth_id):
    """OAuth 로그인 후 DB에 유저 찾기/생성 후 세션 설정"""
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE oauth_provider=? AND oauth_id=?',
        (provider, oauth_id)
    ).fetchone()

    if not user and email:
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()

    if not user:
        # 자동 회원가입
        uid = f'{provider}_{oauth_id}'
        mail = email or f'{uid}@oauth.local'
        try:
            db.execute(
                '''INSERT INTO users (name, gender, birth, user_id, password, email, oauth_provider, oauth_id)
                   VALUES (?,?,?,?,?,?,?,?)''',
                (name, '', '', uid, '', mail, provider, oauth_id)
            )
            db.commit()
            user = db.execute('SELECT * FROM users WHERE user_id=?', (uid,)).fetchone()
        except sqlite3.IntegrityError:
            db.close()
            return redirect('/?msg=이미+등록된+이메일입니다&type=error')
    else:
        if not user['oauth_provider']:
            db.execute(
                'UPDATE users SET oauth_provider=?, oauth_id=? WHERE id=?',
                (provider, oauth_id, user['id'])
            )
            db.commit()

    db.close()
    session['user_id']    = user['id']
    session['user_login'] = user['user_id']
    log_login(user['id'], user['user_id'], provider, True)
    return redirect('/')


# ── Google OAuth ──────────────────────────────────────────

@app.route('/auth/google')
def auth_google():
    if not GOOGLE_CLIENT_ID:
        return redirect('/?msg=구글+OAuth+키가+설정되지+않았습니다&type=error')
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = urllib.parse.urlencode({
        'client_id':     GOOGLE_CLIENT_ID,
        'redirect_uri':  get_base_url() + '/auth/google/callback',
        'response_type': 'code',
        'scope':         'openid email profile',
        'state':         state,
    })
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + params)


@app.route('/auth/google/callback')
def auth_google_callback():
    state = request.args.get('state')
    if state != session.pop('oauth_state', None):
        return redirect('/?msg=인증+오류(state+불일치)&type=error')
    code = request.args.get('code')
    if not code:
        return redirect('/?msg=구글+인증에+실패했습니다&type=error')
    try:
        tok = requests.post('https://oauth2.googleapis.com/token', data={
            'code':          code,
            'client_id':     GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri':  get_base_url() + '/auth/google/callback',
            'grant_type':    'authorization_code',
        }, timeout=10).json()
        info = requests.get('https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {tok.get("access_token")}'},
            timeout=10).json()
    except Exception:
        return redirect('/?msg=구글+서버+연결+오류&type=error')
    return _oauth_finish(info.get('email', ''), info.get('name', ''), 'google', str(info.get('id', '')))


# ── Naver OAuth ───────────────────────────────────────────

@app.route('/auth/naver')
def auth_naver():
    if not NAVER_OAUTH_ID:
        return redirect('/?msg=네이버+OAuth+키가+설정되지+않았습니다&type=error')
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id':     NAVER_OAUTH_ID,
        'redirect_uri':  get_base_url() + '/auth/naver/callback',
        'state':         state,
    })
    return redirect('https://nid.naver.com/oauth2.0/authorize?' + params)


@app.route('/auth/naver/callback')
def auth_naver_callback():
    state = request.args.get('state')
    if state != session.pop('oauth_state', None):
        return redirect('/?msg=인증+오류(state+불일치)&type=error')
    code = request.args.get('code')
    if not code:
        return redirect('/?msg=네이버+인증에+실패했습니다&type=error')
    try:
        tok = requests.get('https://nid.naver.com/oauth2.0/token', params={
            'grant_type':    'authorization_code',
            'client_id':     NAVER_OAUTH_ID,
            'client_secret': NAVER_OAUTH_SECRET,
            'code':          code,
            'state':         state,
        }, timeout=10).json()
        info = requests.get('https://openapi.naver.com/v1/nid/me',
            headers={'Authorization': f'Bearer {tok.get("access_token")}'},
            timeout=10).json().get('response', {})
    except Exception:
        return redirect('/?msg=네이버+서버+연결+오류&type=error')
    return _oauth_finish(info.get('email', ''), info.get('name', ''), 'naver', str(info.get('id', '')))


# ── Kakao OAuth ───────────────────────────────────────────

@app.route('/auth/kakao')
def auth_kakao():
    if not KAKAO_CLIENT_ID:
        return redirect('/?msg=카카오+OAuth+키가+설정되지+않았습니다&type=error')
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    params = urllib.parse.urlencode({
        'client_id':     KAKAO_CLIENT_ID,
        'redirect_uri':  get_base_url() + '/auth/kakao/callback',
        'response_type': 'code',
        'state':         state,
    })
    return redirect('https://kauth.kakao.com/oauth/authorize?' + params)


@app.route('/auth/kakao/callback')
def auth_kakao_callback():
    state = request.args.get('state')
    if state != session.pop('oauth_state', None):
        return redirect('/?msg=인증+오류(state+불일치)&type=error')
    code = request.args.get('code')
    if not code:
        return redirect('/?msg=카카오+인증에+실패했습니다&type=error')
    try:
        tok = requests.post('https://kauth.kakao.com/oauth/token', data={
            'grant_type':   'authorization_code',
            'client_id':    KAKAO_CLIENT_ID,
            'client_secret': KAKAO_CLIENT_SECRET,
            'redirect_uri': get_base_url() + '/auth/kakao/callback',
            'code':         code,
        }, timeout=10).json()
        udata = requests.get('https://kapi.kakao.com/v2/user/me',
            headers={'Authorization': f'Bearer {tok.get("access_token")}'},
            timeout=10).json()
    except Exception:
        return redirect('/?msg=카카오+서버+연결+오류&type=error')
    account = udata.get('kakao_account', {})
    profile = account.get('profile', {})
    email   = account.get('email', '')
    name    = profile.get('nickname', '') or email.split('@')[0] or f'kakao_{udata.get("id","")}'
    return _oauth_finish(email, name, 'kakao', str(udata.get('id', '')))


# ── 관리자 API ────────────────────────────────────────────

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    if data.get('password', '') == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify(success=True)
    return jsonify(success=False, message='비밀번호가 올바르지 않습니다.'), 401


@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify(success=True)


@app.route('/api/admin/status')
def admin_status():
    return jsonify(is_admin=bool(session.get('is_admin')))


@app.route('/api/admin/users')
@admin_required
def admin_users():
    db   = get_db()
    rows = db.execute(
        'SELECT id, name, gender, birth, user_id, email, oauth_provider, created_at FROM users ORDER BY id DESC'
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/logs')
@admin_required
def admin_logs():
    limit = min(int(request.args.get('limit', 200)), 1000)
    db    = get_db()
    rows  = db.execute(
        'SELECT * FROM login_logs ORDER BY id DESC LIMIT ?', (limit,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (uid,))
    db.commit()
    db.close()
    return jsonify(success=True)


@app.route('/api/admin/print-logs')
@admin_required
def admin_print_logs():
    limit = min(int(request.args.get('limit', 200)), 1000)
    db    = get_db()
    rows  = db.execute(
        'SELECT * FROM print_logs ORDER BY id DESC LIMIT ?', (limit,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    db = get_db()
    total_users  = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_logs   = db.execute('SELECT COUNT(*) FROM login_logs').fetchone()[0]
    today_logins = db.execute(
        "SELECT COUNT(*) FROM login_logs WHERE date(logged_at)=date('now','localtime') AND success=1"
    ).fetchone()[0]
    failed_today = db.execute(
        "SELECT COUNT(*) FROM login_logs WHERE date(logged_at)=date('now','localtime') AND success=0"
    ).fetchone()[0]
    db.close()
    return jsonify(total_users=total_users, total_logs=total_logs,
                   today_logins=today_logins, failed_today=failed_today)


# ── 인쇄 기록 API ────────────────────────────────────────

@app.route('/api/print-log', methods=['POST'])
def print_log():
    user = get_current_user()
    if not user:
        return jsonify(success=False, message='로그인 필요'), 401
    data  = request.get_json() or {}
    books = data.get('books', [])
    ptype = data.get('print_type', 'front')
    db = get_db()
    for b in books:
        db.execute(
            '''INSERT INTO print_logs
               (user_db_id, user_login, book_title, book_author, book_isbn,
                book_publisher, book_cover_url, print_type)
               VALUES (?,?,?,?,?,?,?,?)''',
            (user['id'], user['user_id'],
             b.get('title',''), b.get('author',''), b.get('isbn',''),
             b.get('publisher',''), b.get('cover_url',''), ptype)
        )
    db.commit()
    db.close()
    return jsonify(success=True)


@app.route('/api/my-prints')
def my_prints():
    user = get_current_user()
    if not user:
        return jsonify(error='로그인 필요'), 401
    db   = get_db()
    rows = db.execute(
        'SELECT * FROM print_logs WHERE user_db_id=? ORDER BY id DESC LIMIT 200',
        (user['id'],)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ── 기존 API ──────────────────────────────────────────────

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
        '&start=' + start + '&display=' + display + '&sort=' + sort
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
    app.run(debug=True, port=3001)
