import sqlite3
import datetime
from typing import Optional, List, NamedTuple, Tuple, Iterable

class GuildUsage(NamedTuple):
    uso: int
    guild_id: str
    requests: int

# classe de monitoramento

class Tokens:
    """
    gerencia a conexão e as operações com o banco de dados sqlite
    para monitorar o uso de tokens por servidor (guild)
    """
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """
        cria a tabela 'tokens_usage' se ela não existir.
        adiciona um índice único para guild_id, dia_mes e hora para otimizar
        a inserção e evitar duplicatas
        """
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens_usage
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uso INTEGER NOT NULL,
                guild_id TEXT NOT NULL,
                requests INTEGER DEFAULT 1,
                hora INTEGER NOT NULL,
                dia_mes TEXT NOT NULL,
                UNIQUE(guild_id, dia_mes, hora)
            )
        """)
        self.conn.commit()

    # propriedades de data e hora 

    @property
    def _hora_atual(self) -> int:
        """retorna a hora atual como um número inteiro"""
        return datetime.datetime.now().hour

    @property
    def dia_mes_atual(self) -> str:
        """retorna o dia e o mês atuais no formato 'dd-mm'"""
        return datetime.date.today().strftime("%d-%m")

    # métodos de consulta

    def get_usage_order_uso(self) -> Optional[List[GuildUsage]]:
        """
        busca todos os registros da hora atual, ordenados pelo maior uso de tokens
        retorna uma lista de GuildUsage ou None se não houver registros
        """
        self.cursor.execute("""
            SELECT uso, guild_id, requests FROM tokens_usage
            WHERE dia_mes = ? AND hora = ?
            ORDER BY uso DESC
        """, (self.dia_mes_atual, self._hora_atual))
        rows = self.cursor.fetchall()
        # usa list comprehension para converter as tuplas do banco de dados em objetos GuildUsage
        return [GuildUsage(uso=row[0], guild_id=row[1], requests=row[2]) for row in rows] if rows else None

    def tokens_count(self, guild_id: int | str) -> Optional[GuildUsage]:
        """
        busca o registro de uso mais recente para uma guild específica
        retorna um objeto GuildUsage ou None se a guild não for encontrada
        """
        self.cursor.execute("""
            SELECT uso, guild_id, requests FROM tokens_usage
            WHERE guild_id = ?
            ORDER BY id DESC LIMIT 1
        """, (str(guild_id),))
        row = self.cursor.fetchone()
        return GuildUsage(uso=row[0], guild_id=row[1], requests=row[2]) if row else None

    # métodos de modificação

    def insert_usage(self, uso: int, guild_id: int | str):
        """
        insere ou atualiza o uso de tokens para uma guild na hora atual
        usa a cláusula 'on conflict' para realizar um 'upsert' atômico,
        o que é mais eficiente e seguro do que verificar antes de inserir
        """
        guild_id_str = str(guild_id)
        
        self.cursor.execute("""
            INSERT INTO tokens_usage (uso, guild_id, hora, dia_mes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, dia_mes, hora) DO UPDATE SET
                uso = uso + excluded.uso,
                requests = requests + 1
        """, (uso, guild_id_str, self._hora_atual, self.dia_mes_atual))
        self.conn.commit()

    # fechamento da conexão 

    def close(self):
        """fecha a conexão com o banco de dados."""
        if self.conn:
            self.conn.close()