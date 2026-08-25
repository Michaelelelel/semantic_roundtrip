# Shared download functions for the model scripts.

run_hf() {
    if command -v hf >/dev/null 2>&1; then
        hf "$@"
    elif command -v uvx >/dev/null 2>&1; then
        uvx hf "$@"
    elif [ -x "$HOME/.venvs/hf-download/bin/hf" ]; then
        "$HOME/.venvs/hf-download/bin/hf" "$@"
    else
        echo "Install the Hugging Face CLI; see setupproject.md." >&2
        return 1
    fi
}

# Usage: download_file HUGGING_FACE_URL DESTINATION SHA256 [HF_TOKEN]
download_file() (
    url="${1%%\?*}"
    destination="$2"
    checksum="$3"
    token="${4:-}"

    if [ -f "$destination" ] &&
        printf '%s  %s\n' "$checksum" "$destination" |
            sha256sum --check --status; then
        echo "Already downloaded: $destination"
        return
    fi

    hub_path="${url#https://huggingface.co/}"
    repository="${hub_path%%/resolve/*}"
    revision_and_file="${hub_path#*/resolve/}"
    revision="${revision_and_file%%/*}"
    filename="${revision_and_file#*/}"
    download_directory="${destination}.download"
    downloaded="${download_directory}/${filename}"

    mkdir -p "$(dirname -- "$destination")" "$download_directory"
    if [ -n "$token" ]; then
        export HF_TOKEN="$token"
    fi

    run_hf download \
        "$repository" \
        "$filename" \
        --revision "$revision" \
        --local-dir "$download_directory"

    printf '%s  %s\n' "$checksum" "$downloaded" | sha256sum --check
    mv "$downloaded" "$destination"
    rm -rf "$download_directory"
    echo "Downloaded: $destination"
)

# Stop early with a useful message when a gated model needs authentication.
require_hf_token() {
    if [ -z "${HF_TOKEN:-}" ]; then
        echo "HF_TOKEN is required for $1." >&2
        echo "Accept the license first: $2" >&2
        exit 1
    fi
}
