#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/qwen2.5-vl-32b-instruct-f16"
revision='94e4f98b5df15a6198401ad1dce38897b38c41a6'
repository="https://huggingface.co/ggml-org/Qwen2.5-VL-32B-Instruct-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen2.5-VL-32B-Instruct-f16-00001-of-00002.gguf?download=true" \
    "${destination_directory}/Qwen2.5-VL-32B-Instruct-f16-00001-of-00002.gguf" \
    '6d081680128102624201f50955308578c4e26056f3eb5a24a53ae726c7fd0d56'

download_file \
    "${repository}/Qwen2.5-VL-32B-Instruct-f16-00002-of-00002.gguf?download=true" \
    "${destination_directory}/Qwen2.5-VL-32B-Instruct-f16-00002-of-00002.gguf" \
    '88e6e38ffd87cc70560eccc97c6b951b0c50a38832d1fcc41609c13dac3856dd'

download_file \
    "${repository}/mmproj-Qwen2.5-VL-32B-Instruct-f16.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen2.5-VL-32B-Instruct-f16.gguf" \
    '8b07ad34435e512d4d0467d12dcbec49cbebc378e18c02b26c90fa41d8a5c7b9'
