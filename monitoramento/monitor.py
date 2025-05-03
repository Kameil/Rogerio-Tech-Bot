import sqlite3
from .tokens import Tokens
from .messages import Messages


class Monitor():
    def __init__(self):
        self.conn = sqlite3.connect("messages.db")
        self.tokens_monitor = Tokens(self.conn)
        self.messages = Messages(self.conn)
    def close(self):
        self.conn.close()