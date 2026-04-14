FROM ghcr.io/mannygit/warp-env-fythvm:latest

WORKDIR /workspace

# Keep uv on the image's Python and avoid cross-filesystem hardlink warnings when
# the project directory and named volumes live on different mounts.
ENV UV_CACHE_DIR=/workspace/.uv-cache \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

CMD ["bash"]
