#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
destination_directory="${model_root}/vision/llava-v1.5-7b"
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

download_file \
    'https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/9b713a64048c7f982ec3969e60e9f61f7a2730c2/ggml-model-q4_k.gguf?download=true' \
    "${destination_directory}/ggml-model-q4_k.gguf" \
    '7ac9c2f7b8d76cc7f3118cdf0953ebab7a7a9b12bad5dbe237219d2ab61765ea'

download_file \
    'https://huggingface.co/second-state/Llava-v1.5-7B-GGUF/resolve/ffb5e9a1a3172f82448fbdbe578a051c8dc2ff77/llava-v1.5-7b-mmproj-model-f16.gguf?download=true' \
    "${destination_directory}/mmproj-model-f16.gguf" \
    '50da4e5b0a011615f77686f9b02613571e65d23083c225e107c08c3b1775d9b1'
