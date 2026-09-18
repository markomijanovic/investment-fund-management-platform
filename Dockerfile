FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY services ./services
COPY jobs ./jobs
COPY blockchain ./blockchain

RUN addgroup --system iep && adduser --system --ingroup iep iep \
    && chown -R iep:iep /app
USER iep

FROM base AS auth
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "services.auth.app:app"]

FROM base AS employee
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "services.employee.app:app"]

FROM base AS director
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "services.director.app:app"]

FROM base AS checker
CMD ["python", "-m", "jobs.contract_checker"]

