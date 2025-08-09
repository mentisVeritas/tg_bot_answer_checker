from zoneinfo import ZoneInfo
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional


def generate_code(length: int = 6) -> str:
    """Генерация случайного кода из заглавных букв и цифр"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def parse_deadline_input(input_text: str) -> Optional[datetime]:
    """
    Обрабатывает ввод дедлайна в двух форматах:
    - "HH:MM" → ближайшее время сегодня или завтра
    - "HH:MM DD.MM.YYYY" → конкретное время
    """
    input_text = input_text.strip()

    try:
        # Полный формат: 22:00 07.07.2025
        dt = datetime.strptime(input_text, "%H:%M %d.%m.%Y")
        return dt.replace(tzinfo=ZoneInfo("Asia/Tashkent"))

    except ValueError:
        try:
            # Только время
            time_part = datetime.strptime(input_text, "%H:%M").time()
            now = datetime.now().replace(tzinfo=None)  # убираем tzinfo
            today_deadline = datetime.combine(now.date(), time_part)
            deadline = today_deadline if today_deadline > now else today_deadline + timedelta(days=1)
            return deadline.replace(tzinfo=ZoneInfo("Asia/Tashkent"))

        except ValueError:
            return None