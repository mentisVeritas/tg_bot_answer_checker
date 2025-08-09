from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import OWNER_ID
from db import is_admin, get_connection
from keyboards import get_main_keyboard

router = Router()


def ensure_users_table_has_needed_columns():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]

    if "full_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        conn.commit()
    if "first_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        conn.commit()
    if "last_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
        conn.commit()
    if "username" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.commit()

    cursor.close()
    conn.close()


# --- Состояния регистрации ---
class UserRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_name_confirm = State()


# --- /start ---
@router.message(F.text == "/start")
async def start_handler(message: Message, state: FSMContext):
    ensure_users_table_has_needed_columns()

    username = message.from_user.username
    user_id = message.from_user.id
    conn = get_connection()
    cursor = conn.cursor()

    # Обновляем username (если нужно, добавляем пользователя)
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    if exists:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    else:
        cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row and row[0]:
        full_name = row[0]
    else:
        await message.answer("📝 Отправьте ваше имя и фамилию на латинице\nпример: Ivanov Ivan:")
        await state.set_state(UserRegistration.waiting_for_name)
        cursor.close()
        conn.close()
        return

    cursor.close()
    conn.close()

    if user_id == OWNER_ID:
        role = "👑 Владелец"
    elif is_admin(user_id):
        role = "🛡 Админ"
    else:
        role = "👤 Пользователь"

    await message.answer(
        f"👋 Добро пожаловать, <b>{full_name}</b>!\nТы вошёл как: <b>{role}</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user_id, is_user=(role == '👤 Пользователь'))
    )


# --- Получение имени ---
@router.message(UserRegistration.waiting_for_name)
async def ask_confirm_name(message: Message, state: FSMContext):
    raw_name = message.text.strip().upper()
    parts = raw_name.split()

    if len(parts) < 2:
        await message.answer("❗ Укажите и имя, и фамилию через пробел.")
        return

    # Форматируем с заглавной буквы
    full_name = " ".join(parts)
    last_name = parts[0]
    first_name = parts[1]

    await state.update_data(full_name=full_name, first_name=first_name, last_name=last_name)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_name")],
        [InlineKeyboardButton(text="❌ Отправить заново", callback_data="redo_name")]
    ])

    await message.answer(
        f"Вы указали: <b>{full_name}</b>\nВсё верно?",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(UserRegistration.waiting_for_name_confirm)


# --- Подтверждение ФИО ---
@router.callback_query(F.data == "confirm_name")
async def confirm_name(callback: CallbackQuery, state: FSMContext):
    username = callback.from_user.username
    user_id = callback.from_user.id
    data = await state.get_data()
    full_name = data.get("full_name")
    first_name = data.get("first_name")
    last_name = data.get("last_name")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, full_name, first_name, last_name, username)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name = excluded.full_name,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            username = excluded.username
    """, (user_id, full_name, first_name, last_name, username))
    conn.commit()
    cursor.close()
    conn.close()

    await state.clear()

    if user_id == OWNER_ID:
        role = "👑 Владелец"
    elif is_admin(user_id):
        role = "🛡 Админ"
    else:
        role = "👤 Пользователь"

    await callback.message.edit_text(
        f"✅ Спасибо, {full_name}!\nТы вошёл как: <b>{role}</b>",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "📋 Главное меню:",
        reply_markup=get_main_keyboard(user_id, is_user=(role == '👤 Пользователь'))
    )


# --- Повторный ввод ФИО ---
@router.callback_query(F.data == "redo_name")
async def redo_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✏️ Отправьте, пожалуйста, имя и фамилию снова\nпример: Ivanov Ivan:")
    await state.set_state(UserRegistration.waiting_for_name)


# --- Мой профиль ---
@router.message(F.text == "Мой профиль")
async def profile_handler(message: Message):
    user_id = message.from_user.id
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.title, a.answer_text, a.submitted_at
        FROM answers a
        JOIN tests t ON t.test_id = a.test_id
        WHERE a.user_id = ?
        ORDER BY a.submitted_at DESC
    """, (user_id,))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    if not rows:
        return await message.answer("📭 Ты пока не проходил ни одного теста.")

    response = "<b>📊 Мой профиль:</b>\n\n"
    for title, answer_text, date in rows:
        # 'date' is used as a string directly, no datetime conversion is done
        num_answers = len(answer_text.strip().splitlines())
        response += f"📄 <b>{title}</b>\n📅 {date}\nОтветов: {num_answers}\n\n"

    await message.answer(response.strip(), parse_mode="HTML")
