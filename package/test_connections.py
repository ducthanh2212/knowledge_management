"""
Test Database Connections
Kiểm tra kết nối PostgreSQL và Neo4j trước khi chạy ETL
"""

import psycopg2
from neo4j import GraphDatabase

# =============================================================================
# CONFIG
# =============================================================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "kbs_adaptive_exam",
    "user": "kbs_user",
    "password": "kbs_password"
}

NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "12345678"  # neo4j-kbs (recreated)
}

# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_postgresql():
    """Test PostgreSQL connection"""
    print("=" * 60)
    print("TESTING POSTGRESQL CONNECTION")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        
        print("✓ PostgreSQL connected successfully!")
        print(f"  Version: {version[:50]}...")
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        if tables:
            print(f"\n✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"  - {table[0]}")
        else:
            print("\n⚠ No tables found. You need to create schema first!")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ PostgreSQL connection FAILED!")
        print(f"  Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if PostgreSQL is running")
        print("  2. Verify database name, user, and password")
        print("  3. Check pg_hba.conf for authentication settings")
        return False


def test_neo4j():
    """Test Neo4j connection"""
    print("\n" + "=" * 60)
    print("TESTING NEO4J CONNECTION")
    print("=" * 60)
    
    try:
        driver = GraphDatabase.driver(
            NEO4J_CONFIG["uri"],
            auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
        )
        
        # Test query
        with driver.session() as session:
            result = session.run("RETURN 'Hello Neo4j!' as message")
            message = result.single()["message"]
            
            print("✓ Neo4j connected successfully!")
            print(f"  Message: {message}")
            
            # Check if database has data
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
            
            if count > 0:
                print(f"\n✓ Database contains {count} nodes")
                
                # Count by label
                result = session.run("""
                    MATCH (n)
                    RETURN labels(n)[0] as label, count(n) as count
                    ORDER BY label
                """)
                
                print("  Node types:")
                for record in result:
                    print(f"  - {record['label']}: {record['count']}")
            else:
                print("\n⚠ Database is empty. Ready for ETL!")
        
        driver.close()
        return True
        
    except Exception as e:
        print(f"✗ Neo4j connection FAILED!")
        print(f"  Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if Neo4j is running (http://localhost:7474)")
        print("  2. Verify bolt port 7687 is accessible")
        print("  3. Check username and password")
        print("  4. If using Docker: docker ps | grep neo4j")
        return False


def test_excel_file():
    """Test if Excel file exists"""
    print("\n" + "=" * 60)
    print("TESTING EXCEL FILE")
    print("=" * 60)
    
    import os
    import pandas as pd
    
    excel_file = r"D:\master's degree\knowledge_management\term\source\questions\excel_question\questions_week3_fixed_complete.xlsx"
    
    if not os.path.exists(excel_file):
        print(f"✗ File not found: {excel_file}")
        print("\nPlease:")
        print(f"  1. Copy {excel_file} to current directory")
        print(f"  2. Or update EXCEL_FILE path in ETL scripts")
        return False
    
    try:
        df = pd.read_excel(excel_file)
        print(f"✓ Excel file loaded successfully!")
        print(f"  Total rows: {len(df)}")
        print(f"  Total columns: {len(df.columns)}")
        
        # Check critical columns
        critical_cols = ['id', 'subject', 'topic', 'content', 
                        'option_a', 'option_b', 'option_c', 'option_d',
                        'correct', 'difficulty', 'bloom_level']
        
        missing_cols = [col for col in critical_cols if col not in df.columns]
        
        if missing_cols:
            print(f"\n⚠ Missing columns: {missing_cols}")
            return False
        else:
            print(f"\n✓ All critical columns present!")
        
        # Check for null values in options
        null_options = (
            df['option_a'].isna().sum() +
            df['option_b'].isna().sum() +
            df['option_c'].isna().sum() +
            df['option_d'].isna().sum()
        )
        
        if null_options > 0:
            print(f"\n⚠ Found {null_options} null values in options")
            print(f"  These rows will be skipped during ETL")
        
        return True
        
    except Exception as e:
        print(f"✗ Error reading Excel file: {e}")
        return False


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("""
╔════════════════════════════════════════════════════════════╗
║   ETL CONNECTION TEST - KBS ADAPTIVE LEARNING SYSTEM       ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    results = {
        "PostgreSQL": test_postgresql(),
        "Neo4j": test_neo4j(),
        "Excel File": test_excel_file()
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{name:20s} : {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED - READY TO RUN ETL!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Run PostgreSQL ETL: python etl_to_postgresql.py")
        print("  2. Run Neo4j ETL: python etl_to_neo4j.py")
    else:
        print("\n" + "=" * 60)
        print("✗ SOME TESTS FAILED - FIX ERRORS BEFORE ETL")
        print("=" * 60)
        print("\nPlease fix the failed tests above before running ETL.")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
