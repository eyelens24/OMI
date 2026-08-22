FROM python:3.11-slim

WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin app
COPY --chown=app:app . /app
USER app

ENV HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000
CMD ["python", "server.py"]
