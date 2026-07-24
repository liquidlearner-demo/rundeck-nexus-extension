FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml server.py ./
RUN pip install --no-cache-dir fastmcp>=2.3 httpx>=0.27 uvicorn>=0.30

EXPOSE 8710
CMD ["python", "server.py"]
