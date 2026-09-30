#!/bin/bash
set -euo pipefail
exec > /var/log/doom-native-worker-02.log 2>&1
systemd-run --unit=doom-native-worker-safety-stop --on-active=4h /sbin/shutdown -h now
dnf install -y python3.11 python3.11-pip tmux rsync
sudo -u ec2-user /usr/bin/python3.11 -m venv /home/ec2-user/venv
sudo -u ec2-user /home/ec2-user/venv/bin/python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.0
sudo -u ec2-user /home/ec2-user/venv/bin/python -m pip install --no-cache-dir numpy==2.4.6 vizdoom==1.3.1 Pillow==12.3.0
sudo -u ec2-user mkdir -p /home/ec2-user/doom-v3-worker02/{code,runs,datasets,receipts,logs}
touch /home/ec2-user/doom-native-worker-02-ready
chown ec2-user:ec2-user /home/ec2-user/doom-native-worker-02-ready
