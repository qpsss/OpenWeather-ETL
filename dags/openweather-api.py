import json
from datetime import datetime, timedelta

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator


def kelvin_to_celsius(temp_in_kelvin):
    temp_in_celsius = (temp_in_kelvin - 273.15)
    return temp_in_celsius


def transform_weather_data(task_instance):
    data = task_instance.xcom_pull(task_ids="extract_weather_data")
    
    city = data["name"]
    weather_description = data["weather"][0]['description']
    temp_celsius = kelvin_to_celsius(data["main"]["temp"])
    feels_like_celsius= kelvin_to_celsius(data["main"]["feels_like"])
    min_temp_celsius = kelvin_to_celsius(data["main"]["temp_min"])
    max_temp_celsius = kelvin_to_celsius(data["main"]["temp_max"])
    pressure = data["main"]["pressure"]
    humidity = data["main"]["humidity"]
    wind_speed = data["wind"]["speed"]
    time_of_record = datetime.utcfromtimestamp(data['dt'] + data['timezone'])
    sunrise_time = datetime.utcfromtimestamp(data['sys']['sunrise'] + data['timezone'])
    sunset_time = datetime.utcfromtimestamp(data['sys']['sunset'] + data['timezone'])

    transformed_data = {"city": city,
                        "description": weather_description,
                        "temperature_celsius": temp_celsius,
                        "feels_like_celsius": feels_like_celsius,
                        "minimun_temp_celsius":min_temp_celsius,
                        "maximum_temp_celsius": max_temp_celsius,
                        "pressure": pressure,
                        "humidity": humidity,
                        "wind_speed": wind_speed,
                        "time_of_record": time_of_record,
                        "sunrise_local_time)":sunrise_time,
                        "sunset_local_time)": sunset_time                        
                        }
    transformed_data_list = [transformed_data]
    df_data = pd.DataFrame(transformed_data_list)
    
    df_data.to_csv("current_weather_data.csv", index=False, header=False)

def load_weather_data():
    hook = PostgresHook(postgres_conn_id= 'postgres_localhost')
    hook.copy_expert(
        sql= "COPY weather_data FROM stdin WITH DELIMITER as ','",
        filename='current_weather_data.csv'
    )

default_args = {
    'owner': 'qpsss',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 8),
    'email': ['sukmaksinp@gmail.com'],
    'email_on_failure': True,
    'email_on_retry': True,
    'retries': 2,
    'retry_delay': timedelta(minutes=2)
}

with DAG(
    dag_id='openweather_api_dag',
    default_args=default_args,
    schedule_interval = '@hourly',
    catchup=False
) as dag:
    create_table = PostgresOperator(
        task_id='create_table',
        postgres_conn_id = "postgres_localhost",
        sql= ''' 
            CREATE TABLE IF NOT EXISTS weather_data (
            city TEXT,
            description TEXT,
            temperature_celsius NUMERIC,
            feels_like_celsius NUMERIC,
            minimun_temp_celsius NUMERIC,
            maximum_temp_celsius NUMERIC,
            pressure NUMERIC,
            humidity NUMERIC,
            wind_speed NUMERIC,
            time_of_record TIMESTAMP,
            sunrise_local_time TIMESTAMP,
            sunset_local_time TIMESTAMP                    
        );
        '''
    )

    is_weather_api_ready = HttpSensor(
        task_id ='is_weather_api_ready',
        http_conn_id='openwearther_api',
        endpoint='/data/2.5/weather?q=Bangkok&appid=e5e31da0d65a2184f05c9b1ba8feed8d'
    )

    extract_weather_data = SimpleHttpOperator(
        task_id = 'extract_weather_data',
        http_conn_id = 'openwearther_api',
        endpoint='/data/2.5/weather?q=Bangkok&appid=e5e31da0d65a2184f05c9b1ba8feed8d',
        method = 'GET',
        response_filter= lambda r: json.loads(r.text),
        log_response=True
    )

    transform_weather_data = PythonOperator(
        task_id= 'transform_weather_data',
        python_callable=transform_weather_data
    )

    load_weather_data = PythonOperator(
        task_id= 'load_weather_data',
        python_callable=load_weather_data
    )


is_weather_api_ready >> extract_weather_data >> transform_weather_data >> load_weather_data