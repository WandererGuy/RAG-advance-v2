"""Streamlit demo UI. A client of the API — it holds no business logic and touches no database.

Deliberately single-file and plain (PLAN.md Phase 5: "it doesn't need to look good"). Everything
it shows comes from `POST /chat` and `GET /documents`; if a field is not in the API response it
is not shown, so the UI cannot quietly become a second source of truth.

Run:  make ui        (API must already be running: make api)
"""

from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")

# Ingest is synchronous and embedding a long PDF is slow; the answer path also waits on the
# provider. Both need a timeout well above a default 30s or the UI reports failure on a
# request that is still succeeding server-side.
CHAT_TIMEOUT = 120
UPLOAD_TIMEOUT = 600

# Tạm ẩn ô upload trong sidebar. Đặt lại True để khôi phục — API `POST /documents` không đổi.
SHOW_UPLOAD = False

st.set_page_config(page_title="RAG chatbot — hỏi đáp tài liệu nội bộ", page_icon="📄")

# Câu hỏi gợi ý, nhóm theo tài liệu nguồn.
#
# Mỗi câu được viết từ một mục có thật trong tài liệu tương ứng, nên nguồn hiển thị bên cạnh là
# tài liệu *dự kiến* chứa câu trả lời — nó KHÔNG đến từ API và không phải kết quả truy xuất. Sau
# khi hỏi, trích dẫn thật do API trả về mới là nguồn có thẩm quyền; đối chiếu hai bên chính là
# cách nhanh nhất để thấy retriever đúng hay sai.
SUGGESTED_QUESTIONS: list[tuple[str, str, list[str]]] = [
    (
        "01_so_tay_nhan_vien.pdf",
        "Sổ tay nhân viên (HR-HB-01)",
        [
            "Khung giờ bắt buộc có mặt tại công ty là từ mấy giờ đến mấy giờ?",
            "Nghỉ việc thì phải báo trước bao nhiêu ngày?",
            "Ngân sách đào tạo mỗi năm của một nhân viên là bao nhiêu?",
        ],
    ),
    (
        "02_quy_che_luong_thuong_phuc_loi.pdf",
        "Quy chế lương, thưởng và phúc lợi (HR-CB-02)",
        [
            "Làm thêm giờ vào ngày lễ được tính hệ số bao nhiêu?",
            "Thưởng giới thiệu ứng viên cho vị trí kỹ sư là bao nhiêu tiền?",
            "Bảo hiểm sức khỏe chi trả ngoại trú cho nhân viên tối đa bao nhiêu một năm?",
        ],
    ),
    (
        "03_khung_cap_bac_va_danh_gia.pdf",
        "Khung cấp bậc và đánh giá hiệu suất (HR-PF-03)",
        [
            "Thăng cấp thì được tăng lương tối thiểu bao nhiêu phần trăm?",
            "Kế hoạch cải thiện hiệu suất (PIP) kéo dài bao lâu?",
            "Kết quả công việc và giá trị hành vi có trọng số thế nào khi xếp loại?",
        ],
    ),
    (
        "04_nghi_phep_va_lam_viec_tu_xa.pdf",
        "Nghỉ phép và làm việc từ xa (HR-LV-04)",
        [
            "Một tuần phải lên văn phòng tối thiểu mấy ngày?",
            "Nghỉ phép năm chưa dùng hết có được chuyển sang năm sau không?",
            "Kết hôn thì được nghỉ mấy ngày hưởng nguyên lương?",
        ],
    ),
    (
        "05_bao_mat_thong_tin_va_thiet_bi.pdf",
        "Bảo mật thông tin và thiết bị (HR-IT-05)",
        [
            "Mất laptop công ty thì phải báo trong bao lâu?",
            "Mật khẩu tài khoản công việc yêu cầu tối thiểu bao nhiêu ký tự?",
            "Sao chép dữ liệu khách hàng ra ngoài bị xử lý thế nào?",
        ],
    ),
    (
        "06_tuyen_dung_va_thu_viec.pdf",
        "Tuyển dụng và thử việc (HR-RC-06)",
        [
            "Thời gian thử việc là bao lâu và hưởng bao nhiêu phần trăm lương?",
            "Thực tập sinh được trợ cấp bao nhiêu một tháng?",
            "Nhân viên mới phải hoàn thành khóa đào tạo bảo mật trong bao lâu?",
        ],
    ),
    (
        "07_quy_tac_ung_xu.pdf",
        "Quy tắc ứng xử và phòng chống quấy rối (HR-CD-07)",
        [
            "Được nhận quà tặng trị giá bao nhiêu mà không cần khai báo?",
            "Báo cáo vi phạm thì bao lâu Ban Nhân sự phải hoàn tất điều tra?",
            "Làm thêm việc bên ngoài có phải khai báo không?",
        ],
    ),
    (
        "08_cong_tac_phi.pdf",
        "Công tác phí và hoàn chi phí (HR-EX-08)",
        [
            "Đi công tác Hà Nội thì hạn mức khách sạn một đêm là bao nhiêu?",
            "Nộp đề nghị hoàn chi phí muộn nhất bao nhiêu ngày sau chuyến công tác?",
            "Những chi phí nào không được hoàn?",
        ],
    ),
]


def api_get(path: str, **params: Any) -> Any:
    response = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def detail_of(exc: requests.HTTPError) -> str:
    """The API's `detail` if there is one, else the raw status line.

    The routes put the actionable reason in `detail` — an unsupported file type, a document
    with no text layer — and dropping it would leave the user with a bare 4xx.
    """
    try:
        payload = exc.response.json()
    except ValueError:
        return str(exc)
    detail = payload.get("detail", str(exc))
    return detail if isinstance(detail, str) else str(detail)


# --- sidebar: the corpus ---------------------------------------------------------------

with st.sidebar:
    st.header("Tài liệu")

    if SHOW_UPLOAD:
        upload = st.file_uploader("Tải lên PDF hoặc DOCX", type=["pdf", "docx"])
        if upload is not None and st.button("Nạp tài liệu", use_container_width=True):
            with st.spinner("Đang nạp — trích xuất, chia chunk và embed, có thể mất một lúc…"):
                try:
                    response = requests.post(
                        f"{API_BASE}/documents",
                        files={"file": (upload.name, upload.getvalue())},
                        timeout=UPLOAD_TIMEOUT,
                    )
                    response.raise_for_status()
                    result = response.json()
                except requests.HTTPError as exc:
                    st.error(detail_of(exc))
                except requests.RequestException as exc:
                    st.error(f"Không gọi được API: {exc}")
                else:
                    if result["status"] == "skipped":
                        st.info(
                            f"`{result['filename']}` đã có trong hệ thống "
                            f"({result['chunk_count']} chunk) — nội dung không đổi."
                        )
                    else:
                        st.success(
                            f"Đã nạp `{result['filename']}`: {result['chunk_count']} chunk"
                            + (f", {result['page_count']} trang" if result["page_count"] else "")
                        )

        st.divider()
    try:
        documents = api_get("/documents")
    except requests.RequestException as exc:
        st.error(f"Không đọc được danh sách tài liệu: {exc}")
        documents = []

    st.caption(f"{len(documents)} tài liệu")
    for document in documents:
        icon = {"done": "✅", "failed": "❌", "processing": "⏳", "pending": "⏸"}.get(
            document["status"], "•"
        )
        st.write(f"{icon} **{document['filename']}** — {document['chunk_count']} chunk")
        if document["error_message"]:
            st.caption(f"↳ {document['error_message']}")


# --- main: ask a question --------------------------------------------------------------

st.title("📄 Hỏi đáp tài liệu nội bộ")
st.caption(
    "Đặt câu hỏi bằng tiếng Việt. Câu trả lời luôn kèm trích dẫn "
    "`[tên tài liệu, p.số trang]` lấy từ chính tài liệu."
)

# --- suggested questions -----------------------------------------------------------------
#
# Rendered *before* the text input: Streamlit forbids assigning to a widget's session-state key
# after that widget exists, so a click has to seed `question` and rerun, letting the input render
# with the new value already in place.

if "question" not in st.session_state:
    st.session_state["question"] = ""


def ask_suggested(text: str) -> None:
    st.session_state["question"] = text
    st.session_state["asked_from"] = text


with st.expander(
    "💡 Câu hỏi gợi ý — theo từng tài liệu", expanded=not st.session_state["question"]
):
    st.caption(
        "Bấm một câu để điền vào ô hỏi. Tài liệu ghi kèm là nơi *dự kiến* chứa câu trả lời — "
        "hãy so với phần Trích dẫn của câu trả lời để xem hệ thống có tìm đúng tài liệu không."
    )
    for filename, title, questions in SUGGESTED_QUESTIONS:
        st.markdown(f"**{title}**")
        st.caption(f"📄 {filename}")
        for suggestion in questions:
            st.button(
                suggestion,
                key=f"suggest::{filename}::{suggestion}",
                use_container_width=True,
                on_click=ask_suggested,
                args=(suggestion,),
            )
        st.divider()

question = st.text_input(
    "Câu hỏi", placeholder="Chính sách nghỉ phép năm là bao nhiêu ngày?", key="question"
)

# The document a suggestion promised, shown only while its question is still untouched in the box.
expected_source = next(
    (
        f"{title} — `{filename}`"
        for filename, title, questions in SUGGESTED_QUESTIONS
        if question in questions
    ),
    None,
)
if expected_source:
    st.caption(f"🔎 Câu hỏi gợi ý này được lấy từ: {expected_source}")

if st.button("Hỏi", type="primary") and question.strip():
    with st.spinner("Đang tìm trong tài liệu…"):
        try:
            response = requests.post(
                f"{API_BASE}/chat", json={"question": question}, timeout=CHAT_TIMEOUT
            )
            response.raise_for_status()
            answer = response.json()
        except requests.HTTPError as exc:
            st.error(detail_of(exc))
            answer = None
        except requests.RequestException as exc:
            st.error(f"Không gọi được API: {exc}")
            answer = None

    if answer is not None:
        if answer["refused"]:
            # A refusal is the correct answer when the corpus does not cover the question, and
            # it is styled as information rather than as an error on purpose.
            st.warning(answer["answer"])
        else:
            st.markdown(answer["answer"])

        supported = [c for c in answer["citations"] if c["supported"]]
        unsupported = [c for c in answer["citations"] if not c["supported"]]

        if expected_source and supported:
            # Only a hint about retrieval, never a verdict on the answer: a question can be
            # answered correctly from a different document than the one that inspired it.
            expected_file = expected_source.rsplit("`", 2)[-2]
            cited_files = {c["filename"] for c in supported}
            if expected_file in cited_files:
                st.success(f"✅ Trích dẫn có `{expected_file}` — đúng tài liệu dự kiến.")
            else:
                st.info(
                    f"ℹ️ Câu trả lời trích từ {', '.join(f'`{f}`' for f in sorted(cited_files))}, "
                    f"khác tài liệu dự kiến `{expected_file}`."
                )

        if supported:
            st.subheader("Trích dẫn")
            for citation in supported:
                page = citation["page_no"]
                label = f"{citation['filename']}" + (f" — trang {page}" if page else "")
                with st.expander(label):
                    st.write(citation["snippet"] or "(không có đoạn trích)")
                    st.caption(f"chunk_id = {citation['chunk_id']}")

        if unsupported:
            # Never rendered as a normal source: these name a document/page that was not in the
            # model's own context, which is a fabricated citation.
            st.error(
                "⚠️ Trích dẫn không đối chiếu được với tài liệu đã truy xuất "
                "(không nên tin): "
                + ", ".join(
                    f"[{c['filename']}, p.{c['page_no']}]" for c in unsupported
                )
            )

        st.caption(
            f"pipeline `{answer['pipeline_name']}` · {answer['latency_ms']} ms · "
            f"{len(answer['chunk_ids'])} chunk được truy xuất · query_id "
            f"{answer['query_id'] if answer['query_id'] is not None else '(không ghi được)'}"
        )
