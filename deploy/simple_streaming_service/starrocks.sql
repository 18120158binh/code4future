create database test_db;

use test_db;

CREATE TABLE IF NOT EXISTS snowplow_events (
    mess string
)
PROPERTIES (
    "replication_num" = "1"
);

select * from snowplow_events;