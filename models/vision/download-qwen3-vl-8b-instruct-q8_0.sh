#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
destination_directory="${model_root}/vision/qwen3-vl-8b-instruct"
mkdir -p "$destination_directory"

download_file() {
    url="$1"
    destination="$2"
    checksum="$3"
    temporary="${destination}.part"

    if [ -f "$destination" ] && printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
        echo "Already downloaded: $destination"
        return
    fi

    curl -fL --retry 3 --continue-at - "$url" -o "$temporary"
    printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
    mv "$temporary" "$destination"
}

revision="f982a07559d4a2f6c8744d840bf6fccab30eea96"
repository="https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen3VL-8B-Instruct-Q8_0.gguf?download=true" \
    "${destination_directory}/Qwen3VL-8B-Instruct-Q8_0.gguf" \
    "0d264b3941185d00a74f75c4245521dae088ff1efc90ab8d1754e83f5844adb0"

download_file \
    "${repository}/mmproj-Qwen3VL-8B-Instruct-F16.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen3VL-8B-Instruct-F16.gguf" \
    "ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38"
