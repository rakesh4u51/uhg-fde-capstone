import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv(dotenv_path=".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing from .env"
    )


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    )