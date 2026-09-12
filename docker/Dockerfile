FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DISPLAY=:99

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-pip \
        python3-venv \
        procps \
        xvfb \
        libasound2t64 \
        libatk-bridge2.0-0t64 \
        libatk1.0-0t64 \
        libatspi2.0-0t64 \
        libcups2t64 \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libgl1 \
        libglib2.0-0 \
        libglu1-mesa \
        libgtk-3-0t64 \
        libnss3 \
        libopengl0 \
        libsm6 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxi6 \
        libxkbcommon-x11-0 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xfixes0 \
        libxcb-xinerama0 \
        libxcb-xinput0 \
        libxrandr2 \
        libxrender1 \
        libxtst6 \
        libxext6 \
        mesa-utils && \
    rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install PySide6 && \
    /opt/venv/bin/pip install -e /app[test]

ENV PATH="/opt/venv/bin:${PATH}"

COPY docker/docker_prepare.sh /usr/local/bin/docker_prepare.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker_prepare.sh && \
    chmod +x /usr/local/bin/docker_prepare.sh

ENTRYPOINT ["/usr/local/bin/docker_prepare.sh"]
CMD ["mne_nodes"]
