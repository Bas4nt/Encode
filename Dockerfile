FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY Procfile .

# Set environment variables (optional, overridden by Railway)
ENV PYTHONUNBUFFERED=1

# Command to run the bot
CMD ["python", "main.py"]
