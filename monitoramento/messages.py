import sqlite3
import datetime
import discord

class Messages:
    """
    gerencia o salvamento do histórico de mensagens no banco de dados
    """
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        """cria a tabela 'messages' se ela não existir"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages
            (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL UNIQUE,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER,
                author_id INTEGER NOT NULL,
                content TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def insert_message(self, message: discord.Message):
        """
        insere um registro de uma mensagem no banco de dados
        ignora a inserção se a mensagem já existir para evitar duplicatas
        """
        self.cursor.execute(
            """
            INSERT OR IGNORE INTO messages (message_id, channel_id, guild_id, author_id, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.channel.id,
                message.guild.id if message.guild else None,
                message.author.id,
                message.content,
                message.created_at.isoformat()
            )
        )
        self.conn.commit()