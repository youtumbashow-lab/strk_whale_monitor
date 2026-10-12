#!/usr/bin/env python3
"""
Конфигурация STRK Whale Monitor.
Все секреты берутся из переменных окружения (GitHub Secrets).
"""

import os

# ==================== Starknet RPC ====================
STARKNET_RPC_URL = os.getenv(
    "STARKNET_RPC_URL",
    "https://starknet.api.onfinality.io/public"
)

# ==================== Токен STRK ====================
STRK_TOKEN_ADDRESS = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"

# Selector для события Transfer (keccak256("Transfer"))
TRANSFER_SELECTOR = "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"

# ==================== Фильтр ====================
# Минимальная сумма для оповещения (в STRK, не wei)
MIN_AMOUNT_STRK = 500_000

# Сколько последних блоков сканировать за один запуск
LOOKBACK_BLOCKS = 300

# Максимум событий за один запуск
MAX_EVENTS_PER_RUN = 5000

# ==================== Email (SMTP) ====================
EMAIL_CONFIG = {
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    # 465 = SSL, 587 = STARTTLS. Для GitHub Actions 465 работает стабильнее.
    "smtp_port": int(os.getenv("SMTP_PORT", "465")),
    "sender": os.getenv("SMTP_SENDER"),
    "password": os.getenv("SMTP_PASSWORD"),
    "recipient": os.getenv("ALERT_EMAIL"),
}

# Проверка обязательных переменных
_missing = [
    k for k, v in EMAIL_CONFIG.items()
    if k in ("sender", "password", "recipient") and not v
]
if _missing:
    raise RuntimeError(
        f"Не заданы переменные окружения для email: {_missing}. "
        f"Проверьте secrets в GitHub Actions или переменные окружения локально."
    )
