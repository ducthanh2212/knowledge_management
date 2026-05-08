import streamlit as st
import requests
import time
import pandas as pd
import re 

# ================= CẤU HÌNH API =================
BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Hệ thống kiểm tra trắc nghiệm thích ứng theo năng lực", page_icon="🎓", layout="wide")

# --- 1. QUẢN LÝ TRẠNG THÁI (SESSION STATE) ---
if "phase" not in st.session_state:
    st.session_state.phase = "SELECT_SUBJECT"
if "attempt_id" not in st.session_state:
    st.session_state.attempt_id = None
if "student_id" not in st.session_state:
    st.session_state.student_id = 1
if "student_fullname" not in st.session_state:
    st.session_state.student_fullname = ""
if "question_data" not in st.session_state:
    st.session_state.question_data = None
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "question_count" not in st.session_state:
    st.session_state.question_count = 1

# CHÍNH XÁC: Tách thành đếm đúng/sai riêng biệt
if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0 
if "incorrect_count" not in st.session_state:
    st.session_state.incorrect_count = 0 

if "subject_name" not in st.session_state:
    st.session_state.subject_name = ""
if "show_feedback" not in st.session_state:
    st.session_state.show_feedback = False
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# --- HÀM LẤY DANH SÁCH SINH VIÊN CHUYÊN SÂU ---
def fetch_students():
    try:
        res = requests.get(f"{BASE_URL}/students", timeout=2)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

students_data = fetch_students()
if not students_data:
    students_data = [{
        "student_id": 1, "student_code": "SV001", 
        "full_name": "Nguyễn Văn A", "class_name": "KTPM1", 
        "email": "nva@gmail.com", "ability": 0.0
    }]

# --- TÙY CHỈNH GIAO DIỆN CHUNG (SIDEBAR) ---
with st.sidebar:
    st.title("🎓 Adaptive Competency Testing System (ACTS)")
    st.caption("Hệ thống kiểm tra thích ứng theo năng lực")
    
    try:
        health = requests.get(f"{BASE_URL}/", timeout=2)
        status_dot = "🟢" if health.status_code == 200 else "🟡"
    except Exception:
        status_dot = "🔴"
        
    st.markdown(f"**Trạng thái hệ thống:** {status_dot}")
    
    st.subheader("Cấu hình bài thi")
    is_locked = st.session_state.phase != "SELECT_SUBJECT"
    
    subjects = {
        "Nhập môn Python": 1,
        "Cấu trúc dữ liệu": 2,
    }
    
    selected_subject = st.selectbox(
        "📚 Chọn môn học để thi:", 
        list(subjects.keys()), 
        disabled=is_locked 
    )
    
    # CHÍNH XÁC: Hiển thị ID kèm Tên sinh viên để dễ chọn
    student_dict = {f"ID: {s['student_id']} - {s['full_name']} ({s['ability']:.2f})": s for s in students_data}
    selected_student_label = st.selectbox(
        "👤 Chọn Sinh viên:", 
        list(student_dict.keys()), 
        disabled=is_locked 
    )
    selected_student_obj = student_dict[selected_student_label]
    student_id = selected_student_obj['student_id']
    
    # 3. HIỂN THỊ THÔNG TIN VÀ NÚT DỪNG KHI ĐANG THI
    if is_locked:
        st.info(f"📝 Attempt ID: **{st.session_state.attempt_id}**")
        
        # CHÍNH XÁC: Hiển thị Fullname ngay dưới ô nhập ID
        st.info(f"👤 Thí sinh: **{st.session_state.student_fullname}**")
        
        # CHÍNH XÁC: Hiển thị số lượng câu Đúng / Sai
        st.success(f"✅ Số câu trả lời đúng: **{st.session_state.correct_count}**")
        st.error(f"❌ Số câu trả lời sai: **{st.session_state.incorrect_count}**")
        
        if st.button("🛑 Dừng thi và mộp bài", width='stretch'):
            st.session_state.phase = "RESULT"
            st.rerun()

# ==========================================
# GIAI ĐOẠN 1: CHỌN MÔN HỌC & BẮT ĐẦU
# ==========================================
if st.session_state.phase == "SELECT_SUBJECT":
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.title("📝 HỆ THỐNG TRẮC NGHIỆM THÍCH ỨNG THEO NĂNG LỰC")
        st.info("👈 Hãy đảm bảo bạn đã cấu hình Môn thi và ID Sinh viên ở thanh công cụ bên trái.")
        
        with st.container(border=True):
            st.markdown("Nhấn nút bên dưới để khởi tạo và bắt đầu phiên đánh giá năng lực thích ứng.")
            
            if st.button("🚀 BẮT ĐẦU", type="primary", width='stretch'):
                st.session_state.student_id = student_id
                # Lưu tên sinh viên vào session state để hiển thị ở sidebar trong lúc làm bài
                st.session_state.student_fullname = selected_student_obj['full_name']
                st.session_state.subject_name = selected_subject.split(" (")[0]
                subject_id = subjects[selected_subject]
                
                try:
                    api_url = f"{BASE_URL}/cat/start/{student_id}/{subject_id}"
                    with st.spinner("Đang khởi tạo thuật toán IRT và Đồ thị năng lực..."):
                        res = requests.post(api_url)
                    
                    if res.status_code == 200:
                        st.session_state.attempt_id = res.json().get("attempt_id")
                        st.session_state.question_count = 1
                        st.session_state.correct_count = 0
                        st.session_state.incorrect_count = 0
                        st.session_state.phase = "TESTING" 
                        st.rerun() 
                    else:
                        st.error(f"Lỗi từ Backend ({res.status_code}): {res.text}")
                except requests.exceptions.ConnectionError:
                    st.error("❌ Không thể kết nối tới Backend. Hãy chắc chắn FastAPI đang chạy ở cổng 8000!")
        
        st.write("") 
        with st.expander("📋 Xem bảng thông tin chi tiết tất cả Sinh viên", expanded=False):
            if students_data:
                df_stu = pd.DataFrame(students_data)
                # CHÍNH XÁC: Ánh xạ chuẩn các cột từ DB
                df_stu = df_stu[['student_id', 'student_code', 'full_name', 'class_name', 'email', 'ability']]
                df_stu.columns = ["ID", "Mã SV", "Họ và Tên", "Lớp", "Email", "Năng lực (Theta)"]
                st.dataframe(df_stu, hide_index=True, width='stretch')

# ==========================================
# GIAI ĐOẠN 2: LÀM BÀI TEST THÍCH NGHI
# ==========================================
elif st.session_state.phase == "TESTING":
    st.title("🧠 Đang làm bài trắc nghiệm thích ứng...")
    
    def fetch_next_question():
        try:
            res = requests.get(f"{BASE_URL}/cat/next/{st.session_state.attempt_id}")
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "COMPLETED":
                    st.warning("Đã hoàn tất lộ trình câu hỏi! Hệ thống đang chuyển sang màn hình kết quả...")
                    time.sleep(2)
                    st.session_state.phase = "RESULT"
                    st.rerun()
                else:
                    st.session_state.question_data = data
                    st.session_state.start_time = time.time()
            else:
                st.error(f"Lỗi API lấy câu hỏi: {res.text}")
        except Exception as e:
            st.error(f"Lỗi: {e}")

    if st.session_state.question_data is None and not st.session_state.show_feedback:
        fetch_next_question()

    if st.session_state.question_data:
        q = st.session_state.question_data
        
        with st.container(border=True):
            st.caption(f"📚 Môn: **{st.session_state.subject_name.upper()}** | 🆔 ID câu hỏii: **{q.get('question_id')}**")
            
            raw_content = q.get('content', 'Nội dung câu hỏi bị thiếu')
            # 1. Dọn dẹp rác "Copy Code" nếu CSDL có dính vào
            clean_content = re.sub(r"(?i)Copy Code", "", raw_content)
            
            # 2. Tách phần câu hỏi và phần Code dựa vào từ khóa "Code:"
            parts = re.split(r"(?i)Code:", clean_content, maxsplit=1)
            
            # 3. Hiển thị
            if len(parts) == 2:
                text_part = parts[0].strip()
                code_part = parts[1].strip()
                
                # In phần câu hỏi dạng text thường
                st.markdown(f"### Câu {st.session_state.question_count}:\n{text_part}")
                
                # In phần Code vào một khung xám chuẩn chỉ của Streamlit (có highlight cú pháp Python)
                st.code(code_part, language="python")
            else:
                # Nếu câu hỏi không có chữ "Code:", in bình thường
                st.markdown(f"### Câu {st.session_state.question_count}:\n{clean_content}")
            
            options_dict = q.get("options", {})
            available_labels = sorted(list(options_dict.keys())) 
            
            if st.session_state.show_feedback:
                res_data = st.session_state.last_result
                is_correct = res_data.get("correct")
                new_theta = res_data.get("theta", 0.0)
                explanation = res_data.get("explanation", [])

                if is_correct:
                    st.success("🎉 CHÍNH XÁC! Hệ thống sẽ nâng độ khó cho câu tiếp theo.")
                else:
                    st.error("❌ SAI RỒI! Hệ thống sẽ điều chỉnh lại lộ trình câu hỏi cho phù hợp hơn.")
                
                with st.expander("⚙️ Phân tích hệ thống (Rule Engine & IRT)", expanded=True):
                    st.markdown(f"**Năng lực tổng quát (Theta) mới:** `{new_theta:.4f}`")
                    
                    if explanation:
                        df_explain = pd.DataFrame(explanation)
                        df_explain.rename(columns={
                            'topic': 'Chủ đề (Topic)', 
                            'delta': 'Mastery Delta (Thay đổi)', 
                            'rules_applied': 'Số Rules kích hoạt'
                        }, inplace=True)
                        st.table(df_explain)
                    else:
                        st.info("Không có sự thay đổi mức độ thông thạo (Mastery) nào trên Đồ thị cho câu hỏi này.")

                if st.button("Câu hỏi tiếp theo ➡️", type="primary"):
                    st.session_state.show_feedback = False
                    st.session_state.question_data = None 
                    st.session_state.question_count += 1
                    st.rerun()

            else:
                if available_labels:
                    selected = st.radio(
                        "Lựa chọn của bạn:", 
                        available_labels, 
                        format_func=lambda x: f"{x}. {options_dict[x]}", 
                        index=None
                    )
                else:
                    st.warning("⚠️ Câu hỏi này chưa có đáp án trong CSDL.")
                    selected = None

                col1, col2 = st.columns([1, 4])
                
                with col1:
                    if st.button("📤 Gửi đáp án kiểm tra", type="primary", width='stretch', disabled=(selected is None)):
                        time_spent = int(time.time() - st.session_state.start_time)
                        
                        payload = {
                            "attempt_id": st.session_state.attempt_id,
                            "student_id": st.session_state.student_id,
                            "question_id": q.get('question_id'),
                            "selected_option": selected,
                            "time_spent_sec": time_spent
                        }
                        
                        try:
                            with st.spinner("Đang chấm điểm và gửi vào Đồ thị tri thức..."):
                                res = requests.post(f"{BASE_URL}/cat/answer", json=payload)
                                if res.status_code == 200:
                                    res_data = res.json()
                                    st.session_state.last_result = res_data
                                    st.session_state.show_feedback = True
                                    
                                    # CHÍNH XÁC: Cập nhật biến đếm ngay khi có kết quả
                                    if res_data.get("correct"):
                                        st.session_state.correct_count += 1
                                    else:
                                        st.session_state.incorrect_count += 1
                                        
                                    st.rerun()
                                else:
                                    st.error(f"Lỗi khi chấm điểm: {res.text}")
                        except Exception as e:
                            st.error(f"Lỗi kết nối: {e}")

# ==========================================
# GIAI ĐOẠN 3: KẾT QUẢ BÀI THI
# ==========================================
elif st.session_state.phase == "RESULT":
    st.title("🎯 Kết Quả Báo Cáo")
    
    with st.spinner("Đang tổng hợp dữ liệu từ PostgreSQL và truy vấn Graph từ Neo4j..."):
        try:
            res = requests.post(f"{BASE_URL}/cat/submit/{st.session_state.attempt_id}")
            if res.status_code == 200:
                data = res.json()
                st.balloons()
                
                c1, c2, c3 = st.columns(3)
                c1.metric(label="🎓 Năng lực tổng quát (Theta)", value=f"{data.get('final_theta', 0.0):.4f}", delta="IRT Score")
                c2.metric(label="✅ Số câu đúng / ❌ Số câu sai", value=f"{st.session_state.correct_count} / {st.session_state.incorrect_count}")
                c3.metric(label="🏁 Trạng thái", value=data.get("status", "N/A"))
                
                st.divider()
                
                st.subheader("📊 Mức độ thông thạo theo Chủ đề (Topic Mastery)")
                mastery_data = data.get("mastery_summary", [])
                
                if mastery_data:
                    df = pd.DataFrame(mastery_data)
                    if 'topic' in df.columns and 'mastery' in df.columns:
                        st.bar_chart(df.set_index('topic')['mastery'], color="#1f77b4")
                
                with st.expander("🔍 GIẢI THÍCH KẾT QUẢ (Dữ liệu trả về từ Neo4j / IRT Engine)"):
                    st.json(data)
                    
            else:
                st.error(f"Lỗi không thể tổng hợp bài thi: {res.text}")
        except Exception as e:
            st.error(f"Lỗi kết nối API: {e}")
            
    st.divider()
    if st.button("🔄 BẮT ĐẦU PHIÊN TEST MỚI", type="primary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()