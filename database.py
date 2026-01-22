"""
Módulo de banco de dados SQLite para o Bot de Música
Gerencia histórico de reprodução e músicas favoritas
"""

import sqlite3
import os
from datetime import datetime

class MusicDatabase:
    def __init__(self, db_path=None):
        if db_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(script_dir, "music_bot.db")

        self.db_path = db_path
        self.init_database()

    def get_connection(self):
        """Retorna conexão com o banco"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Cria as tabelas se não existirem"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Tabela de histórico
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT,
                thumbnail TEXT,
                duration INTEGER DEFAULT 0,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                guild_id INTEGER,
                guild_name TEXT
            )
        ''')

        # Tabela de favoritos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                thumbnail TEXT,
                duration INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Índices para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_title ON favorites(title)')

        conn.commit()
        conn.close()

    # === HISTÓRICO ===

    def add_to_history(self, title, url=None, thumbnail=None, duration=0, guild_id=None, guild_name=None):
        """Adiciona música ao histórico"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO history (title, url, thumbnail, duration, guild_id, guild_name)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, url, thumbnail, duration, guild_id, guild_name))

        conn.commit()
        conn.close()

    def get_history(self, limit=50, offset=0):
        """Retorna histórico de músicas"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM history
            ORDER BY played_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_history_count(self):
        """Retorna total de músicas no histórico"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM history')
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def clear_history(self):
        """Limpa todo o histórico"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM history')

        conn.commit()
        conn.close()

    def search_history(self, query, limit=20):
        """Busca no histórico"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM history
            WHERE title LIKE ?
            ORDER BY played_at DESC
            LIMIT ?
        ''', (f'%{query}%', limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # === FAVORITOS ===

    def add_favorite(self, title, url, thumbnail=None, duration=0):
        """Adiciona música aos favoritos"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO favorites (title, url, thumbnail, duration, added_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (title, url, thumbnail, duration))

            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False

        conn.close()
        return success

    def remove_favorite(self, url):
        """Remove música dos favoritos"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM favorites WHERE url = ?', (url,))

        conn.commit()
        conn.close()

    def is_favorite(self, url):
        """Verifica se música é favorita"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT 1 FROM favorites WHERE url = ?', (url,))
        result = cursor.fetchone() is not None

        conn.close()
        return result

    def get_favorites(self, limit=100, offset=0):
        """Retorna lista de favoritos"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM favorites
            ORDER BY added_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_favorites_count(self):
        """Retorna total de favoritos"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM favorites')
        count = cursor.fetchone()[0]

        conn.close()
        return count

    def search_favorites(self, query, limit=20):
        """Busca nos favoritos"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM favorites
            WHERE title LIKE ?
            ORDER BY added_at DESC
            LIMIT ?
        ''', (f'%{query}%', limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


# Instância global
db = MusicDatabase()
