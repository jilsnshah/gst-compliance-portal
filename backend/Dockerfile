FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code edits do not invalidate the layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite file and uploaded documents both live under /data, which
# docker-compose maps to a directory on the host -- so a rebuilt or recreated
# container keeps every client file and every audit row.
ENV DATABASE_URL=sqlite:////data/gst_platform.db \
    STORAGE_ROOT=/data/storage

EXPOSE 8010

# Migrations own the schema, so an upgrade never loses data. seed.py then
# creates the first administrator if the database has no users at all.
# SEED_DEMO=true loads the test accounts and sample workbooks; anything else
# just ensures one real administrator exists.
CMD ["sh", "-c", "alembic upgrade head && python seed.py $([ \"$SEED_DEMO\" = true ] && echo --demo) && uvicorn app.main:app --host 0.0.0.0 --port 8010"]
