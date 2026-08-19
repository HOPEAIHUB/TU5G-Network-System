FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install fastapi uvicorn[standard] cryptography pydantic
COPY src ./src
ENV QSAC_PORT=8200
EXPOSE 8200
CMD ["python", "src/qsac_icss.py"]
