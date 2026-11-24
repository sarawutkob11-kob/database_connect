"""R14-T3: Run Job (P7) / Run all (P8, P9) errors never show the password.

R14-AC-7 .. R14-AC-9, R14-AC-13 / R14-AC-14 (Run Job, Run all), R14-AC-16
(P7-P9). Stub GUI (make_stub of tests/test_run_engine.py), the worker is kept
until the test runs it (so a reconnect can happen in between), the real
update_job_status / show_batch_error run, show_table_popup / show_batch_summary
are Mocks, print is patched. No Tk window, no database, no files.
"""

import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_connect_gui as app  # noqa: E402
import test_run_engine as tre  # noqa: E402
from test_r14_run_redaction import (  # noqa: E402
    E2,
    ERR1,
    ERR3,
    PLAIN_ERRORS,
    SECRET_ERRORS,
    R14Case,
    identity_redact,
    make_r14_stub,
    normalize,
    reconnect,
)

GUI = app.DatabaseConnectorGUI
JOB_SQL = "SELECT a FROM t WHERE job = 'J1'"


def _err_lines(texts):
    return [t for t in texts if "Error       : " in t]


# ---------------------------------------------------------------- Run Job harness
def run_job(err, *, password="default", owner=None, swap=False):
    kw = {} if password == "default" else {"password": password}
    stub = make_r14_stub(owner=owner, **kw)
    del stub.update_job_status  # the real one
    stub.show_table_popup = mock.Mock(name="show_table_popup")

    def read(*_a, **_kw):
        raise RuntimeError(err)

    stub.read_sql_dataframe = read
    job = {"name": "J1", "query": JOB_SQL, "profile": "P1"}
    stub.saved_jobs = [job]
    threads = tre._ThreadCapture()
    with mock.patch.object(app.threading, "Thread", side_effect=threads), \
            mock.patch.object(app, "messagebox") as mb:
        stub.run_job(job)
        if swap:
            reconnect(stub)
        threads.run_all()
        tre.run_after_calls(stub)
    popup_errors = [
        list(c.args[0]["Error"]) for c in stub.show_table_popup.call_args_list
    ]
    return stub, {
        "inserted": list(stub.results_text.inserted),
        "run_log": [str(c) for c in stub._write_run_log.call_args_list],
        "popup": popup_errors,
        "popup_args": [c.args[1:] + tuple(sorted(c.kwargs.items()))
                       for c in stub.show_table_popup.call_args_list],
        "finish": [c.args for c in stub._finish_job_result_report.call_args_list],
        "messagebox": [str(c) for c in mb.mock_calls],
        "gets": stub.db_password.get_calls,
    }


# ---------------------------------------------------------------- Run all harness
def run_all(failing="B", err=ERR1, *, modify=False, password="default", owner=None,
            swap=False, outer=None):
    """Run all jobs A, B, C; job `failing` raises RuntimeError(err).

    modify: job B is an UPDATE. outer: "after" -> root.after raises (first call),
    "status" -> update_job_status("running") raises (root.after runs at once).
    """
    kw = {} if password == "default" else {"password": password}
    stub = make_r14_stub(owner=owner, **kw)
    stub._stop_event = threading.Event()
    stub.run_all_btn = tre._Btn("Run all")
    stub.show_batch_summary = mock.Mock(name="show_batch_summary")
    del stub.update_job_status  # the real one
    executed = []

    def read(query, engine=None):
        executed.append(query)
        if f"'{failing}'" in query:
            raise RuntimeError(err)
        return app.pd.DataFrame({"a": [1]})

    def modify_(query, engine=None):
        executed.append(query)
        if f"'{failing}'" in query:
            raise RuntimeError(err)
        return 1

    stub.read_sql_dataframe = read
    stub._execute_modification = modify_
    jobs = [{"name": n, "query": f"SELECT a FROM t WHERE j = '{n}'"} for n in "ABC"]
    if modify:
        jobs[1]["query"] = "UPDATE t SET a = 1 WHERE j = 'B'"

    if outer == "after":
        calls = {"n": 0}

        def after(_ms, fn):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(err)
            stub.after_calls.append(fn)

        stub.root.after.side_effect = after
    elif outer == "status":
        real_status = stub.update_job_status

        def status(*args, **kwargs):
            if args[2] == "running":
                raise RuntimeError(err)
            return real_status(*args, **kwargs)

        stub.update_job_status = status
        stub.root.after.side_effect = lambda _ms, fn: fn()

    threads = tre._ThreadCapture()
    with mock.patch.object(app.threading, "Thread", side_effect=threads), \
            mock.patch.object(app, "messagebox") as mb, \
            mock.patch("time.sleep"):
        stub.run_selected_job(jobs_override=jobs)
        if swap:
            reconnect(stub)
        threads.run_all()
        tre.run_after_calls(stub)
    summary = stub.show_batch_summary.call_args
    return stub, {
        "inserted": list(stub.results_text.inserted),
        "run_log": [str(c) for c in stub._write_run_log.call_args_list],
        "summary": None if summary is None else (summary.args[0], summary.args[1],
                                                 summary.args[3]),
        "executed": executed,
        "messagebox": [str(c) for c in mb.mock_calls],
        "gets": stub.db_password.get_calls,
    }


# ---------------------------------------------------------------- AC-7
class RunJobTests(R14Case):
    def test_ac7_run_job_error_masked(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub, out = run_job(err)
                self.assert_no_leak("results_text", out["inserted"])
                self.assert_no_leak("run log", out["run_log"])
                lines = _err_lines(out["inserted"])
                self.assertEqual(len(lines), 1)
                self.assert_kept("Error line", lines[0], keep)
                self.assertIn("Status      : Fail\n", lines[0])
                self.assertEqual(len(out["popup"]), 1)
                self.assert_no_leak("popup Error", out["popup"][0])
                self.assert_kept("popup Error", out["popup"][0][0], keep)
                stub._finish_job_result_report.assert_called_with(1, 0, 1)
                self.assertEqual(out["gets"], 0)
                self.assert_no_leak("print", self.prints)


# ---------------------------------------------------------------- AC-8
class RunAllTests(R14Case):
    def test_ac8_failed_select_job_masked_and_counted(self):
        for label, err, keep in SECRET_ERRORS:
            with self.subTest(error=label):
                stub, out = run_all(err=err)
                self.assert_no_leak("results_text", out["inserted"])
                self.assert_no_leak("run log", out["run_log"])
                lines = _err_lines(out["inserted"])
                self.assertEqual(len(lines), 1)
                self.assert_kept("Error line", lines[0], keep)
                self.assertEqual(out["summary"], (2, 1, 3))
                self.assertEqual(len(out["executed"]), 3)
                self.assertEqual(out["gets"], 0)
                self.assert_no_leak("print", self.prints)

    def test_ac8_failed_modify_job_still_stops_the_run(self):
        for label, err, _keep in SECRET_ERRORS:
            with self.subTest(error=label):
                _stub, out = run_all(err=err, modify=True)
                self.assert_no_leak("results_text", out["inserted"])
                self.assertEqual(out["summary"], (1, 1, 3))
                self.assertEqual(len(out["executed"]), 2, "job C ran after a failed UPDATE")
                self.assertFalse(any("'C'" in q for q in out["executed"]))


# ---------------------------------------------------------------- AC-9
class RunAllBatchErrorTests(R14Case):
    def test_ac9_batch_error_masked_buttons_back(self):
        for outer in ("after", "status"):
            for label, err, keep in SECRET_ERRORS:
                with self.subTest(outer=outer, error=label):
                    stub, out = run_all(err=err, outer=outer)
                    self.assert_no_leak("results_text", out["inserted"])
                    self.assert_no_leak("run log", out["run_log"])
                    lines = [t for t in out["inserted"] if t.startswith("Error: ")]
                    self.assertEqual(len(lines), 1)
                    self.assert_kept("Error line", lines[0], keep)
                    self.assertIn("\n❌ BATCH EXECUTION ERROR\n", out["inserted"])
                    self.assertIsNone(out["summary"])
                    self.assertEqual(stub.run_all_btn.state, "normal")
                    self.assertEqual(stub.execute_btn.state, "normal")
                    self.assertEqual(stub.inspect_btn.state, "normal")
                    self.assertEqual(stub.save_job_btn.state, "normal")
                    self.assertFalse(stub._batch_running)


# ---------------------------------------------------------------- AC-13 / AC-14
class JobsPasswordSourceTests(R14Case):
    def test_ac13_run_job_reconnect_uses_start_password(self):
        stub, out = run_job(ERR3, swap=True)
        self.assertIs(stub.engine, E2)
        self.assert_no_leak("all", out["inserted"] + out["run_log"] + out["popup"][0]
                            + self.prints)
        self.assert_kept("Error line", _err_lines(out["inserted"])[0], ("bad password", "for u"))
        self.assertEqual(out["gets"], 0, "Password field read")

    def test_ac13_run_all_reconnect_uses_start_password(self):
        for outer in (None, "after", "status"):
            with self.subTest(outer=outer):
                stub, out = run_all(err=ERR3, swap=True, outer=outer)
                self.assertIs(stub.engine, E2)
                self.assert_no_leak("all", out["inserted"] + out["run_log"] + self.prints)
                self.assertTrue(any("bad password" in t for t in out["inserted"]))
                self.assertEqual(out["gets"], 0, "Password field read")

    def test_ac14_no_stored_password_pattern_only(self):
        for owner_case in ("none", "other_engine"):
            for label, err, keep in SECRET_ERRORS:
                with self.subTest(stored=owner_case, error=label):
                    kw = ({"password": None} if owner_case == "none"
                          else {"owner": E2})
                    _s, job_out = run_job(err, **kw)
                    _s, all_out = run_all(err=err, **kw)
                    job_line = _err_lines(job_out["inserted"])[0]
                    all_line = _err_lines(all_out["inserted"])[0]
                    if err is ERR3:  # known limit (R14-Q-3)
                        self.assert_same("popup", job_out["popup"][0][0], err)
                        self.assertTrue(job_line.endswith(f"Error       : {err}\n"))
                        self.assertTrue(all_line.endswith(f"Error       : {err}\n"))
                    else:
                        self.assert_no_leak("run job", job_out["inserted"] + job_out["popup"][0])
                        self.assert_no_leak("run all", all_out["inserted"])
                        self.assert_kept("run job", job_line, keep)
                    self.assertEqual(job_out["gets"] + all_out["gets"], 0)


# ---------------------------------------------------------------- AC-16 (P7-P9)
class JobsPlainErrorUnchangedTests(R14Case):
    """No password in the error: same text as before Round 14 (oracle = identity
    redact_secrets) and the exact pre-R14 strings for str-vs-exception."""

    def _twice(self, fn):
        actual = fn()
        with mock.patch.object(app, "redact_secrets", identity_redact):
            expected = fn()
        return normalize(actual), normalize(expected)

    def test_ac16_run_job(self):
        for label, err in PLAIN_ERRORS:
            with self.subTest(error=label):
                actual, expected = self._twice(lambda: run_job(err)[1])
                self.assertEqual(actual, expected)
                self.assertEqual(actual["popup"], [[err]])
                self.assertEqual(actual["finish"], [[1, 0, 1]])
                self.assertIn(
                    "Job Name    : J1\n"
                    "Query Time  : N.NN sec\n"
                    "Rows        : 0\n"
                    "Columns     : 0\n"
                    "Status      : Fail\n"
                    f"Error       : {err}\n",
                    actual["inserted"],
                )
                # popup DataFrame cell is a str equal to str(exception)
                self.assertEqual(actual["popup"][0][0], str(RuntimeError(err)))

    def test_ac16_run_all(self):
        for modify in (False, True):
            for label, err in PLAIN_ERRORS:
                with self.subTest(error=label, modify=modify):
                    actual, expected = self._twice(
                        lambda: run_all(err=err, modify=modify)[1])
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual["summary"], [1, 1, 3] if modify else [2, 1, 3])
                    lines = _err_lines(actual["inserted"])
                    self.assertEqual(len(lines), 1)
                    self.assertTrue(lines[0].endswith(f"Status      : Fail\nError       : {err}\n"))

    def test_ac16_batch_error(self):
        for outer in ("after", "status"):
            for label, err in PLAIN_ERRORS:
                with self.subTest(outer=outer, error=label):
                    actual, expected = self._twice(lambda: run_all(err=err, outer=outer)[1])
                    self.assertEqual(actual, expected)
                    self.assertIn(f"Error: {err}\n\n", actual["inserted"])


if __name__ == "__main__":
    unittest.main()
