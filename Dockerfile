# Use NVIDIA's runtime image instead of devel-only
FROM nvidia/cuda:12.9.0-runtime-ubuntu22.04 AS runtime
FROM nvidia/cuda:12.9.0-devel-ubuntu22.04 AS builder

# Build stage
RUN apt-get update && apt-get install -y \
    build-essential cmake git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone https://github.com/ggerganov/whisper.cpp.git .

# Install CUDA runtime libraries for linking
RUN apt-get update && apt-get install -y \
    cuda-cudart-12-9 \
    && rm -rf /var/lib/apt/lists/*

# Create symlink for libcuda.so.1 if it doesn't exist
RUN ln -sf /usr/local/cuda/compat/libcuda.so.1 /usr/local/cuda/lib64/libcuda.so.1 || \
    ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/local/cuda/lib64/libcuda.so.1 || true

# Set library path to help linker find CUDA libraries
ENV LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64:$LD_LIBRARY_PATH

RUN cmake -B build -DGGML_CUDA=1 && cmake --build build -j$(nproc)

# Runtime stage
FROM runtime
RUN apt-get update && apt-get install -y \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/build/bin/ ./build/bin/
COPY --from=builder /app/build/lib* ./build/
COPY --from=builder /app/build/src/ ./build/src/
COPY --from=builder /app/build/ggml/src/ ./build/ggml/src/
COPY --from=builder /app/ggml/src/ ./ggml/src/
COPY --from=builder /app/models/ ./models/

# Set library path for runtime to include the build directory
ENV LD_LIBRARY_PATH=/app/build:/app/build/src:/app/build/ggml/src:/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Download the model
RUN ./models/download-ggml-model.sh base.en
RUN ./models/download-ggml-model.sh small.en
RUN ./models/download-ggml-model.sh medium.en
RUN ./models/download-ggml-model.sh large-v3-turbo-q8_0
RUN ./models/download-ggml-model.sh large-v3-turbo
RUN ./models/download-ggml-model.sh large-v3-q5_0

# Expose the server port (default: 8080)
EXPOSE 8080

# No --convert flag since no ffmpeg
CMD ["./build/bin/whisper-server", \
     "--model", "/app/models/ggml-base.en.bin", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--threads", "4", \
     "--processors", "1", \
     # "--flash-attn", \
     "--no-timestamps"]
