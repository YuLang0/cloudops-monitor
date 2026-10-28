FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
RUN useradd --system --uid 10002 --no-create-home agent
USER agent
CMD ["python", "agent.py"]
