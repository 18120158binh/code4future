import os
from pyflink.table import EnvironmentSettings, TableEnvironment


def main():
    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)
    t_env.get_config().get_configuration().set_string("execution.checkpointing.interval", "60s")
    t_env.get_config().get_configuration().set_string("execution.checkpointing.mode", "EXACTLY_ONCE")

    job_dir = os.path.dirname(os.path.realpath(__file__))
    deserialize_module_path = os.path.join(job_dir, "deserialize")
    t_env.get_config().set("python.files", "deserialize/")
    t_env.get_config().set("python.files", f"file://{deserialize_module_path}")
    from deserialize.deserialize_thrift import deserialize_collector_payload
    t_env.create_temporary_system_function("DeserializeCollector", deserialize_collector_payload)
#     jar_path = r"file:///C:/Users/binhln/Documents/work-space/code4future/deploy/simple_streaming_service/flink_job/jars/flink-sql-connector-kafka-3.3.0-1.20.jar;"
#     t_env.get_config().set("pipeline.jars", jar_path)

    t_env.execute_sql("""
        CREATE TABLE kafka_source (
            `value` BYTES
        ) WITH (
            'connector' = 'kafka',
            'topic' = 'snowplow.good.events.1000',
            'properties.bootstrap.servers' = 'kafka:9093',
            'properties.group.id' = 'flink-group',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'raw'
        )
    """)

    t_env.execute_sql("""
        CREATE TEMPORARY VIEW events_with_body AS
        SELECT
            schema_str,
            ipAddress,
            `timestamp`,
            encoding,
            collector,
            userAgent,
            refererUri,
            path,
            querystring,
            body,
            headers,
            contentType,
            hostname,
            networkUserId
        FROM
            kafka_source,
            LATERAL TABLE(DeserializeCollector(`value`))
            AS p(schema_str, ipAddress, `timestamp`, encoding, collector, userAgent, refererUri,
                 path, querystring, body, headers, contentType, hostname, networkUserId)
    """)

    # table = t_env.from_path("events_with_body")
    # table.print_schema()

    t_env.execute_sql("""
        CREATE TEMPORARY VIEW structured_events AS
        SELECT
            schema_str,
            ipAddress,
            TO_TIMESTAMP_LTZ(`timestamp`, 3) AS server_time,
            encoding,
            collector,
            userAgent,
            refererUri,
            path,
            querystring,
            body_data.cx,
            headers,
            contentType,
            hostname,
            networkUserId
        FROM events_with_body e
        CROSS JOIN UNNEST(e.body.data) AS body_data
    """)

    # t_env.execute_sql("""
    #     CREATE TEMPORARY VIEW transform AS
    #     SELECT
    #         cx
    #     FROM structured_events
    # """)


# ✅ Define StarRocks Sink Table (via JDBC)
#     t_env.execute_sql("""
#         CREATE TABLE starrocks_sink (
#                mess STRING
#         ) WITH (
#             'connector' = 'starrocks',
#             'jdbc-url' = 'jdbc:mysql://starrocks-fe:9030',
#             'load-url' = 'starrocks-fe:8030',
#             'database-name' = 'test_db',
#             'table-name' = 'snowplow_events',
#             'username' = 'root',
#             'password' = '',
#             'sink.buffer-flush.interval-ms' = '1000'
#             )
#     """)

    # t_env.execute_sql("""
    #     INSERT INTO starrocks_sink
    #     SELECT `value` as mess FROM kafka_source
    # """).wait()

#     t_env.execute_sql("""
#         INSERT INTO starrocks_sink VALUES ('ABC'), ('def');
#     """).wait()

    # t_env.execute_sql("""
    #     CREATE TABLE print_sink (
    #         schema_str STRING,
    #         ipAddress STRING,
    #         `timestamp` TIMESTAMP,
    #         encoding STRING,
    #         collector STRING,
    #         userAgent STRING,
    #         refererUri STRING,
    #         path STRING,
    #         querystring STRING,
    #         body ROW<data ARRAY<ROW<aid STRING, cd STRING, cs STRING, cx STRING, ds STRING, uid STRING,
    #             dtm STRING, duid STRING, e STRING, eid STRING, lang STRING, p STRING,
    #             ue_px STRING, page STRING, refr STRING, res STRING, sid STRING,
    #             stm STRING, tna STRING, tv STRING, tz STRING, url STRING, vid STRING,
    #             vp STRING, ue_pr STRING, co STRING>>>,
    #         headers ARRAY<STRING>,
    #         contentType STRING,
    #         hostname STRING,
    #         networkUserId STRING
    #     ) WITH (
    #         'connector' = 'print'
    #     )
    # """)

    t_env.execute_sql("""
      CREATE TABLE print_sink1 (
          cx ROW<schema STRING,data ARRAY<ROW<schema STRING, data map<string,string>>>>
      ) WITH (
            'connector' = 'print'
            )
      """)

    print("Job starting... reading from Kafka and printing to console.")
    t_env.execute_sql("""INSERT INTO print_sink1 SELECT   cx  FROM structured_events""").wait()

if __name__ == "__main__":
    main()
