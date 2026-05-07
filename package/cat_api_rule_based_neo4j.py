from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
import pandas as pd
import numpy as np
from neo4j import GraphDatabase

# ================= CONFIG =================

PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"

app = FastAPI(title="CAT Rule-based Neo4j API")

neo_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

def get_conn():
    return psycopg2.connect(**PG_CONFIG)

# ================= IRT =================

def prob_correct(theta, b):
    return 1 / (1 + np.exp(-(theta - b)))

def update_theta(theta, b, result, lr=0.2):
    p = prob_correct(theta, b)
    return float(theta + lr * (result - p))

# ================= RULE ENGINE =================

def evaluate_condition(val, op, thr):
    return {
        ">": val > thr,
        "<": val < thr,
        ">=": val >= thr,
        "<=": val <= thr,
        "==": val == thr
    }.get(op, False)

def forward_chain(rules, difficulty, is_correct):
    facts = {"difficulty": difficulty, "correct": is_correct}
    delta = 0.0

    for r in rules:
        cond = evaluate_condition(
            facts["difficulty"],
            r.get("operator"),
            r.get("threshold")
        )
        res = (facts["correct"] == r.get("result_required"))

        if cond and res:
            delta += r.get("weight", 0)
            facts["difficulty"] += r.get("difficulty_delta", 0)

    return delta

# ================= NEO4J =================

def init_mastery(student_id):
    with neo_driver.session() as s:
        s.run("""
        MATCH (t:Topic)
        MERGE (s:Student {student_id:$sid})
        MERGE (s)-[r:HAS_MASTERY]->(t)
        ON CREATE SET r.mastery = 0.5
        """, sid=student_id)

def get_weak_topics(student_id, k=3):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t)
        RETURN t.topic_id AS tid, r.mastery AS m
        ORDER BY m ASC LIMIT $k
        """, sid=student_id, k=k)
        return [r["tid"] for r in res]

def get_learning_path(topic_ids):
    if not topic_ids:
        return []
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (t:Topic)
        WHERE t.topic_id IN $tids
        MATCH (t)<-[:PREREQUISITE_OF*]-(pre)
        RETURN DISTINCT pre.topic_id AS tid
        """, tids=topic_ids)
        return [r["tid"] for r in res]

def get_rules(topic_id):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (r:Rule)-[:APPLIES_TO]->(t:Topic {topic_id:$tid})
        RETURN r ORDER BY r.priority DESC
        """, tid=topic_id)
        return [dict(r["r"]) for r in res]

def update_mastery(student_id, question_id, is_correct, difficulty):
    explanations = []

    with neo_driver.session() as s:
        res = s.run("""
        MATCH (q:Question {question_id:$qid})-[rel:RELATED_TO]->(t)
        RETURN t.topic_id AS tid, rel.relevance_weight AS w
        """, qid=question_id)

        for r in res:
            tid = r["tid"]
            weight = r["w"]

            rules = get_rules(tid)
            delta = forward_chain(rules, difficulty, is_correct)

            s.run("""
            MATCH (s:Student {student_id:$sid})-[m:HAS_MASTERY]->(t:Topic {topic_id:$tid})
            SET m.mastery = coalesce(m.mastery,0.5) + $delta * $w
            """, sid=student_id, tid=tid, delta=delta, w=weight)

            explanations.append({
                "topic": tid,
                "delta": delta,
                "rules_applied": len(rules)
            })

    return explanations

# ================= MODELS =================

class AnswerRequest(BaseModel):
    attempt_id: int
    student_id: int
    question_id: int
    selected_option: str
    time_spent_sec: int

# ================= START =================

@app.post("/cat/start/{student_id}/{subject_id}")
def start(student_id: int, subject_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        init_mastery(student_id)

        cur.execute(
            "SELECT ability FROM students WHERE student_id=%s",
            (student_id,)
        )
        row = cur.fetchone()
        theta = row[0] if row and row[0] is not None else 0.0

        cur.execute("""
        INSERT INTO attempts(
            student_id, subject_id,
            current_theta, last_theta, theta_history
        )
        VALUES (%s,%s,%s,%s,%s)
        RETURNING attempt_id
        """, (student_id, subject_id, theta, theta, [theta]))

        aid = cur.fetchone()[0]
        conn.commit()

        return {"attempt_id": aid}

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

# ================= NEXT =================

@app.get("/cat/next/{aid}")
def next_q(aid: int):
    conn = get_conn()

    try:
        at = pd.read_sql(
            "SELECT * FROM attempts WHERE attempt_id=%s",
            conn,
            params=[aid]
        )

        if at.empty:
            raise HTTPException(404, "Attempt not found")

        at = at.iloc[0]
        theta = at["current_theta"]
        sid = at["student_id"]

        weak = get_weak_topics(sid)
        prereq = get_learning_path(weak)
        topic_pool = list(set(weak + prereq))

        if not topic_pool:
            raise HTTPException(404, "No topics found")

        with neo_driver.session() as s:
            res = s.run("""
            MATCH (q:Question)-[r:RELATED_TO]->(t)
            WHERE t.topic_id IN $tids
            RETURN q.question_id AS qid, r.relevance_weight AS w
            """, tids=topic_pool)

            candidates = [(r["qid"], r["w"]) for r in res]

        if not candidates:
            raise HTTPException(404, "No questions found")

        ids = [c[0] for c in candidates]

        df = pd.read_sql("""
            SELECT question_id, difficulty, content
            FROM questions
            WHERE question_id = ANY(%s)
        """, conn, params=[ids])

        if df.empty:
            raise HTTPException(404, "No questions in DB")

        wm = dict(candidates)

        df["gap"] = abs(df["difficulty"] - theta)
        df["w"] = df["question_id"].map(wm)
        df["score"] = 0.7 * df["gap"] + 0.3 * (1 - df["w"])

        q = df.sort_values("score").iloc[0]

        return {
            "question_id": int(q["question_id"]),
            "content": q["content"]
        }

    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        conn.close()

# ================= ANSWER =================

@app.post("/cat/answer")
def answer(req: AnswerRequest):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT qo.option_label, q.difficulty
            FROM questions q
            JOIN question_options qo
            ON q.question_id = qo.question_id
            WHERE q.question_id=%s AND qo.is_correct=true
        """, (req.question_id,))

        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Question not found")

        correct, diff = row
        is_correct = (req.selected_option == correct)

        cur.execute("""
            SELECT current_theta, theta_history
            FROM attempts WHERE attempt_id=%s
        """, (req.attempt_id,))

        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Attempt not found")

        theta, hist = row

        new_theta = update_theta(theta, diff, int(is_correct))
        hist.append(new_theta)

        explanation = update_mastery(
            req.student_id,
            req.question_id,
            is_correct,
            diff
        )

        cur.execute("""
            UPDATE attempts
            SET current_theta=%s,
                theta_history=%s
            WHERE attempt_id=%s
        """, (new_theta, hist, req.attempt_id))

        conn.commit()

        return {
            "correct": is_correct,
            "theta": new_theta,
            "explanation": explanation
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

# ================= SUBMIT =================

@app.post("/cat/submit/{attempt_id}")
def submit(attempt_id: int):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT student_id, theta_history
            FROM attempts WHERE attempt_id=%s
        """, (attempt_id,))

        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Attempt not found")

        student_id, theta_hist = row
        final_theta = theta_hist[-1]

        cur.execute("""
            UPDATE attempts
            SET status='COMPLETED'
            WHERE attempt_id=%s
        """, (attempt_id,))

        conn.commit()

        with neo_driver.session() as s:
            res = s.run("""
            MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t)
            RETURN t.topic_id AS topic, r.mastery AS mastery
            ORDER BY mastery ASC
            """, sid=student_id)

            mastery = [dict(r) for r in res]

        return {
            "attempt_id": attempt_id,
            "final_theta": final_theta,
            "status": "COMPLETED",
            "mastery_summary": mastery
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

# ================= EXPLAIN =================

@app.get("/cat/explain/{student_id}")
def explain(student_id: int):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t)
        RETURN t.topic_id AS topic, r.mastery AS mastery
        ORDER BY mastery ASC
        """, sid=student_id)

        return [dict(r) for r in res]

# ================= HEALTH =================

@app.get("/")
def root():
    return {"status": "CAT Rule-based API running"}
