FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-cache
COPY . .

# Stage 2: Final stage - Use python:3.12-slim as the base image
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages and application code from builder stage
COPY --from=builder /app/.venv/ /app/.venv/
COPY --from=builder /app/.chainlit/ /app/.chainlit
COPY --from=builder /app/scripts/ /app/scripts/
COPY --from=builder /app/chainlit.md /app/
COPY --from=builder /app/chainlit_ja.md /app/
COPY --from=builder /app/public /app/public
COPY --from=builder /app/chatui/ /app/chatui/
COPY --from=builder /app/main.py /app/

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8080

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application using the startup script
CMD ["/app/scripts/run.sh"]