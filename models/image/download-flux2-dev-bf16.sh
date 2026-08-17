#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

require_hf_token \
    'the gated FLUX.2 dev checkpoint' \
    'https://huggingface.co/black-forest-labs/FLUX.2-dev'

model_root="${1:-${script_directory}/..}"
diffusion_directory="${model_root}/image/diffusion_models"
encoder_directory="${model_root}/image/text_encoders"
vae_directory="${model_root}/image/vae"

download_file \
    'https://huggingface.co/black-forest-labs/FLUX.2-dev/resolve/26afe3a78bb242c0a8bb181dcc8937bb16e5c66c/flux2-dev.safetensors?download=true' \
    "$diffusion_directory/flux2-dev.safetensors" \
    '6159a3f19f829c8e84ba6e9996b7afaf7c0a5f3428677f5b37445778a320d275' \
    "$HF_TOKEN"

download_file \
    'https://huggingface.co/Comfy-Org/flux2-dev/resolve/ab9055628ea245000e610f2aa2c96f4746093546/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors?download=true' \
    "$encoder_directory/mistral_3_small_flux2_bf16.safetensors" \
    '7d79902f60b1aeb3a6de2cfad02f4367b5e300a1387de3d03ac717cfa3df117c'

download_file \
    'https://huggingface.co/Comfy-Org/flux2-dev/resolve/ab9055628ea245000e610f2aa2c96f4746093546/split_files/vae/flux2-vae.safetensors?download=true' \
    "$vae_directory/flux2-vae.safetensors" \
    'd64f3a68e1cc4f9f4e29b6e0da38a0204fe9a49f2d4053f0ec1fa1ca02f9c4b5'
