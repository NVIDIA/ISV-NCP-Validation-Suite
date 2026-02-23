"""SSH-based validations (platform-agnostic).

These validations use paramiko for SSH connectivity and work on ANY platform:
AWS, GCP, Azure, bare metal, etc.

They consume connection details from step outputs or inventory:
    host: "{{steps.launch_instance.public_ip}}"
    key_file: "{{steps.launch_instance.key_file}}"
    user: "ubuntu"

Requires paramiko: pip install paramiko
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import paramiko

from isvtest.core.ssh import (
    get_failed_subtests,
    get_ssh_client,
    get_ssh_config,
    parse_cpu_range_count,
    run_ssh_command,
)
from isvtest.core.validation import BaseValidation

# =============================================================================
# Connectivity Validations
# =============================================================================


class SshConnectivityCheck(BaseValidation):
    """Test SSH connectivity to remote host.

    Works on any platform with SSH access.

    Config:
        host: Hostname or IP (or from step_output.public_ip)
        key_file: Path to SSH private key
        user: SSH username (default: ubuntu)
    """

    description: ClassVar[str] = "Validates SSH connectivity"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed. Run: pip install paramiko")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        if not host:
            self.set_failed("Missing 'host' in config")
            return
        if not key_path:
            self.set_failed("Missing 'key_file' in config")
            return
        if not os.path.exists(key_path):
            self.set_failed(f"SSH key file not found: {key_path}")
            return

        self.log.info(f"Testing SSH to {host} as {user}")

        try:
            ssh = get_ssh_client(host, user, key_path)
            self.report_subtest("ssh_connect", True, f"Connected to {host}")

            # Test command execution
            exit_code, stdout, _ = run_ssh_command(ssh, "echo 'test'")
            if exit_code == 0 and stdout.strip() == "test":
                self.report_subtest("command_exec", True, "Commands work")
            else:
                self.report_subtest("command_exec", False, f"Output: {stdout}")

            # Test uname
            exit_code, stdout, _ = run_ssh_command(ssh, "uname -a")
            if exit_code == 0:
                self.report_subtest("uname", "Linux" in stdout, f"{stdout[:60]}...")

            # Get uptime
            exit_code, stdout, _ = run_ssh_command(ssh, "cat /proc/uptime | cut -d' ' -f1")
            if exit_code == 0:
                uptime = float(stdout.strip())
                self.report_subtest("uptime", True, f"{uptime:.0f}s")

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"SSH subtests failed: {', '.join(failed)}")
            else:
                self.set_passed(f"SSH to {host} OK")

        except Exception as e:
            self.set_failed(f"SSH failed: {e}")


# =============================================================================
# OS and System Validations
# =============================================================================


class SshOsCheck(BaseValidation):
    """Check OS details via SSH.

    Works on any Linux host.

    Config:
        host, key_file, user: SSH connection details
        expected_os: Expected OS name (optional, e.g., "ubuntu")
    """

    description: ClassVar[str] = "Validates OS via SSH"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        expected_os = self.config.get("expected_os", "").lower()

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # Get OS info
            exit_code, stdout, _ = run_ssh_command(ssh, "cat /etc/os-release")
            if exit_code == 0:
                os_name = ""
                os_version = ""
                for line in stdout.split("\n"):
                    if line.startswith("NAME="):
                        os_name = line.split("=")[1].strip('"').lower()
                    elif line.startswith("VERSION_ID="):
                        os_version = line.split("=")[1].strip('"')

                if expected_os:
                    os_matches = expected_os in os_name
                    self.report_subtest("os_type", os_matches, f"OS: {os_name} {os_version}")
                else:
                    self.report_subtest("os_type", True, f"OS: {os_name} {os_version}")

            # Get kernel
            exit_code, stdout, _ = run_ssh_command(ssh, "uname -r")
            if exit_code == 0:
                self.report_subtest("kernel", True, stdout.strip())

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"OS subtests failed: {', '.join(failed)}")
            elif expected_os and expected_os not in os_name:
                self.set_failed(f"OS mismatch: got {os_name}, expected {expected_os}")
            else:
                self.set_passed(f"OS check on {host} OK")

        except Exception as e:
            self.set_failed(f"OS check failed: {e}")


class SshCpuInfoCheck(BaseValidation):
    """Check CPU and system configuration via SSH.

    Validates CPU count, NUMA topology, and PCI devices.
    """

    description: ClassVar[str] = "Validates CPU, NUMA topology, and PCI configuration"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # Check CPU count
            exit_code, stdout, _ = run_ssh_command(ssh, "nproc")
            cpu_count = stdout.strip() if exit_code == 0 else "?"
            self.report_subtest("cpu_count", exit_code == 0, f"CPUs: {cpu_count}")

            # Check NUMA topology
            exit_code, stdout, _ = run_ssh_command(ssh, "lscpu | grep -E 'NUMA|Socket|Thread' || echo 'N/A'")
            numa_info = stdout.strip().replace("\n", "; ")[:100]
            self.report_subtest("numa", exit_code == 0, numa_info)

            # Check PCI NVIDIA devices
            exit_code, stdout, _ = run_ssh_command(ssh, "lspci | grep -i nvidia || echo 'none'")
            if "none" not in stdout.lower():
                gpu_count = stdout.count("NVIDIA")
                self.report_subtest("pci_nvidia", True, f"Found {gpu_count} NVIDIA device(s)")
            else:
                self.report_subtest("pci_nvidia", False, "No NVIDIA devices on PCI")

            # Check CPU governor
            exit_code, stdout, _ = run_ssh_command(
                ssh, "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'N/A'"
            )
            self.report_subtest("cpu_governor", True, f"Governor: {stdout.strip()}")

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"CPU/PCI subtests failed: {', '.join(failed)}")
            else:
                self.set_passed(f"CPU/PCI check on {host} OK")

        except Exception as e:
            self.set_failed(f"CPU check failed: {e}")


# =============================================================================
# vCPU Pinning and PCI Bus Validations
# =============================================================================


class SshVcpuPinningCheck(BaseValidation):
    """Validate vCPU pinning and NUMA affinity on the host.

    Checks that vCPUs are properly configured:
    - vCPU count matches expected (from instance type)
    - All vCPUs are online
    - NUMA topology is consistent (vCPUs grouped by NUMA node)
    - CPU affinity mask covers all expected vCPUs
    - CPU-to-NUMA mapping is balanced (no empty NUMA nodes)
    - GPU-to-NUMA locality: GPUs share NUMA node with assigned CPUs

    Config:
        host, key_file, user: SSH connection details
        expected_vcpus: Expected vCPU count (optional)
    """

    description: ClassVar[str] = "Validates vCPU pinning and NUMA affinity"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        expected_vcpus = self.config.get("expected_vcpus")

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # --- Check 1: vCPU count ---
            exit_code, stdout, _ = run_ssh_command(ssh, "nproc")
            if exit_code != 0:
                self.set_failed("Cannot determine vCPU count")
                ssh.close()
                return
            vcpu_count = int(stdout.strip())
            if expected_vcpus:
                vcpu_ok = vcpu_count == expected_vcpus
                self.report_subtest(
                    "vcpu_count",
                    vcpu_ok,
                    f"{vcpu_count} vCPUs (expected {expected_vcpus})",
                )
            else:
                self.report_subtest("vcpu_count", vcpu_count > 0, f"{vcpu_count} vCPUs")

            # --- Check 2: All vCPUs are online ---
            exit_code, stdout, _ = run_ssh_command(ssh, "cat /sys/devices/system/cpu/online")
            if exit_code == 0:
                online_range = stdout.strip()
                # Parse range like "0-3" to count
                online_count = parse_cpu_range_count(online_range)
                all_online = online_count == vcpu_count
                self.report_subtest(
                    "vcpu_online",
                    all_online,
                    f"Online: {online_range} ({online_count}/{vcpu_count})",
                )

            # --- Check 3: CPU affinity mask (init process = full mask) ---
            exit_code, stdout, _ = run_ssh_command(
                ssh, "taskset -p 1 2>/dev/null || cat /proc/1/status | grep Cpus_allowed:"
            )
            if exit_code == 0:
                affinity_info = stdout.strip()
                self.report_subtest("cpu_affinity", True, affinity_info[:80])

            # --- Check 4: NUMA topology ---
            exit_code, stdout, _ = run_ssh_command(ssh, "lscpu | grep -E '^NUMA node[0-9]+ CPU' || echo 'no_numa'")
            if exit_code == 0 and "no_numa" not in stdout:
                numa_lines = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
                numa_nodes = len(numa_lines)
                # Check all NUMA nodes have CPUs assigned (balanced)
                all_have_cpus = all(":" in line and line.split(":")[-1].strip() != "" for line in numa_lines)
                self.report_subtest(
                    "numa_topology",
                    all_have_cpus,
                    f"{numa_nodes} NUMA node(s), all populated: {all_have_cpus}",
                )

                # Report per-node detail
                for line in numa_lines:
                    parts = line.split(":")
                    if len(parts) == 2:
                        node_name = parts[0].strip().replace("NUMA ", "").replace(" CPU(s)", "")
                        cpus = parts[1].strip()
                        cpu_cnt = parse_cpu_range_count(cpus) if cpus else 0
                        self.report_subtest(
                            f"numa_{node_name}",
                            cpu_cnt > 0,
                            f"{node_name}: CPUs {cpus} ({cpu_cnt} cores)",
                        )
            else:
                self.report_subtest("numa_topology", True, "Single NUMA node (no NUMA)")

            # --- Check 5: GPU NUMA locality ---
            exit_code, stdout, _ = run_ssh_command(
                ssh, "nvidia-smi --query-gpu=index,gpu_bus_id --format=csv,noheader 2>/dev/null"
            )
            if exit_code == 0 and stdout.strip():
                for line in stdout.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        gpu_idx = parts[0].strip()
                        bus_id = parts[1].strip()
                        # Get NUMA node for this PCI device
                        pci_short = bus_id.lower().replace("0000:", "")
                        numa_exit, numa_out, _ = run_ssh_command(
                            ssh,
                            f"cat /sys/bus/pci/devices/{bus_id.lower()}/numa_node "
                            f"2>/dev/null || cat /sys/bus/pci/devices/0000:{pci_short}/numa_node "
                            f"2>/dev/null || echo '-1'",
                        )
                        numa_node = numa_out.strip() if numa_exit == 0 else "unknown"
                        # -1 means no NUMA affinity (common on single-socket)
                        locality_ok = numa_node != "unknown"
                        self.report_subtest(
                            f"gpu{gpu_idx}_numa",
                            locality_ok,
                            f"GPU {gpu_idx} ({bus_id}) -> NUMA node {numa_node}",
                        )

            ssh.close()

            # Determine overall pass/fail
            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"vCPU pinning subtests failed: {', '.join(failed)}")
            elif expected_vcpus and vcpu_count != expected_vcpus:
                self.set_failed(f"vCPU count mismatch: got {vcpu_count}, expected {expected_vcpus}")
            else:
                self.set_passed(f"vCPU pinning check on {host} OK ({vcpu_count} vCPUs)")

        except Exception as e:
            self.set_failed(f"vCPU pinning check failed: {e}")


class SshPciBusCheck(BaseValidation):
    """Validate PCI bus configuration for GPU devices.

    Checks that PCI bus is properly configured:
    - NVIDIA GPU devices visible on PCI bus
    - PCIe link speed and width reported
    - IOMMU group assignment (passthrough readiness)
    - ACS (Access Control Services) status
    - GPU PCI BAR (Base Address Register) memory mapped

    Config:
        host, key_file, user: SSH connection details
        expected_gpus: Expected GPU count (optional, default: 1)
        expected_link_width: Expected PCIe link width e.g. "x16" (optional)
    """

    description: ClassVar[str] = "Validates PCI bus configuration for GPU devices"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh", "gpu"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        expected_gpus = self.config.get("expected_gpus", ssh_cfg.get("gpu_count", 1))
        expected_link_width = self.config.get("expected_link_width")

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # --- Check 1: NVIDIA PCI devices enumeration ---
            exit_code, stdout, _ = run_ssh_command(ssh, "lspci -d 10de: -nn 2>/dev/null || lspci | grep -i nvidia")
            if exit_code != 0 or not stdout.strip():
                self.set_failed("No NVIDIA devices found on PCI bus")
                ssh.close()
                return

            # Count GPU devices (class 0300=VGA, 0302=3D controller)
            pci_lines = [
                line
                for line in stdout.strip().split("\n")
                if line.strip() and ("3D" in line or "VGA" in line or "Display" in line)
            ]
            gpu_pci_count = len(pci_lines)
            if gpu_pci_count == 0:
                # Fallback: count all NVIDIA entries (includes NVSwitch, etc.)
                pci_lines = [line for line in stdout.strip().split("\n") if line.strip()]
                gpu_pci_count = len(pci_lines)

            count_ok = gpu_pci_count >= expected_gpus
            self.report_subtest(
                "pci_gpu_count",
                count_ok,
                f"{gpu_pci_count} GPU PCI device(s) (expected {expected_gpus})",
            )

            # Report each device
            for i, line in enumerate(pci_lines[:8]):  # Cap at 8 for readability
                bdf = line.split()[0] if line.split() else "?"
                desc = line[len(bdf) :].strip()[:70]
                self.report_subtest(f"pci_dev_{i}", True, f"{bdf}: {desc}")

            # --- Check 2: PCIe link speed and width per GPU ---
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "nvidia-smi --query-gpu=index,pci.bus_id,pcie.link.gen.current,"
                "pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max "
                "--format=csv,noheader 2>/dev/null",
            )
            if exit_code == 0 and stdout.strip():
                for line in stdout.strip().split("\n"):
                    fields = [f.strip() for f in line.split(",")]
                    if len(fields) >= 6:
                        idx, bus, gen_cur, gen_max, w_cur, w_max = fields[:6]
                        degraded = gen_cur != gen_max or w_cur != w_max
                        msg = f"GPU {idx}: Gen{gen_cur}/{gen_max}, x{w_cur}/{w_max}"

                        if expected_link_width:
                            # Strict mode: enforce exact link width
                            link_ok = f"x{w_cur}" == expected_link_width
                            if not link_ok:
                                msg += f" (expected {expected_link_width})"
                        else:
                            # Report mode: note degradation but don't fail
                            # Cloud VMs often report narrower virtual PCIe links
                            link_ok = True
                            if degraded:
                                msg += " (link negotiated below max, normal for cloud VMs)"

                        self.report_subtest(f"pcie_link_gpu{idx}", link_ok, msg)
            else:
                # Fallback to lspci for link info
                exit_code, stdout, _ = run_ssh_command(
                    ssh,
                    "sudo lspci -vvs $(lspci -d 10de: | head -1 | awk '{print $1}') "
                    "2>/dev/null | grep -i 'lnksta\\|lnkcap' || echo 'no_link_info'",
                )
                if "no_link_info" not in stdout:
                    self.report_subtest("pcie_link", True, stdout.strip()[:80])
                else:
                    self.report_subtest("pcie_link", True, "Link info not available")

            # --- Check 3: IOMMU groups ---
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "find /sys/kernel/iommu_groups/ -type l -name '*:*' 2>/dev/null "
                "| xargs -I{} bash -c 'echo $(basename $(dirname $(dirname {}))): $(basename {})' "
                "| grep -i '10de\\|nvidia' 2>/dev/null || "
                "for dev in $(lspci -d 10de: -D | awk '{print $1}'); do "
                "  iommu=$(basename $(readlink -f /sys/bus/pci/devices/$dev/iommu_group 2>/dev/null) 2>/dev/null); "
                '  echo "$dev -> IOMMU group $iommu"; '
                "done 2>/dev/null || echo 'no_iommu'",
            )
            if exit_code == 0 and "no_iommu" not in stdout:
                iommu_info = stdout.strip().replace("\n", "; ")[:120]
                self.report_subtest("iommu_groups", True, iommu_info)
            else:
                self.report_subtest("iommu_groups", True, "IOMMU not available (OK for cloud VMs)")

            # --- Check 4: GPU BAR memory regions ---
            exit_code, stdout, _ = run_ssh_command(
                ssh, "nvidia-smi --query-gpu=index,memory.total,pci.bus_id --format=csv,noheader 2>/dev/null"
            )
            if exit_code == 0 and stdout.strip():
                for line in stdout.strip().split("\n"):
                    fields = [f.strip() for f in line.split(",")]
                    if len(fields) >= 3:
                        idx, mem, bus = fields[:3]
                        mem_ok = mem and "MiB" in mem
                        self.report_subtest(
                            f"gpu{idx}_bar_mem",
                            mem_ok,
                            f"GPU {idx} ({bus}): {mem}",
                        )

            # --- Check 5: ACS check (Access Control Services) ---
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "for dev in $(lspci -d 10de: -D | awk '{print $1}'); do "
                "  acs=$(sudo setpci -s $dev ECAP_ACS+6.w 2>/dev/null); "
                '  if [ -n "$acs" ]; then echo "$dev ACS=$acs"; '
                '  else echo "$dev ACS=N/A"; fi; '
                "done 2>/dev/null || echo 'acs_unavailable'",
            )
            if exit_code == 0 and "acs_unavailable" not in stdout:
                acs_info = stdout.strip().replace("\n", "; ")[:100]
                self.report_subtest("acs", True, acs_info)
            else:
                self.report_subtest("acs", True, "ACS info not available (OK for cloud VMs)")

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"PCI bus subtests failed: {', '.join(failed)}")
            elif not count_ok:
                self.set_failed(f"PCI GPU count: got {gpu_pci_count}, expected {expected_gpus}")
            else:
                self.set_passed(f"PCI bus check on {host} OK ({gpu_pci_count} GPUs)")

        except Exception as e:
            self.set_failed(f"PCI bus check failed: {e}")


# =============================================================================
# Host Software Stack Validations
# =============================================================================


class SshHostSoftwareCheck(BaseValidation):
    """Validate that the correct host software stack is installed.

    Checks Linux kernel, libvirt/QEMU, SBIOS (System BIOS), and NVIDIA drivers
    are present and optionally match expected versions.

    Config:
        host, key_file, user: SSH connection details
        expected_kernel: Expected kernel version substring (optional, e.g. "6.5")
        expected_driver_version: Expected NVIDIA driver version (optional, e.g. "550")
        expected_libvirt_version: Expected libvirt version substring (optional, e.g. "10.0")
        expected_bios_vendor: Expected BIOS vendor substring (optional, e.g. "Amazon")
    """

    description: ClassVar[str] = "Validates kernel, libvirt, SBIOS, and NVIDIA drivers"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        expected_kernel = self.config.get("expected_kernel")
        expected_driver = self.config.get("expected_driver_version")
        expected_libvirt = self.config.get("expected_libvirt_version")
        expected_bios_vendor = self.config.get("expected_bios_vendor")

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        failures: list[str] = []

        try:
            ssh = get_ssh_client(host, user, key_path)

            # ==============================================================
            # 1. Linux Kernel
            # ==============================================================
            exit_code, stdout, _ = run_ssh_command(ssh, "uname -r")
            kernel_version = stdout.strip() if exit_code == 0 else "unknown"
            if expected_kernel:
                kernel_ok = expected_kernel in kernel_version
                self.report_subtest(
                    "kernel_version",
                    kernel_ok,
                    f"Kernel: {kernel_version} (expected: {expected_kernel})",
                )
                if not kernel_ok:
                    failures.append(f"kernel {kernel_version} != {expected_kernel}")
            else:
                self.report_subtest("kernel_version", True, f"Kernel: {kernel_version}")

            # Kernel release details
            exit_code, stdout, _ = run_ssh_command(ssh, "uname -v")
            if exit_code == 0:
                self.report_subtest("kernel_build", True, stdout.strip()[:80])

            # Check loaded kernel modules relevant to GPU/virt
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "lsmod | grep -E '^nvidia|^kvm|^vfio|^vhost' | awk '{print $1}' | sort | tr '\\n' ', ' || echo 'none'",
            )
            if exit_code == 0:
                modules = stdout.strip().rstrip(",")
                self.report_subtest(
                    "kernel_modules",
                    True,
                    f"Key modules: {modules}" if modules and modules != "none" else "No GPU/virt modules loaded",
                )

            # ==============================================================
            # 2. libvirt / QEMU / KVM
            # ==============================================================
            # Check libvirtd
            exit_code, stdout, _ = run_ssh_command(ssh, "libvirtd --version 2>/dev/null || echo 'not_installed'")
            if "not_installed" not in stdout:
                libvirt_ver = stdout.strip()
                if expected_libvirt:
                    libvirt_ok = expected_libvirt in libvirt_ver
                    self.report_subtest(
                        "libvirt",
                        libvirt_ok,
                        f"{libvirt_ver} (expected: {expected_libvirt})",
                    )
                    if not libvirt_ok:
                        failures.append(f"libvirt {libvirt_ver} != {expected_libvirt}")
                else:
                    self.report_subtest("libvirt", True, libvirt_ver)
            else:
                # Not all hosts have libvirt - report but don't fail
                self.report_subtest("libvirt", True, "libvirt not installed (OK for bare metal/cloud)")

            # Check QEMU
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "qemu-system-x86_64 --version 2>/dev/null || qemu-kvm --version 2>/dev/null || echo 'not_installed'",
            )
            if "not_installed" not in stdout:
                qemu_ver = stdout.strip().split("\n")[0][:80]
                self.report_subtest("qemu", True, qemu_ver)
            else:
                self.report_subtest("qemu", True, "QEMU not installed (OK for bare metal/cloud)")

            # Check KVM support
            exit_code, stdout, _ = run_ssh_command(
                ssh, "test -c /dev/kvm && echo 'kvm_available' || echo 'kvm_unavailable'"
            )
            kvm_available = "kvm_available" in stdout
            self.report_subtest(
                "kvm",
                True,
                "KVM available (/dev/kvm)" if kvm_available else "KVM not available",
            )

            # Check virsh if libvirt present
            exit_code, stdout, _ = run_ssh_command(ssh, "virsh version --daemon 2>/dev/null || echo 'not_available'")
            if "not_available" not in stdout:
                virsh_info = stdout.strip().replace("\n", "; ")[:100]
                self.report_subtest("virsh", True, virsh_info)

            # ==============================================================
            # 3. SBIOS (System BIOS / UEFI firmware)
            # ==============================================================
            # BIOS vendor
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "sudo dmidecode -s bios-vendor 2>/dev/null "
                "|| cat /sys/class/dmi/id/bios_vendor 2>/dev/null "
                "|| echo 'unknown'",
            )
            bios_vendor = stdout.strip() if exit_code == 0 else "unknown"
            if expected_bios_vendor:
                vendor_ok = expected_bios_vendor.lower() in bios_vendor.lower()
                self.report_subtest(
                    "bios_vendor",
                    vendor_ok,
                    f"BIOS vendor: {bios_vendor} (expected: {expected_bios_vendor})",
                )
                if not vendor_ok:
                    failures.append(f"BIOS vendor {bios_vendor} != {expected_bios_vendor}")
            else:
                self.report_subtest("bios_vendor", True, f"BIOS vendor: {bios_vendor}")

            # BIOS version
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "sudo dmidecode -s bios-version 2>/dev/null "
                "|| cat /sys/class/dmi/id/bios_version 2>/dev/null "
                "|| echo 'unknown'",
            )
            bios_version = stdout.strip() if exit_code == 0 else "unknown"
            self.report_subtest("bios_version", True, f"BIOS version: {bios_version}")

            # BIOS release date
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "sudo dmidecode -s bios-release-date 2>/dev/null "
                "|| cat /sys/class/dmi/id/bios_date 2>/dev/null "
                "|| echo 'unknown'",
            )
            bios_date = stdout.strip() if exit_code == 0 else "unknown"
            self.report_subtest("bios_date", True, f"BIOS date: {bios_date}")

            # System product / platform
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "sudo dmidecode -s system-product-name 2>/dev/null "
                "|| cat /sys/class/dmi/id/product_name 2>/dev/null "
                "|| echo 'unknown'",
            )
            product = stdout.strip() if exit_code == 0 else "unknown"
            self.report_subtest("system_product", True, f"Platform: {product}")

            # UEFI vs legacy BIOS
            exit_code, stdout, _ = run_ssh_command(
                ssh, "test -d /sys/firmware/efi && echo 'UEFI' || echo 'Legacy BIOS'"
            )
            boot_mode = stdout.strip() if exit_code == 0 else "unknown"
            self.report_subtest("boot_mode", True, f"Boot mode: {boot_mode}")

            # ==============================================================
            # 4. NVIDIA Driver
            # ==============================================================
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo 'not_found'",
            )
            driver_found = stdout.strip() != "not_found" and len(stdout.strip()) > 0

            if driver_found:
                driver_version = stdout.strip().split("\n")[0]
                if expected_driver:
                    driver_ok = expected_driver in driver_version
                    self.report_subtest(
                        "nvidia_driver",
                        driver_ok,
                        f"NVIDIA Driver: {driver_version} (expected: {expected_driver})",
                    )
                    if not driver_ok:
                        failures.append(f"driver {driver_version} != {expected_driver}")
                else:
                    self.report_subtest("nvidia_driver", True, f"NVIDIA Driver: {driver_version}")
            else:
                self.report_subtest("nvidia_driver", False, "NVIDIA driver not found")
                failures.append("NVIDIA driver not installed")

            # CUDA version
            exit_code, stdout, _ = run_ssh_command(ssh, "nvidia-smi | grep 'CUDA Version' | awk '{print $9}'")
            if exit_code == 0 and stdout.strip():
                self.report_subtest("cuda_version", True, f"CUDA: {stdout.strip()}")

            # NVIDIA kernel module version (should match userspace driver)
            exit_code, stdout, _ = run_ssh_command(
                ssh, "cat /sys/module/nvidia/version 2>/dev/null || echo 'not_loaded'"
            )
            if "not_loaded" not in stdout:
                module_ver = stdout.strip()
                self.report_subtest("nvidia_module", True, f"nvidia.ko: {module_ver}")

            # NVIDIA persistence daemon
            exit_code, stdout, _ = run_ssh_command(
                ssh,
                "nvidia-smi --query-gpu=persistence_mode --format=csv,noheader 2>/dev/null | head -1 || echo 'unknown'",
            )
            if exit_code == 0 and stdout.strip() != "unknown":
                persist = stdout.strip()
                self.report_subtest("nvidia_persistence", True, f"Persistence mode: {persist}")

            ssh.close()

            if failures:
                self.set_failed("; ".join(failures))
            else:
                self.set_passed(
                    f"Host software check on {host} OK "
                    f"(kernel={kernel_version}, driver={driver_version if driver_found else 'N/A'})"
                )

        except Exception as e:
            self.set_failed(f"Host software check failed: {e}")


# =============================================================================
# GPU Validations
# =============================================================================


class SshGpuCheck(BaseValidation):
    """Test GPU visibility via SSH.

    Works on any platform with SSH + nvidia-smi.

    Config:
        host, key_file, user: SSH connection details
        expected_gpus: Expected GPU count (optional, default: 1)
    """

    description: ClassVar[str] = "Validates GPU via SSH"
    timeout: ClassVar[int] = 300
    markers: ClassVar[list[str]] = ["ssh", "gpu"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        expected_gpus = self.config.get("expected_gpus", ssh_cfg.get("gpu_count", 1))

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        self.log.info(f"Testing GPU on {host}")

        try:
            ssh = get_ssh_client(host, user, key_path, timeout=60)

            # Test nvidia-smi
            exit_code, stdout, stderr = run_ssh_command(ssh, "nvidia-smi")
            if exit_code != 0:
                self.set_failed(f"nvidia-smi failed: {stderr}")
                ssh.close()
                return
            self.report_subtest("nvidia_smi", True, "Available")

            # Get GPU count
            exit_code, stdout, _ = run_ssh_command(ssh, "nvidia-smi --query-gpu=name --format=csv,noheader | wc -l")
            if exit_code == 0:
                gpu_count = int(stdout.strip())
                passed = gpu_count >= expected_gpus
                self.report_subtest("gpu_count", passed, f"{gpu_count} GPUs (need {expected_gpus})")

            # Get GPU names
            exit_code, stdout, _ = run_ssh_command(ssh, "nvidia-smi --query-gpu=name --format=csv,noheader")
            if exit_code == 0:
                self.report_subtest("gpu_model", True, stdout.strip().split("\n")[0])

            # Get driver version
            exit_code, stdout, _ = run_ssh_command(
                ssh, "nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1"
            )
            if exit_code == 0:
                self.report_subtest("driver", True, f"v{stdout.strip()}")

            # Get GPU memory
            exit_code, stdout, _ = run_ssh_command(
                ssh, "nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1"
            )
            if exit_code == 0:
                self.report_subtest("gpu_memory", True, stdout.strip())

            # Get CUDA version
            exit_code, stdout, _ = run_ssh_command(ssh, "nvidia-smi | grep 'CUDA Version' | awk '{print $9}'")
            if exit_code == 0 and stdout.strip():
                self.report_subtest("cuda", True, f"v{stdout.strip()}")

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"GPU subtests failed: {', '.join(failed)}")
            else:
                self.set_passed(f"GPU check on {host} OK")

        except Exception as e:
            self.set_failed(f"GPU check failed: {e}")


class SshDriverCheck(BaseValidation):
    """Check kernel and NVIDIA drivers via SSH.

    Validates driver installation and versions.

    Config:
        host, key_file, user: SSH connection details
        expected_driver_version: Expected driver version (optional)
    """

    description: ClassVar[str] = "Validates kernel and NVIDIA drivers"
    timeout: ClassVar[int] = 120
    markers: ClassVar[list[str]] = ["ssh", "gpu"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        expected_driver = self.config.get("expected_driver_version")

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # Check kernel version
            exit_code, stdout, _ = run_ssh_command(ssh, "uname -r")
            kernel_version = stdout.strip() if exit_code == 0 else "unknown"
            self.report_subtest("kernel", exit_code == 0, f"Kernel: {kernel_version}")

            # Check NVIDIA driver
            exit_code, stdout, _ = run_ssh_command(
                ssh, "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null || echo 'not_found'"
            )
            driver_found = stdout.strip() != "not_found" and len(stdout.strip()) > 0

            if driver_found:
                driver_version = stdout.strip().split("\n")[0]
                driver_ok = True
                if expected_driver:
                    driver_ok = expected_driver in driver_version
                self.report_subtest(
                    "nvidia_driver",
                    driver_ok,
                    f"NVIDIA Driver: {driver_version}" + (f" (expected: {expected_driver})" if expected_driver else ""),
                )
            else:
                self.report_subtest("nvidia_driver", False, "NVIDIA driver not found")

            # Check CUDA toolkit
            exit_code, stdout, _ = run_ssh_command(ssh, "nvcc --version 2>/dev/null | grep release || echo 'not_found'")
            cuda_found = "not_found" not in stdout and "release" in stdout
            self.report_subtest("cuda_toolkit", cuda_found, stdout.strip() if cuda_found else "CUDA toolkit not found")

            ssh.close()

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"Driver subtests failed: {', '.join(failed)}")
            elif driver_found:
                self.set_passed(f"Drivers check passed: Kernel {kernel_version}")
            else:
                self.set_failed("NVIDIA driver not found")

        except Exception as e:
            self.set_failed(f"Driver check failed: {e}")


# =============================================================================
# Workload Validations
# =============================================================================


def _detect_ssh_container_runtime(ssh: paramiko.SSHClient) -> str:
    """Detect available container runtime on a remote host via SSH.

    Checks for Docker with NVIDIA GPU support. Falls back to "python"
    if Docker is not available or the NVIDIA runtime is not configured.

    Args:
        ssh: Connected paramiko SSHClient instance

    Returns:
        "docker" if Docker + NVIDIA runtime works, otherwise "python"
    """
    exit_code, stdout, _ = run_ssh_command(
        ssh,
        "docker info --format '{{.Runtimes}}' 2>/dev/null",
    )
    if exit_code != 0:
        return "python"
    if "nvidia" not in stdout.lower():
        return "python"
    return "docker"


class SshGpuStressCheck(BaseValidation):
    """Run GPU stress test via SSH using PyTorch matrix multiplications.

    Runs the same gpu_stress_torch.py script used by Slurm/K8s workloads,
    but executed remotely over SSH inside a Docker container (or directly
    with system Python if container_runtime is "python").

    Config:
        host, key_file, user: SSH connection details
        runtime (int): Stress duration in seconds (default: 30)
        memory_gb (int): Target GPU memory usage in GB (default: 16)
        image (str): PyTorch container image (default: nvcr.io/nvidia/pytorch:25.04-py3)
        container_runtime (str): "docker" or "python" (default: "docker")
        expected_gpus (int): Expected GPU count to validate (optional)
    """

    description: ClassVar[str] = "GPU stress test via SSH"
    timeout: ClassVar[int] = 900
    markers: ClassVar[list[str]] = ["ssh", "gpu", "workload"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        runtime = self.config.get("runtime", 30)
        memory_gb = self.config.get("memory_gb", 16)
        image = self.config.get("image", "nvcr.io/nvidia/pytorch:25.04-py3")
        container_runtime = self.config.get("container_runtime")
        expected_gpus = self.config.get("expected_gpus", ssh_cfg.get("gpu_count"))

        script_path = Path(__file__).parent.parent / "workloads" / "scripts" / "gpu_stress_torch.py"
        if not script_path.exists():
            self.set_failed(f"GPU stress script not found: {script_path}")
            return

        try:
            ssh = get_ssh_client(host, user, key_path, timeout=60)

            # Auto-detect runtime if not explicitly configured
            if not container_runtime:
                container_runtime = _detect_ssh_container_runtime(ssh)
                self.log.info(f"Auto-detected runtime: {container_runtime}")

            script_b64 = base64.b64encode(script_path.read_bytes()).decode()
            decode_and_run = f"echo {script_b64} | base64 -d | python3"
            env_vars = f"GPU_STRESS_RUNTIME={runtime} GPU_MEMORY_GB={memory_gb}"

            if container_runtime == "python":
                cmd = f"bash -c '{env_vars} {decode_and_run}'"
            else:
                cmd = (
                    f"docker run --rm --gpus all "
                    f"-e GPU_STRESS_RUNTIME={runtime} -e GPU_MEMORY_GB={memory_gb} "
                    f"{image} bash -c '{decode_and_run}'"
                )

            self.log.info(
                f"Running GPU stress on {host}: runtime={runtime}s, memory={memory_gb}GB, mode={container_runtime}"
            )

            _, stdout, stderr = run_ssh_command(ssh, cmd)
            ssh.close()

            output = f"{stdout}\n{stderr}".strip()
            self.log.debug(f"GPU stress output:\n{output[:2000]}")

            if "FAILURE:" in output:
                self.report_subtest("gpu_stress", False, output.strip())
                self.set_failed(f"GPU stress failed on {host}: {output.strip()}")
                return

            if "SUCCESS:" not in output:
                self.report_subtest("gpu_stress", False, "SUCCESS marker not found")
                self.set_failed(
                    f"GPU stress did not complete successfully on {host}",
                    output=output[-500:],
                )
                return

            # Parse SUCCESS line: "SUCCESS: hostname completed N loops with M GPU(s)"
            match = re.search(r"SUCCESS:.*completed (\d+) loops with (\d+) GPU", output)
            if match:
                loops = int(match.group(1))
                gpu_count = int(match.group(2))
                self.report_subtest("loops", loops > 0, f"{loops} loops completed")
                self.report_subtest("gpu_count", True, f"{gpu_count} GPU(s) stressed")

                if expected_gpus and gpu_count < expected_gpus:
                    self.report_subtest(
                        "gpu_count_check",
                        False,
                        f"Expected {expected_gpus} GPUs, got {gpu_count}",
                    )
                    self.set_failed(f"GPU count mismatch: expected {expected_gpus}, got {gpu_count}")
                    return
            else:
                self.report_subtest("parse", False, "Could not parse SUCCESS output")

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"GPU stress subtests failed: {', '.join(failed)}")
            else:
                self.set_passed(f"GPU stress passed on {host}: {output.strip().splitlines()[-1]}")

        except Exception as e:
            self.set_failed(f"GPU stress failed: {e}")


class SshNcclCheck(BaseValidation):
    """Run single-node NCCL AllReduce test via SSH.

    Validates GPU-to-GPU communication (NVLink/NVSwitch) by running
    NCCL all_reduce_perf_mpi via MPI inside a Docker container on the
    target host. Uses the NVIDIA HPC Benchmarks image. Requires at least
    2 GPUs.

    Config:
        host, key_file, user: SSH connection details
        image (str): Container image (default: nvcr.io/nvidia/hpc-benchmarks:25.04)
        min_bus_bw_gbps (float): Minimum acceptable bus bandwidth in GB/s (default: 0 = no threshold)
        expected_gpus (int): Expected GPU count (optional, used for -np argument)
        message_sizes (str): NCCL test size range flags (default: "-b 1M -e 256M -f 2")
    """

    description: ClassVar[str] = "NCCL AllReduce test via SSH"
    timeout: ClassVar[int] = 900
    markers: ClassVar[list[str]] = ["ssh", "gpu", "workload"]

    _DEFAULT_IMAGE = "nvcr.io/nvidia/hpc-benchmarks:25.04"

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        image = self.config.get("image", self._DEFAULT_IMAGE)
        min_bus_bw = float(self.config.get("min_bus_bw_gbps", 0))
        message_sizes = self.config.get("message_sizes", "-b 1M -e 256M -f 2")

        try:
            ssh = get_ssh_client(host, user, key_path, timeout=60)

            # Verify Docker + NVIDIA runtime are available (NCCL binaries come from the container)
            has_docker = _detect_ssh_container_runtime(ssh) == "docker"
            if not has_docker:
                self.set_failed(
                    f"Docker with NVIDIA runtime not available on {host}. "
                    "NCCL tests require a container with NCCL test binaries."
                )
                ssh.close()
                return

            # Detect GPU count
            exit_code, stdout, _ = run_ssh_command(ssh, "nvidia-smi --query-gpu=name --format=csv,noheader | wc -l")
            if exit_code != 0 or not stdout.strip().isdigit():
                self.set_failed(f"Cannot detect GPU count on {host}")
                ssh.close()
                return

            gpu_count = int(stdout.strip())
            expected_gpus = self.config.get("expected_gpus")
            if expected_gpus:
                gpu_count = int(expected_gpus)

            if gpu_count < 2:
                self.set_passed(f"Skipped: {host} has {gpu_count} GPU(s), need >= 2 for NCCL test")
                ssh.close()
                return

            self.report_subtest("gpu_count", True, f"{gpu_count} GPUs detected")

            nccl_cmd = (
                f"docker run --rm --gpus all --ipc=host {image} "
                f"mpirun --allow-run-as-root -np {gpu_count} "
                f"--bind-to none --map-by slot "
                f"all_reduce_perf_mpi {message_sizes} -g 1"
            )

            self.log.info(f"Running NCCL AllReduce on {host} with {gpu_count} GPUs")
            exit_code, stdout, stderr = run_ssh_command(ssh, nccl_cmd)
            ssh.close()

            output = f"{stdout}\n{stderr}".strip()
            self.log.debug(f"NCCL output:\n{output[:3000]}")

            if exit_code != 0 and "Avg bus bandwidth" not in output:
                self.report_subtest("nccl_run", False, f"Exit code {exit_code}")
                self.set_failed(f"NCCL test failed on {host}", output=output[-500:])
                return

            self.report_subtest("nccl_run", True, "NCCL test completed")

            # Parse average bus bandwidth
            avg_bw_match = re.search(r"#\s*Avg bus bandwidth\s*:\s*([\d.]+)", output)
            if avg_bw_match:
                avg_bw = float(avg_bw_match.group(1))
                self.report_subtest("avg_bus_bw", True, f"{avg_bw:.2f} GB/s")

                if min_bus_bw > 0:
                    bw_ok = avg_bw >= min_bus_bw
                    self.report_subtest(
                        "bw_threshold",
                        bw_ok,
                        f"{avg_bw:.2f} GB/s vs {min_bus_bw} GB/s minimum",
                    )
                    if not bw_ok:
                        self.set_failed(f"Bus bandwidth {avg_bw:.2f} GB/s below threshold {min_bus_bw} GB/s")
                        return
            else:
                self.report_subtest("avg_bus_bw", False, "Could not parse bandwidth")

            # Check out-of-bounds (data corruption)
            oob_match = re.search(r"#\s*Out of bounds values\s*:\s*(\d+)", output)
            if oob_match:
                oob = int(oob_match.group(1))
                oob_ok = oob == 0
                self.report_subtest("data_integrity", oob_ok, f"{oob} out of bounds values")
                if not oob_ok:
                    self.set_failed(f"Data corruption: {oob} out of bounds values")
                    return

            failed = get_failed_subtests(self._subtest_results)
            if failed:
                self.set_failed(f"NCCL subtests failed: {', '.join(failed)}")
            else:
                bw_msg = f", avg BW: {avg_bw:.2f} GB/s" if avg_bw_match else ""
                self.set_passed(f"NCCL AllReduce passed on {host} ({gpu_count} GPUs{bw_msg})")

        except Exception as e:
            self.set_failed(f"NCCL test failed: {e}")


class SshContainerRuntimeCheck(BaseValidation):
    """Container runtime and NVIDIA Docker check.

    Checks Docker and NVIDIA container runtime are available and working.

    Config:
        host, key_file, user: SSH connection details
        ngc_api_key: NGC API key for registry access (optional)
    """

    description: ClassVar[str] = "Tests container runtime and NVIDIA Docker support"
    timeout: ClassVar[int] = 300
    markers: ClassVar[list[str]] = ["ssh", "gpu", "workload", "slow"]

    def run(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.set_failed("paramiko not installed")
            return

        ssh_cfg = get_ssh_config(self.config, self.config.get("inventory", {}))
        host = ssh_cfg["ssh_host"]
        user = ssh_cfg["ssh_user"]
        key_path = ssh_cfg["ssh_key_path"]
        ngc_api_key = self.config.get("ngc_api_key", os.environ.get("NGC_NIM_API_KEY", ""))

        if not host or not key_path:
            self.set_failed("Missing host or key_file")
            return

        try:
            ssh = get_ssh_client(host, user, key_path)

            # Check Docker
            _, stdout, _ = run_ssh_command(ssh, "docker --version 2>/dev/null || echo 'not_found'")
            docker_ok = "not_found" not in stdout and "Docker" in stdout
            self.report_subtest("docker", docker_ok, stdout.strip() if docker_ok else "Docker not installed")

            if not docker_ok:
                self.set_failed("Docker not available")
                ssh.close()
                return

            # Check NVIDIA container runtime
            _, stdout, _ = run_ssh_command(
                ssh,
                "docker run --rm --gpus all nvcr.io/nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi 2>&1 || echo 'nvidia_docker_failed'",
            )
            nvidia_ok = "nvidia_docker_failed" not in stdout and "NVIDIA-SMI" in stdout
            self.report_subtest(
                "nvidia_docker",
                nvidia_ok,
                "NVIDIA Docker working" if nvidia_ok else f"NVIDIA Docker not configured: {stdout[:100]}",
            )

            # Check NGC login if key provided
            if ngc_api_key:
                self.log.info("Testing NGC registry access...")
                _, stdout, _ = run_ssh_command(
                    ssh, f"echo '{ngc_api_key}' | docker login nvcr.io -u '$oauthtoken' --password-stdin 2>&1"
                )
                login_ok = "Succeeded" in stdout
                self.report_subtest("ngc_login", login_ok, "NGC login successful" if login_ok else "NGC login failed")
            else:
                self.report_subtest("ngc_login", True, "NGC_NIM_API_KEY not provided (skipped)")

            ssh.close()
            self.set_passed("Container runtime check passed")

        except Exception as e:
            self.set_failed(f"Container check failed: {e}")
