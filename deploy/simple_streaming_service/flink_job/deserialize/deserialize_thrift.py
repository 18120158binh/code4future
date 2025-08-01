import typing
import json
from pyflink.table import DataTypes
from pyflink.table.udf import udtf
from pyflink.table.types import Row
from thrift.protocol import TBinaryProtocol
from thrift.transport import TTransport
import base64

from .structs.ttypes import CollectorPayload

common_schema = DataTypes.ROW([
    DataTypes.FIELD("schema", DataTypes.STRING()),
    DataTypes.FIELD("data", DataTypes.MAP(DataTypes.STRING(), DataTypes.STRING())),
])

co_type = DataTypes.ROW([
    DataTypes.FIELD("schema", DataTypes.STRING()),
    DataTypes.FIELD("data", DataTypes.ARRAY(common_schema)),
])

ue_pr_type = DataTypes.ROW([
    DataTypes.FIELD("schema", DataTypes.STRING()),
    DataTypes.FIELD("data", common_schema),
])

data_row_type = DataTypes.ROW([
    DataTypes.FIELD("aid", DataTypes.STRING()),
    DataTypes.FIELD("cd", DataTypes.STRING()),
    DataTypes.FIELD("cs", DataTypes.STRING()),
    DataTypes.FIELD("cx", co_type),
    DataTypes.FIELD("ds", DataTypes.STRING()),
    DataTypes.FIELD("uid", DataTypes.STRING()),
    DataTypes.FIELD("dtm", DataTypes.STRING()),
    DataTypes.FIELD("duid", DataTypes.STRING()),
    DataTypes.FIELD("e", DataTypes.STRING()),
    DataTypes.FIELD("eid", DataTypes.STRING()),
    DataTypes.FIELD("lang", DataTypes.STRING()),
    DataTypes.FIELD("p", DataTypes.STRING()),
    DataTypes.FIELD("ue_px", ue_pr_type),
    DataTypes.FIELD("page", DataTypes.STRING()),
    DataTypes.FIELD("refr", DataTypes.STRING()),
    DataTypes.FIELD("res", DataTypes.STRING()),
    DataTypes.FIELD("sid", DataTypes.STRING()),
    DataTypes.FIELD("stm", DataTypes.STRING()),
    DataTypes.FIELD("tna", DataTypes.STRING()),
    DataTypes.FIELD("tv", DataTypes.STRING()),
    DataTypes.FIELD("tz", DataTypes.STRING()),
    DataTypes.FIELD("url", DataTypes.STRING()),
    DataTypes.FIELD("vid", DataTypes.STRING()),
    DataTypes.FIELD("vp", DataTypes.STRING()),
    DataTypes.FIELD("ue_pr", ue_pr_type),
    DataTypes.FIELD("co", co_type)
])

body_type = DataTypes.ROW([
    DataTypes.FIELD("data", DataTypes.ARRAY(data_row_type))
])

result_type = DataTypes.ROW([
    DataTypes.FIELD("schema_str", DataTypes.STRING()),
    DataTypes.FIELD("ipAddress", DataTypes.STRING()),
    DataTypes.FIELD("timestamp", DataTypes.BIGINT()),
    DataTypes.FIELD("encoding", DataTypes.STRING()),
    DataTypes.FIELD("collector", DataTypes.STRING()),
    DataTypes.FIELD("userAgent", DataTypes.STRING()),
    DataTypes.FIELD("refererUri", DataTypes.STRING()),
    DataTypes.FIELD("path", DataTypes.STRING()),
    DataTypes.FIELD("querystring", DataTypes.STRING()),
    DataTypes.FIELD("body", body_type),
    DataTypes.FIELD("headers", DataTypes.ARRAY(DataTypes.STRING())),
    DataTypes.FIELD("contentType", DataTypes.STRING()),
    DataTypes.FIELD("hostname", DataTypes.STRING()),
    DataTypes.FIELD("networkUserId", DataTypes.STRING())
])

def parse_ue_pr(json_str) -> Row:
    if json_str:
        json_obj = json.loads(json_obj)
        data = json_obj.get("data")
        data_map = {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}

        return Row(json_obj.get("schema"), data_map)
    return None

def parse_co(json_str) -> Row:
    if json_str:
        json_obj = json.loads(json_str)
        data_array = []
        for item in json_obj["data"]:
            schema = item.get("schema")
            data = item.get("data")
            data_map = {k: str(v) for k, v in data.items()} if isinstance(data, dict) else {}
            data_array.append(Row(schema, data_map))

        return Row(json_obj.get("schema"), data_array)
    return None

@udtf(result_types=result_type)
def deserialize_collector_payload(data: bytes) -> typing.Iterable[Row]:
    """
    A User-Defined Table Function (UDTF) that deserializes a byte array
    into a structured Row representing a CollectorPayload object.
    """

    if not data:
        return

    try:
        transport = TTransport.TMemoryBuffer(data)
        protocol = TBinaryProtocol.TBinaryProtocol(transport)

        payload = CollectorPayload()
        payload.read(protocol)

        body_obj = None
        if payload.body:
            try:
                body_dict = json.loads(payload.body)
                if "data" in body_dict and isinstance(body_dict["data"], list):
                    structured_data = []
                    for item in body_dict["data"]:
                        ue_px = base64.b64decode(item.get("ue_px")).decode('utf-8') if item.get("ue_px") else None
                        cx = base64.b64decode(item.get("cx")).decode('utf-8') if item.get("cx") else None

                        structured_data.append(Row(
                            item.get("aid"),
                            item.get("cd"),
                            item.get("cs"),
                            parse_co(cx),
                            item.get("ds"),
                            item.get("uid"),
                            item.get("dtm"),
                            item.get("duid"),
                            item.get("e"),
                            item.get("eid"),
                            item.get("lang"),
                            item.get("p"),
                            parse_ue_pr(ue_px),
                            item.get("page"),
                            item.get("refr"),
                            item.get("res"),
                            item.get("sid"),
                            item.get("stm"),
                            item.get("tna"),
                            item.get("tv"),
                            item.get("tz"),
                            item.get("url"),
                            item.get("vid"),
                            item.get("vp"),
                            parse_ue_pr(item.get("ue_pr")),
                            parse_co(item.get("co"))
                        ))
                    body_obj = Row(structured_data)
            except Exception as e:
                pass

        yield Row(
            payload.schema,
            payload.ipAddress,
            payload.timestamp,
            payload.encoding,
            payload.collector,
            payload.userAgent,
            payload.refererUri,
            payload.path,
            payload.querystring,
            body_obj,
            payload.headers,
            payload.contentType,
            payload.hostname,
            payload.networkUserId
        )

    except Exception as e:
        pass