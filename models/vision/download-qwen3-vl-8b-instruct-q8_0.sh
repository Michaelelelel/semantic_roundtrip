#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/qwen3-vl-8b-instruct"

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
