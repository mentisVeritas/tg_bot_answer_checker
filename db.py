import sqlite3
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from config import OWNER_ID
from zoneinfo import ZoneInfo  # добавь в начало файла


DB_NAME = "data/db.sqlite3"


def get_connection():
    return sqlite3.connect(DB_NAME)


def create_tables():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            created_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            updated_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            test_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            code TEXT UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            created_by INTEGER,
            created_at TEXT,
            deadline TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER,
            question_number INTEGER,
            correct_answer TEXT,
            score REAL,
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            test_id INTEGER,
            answer_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (test_id) REFERENCES tests(test_id)
        )
        """)

        conn.commit()

# --- Пользователи ---
def add_user(user_id: int, first_name: str, last_name: str, username: str = None):
    created_at = (datetime.utcnow() + timedelta(hours=5)).replace(microsecond=0).isoformat(timespec='seconds')
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, first_name, last_name, username, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, first_name, last_name, username, created_at))
        conn.commit()


def user_exists(user_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return row.fetchone() is not None


# --- Админы ---
def is_admin(user_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
        return row.fetchone() is not None


def is_admin_or_owner(user_id: int) -> bool:
    return user_id == OWNER_ID or is_admin(user_id)


def add_admin(user_id: int):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (user_id,))
        conn.commit()


def remove_admin(user_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM admins WHERE admin_id = ?", (user_id,))
        conn.commit()


def get_all_admins() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT admin_id FROM admins").fetchall()
        return [r[0] for r in rows]


def sync_admin_info(user_id: int, first_name: str, last_name: str, username: str):
    updated_at = (datetime.utcnow() + timedelta(hours=5)).replace(microsecond=0).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO admins (admin_id, first_name, last_name, username, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(admin_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                username=excluded.username,
                updated_at=excluded.updated_at
        """, (user_id, first_name, last_name, username, updated_at))
        conn.commit()


# --- Тесты ---
def generate_code(length: int = 6) -> str:
    with get_connection() as conn:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
            if not conn.execute("SELECT 1 FROM tests WHERE code = ?", (code,)).fetchone():
                return code


def create_test(title: str, code: str, admin_id: int, deadline: datetime) -> int:
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO tests (title, code, is_active, created_by, deadline)
            VALUES (?, ?, 1, ?, ?)
        """, (title, code, admin_id, deadline.isoformat()))
        return cursor.lastrowid


def add_question(test_id: int, number: int, answer: str, score: float):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO questions (test_id, question_number, correct_answer, score)
            VALUES (?, ?, ?, ?)
        """, (test_id, number, answer, score))
        conn.commit()


def get_tests_by_admin(admin_id: int):
    with get_connection() as conn:
        rows = conn.execute("SELECT test_id, title FROM tests WHERE created_by = ?", (admin_id,))
        return rows.fetchall()


def get_test_with_answers(test_id: int):
    with get_connection() as conn:
        test_info = conn.execute("SELECT title, code, deadline FROM tests WHERE test_id = ?", (test_id,)).fetchone()
        if not test_info:
            return None

        title, code, deadline = test_info
        questions = conn.execute("SELECT question_number, correct_answer, score FROM questions WHERE test_id = ?", (test_id,)).fetchall()
        count = conn.execute("SELECT COUNT(*) FROM answers WHERE test_id = ?", (test_id,)).fetchone()[0]

        return title, questions, count, code, deadline


def delete_test(test_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
        conn.execute("DELETE FROM answers WHERE test_id = ?", (test_id,))
        conn.execute("DELETE FROM tests WHERE test_id = ?", (test_id,))
        conn.commit()


# --- Логика ответов и дедлайна ---
def is_valid_code(code: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM tests WHERE code = ? AND is_active = 1", (code,))
        return row.fetchone() is not None


def get_test_id_by_code(code: str) -> Optional[int]:
    with get_connection() as conn:
        cursor = conn.execute("SELECT test_id FROM tests WHERE code = ?", (code,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_test_deadline(test_id: int) -> Optional[datetime]:
    with get_connection() as conn:
        row = conn.execute("SELECT deadline FROM tests WHERE test_id = ?", (test_id,)).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

def has_submitted(user_id: int, test_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM answers WHERE user_id = ? AND test_id = ?", (user_id, test_id)).fetchone()
        return row is not None


def get_correct_answers(test_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT question_number, correct_answer, score
            FROM questions
            WHERE test_id = ?
            ORDER BY question_number
        """, (test_id,)).fetchall()
        return [{"question_number": r[0], "correct_answer": r[1], "score": r[2]} for r in rows]


def save_answers(user_id: int, test_id: int, answer_text: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO answers (user_id, test_id, answer_text, submitted_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, test_id, answer_text, (datetime.utcnow() + timedelta(hours=5)).replace(microsecond=0).isoformat()))
        conn.commit()


# --- Results and Details ---
def get_test_results(test_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.username, a.submitted_at, a.answer_text
            FROM answers a
            JOIN users u ON u.user_id = a.user_id
            WHERE a.test_id = ?
            ORDER BY u.user_id, a.submitted_at
        """, (test_id,))
        rows = cursor.fetchall()

        correct_answers = get_correct_answers(test_id)
        correct_map = {q["question_number"]: (q["correct_answer"].strip().lower(), q["score"]) for q in correct_answers}
        total_score = sum(q["score"] for q in correct_answers)

        # Сгруппируем ответы по пользователю, возьмём последний (по submitted_at)
        from collections import defaultdict
        user_answers = defaultdict(list)
        user_info = {}

        for row in rows:
            user_id, first_name, last_name, username, submitted_at, answer_text = row
            user_info[user_id] = (first_name, last_name, username)
            user_answers[user_id].append((submitted_at, answer_text))

        results = []
        for user_id, answers_list in user_answers.items():
            # Возьмём последний ответ по дате
            answers_list.sort(key=lambda x: x[0], reverse=True)
            submitted_at, answer_text = answers_list[0]

            parsed_answers = {}
            for line in answer_text.strip().splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2 and parts[0].isdigit():
                    parsed_answers[int(parts[0])] = parts[1].strip().lower()

            score = 0
            solved = 0
            for q_num, (correct_ans, score_val) in correct_map.items():
                user_ans = parsed_answers.get(q_num, "")
                if user_ans == correct_ans:
                    score += score_val
                    solved += 1

            first_name, last_name, username = user_info[user_id]

            results.append({
                "user_id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "submitted_at": submitted_at,
                "score": round(score, 2),
                "solved": solved,
                "total": len(correct_map),
                "max_score": round(total_score, 2)
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)


def get_user_answers_detailed(test_id: int, user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT answer_text FROM answers WHERE test_id = ? AND user_id = ?", (test_id, user_id))
        row = cursor.fetchone()
        if not row:
            return []


        answer_text = row[0]
        user_answers = {}
        for line in answer_text.strip().splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].isdigit():
                user_answers[int(parts[0])] = parts[1].strip().lower()

        correct_answers = get_correct_answers(test_id)
        details = []
        for q in correct_answers:
            q_num = q["question_number"]
            correct = q["correct_answer"].strip().lower()
            user_val = user_answers.get(q_num, "")
            is_correct = (user_val == correct)
            details.append({
                "question_number": q_num,
                "user_answer": user_val,
                "is_correct": is_correct,
                "score": q["score"]
            })

        return details