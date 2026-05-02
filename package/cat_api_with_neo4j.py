from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
import pandas as pd
import numpy as np
from neo4j import GraphDatabase

# =====================================================
# APP INIT
# =====================================================

app = FastAPI()

# =====================================================
# CONFIG
# =====================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"

neo_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# =====================================================
# CAT CORE (IRT 1PL)
# =====================================================

def prob_correct(theta, b):
    return 1 / (1 + np.exp(-(theta - b)))


def update_theta(theta, b, result):
    p = prob_correct(theta, b)
    return theta + 0.2 * (result - p)


def check_convergence(theta_history, threshold=0.01, window=3):
    if len(theta_history) < window:
        return False
    recent = theta_history[-window:]
    return max(recent) - min(recent) < threshold


# =====================================================
# NEO4J FUNCTIONS
# =====================================================

def init_mastery(student_id):
    query = """
    MATCH (t:Topic)
    MERGE (s:Student {student_id: $student_id})
    MERGE (s)-[r:HAS_MASTERY]->(t)
    ON CREATE SET r.mastery = 0.5
    """
    with neo_driver.session() as session:
        session.run(query, student_id=student_id)


def get_weak_topics(student_id, limit=3):
    query = """
    MATCH (s:Student {student_id: $student_id})
          -[r:HAS_MASTERY]->(t:Topic)
    RETURN t.topic_id AS topic_id, r.mastery AS mastery
    ORDER BY r.mastery ASC
    LIMIT $limit
    """
    with neo_driver.session() as session:
        result = session.run(query, student_id=student_id, limit=limit)
        return [r["topic_id"] for r in result]


def get_questions_from_topics(topic_ids):
    query = """
    MATCH (q:Question)-[rel:RELATED_TO]->(t:Topic)
    WHERE t.topic_id IN $topic_ids
    RETURN q.question_id AS qid,
           rel.relevance_weight AS weight
    ORDER BY weight DESC
    """
    with neo_driver.session() as session:
        result = session.run(query, topic_ids=topic_ids)
        return [(r["qid"], r["weight"]) for r in result]


def update_mastery(student_id, question_id, result):
    query = """
    MATCH (s:Student {student_id: $student_id})
    MATCH (q:Question {question_id: $qid})
    MATCH (q)-[rel:RELATED_TO]->(t:Topic)
    MATCH (s)-[m:HAS_MASTERY]->(t)

    SET m.mastery =
        m.mastery + rel.relevance_weight * ($result - m.mastery)
    """
    with neo_driver.session() as session:
        session.run(query,
                    student_id=student_id,
                    qid=question_id,
                    result=result)


# =====================================================
# REQUEST MODEL
# =====================================================

class SubmitAnswer(BaseModel):
    attempt_id: int
    student_id: int
    question_id: int
    selected_option: str
    time_spent_sec: int


# =====================================================
# START CAT
# =====================================================

@app.post("/cat/start/{student_id}/{subject_id}")
def start_cat(student_id: int, subject_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        # init mastery graph
        init_mastery(student_id)

        # get initial theta
        cur.execute("SELECT ability FROM students WHERE id=%s", (student_id,))
        theta = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO attempts (
                student_id, subject_id,
                current_theta, last_theta,
                theta_history, question_count,
                max_questions, started_at
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


# =====================================================
# NEXT QUESTION (HYBRID)
# =====================================================

@app.get("/cat/next/{attempt_id}")
def get_next_question(attempt_id: int):
    conn = get_conn()

    try:
        attempt = pd.read_sql("""
            SELECT current_theta, subject_id,
                   student_id, is_finished,
                   question_count, max_questions
            FROM attempts WHERE id=%s
        """, conn, params=[attempt_id]).iloc[0]

        if attempt["is_finished"]:
            return {"message": "Exam finished"}

        theta = attempt["current_theta"]
        student_id = attempt["student_id"]

        # STEP 1: weak topics
        weak_topics = get_weak_topics(student_id)

        # STEP 2: graph candidates
        candidates = get_questions_from_topics(weak_topics)

        if not candidates:
            return {"message": "No graph candidates"}

        candidate_ids = [c[0] for c in candidates]

        # STEP 3: load from PostgreSQL
        df = pd.read_sql("""
            SELECT id, difficulty, content
            FROM questions
            WHERE id = ANY(%s)
        """, conn, params=[candidate_ids])

        if df.empty:
            return {"message": "No questions"}

        # STEP 4: hybrid scoring
        df["gap"] = abs(df["difficulty"] - theta)

        weight_map = dict(candidates)
        df["graph_weight"] = df["id"].map(weight_map)

        df["score"] = 0.7 * df["gap"] + 0.3 * (1 - df["graph_weight"])

        q = df.sort_values("score").iloc[0]

        return {
            "question_id": int(q["id"]),
            "difficulty": float(q["difficulty"]),
            "content": q["content"]
        }

    finally:
        conn.close()


# =====================================================
# SUBMIT ANSWER
# =====================================================

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

        # save answer
        cur.execute("""
            INSERT INTO attempt_answers (
                attempt_id, question_id,
                selected_option, is_correct,
                time_spent_sec
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            req.attempt_id,
            req.question_id,
            req.selected_option,
            is_correct,
            req.time_spent_sec
        ))

        # update mastery (Neo4j)
        update_mastery(
            student_id=req.student_id,
            question_id=req.question_id,
            result=int(is_correct)
        )

        # check stop
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


# =====================================================
# SUBMIT EXAM
# =====================================================

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
