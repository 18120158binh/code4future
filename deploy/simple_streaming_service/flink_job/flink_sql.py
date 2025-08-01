# table = t_env.from_path("structured_events")
# table.print_schema()

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