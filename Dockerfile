# 3.12, not 3.11: libb/ uses PEP 701 (Python 3.12+) f-strings with nested
# same-type quotes, which are a SyntaxError on 3.11.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching). pyproject + libb are needed
# for the editable install of the `libb` package.
COPY requirements.txt pyproject.toml ./
COPY libb ./libb
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

# App code (user_side/, app/, config/, run.py, …)
COPY . .

# Run state lives on the Railway volume mounted at /data; the live loop runs.
ENV LIBB_DATA_DIR=/data \
    ENABLE_SCHEDULER=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8501

# Starts the scheduler + Streamlit on $PORT (Railway injects PORT).
CMD ["python", "run.py"]
