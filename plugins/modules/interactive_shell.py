# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: interactive_shell
short_description: Run an interactive shell command on the Ansible controller
description:
  - Runs a shell command on the Ansible controller with access to the interactive terminal used to launch ansible-playbook.
  - This is implemented by the corresponding action plugin and does not execute a normal remote module.
options:
  cmd:
    description:
      - The command to run.
    type: str
  require_tty:
    description:
      - Require the parent ansible-playbook stdin to be attached to a TTY.
    type: bool
    default: true
  executable:
    description:
      - Shell executable to use.
    type: str
    default: /bin/sh
  chdir:
    description:
      - Change into this directory before running the command.
    type: path
  creates:
    description:
      - Skip the command if this path or glob already exists.
    type: path
  removes:
    description:
      - Skip the command if this path or glob does not exist.
    type: path
  stdin:
    description:
      - Data to send to stdin instead of attaching to the interactive terminal.
    type: str
  stdin_add_newline:
    description:
      - Append a newline to stdin data.
    type: bool
    default: true
  strip_empty_ends:
    description:
      - Strip trailing newline characters from stdout and stderr.
    type: bool
    default: true
author:
  - Zachariah Brown
'''

EXAMPLES = r'''
- name: Run an interactive controller-side command
  zbrown.paraphernalia.interactive_shell: ./some-command.sh

- name: Run with bash
  zbrown.paraphernalia.interactive_shell:
    cmd: ./some-command.sh
    executable: /bin/bash
'''

RETURN = r'''
cmd:
  description: The command executed.
  returned: always
  type: str
rc:
  description: The command return code.
  returned: always
  type: int
stdout:
  description: Command stdout.
  returned: always
  type: str
stderr:
  description: Command stderr.
  returned: always
  type: str
stdout_lines:
  description: Command stdout split into lines.
  returned: always
  type: list
  elements: str
stderr_lines:
  description: Command stderr split into lines.
  returned: always
  type: list
  elements: str
start:
  description: Command start time.
  returned: always
  type: str
end:
  description: Command end time.
  returned: always
  type: str
delta:
  description: Command runtime duration.
  returned: always
  type: str
'''
