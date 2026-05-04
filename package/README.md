# 🎓 Hybrid Computerized Adaptive Testing System

## (IRT + Knowledge Graph + Rule-Based Reasoning)

---

## 1. 📌 Giới thiệu

Dự án này xây dựng một **hệ thống kiểm tra thích ứng (Computerized Adaptive Testing – CAT)** kết hợp ba thành phần:

* **Item Response Theory (IRT)** → mô hình hóa năng lực người học
* **Knowledge Graph (Neo4j)** → biểu diễn tri thức và quan hệ giữa các chủ đề
* **Rule-Based System** → suy luận và cập nhật mức độ hiểu biết (mastery)

Hệ thống hướng tới:

* Cá nhân hóa bài kiểm tra theo năng lực
* Tối ưu lộ trình học
* Giải thích được (Explainable AI)

---

## 2. 🎯 Mục tiêu

* Xây dựng hệ CAT thích ứng theo năng lực (θ – theta)
* Tích hợp Knowledge Graph để khai thác quan hệ giữa các topic
* Áp dụng rule-based reasoning để cập nhật mastery
* Cung cấp cơ chế giải thích kết quả học tập

---

## 3. 🧠 Kiến trúc hệ thống

### 3.1 Tổng quan

```
+-------------------+
|    FastAPI API    |
+-------------------+
         |
         v
+-------------------+        +----------------------+
|   PostgreSQL      | <----> |        Neo4j         |
| (Transactional DB)|        | (Knowledge Graph)    |
+-------------------+        +----------------------+
         |
         v
+-------------------+
|   IRT Engine      |
+-------------------+
         |
         v
+-------------------+
| Rule-based Engine |
+-------------------+
```

---

### 3.2 Thành phần chính

| Thành phần  | Vai trò                                    |
| ----------- | ------------------------------------------ |
| FastAPI     | API layer                                  |
| PostgreSQL  | Lưu dữ liệu câu hỏi, sinh viên, attempt    |
| Neo4j       | Lưu graph tri thức (Topic, Question, Rule) |
| IRT         | Cập nhật năng lực θ                        |
| Rule Engine | Cập nhật mastery + giải thích              |

---

## 4. 📊 Mô hình toán học (IRT)

Xác suất trả lời đúng:

[
P(\theta) = \frac{1}{1 + e^{-(\theta - b)}}
]

Cập nhật năng lực:

[
\theta_{new} = \theta + \alpha (r - P(\theta))
]

Trong đó:

* ( \theta ): năng lực hiện tại
* ( b ): độ khó câu hỏi
* ( r ): kết quả (0/1)
* ( \alpha ): learning rate

---

## 5. 🧩 Knowledge Graph (Neo4j)

### 5.1 Node

* `Student`
* `Topic`
* `Question`
* `Rule`

### 5.2 Relationship

* `HAS_MASTERY`
* `RELATED_TO`
* `PREREQUISITE_OF`
* `APPLIES_TO`

---

## 6. ⚙️ Rule-Based Reasoning

Sử dụng **forward chaining**:

* Input:

  * difficulty
  * correct/incorrect
* Rule:

  * operator, threshold, weight
* Output:

  * delta mastery

Ví dụ:

```
IF difficulty > 0.5 AND correct = true
THEN increase mastery by 0.1
```

---

## 7. 🔄 Quy trình hoạt động

```
Start Test
   ↓
Select Question (IRT + Graph)
   ↓
User Answer
   ↓
Update Theta (IRT)
   ↓
Update Mastery (Rule + Neo4j)
   ↓
Next Question
   ↓
Submit Test
```

---

## 8. 🌐 API Endpoints

### 8.1 Start Test

```
POST /cat/start/{student_id}/{subject_id}
```

---

### 8.2 Get Next Question

```
GET /cat/next/{attempt_id}
```

---

### 8.3 Submit Answer

```
POST /cat/answer
```

Body:

```json
{
  "attempt_id": 1,
  "student_id": 1,
  "question_id": 10,
  "selected_option": "A",
  "time_spent_sec": 30
}
```

---

### 8.4 Submit Test

```
POST /cat/submit/{attempt_id}
```

---

### 8.5 Explain Knowledge

```
GET /cat/explain/{student_id}
```

---

## 9. ⚙️ Cài đặt và chạy hệ thống

### 9.1 Cài thư viện

```bash
pip install fastapi uvicorn psycopg2 pandas numpy neo4j
```

---

### 9.2 Thứ tự chạy

```bash
# 1. Tạo schema
python bootstrap_schema_postgres.py

# 2. ETL dữ liệu
python etl_to_postgresql.py

# 3. Sync sang Neo4j
python postgres_to_neo4j.py

# 4. Thêm ability
ALTER TABLE students ADD COLUMN ability FLOAT DEFAULT 0.0;

# 5. Chạy API
uvicorn cat_api_rule_based_neo4j:app --reload
```

---

## 10. 📈 Đóng góp chính

* Kết hợp **IRT + Knowledge Graph + Rule-based**
* Xây dựng hệ thống **Explainable CAT**
* Tích hợp suy luận tri thức vào adaptive testing
* Tăng khả năng cá nhân hóa và giải thích

---

## 11. ⚠️ Hạn chế

* Rule-based còn đơn giản (chưa học từ dữ liệu)
* Chưa có stopping condition tối ưu
* Chưa có exposure control cho câu hỏi

---

## 12. 🚀 Hướng phát triển

* Bayesian IRT
* Machine Learning ranking
* Reinforcement Learning cho question selection
* Auto rule learning
* Dashboard visualization

---

## 13. 📚 Tài liệu tham khảo

* Lord, F. M. (1980). *Applications of Item Response Theory*
* Russell & Norvig (AI – Knowledge-Based Systems)
* Neo4j Graph Data Modeling
* FastAPI Documentation

---

## 14. 👨‍💻 Tác giả

* Họ tên: …
* Môn học: Knowledge-Based Systems
* Giảng viên: …

---
