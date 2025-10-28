"""Unit tests for K8sPlatformValidatorBase."""

import json
from string import Template
from unittest.mock import MagicMock, patch

from isvtest.workloads.k8s_platform_validator import (
    DEFAULT_IMAGE,
    DEFAULT_NAMESPACE,
    DEFAULT_TEST_SUITE,
    DEFAULT_TIMEOUT,
    MANIFEST_PATH,
    K8sPlatformValidatorBase,
    K8sPlatformValidatorFunctional,
    K8sPlatformValidatorPerformance,
)


class TestK8sPlatformValidatorBaseInit:
    """Test K8sPlatformValidatorBase initialization."""

    def test_default_config(self) -> None:
        """Test workload initializes with default values."""
        workload = K8sPlatformValidatorBase()
        assert workload.config == {}
        assert workload._job_name is None

    def test_custom_config(self) -> None:
        """Test workload initializes with custom config."""
        config = {
            "test_suite": "performance",
            "cloud_provider": "gcp",
            "timeout": 7200,
        }
        workload = K8sPlatformValidatorBase(config=config)
        assert workload.config == config

    def test_markers(self) -> None:
        """Test workload has correct markers."""
        assert "workload" in K8sPlatformValidatorBase.markers
        assert "kubernetes" in K8sPlatformValidatorBase.markers
        assert "l2" in K8sPlatformValidatorBase.markers
        assert "slow" in K8sPlatformValidatorBase.markers

    def test_default_timeout(self) -> None:
        """Test default timeout is set correctly."""
        assert K8sPlatformValidatorBase.timeout == DEFAULT_TIMEOUT


class TestK8sPlatformValidatorFunctional:
    """Test K8sPlatformValidatorFunctional convenience class."""

    def test_default_test_suite(self) -> None:
        """Test functional workload defaults to functional suite."""
        workload = K8sPlatformValidatorFunctional()
        assert workload.config.get("test_suite") == "functional"

    def test_preserves_other_config(self) -> None:
        """Test that other config values are preserved."""
        config = {"cloud_provider": "aws", "timeout": 1800}
        workload = K8sPlatformValidatorFunctional(config=config)
        assert workload.config.get("test_suite") == "functional"
        assert workload.config.get("cloud_provider") == "aws"
        assert workload.config.get("timeout") == 1800


class TestK8sPlatformValidatorPerformance:
    """Test K8sPlatformValidatorPerformance convenience class."""

    def test_default_test_suite(self) -> None:
        """Test performance workload defaults to performance suite."""
        workload = K8sPlatformValidatorPerformance()
        assert workload.config.get("test_suite") == "performance"

    def test_default_timeout(self) -> None:
        """Test performance workload has longer default timeout."""
        workload = K8sPlatformValidatorPerformance()
        assert workload.config.get("timeout") == 10800  # 3 hours

    def test_class_timeout(self) -> None:
        """Test class-level timeout is set for performance tests."""
        assert K8sPlatformValidatorPerformance.timeout == 10800


class TestJobManifestTemplate:
    """Test the Job manifest template."""

    def test_manifest_file_exists(self) -> None:
        """Test that the manifest file exists."""
        assert MANIFEST_PATH.exists(), f"Manifest file not found: {MANIFEST_PATH}"

    def test_template_has_required_placeholders(self) -> None:
        """Test that the template has correct placeholders."""

        content = MANIFEST_PATH.read_text()
        # Check required placeholders exist (using ${VAR} syntax)
        assert "${JOB_NAME}" in content
        assert "${NAMESPACE}" in content
        assert "${TEST_SUITE}" in content
        assert "${CLOUD_PROVIDER}" in content
        assert "${IMAGE}" in content
        assert "${ACTIVE_DEADLINE_SECONDS}" in content
        assert "${SERVICE_ACCOUNT}" in content
        assert "${PULL_SECRET}" in content
        assert "${TEST_ARGS}" in content

    def test_template_substitution(self) -> None:
        """Test that the template can be substituted successfully."""
        content = MANIFEST_PATH.read_text()
        template = Template(content)
        test_args = json.dumps(["-test.timeout", "55m", "-test.v"])
        manifest = template.substitute(
            JOB_NAME="test-job",
            NAMESPACE="test-ns",
            TEST_SUITE="functional",
            ACTIVE_DEADLINE_SECONDS=3600,
            SERVICE_ACCOUNT="test-sa",
            PULL_SECRET="test-secret",
            IMAGE="test-image:latest",
            CLOUD_PROVIDER="aws",
            TEST_ARGS=test_args,
        )
        assert "test-job" in manifest
        assert "test-ns" in manifest
        assert "functional" in manifest
        assert "aws" in manifest
        assert "test-image:latest" in manifest
        assert "apiVersion: batch/v1" in manifest
        assert "kind: Job" in manifest


class TestReportResults:
    """Test result parsing logic."""

    def test_parse_pass_results(self) -> None:
        """Test parsing Go test pass output."""
        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})

        # Simulate Go test output with PASS
        logs = """
=== RUN   TestGPU_Smi_AllNodes
--- PASS: TestGPU_Smi_AllNodes (15.23s)
=== RUN   TestPod_Creation
--- PASS: TestPod_Creation (5.12s)
PASS
"""
        workload._report_results(logs, "functional")
        assert workload._passed is True
        assert "2 passed" in workload._output

    def test_parse_fail_results(self) -> None:
        """Test parsing Go test fail output."""
        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})

        # Simulate Go test output with FAIL
        logs = """
=== RUN   TestGPU_Smi_AllNodes
--- PASS: TestGPU_Smi_AllNodes (15.23s)
=== RUN   TestPod_Creation
--- FAIL: TestPod_Creation (5.12s)
    pod_test.go:45: expected pod to be running
FAIL
"""
        workload._report_results(logs, "functional")
        assert workload._passed is False
        assert "1 passed" in workload._error
        assert "1 failed" in workload._error
        assert "TestPod_Creation" in workload._error

    def test_parse_skip_results(self) -> None:
        """Test parsing Go test skip output."""
        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})

        # Simulate Go test output with SKIP
        logs = """
=== RUN   TestGPU_Smi_AllNodes
--- PASS: TestGPU_Smi_AllNodes (15.23s)
=== RUN   TestEFA_Check
--- SKIP: TestEFA_Check (0.01s)
    efa_test.go:30: EFA not available, skipping
PASS
"""
        workload._report_results(logs, "functional")
        assert workload._passed is True
        assert "1 passed" in workload._output
        assert "1 skipped" in workload._output

    def test_parse_panic_timeout(self) -> None:
        """Test that panics due to timeout are detected as failures."""
        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})

        # Simulate Go test output with panic from timeout
        # Some tests passed before the panic, but overall run failed
        logs = """
=== RUN   TestCudaPerformance
--- PASS: TestCudaPerformance (0.19s)
=== RUN   TestNcclPerformance
panic: test timed out after 14m0s
     running tests:
             TestNcclPerformance (14m0s)

goroutine 110 [running]:
testing.(*M).startAlarm.func1()
     /usr/local/go/src/testing/testing.go:2682 +0x345
"""
        workload._report_results(logs, "performance")
        assert workload._passed is False
        assert "PANICKED" in workload._error
        assert "timeout" in workload._error.lower() or "runtime error" in workload._error.lower()

    def test_parse_panic_runtime_error(self) -> None:
        """Test that runtime panics are detected as failures."""
        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})

        # Simulate Go test output with runtime panic
        logs = """
=== RUN   TestGPU_Smi_AllNodes
--- PASS: TestGPU_Smi_AllNodes (15.23s)
=== RUN   TestBadCode
panic: runtime error: index out of range [5] with length 3

goroutine 1 [running]:
main.badFunction()
     /app/bad.go:10 +0x45
"""
        workload._report_results(logs, "functional")
        assert workload._passed is False
        assert "PANICKED" in workload._error


class TestValidation:
    """Test validation logic."""

    def test_missing_cloud_provider(self) -> None:
        """Test that missing cloud_provider fails validation."""
        workload = K8sPlatformValidatorBase(config={})

        with patch.object(workload, "_check_infrastructure", return_value=True):
            workload.run()

        assert workload._passed is False
        assert "cloud_provider is required" in workload._error

    def test_invalid_test_suite(self) -> None:
        """Test that invalid test_suite fails validation."""
        workload = K8sPlatformValidatorBase(
            config={
                "cloud_provider": "aws",
                "test_suite": "invalid_suite",
            }
        )

        with patch.object(workload, "_check_infrastructure", return_value=True):
            workload.run()

        assert workload._passed is False
        assert "Invalid test_suite" in workload._error

    def test_valid_test_suites(self) -> None:
        """Test all valid test suites are accepted."""
        valid_suites = ["functional", "performance", "nmc", "nmcstorage"]
        for suite in valid_suites:
            workload = K8sPlatformValidatorBase(
                config={
                    "cloud_provider": "aws",
                    "test_suite": suite,
                    "skip_infrastructure_check": True,
                }
            )
            # Mock the job creation and wait
            with (
                patch.object(workload, "_create_job", return_value=False),
            ):
                workload.run()
                # Should not fail on suite validation
                if workload._error:
                    assert "Invalid test_suite" not in workload._error


class TestCheckInfrastructure:
    """Test infrastructure check logic."""

    @patch("isvtest.workloads.k8s_platform_validator.run_kubectl")
    def test_namespace_not_found(self, mock_run_kubectl: MagicMock) -> None:
        """Test failure when namespace doesn't exist."""
        mock_run_kubectl.return_value = MagicMock(returncode=1, stderr="not found")

        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})
        result = workload._check_infrastructure("test-ns", "test-sa", "test-secret")

        assert result is False
        assert "Namespace 'test-ns' not found" in workload._error

    @patch("isvtest.workloads.k8s_platform_validator.run_kubectl")
    def test_service_account_not_found(self, mock_run_kubectl: MagicMock) -> None:
        """Test failure when service account doesn't exist."""

        def kubectl_side_effect(args: list[str]) -> MagicMock:
            if "namespace" in args:
                return MagicMock(returncode=0)
            elif "serviceaccount" in args:
                return MagicMock(returncode=1, stderr="not found")
            return MagicMock(returncode=0)

        mock_run_kubectl.side_effect = kubectl_side_effect

        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})
        result = workload._check_infrastructure("test-ns", "test-sa", "test-secret")

        assert result is False
        assert "ServiceAccount 'test-sa' not found" in workload._error

    @patch("isvtest.workloads.k8s_platform_validator.run_kubectl")
    def test_pull_secret_warning_only(self, mock_run_kubectl: MagicMock) -> None:
        """Test that missing pull secret only warns, doesn't fail."""

        def kubectl_side_effect(args: list[str]) -> MagicMock:
            if "namespace" in args:
                return MagicMock(returncode=0)
            elif "serviceaccount" in args:
                return MagicMock(returncode=0)
            elif "secret" in args:
                return MagicMock(returncode=1, stderr="not found")
            return MagicMock(returncode=0)

        mock_run_kubectl.side_effect = kubectl_side_effect

        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})
        result = workload._check_infrastructure("test-ns", "test-sa", "test-secret")

        # Should still pass - pull secret is optional
        assert result is True

    @patch("isvtest.workloads.k8s_platform_validator.run_kubectl")
    def test_all_infrastructure_exists(self, mock_run_kubectl: MagicMock) -> None:
        """Test success when all infrastructure exists."""
        mock_run_kubectl.return_value = MagicMock(returncode=0)

        workload = K8sPlatformValidatorBase(config={"cloud_provider": "aws"})
        result = workload._check_infrastructure("test-ns", "test-sa", "test-secret")

        assert result is True


class TestConstants:
    """Test module constants."""

    def test_default_namespace(self) -> None:
        """Test default namespace constant."""
        assert DEFAULT_NAMESPACE == "dgxc-validation"

    def test_default_image(self) -> None:
        """Test default image constant."""
        assert DEFAULT_IMAGE == "nvcr.io/nv-ngc-devops/k8s-platform-validator:latest"

    def test_default_timeout(self) -> None:
        """Test default timeout constant."""
        assert DEFAULT_TIMEOUT == 3600

    def test_default_test_suite(self) -> None:
        """Test default test suite constant."""
        assert DEFAULT_TEST_SUITE == "functional"
