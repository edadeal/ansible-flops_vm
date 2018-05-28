Ansible module for creating VM via API for flops.ru
===================================================

By default module create VM with Ubuntu 16.04 x64. If you want to use some another please change it in code.

API flops.ru
============
[Description](https://flops.ru/kb/knowledge-base/api-upravleniya-resursami/) 

Examples of usage:
==================

Examples for creating VM, change params and remove VM in flops.yml

Dynamic inventory
=================

After creating or changing params, module write ip adresses into the hosts.ini file
If you nothing changed on VM - nothing will change in you hosts.ini

API key
=======

I recomend to use ansible-vault for encrypt string and save it in you vars file:
```
ansible-vault encrypt_string you_api_key --name flops_api_key
```
