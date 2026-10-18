#!/usr/bin/env python3
"""
STRK Whale — дневная сводка с историей.
Группирует переводы из data/transfers.jsonl по датам (МСК),
дописывает/обновляет записи в data/history.json,
отправляет письмо с таблицей: новые даты сверху.
"""

import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter, defaultdict

from config import EMAIL_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_FILE = Path("data/transfers.jsonl")
HISTORY_FILE = Path("data/history.json")

THRESHOLDS = [
    (1_000_000, "> 1M"),
    (500_000,   "> 500K"),
    (100_000,   "> 100K"),
]

HISTORY_DAYS = 30
MSK = timezone(timedelta(hours=3))


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
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def record_date_msk(record):
    ts = record.get('timestamp_utc')
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.astimezone(MSK).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def aggregate_by_date(records):
    by_date = defaultdict(list)
    for r in records:
        d = record_date_msk(r)
        if d:
            by_date[d].append(r)

    result = {}
    for date, recs in by_date.items():
        total = len(recs)
        total_strk = sum(r['amount_strk'] for r in recs)

        buckets = Counter()
        for r in recs:
            amount = r['amount_strk']
            for threshold, _ in THRESHOLDS:
                if amount >= threshold:
                    buckets[threshold] += 1
                    break

        result[date] = {
            'date': date,
            'total': total,
            'total_strk': total_strk,
            'buckets': {str(t): buckets.get(t, 0) for t, _ in THRESHOLDS},
        }
    return result


def merge_into_history(history, new_days):
    existing = {entry['date']: entry for entry in history}

    for date, new_entry in new_days.items():
        if date in existing:
            old = existing[date]
            old['total'] += new_entry['total']
            old['total_strk'] += new_entry['total_strk']
            for k, v in new_entry['buckets'].items():
                old['buckets'][k] = old['buckets'].get(k, 0) + v
        else:
            existing[date] = new_entry

    merged = sorted(existing.values(), key=lambda e: e['date'], reverse=True)
    return merged[:HISTORY_DAYS]


def format_table(history):
    header_labels = ["Дата"] + [label for _, label in THRESHOLDS] + ["Всего", "Сумма STRK"]
    widths = [12] + [10] * len(THRESHOLDS) + [8, 18]

    def fmt_row(cells):
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells))

    lines = [fmt_row(header_labels)]
    lines.append("-+-".join("-" * w for w in widths))

    for entry in history:
        row = [entry['date']]
        for threshold, _ in THRESHOLDS:
            row.append(str(entry['buckets'].get(str(threshold), 0)))
        row.append(str(entry['total']))
        row.append(f"{entry['total_strk']:,.0f}")
        lines.append(fmt_row(row))

    return "\n".join(lines)


def build_summary_body(history, dates_added):
    now_msk = datetime.now(MSK)
    header = (
        f"STRK Whale — дневная сводка\n"
        f"Отчёт за: {now_msk.strftime('%Y-%m-%d %H:%M')} МСК\n"
        f"Обновлены даты: {', '.join(dates_added) if dates_added else '—'}\n"
        f"\n"
        f"{'-' * 90}\n"
        f"История (новые сверху):\n"
        f"{'-' * 90}\n"
    )
    return header + format_table(history)


def main():
    logger.info("Запуск дневной сводки STRK Whale...")

    missing = [
        k for k in ("sender", "password", "recipient")
        if not EMAIL_CONFIG.get(k)
    ]
    if missing:
        logger.error(
            f"Не заданы переменные окружения для email: {missing}. "
            f"Проверьте secrets в GitHub Actions."
        )
        return

    records = load_and_clear_transfers()
    logger.info(f"Загружено записей: {len(records)}")

    if not records:
        logger.info("Записей нет — сводка не отправляется")
        return

    new_days = aggregate_by_date(records)
    logger.info(f"Дат в новых данных: {len(new_days)} → {sorted(new_days.keys(), reverse=True)}")

    history = load_history()
    logger.info(f"В истории было {len(history)} дней")

    history = merge_into_history(history, new_days)
    logger.info(f"В истории стало {len(history)} дней")

    save_history(history)

    body = build_summary_body(history, sorted(new_days.keys(), reverse=True))
    subject = f"[STRK Whale] Сводка за {', '.join(sorted(new_days.keys(), reverse=True))}"
    send_email(subject, body)


if __name__ == "__main__":
    main()
