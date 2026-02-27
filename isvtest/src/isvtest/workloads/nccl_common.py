"""Shared NCCL output parsing utilities.

Used by k8s_nccl, k8s_nccl_multinode, and slurm_nccl_multinode workloads
to parse NCCL AllReduce benchmark output consistently.
"""

import re
from dataclasses import dataclass

# Regex patterns for NCCL benchmark output.
# The "#" prefix is optional -- present in some container output, absent in others.
_RE_AVG_BUS_BW = re.compile(r"#?\s*Avg bus bandwidth\s*:\s*([\d.]+)")
_RE_OUT_OF_BOUNDS = re.compile(r"#?\s*Out of bounds values\s*:\s*(\d+)")
_RE_MAX_BUS_BW = re.compile(r"^\s+\d+\s+\d+\s+\w+\s+\w+\s+[\d.]+\s+([\d.]+)", re.MULTILINE)


@dataclass
class NcclResult:
    """Parsed result of an NCCL benchmark run."""

    success: bool
    avg_bus_bw_gbps: float = 0.0
    max_bus_bw_gbps: float = 0.0
    out_of_bounds: int = -1
    error: str = ""
    output: str = ""


def parse_nccl_output(output: str) -> NcclResult:
    """Parse NCCL AllReduce benchmark output for bandwidth and data integrity.

    Extracts:
    - Average bus bandwidth (GB/s)
    - Maximum bus bandwidth from the data table (GB/s)
    - Out-of-bounds value count (data corruption indicator)

    Args:
        output: Raw stdout/stderr from an NCCL allreduce benchmark run.

    Returns:
        NcclResult with parsed metrics. ``success`` is False if bandwidth
        could not be parsed or data corruption was detected.
    """
    result = NcclResult(success=True, output=output)

    avg_match = _RE_AVG_BUS_BW.search(output)
    if avg_match:
        result.avg_bus_bw_gbps = float(avg_match.group(1))

    bw_matches = _RE_MAX_BUS_BW.findall(output)
    if bw_matches:
        result.max_bus_bw_gbps = max(float(bw) for bw in bw_matches)

    oob_match = _RE_OUT_OF_BOUNDS.search(output)
    if oob_match:
        result.out_of_bounds = int(oob_match.group(1))
        if result.out_of_bounds > 0:
            result.success = False
            result.error = f"Data corruption detected: {result.out_of_bounds} out of bounds values"

    if result.avg_bus_bw_gbps == 0 and result.max_bus_bw_gbps == 0:
        result.success = False
        result.error = result.error or "Could not parse bandwidth results from NCCL output"

    return result
