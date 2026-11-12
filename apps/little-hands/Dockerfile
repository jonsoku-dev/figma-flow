FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes --only-binary=:all: -r requirements.lock \
    && groupadd --gid 10001 littlehands \
    && useradd --uid 10001 --gid 10001 --no-create-home littlehands
COPY manage.py ./
COPY config/ config/
COPY booking/ booking/
COPY templates/ templates/
COPY static/ static/
COPY deploy/entrypoint.py deploy/healthcheck.py deploy/
RUN python -c 'import os,secrets; os.environ.update(LH_ENV="production", LH_SECRET_KEY=secrets.token_urlsafe(64), LH_ALLOWED_HOSTS="localhost", LH_SITE_URL="https://localhost"); from django.core.management import execute_from_command_line; os.environ["DJANGO_SETTINGS_MODULE"]="config.settings"; execute_from_command_line(["manage.py", "collectstatic", "--noinput"])'
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "deploy/entrypoint.py"]
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--threads=2", "--timeout=30", "--worker-tmp-dir=/tmp", "--forwarded-allow-ips=", "--no-control-socket", "--error-logfile=-"]
