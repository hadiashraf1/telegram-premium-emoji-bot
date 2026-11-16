FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --gid 10001 bot && useradd --uid 10001 --gid bot --no-create-home bot && mkdir /data && chown bot:bot /data
COPY app.py catalog.py ./
USER bot
CMD ["python", "app.py"]
