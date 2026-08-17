#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/mistral-small-4-119b"
repository='https://huggingface.co/unsloth/Mistral-Small-4-119B-2603-GGUF/resolve/bd93c721735aa32c035c0f19e738cb3371fd56ff'

download_file \
    "${repository}/UD-Q4_K_M/Mistral-Small-4-119B-2603-UD-Q4_K_M-00001-of-00003.gguf?download=true" \
    "${destination_directory}/Mistral-Small-4-119B-2603-UD-Q4_K_M-00001-of-00003.gguf" \
    'fd3cc46082e4e64eb623eea4611b02583d1de4c20a59411bf1820925d5117dfe'

download_file \
    "${repository}/UD-Q4_K_M/Mistral-Small-4-119B-2603-UD-Q4_K_M-00002-of-00003.gguf?download=true" \
    "${destination_directory}/Mistral-Small-4-119B-2603-UD-Q4_K_M-00002-of-00003.gguf" \
    'f357d8dc029824fa4515ae60d7a8b7e108546763614f16c00a1b4ea0cd94145c'

download_file \
    "${repository}/UD-Q4_K_M/Mistral-Small-4-119B-2603-UD-Q4_K_M-00003-of-00003.gguf?download=true" \
    "${destination_directory}/Mistral-Small-4-119B-2603-UD-Q4_K_M-00003-of-00003.gguf" \
    '9dc960d67fb1ef23029d24878b4cf6c63b743ab26cf9137402549591bd770c50'

download_file \
    "${repository}/mmproj-F16.gguf?download=true" \
    "${destination_directory}/mmproj-F16.gguf" \
    '8afb53096537664e248a0b4a9240c25677bb0f8a8cb5a5aad3cd1d608776a4e7'
