-- 7. students
INSERT INTO students (student_code, full_name, class_name, email)
VALUES
('S001', 'Nguyen Van A', '10A1', 'a@gmail.com'),
('S002', 'Tran Thi B', '10A1', 'b@gmail.com');


-- 8. student_topic_mastery
INSERT INTO student_topic_mastery (student_id, topic_id, mastery_score, question_count, correct_count)
VALUES
(1, 1, 0.75, 20, 15),
(1, 2, 0.60, 10, 6),
(2, 1, 0.80, 25, 20);


-- 9. exam_blueprints
INSERT INTO exam_blueprints (subject_id, name, total_questions, target_difficulty)
VALUES
(1, 'Midterm Math', 10, 0.5),
(1, 'Final Math', 20, 0.6);


-- 14. exam_blueprint_details
INSERT INTO exam_blueprint_details (blueprint_id, topic_id, question_count, difficulty_min, difficulty_max)
VALUES
(1, 1, 5, 0.3, 0.6),
(1, 2, 5, 0.4, 0.7),
(2, 1, 10, 0.4, 0.8);


-- 10. exams
INSERT INTO exams (student_id, subject_id, blueprint_id, requested_count, requested_diff)
VALUES
(1, 1, 1, 10, 0.5),
(2, 1, 1, 10, 0.5);


-- 11. exam_questions
INSERT INTO exam_questions (exam_id, question_id, display_order)
VALUES
(1, 1, 1),
(1, 2, 2),
(1, 3, 3),
(2, 1, 1),
(2, 4, 2);


-- 12. attempts
INSERT INTO attempts (exam_id, student_id, started_at, submitted_at, total_score, max_score, feedback)
VALUES
(1, 1, NOW() - INTERVAL '30 minutes', NOW(), 8, 10, 'Good job'),
(2, 2, NOW() - INTERVAL '25 minutes', NOW(), 6, 10, 'Need improvement');


-- 13. attempt_answers
INSERT INTO attempt_answers (attempt_id, question_id, selected_option, is_correct, time_spent_sec)
VALUES
(1, 1, 'A', TRUE, 30),
(1, 2, 'B', TRUE, 25),
(1, 3, 'C', FALSE, 40),
(2, 1, 'A', TRUE, 20),
(2, 4, 'D', FALSE, 35);


-- 15. rules
INSERT INTO rules (rule_name, description, condition_expr, action_expr, priority)
VALUES
('Low Mastery Rule', 'If mastery < 0.5 then increase easy questions',
 'mastery_score < 0.5',
 'increase_easy_questions',
 1),
('High Mastery Rule', 'If mastery > 0.8 then increase hard questions',
 'mastery_score > 0.8',
 'increase_hard_questions',
 2);


-- 16. rule_topic_mapping
INSERT INTO rule_topic_mapping (rule_id, topic_id)
VALUES
(1, 1),
(2, 1),
(2, 2);


-- 17. llm_generation_logs
INSERT INTO llm_generation_logs (topic_id, prompt_text, raw_response, parsed_json, created_question_id, status)
VALUES
(1, 'Generate algebra question', 'Raw LLM output...', '{"difficulty":0.5}', 1, 'SUCCESS'),
(2, 'Generate geometry question', 'Raw LLM output...', '{"difficulty":0.6}', 2, 'SUCCESS');


-- 18. difficulty_assessments
INSERT INTO difficulty_assessments (question_id, assessed_by, difficulty, confidence, note)
VALUES
(1, 'teacher_1', 0.5, 0.9, 'Medium difficulty'),
(2, 'teacher_2', 0.7, 0.8, 'Hard question');
