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
MIN_AMOUNT_STRK = 100_000
LOOKBACK_BLOCKS = 600
MAX_EVENTS_PER_RUN = 5000

# ==================== Email (SMTP) ====================
# Используется ТОЛЬКО daily_summary.py. monitor.py эти переменные не читает.
# Проверка обязательных полей — внутри daily_summary.py, не здесь.
EMAIL_CONFIG = {
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "465")),
    "sender": os.getenv("SMTP_SENDER"),
    "password": os.getenv("SMTP_PASSWORD"),
    "recipient": os.getenv("ALERT_EMAIL"),
}
