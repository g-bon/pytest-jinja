import datetime
import os
import time
from pathlib import Path

import jinja2


def pytest_addoption(parser):
    group = parser.getgroup("pytest-jinja")
    group.addoption(
        "--html-report",
        action="store",
        dest="html_report_param",
        default=None,
        help="The report destination.",
    )

    group.addoption(
        "--html-template",
        action="store",
        dest="jinja_template_param",
        default=None,
        help="A jinja-based html template.",
    )


def pytest_configure(config):
    report_path = config.getoption("html_report_param")
    template_path = config.getoption("jinja_template_param")

    if report_path and not hasattr(config, "slaveinput"):
        config._html = JinjaReport(report_path, template_path, config)
        config.pluginmanager.register(config._html)


def pytest_unconfigure(config):
    html = getattr(config, "_html", None)
    if html:
        del config._html
        config.pluginmanager.unregister(html)


class JinjaReport:
    def __init__(self, report_path, template_path, config):
        self.report_path = Path(os.path.expandvars(report_path)).expanduser().resolve()
        self.template_path = (
            Path(template_path)
            if template_path
            else Path(__file__).parent / "templates/default/default.html"
        )
        self.results = []
        self.tests_count = 0
        self.errors = self.failed = 0
        self.passed = self.skipped = 0
        self.xfailed = self.xpassed = 0
        has_rerun = config.pluginmanager.hasplugin("rerunfailures")
        self.rerun = 0 if has_rerun else None
        self.config = config
        self.suite_start_time = None
        self.duration = None
        self.time_report_generation = None
        self.environment = None

    class TestResult:
        def __init__(self, report, config):
            self.test_id = report.nodeid
            if getattr(report, "when", "call") != "call":
                self.test_id = "::".join([report.nodeid, report.when])
            self.time = getattr(report, "duration", 0.0)
            self.outcome = report.outcome
            self.stacktrace = str(report.longrepr) if report.longrepr else report.longrepr
            self.config = config

        def __lt__(self, other):
            order = ("Error", "Failed", "Rerun", "XFailed", "XPassed", "Skipped", "Passed")
            return order.index(self.outcome) < order.index(other.outcome)

    def count_passed(self, report, result):
        if report.when == "call":
            self.results.append(result)

            if hasattr(report, "wasxfail"):
                self.xpassed += 1
            else:
                self.passed += 1

    def count_failed(self, report, result):
        self.results.append(result)

        if getattr(report, "when", None) == "call":
            if hasattr(report, "wasxfail"):
                # pytest < 3.0 marked xpasses as failures
                self.xpassed += 1
            else:
                self.failed += 1
        else:
            self.errors += 1

    def count_skipped(self, report, result):
        self.results.append(result)

        if hasattr(report, "wasxfail"):
            self.xfailed += 1
        else:
            self.skipped += 1

    def count_other(self, report, result):
        # For now, the only "other" the plugin give support is rerun
        self.rerun += 1
        self.results.append(result)

    def _generate_report(self, session):
        suite_stop_time = time.time()
        self.duration = suite_stop_time - self.suite_start_time
        self.time_report_generation = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
        self.environment = self._generate_environment(session.config)
        self.tests_count = self.passed + self.failed + self.xpassed + self.xfailed

        templates_path = self.template_path.parent
        jinja_template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(templates_path)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

        template = jinja_template_env.get_template(str(Path(self.template_path).name))
        Path(self.report_path.parent).mkdir(parents=True, exist_ok=True)

        template.stream(report=self,).dump(str(self.report_path))

    def _generate_environment(self, config):
        if not hasattr(config, "_metadata"):
            return dict()
        if config._metadata is None:
            return dict()
        return config._metadata

    def pytest_runtest_logreport(self, report):
        result = self.TestResult(report, self.config)

        if report.passed:
            self.count_passed(report, result)
        elif report.failed:
            self.count_failed(report, result)
        elif report.skipped:
            self.count_skipped(report, result)
        else:
            self.count_other(report, result)

    def pytest_collectreport(self, report):
        if report.failed:
            self.count_failed(report)

    def pytest_sessionstart(self, session):
        self.suite_start_time = time.time()

    def pytest_sessionfinish(self, session):
        self._generate_report(session)

    def pytest_terminal_summary(self, terminalreporter):
        terminalreporter.write_sep("-", "generated html file: {0}".format(self.report_path))
