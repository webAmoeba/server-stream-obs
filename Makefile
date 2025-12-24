.PHONY: install start stop restart reinstall enable disable status logs install-torrent download

install:
	./bin/install.sh

start:
	systemctl start server-stream-obs

stop:
	systemctl stop server-stream-obs

restart:
	systemctl restart server-stream-obs

enable:
	systemctl enable server-stream-obs

disable:
	systemctl disable server-stream-obs

status:
	systemctl status server-stream-obs --no-pager -l

logs:
	journalctl -u server-stream-obs -n 200 --no-pager

reinstall:
	-systemctl stop server-stream-obs
	$(MAKE) install
	systemctl start server-stream-obs

# Torrent helpers
TORRENT_FILE ?= /root/my.torrent
DOWNLOAD_DIR ?= /root/downloads

install-torrent:
	apt-get update -y
	apt-get install -y aria2

download:
	mkdir -p $(DOWNLOAD_DIR)
	aria2c --dir=$(DOWNLOAD_DIR) --seed-time=0 --summary-interval=5 $(TORRENT_FILE)

