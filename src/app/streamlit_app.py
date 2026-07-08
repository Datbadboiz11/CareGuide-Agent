from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from careguide.graph.careguide_graph import CareGuideGraph


TRIAGE_LABELS = {
    "emergency": "Cần cấp cứu",
    "urgent_visit": "Cần khám sớm",
    "routine_visit": "Nên đặt lịch khám",
    "self_care": "Theo dõi tại nhà",
}

TRIAGE_CLASS = {
    "emergency": "triage-emergency",
    "urgent_visit": "triage-urgent",
    "routine_visit": "triage-routine",
    "self_care": "triage-self",
}

EXAMPLE_PROMPTS = {
    "Đau ngực": "Tôi bị đau ngực và khó thở 30 phút",
    "Sốt và ho": "Tôi bị sốt 39 độ, ho và đau họng 3 ngày, không khó thở",
    "Đau bụng": "Tôi bị đau bụng dữ dội và nôn ra máu",
    "Đau đầu": "Tôi bị đau đầu tăng dần, buồn nôn và lú lẫn sau khi ngã đập đầu",
    "Chóng mặt": "Tôi đau đầu chóng mặt sau khi ở trong phòng kín có bếp gas",
}


def main() -> None:
    st.set_page_config(
        page_title="CareGuide",
        page_icon="🩺",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_css()
    init_session_state()

    render_header()
    left, right = st.columns([1.58, 1.0], gap="large")

    with left:
        render_user_panel()
        render_info_cards()
        render_chat_history()

    with right:
        render_result_panel()


@st.cache_resource(show_spinner=False)
def get_graph() -> CareGuideGraph:
    return CareGuideGraph(retrieval_mode="hybrid")


def init_session_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_state", None)
    st.session_state.setdefault("draft_prompt", "")


def render_header() -> None:
    st.markdown(
        """
        <header class="topbar">
          <div class="brand">
            <div class="brand-icon">♡</div>
            <div>
              <div class="brand-name">CareGuide</div>
              <div class="brand-subtitle">Trợ lý sức khỏe của bạn</div>
            </div>
          </div>
          <nav class="nav">
            <span class="nav-item active">Trang chủ</span>
            <span class="nav-item">Hướng dẫn sử dụng</span>
            <span class="nav-item">Về CareGuide</span>
          </nav>
          <div class="actions">
            <span class="emergency-link">Tình huống khẩn cấp</span>
            <span class="language-pill">Tiếng Việt</span>
            <span class="profile-dot"></span>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_user_panel() -> None:
    st.markdown(
        """
        <div class="user-card">
          <div class="welcome-row">
            <div class="bot-avatar">AI</div>
            <div>
              <h1>Chào bạn!</h1>
              <p>Tôi là CareGuide, trợ lý sức khỏe AI luôn sẵn sàng lắng nghe và hỗ trợ bạn.</p>
              <p>Hãy mô tả triệu chứng hoặc vấn đề sức khỏe bạn đang gặp phải.</p>
            </div>
          </div>
          <div class="try-label">Bạn có thể thử:</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(EXAMPLE_PROMPTS))
    for col, (label, prompt) in zip(cols, EXAMPLE_PROMPTS.items(), strict=False):
        if col.button(label, use_container_width=True):
            st.session_state.draft_prompt = prompt
            st.rerun()

    with st.form("symptom_form", clear_on_submit=True):
        user_text = st.text_area(
            "Mô tả chi tiết triệu chứng của bạn",
            value=st.session_state.draft_prompt,
            height=220,
            max_chars=1000,
            placeholder="Mô tả chi tiết triệu chứng của bạn...",
            label_visibility="collapsed",
        )
        st.session_state.draft_prompt = ""
        st.markdown('<div class="textarea-foot">0/1000</div>', unsafe_allow_html=True)

        action_left, action_right = st.columns([1, 1])
        with action_left:
            reset_clicked = st.form_submit_button("Bắt đầu phiên mới", use_container_width=True)
        with action_right:
            submit_clicked = st.form_submit_button("Kiểm tra triệu chứng", type="primary", use_container_width=True)

    if reset_clicked:
        st.session_state.messages = []
        st.session_state.last_state = None
        st.rerun()

    if submit_clicked and user_text.strip():
        run_user_turn(user_text.strip())
        st.rerun()

    st.markdown(
        """
        <div class="privacy-note">
          Thông tin của bạn được bảo mật và chỉ dùng để hỗ trợ tư vấn trong phiên này.
          CareGuide không thay thế chẩn đoán từ bác sĩ.
        </div>
        """,
        unsafe_allow_html=True,
    )


def run_user_turn(user_text: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_text})
    conversation_input = build_conversation_input(st.session_state.messages)

    with st.spinner("CareGuide đang phân tích triệu chứng..."):
        state = get_graph().run(conversation_input)

    st.session_state.last_state = state
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": summarize_assistant_reply(state.get("final_output", {})),
        }
    )


def build_conversation_input(messages: list[dict[str, str]]) -> str:
    user_turns = [message["content"] for message in messages if message["role"] == "user"]
    return "\n".join(user_turns[-6:]).strip()


def summarize_assistant_reply(final_output: dict[str, Any]) -> str:
    if not final_output:
        return "Tôi chưa thể tạo kết quả. Vui lòng thử lại với mô tả cụ thể hơn."
    label = TRIAGE_LABELS.get(final_output.get("triage_level", ""), final_output.get("triage_level", ""))
    recommendation = final_output.get("recommendation", "")
    return f"Mức độ: {label}. {recommendation}"


def render_info_cards() -> None:
    st.markdown(
        """
        <div class="info-grid">
          <div class="info-card danger-card">
            <h3>Dấu hiệu nguy hiểm</h3>
            <ul>
              <li>Đau ngực hoặc tức ngực kéo dài</li>
              <li>Khó thở hoặc thở nhanh</li>
              <li>Ngất xỉu, choáng váng</li>
              <li>Yếu hoặc tê một bên cơ thể</li>
              <li>Ho ra máu, nôn ra máu</li>
            </ul>
            <button class="ghost-danger">Xem tất cả dấu hiệu</button>
          </div>
          <div class="info-card source-card">
            <h3>Nguồn thông tin đáng tin cậy</h3>
            <p>Chúng tôi tham khảo thông tin từ các tổ chức y tế uy tín:</p>
            <ul>
              <li>NHS</li>
              <li>CDC</li>
              <li>MedlinePlus</li>
            </ul>
          </div>
          <div class="info-card history-card">
            <h3>Lịch sử tư vấn</h3>
            <p>Cuộc trò chuyện hiện tại được giữ trong phiên này để bạn có thể bổ sung thông tin liên tục.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chat_history() -> None:
    if not st.session_state.messages:
        return

    rows = []
    for message in st.session_state.messages[-8:]:
        role_class = "user-message" if message["role"] == "user" else "assistant-message"
        role_label = "Bạn" if message["role"] == "user" else "CareGuide"
        rows.append(
            f"""
            <div class="chat-row {role_class}">
              <div class="chat-role">{role_label}</div>
              <div class="chat-bubble">{escape_html(message["content"])}</div>
            </div>
            """
        )

    st.markdown(
        f"""
        <section class="chat-card">
          <h2>Cuộc trò chuyện hiện tại</h2>
          {''.join(rows)}
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_result_panel() -> None:
    state = st.session_state.last_state
    if not state:
        render_empty_result_panel()
        return

    final_output = state.get("final_output", {})
    triage_level = final_output.get("triage_level", "")
    triage_label = TRIAGE_LABELS.get(triage_level, triage_level)
    triage_class = TRIAGE_CLASS.get(triage_level, "triage-routine")
    confidence = final_output.get("confidence", "unknown")

    sections_html = []
    sections_html.append(result_section("Khuyến nghị", [final_output.get("recommendation", "")]))
    sections_html.append(result_section("Việc cần làm ngay", final_output.get("care_advice", []), numbered=True))
    sections_html.append(result_section("Khi nào cần tìm trợ giúp", [final_output.get("when_to_seek_help", "")]))
    sections_html.append(result_section("Dấu hiệu cần lưu ý", final_output.get("red_flags", [])))
    sections_html.append(result_section("Chủ đề y tế liên quan", final_output.get("related_health_topics", [])))

    st.markdown(
        f"""
        <aside class="result-card">
          <div class="result-title-row">
            <h2>Kết quả đánh giá ban đầu</h2>
            <span>{datetime.now().strftime("%H:%M")} hôm nay</span>
          </div>
          <div class="triage-card {triage_class}">
            <div class="triage-icon">!</div>
            <div>
              <div class="triage-label">{escape_html(triage_label)}</div>
              <div class="triage-sub">Mức độ: {escape_html(triage_label.upper())}</div>
            </div>
            <div class="confidence-pill">Độ tin cậy: {escape_html(str(confidence))}</div>
          </div>
          <div class="summary-box">{escape_html(final_output.get("user_summary", ""))}</div>
          {''.join(sections_html)}
          {citations_html(final_output.get("citations", []))}
          {safety_html(final_output)}
        </aside>
        """,
        unsafe_allow_html=True,
    )


def render_empty_result_panel() -> None:
    st.markdown(
        """
        <aside class="result-card">
          <div class="result-title-row">
            <h2>Kết quả đánh giá ban đầu</h2>
            <span>Sẵn sàng</span>
          </div>
          <div class="empty-state">
            <div class="empty-icon">AI</div>
            <h3>Nhập triệu chứng để bắt đầu</h3>
            <p>Kết quả sẽ hiển thị tại đây: mức khuyến nghị, việc cần làm, nguồn tham khảo và lưu ý an toàn.</p>
          </div>
          <div class="safety-box">
            <h3>Lưu ý an toàn</h3>
            <p>Đây chỉ là đánh giá ban đầu dựa trên thông tin bạn cung cấp và không thay thế chẩn đoán của bác sĩ.</p>
          </div>
        </aside>
        """,
        unsafe_allow_html=True,
    )


def result_section(title: str, items: list[str], numbered: bool = False) -> str:
    clean_items = [item for item in items if item]
    if not clean_items:
        return ""
    tag = "ol" if numbered else "ul"
    list_items = "".join(f"<li>{escape_html(item)}</li>" for item in clean_items)
    return f"""
    <div class="result-section">
      <h3>{escape_html(title)}</h3>
      <{tag}>{list_items}</{tag}>
    </div>
    """


def citations_html(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return ""

    rows = []
    for citation in citations[:5]:
        source = escape_html(str(citation.get("source", "")))
        title = escape_html(str(citation.get("title", "")))
        url = escape_html(str(citation.get("url", "")))
        section = escape_html(str(citation.get("section_heading", "")))
        rows.append(
            f"""
            <a class="citation-row" href="{url}" target="_blank">
              <span class="source-badge">{source}</span>
              <span>
                <strong>{title}</strong>
                <small>{section}</small>
              </span>
            </a>
            """
        )
    return f"""
    <div class="result-section citations">
      <h3>Nguồn tham khảo</h3>
      {''.join(rows)}
    </div>
    """


def safety_html(final_output: dict[str, Any]) -> str:
    safety = final_output.get("safety", {})
    passed = bool(safety.get("passed", False))
    status = "Đã kiểm tra an toàn" if passed else "Cần kiểm tra lại"
    disclaimer = final_output.get("safety_disclaimer", "")
    return f"""
    <div class="safety-box">
      <h3>{status}</h3>
      <p>{escape_html(disclaimer)}</p>
    </div>
    """


def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --teal: #078b8f;
          --teal-dark: #056f73;
          --blue: #1267b1;
          --ink: #172033;
          --muted: #667085;
          --line: #d7e1ec;
          --surface: #ffffff;
          --bg: #f7fbfd;
          --danger: #ef4444;
          --danger-bg: #fff4f3;
          --urgent: #b65f00;
          --urgent-bg: #fff7ed;
          --routine: #2563eb;
          --routine-bg: #eff6ff;
          --self: #0f766e;
          --self-bg: #ecfdf5;
        }

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu,
        footer {
          display: none !important;
        }

        .stApp {
          background: var(--bg);
          color: var(--ink);
        }

        .block-container {
          max-width: 1480px;
          padding: 1.2rem 2rem 2rem;
        }

        .topbar {
          display: grid;
          grid-template-columns: 280px 1fr auto;
          align-items: center;
          gap: 24px;
          padding: 6px 0 22px;
          border-bottom: 1px solid var(--line);
          margin-bottom: 22px;
        }

        .brand,
        .nav,
        .actions,
        .welcome-row,
        .result-title-row,
        .triage-card,
        .citation-row {
          display: flex;
          align-items: center;
        }

        .brand {
          gap: 12px;
        }

        .brand-icon,
        .bot-avatar,
        .empty-icon {
          width: 50px;
          height: 50px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          background: linear-gradient(135deg, #dff7f3, #ffffff);
          border: 1px solid #b9e7df;
          color: var(--teal);
          font-weight: 900;
          font-size: 18px;
        }

        .brand-name {
          color: var(--teal);
          font-size: 31px;
          line-height: 1;
          font-weight: 850;
        }

        .brand-subtitle {
          color: var(--muted);
          margin-top: 5px;
          font-size: 14px;
        }

        .nav {
          justify-content: center;
          gap: 28px;
          color: #344054;
          font-weight: 700;
        }

        .nav-item {
          white-space: nowrap;
          padding: 18px 6px;
        }

        .nav-item.active {
          color: var(--teal);
          border-bottom: 3px solid var(--teal);
        }

        .actions {
          justify-content: flex-end;
          gap: 14px;
        }

        .emergency-link,
        .language-pill {
          border-radius: 8px;
          padding: 12px 16px;
          font-weight: 750;
          white-space: nowrap;
          background: var(--surface);
        }

        .emergency-link {
          color: var(--danger);
          border: 1px solid #ff9b9b;
          background: #fff8f8;
        }

        .language-pill {
          border: 1px solid var(--line);
          color: #27364a;
        }

        .profile-dot {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: var(--teal);
          box-shadow: inset 0 -10px 18px rgba(0,0,0,0.08);
        }

        .user-card,
        .result-card,
        .chat-card {
          background: rgba(255, 255, 255, 0.98);
          border: 1px solid var(--line);
          border-radius: 8px;
          box-shadow: 0 10px 28px rgba(17, 24, 39, 0.04);
        }

        .user-card {
          padding: 28px 30px 8px;
          border-bottom: none;
          border-radius: 8px 8px 0 0;
        }

        .welcome-row {
          align-items: flex-start;
          gap: 18px;
        }

        h1, h2, h3, p {
          margin-top: 0;
        }

        h1 {
          font-size: 29px;
          margin-bottom: 10px;
          color: #101828;
          letter-spacing: 0;
        }

        h2 {
          font-size: 20px;
          margin-bottom: 0;
          color: #1d2939;
        }

        h3 {
          font-size: 16px;
          margin-bottom: 12px;
          color: #1d2939;
        }

        p,
        li {
          color: #344054;
          line-height: 1.62;
          font-size: 15px;
        }

        .try-label {
          margin-top: 24px;
          color: var(--muted);
          font-weight: 700;
        }

        div[data-testid="column"] .stButton button {
          background: #ffffff !important;
          border: 1px solid var(--line) !important;
          border-radius: 8px !important;
          color: #1f4164 !important;
          min-height: 44px;
          font-weight: 700;
          box-shadow: none !important;
        }

        div[data-testid="column"] .stButton button:hover {
          border-color: #9bd9d7 !important;
          color: var(--teal) !important;
        }

        div[data-testid="stForm"] {
          background: #ffffff;
          border: 1px solid var(--line);
          border-top: none;
          border-radius: 0 0 8px 8px;
          padding: 10px 30px 26px;
          box-shadow: 0 10px 28px rgba(17, 24, 39, 0.04);
        }

        textarea,
        div[data-baseweb="textarea"] textarea {
          background: #ffffff !important;
          color: var(--ink) !important;
          -webkit-text-fill-color: var(--ink) !important;
          border: 1.5px solid #8cc4ff !important;
          border-radius: 8px !important;
          min-height: 220px !important;
          box-shadow: none !important;
          font-size: 16px !important;
        }

        textarea::placeholder {
          color: #98a2b3 !important;
          opacity: 1 !important;
        }

        .textarea-foot {
          color: #667085;
          font-size: 13px;
          margin-top: -10px;
          margin-bottom: 8px;
        }

        .stFormSubmitButton button {
          border-radius: 8px !important;
          min-height: 48px;
          font-weight: 800 !important;
          box-shadow: none !important;
        }

        .stFormSubmitButton button[kind="primary"] {
          background: linear-gradient(135deg, #07969b, #047d80) !important;
          color: #ffffff !important;
          border: none !important;
        }

        .stFormSubmitButton button:not([kind="primary"]) {
          background: #ffffff !important;
          color: #344054 !important;
          border: 1px solid var(--line) !important;
        }

        .privacy-note {
          color: #718096;
          font-size: 13px;
          text-align: center;
          margin: 14px 0 20px;
        }

        .info-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 18px;
          margin-top: 22px;
        }

        .info-card {
          min-height: 210px;
          background: #ffffff;
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 20px;
        }

        .danger-card {
          background: #fff8f7;
          border-color: #ffd3cf;
        }

        .source-card {
          background: #f9fffd;
        }

        .history-card {
          background: #f8fbff;
        }

        .info-card ul,
        .result-section ul,
        .result-section ol {
          padding-left: 20px;
          margin-bottom: 0;
        }

        .ghost-danger {
          margin-top: 14px;
          border: 1px solid #ff9b9b;
          color: var(--danger);
          background: #ffffff;
          padding: 10px 14px;
          border-radius: 8px;
          font-weight: 750;
        }

        .result-card {
          padding: 24px;
          min-height: 720px;
        }

        .result-title-row {
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 18px;
          color: var(--muted);
          font-size: 13px;
        }

        .triage-card {
          gap: 14px;
          border-radius: 8px;
          padding: 18px;
          border: 1px solid var(--line);
          margin-bottom: 14px;
        }

        .triage-icon {
          width: 44px;
          height: 44px;
          display: grid;
          place-items: center;
          border-radius: 50%;
          font-weight: 900;
          background: rgba(255,255,255,0.65);
        }

        .triage-label {
          font-size: 22px;
          font-weight: 850;
        }

        .triage-sub {
          margin-top: 5px;
          font-weight: 700;
          font-size: 14px;
        }

        .confidence-pill {
          margin-left: auto;
          border: 1px solid currentColor;
          border-radius: 8px;
          padding: 8px 11px;
          font-size: 13px;
          font-weight: 750;
          background: rgba(255,255,255,0.6);
        }

        .triage-emergency {
          background: var(--danger-bg);
          border-color: #ff9d98;
          color: var(--danger);
        }

        .triage-urgent {
          background: var(--urgent-bg);
          border-color: #fed7aa;
          color: var(--urgent);
        }

        .triage-routine {
          background: var(--routine-bg);
          border-color: #bfdbfe;
          color: var(--routine);
        }

        .triage-self {
          background: var(--self-bg);
          border-color: #a7f3d0;
          color: var(--self);
        }

        .summary-box {
          background: #fff7f7;
          color: #8a1f1f;
          border: 1px solid #ffd5d5;
          border-radius: 8px;
          padding: 14px 16px;
          margin-bottom: 22px;
          line-height: 1.6;
        }

        .result-section {
          margin: 22px 0;
        }

        .result-section li {
          margin: 8px 0;
        }

        .citation-row {
          gap: 12px;
          padding: 10px 0;
          border-bottom: 1px solid #edf2f7;
          text-decoration: none;
          color: var(--ink);
        }

        .citation-row small {
          display: block;
          color: var(--muted);
          margin-top: 3px;
          line-height: 1.35;
        }

        .source-badge {
          width: 58px;
          min-width: 58px;
          height: 34px;
          border-radius: 4px;
          background: var(--blue);
          color: white;
          display: grid;
          place-items: center;
          font-size: 12px;
          font-weight: 900;
        }

        .safety-box {
          background: #f1fbf8;
          border: 1px solid #c9eee5;
          border-radius: 8px;
          padding: 16px;
          margin-top: 24px;
        }

        .empty-state {
          text-align: center;
          padding: 110px 34px 120px;
        }

        .empty-icon {
          margin: 0 auto 20px;
        }

        .chat-card {
          margin-top: 22px;
          padding: 22px;
        }

        .chat-row {
          display: grid;
          grid-template-columns: 90px 1fr;
          gap: 12px;
          margin: 12px 0;
          align-items: start;
        }

        .chat-role {
          color: var(--muted);
          font-size: 13px;
          font-weight: 850;
          padding-top: 9px;
        }

        .chat-bubble {
          border-radius: 8px;
          padding: 12px 14px;
          line-height: 1.55;
          border: 1px solid var(--line);
        }

        .user-message .chat-bubble {
          background: #eef8ff;
        }

        .assistant-message .chat-bubble {
          background: #f5fffc;
        }

        @media (max-width: 1100px) {
          .topbar {
            grid-template-columns: 1fr;
          }

          .nav,
          .actions {
            justify-content: flex-start;
            flex-wrap: wrap;
          }

          .info-grid {
            grid-template-columns: 1fr;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
