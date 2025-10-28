import shlex
from typing import ClassVar

from isvtest.core.k8s import get_kubectl_command
from isvtest.core.validation import BaseValidation


class K8sPodHealthCheck(BaseValidation):
    description = "Verify all pods in the cluster are in a healthy state (Running or Succeeded)."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        # Configurable ignore phases
        ignore_phases = self.config.get("ignore_phases", [])

        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        # We generally query for everything NOT running/succeeded
        cmd = f"{kubectl_base} get pods -A --no-headers --field-selector status.phase!=Running,status.phase!=Succeeded"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get pod status: {result.stderr}")
            return

        unhealthy_pods = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 4:
                namespace = parts[0]
                name = parts[1]
                status = parts[3]

                if status in ignore_phases:
                    continue

                unhealthy_pods.append(f"{namespace}/{name} ({status})")

        if unhealthy_pods:
            self.set_failed(
                f"Found {len(unhealthy_pods)} unhealthy pods: {', '.join(unhealthy_pods[:10])}"
                + (f"... and {len(unhealthy_pods) - 10} more" if len(unhealthy_pods) > 10 else "")
            )
            return

        self.set_passed("All pods are Running or Succeeded")


class K8sNoPendingPodsCheck(BaseValidation):
    description = "Verify no pods are stuck in Pending state."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        cmd = f"{kubectl_base} get pods -A --field-selector status.phase=Pending --no-headers"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get pending pods: {result.stderr}")
            return

        pending_pods = []
        for line in result.stdout.splitlines():
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    pending_pods.append(f"{parts[0]}/{parts[1]}")

        if pending_pods:
            self.set_failed(f"Found {len(pending_pods)} pending pods: {', '.join(pending_pods)}")
            return

        self.set_passed("No pending pods found")


class K8sNoErrorPodsCheck(BaseValidation):
    description = "Verify no pods are in Error or CrashLoopBackOff state."
    markers: ClassVar[list[str]] = ["kubernetes"]

    def run(self) -> None:
        kubectl_parts = get_kubectl_command()
        kubectl_base = " ".join(shlex.quote(part) for part in kubectl_parts)

        # Configurable error states
        error_states = self.config.get(
            "error_states",
            [
                "Error",
                "CrashLoopBackOff",
                "ImagePullBackOff",
                "ErrImagePull",
                "CreateContainerConfigError",
            ],
        )

        cmd = f"{kubectl_base} get pods -A --no-headers"
        result = self.run_command(cmd)

        if result.exit_code != 0:
            self.set_failed(f"Failed to get pods: {result.stderr}")
            return

        error_pods = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            # Output format: NAMESPACE NAME READY STATUS RESTARTS AGE
            parts = line.split()
            if len(parts) >= 4:
                namespace = parts[0]
                name = parts[1]
                status = parts[3]

                if status in error_states:
                    error_pods.append(f"{namespace}/{name} ({status})")

        if error_pods:
            self.set_failed(f"Found {len(error_pods)} pods in error state: {', '.join(error_pods)}")
            return

        self.set_passed("No pods in error state found")
