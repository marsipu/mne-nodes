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
        libgl1 \
        libglib2.0-0 \
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
        libxrender1 \
        libxext6 && \
    rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install PySide6 && \
    /opt/venv/bin/pip install -e /app[test]

ENV PATH="/opt/venv/bin:${PATH}"

COPY docker_prepare.sh /usr/local/bin/docker_prepare.sh
RUN chmod +x /usr/local/bin/docker_prepare.sh

ENTRYPOINT ["/usr/local/bin/docker_prepare.sh"]
CMD ["mne_nodes"]
