#!/usr/bin/env python3
"""
Конфигурация STRK Whale Monitor
"""

import os

# ==================== Starknet RPC ====================
# Бесплатные публичные RPC-эндпоинты Starknet
STARKNET_RPC_URL = os.getenv(
    "STARKNET_RPC_URL",
    "https://starknet.api.onfinality.io/public"  # Бесплатный публичный эндпоинт
)

# Альтернативные бесплатные эндпоинты (раскомментируйте нужный):
# STARKNET_RPC_URL = "https://public.1rpc.io/starknet"
# STARKNET_RPC_URL = "https://starknet-rpc.publicnode.com"
# STARKNET_RPC_URL = "https://starknet.drpc.org"
# STARKNET_RPC_URL = "https://free-rpc.nethermind.io/mainnet-juno/"

# ==================== Токен STRK ====================
# Адрес контракта токена STRK в сети Starknet
STRK_TOKEN_ADDRESS = "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d"

# Selector для события Transfer (keccak256("Transfer"))
TRANSFER_SELECTOR = "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"

# ==================== Фильтр ====================
# Минимальная сумма для оповещения (в STRK, не wei)
MIN_AMOUNT_STRK = 100_000  # Например, 100,000 STRK

# ==================== Email (SMTP) ====================
EMAIL_CONFIG = {
    # Для Gmail используйте пароль приложения, не основной пароль!
    # Настройка: https://myaccount.google.com/apppasswords
    "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "sender": os.getenv("SMTP_SENDER", "youtumbashow@gmail.com"),
    "password": os.getenv("SMTP_PASSWORD", "uyar uhbl hlki ghmk"),
    "recipient": os.getenv("ALERT_EMAIL", "leoleokor@gmail.com"),
}

# ==================== Состояние ====================
STATE_FILE = "last_block.json"
