#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/qwen2.5-vl-7b-instruct-f16"
revision='508edd0afaa66bb9e9f40587acc2184f02daf1f6'
repository="https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen2.5-VL-7B-Instruct-f16.gguf?download=true" \
    "${destination_directory}/Qwen2.5-VL-7B-Instruct-f16.gguf" \
    '7b32d3b89735797b7e0e79a241b77da918cdedec6135f7c3d4ec6383a044211b'

download_file \
    "${repository}/mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf" \
    'c24a7f5fcfc68286f0a217023b6738e73bea4f11787a43e8238d4bb1b8604cde'
