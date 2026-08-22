#!/usr/bin/env bash
# Copy CI workflow definitions into .github/workflows/ (requires repo write).
# (Automated agents often push without `workflows` permission, which is why
#  these live in packaging/ci rather than .github/workflows by default.)
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p .github/workflows
cp packaging/ci/ci.yml .github/workflows/ci.yml
cp packaging/ci/release.yml .github/workflows/release.yml
echo "installed .github/workflows/{ci,release}.yml — commit & push to enable CI"
