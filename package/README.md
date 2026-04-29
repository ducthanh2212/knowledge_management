# Knowledge Management System — PostgreSQL + Neo4j ETL Project

## Overview

This project builds a lightweight Knowledge Management System pipeline using:

- Excel as the raw source
- PostgreSQL as the structured database
- Neo4j as the knowledge graph

The project is designed to:

- load exam/question data into PostgreSQL
- normalize relational data
- synchronize data into Neo4j
- build semantic relationships for knowledge exploration

---

# Project Structure

```text
project/
│
├── bootstrap_schema_postgres.py
├── docker-compose.yml
├── etl_to_postgresql.py
├── postgres_to_neo4j.py
├── questions_week3_fixed_complete.xlsx
├── requirements.txt
├── test_connections.py
└── README.md
```

---

# File Descriptions

## bootstrap_schema_postgres.py

Creates PostgreSQL schema automatically.

Purpose:

- create database tables
- initialize constraints
- prepare schema before ETL

Run first before loading data.

---

## docker-compose.yml

Starts local database services.

Typically includes:

- PostgreSQL container
- Neo4j container

Run:

```bash
docker-compose up -d
```

This launches:

- PostgreSQL database
- Neo4j graph database

---

## etl_to_postgresql.py

Loads Excel data into PostgreSQL.

Flow:

```text
Excel
  ↓
Data Cleaning
  ↓
Normalization
  ↓
PostgreSQL Insert
```

Responsibilities:

- read Excel file
- validate records
- clean data
- insert relational records

---

## postgres_to_neo4j.py

Synchronizes PostgreSQL data into Neo4j.

Flow:

```text
PostgreSQL
  ↓
Incremental Sync
  ↓
Neo4j Graph
```

Responsibilities:

- fetch PostgreSQL rows
- incremental sync
- create Neo4j nodes
- create Neo4j relationships
- track sync checkpoints

---

## questions_week3_fixed_complete.xlsx

Raw source data.

Contains:

- subjects
- topics
- questions
- answer options
- knowledge relationships

Used by:

```text
etl_to_postgresql.py
```

---

## requirements.txt

Python dependencies.

Install packages:

```bash
pip install -r requirements.txt
```

---

## test_connections.py

Checks database connectivity.

Purpose:

- test PostgreSQL connection
- test Neo4j connection
- verify credentials

Run before ETL or sync.

---

# System Flow

```text
questions_week3_fixed_complete.xlsx
                ↓
        etl_to_postgresql.py
                ↓
            PostgreSQL
                ↓
         postgres_to_neo4j.py
                ↓
               Neo4j
```

---

# Setup Guide

## Step 1 — Start Services

Run Docker containers:

```bash
docker-compose up -d
```

---

## Step 2 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Step 3 — Test Database Connections

```bash
python test_connections.py
```

Expected:

```text
PostgreSQL Connected
Neo4j Connected
```

This step verifies:

- PostgreSQL credentials
- Neo4j credentials
- container availability
- network connectivity

---

## Step 4 — Create PostgreSQL Schema

```bash
python bootstrap_schema_postgres.py
```

This creates required tables.

---

## Step 5 — Load Excel Into PostgreSQL

```bash
python etl_to_postgresql.py
```

This loads Excel data into PostgreSQL.

---

## Step 6 — Sync PostgreSQL → Neo4j

```bash
python postgres_to_neo4j.py
```

This creates graph data.

---

# Database Architecture

## PostgreSQL Role

PostgreSQL stores:

- normalized tables
- transactional records
- ETL output

Acts as:

```text
source of truth
```

---

## Neo4j Role

Neo4j stores:

- graph relationships
- semantic knowledge connections
- traversal-friendly data

Acts as:

```text
knowledge graph layer
```

---

# Neo4j Graph Structure

## Nodes

```text
Subject
Topic
Question
Option
QuestionType
```

---

## Relationships

```text
(:Topic)-[:BELONGS_TO]->(:Subject)

(:Question)-[:BELONGS_TO]->(:Subject)

(:Question)-[:PRIMARY_TOPIC]->(:Topic)

(:Question)-[:HAS_OPTION]->(:Option)

(:Question)-[:HAS_TYPE]->(:QuestionType)

(:Question)-[:RELATED_TO]->(:Topic)
```

---

# Incremental Sync

The sync engine supports:

```text
created_at
updated_at
deleted_at
```

Incremental logic:

```sql
GREATEST(
    created_at,
    updated_at,
    deleted_at
)
```

Benefits:

- insert tracking
- update tracking
- delete tracking

---

# Common Commands

## Start Services

```bash
docker-compose up -d
```

---

## Stop Services

```bash
docker-compose down
```

---

## Run ETL

```bash
python etl_to_postgresql.py
```

---

## Run Graph Sync

```bash
python postgres_to_neo4j.py
```

---

## Test Connections

```bash
python test_connections.py
```

---

# Expected Workflow

```text
1. Start Docker
2. Create schema
3. Test connection
4. Load Excel
5. Sync graph
```

---

# Recommended Python Version

```text
Python 3.10+
```

---

# Dependencies

Typical dependencies:

- psycopg2
- pandas
- openpyxl
- neo4j
- python-dotenv

---

# Notes

- PostgreSQL stores structured data
- Neo4j stores graph data
- Excel is used only as ingestion source
- Incremental sync avoids full reload

---

# Author

Knowledge Management System

PostgreSQL → Neo4j ETL + Graph Sync Pipeline

