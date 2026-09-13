# Ansible Error Handling & Playbook Tasks Examples

This document contains practical examples of error handling, assertions, failure triggers, and logging techniques in Ansible playbooks.

---

## 1. Error Handling (`ignore_errors` & `failed_when`)

### Ignore Errors
Allows a playbook to continue even if a specific task fails.

```yaml
- name: Execute command, but ignore errors
  ansible.builtin.command: /usr/bin/faulty_command
  ignore_errors: true
```

### Custom Failure Condition (`failed_when`)
Marks a task as failed based on custom criteria (e.g., matching a text pattern in standard output).

```yaml
- name: Fail task if specific text is found in log output
  ansible.builtin.shell: cat /etc/app/status.log
  register: status_output
  failed_when: "'FATAL' in status_output.stdout"
```

---

## 2. Asserts (`ansible.builtin.assert`)

Validates conditions and stops execution with custom failure/success messages if criteria are not met.

```yaml
- name: Check if sufficient memory is available
  ansible.builtin.assert:
    that:
      - ansible_memtotal_mb >= 2048
    fail_msg: "Insufficient RAM! At least 2 GB required (found: {{ ansible_memtotal_mb }} MB)."
    success_msg: "Memory check passed."
```

---

## 3. Forcing Failures (`ansible.builtin.fail`)

Explicitly stops playbook execution under specific conditions.

```yaml
- name: Abort playbook if environment is not production
  ansible.builtin.fail:
    msg: "Security abort: This playbook is not allowed to run in the {{ target_env }} environment!"
  when: target_env != 'production'
```

---

## 4. Writing `ansible_failed_result.msg` to a Logfile

Using `block` and `rescue` to catch failures and log the precise error message returned by Ansible.

```yaml
- name: Execute critical process and log failure
  block:
    - name: Update important service
      ansible.builtin.package:
        name: critical-service
        state: latest
  rescue:
    - name: Write error message to local log file
      ansible.builtin.lineinfile:
        path: /var/log/ansible_errors.log
        line: "{{ ansible_date_time.iso8601 }} - Error on {{ inventory_hostname }}: {{ ansible_failed_result.msg | default('Unknown error') }}"
        create: true
      delegate_to: localhost
```

---

## 5. Capturing and Displaying `ansible_failed_result.msg`

Using `rescue` to display specific error details captured during a failure.

```yaml
- name: Run command and capture failure message in a rescue block
  block:
    - name: Execute a command that may fail
      ansible.builtin.command: systemctl restart non_existent_service
  rescue:
    - name: Output specific error message provided by ansible_failed_result
      ansible.builtin.debug:
        msg: >-
          The task failed on {{ inventory_hostname }}.
          Error details: {{ ansible_failed_result.msg }}
```
