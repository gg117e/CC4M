FROM python:3.12-slim

# Runtime and build dependencies for CCFinderSW, CLAIM, GitHub Linguist, and
# the Rust ccfindersw-parser helper.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        ruby \
        ruby-dev \
        default-jdk-headless \
        pkg-config \
        cmake \
        libcurl4-openssl-dev \
        libgit2-dev \
        libssl-dev \
        zlib1g-dev \
        libicu-dev \
        build-essential \
        cargo \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JAVA_HOME=/usr/lib/jvm/default-java \
    PATH="/usr/lib/jvm/default-java/bin:${PATH}"

WORKDIR /app

# Install Python dependencies first to maximize Docker layer caching.
COPY requirements.txt .
RUN pip install --default-timeout=1000 --retries 5 --no-cache-dir -r requirements.txt

RUN gem install --no-document github-linguist

COPY . .

ARG CCF_PARSER_REPO=https://github.com/YukiOhta0519/ccfindersw-parser.git
RUN set -eux; \
    git clone --depth 1 "$CCF_PARSER_REPO" /tmp/ccfindersw-parser; \
    cd /tmp/ccfindersw-parser; \
    cargo build --release --locked || cargo build --release; \
    install -Dm755 target/release/ccfindersw-parser /usr/local/bin/ccfindersw-parser; \
    mkdir -p /app/lib/ccfindersw-parser/target/release; \
    cp target/release/ccfindersw-parser /app/lib/ccfindersw-parser/target/release/; \
    rm -rf /tmp/ccfindersw-parser

RUN mkdir -p /app/dest

EXPOSE 8000

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
