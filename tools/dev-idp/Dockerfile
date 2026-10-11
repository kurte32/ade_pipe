FROM python:3.12-slim-bookworm
WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" "pyjwt[crypto]>=2.9"
COPY app.py users.json ./
RUN useradd -r -u 10001 devidp && mkdir -p /keys && chown devidp /keys
USER devidp
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
