#!/bin/bash
set -euo pipefail
exec > /var/log/doom-native-worker-02-resume.log 2>&1
# The first attempt's exclusive CPU-wheel index lacked a build dependency.
# Keep that log; resolve general dependencies on PyPI and pin the CPU build.
sudo -u ec2-user /home/ec2-user/venv/bin/python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu 'torch==2.14.0+cpu'
sudo -u ec2-user /home/ec2-user/venv/bin/python -m pip install --no-cache-dir numpy==2.4.6 vizdoom==1.3.1 Pillow==12.3.0
sudo -u ec2-user mkdir -p /home/ec2-user/doom-v3-worker02/{code,runs,datasets,receipts,logs}
touch /home/ec2-user/doom-native-worker-02-ready
chown ec2-user:ec2-user /home/ec2-user/doom-native-worker-02-ready
