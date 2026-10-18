#!/usr/bin/env python3
"""
STRK Whale — дневная сводка с историей.
Читает data/transfers.jsonl за прошедшие сутки, агрегирует по порогам,
дописывает новую строку в data/history.json (в начало), отправляет
письмо с таблицей: первая строка — вчера, ниже — предыдущие дни.
"""

import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

from config import EMAIL_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_FILE = Path("data/transfers.jsonl")
HISTORY_FILE = Path("data/history.json")

# Пороги для разбивки: (нижняя граница, подпись для таблицы)
THRESHOLDS = [
    (1_000_000, "> 1M"),
    (500_000,   "> 500K"),
    (100_000,   "> 100K"),
]

# Сколько дней истории хранить и показывать в таблице
HISTORY_DAYS = 30


def send_email(subject, body):
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


def load_and_clear_transfers():
    """Читает все записи из transfers.jsonl и очищает файл."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    records = []
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    DATA_FILE.write_text('', encoding='utf-8')
    return records


def load_history():
    """Загружает историю из history.json. Возвращает список записей (новые первыми)."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        logger.warning("history.json повреждён — начинаем с пустой истории")
        return []


def save_history(history):
    """Сохраняет историю в history.json."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def aggregate(records):
    """Считает количество переводов по порогам и общую сумму."""
    total = len(records)
    total_strk = sum(r['amount_strk'] for r in records)

    # Каждый перевод попадает только в свой высший порог
    buckets = Counter()
    for r in records:
        amount = r['amount_strk']
        for threshold, _ in THRESHOLDS:
            if amount >= threshold:
                buckets[threshold] += 1
                break

    return {
        'total': total,
        'total_strk': total_strk,
        'buckets': {threshold: buckets.get(threshold, 0) for threshold, _ in THRESHOLDS},
    }


def format_table(history):
    """
    Формирует текстовую таблицу.
    Первая строка данных — последний день (вчера).
    """
    # Заголовок
    header_labels = ["Дата"] + [label for _, label in THRESHOLDS] + ["Всего", "Сумма STRK"]
    # Ширины колонок
    widths = [12] + [10] * len(THRESHOLDS) + [8, 18]

    def fmt_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            parts.append(str(cell).ljust(widths[i]))
        return " | ".join(parts)

    lines = []
    lines.append(fmt_row(header_labels))
    lines.append("-+-".join("-" * w for w in widths))

    for entry in history:
        row = [entry['date']]
        for threshold, _ in THRESHOLDS:
            row.append(str(entry['buckets'].get(str(threshold), entry['buckets'].get(threshold, 0))))
        row.append(str(entry['total']))
        row.append(f"{entry['total_strk']:,.0f}")
        lines.append(fmt_row(row))

    return "\n".join(lines)


def build_summary_body(new_entry, history):
    msk_tz = timezone(timedelta(hours=3))
    now_msk = datetime.now(msk_tz)

    yest = new_entry['date']
    yest_total = new_entry['total']
    yest_strk = new_entry['total_strk']

    header = (
        f"STRK Whale — дневная сводка\n"
        f"Отчёт за: {now_msk.strftime('%Y-%m-%d %H:%M')} МСК\n"
        f"\n"
        f"Вчера ({yest}): {yest_total} переводов на {yest_strk:,.2f} STRK\n"
        f"\n"
        f"{'-' * 90}\n"
        f"История (новые сверху):\n"
        f"{'-' * 90}\n"
    )

    return header + format_table(history)


def main():
    logger.info("Запуск дневной сводки STRK Whale...")

    # 1. Забираем накопленные переводы и очищаем файл
    records = load_and_clear_transfers()
    logger.info(f"Загружено записей за период: {len(records)}")

    # 2. Агрегируем
    agg = aggregate(records)

    # 3. Загружаем историю
    history = load_history()
    logger.info(f"В истории уже {len(history)} дней")

    # 4. Формируем новую запись с датой «вчера» в МСК
    msk_tz = timezone(timedelta(hours=3))
    yesterday_msk = (datetime.now(msk_tz) - timedelta(days=1)).strftime('%Y-%m-%d')

    new_entry = {
        'date': yesterday_msk,
        'total': agg['total'],
        'total_strk': agg['total_strk'],
        'buckets': {str(k): v for k, v in agg['buckets'].items()},
    }

    # 5. Добавляем в начало истории, обрезаем до HISTORY_DAYS
    history.insert(0, new_entry)
    history = history[:HISTORY_DAYS]

    # 6. Сохраняем историю
    save_history(history)
    logger.info(f"История обновлена: {len(history)} дней")

    # 7. Отправляем письмо
    body = build_summary_body(new_entry, history)
    subject = f"[STRK Whale] Сводка за {yesterday_msk}"
    send_email(subject, body)


if __name__ == "__main__":
    main()
