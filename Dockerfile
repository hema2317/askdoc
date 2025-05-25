# Use an official Python runtime
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY . .

# Expose the port (Cloud Run uses $PORT)
ENV PORT=8080

# Run your Flask app
CMD ["gunicorn", "-b", ":8080", "app:app"]
