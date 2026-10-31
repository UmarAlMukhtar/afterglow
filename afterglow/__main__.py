import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description='Afterglow Linux — lyrics and light for your music')
    parser.add_argument('--demo', action='store_true', help='Start with original demo lyrics and simulated audio reaction')
    args = parser.parse_args()
    try:
        from .app import AfterglowApp
        app = AfterglowApp(demo=args.demo)
        return app.run([sys.argv[0]])
    except ImportError as error:
        print('A runtime dependency is missing:', error, file=sys.stderr)
        print('Fedora: sudo dnf install python3-gobject python3-cairo python3-dbus gtk3 pulseaudio-utils', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
