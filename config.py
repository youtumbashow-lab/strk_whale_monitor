#!/usr/bin/env python3
"""
Конфигурация STRK Whale Monitor.
Все секреты берутся из переменных окружения (GitHub Secrets).
"""

import os

# ==================== Starknet RPC ====================
# Приватный эндпоинт Alchemy (или другого провайдера) задаётся через секрет.
# Если переменная не задана — используется бесплатный публичный эндпоинт.
STARKNET_RPC_URL = os.getenv(
    "STARKNET_RPC_URL",
    "https://starknet.api.onfinality.io/public"
)

# Альтернативные бесплатные эндпоинты (раскомментируйте нужный):
# STARKNET_RPC_URL = "https://public.1rpc.io/starknet"
# STARKNET_RPC_URL = "https://starknet-rpc.publicnode.com"
# STARKNET_RPC_URL = "https://starknet.drpc.org"
# STARKNET_RPC_URL = "https://rpc.starknet.lava.build"

# ==================== Токен STRK ====================
# Адрес контракта токена STRK в сети Starknet Mainnet
STRK_TOKEN_ADDRESS = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"

# Selector для события Transfer (keccak256("Transfer"))
TRANSFER_SELECTOR = "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"

# ==================== Фильтр ====================
# Минимальная сумма для оповещения (в STRK, не wei)
MIN_AMOUNT_STRK = 100_000

# Сколько последних блоков сканировать за один запуск.
# 5 минут ≈ 20-50 блоков Starknet, поэтому 100 — с запасом.
LOOKBACK_BLOCKS = 100

# Максимум событий за один запуск (защита от перегрузки).
# В сети много мелких переводов STRK, поэтому лимит высокий.
MAX_EVENTS_PER_RUN = 3000

# ==================== Email (SMTP) ====================
# ВСЕ значения берутся из переменных окружения!
# В GitHub Actions они передаются через secrets.
EMAIL_CONFIG = {
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "sender": os.getenv("SMTP_SENDER"),        # обязательная переменная
    "password": os.getenv("SMTP_PASSWORD"),    # обязательная переменная
    "recipient": os.getenv("ALERT_EMAIL"),     # обязательная переменная
}

# Проверка, что все обязательные переменные заданы
_missing = [
    k for k, v in EMAIL_CONFIG.items()
    if k in ("sender", "password", "recipient") and not v
]
if _missing:
    raise RuntimeError(
        f"Не заданы переменные окружения для email: {_missing}. "
        f"Проверьте secrets в GitHub Actions или переменные окружения локально."
    )
