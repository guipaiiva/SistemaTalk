import sqlite3
import os
import bcrypt  # mesmo algoritmo usado no auth.py

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            perfil        TEXT    NOT NULL CHECK(perfil IN ('admin', 'diretoria', 'logistica')),
            ativo         INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS execucoes (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL REFERENCES users(id),
            script   TEXT    NOT NULL,
            status   TEXT    NOT NULL CHECK(status IN ('rodando', 'concluido', 'erro')),
            inicio   TEXT    NOT NULL,
            fim      TEXT
        )
    """)

    # Cria usuário admin padrão se não existir (hash bcrypt, igual ao auth.py)
    senha_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
    c.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, perfil)
        VALUES (?, ?, 'admin')
    """, ("admin", senha_hash))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco criado em: {DB_PATH}")
    print("Usuário padrão: admin / admin123")
