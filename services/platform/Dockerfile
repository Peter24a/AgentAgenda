FROM python:3.11-slim
WORKDIR /platform
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
RUN useradd --uid 10001 --create-home platform && mkdir /data && chown platform:platform /data
USER platform
EXPOSE 8080
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-proxy-headers"]
