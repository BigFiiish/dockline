FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY dockline ./dockline
COPY evals ./evals
RUN pip install --no-cache-dir -e .
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn dockline.web:app --host 0.0.0.0 --port ${PORT:-8080}"]
