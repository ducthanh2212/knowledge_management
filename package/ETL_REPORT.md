# ETL EXECUTION REPORT

**Date:** 2026-04-25  
**Executed by:** Thành (Member 1)  
**Duration:** (not recorded)

## Summary
- Source: `questions_week3_fixed_complete.xlsx` (258 rows)
- Cleaned: 258 rows (removed 0 with missing options)
- Target: PostgreSQL (5 tables) + Neo4j (knowledge graph)

## Connection Info Used
### PostgreSQL (Docker: `postgres-kbs`)
- Host: `localhost`
- Port: `5432`
- Database: `kbs_adaptive_exam`
- Username: `kbs_user`
- Password: `kbs_password`

### Neo4j (Docker: `neo4j-kbs`)
- Browser: http://localhost:7474
- Bolt URI: `bolt://localhost:7687`
- Username: `neo4j`
- Password: `12345678`

## PostgreSQL Results (verified)
Counts after running `etl_to_postgresql.py`:
- subjects: 2
- topics: 22
- questions: 258
- question_options: 1032
- question_knowledge_links: 258

## Neo4j Results (verified)
### Nodes
- Subject: 2
- Topic: 195 *(includes 22 main topics + auto-created tag topics from `related_topics` / `prerequisites`)*
- Question: 258
- Skill: 6

### Relationships
- HAS_TOPIC: 22
- BELONGS_TO: 258
- TESTS: 258
- COVERS: 722
- PREREQUISITE_OF: 118

## Issues Encountered
1) **PostgreSQL schema missing** (no tables existed).
- Fix: created minimal schema using `source/ne4j_setup/files/bootstrap_schema_postgres.py`, then reran ETL.

2) **Neo4j `COVERS` and `PREREQUISITE_OF` initially = 0**.
- Root cause: Excel fields `related_topics` / `prerequisites` contain tag keywords (e.g., `arrays`, `binary_search`) that weren’t part of the 22 curriculum `Topic` nodes, so relationships couldn’t be created.
- Fix: updated `etl_to_neo4j.py` to auto-create tag `Topic` nodes (`is_tag = true`) before creating edges.

## Data Quality Notes (Excel)
- Shape: 258 rows × 19 columns
- `id`: no duplicates
- `difficulty`: 0.1 → 0.9
- `bloom_level`: 1 → 6 (level 1 dominates)
- `related_topics`: non-empty for 258/258 rows (comma-separated)
- `prerequisites`: non-empty for 258/258 rows (comma-separated)

## Next Steps
- Hand over `ETL_REPORT.md` + connection info to Member 2 for backend integration.
- Confirm backend can query:
  - PostgreSQL questions/options
  - Neo4j graph traversal for adaptive logic

## Phase 9 Verification (Executed)

### PostgreSQL (sample queries)
- Query 1 (Python difficulty 0.4–0.7): returned 10 rows ✅
- Query 2 (Bloom distribution):
  - Level 1: 160
  - Level 2: 37
  - Level 3: 36
  - Level 4: 6
  - Level 5: 10
  - Level 6: 9 ✅
- Query 3 (options for `question_id = 1`): returned 4 options (A–D) with exactly 1 correct ✅

### Neo4j (sample queries)
- Topics of Python: returned 16 topics (main curriculum topics) ✅
- Remember questions about Functions: returned rows ✅
- Prerequisites of OOP: returned rows ✅
- Count questions by skill: matches PostgreSQL Bloom distribution ✅

### PG ↔ Neo4j consistency
- Subjects: PG 2 = Neo4j 2 ✅
- Topics (main topics): PG 22 = Neo4j 22 ✅
- Questions: PG 258 = Neo4j 258 ✅

## Backups (Optional)

### PostgreSQL
- Created SQL dump: `backup_postgres_kbs_adaptive_exam.sql`

### Neo4j
- APOC export not available (no `apoc.*` procedures registered), despite `NEO4J_PLUGINS=[apoc]`.
- Created fallback dump (JSONL): `backup_neo4j_dump.jsonl`

