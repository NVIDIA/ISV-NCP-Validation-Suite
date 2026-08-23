#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deliver and verify a tenant notification for BFX05-01 or BFX06-01.

The script emits only the provider-neutral JSON consumed by the break-fix
validators. It supports three delivery transports:

* ``aws`` creates an ephemeral SNS topic and SQS subscription, publishes the
  notification, proves that the subscriber received the same delivery ID, and
  removes both resources.
* ``kubernetes`` creates an ephemeral in-cluster HTTP receiver, posts from a
  short-lived pod, verifies its acknowledgement, and removes the namespace.
* ``webhook`` posts to a configured Slack, Teams, or generic HTTP endpoint and
  treats a successful HTTP response as the delivery acknowledgement.

Resource identifiers, webhook URLs, response bodies, and credentials are never
included in the output contract.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error, request

_RECEIVER_CODE = r"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size))
            delivery_id = payload["delivery_id"]
            if not isinstance(delivery_id, str) or not delivery_id:
                raise ValueError("missing delivery_id")
            body = json.dumps({"delivery_id": delivery_id, "status": "delivered"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        return

HTTPServer(("0.0.0.0", 8080), Receiver).serve_forever()
"""


class DeliveryError(RuntimeError):
    """Raised when a notification cannot be proved delivered."""


def _timestamp(value: datetime) -> str:
    """Render a UTC timestamp in the provider-neutral ISO 8601 format."""
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _emit(payload: dict[str, Any]) -> int:
    """Write one JSON document and return a process exit code."""
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if payload.get("success") else 1


def _payload(args: argparse.Namespace, delivery_id: str, started_at: datetime) -> dict[str, str]:
    """Build the event delivered to the selected communication system."""
    common = {
        "delivery_id": delivery_id,
        "machine_id": args.machine_id,
        "type": args.event_type,
        "message": args.message,
    }
    if args.event_type == "planned_maintenance":
        common["scheduled_at"] = _timestamp(started_at + timedelta(hours=args.schedule_hours))
    else:
        common["failed_at"] = _timestamp(started_at)
    return common


def _deliver_aws(payload: dict[str, str], region: str) -> str:
    """Publish through SNS and prove receipt through an ephemeral SQS subscriber."""
    try:
        # Lazy import: boto3 is needed only by the optional AWS transport.
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency is present in the workspace
        raise DeliveryError("AWS notification backend requires boto3") from exc

    suffix = uuid.uuid4().hex[:12]
    session = boto3.Session(region_name=region)
    sns = session.client("sns")
    sqs = session.client("sqs")
    topic_arn = ""
    queue_url = ""
    try:
        topic_arn = sns.create_topic(Name=f"isvtest-notification-{suffix}")["TopicArn"]
        queue_url = sqs.create_queue(
            QueueName=f"isvtest-notification-{suffix}",
            Attributes={"MessageRetentionPeriod": "300", "ReceiveMessageWaitTimeSeconds": "10"},
        )["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "sns.amazonaws.com"},
                    "Action": "sqs:SendMessage",
                    "Resource": queue_arn,
                    "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
                }
            ],
        }
        sqs.set_queue_attributes(QueueUrl=queue_url, Attributes={"Policy": json.dumps(policy)})
        sns.subscribe(
            TopicArn=topic_arn,
            Protocol="sqs",
            Endpoint=queue_arn,
            Attributes={"RawMessageDelivery": "true"},
            ReturnSubscriptionArn=True,
        )
        sns.publish(TopicArn=topic_arn, Message=json.dumps(payload, separators=(",", ":")))

        for _ in range(3):
            response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=10)
            for message in response.get("Messages", []):
                try:
                    received = json.loads(message["Body"])
                except (KeyError, json.JSONDecodeError):
                    continue
                if received.get("delivery_id") == payload["delivery_id"]:
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
                    return "aws_sns"
        raise DeliveryError("AWS notification subscriber did not receive the published event")
    except DeliveryError:
        raise
    except Exception as exc:
        raise DeliveryError(f"AWS notification delivery failed: {type(exc).__name__}") from exc
    finally:
        pending_error = sys.exc_info()[1]
        cleanup_failed = False
        if topic_arn:
            try:
                sns.delete_topic(TopicArn=topic_arn)
            except Exception:
                cleanup_failed = True
        if queue_url:
            try:
                sqs.delete_queue(QueueUrl=queue_url)
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            message = "AWS notification cleanup failed"
            if isinstance(pending_error, DeliveryError):
                message = f"{pending_error}; {message}"
            raise DeliveryError(message) from pending_error


def _kubectl_base() -> list[str]:
    """Return the configured kubectl command without invoking a shell."""
    command = shlex.split(os.environ.get("KUBECTL", "kubectl"))
    if not command:
        raise DeliveryError("KUBECTL command is empty")
    return command


def _run(command: list[str], *, stdin: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and convert diagnostics to a sanitized delivery error."""
    try:
        result = subprocess.run(command, input=stdin, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeliveryError(f"Kubernetes notification command failed: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise DeliveryError("Kubernetes notification command returned a non-zero status")
    return result


def _kubernetes_objects(namespace: str, receiver_name: str) -> dict[str, Any]:
    """Build the ephemeral HTTP receiver Pod and Service manifests."""
    labels = {"app.kubernetes.io/name": "isvtest-notification-receiver", "isvtest.nvidia.com/run": receiver_name}
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": receiver_name, "namespace": namespace, "labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "receiver",
                            "image": "python:3.12-alpine",
                            "command": ["python", "-c", _RECEIVER_CODE],
                            "ports": [{"containerPort": 8080}],
                            "readinessProbe": {"tcpSocket": {"port": 8080}, "initialDelaySeconds": 1},
                            "resources": {
                                "requests": {"cpu": "10m", "memory": "16Mi"},
                                "limits": {"cpu": "100m", "memory": "64Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 65532,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                },
            },
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "receiver", "namespace": namespace, "labels": labels},
                "spec": {"selector": labels, "ports": [{"port": 8080, "targetPort": 8080}]},
            },
        ],
    }


def _extract_acknowledgement(output: str, delivery_id: str) -> bool:
    """Return whether command output contains the receiver acknowledgement."""
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        if value.get("delivery_id") == delivery_id and value.get("status") == "delivered":
            return True
    return False


def _deliver_kubernetes(payload: dict[str, str]) -> str:
    """Post from one pod to an ephemeral in-cluster HTTP receiver."""
    kubectl = _kubectl_base()
    suffix = uuid.uuid4().hex[:10]
    namespace = f"isvtest-notification-{suffix}"
    receiver_name = f"receiver-{suffix}"
    sender_name = f"sender-{suffix}"
    created_namespace = False
    try:
        _run([*kubectl, "create", "namespace", namespace])
        created_namespace = True
        objects = json.dumps(_kubernetes_objects(namespace, receiver_name))
        _run([*kubectl, "apply", "-f", "-"], stdin=objects)
        _run([*kubectl, "wait", "--for=condition=Ready", f"pod/{receiver_name}", "-n", namespace, "--timeout=120s"])
        result = _run(
            [
                *kubectl,
                "run",
                sender_name,
                "-n",
                namespace,
                "--image=curlimages/curl:8.10.1",
                "--restart=Never",
                "--attach",
                "--rm",
                "--quiet",
                "--command",
                "--",
                "curl",
                "--fail-with-body",
                "--silent",
                "--show-error",
                "--max-time",
                "30",
                "-H",
                "Content-Type: application/json",
                "--data-binary",
                json.dumps(payload, separators=(",", ":")),
                "http://receiver:8080/notify",
            ],
            timeout=180,
        )
        if not _extract_acknowledgement(result.stdout, payload["delivery_id"]):
            raise DeliveryError("Kubernetes webhook receiver did not acknowledge the notification")
        return "kubernetes_webhook"
    finally:
        if created_namespace:
            pending_error = sys.exc_info()[1]
            cleanup_failed = False
            try:
                cleanup = subprocess.run(
                    [
                        *kubectl,
                        "delete",
                        "namespace",
                        namespace,
                        "--wait=true",
                        "--timeout=60s",
                        "--ignore-not-found",
                    ],
                    text=True,
                    capture_output=True,
                    timeout=70,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed = True
            else:
                cleanup_failed = cleanup.returncode != 0
            if cleanup_failed:
                message = "Kubernetes notification cleanup failed"
                if isinstance(pending_error, DeliveryError):
                    message = f"{pending_error}; {message}"
                raise DeliveryError(message) from pending_error


def _deliver_webhook(payload: dict[str, str], url: str, channel: str) -> str:
    """Post to a configured Slack, Teams, or generic HTTP webhook."""
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1:"):
        raise DeliveryError("Webhook URL must use HTTPS (loopback HTTP is allowed for local testing)")
    outgoing: dict[str, Any] = payload
    text = (
        f"{payload['message']}\nNode: {payload['machine_id']}\n"
        f"Event: {payload['type']}\nDelivery ID: {payload['delivery_id']}"
    )
    if channel == "slack":
        outgoing = {"text": text}
    elif channel == "teams":
        outgoing = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [{"type": "TextBlock", "text": text, "wrap": True}],
                    },
                }
            ],
        }
    body = json.dumps(outgoing, separators=(",", ":")).encode()
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise DeliveryError("Webhook endpoint did not accept the notification")
    except DeliveryError:
        raise
    except (error.URLError, TimeoutError) as exc:
        raise DeliveryError(f"Webhook notification delivery failed: {type(exc).__name__}") from exc
    return channel


def _parse_args() -> argparse.Namespace:
    """Parse the delivery probe arguments."""
    parser = argparse.ArgumentParser(description="Deliver and verify one tenant notification")
    parser.add_argument("--backend", choices=("aws", "kubernetes", "webhook"), required=True)
    parser.add_argument("--event-type", choices=("planned_maintenance", "node_failure"), required=True)
    parser.add_argument("--machine-id", default="notification-probe-node")
    parser.add_argument("--message", required=True)
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--schedule-hours", type=int, default=24)
    parser.add_argument("--webhook-url", default=os.environ.get("ISVTEST_NOTIFICATION_WEBHOOK_URL", ""))
    parser.add_argument(
        "--webhook-channel",
        choices=("slack", "teams", "webhook"),
        default=os.environ.get("ISVTEST_NOTIFICATION_CHANNEL", "webhook"),
    )
    args = parser.parse_args()
    if not args.machine_id.strip() or not args.message.strip():
        parser.error("--machine-id and --message must be non-empty")
    if args.event_type == "planned_maintenance" and args.schedule_hours <= 0:
        parser.error("--schedule-hours must be positive")
    if args.backend == "webhook" and not args.webhook_url:
        parser.error("--webhook-url or ISVTEST_NOTIFICATION_WEBHOOK_URL is required")
    return args


def main() -> int:
    """Deliver a notification and emit normalized proof of receipt."""
    args = _parse_args()
    metadata = {
        "platform": args.backend,
        "test_name": (
            "query_planned_notifications" if args.event_type == "planned_maintenance" else "query_failure_notifications"
        ),
    }
    started_at = datetime.now(UTC)
    delivery_id = str(uuid.uuid4())
    payload = _payload(args, delivery_id, started_at)
    try:
        if args.backend == "aws":
            channel = _deliver_aws(payload, args.region)
        elif args.backend == "kubernetes":
            channel = _deliver_kubernetes(payload)
        else:
            channel = _deliver_webhook(payload, args.webhook_url, args.webhook_channel)
    except DeliveryError as exc:
        return _emit(
            {
                "success": False,
                **metadata,
                "notification_channel_observable": False,
                "notifications": [],
                "error": str(exc),
            }
        )

    notified_at = datetime.now(UTC)
    record = {
        **payload,
        "notified_at": _timestamp(notified_at),
        "channel": channel,
        "delivery_status": "delivered",
    }
    return _emit(
        {
            "success": True,
            **metadata,
            "notification_channel_observable": True,
            "notifications": [record],
        }
    )


if __name__ == "__main__":
    sys.exit(main())
