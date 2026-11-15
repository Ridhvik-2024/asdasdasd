FROM node:22-slim AS client-builder
WORKDIR /build/client
COPY client/package.json client/package-lock.json* ./
COPY client/scripts ./scripts
RUN npm ci --no-audit --no-fund
COPY client/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv/nam
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY --from=client-builder /build/client/dist ./client/dist
RUN python scripts/make_seeds.py && python scripts/make_demo_grid.py
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
