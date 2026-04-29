import psycopg2
from psycopg2.extras import RealDictCursor
from neo4j import GraphDatabase
from decimal import Decimal
from datetime import datetime, date
import logging
import json
import os
import time

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
NEO4J_PASSWORD = "12345678"

BATCH_SIZE = 500
MAX_RETRIES = 3
GRAPH_VERSION = "v4.0"

CHECKPOINT_FILE = "sync_checkpoints.json"
DEAD_LETTER_FILE = "dead_letter_batches.jsonl"

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


# ============================================================
# CONNECTIONS
# ============================================================


def get_pg_connection():
    return psycopg2.connect(
        cursor_factory=RealDictCursor,
        **PG_CONFIG
    )


def get_neo_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


# ============================================================
# NORMALIZE
# ============================================================


def normalize_row(row):
    normalized = {}

    for k, v in row.items():

        if isinstance(v, Decimal):
            normalized[k] = float(v)

        elif isinstance(v, (datetime, date)):
            normalized[k] = v.isoformat()

        else:
            normalized[k] = v

    return normalized


# ============================================================
# CHECKPOINTS
# ============================================================


def load_checkpoints():
    if not os.path.exists(CHECKPOINT_FILE):
        return {}

    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_checkpoints(checkpoints):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoints, f, indent=2)


def get_checkpoint(table_name):
    checkpoints = load_checkpoints()

    return checkpoints.get(
        table_name,
        "2000-01-01T00:00:00"
    )


def update_checkpoint(table_name, latest_timestamp):
    checkpoints = load_checkpoints()

    checkpoints[table_name] = latest_timestamp

    save_checkpoints(checkpoints)


# ============================================================
# DEAD LETTER
# ============================================================


def log_dead_letter(table_name, batch, error):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "table": table_name,
        "error": str(error),
        "rows": batch
    }

    with open(DEAD_LETTER_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


# ============================================================
# CONSTRAINTS
# ============================================================


def create_constraints(session):
    constraints = [
        "CREATE CONSTRAINT subject_unique IF NOT EXISTS FOR (n:Subject) REQUIRE n.subject_id IS UNIQUE",
        "CREATE CONSTRAINT topic_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
        "CREATE CONSTRAINT question_unique IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE",
        "CREATE CONSTRAINT option_unique IF NOT EXISTS FOR (n:Option) REQUIRE n.option_id IS UNIQUE",
        "CREATE CONSTRAINT question_type_unique IF NOT EXISTS FOR (n:QuestionType) REQUIRE n.question_type_id IS UNIQUE"
    ]

    for query in constraints:
        session.run(query)


# ============================================================
# INCREMENTAL FETCH
# ============================================================


def fetch_incremental(cursor, pg_conn, table_name):
    checkpoint = get_checkpoint(table_name)

    query = f"""
        SELECT *
        FROM {table_name}
        WHERE GREATEST(
            COALESCE(created_at, '2000-01-01'),
            COALESCE(updated_at, '2000-01-01'),
            COALESCE(deleted_at, '2000-01-01')
        ) >= %s
        ORDER BY GREATEST(
            COALESCE(created_at, '2000-01-01'),
            COALESCE(updated_at, '2000-01-01'),
            COALESCE(deleted_at, '2000-01-01')
        ) ASC
    """

    try:

        cursor.execute(query, (checkpoint,))
        rows = cursor.fetchall()

    except Exception as e:

        logging.warning(
            f"Incremental unavailable for {table_name}: {e}"
        )

        pg_conn.rollback()

        cursor = pg_conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(f"SELECT * FROM {table_name}")

        rows = cursor.fetchall()

    normalized_rows = [normalize_row(r) for r in rows]

    latest_timestamp = checkpoint

    if rows:

        latest_values = []

        for row in rows:

            timestamps = []

            for col in ["created_at", "updated_at", "deleted_at"]:

                value = row.get(col)

                if value:
                    timestamps.append(value)

            if timestamps:
                latest_values.append(max(timestamps))

        if latest_values:
            latest_timestamp = max(latest_values).isoformat()

    return normalized_rows, latest_timestamp


# ============================================================
# RETRY
# ============================================================


def execute_with_retry(session, query, rows, table_name):
    for attempt in range(MAX_RETRIES):

        try:

            session.execute_write(
                lambda tx: tx.run(
                    query,
                    rows=rows,
                    graph_version=GRAPH_VERSION
                )
            )

            return True

        except Exception as e:

            logging.warning(
                f"Retry {attempt + 1}/{MAX_RETRIES} → {table_name}: {e}"
            )

            if attempt == MAX_RETRIES - 1:
                log_dead_letter(
                    table_name,
                    rows,
                    e
                )

                return False

            time.sleep(2)


# ============================================================
# BATCH
# ============================================================


def chunk_rows(rows, batch_size):
    for i in range(0, len(rows), batch_size):
        yield rows[i:i + batch_size]


# ============================================================
# CYPHER
# ============================================================

SUBJECT_QUERY = """
UNWIND $rows AS row
MERGE (s:Subject {subject_id: row.subject_id})
SET
    s.code = row.code,
    s.name = row.name,
    s.description = row.description,
    s.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    s.created_at = row.created_at,
    s.updated_at = row.updated_at,
    s.deleted_at = row.deleted_at,
    s.graph_version = $graph_version
"""

TOPIC_QUERY = """
UNWIND $rows AS row
MATCH (s:Subject {subject_id: row.subject_id})
MERGE (t:Topic {topic_id: row.topic_id})
SET
    t.code = row.code,
    t.name = row.name,
    t.description = row.description,
    t.bloom_level = row.bloom_level,
    t.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    t.created_at = row.created_at,
    t.updated_at = row.updated_at,
    t.deleted_at = row.deleted_at,
    t.graph_version = $graph_version
MERGE (t)-[:BELONGS_TO]->(s)
"""

QUESTION_TYPE_QUERY = """
UNWIND $rows AS row
MERGE (qt:QuestionType {question_type_id: row.question_type_id})
SET
    qt.name = row.name,
    qt.description = row.description,
    qt.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    qt.created_at = row.created_at,
    qt.updated_at = row.updated_at,
    qt.deleted_at = row.deleted_at,
    qt.graph_version = $graph_version
"""

QUESTION_QUERY = """
UNWIND $rows AS row
MATCH (s:Subject {subject_id: row.subject_id})
MERGE (q:Question {question_id: row.question_id})
SET
    q.content = row.content,
    q.explanation = row.explanation,
    q.difficulty = row.difficulty,
    q.avg_time_sec = row.avg_time_sec,
    q.bloom_level = row.bloom_level,
    q.discrimination_index = row.discrimination_index,
    q.difficulty_stddev = row.difficulty_stddev,
    q.source = row.source,
    q.source_reference = row.source_reference,
    q.is_active = row.is_active,
    q.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    q.created_at = row.created_at,
    q.updated_at = row.updated_at,
    q.deleted_at = row.deleted_at,
    q.graph_version = $graph_version
MERGE (q)-[:BELONGS_TO]->(s)
WITH q, row
FOREACH (_ IN CASE WHEN row.topic_id IS NOT NULL THEN [1] ELSE [] END |
    MERGE (t:Topic {topic_id: row.topic_id})
    MERGE (q)-[:PRIMARY_TOPIC]->(t)
)
FOREACH (_ IN CASE WHEN row.question_type_id IS NOT NULL THEN [1] ELSE [] END |
    MERGE (qt:QuestionType {question_type_id: row.question_type_id})
    MERGE (q)-[:HAS_TYPE]->(qt)
)
"""

OPTION_QUERY = """
UNWIND $rows AS row
MATCH (q:Question {question_id: row.question_id})
MERGE (o:Option {option_id: row.option_id})
SET
    o.option_label = row.option_label,
    o.option_text = row.option_text,
    o.is_correct = row.is_correct,
    o.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    o.created_at = row.created_at,
    o.updated_at = row.updated_at,
    o.deleted_at = row.deleted_at,
    o.graph_version = $graph_version
MERGE (q)-[:HAS_OPTION]->(o)
"""

KNOWLEDGE_QUERY = """
UNWIND $rows AS row
MATCH (q:Question {question_id: row.question_id})
MATCH (t:Topic {topic_id: row.topic_id})
MERGE (q)-[r:RELATED_TO]->(t)
SET
    r.relevance_weight = row.relevance_weight,
    r.deleted = CASE WHEN row.deleted_at IS NOT NULL THEN true ELSE false END,
    r.created_at = row.created_at,
    r.updated_at = row.updated_at,
    r.deleted_at = row.deleted_at,
    r.graph_version = $graph_version
"""


# ============================================================
# MAIN
# ============================================================


def main():
    pg_conn = None
    neo_driver = None

    try:

        global_start = time.time()

        pg_conn = get_pg_connection()
        cursor = pg_conn.cursor(cursor_factory=RealDictCursor)

        neo_driver = get_neo_driver()

        logging.info("Connected PostgreSQL")
        logging.info("Connected Neo4j")

        datasets = [
            ("subjects", SUBJECT_QUERY),
            ("topics", TOPIC_QUERY),
            ("question_types", QUESTION_TYPE_QUERY),
            ("questions", QUESTION_QUERY),
            ("question_options", OPTION_QUERY),
            ("question_knowledge_links", KNOWLEDGE_QUERY)
        ]

        with neo_driver.session() as session:

            create_constraints(session)

            for table_name, query in datasets:

                logging.info(f"Sync → {table_name}")

                rows, latest_timestamp = fetch_incremental(
                    cursor,
                    pg_conn,
                    table_name
                )

                logging.info(f"Rows loaded: {len(rows)}")

                table_start = time.time()

                total_synced = 0

                for batch_idx, batch in enumerate(chunk_rows(rows, BATCH_SIZE), start=1):

                    batch_start = time.time()

                    success = execute_with_retry(
                        session,
                        query,
                        batch,
                        table_name
                    )

                    batch_duration = round(time.time() - batch_start, 2)

                    if success:
                        total_synced += len(batch)

                        logging.info(
                            f"{table_name} batch={batch_idx} rows={len(batch)} duration={batch_duration}s"
                        )

                update_checkpoint(
                    table_name,
                    latest_timestamp
                )

                table_duration = round(time.time() - table_start, 2)

                logging.info(
                    f"{table_name} synced={total_synced} duration={table_duration}s"
                )

        total_duration = round(time.time() - global_start, 2)

        logging.info(
            f"Graph sync completed in {total_duration}s"
        )

    except Exception as e:

        logging.error(f"Sync failed: {e}")

    finally:

        if pg_conn:
            pg_conn.close()

        if neo_driver:
            neo_driver.close()

        logging.info("Connections closed")


if __name__ == "__main__":
    main()
