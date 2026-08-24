#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/llava-v1.5-7b-f16"
revision='9b713a64048c7f982ec3969e60e9f61f7a2730c2'
repository="https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/${revision}"

download_file \
    "${repository}/ggml-model-f16.gguf?download=true" \
    "${destination_directory}/ggml-model-f16.gguf" \
    'be1943f3d90c9ca14356288e8aa5e35a3e9c8d0c6c5e0b338f919bdaad27e6aa'

download_file \
    "${repository}/mmproj-model-f16.gguf?download=true" \
    "${destination_directory}/mmproj-model-f16.gguf" \
    'b7c8ff0f58fca47d28ba92c4443adf8653f3349282cb8d9e6911f22d9b3814fe'
