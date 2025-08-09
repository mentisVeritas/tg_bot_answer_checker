from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot

# Импортируйте ваши функции из 'db'
from db import (
    is_valid_code,
    get_test_id_by_code,
    get_correct_answers,
    save_answers,
    get_test_deadline,
    has_submitted
)

router = Router()


# --- Определение состояний FSM ---
class UserState(StatesGroup):
    waiting_for_code = State()
    waiting_for_answers = State()
    awaiting_confirmation = State()  # Новое состояние для ожидания подтверждения ответов


# --- Хелпер функция для форматирования результатов ---
def format_result_comparison(correct_data: list[dict], user_answers: dict[int, str]) -> tuple[str, int, int]:
    """
    Сравнивает правильные ответы с пользовательскими.
    Предполагается, что user_answers уже является словарем {номер_вопроса: ответ}.
    Возвращает:
        - текст с пометками ✅/❌
        - число правильных
        - общую сумму баллов
    """
    result_lines = []
    correct_count = 0
    total_score = 0
    max_score = 0

    for item in correct_data:
        qnum = item["question_number"]
        correct = item["correct_answer"]
        score = item["score"]
        max_score += score

        user_ans = user_answers.get(qnum)

        if user_ans is not None and str(user_ans).strip().lower() == str(correct).strip().lower():
            result_lines.append(f"{qnum}: {user_ans} ✅")
            correct_count += 1
            total_score += score
        else:
            result_lines.append(f"{qnum}: {user_ans or '—'} ❌")  # Если ответа нет, показываем "—"

    summary = "\n".join(result_lines)
    summary += f"\n\n🎯 Итог: {correct_count} из {len(correct_data)} верно"
    summary += f"\nОбщий балл: {total_score} из {max_score}"

    return summary, correct_count, total_score


# --- Хелпер функция для отправки напоминаний о дедлайне ---
async def send_deadline_reminders(user_id: int, test_id: int, deadline: datetime, bot: Bot, state: FSMContext):

    reminder_tasks = []

    reminders = [
        (timedelta(minutes=15), "⏰ Осталось 15 минут. Рассчитай время и не спеши."),
        (timedelta(minutes=3), "⚠️ Осталось 3 минуты. Пора заканчивать.")
    ]

    for td, text in reminders:
        now = datetime.now(ZoneInfo("Asia/Tashkent"))
        time_to_wait = (deadline - now - td).total_seconds()

        if time_to_wait > 0:
            async def _send_single_reminder(delay_sec, message_text):
                await asyncio.sleep(delay_sec)
                if not has_submitted(user_id, test_id) and await state.get_state() is not None:
                    try:
                        await bot.send_message(user_id, message_text)
                    except Exception as e:
                        print(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")

            task = asyncio.create_task(_send_single_reminder(time_to_wait, text))
            reminder_tasks.append(task)

    final_delay = (deadline - datetime.now(ZoneInfo("Asia/Tashkent"))).total_seconds()
    if final_delay > 0:
        async def _send_deadline_passed_message():
            await asyncio.sleep(final_delay)
            if not has_submitted(user_id, test_id) and await state.get_state() is not None:
                try:
                    await bot.send_message(user_id, "🕰 Время вышло. Тест теперь недоступен для сдачи.")
                except Exception as e:
                    print(f"Ошибка при отправке сообщения о дедлайне пользователю {user_id}: {e}")

        task = asyncio.create_task(_send_deadline_passed_message())
        reminder_tasks.append(task)

    await state.update_data(reminder_tasks=reminder_tasks)


# --- Обработчик команды "Проверить тест" ---
@router.message(F.text.lower() == "проверить тест")
async def ask_for_code(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_test_flow")]
    ])
    await message.answer("🔐 Введи код теста:", reply_markup=keyboard)
    await state.set_state(UserState.waiting_for_code)


# --- Обработчик получения кода теста ---
@router.message(UserState.waiting_for_code, F.text & ~F.text.startswith("/"))
async def receive_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id

    if not is_valid_code(code):
        await message.answer("❌ Неверный код. Проверь и попробуй ещё раз.")
        await state.clear()
        return

    test_id = get_test_id_by_code(code)
    if has_submitted(user_id, test_id):
        await message.answer("⚠️ Ты уже проходил этот тест. Повторная отправка запрещена.")
        await state.clear()
        return

    deadline = get_test_deadline(test_id)
    now = datetime.now(ZoneInfo("Asia/Tashkent"))

    if deadline and now > deadline:
        await message.answer("⏰ Срок сдачи теста уже истёк. Начать тест нельзя.")
        await state.clear()
        return

    await state.update_data(test_id=test_id, deadline=deadline)
    # Обновленные примеры, как в admin.py
    await message.answer("✍️ Введи свои ответы в формате:\n\n"
                         "НОМЕР ОТВЕТ\n"
                         "Ответ должен соответствовать правилам и быть не длиннее 5 символов (6 — если с минусом).\n\n"
                         "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
                         "• `A, B, C`\n"
                         "• `Целые числа` (например: `1, -12, 12345`)\n"
                         "• `Простые дроби` (например: `3/4, -2/3`)\n"
                         "• `Десятичные числа` (например: `0.667, -0.75, 123.4`)\n"
                         "• `Максимум 5 символов` (или `6 с минусом`)\n\n"
                         "✅ ПРИМЕРЫ:\n"
                         "`1 A`\n`2 3/4`\n`3 -2/3`\n`4 -0.75`\n`5 0.667`\n"
                         "`6 12345`\n`7 123.4`\n`8 -12.3`\n`9 -1.5`\n`10 B`", parse_mode="Markdown")

    await state.set_state(UserState.waiting_for_answers)
    bot: Bot = message.bot
    asyncio.create_task(send_deadline_reminders(user_id, test_id, deadline, bot, state))


# --- Основной обработчик ввода ответов и их парсинга ---
@router.message(UserState.waiting_for_answers)
async def process_user_test_submission(message: Message, state: FSMContext):
    user_id = message.from_user.id
    answers_raw = message.text.strip()
    data = await state.get_data()
    test_id = data.get("test_id")
    deadline = get_test_deadline(test_id)

    now = datetime.now(ZoneInfo("Asia/Tashkent"))

    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=ZoneInfo("Asia/Tashkent"))


    if deadline and now > deadline:
        await message.answer("❌ Срок сдачи уже прошёл. К сожалению, ответ не может быть принят.")
        await state.clear()
        return

    lines = answers_raw.splitlines()
    questions = []
    for line in lines:
        try:
            parts = line.strip().split()
            if len(parts) != 2:
                raise ValueError(f"НЕДОСТАТОЧНО ИЛИ СЛИШКОМ МНОГО ЭЛЕМЕНТОВ В СТРОКЕ:\n{line}")
            q = int(parts[0])
            answer = parts[1]

            # Проверяем длину ответа (не более 5 символов без минуса, 6 с минусом)
            if len(answer.replace("-", "")) > 5:
                raise ValueError(f"ОТВЕТ ПРЕВЫШАЕТ ДОПУСТИМУЮ ДЛИНУ В СТРОКЕ:\n{line}")

            # Преобразуем допустимые дроби в десятичный формат (например: 2/3 → 0.667)
            if "/" in answer and answer.replace("-", "").count("/") == 1:
                try:
                    sign = "-" if answer.startswith("-") else ""
                    num, denom = answer.replace("-", "").split("/")
                    frac_val = float(int(num)) / int(denom)
                    point = str(5 - (len(str(int(frac_val))) + 1))
                    answer = f"{sign}{frac_val:.{point}f}".rstrip("0").rstrip(".")
                except Exception:
                    raise ValueError("НЕКОРРЕКТНАЯ ДРОБЬ В СТРОКЕ:\n{line}")
            questions.append((q, answer.strip()))
        except Exception as e:
            await message.answer(
                f"❌ {e}\n\n"
                "✍️ Введи свои ответы в формате:\n\n"
                "НОМЕР ОТВЕТ\n"
                "Ответ должен соответствовать правилам и быть не длиннее 5 символов (6 — если с минусом).\n\n"
                "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
                "• `A, B, C`\n"
                "• `Целые числа` (например: `1, -12, 12345`)\n"
                "• `Простые дроби` (например: `3/4, -2/3`)\n"
                "• `Десятичные числа` (например: `0.667, -0.75, 123.4`)\n"
                "• `Максимум 5 символов` (или `6 с минусом`)\n\n"
                "✅ ПРИМЕРЫ:\n"
                "`1 A`\n`2 3/4`\n`3 -2/3`\n`4 -0.75`\n`5 0.667`\n"
                "`6 12345`\n`7 123.4`\n`8 -12.3`\n`9 -1.5`\n`10 B`", parse_mode="Markdown")
            return

    answers_raw = "\n".join(f"{q} {answer}" for q, answer in questions).strip()

    await state.update_data(raw_answers=answers_raw, parsed_questions=questions)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_answers_submission"),
            InlineKeyboardButton(text="🔁 Ввести заново", callback_data="re_enter_answers")
        ],
        [InlineKeyboardButton(text="❌ Отменить тест", callback_data="cancel_test_flow")]
    ])
    preview = "\n".join([f"{q}. {a}" for q, a in questions])
    await message.answer(f"Вот что получилось:\n\n`{preview}`\n\n*Подтвердите?*", reply_markup=keyboard,
                         parse_mode="Markdown")

    await state.set_state(UserState.awaiting_confirmation)


# --- Обработчик для кнопки "Подтвердить" ---
@router.callback_query(F.data == "confirm_answers_submission", UserState.awaiting_confirmation)
async def handle_confirm_answers(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer("Обработка ответов...")
    data = await state.get_data()
    test_id = data.get("test_id")
    user_id = callback_query.from_user.id
    user_answers_parsed = data.get("parsed_questions")
    answers_raw = data.get("raw_answers")

    if not user_answers_parsed:
        await callback_query.message.edit_text("❌ Ответы не найдены или истекло время. Пожалуйста, начни заново.")
        await state.clear()
        return

    if has_submitted(user_id, test_id):
        await callback_query.message.edit_text("⚠️ Ты уже проходил этот тест. Повторная отправка запрещена.")
        await state.clear()
        return

    correct_data = get_correct_answers(test_id)
    user_answers_dict_for_comparison = {q: a for q, a, *_ in user_answers_parsed}

    summary, correct_count, total_score = format_result_comparison(correct_data, user_answers_dict_for_comparison)

    save_answers(user_id, test_id, answers_raw)


    await callback_query.message.edit_text(summary, parse_mode="Markdown")
    await state.clear()


# --- Обработчик для кнопки "Ввести заново" ---
@router.callback_query(F.data == "re_enter_answers", UserState.awaiting_confirmation)
async def handle_re_enter_answers(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer("Введите ответы заново.")
    # Обновленные примеры, как в admin.py
    await callback_query.message.edit_text(
        "🔁 *Введите ответы заново, следуя формату:*\n"
        "`НОМЕР ОТВЕТ`\n\n"
        "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
        "• `A, B, C`\n"
        "• `Целые числа` (например: `1, -12, 12345`)\n"
        "• `Простые дроби` (например: `3/4, -2/3`)\n"
        "• `Десятичные числа` (например: `0.667, -0.75, 123.4`)\n"
        "• `Максимум 5 символов` (или `6 с минусом`)\n\n"
        "✅ ПРИМЕРЫ:\n"
        "`1 A`\n`2 3/4`\n`3 -2/3`\n`4 -0.75`\n`5 0.667`\n"
        "`6 12345`\n`7 123.4`\n`8 -12.3`\n`9 -1.5`\n`10 B`", parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_answers)


@router.callback_query(F.data == "cancel_test_flow")
async def handle_cancel_test_flow(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer("Действие отменено.")
    data = await state.get_data()
    tasks = data.get("reminder_tasks", [])
    for task in tasks:
        task.cancel()
    await callback_query.message.edit_text(
        "❌ Проверка теста отменена. Вы можете начать заново, отправив команду 'Проверить тест'."
    )
    await state.clear()
