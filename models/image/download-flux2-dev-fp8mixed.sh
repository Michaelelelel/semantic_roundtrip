#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
diffusion_directory="${model_root}/image/diffusion_models"
encoder_directory="${model_root}/image/text_encoders"
vae_directory="${model_root}/image/vae"

download_file \
    'https://huggingface.co/Comfy-Org/flux2-dev/resolve/187ef6fc218f530e006bb6a53ded76e67f8152b8/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors?download=true' \
    "$diffusion_directory/flux2_dev_fp8mixed.safetensors" \
    '863a82e4ff950a42a6b0e80bea824828f129eb1a8fbbdbd9e8cb29859127b486'

download_file \
    'https://huggingface.co/Comfy-Org/flux2-dev/resolve/ab9055628ea245000e610f2aa2c96f4746093546/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors?download=true' \
    "$encoder_directory/mistral_3_small_flux2_bf16.safetensors" \
    '7d79902f60b1aeb3a6de2cfad02f4367b5e300a1387de3d03ac717cfa3df117c'

download_file \
    'https://huggingface.co/Comfy-Org/flux2-dev/resolve/ab9055628ea245000e610f2aa2c96f4746093546/split_files/vae/flux2-vae.safetensors?download=true' \
    "$vae_directory/flux2-vae.safetensors" \
    'd64f3a68e1cc4f9f4e29b6e0da38a0204fe9a49f2d4053f0ec1fa1ca02f9c4b5'
