# The wireless Android Auto bridge (bridge.py). Debian's own packages only:
# Python with the D-Bus bindings for BlueZ and NetworkManager, and iw for the
# Wi-Fi country.
FROM debian:trixie-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-dbus python3-gi iw \
 && rm -rf /var/lib/apt/lists/*
# The code (bridge.py, protocol.py, setting.py) is mounted in (compose.yaml): a
# restart picks up changes, without a
# build, which needs the board's own network.
WORKDIR /opt/aa
CMD ["python3", "-u", "bridge.py"]
