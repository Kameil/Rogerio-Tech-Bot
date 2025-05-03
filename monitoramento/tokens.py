"""
talvez o monitoramento precise de uma classe em
"""

import sqlite3
from datetime import datetime
from typing import Optional, Tuple, List

class Tokens():
    def __init__(self):
        self.conn = sqlite3.connect("messages.db")
        self.cursor = self.conn.cursor()
        self._create_table()
    
    def _create_table(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS tokens_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, uso INT, dia_mes TEXT, guild_id TEXT)")
        self.conn.commit()

    @property
    def dia_mes_atual(self) -> str:
        dia_mes = datetime.date()
        dia_mes_str = f"{dia_mes.day}-{dia_mes.month}"
        return dia_mes_str
    
    @property
    def uso_de_tokens_order_uso(self) -> Optional[List[Tuple[int, str, str, str]]]:
        self.cursor.execute("""
            SELECT * FROM tokens_usage
            WHERE dia-mes = ? 
            ORDER BY uso DESC
        """, (self.dia_mes_atual,))
        all = self.cursor.fetchall()
        return all if all else None

    def tokens_count(self, guild_id: int) -> Optional[Tuple]:
        self.cursor("SELECT * FROM tokens_usage WHERE guild_id = ? ORDER BY id DESC LIMIT 1", (str(guild_id),))
        r = self.cursor.fetchone()
        return r if r else None
    
    def insert_usage(self, uso: int, guild_id:int, dia_mes = datetime.date()):
        dia_mes_str = f"{dia_mes.day}-{dia_mes.month}"
        self.cursor.execute("""
            SELECT * FROM tokens_usage
            WHERE dia_mes = ? AND guild_id = ?
        """, (dia_mes_str, str(guild_id)))
        if self.cursor.fetchone():
            self.cursor.execute("""
                UPDATE tokens_usage
                SET uso = uso + ?
                WHERE guild_id = ? AND dia_mes = ?
            """, (uso, str(guild_id), dia_mes_str))
        else:
            self.cursor.execute(
                """INSERT INTO tokens_usage (uso, dia, dia_mes, guild_id) 
                VALUES (?, ?, ?)
                """,
                (uso, dia_mes, guild_id))
            self.conn.commit()
    
    def close(self):
        self.conn.close()