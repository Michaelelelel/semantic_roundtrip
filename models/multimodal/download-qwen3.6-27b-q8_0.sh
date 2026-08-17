#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/qwen3.6-27b"

revision="8a7ee08e8b9bfb857107ecc25a5599d2f38b76f8"
repository="https://huggingface.co/ggml-org/Qwen3.6-27B-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen3.6-27B-Q8_0.gguf?download=true" \
    "${destination_directory}/Qwen3.6-27B-Q8_0.gguf" \
    "73f8260284708ed78ae266df672288b6ad1f2c73ec7ffeb7514b5cecdba646c9"

download_file \
    "${repository}/mmproj-Qwen3.6-27B-Q8_0.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen3.6-27B-Q8_0.gguf" \
    "dd184a692287f0d7e8fa56c8744df20c46667818efc04e6d48996d18d9521a4e"
