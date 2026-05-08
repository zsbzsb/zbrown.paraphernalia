# zbrown.paraphernalia

Various Ansible plugins and utilities, including `interactive_shell`.

# Installation

Add the collection directly to your `requirements.yml`:

```yaml
---
collections:
  - name: https://github.com/zsbzsb/zbrown.paraphernalia.git
    type: git
    version: main
```

Then install it with:

```bash
ansible-galaxy collection install -r requirements.yml
```

# Compatibility

- Ansible 2.19 tested - but it should work on older Ansible versions as well
- `interactive_shell` requires a Linux/WSL controller host

# Plugins

## `zbrown.paraphernalia.interactive_shell`

`interactive_shell` is a controller-side Ansible action plugin that runs shell commands with access to the interactive terminal used to launch `ansible-playbook`.

It is based on the same general arguments, parameters, and result values as Ansible’s built-in `shell`/`command`-style modules, so it can often be used as a drop-in replacement when you need the command to interact with the user through the terminal.

### Parameters

The plugin adds one extra parameter:

| Parameter     | Default | Description                                                                                                                                                                                                                                                                                                |
| ------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `require_tty` | `true`  | Requires the parent process's stdin to be attached to a terminal. This was added as a safeguard to fail fast when `interactive_shell` is accidentally invoked from a non-interactive environment, such as CI, instead of allowing the playbook run to hang while waiting for input that can never arrive. |

### Recommended usage

Because `interactive_shell` works by attaching to the controller process's terminal, it should be run on the Ansible controller host.

Using both `hosts: localhost` and `connection: local` is strongly recommended:

```yaml
- hosts: localhost
  connection: local
  gather_facts: false

  tasks:
    - name: Run an interactive controller-side command
      zbrown.paraphernalia.interactive_shell: ./some-command.sh
```

This plugin is intended for interactive terminal usage. It generally should not be used in CI environments, automation runners, scheduled jobs, or other non-interactive contexts where Ansible does not have access to an interactive terminal stdin.

### How it works

`interactive_shell` assumes it is running as an Ansible worker process whose parent process is the `ansible-playbook` process running inside an interactive terminal.

It uses the parent process's file descriptors:

```text
0 = stdin
1 = stdout
2 = stderr
```

The plugin does the following:

1. Opens the parent process's file descriptors for use as stdio pipes.
2. Pipes the terminal stdin directly to the child shell process.
3. Captures the child process stdout and stderr.
4. Tees stdout and stderr back to the terminal's stdout/stderr so output is displayed live while also capturing it to be available in the task result.

This allows the child command to behave like an interactive shell command while still returning normal Ansible result values such as `rc`, `stdout`, `stderr`, `stdout_lines`, `stderr_lines`, `changed`, `failed`, `start`, `end`, and `delta`.

### Basic example

```yaml
- name: Run an interactive controller-side command
  zbrown.paraphernalia.interactive_shell: ./some-command.sh
```

### Example: better interactive pause

This can be used as a better-looking version of `pause` when you want to show a prominent message and simply wait for the user to press Enter.

```yaml
- name: Wait for the user to be finished
  zbrown.paraphernalia.interactive_shell: |
    echo -e "\n"
    printf -v line "%${COLUMNS:-$(tput cols)}s" && echo -e "\e[31m${line// /!}\e[0m"
    echo '{{ wait_prompt | trim }}'
    printf -v line "%${COLUMNS:-$(tput cols)}s" && echo -e "\e[31m${line// /!}\e[0m"
    read -rs
    echo -e "\n"
  args:
    executable: /bin/bash
```

Example output:

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
SSH DB tunnel is now open on foobar@localhost:5433. Press [ENTER] to close it...
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

### Example: prompt the user to select from a list

This example lets the user select a host from a list of choices.

```yaml
- name: Pick a {{ host_description }} host
  zbrown.paraphernalia.interactive_shell:
    cmd: |
      hosts=({{ host_list | map('quote') | join(' ') }})

      echo "Available {{ host_description }} hosts:"
      echo

      select chosen_host in "${hosts[@]}"; do
        if [[ -n "${chosen_host:-}" ]]; then
          echo
          printf '%s\n' "SELECTED_HOST:${chosen_host}"
          exit 0
        fi

        echo "Invalid selection. Try again."
      done
  args:
    executable: /bin/bash
  register: selected_host_result
```

Example output:

```text
TASK [Pick a server host] ****************************************************
Available app server hosts:

1) server-instance-joe-live
2) server-instance-steve-live
#? 2

SELECTED_HOST:server-instance-steve-live
```

The selected value can then be parsed from `selected_host_result.stdout_lines`.

### Notes

Only use `interactive_shell` when a task truly requires direct interaction with the user’s terminal. That should usually be rare.

For normal shell commands, automation steps, scripts, and any task that can run without user input, always prefer `ansible.builtin.shell` or `ansible.builtin.command`.

### Philosophy

Ansible is intentionally designed around non-interactive, repeatable automation, and `interactive_shell` goes against that core philosophy in some ways. This plugin is not intended to replace normal Ansible automation patterns or to encourage interactive playbooks where fully automated tasks would be better.

That said, there are limited situations where waiting for user interaction is useful. For example, a playbook might simplify opening an SSH tunnel for local debugging, display the connection details, and then wait for the user to press Enter before closing the tunnel. Ansible itself includes the `pause` module, which reflects that even in a primarily non-interactive automation tool, there are occasional valid cases for controlled user interaction.

Use this plugin for those rare cases where direct interaction with the user’s terminal is the purpose of the task, not as a general replacement for `ansible.builtin.shell`, `ansible.builtin.command`, or proper non-interactive automation.
