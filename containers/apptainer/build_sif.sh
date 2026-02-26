#!/usr/bin/env bash
set -euo pipefail

# ---- User-tunable defaults ----
VM="${VM:-apptainer}"
IMAGE="${IMAGE:-myapp}"
TAG="${TAG:-amd64}"
PLATFORM="${PLATFORM:-linux/amd64}"

# ---- Derived paths ----
MAC_DIR="$(cd "$(dirname "$0")" && pwd)"
TAR_PATH="${MAC_DIR}/${IMAGE}_${TAG}.tar"
SIF_NAME="${IMAGE}_${TAG}.sif"
SIF_PATH="${MAC_DIR}/${SIF_NAME}"

echo "==> Project dir:  ${MAC_DIR}"
echo "==> VM:           ${VM}"
echo "==> Docker image: ${IMAGE}:${TAG}"
echo "==> Platform:     ${PLATFORM}"
echo "==> Tar:          ${TAR_PATH}"
echo "==> SIF name:     ${SIF_NAME}"

# 1) Ensure buildx builder exists
docker buildx create --name multi --use >/dev/null 2>&1 || docker buildx use multi
docker buildx inspect --bootstrap >/dev/null

# 2) Build Docker image
echo "==> Building Docker image..."
docker buildx build --platform "${PLATFORM}" -t "${IMAGE}:${TAG}" --load "${MAC_DIR}"

# 3) Verify architecture
echo "==> Verifying image exists..."
docker image inspect "${IMAGE}:${TAG}" --format '{{.Os}}/{{.Architecture}}'

# 4) Save to tar
echo "==> Saving image to tar..."
docker save "${IMAGE}:${TAG}" -o "${TAR_PATH}"
ls -lh "${TAR_PATH}"

# 5) Build SIF inside Lima VM
echo "==> Building SIF inside Lima VM..."
limactl shell "${VM}" -- bash -lc "
set -e
echo \"VM HOME=\$HOME\"
ls -lh \"${TAR_PATH}\"
apptainer --version
apptainer build --force \"\$HOME/${SIF_NAME}\" docker-archive:///\"${TAR_PATH}\"
ls -lh \"\$HOME/${SIF_NAME}\"
"

# 6) Copy SIF back to macOS
echo "==> Copying SIF back to macOS..."
limactl shell "${VM}" -- bash -lc "cat \"\$HOME/${SIF_NAME}\"" > "${SIF_PATH}"
ls -lh "${SIF_PATH}"

# 7) Remove tar (cleanup step)
echo "==> Removing tar file..."
rm -f "${TAR_PATH}"

echo "==> Done: ${SIF_PATH}"
