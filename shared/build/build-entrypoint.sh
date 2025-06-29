#!/usr/bin/env bash

set -e

if [[ $(id -u envoybuild) != "${BUILD_UID}" ]]; then
    usermod -u "${BUILD_UID}" envoybuild
    chown envoybuild /home/envoybuild
fi

if [[ ! -e /output ]]; then
    mkdir /output
fi

chown envoybuild /output
chmod 1777 /tmp

exec gosu envoybuild "$@"
