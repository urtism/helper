import argparse
import datetime
import os
import sys
import time


def main():
    parser = argparse.ArgumentParser(
        prog='powercall',
        description='Powercall command-line stub for pipeline execution.'
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version='Powercall v3.2.0'
    )
    parser.add_argument(
        '--gui',
        action='store_true',
        help='Launch the PyQt5 GUI application.'
    )
    parser.add_argument(
        '--samplesheet',
        help='Samplesheet JSON file for pipeline execution.'
    )
    parser.add_argument(
        '--pipeline',
        help='Pipeline JSON file to execute.'
    )
    parser.add_argument(
        '--panel',
        help='Panel name used for analysis.'
    )

    args = parser.parse_args()

    if args.gui:
        print('Launching GUI...')
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        try:
            import Helper
        except Exception as exc:
            parser.error(f'Unable to import GUI module: {exc}')
        return

    if args.samplesheet or args.pipeline or args.panel:
        print('CLI pipeline execution is not yet implemented. Use the GUI or extend bin/main.py.')
        return

    parser.print_help()


if __name__ == '__main__':
    main()
