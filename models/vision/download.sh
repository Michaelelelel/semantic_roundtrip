#!/bin/sh
mkdir -p "$(dirname "$0")/llava-v1.5-7b"
curl -fL 'https://huggingface.co/mys/ggml_llava-v1.5-7b/resolve/9b713a64048c7f982ec3969e60e9f61f7a2730c2/ggml-model-q4_k.gguf?download=true' -o "$(dirname "$0")/llava-v1.5-7b/ggml-model-q4_k.gguf"
curl -fL 'https://huggingface.co/second-state/Llava-v1.5-7B-GGUF/resolve/ffb5e9a1a3172f82448fbdbe578a051c8dc2ff77/llava-v1.5-7b-mmproj-model-f16.gguf?download=true' -o "$(dirname "$0")/llava-v1.5-7b/mmproj-model-f16.gguf"
