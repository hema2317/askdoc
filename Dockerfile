# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
ENV PORT 8080
EXPOSE 8080

# Command to run your app
CMD ["python", "app.py"]
