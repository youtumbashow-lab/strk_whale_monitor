#!/usr/bin/env python3
"""
STRK Whale Sale Monitor
Мониторинг крупных переводов STRK с отправкой email-уведомлений.
Адаптирован для запуска через GitHub Actions.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import requests

from config import (
    STARKNET_RPC_URL,
    STRK_TOKEN_ADDRESS,
    MIN_AMOUNT_STRK,
    EMAIL_CONFIG,
    TRANSFER_SELECTOR,
    LOOKBACK_BLOCKS,
    MAX_EVENTS_PER_RUN,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_latest_block():
    """Получение номера последнего блока в сети Starknet"""
    payload = {
        "jsonrpc": "2.0",
        "method": "starknet_blockNumber",
        "params": [],
        "id": 1
    }

    response = requests.post(
        STARKNET_RPC_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    response.raise_for_status()
    return response.json()['result']


def get_transfer_events(from_block, to_block):
    """
    Получение событий Transfer для токена STRK с пагинацией.
    """
    all_events = []
    continuation_token = None
    pages = 0
    max_pages = 20  # защита от бесконечного цикла

    while pages < max_pages:
        filter_params = {
            "from_block": {"block_number": from_block},
            "to_block": {"block_number": to_block},
            "address": STRK_TOKEN_ADDRESS,
            "keys": [[TRANSFER_SELECTOR]],
            "chunk_size": 100
        }

        if continuation_token:
            filter_params["continuation_token"] = continuation_token

        payload = {
            "jsonrpc": "2.0",
            "method": "starknet_getEvents",
            "params": {"filter": filter_params},
            "id": 1
        }

        response = requests.post(
            STARKNET_RPC_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        response.raise_for_status()

        result = response.json().get('result', {})
        events = result.get('events', [])
        all_events.extend(events)

        continuation_token = result.get('continuation_token')
        pages += 1

        if not continuation_token:
            break

        # Ограничение на количество событий для защиты от переполнения
        if len(all_events) >= MAX_EVENTS_PER_RUN:
            logger.warning(f"Достигнут лимит событий: {MAX_EVENTS_PER_RUN}")
            break

    return all_events


def parse_transfer_event(event):
    """
    Парсинг события Transfer.
    Возвращает: from_address, to_address, amount_strk, block, tx_hash
    """
    try:
        data = event.get('data', [])

        if len(data) < 4:
            return None

        # В Starknet ERC20 Transfer: from, to, amount_low, amount_high
        from_addr = hex(int(data[0], 16)) if isinstance(data[0], str) else hex(data[0])
        to_addr = hex(int(data[1], 16)) if isinstance(data[1], str) else hex(data[1])

        # amount — это u256: low + (high << 128)
        amount_low = int(data[2], 16) if isinstance(data[2], str) else data[2]
        amount_high = int(data[3], 16) if isinstance(data[3], str) else data[3]
        amount = amount_low + (amount_high << 128)

        return {
            'from': from_addr,
            'to': to_addr,
            'amount_wei': amount,
            'amount_strk': amount / 10**18,
            'block': event.get('block_number'),
            'tx_hash': event.get('transaction_hash')
        }
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Ошибка парсинга события: {e}")
        return None


def send_email(subject, body):
    """Отправка email-уведомления"""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_CONFIG['sender']
    msg['To'] = EMAIL_CONFIG['recipient']
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_host'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['password'])
            server.send_message(msg)
        logger.info(f"Email отправлен: {subject}")
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")


def format_alert_message(transfer):
    """Форматирование текста уведомления"""
    return f"""
Обнаружен крупный перевод STRK!

Сумма: {transfer['amount_strk']:,.2f} STRK
От: {transfer['from']}
Кому: {transfer['to']}

Блок: {transfer['block']}
Транзакция: https://starkscan.co/tx/{transfer['tx_hash']}

Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
""".strip()


def main():
    logger.info("Запуск STRK Whale Monitor (GitHub Actions mode)...")

    try:
        latest_block = get_latest_block()
    except Exception as e:
        logger.error(f"Не удалось получить номер блока: {e}")
        return

    # Сканируем последние LOOKBACK_BLOCKS блоков при каждом запуске.
    # Это компенсирует задержки GitHub Actions и отсутствие персистентного состояния.
    from_block = max(0, latest_block - LOOKBACK_BLOCKS)

    logger.info(f"Последний блок в сети: {latest_block}")
    logger.info(f"Сканирование блоков {from_block} - {latest_block}")

    try:
        events = get_transfer_events(from_block, latest_block)
    except Exception as e:
        logger.error(f"Ошибка получения событий: {e}")
        return

    logger.info(f"Получено событий: {len(events)}")

    alerts_sent = 0
    seen_hashes = set()  # дедупликация внутри одного запуска

    for event in events:
        tx_hash = event.get('transaction_hash')

        if tx_hash in seen_hashes:
            continue
        seen_hashes.add(tx_hash)

        transfer = parse_transfer_event(event)
        if not transfer:
            continue

        if transfer['amount_strk'] >= MIN_AMOUNT_STRK:
            logger.info(
                f"Крупный перевод: {transfer['amount_strk']:,.2f} STRK "
                f"от {transfer['from']}"
            )

            subject = f"[STRK Whale] {transfer['amount_strk']:,.0f} STRK"
            body = format_alert_message(transfer)
            send_email(subject, body)
            alerts_sent += 1

    logger.info(f"Готово. Отправлено уведомлений: {alerts_sent}")


if __name__ == "__main__":
    main()
