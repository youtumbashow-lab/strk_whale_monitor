#!/usr/bin/env python3
"""
STRK Whale — дневная сводка.
Читает data/transfers.jsonl, агрегирует за прошлые сутки, отправляет письмо
с разбивкой по порогам, очищает файл.
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

# Пороги для разбивки: (нижняя граница, подпись)
THRESHOLDS = [
    (1_000_000, "> 1,000,000 STRK"),
    (500_000,   "> 500,000 STRK"),
    (100_000,   "> 100,000 STRK"),
]


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


def load_and_clear():
    """
    Читает все записи из файла, возвращает их список и очищает файл.
    Возвращаем ВСЁ, что накопилось — раз в сутки это и есть «за прошлый день».
    """
    if not DATA_FILE.exists():
        return []

    records = []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Очищаем файл (создаём, если его нет)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text('', encoding='utf-8')


def build_summary_body(records):
    msk_tz = timezone(timedelta(hours=3))
    now_msk = datetime.now(msk_tz)

    total = len(records)
    total_strk = sum(r['amount_strk'] for r in records)

    # Разбивка по порогам (каждый перевод попадает только в свой высший порог)
    buckets = Counter()
    for r in records:
        amount = r['amount_strk']
        for threshold, _ in THRESHOLDS:
            if amount >= threshold:
                buckets[threshold] += 1
                break
        else:
            # меньше минимального порога — не считаем (не должно быть)
            pass

    lines = [
        f"STRK Whale — дневная сводка",
        f"Отчёт за: {now_msk.strftime('%Y-%m-%d %H:%M')} МСК",
        f"",
        f"Всего крупных переводов: {total}",
        f"Общая сумма: {total_strk:,.2f} STRK",
        f"",
        "-" * 50,
        "Разбивка по порогам:",
    ]

    for threshold, label in THRESHOLDS:
        count = buckets.get(threshold, 0)
        lines.append(f"  {label}: {count} перевод(ов)")

    lines.append("-" * 50)
    return "\n".join(lines)


def main():
    logger.info("Запуск дневной сводки STRK Whale...")

    records = load_and_clear()
    logger.info(f"Загружено записей: {len(records)}")

    if not records:
        logger.info("Записей нет — письмо не отправляем")
        return

    body = build_summary_body(records)
    subject = f"[STRK Whale] Дневная сводка"
    send_email(subject, body)


if __name__ == "__main__":
    main()
