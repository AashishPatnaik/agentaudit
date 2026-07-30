FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

EXPOSE 8501

# Explicit ping interval (default is already 30s, under the ALB's 60s idle
# timeout) — belt-and-suspenders so a long-running "Research" click can't
# go quiet on the ALB-facing connection long enough to be cut off.
CMD ["streamlit", "run", "src/agentaudit_dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.websocketPingInterval=20"]
