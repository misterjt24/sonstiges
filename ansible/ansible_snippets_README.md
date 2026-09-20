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

---

## 6. Sonstiges

### 6.1. Hosts and Group Variables: Inside the Inventory
```python
vagrant1 ansible_host=127.0.0.1 ansible_port=2222
vagrant2 ansible_host=127.0.0.1 ansible_port=2200
vagrant3 ansible_host=127.0.0.1 ansible_port=2201

amsterdam.example.com color=red
seoul.example.com color=green

```
#### Specifying group variables in inventory
```python
[all:vars]
ntp_server=ntp.ubuntu.com

[production:vars]
db_primary_host=frankfurt.example.com
db_primary_port=5432
db_replica_host=london.example.com
```
##### Host and Group Variables: In Their Own Files
**For example**, if Lorin has a directory containing his playbooks at
*/home/lorin/playbooks/* with an inventory directory and hosts file at
*/home/lorin/inventory/hosts*, he should put variables for the
amsterdam.example.com host in the file
*/home/lorin/inventory/host_vars/amsterdam.example.com* and variables for
the production group in the file
*/home/lorin/inventory/group_vars/production*

*group_vars/production*
```python
---
db_primary_host: frankfurt.example.com
db_primary_port: 5432
db_replica_host: london.example.com
db_name: widget_production
db_user: widgetuser
```
If we choose YAML dictionaries, we access the variables like this:
```python
{{ db_primary_host }}
```

### 6.2. Variables and Facts
#### Defining Variables in Playbooks
```python
vars:
tls_dir: /etc/nginx/ssl/
```
You would replace the vars section with a
vars_files that looks like this:
```python
vars_files:
- nginx.yml
```
*The nginx.yml file would look like Example 4-1.
Example 4-1. nginx.yml*
```python
key_file: nginx.key
cert_file: nginx.crt
conf_file: /etc/nginx/sites-available/default
server_name: localhost
```
#### Viewing the Values of Variables
```python
- debug: var=myvarname
```
Accessing Dictionary Keys in a Variable
This rule applies to multiple dereferences, so all of the following are equivalent:
```python
result['stat']['mode']
result['stat'].mode
result.stat['mode']
result.stat.mode
```
### 6.3. Roles: Scaling Up Your Playbooks
[https://github.com/ansiblebook/ansiblebook/tree/3rd-edition/chapter08/playbooks](https://github.com/ansiblebook/ansiblebook/tree/3rd-edition/chapter08/playbooks)

#### Basic Structure of a Role
An Ansible role has a name, such as database. Files associated with the
database role go in the roles/database directory, which contains the
following files and directories:
*roles/database/tasks/main.yml*
The tasks directory has a main.yml file that serves as an entry-point for
the actions a role does.

*roles/database/files/*
Holds files and scripts to be uploaded to hosts

*roles/database/templates/*
Holds Jinja2 template files to be uploaded to hosts

*roles/database/handlers/main.yml*
The handlers directory has a main.yml file that has the actions that
respond to change notifications.

*roles/database/vars/main.yml*
Variables that shouldn’t be overridden

*roles/database/defaults/main.yml*
Default variables that can be overridden

*roles/database/meta/main.yml*
Information about the role

Each individual file is optional; if your role doesn’t have any handlers, for example, there’s no need to have an empty handlers/main.yml file and no
reason to commit such file.

##### Example
```python
- name: Deploy postgres on db
  hosts: db
  vars_files:
    - secrets.yml
  roles:
  - role: database
    tags: database
    database_name: "{{ mezzanine_proj_name }}"
    database_user: "{{ mezzanine_proj_name }}"
- name: Deploy mezzanine on web
  hosts: web
  vars_files:
    - secrets.yml
  roles:
    - role: mezzanine 
      tags: mezzanine
      database_host: "{{ hostvars.db.ansible_enp0s8.ipv4.address
    }}"
    - role: nginx
      tags: nginx
...
```
#### Creating Role Files and Directories with ansible-galaxy
```python
$ ansible-galaxy role init --init-path playbooks/roles web

playbooks
|___ roles
|___ web
|—— README.md
|—— defaults
| |___ main.yml
|—— files
|—— handlers
| |___ main.yml
|—— meta
| |___ main.yml
|—— tasks
| |___ main.yml
|—— templates
|—— tests
| |___ inventory
| |___ test.yml
|___ vars
|___ main.yml
```
### 6.4.  Lookups
```python
$ ansible-doc -t lookup -l
```
*key: "{{ lookup('file', '~/.ssh/id_ed25519.pub') }}"*

#### pipe
```python
- name: Add default public key for vagrant user
authorized_key:
user: vagrant
key: "{{ lookup('pipe', pubkey_cmd ) }}"
vars:
pubkey_cmd: 'ssh-keygen -y -f
~/.vagrant.d/insecure_private_key'
```
#### password
```python
- name: Create deploy user, save random password in pw.txt
become: true
user:
name: deploy
password: "{{ lookup('password', 'pw.txt
encrypt=sha512_crypt') }}"
```
#### template
*message.j2*
```python
This host runs {{ ansible_distribution }}
```

If we define a task like this:
```python
- name: Output message from template
debug:
msg: "{{ lookup('template', 'message.j2') }}"
then we’ll see output that looks like this:
TASK: [Output message from template]
******************************************
ok: [web] => {
"msg": "This host runs Ubuntu\n"
}
```
#### csvfile
The csvfile lookup reads an entry from a .csv file. Assume Lorin has a
.csv file that looks like Example 8-16.

*Example 8-16. users.csv*
```python
username,email
lorin,lorin@ansiblebook.com
john,john@example.com
sue,sue@example.org
```
If he wants to extract Sue’s email address by using the csvfile lookup
plugin, he would invoke the lookup plugin like this:
```python
lookup('csvfile', 'sue file=users.csv delimiter=, col=1')
```
The other arguments specify the name of the .csv file, the delimiter, and
which column should be returned. In our example, we want to do three
things:

Look in the file named users.csv and locate where the fields are
delimited by commas
Look up the row where the value in the first column is sue
Return the value in the second column (column 1, indexed by 0).

This evaluates to sue@example.org.

If the username we want to look up is stored in a variable named
*username*, we could construct the argument string by using the + sign to
concatenate the username string with the rest of the argument string:
```python
lookup('csvfile', username + ' file=users.csv delimiter=, col=1')
```