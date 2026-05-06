# tools/sandbox_runner/Dockerfile
#
# Minimal sandbox image used to:
#   1. Run the test suite (pytest) against a read-only repo mount.
#   2. Apply git patches inside an isolated filesystem.
#
# Build once:
#   docker build -t realai-sandbox:latest tools/sandbox_runner
#
# Usage (test runner):
#   docker run --rm -v $(pwd):/workspace:ro realai-sandbox:latest
#
# Usage (patch apply — read-write mount):
#   docker run --rm -v $(pwd):/workspace realai-sandbox:latest \
#       sh -c "git apply /tmp/patch.diff && git add -A"

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install test dependencies at image build time.
# Adjust to match your project's actual test requirements.
RUN pip install --no-cache-dir pytest chromadb requests

COPY run_tests.sh /usr/local/bin/run_tests.sh
RUN chmod +x /usr/local/bin/run_tests.sh

ENTRYPOINT ["/usr/local/bin/run_tests.sh"]
