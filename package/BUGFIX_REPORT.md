# Báo cáo sửa lỗi – Adaptive Exam System (Hybrid DB + Rule-based CAT)

Ngày: 2026-05-06

## Ngữ cảnh
Repo hiện có các thành phần chính:
- PostgreSQL DB vận hành (schema trong `bootstrap_schema_postgres.py`)
- ETL từ Excel → PostgreSQL (`etl_to_postgresql.py`)
- Đồng bộ PostgreSQL → Neo4j (`postgres_to_neo4j.py`)
- FastAPI CAT API (`cat_api_rule_based_neo4j.py`)

Bạn nghi ngờ: *thiếu column `d` ở một bảng nào đó*.

## Kết quả quét (các bug thực tế)
### 1) API query `students.ability` nhưng schema chưa có
Trong `cat_api_rule_based_neo4j.py`:
- Endpoint `/cat/start/...` chạy: `SELECT ability FROM students ...`

Trong `bootstrap_schema_postgres.py` (bảng `students`) lại **không có cột `ability`**.
Lỗi runtime phía PostgreSQL:
- `column "ability" does not exist`

✅ Đã sửa: thêm `ability FLOAT DEFAULT 0.0` vào bảng `students`.

### 2) API update `attempts.status` nhưng schema chưa có
Trong `cat_api_rule_based_neo4j.py`:
- Endpoint `/cat/submit/...` chạy: `UPDATE attempts SET status='COMPLETED' ...`

Trong `bootstrap_schema_postgres.py` (bảng `attempts`) lại **không có cột `status`**.
Lỗi runtime:
- `column "status" does not exist`

✅ Đã sửa: thêm `status TEXT DEFAULT 'IN_PROGRESS'` vào bảng `attempts`.

### 3) Luồng CAT insert vào `attempts` không có `exam_id` nhưng schema bắt buộc
Trong `cat_api_rule_based_neo4j.py`:
- Endpoint `/cat/start/...` insert vào `attempts(student_id, subject_id, current_theta, last_theta, theta_history)`
- **Không truyền `exam_id`**

Trong `bootstrap_schema_postgres.py` (bảng `attempts`), `exam_id` đang là `NOT NULL`.
Lỗi runtime:
- `null value in column "exam_id" violates not-null constraint`

✅ Đã sửa: cho phép `exam_id` nullable (vẫn giữ FK), có comment giải thích đây là luồng CAT.

> Ghi chú: constraint `UNIQUE(exam_id, student_id)` vẫn giữ nguyên; PostgreSQL cho phép nhiều dòng có `NULL` trong UNIQUE constraint, nên các CAT attempts không có `exam_id` sẽ không bị “đụng nhau”.

### 4) ETL “dễ gãy”: giả định Excel luôn có cột `avg_time_seconds`
Trong `etl_to_postgresql.py`:
- Insert vào DB dùng `avg_time_sec` nhưng đọc Excel lại dùng `row['avg_time_seconds']`.

Nếu file Excel dùng tên khác (hay gặp: `avg_time_sec`) thì ETL sẽ fail:
- `KeyError: 'avg_time_seconds'`

✅ Đã sửa: ETL hỗ trợ cả `avg_time_seconds` và `avg_time_sec`; nếu thiếu/NaN thì mặc định `0`.

## Các file đã thay đổi
- `bootstrap_schema_postgres.py`
  - Thêm `students.ability`.
  - Thêm `attempts.status`.
  - Cho phép `attempts.exam_id` nullable để khớp luồng CAT start.

- `etl_to_postgresql.py`
  - Sửa mapping cột thời gian trung bình linh hoạt (`avg_time_seconds` hoặc `avg_time_sec`).

## Cách áp dụng
Vì schema được tạo bằng cách chạy `bootstrap_schema_postgres.py` (script có DROP và CREATE lại bảng), nên bạn nên chạy lại theo thứ tự:
1. Chạy `python bootstrap_schema_postgres.py`
2. Seed dữ liệu: `psql -U kbs_user -d kbs_adaptive_exam -f "Script seed data.sql"`
3. Chạy ETL + sync + load rules.

Nếu bạn muốn **migration không phá dữ liệu** (dùng `ALTER TABLE` thay vì DROP/CREATE), nói mình biết để mình tạo một script `ALTER TABLE` an toàn.
