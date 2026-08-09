rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py            # Settings + PipelineConfig (đọc env / yaml)
│   │   │   ├── logging.py
│   │   │   └── exceptions.py        # domain exceptions
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── routes/
│   │   │           ├── chat.py
│   │   │           ├── conversations.py
│   │   │           └── documents.py     # upload / ingest
│   │   ├── schemas/                 # Pydantic DTO (API contract)
│   │   ├── models/                  # SQLAlchemy ORM
│   │   ├── repositories/
│   │   │   ├── conversation_repo.py
│   │   │   ├── message_repo.py
│   │   │   └── document_repo.py
│   │   ├── services/
│   │   │   ├── chat_service.py      # orchestration, không biết HTTP
│   │   │   └── ingest_service.py
│   │   ├── llm/
│   │   │   ├── client.py            # provider wrapper, retry, streaming
│   │   │   ├── memory.py            # summarize / truncate history
│   │   │   ├── prompts/             # .jinja hoặc .txt, có version
│   │   │   ├── tools/               # function calling
│   │   │   └── rag/
│   │   │       ├── chunking.py
│   │   │       ├── embedder.py
│   │   │       ├── vector_store.py  # interface + impl (pgvector/qdrant)
│   │   │       ├── retrievers/
│   │   │       │   ├── base.py      # Retriever protocol
│   │   │       │   ├── dense.py
│   │   │       │   ├── bm25.py
│   │   │       │   ├── hybrid.py
│   │   │       │   └── reranker.py
│   │   │       └── pipelines/       # ★ đơn vị được eval
│   │   │           ├── base.py      # RAGPipeline protocol
│   │   │           ├── registry.py  # "naive-v1" -> NaiveV1
│   │   │           ├── naive_v1.py
│   │   │           └── hybrid_v2.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── base.py
│   │   └── workers/                 # ingest bất đồng bộ
│   │
│   ├── eval/
│   │   ├── datasets/
│   │   │   ├── golden_qa.v1.jsonl   # question, ground_truth, relevant_doc_ids
│   │   │   └── README.md            # dataset được version như code
│   │   ├── metrics/
│   │   │   ├── retrieval.py         # recall@k, MRR, nDCG
│   │   │   └── generation.py        # LLM-as-judge
│   │   ├── judge_prompts/
│   │   ├── runner.py                # python -m eval.runner --pipeline naive-v1
│   │   └── report.py                # xuất markdown + chart
│   │
│   ├── scripts/
│   │   ├── ingest_corpus.py
│   │   └── seed_db.py
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/                        # Phase 5
│
├── results/                         # COMMIT VÀO GIT
│   ├── naive-v1.json
│   ├── hybrid-v2.json
│   └── leaderboard.md
│
├── docs/
│   ├── architecture.md
│   ├── adr/
│   └── diagrams/
│
├── data/
│   ├── raw/                         # .gitignore trừ file nhỏ
│   └── samples/
│
├── docker-compose.yml
├── Makefile
└── .github/workflows/
    ├── ci.yml
    └── eval.yml