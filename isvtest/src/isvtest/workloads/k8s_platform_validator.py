"""K8s Platform Validator workload for running L2 validation tests.

This module provides a workload that runs the k8s-platform-validator
Go-based e2e tests as a Kubernetes Job.
"""

import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, ClassVar

from isvtest.core.k8s import (
    delete_job,
    get_job_pods,
    get_kubectl_command,
    get_pod_logs,
    run_kubectl,
    wait_for_job_completion,
)
from isvtest.core.runners import Runner
from isvtest.core.workload import BaseWorkloadCheck

# Default values for the platform validator
DEFAULT_NAMESPACE = "dgxc-validation"
DEFAULT_IMAGE = "nvcr.io/nv-ngc-devops/k8s-platform-validator:latest"
DEFAULT_TIMEOUT = 3600  # 1 hour
DEFAULT_TEST_SUITE = "functional"


@dataclass
class GoTestResult:
    """Result of a single Go test parsed from test output."""

    name: str
    passed: bool
    skipped: bool
    duration: float | None
    message: str


# Path to the job manifest template
MANIFEST_PATH = Path(__file__).parent / "manifests" / "k8s" / "platform_validator_job.yaml"


class K8sPlatformValidatorBase(BaseWorkloadCheck):
    """Run k8s-platform-validator tests as a K8s Job.

    This workload deploys the k8s-platform-validator container image
    as a Kubernetes Job to run comprehensive e2e validation tests.

    Config options:
        test_suite: Test suite to run (functional, performance, nmc, nmcstorage). Default: functional
        cloud_provider: Cloud provider (aws, gcp, azure). Required.
        timeout: Job timeout in seconds. Default: 3600 (1 hour)
        image: Container image. Default: nvcr.io/nv-ngc-devops/k8s-platform-validator:latest
        namespace: Target namespace. Default: dgxc-validation
        service_account: ServiceAccount name. Default: k8s-platform-validator
        pull_secret: Image pull secret name. Default: nvidia-ngcuser-pull-secret
        cleanup: Whether to cleanup job after completion. Default: true
        skip_infrastructure_check: Skip checking for Helm infrastructure. Default: false
        run_tests: Regex pattern to match test names to run (Go -test.run flag).
                   Example: "TestRealGPU|TestAllPods" runs only matching tests.
        skip_tests: Regex pattern to match test names to skip (Go -test.skip flag).
                    Example: "TestEFA" skips all EFA-related tests.

    Example config:
        - K8sPlatformValidatorBase:
            test_suite: functional
            cloud_provider: aws
            timeout: 3600
            skip_tests: "TestEFA"  # Skip EFA tests on non-AWS environments
    """

    description = "K8s platform validation (L2) - e2e tests from k8s-platform-validator"
    timeout: ClassVar[int] = DEFAULT_TIMEOUT
    markers: ClassVar[list[str]] = ["workload", "kubernetes", "l2", "slow"]

    # Exclude base class from discovery
    _exclude_from_discovery: ClassVar[bool] = True

    def __init__(self, runner: Runner | None = None, config: dict[str, Any] | None = None) -> None:
        """Initialize the K8s Platform Validator workload.

        Args:
            runner: Command runner instance.
            config: Configuration dictionary with workload options.
        """
        super().__init__(runner, config)
        self._job_name: str | None = None

    def run(self) -> None:
        """Execute the k8s-platform-validator tests."""
        # Get configuration
        test_suite = self.config.get("test_suite", DEFAULT_TEST_SUITE)
        cloud_provider = self.config.get("cloud_provider")
        timeout = int(self.config.get("timeout", DEFAULT_TIMEOUT))
        namespace = self.config.get("namespace", DEFAULT_NAMESPACE)
        image = self.config.get("image", DEFAULT_IMAGE)
        service_account = self.config.get("service_account", "k8s-platform-validator")
        pull_secret = self.config.get("pull_secret", "nvidia-ngcuser-pull-secret")
        cleanup = self.config.get("cleanup", True)
        skip_infra_check = self.config.get("skip_infrastructure_check", False)
        run_tests = self.config.get("run_tests")  # Regex pattern for tests to run
        skip_tests = self.config.get("skip_tests")  # Regex pattern for tests to skip

        # Validate required parameters
        if not cloud_provider:
            self.set_failed("cloud_provider is required (aws, gcp, azure)")
            return

        valid_suites = ["functional", "performance", "nmc", "nmcstorage"]
        if test_suite not in valid_suites:
            self.set_failed(f"Invalid test_suite '{test_suite}'. Must be one of: {valid_suites}")
            return

        # Check for infrastructure (namespace, service account)
        if not skip_infra_check:
            if not self._check_infrastructure(namespace, service_account, pull_secret):
                return

        # Generate unique job name
        self._job_name = f"isvtest-validator-{test_suite}-{uuid.uuid4().hex[:8]}"

        # Calculate test timeout in minutes (slightly less than job deadline)
        test_timeout_min = max(1, (timeout - 60) // 60)  # Leave 1 min buffer

        # Build test arguments
        test_args = ["-test.timeout", f"{test_timeout_min}m", "-test.v"]
        if run_tests:
            test_args.extend(["-test.run", run_tests])
            self.log.info(f"Running only tests matching: {run_tests}")
        if skip_tests:
            test_args.extend(["-test.skip", skip_tests])
            self.log.info(f"Skipping tests matching: {skip_tests}")

        # Format args as JSON array for YAML
        test_args_json = json.dumps(test_args)

        # Load and render job manifest template
        if not MANIFEST_PATH.exists():
            self.set_failed(f"Manifest file not found: {MANIFEST_PATH}")
            return

        template_content = MANIFEST_PATH.read_text()
        template = Template(template_content)
        manifest = template.substitute(
            JOB_NAME=self._job_name,
            NAMESPACE=namespace,
            TEST_SUITE=test_suite,
            ACTIVE_DEADLINE_SECONDS=timeout,
            SERVICE_ACCOUNT=service_account,
            PULL_SECRET=pull_secret,
            IMAGE=image,
            CLOUD_PROVIDER=cloud_provider,
            TEST_ARGS=test_args_json,
        )

        self.log.info(f"Starting k8s-platform-validator ({test_suite}) tests...")
        self.log.info(f"Job: {self._job_name}, Namespace: {namespace}, Timeout: {timeout}s")

        # Create the job
        if not self._create_job(manifest, namespace):
            return

        logs = ""
        completed = False
        status = ""

        try:
            # Wait for job completion
            self.log.info(f"Waiting for job {self._job_name} to complete...")
            completed, status = wait_for_job_completion(self._job_name, namespace, timeout=timeout)

            # Collect logs
            logs = self._collect_logs(namespace)

        finally:
            # Cleanup early so output appears before subtests
            # This ensures pytest's "PASSED" appears right after subtest output
            if cleanup and self._job_name:
                self.log.info(f"Cleaning up job {self._job_name}...")
                delete_job(self._job_name, namespace, wait=False)

        # Report results after cleanup
        if not completed:
            self.set_failed(
                f"Job timed out after {timeout}s. Status: {status}\n"
                f"Partial logs:\n{logs[:2000] if logs else 'No logs available'}"
            )
            return

        if status == "Complete":
            self._report_results(logs, test_suite)
        else:
            # Job failed
            self.set_failed(f"Job failed with status: {status}\nLogs:\n{logs}")

    def _check_infrastructure(self, namespace: str, service_account: str, pull_secret: str) -> bool:
        """Check that required infrastructure exists.

        Args:
            namespace: Target namespace.
            service_account: ServiceAccount name.
            pull_secret: Image pull secret name.

        Returns:
            True if infrastructure exists, False otherwise.
        """
        # Check namespace exists
        result = run_kubectl(["get", "namespace", namespace])
        if result.returncode != 0:
            self.set_failed(
                f"Namespace '{namespace}' not found. "
                f"Install k8s-platform-validator Helm chart first:\n"
                f"  helm install k8s-platform-validator ./helm/k8s-platform-validator"
            )
            return False

        # Check service account exists
        result = run_kubectl(["get", "serviceaccount", service_account, "-n", namespace])
        if result.returncode != 0:
            self.set_failed(
                f"ServiceAccount '{service_account}' not found in namespace '{namespace}'. "
                f"Install k8s-platform-validator Helm chart first."
            )
            return False

        # Check pull secret exists
        result = run_kubectl(["get", "secret", pull_secret, "-n", namespace])
        if result.returncode != 0:
            self.log.warning(
                f"Pull secret '{pull_secret}' not found in namespace '{namespace}'. "
                f"Job may fail if image requires authentication."
            )
            # Don't fail, just warn - the secret might not be needed for public images

        return True

    def _create_job(self, manifest: str, namespace: str) -> bool:
        """Create the Kubernetes Job.

        Args:
            manifest: Job manifest YAML.
            namespace: Target namespace.

        Returns:
            True if job created successfully, False otherwise.
        """
        kubectl_parts = get_kubectl_command()

        try:
            result = subprocess.run(
                kubectl_parts + ["apply", "-f", "-", "-n", namespace],
                input=manifest,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.set_failed(f"Failed to create job: {result.stderr}")
                return False
            self.log.info(f"Job {self._job_name} created successfully")
            self.log.info("")
            self.log.info("=" * 60)
            self.log.info("To stream live logs, run in another terminal:")
            self.log.info(f"  kubectl logs -f -l job-name={self._job_name} -n {namespace}")
            self.log.info("=" * 60)
            self.log.info("")
            return True
        except subprocess.TimeoutExpired:
            self.set_failed("Timeout creating job")
            return False
        except Exception as e:
            self.set_failed(f"Exception creating job: {e}")
            return False

    def _collect_logs(self, namespace: str) -> str:
        """Collect logs from the job's pod.

        Args:
            namespace: Target namespace.

        Returns:
            Pod logs as string.
        """
        if not self._job_name:
            return ""

        pods = get_job_pods(self._job_name, namespace)
        if not pods:
            self.log.warning(f"No pods found for job {self._job_name}")
            return ""

        # Get logs from first pod
        pod_name = pods[0]
        logs = get_pod_logs(pod_name, namespace, timeout=60)
        return logs

    def _parse_go_test_results(self, logs: str) -> list[GoTestResult]:
        """Parse Go test output and extract individual test results.

        Go test output format:
            === RUN   TestName
            --- PASS: TestName (1.23s)
            --- FAIL: TestName (0.50s)
            --- SKIP: TestName (0.00s)

        For subtests:
            === RUN   TestName/SubtestName
            --- PASS: TestName/SubtestName (0.10s)

        Args:
            logs: Pod logs containing test output.

        Returns:
            List of GoTestResult with name, status, duration, and message.
        """
        results: list[GoTestResult] = []

        # Pattern to match test results with duration
        # Matches: "--- PASS: TestName (1.23s)" or "--- FAIL: TestName/Subtest (0.50s)"
        pattern = r"---\s+(PASS|FAIL|SKIP):\s+(\S+)\s+\(([^)]+)\)"

        for match in re.finditer(pattern, logs):
            status, test_name, duration_str = match.groups()

            # Parse duration (e.g., "1.23s" -> 1.23)
            duration = None
            if duration_str:
                try:
                    duration = float(duration_str.rstrip("s"))
                except ValueError:
                    pass

            # Try to extract failure message for failed tests
            message = ""
            if status == "FAIL":
                # Look for error messages before the FAIL line
                # Go test typically shows errors indented with spaces before the --- FAIL line
                # Look backwards for test output (indented lines after === RUN)
                run_pattern = rf"===\s+RUN\s+{re.escape(test_name)}\n(.*?)---\s+FAIL:\s+{re.escape(test_name)}"
                run_match = re.search(run_pattern, logs, re.DOTALL)
                if run_match:
                    # Get the test output between RUN and FAIL
                    test_output = run_match.group(1).strip()
                    if test_output:
                        # Truncate long messages
                        message = test_output[:500] + ("..." if len(test_output) > 500 else "")
            elif status == "SKIP":
                # Look for skip reason
                skip_pattern = rf"{re.escape(test_name)}.*?:\s*(.+?)(?:\n|$)"
                skip_match = re.search(skip_pattern, logs)
                if skip_match:
                    message = skip_match.group(1).strip()

            results.append(
                GoTestResult(
                    name=test_name,
                    passed=status == "PASS",
                    skipped=status == "SKIP",
                    duration=duration,
                    message=message,
                )
            )

        return results

    def _report_results(self, logs: str, test_suite: str) -> None:
        """Parse and report test results from logs.

        Args:
            logs: Pod logs containing test output.
            test_suite: Name of the test suite run.
        """
        # Parse individual Go test results
        go_test_results = self._parse_go_test_results(logs)

        # Count results
        pass_count = sum(1 for r in go_test_results if r.passed)
        fail_count = sum(1 for r in go_test_results if not r.passed and not r.skipped)
        skip_count = sum(1 for r in go_test_results if r.skipped)

        # Extract test names for summary
        passed_tests = [r.name for r in go_test_results if r.passed]
        failed_tests = [r.name for r in go_test_results if not r.passed and not r.skipped]
        skipped_tests = [r.name for r in go_test_results if r.skipped]

        # Detect panics (timeout, runtime errors, etc.)
        # Go test panics when timeout is exceeded: "panic: test timed out after Xm0s"
        has_panic = "panic:" in logs

        # Check for overall pass/fail - Go test prints "PASS" or "FAIL" as a standalone line
        # Note: There may be cleanup output after PASS/FAIL, so we check for the line anywhere
        log_lines = [line.strip() for line in logs.splitlines()]
        overall_passed = "PASS" in log_lines
        overall_failed = "FAIL" in log_lines

        # Build detailed results message
        results_details = [f"Results: {pass_count} passed, {fail_count} failed, {skip_count} skipped"]
        if has_panic:
            results_details.append("\nWARNING: Test panicked (likely timeout or runtime error)")

        if passed_tests:
            results_details.append("\nPassed tests:\n  - " + "\n  - ".join(passed_tests))

        if failed_tests:
            results_details.append("\nFailed tests:\n  - " + "\n  - ".join(failed_tests))

        if skipped_tests:
            results_details.append("\nSkipped tests:\n  - " + "\n  - ".join(skipped_tests))

        details_str = "\n".join(results_details)

        # Log full test output for visibility
        self.log.info("=" * 60)
        self.log.info("K8s Platform Validator - Full Test Output")
        self.log.info("=" * 60)
        for line in logs.split("\n"):
            self.log.info(line)
        self.log.info("=" * 60)

        # Report each Go test as a pytest subtest
        # Filter to only top-level tests (no "/" in name) to avoid duplicate reporting
        # of parent tests when subtests exist
        top_level_tests = [r for r in go_test_results if "/" not in r.name]

        # Report top-level tests as subtests
        # Flush logging before subtests for cleaner output
        if top_level_tests and self._subtests is not None:
            import sys

            for handler in self.log.handlers:
                handler.flush()
            sys.stdout.flush()
            sys.stderr.flush()

        for result in top_level_tests:
            self.report_subtest(
                name=result.name,
                passed=result.passed,
                message=result.message,
                skipped=result.skipped,
                duration=result.duration,
            )

        # Add newline after subtests for cleaner output
        if top_level_tests and self._subtests is not None:
            print()  # Newline after subtests

        # Store full logs in output
        self._output = logs

        # Subtests are automatically added to JUnit XML via the subtests fixture
        # (see isvtest.testing.subtests.pytest_sessionfinish)

        # Determine pass/fail status
        # Priority: panic > explicit FAIL line > individual failures > overall PASS > individual passes
        if has_panic:
            self.set_failed(f"Platform validator ({test_suite}) PANICKED (timeout or runtime error)\n{details_str}")
        elif overall_failed:
            self.set_failed(f"Platform validator ({test_suite}) FAILED\n{details_str}")
        elif fail_count > 0:
            self.set_failed(f"Platform validator ({test_suite}) FAILED\n{details_str}")
        elif overall_passed:
            self.set_passed(f"Platform validator ({test_suite}) PASSED\n{details_str}")
        elif pass_count > 0 and fail_count == 0:
            # Some tests passed, no failures, but no explicit "PASS" line found
            # This could indicate incomplete run or unexpected output format
            self.log.warning("Tests passed but no overall PASS detected - possible incomplete run")
            self.set_passed(f"Platform validator ({test_suite}) PASSED (partial)\n{details_str}")
        else:
            # Could not determine pass/fail from logs
            self.log.warning("Could not parse test results from logs")
            if "ok" in logs.lower() and "fail" not in logs.lower():
                self.set_passed(f"Platform validator ({test_suite}) completed (results unclear)")
            else:
                self.set_failed(f"Platform validator ({test_suite}) status unclear\nPreview:\n{logs[:2000]}")


class K8sPlatformValidatorFunctional(K8sPlatformValidatorBase):
    """Run k8s-platform-validator functional tests.

    Convenience class with pre-configured test_suite=functional.
    Functional tests validate core K8s functionality including:
    - GPU scheduling and access
    - Pod creation and lifecycle
    - EFA networking (if applicable)
    - ArgoCD applications (if applicable)
    """

    description = "K8s platform validation (L2) - functional tests"

    def __init__(self, runner: Runner | None = None, config: dict[str, Any] | None = None) -> None:
        """Initialize with functional test suite."""
        config = config or {}
        config.setdefault("test_suite", "functional")
        super().__init__(runner, config)


class K8sPlatformValidatorPerformance(K8sPlatformValidatorBase):
    """Run k8s-platform-validator performance tests.

    Convenience class with pre-configured test_suite=performance.
    Performance tests include:
    - NCCL bandwidth tests
    - CUDA benchmarks
    - NVBandwidth measurements
    - NeMo training benchmarks

    Note: These tests are significantly longer running (typically 1-3 hours).
    """

    description = "K8s platform validation (L2) - performance tests"
    timeout: ClassVar[int] = 10800  # 3 hours

    def __init__(self, runner: Runner | None = None, config: dict[str, Any] | None = None) -> None:
        """Initialize with performance test suite."""
        config = config or {}
        config.setdefault("test_suite", "performance")
        config.setdefault("timeout", 10800)
        super().__init__(runner, config)
