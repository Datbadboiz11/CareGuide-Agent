# Triage Labels

## 1. Mục đích

Tài liệu này định nghĩa 4 nhãn triage dùng trong CareGuide Agent. Các nhãn này không phải chẩn đoán y khoa. Chúng chỉ thể hiện mức độ khuyến nghị chăm sóc ban đầu dựa trên triệu chứng, red flags, thời gian, mức độ nặng và yếu tố nguy cơ.

Nguyên tắc quan trọng nhất:

```text
Không bỏ sót trường hợp nguy hiểm.
```

Khi thông tin chưa chắc chắn nhưng có dấu hiệu rủi ro, hệ thống phải chọn nhãn an toàn hơn.

## 2. Danh sách nhãn

| Label | Ý nghĩa | Mục tiêu phản hồi |
| --- | --- | --- |
| `self_care` | Theo dõi tại nhà | Hướng dẫn theo dõi, tự chăm sóc an toàn, red flags cần chú ý |
| `routine_visit` | Đặt lịch khám | Khuyến nghị khám không khẩn cấp nếu triệu chứng kéo dài/tái diễn |
| `urgent_visit` | Đi khám sớm | Khuyến nghị đi khám trong thời gian sớm vì có yếu tố đáng lo |
| `emergency` | Cấp cứu | Khuyến nghị tìm hỗ trợ cấp cứu ngay |

## 3. `self_care`

### Định nghĩa

`self_care` áp dụng khi triệu chứng có vẻ nhẹ, mới xuất hiện trong thời gian ngắn, không có red flag, không có yếu tố nguy cơ rõ ràng và người dùng có thể theo dõi tại nhà trong 24-48 giờ.

### Điều kiện gợi ý

- Triệu chứng nhẹ hoặc vừa.
- Thời gian ngắn.
- Không có khó thở, đau ngực, lơ mơ, co giật, ngất hoặc dấu hiệu nặng.
- Không có bệnh nền nặng được khai báo.
- Không thuộc nhóm nguy cơ cao hoặc chưa có dấu hiệu làm tăng rủi ro.

### Ví dụ

- Sốt nhẹ, ho nhẹ, đau họng 1-2 ngày, không khó thở.
- Đau đầu nhẹ sau thiếu ngủ, không yếu liệt, không nôn ói nhiều, không rối loạn ý thức.
- Đau bụng nhẹ thoáng qua, không sốt cao, không nôn ra máu, không đau dữ dội.

### Phản hồi cần có

- Có thể theo dõi tại nhà.
- Nêu kế hoạch theo dõi 24-48 giờ.
- Nêu dấu hiệu cần đi khám ngay.
- Không khẳng định là bệnh nhẹ chắc chắn.

## 4. `routine_visit`

### Định nghĩa

`routine_visit` áp dụng khi triệu chứng không có dấu hiệu cấp cứu nhưng kéo dài, tái diễn, ảnh hưởng sinh hoạt hoặc cần đánh giá chuyên môn không khẩn cấp.

### Điều kiện gợi ý

- Triệu chứng kéo dài nhiều ngày hoặc nhiều tuần.
- Triệu chứng tái diễn nhiều lần.
- Triệu chứng ảnh hưởng chất lượng sống nhưng không có red flag.
- Có bệnh nền cần bác sĩ theo dõi nhưng chưa có dấu hiệu nặng.
- Người dùng cần tư vấn chuyên môn để xác định nguyên nhân.

### Ví dụ

- Ho kéo dài hơn 1-2 tuần nhưng không khó thở, không đau ngực.
- Đau dạ dày tái diễn, không nôn ra máu, không đi ngoài phân đen.
- Mất ngủ kéo dài ảnh hưởng sinh hoạt.

### Phản hồi cần có

- Khuyến nghị đặt lịch khám.
- Nêu thông tin nên chuẩn bị trước khi khám.
- Nêu red flags cần đi khám sớm hoặc cấp cứu.

## 5. `urgent_visit`

### Định nghĩa

`urgent_visit` áp dụng khi triệu chứng đáng lo, đang nặng lên, có yếu tố nguy cơ hoặc có thể cần đánh giá y tế sớm, nhưng chưa đủ tiêu chí cấp cứu ngay.

### Điều kiện gợi ý

- Triệu chứng vừa đến nặng và đang nặng lên.
- Sốt cao hoặc sốt kéo dài.
- Đau nhiều, mất nước, nôn ói nhiều.
- Người dùng thuộc nhóm nguy cơ cao: trẻ nhỏ, người già, phụ nữ mang thai, người suy giảm miễn dịch, người có bệnh nền tim phổi, tiểu đường hoặc bệnh mạn tính nặng.
- Có chỉ số sinh tồn bất thường nhưng chưa rõ mức cấp cứu.
- Thiếu thông tin quan trọng khiến không thể loại trừ rủi ro.

### Ví dụ

- Sốt cao kéo dài, mệt nhiều nhưng chưa lơ mơ.
- Ho, sốt, đau ngực nhẹ hoặc khó thở nhẹ cần kiểm tra sớm.
- Đau bụng tăng dần, sốt, nôn nhiều.
- Người có bệnh nền tim phổi bị triệu chứng hô hấp mới.

### Phản hồi cần có

- Khuyến nghị đi khám sớm.
- Nêu lý do vì sao cần khám sớm.
- Nêu dấu hiệu nếu xuất hiện thì chuyển sang cấp cứu.
- Không làm người dùng yên tâm quá mức.

## 6. `emergency`

### Định nghĩa

`emergency` áp dụng khi có dấu hiệu nguy hiểm cần tìm hỗ trợ cấp cứu ngay hoặc đến cơ sở y tế khẩn cấp.

### Red flags cấp cứu tối thiểu

Hệ thống phải ưu tiên `emergency` nếu có một hoặc nhiều dấu hiệu sau:

- Khó thở nặng, thở rít, tím tái hoặc SpO2 thấp nếu được khai báo.
- Đau ngực dữ dội, đau ngực kèm khó thở, vã mồ hôi, ngất.
- Lơ mơ, mất ý thức, co giật, yếu liệt nửa người, nói khó đột ngột.
- Sốt cao kèm cứng cổ, lơ mơ, phát ban xuất huyết hoặc co giật.
- Đau đầu dữ dội đột ngột hoặc đau đầu kèm yếu liệt/rối loạn ý thức.
- Đau bụng dữ dội, bụng cứng, nôn ra máu hoặc đi ngoài phân đen.
- Chảy máu không cầm.
- Chấn thương nặng.
- Dấu hiệu sốc: da lạnh ẩm, vã mồ hôi, choáng, ngất, mạch rất nhanh nếu được khai báo.
- Triệu chứng nghiêm trọng ở trẻ nhỏ, người già, phụ nữ mang thai hoặc người có bệnh nền nặng.

### Phản hồi cần có

- Nói rõ đây là tình huống cần hỗ trợ cấp cứu ngay.
- Khuyến nghị gọi cấp cứu hoặc đến cơ sở y tế gần nhất.
- Không đưa kế hoạch theo dõi tại nhà như lựa chọn chính.
- Không hỏi thêm quá nhiều trước khi khuyến nghị cấp cứu.
- Có disclaimer ngắn.

## 7. Quy tắc nâng cấp nhãn

Hệ thống phải nâng nhãn theo hướng an toàn hơn trong các trường hợp:

- `self_care` -> `routine_visit`: triệu chứng kéo dài, tái diễn hoặc ảnh hưởng sinh hoạt.
- `routine_visit` -> `urgent_visit`: triệu chứng nặng lên, có bệnh nền hoặc có yếu tố nguy cơ.
- `urgent_visit` -> `emergency`: có red flag nghiêm trọng.
- Bất kỳ nhãn nào -> `urgent_visit` hoặc `emergency`: thông tin thiếu nhưng không thể loại trừ rủi ro đáng kể.

## 8. Quy tắc xử lý thiếu thông tin

Nếu thiếu thông tin nhưng chưa có red flag rõ:

- Questioning Agent hỏi tối đa 3-5 câu quan trọng nhất.
- Ưu tiên hỏi tuổi, thời gian triệu chứng, mức độ, bệnh nền, thuốc đang dùng và red flags liên quan.

Nếu thiếu thông tin trong tình huống có vẻ rủi ro:

- Không được trả lời chắc chắn là an toàn.
- Khuyến nghị đi khám sớm hoặc cấp cứu tùy mức độ.

## 9. Output triage chuẩn

Triage Agent nên trả về cấu trúc:

```json
{
  "triage_level": "urgent_visit",
  "confidence": "medium",
  "main_reasons": [
    "Sốt cao kéo dài",
    "Triệu chứng đang nặng lên"
  ],
  "red_flags": [],
  "missing_info": [
    "Tuổi",
    "Bệnh nền"
  ],
  "recommended_action": "Nên đi khám sớm để được đánh giá trực tiếp."
}
```
