set -eu
cd /root/amadeus-m120l
printf '%s  %s\n' 'c75a2846fa470ae685783ed13c9ba68793f977d335532fb7d93ed8a67e6b8ef7' 'linux-run-preview.py' | sha256sum -c -
exec /root/jobs-env/bin/python -I -B /root/amadeus-m120l/linux-run-preview.py