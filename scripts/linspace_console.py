"""Consistent CLI status output. Never decorate machine-readable stdout."""
import os
import sys


def linspace_log(level, message):
    colors = {'STEP': '36', 'INFO': '36', 'OK': '32', 'WARN': '33', 'ERROR': '31'}
    color = sys.stderr.isatty() and os.environ.get('TERM', 'dumb') != 'dumb' and not os.environ.get('NO_COLOR')
    label = f'{level:<5}'
    if color:
        label = f'\033[{colors.get(level, "36")}m{label}\033[0m'
    text = ''.join(c for c in str(message) if ord(c) >= 32 or c in '\n\t')
    for line in text.splitlines() or ['']:
        try:
            sys.stderr.write(f'[linspace] {label} {line}\n')
            sys.stderr.flush()
        except BrokenPipeError:
            return
