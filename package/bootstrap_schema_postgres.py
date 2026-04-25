"""Bootstrap minimal PostgreSQL schema for ETL.

Creates the minimum set of tables required by `etl_to_postgresql.py`:
- subjects
- topics
- question_types
- questions
- question_options
- question_knowledge_links

Safe to run multiple times.
"""

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password",
}

DDL = """
CREATE TABLE IF NOT EXISTS subjects (
    subject_id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    topic_id SERIAL PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(subject_id),
    code VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    UNIQUE(subject_id, code)
);

CREATE TABLE IF NOT EXISTS question_types (
    question_type_id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS questions (
    question_id SERIAL PRIMARY KEY,
    subject_id INTEGER REFERENCES subjects(subject_id),
    topic_id INTEGER REFERENCES topics(topic_id),
    question_type_id INTEGER REFERENCES question_types(question_type_id),
    content TEXT NOT NULL,
    explanation TEXT,
    difficulty DECIMAL(3,2) CHECK (difficulty BETWEEN 0 AND 1),
    bloom_level INTEGER CHECK (bloom_level BETWEEN 1 AND 6),
    avg_time_sec INTEGER,
    source_type VARCHAR(50),
    source_reference TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS question_options (
    option_id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(question_id) ON DELETE CASCADE,
    option_label VARCHAR(1) NOT NULL,
    option_text TEXT NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE,
    UNIQUE(question_id, option_label)
);

CREATE TABLE IF NOT EXISTS question_knowledge_links (
    link_id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(question_id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(topic_id),
    relevance_weight DECIMAL(3,2) DEFAULT 1.0,
    UNIQUE(question_id, topic_id)
);
"""


def main() -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(DDL)
        print("✓ PostgreSQL minimal schema is ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
