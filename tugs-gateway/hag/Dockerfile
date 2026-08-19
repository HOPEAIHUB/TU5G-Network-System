FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install fastapi uvicorn[standard] grpcio grpcio-tools pydantic redis httpx
COPY src ./src
ENV HAG_PORT=8090
EXPOSE 8090
CMD ["python", "src/main.py"]
