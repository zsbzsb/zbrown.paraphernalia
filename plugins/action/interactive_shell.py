# -*- coding: utf-8 -*-

# Copyright (c) 2026 Zachariah Brown
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import datetime
import glob
import locale
import os
import subprocess
import threading

from ansible.errors import AnsibleActionFail
from ansible.module_utils.common.text.converters import to_text
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    """
    Controller-side interactive shell.

    Similar task shape to ansible.builtin.shell, but runs on the Ansible
    controller and allows the child command to read directly from the same
    stdin as ansible-playbook.

    stdout/stderr are captured and also immediately written back to the
    controller terminal.
    """

    supports_raw_params = True

    TRANSFERS_FILES = False
    BYPASS_HOST_LOOP = True

    def run(self, tmp=None, task_vars=None):
        result = super(ActionModule, self).run(tmp, task_vars)

        result.update(
            changed=False,
            rc=None,
            cmd=None,
            stdout="",
            stderr="",
            stdout_lines=[],
            stderr_lines=[],
            msg="",
            start=None,
            end=None,
            delta=None,
        )

        if getattr(self._play_context, "become", False):
            result.update(
                failed=True,
                msg=(
                    "interactive_shell runs on the Ansible controller and does not support "
                    "Ansible become/become_user. Use sudo inside the command explicitly if "
                    "you need controller-side privilege escalation."
                ),
            )
            return result

        args = self._task.args.copy()

        # Match ansible.builtin.shell: shell owns $VAR expansion, not Ansible.
        if "expand_argument_vars" in args:
            raise AnsibleActionFail(
                "Unsupported parameter for interactive_shell: expand_argument_vars"
            )

        raw_params = args.pop("_raw_params", None)
        cmd = args.pop("cmd", None)

        if raw_params is not None and cmd is not None:
            result.update(
                failed=True,
                msg="interactive_shell received both free-form command and cmd; only one is allowed",
            )
            return result

        cmd = raw_params if raw_params is not None else cmd

        require_tty = args.pop("require_tty", True)
        executable = args.pop("executable", None) or "/bin/sh"
        chdir = args.pop("chdir", None)
        creates = args.pop("creates", None)
        removes = args.pop("removes", None)
        stdin = args.pop("stdin", None)
        stdin_add_newline = args.pop("stdin_add_newline", True)
        strip_empty_ends = args.pop("strip_empty_ends", True)

        if args:
            result.update(
                failed=True,
                msg="Unsupported parameter(s) for interactive_shell: {}".format(
                    ", ".join(sorted(args.keys()))
                ),
            )
            return result

        if not cmd:
            result.update(
                failed=True,
                msg="interactive_shell requires a free-form command or cmd",
            )
            return result

        cmd = to_text(cmd)
        executable = to_text(executable)

        result["cmd"] = cmd

        def glob_in_chdir(pattern):
            if not pattern:
                return []

            pattern = to_text(pattern)

            if chdir and not os.path.isabs(pattern):
                pattern = os.path.join(to_text(chdir), pattern)

            return glob.glob(pattern)

        check_mode = bool(getattr(self._task, "check_mode", False))
        shoulda = "Would" if check_mode else "Did"

        if creates and glob_in_chdir(creates):
            stdout = "skipped, since {} exists".format(creates)

            result.update(
                rc=0,
                msg="{} not run command since '{}' exists".format(shoulda, creates),
                stdout=stdout,
                stdout_lines=stdout.splitlines(),
                changed=False,
            )

            return result

        if removes and not glob_in_chdir(removes):
            stdout = "skipped, since {} does not exist".format(removes)

            result.update(
                rc=0,
                msg="{} not run command since '{}' does not exist".format(shoulda, removes),
                stdout=stdout,
                stdout_lines=stdout.splitlines(),
                changed=False,
            )

            return result

        if check_mode:
            result.update(
                rc=0,
                msg="Command would have run if not in check mode",
                changed=True,
            )

            if creates is None and removes is None:
                result.update(
                    skipped=True,
                    changed=False,
                )

            return result

        stdin_bytes = None

        if stdin is not None:
            stdin_text = to_text(stdin)

            if stdin_add_newline:
                stdin_text += "\n"

            stdin_bytes = stdin_text.encode("utf-8")

        start = datetime.datetime.now()
        result["start"] = to_text(start)

        try:
            rc, stdout_bytes, stderr_bytes = self._run_interactive_shell(
                require_tty=require_tty,
                executable=executable,
                cmd=cmd,
                chdir=to_text(chdir) if chdir else None,
                stdin_bytes=stdin_bytes,
            )

        except Exception as exc:
            end = datetime.datetime.now()

            result.update(
                failed=True,
                changed=True,
                rc=1,
                msg=to_text(exc),
                end=to_text(end),
                delta=to_text(end - start),
                stderr=to_text(exc),
                stderr_lines=to_text(exc).splitlines(),
            )

            return result

        end = datetime.datetime.now()

        encoding = locale.getpreferredencoding(False) or "utf-8"

        stdout = stdout_bytes.decode(
            encoding,
            errors="replace",
        )

        stderr = stderr_bytes.decode(
            encoding,
            errors="replace",
        )

        if strip_empty_ends:
            stdout = stdout.rstrip("\r\n")
            stderr = stderr.rstrip("\r\n")

        result.update(
            changed=True,
            rc=rc,
            stdout=stdout,
            stderr=stderr,
            stdout_lines=stdout.splitlines(),
            stderr_lines=stderr.splitlines(),
            end=to_text(end),
            delta=to_text(end - start),
        )

        if rc != 0:
            result.update(
                failed=True,
                msg="non-zero return code",
            )

        return result

    def _run_interactive_shell(self, require_tty, executable, cmd, chdir=None, stdin_bytes=None):
        stdout_chunks = []
        stderr_chunks = []
        reader_errors = []

        parent_pid = os.getppid()

        parent_stdin_fd = None
        parent_stdout_fd = None
        parent_stderr_fd = None

        try:
            # Replace sys.stdin with the parent ansible-playbook process's fd 0.
            if stdin_bytes is None:
                parent_stdin_fd = self._open_parent_fd(parent_pid, 0, os.O_RDONLY)

                if require_tty and not os.isatty(parent_stdin_fd):
                    raise RuntimeError("Parent stdin is not a TTY; interactive_shell cannot read interactively")

                child_stdin = parent_stdin_fd
            else:
                child_stdin = subprocess.PIPE

            # Replace sys.stdout/sys.stderr with the parent ansible-playbook
            # process's fd 1/fd 2.
            parent_stdout_fd = self._open_parent_fd(parent_pid, 1, os.O_WRONLY)
            parent_stderr_fd = self._open_parent_fd(parent_pid, 2, os.O_WRONLY)

            proc = subprocess.Popen(
                [executable, "-c", cmd],
                stdin=child_stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=chdir,
                env=os.environ.copy(),
                bufsize=0,
            )

            stdout_thread = threading.Thread(
                target=self._tee_pipe,
                args=(proc.stdout, parent_stdout_fd, stdout_chunks, reader_errors),
                daemon=True,
            )

            stderr_thread = threading.Thread(
                target=self._tee_pipe,
                args=(proc.stderr, parent_stderr_fd, stderr_chunks, reader_errors),
                daemon=True,
            )

            stdout_thread.start()
            stderr_thread.start()

            if stdin_bytes is not None:
                try:
                    proc.stdin.write(stdin_bytes)
                    proc.stdin.close()
                except BrokenPipeError:
                    pass

            rc = proc.wait()

            stdout_thread.join()
            stderr_thread.join()

            if reader_errors:
                raise RuntimeError("; ".join(reader_errors))

            return rc, b"".join(stdout_chunks), b"".join(stderr_chunks)

        finally:
            for fd in (parent_stdin_fd, parent_stdout_fd, parent_stderr_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def _open_parent_fd(self, parent_pid, fd_number, flags):
        proc_fd_path = "/proc/{}/fd/{}".format(parent_pid, fd_number)
        open_flags = flags | getattr(os, "O_NOCTTY", 0)

        try:
            return os.open(proc_fd_path, open_flags)
        except OSError as exc:
            raise RuntimeError(
                "Could not open parent process fd {} at {}: {}".format(
                    fd_number,
                    proc_fd_path,
                    to_text(exc),
                )
            )

    def _tee_pipe(self, pipe, terminal_fd, capture_chunks, reader_errors):
        try:
            pipe_fd = pipe.fileno()

            while True:
                data = os.read(pipe_fd, 4096)

                if not data:
                    break

                capture_chunks.append(data)
                os.write(terminal_fd, data)

        except Exception as exc:
            reader_errors.append(to_text(exc))
