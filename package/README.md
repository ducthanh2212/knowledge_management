# README.md

# Hybrid ETL Pipeline

Pipeline hiện tại:

```text
Excel
  ↓
etl_to_postgresql.py
  ↓
PostgreSQL
  ↓
postgres_to_neo4j.py
  ↓
Neo4j Knowledge Graph
```

Flow mới đã tách rõ:

1. ETL dữ liệu từ Excel → PostgreSQL
2. Sync dữ liệu PostgreSQL → Neo4j

---

# 1. Mục tiêu

Project này dùng mô hình Hybrid Database:

- PostgreSQL = Operational Database
- Neo4j = Knowledge Graph

Dữ liệu được ingest theo pipeline:

```text
Excel
   ↓
PostgreSQL
   ↓
Neo4j
```

---

# 2. Cấu trúc thư mục

```text
source/package/
│
├── docker-compose.yml
├── requirements.txt
├── etl_to_postgresql.py
├── postgres_to_neo4j.py
├── bootstrap_schema_postgres.py
├── test_connections.py
├── questions_week3_fixed_complete.xlsx
├── README.md
└── Câu lệnh tạo bảng SQL.sql
```

---

# 3. Requirements

## Software

- Docker Desktop
- Python 3.10+
- PostgreSQL
- Neo4j

---

# 4. Setup môi trường

## 4.1 Tạo virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 4.2 Install dependencies

```powershell
pip install -r requirements.txt
```

---

# 5. Start Databases

## 5.1 Start Docker

```powershell
docker compose up -d
```

---

## 5.2 Verify containers

```powershell
docker ps
```

Expected:

- PostgreSQL running on port 5432
- Neo4j running on port 7687

---

# 6. Database Configuration

## PostgreSQL

```text
Host: localhost
Port: 5432
Database: kbs_adaptive_exam
User: kbs_user
Password: kbs_password
```

---

## Neo4j

```text
Browser: http://localhost:7474
Bolt URI: bolt://localhost:7687
User: neo4j
Password: 12345678
```

---

# 7. Test Connection

Chạy:

```powershell
python test_connections.py
```

Expected:

```text
✓ PostgreSQL connected
✓ Neo4j connected
✓ Excel loaded
```

---

# 8. Tạo Schema PostgreSQL

Nếu database trống:

```powershell
python bootstrap_schema_postgres.py
```

Hoặc chạy SQL trực tiếp:

```powershell
docker exec -it postgres-kbs psql -U kbs_user -d kbs_adaptive_exam
```

Sau đó chạy file:

```text
Câu lệnh tạo bảng SQL.sql
```

---

# 9. ETL Excel → PostgreSQL

## Run

```powershell
python etl_to_postgresql.py
```

---

## Flow

```text
Excel
 ↓
Normalize
 ↓
Subjects
Topics
QuestionTypes
Questions
QuestionOptions
QuestionKnowledgeLinks
 ↓
PostgreSQL
```

---

## PostgreSQL Tables

Tables được insert:

- subjects
- topics
- question_types
- questions
- question_options
- question_knowledge_links

---

## Verify PostgreSQL

```sql
SELECT 'subjects' AS table_name, COUNT(*) FROM subjects
UNION ALL
SELECT 'topics', COUNT(*) FROM topics
UNION ALL
SELECT 'question_types', COUNT(*) FROM question_types
UNION ALL
SELECT 'questions', COUNT(*) FROM questions
UNION ALL
SELECT 'question_options', COUNT(*) FROM question_options
UNION ALL
SELECT 'question_knowledge_links', COUNT(*) FROM question_knowledge_links;
```

---

# 10. Sync PostgreSQL → Neo4j

## Run

```powershell
python postgres_to_neo4j.py
```

---

## Flow

```text
PostgreSQL
    ↓
Extract Tables
    ↓
Normalize Decimal/Datetime
    ↓
Neo4j MERGE
    ↓
Knowledge Graph
```

---

## Sync Order

Script sẽ sync theo thứ tự:

```text
1. Subjects
2. Topics
3. QuestionTypes
4. Questions
5. Options
6. Knowledge Links
```

---

# 11. Neo4j Graph Model

## Nodes

```text
(:Subject)
(:Topic)
(:Question)
(:Option)
(:QuestionType)
(:Difficulty)
(:BloomLevel)
```

---

## Relationships

```text
(:Topic)-[:BELONGS_TO]->(:Subject)

(:Question)-[:BELONGS_TO]->(:Subject)

(:Question)-[:HAS_OPTION]->(:Option)

(:Question)-[:HAS_TYPE]->(:QuestionType)

(:Question)-[:HAS_DIFFICULTY]->(:Difficulty)

(:Question)-[:HAS_BLOOM_LEVEL]->(:BloomLevel)

(:Question)-[:RELATED_TO]->(:Topic)

(:Question)-[:COVERS_TOPIC]->(:Topic)
```

---

# 12. Verify Neo4j

Mở:

```text
http://localhost:7474
```

Login:

```text
neo4j / 12345678
```

---

## Count Nodes

```cypher
MATCH (n)
RETURN labels(n)[0] AS NodeType, count(n) AS Count
ORDER BY NodeType;
```

---

## Count Relationships

```cypher
MATCH ()-[r]->()
RETURN type(r) AS RelationshipType, count(r) AS Count
ORDER BY RelationshipType;
```

---

## Sample Queries

### Questions of a Topic

```cypher
MATCH (q:Question)-[:RELATED_TO]->(t:Topic {name:'Functions'})
RETURN q.question_id, q.content
LIMIT 10;
```

---

### Question Difficulty

```cypher
MATCH (q:Question)-[:HAS_DIFFICULTY]->(d:Difficulty)
RETURN d.level, count(q)
ORDER BY d.level;
```

---

### Topic Coverage

```cypher
MATCH (q:Question)-[:COVERS_TOPIC]->(t:Topic)
RETURN t.name, count(q)
ORDER BY count(q) DESC;
```

---

# 13. Expected Results

## PostgreSQL

```text
subjects = 2
topics = 22
questions = 258
question_options = 1032
question_knowledge_links = 257
```

---

## Neo4j

Expected minimum:

```text
Subject nodes
Topic nodes
Question nodes
Option nodes
QuestionType nodes
Difficulty nodes
BloomLevel nodes
```

---

# 14. Reset Data

## Reset PostgreSQL

```powershell
docker compose down -v
```

---

## Reset Neo4j

Trong Neo4j Browser:

```cypher
MATCH (n)
DETACH DELETE n;
```

---

# 15. Troubleshooting

## PostgreSQL Connection Fail

Check:

```powershell
docker ps
```

---

## Neo4j Connection Fail

Check:

```powershell
docker logs neo4j-kbs --tail 100
```

---

## Decimal Error

Nếu gặp:

```text
Decimal not supported
```

Script đã có:

```python
normalize_row()
```

để auto convert.

---

# 16. Pipeline Summary

```text
Excel
 ↓
etl_to_postgresql.py
 ↓
PostgreSQL
 ↓
postgres_to_neo4j.py
 ↓
Neo4j Knowledge Graph
```

---

# 17. Architecture

```text
                ┌─────────────┐
                │ Excel Input │
                └──────┬──────┘
                       ↓
         ┌────────────────────────┐
         │ etl_to_postgresql.py   │
         └──────────┬─────────────┘
                    ↓
             ┌──────────────┐
             │ PostgreSQL   │
             └──────┬───────┘
                    ↓
         ┌────────────────────────┐
         │ postgres_to_neo4j.py   │
         └──────────┬─────────────┘
                    ↓
              ┌────────────┐
              │ Neo4j KG   │
              └────────────┘
```

