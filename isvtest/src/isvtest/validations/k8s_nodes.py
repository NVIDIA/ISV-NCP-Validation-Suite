import json
import shlex
from typing import ClassVar

from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation


class K8sNodeCountCheck(BaseValidation):
    description = "Verify the cluster has the expected number of nodes."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        expected_count = self.config.get("count")
        if expected_count is None:
            self.log.info("Skipping: expected count not configured")
            self.set_passed("Skipped: expected count not configured")
            return

        # Convert to int (Jinja2 templating may produce strings)
        try:
            expected_count = int(expected_count)
        except (ValueError, TypeError):
            self.set_failed(f"Invalid expected count: {expected_count}")
            return

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)
        cmd = f"{kubectl_base} get nodes --no-headers | wc -l"

        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get node count: {result.stderr}")
            return

        try:
            actual_count = int(result.stdout.strip())
        except ValueError:
            self.set_failed(f"Invalid node count output: {result.stdout}")
            return

        if actual_count != expected_count:
            self.set_failed(f"Node count mismatch: expected {expected_count}, found {actual_count}")
            return

        self.set_passed(f"Node count matched: {actual_count}")


class K8sNodeReadyCheck(BaseValidation):
    description = "Verify all nodes in the cluster are in Ready state."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        # Use JSON output for safer parsing
        cmd = f"{kubectl_base} get nodes -o json"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get nodes: {result.stderr}")
            return

        try:
            nodes_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            self.set_failed(f"Failed to parse kubectl JSON output: {e}")
            return

        items = nodes_data.get("items", [])
        if not items:
            self.set_passed("No nodes found in cluster")
            return

        not_ready_nodes = []
        total_nodes = len(items)

        for node in items:
            name = node.get("metadata", {}).get("name", "unknown")
            conditions = node.get("status", {}).get("conditions", [])

            # Find the Ready condition
            ready_condition = next((c for c in conditions if c.get("type") == "Ready"), None)

            if not ready_condition:
                not_ready_nodes.append(f"{name} (No Ready condition found)")
                continue

            status = ready_condition.get("status")
            if status != "True":
                reason = ready_condition.get("reason", "Unknown")
                message = ready_condition.get("message", "")
                not_ready_nodes.append(f"{name} (Status: {status}, Reason: {reason} - {message})")

        require_all_ready = self.config.get("require_all_ready", True)

        if not_ready_nodes:
            msg = f"Found {len(not_ready_nodes)} nodes not Ready: {', '.join(not_ready_nodes)}"
            if require_all_ready:
                self.set_failed(msg)
            else:
                self.set_passed(f"WARNING: {msg} (require_all_ready=False)")
            return

        self.set_passed(f"All {total_nodes} nodes are Ready")


class K8sExpectedNodesCheck(BaseValidation):
    description = "Verify all expected nodes from BoM are present in the cluster."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        expected_names = self.config.get("names", [])
        if not expected_names:
            self.set_passed("Skipped: expected_nodes.names not configured")
            return

        # Get actual nodes
        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)
        cmd = f"{kubectl_base} get nodes -o jsonpath='{{.items[*].metadata.name}}'"

        result = self.run_command(cmd)
        if result.exit_code != 0:
            self.set_failed(f"Failed to get nodes: {result.stderr}")
            return

        actual_nodes = result.stdout.strip().split()
        actual_nodes_set = set(actual_nodes)
        expected_names_set = set(expected_names)

        missing_nodes = expected_names_set - actual_nodes_set
        unexpected_nodes = actual_nodes_set - expected_names_set

        errors = []
        if missing_nodes:
            errors.append(f"Missing nodes: {', '.join(sorted(missing_nodes))}")

        if unexpected_nodes:
            allow_unexpected = self.config.get("allow_unexpected_nodes", True)
            if not allow_unexpected:
                errors.append(f"Unexpected nodes: {', '.join(sorted(unexpected_nodes))}")

        if errors:
            self.set_failed("\n".join(errors))
            return

        msg = f"All {len(expected_names)} expected nodes present"
        if unexpected_nodes:
            msg += f" ({len(unexpected_nodes)} unexpected nodes allowed)"
        self.set_passed(msg)
