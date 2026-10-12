#!/usr/bin/env python3
"""
STRK Whale — дневная сводка.
Читает data/transfers.jsonl, агрегирует по порогам, отправляет письмо,
очищает файл (создаёт заново, если удалён).
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
    (1_000_000, "> 1 000 000 STRK"),
    (500_000,   "> 500 000 STRK"),
    (100_000,   "> 100 000 STRK"),
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
    Файл гарантированно создаётся заново даже если его не было.
    """
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

    # Очищаем / создаём заново
    DATA_FILE.write_text('', encoding='utf-8')
    return records


def build_summary_body(records):
    msk_tz = timezone(timedelta(hours=3))
    now_msk = datetime.now(msk_tz)

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

    lines = [
        "STRK Whale — дневная сводка",
        f"Отчёт за: {now_msk.strftime('%Y-%m-%d %H:%M')} МСК",
        "",
        f"Всего крупных переводов: {total}",
        f"Общая сумма: {total_strk:,.2f} STRK",
        "",
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
    subject = "[STRK Whale] Дневная сводка"
    send_email(subject, body)


if __name__ == "__main__":
    main()
