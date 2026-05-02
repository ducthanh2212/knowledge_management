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
# RULE ENGINE
# =====================================================

def evaluate_condition(value, operator, threshold):
    if operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == "==":
        return value == threshold
    return False


def get_rules_for_topic(topic_id):
    query = """
    MATCH (r:Rule)-[:APPLIES_TO]->(t:Topic {topic_id: $topic_id})
    RETURN r
    """

    with neo_driver.session() as session:
        result = session.run(query, topic_id=topic_id)
        rules = []
        for record in result:
            r = record["r"]
            rules.append({
                "operator": r["operator"],
                "threshold": r["threshold"],
                "result_required": r["result_required"],
                "weight": r["weight"]
            })
        return rules


def apply_rules(rules, difficulty, is_correct):
    delta = 0
    for rule in rules:
        cond_ok = evaluate_condition(
            difficulty,
            rule["operator"],
            rule["threshold"]
        )
        result_ok = (is_correct == rule["result_required"])
        if cond_ok and result_ok:
            delta += rule["weight"]
    return delta

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


def update_mastery_rule_based(student_id, question_id, is_correct, difficulty):
    query = """
    MATCH (q:Question {question_id: $qid})-[rel:RELATED_TO]->(t:Topic)
    RETURN t.topic_id AS topic_id, rel.relevance_weight AS w
    """

    with neo_driver.session() as session:
        result = session.run(query, qid=question_id)

        for record in result:
            topic_id = record["topic_id"]
            weight = record["w"]

            rules = get_rules_for_topic(topic_id)
            delta = apply_rules(rules, difficulty, int(is_correct))

            session.run("""
                MATCH (s:Student {student_id: $sid})
                      -[m:HAS_MASTERY]->(t:Topic {topic_id: $tid})
                SET m.mastery = m.mastery + $delta * $w
            """, sid=student_id, tid=topic_id, delta=delta, w=weight)

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
        init_mastery(student_id)

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
# NEXT QUESTION
# =====================================================

@app.get("/cat/next/{attempt_id}")
def get_next_question(attempt_id: int):
    conn = get_conn()

    try:
        attempt = pd.read_sql("""
            SELECT current_theta, subject_id,
                   student_id, is_finished
            FROM attempts WHERE id=%s
        """, conn, params=[attempt_id]).iloc[0]

        if attempt["is_finished"]:
            return {"message": "Exam finished"}

        theta = attempt["current_theta"]
        student_id = attempt["student_id"]

        weak_topics = get_weak_topics(student_id)
        candidates = get_questions_from_topics(weak_topics)

        if not candidates:
            return {"message": "No candidates"}

        candidate_ids = [c[0] for c in candidates]

        df = pd.read_sql("""
            SELECT id, difficulty, content
            FROM questions
            WHERE id = ANY(%s)
        """, conn, params=[candidate_ids])

        if df.empty:
            return {"message": "No questions"}

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
        cur.execute("""
            SELECT correct_option, difficulty
            FROM questions WHERE id=%s
        """, (req.question_id,))
        correct, difficulty = cur.fetchone()

        is_correct = (req.selected_option == correct)

        cur.execute("""
            SELECT current_theta, theta_history
            FROM attempts WHERE id=%s
        """, (req.attempt_id,))
        theta, history = cur.fetchone()

        new_theta = update_theta(theta, difficulty, int(is_correct))
        history.append(new_theta)

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

        update_mastery_rule_based(
            student_id=req.student_id,
            question_id=req.question_id,
            is_correct=is_correct,
            difficulty=difficulty
        )

        finished = check_convergence(history)

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

