#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
model_root="${1:-$script_directory}"

"${script_directory}/text/download-mistral-7b-instruct-v0.1-q4_k_m.sh" "$model_root"
"${script_directory}/vision/download-llava-v1.5-7b-q4_k.sh" "$model_root"
"${script_directory}/image/download-stable-diffusion-v1-5-fp16.sh" "$model_root"

"${script_directory}/text/download-qwen3-8b-q8_0.sh" "$model_root"
"${script_directory}/vision/download-qwen3-vl-8b-instruct-q8_0.sh" "$model_root"
"${script_directory}/image/download-stable-diffusion-xl-base-1.0-fp16.sh" "$model_root"
