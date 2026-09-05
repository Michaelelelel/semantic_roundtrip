#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/gemma-4-31b-it"
revision='4fa4fdf38bee237b5c9e8a5b4e72cf39404c9dcc'
repository="https://huggingface.co/ggml-org/gemma-4-31B-it-GGUF/resolve/${revision}"

download_file \
    "${repository}/gemma-4-31B-it-BF16.gguf?download=true" \
    "${destination_directory}/gemma-4-31B-it-BF16.gguf" \
    '5b2c106a691fa0d6df5f3b8cfa43b4b3f2a3d2aa3ebbdeb303b459df2f1fd352'

download_file \
    "${repository}/mmproj-gemma-4-31B-it-BF16.gguf?download=true" \
    "${destination_directory}/mmproj-gemma-4-31B-it-BF16.gguf" \
    '0e1e4f24cba407a7b91aab0a4175f923dcb075455edd216577270fdffb24658b'
