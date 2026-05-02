from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
import pandas as pd
import numpy as np
import time

app = FastAPI()

# =====================
# DB CONFIG
# =====================
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# =====================
# CAT CORE
# =====================
def prob_correct(theta, b):
    return 1 / (1 + np.exp(-(theta - b)))


def update_theta(theta, b, result):
    p = prob_correct(theta, b)
    return theta + 0.2 * (result - p)


# =====================
# STOPPING CONDITION
# =====================
def check_convergence(theta_history, threshold=0.01, window=3):
    if len(theta_history) < window:
        return False

    recent = theta_history[-window:]
    return max(recent) - min(recent) < threshold


# =====================
# REQUEST MODEL
# =====================
class SubmitAnswer(BaseModel):
    attempt_id: int
    question_id: int
    selected_option: str
    time_spent_sec: int


# =====================
# START CAT
# =====================
@app.post("/cat/start/{student_id}/{subject_id}")
def start_cat(student_id: int, subject_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT ability FROM students WHERE id=%s", (student_id,))
        theta = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO attempts (
                student_id,
                subject_id,
                current_theta,
                last_theta,
                theta_history,
                question_count,
                max_questions,
                started_at
            )
            VALUES (%s, %s, %s, %s, %s, 0, 20, NOW())
            RETURNING id
        """, (student_id, subject_id, theta, theta, [theta]))

        attempt_id = cur.fetchone()[0]
        conn.commit()

        return {"attempt_id": attempt_id, "theta": theta}

    finally:
        cur.close()
        conn.close()


# =====================
# NEXT QUESTION
# =====================
@app.get("/cat/next/{attempt_id}")
def get_next_question(attempt_id: int):
    conn = get_conn()

    try:
        attempt = pd.read_sql("""
            SELECT current_theta, question_count, max_questions, subject_id, is_finished
            FROM attempts WHERE id=%s
        """, conn, params=[attempt_id]).iloc[0]

        if attempt["is_finished"] or attempt["question_count"] >= attempt["max_questions"]:
            return {"message": "Exam finished"}

        theta = attempt["current_theta"]
        subject_id = attempt["subject_id"]

        used = pd.read_sql("""
            SELECT question_id FROM attempt_answers
            WHERE attempt_id=%s
        """, conn, params=[attempt_id])["question_id"].tolist()

        df = pd.read_sql("""
            SELECT id, difficulty, content
            FROM questions
            WHERE subject_id = %s
        """, conn, params=[subject_id])

        df = df[~df["id"].isin(used)]

        if df.empty:
            return {"message": "No more questions"}

        df["gap"] = abs(df["difficulty"] - theta)
        q = df.sort_values("gap").iloc[0]

        return {
            "question_id": int(q["id"]),
            "difficulty": float(q["difficulty"]),
            "content": q["content"]
        }

    finally:
        conn.close()


# =====================
# SUBMIT ANSWER
# =====================
@app.post("/cat/answer")
def submit_answer(req: SubmitAnswer):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # get correct + difficulty
        cur.execute("""
            SELECT correct_option, difficulty
            FROM questions WHERE id=%s
        """, (req.question_id,))
        correct, difficulty = cur.fetchone()

        is_correct = (req.selected_option == correct)

        # load attempt
        cur.execute("""
            SELECT current_theta, theta_history
            FROM attempts WHERE id=%s
        """, (req.attempt_id,))
        theta, history = cur.fetchone()

        # update theta
        new_theta = update_theta(theta, difficulty, int(is_correct))

        history.append(new_theta)

        # save answer (LOGGING)
        cur.execute("""
            INSERT INTO attempt_answers (
                attempt_id, question_id, selected_option,
                is_correct, time_spent_sec
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            req.attempt_id,
            req.question_id,
            req.selected_option,
            is_correct,
            req.time_spent_sec
        ))

        # check stopping
        finished = check_convergence(history)

        # update attempt
        cur.execute("""
            UPDATE attempts
            SET current_theta = %s,
                last_theta = %s,
                theta_history = %s,
                question_count = question_count + 1,
                is_finished = %s
            WHERE id = %s
        """, (
            new_theta,
            theta,
            history,
            finished,
            req.attempt_id
        ))

        conn.commit()

        return {
            "is_correct": is_correct,
            "theta": new_theta,
            "finished": finished
        }

    finally:
        cur.close()
        conn.close()


# =====================
# SUBMIT EXAM
# =====================
@app.post("/cat/submit/{attempt_id}")
def submit_exam(attempt_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE is_correct)
            FROM attempt_answers
            WHERE attempt_id=%s
        """, (attempt_id,))
        score = cur.fetchone()[0]

        cur.execute("""
            UPDATE attempts
            SET submitted_at = NOW(),
                total_score = %s
            WHERE id = %s
        """, (score, attempt_id))

        conn.commit()

        return {"score": score}

    finally:
        cur.close()
        conn.close()
