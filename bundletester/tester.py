import argparse
import logging
import os
import subprocess
import sys
import tempfile
import textwrap

from bundletester import (
    reporter,
    runner,
    spec,
    utils,
    fetchers,
)


def current_environment():
    return subprocess.check_output(['juju', 'switch']).strip()


def validate():
    # Minimally verify we expect we can continue
    subprocess.check_output(['juju', 'version'])


class BundleSpec(object):
    def __init__(self, path=None, name=None):
        self.path = path
        self.name = name

    @staticmethod
    def validate_path(path):
        bp = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(bp):
            raise argparse.ArgumentTypeError("%s not found on filesystem" % bp)
        return bp

    @classmethod
    def parse_cli(cls, spec):
        sp = spec.split(":")
        name, path = None, None

        if any(sp[0].endswith(y) for y in ('.yml', '.yaml')):
            candidate = sp.pop(0)
            path = cls.validate_path(candidate)
            if len(sp):
                name = sp[0]
            return cls(path, name)

        name = sp[0]
        return cls(path, name)


def configure():
    parser = argparse.ArgumentParser()

    parser.add_argument('-e', '--environment')
    parser.add_argument('-t', '--testdir', default=os.getcwd())
    parser.add_argument('-b', '-c', '--bundle',
                        type=BundleSpec.parse_cli,
                        default=BundleSpec(),
                        help=textwrap.dedent("""
                        Specify a bundle ala
                        {/path/to/bundle.yaml}:{bundle_name}. Either
                        path or name is optional
                        """))
    parser.add_argument('-d', '--deployment')

    parser.add_argument('--no-destroy', action="store_true")

    parser.add_argument('-l', '--log-level', dest="log_level",
                        default=logging.INFO)
    parser.add_argument('-o', '--output', dest="output",
                        type=argparse.FileType('w'))
    parser.add_argument('-n', '--dry-run', action="store_true",
                        dest="dryrun")
    parser.add_argument('-r', '--reporter', default="spec",
                        choices=reporter.FACTORY.keys())
    parser.add_argument('-v', '--verbose', action="store_true")

    parser.add_argument('-F', '--allow-failure', dest="failfast",
                        action="store_false")
    parser.add_argument('-s', '--skip-implicit', action="store_true",
                        help="Don't include automatically generated tests")
    parser.add_argument('-x', '--exclude', dest="exclude", action="append")
    parser.add_argument('--test-pattern', dest="test_pattern")
    parser.add_argument('tests', nargs="*")
    options = parser.parse_args()

    if not options.environment:
        options.environment = current_environment()
    logging.basicConfig(level=options.log_level)
    return options


def main():
    options = configure()
    validate()

    if not options.output:
        options.output = sys.stdout

    if options.bundle.name and not options.deployment:
        options.deployment = options.bundle.name

    try:
        fetcher = fetchers.get_fetcher(options.testdir)
        options.testdir = fetcher.fetch(
            tempfile.mkdtemp(prefix='bundletester-'))
    except fetchers.FetchError as e:
        sys.stderr.write("{}\n".format(e))
        sys.exit(1)

    suite = spec.SuiteFactory(options, options.testdir)
    if not suite:
        sys.stderr.write("No Tests Found\n")
        sys.exit(3)

    report = reporter.get_reporter(options.reporter, options.output, options)
    report.set_suite(suite)
    run = runner.Runner(suite, options)
    report.header()
    if len(suite):
        with utils.juju_env(options.environment):
            [report.emit(result) for result in run()]
    report.summary()
    report.exit()


if __name__ == '__main__':
    main()
