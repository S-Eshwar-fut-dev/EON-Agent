FROM python:3.11-slim

# Creates a user with UID 1000 to comply with Hugging Face Spaces Docker rules
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all the application files and ensure permissions are correct
COPY --chown=user . /app

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

EXPOSE 7860
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "7860"]
