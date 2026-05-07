"""Bootstrap PostgreSQL schema for ETL.

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
DROP TABLE IF EXISTS attempt_answers CASCADE;
DROP TABLE IF EXISTS attempts CASCADE;
DROP TABLE IF EXISTS exam_questions CASCADE;
DROP TABLE IF EXISTS exams CASCADE;
DROP TABLE IF EXISTS exam_blueprint_details CASCADE;
DROP TABLE IF EXISTS exam_blueprints CASCADE;
DROP TABLE IF EXISTS question_knowledge_links CASCADE;
DROP TABLE IF EXISTS question_options CASCADE;
DROP TABLE IF EXISTS questions CASCADE;
DROP TABLE IF EXISTS question_types CASCADE;
DROP TABLE IF EXISTS student_topic_mastery CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS rule_topic_mapping CASCADE;
DROP TABLE IF EXISTS rules CASCADE;
DROP TABLE IF EXISTS llm_generation_logs CASCADE;
DROP TABLE IF EXISTS difficulty_assessments CASCADE;
DROP TABLE IF EXISTS topics CASCADE;
DROP TABLE IF EXISTS subjects CASCADE;
DROP TABLE IF EXISTS sync_metadata CASCADE;
DROP TABLE IF EXISTS sync_logs CASCADE;



-- 1. Table subjects 
CREATE TABLE IF NOT EXISTS subjects (
    subject_id  BIGSERIAL PRIMARY KEY,
    code        VARCHAR(50) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at  TIMESTAMP NULL
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
	updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at  TIMESTAMP NULL,
    UNIQUE(subject_id, code),
    UNIQUE(subject_id, name)
);


-- 3. Table question_types
CREATE TABLE IF NOT EXISTS question_types (
    question_type_id BIGSERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,
    description      TEXT,
	created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at  TIMESTAMP NULL
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
	updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at       TIMESTAMP NULL,
    UNIQUE(subject_id, content)
);


-- 5. Table question_options
CREATE TABLE IF NOT EXISTS question_options (
    option_id    BIGSERIAL PRIMARY KEY,
	question_id  BIGINT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    option_label CHAR(1) NOT NULL CHECK (option_label IN ('A','B','C','D')),
    option_text  TEXT NOT NULL,
    is_correct   BOOLEAN DEFAULT FALSE,
	created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at   TIMESTAMP NULL,
    UNIQUE(question_id, option_label)
);


-- 6. Table question_knowledge_links
CREATE TABLE IF NOT EXISTS question_knowledge_links (
    id               BIGSERIAL PRIMARY KEY,
	question_id      BIGINT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    topic_id         BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    relevance_weight NUMERIC(3,2) DEFAULT 1.0,
	created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at       TIMESTAMP NULL,
    UNIQUE(question_id, topic_id)
);


-- 7. Table students
CREATE TABLE IF NOT EXISTS students (
    student_id   BIGSERIAL PRIMARY KEY,
    student_code VARCHAR(50) NOT NULL UNIQUE,
    full_name    VARCHAR(255),
    class_name   VARCHAR(100),
    email        VARCHAR(255) UNIQUE,
    ability      FLOAT DEFAULT 0.0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at   TIMESTAMP NULL
);


-- 8. Table student_topic_mastery
CREATE TABLE IF NOT EXISTS student_topic_mastery (
    id             BIGSERIAL PRIMARY KEY,
	student_id     BIGINT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    topic_id       BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    mastery_score  NUMERIC(4,3) CHECK (mastery_score BETWEEN 0 AND 1),
    question_count INT DEFAULT 0,
    correct_count  INT DEFAULT 0,
	created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, topic_id)
);


-- 9. Table exam_blueprints
CREATE TABLE IF NOT EXISTS exam_blueprints (
    blueprint_id    BIGSERIAL PRIMARY KEY,
    subject_id      BIGINT NOT NULL REFERENCES subjects(subject_id),
    name            VARCHAR(255) NOT NULL,
    total_questions INT NOT NULL,
    target_difficulty NUMERIC(3,2),
	created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at      TIMESTAMP NULL,
    UNIQUE(subject_id, name)
);


-- 10. Table exams
CREATE TABLE IF NOT EXISTS exams (
    exam_id         BIGSERIAL PRIMARY KEY,
    student_id      BIGINT REFERENCES students(student_id),
    subject_id      BIGINT NOT NULL REFERENCES subjects(subject_id),
    blueprint_id    BIGINT,
    requested_count INT NOT NULL,
    requested_diff  NUMERIC(3,2),
	created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at      TIMESTAMP NULL
);


-- 11. Table exam_questions
CREATE TABLE IF NOT EXISTS exam_questions (
    exam_question_id BIGSERIAL PRIMARY KEY,
    exam_id          BIGINT NOT NULL REFERENCES exams(exam_id) ON DELETE CASCADE,
    question_id      BIGINT NOT NULL REFERENCES questions(question_id),
    display_order    INT NOT NULL,
	created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at       TIMESTAMP NULL,
    UNIQUE(exam_id, question_id),
    UNIQUE(exam_id, display_order)
);


-- 12. Table attempts
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id   BIGSERIAL PRIMARY KEY,
    -- For CAT flow we may start an attempt without creating an Exam first.
    exam_id      BIGINT REFERENCES exams(exam_id) ON DELETE CASCADE,
    student_id   BIGINT NOT NULL REFERENCES students(student_id),
    started_at   TIMESTAMP,
    submitted_at TIMESTAMP,
    total_score  NUMERIC(5,2),
    max_score    NUMERIC(5,2),
    feedback     TEXT,
	current_theta FLOAT,
	question_count INT DEFAULT 0,
	max_questions INT DEFAULT 10,
	subject_id BIGINT NOT NULL REFERENCES subjects(subject_id),
	theta_history FLOAT[],
	last_theta FLOAT,
	is_finished BOOLEAN DEFAULT FALSE,
	status TEXT DEFAULT 'IN_PROGRESS',
	created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at   TIMESTAMP NULL,
	-- exam_id can be NULL for CAT attempts.
    UNIQUE(exam_id, student_id)
);


-- 13. Table attempt_answers
CREATE TABLE IF NOT EXISTS attempt_answers (
    attempt_answer_id BIGSERIAL PRIMARY KEY,
	attempt_id        BIGINT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
    question_id       BIGINT NOT NULL REFERENCES questions(question_id),
    selected_option   CHAR(1),
    is_correct        BOOLEAN,
    time_spent_sec    INT,
	created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at        TIMESTAMP NULL,
    UNIQUE(attempt_id, question_id)
);


-- 14. Table exam_blueprint_details
CREATE TABLE IF NOT EXISTS exam_blueprint_details (
    id              BIGSERIAL PRIMARY KEY,
	blueprint_id    BIGINT NOT NULL REFERENCES exam_blueprints(blueprint_id) ON DELETE CASCADE,
    topic_id        BIGINT NOT NULL REFERENCES topics(topic_id),
    question_count  INT NOT NULL,
    difficulty_min  NUMERIC(3,2),
    difficulty_max  NUMERIC(3,2),
	created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at      TIMESTAMP NULL,
    UNIQUE(blueprint_id, topic_id)
);


-- 15. Table rules
CREATE TABLE IF NOT EXISTS rules (
    rule_id        BIGSERIAL PRIMARY KEY,
    rule_name      VARCHAR(255) NOT NULL UNIQUE,
    description    TEXT,
    condition_expr TEXT NOT NULL,
    action_expr    TEXT NOT NULL,
    priority       INT DEFAULT 1,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at     TIMESTAMP NULL
);


-- 16. Table rule_topic_mapping
CREATE TABLE IF NOT EXISTS rule_topic_mapping (
    id            BIGSERIAL PRIMARY KEY,
    rule_id       BIGINT NOT NULL REFERENCES rules(rule_id) ON DELETE CASCADE,
    topic_id      BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
	created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at    TIMESTAMP NULL,
    UNIQUE(rule_id, topic_id)
);


-- 17. Table llm_generation_logs
CREATE TABLE IF NOT EXISTS llm_generation_logs (
    log_id               BIGSERIAL PRIMARY KEY,
    topic_id             BIGINT REFERENCES topics(topic_id),
    prompt_text          TEXT,
    raw_response         TEXT,
    parsed_json          JSONB,
    created_question_id  BIGINT REFERENCES questions(question_id),
    status               VARCHAR(30),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at           TIMESTAMP NULL
);


-- 18. Table difficulty_assessments
CREATE TABLE IF NOT EXISTS difficulty_assessments (
    assessment_id BIGSERIAL PRIMARY KEY,
    question_id   BIGINT NOT NULL REFERENCES questions(question_id) ON DELETE CASCADE,
    assessed_by   VARCHAR(50),
    difficulty    NUMERIC(3,2) CHECK (difficulty BETWEEN 0 AND 1),
    confidence    NUMERIC(3,2),
    note          TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at    TIMESTAMP NULL,
    UNIQUE(question_id, created_at, assessed_by)
);


-- 19. Table sync_metadata
CREATE TABLE IF NOT EXISTS sync_metadata (
	sync_name   TEXT PRIMARY KEY,
	last_sync   TIMESTAMP,
	created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at  TIMESTAMP NULL
);


-- 20. Table sync_logs
CREATE TABLE IF NOT EXISTS sync_logs (
	id SERIAL     PRIMARY KEY,
	sync_name     TEXT,
	table_name    TEXT,
	synced_rows   INTEGER,
	status        TEXT,
	started_at    TIMESTAMP,
	completed_at  TIMESTAMP,
	error_message TEXT,
	created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	deleted_at    TIMESTAMP NULL
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
