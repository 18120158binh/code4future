import os
import glob
from pyflink.table import EnvironmentSettings, TableEnvironment

def main():
    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)
    t_env.get_config().get_configuration().set_string("execution.checkpointing.interval", "60s")
    t_env.get_config().get_configuration().set_string("execution.checkpointing.mode", "EXACTLY_ONCE")
#     jar_path = r"file:///C:/Users/binhln/Documents/work-space/code4future/deploy/simple_streaming_service/flink_job/jars/flink-sql-connector-kafka-3.3.0-1.20.jar;file:///C:/Users/binhln/Documents/work-space/code4future/deploy/simple_streaming_service/flink_job/jars/flink-connector-jdbc-3.3.0-1.20.jar;file:///C:/Users/binhln/Documents/work-space/code4future/deploy/simple_streaming_service/flink_job/jars/mysql-connector-java-8.0.30.jar;file:///C:/Users/binhln/Documents/work-space/code4future/deploy/simple_streaming_service/flink_job/jars/flink-connector-starrocks-1.2.11_flink-1.20.jar"

#     t_env.get_config().set("pipeline.jars", jar_path)

    t_env.execute_sql("""
        CREATE TABLE kafka_source (
            `value` STRING
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'snowplow.good.events.1000',
            'properties.bootstrap.servers' = 'kafka:9093',
            'properties.group.id' = 'flink-group',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'raw'
        )
    """)

    # ✅ Define StarRocks Sink Table (via JDBC)
    t_env.execute_sql("""
        CREATE TABLE starrocks_sink (
               mess STRING
        ) WITH (
            'connector' = 'starrocks',
            'jdbc-url' = 'jdbc:mysql://starrocks-fe:9030',
            'load-url' = 'starrocks-fe:8030',
            'database-name' = 'test_db',
            'table-name' = 'snowplow_events',
            'username' = 'root',
            'password' = '',
            'sink.buffer-flush.interval-ms' = '1000'
            )
    """)

    t_env.execute_sql("""
        INSERT INTO starrocks_sink
        SELECT `value` as mess FROM kafka_source
    """).wait()

#     t_env.execute_sql("""
#         INSERT INTO starrocks_sink VALUES ('ABC'), ('def');
#     """).wait()

#     t_env.execute_sql("""
#         CREATE TABLE print_sink (
#             `value` STRING
#         ) WITH (
#             'connector' = 'print'
#         )
#     """)
#
#     print("Job starting... reading from Kafka and printing to console.")
#     t_env.execute_sql("INSERT INTO print_sink SELECT * FROM kafka_source").wait()

if __name__ == "__main__":
    main()
