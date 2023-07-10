FROM python:3.9-slim

ARG KUBECTL_ARCH="amd64"
ARG KUBECTL_VERSION=v1.21.0

# install - kubectl
RUN set -ex; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update -yq; \
    apt-get install -yq --no-install-recommends \
        curl; \
    curl -sL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${KUBECTL_ARCH}/kubectl" -o /usr/local/bin/kubectl; \
    curl -sL "https://dl.k8s.io/${KUBECTL_VERSION}/bin/linux/${KUBECTL_ARCH}/kubectl.sha256" -o /tmp/kubectl.sha256; \
    echo "$(cat /tmp/kubectl.sha256) /usr/local/bin/kubectl" | sha256sum --check; \
    rm /tmp/kubectl.sha256; \
    chmod +x /usr/local/bin/kubectl; \
    \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*;

WORKDIR /app
COPY requirements.txt ./
RUN pip install --trusted-host pypi.python.org -r requirements.txt

COPY static ./static
COPY templates ./templates
COPY app.py flask_reverse_proxy.py k8s_info_parser.py ./

ENV PORT 5000
#CMD ["python", "./app.py"]
CMD ["gunicorn", "--threads=5", "--workers=1", "--bind=0.0.0.0:5000", "app:app" ]
