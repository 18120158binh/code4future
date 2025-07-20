from pyflink.table import EnvironmentSettings, TableEnvironment

def main():
    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)

    # ✅ Define Kafka Source Table
    t_env.execute_sql("""
        CREATE TABLE kafka_source (
            `value` STRING
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'snowplow.good.events.1000',
            'properties.bootstrap.servers' = 'localhost:9092',
            'properties.group.id' = 'flink-group',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'raw'
        )
    """)

    # ✅ Define StarRocks Sink Table (via JDBC)
    t_env.execute_sql("""
        CREATE TABLE starrocks_sink (
               `value` STRING
        ) WITH (
            'connector' = 'jdbc',
            'url' = 'jdbc:mysql://starrocks-fe:9030/test_db',
            'table-name' = 'target_table',
            'username' = 'root',
            'password' = ''
        )
    """)

    # ✅ Insert from Kafka → StarRocks
    t_env.execute_sql("""
        INSERT INTO starrocks_sink
        SELECT `value` FROM kafka_source
    """)

if __name__ == "__main__":
    main()
