"""runs/server-up.sh: the wait for a test server a script has just started. It ends early on the server's ready line,
gives up when the server's process has ended, and when the server is not up in time stops the process it was given,
by that ID only, so that no leftover holds the relay's port. A stand-in server (a `timeout` of a shell that writes
the server's ready line, or does not) and a stand-in curl that never gets an answer: no server is started and no
port is asked."""
import os
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "runs", "server-up.sh"))
READY = "test: coordinator on TCP 47810 (WebSocket /ws), relay on UDP 47811. Ctrl+C stops."


class ServerUp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.mkdir(bin_dir)
        with open(os.path.join(bin_dir, "curl"), "w") as f:
            f.write("#!/bin/sh\nexit 7\n")   # (curl's "could not connect")
        os.chmod(os.path.join(bin_dir, "curl"), 0o755)
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        self.log = os.path.join(self.tmp.name, "server.log")

    def server(self, shell):
        """A stand-in server: `timeout` of a shell, its command line naming Online.Server as the real one's does."""
        log = open(self.log, "w")
        self.addCleanup(log.close)
        p = subprocess.Popen(["timeout", "60", "sh", "-c", shell, "Online.Server.dll"], stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        return p

    def wait(self, p, **env):
        started = time.monotonic()
        done = subprocess.run(["bash", SCRIPT, "127.0.0.1", self.log, str(p.pid)], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=60)
        return done, time.monotonic() - started

    def test_the_ready_line_ends_the_wait(self):
        p = self.server(f"sleep 1; echo '{READY}'; sleep 30")
        done, took = self.wait(p, UP_SECONDS="20")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(took, 10)
        self.assertIsNone(p.poll(), "a server that is up is left running")

    def test_a_server_not_up_in_time_is_stopped_by_its_id(self):
        p = self.server("sleep 50")
        done, _ = self.wait(p, UP_SECONDS="2")
        self.assertEqual(done.returncode, 1)
        self.assertIn("was not up within 2 s", done.stderr)
        self.assertIsNotNone(p.poll(), "the server it was given is stopped")

    def test_a_server_that_ended_is_not_waited_for(self):
        p = self.server("echo 'Address already in use'; exit 1")
        p.wait()
        done, took = self.wait(p, UP_SECONDS="20")
        self.assertEqual(done.returncode, 1)
        self.assertIn("ended before it was up", done.stderr)
        self.assertLess(took, 10)


if __name__ == "__main__":
    unittest.main()
