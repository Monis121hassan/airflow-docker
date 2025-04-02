# Use the official Airflow image as the base
FROM apache/airflow:2.5.0

# Install the OpenAI Python client library
RUN pip install openai==0.28
