#!/usr/bin/env python3
"""
STRK Whale Sale Monitor
Мониторинг крупных переводов STRK с отправкой email-уведомлений.
Адаптирован для запуска через GitHub Actions.

Отправляет ОДНО сводное письмо со списком всех крупных переводов за запуск.
"""

import json
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

DEBUG = False  # включите True для отладки структуры событий


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
    """Получение событий Transfer токена STRK с пагинацией."""
    all_events = []
    continuation_token = None
    pages = 0
    max_pages = 30

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

        if len(all_events) >= MAX_EVENTS_PER_RUN:
            logger.warning(f"Достигнут лимит событий: {MAX_EVENTS_PER_RUN}")
            break

    return all_events


def _to_int(value):
    """Универсальное преобразование hex/int/str в int."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith('0x') else int(value)
    raise TypeError(f"Не могу преобразовать в int: {value!r}")


def parse_transfer_event(event):
    """
    Парсинг события Transfer.
    Формат Starknet ERC-20:
      keys = [selector, from, to]
      data = [amount_low, amount_high]
    """
    try:
        keys = event.get('keys', [])
        data = event.get('data', [])

        if len(keys) >= 3 and len(data) >= 2:
            from_addr = hex(_to_int(keys[1]))
            to_addr = hex(_to_int(keys[2]))
            amount_low = _to_int(data[0])
            amount_high = _to_int(data[1])
        elif len(data) >= 4:
            from_addr = hex(_to_int(data[0]))
            to_addr = hex(_to_int(data[1]))
            amount_low = _to_int(data[2])
            amount_high = _to_int(data[3])
        else:
            if DEBUG:
                logger.warning(f"Неизвестный формат: keys={keys}, data={data}")
            return None

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
        if DEBUG:
            logger.warning(f"Ошибка парсинга: {e}. event={event}")
        return None


def send_email(subject, body):
    """
    Отправка email. Поддерживает порт 465 (SSL) и 587 (STARTTLS).
    """
    msg = MIMEMultipart()
    msg['From'] = EMAIL_CONFIG['sender']
    msg['To'] = EMAIL_CONFIG['recipient']
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    host = EMAIL_CONFIG['smtp_host']
    port = EMAIL_CONFIG['smtp_port']
    user = EMAIL_CONFIG['sender']
    pwd = EMAIL_CONFIG['password']

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(user, pwd)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, pwd)
                server.send_message(msg)
        logger.info(f"Email отправлен: {subject}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        return False


def format_summary_email(transfers):
    """Формирование текста сводного письма (без from/to/block)."""
    total_strk = sum(t['amount_strk'] for t in transfers)
    header = (
        f"STRK Whale Monitor — обнаружено {len(transfers)} крупных переводов\n"
        f"Суммарно: {total_strk:,.2f} STRK\n"
        f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"{'-' * 60}\n\n"
    )

    # Сортируем по убыванию суммы
    transfers_sorted = sorted(
        transfers, key=lambda t: t['amount_strk'], reverse=True
    )

    lines = []
    for i, t in enumerate(transfers_sorted, 1):
        lines.append(
            f"{i}. {t['amount_strk']:,.2f} STRK\n"
            f"   https://starkscan.co/tx/{t['tx_hash']}\n"
        )
    return header + "\n".join(lines)


def main():
    logger.info("Запуск STRK Whale Monitor (GitHub Actions mode)...")

    try:
        latest_block = get_latest_block()
    except Exception as e:
        logger.error(f"Не удалось получить номер блока: {e}")
        return

    from_block = max(0, latest_block - LOOKBACK_BLOCKS)
    logger.info(f"Последний блок в сети: {latest_block}")
    logger.info(f"Сканирование блоков {from_block} - {latest_block}")

    try:
        events = get_transfer_events(from_block, latest_block)
    except Exception as e:
        logger.error(f"Ошибка получения событий: {e}")
        return

    logger.info(f"Получено событий: {len(events)}")

    if DEBUG and events:
        logger.info(f"RAW [0]: {json.dumps(events[0])}")

    big_transfers = []
    seen_hashes = set()
    parsed_ok = 0
    parsed_fail = 0

    for event in events:
        tx_hash = event.get('transaction_hash')
        if tx_hash in seen_hashes:
            continue
        seen_hashes.add(tx_hash)

        transfer = parse_transfer_event(event)
        if not transfer:
            parsed_fail += 1
            continue

        parsed_ok += 1

        if transfer['amount_strk'] >= MIN_AMOUNT_STRK:
            big_transfers.append(transfer)

    logger.info(
        f"Распарсено: {parsed_ok}, ошибок: {parsed_fail}, "
        f"крупных переводов (≥{MIN_AMOUNT_STRK} STRK): {len(big_transfers)}"
    )

    if not big_transfers:
        logger.info("Крупных переводов нет — email не отправляем")
        return

    subject = f"[STRK Whale] {len(big_transfers)} крупных переводов"
    body = format_summary_email(big_transfers)
    send_email(subject, body)


if __name__ == "__main__":
    main()
