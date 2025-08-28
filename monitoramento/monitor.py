import sqlite3
from .tokens import Tokens
from .messages import Messages


class Monitor():
    """
    classe central que inicializa e gerencia todos os monitores do bot
    conecta-se ao banco de dados e disponibiliza as classes de monitoramento
    """
    def __init__(self):
        self.conn = sqlite3.connect("messages.db")
        self.tokens_monitor = Tokens(self.conn)
        self.messages = Messages(self.conn)

    def close(self):
        # fecha a conexão com o banco de dados
        if self.conn:
            self.conn.close()