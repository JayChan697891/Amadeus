set -eu
umask 077
cd /root/amadeus-sdist-repair-9fb36a1
venv/bin/python -I -B driver-repaired.py > driver-repaired.log 2>&1
venv/bin/python -I -B inspect-install.py > installation.log 2>&1
cat driver-repaired.log installation.log
