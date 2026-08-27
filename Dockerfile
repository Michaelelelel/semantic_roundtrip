FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv==0.11.16 \
    && uv sync --frozen --extra analysis --extra web
ENV PATH="/app/.venv/bin:$PATH"
RUN mkdir -p /app/runs
