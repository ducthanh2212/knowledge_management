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
-- 1. Table subjects 
CREATE TABLE IF NOT EXISTS subjects (
    subject_id  BIGSERIAL PRIMARY KEY,
    code        VARCHAR(50) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- 2. Table topics 
CREATE TABLE IF NOT EXISTS topics (
    topic_id    BIGSERIAL PRIMARY KEY,
    subject_id  BIGINT NOT NULL REFERENCES subjects(subject_id) ON DELETE CASCADE,
    code        VARCHAR(50) NOT NULL,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    bloom_level VARCHAR(30),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subject_id, code),
    UNIQUE(subject_id, name)
);


-- 3. Table question_types
CREATE TABLE IF NOT EXISTS question_types (
    question_type_id BIGSERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,
    description      TEXT
);


-- 4. Table questions
CREATE TABLE IF NOT EXISTS questions (
    question_id      BIGSERIAL PRIMARY KEY,
    subject_id       BIGINT NOT NULL REFERENCES subjects(subject_id),
    topic_id         BIGINT REFERENCES topics(topic_id),
    question_type_id BIGINT REFERENCES question_types(question_type_id),
    content          TEXT NOT NULL,
    explanation      TEXT,
    difficulty       NUMERIC(3,2) CHECK (difficulty BETWEEN 0 AND 1),
    avg_time_sec     INT CHECK (avg_time_sec >= 0),
    bloom_level      VARCHAR(30),
    discrimination_index NUMERIC(3,2),
    difficulty_stddev NUMERIC(3,2),
    source           VARCHAR(50),
    source_reference  VARCHAR(200),
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subject_id, content)
);


-- 5. Table question_options
CREATE TABLE IF NOT EXISTS question_options (
    option_id    BIGSERIAL PRIMARY KEY,
	question_id  BIGINT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    option_label CHAR(1) NOT NULL CHECK (option_label IN ('A','B','C','D')),
    option_text  TEXT NOT NULL,
    is_correct   BOOLEAN DEFAULT FALSE,
    UNIQUE(question_id, option_label)
);


-- 6. Table question_knowledge_links
CREATE TABLE IF NOT EXISTS question_knowledge_links (
    id               BIGSERIAL PRIMARY KEY,
	question_id      BIGINT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    topic_id         BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    relevance_weight NUMERIC(3,2) DEFAULT 1.0,
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
