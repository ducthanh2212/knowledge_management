# Hướng dẫn chạy ETL (Excel → PostgreSQL + Neo4j)

Thư mục này (`source/package/`) là **gói handoff** để người khác có thể chạy lại toàn bộ ETL + verify theo checklist.

## 0) Checklist nhanh (bạn sẽ làm đúng theo thứ tự này)

- [ ] Cài Docker Desktop và đảm bảo Docker đang chạy
- [ ] Tạo Python virtual environment + cài dependencies
- [ ] Start database containers (PostgreSQL + Neo4j)
- [ ] Test kết nối (`test_connections.py`)
- [ ] Tạo schema PostgreSQL (nếu DB trống) (`bootstrap_schema_postgres.py`)
- [ ] Chạy ETL PostgreSQL (`etl_to_postgresql.py`)
- [ ] Chạy ETL Neo4j (`etl_to_neo4j.py`)
- [ ] Verify kết quả bằng SQL/Cypher queries

---

## 1) Yêu cầu môi trường

### Phần mềm cần có

- **Docker Desktop** (Windows/Mac/Linux)
- **Python 3.10+** (khuyến nghị 3.11/3.12)

### File trong gói này

- `docker-compose.yml` – dựng PostgreSQL + Neo4j
- `requirements.txt` – dependencies Python cho ETL
- `questions_week3_fixed_complete.xlsx` – input Excel (258 câu)
- `test_connections.py` – test kết nối + đọc Excel
- `bootstrap_schema_postgres.py` – tạo schema tối thiểu PostgreSQL
- `etl_to_postgresql.py` – ETL Excel → PostgreSQL
- `etl_to_neo4j.py` – ETL Excel → Neo4j
- `ETL_REPORT.md` – báo cáo chạy ETL (tham khảo)

---

## 2) Cách chạy chi tiết (Windows PowerShell)

> Nếu bạn dùng macOS/Linux, thay PowerShell bằng terminal tương đương. Các lệnh `docker compose` giống nhau.

### 2.1. Mở terminal tại đúng thư mục

Mở PowerShell và cd vào thư mục `source/package`.

Ví dụ (đổi thành đường dẫn repo của bạn):

```powershell
cd "D:\master's degree\knowledge_management\term\source\package"
```

### 2.2. Tạo và kích hoạt virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Cài dependencies:

```powershell
pip install -r requirements.txt
```

> Nếu gặp lỗi quyền chạy script khi Activate, chạy PowerShell với quyền admin hoặc dùng:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## 3) Start databases bằng Docker Compose

### 3.1. Khởi động containers

```powershell
docker compose up -d
```

### 3.2. Kiểm tra containers

```powershell
docker ps
```

Kỳ vọng:

- PostgreSQL mở port `5432`
- Neo4j mở port `7474` (Browser) và `7687` (Bolt)

### 3.3. Thông tin kết nối (mặc định trong bộ này)

- **PostgreSQL**
  - Host: `localhost`
  - Port: `5432`
  - Database: `kbs_adaptive_exam`
  - User: `kbs_user`
  - Password: `kbs_password`

- **Neo4j**
  - Browser: http://localhost:7474
  - Bolt URI: `bolt://localhost:7687`
  - User: `neo4j`
  - Password: `12345678`

> Nếu bạn thay đổi password/port trong `docker-compose.yml`, hãy sửa tương ứng trong các file `.py`.

---

## 4) Test kết nối (bắt buộc chạy trước ETL)

Trong venv (`.venv` đã activate), chạy:

```powershell
python test_connections.py
```

Expected: PASS cả 3

- PostgreSQL connected successfully
- Neo4j connected successfully
- Excel file loaded successfully

Nếu fail:

- Postgres fail: kiểm tra container `postgres-kbs` có chạy không, user/db/pass đúng chưa.
- Neo4j fail: kiểm tra `neo4j-kbs` có chạy không, login Browser được không.
- Excel fail: đảm bảo file `questions_week3_fixed_complete.xlsx` nằm cùng folder.

---

## 5) Tạo schema PostgreSQL (chỉ cần nếu DB trống / chưa có bảng)

Chạy:

```powershell
python bootstrap_schema_postgres.py
```

Sau đó có thể xác nhận nhanh bảng bằng `psql`:

```powershell
docker exec -it postgres-kbs psql -U kbs_user -d kbs_adaptive_exam
```
Trong `psql` chạy:

```sql
\dt
```

---

## 6) Chạy ETL PostgreSQL

```powershell
python etl_to_postgresql.py
```

Kỳ vọng:

- Subjects: 2
- Topics: 22
- Questions: 258
- Options: 1032

### Verify nhanh trong PostgreSQL

Vào `psql`:

```powershell
docker exec -it postgres-kbs psql -U kbs_user -d kbs_adaptive_exam
```

Chạy (nhớ kết thúc bằng dấu `;`):

```sql
SELECT 'subjects' as table_name, COUNT(*) as count FROM subjects
UNION ALL SELECT 'topics', COUNT(*) FROM topics
UNION ALL SELECT 'question_types', COUNT(*) FROM question_types
UNION ALL SELECT 'questions', COUNT(*) FROM questions
UNION ALL SELECT 'question_options', COUNT(*) FROM question_options
UNION ALL SELECT 'question_knowledge_links', COUNT(*) FROM question_knowledge_links;
```

Spot-check:

```sql
SELECT question_id, subject_id, topic_id, difficulty, bloom_level
FROM questions
ORDER BY question_id
LIMIT 5;

SELECT option_id, question_id, option_label, is_correct
FROM question_options
WHERE question_id = 1
ORDER BY option_label;
```

> Lưu ý: Nếu prompt `psql` đang là `kbs_adaptive_exam-#` nghĩa là bạn đang kẹt lệnh chưa kết thúc. Bấm `Ctrl+C` để hủy rồi chạy lại.

---

## 7) Chạy ETL Neo4j

```powershell
python etl_to_neo4j.py
```

### Verify nhanh trong Neo4j Browser

Mở browser: http://localhost:7474

Đăng nhập:
- user: `neo4j`
- pass: `12345678`

Chạy query đếm nodes:

```cypher
MATCH (n)
RETURN labels(n)[0] as NodeType, count(n) as Count
ORDER BY NodeType;
```

Kỳ vọng tối thiểu:
- `Subject` = 2
- `Question` = 258
- `Skill` = 6
- `Topic`:
  - **>= 22** (trong bộ ETL này có thể có thêm `Topic` dạng tag từ cột related/prerequisite)

Đếm quan hệ:

```cypher
MATCH ()-[r]->()
RETURN type(r) as RelType, count(r) as Count
ORDER BY RelType;
```

Query kiểm tra theo checklist:

```cypher
// 1) All topics of Python
MATCH (s:Subject {name: 'Python'})-[:HAS_TOPIC]->(t:Topic)
RETURN t.name
ORDER BY t.name;

// 2) Remember questions for Functions
MATCH (q:Question)-[:BELONGS_TO]->(t:Topic {name: 'Functions'})
MATCH (q)-[:TESTS]->(sk:Skill {name: 'Remember'})
RETURN q.id, q.content, q.difficulty
LIMIT 5;

// 3) prerequisites of OOP
MATCH (t_pre:Topic)-[:PREREQUISITE_OF]->(t:Topic {name: 'OOP'})
RETURN t_pre.name;

// 4) counts by skill level
MATCH (q:Question)-[:TESTS]->(sk:Skill)
RETURN sk.name, count(q) as question_count, sk.level
ORDER BY sk.level;
```

### Nếu bạn cần đếm đúng “22 topics chuẩn” (không tính tag topics)

```cypher
MATCH (t:Topic)
WHERE coalesce(t.is_tag,false)=false
RETURN count(t) AS main_topics;
```

---

## 8) Troubleshooting

### 8.1 Neo4j không vào được / connection refused

- Kiểm tra container:

```powershell
docker ps
```

- Xem logs:

```powershell
docker logs neo4j-kbs --tail 200
```

### 8.2 PostgreSQL login fail

- Vào container kiểm tra env:

```powershell
docker inspect postgres-kbs | Select-String -Pattern "POSTGRES"
```

### 8.3 `\dt` báo `dt: not found`

Bạn đang gõ `\dt` trong **shell** chứ chưa vào `psql`.

Hãy vào `psql` trước:

```powershell
docker exec -it postgres-kbs psql -U kbs_user -d kbs_adaptive_exam
```

---

## 9) Kết quả mong đợi (để tick checklist)

### PostgreSQL
- `subjects` = 2
- `topics` = 22
- `questions` = 258
- `question_options` = 1032

### Neo4j
- `(:Subject)` = 2
- `(:Question)` = 258
- `(:Skill)` = 6
- `(:Topic)` >= 22 (do có thể có tag topics)

---

## 10) Nên gửi cho người chạy những thông tin gì?

- Folder `source/package/` này (zip lại là chạy được)
- Hoặc ít nhất:
  - `docker-compose.yml`
  - `requirements.txt`
  - tất cả file `.py`
  - file Excel `.xlsx`

---

### Notes

Nếu bạn muốn “reset data” để chạy lại từ đầu:

- PostgreSQL: xóa volume hoặc drop tables (tùy setup trong compose)
- Neo4j: vào Neo4j Browser chạy:

```cypher
MATCH (n) DETACH DELETE n;
```
