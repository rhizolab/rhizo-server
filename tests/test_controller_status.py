import datetime
import json

from main.resources.models import ControllerStatus
from main.messages.socket_receiver import process_web_socket_message
from main.messages.web_socket_connection import WebSocketConnection


def test_controller_watchdog(db_session, controller_resource):
    ws_conn = WebSocketConnection(None)
    ws_conn.controller_id = controller_resource.id

    process_web_socket_message({"type": "watchdog"}, ws_conn)

    record = db_session.query(ControllerStatus).filter_by(id=controller_resource.id).first()
    assert record.last_watchdog_timestamp

    delta = datetime.datetime.utcnow() - record.last_watchdog_timestamp
    assert delta.total_seconds() < 60


def test_controller_status(db_session, controller_resource, client, app, api):
    assert client.put("/api/v1/resources/folder/controller",
                      content_type="application/x-www-form-urlencoded",
                      data={"status": """{"foo":"bar"}"""}).status_code == 200

    status = db_session.query(ControllerStatus).filter(ControllerStatus.id ==
                                                       controller_resource.id).first()
    attributes = json.loads(status.attributes)
    assert attributes['foo'] == 'bar'

    result = client.get("/api/v1/resources/folder?type=controller_folder&extended=0")
    assert result.status_code == 200

    assert result.json[0]['status']['foo'] == 'bar'
