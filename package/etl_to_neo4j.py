"""
ETL Script: Excel → Neo4j Knowledge Graph
Tạo full schema: Nodes (Subject, Topic, Question, Skill) + Relationships

Author: Member 1 - KBS Adaptive Learning System
Date: 2026-04-25
"""

import pandas as pd
from neo4j import GraphDatabase
import logging
from typing import List, Dict

# =============================================================================
# CONFIGURATION
# =============================================================================

NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "12345678"  # neo4j-kbs (recreated)
}

EXCEL_FILE = r"D:\master's degree\knowledge_management\term\source\questions\excel_question\questions_week3_fixed_complete.xlsx"

# Bloom level mapping
BLOOM_MAPPING = {
    1: "Remember",
    2: "Understand",
    3: "Apply",
    4: "Analyze",
    5: "Evaluate",
    6: "Create"
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# NEO4J CONNECTION
# =============================================================================

class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info("✓ Connected to Neo4j")
    
    def close(self):
        self.driver.close()
        logger.info("✓ Neo4j connection closed")
    
    def run_query(self, query, parameters=None):
        """Execute a Cypher query"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return result.data()


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
        
        self.df = pd.read_excel(self.excel_file)
        logger.info(f"Loaded {len(self.df)} rows")
        
        # Clean: Loại bỏ câu hỏi thiếu options
        before = len(self.df)
        self.df = self.df.dropna(subset=['option_a', 'option_b', 'option_c', 'option_d'])
        after = len(self.df)
        logger.info(f"Removed {before - after} rows with missing options")
        logger.info(f"Valid questions: {after}")
        
        # Fill NaN
        self.df['related_topics'] = self.df['related_topics'].fillna('')
        self.df['prerequisites'] = self.df['prerequisites'].fillna('')
        
        return self.df


# =============================================================================
# NEO4J PROCESSORS
# =============================================================================

class ConstraintsCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
    
    def create_all(self):
        """Tạo constraints để đảm bảo uniqueness"""
        logger.info("=" * 60)
        logger.info("STEP 1: Creating CONSTRAINTS")
        logger.info("=" * 60)
        
        constraints = [
            "CREATE CONSTRAINT subject_id_unique IF NOT EXISTS FOR (s:Subject) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:Question) REQUIRE q.id IS UNIQUE",
            "CREATE CONSTRAINT skill_name_unique IF NOT EXISTS FOR (sk:Skill) REQUIRE sk.name IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                self.neo4j.run_query(constraint)
                logger.info(f"  ✓ {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}")
            except Exception as e:
                logger.warning(f"  ⚠ Constraint already exists or error: {e}")
        
        logger.info("✓ Constraints created\n")


class SubjectNodeCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
    
    def create(self, df: pd.DataFrame):
        """Tạo Subject nodes"""
        logger.info("=" * 60)
        logger.info("STEP 2: Creating SUBJECT Nodes")
        logger.info("=" * 60)
        
        subjects = df['subject'].unique()
        
        for subject_name in subjects:
            code = subject_name[:3].upper()
            
            self.neo4j.run_query("""
                MERGE (s:Subject {id: $code})
                SET s.name = $name,
                    s.description = $description
            """, {
                "code": code,
                "name": subject_name,
                "description": f"{subject_name} programming and concepts"
            })
            
            logger.info(f"  ✓ Subject: {subject_name} (ID: {code})")
        
        logger.info(f"✓ Created {len(subjects)} Subject nodes\n")


class TopicNodeCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
    
    def create(self, df: pd.DataFrame):
        """Tạo Topic nodes và relationship HAS_TOPIC"""
        logger.info("=" * 60)
        logger.info("STEP 3: Creating TOPIC Nodes + HAS_TOPIC Relationships")
        logger.info("=" * 60)
        
        topic_subject_pairs = df[['subject', 'topic']].drop_duplicates()
        
        for _, row in topic_subject_pairs.iterrows():
            subject_name = row['subject']
            topic_name = row['topic']
            subject_code = subject_name[:3].upper()
            
            # Create Topic node
            self.neo4j.run_query("""
                MERGE (t:Topic {name: $name})
                SET t.description = $description
            """, {
                "name": topic_name,
                "description": f"Topic about {topic_name}"
            })
            
            # Create HAS_TOPIC relationship
            self.neo4j.run_query("""
                MATCH (s:Subject {id: $subject_code})
                MATCH (t:Topic {name: $topic_name})
                MERGE (s)-[:HAS_TOPIC]->(t)
            """, {
                "subject_code": subject_code,
                "topic_name": topic_name
            })
            
            logger.info(f"  ✓ Topic: {topic_name} → Subject: {subject_name}")
        
        logger.info(f"✓ Created {len(topic_subject_pairs)} Topic nodes\n")


class SkillNodeCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
    
    def create(self):
        """Tạo Skill nodes (6 Bloom levels)"""
        logger.info("=" * 60)
        logger.info("STEP 4: Creating SKILL Nodes (Bloom's Taxonomy)")
        logger.info("=" * 60)
        
        for level, name in BLOOM_MAPPING.items():
            self.neo4j.run_query("""
                MERGE (sk:Skill {name: $name})
                SET sk.level = $level,
                    sk.description = $description
            """, {
                "name": name,
                "level": level,
                "description": f"Bloom's Taxonomy Level {level}: {name}"
            })
            
            logger.info(f"  ✓ Skill: {name} (Level {level})")
        
        logger.info(f"✓ Created {len(BLOOM_MAPPING)} Skill nodes\n")


class QuestionNodeCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j
    
    def create(self, df: pd.DataFrame):
        """Tạo Question nodes"""
        logger.info("=" * 60)
        logger.info("STEP 5: Creating QUESTION Nodes")
        logger.info("=" * 60)
        
        created = 0
        
        for idx, row in df.iterrows():
            question_id = f"Q{str(row['id']).zfill(3)}"  # Q001, Q002...
            
            self.neo4j.run_query("""
                MERGE (q:Question {id: $id})
                SET q.content = $content,
                    q.difficulty = $difficulty,
                    q.bloom_level = $bloom_level,
                    q.avg_time_seconds = $avg_time
            """, {
                "id": question_id,
                "content": row['content'][:100] + "...",  # Truncate for graph display
                "difficulty": float(row['difficulty']),
                "bloom_level": int(row['bloom_level']),
                "avg_time": int(row['avg_time_seconds'])
            })
            
            created += 1
            if created % 50 == 0:
                logger.info(f"  Processed {created} questions...")
        
        logger.info(f"✓ Created {created} Question nodes\n")


class RelationshipCreator:
    def __init__(self, neo4j: Neo4jConnection):
        self.neo4j = neo4j

    def _ensure_topic(self, topic_name: str):
        """Ensure a Topic node exists for a given name.

        Note: The Excel uses knowledge tags (e.g. "arrays", "binary_search") in
        `related_topics` / `prerequisites` that may not be part of the 22 main
        curriculum topics. We still materialize them as Topic nodes so we can
        build COVERS/PREREQUISITE_OF edges.
        """
        self.neo4j.run_query(
            """
            MERGE (t:Topic {name: $name})
            ON CREATE SET t.description = $description,
                          t.is_tag = true
            """,
            {
                "name": topic_name,
                "description": f"Auto-created tag topic from Excel: {topic_name}",
            },
        )
    
    def create_belongs_to(self, df: pd.DataFrame):
        """Tạo BELONGS_TO: Question → Topic (topic chính)"""
        logger.info("=" * 60)
        logger.info("STEP 6: Creating BELONGS_TO Relationships")
        logger.info("=" * 60)
        
        created = 0
        
        for idx, row in df.iterrows():
            question_id = f"Q{str(row['id']).zfill(3)}"
            topic_name = row['topic']
            
            self.neo4j.run_query("""
                MATCH (q:Question {id: $question_id})
                MATCH (t:Topic {name: $topic_name})
                MERGE (q)-[:BELONGS_TO]->(t)
            """, {
                "question_id": question_id,
                "topic_name": topic_name
            })
            
            created += 1
        
        logger.info(f"✓ Created {created} BELONGS_TO relationships\n")
    
    def create_tests(self, df: pd.DataFrame):
        """Tạo TESTS: Question → Skill (dựa vào bloom_level)"""
        logger.info("=" * 60)
        logger.info("STEP 7: Creating TESTS Relationships")
        logger.info("=" * 60)
        
        created = 0
        
        for idx, row in df.iterrows():
            question_id = f"Q{str(row['id']).zfill(3)}"
            bloom_level = int(row['bloom_level'])
            skill_name = BLOOM_MAPPING[bloom_level]
            
            self.neo4j.run_query("""
                MATCH (q:Question {id: $question_id})
                MATCH (sk:Skill {name: $skill_name})
                MERGE (q)-[:TESTS]->(sk)
            """, {
                "question_id": question_id,
                "skill_name": skill_name
            })
            
            created += 1
        
        logger.info(f"✓ Created {created} TESTS relationships\n")
    
    def create_covers(self, df: pd.DataFrame):
        """Tạo COVERS: Question → Topic (từ related_topics)"""
        logger.info("=" * 60)
        logger.info("STEP 8: Creating COVERS Relationships")
        logger.info("=" * 60)
        
        created = 0
        
        for idx, row in df.iterrows():
            question_id = f"Q{str(row['id']).zfill(3)}"
            related_topics_str = row['related_topics']
            
            if not related_topics_str or pd.isna(related_topics_str):
                continue
            
            # Parse related_topics
            related_topics = [t.strip() for t in related_topics_str.split(',') if t.strip()]
            
            for topic_name in related_topics:
                self._ensure_topic(topic_name)

                self.neo4j.run_query(
                    """
                    MATCH (q:Question {id: $question_id})
                    MATCH (t:Topic {name: $topic_name})
                    MERGE (q)-[r:COVERS]->(t)
                    ON CREATE SET r.weight = 0.5
                    """,
                    {"question_id": question_id, "topic_name": topic_name},
                )
                created += 1
        
        logger.info(f"✓ Created {created} COVERS relationships\n")
    
    def create_prerequisite_of(self, df: pd.DataFrame):
        """Tạo PREREQUISITE_OF: Topic → Topic (từ prerequisites)"""
        logger.info("=" * 60)
        logger.info("STEP 9: Creating PREREQUISITE_OF Relationships")
        logger.info("=" * 60)
        
        created = 0
        
        # Lấy unique (topic, prerequisites) pairs
        topic_prereq_pairs = df[['topic', 'prerequisites']].drop_duplicates()
        
        for _, row in topic_prereq_pairs.iterrows():
            topic_name = row['topic']
            prerequisites_str = row['prerequisites']
            
            if not prerequisites_str or pd.isna(prerequisites_str):
                continue
            
            # Parse prerequisites
            prerequisites = [p.strip() for p in prerequisites_str.split(',') if p.strip()]
            
            for prereq_name in prerequisites:
                # Ensure both ends exist (main topic exists from STEP 3 already)
                self._ensure_topic(prereq_name)

                self.neo4j.run_query(
                    """
                    MATCH (t_pre:Topic {name: $prereq_name})
                    MATCH (t_main:Topic {name: $topic_name})
                    MERGE (t_pre)-[:PREREQUISITE_OF]->(t_main)
                    """,
                    {"prereq_name": prereq_name, "topic_name": topic_name},
                )
                created += 1
        
        logger.info(f"✓ Created {created} PREREQUISITE_OF relationships\n")


# =============================================================================
# MAIN ETL PIPELINE
# =============================================================================

def main():
    logger.info("=" * 60)
    logger.info("ETL PIPELINE: Excel → Neo4j Knowledge Graph")
    logger.info("=" * 60)
    logger.info("")
    
    # Initialize
    neo4j = Neo4jConnection(**NEO4J_CONFIG)
    loader = DataLoader(EXCEL_FILE)
    
    try:
        # Load and clean data
        df = loader.load_and_clean()
        
        # Create constraints
        constraints_creator = ConstraintsCreator(neo4j)
        constraints_creator.create_all()
        
        # Create nodes
        subject_creator = SubjectNodeCreator(neo4j)
        subject_creator.create(df)
        
        topic_creator = TopicNodeCreator(neo4j)
        topic_creator.create(df)
        
        skill_creator = SkillNodeCreator(neo4j)
        skill_creator.create()
        
        question_creator = QuestionNodeCreator(neo4j)
        question_creator.create(df)
        
        # Create relationships
        relationship_creator = RelationshipCreator(neo4j)
        relationship_creator.create_belongs_to(df)
        relationship_creator.create_tests(df)
        relationship_creator.create_covers(df)
        relationship_creator.create_prerequisite_of(df)
        
        # Summary
        logger.info("=" * 60)
        logger.info("ETL COMPLETED SUCCESSFULLY!")
        logger.info("=" * 60)
        logger.info("Graph statistics:")
        
        # Count nodes
        stats = neo4j.run_query("""
            MATCH (n)
            RETURN labels(n)[0] as label, count(n) as count
            ORDER BY label
        """)
        
        for stat in stats:
            logger.info(f"  {stat['label']}: {stat['count']} nodes")
        
        # Count relationships
        rel_stats = neo4j.run_query("""
            MATCH ()-[r]->()
            RETURN type(r) as type, count(r) as count
            ORDER BY type
        """)
        
        logger.info("\nRelationships:")
        for stat in rel_stats:
            logger.info(f"  {stat['type']}: {stat['count']} relationships")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"✗ ETL FAILED: {e}")
        raise
    
    finally:
        neo4j.close()


if __name__ == "__main__":
    main()
