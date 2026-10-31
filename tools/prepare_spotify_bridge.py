#!/usr/bin/env python3
"""Prepare an extension for review. Does not install Spicetify or modify Spotify."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from afterglow.spotify_bridge import bridge_token
from afterglow.storage import paths, atomic_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Destination JS file; defaults to the private Afterglow config directory')
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[1] / 'integrations/spotify/afterglow-bridge.js'
    target = args.output or paths()[0] / 'afterglow-bridge.local.js'
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(target, template.read_text().replace('__AFTERGLOW_LOCAL_TOKEN__', bridge_token()))
    print('Prepared extension:', target)
    print('No Spotify client files or Spicetify configuration were changed.')


if __name__ == '__main__': main()
