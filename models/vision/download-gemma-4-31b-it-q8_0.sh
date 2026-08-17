#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/gemma-4-31b-it"

revision="4fa4fdf38bee237b5c9e8a5b4e72cf39404c9dcc"
repository="https://huggingface.co/ggml-org/gemma-4-31B-it-GGUF/resolve/${revision}"

download_file \
    "${repository}/gemma-4-31B-it-Q8_0.gguf?download=true" \
    "${destination_directory}/gemma-4-31B-it-Q8_0.gguf" \
    "fcd52cebacb165a98df5abe6fb70dbf076835f4a06e064ffb33dd739b8835c9c"

download_file \
    "${repository}/mmproj-gemma-4-31B-it-Q8_0.gguf?download=true" \
    "${destination_directory}/mmproj-gemma-4-31B-it-Q8_0.gguf" \
    "8872f1dd7ba6a750a039c04b45812511f4ecf004e229420cea58c8049a970fb6"
