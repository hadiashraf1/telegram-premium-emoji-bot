FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --gid 10001 bot && useradd --uid 10001 --gid bot --no-create-home bot && mkdir /data && chown bot:bot /data
COPY --chmod=0644 app.py catalog.py seed.py seed-packs.txt ./
USER bot
CMD ["python", "app.py"]
