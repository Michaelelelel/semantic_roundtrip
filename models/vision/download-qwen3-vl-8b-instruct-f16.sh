#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/qwen3-vl-8b-instruct-f16"
revision='f982a07559d4a2f6c8744d840bf6fccab30eea96'
repository="https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/${revision}"

download_file \
    "${repository}/Qwen3VL-8B-Instruct-F16.gguf?download=true" \
    "${destination_directory}/Qwen3VL-8B-Instruct-F16.gguf" \
    '2715c1a097f1943fb88ad59c7c0e9288a7a50c84d60cf18c6227bd9a40520972'

download_file \
    "${repository}/mmproj-Qwen3VL-8B-Instruct-F16.gguf?download=true" \
    "${destination_directory}/mmproj-Qwen3VL-8B-Instruct-F16.gguf" \
    'ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38'
