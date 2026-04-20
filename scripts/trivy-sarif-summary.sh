#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Render Trivy filesystem SARIF as Markdown (one bullet per finding).
# With GITHUB_STEP_SUMMARY set (GitHub Actions), append to the job Summary; else print to stdout.
set -euo pipefail

SARIF="${1:-vulnerability-scan-results.sarif}"

emit_no_sarif() {
	local msg="No SARIF at \`${SARIF}\` (Trivy step may have failed before writing results)."
	if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
		{
			echo "## Trivy findings (detail)"
			echo ""
			echo "$msg"
		} >>"$GITHUB_STEP_SUMMARY"
	fi
	echo "$msg" >&2
}

if [[ ! -f "$SARIF" ]]; then
	emit_no_sarif
	exit 0
fi

if ! command -v jq >/dev/null 2>&1; then
	echo "jq is required for trivy-sarif-summary.sh" >&2
	exit 1
fi

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT

{
	echo "## Trivy findings (detail)"
	echo ""
	echo "One line per HIGH/CRITICAL result from Trivy (misconfigs, vulns, etc.)."
	echo ""
	# shellcheck disable=SC2016
	jq -r '
	  .runs[] | .results[]? |
	  (.message.text // "") as $t |
	  (
	    if ($t | test("Message: ")) then ($t | split("Message: ")[1] | split("\n")[0])
	    else ($t | split("\n")[0])
	    end
	  ) as $msg |
	  "- **\(.ruleId // "?")** [\(.level)] -- \($msg | if length > 200 then .[0:197] + "..." else . end) -- `\(.locations[0].physicalLocation.artifactLocation.uri // "?"):\(.locations[0].physicalLocation.region.startLine // "")`"
	' "$SARIF"
} >"$OUT"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
	cat "$OUT" >>"$GITHUB_STEP_SUMMARY"
else
	cat "$OUT"
fi
