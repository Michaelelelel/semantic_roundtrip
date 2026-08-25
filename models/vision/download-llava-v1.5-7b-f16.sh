#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/vision/llava-v1.5-7b-f16"
model_revision='9b713a64048c7f982ec3969e60e9f61f7a2730c2'
model_repository="https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/${model_revision}"
projector_revision='91120359e17c49efa3f156f001d7edd6a1affcf4'
projector_repository="https://huggingface.co/second-state/Llava-v1.5-7B-GGUF/resolve/${projector_revision}"

download_file \
    "${model_repository}/ggml-model-f16.gguf?download=true" \
    "${destination_directory}/ggml-model-f16.gguf" \
    'be1943f3d90c9ca14356288e8aa5e35a3e9c8d0c6c5e0b338f919bdaad27e6aa'

download_file \
    "${projector_repository}/llava-v1.5-7b-mmproj-model-f16.gguf?download=true" \
    "${destination_directory}/mmproj-model-f16.gguf" \
    '50da4e5b0a011615f77686f9b02613571e65d23083c225e107c08c3b1775d9b1'
