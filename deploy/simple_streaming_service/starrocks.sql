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

create database test_db1;

use test_db;
REFRESH EXTERNAL TABLE demo.test_db.snowplow_events;
CREATE TABLE IF NOT EXISTS snowplow_events (
   user_time datetime,
   schema_event STRING,
   schema_context STRING,
   screen_resolution STRING,
    d date
) PARTITION BY (d);

CREATE TABLE IF NOT EXISTS snowplow_events1 (
                                               user_time datetime,
                                               schema_event STRING,
                                               schema_context STRING,
                                               screen_resolution STRING,
                                               d date
) PROPERTIES ( 'replication_num'='1');

select * from snowplow_events;
