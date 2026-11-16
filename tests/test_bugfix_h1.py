"""R5-T8: Tables worker snapshots Tk credentials and cleans up temporary engines."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database_connect_gui as app  # noqa: E402

GUI = app.DatabaseConnectorGUI


class _Variable:
    def __init__(self, value, name, events):
        self.value = value
        self.name = name
        self.events = events
        self.forbid_get = False

    def get(self):
        if self.forbid_get:
            raise AssertionError(f"worker read Tk variable {self.name}")
        self.events.append(self.name)
        return self.value


class _Thread:
    def __init__(self, target, args=(), daemon=None, events=None):
        self.target = target
        self.args = args
        self.events = events

    def start(self):
        if self.events is not None:
            self.events.append("start")

    def run(self):
        self.target(*self.args)


def _make_stub(db_type="MySQL"):
    events = []
    stub = GUI.__new__(GUI)
    stub._block_if_busy = mock.Mock(return_value=False)
    stub._capture_run_target = mock.Mock(
        return_value=app.RunTarget(mock.MagicMock(name="main_engine"), None)
    )
    stub.db_type = _Variable(db_type, "db_type", events)
    stub.db_name = _Variable("", "db_name", events)
    stub.db_user = _Variable("user_snapshot", "db_user", events)
    stub.db_password = _Variable("password_snapshot", "db_password", events)
    stub.db_host = _Variable("host_snapshot", "db_host", events)
    stub.db_port = _Variable("1433", "db_port", events)
    stub.results_text = mock.Mock()
    stub.inspect_btn = mock.Mock()
    stub.root = mock.Mock()
    stub._create_list_tables_loading_dialog = mock.Mock(return_value=mock.Mock())
    return stub, events


class ListTablesWorkerTests(unittest.TestCase):
    def _start_worker(self, stub, events):
        threads = []

        def create_thread(target, args=(), daemon=None):
            thread = _Thread(target, args, daemon, events)
            threads.append(thread)
            return thread

        with mock.patch.object(app.threading, "Thread", side_effect=create_thread), \
                mock.patch.object(GUI, "_block_if_profile_mismatch", return_value=False):
            stub.list_tables()
        self.assertEqual(len(threads), 1)
        return threads[0]

    def _database_list_engine(self):
        engine = mock.MagicMock(name="main_engine")
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value = [("db_one",)]
        return engine

    def test_credentials_are_read_before_start_and_worker_uses_snapshot(self):
        stub, events = _make_stub()
        stub.engine = self._database_list_engine()
        stub._capture_run_target.return_value = app.RunTarget(stub.engine, None)
        temp_engine = mock.MagicMock(name="temp_engine")
        inspector = mock.Mock()
        inspector.get_schema_names.return_value = []
        stub.get_connection_string = mock.Mock(return_value="connection-string")
        stub.get_connect_args = mock.Mock(return_value={})

        thread = self._start_worker(stub, events)
        self.assertEqual(
            events,
            ["db_type", "db_name", "db_user", "db_password", "db_host", "db_port", "start"],
        )
        self.assertEqual(thread.args, ((
            "user_snapshot", "password_snapshot", "host_snapshot", "1433"
        ),))

        for variable in (stub.db_user, stub.db_password, stub.db_host, stub.db_port):
            variable.value = "changed_after_start"
            variable.forbid_get = True

        with mock.patch.object(app, "create_engine", return_value=temp_engine) as create_engine, \
                mock.patch.object(app, "inspect", return_value=inspector), \
                mock.patch("builtins.print"), mock.patch("traceback.print_exc"):
            thread.run()

        stub.get_connection_string.assert_called_once_with(
            "MySQL", "user_snapshot", "password_snapshot", "host_snapshot", "1433", "db_one"
        )
        create_engine.assert_called_once()
        temp_engine.dispose.assert_called_once_with()

    def test_temporary_engine_is_disposed_when_schema_discovery_raises(self):
        stub, events = _make_stub()
        stub.engine = self._database_list_engine()
        stub._capture_run_target.return_value = app.RunTarget(stub.engine, None)
        temp_engine = mock.MagicMock(name="temp_engine")
        inspector = mock.Mock()
        inspector.get_schema_names.side_effect = RuntimeError("schema discovery failed")

        thread = self._start_worker(stub, events)
        with mock.patch.object(app, "create_engine", return_value=temp_engine), \
                mock.patch.object(app, "inspect", return_value=inspector), \
                mock.patch("builtins.print"), mock.patch("traceback.print_exc"):
            thread.run()

        temp_engine.dispose.assert_called_once_with()

    def test_sql_server_schema_is_bound_as_a_parameter(self):
        stub, events = _make_stub("Microsoft SQL Server")
        stub.engine = self._database_list_engine()
        stub._capture_run_target.return_value = app.RunTarget(stub.engine, None)
        temp_engine = mock.MagicMock(name="temp_engine")
        temp_connection = temp_engine.connect.return_value.__enter__.return_value
        temp_connection.execute.return_value = [("table_one",)]
        inspector = mock.Mock()
        inspector.get_schema_names.return_value = ["customer schema"]

        thread = self._start_worker(stub, events)
        with mock.patch.object(app, "create_engine", return_value=temp_engine), \
                mock.patch.object(app, "inspect", return_value=inspector), \
                mock.patch("builtins.print"), mock.patch("traceback.print_exc"):
            thread.run()

        query, parameters = temp_connection.execute.call_args.args
        self.assertIn("WHERE TABLE_SCHEMA = :schema", str(query))
        self.assertNotIn("customer schema", str(query))
        self.assertEqual(parameters, {"schema": "customer schema"})
        temp_engine.dispose.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()