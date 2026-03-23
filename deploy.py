"""
PythonAnywhere 자동 배포 스크립트
실행: python deploy.py
"""
import requests
import os
import sys

# ── 설정 ────────────────────────────────────────────────
USERNAME   = 'jookyoung'
DOMAIN     = f'{USERNAME}.pythonanywhere.com'
API_BASE   = f'https://www.pythonanywhere.com/api/v0/user/{USERNAME}'
REMOTE_DIR = f'/home/{USERNAME}/mysite'

# 배포할 파일 목록
FILES = ['app.py', 'wsgi.py', 'index.html', 'books.html', 'requirements.txt']

WSGI_CONTENT = f"""import sys, os

path = '/home/{USERNAME}/mysite'
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
"""

# ────────────────────────────────────────────────────────
def get_token():
    token = os.environ.get('PA_TOKEN')
    if not token:
        token = input('PythonAnywhere API 토큰 입력 (Account > API Token): ').strip()
    return token

def headers(token):
    return {'Authorization': f'Token {token}'}

def upload_file(token, local_path, remote_path):
    url = f'https://www.pythonanywhere.com/api/v0/user/{USERNAME}/files/path{remote_path}'
    with open(local_path, 'rb') as f:
        resp = requests.post(url, files={'content': f}, headers=headers(token))
    return resp

def upload_text(token, content, remote_path):
    url = f'https://www.pythonanywhere.com/api/v0/user/{USERNAME}/files/path{remote_path}'
    resp = requests.post(url, files={'content': ('file', content.encode(), 'text/plain')}, headers=headers(token))
    return resp

def create_webapp(token):
    url  = f'{API_BASE}/webapps/'
    resp = requests.post(url, data={
        'domain_name':     DOMAIN,
        'python_version':  'python310'
    }, headers=headers(token))
    return resp

def get_webapp(token):
    url  = f'{API_BASE}/webapps/{DOMAIN}/'
    resp = requests.get(url, headers=headers(token))
    return resp

def reload_webapp(token):
    url  = f'{API_BASE}/webapps/{DOMAIN}/reload/'
    resp = requests.post(url, headers=headers(token))
    return resp

def install_packages(token):
    url  = f'{API_BASE}/consoles/'
    # Bash 콘솔 생성 후 pip 설치
    resp = requests.post(url, data={'executable': 'bash'}, headers=headers(token))
    return resp

def run_bash(token, cmd):
    # 콘솔 생성
    url  = f'{API_BASE}/consoles/'
    resp = requests.post(url, data={'executable': 'bash', 'arguments': f'-c "{cmd}"'},
                         headers=headers(token))
    return resp

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token    = get_token()

    print('\n[1/4] 파일 업로드 중...')
    for fname in FILES:
        local  = os.path.join(base_dir, fname)
        remote = f'{REMOTE_DIR}/{fname}'
        resp   = upload_file(token, local, remote)
        if resp.status_code in (200, 201):
            print(f'  ✓ {fname}')
        else:
            print(f'  ✗ {fname} 실패: {resp.status_code} {resp.text}')
            sys.exit(1)

    print('\n[2/4] 웹앱 생성/확인 중...')
    resp = get_webapp(token)
    if resp.status_code == 404:
        resp = create_webapp(token)
        if resp.status_code == 201:
            print(f'  ✓ 웹앱 생성 완료: {DOMAIN}')
        else:
            print(f'  ✗ 웹앱 생성 실패: {resp.status_code} {resp.text}')
            sys.exit(1)
    else:
        print(f'  ✓ 기존 웹앱 확인됨: {DOMAIN}')

    print('\n[3/4] WSGI 파일 설정 중...')
    wsgi_path = f'/var/www/{USERNAME}_pythonanywhere_com_wsgi.py'
    resp = upload_text(token, WSGI_CONTENT, wsgi_path)
    if resp.status_code in (200, 201):
        print(f'  ✓ WSGI 설정 완료')
    else:
        print(f'  ✗ WSGI 설정 실패: {resp.status_code} {resp.text}')

    print('\n[4/4] 웹앱 재시작 중...')
    resp = reload_webapp(token)
    if resp.status_code == 200:
        print(f'  ✓ 재시작 완료')
    else:
        print(f'  ✗ 재시작 실패: {resp.status_code} {resp.text}')

    print(f'\n배포 완료!')
    print(f'접속 주소: https://{DOMAIN}')
    print(f'\n※ PythonAnywhere Bash에서 아래 명령어로 패키지를 설치하세요:')
    print(f'  pip3.10 install --user flask requests')

if __name__ == '__main__':
    main()
