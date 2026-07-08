const triageLabels = {
  emergency: "Cần cấp cứu",
  urgent_visit: "Cần khám sớm",
  routine_visit: "Nên đặt lịch khám",
  self_care: "Theo dõi tại nhà",
};

const triageClasses = {
  emergency: "triage-emergency",
  urgent_visit: "triage-urgent",
  routine_visit: "triage-routine",
  self_care: "triage-self",
};

const messages = [];

const input = document.querySelector("#symptom-input");
const counter = document.querySelector("#counter");
const form = document.querySelector("#symptom-form");
const submitButton = document.querySelector(".submit-button");
const resetButton = document.querySelector("#reset-session");
const chatCard = document.querySelector("#chat-card");
const chatList = document.querySelector("#chat-list");
const emptyState = document.querySelector("#empty-state");
const loadingState = document.querySelector("#loading-state");
const resultContent = document.querySelector("#result-content");
const resultTime = document.querySelector("#result-time");
const safetyText = document.querySelector("#safety-text");

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt || "";
    updateCounter();
    input.focus();
  });
});

input.addEventListener("input", updateCounter);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) {
    input.focus();
    return;
  }

  messages.push({ role: "user", content: text });
  input.value = "";
  updateCounter();
  renderChat();
  setLoading(true);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const finalOutput = payload.final_output || {};
    renderResult(finalOutput);
    messages.push({
      role: "assistant",
      content: buildAssistantSummary(finalOutput),
    });
    renderChat();
  } catch (error) {
    renderError(error);
  } finally {
    setLoading(false);
  }
});

resetButton.addEventListener("click", () => {
  messages.length = 0;
  chatList.innerHTML = "";
  chatCard.hidden = true;
  resultContent.hidden = true;
  emptyState.hidden = false;
  resultTime.textContent = "Sẵn sàng";
  safetyText.textContent =
    "Đây chỉ là đánh giá ban đầu dựa trên thông tin bạn cung cấp và không thay thế chẩn đoán từ bác sĩ.";
  input.value = "";
  updateCounter();
  input.focus();
});

function updateCounter() {
  counter.textContent = `${input.value.length}/1000`;
}

function setLoading(isLoading) {
  loadingState.hidden = !isLoading;
  submitButton.disabled = isLoading;
  submitButton.innerHTML = isLoading
    ? "Đang phân tích..."
    : 'Kiểm tra triệu chứng <span>➤</span>';
  if (isLoading) {
    emptyState.hidden = true;
  }
}

function renderResult(finalOutput) {
  emptyState.hidden = true;
  resultContent.hidden = false;
  resultTime.textContent = `${new Date().toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  })} hôm nay`;

  const triageLevel = finalOutput.triage_level || "self_care";
  const triageLabel = triageLabels[triageLevel] || triageLevel;
  const triageCard = document.querySelector("#triage-card");
  triageCard.className = `triage-card ${triageClasses[triageLevel] || "triage-self"}`;

  document.querySelector("#triage-label").textContent = triageLabel;
  document.querySelector("#triage-subtitle").textContent = `Mức độ: ${triageLabel.toUpperCase()}`;
  document.querySelector("#confidence-pill").textContent = `Độ tin cậy: ${
    finalOutput.confidence || "-"
  }`;
  document.querySelector("#recommendation-alert").textContent =
    finalOutput.recommendation || "Chưa có khuyến nghị.";
  document.querySelector("#summary-text").textContent =
    finalOutput.user_summary || "Chưa có tóm tắt.";

  renderList("#care-steps", finalOutput.care_advice || []);
  renderOptionalList("#red-flags-section", "#red-flags", finalOutput.red_flags || []);
  renderTopics(finalOutput.related_health_topics || []);
  renderCitations(finalOutput.citations || []);

  safetyText.textContent =
    finalOutput.safety_disclaimer ||
    "Đây chỉ là đánh giá ban đầu dựa trên thông tin bạn cung cấp và không thay thế chẩn đoán từ bác sĩ.";
}

function renderList(selector, items) {
  const list = document.querySelector(selector);
  list.innerHTML = "";
  const cleanItems = items.filter(Boolean);
  if (cleanItems.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Theo dõi triệu chứng và tìm trợ giúp y tế nếu tình trạng nặng lên.";
    list.appendChild(li);
    return;
  }

  cleanItems.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
}

function renderOptionalList(sectionSelector, listSelector, items) {
  const section = document.querySelector(sectionSelector);
  const cleanItems = items.filter(Boolean);
  section.hidden = cleanItems.length === 0;
  if (section.hidden) {
    return;
  }
  renderList(listSelector, cleanItems);
}

function renderTopics(topics) {
  const section = document.querySelector("#topics-section");
  const list = document.querySelector("#topic-list");
  const cleanTopics = topics.filter(Boolean).slice(0, 6);
  section.hidden = cleanTopics.length === 0;
  list.innerHTML = "";
  cleanTopics.forEach((topic) => {
    const span = document.createElement("span");
    span.textContent = topic;
    list.appendChild(span);
  });
}

function renderCitations(citations) {
  const list = document.querySelector("#citations-list");
  list.innerHTML = "";
  const cleanCitations = citations.filter(Boolean).slice(0, 5);
  if (cleanCitations.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "Chưa có nguồn tham khảo cho lượt tư vấn này.";
    list.appendChild(empty);
    return;
  }

  cleanCitations.forEach((citation) => {
    const link = document.createElement("a");
    link.className = "citation-row";
    link.href = citation.url || "#";
    link.target = "_blank";
    link.rel = "noreferrer";

    const badge = document.createElement("span");
    badge.className = "source-badge";
    badge.textContent = citation.source || "SRC";

    const text = document.createElement("span");
    const title = document.createElement("strong");
    title.textContent = citation.title || "Nguồn tham khảo";
    const section = document.createElement("small");
    section.textContent = citation.section_heading || citation.url || "";
    text.append(title, section);

    link.append(badge, text);
    list.appendChild(link);
  });
}

function renderChat() {
  chatCard.hidden = messages.length === 0;
  chatList.innerHTML = "";
  messages.slice(-10).forEach((message) => {
    const row = document.createElement("div");
    row.className = `chat-row ${message.role === "user" ? "user-message" : "assistant-message"}`;

    const role = document.createElement("div");
    role.className = "chat-role";
    role.textContent = message.role === "user" ? "Bạn" : "CareGuide";

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = message.content;

    row.append(role, bubble);
    chatList.appendChild(row);
  });
}

function buildAssistantSummary(finalOutput) {
  const triageLabel = triageLabels[finalOutput.triage_level] || finalOutput.triage_level || "Chưa rõ";
  const recommendation = finalOutput.recommendation || "Tôi đã cập nhật đánh giá dựa trên thông tin mới.";
  return `Mức độ: ${triageLabel}. ${recommendation}`;
}

function renderError(error) {
  resultContent.hidden = true;
  emptyState.hidden = false;
  resultTime.textContent = "Có lỗi";
  safetyText.textContent =
    "Không thể phân tích lúc này. Vui lòng kiểm tra server demo hoặc thử lại sau.";
  messages.push({
    role: "assistant",
    content: `Xin lỗi, CareGuide chưa thể phân tích lúc này. Chi tiết kỹ thuật: ${error.message}`,
  });
  renderChat();
}

updateCounter();
