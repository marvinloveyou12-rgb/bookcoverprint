import sys
import os

# PythonAnywhere: 대시보드의 실제 경로로 교체하세요
# 예) /home/jookyoung/mysite
path = os.environ.get('PROJECT_PATH', '/home/jookyoung/mysite')
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
