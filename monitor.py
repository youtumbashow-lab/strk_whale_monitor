#!/usr/bin/env python3
"""
STRK Whale Sale Monitor
Мониторинг крупных переводов STRK. Пишет найденные события в data/transfers.jsonl
для последующей агрегации дневным скриптом daily_summary.py.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import (
    STARKNET_RPC_URL,
    STRK_TOKEN_ADDRESS,
    MIN_AMOUNT_STRK,
    TRANSFER_SELECTOR,
    LOOKBACK_BLOCKS,
    MAX_EVENTS_PER_RUN,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEBUG = False

DATA_FILE = Path("data/transfers.jsonl")


def get_latest_block():
    payload = {
        "jsonrpc": "2.0",
        "method": "starknet_blockNumber",
        "params": [],
        "id": 1
    }
    r = requests.post(
        STARKNET_RPC_URL, json=payload,
        headers={"Content-Type": "application/json"}, timeout=30
    )
    r.raise_for_status()
    return r.json()['result']


def get_transfer_events(from_block, to_block):
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
        r = requests.post(
            STARKNET_RPC_URL, json=payload,
            headers={"Content-Type": "application/json"}, timeout=60
        )
        r.raise_for_status()

        result = r.json().get('result', {})
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
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith('0x') else int(value)
    raise TypeError(f"Не могу преобразовать в int: {value!r}")


def parse_transfer_event(event):
    try:
        keys = event.get('keys', [])
        data = event.get('data', [])

        if len(keys) >= 3 and len(data) >= 2:
            amount_low = _to_int(data[0])
            amount_high = _to_int(data[1])
        elif len(data) >= 4:
            amount_low = _to_int(data[2])
            amount_high = _to_int(data[3])
        else:
            return None

        amount = amount_low + (amount_high << 128)

        return {
            'amount_strk': amount / 10**18,
            'block': event.get('block_number'),
            'tx_hash': event.get('transaction_hash')
        }
    except (IndexError, ValueError, TypeError):
        return None


def append_to_data_file(transfers):
    """Дописывает найденные крупные переводы в JSONL-файл."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not transfers:
        # Гарантируем, что файл существует даже если нечего писать
        if not DATA_FILE.exists():
            DATA_FILE.touch()
        return 0

    existing_hashes = set()
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing_hashes.add(json.loads(line)['tx_hash'])
                except (json.JSONDecodeError, KeyError):
                    continue

    added = 0
    with open(DATA_FILE, 'a', encoding='utf-8') as f:
        for t in transfers:
            if t['tx_hash'] in existing_hashes:
                continue
            record = {
                'tx_hash': t['tx_hash'],
                'amount_strk': t['amount_strk'],
                'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                'block': t['block'],
            }
            f.write(json.dumps(record) + '\n')
            existing_hashes.add(t['tx_hash'])
            added += 1

    return added


def main():
    logger.info("Запуск STRK Whale Monitor...")

    try:
        latest_block = get_latest_block()
    except Exception as e:
        logger.error(f"Не удалось получить номер блока: {e}")
        return

    from_block = max(0, latest_block - LOOKBACK_BLOCKS)
    logger.info(f"Блоки {from_block} — {latest_block}")

    try:
        events = get_transfer_events(from_block, latest_block)
    except Exception as e:
        logger.error(f"Ошибка получения событий: {e}")
        return

    logger.info(f"Получено событий: {len(events)}")

    big_transfers = []
    seen = set()
    for event in events:
        h = event.get('transaction_hash')
        if h in seen:
            continue
        seen.add(h)
        t = parse_transfer_event(event)
        if t and t['amount_strk'] >= MIN_AMOUNT_STRK:
            big_transfers.append(t)

    logger.info(f"Крупных переводов (≥{MIN_AMOUNT_STRK} STRK): {len(big_transfers)}")

    added = append_to_data_file(big_transfers)
    logger.info(f"Записано новых записей в data/transfers.jsonl: {added}")


if __name__ == "__main__":
    main()
