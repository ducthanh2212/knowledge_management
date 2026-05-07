# 📘 README – Adaptive Exam System (Hybrid DB + Rule-based CAT)

## 1. Tổng quan hệ thống

Hệ thống triển khai mô hình **Computerized Adaptive Testing (CAT)** nhằm sinh đề thi thích nghi theo năng lực người học.

Kiến trúc sử dụng mô hình **Hybrid Database**:

* **PostgreSQL**: lưu dữ liệu vận hành (câu hỏi, sinh viên, attempts…)
* **Neo4j**: lưu đồ thị tri thức (Topic, Rule, Mastery)
* **Rule Engine**: suy luận cập nhật năng lực
* **FastAPI**: cung cấp API cho hệ thống thi

Hệ thống kết hợp:

* IRT (Item Response Theory)
* Rule-based reasoning
* Knowledge Graph

---

## 2. Cấu trúc project

```
.
├── bootstrap_schema_postgres.py
├── etl_to_postgresql.py
├── postgres_to_neo4j.py
├── load_rules.py
├── cat_api_rule_based_neo4j.py
├── test_connections.py
├── docker-compose.yml
├── requirements.txt
├── rules.csv
├── Script seed data.sql
```

---

## 3. Yêu cầu hệ thống

* Python >= 3.9
* Docker + Docker Compose

Ports sử dụng:

* PostgreSQL: 5432
* Neo4j: 7687, 7474

---

## 4. Khởi động database

Chạy container cho PostgreSQL và Neo4j:

```
docker-compose up -d
```

---

## 5. Cài đặt thư viện

```
pip install -r requirements.txt
```

---

## 6. Kiểm tra kết nối (BƯỚC ĐẦU TIÊN – BẮT BUỘC)

Chạy:

```
python test_connections.py
```

Mục tiêu:

* Kiểm tra kết nối PostgreSQL
* Kiểm tra kết nối Neo4j

Nếu lỗi:

* Kiểm tra Docker đã chạy chưa
* Kiểm tra config DB trong code

---

## 7. Thiết lập dữ liệu

### Bước 1: Tạo schema PostgreSQL

```
python bootstrap_schema_postgres.py
```

### Bước 2: Seed dữ liệu ban đầu

```
psql -U kbs_user -d kbs_adaptive_exam -f "Script seed data.sql"
```

### Bước 3: Import dữ liệu vào PostgreSQL

```
python etl_to_postgresql.py
```

### Bước 4: Đồng bộ dữ liệu sang Neo4j

```
python postgres_to_neo4j.py
```

### Bước 5: Load Rule Engine

```
python load_rules.py
```

---

## 8. Chạy API

Khởi động server:

```
uvicorn cat_api_rule_based_neo4j:app --reload
```

Swagger UI:

```
http://127.0.0.1:8000/docs
```

---

## 9. Luồng hoạt động hệ thống (CAT)

### 1. Bắt đầu bài thi

```
POST /cat/start/{student_id}/{subject_id}
```

→ Tạo attempt và khởi tạo năng lực (theta)

---

### 2. Lấy câu hỏi tiếp theo

```
GET /cat/next/{attempt_id}
```

Logic:

* Lấy topic yếu từ Neo4j
* Mở rộng prerequisite
* Chọn câu hỏi phù hợp với theta

---

### 3. Trả lời câu hỏi

```
POST /cat/answer
```

Body mẫu:

```
{
  "attempt_id": 1,
  "student_id": 1,
  "question_id": 10,
  "selected_option": "A",
  "time_spent_sec": 30
}
```

Xử lý:

* Kiểm tra đúng/sai
* Update theta (IRT)
* Apply rule engine
* Update mastery graph

---

### 4. Nộp bài

```
POST /cat/submit/{attempt_id}
```

Kết quả:

* final theta
* mastery theo topic

---

### 5. Xem phân tích năng lực

```
GET /cat/explain/{student_id}
```

---

## 10. Quick Run (chạy nhanh toàn bộ hệ thống)

```
docker-compose up -d
pip install -r requirements.txt

python test_connections.py

python bootstrap_schema_postgres.py
psql -U kbs_user -d kbs_adaptive_exam -f "Script seed data.sql"
python etl_to_postgresql.py
python postgres_to_neo4j.py
python load_rules.py

uvicorn cat_api_rule_based_neo4j:app --reload
```

---

## 11. Troubleshooting

### Không kết nối PostgreSQL

```
docker ps
```

### Không kết nối Neo4j

* Kiểm tra password trong code

### Không có dữ liệu câu hỏi

* Chưa chạy ETL
* Chưa sync Neo4j

### Rule không hoạt động

```
python load_rules.py
```

---

## 12. Ghi chú

Hệ thống được thiết kế theo hướng:

* Hybrid Database
* Rule-based reasoning
* Adaptive Testing (IRT)

Có thể mở rộng:

* Sinh câu hỏi bằng LLM
* Adaptive difficulty nâng cao
* Dashboard analytics
