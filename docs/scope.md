# Scope

## 1. Mục đích hệ thống

CareGuide Agent là hệ thống multi-agent hỗ trợ sàng lọc triệu chứng sức khỏe ban đầu và lập kế hoạch theo dõi trong 24-48 giờ cho người dùng phổ thông.

Hệ thống nhận mô tả triệu chứng bằng tiếng Việt, trích xuất thông tin y tế liên quan, phát hiện dấu hiệu nguy hiểm, phân loại mức độ ưu tiên chăm sóc, truy xuất nguồn y tế đáng tin cậy và tạo phản hồi an toàn, dễ hiểu.

CareGuide Agent không phải là bác sĩ, không thay thế tư vấn y tế chuyên nghiệp và không xử lý cấp cứu thực tế.

## 2. Người dùng mục tiêu

Người dùng mục tiêu là người phổ thông muốn được hỗ trợ định hướng ban đầu khi gặp triệu chứng sức khỏe, ví dụ:

- Không chắc có cần đi khám không.
- Không biết triệu chứng nào cần theo dõi.
- Không biết dấu hiệu nào là nguy hiểm.
- Muốn có bản tóm tắt ngắn để mang đi khám.

Hệ thống không nhắm tới bác sĩ, dược sĩ, nhân viên y tế hoặc đơn vị cấp cứu chuyên nghiệp như một công cụ ra quyết định lâm sàng chính thức.

## 3. Phạm vi chức năng core

Phiên bản core phải hỗ trợ các chức năng sau:

1. Nhận input tiếng Việt dạng tự nhiên.
2. Trích xuất triệu chứng, thời gian, mức độ, phủ định và chỉ số sinh tồn nếu có.
3. Chuẩn hóa triệu chứng tiếng Việt sang thuật ngữ y tế tiếng Anh.
4. Hỏi thêm thông tin còn thiếu nếu thông tin ảnh hưởng tới triage.
5. Phát hiện red flags bằng rule.
6. Phân loại mức độ chăm sóc thành 4 nhãn:
   - `self_care`
   - `routine_visit`
   - `urgent_visit`
   - `emergency`
7. Truy xuất thông tin từ nguồn y tế đáng tin cậy.
8. Tạo kế hoạch theo dõi 24-48 giờ.
9. Tạo tóm tắt cho bác sĩ.
10. Kiểm tra an toàn đầu ra cuối bằng Safety Guardrail Agent.
11. Trả lời bằng tiếng Việt, có cấu trúc, có disclaimer và có nguồn khi đưa thông tin y tế.

## 4. Ngoài phạm vi

Hệ thống không làm các việc sau:

- Không chẩn đoán bệnh chắc chắn.
- Không kê đơn thuốc.
- Không đưa liều dùng thuốc cụ thể.
- Không đề xuất tự dùng thuốc kê đơn.
- Không thay đổi thuốc đang dùng của người dùng.
- Không diễn giải xét nghiệm chuyên sâu như bác sĩ.
- Không thay thế khám trực tiếp.
- Không xử lý cấp cứu như tổng đài y tế hoặc bệnh viện.
- Không lưu dữ liệu cá nhân nhạy cảm trong bản demo public.
- Không sử dụng dữ liệu bệnh nhân thật chưa được cấp quyền.

## 5. Nguyên tắc phản hồi

Phản hồi cuối phải:

- Nêu rõ mức khuyến nghị chăm sóc.
- Tóm tắt thông tin đã ghi nhận.
- Nêu kế hoạch theo dõi 24-48 giờ.
- Nêu dấu hiệu cần đi khám ngay hoặc cấp cứu.
- Có tóm tắt ngắn cho bác sĩ.
- Có disclaimer.
- Có nguồn tham khảo nếu dùng thông tin từ RAG.

Phản hồi cuối không được:

- Khẳng định người dùng mắc một bệnh cụ thể.
- Dùng ngôn ngữ chắc chắn như "bạn bị", "chắc chắn là", "không nguy hiểm" khi chưa đủ căn cứ.
- Kê tên thuốc kèm liều, thời gian dùng hoặc phác đồ.
- Trấn an quá mức khi có dấu hiệu nguy hiểm.
- Khuyên người dùng chờ đợi nếu có dấu hiệu cấp cứu.

## 6. Nguyên tắc ưu tiên an toàn

Trong các trường hợp không chắc chắn, hệ thống phải ưu tiên an toàn:

```text
Nếu có red flag nghiêm trọng, ưu tiên emergency.
Nếu có yếu tố nguy cơ hoặc triệu chứng nặng lên, ưu tiên urgent_visit.
Nếu thiếu thông tin quan trọng, hỏi thêm hoặc khuyến nghị đi khám nếu rủi ro không thể loại trừ.
```

## 7. Dữ liệu được phép dùng trong core

Nguồn dữ liệu ưu tiên:

- MedlinePlus.
- NHS.
- CDC.
- DDXPlus cho symptom vocabulary và synthetic cases.
- Bộ test tiếng Việt tự tạo.

Nguồn dữ liệu có thể dùng ở bản mở rộng:

- Synthea cho hồ sơ bệnh nhân giả lập.
- MedQuAD cho QA y tế phụ trợ.
- NHAMCS cho EDA hoặc ML triage nếu mapping phù hợp.
- MedDialog cho tham khảo cách hỏi bệnh, không dùng làm nguồn lời khuyên y tế.

## 8. Định nghĩa hoàn thành bước core

Core được coi là hoàn thành khi có:

- LangGraph workflow chạy end-to-end.
- Ít nhất 8 agent hoạt động.
- Rule-based triage 4 nhãn.
- RAG có citation từ nguồn chính thống.
- Safety Guardrail Agent kiểm tra đầu ra cuối.
- Streamlit demo chạy được.
- Bộ test tiếng Việt tối thiểu 100 case.
- Evaluation cho parser, triage, RAG và safety.
