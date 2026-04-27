"""
ETL Script: PostgreSQL → Neo4j Knowledge Graph

Mục tiêu:
- Đồng bộ dữ liệu từ PostgreSQL sang Neo4j
- Build Knowledge Graph đúng requirement đồ án Hybrid DB
- Sync semantic relationship cho Adaptive Learning

Date: 2026-04-27
"""

import psycopg2
from neo4j import GraphDatabase
from psycopg2.extras import RealDictCursor

# ============================================================
# CONFIG
# ============================================================

PG_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "12345678"

BATCH_SIZE = 100

# ============================================================
# POSTGRES CONNECTION
# ============================================================


def connect_postgres():
    conn = psycopg2.connect(
        cursor_factory=RealDictCursor,
        **PG_CONFIG
    )
    return conn


# ============================================================
# NEO4J CONNECTION
# ============================================================


def connect_neo4j():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASS)
    )


# ============================================================
# CREATE CONSTRAINTS
# ============================================================


def create_constraints(session):
    constraints = [
        "CREATE CONSTRAINT subject_id IF NOT EXISTS FOR (s:Subject) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT question_id IF NOT EXISTS FOR (q:Question) REQUIRE q.id IS UNIQUE",
        "CREATE CONSTRAINT question_type_id IF NOT EXISTS FOR (qt:QuestionType) REQUIRE qt.id IS UNIQUE"
    ]

    for query in constraints:
        session.run(query)


# ============================================================
# EXTRACT FROM POSTGRES
# ============================================================


def fetch_question_graph(pg_cursor):
    query = """
    SELECT
        q.question_id,
        q.content,
        q.explanation,
        q.difficulty,
        q.bloom_level,
        q.avg_time_sec,
        q.source,
        q.source_reference,
        q.is_active,

        s.subject_id,
        s.name AS subject_name,

        t.topic_id,
        t.name AS topic_name,

        qt.question_type_id,
        qt.name AS question_type_name,

        qkl.relevance_weight

    FROM questions q

    JOIN subjects s
        ON q.subject_id = s.subject_id

    JOIN question_types qt
        ON q.question_type_id = qt.question_type_id

    LEFT JOIN question_knowledge_links qkl
        ON q.question_id = qkl.question_id

    LEFT JOIN topics t
        ON qkl.topic_id = t.topic_id

    WHERE q.is_active = TRUE

    ORDER BY q.question_id
    """

    pg_cursor.execute(query)
    return pg_cursor.fetchall()


# ============================================================
# LOAD TO NEO4J
# ============================================================


def sync_record(tx, row):
    tx.run(
        """
        // ================= SUBJECT =================
        MERGE (s:Subject {id: $subject_id})
        SET s.name = $subject_name

        // ================= TOPIC =================
        FOREACH (_ IN CASE WHEN $topic_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Topic {id: $topic_id})
            SET t.name = $topic_name

            MERGE (t)-[:BELONGS_TO]->(s)
        )

        // ================= QUESTION TYPE =================
        MERGE (qt:QuestionType {id: $question_type_id})
        SET qt.name = $question_type_name

        // ================= QUESTION =================
        MERGE (q:Question {id: $question_id})
        SET
            q.content = $content,
            q.explanation = $explanation,
            q.difficulty = $difficulty,
            q.bloom_level = $bloom_level,
            q.avg_time_sec = $avg_time_sec,
            q.source = $source,
            q.source_reference = $source_reference,
            q.is_active = $is_active

        // ================= RELATIONSHIPS =================
        MERGE (q)-[:HAS_TYPE]->(qt)

        FOREACH (_ IN CASE WHEN $topic_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Topic {id: $topic_id})

            MERGE (q)-[r:RELATED_TO]->(t)
            SET r.weight = $relevance_weight
        )
        """,
        {
            "question_id": row["question_id"],
            "content": row["content"],
            "explanation": row["explanation"],
            "difficulty": float(row["difficulty"]) if row["difficulty"] else None,
            "bloom_level": int(row["bloom_level"]) if row["bloom_level"] else None,
            "avg_time_sec": int(row["avg_time_sec"]) if row["avg_time_sec"] else None,
            "source": row["source"],
            "source_reference": row["source_reference"],
            "is_active": row["is_active"],
            "subject_id": row["subject_id"],
            "subject_name": row["subject_name"],
            "topic_id": row["topic_id"],
            "topic_name": row["topic_name"],
            "question_type_id": row["question_type_id"],
            "question_type_name": row["question_type_name"],
            "relevance_weight": float(row["relevance_weight"]) if row["relevance_weight"] else 1.0
        }
    )


# ============================================================
# OPTIONAL: CLEAR GRAPH
# ============================================================


def clear_graph(session):
    session.run("MATCH (n) DETACH DELETE n")


# ============================================================
# MAIN ETL
# ============================================================


def main():
    print("=" * 60)
    print("PostgreSQL → Neo4j Knowledge Graph Sync")
    print("=" * 60)

    pg_conn = None
    neo_driver = None

    try:
        # ---------------- CONNECT ----------------
        pg_conn = connect_postgres()
        pg_cursor = pg_conn.cursor()

        neo_driver = connect_neo4j()

        print("✓ Connected PostgreSQL")
        print("✓ Connected Neo4j")

        # ---------------- FETCH DATA ----------------
        rows = fetch_question_graph(pg_cursor)

        print(f"✓ Loaded {len(rows)} records from PostgreSQL")

        # ---------------- LOAD ----------------
        with neo_driver.session() as session:
            # Optional clear graph
            # clear_graph(session)

            create_constraints(session)

            for i, row in enumerate(rows, start=1):
                session.execute_write(sync_record, row)

                if i % BATCH_SIZE == 0:
                    print(f"Processed {i}/{len(rows)} records")

        print("\n✓ Knowledge Graph sync completed")

    except Exception as e:
        print(f"✗ Sync failed: {e}")

    finally:
        if pg_conn:
            pg_conn.close()

        if neo_driver:
            neo_driver.close()

        print("✓ Connections closed")


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()




