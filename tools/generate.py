import logging
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class ModelUsageRegulator:
    def __init__(self, db_path: str = "uso.db"):
        self.db_path = db_path
        self.RPM = 5  # requests máximo por minuto por modelo
        self.RPD = 20  # requests máximo por dia por modelo
        self.models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
        self._init_database()

    def _init_database(self):
        """Inicializa as tabelas do banco de dados"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Tabela para controle diário (RPD)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                date TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(model_name, date)
            )
        """)

        # Tabela para controle por minuto (RPM)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_minute (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(model_name, timestamp)
            )
        """)

        conn.commit()
        conn.close()

    def _get_current_date(self) -> str:
        """Retorna a data atual no formato YYYY-MM-DD"""
        return datetime.now().strftime("%Y-%m-%d")

    def _get_current_minute(self) -> str:
        """Retorna o timestamp atual no formato YYYY-MM-DD HH:MM"""
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _get_usage_daily(self, model_name: str) -> int:
        """Retorna o uso diário de um modelo"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date = self._get_current_date()
        cursor.execute(
            "SELECT usage_count FROM usage_daily WHERE model_name = ? AND date = ?",
            (model_name, date),
        )

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 0

    def _get_usage_minute(self, model_name: str) -> int:
        """Retorna o uso no minuto atual de um modelo"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = self._get_current_minute()
        cursor.execute(
            "SELECT usage_count FROM usage_minute WHERE model_name = ? AND timestamp = ?",
            (model_name, timestamp),
        )

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else 0

    def _increment_usage(self, model_name: str):
        """Incrementa o contador de uso para RPD e RPM"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date = self._get_current_date()
        timestamp = self._get_current_minute()

        # Incrementa RPD
        cursor.execute(
            """
            INSERT INTO usage_daily (model_name, date, usage_count)
            VALUES (?, ?, 1)
            ON CONFLICT(model_name, date)
            DO UPDATE SET usage_count = usage_count + 1
        """,
            (model_name, date),
        )

        # Incrementa RPM
        cursor.execute(
            """
            INSERT INTO usage_minute (model_name, timestamp, usage_count)
            VALUES (?, ?, 1)
            ON CONFLICT(model_name, timestamp)
            DO UPDATE SET usage_count = usage_count + 1
        """,
            (model_name, timestamp),
        )

        conn.commit()
        conn.close()

    def _can_use_model(self, model_name: str) -> bool:
        """Verifica se um modelo pode ser usado (não excedeu RPM nem RPD)"""
        daily_usage = self._get_usage_daily(model_name)
        minute_usage = self._get_usage_minute(model_name)

        can_use = daily_usage < self.RPD and minute_usage < self.RPM

        if not can_use:
            logger.info(
                f"Modelo {model_name} atingiu limite - "
                f"RPD: {daily_usage}/{self.RPD}, RPM: {minute_usage}/{self.RPM}"
            )

        return can_use

    def get_available_model(self) -> Optional[str]:
        """
        Retorna o próximo modelo disponível que não excedeu os limites.
        Retorna None se todos os modelos estiverem no limite.
        """
        for model in self.models:
            if self._can_use_model(model):
                logger.info(f"Modelo selecionado: {model}")
                return model

        logger.warning("Todos os modelos atingiram seus limites de uso")
        return None

    def register_usage(self, model_name: str) -> bool:
        """
        Registra o uso de um modelo após validação.
        Retorna True se o uso foi registrado com sucesso.
        """
        if not self._can_use_model(model_name):
            logger.warning(f"Tentativa de usar modelo {model_name} que está no limite")
            return False

        self._increment_usage(model_name)
        logger.info(f"Uso registrado para o modelo {model_name}")
        return True

    def get_usage_stats(self) -> dict:
        """Retorna estatísticas de uso de todos os modelos"""
        stats = {}
        for model in self.models:
            stats[model] = {
                "daily_usage": self._get_usage_daily(model),
                "daily_limit": self.RPD,
                "minute_usage": self._get_usage_minute(model),
                "minute_limit": self.RPM,
                "available": self._can_use_model(model),
            }
        return stats

    def rollback_usage(self, model_name: str):
        """
        Reverte o registro de uso em caso de falha na requisição.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        date = self._get_current_date()
        timestamp = self._get_current_minute()

        # Decrementa RPD (não deixa ficar negativo)
        cursor.execute(
            """
                UPDATE usage_daily
                SET usage_count = MAX(0, usage_count - 1)
                WHERE model_name = ? AND date = ?
            """,
            (model_name, date),
        )

        # Decrementa RPM (não deixa ficar negativo)
        cursor.execute(
            """
                UPDATE usage_minute
                SET usage_count = MAX(0, usage_count - 1)
                WHERE model_name = ? AND timestamp = ?
            """,
            (model_name, timestamp),
        )

        conn.commit()
        conn.close()
        logger.info(f"Uso revertido para o modelo {model_name} devido a falha")

    def cleanup_old_data(self, days_to_keep: int = 7):
        """Remove dados antigos do banco (opcional, para manutenção)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = datetime.now()
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_to_keep)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        cursor.execute("DELETE FROM usage_daily WHERE date < ?", (cutoff_str,))
        cursor.execute("DELETE FROM usage_minute WHERE timestamp < ?", (cutoff_str,))

        conn.commit()
        deleted_rows = cursor.rowcount
        conn.close()

        logger.info(f"Limpeza concluída. {deleted_rows} registros removidos")


# Exemplo de uso
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    regulator = ModelUsageRegulator()

    # Simula várias requisições
    for i in range(25):
        model = regulator.get_available_model()

        if model:
            print(f"\nRequisição {i + 1}: Usando modelo {model}")
            regulator.register_usage(model)

            # Mostra estatísticas
            stats = regulator.get_usage_stats()
            for model_name, data in stats.items():
                print(
                    f"  {model_name}: {data['daily_usage']}/{data['daily_limit']} (dia), "
                    f"{data['minute_usage']}/{data['minute_limit']} (min) - "
                    f"{'✓ disponível' if data['available'] else '✗ indisponível'}"
                )
        else:
            print(f"\nRequisição {i + 1}: ❌ Nenhum modelo disponível no momento")
            break
