"""tools 스크립트 공용: backend/.env 를 읽고 소유자 계정 DB 연결을 돌려줌 (어느 폴더에서 실행해도 동작)"""
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))

import app_config  # noqa: E402


def connect():
    return app_config._owner_conn()


def utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
