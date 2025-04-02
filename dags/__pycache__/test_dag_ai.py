import openai
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from airflow.utils.email import send_email
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.hooks.base import BaseHook
from datetime import timedelta
import os

# Initialize logger
log = LoggingMixin().log

# Fetch OpenAI API key from Airflow's connection
openai_conn = BaseHook.get_connection('openai_default')
openai.api_key = openai_conn.password

def analyze_logs_with_llm(log_content):
    try:
        if not log_content:
            raise ValueError("Log content is empty.")
        print(log_content)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
             messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes Airflow task logs and provides resolutions."},
                {"role": "user", "content": f"Analyze the following Airflow task log and provide resolutions under 100 words:\n\n{log_content}"}
            ],
            max_tokens=200
        )
        log.info("LLM analysis completed successfully.")
        return response.choices[0].message['content'].strip()
    except openai.error.RateLimitError as e:
        log.error(f"OpenAI API quota exceeded: {e}")
        return "OpenAI API quota exceeded. Please check your billing and usage."
    except openai.error.InvalidRequestError as e:
        log.error(f"Invalid request to OpenAI API: {e}")
        return "Invalid request to OpenAI API. Please check your input and model configuration."
    except openai.error.AuthenticationError as e:
        log.error(f"OpenAI API authentication failed: {e}")
        return "OpenAI API authentication failed. Please check your API key."
    except Exception as e:
        log.error(f"LLM analysis failed: {str(e)}")
        return f"LLM analysis could not be completed. Error: {str(e)}"

def format_run_id(run_id):
    if run_id.startswith("manual__"):
        prefix, timestamp = run_id.split("manual__", 1)
        # Replace underscores with the correct characters
        timestamp = timestamp.replace("_", "-", 2)  # Replace the first two underscores with hyphens (for the date)
        timestamp = timestamp.replace("_", ":", 2)  # Replace the next two underscores with colons (for the time)
        timestamp = timestamp.replace("_", ".", 1)  # Replace the next underscore with a period (for the milliseconds)
        # Reconstruct the run_id
        run_id = f"manual__{timestamp}"
    return run_id


def send_analysis_email(subject, log_path, resolution_steps):
    html_content = f"""
    <p><strong>Log file:</strong> {log_path}</p>
    <p><strong>Resolution Steps:</strong><br>
    {resolution_steps}</p>
    """
    send_email(to='monis121hassan@gmail.com', subject=subject, html_content=html_content)

def notify_success(context):
    task_instance = context.get('task_instance')
    if task_instance:
        run_id = format_run_id(task_instance.run_id)
        log_path = os.path.join(
            "/opt/airflow/logs",
            f"dag_id={task_instance.dag_id}",
            f"run_id={run_id}",
            f"task_id={task_instance.task_id}",
            f"attempt={task_instance.try_number-1}.log"
        )
        try:
            with open(log_path, 'r') as log_file:
                log_content = log_file.read()
            insights = analyze_logs_with_llm(log_content)
        except Exception as e:
            log.error(f"Error reading log file: {e}")
            insights = "Could not read log file for analysis."
        
        subject = f"Airflow Task Success: {task_instance.task_id}"
        send_analysis_email(subject, log_path, insights)

def notify_failure(context):
    task_instance = context.get('task_instance')
    if task_instance:
        run_id = format_run_id(task_instance.run_id)
        log_path = os.path.join(
            "/opt/airflow/logs",
            f"dag_id={task_instance.dag_id}",
            f"run_id={run_id}",
            f"task_id={task_instance.task_id}",
            f"attempt={task_instance.try_number-1}.log"
        )
        try:
            with open(log_path, 'r') as log_file:
                log_content = log_file.read()
            resolution_steps = analyze_logs_with_llm(log_content)
        except Exception as e:
            log.error(f"Error reading log file: {e}")
            resolution_steps = "Could not read log file for analysis."
        
        subject = f"Airflow Task Failure: {task_instance.task_id}"
        send_analysis_email(subject, log_path, resolution_steps)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'on_success_callback': notify_success,
    'on_failure_callback': notify_failure,
}

with DAG(
    'test_dag',
    default_args=default_args,
    description='A simple test DAG with LLM-based log analysis on task success and failure',
    schedule_interval=timedelta(days=1),
    start_date=days_ago(1),
    catchup=False,
) as dag:

    t1 = BashOperator(
        task_id='print_date',
        bash_command='exit 1',
    )

    t2 = BashOperator(
        task_id='fail_task',
        bash_command='exit 1',
    )

    t3 = BashOperator(
        task_id='echo_hello',
        bash_command='echo "Hello World!"',
    )

    t1 >> t2 >> t3
