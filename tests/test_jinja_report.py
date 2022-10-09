import random
import re
from pathlib import Path


def run(testdir, report_path: str = "report.html", template_path: str = None, *args):
    report_path = Path(testdir.tmpdir) / report_path
    if template_path:
        result = testdir.runpytest(
            "--html-report", str(report_path), "--html-template", str(template_path), *args
        )
    else:
        result = testdir.runpytest("--html-report", str(report_path), *args)
    with open(str(report_path)) as f:
        html = f.read()
    return result, html


def assert_results_by_outcome(html, test_outcome, test_outcome_number, label=None):
    # Asserts if the test number of this outcome in the summary is correct
    regex_summary = r"(\d)+ {}".format(label or test_outcome)
    assert int(re.search(regex_summary, html).group(1)) == test_outcome_number

    # Asserts if the generated checkbox of this outcome is correct
    regex_checkbox = f'<input checked="true" class="filter" data-test-result="{test_outcome}"'
    if test_outcome_number == 0:
        regex_checkbox += r"(\s)+disabled"
    assert re.search(regex_checkbox, html) is not None

    # Asserts if the table rows of this outcome are correct
    regex_table = f'tbody class="{test_outcome} '
    assert len(re.findall(regex_table, html)) == test_outcome_number


def assert_results(
    html,
    tests=1,
    duration=None,
    passed=1,
    skipped=0,
    failed=0,
    errors=0,
    xfailed=0,
    xpassed=0,
    rerun=0,
):
    # Asserts total amount of tests
    total_tests = re.search(r"(\d)+ tests ran", html)
    assert int(total_tests.group(1)) == tests

    # Asserts tests running duration
    if duration is not None:
        tests_duration = re.search(r"([\d,.]+) seconds", html)
        assert float(tests_duration.group(1)) >= float(duration)

    # Asserts by outcome
    assert_results_by_outcome(html, "passed", passed)
    assert_results_by_outcome(html, "skipped", skipped)
    assert_results_by_outcome(html, "failed", failed)
    assert_results_by_outcome(html, "error", errors, "errors")
    assert_results_by_outcome(html, "xfailed", xfailed, "expected failures")
    assert_results_by_outcome(html, "xpassed", xpassed, "unexpected passes")
    # assert_results_by_outcome(html, "rerun", rerun)


class TestPytestJinja:
    def test_help_message(self, testdir):
        result = testdir.runpytest("--help")
        # fnmatch_lines does an assertion internally
        result.stdout.fnmatch_lines(
            [
                "pytest-jinja:",
                "*--html-report=HTML_REPORT_PARAM",
                "*The report destination.",
                "*--html-template=JINJA_TEMPLATE_PARAM",
                "*A jinja-based html template.",
            ]
        )

    def test_create_report_default_template(self, testdir):
        testdir.makepyfile("def test_pass(): pass")
        report_path = "report.html"
        result, html = run(testdir, report_path)
        assert result.ret == 0
        assert Path(report_path).exists()
        assert "test_create_report" in html
        assert '<span class="passed">1 passed</span>' in html
        assert '<span class="skipped">0 skipped</span>' in html
        assert '<span class="failed">0 failed</span>' in html
        assert '<span class="error">0 errors</span>' in html
        assert '<span class="xfailed">0 expected failures</span>' in html
        assert '<span class="xpassed">0 unexpected passes</span>' in html
        assert '<td class="col-result">passed<span class="collapser"></span></td>'

    def test_create_report_custom_template(self, testdir):
        testdir.makepyfile("def test_pass(): pass")
        report_path = "report.html"
        template_path = Path(__file__).parent / "test_template.html"
        result, html = run(testdir, report_path=report_path, template_path=template_path)
        assert result.ret == 0
        assert Path(report_path).exists()
        assert "test_create_report_custom_template" in html
        assert "<td>passed</td>" in html

    def test_all_outcomes_bootstrap(self, testdir):
        testdir.makepyfile(
            """
        import pytest
        class TestStupid:
            def test_pass(self):
                assert 1 == 1

            def test_fail(self):
                assert 1 == 2

            @pytest.mark.skip
            def test_skip(self):
                pass
        """
        )
        report_path = "report.html"
        template_path = Path(__file__).parent / "test_template.html"
        result, html = run(testdir, report_path=report_path, template_path=template_path)
        assert Path(report_path).exists()
        assert all(
            tag in html for tag in ["<td>passed</td>", "<td>failed</td>", "<td>skipped</td>"]
        )

    def test_durations(self, testdir):
        sleep = float(0.2)
        testdir.makepyfile(
            """
            import time
            def test_sleep():
                time.sleep({:f})
        """.format(
                sleep * 2
            )
        )
        result, html = run(testdir)
        assert result.ret == 0
        assert_results(html, duration=sleep)
        p = re.compile(r'<td class="col-duration">([\d,.]+)')
        m = p.search(html)
        assert float(m.group(1)) >= sleep

    def test_pass(self, testdir):
        testdir.makepyfile("def test_pass(): pass")
        result, html = run(testdir)
        assert result.ret == 0
        assert_results(html)

    def test_skip(self, testdir):
        reason = str(random.random())
        testdir.makepyfile(
            f"""
            import pytest
            def test_skip():
                pytest.skip('{reason}')
        """
        )
        result, html = run(testdir)
        assert result.ret == 0
        assert_results(html, tests=0, passed=0, skipped=1)
        assert f"Skipped: {reason}" in html

    def test_fail(self, testdir):
        testdir.makepyfile("def test_fail(): assert False")
        result, html = run(testdir)
        assert result.ret
        assert_results(html, passed=0, failed=1)
        assert "AssertionError" in html

    def test_rerun(self, testdir):
        testdir.makepyfile(
            """
            import pytest
            @pytest.mark.flaky(reruns=5)
            def test_example():
                assert False
        """
        )
        result, html = run(testdir)
        assert result.ret
        assert_results(html, passed=0, failed=1, rerun=5)

    def test_environment(self, testdir):
        content = str(random.random())
        testdir.makeconftest(
            f"""
            def pytest_configure(config):
                config._metadata['content'] = '{content}'
        """
        )
        testdir.makepyfile("def test_pass(): pass")
        result, html = run(testdir)
        assert result.ret == 0
        assert "Environment" in html
        assert len(re.findall(content, html)) == 1

    def test_utf8_surrogate(self, testdir):
        testdir.makepyfile(
            r"""
            import pytest

            @pytest.mark.parametrize('val', ['\ud800'])
            def test_foo(val):
                pass
        """
        )
        result, html = run(testdir)
        assert result.ret == 0
        assert_results(html, passed=1)

    def test_record_properties(self, testdir):
        testdir.makepyfile(
            r"""
            import pytest

            def test_foo(record_property):
                record_property("example", 123)
        """
        )
        report_path = "report.html"
        template_path = Path(__file__).parent / "test_template.html"
        result, html = run(testdir, report_path=report_path, template_path=template_path)
        assert result.ret == 0
        assert 'example = 123' in html
