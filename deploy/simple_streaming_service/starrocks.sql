CREATE EXTERNAL CATALOG 'demo'
COMMENT "External catalog to Apache Iceberg on MinIO"
PROPERTIES
(
  "type"="iceberg",
  "iceberg.catalog.type"="rest",
  "iceberg.catalog.uri"="http://iceberg-rest:8181",
  "iceberg.catalog.warehouse"="warehouse",
  "aws.s3.access_key"="admin",
  "aws.s3.secret_key"="password",
  "aws.s3.endpoint"="http://minio:9000",
  "aws.s3.enable_path_style_access"="true",
  "client.factory"="com.starrocks.connector.iceberg.IcebergAwsClientFactory"
);

SET CATALOG demo;

create database test_db;
use test_db;

REFRESH EXTERNAL TABLE demo.test_db.snowplow_events;

CREATE TABLE IF NOT EXISTS snowplow_events (
   user_time datetime,
   schema_event STRING,
   schema_context STRING,
   screen_resolution STRING,
    d date
) PARTITION BY (d);

create database test_db;
use test_db;
CREATE TABLE snowplow_events (
                                    schema_str VARCHAR(255),
                                    ipAddress VARCHAR(64),
                                    event_time DATETIME,
                                    encoding VARCHAR(64),
                                    collector VARCHAR(255),
                                    userAgent TEXT,
                                    refererUri TEXT,
                                    path TEXT,
                                    querystring TEXT,
                                    body JSON,
                                    headers ARRAY<STRING>,
                                    contentType VARCHAR(128),
                                    hostname VARCHAR(255),
                                    networkUserId VARCHAR(128),
                                    event_date DATE AS (DATE(event_time))
)
PROPERTIES (
    "replication_num" = "1"
);

CREATE TABLE IF NOT EXISTS snowplow_events (
                                               user_time datetime,
                                               schema_event STRING,
                                               schema_context STRING,
                                               screen_resolution STRING,
                                               d date
) PROPERTIES ( 'replication_num'='1');

CREATE TABLE IF NOT EXISTS test_json (
                                               schema_event STRING,
                                               schema_context STRING,
                                               screen_resolution STRING
) PROPERTIES ( 'replication_num'='1');

select * from snowplow_events;

curl -i http://localhost:8083/connectors -H "Content-Type: application/json" -X POST -d '{
  "name":"starrocks-kafka-connector",
  "config":{
    "connector.class":"com.starrocks.connector.kafka.StarRocksSinkConnector",
    "topics":"snowplow.good.events.1000",
    "key.converter":"org.apache.kafka.connect.json.JsonConverter",
    "value.converter":"org.apache.kafka.converter.ThriftConverter",
    "key.converter.schemas.enable":"true",
    "value.converter.schemas.enable":"false",
    "starrocks.http.url":"starrocks-fe:8030",
    "starrocks.topic2table.map":"snowplow.good.events.1000:snowplow_events",
    "starrocks.username":"root",
    "starrocks.password":"",
    "starrocks.database.name":"test_db",
    "sink.properties.strip_outer_array":"true"
  }
}'

curl -i http://localhost:8083/connectors -H "Content-Type: application/json" -X POST -d '{
  "name":"starrocks-kafka-connector",
  "config":{
    "connector.class":"com.starrocks.connector.kafka.StarRocksSinkConnector",
    "topics":"test.json",
    "key.converter":"org.apache.kafka.connect.json.JsonConverter",
    "value.converter":"org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable":"true",
    "value.converter.schemas.enable":"false",
    "starrocks.http.url":"starrocks-fe:8030",
    "starrocks.topic2table.map":"test.json:test_json",
    "starrocks.username":"root",
    "starrocks.password":"",
    "starrocks.database.name":"test_db",
    "sink.properties.strip_outer_array":"true"
  }
}'