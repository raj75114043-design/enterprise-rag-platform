FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ragp ./ragp
COPY corpus ./corpus
COPY eval ./eval
COPY streamlit_app.py .
RUN mkdir -p data reports && chown -R app:app /app
USER app
EXPOSE 8000 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "ragp.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
