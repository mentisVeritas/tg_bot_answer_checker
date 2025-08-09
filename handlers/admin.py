from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from config import OWNER_ID
from db import (
    is_admin_or_owner,
    create_test, add_question, generate_code,
    get_tests_by_admin, get_test_with_answers,
    delete_test, add_admin, remove_admin, get_all_admins
)
from utils.helpers import parse_deadline_input

router = Router()


class CreateTestState(StatesGroup):
    waiting_for_title = State()
    waiting_for_title_confirm = State()
    waiting_for_questions = State()
    waiting_for_questions_confirm = State()
    waiting_for_deadline = State()
    waiting_for_deadline_confirm = State()
    confirm = State()


class FSMOwner(StatesGroup):
    adding = State()
    removing = State()


@router.message(F.text.lower() == "создать тест")
async def ask_test_title(message: Message, state: FSMContext):
    if not is_admin_or_owner(message.from_user.id):
        await message.answer("🚫 У вас нет прав для создания тестов.")
        return
    await message.answer("📝 Введите название теста:")
    await state.set_state(CreateTestState.waiting_for_title)


@router.message(CreateTestState.waiting_for_title)
async def confirm_test_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_title"),
            InlineKeyboardButton(text="✏️ Ввести другое", callback_data="edit_title")
        ],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_create_test")]
    ])
    await message.answer(f"Название теста: <b>{message.text.strip()}</b>\nПодтвердите?", reply_markup=keyboard,
                         parse_mode="HTML")
    await state.set_state(CreateTestState.waiting_for_title_confirm)


@router.callback_query(F.data == "confirm_title")
async def title_confirmed(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Название подтверждено. Теперь введите вопросы.")
    await state.set_state(CreateTestState.waiting_for_questions)
    await callback.message.answer(
        "✏️ ВВЕДИ ВОПРОСЫ И БАЛЛЫ ПОСТРОЧНО. КАЖДЫЙ В ФОРМАТЕ:\n\n"
        "НОМЕР ОТВЕТ БАЛЛ\n"
        "Баллы должны быть положительными и кратны 0.5 (например: 1, 2.5, 3.0)\n\n"
        "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
        "• A, B, C\n"
        "• Целые числа (например: 1, -12, 12345)\n"
        "• Простые дроби (например: 3/4, -2/3)\n"
        "• Десятичные числа (например: 0.667, -0.75, 123.4)\n"
        "• Максимум 5 символов (или 6 с минусом)\n\n"
        "✅ ПРИМЕРЫ:\n"
        "1 A 1\n"
        "2 3/4 0.5\n"
        "3 -2/3 1.5\n"
        "4 -0.75 2\n"
        "5 0.667 2.5\n"
        "6 12345 1\n"
        "7 123.4 3\n"
        "8 -12.3 2.5\n"
        "9 -1.5 1.5\n"
        "10 B 1\n"
    )


@router.callback_query(F.data == "edit_title")
async def edit_title(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✏️ Отправьте, пожалуйста, новый вариант названия:")
    await state.set_state(CreateTestState.waiting_for_title)


@router.message(CreateTestState.waiting_for_questions)
async def receive_questions(message: Message, state: FSMContext):
    lines = message.text.strip().splitlines()
    questions = []

    for line in lines:
        try:
            parts = line.strip().split()
            if len(parts) < 3:
                raise ValueError(f"НЕДОСТАТОЧНО ЭЛЕМЕНТОВ В СТРОКЕ:\n{line}")
            q = int(parts[0])
            score_val = float(parts[-1])
            answer = " ".join(parts[1:-1])

            # Проверяем длину ответа (не более 5 символов без минуса, 6 с минусом)
            if len(answer.replace("-", "")) > 5:
                raise ValueError(f"ОТВЕТ ПРЕВЫШАЕТ ДОПУСТИМУЮ ДЛИНУ В СТРОКЕ:\n{line}")

            # Преобразуем допустимые дроби в десятичный формат (например: 2/3 → 0.667)
            if "/" in answer and answer.replace("-", "").count("/") == 1:
                try:
                    sign = "-" if answer.startswith("-") else ""
                    num, denom = answer.replace("-", "").split("/")
                    frac_val = float(int(num)) / int(denom)
                    point = str(5-(len(str(int(frac_val)))+1))
                    answer = f"{sign}{frac_val:.{point}f}".rstrip("0").rstrip(".")
                except Exception:
                    raise ValueError("НЕКОРРЕКТНАЯ ДРОБЬ В СТРОКЕ:\n{line}")

            questions.append((q, answer.strip(), score_val))
        except Exception as e:
            await message.answer(
                f"❌ {e}\n\n"
                "✏️ ВВЕДИ ВОПРОСЫ И БАЛЛЫ ПОСТРОЧНО. КАЖДЫЙ В ФОРМАТЕ:\n"
                "НОМЕР ОТВЕТ БАЛЛ\n\n"
                "Баллы должны быть положительными и кратны 0.5 (например: 1, 2.5, 3.0)\n\n"
                "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
                "• A, B, C\n"
                "• Целые числа (например: 1, -12, 12345)\n"
                "• Простые дроби (например: 3/4, -2/3)\n"
                "• Десятичные числа (например: 0.667, -0.75, 123.4)\n"
                "• Максимум 5 символов (или 6 с минусом)\n\n"
                "✅ ПРИМЕРЫ:\n"
                "1 A 1\n"
                "2 3/4 0.5\n"
                "3 -2/3 1.5\n"
                "4 -0.75 2\n"
                "5 0.667 2.5\n"
                "6 12345 1\n"
                "7 123.4 3\n"
                "8 -12.3 2.5\n"
                "9 -1.5 1.5\n"
                "10 B 1\n"
            )
            return

    await state.update_data(questions=questions)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_questions"),
            InlineKeyboardButton(text="🔁 Ввести заново", callback_data="edit_questions")
        ],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_create_test")]
    ])
    preview = "\n".join([f"{q}. {a} (+{s})" for q, a, s in questions])
    await message.answer(f"Вот что получилось:\n\n{preview}\n\nПодтвердите?", reply_markup=keyboard)
    await state.set_state(CreateTestState.waiting_for_questions_confirm)


@router.callback_query(F.data == "confirm_questions")
async def confirm_questions(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Вопросы подтверждены. Теперь введите дедлайн.")
    await callback.message.answer("📅 Введите дедлайн в формате:\nЧЧ:ММ или ЧЧ:ММ ДД.ММ.ГГГГ")
    await state.set_state(CreateTestState.waiting_for_deadline)


@router.callback_query(F.data == "edit_questions")
async def redo_questions(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ ВВЕДИ ВОПРОСЫ И БАЛЛЫ ПОСТРОЧНО. КАЖДЫЙ В ФОРМАТЕ:\n\n"
        "НОМЕР ОТВЕТ БАЛЛ\n"
        "Баллы должны быть положительными и кратны 0.5 (например: 1, 2.5, 3.0)\n\n"
        "✅ ДОПУСТИМЫЕ ОТВЕТЫ:\n"
        "• A, B, C\n"
        "• Целые числа (например: 1, -12, 12345)\n"
        "• Простые дроби (например: 3/4, -2/3)\n"
        "• Десятичные числа (например: 0.667, -0.75, 123.4)\n"
        "• Максимум 5 символов (или 6 с минусом)\n\n"
        "✅ ПРИМЕРЫ:\n"
        "1 A 1\n"
        "2 3/4 0.5\n"
        "3 -2/3 1.5\n"
        "4 -0.75 2\n"
        "5 0.667 2.5\n"
        "6 12345 1\n"
        "7 123.4 3\n"
        "8 -12.3 2.5\n"
        "9 -1.5 1.5\n"
        "10 B 1\n"
    )
    await state.set_state(CreateTestState.waiting_for_questions)


@router.message(CreateTestState.waiting_for_deadline)
async def receive_deadline(message: Message, state: FSMContext):
    deadline = parse_deadline_input(message.text.strip())
    if not deadline:
        await message.answer("❌ Неверный формат. Пример: 22:00 или 22:00 07.07.2025")
        return

    await state.update_data(deadline=deadline)
    data = await state.get_data()
    title = data["title"]
    questions = data["questions"]
    deadline_str = deadline.strftime("%H:%M %d.%m.%Y")

    preview = "\n".join([f"{q}. {a} (+{s})" for q, a, s in questions])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_create_test"),
            InlineKeyboardButton(text="🔁 Изменить дедлайн", callback_data="edit_deadline")
        ],
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_create_test")]
    ])

    await message.answer(
        f"🔍 Подтверди:\n<b>{title}</b>\n⏰ Дедлайн: {deadline_str}\n\n{preview}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(CreateTestState.confirm)


@router.callback_query(F.data == "edit_deadline")
async def redo_deadline(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📅 Введите дедлайн в формате:\nЧЧ:ММ или ЧЧ:ММ ДД.ММ.ГГГГ")
    await state.set_state(CreateTestState.waiting_for_deadline)


@router.callback_query(F.data == "confirm_create_test")
async def confirm_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    title = data["title"]
    questions = data["questions"]
    deadline = data["deadline"]
    # Ensure deadline is timezone-aware, default to +5:00 if not set
    from datetime import timezone, timedelta
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone(timedelta(hours=5)))
    admin_id = callback.from_user.id

    code = generate_code()
    test_id = create_test(title=title, code=code, admin_id=admin_id, deadline=deadline)

    for q, a, s in questions:
        add_question(test_id, q, a, s)

    await callback.message.edit_text(f"✅ Тест создан!\nКод: <code>{code}</code>", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "cancel_create_test")
async def cancel_create(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Создание теста отменено.")
    await state.clear()


@router.message(F.text == "📋 Список админов")
async def list_admins(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    admins = get_all_admins()
    if not admins:
        await message.answer("Список админов пуст.")
    else:
        text = "📋 Админы:\n" + "\n".join([f"• {aid}" for aid in admins])
        await message.answer(text)


@router.message(F.text == "➕ Добавить админа")
async def ask_add_admin(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer("🔢 Введи ID пользователя для добавления в админы:")
    await state.set_state(FSMOwner.adding)


@router.message(FSMOwner.adding)
async def do_add_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        add_admin(admin_id)
        await message.answer(f"✅ Админ {admin_id} добавлен.")
    except:
        await message.answer("❌ Неверный ID.")
    await state.clear()


@router.message(F.text == "➖ Удалить админа")
async def ask_remove_admin(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer("❌ Введи ID администратора для удаления:")
    await state.set_state(FSMOwner.removing)


@router.message(FSMOwner.removing)
async def do_remove_admin(message: Message, state: FSMContext):
    try:
        admin_id = int(message.text.strip())
        remove_admin(admin_id)
        await message.answer(f"✅ Админ {admin_id} удалён.")
    except:
        await message.answer("❌ Неверный ID.")
    await state.clear()


@router.message(F.text.lower() == "мои тесты")
async def show_my_tests(message: Message):
    user_id = message.from_user.id
    if not is_admin_or_owner(user_id):
        return

    tests = get_tests_by_admin(user_id)
    if not tests:
        await message.answer("📭 У тебя пока нет тестов.")
        return

    builder = InlineKeyboardBuilder()
    for test_id, title in tests:
        builder.row(InlineKeyboardButton(text=title, callback_data=f"view_test_info:{test_id}"))

    await message.answer("📚 Выбери тест:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("view_test_info:"))
async def show_test_info(callback: CallbackQuery):
    try:
        test_id = int(callback.data.split(":")[1])
    except:
        return await callback.message.answer("❌ Ошибка обработки запроса.")

    data = get_test_with_answers(test_id)
    if not data:
        return await callback.message.edit_text("❌ Тест не найден.")

    title, questions, submissions, code, deadline = data
    deadline_str = datetime.fromisoformat(deadline).strftime("%H:%M %d.%m.%Y") if deadline else "—"

    header = (
        f"📄 <b>{title}</b>\n"
        f"🔐 Код: <code>{code}</code>\n"
        f"⏰ Дедлайн: {deadline_str}\n"
        f"👥 Сдали: {submissions} чел.\n\n"
    )
    q_block = "\n".join([f"{q}. {a} (+{s})" for q, a, s in questions])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Посмотреть результаты", callback_data=f"view_results:{test_id}")],
        [InlineKeyboardButton(text="🗑 Удалить тест", callback_data=f"delete_test_confirm:{test_id}")]
    ])

    await callback.message.edit_text(header + q_block, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("delete_test_confirm:"))
async def confirm_delete(callback: CallbackQuery):
    test_id = int(callback.data.split(":")[1])
    data = get_test_with_answers(test_id)

    if not data:
        return await callback.message.edit_text("❌ Тест не найден.")

    title, questions, submissions, code, deadline = data
    deadline_str = datetime.fromisoformat(deadline).strftime("%H:%M %d.%m.%Y") if deadline else "—"

    header = (
        f"📄 <b>{title}</b>\n"
        f"🔐 Код: <code>{code}</code>\n"
        f"⏰ Дедлайн: {deadline_str}\n"
        f"👥 Сдали: {submissions} чел.\n\n"
    )
    q_block = "\n".join([f"{q}. {a} (+{s})" for q, a, s in questions])
    footer = f'\n\n\n<b>УДАЛИТЬ ТЕСТ "{title}"?</b>'

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"delete_test:{test_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"view_test_info:{test_id}")
        ]
    ])

    await callback.message.edit_text(header + q_block + footer, parse_mode="HTML", reply_markup=keyboard)



@router.callback_query(F.data.startswith("delete_test:"))
async def do_delete(callback: CallbackQuery):
    test_id = int(callback.data.split(":")[1])
    delete_test(test_id)
    await callback.message.edit_text("✅ Тест успешно удалён.")


# ====== РЕЗУЛЬТАТЫ ТЕСТА И ОТВЕТЫ УЧАСТНИКОВ ======
from db import get_test_results, get_user_answers_detailed
from aiogram.utils.markdown import hbold

@router.callback_query(F.data.startswith("view_results:"))
async def view_results(callback: CallbackQuery):
    test_id = int(callback.data.split(":")[1])
    results = get_test_results(test_id)  # Должен возвращать список участников с баллами по убыванию

    if not results:
        return await callback.message.answer("📭 Пока никто не сдал этот тест.")

    await callback.message.answer("📊 <b>Результаты участников:</b>", parse_mode="HTML")


    for result in results:
        first_name = result["first_name"]
        last_name = result["last_name"]
        username = f'@{result["username"]}' if result.get("username") else None
        submitted_at = datetime.fromisoformat(result["submitted_at"])
        score = result["score"]
        max_score = result["max_score"]
        solved = result["solved"]
        total = result["total"]
        user_id = result["user_id"]

        text = (
            "👤 <b>УЧАСТНИК</b>\n\n"
            f"Ф.И.О: {last_name} {first_name}\n"
        )

        if username:
            text += f"🆔 Юзернейм: {username}\n"

        text += (
            f"🕒 Время сдачи: {submitted_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"✅ Заданий решено: {solved} из {total}\n"
            f"💯 Баллов набрано: {score} из {max_score}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Посмотреть ответы", callback_data=f"view_user_answers:{test_id}:{user_id}")]
        ])

        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("view_user_answers:"))
async def view_user_answers(callback: CallbackQuery):
    _, test_id, user_id = callback.data.split(":")
    test_id = int(test_id)
    user_id = int(user_id)

    answers = get_user_answers_detailed(test_id, user_id)
    if not answers:
        return await callback.message.answer("❌ Ответы не найдены.")

    # Получим текст предыдущего сообщения (где информация об участнике)
    original_text = callback.message.text or ""

    # Формируем блок с ответами
    answers_block = "\n\n📋 <b>ОТВЕТЫ УЧАСТНИКА:</b>\n\n"
    for item in answers:
        q_num = item["question_number"]
        answer = item["user_answer"]
        # Аналогичная обработка дробей для отображения
        if "/" in answer and answer.replace("-", "").count("/") == 1:
            try:
                num, denom = answer.replace("-", "").split("/")
                frac_val = float(int(num)) / int(denom)
                if answer.startswith("-"):
                    frac_val = -frac_val
                answer = f"{frac_val:.3f}".rstrip("0").rstrip(".")
            except:
                answer = "НЕКОРРЕКТНАЯ ДРОБЬ"
        is_correct = item["is_correct"]
        score = item["score"]

        icon = "✅" if is_correct else "❌"
        answers_block += f"{q_num}. {answer} ({score}) {icon}\n"

    # Объединяем исходный текст + блок с ответами
    updated_text = original_text.strip() + answers_block

    # Кнопка "Свернуть"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔽 Свернуть", callback_data=f"collapse_user_answers:{test_id}:{user_id}")]
    ])

    # Обновляем то же сообщение
    await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data.startswith("collapse_user_answers:"))
async def collapse_user_answers(callback: CallbackQuery):
    test_id, user_id = map(int, callback.data.split(":")[1:])

    original_text = callback.message.text or ""

    # Удаляем блок с ответами
    if "📋 ОТВЕТЫ УЧАСТНИКА" in original_text:
        original_text = original_text.split("📋 ОТВЕТЫ УЧАСТНИКА")[0].strip()

    # Восстанавливаем кнопку "Посмотреть ответы"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Посмотреть ответы", callback_data=f"view_user_answers:{test_id}:{user_id}")]
    ])

    await callback.message.edit_text(original_text, parse_mode="HTML", reply_markup=keyboard)
