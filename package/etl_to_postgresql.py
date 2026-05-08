"""
ETL Script: Excel → PostgreSQL
Đổ 258 câu hỏi vào 6 bảng: subjects, topics, question_types, questions, question_options, question_knowledge_links

Author: Member 1 - KBS Adaptive Learning System
Date: 2026-04-25
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import logging
from typing import Dict, List, Tuple

# =============================================================================
# CONFIGURATION
# =============================================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}

EXCEL_FILE = r"D:\HCMUE\[PG_HK2]\KBS\[FINAL Proj]\anhThanh\knowledge_management\package\questions_week3_fixed_complete.xlsx"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

class DatabaseConnection:
    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cursor = None
    
    def connect(self):
        try:
            self.conn = psycopg2.connect(**self.config)
            self.cursor = self.conn.cursor()
            logger.info("✓ Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise
    
    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("✓ Database connection closed")
    
    def commit(self):
        self.conn.commit()
    
    def rollback(self):
        self.conn.rollback()

# =============================================================================
# DATA LOADER
# =============================================================================

class DataLoader:
    def __init__(self, excel_file: str):
        self.excel_file = excel_file
        self.df = None
    
    def load_and_clean(self) -> pd.DataFrame:
        """Load Excel và làm sạch dữ liệu"""
        logger.info(f"Loading Excel file: {self.excel_file}")
        
        # Load Excel
        self.df = pd.read_excel(self.excel_file)
        logger.info(f"Loaded {len(self.df)} rows")
        
        # Clean: Loại bỏ câu hỏi thiếu options
        before = len(self.df)
        self.df = self.df.dropna(subset=['option_a', 'option_b', 'option_c', 'option_d'])
        after = len(self.df)
        logger.info(f"Removed {before - after} rows with missing options")
        logger.info(f"Valid questions: {after}")
        
        # Clean: Strip whitespace
        for col in ['subject', 'topic', 'content', 'correct', 'source_type']:
            if col in self.df.columns:
                self.df[col] = self.df[col].str.strip()
        
        # Fill NaN cho các cột text
        self.df['subtopic'] = self.df['subtopic'].fillna('')
        self.df['explanation'] = self.df['explanation'].fillna('No explanation provided')
        self.df['related_topics'] = self.df['related_topics'].fillna('')
        self.df['prerequisites'] = self.df['prerequisites'].fillna('')
        self.df['source_reference'] = self.df['source_reference'].fillna('manual')
        
        return self.df

# =============================================================================
# ETL PROCESSORS
# =============================================================================

class SubjectProcessor:
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.subject_map = {}  # {name: id}
    
    def process(self, df: pd.DataFrame):
        """Insert subjects và tạo mapping"""
        logger.info("=" * 60)
        logger.info("STEP 1: Processing SUBJECTS")
        logger.info("=" * 60)
        
        subjects = df['subject'].unique()
        logger.info(f"Found {len(subjects)} unique subjects: {list(subjects)}")
        
        for subject_name in subjects:
            # Tạo code từ tên (ví dụ: "Python" -> "PYT")
            code = subject_name[:3].upper()
            
            # Insert subject
            self.db.cursor.execute("""
                INSERT INTO subjects (code, name, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE 
                SET name = EXCLUDED.name
                RETURNING subject_id
            """, (code, subject_name, f"{subject_name} programming and concepts"))
            
            subject_id = self.db.cursor.fetchone()[0]
            self.subject_map[subject_name] = subject_id
            logger.info(f"  ✓ {subject_name} (ID: {subject_id})")
        
        self.db.commit()
        logger.info(f"✓ Inserted {len(subjects)} subjects\n")
        return self.subject_map


class TopicProcessor:
    def __init__(self, db: DatabaseConnection, subject_map: Dict):
        self.db = db
        self.subject_map = subject_map
        self.topic_map = {}  # {name: id}
    
    def process(self, df: pd.DataFrame):
        """Insert topics và tạo mapping"""
        logger.info("=" * 60)
        logger.info("STEP 2: Processing TOPICS")
        logger.info("=" * 60)
        
        # Group by subject và topic
        topic_subject_pairs = df[['subject', 'topic']].drop_duplicates()
        logger.info(f"Found {len(topic_subject_pairs)} unique topics")
        
        for _, row in topic_subject_pairs.iterrows():
            subject_name = row['subject']
            topic_name = row['topic']
            subject_id = self.subject_map[subject_name]
            
            # Tạo code từ tên topic
            code = topic_name.replace(' ', '_')[:20].upper()
            
            # Insert topic
            self.db.cursor.execute("""
                INSERT INTO topics (subject_id, code, name, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (subject_id, code) DO UPDATE 
                SET name = EXCLUDED.name
                RETURNING topic_id
            """, (subject_id, code, topic_name, f"Topic about {topic_name}"))
            
            topic_id = self.db.cursor.fetchone()[0]
            self.topic_map[topic_name] = topic_id
            logger.info(f"  ✓ {topic_name} (ID: {topic_id}, Subject: {subject_name})")
        
        self.db.commit()
        logger.info(f"✓ Inserted {len(topic_subject_pairs)} topics\n")
        return self.topic_map


class QuestionTypeProcessor:
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.question_type_id = None
    
    def process(self):
        """Tạo question_type 'single_choice'"""
        logger.info("=" * 60)
        logger.info("STEP 3: Processing QUESTION_TYPES")
        logger.info("=" * 60)
        
        self.db.cursor.execute("""
            INSERT INTO question_types (name, description)
            VALUES ('single_choice', 'Multiple choice question with one correct answer')
            ON CONFLICT (name) DO UPDATE 
            SET description = EXCLUDED.description
            RETURNING question_type_id
        """)
        
        self.question_type_id = self.db.cursor.fetchone()[0]
        self.db.commit()
        logger.info(f"✓ Question type 'single_choice' (ID: {self.question_type_id})\n")
        return self.question_type_id


class QuestionProcessor:
    def __init__(self, db: DatabaseConnection, subject_map: Dict, topic_map: Dict, question_type_id: int):
        self.db = db
        self.subject_map = subject_map
        self.topic_map = topic_map
        self.question_type_id = question_type_id
        self.question_map = {}  # {original_id: new_question_id}
    
    def process(self, df: pd.DataFrame):
        """Insert questions"""
        logger.info("=" * 60)
        logger.info("STEP 4: Processing QUESTIONS")
        logger.info("=" * 60)
        
        inserted = 0
        skipped = 0
        
        for idx, row in df.iterrows():
            try:
                subject_id = self.subject_map[row['subject']]
                topic_id = self.topic_map[row['topic']]

                # Excel column name can vary between datasets.
                avg_time_val = None
                if 'avg_time_seconds' in df.columns:
                    avg_time_val = row.get('avg_time_seconds')
                elif 'avg_time_sec' in df.columns:
                    avg_time_val = row.get('avg_time_sec')
                else:
                    avg_time_val = 0
                if pd.isna(avg_time_val):
                    avg_time_val = 0
                
                # Insert question
                self.db.cursor.execute("""
                    INSERT INTO questions (
                        subject_id, topic_id, question_type_id,
                        content, explanation, difficulty, bloom_level,
                        avg_time_sec, source, source_reference, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (subject_id, content)
                    DO UPDATE SET content = EXCLUDED.content
                    RETURNING question_id
                """, (
                    subject_id,
                    topic_id,
                    self.question_type_id,
                    row['content'],
                    row['explanation'],
                    float(row['difficulty']),
                    int(row['bloom_level']),
                    int(avg_time_val),
                    row['source_type'],
                    row['source_reference'],
                    True  # is_active
                ))
                
                question_id = self.db.cursor.fetchone()[0]
                self.question_map[row['id']] = question_id
                inserted += 1
                
                if inserted % 50 == 0:
                    logger.info(f"  Processed {inserted} questions...")
                
            except Exception as e:
                logger.error(f"  ✗ Error at row {idx}: {e}")
                skipped += 1
                continue
        
        self.db.commit()
        logger.info(f"✓ Inserted {inserted} questions, Skipped {skipped}\n")
        return self.question_map


class QuestionOptionsProcessor:
    def __init__(self, db: DatabaseConnection, question_map: Dict):
        self.db = db
        self.question_map = question_map
    
    def process(self, df: pd.DataFrame):
        """Insert question_options (4 options per question)"""
        logger.info("=" * 60)
        logger.info("STEP 5: Processing QUESTION_OPTIONS")
        logger.info("=" * 60)
        
        options_data = []
        
        for idx, row in df.iterrows():
            original_id = row['id']
            if original_id not in self.question_map:
                continue
            
            question_id = self.question_map[original_id]
            correct_answer = row['correct'].strip().upper()
            
            # 4 options: A, B, C, D
            for label in ['A', 'B', 'C', 'D']:
                option_text = row[f'option_{label.lower()}']
                is_correct = (label == correct_answer)
                
                options_data.append((
                    question_id,
                    label,
                    str(option_text),
                    is_correct
                ))
        
        # Batch insert
        execute_values(
            self.db.cursor,
            """
            INSERT INTO question_options (question_id, option_label, option_text, is_correct)
            VALUES %s
            ON CONFLICT (question_id, option_label)
            DO UPDATE SET option_text = EXCLUDED.option_text,
                        is_correct = EXCLUDED.is_correct;
            """,
            options_data
        )
        
        self.db.commit()
        logger.info(f"✓ Inserted {len(options_data)} options ({len(options_data)//4} questions × 4)\n")


class QuestionKnowledgeLinksProcessor:
    def __init__(self, db: DatabaseConnection, question_map: Dict, topic_map: Dict):
        self.db = db
        self.question_map = question_map
        self.topic_map = topic_map
    
    def parse_related_topics(self, related_topics_str: str) -> List[str]:
        """Parse 'topic1, topic2, topic3' → ['topic1', 'topic2', 'topic3']"""
        if not related_topics_str or pd.isna(related_topics_str):
            return []
        return [t.strip() for t in related_topics_str.split(',') if t.strip()]
    
    def process(self, df: pd.DataFrame):
        """Insert question_knowledge_links từ related_topics"""
        logger.info("=" * 60)
        logger.info("STEP 6: Processing QUESTION_KNOWLEDGE_LINKS")
        logger.info("=" * 60)
        
        links_data = []
        
        for idx, row in df.iterrows():
            original_id = row['id']
            if original_id not in self.question_map:
                continue
            
            question_id = self.question_map[original_id]
            
            # 1. Link với topic chính (weight = 1.0)
            main_topic = row['topic']
            if main_topic in self.topic_map:
                links_data.append((
                    question_id,
                    self.topic_map[main_topic],
                    1.0  # weight
                ))
            
            # 2. Link với related_topics (weight = 0.5)
            related_topics = self.parse_related_topics(row['related_topics'])
            for topic_name in related_topics:
                if topic_name in self.topic_map:
                    links_data.append((
                        question_id,
                        self.topic_map[topic_name],
                        0.5  # weight thấp hơn
                    ))
        
        # Batch insert với ON CONFLICT để tránh duplicate
        if links_data:
            execute_values(
                self.db.cursor,
                """
                INSERT INTO question_knowledge_links (question_id, topic_id, relevance_weight)
                VALUES %s
                ON CONFLICT (question_id, topic_id) DO NOTHING
                """,
                links_data
            )
        
        self.db.commit()
        logger.info(f"✓ Inserted {len(links_data)} knowledge links\n")


# =============================================================================
# MAIN ETL PIPELINE
# =============================================================================

def main():
    logger.info("=" * 60)
    logger.info("ETL PIPELINE: Excel → PostgreSQL")
    logger.info("=" * 60)
    logger.info("")
    
    # Initialize
    db = DatabaseConnection(DB_CONFIG)
    loader = DataLoader(EXCEL_FILE)
    
    try:
        # Connect to database
        db.connect()
        
        # Load and clean data
        df = loader.load_and_clean()
        
        # Process in order (FK dependencies)
        subject_processor = SubjectProcessor(db)
        subject_map = subject_processor.process(df)
        
        topic_processor = TopicProcessor(db, subject_map)
        topic_map = topic_processor.process(df)
        
        question_type_processor = QuestionTypeProcessor(db)
        question_type_id = question_type_processor.process()
        
        question_processor = QuestionProcessor(db, subject_map, topic_map, question_type_id)
        question_map = question_processor.process(df)
        
        options_processor = QuestionOptionsProcessor(db, question_map)
        options_processor.process(df)
        
        knowledge_links_processor = QuestionKnowledgeLinksProcessor(db, question_map, topic_map)
        knowledge_links_processor.process(df)
        
        # Summary
        logger.info("=" * 60)
        logger.info("ETL COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info(f"✓ Subjects: {len(subject_map)}")
        logger.info(f"✓ Topics: {len(topic_map)}")
        logger.info(f"✓ Questions: {len(question_map)}")
        logger.info(f"✓ Options: {len(question_map) * 4}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"✗ ETL FAILED: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
