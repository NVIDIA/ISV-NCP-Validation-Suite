# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared BFX05/BFX06 notification-delivery provider."""

from __future__ import annotations

import importlib.util
import json
import threading
from argparse import Namespace
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar

import pytest
import yaml

SCRIPT = Path(__file__).parents[1] / "configs" / "providers" / "shared" / "breakfix" / "query_tenant_notification.py"
AWS_CONFIG = Path(__file__).parents[1] / "configs" / "providers" / "aws" / "config" / "bare_metal.yaml"


def _load_module() -> ModuleType:
    """Load the provider script as a module."""
    spec = importlib.util.spec_from_file_location("query_tenant_notification", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def provider() -> ModuleType:
    """Return a freshly loaded provider module."""
    return _load_module()


def _args(event_type: str) -> Namespace:
    """Build the arguments needed by the normalized payload helper."""
    return Namespace(
        machine_id="node-1",
        event_type=event_type,
        message="Tenant notification",
        schedule_hours=24,
    )


def test_planned_payload_has_future_schedule(provider: ModuleType) -> None:
    """The planned payload carries a future, timezone-aware schedule."""
    started_at = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    payload = provider._payload(_args("planned_maintenance"), "delivery-1", started_at)
    assert payload == {
        "delivery_id": "delivery-1",
        "machine_id": "node-1",
        "type": "planned_maintenance",
        "message": "Tenant notification",
        "scheduled_at": "2026-08-24T10:00:00Z",
    }


def test_failure_payload_records_detection_time(provider: ModuleType) -> None:
    """The immediate-failure payload carries the original failure time."""
    started_at = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    payload = provider._payload(_args("node_failure"), "delivery-2", started_at)
    assert payload["failed_at"] == "2026-08-23T10:00:00Z"
    assert payload["type"] == "node_failure"


def test_aws_steps_bind_notification_to_launched_instance() -> None:
    """Both AWS notification records identify the bare-metal instance under test."""
    config = yaml.safe_load(AWS_CONFIG.read_text())
    steps = {step["name"]: step for step in config["commands"]["bare_metal"]["steps"]}
    for name in ("query_planned_notifications", "query_failure_notifications"):
        args = steps[name]["args"]
        index = args.index("--machine-id")
        assert args[index + 1] == "{{steps.launch_instance.instance_id}}"


class _CaptureHandler(BaseHTTPRequestHandler):
    """Capture one test webhook request and acknowledge it."""

    payload: ClassVar[dict[str, Any]] = {}

    def do_POST(self) -> None:
        """Capture the JSON body and return HTTP 204."""
        length = int(self.headers["Content-Length"])
        type(self).payload = json.loads(self.rfile.read(length))
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        """Suppress HTTP server logs in the unit test."""


@pytest.mark.parametrize("channel", ["webhook", "slack", "teams"])
def test_webhook_backends_accept_acknowledged_delivery(provider: ModuleType, channel: str) -> None:
    """Generic, Slack, and Teams webhook formats accept a 2xx acknowledgement."""
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    server.timeout = 10
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        payload = {
            "delivery_id": "delivery-3",
            "machine_id": "node-1",
            "type": "node_failure",
            "message": "Node failed",
        }
        result = provider._deliver_webhook(payload, f"http://127.0.0.1:{server.server_port}/notify", channel)
    finally:
        thread.join(timeout=5)
        server.server_close()
    assert result == channel
    if channel == "webhook":
        assert _CaptureHandler.payload["delivery_id"] == "delivery-3"
    elif channel == "slack":
        assert "delivery-3" in _CaptureHandler.payload["text"]
    else:
        assert _CaptureHandler.payload["type"] == "message"


def test_webhook_rejects_cleartext_non_loopback_url(provider: ModuleType) -> None:
    """Webhook credentials cannot be sent over cleartext remote HTTP."""
    with pytest.raises(provider.DeliveryError, match="must use HTTPS"):
        provider._deliver_webhook({}, "http://example.com/hook", "webhook")


class _FakeSns:
    """Minimal SNS client that forwards publications to the fake SQS client."""

    def __init__(self, sqs: _FakeSqs) -> None:
        self.sqs = sqs
        self.deleted = False

    def create_topic(self, **kwargs: Any) -> dict[str, str]:
        """Return an ephemeral topic ARN."""
        return {"TopicArn": "arn:aws:sns:us-west-2:123456789012:test"}

    def subscribe(self, **kwargs: Any) -> dict[str, str]:
        """Return a confirmed subscription ARN."""
        return {"SubscriptionArn": "arn:aws:sns:subscription"}

    def publish(self, **kwargs: Any) -> dict[str, str]:
        """Forward the message to the fake queue."""
        self.sqs.body = kwargs["Message"]
        return {"MessageId": "message-1"}

    def delete_topic(self, **kwargs: Any) -> None:
        """Record cleanup."""
        self.deleted = True


class _FakeSqs:
    """Minimal SQS client that returns one published message."""

    body = ""

    def __init__(self) -> None:
        self.deleted = False

    def create_queue(self, **kwargs: Any) -> dict[str, str]:
        """Return an ephemeral queue URL."""
        return {"QueueUrl": "https://sqs.us-west-2.amazonaws.com/123456789012/test"}

    def get_queue_attributes(self, **kwargs: Any) -> dict[str, dict[str, str]]:
        """Return the queue ARN."""
        return {"Attributes": {"QueueArn": "arn:aws:sqs:us-west-2:123456789012:test"}}

    def set_queue_attributes(self, **kwargs: Any) -> None:
        """Accept the SNS delivery policy."""

    def receive_message(self, **kwargs: Any) -> dict[str, list[dict[str, str]]]:
        """Return the published message."""
        return {"Messages": [{"Body": self.body, "ReceiptHandle": "receipt-1"}]}

    def delete_message(self, **kwargs: Any) -> None:
        """Accept message deletion."""

    def delete_queue(self, **kwargs: Any) -> None:
        """Record cleanup."""
        self.deleted = True


def test_aws_backend_proves_receipt_and_cleans_up(provider: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """SNS PASS requires the exact delivery ID to arrive and cleans temporary resources."""
    sqs = _FakeSqs()
    sns = _FakeSns(sqs)
    session = SimpleNamespace(client=lambda name: sns if name == "sns" else sqs)
    fake_boto3 = SimpleNamespace(Session=lambda **kwargs: session)
    monkeypatch.setitem(provider.sys.modules, "boto3", fake_boto3)
    payload = {"delivery_id": "delivery-4", "machine_id": "node-1", "type": "node_failure"}
    assert provider._deliver_aws(payload, "us-west-2") == "aws_sns"
    assert sns.deleted
    assert sqs.deleted


def test_aws_backend_does_not_pass_when_cleanup_fails(provider: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """A delivered AWS message cannot PASS while its probe resources remain."""
    sqs = _FakeSqs()
    sns = _FakeSns(sqs)

    def fail_delete(**_kwargs: Any) -> None:
        raise RuntimeError("denied")

    sns.delete_topic = fail_delete
    session = SimpleNamespace(client=lambda name: sns if name == "sns" else sqs)
    monkeypatch.setitem(provider.sys.modules, "boto3", SimpleNamespace(Session=lambda **kwargs: session))
    with pytest.raises(provider.DeliveryError, match="cleanup failed"):
        provider._deliver_aws({"delivery_id": "delivery-4b"}, "us-west-2")
    assert sqs.deleted


def test_aws_backend_preserves_delivery_and_cleanup_failures(
    provider: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AWS diagnostics retain the delivery failure when cleanup also fails."""
    sqs = _FakeSqs()
    sns = _FakeSns(sqs)

    def no_messages(**_kwargs: Any) -> dict[str, Any]:
        """Simulate an empty receive-message poll."""
        return {}

    sqs.receive_message = no_messages

    def fail_delete(**_kwargs: Any) -> None:
        """Simulate a topic cleanup failure."""
        raise RuntimeError("denied")

    sns.delete_topic = fail_delete
    session = SimpleNamespace(client=lambda name: sns if name == "sns" else sqs)
    monkeypatch.setitem(provider.sys.modules, "boto3", SimpleNamespace(Session=lambda **kwargs: session))
    with pytest.raises(provider.DeliveryError, match=r"did not receive.*cleanup failed"):
        provider._deliver_aws({"delivery_id": "delivery-4c"}, "us-west-2")
    assert sqs.deleted


def test_kubernetes_backend_requires_receiver_ack(provider: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kubernetes PASS requires the in-cluster receiver to echo the delivery ID."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        commands.append(command)
        if "run" in command:
            return SimpleNamespace(stdout='{"delivery_id":"delivery-5","status":"delivered"}\n')
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(provider, "_run", fake_run)
    monkeypatch.setattr(provider.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setenv("KUBECTL", "kubectl --context test-cluster")
    payload = {"delivery_id": "delivery-5", "machine_id": "node-1", "type": "planned_maintenance"}
    assert provider._deliver_kubernetes(payload) == "kubernetes_webhook"
    assert any(command[:3] == ["kubectl", "--context", "test-cluster"] for command in commands)
    assert any("apply" in command for command in commands)
    assert any("run" in command for command in commands)


def test_kubernetes_backend_rejects_wrong_ack(provider: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """An acknowledgement for another notification cannot produce PASS evidence."""
    monkeypatch.setattr(
        provider,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(stdout='{"delivery_id":"different","status":"delivered"}\n'),
    )
    monkeypatch.setattr(provider.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    with pytest.raises(provider.DeliveryError, match="did not acknowledge"):
        provider._deliver_kubernetes({"delivery_id": "delivery-6"})


def test_kubernetes_backend_does_not_pass_when_cleanup_fails(
    provider: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delivered webhook cannot PASS while its ephemeral namespace remains."""
    monkeypatch.setattr(
        provider,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(stdout='{"delivery_id":"delivery-7","status":"delivered"}\n'),
    )
    monkeypatch.setattr(provider.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(provider.DeliveryError, match="cleanup failed"):
        provider._deliver_kubernetes({"delivery_id": "delivery-7"})


def test_kubernetes_backend_preserves_delivery_and_cleanup_failures(
    provider: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kubernetes diagnostics retain the acknowledgement failure when cleanup also fails."""
    monkeypatch.setattr(
        provider,
        "_run",
        lambda *args, **kwargs: SimpleNamespace(stdout='{"delivery_id":"different","status":"delivered"}\n'),
    )
    monkeypatch.setattr(provider.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(provider.DeliveryError, match=r"did not acknowledge.*cleanup failed"):
        provider._deliver_kubernetes({"delivery_id": "delivery-8"})
