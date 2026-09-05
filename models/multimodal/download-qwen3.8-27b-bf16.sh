#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/qwen3.8-27b"
revision='0669b98607d47046c7c2b3f801011d54a08cfccf'
repository="https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen3.8-27B-BF16.gguf?download=true" \
    "${destination_directory}/Qwen3.8-27B-BF16.gguf" \
    '5a3eedc837bcbd1365cdbf5b71e698df3122e76586ba872f07ce3ed4a9bfa97e'

download_file \
    "${repository}/mmproj-Qwen3.8-27B-BF16.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen3.8-27B-BF16.gguf" \
    'de2a49866988ea272c43dc2a43ee2662c25725a717ca5b9059ea420a97f53fe8'
