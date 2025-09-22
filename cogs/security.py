import asyncio
import datetime
import logging
import statistics
from collections import deque

from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

class Security(commands.Cog):
    # anti-flood e fallback
    # movidas para dentro da classe para serem acessadas corretamente
    FALLBACK_MODEL = "gemini-2.5-flash-lite" # trocado para um modelo mais recente que o flash-lite
    BUCKET_CAPACITY = 6.0
    LEAK_RATE_PER_SEC = 0.7
    COST_PER_TEXT = 1.5
    COST_PER_ATTACHMENT = 4.0

    def __init__(self, bot):
        self.bot = bot
        self.user_buckets = {}
        self.user_locks = {}
        self.main_lock = asyncio.Lock()
        self.is_high_traffic_mode = False
        self.hourly_usage_history = deque(maxlen=24)
        self.check_traffic.start()

    def cog_unload(self):
        self.check_traffic.cancel()

    @tasks.loop(minutes=15)
    async def check_traffic(self):
        # verifica o trafego de tokens p ativar/desativar o modo de economia
        try:
            records = self.bot.monitor.tokens_monitor.get_usage_order_uso()
            current_hour_usage = sum(r.uso for r in records) if records else 0
            self.hourly_usage_history.append(current_hour_usage)
            if len(self.hourly_usage_history) < 4:
                return # aguarda ter pelo menos uma hora de dados (4 * 15 min)
            
            usage_list = list(self.hourly_usage_history)
            mean_usage = statistics.mean(usage_list)
            stdev_usage = statistics.stdev(usage_list) if len(usage_list) > 1 else 0
            
            # define os limiares com base na media e desvio padrao
            high_traffic_threshold = mean_usage + (1.5 * stdev_usage)
            normal_traffic_threshold = mean_usage + (0.5 * stdev_usage)
            
            if current_hour_usage > high_traffic_threshold and not self.is_high_traffic_mode:
                self.is_high_traffic_mode = True
                logger.warning(
                    f"Limiar de trafego alto atingido. Modo de economia ativado (usando {self.FALLBACK_MODEL})"
                )
            elif current_hour_usage < normal_traffic_threshold and self.is_high_traffic_mode:
                self.is_high_traffic_mode = False
                logger.info("Trafego normalizado. Modo de economia desativado")
        except Exception as e:
            logger.error(f"Erro ao verificar o trafego de tokens: {e}")

    async def is_rate_limited(self, user_id: int, cost: float) -> bool:
        # implementacao do leaky bucket para limitar a taxa de requisicoes por usuario
        user_id_str = str(user_id)
        
        # garante que a criacao de locks seja thread-safe
        async with self.main_lock:
            if user_id_str not in self.user_locks:
                self.user_locks[user_id_str] = asyncio.Lock()
                
        user_lock = self.user_locks[user_id_str]
        async with user_lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            if user_id_str not in self.user_buckets:
                self.user_buckets[user_id_str] = {"level": 0.0, "last_update": now}
            
            bucket = self.user_buckets[user_id_str]
            
            # calcula o "vazamento" do balde desde a ultima atualizacao
            time_passed = (now - bucket["last_update"]).total_seconds()
            leaked_amount = time_passed * self.LEAK_RATE_PER_SEC
            bucket["level"] = max(0.0, bucket["level"] - leaked_amount)
            bucket["last_update"] = now
            
            # verifica se o custo da nova acao excede a capacidade
            if bucket["level"] + cost > self.BUCKET_CAPACITY:
                return True # usuario esta limitado
            
            bucket["level"] += cost
            return False # usuario nao esta limitado


async def setup(bot):
    await bot.add_cog(Security(bot))
