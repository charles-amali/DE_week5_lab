from airflow import DAG
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from datetime import datetime, timedelta
import json

# Default args for the DAG
default_args = {
    'owner': 'Charles',
    'email': ['charles.nkansah@amalitech.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Task 3: Transform the data and generate SQL
def transform_weather_data(**context):
    # Retrieve raw data from XCom
    raw_data = context['ti'].xcom_pull(task_ids='fetch_weather_data')
    data = json.loads(raw_data)

    # Perform transformations
    city = data['name']
    temp_kelvin = data['main']['temp']
    temperature_fahrenheit = (temp_kelvin - 273.15) * 9 / 5 + 32
    pressure = data['main']['pressure']
    humidity = data['main']['humidity']
    timestamp = datetime.utcfromtimestamp(data['dt']).isoformat()

    # Generate the SQL query
    sql = f"""
        INSERT INTO daily_weather (temp_fahrenheit, pressure, humidity, timestamp, city)
        VALUES ({temperature_fahrenheit}, {pressure}, {humidity}, '{timestamp}', '{city}');
    """

    # Push SQL to XCom
    context['ti'].xcom_push(key='weather_sql', value=sql)

# DAG definition
with DAG(
    dag_id='weather_data_pipeline',
    default_args=default_args,
    description='Pipeline for fetching and storing weather data',
    schedule_interval='@daily',
    start_date=datetime(2024, 12, 2),
    catchup=False,
) as dag:

    # Task 1: Check if the API is online
    api_check = HttpSensor(
        task_id='check_api',
        http_conn_id='weather_api',
        endpoint='data/2.5/weather?q=Portland&appid=94f47aea88f1ccd83547c4bc228c692d',
        timeout=20,
        poke_interval=5,
    )

    # Task 2: Fetch the weather data
    fetch_weather_data = SimpleHttpOperator(
        task_id='fetch_weather_data',
        http_conn_id='weather_api',
        endpoint='data/2.5/weather?q=Portland&appid=94f47aea88f1ccd83547c4bc228c692d',
        method='GET',
        response_filter=lambda response: response.text,
        log_response=True,
    )

    # Task 3: Transform data and generate SQL
    transform_data = PythonOperator(
        task_id='transform_weather_data',
        python_callable=transform_weather_data,
        provide_context=True,
    )

    # Task 4: Load data into PostgreSQL
    load_data = PostgresOperator(
        task_id='load_weather_data',
        postgres_conn_id='postgres_local',
        sql="{{ ti.xcom_pull(task_ids='transform_weather_data', key='weather_sql') }}",
    )

    # Task dependencies
    api_check >> fetch_weather_data >> transform_data >> load_data
