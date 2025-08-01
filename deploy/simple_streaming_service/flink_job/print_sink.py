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

    t_env.execute_sql("""
        CREATE TEMPORARY VIEW structured_events AS
        SELECT
            schema_str,
            ipAddress AS ip_address,
            TO_TIMESTAMP_LTZ(`timestamp`, 3) AS server_time,
            encoding,
            collector,
            userAgent AS user_agent,
            refererUri,
            path,
            querystring,
            TO_TIMESTAMP_LTZ(CAST(body_data.dtm AS BIGINT), 3) AS user_time,
            TO_TIMESTAMP_LTZ(CAST(body_data.stm AS BIGINT), 3) AS sent_time,
            COALESCE(body_data.ue_pr.data.schema, body_data.ue_px.data.schema) AS schema_event,
            COALESCE(body_data.co.schema, body_data.cx.schema) AS schema_context,
            body_data.vid AS domain_session_index,
            body_data.aid AS app_id,
            body_data.uid AS user_id,
            body_data.eid AS event_id,
            body_data.p AS platform,
            body_data.e AS event_type,
            body_data.page AS page_title,
            body_data.refr AS referrer_url,
            body_data.tv AS track_verison,
            body_data.tna AS tracker_name,
            body_data.cs AS character_set,
            body_data.lang AS `language`,
            body_data.res AS screen_resolution,
            body_data.cd AS color_depth,
            body_data.tz AS time_zone,
            body_data.vp AS viewport_size,
            body_data.ds AS document_size,
            body_data.sid AS domain_session_id,
            body_data.duid AS domain_user_id,
            headers,
            contentType,
            hostname,
            networkUserId AS network_user_id
        FROM events_with_body e
        CROSS JOIN UNNEST(e.body.data) AS body_data
    """)

    t_env.execute_sql("""
      CREATE TABLE print_sink (
            user_time timestamp,
            schema_event STRING,
            schema_context STRING,
            screen_resolution STRING
      ) WITH (
            'connector' = 'print'
            )
      """)

    print("Job starting... reading from Kafka and printing to console.")
    t_env.execute_sql("""INSERT INTO print_sink
                         SELECT user_time, schema_event, schema_context, screen_resolution
                         FROM structured_events""").wait()

if __name__ == "__main__":
    main()
