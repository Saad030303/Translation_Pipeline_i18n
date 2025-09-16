import sqlite3
from typing import Optional

SCHEMA = '''
CREATE TABLE IF NOT EXISTS cache (
  source TEXT NOT NULL,
  locale TEXT NOT NULL,
  translated TEXT NOT NULL,
  PRIMARY KEY (source, locale)
);
'''

class TranslationCache:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def get(self, source: str, locale: str) -> Optional[str]:
        cur = self.conn.execute("SELECT translated FROM cache WHERE source=? AND locale=?", (source, locale))
        row = cur.fetchone()
        return row[0] if row else None

    def put(self, source: str, locale: str, translated: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO cache (source, locale, translated) VALUES (?, ?, ?)", (source, locale, translated))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
