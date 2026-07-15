# Policy Intelligence Assistant

A customer-ready local demo for exploring CSUB academic policy, asking source-grounded questions, checking draft resolutions, recording conflicts, browsing topics, and uploading PDF/Markdown/text sources. The retrieval layer uses deterministic local embeddings; AWS Bedrock retrieval and generation are intentionally outside this implementation.

## Run locally

From the repository root in WSL:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m backend.scripts.build_index
backend/.venv/bin/python -m backend.scripts.seed_conflicts
backend/.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The role cards use these demo accounts through the backend when it is available and retain a reviewed static fallback for an offline presentation:

- Employee: `employee@campus.edu` / `demo123`
- Policy reviewer: `reviewer@campus.edu` / `demo123`

API documentation is available at `http://localhost:8000/docs`; health is at `http://localhost:8000/api/health`.

## Demo integrity

The copied Handbook, Unit 3 CBA, and CalPERS PDFs are supplied source material. Files whose title contains “Demo stand-in” or “synthetic” are explicitly non-authoritative demo aids. The service-credit scenario is presented as alignment, not a conflict, because the supplied Handbook and CBA both permit up to two years of prior-service credit. Bedrock is not required for this demo.
