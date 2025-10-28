import json
import shlex
from typing import ClassVar

from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation


class K8sMigConfigCheck(BaseValidation):
    description = "Check if MIG (Multi-Instance GPU) labels are available and match configuration."
    markers: ClassVar[list[str]] = ["kubernetes", "gpu"]

    def run(self) -> None:
        require_mig = self.config.get("require_mig", False)
        expected_labels = self.config.get("expected_labels", {})

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        # Get all nodes JSON to check labels
        cmd = f"{kubectl_base} get nodes -o json"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get nodes: {result.stderr}")
            return

        try:
            nodes_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.set_failed("Failed to parse kubectl output")
            return

        mig_nodes = []
        mismatch_nodes = []

        for node in nodes_data.get("items", []):
            name = node.get("metadata", {}).get("name", "unknown")
            labels = node.get("metadata", {}).get("labels", {})

            # Check if node has any MIG labels
            has_mig = any("nvidia.com/mig" in k for k in labels.keys())
            if has_mig:
                mig_nodes.append(name)

            # Verify specific expected labels if configured
            if expected_labels:
                for key, expected_value in expected_labels.items():
                    # Only check if the key exists or if we expect it to exist?
                    # Generally, if we expect a label value, we expect the label to be there.
                    if key not in labels:
                        # Only report missing label if we require MIG or if the node has other MIG labels
                        # (Assuming mixed cluster: non-MIG nodes shouldn't fail this unless we target them specifically)
                        if require_mig or has_mig:
                            mismatch_nodes.append(f"{name} (missing label {key})")
                    elif str(labels[key]) != str(expected_value):
                        mismatch_nodes.append(f"{name} ({key}: {labels[key]} != {expected_value})")

        if mismatch_nodes:
            self.set_failed(f"MIG label mismatch on nodes: {', '.join(mismatch_nodes)}")
            return

        if mig_nodes:
            msg = f"MIG labels found on {len(mig_nodes)} nodes: {', '.join(mig_nodes)}"
            if expected_labels:
                msg += f" (verified {len(expected_labels)} expected values)"
            self.set_passed(msg)
        else:
            if require_mig:
                self.set_failed("No MIG labels found on any node")
            else:
                self.set_passed("No MIG labels found (MIG not configured)")
