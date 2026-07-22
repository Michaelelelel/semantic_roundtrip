#!/bin/sh
curl -fL 'https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors?download=true' -o "$(dirname "$0")/checkpoints/v1-5-pruned-emaonly.safetensors"
