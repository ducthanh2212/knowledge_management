from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
import pandas as pd
import numpy as np
from neo4j import GraphDatabase

app = FastAPI()

# ================= CONFIG =================
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

neo_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_conn():
    return psycopg2.connect(**DB_CONFIG)

# ================= IRT =================

def prob_correct(theta, b):
    return 1 / (1 + np.exp(-(theta - b)))


def update_theta(theta, b, result):
    p = prob_correct(theta, b)
    return theta + 0.2 * (result - p)

# ================= RULE ENGINE (CHAINING) =================

def evaluate_condition(val, op, thr):
    if op == ">": return val > thr
    if op == "<": return val < thr
    if op == ">=": return val >= thr
    if op == "<=": return val <= thr
    if op == "==": return val == thr
    return False


def get_rules(topic_id):
    query = """
    MATCH (r:Rule)-[:APPLIES_TO]->(t:Topic {topic_id:$tid})
    RETURN r ORDER BY r.priority DESC
    """
    with neo_driver.session() as s:
        res = s.run(query, tid=topic_id)
        return [dict(r["r"]) for r in res]


def forward_chain(rules, difficulty, is_correct):
    facts = {"difficulty": difficulty, "correct": is_correct}
    delta = 0

    for r in rules:
        cond = evaluate_condition(facts["difficulty"], r["operator"], r["threshold"])
        res = (facts["correct"] == r["result_required"])

        if cond and res:
            delta += r["weight"]

            # chaining effect
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


def get_weak_topics(student_id):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t)
        RETURN t.topic_id AS tid, r.mastery AS m
        ORDER BY m ASC LIMIT 3
        """, sid=student_id)
        return [r["tid"] for r in res]


def get_learning_path(topic_id):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (t:Topic {topic_id:$tid})<-[:PREREQUISITE_OF*]-(pre)
        RETURN pre.topic_id AS tid
        """, tid=topic_id)
        return [r["tid"] for r in res]


def update_mastery(student_id, question_id, is_correct, difficulty):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (q:Question {question_id:$qid})-[rel:RELATED_TO]->(t)
        RETURN t.topic_id AS tid, rel.relevance_weight AS w
        """, qid=question_id)

        explanations = []

        for r in res:
            tid = r["tid"]
            w = r["w"]

            rules = get_rules(tid)
            delta = forward_chain(rules, difficulty, is_correct)

            s.run("""
            MATCH (s:Student {student_id:$sid})-[m:HAS_MASTERY]->(t:Topic {topic_id:$tid})
            SET m.mastery = m.mastery + $d * $w
            """, sid=student_id, tid=tid, d=delta, w=w)

            explanations.append({
                "topic": tid,
                "delta": delta,
                "rules_used": len(rules)
            })

        return explanations

# ================= MODELS =================

class SubmitAnswer(BaseModel):
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

    init_mastery(student_id)

    cur.execute("SELECT ability FROM students WHERE id=%s", (student_id,))
    theta = cur.fetchone()[0]

    cur.execute("""
    INSERT INTO attempts(student_id,subject_id,current_theta,last_theta,theta_history)
    VALUES(%s,%s,%s,%s,%s) RETURNING id
    """, (student_id, subject_id, theta, theta, [theta]))

    aid = cur.fetchone()[0]
    conn.commit()
    return {"attempt_id": aid}

# ================= NEXT =================

@app.get("/cat/next/{aid}")
def next_q(aid: int):
    conn = get_conn()

    at = pd.read_sql("SELECT * FROM attempts WHERE id=%s", conn, params=[aid]).iloc[0]

    theta = at["current_theta"]
    sid = at["student_id"]

    topics = get_weak_topics(sid)

    # include prerequisite learning path
    extended = set(topics)
    for t in topics:
        extended.update(get_learning_path(t))

    with neo_driver.session() as s:
        res = s.run("""
        MATCH (q:Question)-[r:RELATED_TO]->(t)
        WHERE t.topic_id IN $tids
        RETURN q.question_id AS qid, r.relevance_weight AS w
        """, tids=list(extended))

        candidates = [(r["qid"], r["w"]) for r in res]

    ids = [c[0] for c in candidates]

    df = pd.read_sql("SELECT id,difficulty,content FROM questions WHERE id=ANY(%s)", conn, params=[ids])

    df["gap"] = abs(df["difficulty"] - theta)
    wm = dict(candidates)
    df["w"] = df["id"].map(wm)

    df["score"] = 0.6*df["gap"] + 0.4*(1-df["w"])

    q = df.sort_values("score").iloc[0]

    return {"qid": int(q["id"]), "content": q["content"]}

# ================= ANSWER =================

@app.post("/cat/answer")
def answer(req: SubmitAnswer):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT correct_option,difficulty FROM questions WHERE id=%s", (req.question_id,))
    correct, diff = cur.fetchone()

    is_correct = (req.selected_option == correct)

    cur.execute("SELECT current_theta,theta_history FROM attempts WHERE id=%s", (req.attempt_id,))
    theta, hist = cur.fetchone()

    new_theta = update_theta(theta, diff, int(is_correct))
    hist.append(new_theta)

    explanation = update_mastery(req.student_id, req.question_id, is_correct, diff)

    cur.execute("UPDATE attempts SET current_theta=%s,theta_history=%s WHERE id=%s",
                (new_theta, hist, req.attempt_id))

    conn.commit()

    return {
        "correct": is_correct,
        "theta": new_theta,
        "explanation": explanation
    }

# ================= EXPLAIN =================

@app.get("/cat/explain/{student_id}")
def explain(student_id: int):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t)
        RETURN t.topic_id AS topic, r.mastery AS m
        ORDER BY m ASC
        """, sid=student_id)

        return [{"topic": r["topic"], "mastery": r["m"]} for r in res]

# ================= EVALUATION =================

@app.get("/cat/evaluate/{attempt_id}")
def evaluate(attempt_id: int):
    conn = get_conn()

    df = pd.read_sql("SELECT is_correct FROM attempt_answers WHERE attempt_id=%s", conn, params=[attempt_id])

    accuracy = df["is_correct"].mean()

    return {
        "accuracy": float(accuracy),
        "total_questions": len(df)
    }
