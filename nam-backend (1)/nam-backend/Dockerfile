FROM python:3.12-slim
WORKDIR /srv/nam
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY data ./data
RUN python scripts/make_seeds.py && python scripts/make_demo_grid.py
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
