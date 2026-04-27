import psycopg2
from psycopg2.extras import RealDictCursor
from neo4j import GraphDatabase
from collections import defaultdict

# ============================================================
# CONFIGURATION
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

BATCH_SIZE = 200

# ============================================================
# CONNECTIONS
# ============================================================


def get_postgres_connection():
    return psycopg2.connect(
        cursor_factory=RealDictCursor,
        **PG_CONFIG
    )



def get_neo4j_driver():
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


# ============================================================
# NEO4J CONSTRAINTS
# ============================================================


def create_constraints(session):
    constraints = [
        "CREATE CONSTRAINT subject_unique IF NOT EXISTS FOR (n:Subject) REQUIRE n.subject_id IS UNIQUE",
        "CREATE CONSTRAINT topic_unique IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
        "CREATE CONSTRAINT question_unique IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE",
        "CREATE CONSTRAINT option_unique IF NOT EXISTS FOR (n:Option) REQUIRE n.option_id IS UNIQUE",
        "CREATE CONSTRAINT difficulty_unique IF NOT EXISTS FOR (n:Difficulty) REQUIRE n.level IS UNIQUE",
        "CREATE CONSTRAINT bloom_unique IF NOT EXISTS FOR (n:BloomLevel) REQUIRE n.level IS UNIQUE",
        "CREATE CONSTRAINT type_unique IF NOT EXISTS FOR (n:QuestionType) REQUIRE n.question_type_id IS UNIQUE"
    ]

    for query in constraints:
        session.run(query)


# ============================================================
# DATA EXTRACTION
# ============================================================


def fetch_subjects(cursor):
    cursor.execute("""
        SELECT
            subject_id,
            code,
            name,
            description,
            created_at
        FROM subjects
    """)
    return cursor.fetchall()



def fetch_topics(cursor):
    cursor.execute("""
        SELECT
            topic_id,
            subject_id,
            code,
            name,
            description,
            bloom_level,
            created_at
        FROM topics
    """)
    return cursor.fetchall()



def fetch_questions(cursor):
    cursor.execute("""
        SELECT
            question_id,
            subject_id,
            topic_id,
            question_type_id,
            content,
            explanation,
            difficulty,
            avg_time_sec,
            bloom_level,
            discrimination_index,
            difficulty_stddev,
            source,
            source_reference,
            is_active,
            created_at
        FROM questions
    """)
    return cursor.fetchall()



def fetch_question_types(cursor):
    cursor.execute("""
        SELECT
            question_type_id,
            name,
            description
        FROM question_types
    """)
    return cursor.fetchall()


def sync_question_type(tx, row):
    tx.run(
        """
        MERGE (qt:QuestionType {question_type_id: $question_type_id})
        SET
            qt.name = $name,
            qt.description = $description
        """,
        row
    )



def fetch_options(cursor):
    cursor.execute("""
        SELECT
            option_id,
            question_id,
            option_label,
            option_text,
            is_correct
        FROM question_options
    """)
    return cursor.fetchall()



def fetch_knowledge_links(cursor):
    cursor.execute("""
        SELECT
            id,
            question_id,
            topic_id,
            relevance_weight
        FROM question_knowledge_links
    """)
    return cursor.fetchall()


# ============================================================
# SYNC SUBJECTS
# ============================================================


def sync_subject(tx, row):
    tx.run(
        """
        MERGE (s:Subject {subject_id: $subject_id})
        SET
            s.code = $code,
            s.name = $name,
            s.description = $description,
            s.created_at = $created_at
        """,
        row
    )


# ============================================================
# SYNC TOPICS
# ============================================================


def sync_topic(tx, row):
    tx.run(
        """
        MERGE (t:Topic {topic_id: $topic_id})
        SET
            t.code = $code,
            t.name = $name,
            t.description = $description,
            t.bloom_level = $bloom_level,
            t.created_at = $created_at

        WITH t

        MATCH (s:Subject {subject_id: $subject_id})

        MERGE (t)-[r:BELONGS_TO]->(s)
        SET
            r.created_at = datetime()
        """,
        row
    )


# ============================================================
# SYNC QUESTIONS
# ============================================================


def sync_question(tx, row):
    tx.run(
        """
        MERGE (q:Question {question_id: $question_id})
        SET
            q.content = $content,
            q.explanation = $explanation,
            q.difficulty = $difficulty,
            q.avg_time_sec = $avg_time_sec,
            q.bloom_level = $bloom_level,
            q.discrimination_index = $discrimination_index,
            q.difficulty_stddev = $difficulty_stddev,
            q.source = $source,
            q.source_reference = $source_reference,
            q.is_active = $is_active,
            q.created_at = $created_at

        WITH q

        MERGE (d:Difficulty {level: $difficulty})
        SET d.label = 'Difficulty ' + toString($difficulty)

        WITH q, d

        MERGE (b:BloomLevel {level: $bloom_level})
        SET b.label = 'Bloom Level ' + toString($bloom_level)

        WITH q, d, b

        MERGE (qt:QuestionType {question_type_id: $question_type_id})

        WITH q, d, b, qt

        MERGE (q)-[r1:HAS_DIFFICULTY]->(d)
        SET r1.created_at = datetime()

        MERGE (q)-[r2:HAS_BLOOM_LEVEL]->(b)
        SET r2.created_at = datetime()

        MERGE (q)-[r3:HAS_TYPE]->(qt)
        SET r3.created_at = datetime()

        WITH q

        MATCH (s:Subject {subject_id: $subject_id})

        MERGE (q)-[r4:BELONGS_TO]->(s)
        SET r4.created_at = datetime()

        WITH q

        FOREACH (_ IN CASE WHEN $topic_id IS NOT NULL THEN [1] ELSE [] END |
            MERGE (t:Topic {topic_id: $topic_id})
            MERGE (q)-[r5:COVERS_TOPIC]->(t)
            SET r5.created_at = datetime()
        )
        """,
        row
    )


# ============================================================
# SYNC OPTIONS
# ============================================================


def sync_option(tx, row):
    tx.run(
        """
        MERGE (o:Option {option_id: $option_id})
        SET
            o.option_label = $option_label,
            o.option_text = $option_text,
            o.is_correct = $is_correct

        WITH o

        MATCH (q:Question {question_id: $question_id})

        MERGE (q)-[r:HAS_OPTION]->(o)
        SET
            r.is_correct = $is_correct,
            r.created_at = datetime()
        """,
        row
    )


# ============================================================
# SYNC KNOWLEDGE LINKS
# ============================================================


def sync_knowledge_link(tx, row):
    tx.run(
        """
        MATCH (q:Question {question_id: $question_id})
        MATCH (t:Topic {topic_id: $topic_id})

        MERGE (q)-[r:RELATED_TO]->(t)
        SET
            r.weight = $relevance_weight,
            r.semantic_type = 'knowledge_link',
            r.created_at = datetime()

        MERGE (q)-[r2:COVERS_TOPIC]->(t)
        SET
            r2.created_at = datetime()
        """,
        row
    )


# ============================================================
# NORMALIZE POSTGRES TYPES
# ============================================================

from decimal import Decimal
from datetime import datetime, date


def normalize_row(row):
    """
    Convert PostgreSQL data types to Neo4j-compatible values.
    """
    normalized = {}

    for key, value in row.items():
        if isinstance(value, Decimal):
            normalized[key] = float(value)
        elif isinstance(value, (datetime, date)):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value

    return normalized


# ============================================================
# MAIN
# ============================================================


def main():
    print("=" * 70)
    print("PostgreSQL → Neo4j Graph Sync")
    print("=" * 70)

    pg_conn = None
    neo_driver = None

    try:
        pg_conn = get_postgres_connection()
        cursor = pg_conn.cursor()

        neo_driver = get_neo4j_driver()

        print("✓ Connected PostgreSQL")
        print("✓ Connected Neo4j")

        subjects = fetch_subjects(cursor)
        topics = fetch_topics(cursor)
        question_types = fetch_question_types(cursor)
        questions = fetch_questions(cursor)
        options = fetch_options(cursor)
        links = fetch_knowledge_links(cursor)

        print(f"Subjects: {len(subjects)}")
        print(f"Topics: {len(topics)}")
        print(f"Question Types: {len(question_types)}")
        print(f"Questions: {len(questions)}")
        print(f"Options: {len(options)}")
        print(f"Knowledge Links: {len(links)}")

        with neo_driver.session() as session:

            create_constraints(session)

            print("\nSyncing Subjects...")
            for row in subjects:
                session.execute_write(sync_subject, normalize_row(row))

            print("Syncing Topics...")
            for row in topics:
                session.execute_write(sync_topic, normalize_row(row))

            print("Syncing Question Types...")
            for row in question_types:
                session.execute_write(sync_question_type, normalize_row(row))

            print("Syncing Questions...")
            for row in questions:
                session.execute_write(sync_question, normalize_row(row))

            print("Syncing Options...")
            for row in options:
                session.execute_write(sync_option, normalize_row(row))

            print("Syncing Knowledge Links...")
            for row in links:
                session.execute_write(sync_knowledge_link, normalize_row(row))

        print("\n✓ Graph Sync Completed")

    except Exception as e:
        print(f"\n✗ Error: {e}")

    finally:
        if pg_conn:
            pg_conn.close()

        if neo_driver:
            neo_driver.close()

        print("✓ Connections Closed")


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()
