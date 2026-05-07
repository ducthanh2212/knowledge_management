import csv
from neo4j import GraphDatabase

# ================= CONFIG =================
NEO4J_URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "12345678"

driver = GraphDatabase.driver(NEO4J_URI, auth=(USER, PASSWORD))


# ================= PARSER =================

def parse_value(val: str):
    val = val.strip()
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return float(val)
    except:
        return val


def parse_condition(cond_str):
    ops = [">=", "<=", "==", ">", "<"]

    for op in ops:
        if op in cond_str:
            left, right = cond_str.split(op)
            return {
                "field": left.strip(),
                "operator": op,
                "value": parse_value(right)
            }

    raise ValueError(f"Invalid condition: {cond_str}")


# ================= DB OPS =================

def clear_old_rules(tx):
    tx.run("""
    MATCH (r:Rule)
    DETACH DELETE r
    """)


def insert_rule(tx, rule):
    # Rule node
    tx.run("""
    MERGE (r:Rule {rule_id:$rule_id})
    SET r.priority=$priority,
        r.weight=$weight,
        r.description=$description,
        r.is_active=true
    """, **rule)

    # Action node (1 rule = 1 action)
    tx.run("""
    MATCH (r:Rule {rule_id:$rule_id})
    MERGE (a:Action {type:"UPDATE_MASTERY", delta:$delta})
    MERGE (r)-[:HAS_ACTION]->(a)
    """, rule_id=rule["rule_id"], delta=rule["delta"])

    # Conditions
    for c in rule["conditions"]:
        tx.run("""
        MATCH (r:Rule {rule_id:$rule_id})
        MERGE (c:Condition {
            field:$field,
            operator:$operator,
            value:$value
        })
        MERGE (r)-[:HAS_CONDITION]->(c)
        """, rule_id=rule["rule_id"], **c)

    # Topic mapping
    for tid in rule["topic_ids"]:
        tx.run("""
        MATCH (r:Rule {rule_id:$rule_id})
        MATCH (t:Topic {topic_id:$tid})
        MERGE (r)-[:APPLIES_TO]->(t)
        """, rule_id=rule["rule_id"], tid=tid)


# ================= MAIN =================

def load_rules(csv_path, reset=True):
    with open(csv_path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)

        with driver.session() as session:

            if reset:
                print("🧹 Clearing old rules...")
                session.execute_write(clear_old_rules)

            for row in reader:
                # Skip empty rows
                if not row["rule_id"] or not row["priority"]:
                    continue

                rule = {
                    "rule_id": row["rule_id"].strip(),
                    "priority": int(row["priority"]),
                    "weight": float(row["weight"]),
                    "description": row["description"].strip(),
                    "delta": float(row["delta"]),
                    "topic_ids": [
                        int(x.strip())
                        for x in row["topic_ids"].split("|")
                    ],
                    "conditions": [
                        parse_condition(c.strip())
                        for c in row["conditions"].split(";")
                    ]
                }

                session.execute_write(insert_rule, rule)

                print(f"✅ Inserted {rule['rule_id']}")


# ================= RUN =================

if __name__ == "__main__":
    load_rules("rules.csv", reset=True)
