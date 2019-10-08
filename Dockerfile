FROM unocha/alpine-base-s6-python2:3.8

WORKDIR /srv/dataproxy

COPY . .

RUN apk add --update-cache \
        git \
        py-lxml && \
    pip -q install --upgrade \
        gunicorn \
        html5lib \
        xlrd==1.2.0 \
        json-table-schema && \
    mkdir -p /srv/config /etc/services.d/dataproxy && \
    cp docker/gunicorn_conf.py /srv/config && \
    cp docker/run_dataproxy /etc/services.d/dataproxy/run && \
    mkdir -p /var/log/dataproxy && \
    touch /var/log/dataproxy/dataproxy.access.log && \
    touch /var/log/dataproxy/dataproxy.error.log && \
    git submodule init dataproxy && \
    git submodule update dataproxy && \
    apk add --update-cache \
        build-base \
        python-dev && \
    pip install gevent && \
    apk del \
        build-base \
        python-dev && \
    rm -r /root/.cache && \
    rm -rf /var/cache/apk/*

EXPOSE 5000
