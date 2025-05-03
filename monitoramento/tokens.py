"""
talvez o monitoramento precise de uma classe em
"""

import sqlite3
import datetime
from typing import Optional, Tuple, List, NamedTuple, Iterable


class GuildUsage(NamedTuple):
    uso: int
    guild_id: str
    requests: int


class Tokens():
    def __init__(self):
        self.conn = sqlite3.connect("messages.db")
        self.cursor = self.conn.cursor()
        self._create_table()
    
    def _create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens_usage 
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uso INT,
                guild_id TEXT,
                requests INT DEFAULT 1,
                hora TEXT,
                dia_mes TEXT,
            )
        """)
        self.conn.commit()

    @property
    def _hora_atual(self) -> int:
        return datetime.datetime.now().hour

    @property
    def dia_mes_atual(self) -> str:
        dia_mes = datetime.date.today()
        dia_mes_str = f"{dia_mes.day}-{dia_mes.month}"
        return dia_mes_str
    
    @property
    def get_usage_order_uso(self) -> Optional[List[GuildUsage]]:
        self.cursor.execute("""
            SELECT * FROM tokens_usage
            WHERE dia_mes = ? AND hora = ?
            ORDER BY uso DESC
        """, (self.dia_mes_atual, self._hora_atual))
        rows = self.cursor.fetchall()
        return [GuildUsage(uso=row[1], guild_id=row[2], requests=row[3]) for row in rows] if rows else None

    def tokens_count(self, guild_id: int) -> Optional[GuildUsage]:
        self.cursor("""
            SELECT * FROM tokens_usage 
            WHERE guild_id = ? 
            ORDER BY id DESC LIMIT 1
        """, (str(guild_id),))
        row = self.cursor.fetchone()
        return GuildUsage(uso=row[1], guild_id=row[2], requests=row[3]) if row else None
    
    def insert_usage(self, uso: int, guild_id:int):
        self.cursor.execute("""
            SELECT * FROM tokens_usage
            WHERE dia_mes = ? AND guild_id = ? AND hora = ?
        """, (self.dia_mes_atual, str(guild_id), self._hora_atual))
        if self.cursor.fetchone():
            self.cursor.execute("""
                UPDATE tokens_usage
                SET uso = uso + ?
                    requests = requests + 1
                WHERE guild_id = ? AND dia_mes = ? AND hora = ?
            """, (uso, str(guild_id), self.dia_mes_atual, self._hora_atual))
            self.conn.commit()
        else:
            self.cursor.execute(
                """INSERT INTO tokens_usage (uso, guild_id, hora, dia_mes)
                VALUES (?, ?, ?, ?)
                """,
                (uso, str(guild_id), self._hora_atual, self.dia_mes_atual))
            self.conn.commit()
    
    def close(self):
        self.conn.close()