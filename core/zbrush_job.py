"""Runs inside ZBrush: build one ZTL per asset of job.json (placeholder, replaced once the ZBrush commands are verified)."""
import json
import os
import sys


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(root, 'job.json'), encoding='utf-8') as handle:
        json.load(handle)


if __name__ == '__main__':
    main()
