from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import OWNER_ID
from db import is_admin

def get_main_keyboard(user_id: int, is_user: bool = False) -> ReplyKeyboardMarkup:
    buttons = []

    # Пользователь
    if is_user:
        buttons.append([KeyboardButton(text="Проверить тест")])
        buttons.append([KeyboardButton(text="Мой профиль")])

    # Админ или владелец
    if is_admin(user_id) or user_id == OWNER_ID:
        buttons.append([KeyboardButton(text="Создать тест"),KeyboardButton(text="Проверить тест")])
        buttons.append([KeyboardButton(text="Мои тесты")])

    # Только владелец
    if user_id == OWNER_ID:
        buttons.append([
            KeyboardButton(text="➕ Добавить админа"),
            KeyboardButton(text="➖ Удалить админа")
        ])
        buttons.append([KeyboardButton(text="📋 Список админов")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )