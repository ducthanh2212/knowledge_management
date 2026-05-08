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

def evaluate_condition(fact_value, op, target_value):
    if fact_value is None or target_value is None:
        return False
        
    if op == "==": return fact_value == target_value
    if op == ">=": return fact_value >= target_value
    if op == "<=": return fact_value <= target_value
    if op == ">": return fact_value > target_value
    if op == "<": return fact_value < target_value
    
    return False

def forward_chain(rules, difficulty, is_correct):
    # Tập hợp các sự kiện thực tế (facts) từ câu trả lời của user
    facts = {
        "difficulty": float(difficulty),
        "correct": bool(is_correct)
    }
    total_delta = 0.0

    for r in rules:
        rule_passed = True
        conditions = r.get("conditions", [])
        
        # Duyệt qua TẤT CẢ điều kiện của Rule này (Cả correct và difficulty)
        for cond in conditions:
            field = cond.get("field")
            op = cond.get("operator")
            val = cond.get("value")
            
            # Ép kiểu an toàn cho value từ DB
            if field == "correct" and isinstance(val, str):
                val = val.lower() in ["true", "1", "yes"]
            elif field == "difficulty" and val is not None:
                val = float(val)

            fact_value = facts.get(field)
            
            if not evaluate_condition(fact_value, op, val):
                rule_passed = False
                break # Chỉ cần 1 điều kiện sai, Rule này sẽ bị bỏ qua

        if rule_passed and conditions: # Nếu pass tất cả điều kiện
            rule_weight = float(r.get("weight", 1.0))
            action_delta = float(r.get("delta", 0.0))
            
            applied_delta = action_delta * rule_weight
            total_delta += applied_delta
            
            print(f"[Rule Triggered] {r.get('rule_id')} | Delta applied: {applied_delta}")

    return total_delta

# ================= NEO4J =================

def init_mastery(student_id):
    with neo_driver.session() as s:
        s.run("""
        MATCH (t:Topic)
        MERGE (s:Student {student_id:$sid})
        MERGE (s)-[r:HAS_MASTERY]->(t)
        ON CREATE SET r.mastery = 0.5
        """, sid=student_id)

def get_weak_topics(student_id, valid_topic_ids=None, k=3):
    with neo_driver.session() as s:
        query = "MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t:Topic)"
        
        if valid_topic_ids is not None:
            query += " WHERE t.topic_id IN $valid_tids"
            
        query += """
        RETURN t.topic_id AS tid, r.mastery AS m
        ORDER BY m ASC LIMIT $k
        """
        res = s.run(query, sid=student_id, valid_tids=valid_topic_ids, k=k)
        return [r["tid"] for r in res]
    
def get_learning_path(topic_ids):
    # Đã loại bỏ logic :PREREQUISITE_OF vì database của bạn không sử dụng nó
    # Trả về trực tiếp topic_ids để hệ thống tập trung xoáy sâu vào các điểm yếu
    return topic_ids if topic_ids else []

def get_rules(topic_id):
    with neo_driver.session() as s:
        # Gom tất cả Condition của 1 Rule lại thành 1 list bằng collect()
        res = s.run("""
        MATCH (r:Rule)-[:HAS_CONDITION]->(c:Condition)
        OPTIONAL MATCH (r)-[:HAS_ACTION]->(a:Action)
        WHERE r.is_active = true
        WITH r, a, collect({field: c.field, operator: c.operator, value: c.value}) AS conditions
        RETURN 
            r.rule_id AS rule_id,
            r.weight AS weight,
            r.priority AS priority,
            conditions,
            a.delta AS delta
        ORDER BY r.priority DESC
        """)
        return [dict(row) for row in res]

def update_mastery(student_id, question_id, is_correct, difficulty):
    explanations = []
    with neo_driver.session() as s:
        # LẤY THÊM t.name TRONG TRUY VẤN
        res = s.run("""
        MATCH (q:Question {question_id:$qid})-[rel:RELATED_TO|PRIMARY_TOPIC]->(t:Topic)
        RETURN t.topic_id AS tid, t.name AS tname, rel.relevance_weight AS w
        """, qid=question_id)

        for r in res:
            tid = r["tid"]
            tname = r["tname"] # Lấy tên từ kết quả truy vấn
            weight = float(r["w"]) if r.get("w") is not None else 1.0

            rules = get_rules(tid)
            delta = forward_chain(rules, difficulty, is_correct)

            if delta != 0.0:
                s.run("""
                MATCH (s:Student {student_id:$sid})-[m:HAS_MASTERY]->(t:Topic {topic_id:$tid})
                WITH m, coalesce(m.mastery, 0.5) + ($delta * $w) AS new_mastery
                SET m.mastery = CASE 
                    WHEN new_mastery > 1.0 THEN 1.0
                    WHEN new_mastery < 0.0 THEN 0.0
                    ELSE new_mastery 
                END
                """, sid=student_id, tid=tid, delta=float(delta), w=weight)

            explanations.append({
                "topic": tname,  # TRẢ VỀ TÊN THAY VÌ ID
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

# ================= REST OF THE API =================

@app.post("/cat/start/{student_id}/{subject_id}")
def start(student_id: int, subject_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        init_mastery(student_id)
        cur.execute("SELECT ability FROM students WHERE student_id=%s", (student_id,))
        row = cur.fetchone()
        theta = float(row[0]) if row and row[0] is not None else 0.0

        cur.execute("""
        INSERT INTO attempts(student_id, subject_id, current_theta, last_theta, theta_history)
        VALUES (%s,%s,%s,%s,%s) RETURNING attempt_id
        """, (student_id, subject_id, theta, theta, [theta]))
        aid = cur.fetchone()[0]
        conn.commit()
        return {"attempt_id": aid}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

@app.get("/cat/next/{aid}")
def next_q(aid: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT current_theta, student_id, subject_id FROM attempts WHERE attempt_id=%s", (aid,))
        row = cur.fetchone()
        if not row: raise HTTPException(404, "Attempt not found")
        theta, sid, subject_id = float(row[0]), row[1], row[2]

        cur.execute("SELECT topic_id FROM topics WHERE subject_id=%s", (subject_id,))
        valid_topics = [r[0] for r in cur.fetchall()]
        if not valid_topics: raise HTTPException(404, "Không tìm thấy Topic")

        weak = get_weak_topics(sid, valid_topic_ids=valid_topics)
        prereq = get_learning_path(weak)
        topic_pool = list(set(weak + prereq))

        with neo_driver.session() as s:
            res = s.run("""
            MATCH (q:Question)-[r:RELATED_TO|PRIMARY_TOPIC]->(t:Topic)
            WHERE t.topic_id IN $tids
            RETURN q.question_id AS qid, r.relevance_weight AS w
            """, tids=topic_pool)
            candidates = [(r["qid"], r["w"]) for r in res]

        if not candidates: raise HTTPException(404, "No questions in Graph")
        ids = [c[0] for c in candidates]

        cur.execute("""
            SELECT question_id, difficulty, content FROM questions
            WHERE question_id = ANY(%s) AND question_id NOT IN (
                  SELECT question_id FROM attempt_answers WHERE attempt_id = %s
            )
        """, (ids, aid))
        
        rows = cur.fetchall()
        if not rows: return {"status": "COMPLETED", "message": "No more questions"}

        questions_data = [{"question_id": r[0], "difficulty": float(r[1]), "content": r[2]} for r in rows]
        wm = dict(candidates)

        for q in questions_data:
            gap = abs(q["difficulty"] - theta)
            w = float(wm.get(q["question_id"], 0.5) or 0.5)
            q["score"] = 0.7 * gap + 0.3 * (1.0 - w)

        best_q = sorted(questions_data, key=lambda x: x["score"])[0]
        qid = int(best_q["question_id"])

        cur.execute("SELECT option_label, option_text FROM question_options WHERE question_id=%s", (qid,))
        options_dict = {r[0]: r[1] for r in cur.fetchall()}

        return {"question_id": qid, "content": best_q["content"], "options": options_dict}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/cat/answer")
def answer(req: AnswerRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT qo.option_label, q.difficulty FROM questions q
            JOIN question_options qo ON q.question_id = qo.question_id
            WHERE q.question_id=%s AND qo.is_correct=true
        """, (req.question_id,))
        row = cur.fetchone()
        if not row: raise HTTPException(404, "Question not found")

        correct_label, diff = row[0], float(row[1])
        is_correct = (req.selected_option == correct_label)

        cur.execute("SELECT current_theta, theta_history FROM attempts WHERE attempt_id=%s", (req.attempt_id,))
        row = cur.fetchone()
        theta, hist = float(row[0]), row[1]
        
        new_theta = update_theta(theta, diff, int(is_correct))
        hist.append(new_theta)

        explanation = update_mastery(req.student_id, req.question_id, is_correct, diff)

        cur.execute("""
            INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct, time_spent_sec)
            VALUES (%s, %s, %s, %s, %s)
        """, (req.attempt_id, req.question_id, req.selected_option, is_correct, req.time_spent_sec))

        cur.execute("UPDATE attempts SET current_theta=%s, theta_history=%s WHERE attempt_id=%s", (new_theta, hist, req.attempt_id))
        conn.commit()

        return {"correct": is_correct, "theta": new_theta, "explanation": explanation}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()

@app.post("/cat/submit/{attempt_id}")
def submit(attempt_id: int):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT student_id, theta_history FROM attempts WHERE attempt_id=%s", (attempt_id,))
        row = cur.fetchone()
        student_id, theta_hist = row[0], row[1]
        
        # Lấy theta cuối cùng của lượt thi này
        final_theta = float(theta_hist[-1])

        # 1. Cập nhật trạng thái lượt thi
        cur.execute("UPDATE attempts SET status='COMPLETED' WHERE attempt_id=%s", (attempt_id,))
        
        # 2. THÊM DÒNG NÀY: Lưu Theta mới vào bảng sinh viên để kế thừa cho lần sau
        cur.execute("UPDATE students SET ability=%s WHERE student_id=%s", (final_theta, student_id))
        
        conn.commit()

        with neo_driver.session() as s:
            res = s.run("""
            MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t:Topic)
            RETURN t.name AS topic, r.mastery AS mastery 
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
        
@app.get("/cat/explain/{student_id}")
def explain(student_id: int):
    with neo_driver.session() as s:
        res = s.run("""
        MATCH (s:Student {student_id:$sid})-[r:HAS_MASTERY]->(t:Topic)
        RETURN t.name AS topic, r.mastery AS mastery 
        ORDER BY mastery ASC
        """, sid=student_id)
        return [dict(r) for r in res]
    

@app.get("/students")
def get_all_students():
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Truy vấn đầy đủ các cột theo cấu trúc bảng của bạn
        cur.execute("""
            SELECT student_id, student_code, full_name, class_name, email, ability 
            FROM students 
            ORDER BY student_id ASC
        """)
        rows = cur.fetchall()
        return [{
            "student_id": r[0],
            "student_code": r[1] if r[1] else "",
            "full_name": r[2] if r[2] else "Chưa cập nhật",
            "class_name": r[3] if r[3] else "",
            "email": r[4] if r[4] else "",
            "ability": float(r[5]) if r[5] is not None else 0.0
        } for r in rows]
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/")
def root():
    return {"status": "CAT Rule-based API running (Graph Optimized)"}