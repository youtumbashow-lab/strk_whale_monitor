#!/usr/bin/env python3
"""
STRK Whale Sale Monitor
Мониторинг крупных переводов STRK с отправкой email-уведомлений
"""

import json
import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

import requests

from config import (
    STARKNET_RPC_URL,
    STRK_TOKEN_ADDRESS,
    MIN_AMOUNT_STRK,
    EMAIL_CONFIG,
    STATE_FILE,
    TRANSFER_SELECTOR
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_last_block():
    """Загрузка последнего обработанного блока"""
    if Path(STATE_FILE).exists():
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_block', 0)
    return 0


def save_last_block(block_number):
    """Сохранение последнего обработанного блока"""
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_block': block_number}, f)


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
    Получение событий Transfer для токена STRK
    """
    all_events = []
    continuation_token = None

    while True:
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
        if not continuation_token:
            break

    return all_events


def parse_transfer_event(event):
    """
    Парсинг события Transfer
    Возвращает: from_address, to_address, amount
    """
    try:
        data = event.get('data', [])

        if len(data) < 4:
            return None

        # В Starknet ERC20 Transfer: from, to, amount_low, amount_high
        from_addr = hex(int(data[0], 16)) if isinstance(data[0], str) else hex(data[0])
        to_addr = hex(int(data[1], 16)) if isinstance(data[1], str) else hex(data[1])

        # amount - это u256, хранится как low + high * 2^128
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

Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""".strip()


def main():
    logger.info("Запуск STRK Whale Monitor...")

    last_block = load_last_block()
    latest_block = get_latest_block()

    logger.info(f"Последний обработанный блок: {last_block}")
    logger.info(f"Последний блок в сети: {latest_block}")

    if last_block == 0:
        # Первый запуск - начинаем с текущего блока
        logger.info("Первый запуск, инициализация...")
        save_last_block(latest_block)
        return

    if last_block >= latest_block:
        logger.info("Нет новых блоков для обработки")
        return

    # Ограничиваем глубину сканирования (например, 1000 блоков за раз)
    max_block_range = 1000
    from_block = last_block
    to_block = min(latest_block, last_block + max_block_range)

    logger.info(f"Сканирование блоков {from_block} - {to_block}")

    try:
        events = get_transfer_events(from_block, to_block)
        logger.info(f"Получено событий: {len(events)}")

        alerts_sent = 0

        for event in events:
            transfer = parse_transfer_event(event)
            if not transfer:
                continue

            # Фильтрация по минимальной сумме
            if transfer['amount_strk'] >= MIN_AMOUNT_STRK:
                logger.info(
                    f"Крупный перевод: {transfer['amount_strk']:,.2f} STRK "
                    f"от {transfer['from']}"
                )

                subject = f"[STRK Whale] {transfer['amount_strk']:,.0f} STRK"
                body = format_alert_message(transfer)
                send_email(subject, body)
                alerts_sent += 1

        save_last_block(to_block)
        logger.info(f"Готово. Отправлено уведомлений: {alerts_sent}")

    except Exception as e:
        logger.error(f"Ошибка выполнения: {e}")
        raise


if __name__ == "__main__":
    main()
