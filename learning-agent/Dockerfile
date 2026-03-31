# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirments.txt .

# Install dependencies from the requirements file
# Note: Fixing 'dotenv' typo from requirments.txt to 'python-dotenv'
RUN sed -i 's/^dotenv$/python-dotenv/' requirments.txt && \
    pip install --no-cache-dir -r requirments.txt && \
    pip install --no-cache-dir httpx python-dotenv

# Copy the rest of the application code
COPY . .

# Expose the default Cloud Run port
EXPOSE 8080

# Command to run the ADK web agent.
# We map it to 0.0.0.0 and listen on the dynamically injected $PORT variable.
CMD sh -c "adk web agent --host 0.0.0.0 --port ${PORT:-8080}"
