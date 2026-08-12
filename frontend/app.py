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

st.set_page_config(page_title="RAG chatbot — hỏi đáp tài liệu nội bộ", page_icon="📄")


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

question = st.text_input(
    "Câu hỏi", placeholder="Chính sách nghỉ phép năm là bao nhiêu ngày?", key="question"
)

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
