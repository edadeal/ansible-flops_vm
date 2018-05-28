#!/usr/bin/python
# encoding: utf-8
import time

import requests
from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = """
---
module: flops_vm
short_description: Manage flops.ru via api
description:
  - "The M(flops_vm) module for manage flops via api"

options:
  credentials:
    description:
      - API key, client_id, tenant_id (id of project), public_key_names, for Flops
    required: true
    type: dict

  name:
    description:
      - Server name in flops
    required: true
    type: str
    
  state:
    description:
      - For delete vm
    required: false
    type: str
    default: present
    choices: ['present', 'absent']
    
  memory:
    description:
      - Server ram memory in gb. Max is 16.0
    required: false
    type: float
    default: 0.5
    
  disk:
    description:
      - HDD size in gb. Max is 512.
    required: false
    type: int
    default: 8
    
  cpu:
    description:
      - Number of cores. Max is 12.
    required: false
    type: int
    default: 1
    
  ip_count:
    description:
      - Number of public ip. Max is 2.
    required: false
    type: int
    default: 0
    
author:
  - Pavel Sofrony (pavel@sofrony.ru)
"""

EXAMPLES = '''
# Example from Ansible Playbooks
---

- name: create test vm
  gather_facts: no
  become: False
  hosts: localhost
  tasks:
    - name: create vm
      flops_vm:
        credentials: "{{ flops_credentials }}"
        name: create-via-api
      register: dict_vm
    - name: msg
      debug:
        msg: "{{ dict_vm.msg }}"
    - name: change vm properties
      flops_vm:
        credentials: "{{ flops_credentials }}"
        name: create-via-api
        memory: 1
        disk: 20
        cpu: 2
        ip_count: 1
      register: dict_vm
    - name: msg
      debug:
        msg: "{{ dict_vm.msg }}"
    - name: rm vm
      flops_vm:
        credentials: "{{ flops_credentials }}"
        name: create-via-api
        state: absent
'''


class DotDict(dict):
    __getattr__ = dict.__getitem__


module = AnsibleModule(
    argument_spec=dict(
        credentials=dict(required=True, type="dict", no_log=True),
        name=dict(type="str", required=True),
        state=dict(
            default="present",
            choices=['present', 'absent']),
        memory=dict(type="float", default=0.5),
        disk=dict(type="int", default=8),
        cpu=dict(type="int", default=1),
        ip_count=dict(type="int", default=0),
    ),
    supports_check_mode=True
)


def gb2mb(gb):
    return int(gb * 1024)


def get_read_params(params):
    return {
        'apiKey': params.credentials['flops_api_key'],
        'clientId': params.credentials['flops_client_id'],
    }


def get_edit_params(params):
    tenant_id = params.credentials['flops_tenant_id']
    edit_params = get_read_params(params)
    edit_params.update({'tenantId': tenant_id})
    return edit_params


def get_create_params(params):
    default_distro = {
        "id": 316,
        "name": "UBUNTU",
        "description": "Ubuntu 16.04 x64",
        "bitness": 64
    }
    custom_vm_tariff_id = 1

    return {
        'apiKey': params.credentials['flops_api_key'],
        'publicKeyIds': find_public_keys(get_public_keys_info(), params.credentials['flops_public_key_names']),
        'clientId': params.credentials['flops_client_id'],
        'name': params.name,
        'memory': gb2mb(params.memory),
        'disk': gb2mb(params.disk),
        'cpu': params.cpu,
        'ipCount': params.ip_count,
        'tenantId': params.credentials['flops_tenant_id'],
        'distributionId': default_distro.get("id"),
        'tariffId': custom_vm_tariff_id,
    }


def get_all_vm_data():
    """
    :return: json
    """
    resp = requests.get('https://api.flops.ru/api/v1/vm/',
                        params=get_read_params(module.params))
    res = resp.json()
    return res if res['status'] == 'OK' else res['errorMessage']


def get_public_keys_info():
    """
    :return: json
    """
    resp = requests.get('https://api.flops.ru/api/v1/pubkeys/',
                        params=get_read_params(module.params))
    res = resp.json()
    return res['result'] if res['status'] == 'OK' else res['errorMessage']


def find_public_keys(keys, names):
    """
    :param keys: dict
    :param names: list
    :return: list
    """
    list_key_id = []
    for key_dict in keys:
        if key_dict['name'] in names:
            list_key_id.append(key_dict['id'])
    return list_key_id


def force_get_ip(name):
    """
    :param name: str
    :return: list
    """
    all_vm_data = get_all_vm_data()
    for vm in all_vm_data['result']:
        if vm['name'] == name:
            ip_list = vm['ipAddresses']
            return ip_list


def get_operation_info(id):
    """
    :param id: int
    :return: dict
    """
    resp = requests.get('https://api.flops.ru/api/v1/operation/' + str(id),
                        params=get_read_params(module.params))
    res = resp.json()
    if res['status'] == 'OK':
        return res


def wait_async_resp(resp):
    info = None
    if resp['status'] == 'OK':
        while True:
            info = get_operation_info(resp['operationId'])
            if info['result']['status'] != 'PENDING':
                break
            time.sleep(5)
    else:
        raise ValueError(resp['errorMessage'])
    return int(info['result']['vmId'])


def create_vm(vmid):
    resp = requests.get('https://api.flops.ru/api/v1/vm/' + str(vmid),
                        params=get_read_params(module.params))
    res = resp.json()
    if res['status'] == 'OK':
        public_ip = res['result']['ipAddresses']
        private_ip = res['result']['privateIpAddress']
        vm_name = res['result']['name']
        return {'ip_count': public_ip, 'privateIpAddress': private_ip, 'name': vm_name}


def edit_cpu(vm):
    cpu = module.params.cpu
    cpu_on_vm = vm['cpu']
    if cpu != cpu_on_vm:
        params = get_edit_params(module.params)
        params.update({'cpu': cpu})
        resp = requests.get('https://api.flops.ru/api/v1/vm/%i/cpu_change/' % vm['id'],
                            params=params)
        res = resp.json()
        return (
            {'cpu': cpu, 'changed': True}
            if res['status'] == 'OK' else
            {'cpu': res['errorMessage'], 'changed': False}
        )
    else:
        return {'cpu': cpu, 'changed': False}


def edit_disk(vm):
    disk = gb2mb(module.params.disk)
    disk_on_vm = vm['disk']
    if disk != disk_on_vm:
        params = get_edit_params(module.params)
        params.update({'disk': disk, 'allowMemoryChange': 'true'})
        resp = requests.get('https://api.flops.ru/api/v1/vm/%i/disk_change/' % vm['id'],
                            params=params)
        res = resp.json()
        return (
            {'disk': disk, 'changed': True}
            if res['status'] == 'OK' else
            {'disk': res['errorMessage'], 'changed': False}
        )
    else:
        return {'disk': disk, 'changed': False}


def edit_memory(vm):
    memory = gb2mb(module.params.memory)
    memory_on_vm = vm['memory']
    params = get_edit_params(module.params)
    if memory != memory_on_vm:
        can_be_restarted = memory < memory_on_vm

        params.update({'memory': memory})
        if can_be_restarted:
            params.update({'allowRestart': 'true'})

        resp = requests.get('https://api.flops.ru/api/v1/vm/%i/memory_change/' % vm['id'],
                            params=params)
        res = resp.json()
        if can_be_restarted:
            time.sleep(5)
        return (
            {'memory': memory, 'changed': True}
            if res['status'] == 'OK' else
            {'memory': res['errorMessage'], 'changed': False}
        )
    else:
        return {'memory': memory, 'changed': False}


def edit_ip_numbers(vm):
    list_ip = vm['ipAddresses']
    ip_count_on_vm = len(vm['ipAddresses'])
    params = get_edit_params(module.params)

    ip_count = module.params.ip_count
    if ip_count > ip_count_on_vm:
        run_times = int(ip_count) - ip_count_on_vm
        for i in range(run_times):
            ip_resp = requests.get('https://api.flops.ru/api/v1/vm/%i/ip_add/' % vm['id'],
                                   params=params)
            res = ip_resp.json()
            return (
                {'ip_count': force_get_ip(vm['name']), 'changed': True}
                if res['status'] == 'OK' else
                {'ip_count': res['errorMessage'], 'changed': False}
            )
    elif ip_count < ip_count_on_vm:
        run_times = ip_count_on_vm - int(ip_count)
        for i in range(run_times):
            ip = list_ip[i]
            params.update({'ip': ip})
            ip_resp = requests.get('https://api.flops.ru/api/v1/vm/%i/ip_delete/' % vm['id'],
                                   params=params)
            res = ip_resp.json()
            return (
                {'ip_count': force_get_ip(vm['name']), 'changed': True}
                if res['status'] == 'OK' else
                {'ip_count': res['errorMessage'], 'changed': False}
            )

    return {'ip_count': force_get_ip(vm['name']), 'changed': False}


def rm_vm(id):
    """
    :param id: get int of vm id
    :return: str status
    """
    resp = requests.get('https://api.flops.ru/api/v1/vm/%i/delete/' % id,
                        params=get_edit_params(module.params))
    res = resp.json()
    return res['status'] if res['status'] == 'OK' else res['errorMessage']


def find_vm(vms, name):
    for vm in vms:
        if vm['name'] == name:
            return vm
    else:
        return None


def main():
    module.params = DotDict(module.params)
    name = module.params.name
    state = module.params.state
    changed_status = False
    fail_status = False
    try:
        all_vm_info = get_all_vm_data()
        vm = find_vm(all_vm_info['result'], name)
        if state == 'present':
            if vm:
                cpu = edit_cpu(vm)
                disk = edit_disk(vm)
                memory = edit_memory(vm)
                ip_count = edit_ip_numbers(vm)
                changed_status = any((
                    cpu['changed'],
                    disk['changed'],
                    memory['changed'],
                    ip_count['changed']
                ))
                fail_status = not all((
                    isinstance(cpu['cpu'], int),
                    isinstance(disk['disk'], int),
                    isinstance(memory['memory'], int),
                    isinstance(ip_count['ip_count'], list)
                ))
                result = {'state': 'exist',
                          'cpu': cpu['cpu'],
                          'disk': disk['disk'],
                          'memory': memory['memory'],
                          'ip_count': ip_count['ip_count'],
                          'privateIpAddress': vm['privateIpAddress'],
                          'name': vm['name']
                          }
            else:
                resp = requests.get('https://api.flops.ru/api/v1/vm/install',
                                    params=get_create_params(module.params))
                id = wait_async_resp(resp.json())
                result = create_vm(id)
                result.update({'state': 'created'})
                changed_status = True
        elif state == 'absent':
            if vm:
                status = rm_vm(vm['id'])
                if status == 'OK':
                    result = {'state': 'removed'}
                    changed_status = True
                else:
                    result = {'state': status}
            else:
                raise ValueError("Can't find vm with this name")
        else:
            raise ValueError('Invalid state')
    except Exception as e:
        return module.fail_json(msg=repr(e))

    return module.exit_json(msg=result, changed=changed_status, affected=True, fail=False, failed=fail_status)


if __name__ == '__main__':
    main()
