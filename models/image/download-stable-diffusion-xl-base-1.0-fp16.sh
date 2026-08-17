#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"

download_file \
    'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/47cd5302d866fa60cf8fb81f0e34d42e38f6100c/sd_xl_base_1.0.safetensors?download=true' \
    "${model_root}/image/checkpoints/sd_xl_base_1.0.safetensors" \
    '31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b'
